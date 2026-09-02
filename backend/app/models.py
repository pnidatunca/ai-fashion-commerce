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

    # ---- SITEDE YAZILAN YORUMLAR ----
    #
    # Iki tur yorum ayni tabloda duruyor:
    #
    #   user_id NULL     -> Amazon veri setinden gelen yorum
    #                       (tarihi yok, helpful_votes'u var)
    #   user_id DOLU     -> bu sitede bir kullanicinin yazdigi
    #
    # Ayri tablo yerine ayni tabloda tutuluyor cunku urun
    # detayinda ikisi TEK bir liste olarak gosteriliyor;
    # ayirmak her okumada UNION gerektirirdi.
    #
    # Ikisi de nullable: 700+ eski satirin user_id'si ve
    # tarihi yok, olamaz da.
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Review -> Product ilişkisi
    product = relationship(
        "Product",
        back_populates="reviews",
    )

    user = relationship("User")

    __table_args__ = (

        # Bir kullanici bir urune BIR yorum yazar.
        #
        # Postgres NULL'lari birbirinden farkli saydigi icin
        # bu kisit veri setinden gelen (user_id NULL) yuzlerce
        # satiri etkilemiyor.
        UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_review_user_product",
        ),
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

    # Opsiyonel: Hizli Al'da her seferinde adres girmemek
    # icin kayit sirasinda veya Hesabim'dan eklenebilir.
    address = Column(Text, nullable=True)

    # KULLANICI ADI (@handle) — scripts/20_add_usernames.py
    #
    # Arkadas bulmanin ana yolu. E-posta ile arama TAM
    # eslesme istiyor ve kimse arkadasinin adresini ezbere
    # bilmiyor; kullanici adi paylasilmak UZERE tasarlanmis
    # bir tanimlayici.
    #
    # Tekillik duz UNIQUE degil, LOWER(username) uzerinde
    # fonksiyonel indeks: "Pinar" ve "pinar" ayni anda var
    # olamaz. Bu yalnizca karisiklik degil TAKLIT engeli.
    username = Column(String(24), nullable=True)

    # BEDEN PROFILI (scripts/19_add_user_sizes.py)
    #
    # Kalip karari "bir beden buyuk al" diyor; BIR BEDEN
    # USTU NE oldugunu soyleyebilmek icin kullanicinin
    # bedeni gerekiyor. Hesap fit_advice.shift_size'da.
    #
    # products'taki turetilmis kolonlarin aksine bunlar
    # ORM modelinde: script'in urettigi opsiyonel bir
    # zenginlestirme degil, kullanicinin girdigi veri.
    size_top = Column(String(8), nullable=True)
    size_bottom = Column(String(8), nullable=True)
    size_shoe = Column(String(8), nullable=True)

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
# CART
# =========================================================

