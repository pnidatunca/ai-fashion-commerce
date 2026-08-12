import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    print("=" * 70)
    print("DATABASE CONNECTION TEST")
    print("=" * 70)

    # .env dosyasini yukle
    load_dotenv(ENV_FILE)

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL bulunamadi.\n"
            ".env dosyasini kontrol et."
        )

    print()
    print("DATABASE_URL bulundu.")
    print("Neon PostgreSQL'e baglaniliyor...")

    try:
        with psycopg.connect(
            database_url,
            connect_timeout=10,
            sslmode="require",
        ) as connection:

            with connection.cursor() as cursor:

                # Hangi database?
                cursor.execute(
                    "SELECT current_database();"
                )
                database_name = cursor.fetchone()[0]

                # Hangi PostgreSQL kullanicisi?
                cursor.execute(
                    "SELECT current_user;"
                )
                database_user = cursor.fetchone()[0]

                # PostgreSQL versiyonu
                cursor.execute(
                    "SELECT version();"
                )
                postgres_version = cursor.fetchone()[0]

                # Basit query testi
                cursor.execute(
                    "SELECT 1;"
                )
                test_result = cursor.fetchone()[0]

    except Exception as error:
        print()
        print("=" * 70)
        print("CONNECTION FAILED")
        print("=" * 70)

        print()
        print(f"Error type : {type(error).__name__}")
        print(f"Error      : {error}")

        print()
        print(
            "Neon baglantisi kurulamadi."
        )

        raise

    print()
    print("=" * 70)
    print("CONNECTION SUCCESSFUL")
    print("=" * 70)

    print(f"Database   : {database_name}")
    print(f"User       : {database_user}")
    print(f"SELECT 1   : {test_result}")

    print()
    print("PostgreSQL:")
    print(postgres_version)

    print()
    print(
        "Neon PostgreSQL baglantisi basariyla calisiyor."
    )


if __name__ == "__main__":
    main()