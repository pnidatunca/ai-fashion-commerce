"""
Asistan ayarlari.

NEDEN DATACLASS, NEDEN MODUL SABITI DEGIL
Ilk surumde sinirlar modul seviyesinde `int(os.getenv(...))`
ile okunuyordu. Iki sorunu vardi:

  1. Ayar IMPORT aninda donuyordu. Ayni surecte iki farkli
     asistan (orn. biri hizli/ucuz, biri detayli) calistirmak
     mumkun degildi.
  2. Bozuk bir env degeri uygulamayi import aninda cokertiyordu
     — hem de sohbetle hic ilgisi olmayan bir ucu acan biri
     icin.

Simdi ayarlar bir nesne: testte elle verilir, uretimde
from_env() ile okunur, bozuk deger uyari birakip varsayilana
duser.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace

from .errors import ConfigurationError

logger = logging.getLogger(__name__)


# =========================================================
# VARSAYILAN MODEL ZINCIRI
# =========================================================
#
# NEDEN ZINCIR, NEDEN TEK MODEL DEGIL
# Ucretsiz katmanda kota MODEL BASINA ayri veriliyor. Tek
# modele baglanmak dakikada iki mesaj demek. Zincir,
# kullanilabilir kapasiteyi model sayisi kadar katliyor.
#
# SIRA: basta guclu model (niyeti anlamak muhakeme isi),
# arkada hizli/hafif yedekler. Tukenmis bir modelden gelen
# "hic cevap yok", biraz daha basit bir cevaptan kotudur.
#
# SURUMLER SABIT, "-latest" YOK: takma ad bir gun sessizce
# baska bir modele isaret eder ve asistanin davranisi biz
# hicbir sey degistirmeden degisir.
DEFAULT_MODEL_CHAIN: tuple[str, ...] = (
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)


# =========================================================
# EN KISA IZINLI ZAMAN SINIRI
# =========================================================
#
# Gemini API 10 saniyenin altindaki deadline'i REDDEDIYOR:
#
#     400 INVALID_ARGUMENT
#     "Manually set deadline 8s is too short.
#      Minimum allowed deadline is 10s."
#
# Bu hata ne kota ne zaman asimi oldugu icin yedek model
# zinciri de devreye girmiyor: cagri komple dusuyor. Yani daha
# kisa bir sinir "hizli vazgecmek" degil, "hic cevap almamak"
# demek.
#
# Bu yuzden verilen deger sessizce degil UYARIYLA yukari
# cekiliyor: yapilandirma hatasi yuzunden sohbetin tamamen
# olmesi kabul edilemez, ama neden istedigimiz sayinin
# kullanilmadigi da loglardan gorunmeli.
MIN_CALL_TIMEOUT = 10.0


def _env_number(name: str, default: float) -> float:
    """
    Sayisal env degeri — bozuksa uyari birakip varsayilana
    duser. Yapilandirma hatasi yuzunden servisin hic
    acilmamasi, yavas acilmasindan kotu.
    """

    raw = os.getenv(name, "").strip()

    if not raw:
        return default

    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "%s degeri sayi degil (%r); %s kullaniliyor.",
            name,
            raw,
            default,
        )
        return default


@dataclass(frozen=True)
class AssistantConfig:
    """
    Bir Assistant ornegine ait butun sayisal sinirlar.

    frozen: ayarlar calisma aninda degismesin. Degistirmek
    isteyen with_overrides() ile YENI bir ayar uretir; boylece
    istekler arasinda kazara sizinti olmaz.
    """

    # --- MODEL SECIMI ---
    model_chain: tuple[str, ...] = DEFAULT_MODEL_CHAIN

    # Tercih edilen model zincirin BASINA gecer, yedekler yine
    # durur: acik tercih onemli ama tukenirse sohbetin komple
    # durmasi kabul edilemez.
    preferred_model: str | None = None

    api_key: str | None = None

    # --- ZAMAN SINIRLARI (saniye) ---
    #
    # SINIR KADEMELI, SABIT DEGIL. Olculdu: ayni onemsiz istek
    # ust uste 1.27s / 105.52s / 13.37s / 2.61s / 0.66s dondu.
    # Gecikme uretimde degil, ucretsiz katmanin KUYRUGUNDA.
    #
    # Mantik: DENEYECEK BASKA MODEL VARSA cabuk vazgec, cunku
    # vazgecmenin bedeli kucuk. SON modeldeysen sabirli ol,
    # cunku pes etmenin bedeli "hic cevap yok".
    #
    # Alt sinir MIN_CALL_TIMEOUT: saglayici daha kisasini
    # reddediyor (bkz. yukarisi).
    call_timeout: float = MIN_CALL_TIMEOUT
    last_call_timeout: float = 25.0

    # Akista sinir daha genis: cevabin TAMAMI bu sure icinde
    # akiyor, tek bir cagri gibi olculemez.
    stream_timeout: float = 60.0

    # 429 veya zaman asimi alan model bir sure atlanir. Olmasa
    # her istek once tukenmis modele gidip hata yiyecek, sonra
    # digerine gececekti: her mesaja bosuna bir tur gecikme.
    cooldown_seconds: float = 60.0

    # --- DONGU SINIRLARI ---
    #
    # Model -> arac -> model dongusunun ust siniri. Pratikte
    # 1-2 tur yetiyor. Sinir sonsuz donguye karsi: model ayni
    # araci tekrar tekrar cagirmaya kalkarsa istek kesilir.
    max_tool_rounds: int = 4

    # Modele gonderilen son N mesaj. Hem token maliyeti hem de
    # gecmis buyudukce modelin ilk mesajlara takilip kalmasi
    # icin.
    max_history_messages: int = 16

    # Bir cevapta kart olarak donebilecek en fazla kayit.
    max_cards: int = 8

    # --- URETIM ---
    temperature: float = 0.7
    max_output_tokens: int | None = None

    # Kartlarin kimlik alani. Hem tekrari ayiklamak hem de
    # modelin [SHOW: ...] secimini eslestirmek icin gerekli.
    card_id_field: str = "id"

    def __post_init__(self):

        if not self.model_chain:
            raise ConfigurationError(
                "model_chain bos olamaz: denenecek model yok."
            )

        for name, value in (
            ("call_timeout", self.call_timeout),
            ("last_call_timeout", self.last_call_timeout),
            ("stream_timeout", self.stream_timeout),
        ):
            if value <= 0:
                raise ConfigurationError(
                    f"{name} pozitif olmali (verilen: {value})."
                )

            if value < MIN_CALL_TIMEOUT:

                logger.warning(
                    "%s=%ss saglayicinin izin verdiginden kisa; "
                    "%ss kullaniliyor.",
                    name,
                    value,
                    MIN_CALL_TIMEOUT,
                )

                # frozen dataclass: duzeltmenin tek yolu bu.
                # Alternatif olan "hata firlat" secilmedi cunku
                # mevcut .env dosyalarindaki 8 gibi degerler
                # sohbeti komple durdururdu.
                object.__setattr__(self, name, MIN_CALL_TIMEOUT)

        if self.cooldown_seconds < 0:
            raise ConfigurationError(
                "cooldown_seconds negatif olamaz."
            )

        if self.max_tool_rounds < 1:
            raise ConfigurationError(
                "max_tool_rounds en az 1 olmali."
            )

        if self.max_history_messages < 1:
            raise ConfigurationError(
                "max_history_messages en az 1 olmali."
            )

        if self.max_cards < 0:
            raise ConfigurationError(
                "max_cards negatif olamaz."
            )

        if not self.card_id_field:
            raise ConfigurationError(
                "card_id_field bos olamaz."
            )

    def chain(self) -> list[str]:
        """Denenecek modeller: tercih edilen once, sonra digerleri."""

        models = list(self.model_chain)

        preferred = (self.preferred_model or "").strip()

        if preferred:

            if preferred in models:
                models.remove(preferred)

            models.insert(0, preferred)

        return models

    def resolve_api_key(self) -> str:
        """
        Anahtari dondurur; yoksa ConfigurationError.

        Anahtar env'den de okunabiliyor cunku uygulamalarin
        buyuk kismi onu zaten oradan besliyor. Acikca verilen
        deger her zaman kazanir.
        """

        key = (
            self.api_key
            or os.getenv("GEMINI_API_KEY", "")
            or os.getenv("GOOGLE_API_KEY", "")
        ).strip()

        if not key:
            raise ConfigurationError(
                "API anahtari yok: AssistantConfig(api_key=...) "
                "ver veya GEMINI_API_KEY tanimla."
            )

        return key

    def with_overrides(self, **changes) -> "AssistantConfig":
        return replace(self, **changes)

    @classmethod
    def from_env(
        cls,
        prefix: str = "TOOLCHAT",
        **overrides,
    ) -> "AssistantConfig":
        """
        Ayarlari ortam degiskenlerinden okur.

        Okunanlar (PREFIX varsayilani TOOLCHAT):

            {PREFIX}_MODEL              tercih edilen model
            {PREFIX}_MODEL_CHAIN        virgullu liste
            {PREFIX}_CALL_TIMEOUT       saniye (en az 10)
            {PREFIX}_LAST_CALL_TIMEOUT  saniye
            {PREFIX}_STREAM_TIMEOUT     saniye
            {PREFIX}_COOLDOWN           saniye
            {PREFIX}_TEMPERATURE
            {PREFIX}_MAX_TOOL_ROUNDS
            {PREFIX}_MAX_HISTORY
            {PREFIX}_MAX_CARDS
            {PREFIX}_API_KEY            (yoksa GEMINI_API_KEY)

        overrides ile verilenler env'i EZER: kod icindeki acik
        karar, ortamdan gelen varsayilandan onceliklidir.
        """

        def key(name: str) -> str:
            return f"{prefix}_{name}" if prefix else name

        raw_chain = os.getenv(key("MODEL_CHAIN"), "").strip()

        chain = tuple(
            part.strip()
            for part in raw_chain.split(",")
            if part.strip()
        ) or DEFAULT_MODEL_CHAIN

        base = dict(
            model_chain=chain,
            preferred_model=(
                os.getenv(key("MODEL"), "").strip() or None
            ),
            api_key=(
                os.getenv(key("API_KEY"), "").strip() or None
            ),
            call_timeout=_env_number(
                key("CALL_TIMEOUT"), MIN_CALL_TIMEOUT
            ),
            last_call_timeout=_env_number(
                key("LAST_CALL_TIMEOUT"), 25.0
            ),
            stream_timeout=_env_number(
                key("STREAM_TIMEOUT"), 60.0
            ),
            cooldown_seconds=_env_number(key("COOLDOWN"), 60.0),
            temperature=_env_number(key("TEMPERATURE"), 0.7),
            max_tool_rounds=int(
                _env_number(key("MAX_TOOL_ROUNDS"), 4)
            ),
            max_history_messages=int(
                _env_number(key("MAX_HISTORY"), 16)
            ),
            max_cards=int(_env_number(key("MAX_CARDS"), 8)),
        )

        base.update(overrides)

        return cls(**base)
