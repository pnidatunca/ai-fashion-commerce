"""
Kullanici beden profili: users tablosuna beden kolonlari.

    size_top    ust beden   (XS/S/M/L/XL/XXL)
    size_bottom alt beden   (bel olcusu ya da beden)
    size_shoe   ayakkabi    (36-46)

Bu script IDEMPOTENTTIR: yalnizca eksik kolonu ekler.

Kullanim:
    python scripts/19_add_user_sizes.py
    python scripts/19_add_user_sizes.py --status


NEDEN GEREKLI
-------------
17_extract_fit_signals.py urunun kalibini biliyor
("kalibi buyuk, 5/5 yorum") ama kullanicinin bedenini
bilmiyor. Bu yuzden verilebilen en iyi tavsiye soyleydi:

    "Normal bedeninizin bir beden altini tercih edin."

Kullanici "normal bedenim ne" sorusunu kendi cevaplamak
zorunda kaliyordu. Beden bilinince tavsiye somutlasiyor:

    "Sen genelde M alıyorsun; bu üründe 5 yorumdan 5'i
     büyük geldiğini söylüyor, S öner."

NEDEN SERBEST METIN DEGIL
-------------------------
Kolonlar VARCHAR ama arayuz sabit bir listeden sectiriyor.
Serbest metin olsaydi "m", "M beden", "orta" gibi degerler
birikir ve "bir beden ustu" hesabi yapilamazdi. Hesap
SIZE_SCALE sirasina dayaniyor (bkz. app/fit_advice.py).

NEDEN products'taki gibi ALTER TABLE
------------------------------------
users tablosu ORM modelinde tanimli ve her yerde
kullaniliyor; kolonlar modele de ekleniyor (products'taki
turetilmis kolonlarin aksine). Sebep: bu kolonlar bir
script'in urettigi opsiyonel zenginlestirme degil,
kullanicinin girdigi veri. Script calismadan once de
model onlari bilmeli ki kayit/guncelleme kodu tek olsun.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text

from app.database import engine


MIGRATION = [
    ("size_top", "varchar(8)"),
    ("size_bottom", "varchar(8)"),
    ("size_shoe", "varchar(8)"),
]


def migrate():

    added = []

    with engine.begin() as conn:

        for name, sql_type in MIGRATION:

            exists = conn.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users'
                      AND column_name = :c
                    """
                ),
                {"c": name},
            ).scalar()

            if exists:
                continue

            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN %s %s"
                    % (name, sql_type)
                )
            )

            added.append(name)

    return added


def status():

    with engine.connect() as conn:

        total = conn.execute(
            text("SELECT COUNT(*) FROM users")
        ).scalar()

        filled = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM users
                WHERE size_top IS NOT NULL
                   OR size_bottom IS NOT NULL
                   OR size_shoe IS NOT NULL
                """
            )
        ).scalar()

    print("  kullanici           : %d" % total)
    print("  beden girmis        : %d" % filled)
    print("  beden girmemis      : %d" % (total - filled))


def main():

    parser = argparse.ArgumentParser(
        description="users tablosuna beden kolonlari ekler."
    )
    parser.add_argument("--status", action="store_true")

    args = parser.parse_args()

    print("=" * 62)
    print("KULLANICI BEDEN PROFILI")
    print("=" * 62)

    if args.status:
        # Neon soguk baslangicta ilk baglantiyi reddedebiliyor.
        for attempt in range(3):
            try:
                status()
                return
            except Exception as error:
                if attempt == 2:
                    raise
                print("  tekrar deneniyor (%s)..." % str(error)[:60])
                time.sleep(5)
        return

    for attempt in range(3):
        try:
            added = migrate()
            break
        except Exception as error:
            if attempt == 2:
                raise
            print("  tekrar deneniyor (%s)..." % str(error)[:60])
            time.sleep(5)

    if added:
        print("  eklenen kolonlar: %s" % ", ".join(added))
    else:
        print("  kolonlar zaten var.")

    print()

    status()

    print()
    print("  Hazir.")


if __name__ == "__main__":
    main()
