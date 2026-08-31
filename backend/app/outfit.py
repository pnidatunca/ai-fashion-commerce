"""
TEK PARCADAN KOMBIN KURAR.

PROBLEM
Sohbette kombin kurmak kullanicinin isiydi: asistan duz bir
urun listesi donduruyordu, kullanici kartlardan ikisini elle
isaretliyor, sonra bir pencere adini soruyordu. Ama asistan
"siyah tisort" arandiginda TISORT donduruyor — listedeki iki
karti isaretleyen kullanici iki tisortten olusan bir "kombin"
kaydediyordu. Akis calisiyordu, ise yaramıyordu.

COZUM
Kullanici bir parca seciyor, sistem EKSIK YUVALARI kendisi
dolduruyor: tisort secildiyse pantolon + ayakkabi arıyor,
pantolon secildiyse ust + ayakkabi. Kullaniciya "kombin
olarak ekleyelim mi?" diye sorulacak somut bir oneri cikiyor.

NEDEN LLM DEGIL
Bu uc modelden gecmiyor. Uc sebep:

  1. HIZ. Kullanici karta bastigi anda oneri gorunmeli.
     Gemini turu iyi gunde 4-5 saniye.
  2. KOTA. Ucretsiz katman dakikada 5 istek veriyor ve her
     sohbet turu 2 harciyor. "Karta bas -> oneri" akisi
     kotayi tek basina tuketirdi.
  3. BELIRLILIK. Yuva mantigi (tisort -> pantolon + ayakkabi)
     ve renk uyumu kural tablosu. Modelin bunu her seferinde
     ayni sekilde yapmasi garanti degil; tablonun yapmasi
     garanti.

Arama motoru YENIDEN YAZILMIYOR: her yuva icin normal zincir
calisiyor — query_engine.analyze() -> embed_query() ->
search_service.search(). Yani kombin parcalari da sitenin
geri kalaniyla ayni siralamadan geciyor.
"""

import logging

from sqlalchemy.orm import Session

from app import color_match, currency, query_engine, search_service
from app.models import Product

logger = logging.getLogger(__name__)


# =========================================================
# YUVALAR
# =========================================================
#
# Urun kategorisinden kombin yuvasi tahmini.
#
# Kullanici parcalari elle isaretlemiyor; yuvayi burada
# tahmin ediyoruz ki hem "bu kombindeki AYAKKABIYI degistir"
# akisi hem de buradaki tamamlama mantigi calisabilsin.
#
# Desenler search_service._CATEGORY_PATTERNS ile AYNI
# kaynaktan gelmeli; oradaki liste degisirse buraya da
# bakilmali.
SLOT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ayakkabi", ("› Shoes",)),
    ("dis_giyim", ("› Jackets & Coats", "Outerwear")),
    ("alt", ("› Pants", "› Jeans", "› Shorts", "› Skirts")),
    ("ust", ("› Shirts", "› Polos", "› Tops", "› T-Shirts", "› Dresses")),
    ("aksesuar", ("› Accessories", "› Watches", "› Jewelry", "› Bags")),
)


SLOT_LABELS: dict[str, str] = {
    "ust": "Üst",
    "alt": "Alt",
    "dis_giyim": "Dış giyim",
    "ayakkabi": "Ayakkabı",
    "aksesuar": "Aksesuar",
    "diger": "Diğer",
}


def guess_slot(product) -> str | None:
    """Urun kategorisinden kombin yuvasi. Bilinmiyorsa None."""

    category = (getattr(product, "category", None) or "").lower()

    for slot, patterns in SLOT_PATTERNS:
        for pattern in patterns:
            if pattern.lower() in category:
                return slot

    return None


def is_dress(product) -> bool:
    """
    Elbise mi?

    Ayri sorulmasi gerekiyor cunku elbise kategori yolunda
    "ust" yuvasina dusuyor ama ALT PARCA ISTEMIYOR. Elbiseye
    pantolon onermek, akisin en gorunur hatasi olurdu.
    """

    return "› dresses" in (
        getattr(product, "category", None) or ""
    ).lower()


