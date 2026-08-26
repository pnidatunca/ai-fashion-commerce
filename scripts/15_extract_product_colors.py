"""
Urun gorsellerinden BASKIN GIYSI RENGINI cikarir.

NEDEN BU SCRIPT VAR
-------------------
Renk analizi ozelligi ("size pastel tonlar daha cok yakisir")
ancak katalogda o tondan urun BULUNABILIYORSA anlamli. Metne
bakarak bulunamiyor — olculdu:

    rengi metninde gecen urun : 217 / 728  (%30)
    rengi HIC belirtilmemis   : 511 / 728  (%70)
    "pastel" kelimesi gecen   : 0
    "muted/powder/blush/sage" : 0

Bir de tuzak var: "soft" 351 urunde geciyor ama 335'i KUMAS
anlaminda ("soft cotton", "yumusak"). Renk sinyali sayilirsa
%95 yanlis eslesir.

Buna karsilik 728 urunun 728'inde GORSEL var. Yani renk
bilgisi katalogda mevcut, sadece metinde degil piksellerde.
Bu script onu cikarip kolona yaziyor.

Mimari olarak product_style_scores ile ayni desen: pahali
hesabi bir kez yap, sorguda yalnizca JOIN et.


BASKIN RENK NASIL BULUNUYOR
---------------------------
Amazon urun fotograflari beyaz studyo zemininde. Naif
ortalama alinirsa her urun "acik gri" cikar — zeminin
agirligi giysiyi bastirir. Bu yuzden:

    1. Kucult (96px) — hiz ve gurultu azaltma
    2. MERKEZ KIRP (%60) — giysi ortada, zemin kenarda
    3. ZEMIN AYIKLA — cok acik + doygunlugu dusuk pikseller
       (beyaz zemin, golge) ve cok koyu pikseller (etiket,
       govde golgesi) atilir
    4. Lab uzayinda KABA HISTOGRAM — en agir kutu bulunur
       (mod arama). Ortalama degil: iki renkli bir urunde
       ortalama ikisinin arasinda var olmayan bir renk uretir
    5. O kutudaki piksellerin ortalamasi = baskin renk

Neden Lab: renk yakinligi Lab'da algiyla ortusuyor. RGB'de
esit sayisal uzaklik esit gorsel fark demek degil; eslestirme
ileride DeltaE ile yapilacak ve o da Lab istiyor.


IDEMPOTENT
----------
Yalnizca rengi henuz cikarilmamis urunleri isler. Yarida
kesilirse tekrar calistirmak kaldigi yerden devam eder.

Kullanim:
    python scripts/15_extract_product_colors.py --status
    python scripts/15_extract_product_colors.py --limit 20
    python scripts/15_extract_product_colors.py
    python scripts/15_extract_product_colors.py --report
"""

import argparse
import io
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np
from PIL import Image
from sqlalchemy import text

from app.database import engine


# =========================================================
# AYARLAR
# =========================================================

# Gorsel bu boyuta kucultulur. 96px baskin rengi bulmak icin
# fazlasiyla yeterli ve 728 gorseli hizli isliyor.
RESIZE = 96

# Merkezden alinan oran. Giysi kadrajin ortasinda, beyaz
# studyo zemini kenarlarda.
CENTER_CROP = 0.60

# Zemin ayiklama esikleri (Lab)
#
# BG_MIN_L: bundan acik VE doygunlugu dusuk pikseller zemin
# BG_MAX_CHROMA_FOR_LIGHT: "doygunlugu dusuk" siniri
# DARK_MIN_L: bundan koyu pikseller golge/etiket
BG_MIN_L = 88.0
BG_MAX_CHROMA_FOR_LIGHT = 10.0
DARK_MIN_L = 12.0

# Histogram kutu boyutu (Lab birimi)
BIN_L = 10.0
BIN_AB = 12.0

# Gecerli sayilmasi icin gereken en az piksel orani
MIN_VALID_RATIO = 0.04

REQUEST_TIMEOUT = 20
BETWEEN_REQUESTS = 0.05


# =========================================================
# RENK UZAYI DONUSUMU
# =========================================================
#
# colormath gibi bir kutuphane EKLENMEDI: tek ihtiyac
# sRGB -> Lab ve bu 20 satir. Bagimlilik eklemenin bedeli
# (kurulum, surum uyumu) kazanctan buyuk.

_D65 = np.array([0.95047, 1.00000, 1.08883])

_RGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])


