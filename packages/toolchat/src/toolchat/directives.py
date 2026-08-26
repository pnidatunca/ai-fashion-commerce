"""
[SHOW: ...] direktifi — modelin hangi kartlarin gosterilecegini
soylemesi.

PROBLEM
Arac (orn. bir arama motoru) HER ZAMAN bir sey donduruyor.
Alakasiz bir sorguda katalogdan "en yakin" kayitlar geliyor;
hepsi alakasiz. Model bunu goruyor ve dogru davranip
"bulamadim" yaziyor. Ama arac sonucundaki kayitlar kart olarak
ekranda kaliyordu: metin "bulamadim" derken altinda alti urun
duruyor.

NEDEN BENZERLIK ESIGI DEGIL
Ilk akla gelen cozum "skor < X ise atla" idi. Olculdu ve
CALISMIYOR — dagilimlar cakisiyor:

    gecerli sorgular (n=15): 0.480 ... 0.665
    sacma sorgular   (n=10): 0.425 ... 0.529

0.53 esigi dort gercek aramayi oldururdu, 0.48 esigi
sacmalarin sekizini geciriyordu. Ayiran tek bir sayi yok.

COZUM
Alakayi en iyi bilen taraf MODEL: zaten "bulamadim" yaziyor. O
karari makine-okunur biciminde de istiyoruz. Cevabin sonuna

    [SHOW: B0B28SWXWP, B07HNTS427]

yaziyor; bu satir kullaniciya gitmiyor, burada ayikliyoruz. Ek
API cagrisi YOK.

GUVENLI VARSAYILAN
Direktif yoksa (model unuttu) None donuyor ve cagiran taraf
butun kayitlari gosteriyor. Bozulma yonu "fazla kart goster",
"hicbir sey gostermeme" degil.
"""

from __future__ import annotations

import re

# "hicbiri" anlamina gelen degerler. Turkce ve Ingilizce, hem
# diakritikli hem diakritiksiz: model ikisini de yaziyor.
NONE_WORDS: tuple[str, ...] = (
    "none",
    "yok",
    "hicbiri",
    "hiçbiri",
    "empty",
    "-",
)


class DirectiveParser:
    """
    Bir etikete (varsayilan SHOW) gore direktif ayiklar.

    Etiket degistirilebilir cunku bu mekanizma kartlara ozel
    degil: bir baska proje [CITE: ...] ile kaynak, [TAG: ...]
    ile etiket secmek isteyebilir.
    """

    def __init__(
        self,
        tag: str = "SHOW",
        none_words: tuple[str, ...] = NONE_WORDS,
    ):
        if not tag or not tag.strip():
            raise ValueError("Direktif etiketi bos olamaz.")

        self.tag = tag.strip()

        self.none_words = tuple(
            word.casefold() for word in none_words
        )

        self._pattern = re.compile(
            r"\[\s*" + re.escape(self.tag) + r"\s*:\s*([^\]]*)\]",
            re.IGNORECASE,
        )

    def split(self, reply: str) -> tuple[str, list[str] | None]:
        """
        Cevabi (kullaniciya gidecek metin, secilen kimlikler)
        olarak ayirir.

        Ikinci deger None ise direktif YOKTU -> cagiran taraf
        butun kayitlari gostersin. Bos liste ise model bilincli
        olarak "hicbiri" dedi.

        DIREKTIF METNIN SONUNDA ARANMIYOR, HER YERDE ARANIYOR.
        Ilk surum satir sonuna sabitliydi ve model direktiften
        sonra bir cumle daha yazdiginda ayiklama sessizce
        basarisiz oluyordu: kullanici ham [SHOW: ...] metnini
        goruyordu. Simdi butun gecisler siliniyor, kimlikler
        SONUNCUSUNDAN aliniyor (model kendini duzeltmisse son
        soyledigi gecerlidir).
        """

        if not reply:
            return "", None

        matches = list(self._pattern.finditer(reply))

        if not matches:
            return reply.strip(), None

        text = self._pattern.sub("", reply)

        # Direktif satir icinden silinince arkasinda cift
        # bosluk / bos satir birakiyor.
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        return text, self.parse_ids(matches[-1].group(1))

    def parse_ids(self, raw: str) -> list[str]:
        """Direktif govdesindeki kimlik listesini cozer."""

        cleaned = (raw or "").strip()

        if not cleaned or cleaned.casefold() in self.none_words:
            return []

        return [
            part.strip()
            for part in cleaned.replace(";", ",").split(",")
            if part.strip()
        ]

    def stream_filter(self) -> "DirectiveStreamFilter":
        return DirectiveStreamFilter(self)


class DirectiveStreamFilter:
    """
    Akis halinde gelen metinden direktifi ayiklar.

    NEDEN GEREKLI
    Akista metni parca parca yayinliyoruz, ama direktif cevabin
    SONUNDA. Ham parcalari oldugu gibi gecirirsek kullanici
    ekranda "[SHOW: B0B2..." yazisini gorur.

    NASIL
    Bir "[" gorulduginde o noktadan sonrasi BEKLETILIYOR:
    direktif olabilir. Kapanis "]" gelince direktifse atiliyor;
    degilse (orn. "[not: ...]") bekletilen metin aynen
    yayinlaniyor. Yani gecikme yalnizca kose parantezli bir
    parcanin uzunlugu kadar, cevabin tamami kadar degil.
    """

    def __init__(self, parser: DirectiveParser):
        self._parser = parser
        self._prefix = f"[{parser.tag}:".casefold()
        self._pending = ""

    def _could_be_directive(self, chunk: str) -> bool:
        """
        chunk bir "[" ile basliyor. Bizim direktifin BASLANGICI
        olabilir mi?

        Iki durum: chunk henuz kisa (etiketin bir parcasi olmus
        olabilir) veya chunk yeterince uzun (etiketle
        basliyorsa direktiftir).
        """

        # "[ SHOW:" gibi bosluklu yazimi da tolere et.
        candidate = ("[" + chunk[1:].lstrip()).casefold()

        if len(candidate) < len(self._prefix):
            return self._prefix.startswith(candidate)

        return candidate.startswith(self._prefix)

    def feed(self, delta: str) -> str:
        """Yeni parcayi alir, YAYINLANABILIR metni dondurur."""

        if not delta:
            return ""

        self._pending += delta

        out: list[str] = []

        while self._pending:

            index = self._pending.find("[")

            if index == -1:
                out.append(self._pending)
                self._pending = ""
                break

            out.append(self._pending[:index])

            rest = self._pending[index:]

            if not self._could_be_directive(rest):
                # Bizim direktif degil: "[" karakterini
                # yayinla ve aramaya devam et.
                out.append(rest[0])
                self._pending = rest[1:]
                continue

            if "]" in rest:
                # Tamamlanmis direktif: yayinlanmaz, atilir.
                self._pending = rest[rest.index("]") + 1:]
                continue

            # Henuz kapanmadi: kalanini beklet.
            self._pending = rest
            break

        return "".join(out)

    def close(self) -> str:
        """
        Akis bitti: bekleyen metinden direktifi ayiklayip
        kalani dondurur.

        Direktif hic kapanmadiysa (model yarida kesildi)
        yarim "[SHOW: ..." metni kullaniciya gitmesin diye
        atiliyor.
        """

        pending, self._pending = self._pending, ""

        if not pending:
            return ""

        text, ids = self._parser.split(pending)

        if ids is None and pending.lstrip().startswith("["):
            # Yarim kalmis direktif; kullaniciya gostermiyoruz.
            return ""

        return text
