import sys
from pathlib import Path

from sqlalchemy import text


# Backend import path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import engine


def main():
    print("=" * 70)
    print("SEMANTIC SEARCH DATABASE SETUP")
    print("=" * 70)

    with engine.begin() as connection:
        connection.execute(
            text("CREATE EXTENSION IF NOT EXISTS vector")
        )

        connection.execute(
            text(
                """
                ALTER TABLE products
                ADD COLUMN IF NOT EXISTS search_embedding vector(1536)
                """
            )
        )

    print("Vector extension is enabled.")
    print("products.search_embedding is ready.")


if __name__ == "__main__":
    main()
