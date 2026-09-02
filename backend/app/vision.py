"""
GORSELLE ARAMA — fotograftaki urunu arama cumlesine cevirir.

    kullanici fotografi
        -> Gemini (multimodal)
        -> "kadin siyah midi cicek desenli elbise"
        -> query_engine.analyze -> embed_query -> search_service

Yani YENI BIR ARAMA MOTORU YOK. Uretilen cumle, kullanicinin
elle yazdigi cumleyle tamamen ayni yoldan geciyor: sozlukler,
esanlamli genisletme, olculmus renk eslestirme, fiyat ve kalip
filtreleri hepsi calisiyor.


NEDEN GORSELI DOGRUDAN VEKTORLEMIYORUZ
--------------------------------------
Katalog vektorleri gemini-embedding-001 ile URUN METNINDEN
uretildi (products.search_embedding). O model METIN-ONLY.
Gorseli baska bir modelle vektorlesek bile iki vektor AYNI
UZAYDA olmadigi icin karsilastirilamaz — cikan skor
anlamsiz olur.

Gercek gorsel-gorsel arama istenirse yol ayri: CLIP benzeri
bir modelle products'a IKINCI bir vektor kolonu eklemek
(728 gorsel icin bir kez hesaplanir). O zaman "tam bu gorsel
tarz" cok daha iyi bulunur ama Turkce metin sorgulari o
uzayda calismaz; iki ayri arama yolu bakmak gerekir. Once
bu yol, gerekirse o yukseltme.


GORSEL SAKLANMIYOR
------------------
Baytlar istek boyunca bellekte duruyor, cevap donunce
gidiyor. Diske de veritabanina da yazilmiyor.

Sebep: saklamanin karsiligi yok. Arama yalnizca URETILEN
CUMLEYE ihtiyac duyuyor; fotografin kendisi bir daha
kullanilmiyor. Saklasaydik KVKK yukumlulugu, depolama,
silme akisi ve sizinti riski gelirdi — hicbirinin karsiligi
olmadan.


BOYUT SINIRI ISTEMCIDE DE VAR
-----------------------------
Arayuz gorseli gondermeden once canvas ile kucultuyor
(uzun kenar ~1024px). Buradaki sinir ikinci savunma hatti:
istemci atlatilabilir, sunucu kendini korumali.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import time

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


# Ayni model zinciri mantigi degil: gorsel tarifi tek atislik
# ve kisa. Kota dolarsa kullaniciya soylenip birakiliyor.
VISION_MODEL = os.getenv("VISION_MODEL", "gemini-3.5-flash")

# Sunucu tarafi ust sinir (ham bayt). Istemci zaten ~1024px'e
# kucultuyor ve tipik sonuc 150-400 KB.
MAX_IMAGE_BYTES = 6 * 1024 * 1024

ALLOWED_MIME = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
)

# Uretilen cumlenin ust siniri — arama kutusuna sigacak
# uzunlukta olmali.
MAX_QUERY_CHARS = 160


# DIKKAT: Gemini 3.x DUSUNME token'lari da bu butceden
# harciyor. Ilk olcumde 120 verilmisti ve gorunur cikti
# "erkek siyah" gibi YARIM kaliyordu; fizibilite testi
# ozelligin calismadigini sanmisti. Olcum hatasiydi.
MAX_OUTPUT_TOKENS = 2048


PROMPT = """Bu fotoğraftaki GİYSİ, AYAKKABI veya AKSESUARI bir moda \
kataloğunda aratmak için tek satırlık Türkçe bir arama cümlesi yaz.

Kurallar:
- YALNIZCA arama cümlesini yaz. Açıklama, tırnak, madde işareti yok.
- Şunları içersin: cinsiyet (anlaşılıyorsa), ürün türü, renk, desen, \
kesim ve kumaş izlenimi.
- MARKA ADI YAZMA. Logo görsen bile yazma — katalogda o marka \
olmayabilir ve arama boşa çıkar.
- Kişiyi, yüzü, pozu, arka planı veya mekânı TARİF ETME. Yalnızca ürün.
- Fotoğrafta birden fazla giysi varsa EN BELİRGİN olanı seç.
- Fotoğrafta giysi/ayakkabı YOKSA tek kelime yaz: YOK

