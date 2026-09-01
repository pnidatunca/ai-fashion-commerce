"""
AKILLI ARAMA — sorgu katmani (hibrit siralama + gevsetme)

query_engine.py sorguyu ANLAR, bu dosya onu VERITABANINDA
calistirir.

HIBRIT SIRALAMA
---------------
Saf vektor aramasi tek basina yetmiyor. Olculen problem:

    "kadin yazlik elbise" sorgusunda vektor, basliginda
    "yazlık" yazan urunu illa one almiyor. Anlamsal olarak
    yakin bulduklari arasinda kalin kislik elbiseler de
    cikiyor cunku "elbise" benzerligi "yazlik" farkini
    bastiriyor.

Bu yuzden skor iki kaynaktan geliyor:

    skor = 100 * (1 - cosine_distance)        anlamsal yakinlik
         + facet bonuslari                    kelime eslesmesi
         + tam ifade bonusu
         + kucuk kalite bonusu

Vektor ANLAMI getiriyor, kelime eslesmesi KESINLIGI
getiriyor. Ikisi ayni skorda birlesiyor.


KELIME ESLESMESINDE ALAN AGIRLIGI
---------------------------------
style_engine.py'de ogrenilen ders: `features` ve
`description` alanlari pazarlama metni tasiyor ve skoru
kirletiyor ("sneakers ile kombinleyin" yazan bir kot
streetwear sanilmisti).

Ama aramada bu alanlari tamamen atmak da yanlis: katalogda
"keten" 9 urunde gecerken 7'si baslikta, "polyester" 169
urunde gecerken yalnizca 2'si baslikta. Kumas bilgisi cogu
zaman aciklamada.

Cozum: baslik + kategori TAM bonus, aciklama + ozellikler
YARIM bonus. Guclu kanit ile zayif kanit ayni agirlikta
sayilmiyor.


GEVSETME MERDIVENI
------------------
Kullanicinin istedigi "birebir sonuc cikmazsa alternatif
terimlerle ara" davranisi. Sirali olarak en kirilgan filtre
birakiliyor:

    0. cinsiyet + kategori + renk + desen
    1. desen zorunlulugu birakilir  (bonusa doner)
    2. renk zorunlulugu birakilir   (bonusa doner)
    3. kategori birakilir
    4. yalnizca vektor + bonuslar

Her asamada NEYIN gevsetildigi kaydediliyor ve kullaniciya
soyleniyor. Sessizce filtre dusurmek, kullanicinin "ben
kirmizi istemistim" demesine yol acar.

SAYFALAMA TUTARLILIGI: merdiven sonuc SAYISINA gore karar
veriyor, bu yuzden sayfa 2'de yeniden calistirilirsa farkli
bir asamada durabilir ve urunler tekrar eder. feed.py'deki
cursor dersinin aynisi. Cozum: cozulen asama cevapta
donuyor, sonraki sayfa onu `stage` olarak geri gonderiyor.
"""

from __future__ import annotations

import re

from sqlalchemy import Float, case, func, literal, or_, select
from sqlalchemy.orm import Session

from . import color_match, currency
from .models import Product
from .query_engine import COLOR_TERMS, QueryIntent, fold


# =========================================================
# AYARLAR
# =========================================================

# Bir asamanin "yeterli" sayilmasi icin gereken sonuc sayisi.
#
# Neden 6: urun izgarasi bir satirda 4 kart gosteriyor.
# Tek satiri dolduramayan bir sonuc kumesi kullaniciya
# "arama calismadi" gibi geliyor, oysa filtre fazla dardir.
MIN_RESULTS = 6


