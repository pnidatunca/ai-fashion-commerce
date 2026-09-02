"""
SOSYAL KATMAN — arkadaslik, birebir mesajlasma, urun paylasimi.

Tablolar models.py'de (Friendship / Conversation / Message);
sema kararlarinin gerekcesi orada yazili. Bu dosya KURALLARI
tutuyor: kim kime istek gonderebilir, kim kime yazabilir,
sohbet nasil bulunur.


NEDEN crud.py'YE EKLENMEDI
--------------------------
crud.py veri erisimi: "su satiri getir, bunu yaz". Buradaki
isin cogu veri erisimi DEGIL, KURAL:

    - kendine istek gonderemezsin
    - zaten arkadassaniz ikinci istek olmaz
    - istegi yalnizca ALICI cevaplayabilir
    - arkadas olmayana mesaj gidemez

feed.py ve outfit.py de kendi sorgularini kendi tutuyor;
ayni desen.


GUVENLIK: HER UCTA IKI SORU
---------------------------
"Bu kullanici giris yapmis mi" yetmiyor. Her islemde ikinci
bir soru var: "bu kaynak ONUN mu?" Sohbet kimligi tahmin
edilebilir bir UUID degil ama yine de her okuma/yazmada
kullanicinin o sohbetin tarafi oldugu dogrulaniyor
(_require_participant). Aksi halde kimlik bilen herkes
baskasinin yazismasini okuyabilirdi.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    FRIENDSHIP_ACCEPTED,
    FRIENDSHIP_BLOCKED,
    FRIENDSHIP_DECLINED,
    FRIENDSHIP_PENDING,
    Conversation,
    Friendship,
    Message,
    Product,
    User,
)

logger = logging.getLogger(__name__)


# Kullanici aramada donen en fazla sonuc.
USER_SEARCH_LIMIT = 10

# Sohbet acilisinda cekilen mesaj sayisi.
MESSAGE_PAGE_SIZE = 50


class SocialError(Exception):
    """
    Kural ihlali — teknik hata degil.

    Ayri bir tip: uc katmani bunu 400/403'e cevirebilsin,
    beklenmeyen hatalarla karismasin.
    """

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


# =========================================================
# KULLANICI GORUNUMU
# =========================================================

def public_user(user: User) -> dict:
    """
    Baskasina gosterilebilecek kullanici bilgisi.

    E-POSTA DONMUYOR. Arkadas arama sonuclari ve mesaj
    baslıklari herkese acik yerler; adres sizdirmak
    kullanicinin vermedigi bir izni kullanmak olurdu.
    Ayni karar ReviewResponse'ta da alinmisti.

    Soyadin yalnizca bas harfi: "Emre K." Ad benzerligi
    olanlari ayirt etmeye yetiyor, tam kimlik vermiyor.
    """

    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()

    initial = f" {last[0].upper()}." if last else ""

    return {
        "id": str(user.id),
        "name": (first + initial).strip() or "WishNN kullanıcısı",
        "initials": (
            (first[:1] + last[:1]).upper() or "W"
        ),
        # @handle: paylasilmak uzere tasarlanmis tanimlayici.
        # Ayni adi tasiyan iki kisiyi ayirt etmenin de tek
        # yolu ("ali Y." iki kisi olabilir, @aliyilmaz bir).
        "username": user.username,
    }


# =========================================================
# ARKADASLIK
# =========================================================

def _pair_filter(a, b):
    """A-B veya B-A: iliski yonsuz sorgulanirken kullaniliyor."""

    return or_(
        and_(
            Friendship.requester_id == a,
            Friendship.addressee_id == b,
        ),
        and_(
            Friendship.requester_id == b,
            Friendship.addressee_id == a,
        ),
    )


def get_friendship(db: Session, a, b) -> Friendship | None:
    """Iki kullanici arasindaki iliski satiri (varsa)."""

    return db.execute(
        select(Friendship).where(_pair_filter(a, b))
    ).scalar_one_or_none()


def are_friends(db: Session, a, b) -> bool:

    row = get_friendship(db, a, b)

    return bool(row and row.status == FRIENDSHIP_ACCEPTED)


def search_users(db: Session, me: User, query: str) -> list[dict]:
    """
    Arkadas eklemek icin kullanici arar.

    E-POSTA ILE ARAMA TAM ESLESME ISTIYOR.
    Ad ile arama kismi eslesiyor ("eme" -> "Emre") ama
    e-posta oyle degil: "@gmail" yazip butun gmail
    kullanicilarini listeleyebilmek bir adres hasat etme
    araci olurdu. E-postayi zaten bilen biri tam yazip
    bulabilir.

    Sonuclara mevcut iliski durumu ekleniyor ki arayuz
    "Ekle" mi "İstek gönderildi" mi "Arkadaşınız" mi
    yazacagini bilsin.
    """

    cleaned = (query or "").strip()

    if len(cleaned) < 2:
        return []

    pattern = f"%{cleaned}%"

    # KULLANICI ADI ARAMASI
    #
    # Bastaki @ atiliyor: kullanici "@pinar" da yazabilir
    # "pinar" da. Kullanici adinda KISMI eslesmeye izin
    # veriliyor (e-postanin aksine) cunku amaci tam da
    # bulunabilir olmak — paylasilmak uzere tasarlanmis bir
    # tanimlayici. E-postada kismi arama adres hasat araci
    # olurdu, burada oyle bir risk yok.
    handle = cleaned[1:] if cleaned.startswith("@") else cleaned

    handle_pattern = f"%{handle.lower()}%"

    statement = (
        select(User)
        .where(User.id != me.id)
        .where(
            or_(
                func.lower(User.username).like(handle_pattern),
                func.lower(User.email) == cleaned.lower(),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                # "emre kucukdumlu" gibi tam ad aramasi
                func.concat(
                    User.first_name, " ", User.last_name
                ).ilike(pattern),
            )
        )
        .limit(USER_SEARCH_LIMIT)
    )

    found = list(db.execute(statement).scalars())

    if not found:
        return []

    # ENGELLI KULLANICILAR ARAMADA GORUNMUYOR.
    #
    # Iki yon de gizleniyor: engelledigim kisiyi gormek
    # istemem, beni engelleyen kisiyi de bulmamam gerekir
    # (bulabilsem engel anlamsiz olurdu).
    blocked_rows = db.execute(
        select(Friendship).where(
            and_(
                Friendship.status == FRIENDSHIP_BLOCKED,
                or_(
                    Friendship.requester_id == me.id,
                    Friendship.addressee_id == me.id,
                ),
            )
        )
    ).scalars()

    blocked_ids = set()

    for row in blocked_rows:
        blocked_ids.add(row.requester_id)
        blocked_ids.add(row.addressee_id)

    blocked_ids.discard(me.id)

    found = [u for u in found if u.id not in blocked_ids]

    if not found:
        return []

    # Iliskileri TEK sorguda cek: kullanici basina ayri sorgu
    # 10 istek demek olurdu.
    ids = [u.id for u in found]

    rows = db.execute(
        select(Friendship).where(
            or_(
                and_(
                    Friendship.requester_id == me.id,
                    Friendship.addressee_id.in_(ids),
                ),
                and_(
                    Friendship.addressee_id == me.id,
                    Friendship.requester_id.in_(ids),
                ),
            )
        )
    ).scalars()

    by_other: dict = {}

    for row in rows:

        other = (
            row.addressee_id
            if row.requester_id == me.id
            else row.requester_id
        )

        by_other[other] = row

    # ORTAK ARKADAS SAYILARI — tek sorguda.
    mutual = mutual_counts(db, me, [u.id for u in found])

    results = []

    for user in found:

        row = by_other.get(user.id)

        entry = public_user(user)

        entry["mutual_friends"] = mutual.get(str(user.id), 0)

        if row is None:
            entry["relation"] = "none"

        elif row.status == FRIENDSHIP_ACCEPTED:
            entry["relation"] = "friends"

        elif row.status == FRIENDSHIP_PENDING:
            # Bekleyen istegin YONU onemli: arayuz "istek
            # gonderildi" mi yoksa "kabul et" mi gosterecek.
            entry["relation"] = (
                "outgoing"
                if row.requester_id == me.id
                else "incoming"
            )
            entry["friendship_id"] = str(row.id)

        else:
            entry["relation"] = "declined"

        results.append(entry)

    return results


def send_request(db: Session, me: User, target_id) -> Friendship:
    """
    Arkadaslik istegi gonderir.

    ADIMLAR
      1. hedef var mi, kendisi mi
      2. zaten bir iliski var mi (dort ayri durum)
      3. satiri yaz
      4. yaris kosulunu veritabanina birak

    4. adim onemli: iki istek ayni anda gelirse ikisi de 2.
    adimda "iliski yok" gorur. IntegrityError yakalaniyor ve
    "zaten istek var" mesajina cevriliyor — kisit
    uq_friendship_pair'de (bkz. scripts/18).
    """

    target = db.get(User, target_id)

    if target is None:
        raise SocialError("Kullanıcı bulunamadı.", 404)

    if target.id == me.id:
        raise SocialError("Kendine arkadaşlık isteği gönderemezsin.")

    existing = get_friendship(db, me.id, target.id)

    if existing is not None:

        # ENGEL VARSA ISTEK GONDERILEMEZ.
        #
        # Yonu sormuyoruz: engel hangi tarafta olursa olsun
        # iletisim kapali. Ayrica mesaj da "engellendin"
        # demiyor — engellendigini bilmek engelleyenin
        # vermek zorunda olmadigi bir bilgi.
        if existing.status == FRIENDSHIP_BLOCKED:
            raise SocialError(
                "Bu kullanıcıya şu anda istek gönderemezsin.",
                403,
            )

        if existing.status == FRIENDSHIP_ACCEPTED:
            raise SocialError("Zaten arkadaşsınız.")

        if existing.status == FRIENDSHIP_PENDING:

            if existing.requester_id == me.id:
                raise SocialError("İsteğin zaten bekliyor.")

            raise SocialError(
                "Bu kullanıcı sana zaten istek göndermiş. "
                "İsteklerinden kabul edebilirsin."
            )

        # Reddedilmis istek TEKRAR ACILIYOR.
        #
        # Satiri silip yenisini yazmak yerine ayni satiri
        # pending'e cekiyoruz: uq_friendship_pair zaten
        # ikinci satira izin vermez, silip yazmak da gereksiz
        # bir yazma turu olurdu.
        existing.requester_id = me.id
        existing.addressee_id = target.id
        existing.status = FRIENDSHIP_PENDING
        existing.responded_at = None

        db.commit()
        db.refresh(existing)

        return existing

    friendship = Friendship(
        requester_id=me.id,
        addressee_id=target.id,
        status=FRIENDSHIP_PENDING,
    )

    db.add(friendship)

    try:
        db.commit()

    except IntegrityError:
        # Yaris kosulu: ayni anda karsi taraf da gondermis.
        db.rollback()

        raise SocialError("Bu kullanıcıyla zaten bir isteğin var.")

    db.refresh(friendship)

    return friendship


def respond_request(
    db: Session,
    me: User,
    friendship_id,
    accept: bool,
) -> Friendship:
    """
    Bekleyen istegi kabul eder veya reddeder.

    YALNIZCA ALICI CEVAPLAYABILIR. Gonderenin kendi istegini
    kabul etmesi engelleniyor — yon bilgisini tutmamizin asil
    sebebi bu.
    """

    friendship = db.get(Friendship, friendship_id)

    if friendship is None:
        raise SocialError("İstek bulunamadı.", 404)

    if friendship.addressee_id != me.id:
        raise SocialError(
            "Bu isteği yanıtlama yetkin yok.", 403
        )

    if friendship.status != FRIENDSHIP_PENDING:
        raise SocialError("Bu istek zaten yanıtlanmış.")

    friendship.status = (
        FRIENDSHIP_ACCEPTED if accept else FRIENDSHIP_DECLINED
    )

    friendship.responded_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(friendship)

    return friendship


def remove_friend(db: Session, me: User, other_id) -> None:
    """
    Arkadasligi kaldirir.

    Sohbet SILINMIYOR: yazisma gecmisi arkadaslik durumuna
    bagli degil. Arkadaslikan cikarilan biri yeni mesaj
    gonderemez (send_message kontrol ediyor) ama eski
    mesajlar iki tarafta da durur.
    """

    friendship = get_friendship(db, me.id, other_id)

    if friendship is None:
        raise SocialError("Böyle bir arkadaşlık yok.", 404)

    db.delete(friendship)
    db.commit()


def list_friends(db: Session, me: User) -> list[dict]:

    rows = db.execute(
        select(Friendship).where(
            and_(
                Friendship.status == FRIENDSHIP_ACCEPTED,
                or_(
                    Friendship.requester_id == me.id,
                    Friendship.addressee_id == me.id,
                ),
            )
        )
    ).scalars()

    friends = []

    for row in rows:

        other_id = (
            row.addressee_id
            if row.requester_id == me.id
            else row.requester_id
        )

        other = db.get(User, other_id)

        if other is None:
            continue

        friends.append(public_user(other))

    friends.sort(key=lambda item: item["name"].casefold())

    return friends


def list_pending(db: Session, me: User) -> list[dict]:
    """Bana gelen, henuz yanitlamadigim istekler."""

    rows = db.execute(
        select(Friendship)
        .where(
            and_(
                Friendship.addressee_id == me.id,
                Friendship.status == FRIENDSHIP_PENDING,
            )
        )
        .order_by(Friendship.created_at.desc())
    ).scalars()

    rows = list(rows)

    # Ortak arkadas sayisi: tanimadigin birinden gelen istegi
    # degerlendirmenin en pratik yolu.
    mutual = mutual_counts(db, me, [r.requester_id for r in rows])

    pending = []

    for row in rows:

        requester = db.get(User, row.requester_id)

        if requester is None:
            continue

        entry = public_user(requester)
        entry["friendship_id"] = str(row.id)
        entry["created_at"] = row.created_at
        entry["mutual_friends"] = mutual.get(
            str(row.requester_id), 0
        )

        pending.append(entry)

    return pending


# =========================================================
# SOHBET
# =========================================================

def _canonical(a, b):
    """
    Kanonik sira: kucuk UUID solda.

    conversations tablosunda ck_conversations_canonical_order
    bunu zorunlu tutuyor; burasi o kurala uyan tek yer olsun
    diye ayri fonksiyon.
    """

    return (a, b) if str(a) < str(b) else (b, a)


def get_or_create_conversation(db: Session, a, b) -> Conversation:
    """
    Iki kullanicinin sohbetini bulur, yoksa acar.

    Yaris kosulu: iki mesaj ayni anda gonderilirse ikisi de
    "sohbet yok" gorup ikisi de acmaya calisir. UNIQUE kisiti
    ikincisini reddediyor, IntegrityError yakalanip mevcut
    satir okunuyor.
    """

    low, high = _canonical(a, b)

    existing = db.execute(
        select(Conversation).where(
            and_(
                Conversation.user_low_id == low,
                Conversation.user_high_id == high,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing

    conversation = Conversation(
        user_low_id=low,
        user_high_id=high,
    )

    db.add(conversation)

    try:
        db.commit()

    except IntegrityError:

        db.rollback()

        conversation = db.execute(
            select(Conversation).where(
                and_(
                    Conversation.user_low_id == low,
                    Conversation.user_high_id == high,
                )
            )
        ).scalar_one()

        return conversation

    db.refresh(conversation)

    return conversation


def _require_participant(
    db: Session,
    me: User,
    conversation_id,
) -> Conversation:
    """
    Sohbeti getirir ve kullanicinin TARAFI oldugunu dogrular.

    Her okuma ve yazmada cagriliyor. "Giris yapmis olmak"
    yetmez: kimlik bilen biri baskasinin yazismasini
    okuyabilirdi.
    """

    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise SocialError("Sohbet bulunamadı.", 404)

    if me.id not in (
        conversation.user_low_id,
        conversation.user_high_id,
    ):
        raise SocialError("Bu sohbete erişimin yok.", 403)

    return conversation


def other_party(conversation: Conversation, me: User):

    return (
        conversation.user_high_id
        if conversation.user_low_id == me.id
        else conversation.user_low_id
    )


def list_conversations(db: Session, me: User) -> list[dict]:
    """
    Gelen kutusu: sohbetler, son mesaji ve okunmamis sayisiyla.

    TEK SORGU, N+1 YOK. Sohbet basina "son mesaj nedir" ve
    "kac okunmamis var" ayri ayri sorulsaydi 20 sohbet 41
    sorgu ederdi. Ikisi de LATERAL ve korele alt sorgu ile
    ayni sorguda.

    Siralama last_message_at'e gore: bu alan tam da bunun
    icin denormalize edildi (bkz. models.py Conversation).
    """

    rows = db.execute(
        text(
            """
            SELECT
                c.id,
                c.last_message_at,
                CASE WHEN c.user_low_id = :me
                     THEN c.user_high_id ELSE c.user_low_id
                END                              AS other_id,
                m.body                           AS last_body,
                m.product_id                     AS last_product_id,
                m.sender_id                      AS last_sender_id,
                (
                    SELECT COUNT(*) FROM messages um
                    WHERE um.conversation_id = c.id
                      AND um.sender_id <> :me
                      AND um.read_at IS NULL
                )                                AS unread
            FROM conversations c
            LEFT JOIN LATERAL (
                SELECT body, product_id, sender_id
                FROM messages
                WHERE conversation_id = c.id
                ORDER BY created_at DESC
                LIMIT 1
            ) m ON TRUE
            WHERE (c.user_low_id = :me OR c.user_high_id = :me)
              -- GIZLENMIS SOHBETLER ATLANIYOR.
              -- Kural: gizli <=> hidden_at >= last_message_at.
              -- Yeni mesaj last_message_at'i ileri tasidigi
              -- icin sohbet kendiliginden geri geliyor;
              -- bayrak sifirlamak gerekmiyor.
              AND NOT (
                  c.user_low_id = :me
                  AND c.hidden_low_at IS NOT NULL
                  AND c.hidden_low_at >= c.last_message_at
              )
              AND NOT (
                  c.user_high_id = :me
                  AND c.hidden_high_at IS NOT NULL
                  AND c.hidden_high_at >= c.last_message_at
              )
            ORDER BY c.last_message_at DESC
            """
        ),
        {"me": me.id},
    ).mappings()

    conversations = []

    for row in rows:

        other = db.get(User, row["other_id"])

        if other is None:
            continue

        # Onizleme metni: urun paylasimi olan mesajda govde
        # bos olabilir, o zaman "Ürün paylaştı" yaziyoruz.
        preview = (row["last_body"] or "").strip()

        if not preview and row["last_product_id"]:
            preview = "Ürün paylaştı"

        conversations.append(
            {
                "id": str(row["id"]),
                "user": public_user(other),
                "last_message": preview[:120],
                "last_message_at": row["last_message_at"],
                "unread": int(row["unread"] or 0),
                "last_from_me": row["last_sender_id"] == me.id,
            }
        )

    return conversations


def unread_total(db: Session, me: User) -> int:
    """Header rozeti icin: butun sohbetlerdeki okunmamis toplami."""

    return int(
        db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE (c.user_low_id = :me OR c.user_high_id = :me)
                  AND m.sender_id <> :me
                  AND m.read_at IS NULL
                """
            ),
            {"me": me.id},
        ).scalar()
        or 0
    )


