"""
MUSTERI YORUMLARINDAN BEDEN/KALIP SINYALI CIKARIR.

NEDEN BU SCRIPT VAR
-------------------
"Bu urun kalibina uygun mu, bir beden buyuk mu almaliyim?"
sorusu e-ticarette iadenin bir numarali sebebi. Katalogda
beden tablosu YOK — ama 6327 musteri yorumu var ve insanlar
tam olarak bunu yaziyor.

Olculdu (728 urun, 6327 yorum):

    yorumu olan urun            : 700 / 728
    kesin kalip ifadesi tasiyan : 460 / 728  (%63)

Mimari olarak color_match / product_style_scores ile ayni
desen: pahali metin taramasini BIR KEZ yap, kolona yaz,
sorguda yalnizca oku.


NEDEN LLM DEGIL
---------------
outfit.py'deki gerekcenin aynisi artı bir tane daha:

  1. KOTA. 6327 yorum var. Ucretsiz katman dakikada 5 istek
     veriyor. Yorum basina cagri 21 saat, urun basina toplu
     cagri (700 istek) 2.5 saat surer.
  2. BELIRLILIK. "runs small" ifadesi kalip sinyalidir; bunu
     bir kural tablosu her seferinde ayni sekilde bulur.
  3. DENETLENEBILIRLIK. Kullaniciya "12 yorumdan 9'u kucuk
     geldigini soyluyor" diyeceksek o 9'u gosterebilmemiz
     lazim. Regex hangi yorumun neden sayildigini biliyor.


EN BUYUK TUZAK: OLUMSUZLAMA
---------------------------
Ilk denemede tek kelimeli sifatlar da (tight, snug, roomy,
baggy) sinyal sayilmisti. Kapsam %80'e cikiyordu. Ornekler
okundu ve cogunlugun TERSINE isaret ettigi goruldu:

    "Not tight not too baggy"          -> urun IYI oturuyor
    "not too tight or too baggy"       -> urun IYI oturuyor
    "Not too loose and not too snug"   -> urun IYI oturuyor
    "the buttonholes are slightly tight"  -> beden degil, ILIK
    "slim fit is flattering without being too tight" -> ovgu

Yani "baggy" gecen bir yorumu "buyuk geliyor" saymak
kullaniciya TERS tavsiye vermek olurdu. Yanlis beden
tavsiyesi iadeyi azaltmaz, artirir.

Cozum: tek kelimeli sifatlar TAMAMEN ATILDI. Yalnizca cok
kelimeli, kasitli ifadeler sayiliyor ("runs small", "size
up", "true to size"). Bu ifadelerde olumsuzlama olcum
sonucu %1 — cunku "not runs small" dogal Ingilizce degil.
O %1 icin de yine bir olumsuzluk kontrolu var.

Bedeli: kapsam %80'den %63'e dusuyor. Bilincli tercih;
projenin baska yerlerinde de ayni karar verilmisti (bkz.
AI_PERSONALIZATION.md, badge esigi altinda yuzde
gosterilmiyor): bos bir iddia yerine hicbir iddia.


review_text KULLANILIYOR, source_cleaned KULLANILMIYOR
------------------------------------------------------
reviews tablosunda iki metin var. source_cleaned_review_text
stopword'leri atilmis halde:

    "love look good fit well comfortable breathable"

Yani "not" kelimesi SILINMIS. Olumsuzlama kontrolu o metinde
imkansiz. Ham review_text kullaniliyor.


KULLANIM
--------
    python scripts/17_extract_fit_signals.py --dry-run
    python scripts/17_extract_fit_signals.py
    python scripts/17_extract_fit_signals.py --report
    python scripts/17_extract_fit_signals.py --explain B08MQWFCVF
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text

from app.database import engine


# =========================================================
# IFADE TABLOSU
# =========================================================
#
# Hepsi COK KELIMELI ve kasitli. Tek kelimeli sifatlar
# (tight/snug/roomy/baggy/loose) BILEREK YOK — dosya
# basindaki olumsuzlama notuna bak.
#
# Sayilar olculdu (kac yorumda geciyor):
#   SMALL -> 197 yorum / 163 urun
#   LARGE -> 141 yorum / 108 urun
#   TRUE  -> 546 yorum / 365 urun

SMALL_PATTERNS = [
    r"runs?\s+(?:a\s+bit\s+|a\s+little\s+|slightly\s+|very\s+)?small",
    r"size[sd]?\s+up",
    r"order(?:ed)?\s+(?:a\s+|one\s+)?size\s+up",
    r"go(?:ing)?\s+up\s+a\s+size",
    r"smaller\s+than\s+(?:expected|usual|advertised)",
]

LARGE_PATTERNS = [
    r"runs?\s+(?:a\s+bit\s+|a\s+little\s+|slightly\s+|very\s+)?(?:large|big)",
    r"size[sd]?\s+down",
    r"order(?:ed)?\s+(?:a\s+|one\s+)?size\s+down",
    r"go(?:ing)?\s+down\s+a\s+size",
    r"(?:larger|bigger)\s+than\s+(?:expected|usual|advertised)",
]

TRUE_PATTERNS = [
    r"true\s+to\s+size",
    r"fits?\s+true",
    r"runs?\s+true",
    r"fits?\s+(?:perfectly|as\s+expected|just\s+right)",
]


def _compile(patterns):
    return [re.compile(p, re.IGNORECASE) for p in patterns]


SMALL_RE = _compile(SMALL_PATTERNS)
LARGE_RE = _compile(LARGE_PATTERNS)
TRUE_RE = _compile(TRUE_PATTERNS)


# Olumsuzluk belirteci. Eslesmeden ONCEKI kisa pencerede
# aranıyor.
NEGATION_RE = re.compile(
    r"\b(?:not|no|never|dont|doesnt|didnt|isnt|wasnt|arent|"
    r"don't|doesn't|didn't|isn't|wasn't|aren't)\b",
    re.IGNORECASE,
)

# Olumsuzluk kac karakter geriye kadar aranacak. 28 secildi:
# "does not seem to run small" gibi araya birkac kelime giren
# halleri yakalar, ama onceki CUMLEDEKI bir "not"u yanlislikla
# almayacak kadar kisa. Cumle siniri ayrica kontrol ediliyor.
NEGATION_WINDOW = 28

SENTENCE_END_RE = re.compile(r"[.!?]")


def _is_negated(sentence_text: str, start: int) -> bool:
    """
    Eslesmenin hemen oncesinde olumsuzluk var mi?

    Cumle siniri gecilmiyor: onceki cumlede "not" olmasi bu
    ifadeyi olumsuzlamaz.
    """

    window_start = max(0, start - NEGATION_WINDOW)

    window = sentence_text[window_start:start]

    # Araya cumle sonu girdiyse yalnizca ondan SONRASINA bak.
    boundaries = list(SENTENCE_END_RE.finditer(window))

    if boundaries:
        window = window[boundaries[-1].end():]

    return bool(NEGATION_RE.search(window))


def classify_review(review_text: str) -> str | None:
    """
    Bir yorumu 'small' / 'large' / 'true' / None olarak
    siniflandirir.

    KURALLAR
    - Bir yorum ayni kategoriden birden fazla ifade tasisa
      bile TEK oy sayilir. Aksi halde tek bir konuskan yorum
      urunun kaderini belirlerdi.
    - Ayni yorumda hem 'small' hem 'large' varsa yorum
      ATILIYOR (None). Cunku ya iki farkli beden deneyip
      anlatiyor ("the L was snug, the XL was roomy") ya da
      baska bir urunle kiyasliyor; hangisini kastettigi
      belirsiz. Belirsiz oy, yanlis oydan iyidir.
    """

    if not review_text:
        return None

    hits = set()

    for label, regexes in (
        ("small", SMALL_RE),
        ("large", LARGE_RE),
        ("true", TRUE_RE),
    ):
        for regex in regexes:

            for match in regex.finditer(review_text):

                if _is_negated(review_text, match.start()):
                    continue

                hits.add(label)
                break

            if label in hits:
                break

    if "small" in hits and "large" in hits:
        return None

    # Celiski: "true to size" + "runs small" ayni yorumda.
    # Kasitli ifade (small/large) daha bilgilendirici, o
    # kazaniyor.
    if "small" in hits:
        return "small"

    if "large" in hits:
        return "large"

    if "true" in hits:
        return "true"

    return None


# =========================================================
# KARAR ESIKLERI — ASIMETRIK
# =========================================================
#
# NEDEN TEK ESIK YOK
# Iki karar tipinin YANLIS OLMA BEDELI ayni degil:
#
#   "kalibina uygun"  yanlissa -> kullanici normal bedenini
#     alir. Zaten tavsiye olmasa da yapacagi sey buydu.
#     Zarar dusuk.
#
#   "bir beden buyuk al" yanlissa -> kullanici BILEREK
#     farkli beden alir. Tavsiye yanlissa iade neredeyse
#     kesin. Yani bu ozelligin amacinin (iadeyi azaltmak)
#     tam tersini uretir.
#
# Bu yuzden beden DEGISTIRME tavsiyesi daha fazla kanit
# istiyor.
#
# OLCULEN SONUC (728 urun, 6327 yorum)
#
#   esik (oy/oran/fark)          kucuk   tam  buyuk   KARAR
#   duz  3 / 0.50 / 2                4    83      5      92
#   duz  2 / 0.50 / 1               14   199     18     231
#   ASIMETRIK (secilen)              4   193      5     202
#
# Duz gevsek esik 231 urune karar veriyordu ama riskli
# kararlarin bir kismi 2-1 bolunmesine dayaniyordu. Secilen
# kuralla riskli karar sayisi 9'a duyuyor ve dokuzunun HEPSI
# net cogunluk + itirazsiz:
#
#   B0BZ5JBZ3T  buyuk=5  itiraz yok
#   B005OLALQI  kucuk=3  itiraz yok
#   B07LGVSPKF  kucuk=4  tam=2  buyuk=0
#
# Az ama guvenilir. 526 urunde hicbir iddia gosterilmiyor.

# "kalibina uygun" — dusuk riskli karar
TRUE_MIN_VOTES = 2
TRUE_MIN_SHARE = 0.60
TRUE_MIN_MARGIN = 1

# "kucuk/buyuk geliyor" — beden degistirme tavsiyesi
RISK_MIN_VOTES = 3
RISK_MIN_SHARE = 0.60
RISK_MIN_MARGIN = 2


def decide(small: int, true_fit: int, large: int) -> tuple[str | None, float]:
    """
    Oylardan karar ve guven uretir.

    Doner: (verdict, confidence)
    verdict None ise arayuzde HICBIR iddia gosterilmiyor.
    """

    total = small + true_fit + large

    if total < TRUE_MIN_VOTES:
        return None, 0.0

    counts = {"small": small, "true": true_fit, "large": large}

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)

    winner, top = ranked[0]
    second = ranked[1][1]

    # Esik kazanan karara gore degisiyor (yukaridaki nota bak).
    if winner == "true":
        min_votes = TRUE_MIN_VOTES
        min_share = TRUE_MIN_SHARE
        min_margin = TRUE_MIN_MARGIN
    else:
        min_votes = RISK_MIN_VOTES
        min_share = RISK_MIN_SHARE
        min_margin = RISK_MIN_MARGIN

    if total < min_votes:
        return None, 0.0

    if top / total < min_share:
        return None, 0.0

    if top - second < min_margin:
        return None, 0.0

    # Guven: hem oranı hem hacmi yansitiyor. Tek basina oran
    # yeterli degil — 3'te 3 ile 30'da 30 ayni guveni
    # tasimiyor. 12 oy doygunluk noktasi kabul edildi.
    share = top / total
    volume = min(1.0, total / 12.0)

    confidence = round(share * (0.55 + 0.45 * volume), 3)

    return winner, confidence


# Kullaniciya gosterilecek metin app/fit_advice.py'de.
#
# Neden orada: metni ASIL kullanan taraf uygulama (urun
# sayfasi ve asistan). Script yalnizca --explain ciktisinda
# gosteriyor. Iki yerde ayri yazilsaydi biri gun gelip
# guncellenmezdi.
from app.fit_advice import VERDICT_LABELS


# =========================================================
# MIGRATION
# =========================================================

MIGRATION = [
    ("fit_small_votes", "integer"),
    ("fit_true_votes", "integer"),
    ("fit_large_votes", "integer"),
    ("fit_verdict", "varchar(16)"),
    ("fit_confidence", "double precision"),
]


def migrate():
    """Kolonlari ekler. Idempotent."""

    added = []

    with engine.begin() as conn:

        for name, sql_type in MIGRATION:

            exists = conn.execute(
                text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'products'
                      AND column_name = :c
                """),
                {"c": name},
            ).scalar()

            if exists:
                continue

            conn.execute(
                text(
                    "ALTER TABLE products ADD COLUMN %s %s"
                    % (name, sql_type)
                )
            )

            added.append(name)

        # Arama/siralama "kalibi kucuk olanlari getir" gibi
        # filtreler icin verdict uzerinden gidecek.
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_products_fit_verdict
            ON products (fit_verdict)
        """))

    return added


# =========================================================
# HESAPLAMA
# =========================================================

def compute_all() -> dict:
    """
    Butun yorumlari tarar ve urun basina oylari doner.

    {product_id: Counter({'small': n, 'true': n, 'large': n})}
    """

    votes: dict[str, Counter] = {}

    with engine.connect() as conn:

        rows = conn.execute(text("""
            SELECT product_id, review_text
            FROM reviews
            WHERE review_text IS NOT NULL
              AND review_text <> ''
        """))

        for product_id, review_text in rows:

            label = classify_review(review_text)

            if label is None:
                continue

            votes.setdefault(product_id, Counter())[label] += 1

    return votes


def save(votes: dict) -> int:
    """Oylari ve kararlari products'a yazar."""

    written = 0

    with engine.begin() as conn:

        for product_id, counter in votes.items():

            small = counter.get("small", 0)
            true_fit = counter.get("true", 0)
            large = counter.get("large", 0)

            verdict, confidence = decide(small, true_fit, large)

            conn.execute(
                text("""
                    UPDATE products SET
                        fit_small_votes = :s,
                        fit_true_votes  = :t,
                        fit_large_votes = :l,
                        fit_verdict     = :v,
                        fit_confidence  = :c
                    WHERE product_id = :pid
                """),
                {
                    "s": small,
                    "t": true_fit,
                    "l": large,
                    "v": verdict,
                    "c": confidence,
                    "pid": product_id,
                },
            )

            written += 1

    return written


