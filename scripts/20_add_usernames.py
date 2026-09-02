"""
users tablosuna KULLANICI ADI (@handle) ekler ve mevcut
kullanicilar icin uretir.

    python scripts/20_add_usernames.py
    python scripts/20_add_usernames.py --status
    python scripts/20_add_usernames.py --dry-run

IDEMPOTENT: kolon varsa dokunmuyor, adi olan kullaniciya
yeniden ad uretmiyor.


NEDEN GERIYE DONUK DOLDURMA SART
--------------------------------
Kullanici adi olmayan bir hesap ARANAMAZ hale gelir ve
ozelligin butun amaci arkadas bulmayi kolaylastirmak. Kolonu
ekleyip mevcut 14 kullaniciyi bos birakmak, onlari sistemde
gorunmez yapardi.

Uretim adlarindan yapiliyor: "Pınar Yılmaz" -> "pinaryilmaz".
Turkce harfler elle esleniyor (bkz. app/username.py
_slugify); NFKD tek basina "ı" ve "ş" harflerini
ayirmadigi icin "pnarylmaz" gibi okunmaz adlar cikiyordu.


BUYUK/KUCUK HARF DUYARSIZ TEKILLIK
----------------------------------
UNIQUE kisiti degil, FONKSIYONEL indeks:

    CREATE UNIQUE INDEX ... ON users (LOWER(username))

Duz UNIQUE olsaydi "Pinar" ve "pinar" ayni anda var
olabilirdi. Bu yalnizca karisiklik degil, TAKLIT kapisi:
kimse baskasinin adinin buyuk harfli halini alamamali.
Ayni fikir friendships tablosundaki cift tekillestirmede de
kullanilmisti.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text

from app import username as username_rules
from app.database import SessionLocal, engine


COLUMN_SQL = "ALTER TABLE users ADD COLUMN username VARCHAR(24)"

INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_lower
ON users (LOWER(username))
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


def has_column() -> bool:

    with engine.connect() as conn:
        return bool(
            conn.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users'
                      AND column_name = 'username'
                    """
                )
            ).scalar()
        )


def migrate() -> bool:
    """Kolon + indeks. Idempotent. Kolon eklendiyse True."""

    added = False

    if not has_column():
        with engine.begin() as conn:
            conn.execute(text(COLUMN_SQL))
        added = True

    with engine.begin() as conn:
        conn.execute(text(INDEX_SQL))

    return added


def backfill(dry_run: bool = False) -> list[tuple[str, str]]:
    """Adi olmayan kullanicilara ad uretir."""

    from app.models import User

    db = SessionLocal()

    produced = []

    try:
        pending = (
            db.query(User)
            .filter(
                (User.username.is_(None))
                | (User.username == "")
            )
            .all()
        )

        for user in pending:

            handle = username_rules.suggest(
                db,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                email=user.email or "",
            )

            produced.append(
                (
                    "%s %s" % (user.first_name or "", user.last_name or ""),
                    handle,
                )
            )

            if not dry_run:
                # Hemen yaziliyor ki bir sonraki suggest()
                # bu adi ALINMIS gorsun; yoksa iki kullaniciya
                # ayni ad uretilir ve UNIQUE patlar.
                user.username = handle
                db.flush()

        if not dry_run:
            db.commit()

    finally:
        db.close()

    return produced


def status():

    with engine.connect() as conn:

        total = conn.execute(
            text("SELECT COUNT(*) FROM users")
        ).scalar()

        if not has_column():
            print("  username kolonu YOK")
            print("  kullanici: %d" % total)
            return

        filled = conn.execute(
            text(
                "SELECT COUNT(*) FROM users "
                "WHERE username IS NOT NULL AND username <> ''"
            )
        ).scalar()

        print("  kullanici        : %d" % total)
        print("  kullanici adi var: %d" % filled)
        print("  eksik            : %d" % (total - filled))

        print()
        print("  ORNEKLER")

        rows = conn.execute(
            text(
                """
                SELECT username, first_name, last_name
                FROM users
                WHERE username IS NOT NULL
                ORDER BY username LIMIT 10
                """
            )
        ).all()

        for handle, first, last in rows:
            print("    @%-22s %s %s" % (handle, first or "", last or ""))


def main():

    parser = argparse.ArgumentParser(
        description="users tablosuna kullanici adi ekler."
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne uretilecegini yazar, veritabanina YAZMAZ.",
    )

    args = parser.parse_args()

    print("=" * 62)
    print("KULLANICI ADI (@handle)")
    print("=" * 62)

    if args.status:
        _retrying(status, "durum")
        return

    if args.dry_run:

        if not _retrying(has_column, "kolon kontrolu"):
            print("  username kolonu henuz yok; once migration gerekiyor.")
            print("  (--dry-run yalnizca uretimi gosterir)")
            return

        produced = _retrying(lambda: backfill(dry_run=True), "onizleme")

        print("  URETILECEK ADLAR (%d)" % len(produced))

        for name, handle in produced:
            print("    %-28s -> @%s" % (name.strip()[:28], handle))

        print()
        print("  --dry-run: veritabanina YAZILMADI.")
        return

    added = _retrying(migrate, "migration")

    print("  kolon: %s" % ("eklendi" if added else "zaten vardi"))
    print("  indeks: uq_users_username_lower hazir")
    print()

    produced = _retrying(lambda: backfill(dry_run=False), "doldurma")

    if produced:
        print("  URETILEN ADLAR (%d)" % len(produced))
        for name, handle in produced:
            print("    %-28s -> @%s" % (name.strip()[:28], handle))
    else:
        print("  Butun kullanicilarin adi zaten var.")

    print()

    status()

    print()
    print("  Hazir.")


if __name__ == "__main__":
    main()
