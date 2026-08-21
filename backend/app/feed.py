"""
KESFET AKISI — cursor tabanli sayfalama

Bu modul /api/explore ucunun sorgu katmanidir.

MIMARI KARARI: SIRALAMA TAMAMEN SQL'DE
--------------------------------------
Onceki surumde skor iki parcada uretiliyordu: temel skor
SQL'den geliyor, kisisellestirme Python'da ekleniyordu.
Cursor tabanli sayfalamaya gecerken bu calismiyor:

    Python siralamayi degistiriyorsa, cursor "kaldigim yer"
    bilgisini tasiyamaz. Sayfa 2'de bazi urunler tekrar
    eder, bazilari hic gorunmez.

Bu yuzden siralama ifadesinin BUTUNU SQL'e tasindi:

    final_score =
          en iyi secili tarz skoru          (product_style_scores)
        + cok yonluluk bonusu               (ikinci tarz da yuksekse)
        + sik begenilen marka bonusu        (user_preferences.top_brands)
        + sik begenilen kategori bonusu     (user_preferences.top_categories)
        + fiyat yakinligi bonusu            (median_price'a yakinlik)

Python artik skoru DEGISTIRMIYOR; yalnizca gerekce
cumlesini kuruyor. Boylece gosterilen yuzde, siralamada
kullanilan yuzdenin aynisi. Kart uzerindeki sayi ile
kartin sirasi asla celismez.

Bedeli: renk gecmisi bonusu kaldirildi (urun renklerini
SQL'de tespit etmek gerekirdi). Renk yine skora giriyor
ama arketip paleti uzerinden, temel skorun icinde.


CURSOR NASIL CALISIYOR
----------------------
Keyset pagination: (final_score, product_id) ikilisi.

    WHERE (final_score, product_id) < (:cursor_score, :cursor_id)
    ORDER BY final_score DESC, product_id DESC

OFFSET kullanilmiyor cunku OFFSET her sayfada onceki
satirlari yeniden tarar ve arada yeni etkilesim olursa
kayma (drift) yasanir. Keyset sabit maliyetli ve kaymaz.

Kesif (exploration) slotlari rastgele oldugu icin keyset'e
girmiyor; cursor icinde gosterilmis kimliklerin listesi
tutuluyor (kapali sinir: CURSOR_SEEN_LIMIT).
"""

from __future__ import annotations

import base64
import json

from sqlalchemy import Float, and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from app import style_engine
from app.models import (
    INTERACTION_DISLIKE,
    Product,
    ProductStyleScore,
    UserInteraction,
    UserPreference,
    WishlistItem,
)


# =========================================================
# SABITLER
# =========================================================

# Feed'in ne kadari KESIF (exploration) olacak.
#
# Neden gerekli: eger akis yalnizca modelin yuksek
# skorladigi urunleri gosterirse, egitim verisi modelin
# kendi onyargisini tekrar eder. Model hic gostermedigi
# urun hakkinda hicbir sey ogrenemez (feedback loop).
EXPLORATION_RATIO = 0.25

# Cursor icinde en fazla kac gosterilmis kimlik tutulacak.
# Cursor bir URL parametresi; sinirsiz buyumesine izin
# verilemez.
CURSOR_SEEN_LIMIT = 300

# Kisisellestirme bonuslari (SQL'de uygulanir).
BRAND_BOOST = 8.0
CATEGORY_BOOST = 6.0
PRICE_BOOST = 4.0

# Begenilmeyen marka / kategori cezasi.
#
# "Bu urun ve benzer kategorideki urunler negatif agirlik
# kazanir" kurali. Urunun KENDISI kara listede (kalici
# olarak feed'den dusuyor); ayni kategorideki diger urunler
# ise yalnizca skor kaybediyor.
#
# Neden kategoriyi tamamen dislamiyoruz: bir "Polos"
# urununu begenmemek butun polo yaka tisortleri elemek
# demek degil. Kategoriyi dislamak akisi hizla bosaltir ve
# kullanici bir daha o kategoriyi hic goremez.
BRAND_PENALTY = -7.0
CATEGORY_PENALTY = -9.0