# =========================================================
# RAPORLAR
# =========================================================

def print_distribution(votes: dict) -> None:

    total_products = 0

    with engine.connect() as conn:
        total_products = conn.execute(
            text("SELECT COUNT(*) FROM products")
        ).scalar()

    verdicts = Counter()
    vote_totals = Counter()

    for counter in votes.values():

        small = counter.get("small", 0)
        true_fit = counter.get("true", 0)
        large = counter.get("large", 0)

        verdict, _ = decide(small, true_fit, large)

        verdicts[verdict or "kararsiz"] += 1

        vote_totals[small + true_fit + large] += 1

    print("  SINYALI OLAN URUN : %d / %d (%%%d)" % (
        len(votes), total_products,
        len(votes) * 100 // max(1, total_products),
    ))
    print()

    print("  KARAR DAGILIMI")

    for name, label in (
        ("small", "kalibi kucuk"),
        ("true", "kalibina uygun"),
        ("large", "kalibi buyuk"),
        ("kararsiz", "KARARSIZ (iddia yok)"),
    ):
        count = verdicts.get(name, 0)

        print("    %-22s %4d urun" % (label, count))

    karar_verilen = sum(
        v for k, v in verdicts.items() if k != "kararsiz"
    )

    print()
    print("    karar verilebilen  : %d / %d urun (%%%d)" % (
        karar_verilen, total_products,
        karar_verilen * 100 // max(1, total_products),
    ))
    print()

    print("  OY SAYISI DAGILIMI (urun basina)")

    for n in sorted(vote_totals)[:10]:
        print("    %2d oy -> %4d urun" % (n, vote_totals[n]))