def gender_of(product) -> str | None:
    """
    Kategori yolundan cinsiyet.

    products tablosunda cinsiyet kolonu YOK; bilgi kategori
    yolunda duruyor ("... › Men › Clothing › ..."). Arama da
    ayni yerden okuyor (search_service._GENDER_PATTERNS).
    """

    category = (getattr(product, "category", None) or "").lower()

    if "› women ›" in category:
        return "women"

    if "› men ›" in category:
        return "men"

    return None


# Hangi parcadan sonra hangi yuvalar aranir — SIRAYLA.
#
# Ilk iki yuva kombinin govdesi; ucuncusu (dis giyim) varsa
# guzel, yoksa kombin gecerli. Katalogda kadin dis giyim
# yok, o yuva kadin parcalarinda zaten bos donuyor.
COMPLEMENT_PLAN: dict[str, tuple[str, ...]] = {
    "ust": ("alt", "ayakkabi", "dis_giyim"),
    "elbise": ("ayakkabi", "dis_giyim"),
    "alt": ("ust", "ayakkabi", "dis_giyim"),
    "ayakkabi": ("ust", "alt"),
    "dis_giyim": ("ust", "alt", "ayakkabi"),
    "aksesuar": ("ust", "alt", "ayakkabi"),
}


# Yuva -> aramada kullanilacak giysi kelimesi.
#
# Kelimeler query_engine.CATEGORY_TERMS'de TETIKLEYICI olmak
# zorunda; yoksa intent.category bos kalir ve arama yuvayi
# degil rastgele bir kategoriyi getirir. Ust yuvasi cinsiyete
# gore ayriliyor: katalogdaki kadin ustleri agirlikla bluz,
# erkek ustleri tisort/polo.
SLOT_QUERY_WORD: dict[str, dict[str, str]] = {
    "ust": {"women": "bluz", "men": "tişört", "": "tişört"},
    "alt": {"women": "pantolon", "men": "pantolon", "": "pantolon"},
    "ayakkabi": {"women": "ayakkabı", "men": "ayakkabı", "": "ayakkabı"},
    "dis_giyim": {"women": "ceket", "men": "ceket", "": "ceket"},
}


# Aksesuar yuvasi ONERILMIYOR: katalogda karsiligi olan bir
# kategori deseni yok (search_service._CATEGORY_PATTERNS'de
# aksesuar girdisi bulunmuyor), yani "aksesuar" aramasi
# rastgele urun getirir. Plan tablosunda tohum olarak
# duruyor, hedef olarak degil.
SUGGESTABLE_SLOTS = ("ust", "alt", "ayakkabi", "dis_giyim")


_GENDER_WORD = {"women": "kadın", "men": "erkek"}


# =========================================================
# RENK UYUMU
# =========================================================
#
# Aile -> tercih sirasiyla eslesecek renkler.
#
# Iki kural:
#
#   NOTRLER (siyah, beyaz, gri, bej, kahve) birbiriyle ve her
#   seyle gider; aralarindan kontrast olani seciyoruz.
#
#   DOYGUN renkler (kirmizi, yesil, sari, turuncu, pembe,
#   mor) notrle dengelenir. Kirmiziya yesil onermek teknik
#   olarak "tamamlayici renk" ama giyimde kimsenin istedigi
#   sey degil.
#
# Anahtarlar products.color_family degerleri (script 15'in
# color_family() siniflandirmasi uretiyor), degerler
# color_match paletindeki adlar — yani query_engine'in
# COLOR_TERMS tetikleyicileri.
_HARMONY: dict[str, tuple[str, ...]] = {
    "siyah": ("beyaz", "gri", "lacivert", "bej"),
    "beyaz": ("lacivert", "siyah", "bej", "mavi"),
    "gri": ("siyah", "beyaz", "lacivert"),
    "acik_gri": ("lacivert", "siyah", "beyaz"),
    "bej": ("beyaz", "lacivert", "kahve", "siyah"),
    "kahve": ("bej", "krem", "lacivert", "beyaz"),
    "mavi": ("beyaz", "bej", "siyah", "gri"),
    "kirmizi": ("siyah", "beyaz", "lacivert", "bej"),
    "yesil": ("bej", "beyaz", "siyah", "kahve"),
    "sari": ("lacivert", "beyaz", "gri", "siyah"),
    "turuncu": ("lacivert", "beyaz", "bej", "siyah"),
    "pembe": ("beyaz", "gri", "lacivert", "siyah"),
    "mor": ("gri", "beyaz", "siyah", "bej"),
}