class CartItem(Base):
    """
    Sepetteki urunler, miktarlariyla birlikte.

    Wishlist'ten farki: wishlist "sonra almak icin biriktirme"
    listesidir ve miktar tasimaz. Sepet "simdi almak istedigim
    urunler ve kac adet" bilgisini tutar. Unique kisit ayni
    urunun iki satir olarak eklenmesini engeller — tekrar
    eklemede miktar artar (bkz. crud.add_to_cart).
    """

    __tablename__ = "cart_items"

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

    quantity = Column(
        Integer,
        nullable=False,
        server_default=text("1"),
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

    product = relationship("Product")

    __table_args__ = (

        UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_cart_user_product",
        ),

        CheckConstraint(
            "quantity > 0",
            name="ck_cart_quantity_positive",
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


# =========================================================
# GARDIROP (KOMBIN / LOOK)
# =========================================================

# Kombin, wishlist ve sepetten FARKLI bir sey: onlar tekil
# urun listeleridir, bu bir KOMPOZISYON. "Lacivert takim +
# beyaz gomlek + siyah loafer" birlikte anlam tasiyor;
# parcalardan biri degisince kombin hala ayni kombin.
#
# Bu yuzden iki tablo var: kombinin kendisi (baslik, sahip)
# ve icindeki parcalar. Tek tabloda tutulsaydi "bu kombinin
# pantolonunu degistir" islemi, kombin kimligini kaybetmeden
# yapilamazdi.

# Parcanin kombindeki rolu. Degistirme akisinin anahtari:
# "bu kombindeki AYAKKABIYI degistir" derken hangi parcanin
# yerine ne konacagini bu alan soyluyor.
#
# Bos birakilabilir: kullanici sohbetten kombin kurarken
# parcalari elle isaretlemiyor, slot sonradan urunun
# kategorisinden tahmin ediliyor.
LOOK_SLOTS = (
    "ust",
    "alt",
    "dis_giyim",
    "ayakkabi",
    "aksesuar",
    "diger",
)


class WardrobeLook(Base):
    """
    Kullanicinin gardirobuna kaydettigi bir kombin.

    source: kombinin nereden geldigi ("chat" = AI asistanin
    onerisinden kuruldu). Sonradan "AI onerisi" rozeti
    gostermek ve hangi girisin ise yaradigini olcmek icin.
    """

    __tablename__ = "wardrobe_looks"

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

    title = Column(
        String(120),
        nullable=False,
    )

    note = Column(
        Text,
        nullable=True,
    )

    source = Column(
        String(32),
        nullable=True,
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

    # Kombin silinince parcalari da silinsin. cascade burada
    # ORM tarafi; DB tarafinda ayrica ondelete="CASCADE" var
    # (ikisi birden gerekli: biri Python'dan, digeri dogrudan
    # SQL ile silmede calisiyor).
    items = relationship(
        "WardrobeLookItem",
        cascade="all, delete-orphan",
        order_by="WardrobeLookItem.position",
    )

    __table_args__ = (

        # Gardirop listesi hep "benim kombinlerim, yeniden
        # eskiye" seklinde okunuyor.
        Index(
            "ix_wardrobe_looks_user_created",
            "user_id",
            "created_at",
        ),
    )


class WardrobeLookItem(Base):
    """
    Bir kombinin icindeki tek parca.

    Unique kisit ayni urunun ayni kombine iki kez
    eklenmesini engelliyor: kombin bir kiyafet listesi,
    alisveris sepeti degil — adet kavrami yok.
    """

    __tablename__ = "wardrobe_look_items"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    look_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "wardrobe_looks.id",
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

    slot = Column(
        String(24),
        nullable=True,
    )

    # Kombin icindeki gorunme sirasi. Parca degistirilince
    # yeni urun eskisinin position'ini devraliyor ki kombin
    # gorsel olarak yerinden oynamasin.
    position = Column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    product = relationship("Product")

    __table_args__ = (

        UniqueConstraint(
            "look_id",
            "product_id",
            name="uq_look_product",
        ),
    )


# =========================================================
# SOSYAL KATMAN — ARKADASLIK / MESAJLASMA / URUN PAYLASIMI
# =========================================================
#
# Uc tablo: friendships, conversations, messages.
#
# Tasarim kararlari asagida her tablonun basinda; en onemli
# ikisi kisaca:
#
#   1. Bir CIFT icin TEK satir. Hem arkadaslikta hem
#      sohbette ayni problem var: A-B ile B-A ayni sey ama
#      naif sema iki satir yazmaya izin verir. Cozum
#      veritabani seviyesinde (bkz. her iki tablonun notu).
#
#   2. Paylasilan urun mesajin KENDI kolonunda, ayri bir
#      tabloda degil (bkz. Message.product_id notu).


FRIENDSHIP_PENDING = "pending"
FRIENDSHIP_ACCEPTED = "accepted"
FRIENDSHIP_DECLINED = "declined"

# ENGELLI. Reddetmekten farki: reddedilen kisi TEKRAR istek
# gonderebiliyor (send_request reddedilmis satiri yeniden
# pending'e cekiyor), engelli gonderemiyor. Yani reddetmek
# erteleme, engelleme gercek durak.
FRIENDSHIP_BLOCKED = "blocked"

FRIENDSHIP_STATUSES = (
    FRIENDSHIP_PENDING,
    FRIENDSHIP_ACCEPTED,
    FRIENDSHIP_DECLINED,
    FRIENDSHIP_BLOCKED,
)


class Friendship(Base):
    """
    Iki kullanici arasindaki arkadaslik iliskisi.

    YON KORUNUYOR, CIFT TEKILLESTIRILIYOR
    requester_id / addressee_id ayri duruyor cunku "kim istek
    gonderdi" bilgisi gerekli: istegi yalnizca ALICI kabul
    edebilmeli, gonderen kendi istegini kabul edememeli.

    Ama iliski aslinda YONSUZ: A-B ile B-A ayni arkadasliktir.
    Naif sema ikisinin de yazilmasina izin verir ve o zaman
    "arkadas miyiz?" sorusu iki satir birden bulur, kabul
    edilen biri reddedilen digeri olabilir.

    Cozum uygulama katmaninda DEGIL veritabaninda:

        CREATE UNIQUE INDEX uq_friendship_pair ON friendships (
            LEAST(requester_id, addressee_id),
            GREATEST(requester_id, addressee_id)
        );

    Boylece A→B varken B→A INSERT'i veritabani tarafindan
    reddediliyor. Uygulama unutsa bile ikinci satir olusamaz.
    (Ayni gerekce wishlist_items'daki UNIQUE(user_id,
    product_id) icin de yazilmisti.)

    REDDEDILEN ISTEK SILINMIYOR
    status='declined' olarak kaliyor. Sebep: silseydik ayni
    kisi tekrar tekrar istek gonderebilirdi ve bu bir taciz
    kanali olurdu. Kayit durunca "zaten reddedilmis" kontrolu
    yapilabiliyor.
    """

    __tablename__ = "friendships"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    requester_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    addressee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(
        String(16),
        nullable=False,
        server_default=text("'pending'"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # Kabul/red zamani. Istegin ne kadar bekledigini ve
    # kabul oranini olcmek icin.
    responded_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # KIM ENGELLEDI.
    #
    # Bir cift icin TEK satir var (uq_friendship_pair) ama
    # engelleme YONLU: A B'yi engellediyse engeli yalnizca A
    # kaldirabilir. Satir paylasildigi icin bu bilgi ayri bir
    # kolonda olmak zorunda — requester_id yetmiyor, istegi
    # B gondermis olabilir.
    #
    # Bu olmadan engellenen kisi kendi engelini kaldirabilirdi.
    blocked_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    requester = relationship("User", foreign_keys=[requester_id])
    addressee = relationship("User", foreign_keys=[addressee_id])

    __table_args__ = (

        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'blocked')",
            name="ck_friendships_status",
        ),

        # blocked_by yalnizca engelli satirlarda dolu olmali.
        # Aksi halde "engelli degil ama engelleyeni var" gibi
        # anlamsiz satirlar birikirdi.
        CheckConstraint(
            "(status = 'blocked' AND blocked_by IS NOT NULL)"
            " OR (status <> 'blocked' AND blocked_by IS NULL)",
            name="ck_friendships_blocked_by",
        ),

        # Kendi kendine arkadaslik istegi gonderilemez.
        CheckConstraint(
            "requester_id <> addressee_id",
            name="ck_friendships_not_self",
        ),

        # "Arkadas listem" sorgusu: benim taraf olduğum ve
        # kabul edilmis satirlar. Iki yonden de aranıyor.
        Index(
            "ix_friendships_addressee_status",
            "addressee_id",
            "status",
        ),

        Index(
            "ix_friendships_requester_status",
            "requester_id",
            "status",
        ),
    )


class Conversation(Base):
    """
    Iki kullanici arasindaki birebir sohbet.

    NEDEN participants TABLOSU YOK
    Yaygin sema conversations + conversation_participants
    seklindedir ve grup sohbetini de destekler. Burada
    istenen acikca BIREBIR yazisma. Katilimci tablosu
    olsaydi "A ile B'nin sohbeti hangisi?" sorusu her
    seferinde iki satirlik bir gruplama/join gerektirirdi:

        SELECT conversation_id FROM conversation_participants
        WHERE user_id IN (:a, :b)
        GROUP BY conversation_id HAVING COUNT(*) = 2

    Iki kolonla ayni soru tek indeks aramasi. Grup sohbeti
    gerekirse o zaman katilimci tablosuna gecilir; simdiden
    onun karmasikligini tasimanin karsiligi yok.

    KANONIK SIRA
    user_low_id / user_high_id, UUID siralamasina gore kucuk
    olan basta. Sira INSERT aninda sabitleniyor, boylece
    (A,B) ve (B,A) ayni satira dusuyor ve UNIQUE kisiti iki
    sohbet acilmasini engelliyor. Arkadaslik tablosundaki
    LEAST/GREATEST indeksiyle ayni fikir; burada kolonlarin
    kendisi sirali oldugu icin sorgu daha basit.

    last_message_at DENORMALIZE
    Gelen kutusu sohbetleri "en son yazilana gore" siralar.
    Bunu her acilista MAX(messages.created_at) ile hesaplamak
    sohbet sayisi kadar agregasyon demek. user_preferences'ta
    da ayni karar verilmisti: turetilmis ozeti yaninda tut,
    her istekte gecmisi yeniden okuma.
    """

    __tablename__ = "conversations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_low_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_high_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # Gelen kutusu siralamasi. Mesaj eklendikce guncelleniyor.
    last_message_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        index=True,
    )

    # SOHBET GIZLEME (arsivleme) — taraf basina.
    #
    # NEDEN BOOLEAN DEGIL ZAMAN DAMGASI
    # Gizleme arsivleme gibi davranmali: yeni mesaj gelince
    # sohbet kendiliginden geri gelmeli. Kural tek satir:
    #
    #     gizli <=> hidden_at IS NOT NULL
    #               AND hidden_at >= last_message_at
    #
    # Yeni mesaj last_message_at'i ileri tasiyor ve sohbet
    # otomatik geri geliyor; bayrak sifirlamak gerekmiyor.
    # Boolean olsaydi bir yerde unutulunca kullanici mesaji
    # HIC gormezdi.
    #
    # Iki ayri kolon: biri gizlerken digerinin gelen kutusuna
    # dokunmamali. Kanonik sira sayesinde hangi kolonun kime
    # ait oldugu belirsiz degil.
    hidden_low_at = Column(DateTime(timezone=True), nullable=True)
    hidden_high_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (

        UniqueConstraint(
            "user_low_id",
            "user_high_id",
            name="uq_conversation_pair",
        ),

        CheckConstraint(
            "user_low_id <> user_high_id",
            name="ck_conversations_not_self",
        ),

        # Kanonik sira DB seviyesinde de garanti: uygulama
        # yanlislikla ters sirada yazarsa satir kabul
        # edilmiyor. UNIQUE kisitinin ise yaramasi buna bagli.
        CheckConstraint(
            "user_low_id < user_high_id",
            name="ck_conversations_canonical_order",
        ),
    )


class Message(Base):
    """
    Bir sohbetteki tek mesaj.

    URUN NEDEN AYRI TABLODA DEGIL
    -----------------------------
    Iki secenek vardi:

      A) messages.product_id  (nullable kolon)   <- SECILEN
      B) message_products     (ayri tablo)

    Secim (A). Gerekceler:

      1. OKUMA YOLU EN SICAK YER. Sohbet acildiginda son N
         mesaj cekiliyor. (A) ile bu tek sorgu + products'a
         tek LEFT JOIN. (B) ile ya ikinci bir sorgu ya da
         satir cogaltan bir join + Python'da gruplama gerekir.
         Mesaj listesi uygulamanin en sik okunan yeri; oraya
         join eklemenin bedeli her acilista odenir.

      2. "EN FAZLA BIR URUN" KURALINI SEMA GARANTI EDIYOR.
         Ozellik "bu urunu arkadasima gonder" — mesaj basina
         tek urun. (B) semasi N urune izin verir ve "aslinda
         bir tane olmali" kurali yalnizca uygulama kodunda
         yasar; biri unutunca arayuz bozulur.

      3. MALIYET YOK. Cogu mesaj duz metin ve product_id NULL
         kalacak. PostgreSQL'de NULL degerler satir basindaki
         null bitmap'te 1 bit tutuyor; ayri bir alan
         ayrilmiyor. Yani "cogu satirda bos duracak" endisesi
         bu semada olcumsuz kaliyor.

    (B) NE ZAMAN DOGRU OLURDU
      - Bir mesaj birden fazla urun tasiyacaksa (ornegin bir
        gardirop kombininin tamami gonderilecekse),
      - ya da ek turleri cogalacaksa (urun + kombin + gorsel
        + siparis). O zaman polimorfik bir "attachments"
        tablosu (A)'nin kolon kolon buyumesinden iyidir.

    Bugunku gereksinim tek urun oldugu icin (A). Ileride
    kombin paylasimi istenirse eklenecek sey nullable bir
    look_id kolonu; iki nullable ek kolon hala attachments
    tablosundan basit.

    BOS MESAJ OLAMAZ
    CHECK ile: metin de urun de yoksa satir kabul edilmiyor.
    Aksi halde bos balonlar olusur ve bunu her cagiran yerde
    ayri ayri kontrol etmek gerekirdi.
    """

    __tablename__ = "messages"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    body = Column(
        Text,
        nullable=True,
    )

    # PAYLASILAN URUN. Bkz. yukaridaki "urun neden ayri
    # tabloda degil" notu.
    #
    # ondelete SET NULL, CASCADE DEGIL: katalogdan bir urun
    # kalkarsa mesaj SILINMEMELI. Insanlarin yazismasi urun
    # kataloguna bagli olamaz; kart yerine "bu urun artik
    # yok" gosterilir.
    product_id = Column(
        String,
        ForeignKey("products.product_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # Okundu bilgisi. Birebir sohbette tek alan yetiyor;
    # grup olsaydi ayri bir okundu tablosu gerekirdi.
    read_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    product = relationship("Product")

    __table_args__ = (

        # Bos mesaj yok: ya metin ya urun (ya da ikisi).
        CheckConstraint(
            "body IS NOT NULL OR product_id IS NOT NULL",
            name="ck_messages_not_empty",
        ),

        # Sohbet acilisi: son mesajlar, yeniden eskiye.
        Index(
            "ix_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),

        # Okunmamis rozeti: bu sohbette bana gelen ve
        # okunmamis mesajlar.
        Index(
            "ix_messages_unread",
            "conversation_id",
            "read_at",
        ),
    )
