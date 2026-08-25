import logging
import os
import secrets
import uuid
from datetime import datetime, timezone

import requests
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import (
    crud,
    feed,
    query_engine,
    schemas,
    search_service,
    style_customize,
    style_engine,
)
from app.database import engine, get_db
from app.models import (
    INTERACTION_DISLIKE,
    INTERACTION_LIKE,
    INTERACTION_QUICK_BUY,
    INTERACTION_UNLIKE,
    CartItem,
    User,
)

logger = logging.getLogger(__name__)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

from app.embeddings import embed_query, generate_embedding

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
# VERITABANI ERISILEMEDIGINDE
# =========================================================

@app.exception_handler(OperationalError)
def database_unavailable(request, exc):
    """
    Veritabanina ulasilamadiginda 503 doner.

    ONCEDEN NE OLUYORDU: uc her IP icin 10 saniye bekleyip
    (Neon uc uc IP'ye cozuluyor, toplam 30 saniye) cirilciplak
    bir "500 Internal Server Error" donduruyordu. Arayuz de
    "Backend baglantisini kontrol et" yaziyordu — oysa backend
    ayakta, ulasilamayan sey VERITABANI. Yanlis yeri
    gostermek arizayi aramayi uzatiyor.

    503 + net mesaj iki isi birden yapiyor:

      - dogru katmani isaret ediyor
      - arayuz 500 (kod hatasi) ile 503 (servis yok) ayrimini
        yapabiliyor ve kullaniciya dogru seyi soyluyor

    Neon ucretsiz katmanda kullanilmadiginda askiya aliniyor
    ve ilk istekte uyanmasi birkac saniye suruyor; bu yuzden
    "tekrar dene" onerisi gercekten ise yariyor.
    """

    logger.warning(
        "Veritabanina ulasilamadi: %s %s",
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Veritabanına şu an ulaşılamıyor. "
                "Birkaç saniye sonra tekrar dene."
            ),
            "error": "database_unavailable",
        },
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
    sort: str | None = Query(
        default=None,
        description=(
            "featured | price_asc | price_desc | rating | discount"
        ),
    ),
    db: Session = Depends(get_db),
):
    """
    Urun listesi.

    Siralama sunucuda yapiliyor: sonsuz akista tarayici
    tarafinda siralamak, yalnizca o ana kadar yuklenmis
    urunleri siralamak demektir ve yanlis sonuc verir.
    """

    return crud.get_products(
        db=db,
        limit=limit,
        offset=offset,
        category=category,
        sort=sort,
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
    sort: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return crud.search_products(
        db=db,
        query=q,
        limit=limit,
        offset=offset,
        sort=sort,
    )

# =========================================================
# Semantic search endpoint
# =========================================================
@app.get(
    "/products/semantic-search",
    response_model=list[schemas.SemanticProductResponse],
)
def semantic_search(
    q: str = Query(
        ...,
        min_length=1,
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    category: str | None = Query(
        default=None,
    ),
    color: str | None = Query(
        default=None,
    ),
    gender: str | None = Query(
        default=None,
    ),
    db: Session = Depends(get_db),
):
    query_embedding = generate_embedding(q)

    results = crud.semantic_search_products(
        db=db,
        query_embedding=query_embedding,
        limit=limit,
        offset=offset,
        category=category,
        color=color,
        gender=gender,
    )

    response = []

    for item in results:
        product = item["product"]

        product_data = schemas.ProductResponse.model_validate(
            product
        ).model_dump()

        product_data["similarity_score"] = item[
            "similarity_score"
        ]

        response.append(product_data)

    return response

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
        address=user_data.address,
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
            "address": new_user.address,
        },
    }


# =========================================================
# USER LOGIN
# =========================================================

@app.post("/auth/login")
def login_user(
    user_data: schemas.LoginRequest,
    db: Session = Depends(get_db),
):

    user = (
        db.query(User)
        .filter(User.email == user_data.email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="E-posta veya şifre hatalı.",
        )

    password_correct = pwd_context.verify(
        user_data.password,
        user.password_hash,
    )

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="E-posta veya şifre hatalı.",
        )

    return {
        "message": "Giriş başarılı.",
        "user": {
            "id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "gender": user.gender,
            "age": user.age,
            "address": user.address,
        },
    }


# =========================================================
# KIMLIK
# =========================================================

# GECICI COZUM
#
# Projede henuz JWT / oturum yok; /auth/login sadece
# kullanici objesini donuyor ve frontend bunu localStorage'da
# tutuyor. Etkilesim kaydi user_id gerektirdigi icin kimligi
# X-User-Id basligindan aliyoruz.
#
# Bu baslik istemci tarafindan degistirilebilir, yani
# TAKLIT EDILEBILIR. Uretime cikmadan once burasi JWT
# dogrulamasina cevrilmeli. Tum uclar bu iki dependency'yi
# kullandigi icin degisiklik yalnizca bu dosyayi etkiler.


def get_current_user(
    x_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
    ),
    db: Session = Depends(get_db),
) -> User:
    """Giris zorunlu uclar icin."""

    if not x_user_id:
        raise HTTPException(
            status_code=401,
            detail="Bu islem icin giris yapmalisin.",
        )

    try:
        user_uuid = uuid.UUID(x_user_id)

    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Gecersiz kullanici kimligi.",
        )

    user = db.get(User, user_uuid)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Kullanici bulunamadi.",
        )

    return user


