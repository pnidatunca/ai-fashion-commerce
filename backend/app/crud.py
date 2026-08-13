from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Product, Review


# =========================================================
# PRODUCTS
# =========================================================

def get_products(
    db: Session,
    limit: int = 24,
    offset: int = 0,
):
    """
    Urunleri pagination ile getirir.

    Ornek:
    limit=24, offset=0
    -> ilk 24 urun

    limit=24, offset=24
    -> sonraki 24 urun
    """

    statement = (
        select(Product)
        .offset(offset)
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )


def get_product(
    db: Session,
    product_id: str,
):
    """
    Tek bir urunu product_id ile getirir.
    """

    return db.get(
        Product,
        product_id,
    )


# =========================================================
# REVIEWS
# =========================================================

def get_product_reviews(
    db: Session,
    product_id: str,
    limit: int = 50,
    offset: int = 0,
):
    """
    Belirli bir urune ait yorumlari getirir.

    Helpful vote sayisi yuksek yorumlari once gosterir.
    """

    statement = (
        select(Review)
        .where(
            Review.product_id == product_id
        )
        .order_by(
            Review.helpful_votes.desc()
        )
        .offset(offset)
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )


# =========================================================
# CLASSIC SEARCH
# =========================================================

def search_products(
    db: Session,
    query: str,
    limit: int = 24,
    offset: int = 0,
):
    """
    Basit klasik urun aramasi.

    Semantic Search DEGILDIR.

    Title, brand ve category alanlarinda
    case-insensitive arama yapar.
    """

    query = query.strip()

    if not query:
        return []

    search_pattern = f"%{query}%"

    statement = (
        select(Product)
        .where(
            or_(
                Product.title.ilike(
                    search_pattern
                ),
                Product.brand.ilike(
                    search_pattern
                ),
                Product.category.ilike(
                    search_pattern
                ),
            )
        )
        .offset(offset)
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )