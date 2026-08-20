"""
STIL ESLESME MOTORU  (8 arketip, cok secimli)

Bu dosya "AI Stil Uyumu" yuzdesini ureten kuraldir.

Durustce ne oldugu: iceriğe dayali (content-based) bir
skorlama modeli. Buyuk dil modeli veya sinir agi yok;
urun metni ile arketip sozlukleri arasindaki agirlikli
ortusme + kullanicinin gecmis davranisi.

Neden boyle: yeni kullanicinin hic etkilesimi yoktur
(cold start). Collaborative filtering bu noktada calismaz
cunku ogrenecegi gecmis yoktur. Icerik tabanli skor ilk
saniyeden itibaren anlamli siralama uretir ve ayni zamanda
ML modelinin ogrenecegi ETIKETLI veriyi biriktirir:
kullaniciya hangi skorla ne gosterdik, ne yapti.

Uc asamali calisir:

    1. ADAY URETIMI     (product_style_scores tablosu, SQL)
       Arketip x urun temel skoru onceden hesaplanir.

    2. HARMANLAMA       (blend_scores)
       Kullanici 1-3 tarz sectigi icin skorlar birlestirilir.

    3. YENIDEN SIRALAMA (personalize_score)
       Begenilen marka / kategori / renk / fiyat araligina
       gore skor guncellenir.


SOZLUKLER KATALOGA GORE KALIBRE EDILDI
--------------------------------------
Kelimeler rastgele secilmedi; 707 urunluk katalogda
gercekten gecip gecmedigi olculdu. Katalogda hic gecmeyen
kelimeler cikarildi: skoru degistirmezler ama bakim yapan
kisiye var olmayan bir kapsam varmis gibi gosterirler.

Katalog kapsami cok DENGESIZ ve bu bilinen bir sinirlama:
athleisure ~%29, y2k ~%3. Ince havuzlu arketipler
kullaniciya secim aninda soylenir (THIN_POOL_THRESHOLD).
Cozum formul degistirmek degil, katalogu genisletmektir.

Olcmek icin:
    python scripts/09_compute_style_scores.py --dry-run
"""

from __future__ import annotations

import math
import re
import unicodedata


# =========================================================
# ARKETIPLER
# =========================================================

MINIMALIST = "minimalist"
STREETWEAR = "streetwear"
SMART_CASUAL = "smart_casual"
OLD_MONEY = "old_money"
BOHO = "boho"
ATHLEISURE = "athleisure"
GOTH = "goth"
Y2K = "y2k"

ARCHETYPES = (
    MINIMALIST,
    STREETWEAR,
    SMART_CASUAL,
    OLD_MONEY,
    BOHO,
    ATHLEISURE,
    GOTH,
    Y2K,
)

# Kullanicinin secebilecegi tarz sayisi.
# 3'ten fazlasi "her sey" demektir ve kisisellestirmeyi
# anlamsiz kilar.
MIN_SELECTED_STYLES = 1
MAX_SELECTED_STYLES = 3