# Cok yonluluk bonusu tavani
VERSATILITY_BONUS_MAX = 5.0


# Stil akisinda GOSTERILMEYECEK kategori parcalari.
#
# Kalibrasyonda "ABAFIP Erkek Sissy Tanga" urunu Y2K
# arketipinde 1. siraya cikti: eslesen kelimeler dogruydu
# ("low rise", "dusuk bel") ama urun ic giyim. Stil kesif
# akisi dis giyim ve ayakkabi gostermeli.
#
# Cocuk urunleri de ayni sebeple disarida: yetiskin stil
# arketipine gore siralanan bir akista bebek tulumu
# gostermek yanlis oneri.
EXCLUDED_CATEGORY_PATTERNS = (
    "%› Baby%",
    "%› Boys%",
    "%› Girls%",
    "%Underwear%",
    "%Lingerie%",
    "%Sleep & Lounge%",
    "%Sleepwear%",
    "%Costumes%",
    "%Novelty%",
)


# =========================================================
# CURSOR
# =========================================================

def encode_cursor(score, product_id, seen_ids):
    """
    Cursor'u URL'de tasinabilir tek bir metne cevirir.

    Icerik acikca okunabilir (base64, sifreleme degil):
    imzali/gizli olmasi gerekmiyor cunku icinde hassas veri
    yok ve sunucu her degeri yeniden dogruluyor.
    """

    payload = {
        "s": round(float(score), 4),
        "p": str(product_id),
        "n": list(seen_ids)[-CURSOR_SEEN_LIMIT:],
    }

    raw = json.dumps(payload, separators=(",", ":")).encode()

    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor):
    """
    Cursor'u ayristirir. Bozuk cursor hata vermez, bastan
    baslar: eski bir sekmeden gelen istek yuzunden 500
    donmek istemiyoruz.
    """

    if not cursor:
        return None

    try:
        padding = "=" * (-len(cursor) % 4)

        payload = json.loads(
            base64.urlsafe_b64decode(cursor + padding)
        )

        score = float(payload["s"])
        product_id = str(payload["p"])
        seen = [str(x) for x in payload.get("n", [])]

        return {
            "score": score,
            "product_id": product_id,
            "seen": seen[:CURSOR_SEEN_LIMIT],
        }

    except Exception:
        return None


# =========================================================
# SQL PARCALARI
# =========================================================

def _category_exclusion():
    """Stil akisina uygun olmayan kategorileri disla."""

    conditions = [
        Product.category.notilike(pattern)
        for pattern in EXCLUDED_CATEGORY_PATTERNS
    ]

    # Kategorisi olmayan urun (13 tane) disarida kalmasin
    return or_(
        Product.category.is_(None),
        and_(*conditions),
    )


def _eligibility():
    """
    Feed'de gosterilebilecek urunun temel kosulu.

    Fiyati veya gorseli olmayan urun karti bozuk gorunur ve
    egitim verisini kirletir.
    """

    return (
        Product.price.is_not(None),
        Product.price > 0,
        Product.image_url.is_not(None),
        Product.image_url != "",
        _category_exclusion(),
    )


def disliked_ids_subquery(user_id):
    """
    BEGENMEDIM denen urun kimlikleri.

    product_id IS NOT NULL SART: INITIAL_STYLE olaylari
    urune bagli olmadigi icin product_id NULL olabiliyor.
    NOT IN alt sorgusu tek bir NULL dondurse butun feed
    bosalirdi (x NOT IN (a, NULL) asla TRUE olmaz).
    """

    return (
        select(UserInteraction.product_id)
        .where(
            UserInteraction.user_id == user_id,
            UserInteraction.interaction_type == INTERACTION_DISLIKE,
            UserInteraction.product_id.is_not(None),
        )
    )


