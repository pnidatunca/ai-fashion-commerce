"""
Arac tanimlari (function calling) ve arac calistirma.

NEDEN ARAC CAGIRMA, NEDEN "VERIYI PROMPT'A DOLDUR" DEGIL
Iki alternatif var:

  1. Butun veri kumesini sistem promptuna koy, model icinden
     secsin.
  2. Modele SORGULAMA YETKISI ver, ne arayacagina kendisi
     karar versin.

Birincisi her mesajda on binlerce token demek ve veri buyudugu
anda coker. Ustelik model kayit UYDURABILIR — promptta gordugu
kelimeleri birlestirip var olmayan bir sey tarif etmesi klasik
bir halusinasyon bicimi.

Ikincisi secildi. Model araci cagirir, cagiran taraf GERCEK
sonucu geri verir, model yalnizca KENDISINE VERILEN kayitlar
hakkinda konusur. Ekranda gorunen kartlar da ayni arac
sonuclaridir — yani gorulen kayit, modelin gordugu kaydin ta
kendisi.

NEDEN JSON SCHEMA (DUZ SOZLUK), NEDEN types.Schema DEGIL
Arac tanimlayan taraf uygulama kodudur; onu google.genai
tiplerini import etmeye zorlamak modulu sizdirmak olur. Duz
sozluk verilir, cevrimi burada yapiyoruz. Yarin baska bir
saglayici eklenirse cevrim degisir, uygulama kodu degismez.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from google.genai import types

logger = logging.getLogger(__name__)

# "3.000", "1.250.000" — binlik ayiricili yazim.
_THOUSANDS_PATTERN = re.compile(r"\d{1,3}(?:\.\d{3})+")


# =========================================================
# ARAC SOZLESMESI
# =========================================================

@dataclass
class ToolContext:
    """
    Arac uygulamasina gecen baglam.

    request: cagiran tarafin kendi nesnesi (veritabani
        oturumu, oturum acmis kullanici, doviz kuru... modul
        icine bakmaz, oldugu gibi tasir).
    messages: normalize edilmis sohbet gecmisi.
    state: tek bir istek boyunca yasayan sozluk. Araclar
        birbirine not birakabilir (orn. "bu turda zaten
        aradim").
    """

    request: Any = None
    messages: Sequence[Any] = ()
    state: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    """
    Bir arac cagrisinin sonucu.

    payload: MODELE gidecek sozluk. Kompakt tutulmali; modelin
        okumayacagi alanlar yalnizca token maliyeti.
    cards: CAGIRANA gidecek zengin kayitlar (arayuz kartlari).
        Modele gitmez, bu yuzden resim adresi gibi alanlari
        rahatca tasiyabilir.

    NEDEN IKISI AYRI
    Modelin gordugu ile ekranda gorunenin AYNI KAYNAKTAN
    gelmesi bu modulun temel guvencesi; ama ayni SEKILDE olmasi
    gerekmiyor. Model kisa temsili okur, arayuz zengin temsili
    gosterir.
    """

    payload: Mapping[str, Any]
    cards: list[dict] = field(default_factory=list)

    @classmethod
    def coerce(cls, value: Any) -> "ToolResult":
        """
        Arac duz sozluk dondurduyse onu da kabul et.

        Kart uretmeyen araclar (bir hesaplama, bir kur
        sorgusu) ToolResult yazmak zorunda kalmasin.
        """

        if isinstance(value, ToolResult):
            return value

        if isinstance(value, Mapping):
            return cls(payload=dict(value))

        return cls(
            payload={
                "error": (
                    "Arac beklenmeyen bir deger dondurdu "
                    f"({type(value).__name__})."
                )
            }
        )


ToolHandler = Callable[[dict, ToolContext], Any]


@dataclass(frozen=True)
class ToolSpec:
    """
    Bir aracin tam tanimi: modelin okudugu aciklama + bizim
    calistirdigimiz fonksiyon.

    ACIKLAMA MODEL ICIN YAZILIR
    description ve parametre aciklamalari modelin OKUDUGU tek
    dokumantasyon. Ne zaman cagiracagini buradan ogreniyor;
    yani bu metinler kullanici icin degil MODEL icin yazilir.
    """

    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: ToolHandler

    def declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=json_schema_to_genai(self.parameters),
        )


class ToolRegistry:
    """Ad -> arac eslemesi ve SDK tanimlarinin uretimi."""

    def __init__(self, specs: Sequence[ToolSpec]):

        self._specs: dict[str, ToolSpec] = {}

        for spec in specs or ():

            if spec.name in self._specs:
                raise ValueError(
                    f"Ayni adli iki arac var: {spec.name}"
                )

            self._specs[spec.name] = spec

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    @property
    def names(self) -> list[str]:
        return list(self._specs)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def gemini_tools(self) -> list[types.Tool]:
        """SDK'nin bekledigi Tool listesi. Arac yoksa bos liste."""

        if not self._specs:
            return []

        return [
            types.Tool(
                function_declarations=[
                    spec.declaration()
                    for spec in self._specs.values()
                ]
            )
        ]

    def run(self, name: str, raw_args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        """
        Araci calistirir. HATA FIRLATMAZ.

        Arac patlarsa istegin tamami dusmemeli: modele hatayi
        soyleriz, o da kullaniciya makul bir cevap yazar. Sohbet
        bir arac hatasi yuzunden komple olmez.
        """

        spec = self.get(name)

        if spec is None:

            logger.warning("Bilinmeyen arac cagrildi: %s", name)

            return ToolResult(
                payload={
                    "error": (
                        f"'{name}' diye bir arac yok. Yalnizca "
                        f"su araclari kullan: "
                        f"{', '.join(self.names) or 'yok'}."
                    )
                }
            )

        args = coerce_args(spec.parameters, raw_args)

        try:
            return ToolResult.coerce(spec.handler(args, ctx))

        except Exception:

            logger.exception("Arac hatasi (%s)", name)

            return ToolResult(
                payload={
                    "error": (
                        "Arac cagrisi sirasinda teknik bir hata "
                        "oldu. Kullaniciya kisaca bunu soyle ve "
                        "tekrar denemesini iste."
                    )
                }
            )


# =========================================================
# JSON SCHEMA -> SDK SEMASI
# =========================================================

_TYPES = {
    "object": types.Type.OBJECT,
    "string": types.Type.STRING,
    "number": types.Type.NUMBER,
    "integer": types.Type.INTEGER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
}


def json_schema_to_genai(schema: Mapping[str, Any] | None) -> types.Schema:
    """
    Duz JSON Schema sozlugunu SDK semasina cevirir.

    Desteklenen alanlar bilincli olarak dar: type, description,
    properties, required, items, enum, nullable. Function
    calling'de pratikte kullanilan kume bu. Taninmayan bir alan
    sessizce atlaniyor — semayi zenginlestirmek modelin
    davranisini iyilestirmiyor, ama gecersiz bir sema istegi
    komple reddettiriyor.
    """

    if not schema:
        return types.Schema(type=types.Type.OBJECT, properties={})

    raw_type = str(schema.get("type", "object")).lower()

    # Alanlar tek seferde veriliyor, sonradan atanmiyor: SDK
    # tipleri pydantic modelleri ve dogrulama yalnizca yapici
    # cagrisinda calisiyor.
    fields: dict[str, Any] = {
        "type": _TYPES.get(raw_type, types.Type.OBJECT),
    }

    if schema.get("description"):
        fields["description"] = str(schema["description"])

    if schema.get("enum"):
        fields["enum"] = [str(value) for value in schema["enum"]]

    if schema.get("nullable"):
        fields["nullable"] = True

    properties = schema.get("properties")

    if properties:
        fields["properties"] = {
            key: json_schema_to_genai(value)
            for key, value in properties.items()
        }

    required = schema.get("required")

    if required:
        fields["required"] = [str(name) for name in required]

    items = schema.get("items")

    if items:
        fields["items"] = json_schema_to_genai(items)

    return types.Schema(**fields)


def coerce_args(
    schema: Mapping[str, Any] | None,
    raw_args: Mapping[str, Any] | None,
) -> dict:
    """
    Model argumanlarini semaya gore duzeltir.

    NEDEN GEREKLI
    Model semaya cogu zaman uyuyor, ama "cogu zaman" yeterli
    degil ve olculen sapmalar sunlar:

      - sayisal alani metin olarak yaziyor ("6", "3000 TL")
      - enum disinda deger uyduruyor ("unisex")
      - semada olmayan bir alan ekliyor ("color")

    Bunlarin hepsi arac uygulamasinda elle temizleniyordu; ayni
    donusturme kodu her aracta tekrar ediyordu. Burada bir kez
    yapiliyor:

      - taninmayan alanlar ATILIR (arac beklemedigi bir
        parametreyle karsilasmaz)
      - enum disi degerler ATILIR (yanlis filtre, filtre
        yoklugundan kotudur)
      - sayilar cevrilir, cevrilemezse atilir
      - minimum/maximum verilmisse deger araliga cekilir

    Zorunlu (required) bir alan eksikse DOKUNULMAZ: onun
    kararini arac verir, cunku eksigin ne anlama geldigini
    yalnizca o bilir.
    """

    args = dict(raw_args or {})

    properties = (schema or {}).get("properties") or {}

    if not properties:
        return args

    cleaned: dict[str, Any] = {}

    for key, value in args.items():

        rule = properties.get(key)

        if rule is None:
            logger.debug(
                "Semada olmayan arac argumani atlandi: %s", key
            )
            continue

        if value is None:
            continue

        coerced = _coerce_value(rule, value)

        if coerced is None:
            continue

        cleaned[key] = coerced

    return cleaned


def _coerce_value(rule: Mapping[str, Any], value: Any) -> Any:

    kind = str(rule.get("type", "string")).lower()

    enum = rule.get("enum")

    if kind in ("integer", "number"):

        number = _to_number(value)

        if number is None:
            return None

        minimum = rule.get("minimum")
        maximum = rule.get("maximum")

        if minimum is not None:
            number = max(float(minimum), number)

        if maximum is not None:
            number = min(float(maximum), number)

        return int(number) if kind == "integer" else float(number)

    if kind == "boolean":

        if isinstance(value, bool):
            return value

        text = str(value).strip().casefold()

        if text in ("true", "1", "yes", "evet"):
            return True

        if text in ("false", "0", "no", "hayir"):
            return False

        return None

    if kind == "array":

        if not isinstance(value, (list, tuple)):
            return None

        items = rule.get("items") or {}

        coerced = [
            _coerce_value(items, item)
            for item in value
        ]

        return [item for item in coerced if item is not None]

    text = str(value).strip()

    if not text:
        return None

    if enum and text not in enum:
        logger.debug(
            "Enum disi arac argumani atlandi: %r (izinli: %s)",
            text,
            enum,
        )
        return None

    return text


def _to_number(value: Any) -> float | None:
    """
    "3000", "3000 TL", "3.000" gibi degerleri sayiya cevirir.

    Ilk surumde bu is her aracta ayri ayri int()/try-except ile
    yapiliyordu ve "3000 TL" yazan model butceyi tamamen
    kaybettiriyordu.
    """

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text:
        return None

    # "3.000" / "1.250.000": Turkce binlik ayirici. float()
    # bunu 3.0 diye okur, yani butceyi bin kat kucultur —
    # once bu kalibi ayikliyoruz.
    if _THOUSANDS_PATTERN.fullmatch(text):
        text = text.replace(".", "")

    try:
        return float(text)
    except ValueError:
        pass

    # Sayi olmayan karakterleri atarak son bir deneme.
    digits = "".join(
        char for char in text if char.isdigit() or char in ".,-"
    )

    # Binlik ayirici olarak nokta kullanilmis olabilir
    # ("3.000"): virgul varsa nokta binliktir.
    if "," in digits and "." in digits:
        digits = digits.replace(".", "").replace(",", ".")
    else:
        digits = digits.replace(",", ".")

    try:
        return float(digits)
    except ValueError:
        return None
