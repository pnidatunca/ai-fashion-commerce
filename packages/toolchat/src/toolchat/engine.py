"""
Sohbet dongusu: mesaj -> (arac cagrilari) -> cevap.

Bu dosya modulun kalbi. Yaptigi is uc adimda anlatilabilir:

  1. Gecmisi modele ver, araclarini tanit.
  2. Model arac cagirirsa calistir, sonucu geri ver, tekrar sor.
  3. Model metin yazdiginda cevabi ve gosterilecek kartlari
     ayikla.

DONGUYU NEDEN BIZ SURUYORUZ
SDK'nin otomatik arac cagirma ozelligi var ve kapatildi
(automatic_function_calling disable). Sebep: hangi kayitlarin
donduguNU yakalamamiz gerekiyor — arayuz kartlari bundan
uretiliyor. Otomatik modda arac sonuclari SDK'nin icinde kalir
ve elimize yalnizca son metin geciyor.

DURUM SUNUCUDA TUTULMUYOR
Gecmisi cagiran taraf gonderiyor. Yeni tablo, oturum kimligi,
temizlik isi yok. Bedeli her istekte gecmisin tekrar tasinmasi;
karsiligi durumsuz ve yatay olceklenebilir bir uc.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping, Sequence

from google.genai import types

from .config import AssistantConfig
from .directives import DirectiveParser
from .grounding import GroundingPolicy
from .messages import Message, normalize, to_contents
from .router import ModelRouter
from .tools import ToolContext, ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)


# =========================================================
# SONUC TIPLERI
# =========================================================

@dataclass
class Usage:
    """
    Bu turda harcanan token ve cagri sayisi.

    NEDEN VAR
    Ilk surumde maliyet ancak saglayicinin panosundan
    gorulebiliyordu; hangi sohbetin pahali oldugu bilinmiyordu.
    Burada tur basina olculuyor, cagiran taraf loglayabilir.
    """

    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, response: Any) -> None:

        self.calls += 1

        meta = getattr(response, "usage_metadata", None)

        if meta is None:
            return

        self.prompt_tokens += getattr(meta, "prompt_token_count", 0) or 0
        self.output_tokens += (
            getattr(meta, "candidates_token_count", 0) or 0
        )
        self.total_tokens += getattr(meta, "total_token_count", 0) or 0

    def as_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
        }


@dataclass
class ChatTurn:
    """Bir sohbet turunun tam sonucu."""

    reply: str
    cards: list[dict] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)

    # Cevabi hangi model yazdi. Yedege dusuldugunde bunu
    # gormek, "sohbet neden bugun daha basit cevaplar veriyor"
    # sorusunun cevabi.
    model: str | None = None

    # Arac sonucunda gecmeyen, uydurulmus olabilecek adlar.
    # Bos olmasi beklenen normal durum.
    ungrounded: list[str] = field(default_factory=list)

    usage: Usage = field(default_factory=Usage)

    # Hangi modele kac saniye harcandi, sonuc ne oldu.
    attempts: list[dict] = field(default_factory=list)

    elapsed: float = 0.0

    def as_dict(self) -> dict:
        return {
            "reply": self.reply,
            "cards": self.cards,
            "tool_calls": self.tool_calls,
            "model": self.model,
            "ungrounded": self.ungrounded,
            "usage": self.usage.as_dict(),
            "attempts": self.attempts,
            "elapsed": self.elapsed,
        }


@dataclass(frozen=True)
class Prefetch:
    """
    On arama tarifi: hangi arac, hangi argumanlarla.

    Cagiran taraf yalnizca KARARI verir; araci calistirmak,
    hatayi yutmak ve sonucu modele anlatmak motorun isi.
    """

    tool: str
    args: dict
    note: str | None = None


@dataclass
class StreamEvent:
    """
    Akis olayi.

    type: "text"  -> yayinlanacak metin parcasi
          "tool"  -> arac cagrildi (arayuzde "araniyor" rozeti)
          "done"  -> tur bitti, turn dolu
    """

    type: str
    text: str = ""
    tool: str | None = None
    turn: "ChatTurn | None" = None


# =========================================================
# ON ARAMA — IKI LLM CAGRISINI BIRE INDIRMEK
# =========================================================
#
# ESKI AKIS (iki LLM cagrisi)
#   1. cagri : "arama yapayim mi, hangi terimle" -> arac cagrisi
#      arac  : sorgu calisir
#   2. cagri : sonucu okuyup cevabi yaz
#
# Bu, kuyruga IKI kez girmek demek. Ve o kuyruk olculdu: ayni
# onemsiz istek 0.66s ile 105s arasinda degisiyor. Iki cagriyi
# bire indirmek, kotu talihe yakalanma ihtimalini yariya
# indiriyor.
#
# SONUC MODELE NASIL VERILIYOR
# Ilk denemede contents'e uydurma bir FunctionCall +
# FunctionResponse ikilisi eklendi, yani model sonucu kendi
# cagirdigi bir aracin cevabi gibi gorecekti. API reddetti:
#
#     400 INVALID_ARGUMENT
#     "Function call is missing a thought signature"
#
# Gemini 3.x, gecmisteki arac cagrilarinda modelin kendi
# urettigi imzayi bekliyor ve o imzayi biz uretemeyiz. Bu
# yuzden sonuc DUZ METIN olarak, etiketli bir sistem notu
# halinde veriliyor. Model JSON okumakta zorlanmiyor ve bu yol
# SDK/model surumlerine bagli degil.

DEFAULT_PREFETCH_NOTE = """[SYSTEM NOTE - the user does not see this line]
I ran the `{tool}` tool on your behalf for the user's last message, \
so you can answer without waiting for a tool round.
Arguments: {args}
Result: {result}
If this result answers the question, do NOT call `{tool}` again; \
write the answer directly."""


class Assistant:
    """
    Arac cagiran, dayanakli (grounded) sohbet motoru.

    Uygulamaya ozel HICBIR sey bilmez: veritabani, urun,
    kullanici kavrami yok. Bunlarin hepsi disaridan verilir:

        tools             — arac tanimlari + uygulamalari
        system_prompt      — metin ya da request -> metin fonksiyonu
        prefetch           — istege bagli on arama karari
        before_model_call  — LLM cagrisindan once calisacak kanca
                             (orn. veritabani transaction'ini kapat)
        grounding          — uydurma ad denetimi politikasi
    """

    def __init__(
        self,
        *,
        tools: Sequence[ToolSpec] = (),
        system_prompt: str | Callable[[Any], str] = "",
        config: AssistantConfig | None = None,
        prefetch: Callable[[ToolContext], Prefetch | None] | None = None,
        before_model_call: Callable[[Any], None] | None = None,
        grounding: GroundingPolicy | None = None,
        directive_tag: str | None = "SHOW",
        prefetch_note: str = DEFAULT_PREFETCH_NOTE,
        empty_reply: str = "I could not quite follow that. Could you rephrase?",
        empty_reply_with_cards: str = "Here is what I found.",
        client: Any | None = None,
        router: ModelRouter | None = None,
    ):
        self.config = config or AssistantConfig()

        self.registry = ToolRegistry(tools)

        self._system_prompt = system_prompt

        self._prefetch = prefetch

        self._before_model_call = before_model_call

        self.grounding = grounding

        self.parser = (
            DirectiveParser(directive_tag) if directive_tag else None
        )

        self._prefetch_note = prefetch_note

        self._empty_reply = empty_reply

        self._empty_reply_with_cards = empty_reply_with_cards

        self.router = router or ModelRouter(
            config=self.config,
            client=client,
        )

        # Arac listesi istek basina degismiyor: bir kez uretilip
        # saklaniyor. Sema uretimi ucuz ama bedava degil.
        self._gemini_tools = self.registry.gemini_tools()

    # -----------------------------------------------------
    # YARDIMCILAR
    # -----------------------------------------------------

    def _instruction(self, request: Any) -> str:
        """
        Sistem talimati.

        Fonksiyon olabiliyor cunku talimat cogu zaman isteğe
        gore degisiyor: giris yapmis kullanicinin adi, sectigi
        tercihler, dilin secimi. Sabit metin isteyen taraf
        dogrudan str verir.
        """

        if callable(self._system_prompt):
            return self._system_prompt(request)

        return self._system_prompt

    def _generation_config(self, request: Any) -> types.GenerateContentConfig:

        return types.GenerateContentConfig(
            system_instruction=self._instruction(request) or None,
            tools=self._gemini_tools or None,
            # SDK'nin otomatik arac cagirmasi KAPALI: donguyu
            # elle suruyoruz cunku hangi kayitlarin donduguNU
            # yakalamamiz gerekiyor (kartlar bundan uretiliyor).
            automatic_function_calling=(
                types.AutomaticFunctionCallingConfig(disable=True)
            ),
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
        )

    def _notify_before_call(self, request: Any) -> None:
        """
        LLM cagrisindan hemen once cagiran tarafa haber ver.

        NEDEN VAR
        Araclar genellikle veritabani okuyor ve ORM
        transaction'i commit/rollback'e kadar acik kaliyor.
        Simdi araya bir LLM cagrisi giriyor: normalde birkac
        saniye, ama kuyrukta beklerken dakikalar surebiliyor. Bu
        sirada sunucu acik kalan transaction yuzunden baglantiyi
        dusuruyor (Neon'da yasandi:
        idle_in_transaction_session_timeout).

        Modul veritabani bilmiyor; kancayi cagiriyor, ne
        yapilacagina cagiran karar veriyor.
        """

        if self._before_model_call is None:
            return

        try:
            self._before_model_call(request)
        except Exception as error:
            # Kanca patlarsa sohbet devam etmeli: en kotu
            # senaryoda eski davranisa donuyoruz.
            logger.warning("before_model_call basarisiz: %s", error)

    def _prepare(
        self,
        messages: Sequence[Any],
    ) -> tuple[list[Message], list[types.Content]]:

        history = normalize(messages)

        contents = to_contents(history, self.config.max_history_messages)

        if not contents:
            raise ValueError(
                "Sohbet gecmisi bos: gonderilecek mesaj yok."
            )

        return history, contents

    def _run_prefetch(
        self,
        ctx: ToolContext,
        cards: list[dict],
        tool_calls: list[str],
    ) -> types.Content | None:
        """
        On aramayi calistirir ve modele verilecek sistem notunu
        uretir. Karar cagiranin, calistirmak bizim.

        ON ARAMA BIR HIZLANDIRMA. Patlarsa sohbet eski yoldan
        devam etmeli: model araci kendisi cagirir.
        """

        if self._prefetch is None:
            return None

        try:
            plan = self._prefetch(ctx)
        except Exception as error:
            logger.warning("On arama karari basarisiz: %s", error)
            return None

        if plan is None:
            return None

        if plan.tool not in self.registry:
            logger.warning(
                "On arama tanimsiz araci istedi: %s", plan.tool
            )
            return None

        result = self.registry.run(plan.tool, plan.args, ctx)

        if "error" in result.payload:
            # Hatali on aramayi modele TASIMIYORUZ: elinde
            # bozuk bir sonuc olacaksa hic olmamasi iyidir,
            # araci kendisi cagirir.
            logger.warning(
                "On arama hata dondurdu, atlaniyor: %s",
                result.payload.get("error"),
            )
            return None

        cards.extend(result.cards)

        tool_calls.append(plan.tool)

        template = plan.note or self._prefetch_note

        note = template.format(
            tool=plan.tool,
            args=json.dumps(plan.args, ensure_ascii=False),
            result=json.dumps(
                dict(result.payload), ensure_ascii=False, default=str
            ),
        )

        return types.Content(role="user", parts=[types.Part(text=note)])

    def _execute_calls(
        self,
        calls: Sequence[Any],
        ctx: ToolContext,
        cards: list[dict],
        tool_calls: list[str],
    ) -> types.Content:
        """Arac cagrilarini calistirip cevap parcalarini uretir."""

        parts: list[types.Part] = []

        for call in calls:

            name = getattr(call, "name", "") or ""

            tool_calls.append(name)

            result = self.registry.run(
                name,
                dict(getattr(call, "args", None) or {}),
                ctx,
            )

            cards.extend(result.cards)

            parts.append(
                types.Part.from_function_response(
                    name=name,
                    response=dict(result.payload),
                )
            )

        return types.Content(role="user", parts=parts)

    def _finalize(
        self,
        raw_reply: str,
        cards: list[dict],
        tool_calls: list[str],
        state: dict,
        usage: Usage,
        started: float,
    ) -> ChatTurn:

        if self.parser is not None:
            reply, show_ids = self.parser.split(raw_reply or "")
        else:
            reply, show_ids = (raw_reply or "").strip(), None

        if not reply:
            # Model tur sinirina takildiysa veya bos dondurduyse
            # sessiz kalma; en azindan bulunan kayitlari devret.
            reply = (
                self._empty_reply_with_cards
                if cards
                else self._empty_reply
            )

        unique = self._dedupe(cards)

        ungrounded = (
            self.grounding.audit(reply, cards)
            if self.grounding is not None
            else []
        )

        if ungrounded:
            logger.warning(
                "Cevapta arac sonucunda GECMEYEN ad(lar) var: "
                "%s | model=%s | araclar=%s",
                ", ".join(ungrounded),
                state.get("model"),
                tool_calls,
            )

        selected = self._select(unique, show_ids)

        return ChatTurn(
            reply=reply,
            cards=selected[: self.config.max_cards],
            tool_calls=tool_calls,
            model=state.get("model"),
            ungrounded=ungrounded,
            usage=usage,
            attempts=list(state.get("attempts", [])),
            elapsed=round(time.monotonic() - started, 2),
        )

    def _dedupe(self, cards: Sequence[Mapping[str, Any]]) -> list[dict]:
        """
        Ayni kayit birden fazla arac cagrisinda donmus olabilir.
        Sirayi koru (ilk gorunum), tekrari at.
        """

        field_name = self.config.card_id_field

        seen: set[str] = set()

        unique: list[dict] = []

        for card in cards:

            key = card.get(field_name)

            if key is None:
                # Kimliksiz kart tekrar denetimine girmiyor:
                # neyin ayni oldugunu bilemiyoruz.
                unique.append(dict(card))
                continue

            key = str(key)

            if key in seen:
                continue

            seen.add(key)

            unique.append(dict(card))

        return unique

    def _select(
        self,
        unique: list[dict],
        show_ids: list[str] | None,
    ) -> list[dict]:
        """
        Modelin [SHOW: ...] secimini uygular.

        show_ids None ise direktif yoktu -> hepsi gosterilir
        (guvenli varsayilan). Bos liste ise model bilincli
        olarak "hicbiri" dedi.

        Bilinmeyen kimlikler sessizce atiliyor — model bir
        kimlik uydurursa kart olarak cikmaz. Bu modulun temel
        guvencesi bu.
        """

        if show_ids is None:
            return unique

        field_name = self.config.card_id_field

        by_id = {
            str(card.get(field_name)): card
            for card in unique
            if card.get(field_name) is not None
        }

        # Modelin sirasi korunuyor: onceligini kendisi
        # belirlemis oluyor.
        return [
            by_id[card_id]
            for card_id in show_ids
            if card_id in by_id
        ]

    # -----------------------------------------------------
    # SENKRON TUR
    # -----------------------------------------------------

    def run(
        self,
        messages: Sequence[Any],
        *,
        request: Any = None,
    ) -> ChatTurn:
        """
        Bir sohbet turunu calistirir ve tamamlanmis cevabi
        dondurur.

        Firlatabilecegi hatalar:
            QuotaExceeded       butun modeller 429
            ModelTimeout        butun modeller zaman asimi
            ConfigurationError  API anahtari yok
            ValueError          gecmis bos
        """

        started = time.monotonic()

        history, contents = self._prepare(messages)

        state: dict = {}

        cards: list[dict] = []

        tool_calls: list[str] = []

        usage = Usage()

        ctx = ToolContext(
            request=request,
            messages=history,
            state=state,
        )

        gen_config = self._generation_config(request)

        note = self._run_prefetch(ctx, cards, tool_calls)

        if note is not None:
            contents.append(note)
            self._notify_before_call(request)

        response = self.router.generate(contents, gen_config, state)

        usage.add(response)

        for _ in range(self.config.max_tool_rounds):

            calls = list(getattr(response, "function_calls", None) or [])

            if not calls:
                break

            # Modelin arac cagirma niyeti gecmise AYNEN giriyor:
            # bir sonraki turda kendi cagrisini gormesi lazim
            # (ve Gemini 3.x kendi imzasini bekliyor).
            candidate = self._candidate_content(response)

            if candidate is not None:
                contents.append(candidate)

            contents.append(
                self._execute_calls(calls, ctx, cards, tool_calls)
            )

            self._notify_before_call(request)

            response = self.router.generate(contents, gen_config, state)

            usage.add(response)

        return self._finalize(
            raw_reply=self._response_text(response),
            cards=cards,
            tool_calls=tool_calls,
            state=state,
            usage=usage,
            started=started,
        )

    # -----------------------------------------------------
    # AKISLI TUR
    # -----------------------------------------------------

    def stream(
        self,
        messages: Sequence[Any],
        *,
        request: Any = None,
    ) -> Iterator[StreamEvent]:
        """
        Ayni turu akis halinde calistirir.

        NEDEN AKIS
        Olculen gecikmenin buyuk kismi ILK harfe kadar geciyor;
        cevabin tamami beklenirse kullanici 5-9 saniye bos ekrana
        bakiyor. Akista ilk kelime ~1-2 saniyede dusuyor. Tur
        SUYA ayni is yapiyor, yalnizca teslim bicimi degisiyor.

        NE ZAMAN METIN YAYINLANIR
        Model bazen arac cagirmadan once bir giris cumlesi
        yaziyor ("Bakiyorum..."). O metin de yayinlaniyor: dogru
        ve kullaniciya bilgi veriyor. Direktif satiri
        ([SHOW: ...]) akista da ayiklaniyor, kullaniciya gitmiyor.

        Son olay her zaman type="done" ve icinde tam ChatTurn
        var: cagiran taraf kartlari, modeli ve token sayimini
        oradan alir.
        """

        started = time.monotonic()

        history, contents = self._prepare(messages)

        state: dict = {}

        cards: list[dict] = []

        tool_calls: list[str] = []

        usage = Usage()

        ctx = ToolContext(
            request=request,
            messages=history,
            state=state,
        )

        gen_config = self._generation_config(request)

        note = self._run_prefetch(ctx, cards, tool_calls)

        if note is not None:

            contents.append(note)

            for name in tool_calls:
                yield StreamEvent(type="tool", tool=name)

            self._notify_before_call(request)

        text_filter = (
            self.parser.stream_filter() if self.parser else None
        )

        raw_chunks: list[str] = []

        for round_index in range(self.config.max_tool_rounds + 1):

            stream = self.router.stream(contents, gen_config, state)

            parts: list[Any] = []

            calls: list[Any] = []

            last_chunk: Any = None

            for chunk in stream:

                last_chunk = chunk

                for part in self._chunk_parts(chunk):

                    parts.append(part)

                    call = getattr(part, "function_call", None)

                    if call is not None:
                        calls.append(call)
                        continue

                    piece = getattr(part, "text", None)

                    if not piece:
                        continue

                    raw_chunks.append(piece)

                    visible = (
                        text_filter.feed(piece)
                        if text_filter
                        else piece
                    )

                    if visible:
                        yield StreamEvent(type="text", text=visible)

            usage.add(last_chunk)

            if not calls:
                break

            if round_index >= self.config.max_tool_rounds:
                # Tur siniri: dongude kalmak yerine elimizdekiyle
                # bitiriyoruz.
                logger.warning(
                    "Arac turu siniri asildi; akis kesiliyor."
                )
                break

            contents.append(types.Content(role="model", parts=parts))

            for call in calls:
                yield StreamEvent(
                    type="tool",
                    tool=getattr(call, "name", "") or "",
                )

            contents.append(
                self._execute_calls(calls, ctx, cards, tool_calls)
            )

            self._notify_before_call(request)

        tail = text_filter.close() if text_filter else ""

        if tail:
            yield StreamEvent(type="text", text=tail)

        raw_reply = "".join(raw_chunks)

        turn = self._finalize(
            raw_reply=raw_reply,
            cards=cards,
            tool_calls=tool_calls,
            state=state,
            usage=usage,
            started=started,
        )

        yield StreamEvent(type="done", turn=turn)

    # -----------------------------------------------------
    # SDK CEVABINI OKUMA
    # -----------------------------------------------------
    #
    # Bu uc yardimci, SDK cevabinin sekli degistiginde tek
    # yerden duzeltilebilsin diye ayrildi. Alanlar dogrudan
    # okunsa ayni getattr zinciri motorun her yerine dagilirdi.

    @staticmethod
    def _response_text(response: Any) -> str:

        text = getattr(response, "text", None)

        return text or ""

    @staticmethod
    def _candidate_content(response: Any) -> Any | None:

        candidates = getattr(response, "candidates", None) or []

        if not candidates:
            return None

        return getattr(candidates[0], "content", None)

    @staticmethod
    def _chunk_parts(chunk: Any) -> list[Any]:

        candidates = getattr(chunk, "candidates", None) or []

        if not candidates:
            return []

        content = getattr(candidates[0], "content", None)

        return list(getattr(content, "parts", None) or [])