def report() -> None:
    """Veritabanina yazilmis halin ozeti."""

    with engine.connect() as conn:

        print("=" * 62)
        print("BEDEN/KALIP SINYALI — MEVCUT DURUM")
        print("=" * 62)

        rows = conn.execute(text("""
            SELECT COALESCE(fit_verdict, 'kararsiz') AS v,
                   COUNT(*) AS n,
                   ROUND(AVG(fit_confidence)::numeric, 3) AS guven
            FROM products
            WHERE fit_small_votes IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC
        """))

        for verdict, count, confidence in rows:
            print("  %-12s %4d urun   ortalama guven: %s" % (
                verdict, count, confidence,
            ))

        print()

        print("  EN GUVENILIR ORNEKLER")

        rows = conn.execute(text("""
            SELECT product_id, fit_verdict, fit_confidence,
                   fit_small_votes, fit_true_votes,
                   fit_large_votes,
                   COALESCE(title_tr, title)
            FROM products
            WHERE fit_verdict IS NOT NULL
            ORDER BY fit_confidence DESC, fit_true_votes DESC
            LIMIT 8
        """))

        for pid, verdict, conf, s, t, l, title in rows:
            print("    %-12s %-6s %.2f  (k%d/t%d/b%d)  %s" % (
                pid, verdict, conf, s, t, l, (title or "")[:38],
            ))