# ONEMLI AYRIM: CIKARSANAN vs ACIKCA YAZILAN KISIT
# ------------------------------------------------
# Her filtreyi ayni kolaylikta birakmak yanlis. "siyah
# elbise" arayan biri 3 tane siyah elbise gormeyi, 3 siyah +
# 3 rastgele renk gormeye tercih eder.
#
# crud.py'de bu karar daha once alinmisti ve yorumu duruyor:
#
#     "Kullanici bir renk belirttiginde SADECE o renk gelmeli.
#      Yumusak siralama denenmisti ama 'beyaz gomlek' arayip
#      mavi/siyah urunlerin de listede cikmasina yol acti."
#
# Bu yuzden esik filtrenin KAYNAGINA gore degisiyor:
#
#   CIKARSANAN kisit (desen niyeti — kullanici "renkli" yazdi,
#   "desenli" demedi) sonuc azsa birakilir.
#
#   ACIKCA YAZILAN kisit (renk, kategori, cinsiyet) yalnizca
#   SIFIR sonuc verirse birakilir. Kullanicinin kendi
#   kelimesini, sonuc sayisi az diye yok saymiyoruz.
#
# Anahtar: o asamadan CIKMAK icin gereken en az sonuc.
STAGE_MIN_RESULTS = {
    0: MIN_RESULTS,   # desen niyeti cikarsanmis -> azsa gevset
    1: 1,             # renk acikca yazildi       -> sifirsa gevset
    2: 1,             # kategori acikca yazildi   -> sifirsa gevset
    3: 1,             # cinsiyet acikca yazildi   -> sifirsa gevset
}

# Guclu alan eslesmesi (baslik + kategori) tam bonus alir,
# zayif alan (aciklama + ozellikler) bu carpanla alir.
WEAK_FIELD_FACTOR = 0.5

# Sorgunun tamaminin baslikta gecmesi
EXACT_PHRASE_BONUS = 6.0

# Rating kalitesi. Kucuk tutuluyor: arama alaka duzeyi
# icin var, populerlik sirasi icin degil.
MAX_QUALITY_BONUS = 3.0

# Renk sert filtre DEGILKEN verilen bonus
COLOR_SOFT_BONUS = 9.0


STAGE_LABELS = {
    0: "tam eşleşme",
    1: "desen filtresi gevşetildi",
    2: "renk filtresi gevşetildi",
    3: "kategori filtresi gevşetildi",
    4: "yalnızca anlamsal benzerlik",
}


# =========================================================
# ALAN GRUPLARI
# =========================================================

# Guclu kanit: urunun NE OLDUGUNU soyleyen alanlar
STRONG_FIELDS = (
    Product.title,
    Product.title_tr,
    Product.category,
)

# Zayif kanit: pazarlama metni
WEAK_FIELDS = (
    Product.description,
    Product.description_tr,
    Product.features,
    Product.features_tr,
)


# POSIX regex'te ozel anlam tasiyan karakterler
_REGEX_SPECIALS = ".^$*+?()[]{}|\\"


def _regex_escape(text: str) -> str:
    """
    POSIX regex icin kacisma.

    re.escape KULLANILMIYOR: Python'a ozgu kacismalar
    ("\\-" gibi) uretiyor ve Postgres bunlari ayni sekilde
    yorumlamiyor.
    """

    return "".join(
        "\\" + char if char in _REGEX_SPECIALS else char
        for char in text
    )


def _word_pattern(term: str) -> str:
    """
    Bir terim icin KELIME SINIRLI regex kalibi uretir.

    NEDEN ILIKE '%term%' DEGIL — olculdu:

        %mor%   174 urun  ("more", "memory", "armor")
        \\ymor\\y   0 urun
        %red%   292 urun  ("featured", "required", "colored")
        \\yred\\y  13 urun

    Yani alt dize aramasi kullanildiginda "mor" filtresi
    katalogun %24'une, "red" filtresi %40'ina esliyordu.
    Renk filtresi neredeyse hic filtrelemiyordu.

    Ayni hata sorgu tarafinda da vardi (query_engine
    docstring'i: "topuklu" -> "top"). Kalip ayni:

        4 harf ve uzeri  ->  \\yterim     (on-ek: Turkce ekleri
                                        tolere eder, "desenli"
                                        "desenlidir"i yakalar)
        3 harf ve kisa   ->  \\yterim\\y   (tam kelime: "mor"
                                        "more"a eslesmez)
    """

    folded_length = len(term)

    escaped = _regex_escape(term)

    if folded_length >= 4:
        return r"\y" + escaped

    return r"\y" + escaped + r"\y"