# Tohumun rengi bilinmiyorsa dusulen sira. Notr ve
# katalogda bol: siyah 217, beyaz 85, mavi 131 urun.
_HARMONY_FALLBACK = ("siyah", "beyaz", "lacivert", "bej")


# Yuvaya gore renk egilimi.
#
# Uyum listesinden secim yaparken bu listeyi kesistiriyoruz:
# altta lacivert/denim, ayakkabida siyah/beyaz giyimde
# "kasitli" duruyor. Kesisim bossa uyum listesinin ilki
# kullaniliyor — yuva egilimi bir TERCIH, kural degil.
_SLOT_COLOR_BIAS: dict[str, tuple[str, ...]] = {
    "alt": ("lacivert", "siyah", "bej", "gri"),
    "ayakkabi": ("siyah", "beyaz", "kahve"),
    "ust": ("beyaz", "siyah", "gri", "krem"),
    "dis_giyim": ("siyah", "lacivert", "bej", "gri"),
}


def companion_color(family: str | None, slot: str) -> str:
    """
    Tohumun rengiyle uyumlu, yuvaya yakisan renk adi.

    Donen deger bir PALET ADI ("lacivert"), aile adi degil:
    dogrudan arama sorgusuna yaziliyor ve query_engine onu
    COLOR_TERMS uzerinden tanıyor.
    """

    options = _HARMONY.get(
        (family or "").strip().lower(),
        _HARMONY_FALLBACK,
    )

    bias = _SLOT_COLOR_BIAS.get(slot, ())

    for name in bias:
        if name in options:
            return name

    return options[0]


def _color_label(name: str) -> str:
    """Palet adinin kullaniciya gosterilecek hali."""

    target = color_match.resolve(name)

    return target.label if target else name


# =========================================================
# ARAMA
# =========================================================

# Bir yuva icin kac secenek donuyor.
#
# Ilk secenek "secili" geliyor, gerisi kullanicinin tek
# dokunusla degistirebilecegi alternatifler. Dort yeterli:
# daha fazlasi sohbet balonunu listeye cevirir.
OPTIONS_PER_SLOT = 4

# Yuva basina istenen ham sonuc. Secenek sayisindan yuksek
# cunku tohumun kendisi ve daha once secilen parcalar
# ayiklaniyor.
_FETCH_PER_SLOT = 12


