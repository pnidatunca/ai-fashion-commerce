"""
Sepetsiz akis + agirlik gocu.

Yaptiklari:

  1. user_interactions.weight  kolonunu ekler
  2. QUICK_BUY turunu CHECK kisitina ekler
  3. user_preferences.avoid_brands / avoid_categories ekler
  4. Mevcut satirlarin agirliklarini geriye donuk doldurur

Neden weight satirda saklaniyor: agirlik esleme tablosu
zamanla degisir. Satirin uzerinde o an kullanilan agirlik
yazili olmazsa, alti ay sonra egitim verisini yeniden
cikarttiginda gecmis olaylara BUGUNUN agirliklari uygulanir
ve model farkli bir gecmis ogrenir.

Script idempotenttir. Hicbir veri silmez.

Kullanim:
    python scripts/11_migrate_cartless.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text

from app.database import engine
from app.models import INTERACTION_TYPES, INTERACTION_WEIGHTS


TYPE_SQL_LIST = ", ".join(f"'{t}'" for t in INTERACTION_TYPES)


STEPS = [
    (
        "user_interactions.weight kolonu",
        """
        ALTER TABLE user_interactions
        ADD COLUMN IF NOT EXISTS weight DOUBLE PRECISION
        NOT NULL DEFAULT 0
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
        "yeni tur kisiti (QUICK_BUY dahil)",
        f"""
        ALTER TABLE user_interactions
        ADD CONSTRAINT ck_user_interactions_type
        CHECK (interaction_type IN ({TYPE_SQL_LIST}))
        """,
    ),
    (
        "user_preferences.avoid_brands kolonu",
        """
        ALTER TABLE user_preferences
        ADD COLUMN IF NOT EXISTS avoid_brands JSONB
        """,
    ),
    (
        "user_preferences.avoid_categories kolonu",
        """
        ALTER TABLE user_preferences
        ADD COLUMN IF NOT EXISTS avoid_categories JSONB
        """,
    ),
]


def backfill_weights():
    """
    Mevcut satirlarin agirligini doldurur.

    weight = 0 olan satirlar henuz agirliklandirilmamis
    demektir (kolon yeni eklendi). Agirligi 0 OLMASI GEREKEN
    turler (INITIAL_STYLE) icin bu zararsiz.
    """

    print("\n" + "-" * 70)
    print("AGIRLIK GERIYE DONUK DOLDURMA")
    print("-" * 70)

    total = 0

    for interaction_type, weight in INTERACTION_WEIGHTS.items():

        if weight == 0:
            continue

        with engine.begin() as connection:
            result = connection.execute(
                text("""
                    UPDATE user_interactions
                    SET weight = :w
                    WHERE interaction_type = :t
                      AND weight = 0
                """),
                {"w": weight, "t": interaction_type},
            )

            count = result.rowcount or 0
            total += count

            if count:
                print(f"  {interaction_type:<14} {count:>5} satir -> {weight}")

    if not total:
        print("  doldurulacak satir yok")


def run_steps():
    print("\n" + "-" * 70)
    print("SEMA GUNCELLEMELERI")
    print("-" * 70)

    for label, statement in STEPS:
        with engine.begin() as connection:
            try:
                connection.execute(text(statement))
                print(f"  ok    {label}")
            except Exception as error:
                message = str(error).split("\n")[0][:80]
                print(f"  atla  {label}  ({message})")


def verify():
    print("\n" + "-" * 70)
    print("DOGRULAMA")
    print("-" * 70)

    with engine.connect() as connection:

        rows = connection.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'user_interactions'
              AND column_name IN ('weight', 'match_score', 'selected_styles')
            ORDER BY column_name
        """))
        print("\nuser_interactions:")
        for row in rows:
            print(f"    {row[0]:<16} {row[1]:<20} null={row[2]}")

        rows = connection.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'user_preferences'
              AND column_name LIKE 'avoid%'
            ORDER BY column_name
        """))
        print("\nuser_preferences:")
        found = list(rows)
        for row in found:
            print(f"    {row[0]:<18} {row[1]}")
        if not found:
            print("    (avoid kolonlari YOK)")

        clause = connection.execute(text("""
            SELECT cc.check_clause
            FROM information_schema.table_constraints tc
            JOIN information_schema.check_constraints cc
              ON cc.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'user_interactions'
              AND tc.constraint_name = 'ck_user_interactions_type'
        """)).scalar()

        print("\ntur kisiti:")
        print(f"    {(clause or 'YOK')[:120]}")

        print("\nagirlik dagilimi:")
        rows = connection.execute(text("""
            SELECT interaction_type, weight, COUNT(*)
            FROM user_interactions
            GROUP BY interaction_type, weight
            ORDER BY interaction_type
        """))
        found = list(rows)
        for row in found:
            print(f"    {row[0]:<14} w={row[1]:<6} {row[2]} satir")
        if not found:
            print("    (kayit yok)")


def test_constraints():
    print("\n" + "-" * 70)
    print("KISIT TESTLERI")
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
                "QUICK_BUY kabul edilmeli",
                "INSERT INTO user_interactions "
                "(user_id, product_id, interaction_type, weight) "
                "VALUES (:u, :p, 'QUICK_BUY', 2.0)",
                True,
            ),
            (
                "gecersiz tur REDDEDILMELI",
                "INSERT INTO user_interactions "
                "(user_id, product_id, interaction_type) "
                "VALUES (:u, :p, 'SATIN_ALDIM')",
                False,
            ),
            (
                "QUICK_BUY product_id olmadan REDDEDILMELI",
                "INSERT INTO user_interactions "
                "(user_id, interaction_type) "
                "VALUES (:u, 'QUICK_BUY')",
                False,
            ),
            (
                "negatif agirlik kabul edilmeli",
                "INSERT INTO user_interactions "
                "(user_id, product_id, interaction_type, weight) "
                "VALUES (:u, :p, 'DISLIKE', -1.0)",
                True,
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
    print("SEPETSIZ AKIS + AGIRLIK GOCU")
    print("=" * 70)

    run_steps()
    backfill_weights()
    verify()
    test_constraints()

    print("\nHazir.")


if __name__ == "__main__":
    main()
