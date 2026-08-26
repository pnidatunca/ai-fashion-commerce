"""
Model yonlendirme: kota ve zaman asiminda yedek modele gecis.

PROBLEM
Ucretsiz katmanda kota MODEL BASINA ayri veriliyor ve
gemini-3.5-flash icin dakikada 5 istek. Her sohbet turu 1-2
istek harciyor. Tek modele bagli kalmak, ucuncu mesajda
sohbetin komple durmasi demek — olculdu, yasandi.

Ikinci problem gecikme: ayni onemsiz istek ("tek kelimeyle
merhaba de") bes kez ust uste gonderildiginde

    1.27s | 105.52s | 13.37s | 2.61s | 0.66s

dondu. Ayni model, ayni prompt. Yani gecikme uretimde degil,
katmanin KUYRUGUNDA. Bir istek kotu talihe denk gelirse iki
dakika bekliyor.

COZUM
Sirali bir model listesi. 429 veya zaman asimi alan model
BIRAKILIP siradaki denenir; kotalar ayri oldugu icin bu,
kullanilabilir kapasiteyi model sayisi kadar katliyor.

SOGUMA LISTESI
Hata alan model bir sure atlanir. Olmasa her istek once
tukenmis modele gidip hata yiyecek, sonra digerine gececekti:
her mesaja bosuna bir tur gecikme. Soguma surec icinde
tutuluyor; sunucu yeniden baslarsa sifirlanir, sorun degil, en
fazla bir kez fazladan hata alinir.

SDK'NIN KENDI YENIDEN DENEMESI KISILIYOR
Varsayilan haliyle google-genai, 429 alinca ustel bekleyerek
defalarca tekrar deniyor. Bizim yedek zincirimiz ancak SDK pes
ettikten SONRA devreye girebiliyordu: olculdu, ilk mesaj 143
saniye surdu. Tukenmis bir modeli beklemenin anlami yok —
yanindaki modelin kotasi bos.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Iterator, Sequence

from google import genai
from google.genai import types

from .config import AssistantConfig
from .errors import (
    ModelTimeout,
    QuotaExceeded,
    is_quota_error,
    is_timeout_error,
    retry_seconds,
)

logger = logging.getLogger(__name__)


class ModelRouter:
    """
    Zincirdeki modelleri sirayla deneyen cagri katmani.

    NEDEN SINIF, NEDEN MODUL SEVIYESI SOZLUK DEGIL
    Ilk surumde soguma bilgisi modul seviyesinde bir sozlukteydi.
    Iki sonucu vardi: (1) ayni surecte iki farkli asistan
    birbirinin sogumasini eziyordu, (2) testte durum sizintisi
    oluyordu. Simdi soguma bu nesnenin icinde ve kilitli.
    """

    def __init__(
        self,
        config: AssistantConfig,
        client: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._config = config
        self._clock = clock
        self._client = client
        self._lock = threading.Lock()
        self._cooldown: dict[str, float] = {}

    # -----------------------------------------------------
    # ISTEMCI
    # -----------------------------------------------------

    @property
    def client(self) -> Any:
        """
        Istemci ILK KULLANIMDA kuruluyor.

        Boylece API anahtari olmayan bir ortamda modulu import
        etmek ve arac tanimlarini test etmek mumkun; hata ancak
        gercekten cagri yapilinca cikiyor.
        """

        if self._client is None:

            self._client = genai.Client(
                api_key=self._config.resolve_api_key(),
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(
                        attempts=1,
                        http_status_codes=[],
                    ),
                    timeout=int(self._config.call_timeout * 1000),
                ),
            )

        return self._client

    # -----------------------------------------------------
    # SOGUMA
    # -----------------------------------------------------

    def _cool(self, model: str, seconds: float) -> None:

        with self._lock:
            self._cooldown[model] = self._clock() + seconds

    def _ready(self) -> list[str]:
        """Sogumada olmayanlar once; hepsi sogumadaysa yine hepsi."""

        now = self._clock()

        chain = self._config.chain()

        with self._lock:
            ready = [
                model
                for model in chain
                if self._cooldown.get(model, 0.0) <= now
            ]

        # Hepsi sogumadaysa yine deneriz: soguma bizim
        # TAHMINIMIZ, sunucunun gercegi degil.
        return ready or chain

    def candidates(self, chosen: str | None = None) -> list[str]:
        """
        Bu cagride denenecek modeller.

        chosen: istegin onceki cagrisini karsilayan model. Basa
        aliniyor ama TEK aday yapilmiyor: kuyruk sikismasi
        istegin ortasinda da olabiliyor ve tek adayla kalmak
        "cevap yok" demek.
        """

        models = self._ready()

        if chosen:
            models = [chosen] + [
                model for model in models if model != chosen
            ]

        return models

    # -----------------------------------------------------
    # CAGRI
    # -----------------------------------------------------

    def _attempt_config(
        self,
        gen_config: types.GenerateContentConfig,
        timeout: float,
    ) -> types.GenerateContentConfig:
        """
        Zaman siniri CAGRI BASINA veriliyor: istemcide sabit
        tutulsa son denemeye ayri bir pay taniyamazdik.
        """

        return gen_config.model_copy(
            update={
                "http_options": types.HttpOptions(
                    retry_options=types.HttpRetryOptions(
                        attempts=1,
                        http_status_codes=[],
                    ),
                    timeout=int(timeout * 1000),
                )
            }
        )

    def _timeout_for(self, index: int, total: int) -> float:
        """
        Kademeli sinir.

        Ilk surumde tek bir deger vardi ve su hatayi
        uretiyordu: ikinci model kuyrukta takildi, 18 saniye
        beklendi, sonra ucuncu model 5 saniyede cevap verdi.
        Kullanicinin gordugu sure 23 saniye — 18'i tamamen bosa.

        Mantik: DENEYECEK BASKA MODEL VARSA cabuk vazgec. SON
        modeldeysen sabirli ol.
        """

        if index == total - 1:
            return self._config.last_call_timeout

        return self._config.call_timeout

    def generate(
        self,
        contents: Sequence[Any],
        gen_config: types.GenerateContentConfig,
        state: dict,
    ) -> Any:
        """
        Tek bir uretim cagrisi — gerekirse yedek modellerle.

        state: tek istek boyunca tasinan sozluk. Ilk basarili
        model buraya yaziliyor ve ayni istegin sonraki cagrilari
        dogrudan onu kullaniyor; arac turundan sonra bastan
        denemek tukenmis modele bosuna gitmek olurdu.
        """

        models = self.candidates(state.get("model"))

        attempts = state.setdefault("attempts", [])

        last_retry_after: int | None = None

        timed_out: list[str] = []

        for index, model in enumerate(models):

            limit = self._timeout_for(index, len(models))

            started = self._clock()

            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=list(contents),
                    config=self._attempt_config(gen_config, limit),
                )

                state["model"] = model

                attempts.append(
                    {
                        "model": model,
                        "seconds": round(self._clock() - started, 2),
                        "outcome": "ok",
                    }
                )

                return response

            except Exception as error:

                outcome = self._handle_error(
                    error=error,
                    model=model,
                    limit=limit,
                    is_last=index == len(models) - 1,
                    state=state,
                    timed_out=timed_out,
                )

                attempts.append(
                    {
                        "model": model,
                        "seconds": round(self._clock() - started, 2),
                        "outcome": outcome,
                    }
                )

                if outcome == "quota":
                    last_retry_after = (
                        retry_seconds(error) or last_retry_after
                    )

        self._raise_exhausted(timed_out, last_retry_after, models)

    def stream(
        self,
        contents: Sequence[Any],
        gen_config: types.GenerateContentConfig,
        state: dict,
    ) -> Iterator[Any]:
        """
        Akisli uretim.

        YEDEGE GECIS YALNIZCA ILK PARCADAN ONCE
        Bir parca yayinlandiktan sonra model degistirmek,
        kullanicinin ekranindaki yarim cumlenin ustune baska bir
        modelin cumlesini yazmak olurdu. Bu yuzden ilk parca
        gelene kadar yedege gecebiliyoruz; sonrasinda hata
        cagirana gidiyor.

        Zaman siniri burada stream_timeout: cevabin TAMAMI bu
        sure icinde akiyor, tek bir cagri gibi olculemez.
        """

        models = self.candidates(state.get("model"))

        attempts = state.setdefault("attempts", [])

        last_retry_after: int | None = None

        timed_out: list[str] = []

        for index, model in enumerate(models):

            started = self._clock()

            limit = self._config.stream_timeout

            try:
                stream = self.client.models.generate_content_stream(
                    model=model,
                    contents=list(contents),
                    config=self._attempt_config(gen_config, limit),
                )

                iterator = iter(stream)

                # Ilk parca burada cekiliyor: baglanti/kota
                # hatalari bu satirda ciksin ki hata yedege
                # gecmemizi hala mumkun kilsin.
                first = next(iterator, None)

            except Exception as error:

                outcome = self._handle_error(
                    error=error,
                    model=model,
                    limit=limit,
                    is_last=index == len(models) - 1,
                    state=state,
                    timed_out=timed_out,
                )

                attempts.append(
                    {
                        "model": model,
                        "seconds": round(self._clock() - started, 2),
                        "outcome": outcome,
                    }
                )

                if outcome == "quota":
                    last_retry_after = (
                        retry_seconds(error) or last_retry_after
                    )

                continue

            state["model"] = model

            attempts.append(
                {
                    "model": model,
                    "seconds": round(self._clock() - started, 2),
                    "outcome": "ok",
                }
            )

            return self._resume(first, iterator)

        self._raise_exhausted(timed_out, last_retry_after, models)

    @staticmethod
    def _resume(first: Any, iterator: Iterator[Any]) -> Iterator[Any]:
        """Cekilmis ilk parcayi geri koyup akisi surdurur."""

        if first is not None:
            yield first

        yield from iterator

    # -----------------------------------------------------
    # HATA YONETIMI
    # -----------------------------------------------------

    def _handle_error(
        self,
        error: Exception,
        model: str,
        limit: float,
        is_last: bool,
        state: dict,
        timed_out: list[str],
    ) -> str:
        """
        Hatayi siniflandirir ve gerekiyorsa soguma yazar.

        Doner: "timeout" | "quota". Baska hata tiplerinde
        HATAYI YENIDEN FIRLATIR: bilmedigimiz bir sorunu yedek
        modelle maskelemek, gercek arizayi gizlemek olur.
        """

        if is_timeout_error(error):

            timed_out.append(model)

            # Kuyrukta bekleyen model bir sure atlanacak: ayni
            # cagrida tekrar denemek ayni kuyruga girmek olur.
            self._cool(model, self._config.cooldown_seconds)

            logger.warning(
                "%s %ss icinde cevap vermedi (%s).",
                model,
                limit,
                "son deneme" if is_last else "siradaki modele geciliyor",
            )

            state.pop("model", None)

            return "timeout"

        if not is_quota_error(error):
            raise error

        wait = retry_seconds(error) or self._config.cooldown_seconds

        self._cool(model, wait)

        logger.warning(
            "%s kotasi doldu, siradaki modele geciliyor "
            "(soguma %ss).",
            model,
            wait,
        )

        # Istegin ortasinda model degisiyorsa secimi de birak:
        # bir sonraki cagri yeniden secsin.
        state.pop("model", None)

        return "quota"

    def _raise_exhausted(
        self,
        timed_out: list[str],
        last_retry_after: int | None,
        models: Sequence[str],
    ) -> None:
        """
        Butun modeller tukendi. HANGI hata olduguna gore ayri
        tip firlatiliyor.

        Hepsi zaman asimina ugradiysa bu bir kota sorunu DEGIL:
        servis yavas. Kullaniciya "kotan doldu" demek yanlis
        teshis olurdu ve yapacagi sey de degisirdi (beklemek
        yerine tekrar denemek).
        """

        if timed_out and last_retry_after is None:
            raise ModelTimeout(
                "Hicbir model zamaninda cevap vermedi "
                f"({self._config.call_timeout}s sinirla "
                f"denenenler, sonuncusu "
                f"{self._config.last_call_timeout}s): "
                + ", ".join(timed_out),
                tried=tuple(timed_out),
            )

        raise QuotaExceeded(
            retry_after=last_retry_after,
            tried=tuple(models),
        )
