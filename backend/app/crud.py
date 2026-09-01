import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app import style_engine
from app.models import (
    INTERACTION_DISLIKE,
    INTERACTION_INITIAL_STYLE,
    INTERACTION_LIKE,
    INTERACTION_QUICK_BUY,
    CartItem,
    Product,
    Review,
    User,
    UserInteraction,
    UserPreference,
    WardrobeLook,
    WardrobeLookItem,
    WishlistItem,
    weight_for,
)


# Desteklenen siralamalar. Anahtarlar frontend'in
# gonderdigi degerler.
PRODUCT_SORTS = (
    "featured",
    "price_asc",
    "price_desc",
    "rating",
    "discount",
)


def _product_sort_expression(sort):
    """
    Siralama ifadesi. Son eleman her zaman product_id:
    esit degerlerde deterministik sira sagliyor.

    NULL degerler sona: fiyati olmayan urun "en ucuz",
    puani olmayan urun "en yuksek puanli" gorunmemeli.
    """

    if sort == "price_asc":
        return (
            Product.price.asc().nullslast(),
            Product.product_id.asc(),
        )

    if sort == "price_desc":
        return (
            Product.price.desc().nullslast(),
            Product.product_id.asc(),
        )

    if sort == "rating":
        return (
            Product.rating.desc().nullslast(),
            Product.rating_count.desc().nullslast(),
            Product.product_id.asc(),
        )

    if sort == "discount":
        return (
            Product.discount_percent.desc().nullslast(),
            Product.product_id.asc(),
        )

    # featured / bilinmeyen -> deterministik varsayilan
    return (Product.product_id.asc(),)