def _like_any(fields, terms: list[str]):
    """
    Verilen terimlerden herhangi biri verilen alanlardan
    herhangi birinde geciyor mu.

    Terimler HEM orijinal HEM katlanmis haliyle araniyor.
    Sebep olculdu: katalogda "yazlık" 65 urunde var,
    "yazlik" (ASCII) 0 urunde. Tersi de mumkun oldugu icin
    iki yazim da deneniyor.

    PERFORMANS NOTU: regex karsilastirmasi trigram/GIN
    indeksinden yararlanamiyor, her satiri tarar. 728 urunde
    onemsiz. Katalog on binlere cikarsa tam metin arama
    (tsvector) veya materyalize edilmis facet kolonlari
    gerekir.
    """

    conditions = []

    for term in terms:
        raw = str(term or "").strip()

        if not raw:
            continue

        for variant in {raw.lower(), fold(raw)}:
            if not variant:
                continue

            pattern = _word_pattern(variant)

            for column in fields:
                # op("~*") = Postgres buyuk/kucuk harf
                # duyarsiz regex karsilastirmasi
                conditions.append(column.op("~*")(pattern))

    return or_(*conditions) if conditions else None


def _facet_bonus_expression(intent: QueryIntent):
    """
    Facet kelime eslesmelerini tek bir SQL toplamina cevirir.

    Her facet en fazla bir kez puan veriyor: "yazlık" hem
    baslikta hem aciklamada geciyorsa iki kez saymiyoruz.
    Tekrar sayim, uzun aciklamasi olan urunleri hakedilmemis
    sekilde one cikariyor.
    """

    terms_total = literal(0.0, Float)

    for facets in intent.facets.values():
        for facet in facets:

            strong = _like_any(STRONG_FIELDS, facet.expand)
            weak = _like_any(WEAK_FIELDS, facet.expand)

            if strong is None and weak is None:
                continue

            branches = []

            if strong is not None:
                branches.append((strong, literal(facet.bonus, Float)))

            if weak is not None:
                branches.append(
                    (
                        weak,
                        literal(facet.bonus * WEAK_FIELD_FACTOR, Float),
                    )
                )

            terms_total = terms_total + case(
                *branches,
                else_=literal(0.0, Float),
            )

    return terms_total


def _color_terms(colors: list[str]) -> list[str]:

    terms: list[str] = []

    for color in colors:
        terms.extend(COLOR_TERMS.get(color, [color]))

    return terms


def _color_bonus_expression(colors: list[str], measured: bool = False):
    """
    Renk SERT FILTRE OLMADIGINDA verilen bonus.

    Merdiven renk filtresini gevsettiginde renk tamamen
    kaybolmamali; eslesen urunler yine one gelmeli. Aksi
    halde "kirmizi elbise" aramasi renk filtresi dusunce
    rastgele renklerle doluyor.

    IKI KAYNAK, EN BUYUGU ALINIR:

      metin  — aciklamasinda rengi yazan urun
      olcum  — gorselinden rengi cikarilmis urun (DeltaE)

    Toplamak yerine GREATEST: iki kaynak da eslesen urun
    (hem "siyah" yaziyor hem olcum siyah) cifte bonus alip
    listeyi ele gecirmesin. Ikisi ayni bilginin iki kaniti,
    iki ayri erdem degil.
    """

    if not colors:
        return literal(0.0, Float)

    parts = []

    condition = _like_any(STRONG_FIELDS + WEAK_FIELDS, _color_terms(colors))

    if condition is not None:
        parts.append(
            case(
                (condition, literal(COLOR_SOFT_BONUS, Float)),
                else_=literal(0.0, Float),
            )
        )

    if measured:

        targets = color_match.resolve_many(colors)

        if targets:
            parts.append(color_match.bonus_expression(targets))

    if not parts:
        return literal(0.0, Float)

    if len(parts) == 1:
        return parts[0]

    return func.greatest(*parts)


