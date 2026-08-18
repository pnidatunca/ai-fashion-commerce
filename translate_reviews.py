import os
import json
import time

import psycopg
from dotenv import load_dotenv
from google import genai


# =========================================================
# AYARLAR
# =========================================================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = "gemini-2.5-flash-lite"

TEST_LIMIT = 10
BATCH_SIZE = 10


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL bulunamadı.")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY bulunamadı.")


# =========================================================
# GEMINI
# =========================================================

client = genai.Client(api_key=GEMINI_API_KEY)


# =========================================================
# REVIEWLARI GETİR
# =========================================================

def get_reviews(conn, limit=10):
    query = """
        SELECT
            review_id,
            review_title,
            review_text
        FROM reviews
        WHERE
            (review_title_tr IS NULL OR review_title_tr = '')
            OR
            (review_text_tr IS NULL OR review_text_tr = '')
        ORDER BY review_id
        LIMIT %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (limit,))
        return cur.fetchall()


# =========================================================
# GEMINI İLE ÇEVİR
# =========================================================

def translate_batch(reviews):
    reviews_for_ai = []

    for review_id, title, text in reviews:
        reviews_for_ai.append({
            "review_id": str(review_id),
            "review_title": title or "",
            "review_text": text or ""
        })

    prompt = f"""
You are a professional English-to-Turkish translator.

Translate the following product reviews from English to natural,
clear Turkish.

IMPORTANT RULES:

1. Preserve the original meaning.
2. Do not add information.
3. Do not remove important information.
4. Keep product names, brand names and model numbers unchanged.
5. Translate the review title naturally.
6. Translate the review text naturally.
7. Return ONLY valid JSON.
8. Do not use Markdown.
9. Keep the same review_id.

Expected JSON format:

[
  {{
    "review_id": "123",
    "review_title_tr": "Türkçe başlık",
    "review_text_tr": "Türkçe yorum"
  }}
]

Reviews:

{json.dumps(reviews_for_ai, ensure_ascii=False, indent=2)}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "temperature": 0.2,
            "response_mime_type": "application/json"
        }
    )

    result_text = response.text.strip()

    return json.loads(result_text)


# =========================================================
# DATABASE'E KAYDET
# =========================================================

def save_translations(conn, translations):
    query = """
        UPDATE reviews
        SET
            review_title_tr = %s,
            review_text_tr = %s
        WHERE review_id = %s
    """

    saved = 0

    with conn.cursor() as cur:
        for item in translations:
            review_id = item["review_id"]
            title_tr = item.get("review_title_tr", "")
            text_tr = item.get("review_text_tr", "")

            cur.execute(
                query,
                (
                    title_tr,
                    text_tr,
                    review_id
                )
            )

            saved += cur.rowcount

    conn.commit()

    return saved


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)
    print("REVIEW TRANSLATION")
    print("=" * 60)

    print(f"Model      : {MODEL_NAME}")
    print(f"Test limit : {TEST_LIMIT}")
    print(f"Batch size : {BATCH_SIZE}")
    print()

    with psycopg.connect(DATABASE_URL) as conn:

        reviews = get_reviews(
            conn,
            limit=TEST_LIMIT
        )

        if not reviews:
            print("Çevrilecek review bulunamadı.")
            return

        print(f"{len(reviews)} review bulundu.")
        print()

        try:
            print("Gemini'ye gönderiliyor...")

            translations = translate_batch(reviews)

            print(
                f"Gemini'den {len(translations)} çeviri alındı."
            )

            saved = save_translations(
                conn,
                translations
            )

            print(
                f"✓ {saved} review veritabanına kaydedildi."
            )

        except Exception as e:

            print()
            print("❌ HATA:")
            print(e)
            print()

            print(
                "Bu batch veritabanına kaydedilmedi."
            )

    print()
    print("=" * 60)
    print("TEST TAMAMLANDI")
    print("=" * 60)


if __name__ == "__main__":
    main()