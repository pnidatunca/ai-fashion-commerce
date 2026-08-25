"""
Urun yorumlarini Ingilizce'den Turkce'ye cevirir.

Sitede yorumlar Amazon'dan geldigi icin Ingilizce. Urun
basliklari (title_tr) ve aciklamalari (description_tr) zaten
cevrilmisti; yorumlar cevrilmemisti ve kullanici Turkce bir
sayfada Ingilizce yorum okuyordu.

    olculen durum: 6327 yorum, 0'i cevrilmis,
                   ~2.24 milyon karakter, 700 urune dagilmis


NEDEN AYRI KOLON, USTUNE YAZMIYORUZ
-----------------------------------
review_title_tr / review_text_tr kolonlarina yaziyor,
orijinali BOZMUYOR. Sebepleri:

  1. Ceviri kalitesi denetlenebilir olmali. Orijinal
     silinirse "bu ceviri dogru mu" sorusu cevaplanamaz.

  2. Geri donus mumkun kalir: ceviri bos veya basarisizsa
     arayuz orijinali gosteriyor (frontend'de reviewTitle /
     reviewText yardimcilari).

  3. sentiment_score orijinal Ingilizce metne gore
     hesaplanmis; metni degistirmek o skoru gecersiz kilardi.

Ayni desen urun basliklarinda da kullanildi (title /
title_tr yan yana duruyor).


IDEMPOTENT VE KALDIGI YERDEN DEVAM EDER
---------------------------------------
Yalnizca cevirisi eksik satirlari secer. Yarida kesilirse
tekrar calistirmak kaldigi yerden devam eder; ayni yorumu
iki kez cevirip para harcamaz.

6327 yorum tek oturumda bitmeyebilir (API limiti, ag hatasi).
Bu yuzden her parti KENDI ICINDE kaydediliyor: 300. partide
hata olsa bile ilk 299 parti veritabaninda kalir.


PARTI BOYUTU KARAKTERE GORE, SABIT SAYIYA GORE DEGIL
----------------------------------------------------
Yorum uzunlugu cok degisken: ortalama 331 karakter ama en
uzun 15.329 karakter. Sabit "20 yorum" dersek, uzun
yorumlardan olusan bir parti model context'ini tasiriyor ve
cevap kesiliyor (JSON bozuk geliyor).

Karakter butcesi ile bolmek bunu onluyor. Tek basina
butceden buyuk olan yorum kendi partisinde gidiyor.


DONEN VERI DOGRULANIYOR
-----------------------
Model bazen istenmeyen sey yapar: eksik oge dondurur, olmayan
bir review_id uydurur, bos ceviri verir. Uc kontrol var:

  1. review_id gonderdigimiz kumede DEGILSE yazilmaz
     (uydurma kimlige yazmak baska yorumu bozar)
  2. bos ceviri yazilmaz — satir "cevrilmemis" kalir ve
     sonraki calistirmada tekrar denenir
  3. eksik donen ogeler raporlanir

Kullanim:

    python scripts/14_translate_reviews.py               # hepsi
    python scripts/14_translate_reviews.py --limit 50    # ilk 50
    python scripts/14_translate_reviews.py --dry-run     # yazmadan
    python scripts/14_translate_reviews.py --status      # durum

Tek surecte ~3 saat suruyor (sure API gecikmesinden geliyor,
isten degil). Paralel calistirmak icin dort ayri terminalde:

    python scripts/14_translate_reviews.py --shard 0/4
    python scripts/14_translate_reviews.py --shard 1/4
    python scripts/14_translate_reviews.py --shard 2/4
    python scripts/14_translate_reviews.py --shard 3/4

Dilimler review_id hash'ine gore bolundugu icin KESISMEZ;
ayni yorum iki kez cevrilmez.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
from sqlalchemy import text

from app.database import engine

load_dotenv(ROOT / ".env")


# =========================================================
# AYARLAR
# =========================================================

# gemini-2.5-flash-lite ARTIK YOK: API "no longer available
# to new users" diyip 3.5'e yonlendiriyor. Model adini
# sabitlemek yerine listeden ilk calisani seciyoruz ki
# bir sonraki kullanimdan dusme durumu isi durdurmasin.
MODEL_CANDIDATES = (
    "gemini-3.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
)

# Bir partideki en fazla karakter (baslik + metin toplami).
# Model context'i cok daha buyuk ama cevap JSON'u da ayni
# uzunlukta donuyor; 6000 karakter guvenli ve hizli.
BATCH_CHAR_BUDGET = 6000

# Bir partide en fazla yorum (kisa yorumlarda partiyi
# gereksiz sismekten korur)
BATCH_MAX_ITEMS = 25

# Gecici hatada tekrar deneme
MAX_RETRIES = 4
RETRY_BASE_SLEEP = 3.0

# Partiler arasi bekleme (hiz limitine takilmamak icin)
BETWEEN_BATCHES = 0.4


PROMPT_HEADER = """You are a professional English-to-Turkish translator
working on an e-commerce site's customer reviews.