def _exact_phrase_expression(intent: QueryIntent):
    """Temizlenmis sorgunun tamami baslikta geciyorsa bonus."""

    phrase = intent.cleaned.strip()

    if len(phrase) < 4:
        return literal(0.0, Float)

    condition = _like_any(
        (Product.title, Product.title_tr),
        [phrase],
    )

    if condition is None:
        return literal(0.0, Float)

    return case(
        (condition, literal(EXACT_PHRASE_BONUS, Float)),
        else_=literal(0.0, Float),
    )


def _quality_expression():
    """
    Rating bonusu, yorum sayisiyla agirliklandirilmis.

    4.9 puanli 2 yorumlu urun ile 4.5 puanli 900 yorumlu
    urun ayni degilse; ikinci daha guvenilir. Carpan
    log tabanli degil basit doygunluk: 50 yorumda tam
    agirliga ulasiyor.
    """

    rating = func.coalesce(Product.rating, 0.0)
    count = func.coalesce(Product.rating_count, 0)

    confidence = func.least(literal(1.0, Float), count / literal(50.0, Float))

    # rating 0..5 -> 0..MAX_QUALITY_BONUS
    return (rating / literal(5.0, Float)) * confidence * literal(
        MAX_QUALITY_BONUS, Float
    )


# =========================================================
# KATEGORI / CINSIYET FILTRELERI
# =========================================================

# DESENLER KATALOGDAN OLCULEREK YAZILDI.
#
# Ilk surum crud.py'deki desenleri kopyalamisti ve gercek
# bir hata tasiyordu:
#
#     "%Coats%" deseni "Suits & Sport Coats" ile de esliyor.
#
# Sonuc: "manto" aramasinda ilk sirada erkek sherwani
# takimlari cikiyordu (kategori: Suits & Sport Coats › Suits).
# Kullanici dis giyim arayip takim elbise goruyordu.
#
# Cozum: desenler " › " ayiricisiyla DAL ADINA baglandi.
# Yanindaki sayilar 728 urunluk katalogda olculen eslesme
# sayisi; katalogda hic bulunmayan dallar (Sweaters, Skirts,
# Leggings, Vests, Boots) bilincli olarak YAZILMADI —
# skorlamayi degistirmezler ama bakim yapan kisiye var
# olmayan bir kapsam varmis gibi gosterirler.

_CATEGORY_PATTERNS: dict[str, list[str]] = {
    "dress": [
        "%› Dresses%",              # 41
    ],
    "shirt": [
        "%› Shirts%",              # 63
        "%› Polos%",               # 60
        "%T-Shirts%",              # 59
        "%Tops, Tees%",            # 71
        "%Blouses%",               # 66
        "%Tunics%",                # 16
        "%Hoodies & Sweatshirts%",  # 2
        "%Tank Tops%",             # 1
        "%Tanks & Camis%",         # 1
    ],
    "pants": [
        "%› Pants%",               # 52
        "%› Jeans%",               # 72
        "%Shorts%",                # 53
        "%Active Pants%",          # 26
    ],
    "jacket": [
        "%› Jackets & Coats%",     # 33  (Sport Coats'i YAKALAMAZ)
        "%Outerwear%",             # 7
    ],
    "shoes": [
        "%› Shoes ›%",             # 82
        "%› Shoes",                # 2
    ],
}

# Deger LISTE: "kids" tek bir breadcrumb dalina denk
# gelmiyor. Katalogda Boys / Baby (Baby Boys, Baby Girls) diye
# ayri bolumler var, ucu birlikte cocugu karsiliyor.
# Men/Women tek desen olarak kaliyor, davranislari degismedi.
_GENDER_PATTERNS = {
    "women": ["%› Women ›%"],
    "men": ["%› Men ›%"],
    "kids": ["%› Boys ›%", "%› Girls ›%", "%› Baby ›%"],
}