def _search_slot(
    db: Session,
    slot: str,
    color: str,
    gender: str | None,
    exclude: set[str],
    rate: float,
) -> tuple[list[dict], str]:
    """
    Bir yuvayi doldurur. Donen: (secenekler, kurulan sorgu).

    CINSIYET GEVSETMESI: sorgu once cinsiyetle kuruluyor
    ("kadın lacivert pantolon"). Katalogda o kesisim ince
    olabiliyor — kadin pantolonu 21 urun — ve sonuc bos
    donerse cinsiyet dusuruluyor. Bos bir yuva gostermek,
    cinsiyeti tam tutturmaktan daha kotu.

    SONUCLAR YUVAYA GORE DOGRULANIYOR — bu satirlar sussuz
    degil, olculdu: kadin bir bluzden kombin kurulurken
    "dis giyim" yuvasina BLUZ, kadin bir elbisede JEAN
    geliyordu. Sebep, search_service'in asama merdiveni:
    kategori filtresi sonuc vermezse GEVSETIYOR ve alakasiz
    ama "benzer" urunler donuyor. Katalogda kadin dis giyimi
    hic yok (0 urun), yani o yuva her kadin kombininde
    yanlis doluyordu.

    Arama motoru icin bu davranis dogru — bos sonuc sayfasi
    gostermektense yakin bir sey gostermek iyidir. Kombin
    icin YANLIS: "dis giyim" diye bluz onerirsen oneri
    guvenilirligini kaybediyor. Bu yuzden yuvasi
    tutmayanlar burada ayiklaniyor ve yuva bos kaliyor.
    """

    word = SLOT_QUERY_WORD[slot].get(gender or "", "")

    if not word:
        return [], ""

    attempts = []

    if gender:
        attempts.append(f"{_GENDER_WORD[gender]} {color} {word}")

    attempts.append(f"{color} {word}")

    for query in attempts:

        intent = query_engine.analyze(query)

        # Zincirin geri kalani /api/search ile ayni: ham
        # sorgu degil, zenginlestirilmis metin vektorlenir.
        vector = embed_slot_query(intent.embed_text)

        items, _meta = search_service.search(
            db=db,
            intent=intent,
            query_embedding=vector,
            limit=_FETCH_PER_SLOT,
            offset=0,
            usd_try_rate=rate,
        )

        options = []

        for entry in items:

            product = entry["product"]

            if product.product_id in exclude:
                continue

            # YUVA SARTI. Elbise ozel durum: "ust" yuvasi
            # arandiginda elbise gelmemeli — kombin zaten
            # bir alt parca da tasiyor.
            if guess_slot(product) != slot:
                continue

            if slot == "ust" and is_dress(product):
                continue

            # CINSIYET SARTI, gevsek: tohumun cinsiyeti ya da
            # belirsiz (unisex urunlerin kategori yolunda
            # "Men"/"Women" gecmiyor). Ters cinsiyet
            # ELENIYOR — kadin kombinine erkek pantolonu
            # koymak, o yuvayi bos birakmaktan kotu.
            if gender:

                other = gender_of(product)

                if other is not None and other != gender:
                    continue

            options.append(
                {
                    "product": product,
                    "similarity_score": entry["similarity_score"],
                }
            )

            if len(options) >= OPTIONS_PER_SLOT:
                break

        if options:
            return options, query

    return [], attempts[-1]


def embed_slot_query(text: str):
    """
    Yuva sorgusunun vektoru.

    Ayri fonksiyon cunku app.embeddings importu MODUL
    SEVIYESINDE yapilamiyor: embeddings, cagrildiginda
    Gemini anahtarini bekliyor ve outfit modulunu import
    eden testlerin anahtara ihtiyaci olmamali. Ic import
    ayni zamanda dairesel bagimliligi da kesiyor.
    """

    from app.embeddings import embed_query

    return embed_query(text)


# =========================================================
# KOMBIN
# =========================================================

def _seed_kind(product) -> str:
    """
    Tamamlama planinin anahtari.

    guess_slot() yeterli degil: elbise "ust" yuvasina
    dusuyor ama alt parca istemiyor (bkz. is_dress).
    """

    if is_dress(product):
        return "elbise"

    return guess_slot(product) or "ust"


def _brand_label(brand: str | None) -> str | None:
    """
    Marka adinin gosterilebilir hali.

    KATALOG VERISI KIRLI — sayildi: 728 markali urunun
    649'u " Store" ile bitiyor ("Skechers Store"), 78'i
    "Brand: " ile basliyor ("Brand: Nike"). Kombin adina
    oldugu gibi yazilinca "Brand: Kinglaman kombini" gibi
    bir baslik cikiyordu.

    Temizlik BURADA, dar kapsamda: ayni kirlilik urun
    kartlarinda da gorunuyor ama orayi duzeltmek bu isin
    parcasi degil. Duzeltilirse ortak bir yardimciya
    tasinmali.
    """

    name = (brand or "").strip()

    if not name:
        return None

    if name.lower().startswith("brand:"):
        name = name[len("brand:"):].strip()

    if name.lower().endswith(" store"):
        name = name[: -len(" store")].strip()

    return name or None


