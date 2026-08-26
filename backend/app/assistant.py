"""
AI ALISVERIS ASISTANI — WishNN uyarlamasi.

Bu dosya artik bir sohbet MOTORU degil, motorun WishNN'e
baglandigi yer. Motor `toolchat` paketinde
(packages/toolchat) ve uygulamaya ozel hicbir sey bilmiyor:
model zinciri, kota devri, arac dongusu, kart secimi,
direktif ayiklama ve dayanak denetimi orada.

BURADA KALAN — yalnizca WishNN'e ait olanlar:

    araclar        search_catalog / get_product_details
    sistem prompt  stil danismani personasi ve kurallari
    doviz kuru     katalog USD, kullanici TL konusuyor
    on arama       query_engine sinyal buldu mu
    kart sekli     arayuzun bekledigi urun alanlari
    denylist       katalogda olmadigi dogrulanmis markalar

NEDEN AYRILDI
Ilk surumde bunlarin hepsi tek dosyadaydi (1732 satir) ve iki
sey birbirine gecmisti: "Gemini kotasi doldugunda ne yapmali"
gibi HER projede ayni olan kararlar ile "keten gomlek nasil
aranir" gibi yalnizca WishNN'e ait olanlar. Ilkini baska bir
projeye tasimanin yolu kopyala-yapistirdi.

DIS SOZLESME DEGISMEDI
main.py hala su ucunu cagiriyor:

    assistant.run_chat(db=..., messages=..., user=...)
    assistant.QuotaExceeded
    assistant.get_usd_try_rate()

Donen sozluk de ayni: reply / products / tool_calls / model /
ungrounded. Yani uc, sema ve arayuz bu degisiklikten
etkilenmedi.

NEDEN ARAC CAGIRMA (kisa hatirlatma)
Butun katalogu (728 urun) prompta doldurmak her mesajda ~200k
token demek ve model urun UYDURABILIR. Bunun yerine modele
ARAMA YETKISI veriyoruz: `search_catalog` cagirir, biz GERCEK
veritabani sonucunu geri veririz, model yalnizca kendisine
verilen urunler hakkinda konusur. Ekranda gorunen kartlar da
ayni arac sonucundan uretilir.

ARAMA YENIDEN YAZILMADI
`search_catalog` yeni bir arama motoru degil. /api/search
ucunun kullandigi UC ADIMIN aynisini cagiriyor:

    query_engine.analyze()  ->  embed_query()  ->  search_service.search()

Yani sozlukler, esanlamli genisletme, hibrit siralama ve filtre
gevsetme merdiveni sohbette de aynen calisiyor.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, replace
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session
from toolchat import (
    DEFAULT_MODEL_CHAIN,
    Assistant,
    AssistantConfig,
    ConfigurationError,
    GroundingPolicy,
    ModelTimeout,
    Prefetch,
    QuotaExceeded,
    ToolContext,
    ToolResult,
    ToolSpec,
)

from app import (
    color_match,
    crud,
    currency,
    price_intent,
    query_engine,
    search_service,
    style_engine,
)
from app.embeddings import embed_query
from app.models import User

logger = logging.getLogger(__name__)

# main.py bunlari `assistant.X` olarak yakaliyor; import yolu
# degisse bile ucun kodu degismesin diye burada duruyorlar.
__all__ = [
    "run_chat",
    "stream_chat",
    "QuotaExceeded",
    "ModelTimeout",
    "ConfigurationError",
    "get_usd_try_rate",
    "DEFAULT_MODEL_CHAIN",
]


# Bir cevapta kart olarak gosterilecek en fazla urun.
MAX_CARDS = 8

# Tek arac cagrisinda donebilecek en fazla urun.
MAX_TOOL_RESULTS = 12


# =========================================================
# DOVIZ KURU
# =========================================================
#
# Katalog fiyatlari USD (Amazon kaynakli). Kullanici ise
# "3000 TL altinda" diye konusuyor.
#
# KUR ARTIK app/currency.py'DE. Sebep: fiyat filtresi artik
# SQL'de calisiyor (search_service._apply_price) ve arama
# motorunun da ayni kura ihtiyaci var. Iki yerde ayri
# hesaplanirsa arama 3000 TL siniriyla filtreler, kart baska
# bir kurdan 3100 TL yazar — sistem kendi soyledigini
# yalanlar.
#
# Bu isimler main.py ve /exchange-rate ucu icin duruyor.

FALLBACK_USD_TRY = currency.FALLBACK_USD_TRY

get_usd_try_rate = currency.get_usd_try_rate

_to_try = currency.to_try


# =========================================================
# ISTEK BAGLAMI
# =========================================================

@dataclass
class ChatRequest:
    """
    Bir sohbet turu boyunca araclarin ihtiyac duydugu her sey.

    Motor bu nesnenin icine BAKMAZ; oldugu gibi araclara ve
    sistem prompt fonksiyonuna tasir. Yani veritabani oturumu
    modulun sozlesmesine hic girmiyor.
    """

    db: Session
    user: User | None
    rate: float


# =========================================================
# ARAC TANIMLARI
# =========================================================
#
# Aciklamalar modelin OKUDUGU tek dokumantasyon. Ne zaman
# cagiracagini buradan ogreniyor, bu yuzden aciklamalar
# kullanici icin degil MODEL icin yazildi.
#
# Semalar duz JSON Schema sozlugu: motor bunu SDK tipine
# kendisi ceviriyor ve argumanlari semaya gore duzeltiyor
# (metin -> sayi, enum disi degeri atma, "3000 TL" -> 3000).

SEARCH_CATALOG_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Aranacak ürünün Türkçe doğal dil tarifi. "
                "Örnek: 'yazlık ince keten erkek gömleği'. "
                "Konuşmadan öğrendiğin bağlamı buraya DAHİL ET "
                "— kullanıcı önceki mesajda 'siyah olsun' "
                "dediyse sorguya siyah yaz."
            ),
        },
        "gender": {
            "type": "string",
            "enum": ["women", "men"],
            "description": (
                "Cinsiyet filtresi. Yalnızca konuşmadan AÇIKÇA "
                "biliyorsan gönder. Emin değilsen boş bırak — "
                "tahmin etme."
            ),
        },
        "color": {
            "type": "string",
            "description": (
                "Renk filtresi — kullanıcı bir renk söylediyse "
                "GÖNDER. Türkçe renk adı yaz: siyah, beyaz, gri, "
                "antrasit, bej, krem, lacivert, mavi, turkuaz, "
                "kahverengi, taba, bordo, kırmızı, somon, pembe, "
                "gül kurusu, mor, lila, yeşil, zeytin yeşili, "
                "sarı, hardal, turuncu, petrol. "
                "Renk eşleştirmesi ürün görsellerinden ölçülen "
                "gerçek renkle yapılıyor, açıklama metniyle "
                "değil — yani bu alanı doldurmak sorguya rengi "
                "yazmaktan daha isabetli. Kullanıcı renk "
                "belirtmediyse BOŞ BIRAK, tahmin etme."
            ),
        },
        "max_price_try": {
            "type": "number",
            "description": (
                "Üst fiyat sınırı, Türk Lirası cinsinden. "
                "Kullanıcı bütçe belirttiyse gönder. Bu sınır "
                "veritabanında uygulanıyor ve ASLA "
                "gevşetilmiyor: dönen ürünlerin hepsi bu "
                "fiyatın altındadır."
            ),
        },
        "min_price_try": {
            "type": "number",
            "description": "Alt fiyat sınırı, Türk Lirası cinsinden.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TOOL_RESULTS,
            "description": (
                "Kaç ürün dönsün (1-12). Varsayılan 6. Kullanıcı "
                "'birkaç seçenek' derse 4-6, 'daha fazla göster' "
                "derse 10-12 kullan."
            ),
        },
    },
    "required": ["query"],
}


GET_PRODUCT_DETAILS_SCHEMA = {
    "type": "object",
    "properties": {
        "product_id": {
            "type": "string",
            "description": (
                "Ürünün kimliği. Daha önce search_catalog "
                "sonucunda dönen product_id değerlerinden biri "
                "olmalı."
            ),
        },
    },
    "required": ["product_id"],
}


# =========================================================
# URUN TEMSILLERI
# =========================================================

def _product_for_card(product, rate: float) -> dict:
    """
    Arayuzdeki sohbet kartinin ihtiyaci olan alanlar.

    NEDEN ORM NESNESI DEGIL DUZ SOZLUK
    Arac cagrisi bir okuma transaction'i aciyor ve SQLAlchemy
    onu commit/rollback'e kadar acik tutuyor. Araya LLM cagrisi
    giriyor: normalde 4-5 saniye, ama kuyrukta beklerken
    dakikalara cikabiliyor. Neon'un
    idle_in_transaction_session_timeout'u bu sirada baglantiyi
    dusuruyor (gercekten yasandi).

    Cozum: urunu okurken ihtiyacimiz olan HER SEYI aliyoruz,
    sonra transaction kapatilabiliyor. ORM nesnesi tasinsa
    rollback sonrasi alanlar expire olur ve serilestirme aninda
    yeni sorgu tetiklenirdi.

    FIYAT IKI BICIMDE GIDIYOR:

      price      USD — sitenin geri kalaniyla ayni sekil
      price_try  TL  — bu turda filtre icin kullanilan kur

    Ikincisi eklendi cunku arayuz TL fiyatini kendi kuruyla
    hesapliyordu ve kur alinamazsa sabit yedege (47.88)
    dusuyordu. Asistan "3000 TL altinda" diye filtreledigi
    halde kartta 3100 TL yazabiliyordu — sistemin kendi
    soyledigini yalanlamasi. Artik kartta yazan sayi,
    filtrenin kullandigi sayidir.
    """

    return {
        "product_id": product.product_id,
        "title": product.title,
        "title_tr": product.title_tr,
        "brand": product.brand,
        "category": product.category,
        "price": product.price,
        "price_try": currency.to_try(product.price, rate),
        "rating": product.rating,
        "rating_count": product.rating_count,
        "image_url": product.image_url,
    }


# =========================================================
# KATALOG FIYAT DAGILIMI
# =========================================================
#
# NEDEN GEREKLI
# Model tek tek fiyatlari goruyor ama "bu pahali mi, ucuz mu"
# sorusuna cevap veremiyor: karsilastirma noktasi yok.
# Olculen davranis: kullanici "ucuz bir tisort" dediginde
# asistan hicbir fiyat filtresi uygulamiyor ve 4.800 TL'lik
# urunu "uygun fiyatli" diye sunuyordu.
#
# Dagilim sistem talimatina giriyor (bir kez, 6 saat
# onbellekli) ve "ucuz" niyeti sayiya cevrilirken de
# kullaniliyor (price_intent.resolve).

_PRICE_STATS_TTL_SECONDS = 6 * 60 * 60

_price_stats_cache: dict = {
    "value": None,
    "fetched_at": 0.0,
    "rate": None,
}


def catalog_price_stats(db: Session) -> price_intent.PriceStats | None:
    """
    Katalogun TL fiyat dagilimi — 6 saat onbellekli.

    Yuzdelikler SQL'de hesaplaniyor (percentile_cont): 728
    fiyati Python'a tasimanin bir faydasi yok.

    Kur degistiginde onbellek dusuyor: dagilim TL cinsinden
    ve kur onun tamamini kaydirir.
    """

    rate = currency.get_usd_try_rate()

    now = time.monotonic()

    cached = _price_stats_cache["value"]

    if (
        cached is not None
        and _price_stats_cache["rate"] == rate
        and now - _price_stats_cache["fetched_at"] < _PRICE_STATS_TTL_SECONDS
    ):
        return cached

    try:
        row = db.execute(
            text(
                """
                SELECT min(price),
                       percentile_cont(0.33) WITHIN GROUP (ORDER BY price),
                       percentile_cont(0.50) WITHIN GROUP (ORDER BY price),
                       percentile_cont(0.66) WITHIN GROUP (ORDER BY price),
                       max(price),
                       count(*)
                FROM products
                WHERE price IS NOT NULL AND price > 0
                """
            )
        ).first()

    except Exception as error:

        logger.warning("Katalog fiyat dagilimi okunamadi: %s", error)

        # Basarisiz sorgu oturumu "rollback bekliyor" durumunda
        # birakiyor; ayni istekteki sonraki sorgular da
        # PendingRollbackError ile duserdi. Fiyat baglami
        # olmadan devam etmek kabul edilebilir, aramanin
        # cokmesi degil.
        try:
            db.rollback()
        except Exception:
            pass

        return cached

    if row is None or row[5] in (None, 0):
        return None

    stats = price_intent.PriceStats(
        minimum=currency.to_try(row[0], rate) or 0.0,
        p33=currency.to_try(row[1], rate) or 0.0,
        median=currency.to_try(row[2], rate) or 0.0,
        p66=currency.to_try(row[3], rate) or 0.0,
        maximum=currency.to_try(row[4], rate) or 0.0,
        count=int(row[5]),
    )

    _price_stats_cache["value"] = stats
    _price_stats_cache["fetched_at"] = now
    _price_stats_cache["rate"] = rate

    return stats


def _product_for_model(product, rate: float) -> dict:
    """
    Modele giden kompakt urun temsili.

    Aciklama ve ozellikler BILEREK yok: bir arama sonucunda 8
    urunun tam aciklamasi binlerce token eder ve modelin
    kullanici mesajina odagini dagitir. Detay gerekirse model
    get_product_details ile ayrica ister.
    """

    title = (product.title_tr or product.title or "").strip()

    return {
        "product_id": product.product_id,
        "title": title[:110],
        "brand": product.brand or "",
        "category": product.category or "",
        "price_try": _to_try(product.price, rate),
        "rating": product.rating,
        "rating_count": product.rating_count or 0,
    }


# =========================================================
# ARAC UYGULAMALARI
# =========================================================

def _apply_color_argument(intent, color: str | None) -> str | None:
    """
    Modelin verdigi rengi niyete islerir.

    NEDEN GEREKLI
    Renk eskiden yalnizca SORGU METNI icinden okunuyordu.
    Model "siyah" kelimesini query'ye yazmayi unuttugunda renk
    tamamen kayboluyordu; ustelik konusmanin basinda soylenmis
    bir renk ("siyah olsun") sonraki turda metinde
    tekrarlanmiyordu. Cinsiyet icin cozulmus olan sorun
    renkte cozulmemisti.

    Doner: taninan rengin adi (yoksa None).
    """

    if not color:
        return None

    target = color_match.resolve(color)

    if target is None:
        logger.info("Taninmayan renk argumani: %r", color)
        return None

    # Palet slug'i query_engine anahtarina cevrilmiyor: renk
    # eslestirmesi artik color_match uzerinden yapiliyor ve o
    # slug'lari da anlar. Metin eslesmesi icin de slug yeterli
    # (COLOR_TERMS'te yoksa kelimenin kendisi aranir).
    intent.colors = [target.slug]

    return target.label


def _price_summary(products, rate: float) -> dict | None:
    """
    Sonuclarin fiyat dagilimi — modelin FIYAT ALGISI icin.

    Model tek tek fiyatlari goruyor ama "bu pahali mi" sorusuna
    cevap veremiyor. Ozetle birlikte "3 secenek 2.000 TL
    altinda, en pahalisi 5.400 TL" gibi cumleler kurabiliyor.
    """

    values = [
        currency.to_try(product.price, rate)
        for product in products
        if product.price is not None
    ]

    values = [value for value in values if value is not None]

    if not values:
        return None

    values.sort()

    return {
        "min_try": round(values[0]),
        "median_try": round(values[len(values) // 2]),
        "max_try": round(values[-1]),
    }


def _cheapest_alternative(request: "ChatRequest", intent) -> float | None:
    """
    Butce yuzunden sonuc bosaldiysa: ayni kriterlerdeki EN UCUZ
    urunun fiyati.

    NEDEN
    "Bu butcede urun yok" dogru ama yetersiz bir cevap.
    Kullanicinin bilmek istedigi sey "peki ne kadara var".
    Butce sinirini kaldirip tek bir sorgu daha atiyoruz —
    yalnizca sonuc BOS oldugunda, yani nadir durumda.
    """

    try:
        relaxed = query_engine.analyze(intent.raw)
        relaxed.gender = intent.gender
        relaxed.colors = list(intent.colors)
        relaxed.price = replace(
            intent.price, min_try=None, max_try=None
        )

        items, _ = search_service.search(
            db=request.db,
            intent=relaxed,
            query_embedding=None,
            limit=12,
            offset=0,
            usd_try_rate=request.rate,
        )

    except Exception as error:

        logger.warning("En ucuz alternatif bulunamadi: %s", error)

        return None

    prices = [
        currency.to_try(item["product"].price, request.rate)
        for item in items
        if item["product"].price is not None
    ]

    prices = [price for price in prices if price is not None]

    return round(min(prices)) if prices else None


def _search_catalog(args: dict, ctx: ToolContext) -> ToolResult:

    request: ChatRequest = ctx.request

    query = str(args.get("query") or "").strip()

    if not query:
        return ToolResult(payload={"error": "query bos olamaz."})

    # Sema limiti 1-12 arasina cekiyor; varsayilan burada.
    limit = int(args.get("limit") or 6)

    # ADIM 1 — ANLA. /api/search ile ayni cozumleyici. Butce de
    # burada okunuyor: "3000 TL altinda" cumlesi artik SAYIYA
    # donusuyor (bkz. price_intent).
    intent = query_engine.analyze(query)

    # Modelin acik cinsiyet bilgisi, sozluk tahminini EZER.
    # Sebep: cinsiyet konusmanin basinda soylenip sonraki
    # sorgularda tekrarlanmayan bir bilgi. "peki ayakkabi?"
    # cumlesinde cinsiyet yok ama model biliyor.
    gender = args.get("gender")

    if gender in ("women", "men"):
        intent.gender = gender

    color_label = _apply_color_argument(intent, args.get("color"))

    # MODELIN BUTCESI, CUMLEDEN OKUNANI EZER.
    #
    # Model konusmanin tamamini goruyor: butce iki mesaj once
    # soylenmis olabilir. Yalnizca VERDIGI sinir degisiyor,
    # digeri korunuyor — "en fazla 3000" dedikten sonra "en az
    # 1000" demek ikisini birden gecerli kilar.
    model_min = args.get("min_price_try")
    model_max = args.get("max_price_try")

    if model_min is not None or model_max is not None:

        intent.price = replace(
            intent.price,
            min_try=(
                float(model_min)
                if model_min is not None
                else intent.price.min_try
            ),
            max_try=(
                float(model_max)
                if model_max is not None
                else intent.price.max_try
            ),
            source=(intent.price.source or "") + "+model",
        )

    # SAYISIZ BUTCE NIYETI ("ucuz bir sey") KATALOGA GORE
    # SAYIYA CEVRILIR. Mutlak bir "ucuz" yok; dagilimin alt
    # ucu var.
    if intent.price.kind and not intent.price.has_bounds:
        intent.price = price_intent.resolve(
            intent.price, catalog_price_stats(request.db)
        )

    # ADIM 2 — VEKTORLE. Ham sorgu degil, zenginlestirilmis
    # metin. (Neden: bkz. docs/AI_SEARCH.md)
    vector = embed_query(intent.embed_text)

    # ADIM 3 — ARA. Hibrit siralama + gevsetme merdiveni.
    # Fiyat filtresi artik SQL'de (ve merdivenin disinda):
    # once genis cekip Python'da elemek, butceye uyan urun
    # ilk 48'de degilse "yok" demeye yol aciyordu.
    items, meta = search_service.search(
        db=request.db,
        intent=intent,
        query_embedding=vector,
        limit=limit,
        offset=0,
        usd_try_rate=request.rate,
    )

    products = [item["product"] for item in items][:limit]

    # SON KONTROL — BUTCE SINIRI.
    #
    # Filtre SQL'de calisiyor, yani bu satirin normalde hicbir
    # sey yapmamasi gerekiyor. Yine de duruyor cunku iddia
    # cok net: "listedeki butun urunler butcenin icinde".
    # Bu cumleyi soyleyen yerin onu DOGRULAMASI gerekir; bir
    # gun filtre kazara kalkarsa hata sessizce kullaniciya
    # gitmesin.
    if intent.price.has_bounds:

        allowed = []

        for product in products:

            price_try = currency.to_try(product.price, request.rate)

            if price_try is None:
                continue

            if (
                intent.price.min_try is not None
                and price_try < intent.price.min_try
            ):
                continue

            if (
                intent.price.max_try is not None
                and price_try > intent.price.max_try
            ):
                continue

            allowed.append(product)

        if len(allowed) != len(products):
            logger.warning(
                "Butce disi %s urun son kontrolde elendi "
                "(SQL filtresi beklenmedik bicimde uygulanmadi).",
                len(products) - len(allowed),
            )

        products = allowed

    payload = {
        "found": len(products),
        "products": [
            _product_for_model(product, request.rate)
            for product in products
        ],
    }

    if intent.price.has_bounds:

        payload["price_filter_applied"] = {
            "min_try": intent.price.min_try,
            "max_try": intent.price.max_try,
            "note": (
                "Bu sinir veritabaninda uygulandi; listedeki "
                "butun urunler bu araligin icinde."
            ),
        }

    summary = _price_summary(products, request.rate)

    if summary:
        payload["price_range_try"] = summary

    if color_label:
        payload["color_filter"] = {
            "label": color_label,
            "source": meta.get("color_source"),
            "note": (
                "Renk urun gorselinden olculen degerle "
                "eslestirildi."
                if meta.get("color_source") == "measured"
                else "Renk yalnizca urun metninden eslestirildi; "
                     "katalogda urunlerin cogu rengini metninde "
                     "yazmiyor, bu yuzden liste eksik olabilir."
            ),
        }

    # Merdiven bir kisiti biraktiysa model bunu BILMELI ki
    # kullaniciya durustce soyleyebilsin ("tam siyah bulamadim,
    # yakin tonlari getirdim").
    if meta.get("relaxed"):
        payload["relaxed_filters"] = meta["relaxed"]

    if not products:

        if intent.price.has_bounds:

            cheapest = _cheapest_alternative(request, intent)

            payload["note"] = (
                "Bu butcede bu kriterlere uyan urun YOK. "
                "Kullaniciya durustce soyle."
            )

            if cheapest:
                payload["cheapest_matching_try"] = cheapest
                payload["note"] += (
                    f" Ayni aramada butce disinda kalan en ucuz "
                    f"urun {cheapest} TL — bunu soyleyebilirsin."
                )

        else:
            payload["note"] = (
                "Bu kriterlerle katalogda urun yok. Kullaniciya "
                "durustce soyle ve kisitlardan birini gevsetmeyi "
                "oner (butce, renk veya kategori)."
            )

    return ToolResult(
        payload=payload,
        cards=[
            _product_for_card(product, request.rate)
            for product in products
        ],
    )


def _get_product_details(args: dict, ctx: ToolContext) -> ToolResult:

    request: ChatRequest = ctx.request

    product_id = str(args.get("product_id") or "").strip()

    if not product_id:
        return ToolResult(payload={"error": "product_id bos olamaz."})

    product = crud.get_product(db=request.db, product_id=product_id)

    if product is None:
        return ToolResult(
            payload={
                "error": (
                    f"'{product_id}' katalogda yok. Yalnizca "
                    "search_catalog sonucundaki kimlikleri kullan."
                )
            }
        )

    reviews = crud.get_product_reviews(
        db=request.db,
        product_id=product_id,
        limit=8,
        offset=0,
    )

    review_payload = []

    for review in reviews:

        text = (
            review.review_text
            or review.source_cleaned_review_text
            or ""
        ).strip()

        if not text:
            continue

        review_payload.append(
            {
                "rating": review.rating,
                "verified": bool(review.verified_purchase),
                "text": text[:280],
            }
        )

    description = (
        product.description_tr or product.description or ""
    ).strip()

    features = (product.features_tr or product.features or "").strip()

    return ToolResult(
        payload={
            "product": _product_for_model(product, request.rate),
            "description": description[:900],
            "features": features[:600],
            "availability": product.availability or "",
            "reviews": review_payload,
            "review_note": (
                "Yorum yok."
                if not review_payload
                else "Yalnizca bu yorumlarda yazani soyle."
            ),
        },
        cards=[_product_for_card(product, request.rate)],
    )


TOOLS = [
    ToolSpec(
        name="search_catalog",
        description=(
            "WishNN kataloğunda ürün arar. Kullanıcı bir ürün "
            "tarif ettiğinde, bir öneri istediğinde veya aramayı "
            "daralttığında BU ARACI ÇAĞIR. Asla kendi bilgine "
            "dayanarak ürün uydurma — gösterilecek her ürün bu "
            "aracın döndürdüğü sonuçlardan gelmeli. Sonuçlar "
            "anlamsal arama ile bulunur, birebir kelime eşleşmesi "
            "değildir; doğal bir cümle ver, anahtar kelime listesi "
            "değil."
        ),
        parameters=SEARCH_CATALOG_SCHEMA,
        handler=_search_catalog,
    ),
    ToolSpec(
        name="get_product_details",
        description=(
            "Tek bir ürünün tam açıklamasını, özelliklerini ve "
            "gerçek müşteri yorumlarını getirir. Kullanıcı daha "
            "önce gösterilmiş bir ürün hakkında soru sorduğunda "
            "kullan: 'bu kumaşı ne?', 'yorumlar ne diyor?', "
            "'kalıbı nasıl?'. Yorumlara dayanarak konuşurken "
            "abartma, yorumlarda geçmeyen bir şeyi söyleme."
        ),
        parameters=GET_PRODUCT_DETAILS_SCHEMA,
        handler=_get_product_details,
    ),
]


# =========================================================
# SISTEM TALIMATI
# =========================================================

def _user_context(db: Session, user: User | None) -> str:
    """
    Giris yapmis kullanicinin bildigimiz tercihleri.

    Yalnizca ZATEN sahip oldugumuz veri: ad, cinsiyet, yas ve
    Kesfet icin sectigi stil arketipleri. Ek sorgu maliyeti tek
    satirlik bir user_preferences okumasi.
    """

    if user is None:
        return (
            "Kullanıcı giriş yapmamış. Kişisel geçmişini "
            "bilmiyorsun; favorilere ekleme gibi hesap "
            "gerektiren işlemleri sen yapamazsın, kullanıcı "
            "ürün kartındaki kalp simgesine basmalı."
        )

    lines = []

    if user.first_name:
        lines.append(f"Adı: {user.first_name}")

    if user.gender:
        lines.append(f"Cinsiyet: {user.gender}")

    if user.age:
        lines.append(f"Yaş: {user.age}")

    try:
        preference = crud.get_preference(db, user.id)
    except Exception as error:
        logger.warning("Tercih okunamadi: %s", error)
        preference = None

    selected = list(
        (preference.selected_styles or []) if preference else []
    )

    if selected:

        labels = []

        for archetype in selected:

            profile = style_engine.ARCHETYPE_PROFILES.get(archetype)

            labels.append(profile["label"] if profile else archetype)

        lines.append("Keşfet için seçtiği tarzlar: " + ", ".join(labels))

    if not lines:
        return "Kullanıcı giriş yapmış ama profili boş."

    return (
        "Giriş yapmış kullanıcı hakkında bildiklerin:\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nBu bilgileri önerilerinde sessizce kullan; "
        "her mesajda kullanıcıya geri sayma."
    )


def _price_context(db: Session) -> str:
    """
    Katalogun fiyat dagilimi — modelin "pahali/ucuz" sozcugunu
    dogru kullanabilmesi icin.

    Olculen hata: fiyat baglami olmayan model 4.800 TL'lik bir
    tisorte "uygun fiyatli" diyordu. Bir sayinin pahali olup
    olmadigi ancak dagilim icindeki yerinden anlasilir.

    Veritabani okunamazsa BOS DONER: eksik baglam, yanlis
    baglamdan iyidir.
    """

    stats = catalog_price_stats(db)

    if stats is None:
        return ""

    def money(value: float) -> str:
        return f"{value:,.0f}".replace(",", ".")

    return f"""

