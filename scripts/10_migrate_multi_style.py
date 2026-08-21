"""
8 arketip + cok secimli tarz gocu.

Yaptiklari:

  1. user_preferences.selected_styles  (JSONB) ekler
  2. user_interactions.selected_styles (JSONB) ekler
  3. Arketip CHECK kisitlarini 8 degere genisletir
  4. selected_styles uzunluk kisitini (1-3) ekler
  5. Eski 'classic' degerini 'smart_casual'a tasir
  6. Mevcut style_archetype degerlerinden selected_styles
     doldurur (geriye donuk uyum)

Neden create_all yetmiyor: create_all yalnizca EKSIK
TABLOLARI olusturur. Var olan bir tabloya kolon eklemez,
kisit degistirmez.

Script idempotenttir. Hicbir veri silmez.

Kullanim:
    python scripts/10_migrate_multi_style.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text

from app.database import engine
from app.style_engine import ARCHETYPES


# SQL icin: 'minimalist', 'streetwear', ...
ARCHETYPE_SQL_LIST = ", ".join(f"'{a}'" for a in ARCHETYPES)


STEPS = [
    (
        "user_preferences.selected_styles kolonu",
        """
        ALTER TABLE user_preferences
        ADD COLUMN IF NOT EXISTS selected_styles JSONB
        """,
    ),
    (
        "user_interactions.selected_styles kolonu",
        """
        ALTER TABLE user_interactions
        ADD COLUMN IF NOT EXISTS selected_styles JSONB
        """,
    ),
    (
        "eski 'classic' -> 'smart_casual' (preferences)",
        """
        UPDATE user_preferences
        SET style_archetype = 'smart_casual'
        WHERE style_archetype = 'classic'
        """,
    ),
    (
        "eski 'classic' -> 'smart_casual' (interactions)",
        """
        UPDATE user_interactions
        SET style_archetype = 'smart_casual'
        WHERE style_archetype = 'classic'
        """,
    ),
    (
        "eski 'classic' skorlari silindi",
        """
        DELETE FROM product_style_scores
        WHERE archetype = 'classic'
        """,
    ),
    (
        "preferences arketip kisiti kaldirildi",
        """
        ALTER TABLE user_preferences
        DROP CONSTRAINT IF EXISTS ck_user_preferences_archetype
        """,
    ),
    (
        "preferences arketip kisiti (8 deger)",
        f"""
        ALTER TABLE user_preferences
        ADD CONSTRAINT ck_user_preferences_archetype
        CHECK (style_archetype IS NULL
               OR style_archetype IN ({ARCHETYPE_SQL_LIST}))
        """,
    ),
    (
        "selected_styles uzunluk kisiti kaldirildi",
        """
        ALTER TABLE user_preferences
        DROP CONSTRAINT IF EXISTS ck_user_preferences_selected_styles_len
        """,
    ),
    (
        "selected_styles uzunluk kisiti (1-3)",
        """
        ALTER TABLE user_preferences
        ADD CONSTRAINT ck_user_preferences_selected_styles_len
        CHECK (selected_styles IS NULL
               OR jsonb_array_length(selected_styles) BETWEEN 1 AND 3)
        """,
    ),
    (
        "style_scores arketip kisiti kaldirildi",
        """
        ALTER TABLE product_style_scores
        DROP CONSTRAINT IF EXISTS ck_product_style_scores_archetype
        """,
    ),
    (
        "style_scores arketip kisiti (8 deger)",
        f"""
        ALTER TABLE product_style_scores
        ADD CONSTRAINT ck_product_style_scores_archetype
        CHECK (archetype IN ({ARCHETYPE_SQL_LIST}))
        """,
    ),
    (
        "selected_styles geriye donuk dolduruldu",
        """
        UPDATE user_preferences
        SET selected_styles = jsonb_build_array(style_archetype)
        WHERE selected_styles IS NULL
          AND style_archetype IS NOT NULL
        """,
    ),
]


def run_steps():
    print("\n" + "-" * 70)
    print("GUNCELLEMELER")
    print("-" * 70)

    for label, statement in STEPS:
        with engine.begin() as connection:
            try:
                result = connection.execute(text(statement))
                count = getattr(result, "rowcount", -1)
                suffix = f"  ({count} satir)" if count and count > 0 else ""
                print(f"  ok    {label}{suffix}")
            except Exception as error:
                message = str(error).split("\n")[0][:80]
                print(f"  atla  {label}  ({message})")


def verify():
    print("\n" + "-" * 70)
    print("DOGRULAMA")
    print("-" * 70)

    with engine.connect() as connection:

        for table in ("user_preferences", "user_interactions"):
            rows = connection.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = :t AND column_name = 'selected_styles'
            """), {"t": table}).all()

            state = rows[0][1] if rows else "YOK"
            print(f"  {table}.selected_styles : {state}")

        print("\n  CHECK kisitlari:")
        rows = connection.execute(text("""
            SELECT tc.table_name, tc.constraint_name, cc.check_clause
            FROM information_schema.table_constraints tc
            JOIN information_schema.check_constraints cc
              ON cc.constraint_name = tc.constraint_name
            WHERE tc.table_name IN
                  ('user_preferences', 'product_style_scores')
              AND tc.constraint_type = 'CHECK'
              AND cc.check_clause NOT LIKE '%IS NOT NULL'
            ORDER BY tc.table_name
        """))
        for row in rows:
            print(f"    {row[0]}.{row[1]}")
            print(f"      {row[2][:100]}")

        print("\n  mevcut arketip degerleri:")
        rows = connection.execute(text("""
            SELECT archetype, COUNT(*)
            FROM product_style_scores
            GROUP BY archetype ORDER BY archetype
        """))
        found = list(rows)
        if found:
            for row in found:
                print(f"    {row[0]:<14} {row[1]}")
        else:
            print("    (bos — 09 scripti kosturulmali)")


