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

    model_config = ConfigDict(
        from_attributes=True
    )


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

class ProductDetailResponse(ProductResponse):
    reviews: list[ReviewResponse] = []

class SemanticProductResponse(ProductResponse):
    similarity_score: float


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


# =========================================================
# USER REGISTER
# =========================================================

class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
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
]


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