KATALOG FİYAT ARALIĞI (TL, {stats.count} ürün)
En ucuz {money(stats.minimum)} · alt üçlük {money(stats.p33)} \
· orta {money(stats.median)} · üst üçlük {money(stats.p66)} \
· en pahalı {money(stats.maximum)}.
Bir ürüne "uygun fiyatlı" demek için fiyatı {money(stats.p33)} \
TL civarında ya da altında olmalı; {money(stats.p66)} TL \
üstü bu katalogda pahalı sayılır. Kullanıcı "ucuz bir şey" \
derse bu aralığın alt ucundan ara."""


def _system_prompt(request: ChatRequest) -> str:
    """
    Sistem talimati. Her istekte yeniden uretiliyor cunku
    kullanici baglami (ad, tarzlar) ve fiyat dagilimi icinde.
    """

    return f"""Sen WishNN'in kişisel stil danışmanısın. WishNN bir moda \
e-ticaret sitesi. Kullanıcıyla Türkçe, sıcak ve net konuşursun.

GÖREVİN
Kullanıcının ne aradığını anlamak ve KATALOGDAN gerçek ürünler \
bulmak. Genel moda tavsiyesi veren bir sohbet botu değilsin; \
işin sonunda kullanıcının önüne somut ürünler koymak var.