ARCHETYPE_PROFILES = {
    MINIMALIST: {
        "emoji": "🌿",
        "label": "Minimalist & Basic",
        "short_label": "Minimalist",
        "tagline": "Nötr tonlar, kapsül gardırop",
        "description": (
            "Gösterişsiz ama iyi oturan parçalar. "
            "Siyah, beyaz, gri, bej."
        ),
        "image_url": (
            "https://images.unsplash.com/photo-1479064555552-3ef4979f8908"
            "?auto=format&fit=crop&w=800&q=80"
        ),
    },
    STREETWEAR: {
        "emoji": "🛹",
        "label": "Streetwear & Urban",
        "short_label": "Streetwear",
        "tagline": "Oversize, hoodie, sneaker",
        "description": (
            "Bol kesim üstler, kargo pantolon, "
            "grafik baskı ve spor ayakkabı."
        ),
        "image_url": (
            "https://images.unsplash.com/photo-1523398002811-999ca8dec234"
            "?auto=format&fit=crop&w=800&q=80"
        ),
    },
    SMART_CASUAL: {
        "emoji": "💼",
        "label": "Smart Casual & Office",
        "short_label": "Smart Casual",
        "tagline": "Şık blazer, kumaş pantolon",
        "description": (
            "Ofise de akşam yemeğine de gidebilen "
            "modern kesimler."
        ),
        "image_url": (
            "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d"
            "?auto=format&fit=crop&w=800&q=80"
        ),
    },
    OLD_MONEY: {
        "emoji": "🍷",
        "label": "Old Money & Elegant",
        "short_label": "Old Money",
        "tagline": "Lüks dokular, klasik kesimler",
        "description": (
            "Yün, keten, ipek. Trençkot, loafer, "
            "polo yaka. Sessiz lüks."
        ),
        "image_url": (
            "https://images.unsplash.com/photo-1594938298603-c8148c4dae35"
            "?auto=format&fit=crop&w=800&q=80"
        ),
    },
    BOHO: {
        "emoji": "🎨",
        "label": "Boho & Vintage",
        "short_label": "Boho",
        "tagline": "Desenli, retro, özgür",
        "description": (
            "Çiçek desenleri, fırfırlar, tunikler, "
            "salaş kesimler."
        ),
        "image_url": (
            "https://images.unsplash.com/photo-1490481651871-ab68de25d43d"
            "?auto=format&fit=crop&w=800&q=80"
        ),
    },
    ATHLEISURE: {
        "emoji": "🏋️",
        "label": "Athleisure & Sporty",
        "short_label": "Athleisure",
        "tagline": "Tayt, performans, dinamik",
        "description": (
            "Antrenmandan sokağa geçebilen nefes "
            "alabilir parçalar."
        ),
        "image_url": (
            "https://images.unsplash.com/photo-1483721310020-03333e577078"
            "?auto=format&fit=crop&w=800&q=80"
        ),
    },
    GOTH: {
        "emoji": "🖤",
        "label": "Goth & Dark Academia",
        "short_label": "Goth",
        "tagline": "Siyah tonlar, deri, kış",
        "description": (
            "Koyu paletler, dantel, deri detaylar, "
            "ekose ve balıkçı yaka."
        ),
        "image_url": (
            "https://images.unsplash.com/photo-1516762689617-e1cffcef479d"
            "?auto=format&fit=crop&w=800&q=80"
        ),
    },
    Y2K: {
        "emoji": "✨",
        "label": "Y2K & Trendy",
        "short_label": "Y2K",
        "tagline": "Canlı renkler, 2000'ler",
        "description": (
            "File dokular, parlak tonlar, kısa "
            "kesimler, platform tabanlar."
        ),
        "image_url": (
            "https://images.unsplash.com/photo-1495121605193-b116b5b9c5fe"
            "?auto=format&fit=crop&w=800&q=80"
        ),
    },
}


# =========================================================
# SOZLUKLER
# =========================================================

# Urun basligi Ingilizce, title_tr Turkce. Ikisini birlikte
# tarayabilmek icin her iki dilden anahtar kelime var.
#
# Agirliklar: 8-10 = arketipin imza parcasi
#             4-7  = guclu isaret
#             2-3  = zayif isaret

