import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# =========================================================
# REVIEW RESPONSE
# =========================================================

class ReviewResponse(BaseModel):
    review_id: str
    product_id: str

    rating: float | None = None
    helpful_votes: int = 0
    verified_purchase: bool = False

    review_title: str | None = None
    review_text: str | None = None

    sentiment_score: float | None = None

    # Sitede yazilmis yorumlarda dolu, veri setinden
    # gelenlerde None (onlarin tarihi yok).
    created_at: datetime | None = None

    # Yorumu yazan kullanicinin gorunen adi. Veri seti
    # yorumlarinda None.
    #
    # E-POSTA ASLA DONMUYOR: yorumlar herkese acik, adres
    # sizdirmak olurdu. Yalnizca ad + soyadin bas harfi.
    author_name: str | None = None

    # Bu yorum, istegi yapan kullanicinin kendi yorumu mu?
    # Arayuz "duzenle/sil" dugmesini buna gore gosteriyor.
    is_mine: bool = False

    model_config = ConfigDict(
        from_attributes=True
    )


class CreateReviewRequest(BaseModel):
    """
    Kullanicinin yazdigi yorum.

    Ayni kullanici ayni urune tekrar gonderirse yorumu
    GUNCELLENIYOR (bkz. crud.save_user_review) — "zaten yorum
    yaptin" hatasi vermek yerine duzenlemesine izin veriyoruz.
    """

    # Yarim yildiz yok: arayuz 1-5 arasi tam yildiz gosteriyor.
    rating: int = Field(ge=1, le=5)

    review_text: str = Field(min_length=3, max_length=2000)

    review_title: str | None = Field(default=None, max_length=120)

    @field_validator("review_text", "review_title")
    @classmethod
    def _strip(cls, value):

        if value is None:
            return None

        cleaned = value.strip()

        return cleaned or None

    @model_validator(mode="after")
    def _require_text(self):

        # _strip bosluktan olusan metni None'a cevirebiliyor;
        # min_length bunu yakalamiyor.
        if not self.review_text:
            raise ValueError("Yorum metni boş olamaz.")

        return self


# =========================================================
# PRODUCT RESPONSE
# =========================================================

class ProductResponse(BaseModel):
    product_id: str
    title: str

    # Türkçe alanlar
    title_tr: str | None = None

    brand: str | None = None
    category: str | None = None

    description: str | None = None
    description_tr: str | None = None

    features: str | None = None
    features_tr: str | None = None

    availability: str | None = None
    product_url: str | None = None

    price: float | None = None
    list_price: float | None = None
    discount_percent: int | None = None

    rating: float | None = None
    rating_count: int | None = None

    image_url: str | None = None

    search_text: str | None = None

    model_config = ConfigDict(
        from_attributes=True
    )


# =========================================================
# PRODUCT DETAIL RESPONSE
# =========================================================

# =========================================================
# BEDEN/KALIP TAVSIYESI
# =========================================================
#
# Veriyi scripts/17_extract_fit_signals.py uretiyor, metni
# app/fit_advice.py kuruyor. Burada yalnizca sozlesme var.

class FitAdvice(BaseModel):
    """
    Yorumlardan cikarilan kalip karari.

    None DONMESI NORMALDIR: 728 urunun 526'sinda karar
    verilebilecek kadar kanit yok (olculdu). O durumda alan
    hic gonderilmiyor ve arayuz kutuyu gostermiyor. Bos bir
    iddia yerine hicbir iddia.
    """

    # small | true | large
    verdict: str

    # Arayuzde gosterilecek baslik ve tavsiye cumlesi.
    title: str
    advice: str

    confidence: float

    # GEREKCE. "5 yorumdan 5'i" cumlesi bunlardan kuruluyor;
    # kullanici iddiayi kendisi tartabilmeli.
    agree_count: int
    total_count: int

    votes: dict[str, int] = {}


class ProductDetailResponse(ProductResponse):
    """
    /products/{id} cevabi.

    `reviews` alani KALDIRILDI (tanimliydi ama hic
    kullanilmiyordu). Arayuz yorumlari ayri bir uctan
    cekiyor — /products/{id}/reviews — ve iki istek paralel
    gidiyor (bkz. app.js openProduct). Burada bos bir liste
    tasimak "bu urunun yorumu yok" der gibi olurdu.
    """

    fit: FitAdvice | None = None

class SemanticProductResponse(ProductResponse):
    similarity_score: float

    # Gorselden olculmus renk bilgisi. Renk secilmis bir
    # istekte doluyor; yoksa None kaliyor (renk verisi
    # cikarilmamis ya da istek renksiz).
    #
    # color_distance: secilen palete DeltaE uzakligi. Kucuk =
    # daha iyi eslesme. Arayuz "neden bu urun?" sorusuna
    # bununla cevap verebilir.
    color_family: str | None = None
    is_pastel: bool | None = None
    color_distance: float | None = None


# =========================================================
# OZELLESTIR (EMBEDDING TABANLI STIL PROFILI)
# =========================================================
#
# style_customize.py'nin bacend'i: yas/cinsiyet/renk/tarz
# secimlerinden dogal dil promptu uretip Gemini embedding'e
# gonderiyoruz. Statik bir if-else filtre DEGIL — bkz. o
# modulun docstring'i.