def _apply_gender(statement, gender: str | None):
    patterns = _GENDER_PATTERNS.get(gender or "")

    if not patterns:
        return statement

    return statement.where(
        or_(*[Product.category.ilike(p) for p in patterns])
    )


def _apply_category(statement, category: str | None):
    patterns = _CATEGORY_PATTERNS.get(category or "")

    if not patterns:
        return statement

    return statement.where(
        or_(*[Product.category.ilike(p) for p in patterns])
    )


def text_match_condition(terms: list[str]):
    """
    Verilen terimlerden metin eslesme kosulu (baslik/kategori +
    aciklama/ozellikler).

    Dis modullere ACIK: trend onerileri katalogda kac urunle
    karsilandigini sayarken aramanin kullandigi AYNI kosulu
    kullanmak zorunda. Ayri bir sayim sorgusu yazilsa "8 urun
    var" diyen etiket tiklandiginda 3 urun gosterebilirdi.
    """

    return _like_any(STRONG_FIELDS + WEAK_FIELDS, terms)


def color_condition(colors: list[str], measured: bool = False):
    """
    Renk eslesme kosulu — metin VEYA olculmus renk.

    _apply_colors bunu kullaniyor; disariya acik olmasinin
    sebebi text_match_condition ile ayni: sayim ile arama ayni
    kosulu paylasmali.
    """

    if not colors:
        return None

    conditions = []

    text_condition = text_match_condition(_color_terms(colors))

    if text_condition is not None:
        conditions.append(text_condition)

    if measured:

        targets = color_match.resolve_many(colors)

        measured_condition = color_match.measured_condition(targets)

        if measured_condition is not None:
            conditions.append(measured_condition)

    if not conditions:
        return None

    if len(conditions) == 1:
        return conditions[0]

    return or_(*conditions)


def _apply_colors(statement, colors: list[str], measured: bool = False):
    """
    Renk sert filtresi.

    IKI KANIT, "VEYA" ILE: metinde rengi yazan urunler VE
    gorselinden o renk olculen urunler.

    NEDEN BOYLE OLMAK ZORUNDA
    Katalogda urunlerin yalnizca %30'u rengini metninde
    yaziyor (olculdu: 217/728). Sadece metne bakan filtre,
    gercekten siyah olan urunlerin %70'ini eliyordu; sonuc
    sayisi dusuk kaldigi icin merdiven rengi tamamen
    birakiyor ve ekrana rastgele renkler geliyordu. Yani
    "renk filtresi" pratikte renk BOZUCU calisiyordu.
    """

    condition = color_condition(colors, measured=measured)

    if condition is None:
        return statement

    return statement.where(condition)


def _apply_price(statement, intent: QueryIntent, rate: float | None):
    """
    Butce filtresi — SQL'de, gevsetilmeden.

    NEDEN SQL'DE
    Onceki surumde fiyat filtresi Python tarafindaydi: genis
    cekilip (limit * 4) elde eleniyordu. Iki sonucu vardi:
    (1) butceye uyan urun listenin ilk 48'inde degilse "bu
    butcede urun yok" deniyordu — oysa vardi; (2) sayfalama
    bozuluyordu.

    NEDEN TL DEGIL USD KARSILASTIRMASI
    Katalog fiyatlari USD. Siniri BIR KEZ USD'ye ceviriyoruz;
    her satirda "price * kur" hesaplamak indeksi de kullanim
    disi birakirdi.

    FIYATI BILINMEYEN URUN ELENIR: "3000 TL alti" diyen birine
    fiyati belirsiz bir urun gostermek cevabi yanlis yapar.
    """

    if not intent.has_price_filter():
        return statement

    minimum = currency.to_usd(intent.min_price_try, rate)
    maximum = currency.to_usd(intent.max_price_try, rate)

    if minimum is None and maximum is None:
        return statement

    statement = statement.where(Product.price.is_not(None))

    if minimum is not None:
        statement = statement.where(Product.price >= minimum)

    if maximum is not None:
        statement = statement.where(Product.price <= maximum)

    return statement