_POSITIVE = {
    MINIMALIST: {
        "solid": 7, "plain": 7, "basic": 6, "düz": 5,
        "classic fit": 4, "crew neck": 5, "bisiklet yaka": 4,
        "slim": 3, "regular fit": 3, "essential": 5,
        "knit": 3, "sweater": 3, "cardigan": 3, "kazak": 3,
        "gömlek": 2, "trouser": 3, "pantolon": 2, "chino": 3,
        "tişört": 3, "t-shirt": 3, "tee": 2,
        "turtleneck": 3, "balıkçı yaka": 3,
        "pima": 3, "supima": 3, "pamuklu": 2,
    },
    STREETWEAR: {
        "hoodie": 10, "hoodies": 10, "kapüşonlu": 9,
        "sweatshirt": 8, "sweat": 3, "jogger": 8,
        "oversized": 8, "oversize": 8, "bol kesim": 7,
        "graphic": 7, "grafik": 6, "baskılı": 5, "baskı": 4,
        "logo": 3, "sneaker": 8, "spor ayakkabı": 7,
        "cargo": 7, "kargo": 7, "denim": 4, "jean": 3,
        "streetwear": 10, "tracksuit": 6, "eşofman": 5,
        "pullover": 4, "fleece": 3, "polar": 3,
        "cap": 3, "şapka": 3, "bere": 3,
    },
    SMART_CASUAL: {
        "blazer": 10, "chino": 8, "polo": 6,
        "dress shirt": 8, "klasik gömlek": 7, "gömlek": 4,
        "kumaş pantolon": 8, "dress pant": 7,
        "modern fit": 6, "slim fit": 5, "tailored": 7,
        "loafer": 6, "oxford": 5, "derby": 4,
        "sport coat": 8, "spor ceket": 7, "ceket": 3,
        "ofis": 6, "business": 6, "wrinkle": 4,
        "ütü gerektirmeyen": 5, "twill": 3,
        "pleated": 3, "pileli": 3, "düğmeli": 3,
    },
    OLD_MONEY: {
        "wool": 8, "yün": 8, "merino": 8,
        "silk": 8, "ipek": 8, "linen": 8, "keten": 8,
        "tweed": 9, "cashmere": 10, "kaşmir": 10,
        "trench": 9, "trençkot": 9, "overcoat": 8,
        "palto": 7, "kaban": 6,
        "loafer": 7, "oxford": 6,
        "polo shirt": 5, "polo yaka": 5,
        "tailored": 7, "kruvaze": 7,
        "cardigan": 5, "hırka": 5,
        "camel": 5, "houndstooth": 7, "kazayağı": 7,
        "pinstripe": 6, "manşet": 3,
    },
    BOHO: {
        "boho": 10, "bohem": 10,
        "floral": 8, "çiçekli": 8, "çiçek desenli": 8,
        "vintage": 7, "retro": 7,
        "tunic": 7, "tunik": 7,
        "maxi": 6, "midi": 4,
        "ruffle": 7, "fırfırlı": 7, "fırfır": 6,
        "flowy": 6, "salaş": 6, "puf kollu": 6,
        "crochet": 8, "örgü": 3,
        "embroidered": 7, "nakışlı": 6,
        "batik": 7, "desenli": 5, "printed": 4,
        "smocked": 5, "smoklu": 5, "kimono": 6,
    },
    # Agirliklar bilincli olarak DUSUK.
    #
    # Spor urunu basliklarinda bu kelimeler birlikte gecme
    # egiliminde ("Atletik Sort - Hizli Kuruyan, Nefes
    # Alabilir, Performans"). Yuksek agirliklarla toplam
    # 97.9'a kadar cikti ve athleisure butun katalogu
    # domine etti (221/707 urunde en yuksek skor).
    ATHLEISURE: {
        "athletic": 5, "activewear": 6, "aktif": 2,
        "workout": 5, "antrenman": 5, "training": 4,
        "running": 5, "koşu": 5, "yürüyüş": 3,
        "yoga": 7, "pilates": 7, "gym": 5,
        "performance": 4, "performans": 4,
        "quick dry": 3, "hızlı kuruyan": 3,
        "nefes alabilir": 3, "moisture": 3, "ter emici": 3,
        "compression": 5, "sıkıştırma": 4,
        "tayt": 8, "şort": 3, "short": 2,
        "spor büstiyer": 9,
        "sporcu": 4, "golf": 4, "tennis": 5,
        "stretch": 2, "esnek": 2, "lightweight": 2,
    },
    # "black"/"siyah" agirligi 7'den 3'e dusuruldu.
    #
    # Kalibrasyonda siyah bir cocuk atleti bu arketipte
    # 1. siraya cikti. Siyah olmak goth yapmaz; deri,
    # dantel, korse, ekose, bot yapar. Renk artik yalnizca
    # destekleyici sinyal.
    GOTH: {
        "black": 3, "siyah": 3,
        "leather": 10, "deri": 9, "suni deri": 9,
        "lace": 8, "dantel": 8,
        "corset": 10, "korse": 10,
        "plaid": 7, "ekose": 7, "flannel": 5, "flanel": 5,
        "turtleneck": 7, "balıkçı yaka": 7,
        "combat": 8, "boot": 5, "bot": 5,
        "chunky": 4, "chain": 6, "zincir": 6,
        "çentikli": 3,
    },
    # Belirsiz kelimeler cikarildi: "file", "mini", "canli",
    # "parlak", "askili", "flare", "bootcut".
    #
    # Bunlar Y2K'ye ozgu degil ve katalogdaki spor
    # urunlerinde geciyordu; "Polo Ralph Lauren Athletic
    # Performance" urunu bu yuzden Y2K'de 1. siraya cikmisti.
    #
    # SONUC: katalogda gercek Y2K parcasi neredeyse yok
    # (bkz. THIN_POOL_THRESHOLD). Tercih edilen davranis,
    # alakasiz urune yuksek skor vermek yerine SKOR
    # VERMEMEK — badge esigini gecmez, sahte yuzde cikmaz.
    Y2K: {
        "y2k": 10,
        "mesh": 5,
        "crop": 9, "crop top": 10, "kısa üst": 8,
        "halter": 8,
        "low rise": 9, "düşük bel": 9,
        "sequin": 9, "payet": 9, "pullu": 7,
        "glitter": 8, "simli": 8, "shimmer": 7,
        "metallic": 8, "metalik": 8,
        "neon": 9,
        "butterfly": 8, "kelebek": 8,
        "rhinestone": 8, "taşlı": 7,
        "mini etek": 9,
        "platform": 8, "kalın taban": 7,
        "velour": 7, "tie dye": 7,
    },
}


