"""
SOSYAL KATMAN TABLOLARI: friendships, conversations, messages.

Bu script IDEMPOTENTTIR: create_all yalnizca eksik tabloyu
olusturur, var olan tablolara dokunmaz ve veri silmez.

Kullanim:
    python scripts/18_create_social_tables.py
    python scripts/18_create_social_tables.py --sql
    python scripts/18_create_social_tables.py --status


NEDEN EK BIR HAM SQL ADIMI VAR
------------------------------
Arkadaslik cifti FONKSIYONEL bir indeksle tekillestiriliyor:

    CREATE UNIQUE INDEX uq_friendship_pair ON friendships (
        LEAST(requester_id, addressee_id),
        GREATEST(requester_id, addressee_id)
    );

Boyle bir indeks SQLAlchemy'nin __table_args__ yapisinda
temiz ifade edilemiyor, bu yuzden create_all'dan SONRA elle
calistiriliyor. Yaptigi is: A→B arkadasligi varken B→A
satirinin olusmasini VERITABANI seviyesinde engellemek.

Uygulama katmaninda da kontrol var ama tek basina yetmez:
iki istek ayni anda gelirse ikisi de "yok" gorup ikisi de
yazar. Kisit veritabaninda olunca yaris kosulu imkansiz.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import inspect, text

from app.database import Base, engine

# noqa: F401 — import edilmeleri SART: Base.metadata'ya
# ancak boyle kaydoluyorlar, yoksa create_all onlari gormez.
from app.models import (  # noqa: F401
    Conversation,
    Friendship,
    Message,
)


TARGET_TABLES = ("friendships", "conversations", "messages")


# create_all'in uretemedigi fonksiyonel indeks.
PAIR_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_friendship_pair
ON friendships (
    LEAST(requester_id, addressee_id),
    GREATEST(requester_id, addressee_id)
)
"""


# Belgeleme amacli: bu semanin duz SQL karsiligi.
# --sql ile yazdiriliyor. Neon konsoluna elle yapistirmak
# isteyen olursa diye.
EQUIVALENT_SQL = """
-- =====================================================
-- ARKADASLIK
-- =====================================================
CREATE TABLE IF NOT EXISTS friendships (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    addressee_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at  TIMESTAMPTZ,

    CONSTRAINT ck_friendships_status
        CHECK (status IN ('pending', 'accepted', 'declined')),

    CONSTRAINT ck_friendships_not_self
        CHECK (requester_id <> addressee_id)
);

-- Bir CIFT icin TEK satir: A->B varken B->A yazilamaz.
-- Yon (kim istedi) korunuyor ama iliski tekil.
CREATE UNIQUE INDEX IF NOT EXISTS uq_friendship_pair
ON friendships (
    LEAST(requester_id, addressee_id),
    GREATEST(requester_id, addressee_id)
);

CREATE INDEX IF NOT EXISTS ix_friendships_addressee_status
    ON friendships (addressee_id, status);
CREATE INDEX IF NOT EXISTS ix_friendships_requester_status
    ON friendships (requester_id, status);


-- =====================================================
-- SOHBET (birebir)
-- =====================================================
CREATE TABLE IF NOT EXISTS conversations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_low_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_high_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_conversation_pair
        UNIQUE (user_low_id, user_high_id),

    CONSTRAINT ck_conversations_not_self
        CHECK (user_low_id <> user_high_id),

    -- Kanonik sira: (A,B) ve (B,A) ayni satira dussun diye
    -- kucuk UUID her zaman solda. UNIQUE kisitinin ise
    -- yaramasi buna bagli.
    CONSTRAINT ck_conversations_canonical_order
        CHECK (user_low_id < user_high_id)
);

CREATE INDEX IF NOT EXISTS ix_conversations_last_message_at
    ON conversations (last_message_at);


-- =====================================================
-- MESAJ
-- =====================================================
CREATE TABLE IF NOT EXISTS messages (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body             TEXT,

    -- PAYLASILAN URUN — ayri tablo DEGIL, nullable kolon.
    -- Gerekce: mesaj basina en fazla bir urun ve sohbet
    -- acilisi en sicak okuma yolu (tek LEFT JOIN).
    -- Ayrinti: models.py -> Message docstring.
    --
    -- SET NULL: katalogdan urun kalkarsa mesaj SILINMEZ.
    product_id       VARCHAR REFERENCES products(product_id) ON DELETE SET NULL,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at          TIMESTAMPTZ,

    -- Bos mesaj olamaz: ya metin ya urun.
    CONSTRAINT ck_messages_not_empty
        CHECK (body IS NOT NULL OR product_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_created
    ON messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS ix_messages_unread
    ON messages (conversation_id, read_at);
CREATE INDEX IF NOT EXISTS ix_messages_product_id
    ON messages (product_id);
"""


def _retrying(action, label):
    """
    Neon soguk baslangicta ilk baglantiyi reddedebiliyor
    (olculdu: askidayken connect_timeout'a takiliyor, uyandiktan
    sonra 3-4 saniyede baglaniyor).
    """

    for attempt in range(3):

        try:
            return action()

        except Exception as error:

            if attempt == 2:
                raise

            print(
                "  %s denemesi %d basarisiz (%s). "
                "5 saniye sonra tekrar..."
                % (label, attempt + 1, str(error)[:80])
            )

            time.sleep(5)


def show_status():

    inspector = inspect(engine)

    existing = set(inspector.get_table_names())

    print("  TABLOLAR")

    for table in TARGET_TABLES:

        mark = "VAR" if table in existing else "YOK"

        satir = ""

        if table in existing:

            with engine.connect() as conn:
                count = conn.execute(
                    text("SELECT COUNT(*) FROM %s" % table)
                ).scalar()

            satir = "  (%d satir)" % count

        print("    %-16s %s%s" % (table, mark, satir))


def main():

    parser = argparse.ArgumentParser(
        description="Sosyal katman tablolarini olusturur."
    )
    parser.add_argument(
        "--sql",
        action="store_true",
        help="Semanin duz SQL karsiligini yazar, hicbir sey calistirmaz.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Tablolar var mi, kac satir?",
    )

    args = parser.parse_args()

    if args.sql:
        print(EQUIVALENT_SQL)
        return

    print("=" * 70)
    print("SOSYAL KATMAN TABLOLARI")
    print("=" * 70)

    if args.status:
        _retrying(show_status, "durum")
        return

    inspector = _retrying(lambda: inspect(engine), "baglanti")

    existing = set(inspector.get_table_names())

    for table in TARGET_TABLES:

        if table in existing:
            print("  %s zaten var." % table)
        else:
            print("  olusturulacak: %s" % table)

    print()

    _retrying(
        lambda: Base.metadata.create_all(bind=engine),
        "create_all",
    )

    print("  create_all tamamlandi.")

    # create_all'in uretemedigi fonksiyonel indeks.
    def add_pair_index():
        with engine.begin() as conn:
            conn.execute(text(PAIR_INDEX_SQL))

    _retrying(add_pair_index, "uq_friendship_pair")

    print("  uq_friendship_pair indeksi hazir.")
    print()

    show_status()

    print()
    print("  Hazir.")


if __name__ == "__main__":
    main()