def list_messages(
    db: Session,
    me: User,
    conversation_id,
    limit: int = MESSAGE_PAGE_SIZE,
) -> tuple[Conversation, list[Message]]:
    """
    Sohbetin son mesajlari, eskiden yeniye.

    Sorgu yeniden eskiye siralayip limitliyor (indeks bu
    yonde), sonra liste ters cevriliyor: ekranda eskiden
    yeniye okunuyor.
    """

    conversation = _require_participant(db, me, conversation_id)

    rows = list(
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        ).scalars()
    )

    rows.reverse()

    return conversation, rows


def mark_read(db: Session, me: User, conversation_id) -> int:
    """
    Karsi taraftan gelen okunmamislari okundu isaretler.

    Kendi mesajlarima dokunmuyor: "okundu" bilgisi ALICININ
    eylemi.
    """

    conversation = _require_participant(db, me, conversation_id)

    result = db.execute(
        text(
            """
            UPDATE messages
            SET read_at = NOW()
            WHERE conversation_id = :cid
              AND sender_id <> :me
              AND read_at IS NULL
            """
        ),
        {"cid": conversation.id, "me": me.id},
    )

    db.commit()

    return int(result.rowcount or 0)


def send_message(
    db: Session,
    me: User,
    to_user_id=None,
    conversation_id=None,
    body: str | None = None,
    product_id: str | None = None,
) -> tuple[Conversation, Message]:
    """
    Mesaj gonderir. Metin, urun ya da ikisi birden.

    ADIMLAR
      1. icerik var mi (bos mesaj yok)
      2. urun verildiyse GERCEKTEN var mi
      3. alici kim — sohbetten ya da to_user_id'den
      4. ARKADAS MIYIZ
      5. sohbeti bul/ac
      6. mesaji yaz + last_message_at guncelle

    4. ADIM NEDEN VAR
    Ozellik "arkadasina gonder". Arkadaslik kontrolu olmasa
    kimlik bilen herkes herkese yazabilirdi; bu bir spam
    kanali olurdu.

    2. ADIM NEDEN VAR
    Uydurma bir product_id ile mesaj atilirsa sohbette bos
    bir kart cikar ve hata kullanicinin karsisina cok sonra
    cikar. Ayni kontrol gardirop kaydetmede de yapiliyor.
    """

    text_body = (body or "").strip() or None

    product_key = (product_id or "").strip() or None

    if not text_body and not product_key:
        raise SocialError("Boş mesaj gönderilemez.")

    if product_key is not None:

        exists = db.get(Product, product_key)

        if exists is None:
            raise SocialError("Ürün bulunamadı.", 404)

    # ALICIYI BELIRLE
    if conversation_id is not None:

        conversation = _require_participant(db, me, conversation_id)

        target_id = other_party(conversation, me)

    else:

        if to_user_id is None:
            raise SocialError("Alıcı belirtilmedi.")

        target = db.get(User, to_user_id)

        if target is None:
            raise SocialError("Kullanıcı bulunamadı.", 404)

        if target.id == me.id:
            raise SocialError("Kendine mesaj gönderemezsin.")

        target_id = target.id

        conversation = None

    if is_blocked_between(db, me.id, target_id) is not None:
        raise SocialError(
            "Bu kullanıcıyla mesajlaşma kapalı.",
            403,
        )

    if not are_friends(db, me.id, target_id):
        raise SocialError(
            "Yalnızca arkadaşlarına mesaj gönderebilirsin.",
            403,
        )

    if conversation is None:
        conversation = get_or_create_conversation(
            db, me.id, target_id
        )

    message = Message(
        conversation_id=conversation.id,
        sender_id=me.id,
        body=text_body,
        product_id=product_key,
    )

    db.add(message)

    # Gelen kutusu siralamasi bu alandan okunuyor; mesajla
    # AYNI islemde guncelleniyor ki ikisi ayrisamasin.
    conversation.last_message_at = datetime.now(timezone.utc)

    db.commit()

    db.refresh(message)
    db.refresh(conversation)

    return conversation, message