def _apply_pattern(statement, intent: QueryIntent):
    """
    Desen niyetini SERT filtre yapar.

    Neden filtre: "renkli elbise" arayan biri duz siyah
    elbise gormek istemiyor. Katalogda desen kelimeleri
    yeterince yayginn (desen 103, print 91, floral 36) —
    filtre sonucu bosaltmiyor.

    Merdivenin 1. asamasinda birakiliyor.
    """

    facets = intent.facets.get("pattern", [])

    pattern_facet = next(
        (f for f in facets if f.key == "pattern"),
        None,
    )

    if pattern_facet is None:
        return statement

    condition = _like_any(
        STRONG_FIELDS + WEAK_FIELDS,
        pattern_facet.expand,
    )

    if condition is None:
        return statement

    return statement.where(condition)


# =========================================================
# TEK ASAMA
# =========================================================

def _run_stage(
    db: Session,
    intent: QueryIntent,
    query_embedding: list[float],
    stage: int,
    limit: int,
    offset: int,
    measured_color: bool = False,
    rate: float | None = None,
):
    """
    Belirli bir gevsetme asamasini calistirir.

    Dondurulen her satir: (Product, distance, bonus_total)
    """

    if query_embedding:
        distance = Product.search_embedding.cosine_distance(
            query_embedding
        ).label("distance")

        similarity = (literal(1.0, Float) - distance) * literal(100.0, Float)
    else:
        # Embedding uretilemedi (API anahtari yok veya servis
        # hatasi). Aramanin tamamen cokmesi yerine LEKSIKAL
        # skora dusuyoruz: bonuslar zaten kelime eslesmesine
        # dayaniyor. Sonuc daha zayif ama kullanilabilir ve
        # kullaniciya bu durum soyleniyor (meta.semantic).
        distance = literal(1.0, Float).label("distance")
        similarity = literal(0.0, Float)

    bonus = (
        _facet_bonus_expression(intent)
        + _exact_phrase_expression(intent)
        + _quality_expression()
    )

    # Renk sert filtre degilse bonusa donusuyor
    if stage >= 2:
        bonus = bonus + _color_bonus_expression(
            intent.colors, measured=measured_color
        )

    final_score = (similarity + bonus).label("final_score")

    statement = select(
        Product,
        distance,
        final_score,
    )

    # Embedding yoksa vektor siralamasi yapamayiz, ama
    # embedding'i olmayan urunleri de dislamanin anlami
    # kalmaz — leksikal aramada hepsi adaydir.
    if query_embedding:
        statement = statement.where(
            Product.search_embedding.is_not(None)
        )

    # ---- asamaya gore filtreler ----

    # Cinsiyet en son birakilan filtre: "kadin elbise"
    # aramasinda erkek urunu gostermek en rahatsiz edici
    # hata. Yine de 4. asamada birakiliyor, cunku hicbir
    # sonuc gostermemek daha kotu.
    if stage <= 3:
        statement = _apply_gender(statement, intent.gender)

    if stage <= 2:
        statement = _apply_category(statement, intent.category)

    if stage <= 1:
        statement = _apply_colors(
            statement, intent.colors, measured=measured_color
        )

    if stage <= 0:
        statement = _apply_pattern(statement, intent)

    # BUTCE HER ASAMADA UYGULANIR — merdivenin disinda.
    #
    # Diger kisitlar sonuc bulunamazsa birakilabiliyor; fiyat
    # birakilamaz. Butceyi gevsetmek "filtreyi biraz esnettim"
    # degil, kullanicinin veremeyecegi bir fiyati onermektir.
    statement = _apply_price(statement, intent, rate)

    statement = (
        statement
        .order_by(final_score.desc(), Product.product_id.desc())
        .offset(offset)
        .limit(limit)
    )

    return db.execute(statement).all()


