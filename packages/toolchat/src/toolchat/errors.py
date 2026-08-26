"""
Hata tipleri ve hata siniflandirma.

NEDEN AYRI TIPLER
Cagiran taraf (bir HTTP ucu, bir CLI) her hataya ayni cevabi
veremez:

    QuotaExceeded  -> ortada ariza YOK, beklemek gerekiyor (429)
    ModelTimeout   -> servis yavas, tekrar denenebilir  (504)
    ConfigurationError -> anahtar/ayar eksik, kendi kendine
                          duzelmez (503)

Hepsi tek bir Exception olsa arayuz "asistana ulasilamadi"
demek zorunda kalirdi; ucu de yanlis teshis.

DIS TIPLERDEN MIRAS
ModelTimeout ayni zamanda TimeoutError, ConfigurationError ayni
zamanda RuntimeError. Boylece bu modulu bilmeyen bir kod
(`except TimeoutError`) yine calisir; modulu tanimak zorunlu
degil.
"""

from __future__ import annotations

import re


class AssistantError(Exception):
    """Modulun butun hatalarinin ortak atasi."""


class ConfigurationError(AssistantError, RuntimeError):
    """
    Eksik veya gecersiz yapilandirma: API anahtari yok, model
    listesi bos, negatif zaman siniri.

    RuntimeError'dan da miras aliyor: mevcut kodlar bu durumu
    genellikle RuntimeError olarak yakaliyor.
    """


class QuotaExceeded(AssistantError):
    """
    Zincirdeki BUTUN modeller kota siniri (HTTP 429) verdi.

    retry_after: servisin bildirdigi bekleme suresi (saniye).
    Bildirmediyse None; o zaman cagiran taraf genel bir mesaj
    yazar.
    """

    def __init__(
        self,
        retry_after: int | None = None,
        tried: tuple[str, ...] = (),
    ):
        self.retry_after = retry_after
        self.tried = tuple(tried)

        message = "Butun modellerin kotasi doldu"

        if tried:
            message += ": " + ", ".join(tried)

        super().__init__(message + ".")


class ModelTimeout(AssistantError, TimeoutError):
    """
    Zincirdeki butun modeller zaman siniri icinde cevap
    vermedi.

    Kota hatasindan AYRI tutuluyor: burada kota bitmemis,
    servis yavas. Kullaniciya "kotan doldu" demek yanlis
    teshis olurdu.
    """

    def __init__(self, message: str, tried: tuple[str, ...] = ()):
        self.tried = tuple(tried)
        super().__init__(message)


class ToolError(AssistantError):
    """
    Arac uygulamasi kendi icinde bir sorun bildirmek isterse.

    Zorunlu degil: arac dogrudan {"error": "..."} da
    donebilir. Fark yok, ikisi de modele hata olarak gider.
    """


# =========================================================
# SINIFLANDIRMA
# =========================================================
#
# SDK hatalari tek bir tipte gelmiyor: kimi APIError, kimi
# httpx'in kendi timeout'u, kimi duz ValueError. Tipe gore
# ayirmak kirilgan oldugu icin hem kod alanina hem metne
# bakiyoruz.

_RETRY_PATTERN = re.compile(r"retry in ([0-9.]+)s", re.IGNORECASE)


def retry_seconds(error: Exception) -> int | None:
    """429 govdesindeki 'Please retry in 48.2s' degerini okur."""

    match = _RETRY_PATTERN.search(str(error))

    if match:
        return int(float(match.group(1))) + 1

    return None


def is_quota_error(error: Exception) -> bool:

    if getattr(error, "code", None) == 429:
        return True

    text = str(error)

    return "RESOURCE_EXHAUSTED" in text or "429" in text


def is_timeout_error(error: Exception) -> bool:
    """
    Zaman asimi mi?

    UC AYRI KAYNAK var, hepsi ayni anlama geliyor:

    1. Bizim istemci sinirimiz — SDK altta httpx kullaniyor ve
       timeout'u kendi tipiyle firlatiyor. Tip ADINA bakiyoruz;
       httpx'i buraya import etmekten daha az bagimlilik.

    2. Sunucunun kendi siniri — 504 DEADLINE_EXCEEDED.

    3. 503 UNAVAILABLE — "yuksek talep". Yapilacak sey ayni:
       siradaki modeli dene.
    """

    if "timeout" in type(error).__name__.lower():
        return True

    if getattr(error, "code", None) in (503, 504):
        return True

    lowered = str(error).lower()

    return (
        "timed out" in lowered
        or "deadline_exceeded" in lowered
        or "deadline expired" in lowered
        or "503 unavailable" in lowered
        or "504 deadline" in lowered
    )