def wishlisted_ids_subquery(user_id):
    """Zaten favorilere eklenmis urunler."""

    return (
        select(WishlistItem.product_id)
        .where(WishlistItem.user_id == user_id)
    )


def _style_aggregate(selected_styles):
    """
    Secili tarzlarin skorlarini urun basina toplar.

    Doner: (subquery, best_score, best_style, second_score)

    array_agg(... ORDER BY score DESC) ile en iyi ve ikinci
    en iyi tarzi ayni sorguda cikariyoruz. Ayri sorgular
    atmak N+1 olurdu.
    """

    aggregate = (
        select(
            ProductStyleScore.product_id.label("product_id"),

            func.max(ProductStyleScore.score).label("best_score"),

            # En yuksek skorlu arketipin adi
            (
                func.array_agg(
                    ProductStyleScore.archetype,
                    order_by=ProductStyleScore.score.desc(),
                )[1]
            ).label("best_style"),

            # Ikinci en yuksek skor (yoksa NULL)
            (
                func.array_agg(
                    ProductStyleScore.score,
                    order_by=ProductStyleScore.score.desc(),
                )[2]
            ).label("second_score"),
        )
        .where(ProductStyleScore.archetype.in_(selected_styles))
        .group_by(ProductStyleScore.product_id)
        .subquery("style_agg")
    )

    return aggregate


def _versatility_expression(aggregate):
    """
    Cok yonluluk bonusu.

    style_engine.blend_scores ile AYNI form:
        ikinci skor esigi geciyorsa
        min(5, 5 * ikinci / birinci)

    Iki yerde ayni formul olmasi risk; degistirirken
    ikisini birlikte degistir.
    """

    ratio = (
        aggregate.c.second_score
        / func.greatest(aggregate.c.best_score, literal(1.0))
    )

    return case(
        (
            aggregate.c.second_score
            >= literal(style_engine.REASON_CHIP_THRESHOLD),
            func.least(
                literal(VERSATILITY_BONUS_MAX),
                literal(VERSATILITY_BONUS_MAX) * ratio,
            ),
        ),
        else_=literal(0.0),
    )


def _leaf_category_expression():
    """
    "... › Men › Clothing › Shirts › Polos" -> "polos"

    style_engine._leaf_category'nin SQL karsiligi.
    Son "›" isaretinden sonrasini alip kucuk harfe ceviriyor.
    """

    return func.lower(
        func.trim(
            func.regexp_replace(
                func.coalesce(Product.category, ""),
                "^.*›\\s*",
                "",
            )
        )
    )


def _personal_boost_expression(preference):
    """
    Kisisellestirme bonusu — SQL ifadesi.

    JSONB `?` operatoru (has_key) ile kullanicinin sik
    begendigi marka/kategori listesinde olup olmadigina
    bakiyoruz. top_brands anahtarlari style_engine.normalize
    ile kucuk harfe cevrilmis halde saklandigi icin burada
    da lower() kullaniyoruz.
    """

    if preference is None:
        return literal(0.0)

    brands = preference.top_brands or {}
    categories = preference.top_categories or {}
    avoid_brands = preference.avoid_brands or {}
    avoid_categories = preference.avoid_categories or {}
    median = preference.median_price

    parts = []

    if brands:
        parts.append(
            case(
                (
                    func.lower(
                        func.coalesce(Product.brand, "")
                    ).in_(list(brands.keys())),
                    literal(BRAND_BOOST),
                ),
                else_=literal(0.0),
            )
        )

    if categories:
        parts.append(
            case(
                (
                    _leaf_category_expression().in_(
                        list(categories.keys())
                    ),
                    literal(CATEGORY_BOOST),
                ),
                else_=literal(0.0),
            )
        )

    if median:
        # Medyanin %45 bandi icindeyse odul
        parts.append(
            case(
                (
                    func.abs(Product.price - literal(float(median)))
                    <= literal(float(median) * 0.45),
                    literal(PRICE_BOOST),
                ),
                else_=literal(0.0),
            )
        )

    # ---- Negatif agirliklar ----

    if avoid_brands:
        parts.append(
            case(
                (
                    func.lower(
                        func.coalesce(Product.brand, "")
                    ).in_(list(avoid_brands.keys())),
                    literal(BRAND_PENALTY),
                ),
                else_=literal(0.0),
            )
        )

    if avoid_categories:
        parts.append(
            case(
                (
                    _leaf_category_expression().in_(
                        list(avoid_categories.keys())
                    ),
                    literal(CATEGORY_PENALTY),
                ),
                else_=literal(0.0),
            )
        )

    if not parts:
        return literal(0.0)

    total = parts[0]
    for part in parts[1:]:
        total = total + part

    return total