DEĞİŞMEZ KURALLAR

1. Ürün uydurma. Bahsettiğin her ürün search_catalog'un \
döndürdüğü sonuçlardan gelmeli.

1b. MARKA ADI KURALI — en sık yaptığın hata bu. Cevabında \
yazdığın her marka adı, search_catalog sonucundaki bir ürünün \
"brand" veya "title" alanında AYNEN geçiyor olmalı. Katalog \
Amazon kaynaklı ve içinde Türk perakende markaları YOK: Koton, \
LC Waikiki, Trendyol, Defacto, Mavi gibi isimleri asla yazma. \
Hangi markayı yazacağını hatırlamıyorsan marka adı hiç kullanma \
— "keten olan" veya "V yakalı model" demek, olmayan bir marka \
uydurmaktan iyidir. Arama yapmadıysan hiçbir ürünü adıyla anma.

2a. GEREKSİZ ARAMA YAPMA. Konuşmada zaten bir search_catalog \
sonucu varsa ve kullanıcının son sorusunu karşılıyorsa \
DOĞRUDAN cevabı yaz — aramayı tekrarlamak kullanıcıyı boşuna \
bekletiyor. Yalnızca gerçekten farklı bir şey aramak \
gerekiyorsa (kategori değişti, bütçe değişti, sonuçlar \
alakasız) aracı çağır.

