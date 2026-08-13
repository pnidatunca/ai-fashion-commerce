import os
from typing import Optional
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text, or_
from sqlalchemy.orm import Session

from .database import engine, get_db
from .models import Product
# FastAPI uygulamasını oluşturuyoruz.
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API: Tüm Ürünleri Listele (Sınırlandırılmış)
@app.get("/api/products")
def get_products(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Product).limit(limit).all()

# API: Kategorileri listele
@app.get("/api/categories")
def get_categories(db: Session = Depends(get_db)):
    categories = db.query(Product.category).distinct().filter(Product.category.isnot(None)).all()
    # categories: [('Shoes',), ('Shirts',), ...] formatından listeye dönüştürüyoruz
    return [c[0] for c in categories]

# API: Ürünleri listele ve arama/filtreleme yap
@app.get("/api/search")
def search_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Product)
    
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                Product.title.ilike(search_pattern),
                Product.brand.ilike(search_pattern),
                Product.category.ilike(search_pattern)
            )
        )
    
    if category:
        query = query.filter(Product.category == category)
        
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
        
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
        
    products = query.limit(50).all()
    return products

# API: Tekil ürün detayını getir
@app.get("/api/products/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return product


# Database bağlantısını test etmek için kullanacağımız endpoint.
@app.get("/api/db-test")
def db_test():

    # Database'e bağlantı açıyoruz.
    with engine.connect() as connection:

        # PostgreSQL'e basit bir test sorgusu gönderiyoruz.
        result = connection.execute(text("SELECT 1"))

        # Database'den gelen sonucu döndürüyoruz.
        return {
            "database": "connected",
            "result": result.scalar()
        }

class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 10

@app.post("/api/semantic-search")
def semantic_search(request: SemanticSearchRequest, db: Session = Depends(get_db)):
    # NOT: Bu uç nokta Phase 6'da yapay zeka destekli vektör aramaya dönüştürülecektir.
    # Şimdilik MVP için fallback olarak klasik arama kullanıyoruz.
    search_pattern = f"%{request.query}%"
    products = db.query(Product).filter(
        or_(
            Product.title.ilike(search_pattern),
            Product.brand.ilike(search_pattern),
            Product.category.ilike(search_pattern)
        )
    ).limit(request.limit).all()
    
    return products

# Frontend dosyalarını sunmak için StaticFiles kullanıyoruz.
# Backend klasöründen bir üst dizine (..) çıkıp frontend klasörüne ulaşıyoruz.
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")