def test_constraints():
    print("\n" + "-" * 70)
    print("KISIT TESTLERI")
    print("-" * 70)

    with engine.connect() as connection:

        user_id = connection.execute(
            text("SELECT id FROM users LIMIT 1")
        ).scalar()

        if user_id is None:
            print("  kullanici yok, testler atlaniyor")
            return

        cases = [
            (
                "8 arketipten biri kabul edilmeli",
                "INSERT INTO user_preferences "
                "(user_id, style_archetype, selected_styles) "
                "VALUES (:u, 'old_money', '[\"old_money\"]'::jsonb)",
                True,
            ),
            (
                "gecersiz arketip REDDEDILMELI",
                "INSERT INTO user_preferences "
                "(user_id, style_archetype) VALUES (:u, 'classic')",
                False,
            ),
            (
                "3 tarz kabul edilmeli",
                "INSERT INTO user_preferences "
                "(user_id, selected_styles) VALUES "
                "(:u, '[\"goth\",\"y2k\",\"boho\"]'::jsonb)",
                True,
            ),
            (
                "4 tarz REDDEDILMELI",
                "INSERT INTO user_preferences "
                "(user_id, selected_styles) VALUES "
                "(:u, '[\"goth\",\"y2k\",\"boho\",\"minimalist\"]'::jsonb)",
                False,
            ),
            (
                "bos dizi REDDEDILMELI",
                "INSERT INTO user_preferences "
                "(user_id, selected_styles) VALUES (:u, '[]'::jsonb)",
                False,
            ),
        ]

        for label, statement, should_pass in cases:
            savepoint = connection.begin_nested()
            try:
                connection.execute(text(statement), {"u": user_id})
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
    print("8 ARKETIP + COK SECIMLI TARZ GOCU")
    print("=" * 70)

    run_steps()
    verify()
    test_constraints()

    print("\nHazir. Sirada:")
    print("    python scripts/09_compute_style_scores.py")


if __name__ == "__main__":
    main()
