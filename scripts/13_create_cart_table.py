"""
cart_items tablosunu olusturur.

Bu script IDEMPOTENTTIR: create_all yalnizca eksik tabloyu
olusturur, var olan tablolara dokunmaz ve veri silmez.

Kullanim:
    python scripts/13_create_cart_table.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import inspect

from app.database import Base, engine
from app.models import CartItem  # noqa: F401


TARGET_TABLE = "cart_items"


def main():
    print("=" * 70)
    print("SEPET TABLOSU")
    print("=" * 70)

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    if TARGET_TABLE in existing:
        print(f"\n{TARGET_TABLE} zaten var, sema kontrol ediliyor...")
    else:
        print(f"\nOlusturulacak: {TARGET_TABLE}")

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

    inspector = inspect(engine)

    print("\n" + "-" * 70)
    print("DOGRULAMA")
    print("-" * 70)

    columns = inspector.get_columns(TARGET_TABLE)
    indexes = inspector.get_indexes(TARGET_TABLE)

    print(f"\n{TARGET_TABLE}")
    for column in columns:
        nullable = "NULL" if column["nullable"] else "NOT NULL"
        print(f"    {column['name']:<20} {str(column['type']):<28} {nullable}")

    print("  indeksler:")
    for index in indexes:
        unique = " (UNIQUE)" if index["unique"] else ""
        print(f"    {index['name']}: {index['column_names']}{unique}")

    print("\nHazir.")


if __name__ == "__main__":
    main()