_NEGATIVE = {
    MINIMALIST: {
        "graphic": 7, "grafik": 6, "baskılı": 5,
        "sequin": 9, "payet": 9, "glitter": 8, "simli": 7,
        "floral": 6, "çiçekli": 6, "leopard": 8, "leopar": 8,
        "neon": 8, "tie dye": 7, "batik": 6, "fırfırlı": 5,
        "rhinestone": 8, "taşlı": 7,
    },
    STREETWEAR: {
        "blazer": 7, "suit": 7, "takım": 5, "tailored": 6,
        "ofis": 6, "business": 5, "trench": 4,
        "loafer": 4, "kruvaze": 5, "keten": 3,
        "floral": 4, "çiçekli": 4, "fırfırlı": 6,
    },
    SMART_CASUAL: {
        "hoodie": 7, "kapüşonlu": 6, "sweatshirt": 6,
        "jogger": 7, "oversized": 6, "oversize": 6,
        "tayt": 8, "spor büstiyer": 8,
        "graphic": 5, "grafik": 4, "neon": 7,
        "payet": 7, "sequin": 7, "crop": 6,
    },
    OLD_MONEY: {
        "hoodie": 7, "kapüşonlu": 6, "sweatshirt": 6,
        "jogger": 7, "graphic": 7, "grafik": 6,
        "neon": 9, "payet": 8, "sequin": 8, "glitter": 8,
        "tie dye": 8, "batik": 7, "crop": 6,
        "tayt": 7, "y2k": 8, "leopar": 6, "leopard": 6,
    },
    BOHO: {
        "blazer": 5, "suit": 6, "takım": 4,
        "athletic": 6, "activewear": 6, "workout": 6,
        "tayt": 6, "compression": 6,
        "ofis": 5, "business": 5, "performans": 5,
    },
    ATHLEISURE: {
        "blazer": 8, "suit": 8, "takım": 6, "tailored": 7,
        "trench": 6, "loafer": 6, "oxford": 5,
        "keten": 4, "ipek": 6, "silk": 6,
        "payet": 7, "sequin": 7, "dantel": 6, "lace": 5,
        "ofis": 6, "kruvaze": 6,
    },
    GOTH: {
        "neon": 8, "canlı": 5, "floral": 6, "çiçekli": 6,
        "pastel": 7, "beyaz": 4, "white": 4,
        "athletic": 4, "activewear": 4, "golf": 5,
        "tie dye": 6, "batik": 5, "bohem": 5, "boho": 5,
        "keten": 3,
    },
    Y2K: {
        "blazer": 6, "suit": 7, "takım": 5, "tailored": 6,
        "wool": 5, "yün": 5, "tweed": 7, "trench": 5,
        "ofis": 6, "business": 6, "klasik gömlek": 6,
        "loafer": 4, "kruvaze": 6, "palto": 4,
    },
}


# Renk aileleri
_COLOR_WORDS = {
    "siyah": ("black", "siyah"),
    "beyaz": ("white", "beyaz", "ivory", "ecru"),
    "gri": ("grey", "gray", "gri", "charcoal", "antrasit"),
    "bej": ("beige", "bej", "khaki", "haki", "camel", "taş"),
    "lacivert": ("navy", "lacivert"),
    "krem": ("cream", "krem"),
    "kahve": ("brown", "kahve", "chocolate", "coffee", "tarçın"),
    "bordo": ("burgundy", "bordo", "maroon", "wine", "şarap"),
    "yeşil": ("green", "yeşil", "olive", "zeytin"),
    "mavi": ("blue", "mavi", "indigo", "denim"),
    "kırmızı": ("red", "kırmızı"),
    "turuncu": ("orange", "turuncu"),
    "mor": ("purple", "mor", "lilac", "lila"),
    "pembe": ("pink", "pembe", "fuşya", "fuchsia"),
    "sarı": ("yellow", "sarı", "mustard", "hardal"),
}

_ARCHETYPE_COLORS = {
    MINIMALIST: ("siyah", "beyaz", "gri", "bej", "krem", "lacivert"),
    STREETWEAR: ("siyah", "beyaz", "gri", "mavi", "kırmızı", "yeşil"),
    SMART_CASUAL: ("lacivert", "gri", "beyaz", "bej", "mavi"),
    OLD_MONEY: ("lacivert", "kahve", "bordo", "krem", "bej", "yeşil"),
    BOHO: ("kahve", "bej", "yeşil", "turuncu", "krem", "bordo"),
    ATHLEISURE: ("siyah", "gri", "mavi", "pembe", "mor", "yeşil"),
    GOTH: ("siyah", "gri", "bordo", "mor", "kahve"),
    Y2K: ("pembe", "mor", "mavi", "turuncu", "sarı", "beyaz"),
}


# Arketipin tipik fiyat araligi (USD, katalog para birimi)
_PRICE_BANDS = {
    MINIMALIST: (15.0, 65.0),
    STREETWEAR: (20.0, 90.0),
    SMART_CASUAL: (25.0, 110.0),
    OLD_MONEY: (45.0, 250.0),
    BOHO: (18.0, 80.0),
    ATHLEISURE: (15.0, 75.0),
    GOTH: (20.0, 120.0),
    Y2K: (12.0, 60.0),
}


