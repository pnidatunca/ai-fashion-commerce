import logging
import os
from collections import OrderedDict
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"

load_dotenv(ENV_FILE)

logger = logging.getLogger(__name__)


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 1536


def generate_embedding(text: str) -> list[float]:
    cleaned_text = text.strip()

    if not cleaned_text:
        raise ValueError("Embedding metni bos olamaz.")

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY bulunamadi. "
            "Repo kokundeki .env dosyasini kontrol et."
        )

    client = genai.Client(api_key=api_key)

    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=cleaned_text,
        config=types.EmbedContentConfig(
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )

    if not response.embeddings:
        raise RuntimeError(
            "Gemini embedding API bos cevap dondurdu."
        )

    embedding = response.embeddings[0].values

    if embedding is None:
        raise RuntimeError(
            "Embedding degeri alinamadi."
        )

    embedding = list(embedding)

    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            "Beklenmeyen embedding boyutu: "
            f"{len(embedding)}. "
            f"Beklenen: {EMBEDDING_DIMENSIONS}."
        )

    return embedding

# =========================================================
# SORGU EMBEDDING ONBELLEGI
# =========================================================
#
# Her arama bir Gemini API cagrisi demek: hem para hem
# gecikme. Ayni sorgu tekrar geliyor mu? Evet, surekli:
#
#   - kullanici sonsuz akista asagi kaydiriyor (sayfa 2, 3)
#   - "kadin elbise" gibi populer sorgular tekrar ediyor
#   - gevsetme merdiveni ayni vektoru tekrar kullaniyor
#
# Bu yuzden kucuk bir LRU onbellek tutuyoruz. Vektor
# deterministik oldugu icin onbellege almak davranisi
# degistirmiyor.
#
# Neden process ici ve kucuk: sunucu yeniden baslarsa
# kaybolmasi sorun degil, tekrar uretilir. Redis eklemek
# bu boyutta gereksiz karmasiklik.

QUERY_CACHE_SIZE = 256

_query_cache: OrderedDict[str, list[float]] = OrderedDict()


def embed_query(text: str) -> list[float] | None:
    """
    Arama sorgusu icin embedding uretir.

    generate_embedding'den iki farki var:

    1. ONBELLEKLI — ayni sorgu ikinci kez API'ye gitmiyor.

    2. HATA FIRLATMIYOR — None donuyor. Arama ucu, embedding
       uretilemediginde 500 vermek yerine kelime eslesmesine
       dusuyor (bkz. search_service._run_stage). Arama
       sitenin ana islevi; API anahtari eksik oldugu icin
       tamamen calismamasi kabul edilemez.
    """

    cleaned = str(text or "").strip()

    if not cleaned:
        return None

    cached = _query_cache.get(cleaned)

    if cached is not None:
        _query_cache.move_to_end(cleaned)
        return cached

    try:
        vector = generate_embedding(cleaned)
    except Exception as error:
        # Gerekce loglaniyor ama istek dusurulmuyor.
        logger.warning(
            "Sorgu embedding uretilemedi (%s): %s",
            cleaned[:80],
            error,
        )
        return None

    _query_cache[cleaned] = vector
    _query_cache.move_to_end(cleaned)

    while len(_query_cache) > QUERY_CACHE_SIZE:
        _query_cache.popitem(last=False)

    return vector


def query_cache_stats() -> dict:
    """Tanilama icin: onbellekte kac sorgu var."""

    return {
        "size": len(_query_cache),
        "capacity": QUERY_CACHE_SIZE,
    }
