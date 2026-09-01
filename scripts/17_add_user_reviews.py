"""
reviews tablosuna kullanici yorumu alanlarini ekler.

Veri setinden gelen yorumlar (user_id NULL) ile sitede
yazilan yorumlar ayni tabloda duruyor; bkz. models.Review
icindeki aciklama.

Bu script IDEMPOTENTTIR: her adim "IF NOT EXISTS" ile
korunuyor, var olan veriye dokunmuyor.

Kullanim:
    python scripts/17_add_user_reviews.py
"""

import sys
import time
from pathlib import Path

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import engine


STEPS = [
    (
        "user_id kolonu",
        """
        ALTER TABLE reviews
        ADD COLUMN IF NOT EXISTS user_id UUID
        """,
    ),
    (
        "created_at kolonu",
        """
        ALTER TABLE reviews
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ
        """,
    ),
    (
        "user_id -> users.id yabanci anahtari",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'reviews_user_id_fkey'
            ) THEN
                ALTER TABLE reviews
                ADD CONSTRAINT reviews_user_id_fkey
                FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE;
            END IF;
        END $$
        """,
    ),
    (
        "user_id indeksi",
        """
        CREATE INDEX IF NOT EXISTS ix_reviews_user_id
        ON reviews (user_id)
        """,
    ),
    (
        # Bir kullanici bir urune bir yorum. NULL'lar
        # (veri seti yorumlari) bu kisittan etkilenmiyor.
        "kullanici+urun unique kisiti",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_review_user_product'
            ) THEN
                ALTER TABLE reviews
                ADD CONSTRAINT uq_review_user_product
                UNIQUE (user_id, product_id);
            END IF;
        END $$
        """,
    ),
]


def main():
    print("=" * 70)
    print("KULLANICI YORUMLARI MIGRATION")
    print("=" * 70)

    for label, sql in STEPS:

        # Neon soguk baslangicta ilk baglantiyi reddedebilir.
        for attempt in range(3):
            try:
                with engine.begin() as connection:
                    connection.execute(text(sql))
                print(f"  OK  {label}")
                break

            except Exception as error:
                if attempt < 2:
                    print(
                        f"  .. {label} basarisiz ({error}). "
                        "5 saniye sonra tekrar..."
                    )
                    time.sleep(5)
                else:
                    raise

    print("\n" + "-" * 70)
    print("DOGRULAMA")
    print("-" * 70)

    inspector = inspect(engine)

    columns = {c["name"]: c for c in inspector.get_columns("reviews")}

    for name in ("user_id", "created_at"):
        column = columns.get(name)
        if column:
            nullable = "NULL" if column["nullable"] else "NOT NULL"
            print(f"  reviews.{name:<12} {str(column['type']):<16} {nullable}")
        else:
            print(f"  reviews.{name:<12} EKSIK")

    print("\n  unique kisitlar:")
    for constraint in inspector.get_unique_constraints("reviews"):
        print(f"    {constraint['name']}: {constraint['column_names']}")

    print("\n  yabanci anahtarlar:")
    for key in inspector.get_foreign_keys("reviews"):
        print(
            f"    {key['constrained_columns']} -> "
            f"{key['referred_table']}.{key['referred_columns']}"
        )

    with engine.begin() as connection:
        total = connection.execute(
            text("SELECT COUNT(*) FROM reviews")
        ).scalar()

        dataset = connection.execute(
            text("SELECT COUNT(*) FROM reviews WHERE user_id IS NULL")
        ).scalar()

    print(f"\n  toplam yorum: {total}  (veri setinden: {dataset})")
    print("\nHazir.")


if __name__ == "__main__":
    main()