# =========================================================
# ENGELLEME
# =========================================================
#
# REDDETMEKTEN FARKI
# Reddedilen istek 'declined' olarak kaliyor ama ayni kisi
# TEKRAR gonderebiliyor: send_request reddedilmis satiri
# yeniden 'pending'e cekiyor (bilincli — insanlar fikir
# degistirir). Yani reddetmek bir koruma degil, erteleme.
#
# Engelleme gercek durak: istek gonderilemiyor, mesaj
# gidemiyor, aramada gorunmuyor.

def is_blocked_between(db: Session, a, b) -> Friendship | None:
    """
    Iki kullanici arasinda engel var mi?

    YONU SORMUYOR. Engel hangi yonde olursa olsun iletisim
    kapali: A B'yi engellediyse B de A'ya yazamaz. Aksi halde
    engelleme tek tarafli bir "sessize alma" olurdu ve
    engellenen kisi yazmaya devam ederdi.
    """

    row = get_friendship(db, a, b)

    if row is not None and row.status == FRIENDSHIP_BLOCKED:
        return row

    return None


def block_user(db: Session, me: User, other_id) -> Friendship:
    """
    Kullaniciyi engeller.

    Arkadaslik varsa BOZULUYOR: engelledigin biri arkadas
    listende kalmamali.

    Satir yoksa olusturuluyor — arkadas olmayan birini de
    engelleyebilmek gerekiyor (tanimadigin biri istek
    gonderiyorsa asil ihtiyac bu).
    """

    if str(other_id) == str(me.id):
        raise SocialError("Kendini engelleyemezsin.")

    other = db.get(User, other_id)

    if other is None:
        raise SocialError("Kullanıcı bulunamadı.", 404)

    row = get_friendship(db, me.id, other.id)

    if row is None:

        row = Friendship(
            requester_id=me.id,
            addressee_id=other.id,
            status=FRIENDSHIP_BLOCKED,
            blocked_by=me.id,
        )

        db.add(row)

    else:

        if (
            row.status == FRIENDSHIP_BLOCKED
            and row.blocked_by == me.id
        ):
            raise SocialError("Bu kullanıcıyı zaten engellemişsin.")

        if (
            row.status == FRIENDSHIP_BLOCKED
            and row.blocked_by != me.id
        ):
            # Karsi taraf beni engellemis. Ustune yazmak,
            # onun engelini kaldirmak olurdu.
            raise SocialError(
                "Bu kullanıcıyla iletişim engellenmiş durumda.",
                403,
            )

        row.status = FRIENDSHIP_BLOCKED
        row.blocked_by = me.id
        row.responded_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(row)

    return row


