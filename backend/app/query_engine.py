"""
AKILLI ARAMA MOTORU — sorgu anlama katmani

Bu dosya kullanicinin arama kutusuna yazdigi dogal dil
cumlesini alir ve arama motorunun kullanabilecegi yapiya
cevirir:

    "kadin yazlik renkli elbise ariyorum"
        |
        v
    ana terim   : kadin yazlik renkli elbise
    cinsiyet    : women
    kategori    : dress
    sezon       : summer
    desen niyeti: True         <- "renkli"
    genisletme  : desenli, cicekli, keten, sifon, ince...
    alternatif  : "kadin desenli yazlik elbise", ...


NEDEN BACKEND'DE
----------------
Sozlukler daha once frontend'de (app.js icinde
detectCategoryFromQuery / detectColorFromQuery /
detectGenderFromQuery) duruyordu. Iki problem vardi:

1. Embedding backend'de uretiliyor. Sorgu zenginlestirmesi
   embedding'e girmezse hicbir ise yaramaz — vektor yalnizca
   kullanicinin yazdigi ham cumleyi gorur.

2. Ayni sozlugu iki yerde tutmak, gun gelip birinin
   guncellenmemesi demek.

Artik tek kaynak burasi. Frontend analizi backend'den okuyup
gosteriyor, kendi tahminini yapmiyor.


SUBSTRING DEGIL TOKEN
---------------------
Onceki surum `text.includes(word)` kullaniyordu ve bu iki
gercek hata uretiyordu:

    "topuklu ayakkabi"  -> "top" eslesti   -> kategori: shirt
    "manto ariyorum"    -> "man" eslesti   -> cinsiyet: men

Ayni hata style_engine.py'de de yasanmisti ("cap" kelimesi
baska kelimelerin icinde bulunuyordu). Cozum ayni: tek
kelimeli anahtarlar icin token esligi, cok kelimeli
anahtarlar icin alt dize.

Turkce ekleme dili oldugu icin token esligi tek basina
yetmiyor ("elbiseler", "gomlekleri"). 4 harf ve uzeri
anahtarlarda on-ek eslesmesi kabul ediliyor; 3 harfli
anahtarlarin cekimli halleri sozluge elle yazildi.

`top` anahtari bilincli olarak SILINDI. Ingilizce urun
basliklarinda mesru bir kelime ama biz KULLANICI SORGUSUNU
tariyoruz; Turkce yazan birinin "top" demesi giysi
kastetmiyor. "bluz", "tisort", "gomlek" zaten ayni kategoriyi
kapsiyor.


SOZLUKLER KATALOGA GORE OLCULDU
-------------------------------
728 urunluk katalogda her kelimenin gercekten gecip
gecmedigi sayildi. Ogrenilenler:

  - Turkce alanlar DOLU: "yazlik" 65 urun (62'si baslikta),
    "pamuk" 227, "gunluk" 506, "desen" 103. Turkce arama
    gercekten karsilik buluyor.

  - TURKCE KARAKTERSIZ yazimlar HIC YOK: "yazlik", "sifon",
    "cicek", "cizgili", "dugun" -> 0 urun. Kullanici Turkce
    karakter kullanmadan yazarsa (yaygin klavye aliskanligi)
    hicbir sey bulamaz. Bu yuzden hem sorgu hem urun metni
    ASCII'ye katlanarak karsilastiriliyor.

  - "renkli" literal olarak neredeyse yok: renkli 20,
    colorful 3, multicolor 0. Ama "desen" 103, "print" 91,
    "floral" 36, "cicek" 35 var. Yani "renkli" niyetini
    LITERAL aramak bos donuyor; desen/cicek uzerinden
    karsilamak gerekiyor. Kullanicinin istedigi davranis da
    tam olarak bu.

  - "keten" 9, "pamuk" 227. Yazlik genisletmesindeki terimler
    esit degerde degil; keten filtre olarak kullanilirsa
    sonuc neredeyse bos kalir. Bu yuzden kumas SERT FILTRE
    degil, siralama bonusu.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


# =========================================================
# NORMALIZASYON
# =========================================================

# Turkce harflerin ASCII karsiligi.
#
# unicodedata.normalize("NFKD") tek basina yetmiyor: "i" ve
# "I" ayrimi Turkce'de ozel ("İ" -> "i", "ı" -> "i") ve
# NFKD "ı" harfini bosaltmiyor.

_FOLD = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def fold(text: str) -> str:
    """
    Metni karsilastirilabilir hale getirir: Turkce harfler
    ASCII'ye katlanir, kucuk harfe cevrilir, aksanlar duser.

    Hem sorguya hem urun metnine uygulaniyor. Tek tarafa
    uygulamak ise yaramaz: katalogda "yazlik" (ASCII) hic
    gecmiyor, "yazlık" geciyor.
    """

    if not text:
        return ""

    folded = str(text).translate(_FOLD)

    # Kalan aksanli harfler (ör. "é") icin genel yol
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(c for c in folded if not unicodedata.combining(c))

    return folded.lower()


def tokenize(text: str) -> list[str]:
    """Katlanmis metni token listesine cevirir."""

    return [t for t in _TOKEN_SPLIT.split(fold(text)) if t]


# =========================================================
# DOLGU KELIMELER
# =========================================================

# Arama motorunu yaniltan kelimeler. Kullanici "kadin yazlik
# elbise ariyorum" yaziyor; "ariyorum" kelimesinin embedding'e
# girmesi vektoru urunlerden uzaklastiriyor.
#
# Liste bilincli olarak MUHAFAZAKAR. Anlam tasiyan bir
# kelimeyi yanlislikla atmak, dolgu kelimeyi birakmaktan
# daha zararli: "yeni" atilirsa siralama niyeti kaybolur.

STOPWORDS = frozenset(
    {
        # arama fiilleri
        "ariyorum", "ariyoruz", "ara", "arama", "arar",
        "bul", "bulur", "bulabilir", "buldur", "bulmak",
        "goster", "gosterir", "gosterebilir",
        "oner", "onerir", "onerebilir", "onerisi",
        "istiyorum", "isterim", "istedigim", "istiyoruz",
        "alacagim", "almak", "alabilir",
        "bakiyorum", "bakmak",
        # ihtiyac kaliplari
        "lazim", "gerek", "gerekiyor", "ihtiyacim",
        "olsun", "olur", "olacak",
        # nezaket / soru
        "bana", "bize", "benim", "rica", "ederim", "lutfen",
        "acaba", "musun", "misin", "mudur", "midir",
        "var", "yok", "mi", "mu", "ne", "nerede", "hangi",
        # genel doldurucular
        "bir", "tane", "adet", "biraz", "cok", "daha",
        "icin", "ile", "ve", "veya", "ya", "da", "de",
        "gibi", "kadar", "tarzi", "tarzinda",
        # anlam tasimayan urun sozcukleri
        # ("elbise" gibi kategori kelimeleri BURADA DEGIL)
        "urun", "urunler", "urunu", "model", "modeli",
        "cesit", "cesitleri", "secenek", "secenekleri",
    }
)


# Baglama gore atilan kelimeler.
#
# "uygun" tek basina dolgu ("ofis icin UYGUN bir gomlek") ama
# "uygun fiyat" bambaska bir sey — ucuz demek. Kelimeyi
# kosulsuz atmak fiyat niyetini yok ediyor, hic atmamak da
# dolgu birakiyor. Bu yuzden ARDINDAN GELEN kelimeye
# bakiyoruz.
CONDITIONAL_STOPWORDS: dict[str, frozenset[str]] = {
    # kelime -> ardindan gelirse KORUNACAK kelimeler
    "uygun": frozenset({"fiyat", "fiyatli", "fiyata", "butce", "butceye"}),
}


# Cok kelimeli dolgu kaliplari.
#
# Tek tek atilamazlar cunku parcalari anlam tasiyor:
# "var" ve "mi" ayri ayri listede olsa da "ne var" gibi
# kaliplar tokenizasyondan once temizlenirse geriye daha
# temiz bir cumle kaliyor.
STOPPHRASES = (
    "uygun olsun",
    "bulur musun",
    "bulabilir misin",
    "onerir misin",
    "var mi",
    "rica ederim",
    "ne var",
    "ne onerirsin",
    "bakmak istiyorum",
)


# =========================================================
# FACET SOZLUKLERI
# =========================================================
#
# Her deger listesi KATLANMIS (ASCII, kucuk harf) yazilir —
# karsilastirma da katlanmis metin uzerinde yapiliyor.
#
# 3 harfli anahtarlarin cekimli halleri elle yazildi
# (on-ek eslesmesi yalnizca 4+ harfte aciliyor).

GENDER_TERMS: dict[str, list[str]] = {
    "women": [
        "kadin", "kadinlar", "bayan", "bayanlar",
        "women", "woman", "womens", "female", "ladies",
        "kiz",
    ],
    "men": [
        "erkek", "erkekler", "men", "mens", "man",
        "male", "beyefendi",
    ],
}


# Giysi tipi. Deger, crud.semantic_search_products'in
# bekledigi kategori anahtari.

CATEGORY_TERMS: dict[str, list[str]] = {
    "dress": [
        "elbise", "elbiseler", "dress", "dresses",
        "gown", "abiye", "tulum",
    ],
    "shirt": [
        "gomlek", "gomlekler", "shirt", "shirts",
        "tisort", "tshirt", "t-shirt", "tee", "tees",
        "polo", "polos", "bluz", "blouse", "blouses",
        "kazak", "sweatshirt", "hoodie", "atlet",
        "body", "badi",
    ],
    "pants": [
        "pantolon", "pantolonlar", "pants", "trousers",
        "jean", "jeans", "kot", "sort", "shorts",
        "tayt", "leggings", "etek", "skirt", "skirts",
        "jogger",
    ],
    "jacket": [
        "ceket", "ceketler", "jacket", "jackets",
        "coat", "coats", "mont", "montlar", "kaban",
        "blazer", "yelek", "trenckot", "manto", "parka",
        "hirka", "cardigan",
    ],
    "shoes": [
        "ayakkabi", "ayakkabilar", "shoe", "shoes",
        "sneaker", "sneakers", "spor ayakkabi",
        "bot", "botlar", "botu", "boot", "boots",
        "sandalet", "sandal", "sandals", "terlik",
        "topuklu", "babet", "loafer", "cizme",
    ],
}


COLOR_TERMS: dict[str, list[str]] = {
    "white": ["beyaz", "white", "ekru"],
    "black": ["siyah", "black"],
    "red": ["kirmizi", "red", "bordo"],
    "blue": ["mavi", "blue"],
    "navy": ["lacivert", "navy"],
    "green": ["yesil", "green", "haki"],
    "yellow": ["sari", "yellow", "hardal"],
    "pink": ["pembe", "pink", "fusya"],
    "purple": ["mor", "purple", "lila"],
    "gray": ["gri", "gray", "grey", "fume"],
    "brown": ["kahverengi", "brown", "taba"],
    "beige": ["bej", "beige", "krem", "cream"],
    "orange": ["turuncu", "orange"],
}


# =========================================================
# ANLAMSAL GENISLETME
# =========================================================
#
# Bu bolum kullanicinin asil istedigi sey: "yazlik" diyen
# birine askili/ince/keten/sifon urunleri de getirmek.
#
# `expand` listesindeki terimler embedding metnine ve
# siralama bonusuna girer, SERT FILTREYE GIRMEZ. Sebep:
# katalogda "keten" yalnizca 9 urunde var; filtre yapilirsa
# "yazlik keten elbise" aramasi neredeyse bos doner.


@dataclass(frozen=True)
class Facet:
    """Tespit edilen bir niyet ve onun genisletmesi."""

    key: str
    label: str          # kullaniciya gosterilecek Turkce etiket
    triggers: list[str]  # sorguda aranan kelimeler
    expand: list[str]    # embedding + bonus terimleri
    bonus: float         # siralama bonusu

    # Kullaniciya "sunu da dene" olarak gosterilecek TURKCE
    # ifadeler.
    #
    # Neden ayri bir alan: `expand` listesi katalogla
    # eslesmek icin Ingilizce terimler de tasiyor
    # ("patterned", "lightweight"). Bunlari oneri olarak
    # gostermek Turkce arayuzde tuhaf duruyordu
    # ("kadın patterned elbise"). Oneri metni insan icin,
    # genisletme terimi makine icin.
    suggest: tuple[str, ...] = ()


SEASON_FACETS: list[Facet] = [
    Facet(
        key="summer",
        label="Yazlık",
        triggers=[
            "yazlik", "yaz", "summer", "ilkbahar", "spring",
            "sicak", "plaj", "beach", "tatil", "vacation",
        ],
        # Katalogda olculen karsilik: yazlik 65, summer 122,
        # lightweight 201, breathable 215, short sleeve 135,
        # pamuk 227, keten 9, sifon 16
        expand=[
            "yazlık", "summer", "ince", "lightweight",
            "breathable", "kısa kollu", "short sleeve",
            "askılı", "sleeveless", "pamuklu", "cotton",
            "keten", "linen", "şifon", "chiffon",
        ],
        bonus=7.0,
        suggest=("yazlık", "ince", "kısa kollu"),
    ),
    Facet(
        key="winter",
        label="Kışlık",
        triggers=[
            "kislik", "kis", "winter", "sonbahar", "soguk",
            "kar", "uskuru",
        ],
        # kislik 19, winter 50, warm 87, fleece 37, yun 85
        expand=[
            "kışlık", "winter", "kalın", "warm", "sıcak tutan",
            "polar", "fleece", "yün", "wool", "termal",
            "thermal", "şişme", "puffer", "kapitone", "quilted",
        ],
        bonus=7.0,
        suggest=("kışlık", "kalın", "sıcak tutan"),
    ),
]


PATTERN_FACETS: list[Facet] = [
    Facet(
        key="pattern",
        label="Renkli / Desenli",
        triggers=[
            "renkli", "colorful", "desenli", "desen",
            "cicekli", "cicek", "floral", "baskili",
            "printed", "print", "canli", "rengarenk",
            "multicolor", "cizgili", "striped", "ekose",
            "plaid", "puantiye", "leopar", "leopard",
        ],
        # renkli 20, colorful 3, multicolor 0  <- literal bos
        # desen 103, print 91, floral 36, cicek 35  <- gercek
        expand=[
            "desenli", "patterned", "çiçekli", "floral",
            "baskılı", "printed", "print", "renkli",
            "çok renkli", "colorful", "çizgili", "striped",
            "canlı renkler", "graphic",
        ],
        bonus=8.0,
        suggest=("desenli", "çiçekli", "çok renkli"),
    ),
    Facet(
        key="plain",
        label="Düz / Sade",
        triggers=[
            "duz", "sade", "solid", "plain", "tek renk",
            "minimal", "basic",
        ],
        expand=["düz", "solid", "sade", "plain", "basic", "minimal"],
        bonus=5.0,
        suggest=("düz", "sade"),
    ),
]


FABRIC_FACETS: list[Facet] = [
    Facet("linen", "Keten", ["keten", "linen"],
          ["keten", "linen"], 4.0, ("keten",)),
    Facet("cotton", "Pamuklu", ["pamuk", "pamuklu", "cotton"],
          ["pamuklu", "cotton", "pamuk"], 4.0, ("pamuklu",)),
    Facet("chiffon", "Şifon", ["sifon", "chiffon"],
          ["şifon", "chiffon"], 4.0, ("şifon",)),
    Facet("silk", "İpek", ["ipek", "silk", "saten", "satin"],
          ["ipek", "silk", "saten", "satin"], 4.0, ("ipek", "saten")),
    Facet("denim", "Denim", ["denim", "kot", "jean"],
          ["denim", "kot", "jean"], 4.0, ("kot",)),
    Facet("leather", "Deri", ["deri", "leather", "suni deri"],
          ["deri", "leather"], 4.0, ("deri",)),
    Facet("knit", "Triko", ["triko", "knit", "orgu"],
          ["triko", "knit", "örgü"], 4.0, ("triko", "örgü")),
    Facet("lace", "Dantel", ["dantel", "lace", "guipure"],
          ["dantel", "lace"], 4.0, ("dantel",)),
]


FIT_FACETS: list[Facet] = [
    Facet("oversized", "Oversize", ["oversize", "oversized", "bol", "salas"],
          ["oversized", "bol kesim", "loose", "salaş"], 3.0,
          ("oversize", "bol kesim")),
    Facet("slim", "Dar kesim", ["slim", "dar", "skinny", "kalip"],
          ["slim fit", "dar kesim", "skinny"], 3.0, ("dar kesim",)),
    Facet("crop", "Crop", ["crop", "kisa"],
          ["crop", "kısa", "cropped"], 3.0, ("crop",)),
    Facet("maxi", "Uzun / Maxi", ["maxi", "uzun"],
          ["maxi", "uzun", "long"], 3.0, ("uzun",)),
    Facet("mini", "Mini", ["mini"], ["mini", "kısa"], 3.0, ("mini",)),
    Facet("midi", "Midi", ["midi"], ["midi"], 3.0, ("midi",)),
    Facet("highwaist", "Yüksek bel", ["yuksek bel", "high waist", "highwaist"],
          ["yüksek bel", "high waist", "high rise"], 3.0, ("yüksek bel",)),
]


OCCASION_FACETS: list[Facet] = [
    Facet(
        key="work",
        label="Ofis / İş",
        triggers=["ofis", "office", "is", "work", "resmi",
                  "formal", "klasik", "toplanti", "mulakat"],
        expand=["ofis", "office", "work", "formal", "klasik",
                "business", "resmi"],
        bonus=5.0,
        suggest=("ofis", "klasik"),
    ),
    Facet(
        key="party",
        label="Davet / Gece",
        triggers=["davet", "party", "gece", "evening", "dugun",
                  "wedding", "nisan", "abiye", "kokteyl",
                  "mezuniyet", "dogum gunu"],
        expand=["davet", "party", "gece", "evening", "wedding",
                "abiye", "cocktail", "özel gün"],
        bonus=5.0,
        suggest=("davet", "abiye", "gece"),
    ),
    Facet(
        key="sport",
        label="Spor",
        triggers=["spor", "sport", "antrenman", "workout", "gym",
                  "kosu", "running", "fitness", "yoga"],
        expand=["spor", "sport", "athletic", "workout", "gym",
                "performance", "aktif"],
        bonus=5.0,
        suggest=("spor", "antrenman"),
    ),
    Facet(
        key="casual",
        label="Günlük",
        triggers=["gunluk", "casual", "rahat", "sokak",
                  "streetwear", "gundelik"],
        expand=["günlük", "casual", "rahat", "everyday"],
        bonus=4.0,
        suggest=("günlük", "rahat"),
    ),
]


ALL_FACET_GROUPS: dict[str, list[Facet]] = {
    "season": SEASON_FACETS,
    "pattern": PATTERN_FACETS,
    "fabric": FABRIC_FACETS,
    "fit": FIT_FACETS,
    "occasion": OCCASION_FACETS,
}


# =========================================================
# SINIRLAR
# =========================================================

# Embedding metnine eklenecek en fazla genisletme terimi.
#
# NEDEN SINIR VAR: embedding anlamlari ortalar. "kadin
# yazlik renkli elbise" sorgusuna 20 terim eklenirse vektor
# "elbise"den uzaklasip genel bir "yazlik giyim" bulutuna
# kayiyor. Olculen davranis: 6-8 terim anlamı keskinlestirir,
# 15+ terim bulanistiriyor.
#
# Geri kalan terimler kaybolmuyor; SQL tarafinda leksikal
# bonus olarak kullaniliyor (hibrit arama).
MAX_EMBED_EXPANSIONS = 8

# Kullaniciya gosterilecek alternatif sorgu sayisi
MAX_ALTERNATIVES = 4

# 4 harften kisa anahtarlarda on-ek eslesmesi kapali
PREFIX_MIN_LENGTH = 4


# =========================================================
# ESLESME
# =========================================================

def _matches(term: str, tokens: set[str], folded_text: str) -> bool:
    """
    Bir sozluk terimi sorguda geciyor mu.

    Cok kelimeli terim ("short sleeve") alt dize ile,
    tek kelimeli terim token esligi ile aranir. 4 harf ve
    uzeri tek kelimeler on-ek olarak da kabul edilir
    ("elbise" -> "elbiseler").
    """

    folded_term = fold(term)

    if not folded_term:
        return False

    if " " in folded_term or "-" in folded_term:
        return folded_term in folded_text

    if folded_term in tokens:
        return True

    if len(folded_term) >= PREFIX_MIN_LENGTH:
        return any(
            token.startswith(folded_term)
            for token in tokens
        )

    return False


def _first_match(
    table: dict[str, list[str]],
    tokens: set[str],
    folded_text: str,
) -> str | None:
    """Sozlukten ilk eslesen anahtari dondurur."""

    for key, terms in table.items():
        if any(_matches(t, tokens, folded_text) for t in terms):
            return key

    return None


def _matching_facets(
    facets: list[Facet],
    tokens: set[str],
    folded_text: str,
) -> list[Facet]:
    return [
        facet
        for facet in facets
        if any(_matches(t, tokens, folded_text) for t in facet.triggers)
    ]


# =========================================================
# SONUC YAPISI
# =========================================================

@dataclass
class QueryIntent:
    """Bir arama sorgusunun cozumlenmis hali."""

    raw: str
    cleaned: str

    gender: str | None = None
    category: str | None = None
    colors: list[str] = field(default_factory=list)

    facets: dict[str, list[Facet]] = field(default_factory=dict)

    embed_text: str = ""
    boost_terms: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)

    # Kullaniciya gosterilecek etiketler
    chips: list[dict] = field(default_factory=list)
    note: str = ""

    def facet_keys(self, group: str) -> list[str]:
        return [f.key for f in self.facets.get(group, [])]

    def wants_pattern(self) -> bool:
        return "pattern" in self.facet_keys("pattern")

    def to_dict(self) -> dict:
        """API cevabi icin duz sozluk."""

        return {
            "raw": self.raw,
            "cleaned": self.cleaned,
            "gender": self.gender,
            "category": self.category,
            "colors": self.colors,
            "season": self.facet_keys("season"),
            "patterns": self.facet_keys("pattern"),
            "fabrics": self.facet_keys("fabric"),
            "fits": self.facet_keys("fit"),
            "occasions": self.facet_keys("occasion"),
            "embed_text": self.embed_text,
            "boost_terms": self.boost_terms,
            "alternatives": self.alternatives,
            "chips": self.chips,
            "note": self.note,
        }


# =========================================================
# TEMIZLIK
# =========================================================

def clean_query(raw: str) -> str:
    """
    Dolgu kelimeleri atar.

    Orijinal yazim KORUNUYOR: Turkce karakterler embedding
    icin degerli ("yazlık" ile "yazlik" ayni vektoru
    uretmiyor). Katlanmis hal yalnizca karsilastirmada
    kullaniliyor.

    Hepsi atilirsa ham sorguya geri donuyoruz: bos bir arama
    terimi uretmek, dolgu kelimeyi birakmaktan kotudur.
    """

    text = str(raw or "").strip()

    if not text:
        return ""

    words = [w for w in re.split(r"\s+", text) if w]

    # Katlanmis karsiliklar: indeksler `words` ile ayni
    folded = [
        fold(word).strip("-_.,!?()[]{}\"'")
        for word in words
    ]

    # ---- 1. cok kelimeli kaliplar ----

    drop = [False] * len(words)

    for phrase in STOPPHRASES:
        parts = phrase.split()
        span = len(parts)

        for start in range(len(folded) - span + 1):
            if folded[start:start + span] == parts:
                for offset in range(span):
                    drop[start + offset] = True

    # ---- 2. tek kelimeler ----

    for index, token in enumerate(folded):

        if drop[index] or not token:
            continue

        if token in STOPWORDS:
            drop[index] = True
            continue

        protectors = CONDITIONAL_STOPWORDS.get(token)

        if protectors is None:
            continue

        following = folded[index + 1] if index + 1 < len(folded) else ""

        if following not in protectors:
            drop[index] = True

    kept = [
        words[index].strip()
        for index in range(len(words))
        if not drop[index] and words[index].strip()
    ]

    return " ".join(kept) if kept else text


# =========================================================
# ANA GIRIS
# =========================================================

def analyze(raw_query: str) -> QueryIntent:
    """
    Dogal dil sorgusunu arama stratejisine cevirir.

    Bu fonksiyon veritabanina DOKUNMAZ ve saf (deterministik)
    calisir; test etmesi ucuz ve sonuclari ongorulebilir.
    """

    raw = str(raw_query or "").strip()

    cleaned = clean_query(raw)

    folded_text = fold(cleaned)
    tokens = set(tokenize(cleaned))

    intent = QueryIntent(raw=raw, cleaned=cleaned)

    # ---- sert filtreler ----

    intent.gender = _first_match(GENDER_TERMS, tokens, folded_text)
    intent.category = _first_match(CATEGORY_TERMS, tokens, folded_text)

    intent.colors = [
        key
        for key, terms in COLOR_TERMS.items()
        if any(_matches(t, tokens, folded_text) for t in terms)
    ]

    # ---- yumusak facet'ler ----

    for group, facets in ALL_FACET_GROUPS.items():
        found = _matching_facets(facets, tokens, folded_text)

        if found:
            intent.facets[group] = found

    # "renkli" bir RENK DEGIL, bir desen niyeti.
    #
    # Kullanici "renkli elbise" yazdiginda sert renk filtresine
    # dusmemeli — katalogda "renkli" kelimesi 20 urunde var ve
    # filtre yapilirsa sonuc neredeyse bos kalir. Desen
    # facet'i bu niyeti karsiliyor.

    intent.embed_text = _build_embed_text(intent)
    intent.boost_terms = _build_boost_terms(intent)
    intent.alternatives = _build_alternatives(intent)
    intent.chips = _build_chips(intent)
    intent.note = _build_note(intent)

    return intent


# =========================================================
# ZENGINLESTIRME
# =========================================================

def _ordered_expansions(intent: QueryIntent) -> list[str]:
    """
    Genisletme terimlerini DONUSUMLU olarak dizer.

    Ilk surum gruplari sirayla tuketiyordu ve bu olculebilir
    bir hata uretti:

        "kadin yazlik renkli elbise"
        -> desen grubu 14 terim tasiyor, MAX_EMBED_EXPANSIONS
           8 oldugu icin 8 slotun hepsini desen kapiyordu.
           Kullanicinin acikca yazdigi "yazlik" niyeti
           embedding'e HIC girmiyordu.

        "yazlik keten pantolon"
        -> ayni sekilde "keten" disarida kaliyordu.

