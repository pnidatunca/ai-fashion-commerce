"""
OLCULMUS RENK ESLESTIRME — renk filtresini metinden pikselden
okunmus degerlere tasir.

PROBLEM
-------
Renk filtresi metne bakiyordu: baslik/aciklama icinde "siyah",
"black" gibi bir kelime aramak. Katalogda olculdu
(scripts/15_extract_product_colors.py):

    rengi metninde gecen urun : 217 / 728  (%30)
    rengi HIC belirtilmemis   : 511 / 728  (%70)

Yani "siyah elbise" arayan kullaniciya, gercekten siyah olan
urunlerin %70'i HIC gosterilemiyordu. Daha kotusu: sert renk
filtresi cok az sonuc buldugu icin gevsetme merdiveni rengi
tamamen birakiyor ve ekrana rastgele renkler geliyordu. Bu,
"renk onerisi yanlis" sikayetinin tam kaynagi.

Ayni script her urunun GORSELINDEN baskin rengi cikarip
kolonlara yaziyor (Lab uzayinda). Bu modul o kolonlari arama
motoruna baglar:

    metin eslesmesi  OR  olculmus renk ailesi     -> kapsam
    Lab uzaklikina gore bonus (DeltaE)            -> isabet


KOLONLAR NEDEN ORM MODELINE EKLENMEDI
-------------------------------------
Kolonlari products tablosuna script ekliyor (ALTER TABLE).
Product modeline yazsaydik ve script henuz calismamis olsaydi
SQLAlchemy her urun sorgusunda o kolonlari SELECT ederdi ve
BUTUN site (urun listesi, arama, sepet) "column does not
exist" ile duserdi. Yani opsiyonel bir zenginlestirme, zorunlu
bir bagimlilik haline gelirdi.

Bu yuzden kolonlara literal_column ile dokunuyoruz ve yalnizca
is_ready() dogruladiktan sonra. Veri yoksa sistem eski
davranisina (metin eslesmesi) duser; hicbir sey kirilmaz.


ESLESTIRME ICIN HANGI HEDEF RENK
--------------------------------
Kullanicinin gordugu paletin ta kendisi: frontend'deki
CUSTOMIZE_COLORS listesindeki hex degerleri. Boylece
kullanicinin tikladigi kare ile eslestirmede kullanilan hedef
AYNI renk oluyor. Ayri bir "sistem rengi" tanimlamak, ekranda
gorulen ile arama arasinda sessiz bir fark yaratirdi.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy import Float, case, func, literal, literal_column, or_, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =========================================================
# KOLON TUTAMAKLARI
# =========================================================
#
# products tablosunun script tarafindan eklenen kolonlari.
# Modele bagli degil (bkz. modul docstring'i).

COL_L = literal_column("products.dominant_l")
COL_A = literal_column("products.dominant_a")
COL_B = literal_column("products.dominant_b")
COL_FAMILY = literal_column("products.color_family")
COL_RATIO = literal_column("products.color_pixel_ratio")

# NOT: tone_value / tone_saturation / tone_undertone / is_pastel
# kolonlari da script tarafindan yaziliyor ama SQL ifadesi
# olarak kullanilmiyorlar. is_pastel fetch_colors ile okunup
# API cevabina konuyor; digerleri henuz hicbir yerde
# gerekmiyor ve olmayan bir ozellik icin kod tutmuyoruz.


# Gorselin ne kadari giysi olarak sayildi. Cok kucukse olculen
# renk guvenilir degil (urun kadrajin kenarinda, gorsel
# kolaj olabilir). Script'in raporundaki dagilima gore %8
# altindaki olcumler ayikliyor.
MIN_PIXEL_RATIO = 0.08

# DeltaE (CIE76) esikleri. Referans: 1-2 gozle ayirt edilemez,
# ~10 "ayni renk ailesi, farkli ton", ~25 komsu renk.
#
# Bonus KADEMELI cunku tek esik iki hatayi birden uretiyor:
# dar tutulunca lacivert bir urun "mavi" aramasinda hic bonus
# almiyor, genis tutulunca acik mavi ile lacivert ayni skoru
# aliyor.
DELTA_E_EXACT = 14.0
DELTA_E_NEAR = 30.0

DELTA_E_MISS = 999.0

# Olculmus renk uzakligindan gelen bonus. COLOR_SOFT_BONUS
# (9.0) ile ayni buyukluk sirasinda tutuluyor: renk guclu bir
# sinyal ama tek sinyal degil.
COLOR_EXACT_BONUS = 9.0
COLOR_NEAR_BONUS = 4.0


@dataclass(frozen=True)
class ColorTarget:
    """Bir renk adinin olculebilir karsiligi."""

    slug: str
    label: str
    hex: str
    lab: tuple[float, float, float]
    families: tuple[str, ...]


# =========================================================
# sRGB -> Lab
# =========================================================
#
# Script numpy ile ayni donusumu yapiyor; burada saf Python,
# cunku istek yolunda tek bir hex cevrilecek ve numpy'yi
# arama yoluna sokmanin bir faydasi yok. Formuller standart
# (D65 beyaz noktasi).

_WHITE_POINT = (0.95047, 1.00000, 1.08883)


def _to_linear(channel: float) -> float:

    value = channel / 255.0

    if value <= 0.04045:
        return value / 12.92

    return ((value + 0.055) / 1.055) ** 2.4


def _pivot(value: float) -> float:

    if value > 0.008856:
        return value ** (1.0 / 3.0)

    return (7.787 * value) + (16.0 / 116.0)


def srgb_to_lab(hex_color: str) -> tuple[float, float, float]:
    """'#d8c3a5' -> (L*, a*, b*)."""

    raw = str(hex_color or "").strip().lstrip("#")

    if len(raw) != 6:
        raise ValueError(f"Gecersiz hex: {hex_color!r}")

    red = _to_linear(int(raw[0:2], 16))
    green = _to_linear(int(raw[2:4], 16))
    blue = _to_linear(int(raw[4:6], 16))

    x = red * 0.4124 + green * 0.3576 + blue * 0.1805
    y = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z = red * 0.0193 + green * 0.1192 + blue * 0.9505

    fx = _pivot(x / _WHITE_POINT[0])
    fy = _pivot(y / _WHITE_POINT[1])
    fz = _pivot(z / _WHITE_POINT[2])

    return (
        round(116.0 * fy - 16.0, 2),
        round(500.0 * (fx - fy), 2),
        round(200.0 * (fy - fz), 2),
    )


# =========================================================
# PALET
# =========================================================
#
# hex degerleri frontend/app.js icindeki CUSTOMIZE_COLORS ile
# AYNI. Aileler script'in color_family() siniflandirmasinin
# uretebildigi degerlerden secildi:
#
#   siyah, beyaz, gri, acik_gri, bej, kahve, kirmizi,
#   pembe, turuncu, sari, yesil, mavi, mor
#
# Bir renk birden fazla aileye bakabilir: "taba" olculumde
# kahve de bej de cikabiliyor. Aile filtresi KAPSAM icin,
# isabeti DeltaE saglıyor.
# AILELER TAHMINLE DEGIL, SINIFLANDIRICIYA SORULARAK YAZILDI
# Her hex, script'in color_family() fonksiyonundan geciriliyor
# ve cikan aile listeye ekleniyor. Iki yeri boylece duzeltildi:
#
#   somon  (#e08e79) -> hue 40 derece -> "kirmizi" cikiyor
#   turuncu(#c9702e) -> hue 59, L 56  -> "kahve" cikiyor
#
# Ilk yazimda bunlar (pembe, turuncu) ve (turuncu,) idi; yani
# somon ve turuncu aramalari gercekten o renkte olan urunleri
# ELEYECEKTI. Bu, duzeltmeye calistigimiz hatanin ta kendisi.
_PALETTE: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("siyah", "Siyah", "#111111", ("siyah",)),
    # BEYAZ + ACIK_GRI: script beyaz studyo zeminini ayiklarken
    # (L >= 88 ve doygunlugu dusuk pikseller) beyaz giysinin
    # kendi aydinlik piksellerini de atiyor. Geriye golgeli
    # kisim kaliyor ve olcum "acik_gri" cikiyor. Yani beyaz
    # urunler duzenli olarak o aileye dusuyor.
    ("beyaz", "Beyaz", "#ffffff", ("beyaz", "acik_gri")),
    ("gri", "Gri", "#9ca3af", ("gri", "acik_gri")),
    ("antrasit", "Antrasit", "#3f3f46", ("gri", "siyah")),
    ("bej", "Bej", "#d8c3a5", ("bej",)),
    ("krem", "Krem", "#f0e6d2", ("bej", "beyaz")),
    # Lacivert ile mavi AYNI ailede: script hue 175-300
    # araligini tek bir "mavi" ailesi sayiyor (denim ve
    # lacivert oraya dusuyor). Ikisini ayiran sey DeltaE:
    # lacivertin L* degeri cok daha dusuk.
    ("lacivert", "Lacivert", "#1e2a4a", ("mavi",)),
    ("mavi", "Mavi", "#3b6fa0", ("mavi",)),
    ("turkuaz", "Turkuaz", "#2e8b8b", ("mavi", "yesil")),
    ("kahverengi", "Kahve", "#6b4226", ("kahve",)),
    ("taba", "Taba", "#a97c50", ("kahve", "bej", "turuncu")),
    ("bordo", "Bordo", "#6b1f2a", ("kirmizi",)),
    ("kirmizi", "Kırmızı", "#b23a3a", ("kirmizi",)),
    ("somon", "Somon", "#e08e79", ("pembe", "kirmizi", "turuncu")),
    ("pembe", "Pembe", "#d98ca0", ("pembe",)),
    ("gul_kurusu", "Gül Kurusu", "#b76e79", ("pembe", "kirmizi")),
    ("mor", "Mor", "#6b4b8a", ("mor",)),
    ("lila", "Lila", "#b19cd9", ("mor", "pembe")),
    ("yesil", "Yeşil", "#4b6b4b", ("yesil",)),
    ("zeytin_yesili", "Zeytin Yeşili", "#6b6b3a", ("yesil", "sari")),
    ("sari", "Sarı", "#d9b93b", ("sari",)),
    ("hardal", "Hardal", "#c9a227", ("sari", "kahve")),
    ("turuncu", "Turuncu", "#c9702e", ("turuncu", "kahve")),
    ("petrol", "Petrol", "#1f4e4e", ("mavi", "yesil")),
)


TARGETS: dict[str, ColorTarget] = {
    slug: ColorTarget(
        slug=slug,
        label=label,
        hex=hex_color,
        lab=srgb_to_lab(hex_color),
        families=families,
    )
    for slug, label, hex_color, families in _PALETTE
}


# Ad -> slug. Uc kaynaktan gelen adlari ayni hedefe baglar:
#
#   1. query_engine.COLOR_TERMS anahtarlari (Ingilizce)
#   2. frontend paletindeki id'ler (Turkce, diakritikli)
#   3. modelin/kullanicinin serbest yazimi ("kirmizi", "acik mavi")
_ALIASES: dict[str, str] = {
    # --- query_engine anahtarlari ---
    "white": "beyaz",
    "black": "siyah",
    "red": "kirmizi",
    "blue": "mavi",
    "navy": "lacivert",
    "green": "yesil",
    "yellow": "sari",
    "pink": "pembe",
    "purple": "mor",
    "gray": "gri",
    "grey": "gri",
    "brown": "kahverengi",
    "beige": "bej",
    "orange": "turuncu",
    # --- serbest yazim / es anlam ---
    "ekru": "krem",
    "krem rengi": "krem",
    "fume": "gri",
    "antrasit gri": "antrasit",
    "kahve": "kahverengi",
    "kahve rengi": "kahverengi",
    "camel": "taba",
    "bordo kirmizi": "bordo",
    "fusya": "pembe",
    "pudra": "somon",
    "gul kurusu": "gul_kurusu",
    "gulkurusu": "gul_kurusu",
    "zeytin": "zeytin_yesili",
    "zeytin yesili": "zeytin_yesili",
    "haki": "zeytin_yesili",
    "petrol mavisi": "petrol",
    "petrol yesili": "petrol",
    "turkuvaz": "turkuaz",
    "lacivert mavi": "lacivert",
    "koyu mavi": "lacivert",
    "acik mavi": "mavi",
    "koyu yesil": "yesil",
    "sari renk": "sari",
}


_TR_FOLD = str.maketrans(
    {
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i", "İ": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
        "’": "", "'": "",
    }
)


def normalize_name(name: str) -> str:
    return str(name or "").translate(_TR_FOLD).lower().strip()


def resolve(name: str) -> ColorTarget | None:
    """
    Bir renk adini olculebilir hedefe cevirir.

    Kabul edilenler: paletin slug'lari, query_engine'in
    Ingilizce anahtarlari, yaygin Turkce yazimlar. Taninmayan
    ad None doner — uydurma bir hedef yaratmak, renk
    filtresini sessizce yanlis yapmak olurdu.
    """

    key = normalize_name(name)

    if not key:
        return None

    if key in TARGETS:
        return TARGETS[key]

    slug = _ALIASES.get(key)

    if slug:
        return TARGETS[slug]

    # "siyah elbise" gibi fazladan kelime tasiyan girdiler.
    for word in key.split():
        if word in TARGETS:
            return TARGETS[word]
        if word in _ALIASES:
            return TARGETS[_ALIASES[word]]

    return None


def resolve_many(names) -> list[ColorTarget]:
    """Taninan hedefler, sirayi ve tekilligi koruyarak."""

    targets: list[ColorTarget] = []
    seen: set[str] = set()

    for name in names or ():

        target = resolve(name)

        if target is None or target.slug in seen:
            continue

        seen.add(target.slug)
        targets.append(target)

    return targets


def families_for(targets) -> tuple[str, ...]:
    """Hedeflerin bakacagi olculmus renk aileleri."""

    families: list[str] = []

    for target in targets:
        for family in target.families:
            if family not in families:
                families.append(family)

    return tuple(families)


# =========================================================
# SQL IFADELERI
# =========================================================

def _trusted():
    """Olculmus rengin guvenilir oldugu satirlar."""

    return (
        COL_L.is_not(None),
        func.coalesce(COL_RATIO, literal(0.0)) >= literal(MIN_PIXEL_RATIO),
    )


def measured_condition(targets):
    """
    Olculmus renge gore eslesme kosulu.

    IKI YOL, "VEYA" ILE BAGLI:

      1. AILE — kaba ama saglam gruplama. Siniflandiricinin
         esikleri olcumle yazildi, guvenilir.
      2. DELTA_E <= DELTA_E_EXACT — aile sinirlarindan bagimsiz
         kacis kapisi. Bir urunun olculen rengi hedefe 14
         DeltaE'den yakinsa o renktedir; siniflandiricinin
         hangi kutuya koydugu onemli degil.

    Ikinci yol neden gerekli: aile sinirlari doga tarafindan
    degil esiklerle cizildi ve sinira yakin renkler (somon /
    turuncu / kiremit) kutu degistiriyor. Sadece aileye
    guvenmek o urunleri eliyordu.
    """

    families = families_for(targets)

    if not families:
        return None

    trusted_l, trusted_ratio = _trusted()

    near_enough = delta_e_expression(targets) <= literal(DELTA_E_EXACT)

    return (
        trusted_l
        & trusted_ratio
        & or_(COL_FAMILY.in_(families), near_enough)
    )


def delta_e_expression(targets):
    """
    Hedeflere en yakin DeltaE (CIE76).

    Birden fazla renk secildiyse EN YAKIN olani sayiyor:
    kullanici "bej veya krem" dediyse urunun ikisinden birine
    yakin olmasi yeter.

    Olcumu olmayan satirlar DELTA_E_MISS aliyor — bonus
    almasin ama siralamadan da dusmesin.
    """

    if not targets:
        return literal(DELTA_E_MISS, Float)

    distances = []

    for target in targets:

        lab_l, lab_a, lab_b = target.lab

        distances.append(
            func.sqrt(
                func.power(func.coalesce(COL_L, literal(-500.0)) - literal(lab_l), 2)
                + func.power(func.coalesce(COL_A, literal(-500.0)) - literal(lab_a), 2)
                + func.power(func.coalesce(COL_B, literal(-500.0)) - literal(lab_b), 2)
            )
        )

    if len(distances) == 1:
        nearest = distances[0]
    else:
        nearest = func.least(*distances)

    return func.least(nearest, literal(DELTA_E_MISS, Float))


def bonus_expression(targets):
    """
    Renk yakinligi bonusu — kademeli.

    Metin eslesmesinden BAGIMSIZ: aciklamasinda renk yazmayan
    ama gercekten siyah olan urun de bonus alabiliyor. Iki
    katman birbirini tamamliyor.
    """

    if not targets:
        return literal(0.0, Float)

    delta = delta_e_expression(targets)

    return case(
        (delta <= literal(DELTA_E_EXACT), literal(COLOR_EXACT_BONUS, Float)),
        (delta <= literal(DELTA_E_NEAR), literal(COLOR_NEAR_BONUS, Float)),
        else_=literal(0.0, Float),
    )


# =========================================================
# HAZIRLIK DURUMU
# =========================================================

_READY_TTL_SECONDS = 300

_ready_cache: dict = {
    "value": None,
    "checked_at": 0.0,
    "filled": 0,
}


def is_ready(db: Session) -> bool:
    """
    Olculmus renk verisi kullanilabilir mi?

    Iki sey gerekiyor: kolonlar var ve icinde veri var.
    Sonuc onbellekli (5 dk) — her aramada information_schema
    sorgusu atmak anlamsiz.

    HATA DURUMUNDA FALSE: renk zenginlestirmesi bir EK. Onun
    yuzunden aramanin komple dusmesi kabul edilemez.
    """

    now = time.monotonic()

    if (
        _ready_cache["value"] is not None
        and now - _ready_cache["checked_at"] < _READY_TTL_SECONDS
    ):
        return bool(_ready_cache["value"])

    ready = False
    filled = 0

    try:
        has_column = db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'products'
                  AND column_name = 'color_family'
                """
            )
        ).scalar()

        if has_column:

            filled = int(
                db.execute(
                    text(
                        "SELECT count(*) FROM products "
                        "WHERE dominant_l IS NOT NULL"
                    )
                ).scalar()
                or 0
            )

            # Tek satir bile ise yarar: olculmus renk METIN
            # eslesmesine EKLENIYOR (OR), yerine gecmiyor.
            # Yani kismi veri kapsami yalnizca artirir.
            ready = filled > 0

    except Exception as error:

        logger.warning(
            "Olculmus renk verisi kontrol edilemedi: %s", error
        )

        ready = False

    _ready_cache["value"] = ready
    _ready_cache["checked_at"] = now
    _ready_cache["filled"] = filled

    if not ready:
        logger.info(
            "Olculmus renk verisi yok; renk filtresi metne "
            "dayanacak. Etkinlestirmek icin: "
            "python scripts/15_extract_product_colors.py"
        )

    return ready