2. Önce ara, sonra soru sor. Kullanıcının söylediği kadarıyla \
bir arama YAPILABİLİYORSA yap. Ardından sonucu daraltmak için \
tek bir soru sorabilirsin. Arka arkaya soru sorup kullanıcıyı \
sorguya çekme — en fazla bir soru, o da gerçekten gerekliyse.

3. Kısa yaz. 2-4 cümle. Ürünler kullanıcının ekranında kart \
olarak zaten görünüyor; fiyat, marka ve puanı tek tek yazıya \
dökme. Bunun yerine NEDEN bu ürünleri seçtiğini söyle.

4. Ürünleri madde madde listeleme. Kartlar o işi yapıyor. En \
fazla bir-iki ürünü adıyla öne çıkar ("keten olan günlük \
kullanım için daha rahat").

5. Dürüst ol. Katalog yaklaşık 730 parçalık seçili bir koleksiyon \
— her şey bulunmaz. Sonuç yoksa "bulamadım" de ve neyi \
değiştirebileceğini öner. Zayıf sonuçları güçlüymüş gibi sunma.

6. Bir kısıt gevşetildiyse (relaxed_filters) söyle. "Tam siyah \
bulamadım, koyu tonları getirdim" demek, sessizce yanlış ürün \
göstermekten iyidir.