# =========================================================
# ADAY SORGUSU
# =========================================================

def build_candidate_query(
    selected_styles,
    user_id=None,
    preference=None,
    cursor=None,
    exclude_ids=None,
):
    """
    Skorlu aday sorgusu.

    Doner: (statement, score_expression)

    statement satirlari: (Product, best_style, final_score)
    """

    aggregate = _style_aggregate(selected_styles)

    versatility = _versatility_expression(aggregate)
    personal = _personal_boost_expression(preference)

    # PRATIK TAVAN 97.
    #
    # Bilesenlerin toplami 111'e kadar cikabiliyor
    # (temel 95 + cok yonluluk 5 + marka 8 + kategori 6 +
    # fiyat 4). Kirpma olmasa "%100 AI Stil Uyumu" yazardi.
    #
    # 98-100 araligi bilincli olarak BOS BIRAKILDI: hicbir
    # icerik modeli durustce "%100 uyum" diyemez. Kullanici
    # 97 gordugunde "bu sistemin iddia edebilecegi en ust
    # seviye" anlamini alsin, sahte bir kesinlik degil.
    final_score = func.least(
        literal(97.0),
        func.cast(
            aggregate.c.best_score + versatility + personal,
            Float,
        ),
    ).label("final_score")

    statement = (
        select(
            Product,
            aggregate.c.best_style,
            aggregate.c.second_score,
            final_score,
        )
        .join(
            aggregate,
            aggregate.c.product_id == Product.product_id,
        )
        .where(*_eligibility())
    )

    if user_id is not None:
        statement = statement.where(
            Product.product_id.not_in(
                disliked_ids_subquery(user_id)
            ),
            Product.product_id.not_in(
                wishlisted_ids_subquery(user_id)
            ),
        )

    blocked = list(exclude_ids or [])

    if cursor:
        blocked.extend(cursor["seen"])

    if blocked:
        statement = statement.where(
            Product.product_id.not_in(blocked)
        )

    # ---- KEYSET ----
    #
    # (final_score, product_id) < (cursor_score, cursor_id)
    #
    # Skor esitliginde product_id ayirt edici oldugu icin
    # sira deterministik; ayni urun iki sayfada gorunmez.

    if cursor:
        statement = statement.where(
            func.row(final_score, Product.product_id)
            < func.row(
                literal(cursor["score"]),
                literal(cursor["product_id"]),
            )
        )

    statement = statement.order_by(
        final_score.desc(),
        Product.product_id.desc(),
    )

    return statement


def build_random_query(
    user_id=None,
    exclude_ids=None,
):
    """Kesif slotlari ve arketipsiz akis icin rastgele urun."""

    statement = select(Product).where(*_eligibility())

    if user_id is not None:
        statement = statement.where(
            Product.product_id.not_in(
                disliked_ids_subquery(user_id)
            ),
            Product.product_id.not_in(
                wishlisted_ids_subquery(user_id)
            ),
        )

    if exclude_ids:
        statement = statement.where(
            Product.product_id.not_in(list(exclude_ids))
        )

    return statement.order_by(func.random())