# =========================================================
# GOSTERIM ESIKLERI
# =========================================================

# 72 uzeri : "%86 AI Stil Uyumu" — sayiyi gosteriyoruz
# 60-72    : sadece gerekce cumlesi
# 60 alti  : hicbir sey
#
# Neden iki kademe: "%61 uyum" yazmak kullaniciyi ikna
# etmez, guveni azaltir. Zayif ama gercek bir sinyal varsa
# sayi yerine SEBEBI soylemek daha durust.

MATCH_BADGE_THRESHOLD = 72
REASON_CHIP_THRESHOLD = 60

# Bir arketipte bu sayidan az urun badge esigini geciyorsa
# "ince havuz" sayilir ve kullaniciya secim aninda soylenir.
THIN_POOL_THRESHOLD = 25


# =========================================================
# METIN
# =========================================================

def normalize(text) -> str:
    """Kucuk harf, noktalama -> bosluk, Turkce karakter korunur."""

    if not text:
        return ""

    lowered = unicodedata.normalize("NFC", str(text).lower())

    lowered = re.sub(r"[^\w\sçğıöşü-]", " ", lowered)

    return re.sub(r"\s+", " ", lowered).strip()


def product_text(product) -> str:
    """
    Skorlamada kullanilan birlesik urun metni.

    DIKKAT: features / description BILINCLI OLARAK yok.

    Kalibrasyonda goruldu ki pazarlama metni yanlis sinyal
    uretiyor: bir kot pantolonun aciklamasinda "sneakers ile
    kombinleyin" yazdigi icin urun streetwear sanildi.
    Baslik ve kategori ise urunun ne OLDUGUNU soyler.
    """

    return normalize(
        " ".join(
            [
                getattr(product, "title", "") or "",
                getattr(product, "title_tr", "") or "",
                getattr(product, "category", "") or "",
            ]
        )
    )


def text_tokens(text: str):
    """
    Kelime kumesi.

    Alt dize aramasi yanlis pozitif uretiyordu ("cap"
    kelimesi baska kelimelerin icinde esleşiyordu). Tek
    kelimeli anahtarlar icin kume uyeligi, cok kelimeli
    anahtarlar icin alt dize aramasi kullaniyoruz.
    """

    return set(re.split(r"[\s\-/]+", text)) if text else set()


def _matches(keyword: str, text: str, tokens) -> bool:

    if " " in keyword:
        return keyword in text

    return keyword in tokens


def detect_colors(text: str):
    """Metinde gecen renk ailelerini dondurur."""

    tokens = text_tokens(text)

    return [
        family
        for family, words in _COLOR_WORDS.items()
        if any(_matches(word, text, tokens) for word in words)
    ]


# =========================================================
# TEMEL SKOR  (ARKETIP x URUN)
# =========================================================

