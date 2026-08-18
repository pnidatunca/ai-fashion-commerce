from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware

from app import crud, schemas
from app.database import engine, get_db
import requests
from app.models import User
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

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

import requests

@app.get("/exchange-rate")
def get_exchange_rate():

    response = requests.get(
        "https://open.er-api.com/v6/latest/USD"
    )

    data = response.json()

    return {
        "rate": data["rates"]["TRY"]
    }

# =========================================================
# USER REGISTER
# =========================================================

# =========================================================
# USER REGISTER
# =========================================================

@app.post("/auth/register")
def register_user(
    user_data: schemas.RegisterRequest,
    db: Session = Depends(get_db),
):
    # Email daha önce kayıtlı mı?
    existing_user = (
        db.query(User)
        .filter(User.email == user_data.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Bu email adresi zaten kayıtlı.",
        )

    # Şifreyi hashle
    hashed_password = pwd_context.hash(
        user_data.password
    )

    # Yeni kullanıcı
    new_user = User(
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        email=user_data.email,
        gender=user_data.gender,
        age=user_data.age,
        password_hash=hashed_password,
    )

    # Neon'a kaydet
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Hesap başarıyla oluşturuldu.",
        "user": {
            "id": new_user.id,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name,
            "email": new_user.email,
            "gender": new_user.gender,
            "age": new_user.age,
        },
    }