def get_optional_user(
    x_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
    ),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Giris zorunlu olmayan uclar icin.

    Gecersiz kimlik hata vermez, misafir olarak devam eder.
    """

    if not x_user_id:
        return None

    try:
        user_uuid = uuid.UUID(x_user_id)

    except ValueError:
        return None

    return db.get(User, user_uuid)


# =========================================================
# HESAP YONETIMI
# =========================================================

def _account_response(user: User) -> schemas.AccountResponse:
    """Login/register'in dondurdugu kullanici sekliyle
    birebir ayni; frontend tek bir güncelleme yardimcisini
    (updateSessionUser) her yerde kullanabilir."""

    return schemas.AccountResponse(
        id=str(user.id),
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        gender=user.gender,
        age=user.age,
        address=user.address,
    )


@app.get(
    "/auth/me",
    response_model=schemas.AccountResponse,
)
def get_my_account(
    user: User = Depends(get_current_user),
):
    """Hesabım ekraninin acilista okudugu, sunucudaki
    guncel bilgi (localStorage'daki onbellege degil)."""

    return _account_response(user)


@app.patch(
    "/auth/profile",
    response_model=schemas.AccountResponse,
)
def update_profile(
    payload: schemas.UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ad, soyad ve temel profil alanlarini gunceller.

    E-posta ve sifre burada DEGISTIRILMEZ; onlar ayri, daha
    siki dogrulamali uclardan (change-email, change-password)
    yonetilir."""

    user.first_name = payload.first_name
    user.last_name = payload.last_name
    user.gender = payload.gender
    user.age = payload.age
    user.address = payload.address

    db.commit()
    db.refresh(user)

    return _account_response(user)


@app.patch(
    "/auth/email",
    response_model=schemas.AccountResponse,
)
def change_email(
    payload: schemas.ChangeEmailRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    E-posta degisikligi.

    GUVENLIK: X-User-Id basligi tek basina kimlik kaniti
    degil (bkz. get_current_user docstring'i), bu yuzden bu
    hassas islem icin mevcut sifre ayrica dogrulanir.

    NOT: e-posta dogrulama (yeni adrese mail/kod gonderme)
    altyapisi yok. Sifre doğrulanir doğrulanmaz e-posta
    DOGRUDAN degisir; sahte bir "onay maili" akisi taklit
    edilmiyor.
    """

    if not pwd_context.verify(
        payload.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Mevcut şifre hatalı.",
        )

    if payload.new_email == user.email.lower():
        raise HTTPException(
            status_code=422,
            detail="Bu zaten kayıtlı e-posta adresin.",
        )

    # Buyuk/kucuk harf farkina ragmen ayni adresi yakalamak
    # icin ilike (register/login tarafinda henuz normalize
    # edilmedigi icin buradaki kontrol case-insensitive).
    existing = (
        db.query(User)
        .filter(User.email.ilike(payload.new_email))
        .first()
    )

    if existing is not None:
        raise HTTPException(
            status_code=400,
            detail="Bu email adresi zaten kayıtlı.",
        )

    user.email = payload.new_email

    db.commit()
    db.refresh(user)

    return _account_response(user)


@app.post("/auth/change-password")
def change_password(
    payload: schemas.ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sifre degisikligi.

    Mevcut sifre hash ile dogrulanmadan degisiklik YAPILMAZ.
    Yeni sifrenin gucu ve tekrarla eslesmesi schema'da
    (ChangePasswordRequest) zaten kontrol edildi.

    Sifre hicbir zaman response'a dahil edilmez; sadece bir
    basari mesaji doner.
    """

    if not pwd_context.verify(
        payload.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Mevcut şifre hatalı.",
        )

    user.password_hash = pwd_context.hash(
        payload.new_password
    )

    db.commit()

    return {"message": "Şifren başarıyla değiştirildi."}


def _parse_exclude(raw: str | None) -> list[str]:
    """
    "A,B,C" -> ["A", "B", "C"]

    Frontend ekranda duran kartlari tekrar almamak icin
    gonderir. Sorguyu sisirmemesi icin 200 ile siniriyoruz.
    """

    if not raw:
        return []

    ids = [
        part.strip()
        for part in raw.split(",")
        if part.strip()
    ]

    return ids[:200]


# =========================================================
# EXPLORE FEED
# =========================================================

@app.get(
    "/explore",
    response_model=schemas.ExploreResponse,
)
def explore_feed(
    limit: int = Query(
        default=12,
        ge=1,
        le=48,
    ),
    exclude: str | None = Query(
        default=None,
        description="Virgulle ayrilmis, ekranda duran urun kimlikleri",
    ),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Kesfet akisi.

    Giris yapmis kullanicida BEGENMEDIM dedigi ve zaten
    favorilerinde olan urunler haric tutulur.
    """

    user_id = user.id if user else None

    exclude_ids = _parse_exclude(exclude)

    items = crud.get_explore_feed(
        db=db,
        user_id=user_id,
        limit=limit,
        exclude_product_ids=exclude_ids,
    )

    # Ekranda duran kartlar haric, geriye kac urun kaldi
    remaining = crud.count_explore_pool(
        db=db,
        user_id=user_id,
        exclude_product_ids=exclude_ids,
    )

    return schemas.ExploreResponse(
        items=items,
        exhausted=len(items) == 0,
        remaining=remaining,
    )


# =========================================================
# INTERACTIONS
# =========================================================

@app.post(
    "/interactions",
    response_model=schemas.InteractionAccepted,
    status_code=201,
)
def create_interaction(
    payload: schemas.InteractionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Tek etkilesim kaydi.

    LIKE geldiginde wishlist de guncellenir: "kalplenen urun
    favorilere eklenir" kurali hangi uc kullanilirsa
    kullanilsin bozulmaz.
    """

    recorded = crud.record_interactions(
        db=db,
        user_id=user.id,
        items=[payload],
    )

    if payload.interaction_type == INTERACTION_LIKE:

        crud.add_to_wishlist(
            db=db,
            user_id=user.id,
            product_id=payload.product_id,
        )

    elif payload.interaction_type == INTERACTION_UNLIKE:

        crud.remove_from_wishlist(
            db=db,
            user_id=user.id,
            product_id=payload.product_id,
        )

    return schemas.InteractionAccepted(
        recorded=len(recorded),
        in_wishlist=crud.is_in_wishlist(
            db=db,
            user_id=user.id,
            product_id=payload.product_id,
        ),
        wishlist_count=crud.get_wishlist_count(
            db=db,
            user_id=user.id,
        ),
    )


@app.post(
    "/interactions/batch",
    response_model=schemas.InteractionAccepted,
    status_code=201,
)
def create_interactions_batch(
    payload: schemas.InteractionBatchCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Toplu etkilesim kaydi.

    Ozellikle VIEW olaylari icindir: her kart gorunumu icin
    ayri HTTP istegi atmak yerine frontend biriktirip
    toplu gonderir.
    """

    recorded = crud.record_interactions(
        db=db,
        user_id=user.id,
        items=payload.items,
    )

    return schemas.InteractionAccepted(
        recorded=len(recorded),
    )


@app.get("/me/interactions/stats")
def my_interaction_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Kullanicinin etkilesim dagilimi.

    Egitim verisinin ne kadar biriktigini gormek icin.
    """

    counts = crud.get_interaction_counts(
        db=db,
        user_id=user.id,
    )

    return {
        "user_id": str(user.id),
        "counts": counts,
        "total": sum(counts.values()),
        "wishlist_count": crud.get_wishlist_count(
            db=db,
            user_id=user.id,
        ),
    }


# =========================================================
# WISHLIST
# =========================================================

# DIKKAT: /wishlist/ids rotasi /wishlist/{product_id}
# ile cakismamasi icin ondan ONCE tanimlanmali.

@app.get(
    "/wishlist/ids",
    response_model=schemas.WishlistIdsResponse,
)
def wishlist_ids(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sadece urun kimlikleri.

    Sayfa acilisinda butun kalp ikonlarinin durumunu tek
    hafif istekle dolduruyoruz.
    """

    ids = crud.get_wishlist_product_ids(
        db=db,
        user_id=user.id,
    )

    return schemas.WishlistIdsResponse(
        product_ids=ids,
        count=len(ids),
    )


@app.get(
    "/wishlist",
    response_model=list[schemas.WishlistItemResponse],
)
def list_wishlist(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Favori listesi, urun detaylari ile."""

    return crud.get_wishlist(
        db=db,
        user_id=user.id,
        limit=limit,
        offset=offset,
    )


@app.post(
    "/wishlist/{product_id}",
    response_model=schemas.InteractionAccepted,
    status_code=201,
)
def add_wishlist_item(
    product_id: str,
    source: schemas.InteractionSource = Query(
        default="explore",
    ),
    position: int | None = Query(
        default=None,
        ge=0,
        le=10_000,
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Favorilere ekler ve LIKE etkilesimini kaydeder.

    Iki islem birlikte yapilir: wishlist anlik durumu,
    user_interactions ise egitim verisi icin gecmisi tutar.
    """

    product = crud.get_product(db=db, product_id=product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Urun bulunamadi.",
        )

    crud.add_to_wishlist(
        db=db,
        user_id=user.id,
        product_id=product_id,
    )

    recorded = crud.record_interactions(
        db=db,
        user_id=user.id,
        items=[
            schemas.InteractionCreate(
                product_id=product_id,
                interaction_type=INTERACTION_LIKE,
                source=source,
                position=position,
            )
        ],
    )

    return schemas.InteractionAccepted(
        recorded=len(recorded),
        in_wishlist=True,
        wishlist_count=crud.get_wishlist_count(
            db=db,
            user_id=user.id,
        ),
    )


@app.delete(
    "/wishlist/{product_id}",
    response_model=schemas.InteractionAccepted,
)
def remove_wishlist_item(
    product_id: str,
    source: schemas.InteractionSource = Query(
        default="wishlist",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Favorilerden cikarir ve UNLIKE etkilesimini kaydeder.

    UNLIKE, DISLIKE ile ayni sey DEGILDIR: urun feed'den
    kalici olarak dislanmaz, sadece favorilerden cikar.
    """

    removed = crud.remove_from_wishlist(
        db=db,
        user_id=user.id,
        product_id=product_id,
    )

    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Bu urun favorilerinde degil.",
        )

    recorded = crud.record_interactions(
        db=db,
        user_id=user.id,
        items=[
            schemas.InteractionCreate(
                product_id=product_id,
                interaction_type=INTERACTION_UNLIKE,
                source=source,
            )
        ],
    )

    return schemas.InteractionAccepted(
        recorded=len(recorded),
        in_wishlist=False,
        wishlist_count=crud.get_wishlist_count(
            db=db,
            user_id=user.id,
        ),
    )


# =========================================================
# SEPET
# =========================================================
#
# Wishlist'ten farki: sepet "simdi almak istedigim urunler ve
# kac adet" bilgisini tutar, tek seferde COKLU urun odemesi
# icindir. Hizli Al (quick-order) tek urunluk anlik satin
# almayi karsilar; ikisi birlikte var olabilir.

def _cart_summary(items: list[CartItem]):
    """Toplam adet ve ara toplami tek yerden hesaplar —
    dort ayri endpoint'te aynen tekrarlanmasin diye."""

    total_quantity = sum(item.quantity for item in items)

    subtotal = sum(
        float(item.product.price or 0) * item.quantity
        for item in items
    )

    return total_quantity, subtotal


@app.get(
    "/cart",
    response_model=schemas.CartSummaryResponse,
)
def view_cart(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sepet paneli ve header rozeti bu tek uctan beslenir."""

    items = crud.get_cart(db=db, user_id=user.id)

    total_quantity, subtotal = _cart_summary(items)

    return schemas.CartSummaryResponse(
        items=items,
        total_quantity=total_quantity,
        subtotal=subtotal,
    )


# DIKKAT: /cart/checkout, /cart/{product_id} ile cakismamasi
# icin ondan ONCE tanimlanmali (wishlist/ids ile ayni sebep).

@app.post(
    "/cart/checkout",
    response_model=schemas.CartCheckoutResponse,
    status_code=201,
)
def checkout_cart(
    payload: schemas.CartCheckoutRequest = schemas.CartCheckoutRequest(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sepetteki TUM urunleri tek seferde 'satin alir'.

    Hizli Al'daki (quick_order) ayni mantik: gercek bir odeme
    saglayicisi yok, kart bilgisi alinmiyor. Her urun icin
    QUICK_BUY etkilesimi kaydedilir (ML acisindan ayni
    agirlikta bir satin alma sinyali) ve urun favorilerde
    kalmiyor.

    ONEMLI: response nesnesi sepet BOSALTILMADAN ONCE
    olusturuluyor. SQLAlchemy session'i her commit'te nesneleri
    expire ediyor; clear_cart'in kendi commit'i sonrasi bu
    nesnelere tekrar erisilirse ObjectDeletedError alinir.
    """

    items = crud.get_cart(db=db, user_id=user.id)

    if not items:
        raise HTTPException(
            status_code=422,
            detail="Sepetin boş.",
        )

    for item in items:
        if item.product.price is None or item.product.price <= 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{item.product.title} için fiyat bilgisi "
                    "yok, ödeme yapılamıyor."
                ),
            )

    recorded_total = 0

    for item in items:

        recorded = crud.record_interactions(
            db=db,
            user_id=user.id,
            items=[
                schemas.InteractionCreate(
                    product_id=item.product_id,
                    interaction_type=INTERACTION_QUICK_BUY,
                    source=payload.source or "cart",
                )
            ],
        )

        recorded_total += len(recorded)

        crud.remove_from_wishlist(
            db=db,
            user_id=user.id,
            product_id=item.product_id,
        )

    total_quantity, subtotal = _cart_summary(items)

    order_number = _build_order_number()

    response = schemas.CartCheckoutResponse(
        order_number=order_number,
        items=items,
        total_quantity=total_quantity,
        subtotal=subtotal,
        recorded=recorded_total,
        toast=schemas.ToastMessage(
            title="Siparişin alındı",
            message=(
                f"{order_number} · {total_quantity} ürün · "
                "Benzer parçalar akışında öne çıkarılacak."
            ),
            tone="success",
        ),
    )

    # Sepeti bosalt ve zevk profilini tazele — nesneler
    # yukarida zaten Pydantic modeline kopyalandigi icin bu
    # commit'lerin onlari expire etmesi bir sorun degil.
    crud.clear_cart(db=db, user_id=user.id)
    crud.refresh_taste_profile(db, user.id)

    return response


@app.post(
    "/cart/{product_id}",
    response_model=schemas.CartSummaryResponse,
    status_code=201,
)
def add_cart_item(
    product_id: str,
    payload: schemas.AddToCartRequest = schemas.AddToCartRequest(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sepete ekler. Zaten sepetteyse miktar ARTAR (ustune
    eklenir), mutlak degere ayarlamak icin PATCH kullanilir.
    """

    product = crud.get_product(db=db, product_id=product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Ürün bulunamadı.",
        )

    if product.price is None or product.price <= 0:
        raise HTTPException(
            status_code=422,
            detail="Bu ürünün fiyat bilgisi yok, sepete eklenemez.",
        )

    crud.add_to_cart(
        db=db,
        user_id=user.id,
        product_id=product_id,
        quantity=payload.quantity,
    )

    items = crud.get_cart(db=db, user_id=user.id)

    total_quantity, subtotal = _cart_summary(items)

    return schemas.CartSummaryResponse(
        items=items,
        total_quantity=total_quantity,
        subtotal=subtotal,
    )


@app.patch(
    "/cart/{product_id}",
    response_model=schemas.CartSummaryResponse,
)
def update_cart_item(
    product_id: str,
    payload: schemas.UpdateCartQuantityRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Miktari MUTLAK bir degere ayarlar. 0 gonderilirse urun sepetten cikar."""

    updated = crud.set_cart_quantity(
        db=db,
        user_id=user.id,
        product_id=product_id,
        quantity=payload.quantity,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Bu ürün sepetinde değil.",
        )

    items = crud.get_cart(db=db, user_id=user.id)

    total_quantity, subtotal = _cart_summary(items)

    return schemas.CartSummaryResponse(
        items=items,
        total_quantity=total_quantity,
        subtotal=subtotal,
    )


@app.delete(
    "/cart/{product_id}",
    response_model=schemas.CartSummaryResponse,
)
def remove_cart_item(
    product_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    removed = crud.remove_from_cart(
        db=db,
        user_id=user.id,
        product_id=product_id,
    )

    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Bu ürün sepetinde değil.",
        )

    items = crud.get_cart(db=db, user_id=user.id)

    total_quantity, subtotal = _cart_summary(items)

    return schemas.CartSummaryResponse(
        items=items,
        total_quantity=total_quantity,
        subtotal=subtotal,
    )


# =========================================================
# ML EGITIM VERISI
# =========================================================

@app.get(
    "/ml/interactions",
    response_model=list[schemas.InteractionResponse],
)
def ml_interactions(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    since: datetime | None = Query(default=None),
    x_ml_token: str | None = Header(
        default=None,
        alias="X-ML-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Butun kullanicilarin ham etkilesim kaydi.

    Bu uc TUM kullanicilarin verisini dondurur, yani kisisel
    veri icerir. .env icindeki ML_EXPORT_TOKEN ile korunur;
    token tanimli degilse uc kapalidir.

    Toplu egitim verisi icin HTTP yerine
    scripts/07_export_training_data.py kullanmak daha
    verimlidir (dogrudan veritabanindan okur).
    """

    expected = os.getenv("ML_EXPORT_TOKEN")

    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "ML export ucu yapilandirilmadi. "
                ".env icine ML_EXPORT_TOKEN ekle."
            ),
        )

    if not x_ml_token or not secrets.compare_digest(
        x_ml_token,
        expected,
    ):
        raise HTTPException(
            status_code=403,
            detail="Gecersiz ML token.",
        )

    return crud.get_training_interactions(
        db=db,
        limit=limit,
        offset=offset,
        since=since,
    )


# =========================================================
# AI KISISELLESTIRME KATMANI  (/api)
# =========================================================

api = APIRouter(prefix="/api", tags=["ai"])


def _archetype_options(db: Session):
    """
    8 stil karti + her birinin GERCEK havuz sayisi.

    Havuz sayisini gostermek bilincli bir karar: katalog
    kapsami cok dengesiz. Kullanici "Y2K" secip bos bir
    akisla karsilasirsa sistemin bozuk oldugunu dusunur.
    Sayiyi onceden gormek hem durust hem de daha iyi secim
    yapmasini sagliyor.
    """

    options = []

    for archetype in style_engine.ARCHETYPES:

        profile = style_engine.ARCHETYPE_PROFILES[archetype]

        pool = feed.count_style_pool(db, archetype)

        options.append(
            schemas.ArchetypeOption(
                id=archetype,
                emoji=profile["emoji"],
                label=profile["label"],
                short_label=profile["short_label"],
                tagline=profile["tagline"],
                description=profile["description"],
                image_url=profile["image_url"],
                pool_count=pool,
                is_thin=pool < style_engine.THIN_POOL_THRESHOLD,
            )
        )

    return options


def _resolve_styles(user, db: Session, override):
    """
    Hangi tarzlar kullanilacak?

    1. Istekte acikca belirtilmisse onlar (misafir
       kullanici secimini localStorage'da tutuyor)
    2. Giris yapmissa kayitli tercihi
    3. Hicbiri yoksa bos -> kisisellestirme yapilmaz
    """

    if override:
        cleaned = style_engine.normalize_selected_styles(override)
        if cleaned:
            return cleaned

    if user is None:
        return []

    return crud.selected_styles_for(db, user.id)


def _parse_styles_param(raw):
    """"streetwear,y2k" -> ["streetwear", "y2k"]"""

    if not raw:
        return []

    return [part.strip() for part in raw.split(",") if part.strip()]


# ---------------------------------------------------------
# TARZ SECIMI
# ---------------------------------------------------------

@api.get(
    "/archetypes",
    response_model=schemas.ArchetypeListResponse,
)
def list_archetypes(
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Onboarding modalinin gosterecegi 8 stil karti.

    Giris yapmis kullanicinin mevcut secimi de doner ki
    modal tekrar tekrar acilmasin.
    """

    selected = []

    if user is not None:
        selected = crud.selected_styles_for(db, user.id)

    return schemas.ArchetypeListResponse(
        options=_archetype_options(db),
        selected=selected,
        min_choices=style_engine.MIN_SELECTED_STYLES,
        max_choices=style_engine.MAX_SELECTED_STYLES,
    )


# ---------------------------------------------------------
# OZELLESTIR  (embedding/LLM tabanli stil profili)
# ---------------------------------------------------------
#
# style_engine.py'deki 8 arketiplik icerik-tabanli skorlamadan
# FARKLI bir yol: burada statik bir if-else filtre yok, kullanici
# secimleri dogal dil promptuna donusup Gemini embedding'e
# gidiyor ve urun embeddingleriyle (pgvector) anlamsal olarak
# karsilastiriliyor — bkz. style_customize.py docstring'i.
#
# Giris SART DEGIL: misafir de "Özelleştir" akisini deneyebilir,
# tipki arketip secimi gibi.

@api.post(
    "/style-customize",
    response_model=schemas.StyleCustomizeResponse,
)
def style_customize_endpoint(
    payload: schemas.StyleCustomizeRequest,
    db: Session = Depends(get_db),
):
    """
    Yas/cinsiyet/renk/tarz secimlerinden bir stil profili
    promptu kurar, Gemini ile embed eder ve en yakin urunleri
    (cosine distance) doner.

    Donen 'prompt' alani seffaflik icindir: kullanici hangi
    metnin AI'a gonderildigini gorebilir.
    """

    prompt = style_customize.build_style_profile_prompt(
        age=payload.age,
        gender=payload.gender,
        colors=payload.colors,
        styles=payload.styles,
    )

    embedding = style_customize.embed_style_profile(prompt)

    gender_filter = style_customize.resolve_gender_filter(
        payload.gender
    )

    results = crud.semantic_search_products(
        db=db,
        query_embedding=embedding,
        limit=24,
        gender=gender_filter,
    )

    items = []

    for result in results:

        product_data = schemas.ProductResponse.model_validate(
            result["product"]
        ).model_dump()

        product_data["similarity_score"] = result[
            "similarity_score"
        ]

        items.append(product_data)

    return schemas.StyleCustomizeResponse(
        prompt=prompt,
        items=items,
        count=len(items),
    )


@api.post(
    "/initial-style",
    response_model=schemas.InitialStyleResponse,
    status_code=201,
)
def set_initial_style(
    payload: schemas.InitialStyleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Tarz secimini kaydeder (cold start cozumu).

    Iki sey yapar:
      - user_preferences.selected_styles guncellenir
      - user_interactions'a INITIAL_STYLE olayi yazilir

    Misafir kullanici bu ucu cagirmaz; secimini
    localStorage'da tutar ve giris yaptiginda frontend
    burayi bir kez cagirir.
    """

    try:
        preference = crud.set_selected_styles(
            db=db,
            user_id=user.id,
            styles=payload.selected_styles,
        )

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    styles = list(preference.selected_styles or [])

    labels = [
        style_engine.style_label(style) for style in styles
    ]

    # Secili tarzlarin BIRLESIK havuzu (tekil urun sayisi).
    # Tek tek toplamak yanlis olur: ayni urun iki tarzda da
    # esigi gecebilir.
    matched = feed.count_combined_pool(db, styles)

    if len(labels) == 1:
        message = f"{labels[0]} tarzına göre akışın hazırlandı."
    else:
        message = (
            f"{' + '.join(labels)} tarzlarına göre "
            f"akışın hazırlandı."
        )

    return schemas.InitialStyleResponse(
        selected_styles=styles,
        primary_label=labels[0],
        labels=labels,
        message=message,
        matched_products=matched,
        is_thin=matched < style_engine.THIN_POOL_THRESHOLD,
    )


# ---------------------------------------------------------
# AI FEED  (cursor tabanli sonsuz akis)
# ---------------------------------------------------------

@api.get(
    "/explore",
    response_model=schemas.AiExploreResponse,
)
def ai_explore(
    limit: int = Query(default=12, ge=1, le=48),
    cursor: str | None = Query(
        default=None,
        description=(
            "Onceki yanittaki meta.next_cursor. Sonsuz akis "
            "bunu gonderir; sayfa numarasi YOK."
        ),
    ),
    styles: str | None = Query(
        default=None,
        description=(
            "Virgulle ayrilmis tarzlar. Misafir kullanicinin "
            "localStorage'daki secimi icin."
        ),
    ),
    exclude: str | None = Query(
        default=None,
        description="Geriye donuk uyum; cursor tercih edilir.",
    ),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    AI skorlu Kesfet akisi — CURSOR TABANLI.

    Sayfa numarasi ve OFFSET yok. Her yanit
    `meta.next_cursor` doner; istemci onu bir sonraki
    istekte aynen geri gonderir.

    Neden OFFSET degil: OFFSET her sayfada onceki satirlari
    yeniden tarar (maliyet buyur) ve arada yeni bir
    etkilesim olursa siralama kayar; kullanici ayni urunu
    iki kez gorur veya bazi urunler hic gorunmez.
    Keyset pagination bu iki problemi de yasamaz.

    Siralama: secili tarzlarin en iyi skoru + cok yonluluk
    bonusu + kullanicinin begeni gecmisinden gelen bonuslar.
    Slotlarin %25'i kesif icin ayrilir.
    """

    user_id = user.id if user else None

    resolved = _resolve_styles(
        user,
        db,
        _parse_styles_param(styles),
    )

    items, meta = feed.get_feed(
        db=db,
        user_id=user_id,
        selected_styles=resolved,
        limit=limit,
        cursor_token=cursor,
        exclude_ids=_parse_exclude(exclude),
    )

    remaining = feed.count_pool(db=db, user_id=user_id)

    return schemas.AiExploreResponse(
        items=[
            schemas.AiExploreItem(
                product=item["product"],
                match_score=item["match_score"],
                match_label=item["match_label"],
                reason_label=item["reason_label"],
                matched_style=item["matched_style"],
                is_exploration=item["is_exploration"],
                position=item["position"],
            )
            for item in items
        ],
        meta=schemas.ExploreMeta(**meta),
        exhausted=len(items) == 0,
        remaining=remaining,
    )


# ---------------------------------------------------------
# ETKILESIM
# ---------------------------------------------------------

def _build_toast(interaction_type, product, preference):
    """
    Bildirim metnini uretir.

    Onemli: metin gercekten olan seyi anlatiyor. LIKE
    sonrasi "benzer urunler onceliklendirildi" diyoruz
    cunku refresh_taste_profile calisti ve bir sonraki feed
    sorgusu bu markayi/kategoriyi gercekten yukseltecek.
    Mesaj sus degil, sonucun ozeti.
    """

    if interaction_type == INTERACTION_LIKE:

        brand = (getattr(product, "brand", None) or "").strip()

        in_profile = brand and style_engine.normalize(brand) in (
            (preference.top_brands or {}) if preference else {}
        )

        message = (
            f"{brand} parçaları akışında öne çıkarılacak."
            if in_profile
            else "Anlaşıldı, bu tarz ürünler akışına önceliklendirildi."
        )

        return schemas.ToastMessage(
            title="Favorilerine eklendi",
            message=message,
            tone="success",
        )

    if interaction_type == INTERACTION_DISLIKE:

        return schemas.ToastMessage(
            title="Bu ürün ve benzer kesimler elendi",
            message="Bir daha gösterilmeyecek.",
            tone="neutral",
        )

    if interaction_type == INTERACTION_UNLIKE:

        return schemas.ToastMessage(
            title="Favorilerden çıkarıldı",
            message="Ürün akışına geri dönebilir.",
            tone="info",
        )

    return None


@api.post(
    "/interact",
    response_model=schemas.InteractResponse,
    status_code=201,
)
def interact(
    payload: schemas.InteractRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Tek uctan butun urun etkilesimleri.

    LIKE    -> wishlist'e ekler + zevk profilini tazeler
    UNLIKE  -> wishlist'ten cikarir
    DISLIKE -> kalici olarak feed'den duser
    VIEW    -> sadece kaydeder

    Etkilesim aninda gosterilen match_score ve matched_style
    da kaydedilir; modelin kendi onerisinin etkisini
    olcebilmek icin gerekli.
    """

    product = crud.get_product(db=db, product_id=payload.product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Ürün bulunamadı.",
        )

    preference = crud.get_preference(db, user.id)

    active_styles = (
        list(preference.selected_styles or []) if preference else []
    )

    recorded = crud.record_interactions(
        db=db,
        user_id=user.id,
        items=[payload],
        match_score=payload.match_score,
        style_archetype=(
            payload.matched_style
            or (active_styles[0] if active_styles else None)
        ),
        selected_styles=active_styles or None,
    )

    if payload.interaction_type == INTERACTION_LIKE:

        crud.add_to_wishlist(
            db=db,
            user_id=user.id,
            product_id=payload.product_id,
        )

        # Zevk profilini hemen tazeliyoruz: bir sonraki feed
        # istegi bu begeniyi zaten kullanacak.
        preference = crud.refresh_taste_profile(db, user.id)

    elif payload.interaction_type == INTERACTION_UNLIKE:

        crud.remove_from_wishlist(
            db=db,
            user_id=user.id,
            product_id=payload.product_id,
        )

    elif payload.interaction_type == INTERACTION_DISLIKE:

        # Begenilmeyen urun favorilerde kalmasin
        crud.remove_from_wishlist(
            db=db,
            user_id=user.id,
            product_id=payload.product_id,
        )

        preference = crud.refresh_taste_profile(db, user.id)

    return schemas.InteractResponse(
        recorded=len(recorded),
        in_wishlist=crud.is_in_wishlist(
            db=db,
            user_id=user.id,
            product_id=payload.product_id,
        ),
        wishlist_count=crud.get_wishlist_count(
            db=db,
            user_id=user.id,
        ),
        toast=_build_toast(
            payload.interaction_type,
            product,
            preference,
        ),
    )


# ---------------------------------------------------------
# PROFIL SEFFAFLIGI
# ---------------------------------------------------------

@api.get(
    "/preferences",
    response_model=schemas.PreferenceResponse,
)
def my_preferences(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    "AI benim hakkimda ne biliyor" paneli.

    Kullaniciya kendi profilini gostermek hem guven verir
    hem de kisisel veri seffafligi acisindan dogru olan.
    """

    preference = crud.get_preference(db, user.id)

    if preference is None:
        return schemas.PreferenceResponse()

    styles = list(preference.selected_styles or [])

    return schemas.PreferenceResponse(
        selected_styles=styles,
        style_labels=[
            style_engine.style_label(s) for s in styles
        ],
        style_archetype=preference.style_archetype,
        archetype_label=(
            style_engine.style_label(preference.style_archetype)
            if preference.style_archetype
            else None
        ),
        like_count=preference.like_count or 0,
        dislike_count=preference.dislike_count or 0,
        top_brands=preference.top_brands or {},
        top_categories=preference.top_categories or {},
        top_colors=preference.top_colors or {},
        avoid_brands=preference.avoid_brands or {},
        avoid_categories=preference.avoid_categories or {},
        median_price=preference.median_price,
        profile_computed_at=preference.profile_computed_at,
    )




# ---------------------------------------------------------
# HIZLI SATIN ALMA  (sepetsiz)
# ---------------------------------------------------------

# Sepet kaldirildi. Satin alma tek urun uzerinden, tek
# ekranda yapiliyor.
#
# ML acisindan onemi: QUICK_BUY, LIKE'tan daha guclu bir
# sinyal (agirlik 2.0 vs 1.0). Kullanici sadece begenmiyor,
# para harcamaya niyet ediyor. Oneri modeli icin en degerli
# etiket bu.
#
# UYARI: gercek bir odeme saglayicisi ve orders tablosu YOK.
# Bu uc siparis numarasi uretir ve etkilesimi kaydeder;
# tahsilat yapmaz. Kart bilgisi hicbir yere gonderilmez.


@api.post(
    "/quick-order",
    response_model=schemas.QuickOrderResponse,
    status_code=201,
)
def quick_order(
    payload: schemas.QuickOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Tek urunluk hizli satin alma.

    Sepet gerektirmez. Kart bilgileri istemcide dogrulanir
    ve BURAYA GONDERILMEZ; bu uc yalnizca niyeti kaydeder.
    """

    product = crud.get_product(
        db=db,
        product_id=payload.product_id,
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Ürün bulunamadı.",
        )

    if product.price is None or product.price <= 0:
        raise HTTPException(
            status_code=422,
            detail="Bu ürünün fiyat bilgisi yok, satın alınamaz.",
        )

    preference = crud.get_preference(db, user.id)

    active_styles = (
        list(preference.selected_styles or []) if preference else []
    )

    # En guclu ML sinyali: satin alma niyeti
    recorded = crud.record_interactions(
        db=db,
        user_id=user.id,
        items=[
            schemas.InteractionCreate(
                product_id=payload.product_id,
                interaction_type=INTERACTION_QUICK_BUY,
                source=payload.source or "quick_checkout",
                position=payload.position,
                match_score=payload.match_score,
                matched_style=payload.matched_style,
            )
        ],
        style_archetype=(
            payload.matched_style
            or (active_styles[0] if active_styles else None)
        ),
        selected_styles=active_styles or None,
    )

    # Satin alinan urun favorilerde kalmasin: artik alindi
    crud.remove_from_wishlist(
        db=db,
        user_id=user.id,
        product_id=payload.product_id,
    )

    # Zevk profilini tazele — satin alma en agir sinyal
    crud.refresh_taste_profile(db, user.id)

    order_number = _build_order_number()

    return schemas.QuickOrderResponse(
        order_number=order_number,
        product_id=payload.product_id,
        product_title=(product.title_tr or product.title),
        recorded=len(recorded),
        wishlist_count=crud.get_wishlist_count(
            db=db,
            user_id=user.id,
        ),
        toast=schemas.ToastMessage(
            title="Siparişin alındı",
            message=(
                f"{order_number} · Benzer parçalar akışında "
                f"öne çıkarılacak."
            ),
            tone="success",
        ),
    )


def _build_order_number():
    """
    WISHNN-20260820-4831

    Sunucuda uretiliyor: istemcide uretilse iki sekme ayni
    numarayi verebilir ve destek tarafinda karisiklik olur.
    """

    now = datetime.now(timezone.utc)

    stamp = now.strftime("%Y%m%d")

    # secrets.randbelow yok; randbits ile kriptografik
    # rastgelelik yeterli (siparis numarasi tahmin
    # edilebilir olmamali).
    suffix = secrets.randbits(20) % 10000

    return f"WISHNN-{stamp}-{suffix:04d}"


# =========================================================
# AKILLI ARAMA  (AI Search)
# =========================================================

@api.get(
    "/search",
    response_model=schemas.SearchResponse,
)
def ai_search(
    q: str = Query(
        ...,
        min_length=1,
        max_length=200,
    ),
    limit: int = Query(
        default=24,
        ge=1,
        le=60,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    stage: int | None = Query(
        default=None,
        ge=0,
        le=4,
        description=(
            "Gevsetme asamasi. Ilk sayfada bos birakilir; "
            "sonraki sayfalarda meta.stage geri gonderilir "
            "ki siralama tutarli kalsin."
        ),
    ),
    db: Session = Depends(get_db),
):
    """
    Dogal dil aramasi.

    Uc adim:

        1. ANLA      query_engine.analyze()
           Dolgu kelimeleri atar, cinsiyet/kategori/renk
           tespit eder, sezon-desen-kumas niyetlerini
           genisletir.

        2. VEKTORLE  embed_query()
           Zenginlestirilmis metni (ham sorguyu DEGIL)
           embedding'e cevirir. Onbellekli ve hata
           firlatmaz.

        3. ARA       search_service.search()
           Hibrit siralama + gerekirse filtre gevsetme.

    Eski /products/semantic-search ucu OLDUGU GIBI kaliyor:
    frontend gecisi ve mevcut testler ona bagli.
    """

    intent = query_engine.analyze(q)

    # DIKKAT: embedding'e ham sorgu degil, zenginlestirilmis
    # metin gidiyor. Butun anlamsal genisletmenin ise
    # yaramasi buna bagli.
    vector = embed_query(intent.embed_text)

    items, meta = search_service.search(
        db=db,
        intent=intent,
        query_embedding=vector,
        limit=limit,
        offset=offset,
        stage=stage,
    )

    return schemas.SearchResponse(
        query=schemas.SearchAnalysis(**intent.to_dict()),
        items=[
            schemas.SearchItem(
                product=schemas.ProductResponse.model_validate(
                    item["product"]
                ),
                similarity_score=item["similarity_score"],
                search_score=item["search_score"],
                reasons=item["reasons"],
            )
            for item in items
        ],
        meta=schemas.SearchMeta(**meta),
    )


@api.get("/search/analyze")
def ai_search_analyze(
    q: str = Query(..., min_length=1, max_length=200),
):
    """
    Yalnizca sorgu cozumlemesi — veritabanina ve embedding
    API'sine hic dokunmaz.

    Sozluk kalibre ederken ve test yazarken gerekli:
    "bu sorgudan ne anladin" sorusunu bedava sorabilmek
    lazim. Aksi halde her deneme bir Gemini cagrisi.
    """

    return query_engine.analyze(q).to_dict()


app.include_router(api)
