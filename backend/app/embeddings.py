import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"

load_dotenv(ENV_FILE)


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