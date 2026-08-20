from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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

class LoginRequest(BaseModel):
    email: str
    password: str


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
