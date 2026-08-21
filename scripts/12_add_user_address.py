import sys
from pathlib import Path

from sqlalchemy import text

# Backend import path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import engine


def main():
    print("=" * 70)
    print("USER ADDRESS MIGRATION")
    print("=" * 70)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS address TEXT
                """
            )
        )

    print("users.address is ready.")


if __name__ == "__main__":
    main()