def score_product_for_archetype(product, archetype: str):
    """
    0-98 arasi temel stil skoru ve gerekce uretir.

    Doner: (score, reasons, detail)

    Bilesenler:
        taban                       32
        anahtar kelime ortusmesi   0-38  (doygunluk egrisi)
        renk uyumu                 0-12
        fiyat araligi uyumu        0-10
        urun kalitesi (rating)     0-6
        negatif kelime cezasi    -28-0

    Teorik tavan 100 ama butun bilesenlerin ayni anda tam
    olmasi gerekir; pratikte ~90'da kalir. 100 bilincli
    olarak ULASILMAZ: hicbir icerik modeli durustce
    "%100 uyum" diyemez.
    """

    if archetype not in _POSITIVE:
        archetype = MINIMALIST

    text = product_text(product)
    tokens = text_tokens(text)

    reasons = []
    detail = {}

    # ---- 1. Anahtar kelime ortusmesi ----

    positive_hits = []
    positive_raw = 0

    for word, weight in _POSITIVE[archetype].items():
        if _matches(word, text, tokens):
            positive_raw += weight
            positive_hits.append(word)

    # Doygunluk egrisi. Lineer birakilsa uzun basliklar
    # sirf uzunlugundan yuksek skor alirdi.
    keyword_score = 38.0 * (1.0 - math.exp(-positive_raw / 12.0))

    detail["keyword_raw"] = positive_raw
    detail["keyword_hits"] = positive_hits[:6]

    # ---- 2. Negatif kelime cezasi ----

    negative_raw = 0
    negative_hits = []

    for word, weight in _NEGATIVE[archetype].items():
        if _matches(word, text, tokens):
            negative_raw += weight
            negative_hits.append(word)

    penalty = min(28.0, negative_raw * 2.4)

    detail["negative_raw"] = negative_raw
    detail["negative_hits"] = negative_hits[:6]

    # ---- 3. Renk uyumu ----

    colors = detect_colors(text)
    preferred = _ARCHETYPE_COLORS[archetype]

    matched_colors = [c for c in colors if c in preferred]

    raw_color_score = 12.0 if matched_colors else (
        3.0 if not colors else 0.0
    )

    # RENK BIR NITELEYICIDIR, BIRINCIL SINYAL DEGIL.
    #
    # Kalibrasyonda siyah bir cocuk atleti "Goth" arketipinde
    # 85.6 aldi: sadece "siyah" kelimesi yuzunden. Bir urunun
    # rengi arketibin paletine uyuyor olmasi, o urunun o tarza
    # ait oldugunu GOSTERMEZ. Once bicim/doku kaniti gerekir.
    #
    # Bu yuzden renk puanini anahtar kelime kanitiyla
    # olcekliyoruz: hic kelime esleşmesi yoksa renk 0 puan,
    # 6+ ham kelime agirliginda tam puan.

    color_evidence = min(1.0, positive_raw / 6.0)

    color_score = raw_color_score * color_evidence

    detail["colors"] = colors
    detail["matched_colors"] = matched_colors

    # ---- 4. Fiyat araligi ----

    price = getattr(product, "price", None)
    low, high = _PRICE_BANDS[archetype]

    if price is None:
        price_score = 3.0
    elif low <= price <= high:
        price_score = 10.0
    else:
        distance = low - price if price < low else price - high
        span = max(high - low, 1.0)
        price_score = max(0.0, 10.0 - 10.0 * (distance / span))

    # ---- 5. Urun kalitesi ----

    rating = getattr(product, "rating", None) or 0
    rating_count = getattr(product, "rating_count", None) or 0

    # Az yorumlu yuksek puan guvenilmez: log ile agirlikla
    confidence = min(1.0, math.log10(rating_count + 1) / 3.0)
    quality_score = 6.0 * (max(0.0, rating - 3.0) / 2.0) * confidence

    # ---- Toplam ----

    raw = (
        32.0
        + keyword_score
        + color_score
        + price_score
        + quality_score
        - penalty
    )

    score = max(0.0, min(98.0, raw))

    # ---- Gerekceler ----

    if matched_colors:
        reasons.append(f"color:{matched_colors[0]}")

    if positive_hits:
        reasons.append(f"style:{archetype}")

    if price is not None and low <= price <= high:
        reasons.append("price:band")

    if rating >= 4.3 and rating_count >= 50:
        reasons.append("quality:high")

    detail["components"] = {
        "base": 32.0,
        "keyword": round(keyword_score, 2),
        "color": round(color_score, 2),
        "price": round(price_score, 2),
        "quality": round(quality_score, 2),
        "penalty": round(-penalty, 2),
    }

    return round(score, 2), reasons, detail


# =========================================================
# HARMANLAMA  (COK SECIMLI TARZ)
# =========================================================

# Ayni urun ikinci bir secili tarza da uyuyorsa aldigi ek
# puan. "Cok yonlu parca" odulu; kucuk tutuluyor cunku asil
# karar en iyi eslesme.
VERSATILITY_BONUS_MAX = 5.0


def blend_scores(scores_by_archetype, selected_styles):
    """
    Kullanicinin sectigi 1-3 tarzin skorlarini birlestirir.

    scores_by_archetype: {archetype: (score, reasons)}
    selected_styles:     ["streetwear", "y2k"]

    Doner: (score, matched_style, reasons)

    Neden max, ortalama degil: kullanici tarzlari BIRLIKTE
    degil ALTERNATIF olarak sectiginden, bir hoodie'nin
    "Streetwear + Old Money" seciminde ortalamaya vurulup
    dusmesi yanlis olurdu. Hoodie mukemmel bir streetwear
    parcasidir; kullanici onu gormek istiyor.

    Ikinci en iyi skor da yuksekse kucuk bir bonus veriyoruz:
    iki tarza da uyan parca gercekten daha degerli.
    """

    candidates = [
        (scores_by_archetype[style][0], style)
        for style in selected_styles
        if style in scores_by_archetype
    ]

    if not candidates:
        return 0.0, None, []

    candidates.sort(key=lambda row: -row[0])

    best_score, best_style = candidates[0]

    bonus = 0.0

    if len(candidates) > 1:
        second_score = candidates[1][0]

        if second_score >= REASON_CHIP_THRESHOLD:
            ratio = second_score / max(best_score, 1.0)
            bonus = VERSATILITY_BONUS_MAX * min(1.0, ratio)

    reasons = list(scores_by_archetype[best_style][1])

    if bonus > 0:
        reasons.append("style:versatile")

    return (
        round(min(98.0, best_score + bonus), 2),
        best_style,
        reasons,
    )


# =========================================================
# KISISELLESTIRME  (YENIDEN SIRALAMA)
# =========================================================

