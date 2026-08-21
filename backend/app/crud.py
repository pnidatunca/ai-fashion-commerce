from datetime import datetime, timezone

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app import style_engine
from app.models import (
    INTERACTION_DISLIKE,
    INTERACTION_INITIAL_STYLE,
    INTERACTION_LIKE,
    Product,
    Review,
    User,
    UserInteraction,
    UserPreference,
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