def unblock_user(db: Session, me: User, other_id) -> None:
    """
    Engeli kaldirir.

    YALNIZCA ENGELLEYEN KALDIRABILIR. blocked_by kolonunun
    var olma sebebi bu: bir cift icin tek satir oldugu icin
    "kim engelledi" bilgisi olmadan engellenen kisi kendi
    engelini kaldirabilirdi.

    Satir SILINIYOR, 'declined'a cevrilmiyor: engel kalkinca
    iki taraf da bastan baslayabilmeli.
    """

    row = get_friendship(db, me.id, other_id)

    if row is None or row.status != FRIENDSHIP_BLOCKED:
        raise SocialError("Böyle bir engel yok.", 404)

    if row.blocked_by != me.id:
        raise SocialError(
            "Bu engeli yalnızca engelleyen kişi kaldırabilir.",
            403,
        )

    db.delete(row)
    db.commit()


def list_blocked(db: Session, me: User) -> list[dict]:
    """Benim engelledigim kisiler."""

    rows = db.execute(
        select(Friendship).where(
            and_(
                Friendship.status == FRIENDSHIP_BLOCKED,
                Friendship.blocked_by == me.id,
            )
        )
    ).scalars()

    blocked = []

    for row in rows:

        other_id = (
            row.addressee_id
            if row.requester_id == me.id
            else row.requester_id
        )

        other = db.get(User, other_id)

        if other is not None:
            blocked.append(public_user(other))

    return blocked


