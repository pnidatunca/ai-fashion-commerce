"""
USD/TRY kuru — TEK KAYNAK.

NEDEN AYRI MODUL
Kur eskiden assistant.py icindeydi ve yalnizca sohbet
kullaniyordu. Simdi arama motoru da fiyat filtresi uyguluyor
(bkz. search_service._apply_price): kullanici "3000 TL altinda"
dediginde katalogdaki USD fiyat TL'ye cevrilmek zorunda.

Kur iki yerde ayri ayri hesaplanirsa arada kacinilmaz bir
tutarsizlik olur: arama 3000 TL siniriyla filtreler, kart
baska bir kurdan 3100 TL yazar. Kullanici icin bu, sistemin
yalan soylemesidir. Bu yuzden kur tek yerden geliyor ve tek
onbellek paylasiliyor.

search_service bu modulu import edebiliyor ama assistant'i
edemez (assistant zaten search_service'i import ediyor —
dongusel olurdu). Kuru asagi tasimanin bir sebebi de bu.
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


# Servis dusuk oldugunda kullanilacak son cikis. Guncel
# olmayabilir ama "fiyat gosterilemedi" demekten iyidir.
FALLBACK_USD_TRY = 47.88

# Kur gun icinde alisveris kararini etkileyecek kadar
# oynamiyor; arama gecikmesine her istekte bir HTTP turu
# eklemek anlamsiz.
RATE_TTL_SECONDS = 6 * 60 * 60

_cache: dict = {
    "value": None,
    "fetched_at": 0.0,
}


def get_usd_try_rate() -> float:
    """
    USD/TRY kuru — 6 saat onbellekli.

    Dis servis dusuk olsa bile arama ve sohbet CALISMAYA DEVAM
    ETMELI; hata durumunda son bilinen deger, o da yoksa sabit
    bir yedek doner.
    """

    now = time.monotonic()

    cached = _cache["value"]

    if (
        cached is not None
        and now - _cache["fetched_at"] < RATE_TTL_SECONDS
    ):
        return cached

    try:
        response = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=5,
        )

        rate = float(response.json()["rates"]["TRY"])

        if rate <= 0:
            raise ValueError("Kur sifir veya negatif.")

        _cache["value"] = rate
        _cache["fetched_at"] = now

        return rate

    except Exception as error:

        logger.warning("USD/TRY kuru alinamadi: %s", error)

        # Eski deger varsa bayat haliyle bile yedekten iyidir.
        return cached if cached is not None else FALLBACK_USD_TRY


def to_try(usd_value, rate: float | None = None) -> float | None:
    """USD -> TL. Deger yoksa None (sifir DEGIL)."""

    if usd_value is None:
        return None

    if rate is None:
        rate = get_usd_try_rate()

    return round(float(usd_value) * rate, 2)


def to_usd(try_value, rate: float | None = None) -> float | None:
    """
    TL -> USD.

    NEDEN GEREKLI
    Fiyat filtresi SQL'de calisiyor ve katalog fiyatlari USD.
    "price * kur <= 3000" yazmak yerine siniri BIR KEZ USD'ye
    ceviriyoruz: hem indeks kullanilabilir kaliyor hem de her
    satirda carpma yapilmiyor.
    """

    if try_value is None:
        return None

    if rate is None:
        rate = get_usd_try_rate()

    if rate <= 0:
        return None

    return float(try_value) / rate