def srgb_to_lab(rgb):
    """
    rgb: (N, 3) 0-255 uint8/float  ->  (N, 3) Lab

    Standart sRGB -> linear -> XYZ (D65) -> CIE Lab zinciri.
    """

    rgb = np.asarray(rgb, dtype=np.float64) / 255.0

    # sRGB gama kaldirma
    linear = np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        ((rgb + 0.055) / 1.055) ** 2.4,
    )

    xyz = linear @ _RGB_TO_XYZ.T
    xyz = xyz / _D65

    # XYZ -> Lab
    epsilon = 216.0 / 24389.0
    kappa = 24389.0 / 27.0

    f = np.where(
        xyz > epsilon,
        np.cbrt(xyz),
        (kappa * xyz + 16.0) / 116.0,
    )

    lab = np.empty_like(f)
    lab[:, 0] = 116.0 * f[:, 1] - 16.0
    lab[:, 1] = 500.0 * (f[:, 0] - f[:, 1])
    lab[:, 2] = 200.0 * (f[:, 1] - f[:, 2])

    return lab


# =========================================================
# RENK AILESI VE TON SINIFLARI
# =========================================================

def color_family(l, a, b):
    """
    Lab degerini insan diliyle bir renk ailesine yerlestirir.

    ESIKLER TAHMINLE DEGIL OLCUMLE YAZILDI
    --------------------------------------
    Ilk surumde esikler RGB sezgisiyle konulmustu ve 18
    referans rengin 16'sini yanlis sinifladi. En gorunur
    sonucu: Levi's / Wrangler / Lee JEAN'leri "mor" cikiyordu.

    Sebep: Lab'da hue acisi RGB sezgisiyle ortusmuyor. Olculen
    gercek acilar (atan2(b*, a*), derece):

        bordo        18.9        turkuaz      196.5
        kirmizi      33.4        acik mavi    259.6
        turuncu      61.3        denim orta   271.4
        kahve        64.6        denim koyu   282.4
        bej          82.4        lacivert     291.3
        hardal       90.8        mavi         293.2
        sari         93.6        lila         310.4
        haki        111.6        mor          313.5
        yesil       145.3        pembe        354.5

    Yani mavi ~260-295 arasinda, mor ~310'da. Eski kod
    250-290'i "mor" sayiyordu; butun denim oraya dusuyordu.

    Amac isabetli bir renk ADI degil, filtrelenebilir bir
    GRUP: "bej mi krem mi" tartismasi kullaniciya bir sey
    katmiyor, "mavi mi mor mu" katiyor.
    """

    chroma = float(np.hypot(a, b))

    # Notr eksen: doygunluk cok dusukse renk degil, ton
    if chroma < 8:
        if l >= 82:
            return "beyaz"
        if l >= 60:
            return "acik_gri"
        if l >= 32:
            return "gri"
        return "siyah"

    hue = float(np.degrees(np.arctan2(b, a)) % 360)

    # --- sicak taraf ---

    if hue < 10 or hue >= 330:
        # pembe ile koyu kirmizi ayni acida; ayrim PARLAKLIKTA
        return "pembe" if l >= 58 else "kirmizi"

    if hue < 45:
        return "kirmizi"

    if hue < 75:
        # turuncu, kahve ve bej burada ic ice
        if l >= 70 and chroma < 24:
            return "bej"
        if l < 58:
            return "kahve"
        return "turuncu" if chroma >= 26 else "bej"

    if hue < 105:
        if l >= 70 and chroma < 24:
            return "bej"
        if l < 55:
            return "kahve"
        return "sari"

    # --- yesil ---

    if hue < 175:
        return "yesil"

    # --- soguk taraf ---

    if hue < 300:
        # turkuazdan lacivert/denime kadar hepsi mavi ailesi
        return "mavi"

    if hue < 330:
        return "mor"

    return "pembe"


def tone_class(l, a, b):
    """
    Renk analizi icin gereken UC EKSEN:

        deger       : acik / orta / koyu      (L*)
        doygunluk   : soft / orta / canli     (C*)
        alt ton     : sicak / notr / soguk    (b*'nin isareti)

    "Size pastel tonlar yakisir" cumlesi tam olarak
    "acik + soft" kutusuna denk geliyor.
    """

    chroma = float(np.hypot(a, b))

    if l >= 72:
        value = "acik"
    elif l >= 42:
        value = "orta"
    else:
        value = "koyu"

    if chroma < 14:
        saturation = "soft"
    elif chroma < 34:
        saturation = "orta"
    else:
        saturation = "canli"

    # Alt ton: b* sari-mavi ekseni, sicaklik burada okunuyor
    if chroma < 8:
        undertone = "notr"
    elif b > 6:
        undertone = "sicak"
    elif b < -4:
        undertone = "soguk"
    else:
        undertone = "notr"

    return value, saturation, undertone


