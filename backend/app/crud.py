from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.models import Product, Review


def get_products(
    db: Session,
    limit: int = 24,
    offset: int = 0,
    category: str | None = None,
):
    statement = select(Product)

    if category:

        category = category.lower()

        if category == "men":
            statement = statement.where(
                Product.category.ilike("%› Men ›%")
            )

        elif category == "women":
            statement = statement.where(
                Product.category.ilike("%› Women ›%")
            )

        elif category == "dress":
            statement = statement.where(
                Product.category.ilike("%› Dresses%")
            )

        elif category == "shirt":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Shirts%"),
                    Product.category.ilike("%› Polos%"),
                )
            )

        elif category == "pants":
            statement = statement.where(
                Product.category.ilike("%› Pants%")
            )

        elif category == "jacket":
            statement = statement.where(
                or_(
                    Product.category.ilike("%Jackets%"),
                    Product.category.ilike("%Coats%"),
                )
            )

        elif category == "shoes":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Shoes ›%"),
                    Product.category.ilike("%› Shoes"),
                )
            )

    statement = (
        statement
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
               Product.title_tr.ilike(
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

def semantic_search_products(
    db: Session,
    query_embedding: list[float],
    limit: int = 10,
    offset: int = 0,
    category: str | None = None,
    color: str | None = None,
    gender: str | None = None,
):
    """
    Urunleri pgvector cosine distance ile anlamsal olarak siralar.

    query_embedding:
        Kullanici sorgusunun Gemini ile uretilmis 1536 boyutlu vector'u.

    category:
        Opsiyonel giysi tipi filtresi (dress, shirt, pants, jacket, shoes).
        "men"/"women" da kabul edilir (classic category filtering ile uyum icin).

    gender:
        Opsiyonel, category'den bagimsiz cinsiyet filtresi (men/women).
        Boylece "erkek gomlek" gibi sorgularda hem giysi tipi hem de
        cinsiyet ayni anda filtrelenebilir.
    """

    distance = (
        Product.search_embedding
        .cosine_distance(query_embedding)
        .label("distance")
    )

    statement = (
        select(
            Product,
            distance,
        )
        .where(
            Product.search_embedding.is_not(None)
        )
    )

    # =====================================================
    # CATEGORY FILTER
    # =====================================================

    if category:

        category = category.lower()

        if category == "men":
            statement = statement.where(
                Product.category.ilike("%› Men ›%")
            )

        elif category == "women":
            statement = statement.where(
                Product.category.ilike("%› Women ›%")
            )

        elif category == "dress":
            statement = statement.where(
                Product.category.ilike("%› Dresses%")
            )

        elif category == "shirt":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Shirts%"),
                    Product.category.ilike("%› Polos%"),
                    Product.category.ilike("%T-Shirts%"),
                    Product.category.ilike("%Tops%"),
                    Product.category.ilike("%Tees%"),
                    Product.category.ilike("%Blouses%"),
                )
            )

        elif category == "pants":
            statement = statement.where(
                Product.category.ilike("%› Pants%")
            )

        elif category == "jacket":
            statement = statement.where(
                or_(
                    Product.category.ilike("%Jackets%"),
                    Product.category.ilike("%Coats%"),
                )
            )

        elif category == "shoes":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Shoes ›%"),
                    Product.category.ilike("%› Shoes"),
                )
            )

    # =====================================================
    # GENDER FILTER
    # =====================================================

    # category zaten "men"/"women" degerlerini kabul ediyor,
    # ama tek basli oldugu icin "shirt" gibi bir giysi tipiyle
    # ayni anda kullanilamiyor. gender, category'den bagimsiz
    # calisarak "erkek gomlek" gibi sorgularda ikisini birlikte
    # filtrelemeyi saglar.

    if gender:

        gender = gender.lower()

        if gender == "men":
            statement = statement.where(
                Product.category.ilike("%› Men ›%")
            )

        elif gender == "women":
            statement = statement.where(
                Product.category.ilike("%› Women ›%")
            )

    # =====================================================
    # COLOR FILTER
    # =====================================================

    # Renk kelimesi urun basliginda birebir gecmiyor diye
    # urunu tamamen elemek yerine, renk eslesen urunleri
    # siralamada one alan yumusak bir agirlik uyguluyoruz.
    # Boylece kategori+cinsiyet ile tutarli ama basliginda
    # rengi gecmeyen urunler de sonuclardan tamamen kaybolmuyor.

    ranking_expression = distance

    if color:

        color = color.lower()

        color_terms = {
            "white": ["white", "beyaz"],
            "black": ["black", "siyah"],
            "red": ["red", "kırmızı", "kirmizi"],
            "blue": ["blue", "mavi"],
            "navy": ["navy", "lacivert"],
            "green": ["green", "yeşil", "yesil"],
            "yellow": ["yellow", "sarı", "sari"],
            "pink": ["pink", "pembe"],
            "purple": ["purple", "mor"],
            "gray": ["gray", "grey", "gri"],
            "brown": ["brown", "kahverengi"],
            "beige": ["beige", "bej"],
        }

        terms = color_terms.get(
            color,
            [color],
        )

        color_conditions = []

        for term in terms:

            pattern = f"%{term}%"

            color_conditions.extend([
                Product.title.ilike(pattern),
                Product.title_tr.ilike(pattern),
            ])

        color_match = or_(*color_conditions)

        ranking_expression = case(
            (color_match, distance),
            else_=distance + 0.15,
        )

    # =====================================================
    # VECTOR RANKING
    # =====================================================

    statement = (
        statement
        .order_by(ranking_expression)
        .offset(offset)
        .limit(limit)
    )

    rows = db.execute(statement).all()

    results = []

    for product, cosine_distance in rows:

        similarity_score = (
            1 - float(cosine_distance)
        )

        results.append(
            {
                "product": product,
                "similarity_score": similarity_score,
            }
        )

    return results