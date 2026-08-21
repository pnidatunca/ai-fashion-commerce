from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from sqlalchemy.orm import relationship

from pgvector.sqlalchemy import VECTOR

from .database import Base


# =========================================================
# ETKILESIM TURLERI
# =========================================================

# VIEW    : urun kullaniciya gosterildi (implicit feedback)
# LIKE    : kalp butonu, wishlist'e eklendi
# UNLIKE  : wishlist'ten cikarildi
# DISLIKE : "begenmedim", bir daha onerilmez
#
# Yeni tur eklerken CheckConstraint'i de guncelle.

INTERACTION_VIEW = "VIEW"
INTERACTION_LIKE = "LIKE"
INTERACTION_UNLIKE = "UNLIKE"
INTERACTION_DISLIKE = "DISLIKE"

# Hizli satin alma. Sepet kaldirildigi icin satin alma
# niyeti dogrudan urun uzerinden olusuyor.
#
# ML acisindan EN GUCLU sinyal: kullanici sadece
# begenmiyor, para harcamaya niyet ediyor.
INTERACTION_QUICK_BUY = "QUICK_BUY"

# Urune bagli DEGIL: kullanici arketip sectiginde yazilir.
# Cold start sinyali; product_id NULL olur.
INTERACTION_INITIAL_STYLE = "INITIAL_STYLE"

INTERACTION_TYPES = (
    INTERACTION_VIEW,
    INTERACTION_LIKE,
    INTERACTION_UNLIKE,
    INTERACTION_DISLIKE,
    INTERACTION_QUICK_BUY,
    INTERACTION_INITIAL_STYLE,
)


# =========================================================
# ETKILESIM AGIRLIKLARI
# =========================================================

# Bu agirliklar OLAYLA BIRLIKTE veritabanina yazilir.
#
# Neden export sirasinda hesaplamak yerine: agirlik esleme
# tablosu zamanla degisir. Satirin uzerinde o an kullanilan
# agirlik yazili olmazsa, alti ay sonra egitim verisini
# yeniden cikarttiginda gecmis olaylara BUGUNUN agirliklari
# uygulanir ve model farkli bir gecmis ogrenir.
#
# Yeni bir tur eklerken buraya da eklemeyi unutma.

INTERACTION_WEIGHTS = {
    INTERACTION_QUICK_BUY: 2.0,      # satin alma niyeti
    INTERACTION_LIKE: 1.0,           # acik pozitif
    INTERACTION_VIEW: 0.1,           # zayif sinyal
    INTERACTION_UNLIKE: -0.3,        # fikir degistirdi
    INTERACTION_DISLIKE: -1.0,       # acik negatif
    INTERACTION_INITIAL_STYLE: 0.0,  # urun-disi olay
}


def weight_for(interaction_type):
    """Bilinmeyen tur 0 agirlik alir."""

    return INTERACTION_WEIGHTS.get(interaction_type, 0.0)

# Urun kimligi zorunlu olmayan turler
PRODUCTLESS_INTERACTION_TYPES = (
    INTERACTION_INITIAL_STYLE,
)


# =========================================================
# PRODUCT
# =========================================================

class Product(Base):
    __tablename__ = "products"

    # Amazon ASIN
    # Örnek: B0DLGB4RYH
    product_id = Column(
        String,
        primary_key=True,
        index=True,
    )

    # Ürün temel bilgileri
    title = Column(
        Text,
        nullable=False,
    )

    # Türkçe başlık
    title_tr = Column(Text)

    brand = Column(String)

    category = Column(Text)

    description = Column(Text)


    features = Column(Text)


    # Türkçe açıklama
    description_tr = Column(Text)

    features = Column(Text)

    # Türkçe özellikler
    features_tr = Column(Text)


    availability = Column(String)

    product_url = Column(Text)

    # Fiyat bilgileri
    price = Column(Float)

    list_price = Column(Float)

    discount_percent = Column(Integer)

    # Rating bilgileri
    rating = Column(Float)

    rating_count = Column(Integer)

    # Ana ürün görseli
    image_url = Column(Text)

    # Semantic Search için hazırladığımız
    # birleşik ürün metni
    search_text = Column(Text)


    # Semantic Search icin urun metninin vector temsili.
    # Embeddingler sonraki asamada uretilecegi icin nullable kalir.
    search_embedding = Column(
        VECTOR(1536),
        nullable=True,
    )


    # Bir ürünün birden fazla review'su olabilir.
    reviews = relationship(
        "Review",
        back_populates="product",
        cascade="all, delete-orphan",
    )