def coverage(db: Session) -> dict:
    """Teshis: kac urunun rengi olculmus."""

    is_ready(db)

    return {
        "ready": bool(_ready_cache["value"]),
        "measured": _ready_cache["filled"],
    }


def reset_cache() -> None:
    """Script calistiktan sonra beklemeden aktiflesmek icin."""

    _ready_cache["value"] = None
    _ready_cache["checked_at"] = 0.0


def fetch_colors(db: Session, product_ids) -> dict[str, dict]:
    """
    Verilen urunlerin olculmus renk bilgisi.

    Neden ayri sorgu: kolonlar ORM modelinde olmadigi icin
    urunle birlikte gelmiyorlar. Yalnizca gerekli oldugunda
    (renk secilmis bir istek) ve tek turda cekiliyor.
    """

    ids = [str(pid) for pid in (product_ids or []) if pid]

    if not ids or not is_ready(db):
        return {}

    try:
        rows = db.execute(
            text(
                """
                SELECT product_id, dominant_l, dominant_a, dominant_b,
                       color_family, is_pastel, color_pixel_ratio
                FROM products
                WHERE product_id = ANY(:ids)
                """
            ),
            {"ids": ids},
        ).all()

    except Exception as error:

        logger.warning("Renk bilgisi okunamadi: %s", error)

        return {}

    result: dict[str, dict] = {}

    for row in rows:

        if row[1] is None:
            continue

        ratio = float(row[6] or 0.0)

        result[str(row[0])] = {
            "lab": (float(row[1]), float(row[2]), float(row[3])),
            "family": row[4],
            "is_pastel": bool(row[5]),
            "ratio": ratio,
            "trusted": ratio >= MIN_PIXEL_RATIO,
        }

    return result


def delta_e(lab_a, lab_b) -> float:
    """Python tarafinda CIE76 — yeniden siralama icin."""

    return (
        (lab_a[0] - lab_b[0]) ** 2
        + (lab_a[1] - lab_b[1]) ** 2
        + (lab_a[2] - lab_b[2]) ** 2
    ) ** 0.5


def nearest_distance(lab, targets) -> float:
    """Bir olcumun hedeflere en yakin uzakligi."""

    if not targets or lab is None:
        return DELTA_E_MISS

    return min(delta_e(lab, target.lab) for target in targets)