Translate each review into natural, fluent Turkish that a Turkish
shopper would actually write.

RULES:
1. Preserve the original meaning and tone. A sarcastic review stays
   sarcastic; an enthusiastic one stays enthusiastic.
2. Do not add or remove information.
3. Keep brand names, product names, model numbers and sizes
   unchanged (e.g. "Levi's 501", "XL", "US 10").
4. Convert nothing else: do not convert prices or units.
5. If the title is empty, return an empty string for it.
6. Return ONLY a valid JSON array. No Markdown, no commentary.
7. Return the SAME review_id you were given, unchanged.
8. Return one object for EVERY review given.

Output format:

[
  {"review_id": "...", "review_title_tr": "...", "review_text_tr": "..."}
]

Reviews to translate:

"""


# =========================================================
# VERITABANI
# =========================================================

SELECT_PENDING = """
    SELECT review_id, review_title, review_text
    FROM reviews
    WHERE
        (review_text IS NOT NULL AND review_text <> '')
        AND (
            review_text_tr IS NULL OR review_text_tr = ''
        )
        {shard}
    ORDER BY helpful_votes DESC NULLS LAST, review_id
    LIMIT :limit
"""

# PARALEL CALISTIRMA (--shard)
#
# 6289 yorum tek surecte ~3 saat suruyor: her API cagrisi
# ~28 saniye ve 396 parti var. Sure API gecikmesinden
# geliyor, isten degil — yani beklemek bosa gecen zaman.
#
# Cozum: isi review_id hash'ine gore BOLUP birkac sureci
# ayni anda calistirmak.
#
#     python scripts/14_translate_reviews.py --shard 0/4
#     python scripts/14_translate_reviews.py --shard 1/4
#     python scripts/14_translate_reviews.py --shard 2/4
#     python scripts/14_translate_reviews.py --shard 3/4
#
# Neden hash ile bolme, LIMIT/OFFSET degil: OFFSET kullanan
# iki surec ayni satirlari secebilir (aradaki satirlar
# guncellendikce pencere kayiyor) ve ayni yorumu iki kez
# cevirip para harcar. Hash bolumu KESISMEZ.
#
# Yazma tarafi zaten review_id'ye gore UPDATE oldugu icin
# cakisma bozulma uretmiyor; hash bolmesi yalnizca bosa
# giden cagriyi engelliyor.
SHARD_CLAUSE = "AND (abs(hashtext(review_id)) % :shard_total) = :shard_index"

UPDATE_ONE = """
    UPDATE reviews
    SET review_title_tr = :title_tr,
        review_text_tr = :text_tr
    WHERE review_id = :review_id
