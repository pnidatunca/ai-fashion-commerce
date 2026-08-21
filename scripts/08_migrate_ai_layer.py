"""
AI kisisellestirme katmani icin sema gocu.

Yaptiklari:

  1. user_preferences        tablosunu olusturur
  2. product_style_scores    tablosunu olusturur
  3. user_interactions'a match_score ve style_archetype
     kolonlarini ekler
  4. product_id'yi NULL kabul eder hale getirir
     (INITIAL_STYLE olaylari urune bagli degil)
  5. interaction_type CHECK kisitini INITIAL_STYLE ile
     genisletir
  6. Urun kimliginin yalnizca INITIAL_STYLE'da bos
     olabilecegi kisitini ekler

Neden create_all yetmiyor: create_all yalnizca EKSIK
TABLOLARI olusturur. Var olan bir tabloya kolon eklemez,
kisit degistirmez. Bunlar acik ALTER TABLE gerektirir.

Script idempotenttir: birden fazla kez kosturulabilir.
Hicbir veri silmez.

Kullanim:
    python scripts/08_migrate_ai_layer.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import inspect, text

from app.database import Base, engine
from app.models import (  # noqa: F401
    ProductStyleScore,
    UserInteraction,
    UserPreference,
    WishlistItem,
)


# Sirasi onemli: kolonlar kisitlardan once eklenmeli.
STEPS = [
    (
        "match_score kolonu",
        """
        ALTER TABLE user_interactions
        ADD COLUMN IF NOT EXISTS match_score DOUBLE PRECISION
        """,
    ),
    (
        "style_archetype kolonu",
        """
        ALTER TABLE user_interactions
        ADD COLUMN IF NOT EXISTS style_archetype VARCHAR(32)
        """,
    ),
    (
        "interaction_type genisletildi (24 karakter)",
        """
        ALTER TABLE user_interactions
        ALTER COLUMN interaction_type TYPE VARCHAR(24)
        """,
    ),
    (
        "product_id NULL kabul ediyor",
        """
        ALTER TABLE user_interactions
        ALTER COLUMN product_id DROP NOT NULL
        """,
    ),
    (
        "eski tur kisiti kaldirildi",
        """
        ALTER TABLE user_interactions
        DROP CONSTRAINT IF EXISTS ck_user_interactions_type
        """,
    ),
    (
        "yeni tur kisiti (INITIAL_STYLE dahil)",
        """
        ALTER TABLE user_interactions
        ADD CONSTRAINT ck_user_interactions_type
        CHECK (interaction_type IN
            ('VIEW', 'LIKE', 'UNLIKE', 'DISLIKE', 'INITIAL_STYLE'))
        """,
    ),
    (
        "urun kimligi zorunlulugu kisiti",
        """
        ALTER TABLE user_interactions
        DROP CONSTRAINT IF EXISTS ck_user_interactions_product_required
        """,
    ),
    (
        "urun kimligi zorunlulugu eklendi",
        """
        ALTER TABLE user_interactions
        ADD CONSTRAINT ck_user_interactions_product_required
        CHECK (interaction_type = 'INITIAL_STYLE'
               OR product_id IS NOT NULL)
        """,
    ),
]


def create_new_tables():
    print("\n" + "-" * 70)
    print("1. YENI TABLOLAR")
    print("-" * 70)

    inspector = inspect(engine)
    before = set(inspector.get_table_names())

    for attempt in range(3):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except Exception as error:
            if attempt < 2:
                print(f"  deneme {attempt + 1} basarisiz: {error}")
                time.sleep(5)
            else:
                raise

    after = set(inspect(engine).get_table_names())
    created = sorted(after - before)

    if created:
        print("  olusturuldu:", ", ".join(created))
    else:
        print("  yeni tablo yok (hepsi mevcut)")


def run_alters():
    print("\n" + "-" * 70)
    print("2. user_interactions GUNCELLEMELERI")
    print("-" * 70)

    for label, statement in STEPS:
        with engine.begin() as connection:
            try:
                connection.execute(text(statement))
                print(f"  ok    {label}")
            except Exception as error:
                message = str(error).split("\n")[0][:90]
                print(f"  atla  {label}  ({message})")


def verify():
    print("\n" + "-" * 70)
    print("3. DOGRULAMA")
    print("-" * 70)

    with engine.connect() as connection:

        print("\nuser_interactions kolonlari:")
        rows = connection.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'user_interactions'
            ORDER BY ordinal_position
        """))
        for row in rows:
            print(f"    {row[0]:<18} {row[1]:<26} null={row[2]}")

        print("\nCHECK kisitlari:")
        rows = connection.execute(text("""
            SELECT tc.constraint_name, cc.check_clause
            FROM information_schema.table_constraints tc
            JOIN information_schema.check_constraints cc
              ON cc.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'user_interactions'
              AND tc.constraint_type = 'CHECK'
              AND cc.check_clause NOT LIKE '%IS NOT NULL'
        """))
        for row in rows:
            print(f"    {row[0]}")
            print(f"      {row[1][:110]}")

        for table in ("user_preferences", "product_style_scores"):
            print(f"\n{table} kolonlari:")
            rows = connection.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = :t
                ORDER BY ordinal_position
            """), {"t": table})
            for row in rows:
                print(f"    {row[0]:<24} {row[1]:<26} null={row[2]}")


def test_constraints():
    """Kisitlarin gercekten calistigini dogrula."""

    print("\n" + "-" * 70)
    print("4. KISIT TESTLERI")
    print("-" * 70)

    with engine.connect() as connection:

        user_id = connection.execute(
            text("SELECT id FROM users LIMIT 1")
        ).scalar()

        product_id = connection.execute(
            text("SELECT product_id FROM products LIMIT 1")
        ).scalar()

        if user_id is None or product_id is None:
            print("  kullanici/urun yok, testler atlaniyor")
            return

        cases = [
            (
                "INITIAL_STYLE product_id olmadan kabul edilmeli",
                "INSERT INTO user_interactions "
                "(user_id, interaction_type, style_archetype) "
                "VALUES (:u, 'INITIAL_STYLE', 'minimalist')",
                True,
            ),
            (
                "LIKE product_id olmadan REDDEDILMELI",
                "INSERT INTO user_interactions "
                "(user_id, interaction_type) "
                "VALUES (:u, 'LIKE')",
                False,
            ),
            (
                "gecersiz tur REDDEDILMELI",
                "INSERT INTO user_interactions "
                "(user_id, product_id, interaction_type) "
                "VALUES (:u, :p, 'SEVDIM')",
                False,
            ),
            (
                "match_score ile LIKE kabul edilmeli",
                "INSERT INTO user_interactions "
                "(user_id, product_id, interaction_type, match_score, "
                "style_archetype) "
                "VALUES (:u, :p, 'LIKE', 84.2, 'classic')",
                True,
            ),
            (
                "gecersiz arketip (preferences) REDDEDILMELI",
                "INSERT INTO user_preferences "
                "(user_id, style_archetype) VALUES (:u, 'gotik')",
                False,
            ),
        ]

        for label, statement, should_pass in cases:
            savepoint = connection.begin_nested()
            try:
                connection.execute(
                    text(statement),
                    {"u": user_id, "p": product_id},
                )
                result = True
            except Exception:
                result = False
            finally:
                savepoint.rollback()

            mark = "ok   " if result == should_pass else "HATA "
            print(f"  {mark} {label}")

        connection.rollback()


def main():
    print("=" * 70)
    print("AI KATMANI SEMA GOCU")
    print("=" * 70)

    create_new_tables()
    run_alters()
    verify()
    test_constraints()

    print("\nHazir. Sirada:")
    print("    python scripts/09_compute_style_scores.py")


if __name__ == "__main__":
    main()
