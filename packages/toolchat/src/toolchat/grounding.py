"""
Dayanak denetimi: model, arac sonucunda GECMEYEN bir ad yazdi mi?

NEDEN VAR
Kartlar her zaman gercek: yalnizca arac sonucundan uretiliyorlar
ve modelin uydurdugu bir kimlik kart olarak cikmiyor. Ama
DUZYAZI oyle degil. Olculdu: yedek modele dusuldugunde asistan
"Koton ve Trendyol sandalet modellerini listeledim" yazdi —
katalogda o markalardan SIFIR kayit var (SQL ile sayildi).

NEDEN CEVABI DUZELTMIYORUZ
Metni otomatik kirpmak/yeniden yazmak daha bete goturur:
cumlenin ortasindan bir ad silinince anlam bozulur ve kullanici
neden bozuk cumle gordugunu anlayamaz. Burada yapilan is TESPIT
VE KAYIT — sorun sessiz kalmasin, loglardan gorulebilsin.

IKI KATMAN
1. DENYLIST: katalogda olmadigi DOGRULANMIS adlar. Bicimden
   bagimsiz calisir, tam olarak gorulen hatayi hedefler.
2. KALIN YAZIM: sistem talimati marka adlarini **kalin** yazmayi
   soyluyorsa denetim oradan da tutunabilir. Model kalin
   kullanmazsa bu katman sessiz kalir; yani guvence degil,
   gozlem araci.

BILINEN YANLIS POZITIF
Model "LC Waikiki bizde yok" gibi DOGRU bir cumle yazdiginda da
ad metinde gectigi icin isaretlenir. Olumsuzlama cozumlemesi
eklemedik: bu bir log uyarisi, kullaniciya gitmiyor ve yanlis
pozitifin bedeli yalnizca gurultu. Yanlis NEGATIF (gercek
uydurmayi kacirmak) daha pahali olurdu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

_BOLD_PATTERN = re.compile(r"\*\*([^*]{2,60})\*\*")


@dataclass(frozen=True)
class GroundingPolicy:
    """
    Denetim ayarlari.

    fields: kart sozlugunun hangi alanlari "gercek" kabul
        edilen metni tasiyor (marka, baslik, cevirisi...).
    denylist: veri kumesinde OLMADIGI dogrulanmis adlar.
    bold: **kalin** yazilmis adlar da denetlensin mi.
    """

    fields: tuple[str, ...] = ("brand", "title")
    denylist: tuple[str, ...] = ()
    bold: bool = True

    def haystack(self, cards: Sequence[Mapping[str, Any]]) -> str:
        """Arac sonucundaki butun metin, tek bir kucuk-harf yigin."""

        parts: list[str] = []

        for card in cards or ():
            for name in self.fields:
                value = card.get(name) if isinstance(card, Mapping) else None
                if value:
                    parts.append(str(value))

        return " ".join(parts).casefold()

    def audit(
        self,
        reply: str,
        cards: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        """Cevapta gecen ama arac sonucunda GECMEYEN adlar."""

        if not reply:
            return []

        haystack = self.haystack(cards)

        lowered = reply.casefold()

        found: list[str] = []

        for absent in self.denylist:

            needle = absent.casefold()

            if needle in lowered and needle not in haystack:
                found.append(absent)

        if self.bold:

            for name in _BOLD_PATTERN.findall(reply):

                cleaned = name.strip().casefold()

                if not cleaned:
                    continue

                # Ilk kelime yeter: "KuaiLu Store" veri
                # kumesinde "KuaiLu" olarak gecebiliyor.
                if cleaned.split()[0] not in haystack:
                    found.append(name.strip())

        # Ayni ad iki katmandan da gelebilir (hem denylist'te
        # hem kalin yazilmis). Log satirinda tekrar gorunmesin.
        seen: set[str] = set()

        deduped: list[str] = []

        for name in found:

            key = name.casefold()

            if key in seen:
                continue

            seen.add(key)
            deduped.append(name)

        return deduped


# Denetimi hic istemeyen cagiran taraf icin: hicbir sey
# isaretlemeyen, maliyeti sifir politika.
NO_GROUNDING = GroundingPolicy(fields=(), denylist=(), bold=False)
