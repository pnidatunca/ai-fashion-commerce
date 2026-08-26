"""
SOHBET BASLAMADAN ONCE: YILLIK TREND SECKISI + GIDILECEK YER

Bos sohbet ekraninda "ne yazsam" tereddutu en buyuk terk
sebebi. Mevcut dort hazir cumle bunu kismen coziyordu ama
hepsi ayni kalipta: rastgele birkac ornek.

Burada iki ayri giris kapisi var:

  1. YILLIK TREND — sezonun rengi, tarzi ve kumasi. Kullanici
     "ne moda?" sorusunun cevabini gorup dogrudan o yonde
     arama baslatabiliyor.

  2. GIDILECEK YER — "nereye gidiyorsun?" Kullanici yeri
     yaziyor (dugun, is yemegi, mezuniyet...) ve asistan o
     baglama gore oneri yapiyor. Kiyafet secimi cogu zaman
     urun degil OLAY uzerinden baslar; arama kutusu bunu hic
     karsilamiyordu.


TREND LISTESI ELLE DERLENDI — VERIDEN CIKMIYOR
----------------------------------------------
Bu liste bir EDITORYAL secki. Katalog verisinden istatistikle
uretilmiyor ve bir moda kurumuna (Pantone, WGSN vb.)
dayandirilmiyor — oyle bir kaynagimiz yok ve varmis gibi
yazmak kullaniciya yanlis bir yetke sunmak olurdu. Arayuzde
"WishNN seckisi" olarak gosteriliyor.

Sonucu: sezon degistiginde BU DOSYA elle guncellenir.
TREND_YEAR / TREND_SEASON degerleri de burada; guncellenmediginde
kullanici gecmis bir sezonu "bu sezon" diye gorur.


KATALOGDA OLMAYAN TREND GOSTERILMEZ
-----------------------------------
Her trend ogesi katalogda kac urunle karsilandigi SAYILIYOR ve
esigin altinda kalan oge listeden dusuyor. Sebebi basit: "bu
sezon zeytin yesili" deyip tiklayinca sifir sonuc gostermek,
hic oneri yapmamaktan kotudur.

Sayim, aramanin kullandigi AYNI kosullarla yapiliyor:
renk icin metin + olculmus renk (color_match), kumas icin
sozluk terimleri (query_engine), tarz icin onceden hesaplanmis
arketip skorlari (product_style_scores).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import color_match, query_engine, search_service
from app.models import Product

logger = logging.getLogger(__name__)


# =========================================================
# SEZON
# =========================================================

TREND_YEAR = 2026

TREND_SEASON = "İlkbahar / Yaz"

TREND_TITLE = "2026 İlkbahar/Yaz seçkisi"

TREND_NOTE = (
    "Bu sezon öne çıkan renk, tarz ve kumaşlar. WishNN "
    "seçkisi — kataloğumuzda gerçekten bulunan parçalardan."
)


# Bir trend ogesinin gosterilmesi icin gereken en az urun.
# 8 sayisi kararla secildi: alti tikladiktan sonra "birkac
# secenek" cumlesi kurulabilecek en kucuk sayi.
MIN_AVAILABLE = 8

# Arketip skoru bu esigin ustundeki urunler "bu tarz" sayiliyor.
# Dagilim olculdu (product_style_scores):
#
#     >=70 : 19-106 urun   <- net eslesme
#     >=50 : 37-354 urun
#     >=30 : 639-691 urun  <- neredeyse butun katalog
#
# 70 secildi: 30 ve 50 esikleri "her urun her tarza uyar"
# demeye varıyor ve trend onerisini anlamsizlastiriyor.
STYLE_SCORE_THRESHOLD = 70.0


@dataclass(frozen=True)
class TrendItem:
    """
    Bir trend ogesi.

    kind    : "color" | "style" | "fabric"
    ref     : sayim ve arama icin anahtar
              (renk slug'i / arketip / kumas facet'i)
    prompt  : tiklandiginda sohbete gidecek mesaj
    swatch  : renk ogeleri icin hex; digerlerinde None
    """

    id: str
    kind: str
    ref: str
    label: str
    note: str
    prompt: str
    swatch: str | None = None


# =========================================================
# SECKI
# =========================================================
#
# ADAY listesi: hangisinin gosterilecegine katalogdaki urun
# sayisi karar veriyor (bkz. modul docstring'i).
#
# Renkler color_match paletinden secildi — yani kullanicinin
# Ozelleştir ekraninda gordugu ayni renkler ve ayni hedef
# degerler. Iki yerde farkli "bej" tanimi olmasi, aramayi
# sessizce tutarsiz yapardi.

TREND_COLORS: tuple[TrendItem, ...] = (
    TrendItem(
        id="trend-color-bej",
        kind="color",
        ref="bej",
        label="Bej",
        note="Sessiz lüks nötrleri",
        prompt=(
            "Bu sezon bej ve nötr tonlar öne çıkıyor. Bej "
            "tonlarında birkaç parça önerir misin?"
        ),
    ),
    TrendItem(
        id="trend-color-krem",
        kind="color",
        ref="krem",
        label="Krem",
        note="Kirli beyaz, yumuşak geçiş",
        prompt=(
            "Krem ve kirli beyaz tonlarında parçalar göster."
        ),
    ),
    TrendItem(
        id="trend-color-zeytin",
        kind="color",
        ref="zeytin_yesili",
        label="Zeytin Yeşili",
        note="Toprak tonlu yeşil",
        prompt=(
            "Zeytin yeşili / haki tonlarında ne var? Birkaç "
            "parça önerir misin?"
        ),
    ),
    TrendItem(
        id="trend-color-lacivert",
        kind="color",
        ref="lacivert",
        label="Lacivert",
        note="Siyahın yerine geçen klasik",
        prompt=(
            "Lacivert tonlarında şık parçalar göster."
        ),
    ),
    TrendItem(
        id="trend-color-taba",
        kind="color",
        ref="taba",
        label="Taba",
        note="Deri ve süet dokularla",
        prompt="Taba ve kahve tonlarında parçalar göster.",
    ),
    TrendItem(
        id="trend-color-somon",
        kind="color",
        ref="somon",
        label="Somon",
        note="Yumuşak sıcak vurgu",
        prompt=(
            "Somon ve pudra tonlarında yazlık parçalar göster."
        ),
    ),
)


TREND_STYLES: tuple[TrendItem, ...] = (
    TrendItem(
        id="trend-style-old_money",
        kind="style",
        ref="old_money",
        label="Sessiz Lüks",
        note="Klasik kesim, iyi kumaş, logo yok",
        prompt=(
            "Sessiz lüks (old money) tarzına uygun parçalar "
            "önerir misin?"
        ),
    ),
    TrendItem(
        id="trend-style-minimalist",
        kind="style",
        ref="minimalist",
        label="Minimalist",
        note="Kapsül gardırop, nötr tonlar",
        prompt=(
            "Minimalist bir kapsül gardırop için temel "
            "parçalar göster."
        ),
    ),
    TrendItem(
        id="trend-style-athleisure",
        kind="style",
        ref="athleisure",
        label="Athleisure",
        note="Spor parçalar günlük kombinde",
        prompt=(
            "Athleisure tarzı — hem spor hem günlük "
            "giyebileceğim parçalar göster."
        ),
    ),
    TrendItem(
        id="trend-style-smart_casual",
        kind="style",
        ref="smart_casual",
        label="Smart Casual",
        note="Ofise de akşam yemeğine de",
        prompt=(
            "Smart casual tarzında, ofiste de akşam yemeğinde "
            "de giyebileceğim parçalar önerir misin?"
        ),
    ),
)


TREND_FABRICS: tuple[TrendItem, ...] = (
    TrendItem(
        id="trend-fabric-linen",
        kind="fabric",
        ref="linen",
        label="Keten",
        note="Sıcakta nefes alan dokular",
        prompt="Keten kumaştan yazlık parçalar göster.",
    ),
    TrendItem(
        id="trend-fabric-knit",
        kind="fabric",
        ref="knit",
        label="Triko",
        note="İnce örgü, mevsim geçişi",
        prompt="İnce triko / örgü parçalar önerir misin?",
    ),
    TrendItem(
        id="trend-fabric-denim",
        kind="fabric",
        ref="denim",
        label="Denim",
        note="Her sezon duran temel",
        prompt="Denim parçalar göster.",
    ),
    TrendItem(
        id="trend-fabric-silk",
        kind="fabric",
        ref="silk",
        label="Saten / İpek",
        note="Akışkan yüzey, davet için",
        prompt=(
            "Saten veya ipek görünümlü şık parçalar göster."
        ),
    ),
    TrendItem(
        id="trend-fabric-cotton",
        kind="fabric",
        ref="cotton",
        label="Pamuklu",
        note="Günlük giyimin temeli",
        prompt="Pamuklu, günlük giyilebilecek parçalar göster.",
    ),
)


# =========================================================
# GIDILECEK YER
# =========================================================
#
# Kullanici yeri SERBEST yazabiliyor; buradaki liste yalnizca
# hizli secim. Yazilan metin query_engine'in "occasion"
# sozlugune dusuyor ("dugun", "mezuniyet", "kokteyl" hepsi
# party facet'ini tetikliyor), dusmezse de asistan cumleyi
# yine okuyor. Yani liste eksik olabilir, ozellik calismaya
# devam eder.

DESTINATION_HINT = "Nereye gidiyorsun?"

DESTINATION_PLACEHOLDER = "düğün, iş yemeği, mezuniyet…"

# {place} kullanicinin yazdigi ya da sectigi yer.
#
# Cumle neden boyle: "ne giyebilirim" sorusu asistanin
# kategoriyi KENDISININ secmesini istiyor. "Bana elbise
# oner" deseydik kullanicinin yerine karar vermis olurduk.
DESTINATION_PROMPT = (
    "{place} için ne giyebilirim? Bana uygun parçalar "
    "önerir misin?"
)

# place, kalibin {place} yerine giren AD ÖBEĞI — cumle degil.
#
# Ilk yazimda tam cumleler vardi ("Bir dugune gidiyorum") ve
# kalipla birlesince bozuk Turkce uretiyordu: "Bir dugune
# gidiyorum icin ne giyebilirim?". Etiket ile ad obegi ayni
# oldugunda place yazilmiyor.
DESTINATIONS: tuple[dict, ...] = (
    {"id": "wedding", "label": "Düğün"},
    {"id": "dinner", "label": "İş yemeği"},
    {"id": "office", "label": "Ofis"},
    {"id": "date", "label": "Buluşma"},
    {"id": "vacation", "label": "Tatil"},
    {"id": "graduation", "label": "Mezuniyet", "place": "Mezuniyet töreni"},
)


# =========================================================
# KULLANILABILIRLIK SAYIMI
# =========================================================

def _count_color(db: Session, slug: str) -> int:
    """
    Renk icin aday urun sayisi — arama ile AYNI kosul:
    metin eslesmesi VEYA olculmus renk.
    """

    targets = color_match.resolve_many([slug])

    if not targets:
        return 0

    condition = search_service.color_condition(
        [slug],
        measured=color_match.is_ready(db),
    )

    if condition is None:
        return 0

    return int(
        db.execute(
            select(func.count()).select_from(Product).where(condition)
        ).scalar()
        or 0
    )


def _count_fabric(db: Session, facet_key: str) -> int:
    """Kumas icin aday urun sayisi — sozluk terimleriyle."""

    facet = next(
        (
            item
            for item in query_engine.FABRIC_FACETS
            if item.key == facet_key
        ),
        None,
    )

    if facet is None:
        return 0

    condition = search_service.text_match_condition(
        list(facet.expand) + list(facet.triggers)
    )

    if condition is None:
        return 0

    return int(
        db.execute(
            select(func.count()).select_from(Product).where(condition)
        ).scalar()
        or 0
    )


def _count_styles(db: Session) -> dict[str, int]:
    """
    Arketip -> net eslesen urun sayisi.

    Tek sorguda hepsi: her trend tarzi icin ayri COUNT atmak
    dort tur demekti ve tablo kucuk.
    """

    try:
        rows = db.execute(
            text(
                """
                SELECT archetype, count(*)
                FROM product_style_scores
                WHERE score >= :threshold
                GROUP BY archetype
                """
            ),
            {"threshold": STYLE_SCORE_THRESHOLD},
        ).all()

    except Exception as error:

        # Tablo yoksa (script henuz kosmadiysa) tarz onerileri
        # sayilamaz. Ozellik kirilmiyor: sayim bilinmiyorsa
        # oge yine gosteriliyor (bkz. _resolve).
        logger.warning("Arketip skorlari okunamadi: %s", error)

        return {}

    return {str(row[0]): int(row[1]) for row in rows}


def _resolve(
    db: Session,
    items: tuple[TrendItem, ...],
    style_counts: dict[str, int],
) -> list[dict]:
    """
    Ogeleri sayimla birlestirir ve esigin altinda kalanlari atar.

    SAYIM YAPILAMADIYSA OGE KALIR. Sayim bir iyilestirme; onun
    basarisizligi yuzunden butun trend bolumunu bos gostermek
    kullaniciya daha az sey verirdi. Bu durumda available None
    doner ve arayuz sayi yazmaz.
    """

    resolved: list[dict] = []

    for item in items:

        available: int | None

        try:
            if item.kind == "color":
                available = _count_color(db, item.ref)

            elif item.kind == "fabric":
                available = _count_fabric(db, item.ref)

            else:
                available = style_counts.get(item.ref)

        except Exception as error:

            logger.warning(
                "Trend ogesi sayilamadi (%s): %s", item.id, error
            )

            available = None

        if available is not None and available < MIN_AVAILABLE:
            logger.info(
                "Trend ogesi atlandi (%s): katalogda %s urun.",
                item.id,
                available,
            )
            continue

        resolved.append(
            {
                "id": item.id,
                "kind": item.kind,
                "label": item.label,
                "note": item.note,
                "prompt": item.prompt,
                "swatch": item.swatch or _swatch_for(item),
                "available": available,
            }
        )

    return resolved


def _swatch_for(item: TrendItem) -> str | None:
    """Renk ogeleri paletteki hex degerini tasir."""

    if item.kind != "color":
        return None

    target = color_match.TARGETS.get(item.ref)

    return target.hex if target else None


# =========================================================
# CEVAP
# =========================================================

_CACHE_TTL_SECONDS = 30 * 60

_cache: dict = {
    "value": None,
    "built_at": 0.0,
}


def starters(db: Session, force: bool = False) -> dict:
    """
    Sohbet acilis onerileri.

    30 dakika onbellekli: icerik elle derlendi, sayimlar da
    katalog degismedikce ayni. Her sohbet acilisinda ~12 COUNT
    sorgusu atmanin anlami yok.
    """

    now = time.monotonic()

    if (
        not force
        and _cache["value"] is not None
        and now - _cache["built_at"] < _CACHE_TTL_SECONDS
    ):
        return _cache["value"]

    style_counts = _count_styles(db)

    payload = {
        "trend": {
            "year": TREND_YEAR,
            "season": TREND_SEASON,
            "title": TREND_TITLE,
            "note": TREND_NOTE,

            # Kaynak aciga cikariliyor: liste elle derlendi,
            # veriden cikmadi. Arayuz bunu "WishNN seçkisi"
            # olarak gosteriyor.
            "source": "editorial",

            "colors": _resolve(db, TREND_COLORS, style_counts),
            "styles": _resolve(db, TREND_STYLES, style_counts),
            "fabrics": _resolve(db, TREND_FABRICS, style_counts),
        },
        "destination": {
            "hint": DESTINATION_HINT,
            "placeholder": DESTINATION_PLACEHOLDER,
            "prompt_template": DESTINATION_PROMPT,
            "options": [
                {
                    "id": option["id"],
                    "label": option["label"],
                    "prompt": DESTINATION_PROMPT.format(
                        place=option.get("place") or option["label"]
                    ),
                }
                for option in DESTINATIONS
            ],
        },
    }

    _cache["value"] = payload
    _cache["built_at"] = now

    return payload


def reset_cache() -> None:
    """Secki elle guncellendiginde beklemeden yansimasi icin."""

    _cache["value"] = None
    _cache["built_at"] = 0.0