class StyleCustomizeRequest(BaseModel):
    age: int | None = Field(default=None, ge=13, le=100)

    gender: str | None = None

    colors: list[str] = Field(default_factory=list, max_length=8)

    styles: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def _require_some_signal(self):

        if not (self.age or self.gender or self.colors or self.styles):
            raise ValueError(
                "Profil oluşturmak için en az bir tercih seç."
            )

        return self


class StyleCustomizeResponse(BaseModel):
    """
    prompt: kullaniciya SEFFAFLIK icin — hangi metnin embedding'e
    gonderildigini gorebilir, "kara kutu" hissi vermez.
    """

    prompt: str

    items: list[SemanticProductResponse]

    count: int

    # "measured": renkler urun gorsellerinden olculen
    # degerlerle eslestirildi. "semantic": renk verisi henuz
    # cikarilmamis, eslestirme yalnizca embedding ile yapildi
    # (katalogda urunlerin %70'i rengini metninde yazmadigi
    # icin bu yol renkte zayif).
    color_source: str = "semantic"

    # Kac urun secilen palete gercekten yakin cikti.
    # Kullaniciya "6 renk sectin, 18 urun uydu" demek
    # sessizce alakasiz urun gostermekten iyidir.
    color_matched: int = 0


# =========================================================
# AKILLI ARAMA  (/api/search)
# =========================================================

class SearchChip(BaseModel):
    """
    "AI ne anladi" etiketi.

    strict=True olanlar sert filtre (o urun gelmezse hic
    gelmez), strict=False olanlar siralama bonusu.
    Kullaniciya bu ayrimi gostermek onemli: renk filtresinin
    sonucu daraltmasi ile "yazlik" niyetinin sadece one
    almasi ayni sey degil.
    """

    kind: str
    label: str
    strict: bool


class SearchAnalysis(BaseModel):
    """Sorgu cozumlemesinin kullaniciya gosterilen hali."""

    raw: str
    cleaned: str

    gender: str | None = None
    category: str | None = None
    colors: list[str] = []

    season: list[str] = []
    patterns: list[str] = []
    fabrics: list[str] = []
    fits: list[str] = []
    occasions: list[str] = []

    # Cumleden okunan butce: {"min_try", "max_try", "kind",
    # "approximate"}. Kullanicinin yazdigi sayinin dogru
    # anlasildigini gormesi icin aciga cikariliyor.
    price: dict | None = None

    # Embedding'e giden zenginlestirilmis metin. Aciga
    # cikariyoruz cunku "AI aramayi nasil degistirdi"
    # sorusunun en dogru cevabi bu.
    embed_text: str = ""

    alternatives: list[str] = []
    chips: list[SearchChip] = []
    note: str = ""


class SearchItem(BaseModel):
    product: ProductResponse

    # Ham vektor benzerligi (0-1)
    similarity_score: float

    # Vektor + kelime bonuslarinin toplami
    search_score: float

    # Bu urunun hangi niyetlere uydugu
    reasons: list[str] = []


class SearchMeta(BaseModel):
    stage: int
    stage_label: str

    # Bu asamaya gelmek icin nelerin birakildigi
    relaxed: list[str] = []

    min_results: int
    has_more: bool

    # False ise embedding uretilemedi ve arama yalnizca
    # kelime eslesmesiyle calisti.
    semantic: bool = True

    # "measured": renk gorselden olculmus degerlerle de
    # eslestirildi. "text": yalnizca metin eslesmesi (renk
    # verisi henuz cikarilmamis). None: renk aranmadi.
    color_source: str | None = None

    # Gercekten uygulanan butce siniri ve kullanilan kur.
    # Sinir gevsetilmiyor; kullanici gordugu sayiya
    # guvenebilmeli.
    price_filter: dict | None = None
    usd_try_rate: float | None = None


class SearchResponse(BaseModel):
    query: SearchAnalysis
    items: list[SearchItem]
    meta: SearchMeta


# =========================================================
# USER REGISTER
# =========================================================

class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str

    # KULLANICI ADI — opsiyonel.
    #
    # Arayuz soruyor ama API zorunlu tutmuyor: bos gelirse
    # ad-soyaddan uretiliyor (username.suggest). Zorunlu
    # kilsaydik hem eski istemciler kirilirdi hem de kaydin
    # onune bir engel daha koymus olurduk.
    #
    # Adi OLMAYAN kullanici aranamaz hale gelirdi; bu yuzden
    # "bos birak" secenegi yok, yalnizca "sen sec ya da biz
    # uretelim" var.
    username: str | None = Field(default=None, max_length=24)
    gender: str | None = None
    age: int | None = None
    password: str

    # Opsiyonel: doldurulursa Hizli Al formunu onceden
    # doldurmak icin kullanilir, kayit icin sart degildir.
    address: str | None = Field(default=None, max_length=500)

class LoginRequest(BaseModel):
    email: str
    password: str


# =========================================================
# HESAP YONETIMI
# =========================================================

PASSWORD_MIN_LENGTH = 8