# =========================================================
# GONDERILEN ISTEKLER
# =========================================================

def list_sent(db: Session, me: User) -> list[dict]:
    """
    Benim gonderdigim, henuz yanitlanmamis istekler.

    NEDEN GEREKLI
    Onceden yalnizca GELEN istekler gorunuyordu. Yanlis
    kisiye istek atan kullanici onu hicbir yerde goremiyor ve
    geri cekemiyordu; istek karsi tarafta sonsuza kadar
    asili kaliyordu.
    """

    rows = db.execute(
        select(Friendship)
        .where(
            and_(
                Friendship.requester_id == me.id,
                Friendship.status == FRIENDSHIP_PENDING,
            )
        )
        .order_by(Friendship.created_at.desc())
    ).scalars()

    sent = []

    for row in rows:

        other = db.get(User, row.addressee_id)

        if other is None:
            continue

        entry = public_user(other)
        entry["friendship_id"] = str(row.id)
        entry["created_at"] = row.created_at

        sent.append(entry)

    return sent


def cancel_request(db: Session, me: User, friendship_id) -> None:
    """
    Gonderilmis istegi geri ceker.

    YALNIZCA GONDEREN cagirabilir ve yalnizca HENUZ
    YANITLANMAMIS istek geri cekilebilir. Kabul edilmis bir
    arkadasligi "geri cekmek" diye bir sey yok; o
    remove_friend'in isi.

    Satir SILINIYOR: geri cekilen istek hic olmamis gibi
    davranmali, ikisi de bastan baslayabilmeli.
    """

    row = db.get(Friendship, friendship_id)

    if row is None:
        raise SocialError("İstek bulunamadı.", 404)

    if row.requester_id != me.id:
        raise SocialError("Bu isteği geri çekme yetkin yok.", 403)

    if row.status != FRIENDSHIP_PENDING:
        raise SocialError(
            "Bu istek zaten yanıtlanmış, geri çekilemez."
        )

    db.delete(row)
    db.commit()


