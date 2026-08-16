import sys
from pathlib import Path

from sqlalchemy import func, select


# Backend import path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.embeddings import EMBEDDING_DIMENSIONS, generate_embedding
from app.models import Product


def main():
    print("=" * 70)
    print("SINGLE PRODUCT EMBEDDING TEST")
    print("=" * 70)

    db = SessionLocal()

    try:
        statement = (
            select(Product)
            .where(
                Product.search_text.is_not(None),
                func.length(func.trim(Product.search_text)) > 0,
            )
            .order_by(Product.product_id)
            .limit(1)
        )

        product = db.scalar(statement)

        if product is None:
            raise RuntimeError(
                "search_text alani dolu bir urun bulunamadi."
            )

        product_id = product.product_id
        embedding = generate_embedding(product.search_text)
        embedding_dimension = len(embedding)

        if embedding_dimension != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                "Embedding boyutu dogrulanamadi: "
                f"{embedding_dimension}."
            )

        product.search_embedding = embedding
        db.commit()

        stored_embedding = db.scalar(
            select(Product.search_embedding).where(
                Product.product_id == product_id
            )
        )

        if (
            stored_embedding is None
            or len(stored_embedding) != EMBEDDING_DIMENSIONS
        ):
            raise RuntimeError(
                "Embedding veritabanina kaydedilemedi."
            )

        print(f"Product ID        : {product_id}")
        print(f"Embedding dimension: {embedding_dimension}")
        print("Database save     : successful")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