7. Konu dışına çıkma. Moda, ürün, beden, kombin ve sipariş \
dışındaki konularda kibarca konuyu WishNN'e getir.

8. FİYAT — dikkatli ol, en çok burada yanılıyorsun.

8a. Bütçe duyduğunda max_price_try (veya min_price_try) \
GÖNDER. "3000 TL altında", "bütçem 5 bin", "2000-4000 arası", \
"en fazla 1500" hepsi bunu gerektirir. Bu sınır veritabanında \
uygulanır ve gevşetilmez; dönen ürünlerin hepsi sınırın \
içindedir.

8b. Bütçeyi SONRAKİ aramalara da taşı. Kullanıcı bir kez \
"bütçem 3000" dediyse, üç mesaj sonra "peki ayakkabı?" \
dediğinde de bütçe hâlâ 3000'dir.

8c. Sonuç boş dönerse bütçeyi kendi kafandan yükseltme. \
"Bu bütçede bulamadım" de. Arac cevabında \
cheapest_matching_try varsa onu söyle: "bu bütçede yok, en \
yakını X TL" demek dürüst ve yararlıdır.

8d. Bir ürüne "ucuz", "uygun fiyatlı" veya "pahalı" demeden \
önce fiyatını katalog aralığıyla karşılaştır (aşağıda \
veriliyor). Medyanın üstündeki bir ürüne "hesaplı" demek \
kullanıcıyı yanıltır.