def _validate_password_strength(value: str) -> str:
    """
    Minimum guvenlik kurali: en az 8 karakter, en az bir harf
    ve bir rakam. Register akisindaki 6 karakter kuralindan
    kasitli olarak daha siki — kullanici burada zaten var olan
    bir hesabi koruyor, ilk kayittaki surtunmeyi degistirmiyoruz.
    """

    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Şifre en az {PASSWORD_MIN_LENGTH} karakter olmalı."
        )

    if not re.search(r"[A-Za-z]", value):
        raise ValueError("Şifre en az bir harf içermeli.")

    if not re.search(r"\d", value):
        raise ValueError("Şifre en az bir rakam içermeli.")

    return value


class UpdateProfileRequest(BaseModel):
    """Ad/soyad ve temel profil alanlari. E-posta ve sifre
    ayri, daha hassas uclardan degistirilir."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    gender: str | None = None
    age: int | None = Field(default=None, ge=13, le=100)
    address: str | None = Field(default=None, max_length=500)

    # BEDEN PROFILI. Hepsi opsiyonel — kullanici girmek
    # zorunda degil ve girmezse kalip tavsiyesi genel
    # cumleye ("bir beden ustunu tercih edin") duser.
    size_top: str | None = Field(default=None, max_length=8)
    size_bottom: str | None = Field(default=None, max_length=8)
    size_shoe: str | None = Field(default=None, max_length=8)

    # Bos/None gelirse MEVCUT AD KORUNUYOR (adres ve bedenin
    # aksine). Sebep: kullanici adini silmek diye bir sey yok
    # — silinirse hesap aranamaz hale gelir.
    username: str | None = Field(default=None, max_length=24)


class ChangeEmailRequest(BaseModel):
    """
    E-posta degisikligi hassas bir islem oldugu icin mevcut
    sifre tekrar istenir.

    NOT: projede e-posta dogrulama (mail gonderimi, link/kod
    onayi) altyapisi YOK. Bu uc, sifre dogrulandiktan sonra
    e-postayi DOGRUDAN degistirir. Gercek bir urunde bu adim
    "yeni adrese dogrulama maili gonder, onaylanana kadar eski
    adresi aktif tut" seklinde olmali; o altyapi kurulana kadar
    bunu taklit eden sahte bir akis eklemiyoruz.
    """

    new_email: str = Field(min_length=3, max_length=200)
    current_password: str

    @field_validator("new_email")
    @classmethod
    def _normalize_and_validate_email(cls, value: str) -> str:

        normalized = value.strip().lower()

        # Frontend'deki isValidEmail ile ayni kural.
        if not re.match(
            r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$",
            normalized,
        ):
            raise ValueError("Geçerli bir e-posta adresi gir.")

        return normalized


class ChangePasswordRequest(BaseModel):
    """
    Sifre degisikligi mevcut sifre dogrulanmadan yapilamaz.
    Yeni sifre minimum guvenlik kuralini gecmeli ve tekrari ile
    eslesmeli. Gercek dogrulama (hash karsilastirmasi) endpoint
    icinde yapilir; burada sadece sekil/eslesme kontrolu var.
    """

    current_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def _check_new_password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)

    @model_validator(mode="after")
    def _check_confirmation_and_change(self):

        if self.new_password != self.confirm_password:
            raise ValueError("Yeni şifreler eşleşmiyor.")

        if self.new_password == self.current_password:
            raise ValueError(
                "Yeni şifre mevcut şifreyle aynı olamaz."
            )

        return self


class AccountResponse(BaseModel):
    """Login/register ile ayni kullanici sekli — frontend
    tek bir signIn/updateSession yardimcisini her yerde
    kullanabilsin diye alan adlari birebir eslesiyor."""

    id: str
    first_name: str
    last_name: str
    email: str
    gender: str | None = None
    age: int | None = None
    address: str | None = None

    size_top: str | None = None
    size_bottom: str | None = None
    size_shoe: str | None = None

    username: str | None = None


# =========================================================
# INTERACTIONS
# =========================================================

# Tarz arketipleri — asagida da kullanildigi icin
# dosyanin basinda tanimli.
StyleArchetype = Literal[
    "minimalist",
    "streetwear",
    "smart_casual",
    "old_money",
    "boho",
    "athleisure",
    "goth",
    "y2k",
]


InteractionType = Literal[
    "VIEW",
    "LIKE",
    "UNLIKE",
    "DISLIKE",
    "QUICK_BUY",
]

InteractionSource = Literal[
    "explore",
    "detail",
    "grid",
    "wishlist",
    "featured",
    "quick_checkout",
    "cart",

    # AI sohbet asistaninin onerdigi kartlar.
    #
    # Neden mevcut bir deger yeniden kullanilmadi: source bir
    # BAGLAM OZELLIGI (bkz. EXPLORE_AND_RECOMMENDATIONS.md).
    # Sohbette verilen kalp, kullanicinin niyetini tarif
    # ettikten SONRA geliyor — gridde gezerken verilen kalpten
    # farkli bir sinyal. "grid" diye kaydetmek egitim verisini
    # sessizce bozardi.
    #
    # Migration gerekmiyor: user_interactions.source
    # VARCHAR(32) ve uzerinde CHECK kisiti yok.
    "chat",
]


# Toast bildirimi — sepet, etkilesim ve hizli siparis
# cevaplarinin UCUNDE de kullaniliyor, bu yuzden paylasilan
# tiplerin yaninda duruyor.
#
# ONCEDEN dosyanin ilerisinde tanimliydi ve ilk kullanimi
# (CartCheckoutResponse, satir ~536) ondan onceydi: backend
# NameError ile hic ayaga kalkmiyordu. StyleArchetype icin de
# ayni sey yasanmisti; Python sinif govdesindeki tip
# ifadelerini tanim aninda cozdugu icin SIRA onemli.
class ToastMessage(BaseModel):
    """
    Arayuzde gosterilecek bildirim.

    Metni backend uretiyor: mesaj gercekten olan seyi
    anlatmali. "Benzer urunler onceliklendirildi" yazip
    hicbir sey yapmamak kullaniciyi aldatmak olur.
    """

    title: str
    message: str

    # success | info | neutral
    tone: str = "info"



class InteractionCreate(BaseModel):
    """
    Tek bir kullanici etkilesimi.

    record_interactions bu sekli bekliyor. match_score ve
    matched_style burada TANIMLI OLMALI: Pydantic tanimsiz
    alanlari sessizce atar, bu yuzden eksik olduklarinda
    veritabanina NULL yazilir ve fark edilmez.
    """

    product_id: str = Field(min_length=1, max_length=64)

    interaction_type: InteractionType

    source: InteractionSource | None = None

    # Feed'de kacinci kart oldugu (position bias icin)
    position: int | None = Field(default=None, ge=0, le=10_000)

    # Etkilesim aninda gosterilen AI skoru
    match_score: float | None = Field(default=None, ge=0, le=100)

    # Karttaki eslesen tarz
    matched_style: StyleArchetype | None = None


class InteractionBatchCreate(BaseModel):
    """
    Coklu etkilesim.

    VIEW olaylari cok sik uretildigi icin istek basina bir
    olay yerine toplu gonderilir.
    """

    items: list[InteractionCreate] = Field(
        min_length=1,
        max_length=100,
    )


class InteractionResponse(BaseModel):
    id: UUID
    user_id: UUID
    product_id: str

    interaction_type: str
    source: str | None = None
    position: int | None = None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class InteractionAccepted(BaseModel):
    """Yazma uclarinin kisa cevabi."""

    recorded: int

    # LIKE/UNLIKE sonrasi guncel wishlist durumu
    in_wishlist: bool | None = None

    wishlist_count: int | None = None


# =========================================================
# WISHLIST
# =========================================================

class WishlistItemResponse(BaseModel):
    product_id: str
    created_at: datetime

    product: ProductResponse

    model_config = ConfigDict(
        from_attributes=True
    )


class WishlistIdsResponse(BaseModel):
    """
    Kalp ikonlarinin durumunu tek istekle doldurmak icin
    hafif cevap: sadece urun kimlikleri.
    """

    product_ids: list[str]

    count: int


# =========================================================
# CART
# =========================================================

class CartItemResponse(BaseModel):
    product_id: str
    quantity: int
    updated_at: datetime

    product: ProductResponse

    model_config = ConfigDict(
        from_attributes=True
    )


class CartSummaryResponse(BaseModel):
    """
    Sepet paneli ve header rozeti tek bu cevaptan besleniyor:
    urun listesi + toplam adet + ara toplam, tek istekte.
    """

    items: list[CartItemResponse]

    total_quantity: int
    subtotal: float


class AddToCartRequest(BaseModel):
    quantity: int = Field(default=1, ge=1, le=99)


class UpdateCartQuantityRequest(BaseModel):
    """quantity 0 gelirse urun sepetten tamamen cikarilir."""

    quantity: int = Field(ge=0, le=99)


class CartCheckoutRequest(BaseModel):
    """
    Sepetteki TUM urunleri tek seferde 'satin alir'.

    DIKKAT: kart bilgisi ALINMIYOR (bkz. QuickOrderRequest'in
    ayni uyarisi) — bu da gercek bir odeme saglayicisi
    olmadan calisan bir demo akistir.
    """

    source: InteractionSource | None = None


class CartCheckoutResponse(BaseModel):
    order_number: str

    items: list[CartItemResponse]
    total_quantity: int
    subtotal: float

    recorded: int

    toast: ToastMessage | None = None


# =========================================================
# EXPLORE FEED
# =========================================================

class ExploreResponse(BaseModel):
    items: list[ProductResponse]

    # Havuzda gosterilebilecek baska urun kalmadiysa true.
    # Frontend "hepsini gordun" ekranini bununla acar.
    exhausted: bool

    # Kullaniciya gosterilebilir kalan urun sayisi
    remaining: int


# =========================================================
# AI KISISELLESTIRME
# =========================================================

class ArchetypeOption(BaseModel):
    """Onboarding modalinda gosterilen tek kart."""

    id: StyleArchetype
    emoji: str
    label: str
    short_label: str
    tagline: str
    description: str
    image_url: str

    # Bu tarzda badge esigini gecen GERCEK urun sayisi.
    #
    # Katalog kapsami cok dengesiz (athleisure ~87 urun,
    # y2k ~0). Kullanicinin bunu secim aninda gormesi
    # gerekiyor; aksi halde bos bir akisla karsilasip
    # sistemin bozuk oldugunu dusunur.
    pool_count: int = 0

    # pool_count esigin altindaysa true
    is_thin: bool = False


class ArchetypeListResponse(BaseModel):
    options: list[ArchetypeOption]

    # Kullanicinin halihazirda secili tarzlari (sirali)
    selected: list[StyleArchetype] = []

    min_choices: int = 1
    max_choices: int = 3


class InitialStyleRequest(BaseModel):
    """
    1-3 tarz. Sira korunur; ilk eleman birincil tarz.
    """

    selected_styles: list[StyleArchetype] = Field(
        min_length=1,
        max_length=3,
    )


class InitialStyleResponse(BaseModel):
    selected_styles: list[StyleArchetype]

    # Birincil tarzin kisa adi
    primary_label: str

    # Butun secili tarzlarin adlari
    labels: list[str]

    # Arayuzde gosterilecek onay metni
    message: str

    # Secili tarzlarin toplam havuzu (tekil urun)
    matched_products: int

    # Havuz ince mi (kullaniciya uyari gosterilir)
    is_thin: bool = False


class MatchInfo(BaseModel):
    """Kart uzerindeki AI etiketleri."""

    match_score: float | None = None

    # "%86 AI Stil Uyumu" — esigin altindaysa None
    match_label: str | None = None

    # "Seçtiğin 'Streetwear' tarzı ve en çok beğendiğin
    #  'Siyah' tonuna göre önerildi."
    reason_label: str | None = None

    # Hangi secili tarz eslesti
    matched_style: StyleArchetype | None = None

    # Bu urun modelin onerisi mi, kesif slotu mu
    is_exploration: bool = False

    position: int


class AiExploreItem(MatchInfo):
    product: ProductResponse


class ExploreMeta(BaseModel):
    personalized: bool

    selected_styles: list[StyleArchetype] = []

    # Profilin dayandigi begeni sayisi
    liked_count: int = 0

    exploration_slots: int = 0

    # Sonsuz akisin bir sonraki istekte gonderecegi cursor.
    # None ise akis bitti.
    next_cursor: str | None = None

    has_more: bool = False


class AiExploreResponse(BaseModel):
    items: list[AiExploreItem]

    meta: ExploreMeta

    exhausted: bool

    remaining: int


class InteractRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=64)

    interaction_type: InteractionType

    source: InteractionSource | None = None

    position: int | None = Field(default=None, ge=0, le=10_000)

    # Etkilesim aninda kullaniciya gosterilen AI skoru.
    # ML icin kritik; frontend karttan aynen geri gonderir.
    match_score: float | None = Field(
        default=None, ge=0, le=100
    )

    # Karttaki eslesen tarz (varsa)
    matched_style: StyleArchetype | None = None


class InteractResponse(BaseModel):
    recorded: int

    in_wishlist: bool | None = None

    wishlist_count: int | None = None

    toast: ToastMessage | None = None


class PreferenceResponse(BaseModel):
    """
    "AI benim hakkimda ne biliyor" paneli.

    Kullaniciya profilini gostermek hem guven verir hem
    KVKK/GDPR tarafinda seffaflik saglar.
    """

    selected_styles: list[StyleArchetype] = []

    style_labels: list[str] = []

    style_archetype: StyleArchetype | None = None

    archetype_label: str | None = None

    like_count: int = 0

    dislike_count: int = 0

    top_brands: dict[str, float] = {}

    top_categories: dict[str, float] = {}

    top_colors: dict[str, float] = {}

    # Negatif sinyaller — seffaflik icin kullaniciya da
    # gosteriliyor ("AI neyi elemis?")
    avoid_brands: dict[str, float] = {}

    avoid_categories: dict[str, float] = {}

    median_price: float | None = None

    profile_computed_at: datetime | None = None


# =========================================================
# HIZLI SATIN ALMA  (sepetsiz)
# =========================================================

class QuickOrderRequest(BaseModel):
    """
    Tek urunluk siparis.

    DIKKAT: kart bilgisi ALINMIYOR. Dogrulama istemcide
    yapiliyor ve kart verisi sunucuya hic gonderilmiyor.
    Gercek bir odeme saglayicisi eklendiginde tokenizasyon
    yapilmali; kart numarasi bu ucun govdesine ASLA
    girmemeli.
    """

    product_id: str = Field(min_length=1, max_length=64)

    source: InteractionSource | None = None

    position: int | None = Field(default=None, ge=0, le=10_000)

    match_score: float | None = Field(default=None, ge=0, le=100)

    matched_style: StyleArchetype | None = None


class QuickOrderResponse(BaseModel):
    order_number: str

    product_id: str
    product_title: str

    recorded: int

    wishlist_count: int = 0

    toast: ToastMessage | None = None


# =========================================================
# AI SOHBET ASISTANI
# =========================================================
#
# Gecmis SUNUCUDA tutulmuyor: istemci her turda konusmanin
# tamamini gonderiyor (bkz. backend/app/assistant.py). Bu
# yuzden istek modeli tek bir mesaj degil, mesaj LISTESI.

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]

    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    # Ust sinir hem token maliyetini hem de kotu niyetli
    # buyuk govdeleri kapatiyor. Asistan zaten son
    # MAX_HISTORY_MESSAGES mesaji okuyor.
    messages: list[ChatMessage] = Field(
        min_length=1,
        max_length=40,
    )


class ChatProduct(BaseModel):
    """
    Sohbet balonunun altindaki kartin ihtiyaci olan alanlar.

    NEDEN ProductResponse DEGIL
    Iki sebep:

    1. DURUSTLUK. ProductResponse'un description/features/
       search_text alanlari var; sohbet bunlari okumuyor ve
       None gonderirse "bu urunun aciklamasi yok" demis olur.
       Sozlesme tasidigi seyi tarif etmeli.

    2. BOYUT. search_text urun basina kilobaytlar tutuyor ve
       bir cevapta 8 kart donebiliyor. Karta hicbir faydasi
       yok.

    Karta basildiginda arayuz /products/{id} ile tam kaydi
    zaten cekiyor (openProduct).

    FIYAT IKI ALANDA:

      price      USD — sitenin geri kalaniyla ayni sekil
      price_try  TL  — SUNUCUNUN kullandigi kur ile

    NEDEN IKINCISI EKLENDI
    Arayuz TL fiyatini kendi kuruyla hesapliyordu
    (formatPrice -> toTry). Kur alinamazsa sabit bir yedege
    (47.88) dusuyor. O anda asistan "3000 TL altinda" diye
    filtrelemisse, kartta 3100 TL yazabiliyordu: sistem
    kendi soyledigi seyi yalanliyordu.

    Sohbette gosterilen TL fiyati artik filtrenin
    kullandigi AYNI sayidir.
    """

    product_id: str
    title: str

    title_tr: str | None = None
    brand: str | None = None
    category: str | None = None

    price: float | None = None
    price_try: float | None = None

    rating: float | None = None
    rating_count: int | None = None

    image_url: str | None = None


# =========================================================
# SOHBET ACILIS ONERILERI  (/api/chat/starters)
# =========================================================

class ChatStarterItem(BaseModel):
    """
    Tiklanabilir bir oneri.

    prompt: sohbete AYNEN gonderilecek cumle. Arayuz kendi
        cumlesini kurmuyor — oneri metniyle gonderilen mesaj
        ayni yerden gelsin ki "tikladigim sey ile sordugu sey"
        arasinda fark olmasin.

    available: katalogda bu oneriyi karsilayan urun sayisi.
        None ise sayilamadi (arayuz sayi yazmaz).
    """

    id: str
    kind: str
    label: str
    note: str = ""
    prompt: str

    # Renk onerilerinde paletteki hex; digerlerinde None.
    swatch: str | None = None

    available: int | None = None


class ChatTrend(BaseModel):
    year: int
    season: str
    title: str
    note: str = ""

    # "editorial": liste elle derlendi, veriden cikarilmadi.
    # Arayuz bunu kullaniciya "WishNN seckisi" olarak
    # gosteriyor; olmayan bir yetke (Pantone vb.) ima
    # etmemek icin acikca tasiniyor.
    source: str = "editorial"

    colors: list[ChatStarterItem] = []
    styles: list[ChatStarterItem] = []
    fabrics: list[ChatStarterItem] = []


class ChatDestinationOption(BaseModel):
    id: str
    label: str
    prompt: str


class ChatDestination(BaseModel):
    hint: str
    placeholder: str

    # {place} kalibi. Kullanici serbest metin yazdiginda
    # arayuz bu kalibi dolduruyor.
    prompt_template: str

    options: list[ChatDestinationOption] = []


class ChatStartersResponse(BaseModel):
    trend: ChatTrend
    destination: ChatDestination


class ChatResponse(BaseModel):
    reply: str

    # Sohbette kart olarak gosterilecek urunler.
    products: list[ChatProduct] = []

    # Modelin bu turda hangi araclari cagirdigi. Arayuzde
    # "katalogda arandi" rozetini gostermek ve hata
    # ayiklamak icin.
    tool_calls: list[str] = []


# =========================================================
# GARDIROP (KOMBIN / LOOK)
# =========================================================

# Kombin, sepet/wishlist gibi tekil bir urun listesi DEGIL:
# birlikte giyilen parcalarin kompozisyonu. Bu yuzden
# response ic ice: look -> items -> product.
#
# Kart icin ChatProduct yerine ProductResponse kullaniliyor:
# gardirop paneli fiyat/gorsel/baslik disinda kategoriyi de
# gosteriyor ve "parcayi degistir" akisi kategori bilgisine
# ihtiyac duyuyor.

class WardrobeLookItemResponse(BaseModel):
    product_id: str

    # Parcanin kombindeki rolu ("ust", "ayakkabi"...).
    # Bos olabilir: sohbetten kurulan kombinlerde kullanici
    # slot secmiyor, urun kategorisinden tahmin ediliyor.
    slot: str | None = None

    position: int

    product: ProductResponse

    model_config = ConfigDict(
        from_attributes=True
    )


class WardrobeLookResponse(BaseModel):
    """
    Tek kombin. item_count ve total_price ORM'de YOK,
    endpoint hesaplayip veriyor (bkz. _look_summary) — bu
    yuzden from_attributes kullanilmiyor.
    """

    id: UUID
    title: str
    note: str | None = None
    source: str | None = None

    items: list[WardrobeLookItemResponse]

    item_count: int
    total_price: float

    created_at: datetime
    updated_at: datetime


class WardrobeListResponse(BaseModel):
    """Gardirop paneli ve header rozeti tek istekten beslenir."""

    looks: list[WardrobeLookResponse]
    count: int


class LookItemInput(BaseModel):
    product_id: str

    # Istemci slot gonderebilir ama zorunlu degil; sunucu
    # bos gelirse urun kategorisinden tahmin ediyor.
    slot: str | None = Field(default=None, max_length=24)


class SaveLookRequest(BaseModel):
    """
    Sohbetten ya da elle kombin kaydetme.

    En az IKI parca sart: tek urun bir kombin degil, o
    favorilere eklenir. Ust sinir 12 — bir "look" 12 parcadan
    fazlaysa artik kombin degil gardirop listesidir.
    """

    title: str = Field(min_length=1, max_length=120)

    items: list[LookItemInput] = Field(min_length=2, max_length=12)

    note: str | None = Field(default=None, max_length=500)

    # "chat" = AI asistanin onerisinden kuruldu.
    source: str | None = Field(default=None, max_length=32)


class RenameLookRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ReplaceLookItemRequest(BaseModel):
    """Kombindeki bir parcayi baska urunle degistirir."""

    new_product_id: str = Field(min_length=1)


class LookSuggestionResponse(BaseModel):
    """
    "Bu parcayi degistir" ekraninin alternatifleri.

    replaced_product_id: hangi parcanin yerine arandigi.
    Arayuz "X yerine sunlar" diye yazabilsin diye aciga
    cikariliyor.

    reason: aramanin nasil kuruldugu (kategori + kombinin
    diger parcalarinin renkleri). Kullaniciya "neden bunlar?"
    sorusunun cevabini verebilmek icin.
    """

    replaced_product_id: str
    reason: str

    items: list[SemanticProductResponse]
    count: int


# =========================================================
# KOMBIN ONERISI  (/api/outfit/{product_id})
# =========================================================

class OutfitOption(BaseModel):
    """
    Bir yuvanin tek adayi.

    ChatProduct'i sarmalyor cunku sohbet balonunda AYNI kart
    cizilecek — ayri bir alan kumesi ikinci bir kart
    bilesenini zorunlu kilardi.
    """

    product: ChatProduct
    similarity_score: float


class OutfitSlot(BaseModel):
    """
    Kombinin bir yuvasi ve adaylari.

    Ilk aday "secili" kabul ediliyor; gerisi kullanicinin tek
    dokunusla degistirebilecegi alternatifler.

    query/color aciga cikariliyor: kullanici "neden bu
    pantolon?" diye sordugunda cevabi arayuz verebilsin.
    """

    slot: str
    label: str

    color: str | None = None
    color_label: str | None = None

    query: str | None = None

    options: list[OutfitOption]


class OutfitResponse(BaseModel):
    """
    "Bu parcayla kombin kur" cevabi.

    Sohbette kullanici bir karta bastigi anda cagriliyor;
    modelden GECMIYOR (bkz. app/outfit.py). Bu yuzden kota
    harcamiyor ve aninda donuyor.

    title: onerilen kombin adi. Kullaniciya pencere acip ad
    sormuyoruz; kaydettikten sonra gardiroptan degistirebilir.
    """

    seed: ChatProduct
    seed_slot: str | None = None
    seed_color: str | None = None

    title: str
    reason: str

    slots: list[OutfitSlot]

    # Kac tamamlayici yuva doldu. Sifir ise arayuz "bu parcaya
    # uygun tamamlayici bulamadim" diyip kaydet dugmesini
    # hic gostermiyor.
    count: int


# =========================================================
# SOSYAL KATMAN — ARKADASLIK / MESAJLASMA
# =========================================================
#
# Kurallar app/social.py'de, tablolar models.py'de.
# Burada yalnizca disari acilan sozlesme var.

class PublicUser(BaseModel):
    """
    Baskasina gosterilen kullanici.

    E-POSTA YOK ve bu bilincli: arkadas arama sonuclari ile
    mesaj basliklari, kullanicinin adresini gormeyi hak
    etmeyen kisilere de gorunuyor. Ayni karar
    ReviewResponse'ta da alinmisti.

    KULLANICI ADI VAR ve bu da bilincli: paylasilmak uzere
    tasarlanmis tanimlayici o. Ayni adi tasiyan iki kisiyi
    ayirt etmenin de tek yolu.
    """

    id: str
    name: str
    initials: str

    username: str | None = None


class UserSearchResult(PublicUser):
    """
    Arama sonucu — mevcut iliski durumuyla birlikte.

    relation arayuzun hangi dugmeyi cizecegini belirliyor:

        none      -> "Arkadaş Ekle"
        outgoing  -> "İstek gönderildi" (pasif)
        incoming  -> "Kabul Et"  (friendship_id dolu)
        friends   -> "Arkadaşınız"
        declined  -> "Arkadaş Ekle" (tekrar denenebilir)
    """

    relation: str

    # Yalnizca incoming durumunda dolu.
    friendship_id: str | None = None


class FriendRequestCreate(BaseModel):
    user_id: UUID


class FriendRequest(PublicUser):
    friendship_id: str
    created_at: datetime


class FriendRequestResponse(BaseModel):
    """Kabul mu red mi."""

    accept: bool


# =========================================================
# MESAJLASMA
# =========================================================

class MessageProduct(BaseModel):
    """
    Mesajin icindeki urun karti.

    ProductResponse DEGIL: sohbet balonunda yalnizca gorsel,
    ad, marka ve fiyat gorunuyor. Tam urun sozlesmesini
    tasimak her mesajda kilobaytlarca description ve
    search_text goturmek olurdu. Karta basildiginda arayuz
    /products/{id} ile tam kaydi zaten cekiyor.

    Ayni gerekce ChatProduct icin de yazilmisti.
    """

    product_id: str
    title: str
    title_tr: str | None = None
    brand: str | None = None
    price: float | None = None
    image_url: str | None = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str

    sender_id: str

    # Arayuz balonu saga mi sola mi hizalayacak. sender_id ile
    # de hesaplanabilirdi ama o zaman istemcinin kendi
    # kimligini bilmesi ve karsilastirmasi gerekirdi; sunucu
    # zaten biliyor.
    from_me: bool

    body: str | None = None

    # PAYLASILAN URUN. Mesaj basina en fazla BIR tane —
    # bu bir sema garantisi, uygulama kurali degil
    # (bkz. models.py Message.product_id notu).
    product: MessageProduct | None = None

    created_at: datetime
    read_at: datetime | None = None


class ConversationSummary(BaseModel):
    """Gelen kutusundaki tek satir."""

    id: str

    user: PublicUser

    last_message: str = ""
    last_message_at: datetime

    unread: int = 0

    # Son mesaji ben mi yazdim — arayuz "Sen: ..." on eki
    # koyuyor.
    last_from_me: bool = False


class ConversationDetail(BaseModel):
    id: str
    user: PublicUser
    messages: list[MessageResponse] = []


class SendMessageRequest(BaseModel):
    """
    Mesaj gonderme.

    ALICI IKI SEKILDE verilebiliyor:
      conversation_id -> mevcut sohbete yaz
      to_user_id      -> kisiye yaz (sohbet yoksa acilir)

    Ikisi de yoksa istek reddediliyor. Urun paylasimi
    genelde ikinci yoldan geliyor: kullanici urun
    sayfasindan "arkadasima gonder" diyor ve o an bir
    sohbet olmayabilir.
    """

    conversation_id: UUID | None = None
    to_user_id: UUID | None = None

    body: str | None = Field(default=None, max_length=2000)

    product_id: str | None = Field(default=None, max_length=64)

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value):

        if value is None:
            return None

        return value.strip() or None

    @model_validator(mode="after")
    def _require_content_and_target(self):

        # Bos mesaj: veritabaninda da CHECK var
        # (ck_messages_not_empty) ama hatayi 500 yerine 422
        # olarak ve anlasilir bir mesajla vermek istiyoruz.
        if not self.body and not self.product_id:
            raise ValueError(
                "Mesaj metni veya ürün göndermelisin."
            )

        if self.conversation_id is None and self.to_user_id is None:
            raise ValueError("Alıcı belirtilmedi.")

        return self


class SendMessageResponse(BaseModel):
    conversation_id: str
    message: MessageResponse


class UnreadCountResponse(BaseModel):
    unread: int = 0

# =========================================================
# GORSELLE ARAMA
# =========================================================
#
# Kurallar app/vision.py'de. Gorsel SAKLANMIYOR: baytlar
# istek boyunca bellekte, cevap donunce gidiyor.

class VisionDescribeRequest(BaseModel):
    """
    Fotograf, base64 olarak.

    NEDEN multipart/form-data DEGIL
    FastAPI'nin UploadFile'i python-multipart paketini
    zorunlu kiliyor ve o kurulu degil. Base64 %33 sisiriyor
    ama arayuz gorseli gondermeden once canvas ile ~1024px'e
    kucultuyor: tipik sonuc 150-400 KB, base64 ile 200-550 KB.
    Yeni bir bagimlilik eklemeye degmeyecek bir fark.

    Kucultmenin ikinci faydasi: Gemini'ye 12 megapiksel
    gondermenin tarife hicbir katkisi yok, yalnizca gecikme
    ve maliyet.
    """

    # data:image/jpeg;base64,... ya da ciplak base64
    image: str = Field(min_length=32)

    @field_validator("image")
    @classmethod
    def _strip(cls, value: str) -> str:
        return (value or "").strip()


class VisionDescribeResponse(BaseModel):
    """
    Uretilen arama cumlesi.

    Arayuz bunu sohbete NORMAL BIR KULLANICI MESAJI olarak
    koyuyor. Boylece:
      - sohbet sozlesmesi degismiyor (gecmis metin kaliyor,
        her turda dev base64 tasinmiyor)
      - kullanici modelin ne anladigini GORUYOR ve
        duzeltebiliyor ("hayir, lacivert olacak")

    Ikincisi bilincli: arama analiz panelindeki seffaflik
    kararinin aynisi.
    """

    query: str

    # Tani/olcum icin: kac saniye surdu, hangi model, kac bayt.
    seconds: float = 0.0
    model: str = ""
    bytes: int = 0

class UsernameCheckResponse(BaseModel):
    """
    Kullanici adi musait mi?

    reason: musait DEGILSE sebebi (kural ihlali ya da
    alinmis). Arayuz bunu oldugu gibi gosteriyor —
    "gecersiz" demek yerine "nokta ile bitemez" demek
    kullanicinin ne duzeltecegini soyluyor.

    suggestion: alinmissa yakin bir alternatif.
    """

    username: str
    available: bool
    reason: str | None = None
    suggestion: str | None = None