# Hangi asama HANGI kisiti birakiyor.
#
# Bir asamanin numarasi tek basina "sunu gevsettim" demek
# degil: kullanici renk yazmadiysa renk asamasindan gecmek
# hicbir seyi degistirmiyor. Etiket ancak kisit GERCEKTEN
# varsa yazilmali — yoksa arayuzde "desen filtresi
# gevsetildi" yazip desen niyeti hic olmamis oluyor.
_STAGE_CONSTRAINT = {
    1: "pattern",
    2: "color",
    3: "category",
    4: "gender",
}


def _active_constraints(intent: QueryIntent) -> set[str]:
    """Sorguda gercekten var olan kisitlar."""

    active: set[str] = set()

    if "pattern" in intent.facet_keys("pattern"):
        active.add("pattern")

    if intent.colors:
        active.add("color")

    if intent.category:
        active.add("category")

    if intent.gender:
        active.add("gender")

    return active


def _stage_plan(intent: QueryIntent) -> list[int]:
    """
    Denenecek asamalar.

    Var olmayan bir kisiti "birakan" asama atlaniyor: ayni
    sorguyu ikinci kez calistirmak bos SQL turu demek.
    """

    active = _active_constraints(intent)

    return [0] + [
        stage
        for stage in sorted(_STAGE_CONSTRAINT)
        if _STAGE_CONSTRAINT[stage] in active
    ]


def _relaxed_labels(stage: int, intent: QueryIntent) -> list[str]:
    """
    O asamaya gelmek icin GERCEKTEN nelerin birakildigi.

    Var olmayan kisitlar listeye girmiyor.
    """

    active = _active_constraints(intent)

    return [
        STAGE_LABELS[s]
        for s in range(1, stage + 1)
        if _STAGE_CONSTRAINT.get(s) in active
    ]


# =========================================================
# ANA GIRIS
# =========================================================

