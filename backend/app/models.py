from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from sqlalchemy.orm import relationship

from .database import Base


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