# =========================================================
# REVIEW
# =========================================================

class Review(Base):
    __tablename__ = "reviews"

    # Amazon review ID
    # Örnek: R2AUQFPJY5ERCZ
    review_id = Column(
        String,
        primary_key=True,
        index=True,
    )

    # Bu yorum hangi ürüne ait?
    product_id = Column(
        String,
        ForeignKey(
            "products.product_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # Yorumdaki yıldız puanı
    rating = Column(Float)

    # Yoruma verilen helpful vote sayısı
    helpful_votes = Column(
        Integer,
        default=0,
    )

    # Verified Purchase mı?
    verified_purchase = Column(
        Boolean,
        default=False,
    )

    # Review başlığı
    review_title = Column(Text)

    # Review metni
    review_text = Column(Text)

    # Temizlenmiş orijinal review metni
    source_cleaned_review_text = Column(Text)

    # Dataset içerisindeki sentiment skoru
    sentiment_score = Column(Float)

    # Review -> Product ilişkisi
    product = relationship(
        "Product",
        back_populates="reviews",
    )

# =========================================================
# USER
# =========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
    UUID(as_uuid=True),
    primary_key=True,
    server_default=text("gen_random_uuid()"),
    )

    first_name = Column(
        String,
        nullable=False,
    )

    last_name = Column(
        String,
        nullable=False,
    )

    email = Column(
        String,
        nullable=False,
        unique=True,
        index=True,
    )

    gender = Column(String)

    age = Column(Integer)

    password_hash = Column(
        String,
        nullable=False,
    )

    created_at = Column(
    DateTime,
    nullable=False,
    server_default=text("NOW()"),
     )

# =========================================================
# USER INTERACTIONS
# =========================================================

class UserInteraction(Base):
    """
    Kullanici etkilesimlerinin append-only olay kaydi.

    Bu tablo GUNCELLENMEZ ve SILINMEZ; her etkilesim yeni bir
    satirdir. Recommendation / Collaborative Filtering modeli
    icin egitim verisi kaynagi budur, bu yuzden gecmisin
    bozulmamasi onemlidir.

    Anlik durum ("bu urun su anda favorilerimde mi?") bu
    tablodan turetilmez; onun icin wishlist_items kullanilir.
    """

    __tablename__ = "user_interactions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # INITIAL_STYLE olaylari bir urune bagli olmadigi icin
    # NULL olabilir. Asagidaki CHECK diger turlerde zorunlu
    # tutar.
    product_id = Column(
        String,
        ForeignKey(
            "products.product_id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    # VIEW / LIKE / UNLIKE / DISLIKE / INITIAL_STYLE
    interaction_type = Column(
        String(24),
        nullable=False,
    )

    # Etkilesim aninda kullaniciya GOSTERILEN AI skoru.
    #
    # ML icin kritik: model "kullanici neyi begendi" degil
    # "kullaniciya X skoruyla gosterilen seyi begendi mi"
    # sorusunu ogrenmeli. Bu kolon olmadan sistemin kendi
    # onerisinin etkisini (feedback loop) olcemezsin.
    match_score = Column(
        Float,
    )

    # INITIAL_STYLE olaylarinda secilen BIRINCIL arketip.
    # Diger turlerde etkilesim aninda aktif olan arketip.
    style_archetype = Column(
        String(32),
    )

    # INITIAL_STYLE olaylarinda secilen butun tarzlar.
    # Olay kaydi append-only oldugu icin kullanicinin tarz
    # gecmisi bu kolondan izlenebilir.
    selected_styles = Column(
        JSONB,
    )

    # Olay aninda gecerli olan ML agirligi.
    #
    # INTERACTION_WEIGHTS tablosundan yaziliyor. Satirda
    # saklanmasinin sebebi: agirlik esleme tablosu
    # degistiginde GECMIS olaylarin agirligi degismemeli.
    weight = Column(
        Float,
        nullable=False,
        server_default=text("0"),
    )

    # Etkilesimin gerceklestigi yer: explore, detail,
    # wishlist, grid. Modelde baglam ozelligi (context
    # feature) olarak kullanilabilir.
    source = Column(
        String(32),
    )

    # Istekte gelen sira numarasi: feed'de kacinci karttı.
    # Position bias duzeltmesi icin gerekli.
    position = Column(
        Integer,
    )

    # Alan adi olarak "timestamp" yerine created_at:
    # timestamp SQL'de tip adi oldugu icin karisiklik yaratir.
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        index=True,
    )

    user = relationship("User")
    product = relationship("Product")

    __table_args__ = (

        CheckConstraint(
            "interaction_type IN "
            "('VIEW', 'LIKE', 'UNLIKE', 'DISLIKE', "
            "'QUICK_BUY', 'INITIAL_STYLE')",
            name="ck_user_interactions_type",
        ),

        # Urun kimligi yalnizca INITIAL_STYLE'da bos olabilir.
        # Bu kisit olmasa bos product_id'li LIKE satirlari
        # egitim verisini sessizce bozardi.
        CheckConstraint(
            "interaction_type = 'INITIAL_STYLE' "
            "OR product_id IS NOT NULL",
            name="ck_user_interactions_product_required",
        ),

        # Explore feed'in DISLIKE haric tutma sorgusu
        Index(
            "ix_user_interactions_user_type",
            "user_id",
            "interaction_type",
        ),

        # Kronolojik egitim verisi cikarimi
        Index(
            "ix_user_interactions_user_created",
            "user_id",
            "created_at",
        ),

        # Kullanici-urun cifti gecmisi
        Index(
            "ix_user_interactions_user_product",
            "user_id",
            "product_id",
        ),
    )


# =========================================================
# WISHLIST
# =========================================================

class WishlistItem(Base):
    """
    Kullanicinin favori listesinin ANLIK durumu.

    user_interactions LIKE/UNLIKE olaylarini saklar; bu tablo
    ise "su an favorilerimde ne var" sorusunu tek sorguda
    cevaplar. Unique kisit ayni urunun iki kez eklenmesini
    veritabani seviyesinde engeller.
    """

    __tablename__ = "wishlist_items"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    product_id = Column(
        String,
        ForeignKey(
            "products.product_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    product = relationship("Product")

    __table_args__ = (

        UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_wishlist_user_product",
        ),
    )


# =========================================================
# USER PREFERENCES
# =========================================================

class UserPreference(Base):
    """
    Kullanicinin UZUN VADELI zevk profili.

    user_interactions olay akisi, bu tablo ise o akistan
    turetilmis ozet. Her feed istegi icin butun gecmisi
    yeniden okumak yerine burayi okuyoruz.

    Kullanici basina TEK satir (user_id unique).

    Neden ayri tablo:
      - Arketip secimi (cold start) hemen burada durur
      - Turetilmis alanlar (top_brands vb.) periyodik
        guncellenebilir; olay kaydi bozulmaz
      - Feed sorgusu tek satir okur, agregasyon yapmaz
    """

    __tablename__ = "user_preferences"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    # BIRINCIL tarz: selected_styles listesinin ilki.
    #
    # Neden ayri tutuluyor: indekslenebilir tek deger olarak
    # sorgulamak ve raporlamak kolay. selected_styles ise
    # kullanicinin gercek secimidir (1-3 tarz).
    style_archetype = Column(
        String(32),
    )

    # Kullanicinin sectigi butun tarzlar, SIRALI.
    # ["streetwear", "y2k"] — ilk eleman birincil tarz.
    #
    # Sira onemli: kullanici once neyi sectiyse ona daha
    # cok agirlik verilebilir (su an verilmiyor, blend_scores
    # en iyi eslesmeyi aliyor).
    selected_styles = Column(
        JSONB,
    )

    archetype_selected_at = Column(
        DateTime(timezone=True),
    )

    # Kullanicinin arketibi kac kez degistirdigi.
    # Sik degistiren kullanici icin arketip agirligi
    # dusurulebilir.
    archetype_change_count = Column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    # LIKE gecmisinden turetilen ozetler.
    # JSONB: {"nike": 3.2, "levis": 1.0} bicimi.
    top_brands = Column(
        JSONB,
    )

    top_categories = Column(
        JSONB,
    )

    top_colors = Column(
        JSONB,
    )

    # BEGENILMEYEN marka ve kategoriler.
    #
    # "Bu urun ve benzer kategorideki urunler negatif
    # agirlik kazanir" kurali icin gerekli. Urunun kendisi
    # kara listeye giriyor (kalici), ayni kategorideki diger
    # urunler ise yalnizca skor kaybediyor — kategoriyi de
    # tamamen dislamak akisi hizla bosaltirdi.
    avoid_brands = Column(
        JSONB,
    )

    avoid_categories = Column(
        JSONB,
    )

    # Begenilen urunlerin medyan fiyati (USD)
    median_price = Column(
        Float,
    )

    like_count = Column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    dislike_count = Column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    # Turetilmis alanlarin en son ne zaman hesaplandigi
    profile_computed_at = Column(
        DateTime(timezone=True),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    user = relationship("User")

    __table_args__ = (

        CheckConstraint(
            "style_archetype IS NULL OR style_archetype IN "
            "('minimalist', 'streetwear', 'smart_casual', "
            "'old_money', 'boho', 'athleisure', 'goth', 'y2k')",
            name="ck_user_preferences_archetype",
        ),

        # selected_styles bir JSONB dizisidir; icerigini
        # CHECK ile dogrulamak yerine uygulama katmaninda
        # style_engine.normalize_selected_styles temizliyor.
        # Dizi uzunlugunu burada siniriyoruz.
        CheckConstraint(
            "selected_styles IS NULL OR "
            "jsonb_array_length(selected_styles) BETWEEN 1 AND 3",
            name="ck_user_preferences_selected_styles_len",
        ),
    )


# =========================================================
# PRODUCT STYLE SCORES
# =========================================================

class ProductStyleScore(Base):
    """
    Arketip x urun TEMEL skoru. Onceden hesaplanir.

    Bu tablo modelin "egitilmis agirliklari" gibidir:
    scripts/09_compute_style_scores.py doldurur, feed
    sorgusu sadece JOIN eder ve ORDER BY yapar.

    Neden onceden: skor metin analizine dayaniyor. Her
    istekte 700 urunun metnini Python'da islemek hem yavas
    hem de SQL tarafinda ORDER BY yapilmasini imkansiz
    kilardi (yani sayfalama bozulurdu).

    Katalog veya sozlukler degistiginde script yeniden
    kosturulur.
    """

    __tablename__ = "product_style_scores"

    product_id = Column(
        String,
        ForeignKey(
            "products.product_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    archetype = Column(
        String(32),
        primary_key=True,
    )

    # 0-100
    score = Column(
        Float,
        nullable=False,
    )

    # ["color:bej", "style:minimalist", "price:band"]
    reasons = Column(
        JSONB,
    )

    computed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    product = relationship("Product")

    __table_args__ = (

        CheckConstraint(
            "archetype IN "
            "('minimalist', 'streetwear', 'smart_casual', "
            "'old_money', 'boho', 'athleisure', 'goth', 'y2k')",
            name="ck_product_style_scores_archetype",
        ),

        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_product_style_scores_range",
        ),

        # Feed sorgusunun sicak yolu:
        # WHERE archetype = :a ORDER BY score DESC
        Index(
            "ix_product_style_scores_archetype_score",
            "archetype",
            "score",
        ),
    )