8e. Fiyatları yazıya dökmek zorunda değilsin, kartlarda \
görünüyor. Ama bir fiyat yazarsan arac sonucundaki price_try \
değerini yaz; kendi hesabını yapma.

8f. RENK için de aynısı: kullanıcı renk söylediyse color \
parametresini gönder. Renk eşleştirmesi ürün görselinden \
ölçülen gerçek renkle yapılıyor; katalogdaki ürünlerin çoğu \
rengini metninde yazmıyor, o yüzden rengi sadece query \
metnine yazmak yetersiz kalır.

9. Düz metin yaz. Sohbet balonu markdown işlemiyor; başlık, \
madde işareti ve tablo kullanma. Bir marka adını öne \
çıkarmak istersen **çift yıldız** işe yarar, başka biçim \
yok.

HANGİ ÜRÜNLER GÖSTERİLECEK — ZORUNLU
Cevabının EN SON satırına hangi ürünlerin kart olarak
gösterileceğini yaz:

    [SHOW: B0B28SWXWP, B07HNTS427]

Kurallar:
- Yalnızca GERÇEKTEN önerdiğin ürünleri yaz.
- Arama sonucu alakasızsa veya "bulamadım" diyorsan
  [SHOW: none] yaz. Kullanıcıya bulamadığını söyleyip
  altına alakasız ürünler dizmek onu aldatmaktır.
- Kimlikler search_catalog'un döndürdüğü değerler olmalı.
- Bu satır kullanıcıya gösterilmiyor, arayüz onu ayıklıyor.
  Cevabında bu satırdan bahsetme.

BAĞLAMI HATIRLA
Kullanıcı "erkek" dedikten sonra "peki ayakkabı?" derse, bu \
erkek ayakkabısı demektir. Öğrendiğin cinsiyeti, rengi, bütçeyi \
ve tarzı sonraki aramalara da taşı — kullanıcıya tekrar sorma.