def is_pastel(l, a, b):
    """
    Pastel = ACIK + SOFT.

    Katalogda "pastel" kelimesi 0 urunde geciyor; bu yuzden
    pastel bir ETIKET degil, olculen bir konum.
    """

    chroma = float(np.hypot(a, b))
    return bool(l >= 70 and 6 <= chroma < 22)


# =========================================================
# BASKIN RENK
# =========================================================

def dominant_lab(image):
    """
    Gorselin baskin GIYSI rengini Lab olarak dondurur.

    Donen: (l, a, b, gecerli_piksel_orani) veya None
    """

    image = image.convert("RGB")
    image.thumbnail((RESIZE, RESIZE), Image.Resampling.LANCZOS)

    pixels = np.asarray(image, dtype=np.float64)

    height, width = pixels.shape[:2]

    # --- merkez kirp ---
    dy = int(height * (1 - CENTER_CROP) / 2)
    dx = int(width * (1 - CENTER_CROP) / 2)

    crop = pixels[dy:height - dy, dx:width - dx].reshape(-1, 3)

    if crop.shape[0] < 40:
        crop = pixels.reshape(-1, 3)

    total = crop.shape[0]

    lab = srgb_to_lab(crop)

    l = lab[:, 0]
    chroma = np.hypot(lab[:, 1], lab[:, 2])

    # --- zemin ve golge ayikla ---
    background = (l >= BG_MIN_L) & (chroma <= BG_MAX_CHROMA_FOR_LIGHT)
    too_dark = l <= DARK_MIN_L

    keep = ~(background | too_dark)

    valid = lab[keep]
    ratio = valid.shape[0] / float(total)

    if valid.shape[0] < 20 or ratio < MIN_VALID_RATIO:
        # Urun gercekten beyaz olabilir: zemin filtresini
        # gevset ve yalnizca cok koyu pikselleri at.
        keep = ~too_dark
        valid = lab[keep]
        ratio = valid.shape[0] / float(total)

        if valid.shape[0] < 20:
            return None

    # --- kaba histogram: mod arama ---
    keys = np.stack([
        np.floor(valid[:, 0] / BIN_L),
        np.floor(valid[:, 1] / BIN_AB),
        np.floor(valid[:, 2] / BIN_AB),
    ], axis=1).astype(np.int64)

    _, inverse, counts = np.unique(
        keys, axis=0, return_inverse=True, return_counts=True
    )

    heaviest = int(np.argmax(counts))

    cluster = valid[inverse == heaviest]

    mean = cluster.mean(axis=0)

    return float(mean[0]), float(mean[1]), float(mean[2]), float(ratio)


# =========================================================
# VERITABANI
# =========================================================

MIGRATION = [
    ("dominant_l", "double precision"),
    ("dominant_a", "double precision"),
    ("dominant_b", "double precision"),
    ("color_family", "text"),
    ("tone_value", "text"),
    ("tone_saturation", "text"),
    ("tone_undertone", "text"),
    ("is_pastel", "boolean"),
    ("color_pixel_ratio", "double precision"),
]


def migrate():
    """Kolonlari ekler. Idempotent."""

    added = []

    with engine.begin() as conn:
        for name, sql_type in MIGRATION:
            exists = conn.execute(
                text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'products' AND column_name = :c
                """),
                {"c": name},
            ).scalar()

            if exists:
                continue

            conn.execute(
                text("ALTER TABLE products ADD COLUMN %s %s"
                     % (name, sql_type))
            )
            added.append(name)

        # Eslestirme sorgusu tone kolonlarindan filtreleyecek
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_products_tone
            ON products (tone_value, tone_saturation, tone_undertone)
        """))

    return added


def fetch_status():
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM products WHERE image_url IS NOT NULL")
        ).scalar()

        done = conn.execute(
            text("SELECT count(*) FROM products WHERE dominant_l IS NOT NULL")
        ).scalar()

    return total, done


def fetch_pending(limit):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT product_id, image_url
                FROM products
                WHERE image_url IS NOT NULL
                  AND image_url <> ''
                  AND dominant_l IS NULL
                ORDER BY product_id
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

    return [(r[0], r[1]) for r in rows]


UPDATE = """
    UPDATE products
    SET dominant_l = :l,
        dominant_a = :a,
        dominant_b = :b,
        color_family = :family,
        tone_value = :value,
        tone_saturation = :saturation,
        tone_undertone = :undertone,
        is_pastel = :pastel,
        color_pixel_ratio = :ratio
    WHERE product_id = :pid
"""


def save(rows):
    if not rows:
        return 0

    with engine.begin() as conn:
        for row in rows:
            conn.execute(text(UPDATE), row)

    return len(rows)


# =========================================================
# RAPOR — kararin dayanagi
# =========================================================

