import sys
from pathlib import Path

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.embeddings import generate_embedding
from app.models import Product


TOP_K = 10


def main():
    print("=" * 70)
    print("SEMANTIC SEARCH TEST")
    print("=" * 70)

    query = (
        " ".join(sys.argv[1:]).strip()
        if len(sys.argv) > 1
        else "lightweight breathable shirt for summer"
    )

    print(f"Query: {query}")
    print()

    query_embedding = generate_embedding(query)

    db = SessionLocal()

    try:
        distance = (
            Product.search_embedding
            .cosine_distance(query_embedding)
            .label("distance")
        )

        statement = (
            select(
                Product,
                distance,
            )
            .where(
                Product.search_embedding.is_not(None)
            )
            .order_by(distance)
            .limit(TOP_K)
        )

        results = db.execute(statement).all()

        if not results:
            print("Sonuc bulunamadi.")
            return

        print(f"Top {len(results)} semantic results:")
        print("=" * 70)

        for index, (product, cosine_distance) in enumerate(
            results,
            start=1,
        ):
            similarity = 1 - float(cosine_distance)

            print()
            print(f"{index}. {product.title}")
            print(f"   ID         : {product.product_id}")
            print(f"   Brand      : {product.brand}")
            print(f"   Category   : {product.category}")
            print(f"   Price      : ${product.price}")
            print(f"   Similarity : {similarity:.4f}")

    finally:
        db.close()


if __name__ == "__main__":
    main()