def count_pool(db: Session, user_id=None):
    """Kullaniciya gosterilebilecek toplam urun sayisi."""

    statement = (
        select(func.count())
        .select_from(Product)
        .where(*_eligibility())
    )

    if user_id is not None:
        statement = statement.where(
            Product.product_id.not_in(
                disliked_ids_subquery(user_id)
            ),
            Product.product_id.not_in(
                wishlisted_ids_subquery(user_id)
            ),
        )

    return db.scalar(statement) or 0


def count_style_pool(
    db: Session,
    archetype: str,
    minimum_score=None,
):
    """
    Bir arketipte badge esigini gecen urun sayisi.

    Stil secim ekraninda gercek sayiyi gosterebilmek icin.
    Katalog kapsami cok dengesiz (athleisure ~%29, y2k ~%3);
    kullanicinin bunu SECIM ANINDA gormesi gerekiyor.
    """

    threshold = (
        style_engine.MATCH_BADGE_THRESHOLD
        if minimum_score is None
        else minimum_score
    )

    return db.scalar(
        select(func.count())
        .select_from(ProductStyleScore)
        .join(
            Product,
            Product.product_id == ProductStyleScore.product_id,
        )
        .where(
            ProductStyleScore.archetype == archetype,
            ProductStyleScore.score >= threshold,
            *_eligibility(),
        )
    ) or 0


# =========================================================
# AKIS
# =========================================================

