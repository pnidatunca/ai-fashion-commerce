"""
SOSYAL KATMAN GENISLETME: engelleme + sohbet gizleme.

    python scripts/21_social_block_and_hide.py
    python scripts/21_social_block_and_hide.py --status

IDEMPOTENT: var olan kolona/kisita dokunmuyor.


1) ENGELLEME
------------
friendships.status CHECK kisitina 'blocked' ekleniyor ve
blocked_by kolonu geliyor.

NEDEN blocked_by GEREKLI
Bir cift icin TEK satir var (uq_friendship_pair). Engelleme
ise YONLU: A B'yi engellediyse engeli yalnizca A
kaldirabilir. Satir paylasildigi icin "kim engelledi"
bilgisi ayri bir kolonda tutulmak zorunda; requester_id
buna yetmiyor (istegi B gondermis olabilir).

Bu olmadan engellenen kisi kendi engelini kaldirabilirdi —
engelleme diye bir sey olmazdi.

NEDEN GEREKLI (urun tarafi)
Reddedilen istek 'declined' olarak kaliyor ama ayni kisi
tekrar istek gonderebiliyor (send_request reddedilmis
satiri yeniden 'pending'e cekiyor). Yani reddetmek bir
koruma DEGIL, yalnizca erteleme. Engelleme gercek durak.


2) SOHBET GIZLEME
-----------------
conversations tablosuna hidden_low_at / hidden_high_at.

NEDEN BOOLEAN DEGIL ZAMAN DAMGASI
Gizleme "arsivleme" gibi davranmali: yeni mesaj gelince
sohbet kendiliginden geri gelmeli. Boolean olsaydi her yeni
mesajda bayragi ayrica sifirlamak gerekirdi ve bir yerde
unutulursa kullanici mesaji HIC gormezdi.

Zaman damgasiyla kural tek satir:

    gizli  <=>  hidden_at IS NOT NULL
                AND hidden_at >= last_message_at

Yeni mesaj last_message_at'i ileri tasiyor ve sohbet
otomatik geri geliyor. Ekstra yazma yok.

NEDEN low/high AYRI IKI KOLON
Sohbet iki kisilik ve kanonik sirali (user_low_id <
user_high_id). Biri sohbeti gizlerken digerinin gelen
kutusuna dokunmamali. Ayri bir tablo (conversation_hidden)
kurmak da olurdu ama birebir sohbette iki kolon ayni isi
tek indeks aramasiyla yapiyor — conversations tablosunun
participants tablosu YERINE iki kolonla tasarlanmasindaki
gerekcenin aynisi.

MESAJLAR SILINMIYOR: gizleme yalnizca BENIM gelen kutumu
etkiliyor. Karsi taraf yazismayi gormeye devam ediyor.
Iki kisilik bir konusmanin yarisini silmek, digerinin
gecmisini de yok etmek olurdu.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text

from app.database import engine


NEW_COLUMNS = [
    ("friendships", "blocked_by", "uuid"),
    ("conversations", "hidden_low_at", "timestamptz"),
    ("conversations", "hidden_high_at", "timestamptz"),
]


# CHECK kisiti degistirilemez; DROP + ADD gerekiyor.
STATUS_CONSTRAINT = """
ALTER TABLE friendships
    DROP CONSTRAINT IF EXISTS ck_friendships_status;

ALTER TABLE friendships
    ADD CONSTRAINT ck_friendships_status
    CHECK (status IN ('pending', 'accepted', 'declined', 'blocked'));
"""

# blocked_by yalnizca engelli satirlarda dolu olmali.
BLOCKED_BY_CONSTRAINT = """
ALTER TABLE friendships
    DROP CONSTRAINT IF EXISTS ck_friendships_blocked_by;

ALTER TABLE friendships
    ADD CONSTRAINT ck_friendships_blocked_by
    CHECK (
        (status = 'blocked' AND blocked_by IS NOT NULL)
        OR (status <> 'blocked' AND blocked_by IS NULL)
    );
"""

FK_SQL = """
ALTER TABLE friendships
    DROP CONSTRAINT IF EXISTS fk_friendships_blocked_by;

ALTER TABLE friendships
    ADD CONSTRAINT fk_friendships_blocked_by
    FOREIGN KEY (blocked_by) REFERENCES users(id) ON DELETE CASCADE;
"""


def _retrying(action, label):
    """Neon soguk baslangicta ilk baglantiyi reddedebiliyor."""

    for attempt in range(3):
        try:
            return action()
        except Exception as error:
            if attempt == 2:
                raise
            print("  %s yeniden deneniyor (%s)..."
                  % (label, str(error)[:70]))
            time.sleep(6)


def has_column(table: str, column: str) -> bool:

    with engine.connect() as conn:
        return bool(
            conn.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = :t AND column_name = :c
                    """
                ),
                {"t": table, "c": column},
            ).scalar()
        )


def migrate() -> list[str]:

    added = []

    for table, column, sql_type in NEW_COLUMNS:

        if has_column(table, column):
            continue

        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE %s ADD COLUMN %s %s"
                    % (table, column, sql_type)
                )
            )

        added.append("%s.%s" % (table, column))

    # Kisitlar: DROP IF EXISTS + ADD, yani tekrar
    # calistirilabilir.
    with engine.begin() as conn:
        for statement in STATUS_CONSTRAINT.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))

    with engine.begin() as conn:
        for statement in FK_SQL.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))

    with engine.begin() as conn:
        for statement in BLOCKED_BY_CONSTRAINT.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))

    # Gelen kutusu sorgusu bu kolonlardan filtreliyor.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_friendships_status
                ON friendships (status)
                """
            )
        )

    return added


def status():

    with engine.connect() as conn:

        print("  KOLONLAR")

        for table, column, _ in NEW_COLUMNS:
            mark = "VAR" if has_column(table, column) else "YOK"
            print("    %-28s %s" % ("%s.%s" % (table, column), mark))

        print()
        print("  KISITLAR")

        rows = conn.execute(
            text(
                """
                SELECT conname, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname IN (
                    'ck_friendships_status',
                    'ck_friendships_blocked_by',
                    'fk_friendships_blocked_by'
                )
                ORDER BY conname
                """
            )
        ).all()

        for name, definition in rows:
            print("    %s" % name)
            print("      %s" % definition[:110])

        print()
        print("  ARKADASLIK DURUMLARI")

        rows = conn.execute(
            text(
                """
                SELECT status, COUNT(*) FROM friendships
                GROUP BY status ORDER BY 2 DESC
                """
            )
        ).all()

        if rows:
            for value, count in rows:
                print("    %-12s %d" % (value, count))
        else:
            print("    (kayit yok)")


def main():

    parser = argparse.ArgumentParser(
        description="Engelleme + sohbet gizleme kolonlari."
    )
    parser.add_argument("--status", action="store_true")

    args = parser.parse_args()

    print("=" * 66)
    print("SOSYAL: ENGELLEME + SOHBET GIZLEME")
    print("=" * 66)

    if args.status:
        _retrying(status, "durum")
        return

    added = _retrying(migrate, "migration")

    if added:
        print("  eklenen kolonlar: %s" % ", ".join(added))
    else:
        print("  kolonlar zaten vardi.")

    print("  kisitlar guncellendi ('blocked' artik gecerli).")
    print()

    status()

    print()
    print("  Hazir.")


if __name__ == "__main__":
    main()
