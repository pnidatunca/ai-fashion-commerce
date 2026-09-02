"""
KULLANICI ADI — @handle kurallari ve uretimi.

Neden ayri modul: kullanici adi UC yerde kullaniliyor —
kayit (main.register_user), profil guncelleme ve arkadas
arama (social.search_users). Kurali uc yere kopyalamak, gun
gelip birinin guncellenmemesi demek. Ayni gerekce
query_engine'in frontend'den backend'e tasinmasinda da
yazilmisti.


NEDEN KULLANICI ADI EKLENDI
---------------------------
Arkadas aramak icin tek yol TAM e-posta adresiydi. Iki
problemi vardi:

  1. Kimsenin arkadasinin e-postasini ezbere bilmesi
     gerekmiyor. "pinar@ozdilek.com" yazmak zorunda kalmak,
     arkadas eklemeyi pratikte imkansiz kiliyordu.

  2. E-postayi paylasmak, paylasilmasi gerekmeyen bir sey
     paylasmak. Kullanici adi herkese acik olmak UZERE
     tasarlanmis bir tanimlayici; e-posta degil.

Kismi e-posta aramasi bilincli olarak KAPALI (adres hasat
araci olurdu). Kullanici adi bu boslugu dogru sekilde
dolduruyor: paylasilabilir, aranabilir, degistirilebilir.


TEK SEY, UC IS
--------------
    arama    : "@pinar" yazip bul
    kod      : kullanici adini soyle, o seni bulsun
    link     : site/?add=pinar

Ucu icin ayri mekanizma kurmadik; ucu de ayni alani
kullaniyor.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func
from sqlalchemy.orm import Session


MIN_LENGTH = 3
MAX_LENGTH = 24


# Harf ile baslar; harf, rakam, alt cizgi ve nokta icerir.
# Nokta ile bitemez, iki nokta yan yana gelemez.
PATTERN = re.compile(r"^[a-z][a-z0-9._]{2,23}$")


# Sistem yollariyla ve kurumsal adlarla cakismasin.
#
# "wishnn" ozellikle onemli: birinin @wishnn olmasi, resmi
# hesap sanilmasina yol acar.
RESERVED = {
    "admin", "administrator", "root", "system", "api",
    "wishnn", "wishn", "destek", "support", "help",
    "info", "iletisim", "contact", "moderator", "mod",
    "official", "resmi", "test", "null", "undefined",
    "me", "you", "user", "kullanici", "hesap", "account",
    "login", "logout", "register", "kayit", "giris",
    "search", "arama", "explore", "kesfet", "sepet", "cart",
}


class UsernameError(ValueError):
    """Kural ihlali — mesaj dogrudan kullaniciya gosteriliyor."""


def normalize(raw: str) -> str:
    """
    Girdiyi kanonik bicime cevirir.

    Kucuk harfe indiriyor ve bastaki @ isaretini atiyor:
    kullanici "@Pinar" yazdiginda da "pinar" bulunmali.
    """

    value = (raw or "").strip()

    if value.startswith("@"):
        value = value[1:]

    return value.strip().lower()


def validate(raw: str) -> str:
    """
    Kurallara uyuyorsa kanonik hali doner, uymuyorsa
    UsernameError firlatir.
    """

    value = normalize(raw)

    if not value:
        raise UsernameError("Kullanıcı adı boş olamaz.")

    if len(value) < MIN_LENGTH:
        raise UsernameError(
            "Kullanıcı adı en az %d karakter olmalı." % MIN_LENGTH
        )

    if len(value) > MAX_LENGTH:
        raise UsernameError(
            "Kullanıcı adı en fazla %d karakter olabilir."
            % MAX_LENGTH
        )

    if not PATTERN.match(value):
        raise UsernameError(
            "Kullanıcı adı bir harfle başlamalı; yalnızca "
            "küçük harf, rakam, alt çizgi ve nokta içerebilir."
        )

    if value.endswith("."):
        raise UsernameError("Kullanıcı adı nokta ile bitemez.")

    if ".." in value:
        raise UsernameError(
            "Kullanıcı adında art arda iki nokta olamaz."
        )

    if value in RESERVED:
        raise UsernameError("Bu kullanıcı adı ayrılmış, başka bir tane seç.")

    return value


def is_taken(db: Session, value: str, exclude_user_id=None) -> bool:
    """
    Alinmis mi?

    BUYUK/KUCUK HARF DUYARSIZ. "Pinar" ve "pinar" ayni kisi
    sanilacak kadar benzer; ikisinin birden var olmasi
    kimlik karisikligi (ve taklit) kapisi acardi.

    exclude_user_id: kullanici kendi adini kaydederken
    "zaten alinmis" dememek icin.
    """

    from app.models import User

    query = db.query(User).filter(
        func.lower(User.username) == value.lower()
    )

    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)

    return db.query(query.exists()).scalar()


def _slugify(text: str) -> str:
    """
    Turkce adi kullanici adina cevirir.

    "Pınar Yılmaz" -> "pinaryilmaz"

    unicodedata ile aksan ayikliyoruz ama Turkce'ye ozgu
    birkac harf NFKD'de ayrismiyor (ı, ş, ğ); onlari elle
    esliyoruz. Aksi halde "pnarylmaz" gibi okunmaz adlar
    cikiyordu.
    """

    replacements = {
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s",
        "ğ": "g", "Ğ": "g", "ç": "c", "Ç": "c",
        "ö": "o", "Ö": "o", "ü": "u", "Ü": "u",
    }

    value = "".join(replacements.get(ch, ch) for ch in (text or ""))

    value = unicodedata.normalize("NFKD", value)

    value = "".join(c for c in value if not unicodedata.combining(c))

    value = value.lower()

    value = re.sub(r"[^a-z0-9]+", "", value)

    return value


def suggest(
    db: Session,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
) -> str:
    """
    Bos birakildiginda ya da mevcut kullanicilar icin
    kullanilabilir bir ad uretir.

    Sirayla dener: adsoyad -> ad -> e-postanin yerel kismi.
    Hepsi doluysa sonuna sayi ekler.

    ASLA bos donmuyor: kullanici adi olmayan bir hesap
    aranamaz hale gelirdi ve ozelligin amaci tam da bu.
    """

    candidates = []

    base = _slugify("%s%s" % (first_name or "", last_name or ""))

    if base:
        candidates.append(base)

    only_first = _slugify(first_name or "")

    if only_first and only_first != base:
        candidates.append(only_first)

    local = _slugify((email or "").split("@")[0])

    if local:
        candidates.append(local)

    candidates.append("wn")  # son care: her zaman bir taban olsun

    for candidate in candidates:

        candidate = candidate[:MAX_LENGTH]

        # Kural harf ile baslamayi sart kosuyor.
        if not candidate or not candidate[0].isalpha():
            candidate = "u" + candidate

        candidate = candidate[:MAX_LENGTH]

        if len(candidate) < MIN_LENGTH:
            candidate = (candidate + "user")[:MAX_LENGTH]

        if candidate in RESERVED:
            continue

        if not is_taken(db, candidate):
            return candidate

        # Alinmissa sayi ekleyerek dene.
        for suffix in range(2, 1000):

            tail = str(suffix)

            trimmed = candidate[: MAX_LENGTH - len(tail)]

            attempt = trimmed + tail

            if attempt not in RESERVED and not is_taken(db, attempt):
                return attempt

    # Buraya pratikte gelinmiyor; yine de sessiz kalmasin.
    raise UsernameError("Kullanıcı adı üretilemedi.")