def explain(product_id: str) -> None:
    """
    Bir urunun kararini GEREKCESIYLE gosterir.

    Denetlenebilirlik icin: "12 yorumdan 9'u kucuk demis"
    diyorsak o 9 yorumu gosterebilmemiz lazim.
    """

    with engine.connect() as conn:

        rows = conn.execute(
            text("""
                SELECT review_text FROM reviews
                WHERE product_id = :pid
                  AND review_text IS NOT NULL
            """),
            {"pid": product_id},
        ).fetchall()

    if not rows:
        print("  Bu urunun yorumu yok.")
        return

    counter = Counter()

    print("=" * 62)
    print("KALIP GEREKCESI: %s" % product_id)
    print("=" * 62)
    print("  toplam yorum: %d" % len(rows))
    print()

    for (review_text,) in rows:

        label = classify_review(review_text)

        if label is None:
            continue

        counter[label] += 1

        snippet = " ".join(review_text.split())[:120]

        print("  [%s] %s" % (label.upper(), snippet))

    print()

    verdict, confidence = decide(
        counter.get("small", 0),
        counter.get("true", 0),
        counter.get("large", 0),
    )

    print("  oylar  : kucuk=%d  tam=%d  buyuk=%d" % (
        counter.get("small", 0),
        counter.get("true", 0),
        counter.get("large", 0),
    ))
    print("  KARAR  : %s (guven %.2f)" % (
        verdict or "KARARSIZ — iddia gosterilmez", confidence,
    ))

    if verdict:
        title, advice = VERDICT_LABELS[verdict]
        print("  etiket : %s" % title)
        print("  tavsiye: %s" % advice)


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Musteri yorumlarindan beden/kalip sinyali cikarir."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hesaplar ve dagilimi yazar, veritabanina YAZMAZ.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Veritabanindaki mevcut halin ozeti.",
    )
    parser.add_argument(
        "--explain",
        metavar="PRODUCT_ID",
        help="Bir urunun kararini gerekcesiyle gosterir.",
    )

    args = parser.parse_args()

    if args.report:
        report()
        return

    if args.explain:
        explain(args.explain)
        return

    print("=" * 62)
    print("BEDEN/KALIP SINYALI CIKARIMI")
    print("=" * 62)

    print("  yorumlar taraniyor...")

    votes = compute_all()

    print()

    print_distribution(votes)

    print()

    if args.dry_run:
        print("  --dry-run: veritabanina YAZILMADI.")
        return

    added = migrate()

    if added:
        print("  eklenen kolonlar:", ", ".join(added))

    written = save(votes)

    print("  %d urun guncellendi." % written)
    print()
    print("  Hazir. Ozet icin: --report")


if __name__ == "__main__":
    main()