Örnek çıktı: kadın siyah midi boy çiçek desenli kolsuz yazlık elbise"""


class VisionError(Exception):
    """Gorsel islenemedi — kullaniciya gosterilecek sebep."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


class NoGarmentFound(VisionError):
    """
    Fotografta giysi yok.

    Ayri bir tip: bu bir HATA degil, gecerli bir sonuc.
    Kullaniciya "kedi fotografi yuklemissin" demek, "gorsel
    islenemedi" demekten cok daha yardimci.
    """

    def __init__(self):
        super().__init__(
            "Fotoğrafta bir giysi ya da ayakkabı göremedim. "
            "Ürünün net göründüğü bir fotoğraf dener misin?",
            422,
        )


def decode_image(data_url_or_b64: str) -> tuple[bytes, str]:
    """
    Istemciden gelen base64'u baytlara cevirir.

    Iki bicim kabul ediliyor:
        data:image/jpeg;base64,/9j/4AAQ...
        /9j/4AAQ...

    Ilki canvas.toDataURL()'in dogal ciktisi; ikincisi elle
    ayiklanmis hali. Ikisini de kabul etmek arayuzun hangi
    yolu sectigine bagimliligi kaldiriyor.
    """

    raw = (data_url_or_b64 or "").strip()

    if not raw:
        raise VisionError("Görsel boş.")

    mime = "image/jpeg"

    if raw.startswith("data:"):

        try:
            header, raw = raw.split(",", 1)
        except ValueError:
            raise VisionError("Görsel biçimi okunamadı.")

        # data:image/png;base64
        if ";" in header and ":" in header:
            mime = header.split(":", 1)[1].split(";", 1)[0].strip()

    if mime not in ALLOWED_MIME:
        raise VisionError(
            "Bu görsel biçimi desteklenmiyor (%s). "
            "JPEG, PNG veya WEBP gönder." % mime
        )

    try:
        image = base64.b64decode(raw, validate=True)

    except (binascii.Error, ValueError):
        raise VisionError("Görsel çözümlenemedi.")

    if not image:
        raise VisionError("Görsel boş.")

    if len(image) > MAX_IMAGE_BYTES:
        raise VisionError(
            "Görsel çok büyük (%d MB). En fazla %d MB."
            % (
                len(image) // (1024 * 1024),
                MAX_IMAGE_BYTES // (1024 * 1024),
            )
        )

    return image, mime


def describe(image: bytes, mime: str) -> dict:
    """
    Gorseli arama cumlesine cevirir.

    Doner: {"query": str, "seconds": float, "model": str}
    Giysi yoksa NoGarmentFound firlatir.
    """

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise VisionError(
            "Görselle arama şu anda kullanılamıyor.", 503
        )

    client = genai.Client(api_key=api_key)

    started = time.time()

    try:
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=image, mime_type=mime),
                types.Part(text=PROMPT),
            ],
            config=types.GenerateContentConfig(
                # Dusuk sicaklik: ayni fotograf ayni cumleyi
                # uretsin. Kullanici tekrar denediginde farkli
                # sonuc almasi guveni sarsardi.
                temperature=0.2,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            ),
        )

    except Exception as error:

        text_error = str(error)

        if "RESOURCE_EXHAUSTED" in text_error or "429" in text_error:
            raise VisionError(
                "Görsel arama dakikalık istek sınırına takıldı. "
                "Birazdan tekrar dene.",
                429,
            )

        logger.exception("Gorsel tarif edilemedi")

        raise VisionError(
            "Görsel işlenemedi. Birazdan tekrar dene.", 502
        )

    sentence = (response.text or "").strip()

    # Model bazen tirnak icinde donduruyor.
    sentence = sentence.strip('"').strip("'").strip()

    # Tek satira indir: cok satirli cevap arama kutusuna
    # yapistirilinca bozuk gorunur.
    sentence = " ".join(sentence.split())

    if not sentence or sentence.upper().startswith("YOK"):
        raise NoGarmentFound()

    return {
        "query": sentence[:MAX_QUERY_CHARS],
        "seconds": round(time.time() - started, 2),
        "model": VISION_MODEL,
    }


def describe_base64(data_url_or_b64: str) -> dict:
    """decode + describe — ucun cagirdigi tek fonksiyon."""

    image, mime = decode_image(data_url_or_b64)

    result = describe(image, mime)

    result["bytes"] = len(image)

    return result
