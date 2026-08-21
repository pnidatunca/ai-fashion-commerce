from pydantic import BaseModel, ConfigDict


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