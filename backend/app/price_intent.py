"""
BUTCE COZUMLEYICI — "3000 TL altinda" cumlesini sayiya cevirir.

NEDEN VAR
---------
Fiyat, kullanicinin en sik soyledigi ve sistemin en cok
yanlis anladigi kisitti. Olculen davranis:

    Kullanici : "3000 TL altinda siyah sneaker"
    On arama  : query="3000 TL altinda siyah sneaker"
                fiyat filtresi YOK
    Sonuc     : 8 urun, ucu 4000 TL uzeri
    Asistan   : bulunan urunleri onerdi

Yani butce cumlenin icinde yaziyordu ama hicbir yerde SAYIYA
donusmuyordu. Model kendi araciyla max_price_try gonderebiliyordu
ama on arama (prefetch) yolunda modele hic sorulmuyor; o yolda
butce tamamen kayboluyordu.

Cozum: butceyi sorgu cozumleme katmaninda, kelimelerden
okuyoruz. Boylece hem /api/search hem sohbet ayni sayiyi
goruyor ve fiyat filtresi SQL'de calisiyor.


NEDEN KENDI KUCUK NORMALIZASYONU VAR
------------------------------------
query_engine.fold() ayni isi yapiyor ama query_engine BU
modulu import ediyor; tersi dongusel olurdu. Ihtiyac duyulan
normalizasyon da dar: kucuk harf, Turkce karakter katlama ve
kesme isaretini atmak.


NE YAKALANMAZ — BILINCLI
------------------------
Beden, numara ve yas gibi sayilar butce sanilmamali:

    "42 numara ayakkabi"   -> butce yok
    "38 beden elbise"      -> butce yok
    "25 yasindayim"        -> butce yok

Bu yuzden ciplak bir sayi ASLA butce sayilmiyor: ya bir para
birimi kelimesi (tl / lira / ₺) ya da bir karsilastirma ifadesi
(altinda, en fazla, uzerinde...) gerekiyor. Ustelik alt sinir
MIN_MEANINGFUL_PRICE ile korunuyor — katalogdaki en ucuz urun
bile ~500 TL, yani "42" bir fiyat olamaz.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace

logger = logging.getLogger(__name__)


# Katalogdaki en ucuz urun ~10 USD (~480 TL). Bunun altindaki
# sayilar fiyat degil beden/numara/yas olma ihtimali cok daha
# yuksek. Esik dusuk tutuluyor: amac fiyat gibi durmayan
# sayilari elemek, gercek bir "150 TL" niyetini degil.
MIN_MEANINGFUL_PRICE = 100.0

# Ust sinir: kullanici bir sey sasirtici yazarsa (telefon
# numarasi, yil) filtreyi anlamsizca genisletmesin.
MAX_MEANINGFUL_PRICE = 5_000_000.0

# "3000 civarinda" ne kadar esneklik demek. Olcum yok, karar
# var: kullanici tam sayi soylemek istemedigini belirtiyor,
# %25 makul bir pencere ve katalogda genellikle bir bant
# dolduruyor.
APPROX_SPREAD = 0.25


_TR_FOLD = str.maketrans(
    {
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i", "İ": "i", "î": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u", "û": "u",
        "â": "a",
        "’": "", "'": "", "`": "",
    }
)


@dataclass(frozen=True)
class Budget:
    """
    Cozumlenmis butce.

    min_try / max_try : TL cinsinden sinirlar (None = sinir yok)
    kind              : sayisiz niyet — "cheap" | "premium" | ""
    approximate       : "civarinda" gibi esnek bir ifade miydi
    source            : hangi kalip yakaladi (teshis/log icin)
    """

    min_try: float | None = None
    max_try: float | None = None
    kind: str = ""
    approximate: bool = False
    source: str = ""

    def __bool__(self) -> bool:
        return bool(
            self.min_try is not None
            or self.max_try is not None
            or self.kind
        )

    @property
    def has_bounds(self) -> bool:
        return self.min_try is not None or self.max_try is not None

    def as_dict(self) -> dict:
        return {
            "min_try": self.min_try,
            "max_try": self.max_try,
            "kind": self.kind or None,
            "approximate": self.approximate,
        }


@dataclass(frozen=True)
class PriceStats:
    """
    Katalogun fiyat dagilimi (TL).

    "Ucuz bir sey" isteyen birine ne gosterecegimizi bilmek
    icin gerekli: mutlak bir "ucuz" yok, KATALOGA GORE ucuz var.
    """

    minimum: float
    p33: float
    median: float
    p66: float
    maximum: float
    count: int

    def as_dict(self) -> dict:
        return {
            "min_try": round(self.minimum),
            "p33_try": round(self.p33),
            "median_try": round(self.median),
            "p66_try": round(self.p66),
            "max_try": round(self.maximum),
            "count": self.count,
        }


# =========================================================
# NORMALIZASYON
# =========================================================

def _fold(text: str) -> str:
    return str(text or "").translate(_TR_FOLD).lower()


def _expand_thousands(match: re.Match) -> str:
    return match.group(1).replace(".", "")


def _expand_bin(match: re.Match) -> str:
    """'3 bin', '3bin', '2,5 bin', '3k' -> duz sayi."""

    raw = match.group(1).replace(",", ".")

    try:
        return str(int(float(raw) * 1000))
    except ValueError:
        return match.group(0)


def _normalize(text: str) -> str:
    """
    Sayilari tek bicime indirir.

    "3.000", "3 bin", "3bin", "3k" hepsi "3000" olur. Aksi
    halde her kalibi ayri ayri butun yazim bicimleriyle
    yazmak gerekirdi.
    """

    folded = _fold(text)

    # 3.000 / 1.250.000 -> 3000 / 1250000
    folded = re.sub(
        r"(?<!\d)(\d{1,3}(?:\.\d{3})+)(?!\d)",
        _expand_thousands,
        folded,
    )

    # 3 bin / 3bin / 2,5 bin / 3k -> 3000 / 2500
    folded = re.sub(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:bin|k)\b",
        _expand_bin,
        folded,
    )

    return folded


# =========================================================
# KALIPLAR
# =========================================================

_MONEY = r"(?:tl|lira|try|₺)"

# Sayidan sonra gelebilen ekler: "3000in", "3000tlnin" gibi
# kesme isareti atilmis yazimlar.
_SUFFIX = r"(?:\s*" + _MONEY + r")?\s*[a-z]{0,4}\s*"

# Sayinin ARDINDAN gelirse o sayi fiyat DEGILDIR.
_NOT_PRICE_AFTER = re.compile(
    r"^\s*(?:beden|numara|no\b|yas\b|yasinda|cm|mm|kg|gr\b|"
    r"adet|tane|parca|litre|ml|gb|yil|ay\b|gun)"
)

_MAX_AFTER = (
    r"(?:altinda|alti\b|altina|asagisi|asagi|"
    r"kadar|gecmeyen|gecmesin|den az|dan az|max)"
)

_MIN_AFTER = (
    r"(?:uzerinde|uzeri|ustu\b|ustunde|"
    r"den fazla|dan fazla|den yukari|dan yukari)"
)

_APPROX_AFTER = (
    r"(?:civari|civarinda|civarlarinda|dolayinda|dolaylarinda|"
    r"bandinda|bandi|gibi|kadarlik|seviyesinde)"
)

_CHEAP_WORDS = (
    "ucuz",
    "hesapli",
    "ekonomik",
    "uygun fiyat",
    "uygun fiyatli",
    "butcem kisitli",
    "butcem dar",
    "cok para",
    "az para",
    "fazla para vermek istemiyorum",
    "en ucuz",
)

_PREMIUM_WORDS = (
    "pahali",
    "luks",
    "premium",
    "ust segment",
    "fiyat onemli degil",
    "para onemli degil",
    "butce sinirsiz",
    "kaliteli olsun fiyat",
)


def _valid(value: float | None) -> float | None:
    """Fiyat gibi durmayan sayiyi eler."""

    if value is None:
        return None

    if value < MIN_MEANINGFUL_PRICE or value > MAX_MEANINGFUL_PRICE:
        return None

    return float(value)


def _number_at(text: str, match: re.Match, group: int = 1) -> float | None:
    """Yakalanan sayiyi, yanlis baglam kontrolunden gecirerek okur."""

    try:
        value = float(match.group(group))
    except (TypeError, ValueError):
        return None

    # "42 numara" gibi kullanimlar butce degil.
    tail = text[match.end(group):]

    if _NOT_PRICE_AFTER.match(tail):
        return None

    return _valid(value)


def parse(text: str) -> Budget:
    """
    Serbest metinden butce cikarir. Bulamazsa bos Budget doner
    (bool degeri False).

    Kalip sirasi ONEMLI: en belirgin ifade once denenir.
    "3000 ile 5000 arasi" once aralik olarak yakalanmali; aksi
    halde ciplak para kalibi ilk sayiyi ust sinir sanip
    kullanicinin alt sinirini yok eder.
    """

    if not text:
        return Budget()

    normalized = _normalize(text)

    # ---- 1. ARALIK ----
    #
    # Iki sayinin ikisi de fiyat gibi gorunmeli. "42-44 numara"
    # bu yuzden gecmiyor: hem esigin altinda hem ardindan
    # "numara" geliyor.
    range_match = re.search(
        rf"(\d+)\s*{_MONEY}?\s*(?:-|ile|ila|–|—|arasi|arasinda)\s*"
        rf"(\d+)\s*{_MONEY}?\s*(?:aras\w*)?",
        normalized,
    )

    if range_match:

        low = _number_at(normalized, range_match, 1)
        high = _number_at(normalized, range_match, 2)

        if low is not None and high is not None:

            return Budget(
                min_try=min(low, high),
                max_try=max(low, high),
                source="range",
            )

    # ---- 2. UST SINIR ----

    for pattern, source in (
        (r"(?:en fazla|en cok|maksimum|maks|max|ust sinir)\s*(\d+)", "max_before"),
        (rf"(\d+){_SUFFIX}{_MAX_AFTER}", "max_after"),
        (r"(?:butce\w*)[^\d]{0,15}(\d+)", "budget_word"),
    ):
        match = re.search(pattern, normalized)

        if match:

            value = _number_at(normalized, match, 1)

            if value is not None:
                return Budget(max_try=value, source=source)

    # ---- 3. ALT SINIR ----

    for pattern, source in (
        (r"(?:en az|minimum|asgari|min)\s*(\d+)", "min_before"),
        (rf"(\d+){_SUFFIX}{_MIN_AFTER}", "min_after"),
    ):
        match = re.search(pattern, normalized)

        if match:

            value = _number_at(normalized, match, 1)

            if value is not None:
                return Budget(min_try=value, source=source)

    # ---- 4. YAKLASIK ----
    #
    # "3000 civarinda": kullanici tam sayi vermek istemedigini
    # soyluyor. Sert bir ust sinir koymak yanlis olurdu — 3100
    # TL'lik urunu saklamak kullanicinin kastettigi sey degil.

    approx_match = re.search(
        rf"(\d+){_SUFFIX}{_APPROX_AFTER}",
        normalized,
    )

    if approx_match:

        value = _number_at(normalized, approx_match, 1)

        if value is not None:
            return Budget(
                min_try=round(value * (1 - APPROX_SPREAD), 2),
                max_try=round(value * (1 + APPROX_SPREAD), 2),
                approximate=True,
                source="approx",
            )

    # ---- 5. CIPLAK PARA ----
    #
    # En gevsek kalip, bu yuzden en sonda: "3000 TL sneaker"
    # cumlesinde kullanici muhtemelen ust sinir soyluyor.
    # Para birimi kelimesi ZORUNLU — yoksa beden/numara
    # yakalanir.

    money_match = re.search(
        rf"(\d+)\s*{_MONEY}",
        normalized,
    )

    if money_match:

        value = _number_at(normalized, money_match, 1)

        if value is not None:
            return Budget(max_try=value, source="bare_money")

    # ---- 6. SAYISIZ NIYET ----

    for word in _PREMIUM_WORDS:
        if word in normalized:
            return Budget(kind="premium", source=f"word:{word}")

    for word in _CHEAP_WORDS:
        if word in normalized:
            return Budget(kind="cheap", source=f"word:{word}")

    return Budget()


_STRIP_WORDS = frozenset(
    {
        "tl", "lira", "try", "₺",
        "altinda", "alti", "altina", "asagisi", "asagi",
        "uzerinde", "uzeri", "ustu", "ustunde",
        "kadar", "civari", "civarinda", "dolayinda",
        "dolaylarinda", "bandinda", "arasi", "arasinda",
        "ile", "ila", "en", "fazla", "cok", "az",
        "maksimum", "maks", "max", "minimum", "min", "asgari",
        "butce", "butcem", "butceyle", "butcem var",
        "gecmeyen", "gecmesin", "bin",
    }
)


def strip(text: str, budget: Budget | None = None) -> str:
    """
    Butce ifadesini metinden cikarir.

    NEDEN
    Butce artik SAYI olarak tasiniyor; kelimelerin metinde
    kalmasi yalnizca zarar veriyor. "3000 TL altinda siyah
    sneaker" cumlesi embedding'e oldugu gibi giderse vektor
    "3000" civarinda bir anlam ariyor ve gercek niyet (siyah
    sneaker) zayifliyor.

    NASIL — KELIME KELIME, KALIPLA DEGIL
    Regex ile span silmek orijinal yazimi (Turkce karakterler,
    buyuk harf) bozuyordu. Burada kelimeler tek tek
    degerlendiriliyor: rakam iceren veya butce sozlugunde olan
    kelimeler atiliyor.

    BUTCE BULUNAMADIYSA HICBIR SEY ATILMAZ. Aksi halde "42
    numara" veya "501 jean" gibi urun bilgisi tasiyan sayilar
    silinirdi.
    """

    if budget is not None and not budget.has_bounds:
        return text

    words = [word for word in re.split(r"\s+", str(text or "")) if word]

    kept = []

    for word in words:

        folded = _fold(word).strip(".,!?()[]{}\"-")

        if any(char.isdigit() for char in folded):
            continue

        if folded in _STRIP_WORDS:
            continue

        kept.append(word)

    return " ".join(kept).strip()


def resolve(budget: Budget, stats: PriceStats | None) -> Budget:
    """
    Sayisiz niyeti ("ucuz bir sey") katalog dagilimiyla sayiya
    cevirir.

    NEDEN KATALOGA GORE
    Mutlak bir "ucuz" yok. 2000 TL bir katalogda pahali,
    digerinde ucuzdur. Kullanicinin kastettigi sey "bu
    magazanin ucuz tarafi" — yani dagilimin alt ucu.

    stats yoksa (veritabani okunamadi) niyet aynen kaliyor:
    filtre uygulanmaz ama bilgi kaybolmaz, model yine
    "butcene uygun taraftan sectim" diyebilir.
    """

    if not budget.kind or stats is None:
        return budget

    if budget.kind == "cheap" and budget.max_try is None:
        return replace(
            budget,
            max_try=round(stats.p33, 2),
            source=budget.source + "+stats",
        )

    if budget.kind == "premium" and budget.min_try is None:
        return replace(
            budget,
            min_try=round(stats.p66, 2),
            source=budget.source + "+stats",
        )

    return budget


def describe(budget: Budget) -> str:
    """Kullaniciya/loga gosterilecek kisa ifade."""

    def money(value: float) -> str:
        return f"{value:,.0f}".replace(",", ".") + " TL"

    if budget.min_try is not None and budget.max_try is not None:

        if budget.approximate:
            middle = (budget.min_try + budget.max_try) / 2
            return f"{money(middle)} civarı"

        return f"{money(budget.min_try)} - {money(budget.max_try)}"

    if budget.max_try is not None:
        return f"en fazla {money(budget.max_try)}"

    if budget.min_try is not None:
        return f"en az {money(budget.min_try)}"

    if budget.kind == "cheap":
        return "uygun fiyatlı"

    if budget.kind == "premium":
        return "üst segment"

    return ""
