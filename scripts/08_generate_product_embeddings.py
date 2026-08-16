import sys
import time
from pathlib import Path

from sqlalchemy import func, select


# =========================================================
# BACKEND IMPORT PATH
# =========================================================

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.embeddings import EMBEDDING_DIMENSIONS, generate_embedding
from app.models import Product


# =========================================================
# CONFIG
# =========================================================

BATCH_SIZE = 10

# Gemini API'yi gereksiz yere zorlamamak için
# her ürün arasında kısa bekleme.
REQUEST_DELAY_SECONDS = 1.0

# Bir ürün embedding isteği başarısız olursa
# kaç kez yeniden denenecek?
MAX_RETRIES = 5

# Exponential backoff başlangıcı:
# 5 → 10 → 20 → 40 → 60 saniye
INITIAL_RETRY_DELAY = 5


# =========================================================
# EMBEDDING WITH RETRY
# =========================================================

def generate_embedding_with_retry(
    text: str,
    product_id: str,
) -> list[float]:

    retry_delay = INITIAL_RETRY_DELAY

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            embedding = generate_embedding(text)

            if len(embedding) != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    f"Embedding boyutu hatali: "
                    f"{len(embedding)}"
                )

            return embedding

        except Exception as error:

            print()
            print(
                f"[WARNING] {product_id} embedding hatasi."
            )

            print(
                f"Deneme {attempt}/{MAX_RETRIES}"
            )

            print(
                f"Hata: {error}"
            )

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"{product_id} icin embedding "
                    f"{MAX_RETRIES} denemeden sonra "
                    "uretiletmedi."
                ) from error

            print(
                f"{retry_delay} saniye sonra "
                "tekrar denenecek..."
            )

            time.sleep(retry_delay)

            retry_delay = min(
                retry_delay * 2,
                60,
            )

    raise RuntimeError(
        "Beklenmeyen retry durumu."
    )


# =========================================================
# DATABASE COUNTS
# =========================================================

def get_counts(db):

    total = db.scalar(
        select(func.count())
        .select_from(Product)
        .where(
            Product.search_text.is_not(None),
            func.length(
                func.trim(Product.search_text)
            ) > 0,
        )
    )

    embedded = db.scalar(
        select(func.count())
        .select_from(Product)
        .where(
            Product.search_text.is_not(None),
            func.length(
                func.trim(Product.search_text)
            ) > 0,
            Product.search_embedding.is_not(None),
        )
    )

    total = total or 0
    embedded = embedded or 0

    return total, embedded


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 70)
    print("PRODUCT EMBEDDING GENERATOR")
    print("=" * 70)

    db = SessionLocal()

    try:

        total, already_embedded = get_counts(db)

        remaining = total - already_embedded

        print(f"Total products     : {total}")
        print(f"Already embedded   : {already_embedded}")
        print(f"Remaining          : {remaining}")
        print(f"Embedding dimension: {EMBEDDING_DIMENSIONS}")
        print(f"Batch size         : {BATCH_SIZE}")
        print("=" * 70)

        if remaining <= 0:

            print(
                "Tum urunler zaten embed edilmis."
            )

            return

        processed_this_run = 0

        while True:

            # ---------------------------------------------
            # Sadece embedding'i olmayan ürünleri getir.
            # ---------------------------------------------

            statement = (
                select(Product)
                .where(
                    Product.search_text.is_not(None),
                    func.length(
                        func.trim(Product.search_text)
                    ) > 0,
                    Product.search_embedding.is_(None),
                )
                .order_by(Product.product_id)
                .limit(BATCH_SIZE)
            )

            products = list(
                db.scalars(statement).all()
            )

            if not products:
                break

            print()
            print(
                f"Yeni batch: {len(products)} urun"
            )

            print("-" * 70)

            # ---------------------------------------------
            # BATCH
            # ---------------------------------------------

            for product in products:

                current_number = (
                    already_embedded
                    + processed_this_run
                    + 1
                )

                percentage = (
                    current_number / total * 100
                    if total
                    else 0
                )

                print(
                    f"[{current_number}/{total}] "
                    f"({percentage:.1f}%) "
                    f"{product.product_id}"
                )

                embedding = (
                    generate_embedding_with_retry(
                        product.search_text,
                        product.product_id,
                    )
                )

                product.search_embedding = embedding

                processed_this_run += 1

                time.sleep(
                    REQUEST_DELAY_SECONDS
                )

            # ---------------------------------------------
            # Her batch tamamlandığında DB'ye yaz.
            # ---------------------------------------------

            db.commit()

            print(
                f"Batch kaydedildi. "
                f"Bu calismada: "
                f"{processed_this_run} urun."
            )

        # ---------------------------------------------
        # FINAL CHECK
        # ---------------------------------------------

        final_total, final_embedded = get_counts(db)

        print()
        print("=" * 70)
        print("EMBEDDING GENERATION COMPLETED")
        print("=" * 70)

        print(
            f"Bu calismada embed edilen: "
            f"{processed_this_run}"
        )

        print(
            f"Database total           : "
            f"{final_total}"
        )

        print(
            f"Database embedded        : "
            f"{final_embedded}"
        )

        print(
            f"Database remaining       : "
            f"{final_total - final_embedded}"
        )

        if final_total == final_embedded:

            print()
            print(
                "Tum urun embeddingleri hazir."
            )

    except KeyboardInterrupt:

        db.rollback()

        print()
        print("=" * 70)
        print("ISLEM KULLANICI TARAFINDAN DURDURULDU")
        print("=" * 70)

        print(
            "Mevcut batch rollback edildi."
        )

        print(
            "Daha once commit edilen batch'ler korunuyor."
        )

        print(
            "Script tekrar calistirildiginda "
            "kaldigi yerden devam eder."
        )

    except Exception as error:

        db.rollback()

        print()
        print("=" * 70)
        print("EMBEDDING GENERATION FAILED")
        print("=" * 70)

        print(
            f"Hata: {error}"
        )

        print()
        print(
            "Mevcut batch rollback edildi."
        )

        print(
            "Daha once kaydedilmis embeddingler korunuyor."
        )

        print(
            "Sorun cozuldugunde scripti tekrar "
            "calistirabilirsin."
        )

        raise

    finally:

        db.close()


if __name__ == "__main__":
    main()