{_user_context(request.db, request.user)}{_price_context(request.db)}"""


# =========================================================
# ON ARAMA KARARI
# =========================================================
#
# Motor on aramayi CALISTIRIYOR; neyi arayacagina burada karar
# veriliyor cunku karar tamamen WishNN'e ait: query_engine
# sozlugunde sinyal var mi?
#
# NE ZAMAN YAPILMIYOR
# query_engine hicbir sinyal (cinsiyet/kategori/renk/niyet)
# bulamazsa atlaniyor. Olculdu:
#
#   "merhaba", "tesekkurler", "bu kumasi ne?"  -> sinyal yok
#   "peki ayakkabi?", "siyah olsun"            -> sinyal var
#
# Sinyalsiz mesajda arama yapmak bosa 2 saniye demekti.

PREFETCH_NOTE = """[SİSTEM NOTU — kullanıcı bu satırı görmüyor]
Kullanıcının son mesajı için katalog aramasını SENİN ADINA \
önceden yaptım; böylece bir tur beklemeden cevap yazabilirsin.
Arama parametreleri: {args}
Sonuç: {result}
Bu sonuçlar soruyu karşılıyorsa {tool} aracını TEKRAR ÇAĞIRMA, \
doğrudan cevabı yaz. Gösterilecek ürünleri [SHOW: ...] satırında \
bu sonuçlardan seç."""


def _previous_user_intents(messages):
    """
    Onceki kullanici mesajlarinin cozumlemeleri — en yeniden
    en eskiye.

    Tek tek analyze() cagirmak yerine tek yerde uretiliyor:
    cinsiyet, renk ve butce ayni listeden okunuyor.
    """

    for message in reversed(messages[:-1]):

        if message.role != "user":
            continue

        yield query_engine.analyze(message.content)


def _inherit_gender(messages) -> str | None:
    """
    Onceki kullanici mesajlarindan cinsiyeti devralir.

    Cinsiyet konusmanin basinda bir kez soylenip sonra
    tekrarlanmayan bir bilgi: "erkek giyim bakiyorum" ... "peki
    ayakkabi?". Ikinci mesajda cinsiyet yok ama kullanicinin
    kastettigi belli.

    Kategori DEVRALINMIYOR: o her mesajda degisiyor ("ayakkabi"
    onceki "gomlek"in yerine geciyor, ustune eklenmiyor).

    Bunu LLM'e sormuyoruz — sozluk isi ve query_engine bunu
    zaten yapiyor.
    """

    for intent in _previous_user_intents(messages):

        if intent.gender:
            return intent.gender

    return None


def _inherit_color(messages) -> str | None:
    """
    Onceki mesajlardan rengi devralir.

    NEDEN
    "siyah bir sneaker" ... "3000 TL altinda olanlari goster"
    dizisinde ikinci mesajda renk yok. On arama rengi
    kaybediyordu ve kullaniciya renk renk karisik sonuclar
    donuyordu — sikayetin en sik gorulen hali bu.

    NEDEN GUVENLI
    Kullanici rengi DEGISTIRDIGINDE yeni mesajda renk oluyor
    ve o kazaniyor (bu fonksiyon yalnizca son mesajda renk
    yoksa cagriliyor). Kaybedilen tek durum "renk fark
    etmez"e donmek; onu da model kendi araciyla asabiliyor.

    Sistem talimati modele de ayni seyi soyluyor: ogrendigin
    rengi sonraki aramalara tasi. Burasi o kuralin on arama
    yolundaki karsiligi.
    """

    for intent in _previous_user_intents(messages):

        if intent.colors:
            return intent.colors[0]

    return None


def _inherit_budget(messages):
    """
    Onceki mesajlardan butceyi devralir.

    Butce konusmada BIR KEZ soylenen ve sonuna kadar gecerli
    kalan bir kisit: "butcem 3000" dedikten sonra kullanici
    her mesajda tekrar etmiyor. Devralmazsak on arama her
    turda butcesiz calisir ve butce disi urunler doner —
    duzeltilen hatanin tam kendisi.
    """

    for intent in _previous_user_intents(messages):

        if intent.price.has_bounds:
            return intent.price

    return None


def _prefetch(ctx: ToolContext) -> Prefetch | None:
    """Son kullanici mesajinda arama sinyali varsa on arama tarifi."""

    messages = list(ctx.messages)

    if not messages:
        return None

    last = messages[-1]

    if last.role != "user":
        return None

    text = last.content.strip()

    if not text:
        return None

    intent = query_engine.analyze(text)

    signal_count = sum(
        len(values) for values in intent.facets.values()
    )

    has_signal = bool(
        intent.gender
        or intent.category
        or intent.colors
        or signal_count
        # Butce de bir arama sinyali: "3000 TL altinda
        # olanlari goster" cumlesinde baska hicbir sinyal
        # yok ama bu apacik bir daraltma istegi.
        or intent.price
    )

    if not has_signal:
        return None

    args: dict = {"query": text, "limit": 6}

    gender = intent.gender or _inherit_gender(messages)

    if gender:
        args["gender"] = gender

    # RENK: son mesajda varsa o, yoksa konusmadan devralinan.
    color = intent.colors[0] if intent.colors else _inherit_color(messages)

    if color:
        args["color"] = color

    # BUTCE: ayni mantik. Son mesajdaki sinir kazanir; yoksa
    # daha once soylenmis olan hala gecerlidir.
    budget = intent.price if intent.price.has_bounds else _inherit_budget(messages)

    if budget is not None:

        if budget.min_try is not None:
            args["min_price_try"] = budget.min_try

        if budget.max_try is not None:
            args["max_price_try"] = budget.max_try

    return Prefetch(tool="search_catalog", args=args, note=PREFETCH_NOTE)


# =========================================================
# DAYANAK DENETIMI
# =========================================================
#
# KATALOGDA OLMADIGI DOGRULANMIS MARKALAR.
#
# Kalin (**...**) denetimi bicime bagli: model yildiz
# kullanmazsa hicbir sey yakalanmaz (olculdu, sik oluyor). Bu
# liste bicimden bagimsiz calisiyor ve tam olarak GORULEN
# hatayi hedefliyor: yedek modele dusuldugunde asistan "Koton
# ve Trendyol sandaletleri" yazdi.
#
# Katalog Amazon kaynakli; bu markalarin hicbirinden urun YOK
# (SQL ile sayildi). Liste kisa ve kasitli: genel bir marka
# sozlugu tutmak degil, bilinen yanlisi yakalamak.
ABSENT_BRANDS = (
    "koton",
    "lc waikiki",
    "lcw",
    "trendyol",
    "defacto",
    "mavi jeans",
    "boyner",
    "zara",
    "h&m",
    "bershka",
)

GROUNDING = GroundingPolicy(
    fields=("brand", "title", "title_tr"),
    denylist=ABSENT_BRANDS,
    bold=True,
)


# =========================================================
# ASISTAN ORNEGI
# =========================================================
#
# Tek ornek, surec boyunca yasiyor. Sebep yalnizca hiz degil:
# model soguma listesi bu nesnenin icinde. Her istekte yeni bir
# asistan kurulsa "bu model tukendi" bilgisi kaybolur ve her
# mesaj tukenmis modeli yeniden denerdi.

_assistant: Assistant | None = None


def _close_transaction(request: ChatRequest) -> None:
    """
    Okuma transaction'ini LLM cagrisindan ONCE kapat.

    Araclar SELECT calistirdi ve SQLAlchemy transaction'i
    commit/rollback'e kadar acik tutuyor. Simdi araya bir LLM
    cagrisi giriyor: normalde 4-5 saniye, ama kuyrukta beklerken
    dakikalar surebiliyor. Neon o sirada
    idle_in_transaction_session_timeout ile baglantiyi dusuruyor.

    rollback, commit degil: yazma yapmadik, yalnizca
    transaction'i biraktik. Ihtiyacimiz olan urun alanlari
    _product_for_card ile zaten duz sozluge kopyalandi, yani
    expire olacak bir sey kalmadi.
    """

    request.db.rollback()


def get_assistant() -> Assistant:
    """Surec omurlu asistan ornegi (ilk cagrida kurulur)."""

    global _assistant

    if _assistant is None:

        # CHAT_MODEL, CHAT_CALL_TIMEOUT, CHAT_LAST_CALL_TIMEOUT
        # gibi mevcut env adlari korunuyor (bkz. .env.example).
        config = AssistantConfig.from_env(
            prefix="CHAT",
            card_id_field="product_id",
            max_cards=MAX_CARDS,
        )

        _assistant = Assistant(
            tools=TOOLS,
            system_prompt=_system_prompt,
            config=config,
            prefetch=_prefetch,
            before_model_call=_close_transaction,
            grounding=GROUNDING,
            directive_tag="SHOW",
            empty_reply=(
                "Bunu tam anlayamadım. Biraz daha açabilir misin?"
            ),
            empty_reply_with_cards=(
                "Sana birkaç seçenek buldum, aşağıda listeledim."
            ),
        )

        logger.info(
            "Sohbet asistani kuruldu: model zinciri=%s",
            ", ".join(config.chain()),
        )

    return _assistant


def _require_api_key() -> None:
    """
    Anahtari EN BASTA kontrol et.

    Motor da kontrol ediyor ama ancak ilk LLM cagrisinda; o ana
    kadar on arama calisip bir embedding cagrisi ve bir
    veritabani sorgusu harcanmis olurdu. Sonuc yine hata
    olacaksa masrafi hic yapmamak daha iyi.
    """

    if not (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("CHAT_API_KEY", "").strip()
    ):
        raise ConfigurationError(
            "GEMINI_API_KEY tanimli degil; sohbet asistani "
            "calisamaz."
        )


def _request(db: Session, user: User | None) -> ChatRequest:
    return ChatRequest(db=db, user=user, rate=get_usd_try_rate())


# =========================================================
# UCUN CAGIRDIGI YUZ
# =========================================================

def run_chat(
    db: Session,
    messages: list,
    user: User | None = None,
) -> dict:
    """
    Bir sohbet turunu calistirir.

    Doner: {"reply": str, "products": [dict], "tool_calls": [str],
            "model": str | None, "ungrounded": [str],
            "usage": dict}

    products duz sozluklerdir (ORM nesnesi degil): arac cagrisi
    sirasinda okunup kopyalandilar, boylece transaction LLM
    cagrisindan once kapatilabiliyor. Serilestirmeyi cagiran
    taraf ChatProduct semasiyla yapiyor.

    Firlatabilecegi hatalar main.py'de tek tek karsilaniyor:
        QuotaExceeded       -> 429 (bekle)
        ModelTimeout        -> 504 (yavas)
        ConfigurationError  -> 503 (anahtar yok)
    """

    _require_api_key()

    turn = get_assistant().run(
        messages,
        request=_request(db, user),
    )

    return {
        "reply": turn.reply,
        "products": turn.cards,
        "tool_calls": turn.tool_calls,
        "model": turn.model,
        "ungrounded": turn.ungrounded,
        "usage": turn.usage.as_dict(),
    }


def stream_chat(
    db: Session,
    messages: list,
    user: User | None = None,
) -> Iterator[dict]:
    """
    Ayni turu AKIS halinde calistirir.

    NEDEN
    Olculen gecikmenin buyuk kismi ilk harfe kadar geciyor:
    kullanici 5-9 saniye bos ekrana bakiyor. Akista ilk kelime
    ~1-2 saniyede dusuyor. Yapilan is ayni, teslim bicimi
    farkli.

    Uretilen sozlukler:
        {"type": "tool",  "name": "search_catalog"}
        {"type": "text",  "delta": "..."}
        {"type": "done",  "reply": ..., "products": [...], ...}

    NOT: arayuz (frontend/app.js) su an /api/chat ucunu, yani
    senkron yolu kullaniyor. Bu fonksiyon akisa gecis icin hazir
    duruyor; ikisi ayni motoru ve ayni araclari kullaniyor.
    """

    _require_api_key()

    request = _request(db, user)

    for event in get_assistant().stream(messages, request=request):

        if event.type == "text":
            yield {"type": "text", "delta": event.text}

        elif event.type == "tool":
            yield {"type": "tool", "name": event.tool}

        elif event.type == "done" and event.turn is not None:

            yield {
                "type": "done",
                "reply": event.turn.reply,
                "products": event.turn.cards,
                "tool_calls": event.turn.tool_calls,
                "model": event.turn.model,
                "ungrounded": event.turn.ungrounded,
                "usage": event.turn.usage.as_dict(),
            }
