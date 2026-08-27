"""
wardrobe_looks ve wardrobe_look_items tablolarini olusturur.

Bu script IDEMPOTENTTIR: create_all yalnizca eksik tabloyu
olusturur, var olan tablolara dokunmaz ve veri silmez.

Kullanim:
    python scripts/16_create_wardrobe_tables.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import inspect

from app.database import Base, engine

# noqa: F401 — import edilmeleri SART: Base.metadata'ya
# ancak boyle kaydoluyorlar, yoksa create_all onlari gormez.
from app.models import WardrobeLook, WardrobeLookItem  # noqa: F401


TARGET_TABLES = ("wardrobe_looks", "wardrobe_look_items")


def main():
    print("=" * 70)
    print("GARDIROP TABLOLARI")
    print("=" * 70)

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    for table in TARGET_TABLES:
        if table in existing:
            print(f"\n{table} zaten var, sema kontrol ediliyor...")
        else:
            print(f"\nOlusturulacak: {table}")

    # Neon soguk baslangicta ilk baglantiyi reddedebilir.
    for attempt in range(3):
        try:
            Base.metadata.create_all(bind=engine)
            print("\ncreate_all tamamlandi.")
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

    for table in TARGET_TABLES:

        columns = inspector.get_columns(table)
        indexes = inspector.get_indexes(table)
        uniques = inspector.get_unique_constraints(table)
        foreign_keys = inspector.get_foreign_keys(table)

        print(f"\n{table}")
        for column in columns:
            nullable = "NULL" if column["nullable"] else "NOT NULL"
            print(f"    {column['name']:<20} {str(column['type']):<28} {nullable}")

        print("  indeksler:")
        for index in indexes:
            unique = " (UNIQUE)" if index["unique"] else ""
            print(f"    {index['name']}: {index['column_names']}{unique}")

        print("  unique kisitlar:")
        for constraint in uniques:
            print(f"    {constraint['name']}: {constraint['column_names']}")

        print("  yabanci anahtarlar:")
        for key in foreign_keys:
            print(
                f"    {key['constrained_columns']} -> "
                f"{key['referred_table']}.{key['referred_columns']}"
            )

    print("\nHazir.")


if __name__ == "__main__":
    main()
