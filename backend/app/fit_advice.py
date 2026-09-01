"""
BEDEN/KALIP TAVSIYESI — yorumlardan cikarilan sinyali okur.

Veriyi scripts/17_extract_fit_signals.py uretiyor; bu modul
yalnizca OKUYOR ve kullaniciya gosterilecek metne ceviriyor.

    script  : 6327 yorumu tarar, oylari sayar, karari yazar
    burasi  : kolonu okur, "Kalıbı büyük" cumlesini kurar


KOLONLAR NEDEN ORM MODELINE EKLENMEDI
-------------------------------------
color_match.py'deki gerekcenin AYNISI. Kolonlari products
tablosuna script ekliyor (ALTER TABLE). Product modeline
yazsaydik ve script henuz calismamis olsaydi SQLAlchemy her
urun sorgusunda o kolonlari SELECT ederdi ve butun site
(urun listesi, arama, sepet) "column does not exist" ile
duserdi.

Yani opsiyonel bir zenginlestirme, zorunlu bir bagimlilik
haline gelirdi. Bu yuzden ham SQL ile okuyoruz ve yalnizca
is_ready() dogruladiktan sonra. Veri yoksa arayuzde kalip
kutusu HIC gorunmuyor; hicbir sey kirilmiyor.


NEDEN OY SAYILARI DA TASINIYOR
------------------------------
Arayuz "Alıcılar büyük geldiğini söylüyor" derken kac kisinin
soyledigini de gosteriyor. Gerekcesiz bir iddia, kullanicinin
dogrulayamadigi bir iddiadir; 5 yorumdan 5'i demek ile 3
yorumdan 2'si demek ayni guveni tasimaz ve kullanici bu
ayrimi kendisi yapabilmeli.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Kullaniciya gosterilecek metin BACKEND'DE uretiliyor.
#
# Neden frontend'de degil: esikler, oy sayilari ve karar
# mantigi burada. Metni orada kursaydik ayni kural iki yerde
# yasardi ve biri gun gelip guncellenmezdi (query_engine
# sozluklerinin frontend'den backend'e tasinma gerekcesinin
# aynisi — bkz. docs/AI_SEARCH.md).
VERDICT_LABELS: dict[str, tuple[str, str]] = {
    "small": (
        "Kalıbı küçük",
        "Alıcılar bu ürünün küçük geldiğini söylüyor. "
        "Normal bedeninizin bir beden üstünü tercih edin.",
    ),
    "true": (
        "Kalıbına uygun",
        "Alıcılar bedeninin doğru olduğunu söylüyor. "
        "Normalde giydiğiniz bedeni alabilirsiniz.",
    ),
    "large": (
        "Kalıbı büyük",
        "Alıcılar bu ürünün büyük geldiğini söylüyor. "
        "Normal bedeninizin bir beden altını tercih edin.",
    ),
}


# Modele (LLM) verilen kisa hal. Kullanici metninden ayri
# tutuluyor: asistan cumleyi kendi kurmali, hazir cumleyi
# kopyalamamali.
VERDICT_FOR_MODEL = {
    "small": "kalibi kucuk geliyor, bir beden buyuk onerilir",
    "true": "kalibina uygun, normal beden alinabilir",
    "large": "kalibi buyuk geliyor, bir beden kucuk onerilir",
}


_READY_TTL_SECONDS = 300

_ready_cache: dict = {"value": None, "checked_at": 0.0}


def is_ready(db: Session) -> bool:
    """
    Kalip verisi kullanilabilir mi?

    Iki sey kontrol ediliyor: kolon var mi ve icinde veri var
    mi. Onbellekli — her urun isteginde
    information_schema'ya gitmek anlamsiz.
    """

    now = time.monotonic()

    cached = _ready_cache["value"]

    if (
        cached is not None
        and now - _ready_cache["checked_at"] < _READY_TTL_SECONDS
    ):
        return bool(cached)

    ready = False

    try:
        has_column = db.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'products'
                  AND column_name = 'fit_verdict'
                """
            )
        ).scalar()

        if has_column:

            filled = int(
                db.execute(
                    text(
                        "SELECT count(*) FROM products "
                        "WHERE fit_verdict IS NOT NULL"
                    )
                ).scalar()
                or 0
            )

            ready = filled > 0

    except Exception as error:

        # Kalip tavsiyesi bir ek; okunamiyorsa urun sayfasi
        # yine acilmali.
        logger.warning("Kalip verisi kontrol edilemedi: %s", error)

        ready = False

    _ready_cache["value"] = ready
    _ready_cache["checked_at"] = now

    return ready


def reset_ready_cache() -> None:
    """Script calistiktan sonra sunucuyu beklemeden tazelemek icin."""

    _ready_cache["value"] = None
    _ready_cache["checked_at"] = 0.0


def _build(row) -> dict | None:
    """DB satirindan arayuzun bekledigi sozlugu kurar."""

    if row is None:
        return None

    verdict = row.fit_verdict

    if not verdict or verdict not in VERDICT_LABELS:
        return None

    title, advice = VERDICT_LABELS[verdict]

    small = int(row.fit_small_votes or 0)
    true_fit = int(row.fit_true_votes or 0)
    large = int(row.fit_large_votes or 0)

    total = small + true_fit + large

    agree = {"small": small, "true": true_fit, "large": large}[verdict]

    return {
        "verdict": verdict,
        "title": title,
        "advice": advice,
        "confidence": float(row.fit_confidence or 0.0),
        # Gerekce: "5 yorumdan 5'i" cumlesi buradan kuruluyor.
        "agree_count": agree,
        "total_count": total,
        "votes": {
            "small": small,
            "true": true_fit,
            "large": large,
        },
    }


def get(db: Session, product_id: str) -> dict | None:
    """
    Tek urunun kalip tavsiyesi. Karar yoksa None.

    None donmesi normaldir ve arayuzde hicbir sey
    gosterilmemesi anlamina gelir: 728 urunun 526'sinda karar
    verilebilecek kadar kanit yok (olculdu). Bos bir iddia
    yerine hicbir iddia.
    """

    if not product_id or not is_ready(db):
        return None

    try:
        row = db.execute(
            text(
                """
                SELECT fit_verdict, fit_confidence,
                       fit_small_votes, fit_true_votes,
                       fit_large_votes
                FROM products
                WHERE product_id = :pid
                """
            ),
            {"pid": product_id},
        ).one_or_none()

    except Exception as error:

        logger.warning(
            "Kalip verisi okunamadi (%s): %s", product_id, error
        )

        return None

    return _build(row)


def for_model(db: Session, product_id: str) -> str | None:
    """
    Asistanin arac cevabina girecek kisa hal.

    Kullaniciya gosterilen cumle DEGIL: model kendi cumlesini
    kurmali. Oy sayisi da veriliyor ki asistan abartmasin
    ("herkes buyuk diyor" demek yerine "5 yorumdan 5'i").
    """

    data = get(db, product_id)

    if data is None:
        return None

    return "%s (%d/%d yorum)" % (
        VERDICT_FOR_MODEL[data["verdict"]],
        data["agree_count"],
        data["total_count"],
    )