def _title(seed, slots) -> str:
    """
    Kombin icin ad onerisi.

    Kullaniciya pencere acip ad SORULMUYOR — akisin en can
    sikici adimi oydu. Ad burada uretiliyor, kullanici
    isterse gardiroptan yeniden adlandirabiliyor.
    """

    parts = [
        SLOT_LABELS.get(entry["slot"], entry["slot"])
        for entry in slots
    ]

    seed_word = "Kombin"

    if is_dress(seed):
        seed_word = "Elbise kombini"

    else:

        brand = _brand_label(seed.brand)

        if brand:
            seed_word = f"{brand} kombini"

    if not parts:
        return seed_word

    return f"{seed_word} ({len(parts) + 1} parça)"


def _reason(seed_family: str | None, slots) -> str:
    """
    "Neden bunlar?" sorusunun cevabi.

    Kullaniciya gosteriliyor: oneri bir kara kutu olmasin.
    """

    if not slots:
        return "Bu parçaya uygun tamamlayıcı bulunamadı."

    colors = []

    for entry in slots:

        label = entry.get("color_label")

        if label and label not in colors:
            colors.append(label)

    seed_label = _color_label(seed_family) if seed_family else None

    pieces = ", ".join(
        SLOT_LABELS.get(entry["slot"], entry["slot"]).lower()
        for entry in slots
    )

    if seed_label and colors:
        return (
            f"{seed_label} parçaya {', '.join(colors[:2]).lower()} "
            f"tonlarda {pieces} seçtim."
        )

    return f"Bu parçaya {pieces} seçtim."


def build(
    db: Session,
    seed: Product,
    rate: float | None = None,
    max_slots: int = 3,
) -> dict:
    """
    Tohum urunden bir kombin onerisi kurar.

    Donen sozluk:

        seed         tohum urun (ORM)
        seed_slot    tohumun yuvasi
        seed_color   olculmus renk ailesi ("siyah") | None
        title        onerilen kombin adi
        reason       onerinin gerekcesi (kullaniciya gosterilir)
        slots        [{slot, label, color, color_label,
                       query, options: [{product, score}]}]

    ORM nesnesi donuyor; cagiran taraf serilestiriyor. Bu uc
    sohbetin aksine transaction'i acik tutmuyor: arada LLM
    cagrisi yok, istek milisaniyeler icinde bitiyor.
    """

    if rate is None:
        rate = currency.get_usd_try_rate()

    kind = _seed_kind(seed)
    gender = gender_of(seed)

    # Tohumun olculmus rengi. Renk verisi yoksa (ya da
    # olcum guvenilmezse) uyum tablosu yedege dusuyor —
    # oneri yine cikiyor, sadece renk gerekcesi olmadan.
    measured = color_match.fetch_colors(db, [seed.product_id])

    entry = measured.get(str(seed.product_id)) or {}

    seed_family = entry.get("family") if entry.get("trusted") else None

    # Tohumun kendisi bir daha onerilmemeli; yuvalar
    # arasinda da tekrar olmamali (ayni urun hem ust hem
    # dis giyim seceneginde cikabiliyor).
    exclude = {seed.product_id}

    slots = []

    for slot in COMPLEMENT_PLAN.get(kind, ()):

        if slot not in SUGGESTABLE_SLOTS:
            continue

        if len(slots) >= max_slots:
            break

        color = companion_color(seed_family, slot)

        options, query = _search_slot(
            db=db,
            slot=slot,
            color=color,
            gender=gender,
            exclude=exclude,
            rate=rate,
        )

        if not options:
            # Katalogda o yuva bos (orn. kadin dis giyim).
            # Sessizce atlaniyor: kullaniciya bos bir raf
            # gostermenin faydasi yok.
            logger.info(
                "Kombin yuvasi bos: %s (%s) — sorgu: %s",
                slot,
                seed.product_id,
                query,
            )
            continue

        for option in options:
            exclude.add(option["product"].product_id)

        slots.append(
            {
                "slot": slot,
                "label": SLOT_LABELS.get(slot, slot),
                "color": color,
                "color_label": _color_label(color),
                "query": query,
                "options": options,
            }
        )

    return {
        "seed": seed,
        "seed_slot": guess_slot(seed),
        "seed_color": seed_family,
        "title": _title(seed, slots),
        "reason": _reason(seed_family, slots),
        "slots": slots,
        "rate": rate,
    }