def _leaf_category(category) -> str:
    """
    "... › Men › Clothing › Shirts › Polos" -> "polos"
    """

    if not category:
        return ""

    parts = [p.strip() for p in str(category).split("›")]

    return normalize(parts[-1]) if parts else ""


def build_taste_profile(liked_products, disliked_products=None):
    """
    Begenilen urunlerden zevk profili cikarir.

    liked_products: en yeniden en eskiye sirali.
    Yeni begeniler daha agir sayilir (recency weighting):
    zevk zamanla degisir, alti ay onceki begeni bugunkuyle
    ayni agirlikta olmamali.
    """

    brands = {}
    categories = {}
    colors = {}
    prices = []

    for index, product in enumerate(liked_products):

        weight = 0.9 ** index

        brand = normalize(getattr(product, "brand", ""))
        if brand:
            brands[brand] = brands.get(brand, 0.0) + weight

        leaf = _leaf_category(getattr(product, "category", ""))
        if leaf:
            categories[leaf] = categories.get(leaf, 0.0) + weight

        for color in detect_colors(product_text(product)):
            colors[color] = colors.get(color, 0.0) + weight

        price = getattr(product, "price", None)
        if price:
            prices.append(float(price))

    avoid_brands = {}
    avoid_categories = {}

    for product in (disliked_products or []):

        brand = normalize(getattr(product, "brand", ""))
        if brand:
            avoid_brands[brand] = avoid_brands.get(brand, 0.0) + 1.0

        leaf = _leaf_category(getattr(product, "category", ""))
        if leaf:
            avoid_categories[leaf] = (
                avoid_categories.get(leaf, 0.0) + 1.0
            )

    prices.sort()

    return {
        "brands": brands,
        "categories": categories,
        "colors": colors,
        "avoid_brands": avoid_brands,
        "avoid_categories": avoid_categories,
        "median_price": prices[len(prices) // 2] if prices else None,
        "liked_count": len(liked_products),
    }


def personalize_score(base_score, reasons, product, taste):
    """
    Temel skoru kullanici gecmisine gore guncelller.

    Bu fonksiyon "kalp bastigin urunlere benzerler
    onceliklenir" vaadini gercek yapan yerdir.
    """

    if not taste or not taste.get("liked_count"):
        return base_score, reasons, {}

    reasons = list(reasons)
    boost = 0.0
    detail = {}

    brand = normalize(getattr(product, "brand", ""))
    leaf = _leaf_category(getattr(product, "category", ""))
    colors = detect_colors(product_text(product))

    # ---- Marka yakinligi ----

    brand_weight = taste["brands"].get(brand, 0.0)

    if brand_weight > 0:
        brand_boost = min(9.0, 5.0 * math.sqrt(brand_weight))
        boost += brand_boost
        detail["brand"] = round(brand_boost, 2)
        reasons.insert(0, "history:brand")

    # ---- Kategori yakinligi ----

    category_weight = taste["categories"].get(leaf, 0.0)

    if category_weight > 0:
        category_boost = min(8.0, 4.5 * math.sqrt(category_weight))
        boost += category_boost
        detail["category"] = round(category_boost, 2)

        if "history:brand" not in reasons:
            reasons.insert(0, "history:category")

    # ---- Renk yakinligi ----

    color_weight = 0.0
    matched_history_color = None

    for color in colors:
        weight = taste["colors"].get(color, 0.0)
        if weight > color_weight:
            color_weight = weight
            matched_history_color = color

    if color_weight > 0:
        color_boost = min(5.0, 3.0 * math.sqrt(color_weight))
        boost += color_boost
        detail["color"] = round(color_boost, 2)

        reasons.append(f"history_color:{matched_history_color}")

        if not any(r.startswith("history:") for r in reasons):
            reasons.insert(0, "history:color")

    # ---- Fiyat yakinligi ----

    price = getattr(product, "price", None)
    median = taste.get("median_price")

    if price and median and abs(price - median) <= median * 0.45:
        boost += 4.0
        detail["price"] = 4.0

    # ---- Begenilmeyen marka / kategori cezasi ----

    if taste["avoid_brands"].get(brand, 0.0) >= 2:
        boost -= 6.0
        detail["avoid_brand"] = -6.0

    if taste["avoid_categories"].get(leaf, 0.0) >= 2:
        boost -= 8.0
        detail["avoid_category"] = -8.0

    return (
        round(max(0.0, min(100.0, base_score + boost)), 2),
        reasons,
        detail,
    )


# =========================================================
# GEREKCE CUMLESI
# =========================================================

_COLOR_DISPLAY = {
    "siyah": "Siyah", "beyaz": "Beyaz", "gri": "Gri",
    "bej": "Bej", "lacivert": "Lacivert", "krem": "Krem",
    "kahve": "Kahve", "bordo": "Bordo", "yeşil": "Yeşil",
    "mavi": "Mavi", "kırmızı": "Kırmızı", "turuncu": "Turuncu",
    "mor": "Mor", "pembe": "Pembe", "sarı": "Sarı",
}


def style_label(archetype):
    """Kart uzerinde kullanilacak kisa tarz adi."""

    profile = ARCHETYPE_PROFILES.get(archetype)

    return profile["short_label"] if profile else None


def build_reason_sentence(
    reasons,
    matched_style,
    product=None,
    is_exploration=False,
):
    """
    Karta basilacak AI aciklamasini kurar.

    Ornek cikti:
      "Seçtiğin 'Streetwear' tarzı ve en çok beğendiğin
       'Siyah' tonuna göre önerildi."

    Kural: yalnizca GERCEKTEN tetiklenmis sinyaller cumleye
    girer. Uydurma gerekce yazmak, yanlis yuzde yazmaktan
    daha kotudur — kullanici bir kez yakalarsa butun sisteme
    guvenmeyi birakir.
    """

    if is_exploration:
        return (
            "Tarzının dışından bir deneme. "
            "Beğenmezsen akıştan eleyebilirsin."
        )

    style = style_label(matched_style)

    history_color = next(
        (
            _COLOR_DISPLAY.get(r.split(":", 1)[1])
            for r in reasons
            if r.startswith("history_color:")
        ),
        None,
    )

    product_color = next(
        (
            _COLOR_DISPLAY.get(r.split(":", 1)[1])
            for r in reasons
            if r.startswith("color:")
        ),
        None,
    )

    brand = (getattr(product, "brand", None) or "").strip()

    has_brand_history = "history:brand" in reasons
    has_category_history = "history:category" in reasons
    versatile = "style:versatile" in reasons

    # En spesifik sinyalden baslayarak

    if has_brand_history and brand and style:
        return (
            f"Sık beğendiğin {brand} ve seçtiğin "
            f"'{style}' tarzına göre önerildi."
        )

    if has_brand_history and brand:
        return f"Sık beğendiğin {brand} parçalarından."

    if history_color and style:
        return (
            f"Seçtiğin '{style}' tarzı ve en çok beğendiğin "
            f"'{history_color}' tonuna göre önerildi."
        )

    if has_category_history and style:
        return f"Beğendiklerine benzer bir '{style}' parçası."

    if versatile and style:
        return (
            f"Seçtiğin birden fazla tarza uyuyor, "
            f"özellikle '{style}'."
        )

    if product_color and style:
        return (
            f"'{style}' tarzının {product_color} paletine "
            f"uyduğu için önerildi."
        )

    if style:
        return f"'{style}' tarzının tipik parçalarından."

    return None


def build_match_display(
    score,
    reasons,
    matched_style=None,
    product=None,
    is_exploration=False,
):
    """
    Skor ve gerekceleri karta basilacak alanlara cevirir.

    Doner:
        {
          "match_score":   86.7,
          "match_label":   "%87 AI Stil Uyumu" | None,
          "reason_label":  "Seçtiğin 'Streetwear' ..." | None,
          "matched_style": "streetwear" | None
        }

    Frontend hicbir esik hesabi YAPMAZ, geleni basar.
    Esikler tek yerde (burada) durur; iki yerde tutmak
    gun gelip birinin guncellenmemesi demektir.
    """

    sentence = build_reason_sentence(
        reasons,
        matched_style,
        product=product,
        is_exploration=is_exploration,
    )

    if score is not None and score >= MATCH_BADGE_THRESHOLD:
        return {
            "match_score": score,
            "match_label": f"%{int(round(score))} AI Stil Eşleşmesi",
            "reason_label": sentence,
            "matched_style": matched_style,
        }

    if (
        score is not None
        and score >= REASON_CHIP_THRESHOLD
        and sentence
    ):
        return {
            "match_score": score,
            "match_label": None,
            "reason_label": sentence,
            "matched_style": matched_style,
        }

    return {
        "match_score": score,
        "match_label": None,
        "reason_label": sentence if is_exploration else None,
        "matched_style": matched_style,
    }


# =========================================================
# DOGRULAMA
# =========================================================

def normalize_selected_styles(styles):
    """
    Gelen tarz listesini temizler.

    - bilinmeyen degerleri atar
    - tekrarlari kaldirir (sirayi korur)
    - en fazla MAX_SELECTED_STYLES tane birakir

    Bos liste donerse cagiran taraf hata vermelidir.
    """

    if not styles:
        return []

    seen = set()
    cleaned = []

    for style in styles:
        if style in ARCHETYPES and style not in seen:
            seen.add(style)
            cleaned.append(style)

    return cleaned[:MAX_SELECTED_STYLES]