def get_products(
    db: Session,
    limit: int = 24,
    offset: int = 0,
    category: str | None = None,
    sort: str | None = None,
):
    statement = select(Product)

    if category:

        category = category.lower()

        # Breadcrumb ya "... › Men › Clothing › ..." seklinde
        # devam eder ya da "... › Men" ile biter.
        # Ikinci durumu da yakalamamiz gerekiyor.

        if category == "men":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Men ›%"),
                    Product.category.ilike("%› Men"),
                )
            )

        elif category == "women":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Women ›%"),
                    Product.category.ilike("%› Women"),
                )
            )

        # COCUK: katalogda tek bir "Kids" bolumu YOK.
        # Uc ayri bolum var ve ucu birlikte cocugu karsiliyor:
        #
        #   Boys                33 urun
        #   Baby                35 urun  (Baby Boys / Baby Girls
        #                                 alt dallariyla)
        #   Girls                0 urun  (bugun standalone yok;
        #                                 ileride cikarsa hazir)
        #
        # Olculdu: bu desen Men/Women ile HIC kesismiyor
        # (kids AND men = 0, kids AND women = 0), yani bir urun
        # iki bolumde birden gorunmuyor.
        elif category == "kids":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Boys ›%"),
                    Product.category.ilike("%› Boys"),
                    Product.category.ilike("%› Girls ›%"),
                    Product.category.ilike("%› Girls"),
                    Product.category.ilike("%› Baby ›%"),
                    Product.category.ilike("%› Baby"),
                )
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

            # "%Coats%" deseni "Suits & Sport Coats" ile de
            # esliyordu: dis giyim filtresi takim elbise
            # donduruyordu. Desen artik DAL ADINA bagli.
            #
            # Olculmus hali:
            #   "%› Jackets & Coats%"  -> 33 urun
            #   "%Outerwear%"           -> 7 urun
            #   "%Coats%" (eski)        -> 44 urun (11'i takim)
            #
            # Ayni desenler search_service._CATEGORY_PATTERNS
            # icinde de var; oradaki liste kaynaktir.
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Jackets & Coats%"),
                    Product.category.ilike("%Outerwear%"),
                )
            )

        elif category == "shoes":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Shoes ›%"),
                    Product.category.ilike("%› Shoes"),
                )
            )

    # SIRALAMA ARTIK SUNUCUDA.
    #
    # Onceden sadece ekrandaki 12 urun tarayicida
    # siralaniyordu; "fiyat artan" secildiginde katalogun
    # en ucuz urunleri degil o sayfadaki en ucuzu geliyordu.
    # Sonsuz akista bu daha da bozuk gorunur: her yeni parti
    # siralanmamis olarak sona ekleniyordu.
    #
    # Her siralamanin sonunda product_id var: ORDER BY
    # olmadan Postgres satir sirasini garanti etmez ve
    # esit degerlerde sayfalar arasi kayma olur.

    statement = statement.order_by(
        *_product_sort_expression(sort)
    )

    statement = statement.offset(offset).limit(limit)

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

    SIRALAMA: sitede yazilan yorumlar (created_at DOLU) en
    ustte, yeniden eskiye; ardindan veri setinden gelenler
    helpful_votes'a gore.

    Neden boyle: onceden yalnizca helpful_votes'a gore
    siralaniyordu. Yeni yazilan bir yorumun oyu 0 oldugu icin
    yuzlerce veri seti yorumunun ALTINA dusuyordu — kullanici
    yorumunu yazip bulamiyordu.
    """

    statement = (
        select(Review)
        .where(
            Review.product_id == product_id
        )
        .order_by(
            # nullslast: created_at'i olanlar (kullanici
            # yorumlari) once, NULL olanlar (veri seti) sonra
            Review.created_at.desc().nullslast(),
            Review.helpful_votes.desc(),
            # Esit degerlerde deterministik sira
            Review.review_id.asc(),
        )
        .offset(offset)
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )


# =========================================================
# KULLANICI YORUMLARI
# =========================================================

# Veri setinden gelen yorumlar READ-ONLY: onlarin user_id'si
# NULL ve dokunulmuyor. Buradaki fonksiyonlar yalnizca
# kullanicinin KENDI yorumunu yonetiyor.

def get_user_review(db: Session, user_id, product_id: str):
    """Kullanicinin bu urune yazdigi yorum (yoksa None)."""

    return db.scalar(
        select(Review)
        .where(Review.product_id == product_id)
        .where(Review.user_id == user_id)
    )


def user_has_purchased(db: Session, user_id, product_id: str) -> bool:
    """
    Kullanici bu urunu satin aldi mi?

    "Verified Purchase" etiketini UYDURMUYORUZ: hem sepet
    odemesi hem Hizli Al, QUICK_BUY etkilesimi kaydediyor
    (bkz. main.checkout_cart / quick_order). Etiket bu kayda
    dayaniyor.
    """

    found = db.scalar(
        select(UserInteraction.id)
        .where(UserInteraction.user_id == user_id)
        .where(UserInteraction.product_id == product_id)
        .where(
            UserInteraction.interaction_type == INTERACTION_QUICK_BUY
        )
        .limit(1)
    )

    return found is not None


def save_user_review(
    db: Session,
    user_id,
    product_id: str,
    rating: float,
    review_text: str,
    review_title: str | None = None,
):
    """
    Yorumu olusturur, varsa GUNCELLER.

    uq_review_user_product kisiti bir kullaniciya urun basina
    tek yorum hakki veriyor; ikinci gonderim "duzenleme"
    olarak ele aliniyor — kullaniciya "zaten yorum yaptin"
    hatasi vermek yerine yazdigini degistirmesine izin
    vermek daha dogru.
    """

    verified = user_has_purchased(db, user_id, product_id)

    review = get_user_review(db, user_id, product_id)

    if review is None:

        review = Review(
            # review_id String bir PK (veri setinde Amazon
            # kimlikleri var). Kendi yorumlarimiza "u-" oneki
            # koyuyoruz: kaynagi tek bakista belli olsun.
            review_id=f"u-{uuid.uuid4().hex[:24]}",
            product_id=product_id,
            user_id=user_id,
            helpful_votes=0,
        )

        db.add(review)

    review.rating = rating
    review.review_title = review_title
    review.review_text = review_text
    review.verified_purchase = verified
    review.created_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(review)

    return review


def delete_user_review(db: Session, user_id, product_id: str) -> bool:
    """
    Kullanicinin kendi yorumunu siler.

    user_id kosulu SART: veri seti yorumlarinin ve baska
    kullanicilarin yorumlarinin silinememesi buna bagli.
    """

    review = get_user_review(db, user_id, product_id)

    if review is None:
        return False

    db.delete(review)
    db.commit()

    return True


# =========================================================
# CLASSIC SEARCH
# =========================================================

def search_products(
    db: Session,
    query: str,
    limit: int = 24,
    offset: int = 0,
    sort: str | None = None,
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

    # Kullanicinin yazdigi % ve _ karakterleri LIKE joker
    # karakterleridir. Kacisilmazsa "%" yazan kullanici
    # butun katalogla eslesir.

    escaped = (
        query
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )

    search_pattern = f"%{escaped}%"

    statement = (
        select(Product)
        .where(
            or_(
                Product.title.ilike(search_pattern, escape="\\"),
                Product.title_tr.ilike(search_pattern, escape="\\"),
                Product.brand.ilike(search_pattern, escape="\\"),
                Product.category.ilike(search_pattern, escape="\\"),
            )
        )
        .order_by(*_product_sort_expression(sort))
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

        # Bkz. get_products icindeki ayni desenin aciklamasi:
        # tek bir "Kids" bolumu yok, uc bolum birlikte.
        elif category == "kids":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Boys ›%"),
                    Product.category.ilike("%› Girls ›%"),
                    Product.category.ilike("%› Baby ›%"),
                )
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

            # "%Coats%" deseni "Suits & Sport Coats" ile de
            # esliyordu: dis giyim filtresi takim elbise
            # donduruyordu. Desen artik DAL ADINA bagli.
            #
            # Olculmus hali:
            #   "%› Jackets & Coats%"  -> 33 urun
            #   "%Outerwear%"           -> 7 urun
            #   "%Coats%" (eski)        -> 44 urun (11'i takim)
            #
            # Ayni desenler search_service._CATEGORY_PATTERNS
            # icinde de var; oradaki liste kaynaktir.
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Jackets & Coats%"),
                    Product.category.ilike("%Outerwear%"),
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

        # "cocuk pantolonu" gibi sorgular: cinsiyet cocuk,
        # kategori pantolon — ikisi birlikte filtreleniyor.
        elif gender == "kids":
            statement = statement.where(
                or_(
                    Product.category.ilike("%› Boys ›%"),
                    Product.category.ilike("%› Girls ›%"),
                    Product.category.ilike("%› Baby ›%"),
                )
            )

    # =====================================================
    # COLOR FILTER
    # =====================================================

    # Kullanici bir renk belirttiginde SADECE o renk gelmeli.
    # Yumusak siralama (eslesmeyeni cezalandirip yine de
    # gostermek) denenmisti ama kullanici deneyiminde "beyaz
    # gomlek" arayip mavi/siyah urunlerin de listede cikmasina
    # yol acti. Bu yuzden renk sert bir filtre: eslesen urun
    # sayisi limit'ten az bile olsa, sadece gercekten eslesenler
    # donuyor.

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

        # Renk cogu zaman baslikta degil, description/features
        # alanlarinda geciyor (bazen hic gecmiyor). Sadece
        # title/title_tr'a bakmak eslesmeleri gereksiz yere
        # daraltiyordu (ör. erkek gomleklerinde "white" kelimesi
        # hicbir baslikta yokken description'da var).

        color_fields = [
            Product.title,
            Product.title_tr,
            Product.description,
            Product.description_tr,
            Product.features,
            Product.features_tr,
        ]

        color_conditions = []

        for term in terms:

            pattern = f"%{term}%"

            color_conditions.extend(
                field.ilike(pattern)
                for field in color_fields
            )

        statement = statement.where(
            or_(*color_conditions)
        )

    # =====================================================
    # VECTOR RANKING
    # =====================================================

    statement = (
        statement
        .order_by(distance)
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


def get_user_by_email(
    db: Session,
    email: str,
):
    return (
        db.query(User)
        .filter(User.email == email)
        .first()
    )


# =========================================================
# EXPLORE FEED
# =========================================================

def _eligible_products_statement():
    """
    Feed'de gosterilebilecek urunlerin temel kosulu.

    Fiyati veya gorseli olmayan urun karti bozuk gorunur ve
    egitim verisini kirletir; bu yuzden havuza alinmaz.
    """

    return select(Product).where(
        Product.price.is_not(None),
        Product.price > 0,
        Product.image_url.is_not(None),
        Product.image_url != "",
    )


def disliked_product_ids_subquery(user_id):
    """
    Kullanicinin BEGENMEDIM dedigi urunlerin kimlikleri.

    user_interactions append-only oldugu ve DISLIKE satirlari
    hic silinmedigi icin bu haric tutma kalicidir.
    """

    # product_id IS NOT NULL SART.
    #
    # INITIAL_STYLE olaylari urune bagli olmadigi icin
    # product_id kolonu artik NULL kabul ediyor. NOT IN
    # alt sorgusu tek bir NULL dondurse butun feed bosalir
    # (x NOT IN (a, NULL) asla TRUE olmaz). Tur filtresi
    # bunu zaten engelliyor ama sema degisikliklerine karsi
    # aciktan koruyoruz.

    return (
        select(UserInteraction.product_id)
        .where(
            UserInteraction.user_id == user_id,
            UserInteraction.interaction_type
            == INTERACTION_DISLIKE,
            UserInteraction.product_id.is_not(None),
        )
    )


def wishlisted_product_ids_subquery(user_id):
    """Zaten favorilere eklenmis urunler."""

    return (
        select(WishlistItem.product_id)
        .where(WishlistItem.user_id == user_id)
    )


def _apply_feed_filters(
    statement,
    user_id=None,
    exclude_product_ids=None,
):
    """
    Feed sorgusuna kullaniciya ozel haric tutmalari ekler.

    Uretilen NOT IN mantigi:

        SELECT * FROM products p
        WHERE p.product_id NOT IN (
            SELECT product_id FROM user_interactions
            WHERE user_id = :uid
              AND interaction_type = 'DISLIKE'
        )
        AND p.product_id NOT IN (
            SELECT product_id FROM wishlist_items
            WHERE user_id = :uid
        )

    Not: user_interactions.product_id ve
    wishlist_items.product_id NOT NULL oldugu icin NOT IN
    burada guvenlidir. Alt sorgu NULL dondurebiliyorsa
    NOT IN tum sonucu bosaltir; o durumda NOT EXISTS
    kullanilmalidir.

    Yuz binlerce satira cikildiginda ayni filtreyi
    NOT EXISTS / LEFT JOIN ... IS NULL bicimine cevirmek
    Postgres'te daha iyi plan uretir.
    """

    if user_id is not None:

        statement = statement.where(
            Product.product_id.not_in(
                disliked_product_ids_subquery(user_id)
            )
        )

        statement = statement.where(
            Product.product_id.not_in(
                wishlisted_product_ids_subquery(user_id)
            )
        )

    if exclude_product_ids:

        statement = statement.where(
            Product.product_id.not_in(exclude_product_ids)
        )

    return statement


def get_explore_feed(
    db: Session,
    user_id=None,
    limit: int = 12,
    exclude_product_ids=None,
):
    """
    Kesfet akisi.

    Giris yapmamis kullanici icin sadece rastgele urun doner;
    kisiselleştirme ve haric tutma yapilmaz.

    ORDER BY random() bu katalog boyutunda (< 1000 satir)
    sorunsuzdur. Katalog buyudugunde TABLESAMPLE SYSTEM veya
    onceden hesaplanmis bir oneri tablosu tercih edilmelidir.
    """

    statement = _apply_feed_filters(
        _eligible_products_statement(),
        user_id=user_id,
        exclude_product_ids=exclude_product_ids,
    )

    return list(
        db.scalars(
            statement
            .order_by(func.random())
            .limit(limit)
        ).all()
    )


def count_explore_pool(
    db: Session,
    user_id=None,
    exclude_product_ids=None,
):
    """Kullaniciya gosterilebilecek toplam urun sayisi."""

    statement = _apply_feed_filters(
        select(func.count())
        .select_from(Product)
        .where(
            Product.price.is_not(None),
            Product.price > 0,
            Product.image_url.is_not(None),
            Product.image_url != "",
        ),
        user_id=user_id,
        exclude_product_ids=exclude_product_ids,
    )

    return db.scalar(statement) or 0


# =========================================================
# INTERACTIONS
# =========================================================

def record_interactions(
    db: Session,
    user_id,
    items,
    match_score=None,
    style_archetype=None,
    selected_styles=None,
):
    """
    Etkilesimleri append-only olarak yazar.

    match_score / style_archetype: etkilesim aninda
    kullaniciya gosterilen AI baglami. Olayin kendisi kadar
    onemli, cunku model "X skoruyla gosterilen urun
    begenildi mi" sorusunu ogrenmeli.

    Olayin uzerinde kendi degeri varsa o kazanir; yoksa
    fonksiyona verilen ortak deger kullanilir.

    Var olmayan product_id'ler sessizce atlanir: eski bir
    sekmeden gelen istek yuzunden 500 donmek istemiyoruz.
    """

    incoming = list(items)

    if not incoming:
        return []

    product_ids = {item.product_id for item in incoming}

    known_ids = set(
        db.scalars(
            select(Product.product_id).where(
                Product.product_id.in_(product_ids)
            )
        ).all()
    )

    rows = [
        UserInteraction(
            user_id=user_id,
            product_id=item.product_id,
            interaction_type=item.interaction_type,
            source=item.source,
            position=item.position,
            match_score=(
                getattr(item, "match_score", None)
                if getattr(item, "match_score", None) is not None
                else match_score
            ),

            # Agirlik OLAYLA BIRLIKTE yaziliyor.
            # Esleme tablosu degisse bile gecmis olaylarin
            # agirligi degismemeli.
            weight=weight_for(item.interaction_type),

            style_archetype=(
                getattr(item, "matched_style", None)
                or style_archetype
            ),
            selected_styles=selected_styles,
        )
        for item in incoming
        if item.product_id in known_ids
    ]

    if not rows:
        return []

    db.add_all(rows)
    db.commit()

    for row in rows:
        db.refresh(row)

    return rows


def get_interaction_counts(
    db: Session,
    user_id,
):
    """Kullanicinin etkilesim turlerine gore dagilimi."""

    rows = db.execute(
        select(
            UserInteraction.interaction_type,
            func.count(),
        )
        .where(UserInteraction.user_id == user_id)
        .group_by(UserInteraction.interaction_type)
    ).all()

    return {row[0]: row[1] for row in rows}


def get_training_interactions(
    db: Session,
    limit: int = 1000,
    offset: int = 0,
    since=None,
):
    """
    ML egitimi icin ham olay kaydi.

    Kronolojik sirali doner: zaman bazli train/test bolmesi
    (temporal split) bu siraya dayanir.
    """

    statement = select(UserInteraction)

    if since is not None:
        statement = statement.where(
            UserInteraction.created_at >= since
        )

    statement = (
        statement
        .order_by(
            UserInteraction.created_at,
            UserInteraction.id,
        )
        .offset(offset)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


# =========================================================
# WISHLIST
# =========================================================

def add_to_wishlist(
    db: Session,
    user_id,
    product_id: str,
):
    """
    Favorilere ekler. Idempotenttir.

    ON CONFLICT DO NOTHING: iki sekmeden ayni anda kalp
    basilirsa unique kisit ihlali yerine tek satir olusur.
    """

    statement = (
        pg_insert(WishlistItem)
        .values(
            user_id=user_id,
            product_id=product_id,
        )
        .on_conflict_do_nothing(
            constraint="uq_wishlist_user_product",
        )
    )

    db.execute(statement)
    db.commit()

    return True


def remove_from_wishlist(
    db: Session,
    user_id,
    product_id: str,
):
    """Favorilerden cikarir. Kayit yoksa False doner."""

    item = db.scalar(
        select(WishlistItem).where(
            WishlistItem.user_id == user_id,
            WishlistItem.product_id == product_id,
        )
    )

    if item is None:
        return False

    db.delete(item)
    db.commit()

    return True


def get_wishlist(
    db: Session,
    user_id,
    limit: int = 100,
    offset: int = 0,
):
    """
    Favori listesi, urun detaylari ile birlikte.

    joinedload olmasa her satir icin ayri bir urun sorgusu
    cikardi (N+1 problemi).
    """

    statement = (
        select(WishlistItem)
        .options(joinedload(WishlistItem.product))
        .where(WishlistItem.user_id == user_id)
        .order_by(WishlistItem.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    return list(
        db.scalars(statement).unique().all()
    )


def get_wishlist_product_ids(
    db: Session,
    user_id,
):
    """Sadece kimlikler: kalp ikonlarini doldurmak icin."""

    return list(
        db.scalars(
            select(WishlistItem.product_id)
            .where(WishlistItem.user_id == user_id)
            .order_by(WishlistItem.created_at.desc())
        ).all()
    )


def get_wishlist_count(
    db: Session,
    user_id,
):
    return db.scalar(
        select(func.count())
        .select_from(WishlistItem)
        .where(WishlistItem.user_id == user_id)
    ) or 0


def is_in_wishlist(
    db: Session,
    user_id,
    product_id: str,
):
    return db.scalar(
        select(func.count())
        .select_from(WishlistItem)
        .where(
            WishlistItem.user_id == user_id,
            WishlistItem.product_id == product_id,
        )
    ) > 0


# =========================================================
# CART
# =========================================================
#
# Wishlist'ten farki: sepette miktar var. Ayni urun tekrar
# eklendiginde yeni satir acmak yerine miktari artiriyoruz
# (ON CONFLICT DO UPDATE) — boylece unique kisit hep tek
# satir garantiler ve "sepette kac cesit urun var" sorusu
# basit bir COUNT kalir.

def add_to_cart(
    db: Session,
    user_id,
    product_id: str,
    quantity: int = 1,
):
    """
    Sepete ekler. Zaten sepetteyse miktari ARTIRIR
    (mutlak deger olarak ayarlamaz — bkz. set_cart_quantity).
    """

    insert_statement = pg_insert(CartItem).values(
        user_id=user_id,
        product_id=product_id,
        quantity=quantity,
    )

    statement = insert_statement.on_conflict_do_update(
        constraint="uq_cart_user_product",
        set_={
            "quantity": CartItem.quantity + insert_statement.excluded.quantity,
            "updated_at": func.now(),
        },
    )

    db.execute(statement)
    db.commit()

    return True


def set_cart_quantity(
    db: Session,
    user_id,
    product_id: str,
    quantity: int,
):
    """
    Miktari MUTLAK bir degere ayarlar (artirmaz).

    quantity <= 0 gelirse urunu sepetten tamamen cikarir —
    boylece frontend "miktari sifirla" ile "kaldir" arasinda
    ayri bir uc cagirmak zorunda kalmaz.
    """

    if quantity <= 0:
        return remove_from_cart(db, user_id, product_id)

    item = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id,
        )
    )

    if item is None:
        return False

    item.quantity = quantity
    item.updated_at = datetime.now(timezone.utc)

    db.commit()

    return True


def remove_from_cart(
    db: Session,
    user_id,
    product_id: str,
):
    """Sepetten tamamen cikarir. Kayit yoksa False doner."""

    item = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id,
        )
    )

    if item is None:
        return False

    db.delete(item)
    db.commit()

    return True


def get_cart(
    db: Session,
    user_id,
):
    """Sepet icerigi, urun detaylariyla birlikte (N+1 onlemek icin joinedload)."""

    statement = (
        select(CartItem)
        .options(joinedload(CartItem.product))
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.created_at.desc())
    )

    return list(
        db.scalars(statement).unique().all()
    )


def get_cart_count(
    db: Session,
    user_id,
):
    """Toplam ADET (urun cesidi degil, miktarlarin toplami) — header rozeti icin."""

    return db.scalar(
        select(func.coalesce(func.sum(CartItem.quantity), 0))
        .select_from(CartItem)
        .where(CartItem.user_id == user_id)
    ) or 0


def clear_cart(
    db: Session,
    user_id,
):
    """Odeme sonrasi sepeti bosaltir."""

    db.query(CartItem).filter(
        CartItem.user_id == user_id
    ).delete()

    db.commit()


# =========================================================
# AI KISISELLESTIRME — TERCIHLER
# =========================================================
#
# Akis sorgulari app/feed.py icinde. Burada yalnizca
# kullanici tercihlerinin yazilmasi/okunmasi var.
#
# Neden ayrildi: feed sorgusu cursor tabanli keyset,
# JSONB operatorleri ve pencere fonksiyonlari kullaniyor.
# Onu ayri bir modulde tutmak crud.py'yi okunur biraktı.


def get_preference(db: Session, user_id):
    """Kullanicinin tercih satiri (yoksa None)."""

    return db.scalar(
        select(UserPreference).where(
            UserPreference.user_id == user_id
        )
    )


def get_or_create_preference(db: Session, user_id):
    """Tercih satirini getirir, yoksa olusturur."""

    preference = get_preference(db, user_id)

    if preference is not None:
        return preference

    # ON CONFLICT: iki sekme ayni anda tarz secebilir
    db.execute(
        pg_insert(UserPreference)
        .values(user_id=user_id)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    db.commit()

    return get_preference(db, user_id)


def set_selected_styles(
    db: Session,
    user_id,
    styles,
):
    """
    Tarz secimini kaydeder ve INITIAL_STYLE olayini yazar.

    styles: 1-3 arketip, SIRALI. Ilk eleman birincil tarz.

    Kullanici tarzini degistirebilir; her degisiklik yeni
    bir INITIAL_STYLE satiri uretir (olay kaydi append-only).
    archetype_change_count sik degistiren kullaniciyi
    isaretler: onun icin tarz sinyaline daha az guvenilir.
    """

    cleaned = style_engine.normalize_selected_styles(styles)

    if not cleaned:
        raise ValueError("En az bir gecerli tarz gerekli.")

    preference = get_or_create_preference(db, user_id)

    previous = list(preference.selected_styles or [])

    preference.selected_styles = cleaned
    preference.style_archetype = cleaned[0]
    preference.archetype_selected_at = datetime.now(timezone.utc)

    if previous and previous != cleaned:
        preference.archetype_change_count = (
            preference.archetype_change_count or 0
        ) + 1

    preference.updated_at = datetime.now(timezone.utc)

    db.add(
        UserInteraction(
            user_id=user_id,
            product_id=None,
            interaction_type=INTERACTION_INITIAL_STYLE,
            source="onboarding",
            style_archetype=cleaned[0],
            selected_styles=cleaned,
        )
    )

    db.commit()
    db.refresh(preference)

    return preference


def refresh_taste_profile(db: Session, user_id):
    """
    LIKE gecmisinden zevk profilini yeniden hesaplar ve
    user_preferences'a yazar.

    Her kalpten sonra cagriliyor. Feed sorgusu boylece
    butun gecmisi yeniden okumak zorunda kalmiyor: tek
    satir okuyup hazir ozeti kullaniyor.

    JSONB anahtarlari style_engine.normalize ile kucuk
    harfe cevrilmis halde saklanir; feed.py'deki SQL
    bonusu da lower() ile arıyor.
    """

    preference = get_or_create_preference(db, user_id)

    # Wishlist'ten degil OLAY KAYDINDAN okuyoruz: kullanici
    # favoriden cikarmis olsa da o begeni bir sinyaldi.
    liked = list(
        db.scalars(
            select(Product)
            .join(
                UserInteraction,
                UserInteraction.product_id == Product.product_id,
            )
            .where(
                UserInteraction.user_id == user_id,
                UserInteraction.interaction_type == INTERACTION_LIKE,
            )
            .order_by(UserInteraction.created_at.desc())
            .limit(60)
        ).all()
    )

    disliked = list(
        db.scalars(
            select(Product)
            .join(
                UserInteraction,
                UserInteraction.product_id == Product.product_id,
            )
            .where(
                UserInteraction.user_id == user_id,
                UserInteraction.interaction_type == INTERACTION_DISLIKE,
            )
            .order_by(UserInteraction.created_at.desc())
            .limit(60)
        ).all()
    )

    taste = style_engine.build_taste_profile(liked, disliked)

    # En guclu 12 sinyali tutuyoruz; tamamini saklamak
    # satiri sisirir, faydasi yok.
    def top(mapping, count=12):
        return dict(
            sorted(mapping.items(), key=lambda item: -item[1])[:count]
        )

    preference.top_brands = top(taste["brands"])
    preference.top_categories = top(taste["categories"])
    preference.top_colors = top(taste["colors"])

    # "Benzer kategorideki urunler negatif agirlik kazanir"
    # kurali icin: feed sorgusu bunlari SQL'de okuyup ceza
    # uyguluyor. Onceden yalnizca bellekte hesaplaniyordu ve
    # siralamayi hic etkilemiyordu.
    preference.avoid_brands = top(taste["avoid_brands"])
    preference.avoid_categories = top(taste["avoid_categories"])
    preference.median_price = taste["median_price"]
    preference.like_count = len(liked)
    preference.dislike_count = len(disliked)
    preference.profile_computed_at = datetime.now(timezone.utc)
    preference.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(preference)

    return preference


def selected_styles_for(db: Session, user_id):
    """Kullanicinin kayitli tarzlari (yoksa bos liste)."""

    preference = get_preference(db, user_id)

    if preference is None:
        return []

    return list(preference.selected_styles or [])


# =========================================================
# GARDIROP (KOMBIN / LOOK)
# =========================================================

# Buradaki fonksiyonlar sepet/wishlist ile ayni sozlesmeyi
# tasiyor: her biri kendi icinde commit ediyor, kayit yoksa
# False donuyor (404'u endpoint atiyor).
#
# Farki: kombin ic ice bir yapi (look -> items -> product).
# Okuma yaparken iki seviye joinedload sart, yoksa her parca
# icin ayri sorgu gider ve 5 kombinlik bir gardirop 20+
# sorguya cikar.

def _look_query():
    """Look + parcalari + parcalarin urunleri, tek sorguda."""

    return (
        select(WardrobeLook)
        .options(
            joinedload(WardrobeLook.items)
            .joinedload(WardrobeLookItem.product)
        )
    )


def get_looks(db: Session, user_id):
    """Kullanicinin tum kombinleri, yeniden eskiye."""

    statement = (
        _look_query()
        .where(WardrobeLook.user_id == user_id)
        .order_by(WardrobeLook.created_at.desc())
    )

    return list(db.scalars(statement).unique().all())


def get_look(db: Session, user_id, look_id):
    """
    Tek kombin.

    user_id kosulu GUVENLIK icin: look_id tahmin edilebilir
    olmasa da, baskasinin kombinini id'siyle okumak mumkun
    olmamali.
    """

    statement = (
        _look_query()
        .where(WardrobeLook.id == look_id)
        .where(WardrobeLook.user_id == user_id)
    )

    return db.scalars(statement).unique().one_or_none()


def get_look_count(db: Session, user_id) -> int:
    """Header rozeti icin: kac kombin var."""

    statement = (
        select(func.count())
        .select_from(WardrobeLook)
        .where(WardrobeLook.user_id == user_id)
    )

    return db.scalar(statement) or 0


def create_look(db: Session, user_id, title, entries, source=None, note=None):
    """
    Yeni kombin olusturur.

    entries: [{"product_id": str, "slot": str | None}, ...]
    Sira ONEMLI: listedeki sira position olarak yaziliyor,
    kombin ekranda hep ayni duzende gorunsun diye.

    Ayni urun listede iki kez gecerse ikincisi atlaniyor —
    uq_look_product kisitina carpip tum islemi geri almasin.
    """

    look = WardrobeLook(
        user_id=user_id,
        title=title,
        source=source,
        note=note,
    )

    db.add(look)

    # Parcalari eklemeden once look'un id'si gerekiyor.
    db.flush()

    seen = set()
    position = 0

    for entry in entries:

        product_id = entry.get("product_id")

        if not product_id or product_id in seen:
            continue

        seen.add(product_id)

        db.add(
            WardrobeLookItem(
                look_id=look.id,
                product_id=product_id,
                slot=entry.get("slot"),
                position=position,
            )
        )

        position += 1

    db.commit()

    # Iliskileri dolu, taze bir nesne don: endpoint bunu
    # dogrudan response'a ceviriyor.
    return get_look(db, user_id, look.id)


def rename_look(db: Session, user_id, look_id, title):
    """Kombin basligini degistirir."""

    look = db.scalar(
        select(WardrobeLook)
        .where(WardrobeLook.id == look_id)
        .where(WardrobeLook.user_id == user_id)
    )

    if look is None:
        return False

    look.title = title
    look.updated_at = datetime.now(timezone.utc)

    db.commit()

    return True


def delete_look(db: Session, user_id, look_id):
    """Kombini ve parcalarini siler."""

    look = db.scalar(
        select(WardrobeLook)
        .where(WardrobeLook.id == look_id)
        .where(WardrobeLook.user_id == user_id)
    )

    if look is None:
        return False

    db.delete(look)
    db.commit()

    return True


def _touch_look(db: Session, look_id):
    """
    Parca degisince kombinin updated_at'ini ilerletir.

    Gardirop listesi created_at'e gore siralaniyor ama
    "en son dokundugum kombin" bilgisi arayuzde
    gosterilebilsin diye tutuluyor.
    """

    look = db.get(WardrobeLook, look_id)

    if look is not None:
        look.updated_at = datetime.now(timezone.utc)


def add_look_item(db: Session, user_id, look_id, product_id, slot=None):
    """
    Kombine yeni parca ekler.

    Ayni urun zaten varsa False doner — kombinde adet
    kavrami yok, tekrar eklemenin anlami olmaz.
    """

    look = db.scalar(
        select(WardrobeLook)
        .where(WardrobeLook.id == look_id)
        .where(WardrobeLook.user_id == user_id)
    )

    if look is None:
        return False

    exists = db.scalar(
        select(WardrobeLookItem)
        .where(WardrobeLookItem.look_id == look_id)
        .where(WardrobeLookItem.product_id == product_id)
    )

    if exists is not None:
        return False

    last_position = db.scalar(
        select(func.coalesce(func.max(WardrobeLookItem.position), -1))
        .where(WardrobeLookItem.look_id == look_id)
    )

    db.add(
        WardrobeLookItem(
            look_id=look_id,
            product_id=product_id,
            slot=slot,
            position=(last_position or 0) + 1
            if last_position is not None
            else 0,
        )
    )

    _touch_look(db, look_id)

    db.commit()

    return True


def replace_look_item(db: Session, user_id, look_id, old_product_id, new_product_id):
    """
    Kombindeki bir parcayi baskasiyla degistirir.

    Yeni urun eskisinin position VE slot degerini
    devraliyor: kombin gorsel olarak yerinden oynamasin ve
    "ayakkabi" yuvasindaki parca ayakkabi kalsin.

    Yeni urun kombinde ZATEN varsa islem yapilmiyor —
    tekrar eklemek uq_look_product'a carpardi.
    """

    look = db.scalar(
        select(WardrobeLook)
        .where(WardrobeLook.id == look_id)
        .where(WardrobeLook.user_id == user_id)
    )

    if look is None:
        return False

    item = db.scalar(
        select(WardrobeLookItem)
        .where(WardrobeLookItem.look_id == look_id)
        .where(WardrobeLookItem.product_id == old_product_id)
    )

    if item is None:
        return False

    if old_product_id == new_product_id:
        return True

    duplicate = db.scalar(
        select(WardrobeLookItem)
        .where(WardrobeLookItem.look_id == look_id)
        .where(WardrobeLookItem.product_id == new_product_id)
    )

    if duplicate is not None:
        return False

    item.product_id = new_product_id

    _touch_look(db, look_id)

    db.commit()

    return True


def remove_look_item(db: Session, user_id, look_id, product_id):
    """Kombinden bir parcayi cikarir."""

    look = db.scalar(
        select(WardrobeLook)
        .where(WardrobeLook.id == look_id)
        .where(WardrobeLook.user_id == user_id)
    )

    if look is None:
        return False

    item = db.scalar(
        select(WardrobeLookItem)
        .where(WardrobeLookItem.look_id == look_id)
        .where(WardrobeLookItem.product_id == product_id)
    )

    if item is None:
        return False

    db.delete(item)

    _touch_look(db, look_id)

    db.commit()

    return True
