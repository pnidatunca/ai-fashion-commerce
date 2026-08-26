"""
Sohbet gecmisi: normalizasyon ve Gemini formatina cevrim.

DURUM SUNUCUDA TUTULMUYOR
Gecmisi cagiran taraf gonderiyor, modul saklamiyor. Yeni tablo,
oturum kimligi, temizlik isi yok. Bedeli: her istek gecmisi
tekrar tasiyor — bu yuzden max_history_messages ile kirpiliyor.

NEDEN NORMALIZASYON KATMANI
Cagiran taraf gecmisi kendi tipiyle tutuyor: FastAPI'de bir
pydantic modeli, bir CLI'da duz sozluk, bir testte dataclass.
Modul bunlarin hicbirini bilmek zorunda degil; role/content
okunabiliyorsa yeter. Boylece paket pydantic'e bagimli olmadan
pydantic kullanan projelerde calisiyor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from google.genai import types

logger = logging.getLogger(__name__)

USER = "user"
ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    role: str
    content: str


def _read(source: Any, field: str) -> Any:
    """Sozluk mu nesne mi bilmeden alan okur."""

    if isinstance(source, dict):
        return source.get(field)

    return getattr(source, field, None)


def normalize(messages: Iterable[Any]) -> list[Message]:
    """
    Herhangi bir gecmis temsilini Message listesine cevirir.

    Atlananlar ve nedenleri:

    - BOS icerik: modele gonderilecek bir sey yok, contents
      icinde bos bir Part API hatasina yol acabiliyor.
    - "system" rolu: sistem talimati AYRI bir alan
      (system_instruction). Gecmise sistem mesaji karistirmak
      talimatin agirligini dusurur; sessizce yutmak yerine
      uyari birakiyoruz ki cagiran yanlis yerde aradigini
      gorsun.
    """

    normalized: list[Message] = []

    for item in messages or ():

        raw_role = str(_read(item, "role") or USER).strip().lower()

        content = str(_read(item, "content") or "").strip()

        if not content:
            continue

        if raw_role == "system":
            logger.warning(
                "Gecmisteki 'system' mesaji atlandi; sistem "
                "talimati system_prompt ile verilir."
            )
            continue

        # "model" Gemini'nin, "assistant" yaygin sozlesmenin
        # adi. Ikisini de kabul ediyoruz.
        role = (
            ASSISTANT
            if raw_role in (ASSISTANT, "model", "bot", "ai")
            else USER
        )

        normalized.append(Message(role=role, content=content))

    return normalized


def to_contents(
    messages: Sequence[Message],
    max_history: int,
) -> list[types.Content]:
    """
    Son max_history mesaji Gemini contents'ine cevirir.

    ROL ADLARI: Gemini "user"/"model" diyor, disariya
    "user"/"assistant" konusuyoruz (yaygin sozlesme). Cevrim
    burada, tek yerde.

    BASTAKI ASISTAN MESAJLARI ATILIYOR: kirpma penceresi
    rastgele bir yerden kesiyor ve pencere bir asistan
    cevabiyla baslayabiliyor. Modele "once ben konusmusum, ne
    dedigimi hatirlamiyorum" demek bir sey kazandirmiyor;
    ustelik bazi surumler ilk mesajin kullanicidan gelmesini
    bekliyor.
    """

    window = list(messages[-max_history:]) if max_history else []

    while window and window[0].role == ASSISTANT:
        window.pop(0)

    return [
        types.Content(
            role="model" if message.role == ASSISTANT else "user",
            parts=[types.Part(text=message.content)],
        )
        for message in window
    ]


def last_user_message(messages: Sequence[Message]) -> Message | None:
    """
    Son KULLANICI mesaji.

    On arama (prefetch) buna bakiyor: aranacak sey her zaman
    kullanicinin son soyledigi seydir.
    """

    for message in reversed(messages):
        if message.role == USER:
            return message

    return None
