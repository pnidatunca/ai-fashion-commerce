"""
user_interactions ve wishlist_items tablolarini olusturur.

Bu script IDEMPOTENTTIR: create_all yalnizca eksik tablolari
olusturur, var olan products / reviews / users tablolarina
dokunmaz ve veri silmez.

Kullanim:
    python scripts/06_create_feedback_tables.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import inspect, text

from app.database import Base, engine
from app.models import UserInteraction, WishlistItem  # noqa: F401


TARGET_TABLES = ["user_interactions", "wishlist_items"]


def main():
    print("=" * 70)
    print("FEEDBACK TABLOLARI")
    print("=" * 70)

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    print("\nMevcut tablolar:", ", ".join(sorted(existing)) or "(yok)")

    missing = [t for t in TARGET_TABLES if t not in existing]

    if not missing:
        print("\nHer iki tablo da zaten var. Yeni sema kontrol ediliyor...")
    else:
        print("\nOlusturulacak:", ", ".join(missing))

    # Neon soguk baslangicta ilk baglantiyi reddedebilir.
    for attempt in range(3):
        try:
            Base.metadata.create_all(bind=engine)
            print("create_all tamamlandi.")
            break

        except Exception as error:
            if attempt < 2:
                print(
                    f"Deneme {attempt + 1} basarisiz: {error}. "
                    "5 saniye sonra tekrar denenecek..."
                )
                time.sleep(5)
            else:
                raise

    # Dogrulama
    inspector = inspect(engine)

    print("\n" + "-" * 70)
    print("DOGRULAMA")
    print("-" * 70)

    for table in TARGET_TABLES:
        columns = inspector.get_columns(table)
        indexes = inspector.get_indexes(table)

        print(f"\n{table}")
        for column in columns:
            nullable = "NULL" if column["nullable"] else "NOT NULL"
            print(f"    {column['name']:<20} {str(column['type']):<28} {nullable}")

        print("  indeksler:")
        for index in indexes:
            unique = " (UNIQUE)" if index["unique"] else ""
            print(f"    {index['name']}: {index['column_names']}{unique}")

    # CHECK kisitini dogrula: gecersiz tur reddedilmeli
    print("\n" + "-" * 70)
    print("CHECK KISIT TESTI")
    print("-" * 70)

    with engine.connect() as connection:
        user_id = connection.execute(
            text("SELECT id FROM users LIMIT 1")
        ).scalar()

        product_id = connection.execute(
            text("SELECT product_id FROM products LIMIT 1")
        ).scalar()

        if user_id is None or product_id is None:
            print("Test icin kullanici/urun yok, atlaniyor.")
            return

        # SAVEPOINT: SELECT'ler zaten bir transaction actigi icin
        # begin() yerine begin_nested() kullaniyoruz.
        savepoint = connection.begin_nested()

        try:
            connection.execute(
                text(
                    "INSERT INTO user_interactions "
                    "(user_id, product_id, interaction_type) "
                    "VALUES (:u, :p, 'HATALI_TUR')"
                ),
                {"u": user_id, "p": product_id},
            )
            print("SORUN: gecersiz interaction_type kabul edildi!")

        except Exception:
            print("OK: gecersiz interaction_type CHECK ile reddedildi.")

        finally:
            savepoint.rollback()
            connection.rollback()

    print("\nHazir.")


if __name__ == "__main__":
    main()