def search(
    db: Session,
    intent: QueryIntent,
    query_embedding: list[float] | None,
    limit: int = 24,
    offset: int = 0,
    stage: int | None = None,
    usd_try_rate: float | None = None,
) -> tuple[list[dict], dict]:
    """
    Sorguyu calistirir, gerekirse filtreleri gevsetir.

    query_embedding:
        None verilebilir. O durumda anlamsal siralama
        devre disi kalir ve yalnizca kelime eslesmesi
        calisir (bkz. _run_stage).

    stage:
        None ise merdiven islatilir ve cozulen asama
        meta icinde donuyor. Sayfa 2+ icin cagiran taraf
        o degeri geri gondermeli — yoksa asama degisip
        urunler tekrar eder.

    Donen: (items, meta)
    """

    max_stage = max(STAGE_LABELS)

    if stage is not None:
        stages = [max(0, min(int(stage), max_stage))]
    else:
        stages = _stage_plan(intent)

    # Olculmus renk verisi BIR KEZ sorgulanir (5 dk onbellekli)
    # ve yalnizca renk gercekten arandiginda: veri yoksa
    # sistem eski metin davranisina duser.
    measured_color = bool(intent.colors) and color_match.is_ready(db)

    # Kur yalnizca butce varken gerekiyor; onbellekli oldugu
    # icin maliyeti yok ama gereksiz cagri da yapmiyoruz.
    rate = usd_try_rate

    if intent.has_price_filter() and rate is None:
        rate = currency.get_usd_try_rate()

    rows: list = []
    used_stage = stages[0]

    for index, candidate in enumerate(stages):

        rows = _run_stage(
            db=db,
            intent=intent,
            query_embedding=query_embedding,
            stage=candidate,
            limit=limit,
            offset=offset,
            measured_color=measured_color,
            rate=rate,
        )

        used_stage = candidate

        # Son asama: gevsetecek bir sey kalmadi
        if index + 1 >= len(stages):
            break

        # offset > 0 iken sonuc sayisi zaten dogal olarak
        # azaliyor; sayfa sonunda merdivenin devreye girip
        # filtre gevsetmesi yanlis olur. Bu yuzden esik
        # yalnizca ilk sayfada uygulaniyor.
        if offset > 0:
            break

        # ESIK, BIRAKILACAK KISITIN KAYNAGINA GORE.
        #
        # Bir sonraki asama neyi birakiyorsa esik ona gore:
        # cikarsanan kisit (desen) sonuc azsa birakilir,
        # kullanicinin acikca yazdigi kisit (renk, kategori,
        # cinsiyet) yalnizca sifir sonucta birakilir.
        next_stage = stages[index + 1]

        threshold = min(
            STAGE_MIN_RESULTS.get(next_stage - 1, 1),
            limit,
        )

        if len(rows) >= threshold:
            break

    items: list[dict] = []

    for product, distance, final_score in rows:

        similarity = 1.0 - float(distance)

        items.append(
            {
                "product": product,
                "similarity_score": similarity,
                "search_score": round(float(final_score), 2),
                "reasons": _row_reasons(product, intent),
            }
        )

    meta = {
        "stage": used_stage,
        "stage_label": STAGE_LABELS[used_stage],
        "relaxed": _relaxed_labels(used_stage, intent),
        "min_results": MIN_RESULTS,
        "has_more": len(rows) == limit,
        "semantic": bool(query_embedding),

        # Renk nereden bilindi: "measured" ise gorselden
        # olculmus renk de kullanildi, "text" ise yalnizca
        # metin eslesmesi. Sohbet ve arayuz durust
        # konusabilsin diye aciga cikariyoruz.
        "color_source": (
            "measured" if measured_color
            else ("text" if intent.colors else None)
        ),

        # Uygulanan butce. Kullanicinin gordugu sinirin
        # gercekten uygulandigini dogrulamanin tek yolu.
        "price_filter": (
            intent.price.as_dict() if intent.has_price_filter() else None
        ),
        "usd_try_rate": rate,
    }

    return items, meta


def _row_reasons(product: Product, intent: QueryIntent) -> list[str]:
    """
    Bir urunun neden geldigini kisa etiketlerle anlatir.

    SQL bonusunu tekrar hesaplamiyoruz; Python tarafinda
    yalnizca ETIKET uretiyoruz. Iki yerde puan hesaplamak,
    gun gelip birinin degismemesi demek — style_engine'de
    esiklerin tek yerde tutulmasiyla ayni gerekce.
    """

    haystack = fold(
        " ".join(
            str(value or "")
            for value in (
                product.title,
                product.title_tr,
                product.category,
                product.description,
                product.description_tr,
                product.features,
                product.features_tr,
            )
        )
    )

    reasons: list[str] = []

    for group in ("season", "pattern", "fabric", "fit", "occasion"):
        for facet in intent.facets.get(group, []):

            hit = any(
                _term_in_text(term, haystack)
                for term in facet.expand
                if term
            )

            if hit:
                reasons.append(facet.label)

    return reasons


def _term_in_text(term: str, haystack: str) -> bool:
    """
    SQL'deki kelime sinirli eslesmenin Python karsiligi.

    Ayni kurali kullanmak ZORUNLU: etiket ("Yazlık" yazisi)
    ile puan ayni kanittan gelmeli. Farkli kural kullanmak
    "skoru yukseltmis ama sebebi yazmamis" ya da tersi
    tutarsizliklar uretir — kullanicinin gordugu gerekce
    yanlis olur.
    """

    folded = fold(term).strip()

    if not folded:
        return False

    escaped = re.escape(folded)

    # 4+ harf: on-ek eslesmesi, kisa terim: tam kelime
    pattern = (
        r"\b" + escaped
        if len(folded) >= 4
        else r"\b" + escaped + r"\b"
    )

    return re.search(pattern, haystack) is not None