def get_feed(
    db: Session,
    user_id=None,
    selected_styles=None,
    limit: int = 12,
    cursor_token=None,
    exclude_ids=None,
):
    """
    Kesfet akisinin bir sayfasi.

    Doner: (items, meta)

    items ogesi:
        {
          product, match_score, match_label, reason_label,
          matched_style, is_exploration, position
        }

    meta:
        {
          personalized, selected_styles, liked_count,
          next_cursor, exploration_slots, has_more
        }
    """

    styles = style_engine.normalize_selected_styles(
        selected_styles or []
    )

    cursor = decode_cursor(cursor_token)

    seen = list(cursor["seen"]) if cursor else []

    preference = None

    if user_id is not None:
        preference = db.scalar(
            select(UserPreference).where(
                UserPreference.user_id == user_id
            )
        )

    # -----------------------------------------------------
    # Tarz secilmemis: rastgele akis, skor yok
    # -----------------------------------------------------

    if not styles:

        products = list(
            db.scalars(
                build_random_query(
                    user_id,
                    exclude_ids=list(exclude_ids or []) + seen,
                ).limit(limit)
            ).all()
        )

        items = [
            {
                "product": product,
                "match_score": None,
                "match_label": None,
                "reason_label": None,
                "matched_style": None,
                "is_exploration": True,
                "position": index,
            }
            for index, product in enumerate(products)
        ]

        seen.extend(p.product_id for p in products)

        next_cursor = (
            encode_cursor(0.0, "", seen) if products else None
        )

        return items, {
            "personalized": False,
            "selected_styles": [],
            "liked_count": 0,
            "next_cursor": next_cursor,
            "exploration_slots": len(items),
            "has_more": len(products) == limit,
        }

    # -----------------------------------------------------
    # Slot dagilimi
    # -----------------------------------------------------

    explore_slots = (
        round(limit * EXPLORATION_RATIO) if limit >= 4 else 0
    )
    exploit_slots = limit - explore_slots

    # -----------------------------------------------------
    # 1. Skorlu adaylar (keyset)
    # -----------------------------------------------------

    rows = db.execute(
        build_candidate_query(
            styles,
            user_id=user_id,
            preference=preference,
            cursor=cursor,
            exclude_ids=exclude_ids,
        ).limit(exploit_slots)
    ).all()

    scored_items = []

    for product, best_style, second_score, final_score in rows:

        # Gerekce icin temel skorun sebeplerini yeniden
        # uretiyoruz. Skoru DEGISTIRMIYOR; yalnizca hangi
        # sinyallerin tetiklendigini soyluyor.
        _, reasons, _ = style_engine.score_product_for_archetype(
            product, best_style
        )

        if (
            second_score is not None
            and second_score >= style_engine.REASON_CHIP_THRESHOLD
        ):
            reasons.append("style:versatile")

        # SQL'de marka/kategori bonusu uygulandiysa gerekceye
        # de yansisin
        if preference:
            brand = style_engine.normalize(product.brand or "")
            leaf = style_engine._leaf_category(product.category)

            if brand and brand in (preference.top_brands or {}):
                reasons.insert(0, "history:brand")
            elif leaf and leaf in (preference.top_categories or {}):
                reasons.insert(0, "history:category")

        display = style_engine.build_match_display(
            round(float(final_score), 2),
            reasons,
            matched_style=best_style,
            product=product,
        )

        scored_items.append(
            {
                "product": product,
                "is_exploration": False,
                **display,
            }
        )

    # Sonraki cursor: bu sayfada tuketilen SON aday
    next_cursor = None

    if rows:
        last_product, _, _, last_score = rows[-1]

        seen.extend(
            item["product"].product_id for item in scored_items
        )

    # -----------------------------------------------------
    # 2. Kesif slotlari
    # -----------------------------------------------------

    exploration_items = []

    if explore_slots > 0:

        blocked = (
            list(exclude_ids or [])
            + seen
            + [i["product"].product_id for i in scored_items]
        )

        products = list(
            db.scalars(
                build_random_query(
                    user_id,
                    exclude_ids=blocked,
                ).limit(explore_slots)
            ).all()
        )

        for product in products:

            display = style_engine.build_match_display(
                None,
                [],
                matched_style=None,
                product=product,
                is_exploration=True,
            )

            exploration_items.append(
                {
                    "product": product,
                    "is_exploration": True,
                    **display,
                }
            )

            seen.append(product.product_id)

    # -----------------------------------------------------
    # 3. Birlestirme
    # -----------------------------------------------------
    #
    # Kesif urunlerini sona koymak position bias yaratir:
    # her zaman en altta olan urun az etkilesim alir ve veri
    # yine yanli olur. Araya serpistiriyoruz.

    items = []
    exploration_queue = list(exploration_items)
    exploit_index = 0
    slot = 0

    while len(items) < limit and (
        exploit_index < len(scored_items) or exploration_queue
    ):
        take_exploration = exploration_queue and (
            slot % 4 == 3 or exploit_index >= len(scored_items)
        )

        if take_exploration:
            item = exploration_queue.pop(0)
        else:
            item = scored_items[exploit_index]
            exploit_index += 1

        item["position"] = slot
        items.append(item)

        slot += 1

    if rows:
        next_cursor = encode_cursor(
            float(last_score),
            last_product.product_id,
            seen,
        )

    return items, {
        "personalized": True,
        "selected_styles": styles,
        "liked_count": (
            preference.like_count if preference else 0
        ) or 0,
        "next_cursor": next_cursor,
        "exploration_slots": len(exploration_items),
        "has_more": len(rows) == exploit_slots,
    }


def count_combined_pool(db: Session, selected_styles):
    """
    Secili tarzlarin BIRLESIK havuzu (tekil urun sayisi).

    Tek tek toplamak yanlis olur: ayni urun iki tarzda da
    badge esigini gecebilir ve iki kez sayilir.
    """

    styles = style_engine.normalize_selected_styles(
        selected_styles or []
    )

    if not styles:
        return 0

    return db.scalar(
        select(func.count(func.distinct(ProductStyleScore.product_id)))
        .select_from(ProductStyleScore)
        .join(
            Product,
            Product.product_id == ProductStyleScore.product_id,
        )
        .where(
            ProductStyleScore.archetype.in_(styles),
            ProductStyleScore.score
            >= style_engine.MATCH_BADGE_THRESHOLD,
            *_eligibility(),
        )
    ) or 0
