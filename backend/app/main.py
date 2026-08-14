from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware

from app import crud, schemas
from app.database import engine, get_db


app = FastAPI(
    title="AI Fashion Commerce API",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
) 


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def home():
    return {
        "message": "AI Fashion Commerce API çalışıyor"
    }


# =========================================================
# DATABASE TEST
# =========================================================

@app.get("/db-test")
def db_test():
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT 1")
        )

        return {
            "database": "connected",
            "result": result.scalar(),
        }


# =========================================================
# PRODUCTS LIST
# =========================================================
@app.get(
    "/products",
    response_model=list[schemas.ProductResponse],
)
def list_products(
    limit: int = Query(
        default=24,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    category: str | None = Query(
        default=None,
    ),
    db: Session = Depends(get_db),
):
    return crud.get_products(
        db=db,
        limit=limit,
        offset=offset,
        category=category,
    )


# =========================================================
# CLASSIC PRODUCT SEARCH
# =========================================================

# Bu route'u /products/{product_id}'den
# ONCE tanimliyoruz.
#
# Cunku "search" kelimesinin product_id
# olarak algilanmasini istemiyoruz.

@app.get(
    "/products/search",
    response_model=list[schemas.ProductResponse],
)
def search_products(
    q: str = Query(
        min_length=1,
        max_length=200,
    ),
    limit: int = Query(
        default=24,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    return crud.search_products(
        db=db,
        query=q,
        limit=limit,
        offset=offset,
    )


# =========================================================
# PRODUCT DETAIL
# =========================================================

@app.get(
    "/products/{product_id}",
    response_model=schemas.ProductResponse,
)
def product_detail(
    product_id: str,
    db: Session = Depends(get_db),
):
    product = crud.get_product(
        db=db,
        product_id=product_id,
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return product


# =========================================================
# PRODUCT REVIEWS
# =========================================================

@app.get(
    "/products/{product_id}/reviews",
    response_model=list[schemas.ReviewResponse],
)
def product_reviews(
    product_id: str,
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    product = crud.get_product(
        db=db,
        product_id=product_id,
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return crud.get_product_reviews(
        db=db,
        product_id=product_id,
        limit=limit,
        offset=offset,
    )