Simdi her gruptan sirayla birer terim aliniyor: tespit
    edilen her niyet embedding metninde temsil ediliyor.
    Grup sirasi hala onemli (ilk turda kim once gelsin), ama
    artik kimse tamamen dislanmiyor.
    """

    order = ["pattern", "season", "fabric", "occasion", "fit"]

    # Her grubun terim listesini sirayla hazirla
    queues: list[list[str]] = []

    for group in order:
        group_terms: list[str] = []

        for facet in intent.facets.get(group, []):
            group_terms.extend(facet.expand)

        if group_terms:
            queues.append(group_terms)

    terms: list[str] = []
    seen: set[str] = set()

    # Donusumlu tuketim: en uzun kuyruk bitene kadar
    depth = max((len(q) for q in queues), default=0)

    for index in range(depth):
        for queue in queues:
            if index >= len(queue):
                continue

            term = queue[index]
            key = fold(term)

            if key and key not in seen:
                seen.add(key)
                terms.append(term)

    return terms


def _build_embed_text(intent: QueryIntent) -> str:
    """
    Embedding'e gidecek metni kurar.

    HIBRIT ARAMA KARARI: butun genisletme terimlerini
    vektore yuklemiyoruz. Embedding anlamlari ortaladigi
    icin 15+ terim sorguyu bulanistiriyor; "elbise" niyeti
    genel bir "yazlik giyim" bulutuna kayiyor.

    Ilk MAX_EMBED_EXPANSIONS terim vektore, geri kalani
    SQL tarafinda leksikal bonusa gidiyor. Boylece anlam
    vektorden, kesinlik kelimeden geliyor.
    """

    parts = [intent.cleaned] if intent.cleaned else []

    # Cinsiyeti iki dilde de veriyoruz: katalog basliklari
    # Ingilizce, Turkce ceviriler ayri alanda.
    if intent.gender == "women":
        parts.append("kadın women")
    elif intent.gender == "men":
        parts.append("erkek men")

    expansions = _ordered_expansions(intent)

    if expansions:
        parts.append(" ".join(expansions[:MAX_EMBED_EXPANSIONS]))

    text = " ".join(p for p in parts if p).strip()

    return text or intent.raw


def _build_boost_terms(intent: QueryIntent) -> list[str]:
    """
    SQL tarafinda leksikal bonus verilecek terimler.

    Vektor arama "yazlik" niyetini yakalayabilir ama
    GARANTI ETMEZ. Basliginda gercekten "yazlık" yazan bir
    urunun one cikmasi icin kelime eslesmesi de gerekiyor.
    """

    terms: list[str] = []
    seen: set[str] = set()

    for group_facets in intent.facets.values():
        for facet in group_facets:
            for term in facet.expand:
                key = fold(term)

                if key and key not in seen:
                    seen.add(key)
                    terms.append(term)

    return terms


def _category_word_in_query(intent: QueryIntent) -> str:
    """
    Kullanicinin sorgusunda gecen kategori kelimesini
    oldugu gibi dondurur ("tişört", "manto", "bot").

    Ham sorgudan aliniyor ki Turkce yazim korunsun; katlanmis
    hali yalnizca karsilastirma icin kullaniliyor.
    """

    if not intent.category:
        return ""

    terms = CATEGORY_TERMS.get(intent.category, [])
    folded_terms = {fold(t) for t in terms}

    for word in re.split(r"\s+", intent.cleaned.strip()):
        stripped = word.strip("-_.,!?()[]{}\"'")
        folded_word = fold(stripped)

        if not folded_word:
            continue

        if folded_word in folded_terms:
            return stripped

        # "elbiseler" -> "elbise" (on-ek eslesmesi)
        if any(
            len(t) >= PREFIX_MIN_LENGTH and folded_word.startswith(t)
            for t in folded_terms
        ):
            return stripped

    return ""


def _build_alternatives(intent: QueryIntent) -> list[str]:
    """
    "Birebir sonuc cikmazsa" kullanilacak alternatif sorgular.

    Bunlar kullaniciya oneri olarak gosteriliyor; arama
    motoru kendi gevsetme merdivenini ayri isletiyor
    (search_service.py). Ikisi ayri sey: bu liste insanin
    tiklayacagi bir sey, merdiven makinenin yaptigi sey.
    """

    base_parts: list[str] = []

    if intent.gender == "women":
        base_parts.append("kadın")
    elif intent.gender == "men":
        base_parts.append("erkek")

    # KULLANICININ KENDI KELIMESI tercih ediliyor.
    #
    # Sabit etiket kullanmak yanlis oneri uretiyordu:
    # "oversize beyaz tisort" sorgusuna "oversized gömlek"
    # onerilmisti — kullanici tisort yazmisti, gomlek degil.
    # Kategori anahtarlari kaba (shirt = gomlek/tisort/bluz);
    # oneri metninde kullanicinin yazdigi kelimeyi korumak
    # hem daha dogru hem daha az sasirtici.
    category_label = _category_word_in_query(intent) or {
        "dress": "elbise",
        "shirt": "üst giyim",
        "pants": "alt giyim",
        "jacket": "dış giyim",
        "shoes": "ayakkabı",
    }.get(intent.category or "", "")

    alternatives: list[str] = []
    seen: set[str] = set()

    def add(*words: str) -> None:
        """Bir oneri ekler. Uc kural uyguluyor."""

        # 1. KELIME TEKRARINI AT.
        #
        # Facet es anlamlisi ile kategori kelimesi ayni
        # olabiliyor: "abiye" hem davet facet'inin onerisi
        # hem CATEGORY_TERMS["dress"] icinde ve sonuc
        # "abiye abiye" oluyordu. Ayni sey "kot kot" icin de
        # gecerliydi (denim facet'i + pants kategorisi).
        parts: list[str] = []
        part_keys: set[str] = set()

        for chunk in words:
            for word in re.split(r"\s+", str(chunk or "").strip()):
                if not word:
                    continue

                word_key = fold(word)

                if word_key and word_key not in part_keys:
                    part_keys.add(word_key)
                    parts.append(word)

        text = " ".join(parts).strip()

        if not text:
            return

        # 2. EN AZ IKI ANLAMLI PARCA OLSUN.
        #
        # Tek kelimelik oneri hicbir sey anlatmiyor:
        # "topuklu ayakkabı" arayana "topuklu" onermek
        # sorguyu kirpmaktan baska bir sey degil. Iki parca
        # en az "nitelik + kategori" demek.
        if len(parts) < 2:
            return

        # 3. TEKRARI VE SORGUNUN KENDISINI ATLA.
        key = fold(text)

        if key in seen or key == fold(intent.cleaned):
            return

        seen.add(key)
        alternatives.append(text)

    base = " ".join(base_parts)

    # Her facet icin bir alternatif: o niyetin TURKCE
    # es anlamlisi + kategori.
    #
    # `suggest` bos kalirsa `expand`e dusuyoruz — oneri hic
    # gostermemekten iyi, ama Ingilizce cikabilir.
    for group in ("pattern", "season", "fabric", "occasion", "fit"):
        for facet in intent.facets.get(group, []):

            words = facet.suggest or tuple(facet.expand[:2])

            for term in words:
                add(base, term, category_label)

            if len(alternatives) >= MAX_ALTERNATIVES:
                return alternatives[:MAX_ALTERNATIVES]

    # Hic facet yoksa renk / kategori uzerinden bir sey oner
    if not alternatives and category_label:
        add(base, category_label)

    return alternatives[:MAX_ALTERNATIVES]


# =========================================================
# ACIKLAMA (kullaniciya gosterilen)
# =========================================================

_GENDER_LABEL = {"women": "Kadın", "men": "Erkek"}

_CATEGORY_LABEL = {
    "dress": "Elbise",
    "shirt": "Üst giyim",
    "pants": "Alt giyim",
    "jacket": "Dış giyim",
    "shoes": "Ayakkabı",
}

_COLOR_LABEL = {
    "white": "Beyaz", "black": "Siyah", "red": "Kırmızı",
    "blue": "Mavi", "navy": "Lacivert", "green": "Yeşil",
    "yellow": "Sarı", "pink": "Pembe", "purple": "Mor",
    "gray": "Gri", "brown": "Kahverengi", "beige": "Bej",
    "orange": "Turuncu",
}


def _build_chips(intent: QueryIntent) -> list[dict]:
    """
    Arama sonuclarinin ustunde gosterilecek "AI ne anladi"
    etiketleri.

    Neden gosteriyoruz: sorguyu sessizce degistiren bir
    arama motoru kullaniciyi sasirtir. "Renkli" yazip
    desenli urunler gelince, sebebini gormek gerekiyor.
    Ayrica yanlis anlasilma oldugunda kullanici bunu
    gorup sorguyu duzeltebiliyor.
    """

    chips: list[dict] = []

    if intent.gender:
        chips.append({
            "kind": "gender",
            "label": _GENDER_LABEL[intent.gender],
            "strict": True,
        })

    if intent.category:
        chips.append({
            "kind": "category",
            "label": _CATEGORY_LABEL.get(intent.category, intent.category),
            "strict": True,
        })

    for color in intent.colors:
        chips.append({
            "kind": "color",
            "label": _COLOR_LABEL.get(color, color),
            "strict": True,
        })

    for group in ("season", "pattern", "fabric", "fit", "occasion"):
        for facet in intent.facets.get(group, []):
            chips.append({
                "kind": group,
                "label": facet.label,
                "strict": False,
            })

    return chips


def _build_note(intent: QueryIntent) -> str:
    """
    Yonlendirme notu: aramanin neyi one aldigini bir cumlede
    anlatir. Uydurma bilgi YOK — yalnizca gercekten
    tetiklenmis facet'ler cumleye girer.
    """

    if intent.wants_pattern():
        return (
            "Birebir \"renkli\" yazmayan ama desenli, çiçekli ve "
            "baskılı ürünler de sonuçlara dahil edildi; "
            "katalogda \"renkli\" kelimesi nadir geçiyor."
        )

    season = intent.facet_keys("season")

    if "summer" in season:
        return (
            "Yazlık niyeti ince, kısa kollu, askılı, keten ve "
            "şifon ürünlere genişletildi."
        )

    if "winter" in season:
        return (
            "Kışlık niyeti kalın, yün, polar ve şişme ürünlere "
            "genişletildi."
        )

    if intent.facets.get("occasion"):
        labels = [f.label for f in intent.facets["occasion"]]
        return (
            "%s kullanımına uygun ürünler öne alındı."
            % " / ".join(labels)
        )

    if intent.facets.get("fabric"):
        labels = [f.label for f in intent.facets["fabric"]]
        return (
            "%s ürünler öne alındı; kumaş bilgisi ürün "
            "açıklamasında geçiyorsa da sayılıyor."
            % " / ".join(labels)
        )

    if intent.cleaned != intent.raw:
        return "Arama terimi sadeleştirildi, anlamsal olarak eşleştirildi."

    return "Anlamsal benzerliğe göre sıralandı."