# =========================================================
# ORTAK ARKADAS
# =========================================================

def mutual_counts(db: Session, me: User, other_ids) -> dict:
    """
    Her hedef kullanici icin ORTAK arkadas sayisi.

    TEK SORGU, kullanici basina bir tane degil: arama 10
    sonuc donduruyor ve her biri icin ayri sorgu 10 istek
    demekti.

    Mantik: benim kabul edilmis arkadaslarim ile onun kabul
    edilmis arkadaslarinin kesisimi. Iliski yonsuz oldugu
    icin her satirdan "digeri kim" hesaplanarak iki taraf da
    taraniyor.

    NEDEN GOSTERILIYOR
    Tanimadigin birinden gelen istegi degerlendirmenin en
    pratik yolu. "2 ortak arkadasin var" bilgisi, kabul edip
    etmeme kararini kullanicinin kendisinin vermesini
    sagliyor — sistemin onun yerine karar vermesi yerine.
    """

    ids = [str(i) for i in (other_ids or []) if i]

    if not ids:
        return {}

    rows = db.execute(
        text(
            """
            -- DIKKAT: ":ids::uuid[]" YAZILMAZ.
            -- SQLAlchemy'nin text() ayristirmasi "::" cast
            -- sozdizimini bind parametresiyle karistiriyor ve
            -- parametre HIC baglanmiyor; sonuc 500. Olculdu.
            -- CAST(... AS ...) bicimi belirsiz degil.
            WITH hedefler AS (
                SELECT UNNEST(CAST(:ids AS uuid[])) AS hedef
            ),
            benim AS (
                SELECT CASE WHEN requester_id = CAST(:me AS uuid)
                            THEN addressee_id ELSE requester_id END AS uid
                FROM friendships
                WHERE status = 'accepted'
                  AND (requester_id = CAST(:me AS uuid)
                       OR addressee_id = CAST(:me AS uuid))
            ),
            onlar AS (
                SELECT
                    h.hedef AS hedef,
                    CASE WHEN f.requester_id = h.hedef
                         THEN f.addressee_id ELSE f.requester_id END AS uid
                FROM hedefler h
                JOIN friendships f
                  ON f.status = 'accepted'
                 AND (f.requester_id = h.hedef OR f.addressee_id = h.hedef)
            )
            SELECT o.hedef, COUNT(*)
            FROM onlar o
            JOIN benim b ON b.uid = o.uid
            WHERE o.uid <> CAST(:me AS uuid)
            GROUP BY o.hedef
            """
        ),
        {"me": str(me.id), "ids": ids},
    ).all()

    return {str(row[0]): int(row[1]) for row in rows}


# =========================================================
# SOHBET GIZLEME (ARSIVLEME)
# =========================================================

def hide_conversation(db: Session, me: User, conversation_id) -> None:
    """
    Sohbeti BENIM gelen kutumdan kaldirir.

    MESAJLAR SILINMIYOR. Iki kisilik bir konusmanin yarisini
    silmek, karsi tarafin gecmisini de yok etmek olurdu.

    Zaman damgasi yaziliyor; yeni mesaj gelince
    last_message_at ileri gidiyor ve sohbet KENDILIGINDEN
    geri geliyor (bkz. models.py Conversation notu). Yani bu
    "sil" degil "arsivle".
    """

    conversation = _require_participant(db, me, conversation_id)

    now = datetime.now(timezone.utc)

    if conversation.user_low_id == me.id:
        conversation.hidden_low_at = now
    else:
        conversation.hidden_high_at = now

    db.commit()