"""


def fetch_status():
    """Kac yorum var, kaci cevrilmis."""

    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM reviews")
        ).scalar()

        translatable = conn.execute(
            text(
                "SELECT count(*) FROM reviews "
                "WHERE review_text IS NOT NULL AND review_text <> ''"
            )
        ).scalar()

        done = conn.execute(
            text(
                "SELECT count(*) FROM reviews "
                "WHERE review_text_tr IS NOT NULL "
                "AND review_text_tr <> ''"
            )
        ).scalar()

    return total, translatable, done


def fetch_pending(limit, shard=None):
    """
    shard: (index, total) veya None
    """

    params = {"limit": limit}

    if shard:
        clause = SHARD_CLAUSE
        params["shard_index"] = shard[0]
        params["shard_total"] = shard[1]
    else:
        clause = ""

    query = SELECT_PENDING.format(shard=clause)

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).fetchall()

    return [
        {
            "review_id": r[0],
            "review_title": r[1] or "",
            "review_text": r[2] or "",
        }
        for r in rows
    ]


def save_batch(translations, allowed_ids):
    """
    Ceviriyi yazar. Uc kontrol uyguluyor.

    Donen: (yazilan, atlanan_bos, atlanan_bilinmeyen)
    """

    written = 0
    empty = 0
    unknown = 0

    with engine.begin() as conn:
        for item in translations:

            if not isinstance(item, dict):
                unknown += 1
                continue

            review_id = str(item.get("review_id") or "").strip()

            # 1. Uydurma kimlige YAZMIYORUZ. Modelin
            #    hallusinasyonu baska bir yorumun uzerine
            #    yazabilir.
            if review_id not in allowed_ids:
                unknown += 1
                continue

            text_tr = (item.get("review_text_tr") or "").strip()
            title_tr = (item.get("review_title_tr") or "").strip()

            # 2. Bos ceviri YAZILMIYOR: satir "cevrilmemis"
            #    kalsin ve sonraki calistirmada tekrar
            #    denensin. Bos yazmak onu "bitti" sayardi.
            if not text_tr:
                empty += 1
                continue

            conn.execute(
                text(UPDATE_ONE),
                {
                    "title_tr": title_tr,
                    "text_tr": text_tr,
                    "review_id": review_id,
                },
            )

            written += 1

    return written, empty, unknown


# =========================================================
# PARTILEME
# =========================================================

def make_batches(reviews):
    """
    Karakter butcesine gore parti olusturur.

    Butceden buyuk tek bir yorum kendi partisinde gider —
    aksi halde hicbir partiye sigmaz ve sonsuza kadar
    atlanir.
    """

    batches = []
    current = []
    current_chars = 0

    for review in reviews:

        size = len(review["review_title"]) + len(review["review_text"])

        too_big = size >= BATCH_CHAR_BUDGET

        if too_big:
            if current:
                batches.append(current)
                current = []
                current_chars = 0

            batches.append([review])
            continue

        over_budget = current_chars + size > BATCH_CHAR_BUDGET
        over_count = len(current) >= BATCH_MAX_ITEMS

        if current and (over_budget or over_count):
            batches.append(current)
            current = []
            current_chars = 0

        current.append(review)
        current_chars += size

    if current:
        batches.append(current)

    return batches


# =========================================================
# GEMINI
# =========================================================

_client = None
_model = None


def get_client():
    global _client

    if _client is not None:
        return _client

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY bulunamadi. Repo kokundeki .env "
            "dosyasini kontrol et."
        )

    from google import genai

    _client = genai.Client(api_key=api_key)

    return _client


def pick_model():
    """
    Calisan ilk modeli secer.

    Model adini sabitlemek kirilgan: gemini-2.5-flash-lite
    kullanimdan dustu ve eski script 404 aliyordu.
    """

    global _model

    if _model is not None:
        return _model

    client = get_client()

    probe = [
        {
            "review_id": "probe",
            "review_title": "Great",
            "review_text": "Fits well and looks good.",
        }
    ]

    for name in MODEL_CANDIDATES:
        try:
            client.models.generate_content(
                model=name,
                contents=PROMPT_HEADER
                + json.dumps(probe, ensure_ascii=False),
                config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                },
            )
        except Exception as error:
            print("  model %-24s kullanilamiyor (%s)"
                  % (name, str(error)[:60]))
            continue

        _model = name
        return name

    raise RuntimeError(
        "Hicbir Gemini modeli calismadi. MODEL_CANDIDATES "
        "listesini guncelle."
    )


def translate_batch(batch):
    """
    Bir partiyi cevirir. Gecici hatalarda tekrar dener.

    Donen: liste (bos olabilir)
    """

    client = get_client()
    model = pick_model()

    payload = json.dumps(batch, ensure_ascii=False, indent=1)

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            response = client.models.generate_content(
                model=model,
                contents=PROMPT_HEADER + payload,
                config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                },
            )

            raw = (response.text or "").strip()

            if not raw:
                raise ValueError("model bos cevap dondurdu")

            parsed = json.loads(raw)

            if isinstance(parsed, dict):
                # Bazen {"reviews": [...]} sarmaliyor
                for key in ("reviews", "data", "items", "result"):
                    if isinstance(parsed.get(key), list):
                        parsed = parsed[key]
                        break

            if not isinstance(parsed, list):
                raise ValueError("beklenen JSON dizisi degil")

            return parsed

        except Exception as error:
            last_error = error

            if attempt >= MAX_RETRIES:
                break

            sleep_for = RETRY_BASE_SLEEP * attempt

            print(
                "    deneme %d/%d basarisiz (%s) — %.0fs sonra tekrar"
                % (attempt, MAX_RETRIES, str(error)[:70], sleep_for)
            )

            time.sleep(sleep_for)

    print("    PARTI ATLANDI: %s" % str(last_error)[:90])

    return []


# =========================================================
# MAIN
# =========================================================

def main():
    parser = argparse.ArgumentParser(
        description="Yorumlari Ingilizce'den Turkce'ye cevirir."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="En fazla kac yorum cevrilsin (0 = hepsi)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Cevirir ama veritabanina yazmaz",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Yalnizca durum raporu",
    )
    parser.add_argument(
        "--shard",
        type=str,
        default=None,
        metavar="I/N",
        help=(
            "Isin bir dilimini isle (ör. 0/4). Birkac sureci "
            "ayni anda calistirmak icin; dilimler kesismez."
        ),
    )
    args = parser.parse_args()

    shard = None

    if args.shard:
        try:
            index_text, total_text = args.shard.split("/")
            shard = (int(index_text), int(total_text))
        except ValueError:
            parser.error("--shard bicimi I/N olmali (ör. 0/4)")

        if not (0 <= shard[0] < shard[1]):
            parser.error("--shard: 0 <= I < N olmali")

    total, translatable, done = fetch_status()
    pending_count = translatable - done

    print("=" * 62)
    print("YORUM CEVIRISI  (Ingilizce -> Turkce)")
    print("=" * 62)
    print("  toplam yorum        : %d" % total)
    print("  cevrilebilir (metni olan): %d" % translatable)
    print("  cevrilmis           : %d" % done)
    print("  bekleyen            : %d" % pending_count)

    if translatable:
        print("  tamamlanma          : %%%.1f"
              % (100.0 * done / translatable))

    print()

    if args.status:
        return

    if pending_count <= 0:
        print("Cevrilecek yorum yok.")
        return

    limit = args.limit if args.limit > 0 else pending_count

    reviews = fetch_pending(limit, shard=shard)

    if not reviews:
        print("Cevrilecek yorum yok.")
        return

    batches = make_batches(reviews)

    chars = sum(
        len(r["review_title"]) + len(r["review_text"])
        for r in reviews
    )

    if shard:
        print("  dilim               : %d/%d" % (shard[0], shard[1]))

    print("  bu calistirmada     : %d yorum" % len(reviews))
    print("  parti sayisi        : %d" % len(batches))
    print("  karakter            : %d" % chars)
    print("  model               : ", end="", flush=True)

    model = pick_model()
    print(model)

    if args.dry_run:
        print()
        print("  --dry-run: veritabanina YAZILMAYACAK")

    print()

    written_total = 0
    empty_total = 0
    unknown_total = 0
    missing_total = 0
    started = time.time()

    for index, batch in enumerate(batches, 1):

        allowed = {r["review_id"] for r in batch}

        batch_chars = sum(
            len(r["review_title"]) + len(r["review_text"])
            for r in batch
        )

        print(
            "  [%4d/%d] %2d yorum, %5d karakter ... "
            % (index, len(batches), len(batch), batch_chars),
            end="",
            flush=True,
        )

        translations = translate_batch(batch)

        if not translations:
            print()
            continue

        returned_ids = {
            str(t.get("review_id") or "").strip()
            for t in translations
            if isinstance(t, dict)
        }

        missing = allowed - returned_ids
        missing_total += len(missing)

        if args.dry_run:
            print("%d ceviri alindi (yazilmadi)" % len(translations))

            for item in translations[:1]:
                if isinstance(item, dict):
                    print(
                        "            ornek: %s"
                        % (item.get("review_title_tr") or "")[:60]
                    )

            continue

        written, empty, unknown = save_batch(translations, allowed)

        written_total += written
        empty_total += empty
        unknown_total += unknown

        notes = []

        if empty:
            notes.append("%d bos" % empty)
        if unknown:
            notes.append("%d bilinmeyen kimlik" % unknown)
        if missing:
            notes.append("%d donmedi" % len(missing))

        print(
            "%d yazildi%s"
            % (written, (" (%s)" % ", ".join(notes)) if notes else "")
        )

        if index < len(batches):
            time.sleep(BETWEEN_BATCHES)

    elapsed = time.time() - started

    print()
    print("=" * 62)
    print("SONUC")
    print("=" * 62)
    print("  yazilan             : %d" % written_total)

    if empty_total:
        print("  bos ceviri (atlandi): %d" % empty_total)
    if unknown_total:
        print("  bilinmeyen kimlik   : %d" % unknown_total)
    if missing_total:
        print("  hic donmeyen        : %d" % missing_total)

    print("  sure                : %.1f dakika" % (elapsed / 60))

    total, translatable, done = fetch_status()

    print()
    print("  guncel durum        : %d / %d cevrilmis (%%%.1f)"
          % (done, translatable,
             100.0 * done / translatable if translatable else 0))

    remaining = translatable - done

    if remaining > 0:
        print()
        print("  %d yorum kaldi. Ayni komutu tekrar calistir:" % remaining)
        print("      python scripts/14_translate_reviews.py")


if __name__ == "__main__":
    main()