def report():
    """
    Renk dagilimi. Ozelligin degerli olup olmadigini bu tablo
    soyluyor: katalog ezici cogunlukla siyah/lacivert ise
    "size pastel yakisir" sonucuna gosterilecek urun yok.
    """

    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM products WHERE dominant_l IS NOT NULL")
        ).scalar()

        if not total:
            print("Henuz renk cikarilmamis. Once scripti calistir.")
            return

        print("=" * 62)
        print("RENK AILESI DAGILIMI  (%d urun)" % total)
        print("=" * 62)

        for family, n in conn.execute(text("""
            SELECT color_family, count(*) FROM products
            WHERE color_family IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC
        """)):
            bar = "#" * int(40.0 * n / total)
            print("  %-10s %4d  %5.1f%%  %s" % (family, n, 100.0*n/total, bar))

        print()
        print("=" * 62)
        print("TON EKSENLERI")
        print("=" * 62)

        for label, column in [
            ("deger", "tone_value"),
            ("doygunluk", "tone_saturation"),
            ("alt ton", "tone_undertone"),
        ]:
            print("  %s:" % label)
            for value, n in conn.execute(text("""
                SELECT %s, count(*) FROM products
                WHERE %s IS NOT NULL GROUP BY 1 ORDER BY 2 DESC
            """ % (column, column))):
                print("    %-8s %4d  %5.1f%%" % (value, n, 100.0*n/total))
            print()

        pastel = conn.execute(text(
            "SELECT count(*) FROM products WHERE is_pastel"
        )).scalar()

        print("=" * 62)
        print("KARAR ICIN ONEMLI SAYILAR")
        print("=" * 62)
        print("  pastel (acik + soft)  : %d  (%%%.1f)"
              % (pastel, 100.0 * pastel / total))

        for label, where in [
            ("sicak alt ton", "tone_undertone = 'sicak'"),
            ("soguk alt ton", "tone_undertone = 'soguk'"),
            ("canli / doygun", "tone_saturation = 'canli'"),
            ("koyu",           "tone_value = 'koyu'"),
            ("acik",           "tone_value = 'acik'"),
        ]:
            n = conn.execute(text(
                "SELECT count(*) FROM products WHERE %s" % where
            )).scalar()
            print("  %-21s : %d  (%%%.1f)" % (label, n, 100.0 * n / total))


# =========================================================
# MAIN
# =========================================================

def main():
    parser = argparse.ArgumentParser(
        description="Urun gorsellerinden baskin rengi cikarir."
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    if args.report:
        report()
        return

    added = migrate()

    if added:
        print("eklenen kolonlar:", ", ".join(added))
        print()

    total, done = fetch_status()

    print("=" * 62)
    print("URUN RENK CIKARIMI")
    print("=" * 62)
    print("  gorseli olan urun : %d" % total)
    print("  rengi cikarilmis  : %d" % done)
    print("  bekleyen          : %d" % (total - done))
    print()

    if args.status:
        return

    pending = fetch_pending(
        args.limit if args.limit > 0 else (total - done)
    )

    if not pending:
        print("Islenecek urun yok.")
        print()
        report()
        return

    print("  bu calistirmada   : %d urun" % len(pending))
    print()

    written = 0
    failed = 0
    batch = []
    started = time.time()

    for index, (pid, url) in enumerate(pending, 1):

        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )

            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT
            ) as response:
                data = response.read()

            image = Image.open(io.BytesIO(data))

            result = dominant_lab(image)

            if result is None:
                failed += 1
                continue

            l, a, b, ratio = result

            value, saturation, undertone = tone_class(l, a, b)

            batch.append({
                "pid": pid,
                "l": round(l, 2),
                "a": round(a, 2),
                "b": round(b, 2),
                "family": color_family(l, a, b),
                "value": value,
                "saturation": saturation,
                "undertone": undertone,
                "pastel": is_pastel(l, a, b),
                "ratio": round(ratio, 3),
            })

        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as error:
            failed += 1

            if failed <= 5:
                print("    %s indirilemedi: %s"
                      % (pid, type(error).__name__))

        if len(batch) >= 25:
            written += save(batch)
            batch = []

            elapsed = time.time() - started
            rate = index / elapsed if elapsed else 0

            print("  [%4d/%d] %d yazildi, %d basarisiz  (%.1f urun/sn)"
                  % (index, len(pending), written, failed, rate))

        time.sleep(BETWEEN_REQUESTS)

    written += save(batch)

    print()
    print("  yazilan     : %d" % written)
    print("  basarisiz   : %d" % failed)
    print("  sure        : %.1f dakika" % ((time.time() - started) / 60))
    print()

    report()


if __name__ == "__main__":
    main()
