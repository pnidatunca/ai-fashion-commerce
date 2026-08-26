"""
Test ikizleri.

NEDEN SAHTE ISTEMCI
Gercek API'ye vurmak testi ucretli, yavas ve kararsiz yapardi;
ustelik test etmek istedigimiz sey modelin zekasi DEGIL, bizim
dongumuz: kota devri, arac cagrisi, kart secimi, direktif
ayiklama. Bunlarin hepsi istemci sahte oldugunda da aynen
calisiyor.

PARCALAR GERCEK SDK TIPLERI
Cevabin govdesi (Content/Part/FunctionCall) sahte degil: motor
bu parcalari gecmise geri koyuyor ve SDK onlari dogruluyor.
Sahte bir Part kullanmak testi gecirir ama uretimde patlardi.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.genai import types


def FakeCall(name: str, args: dict | None = None) -> types.FunctionCall:
    return types.FunctionCall(name=name, args=dict(args or {}))


def _candidate(parts: list[types.Part]) -> types.Candidate:
    return types.Candidate(
        content=types.Content(role="model", parts=parts)
    )


@dataclass
class FakeUsage:
    prompt_token_count: int = 10
    candidates_token_count: int = 5
    total_token_count: int = 15


class FakeResponse:
    """generate_content donusunun ihtiyac duyulan yuzu."""

    def __init__(
        self,
        text: str | None = None,
        calls: list[types.FunctionCall] | None = None,
        usage: FakeUsage | None = None,
    ):
        self.text = text

        self.function_calls = list(calls or [])

        self.usage_metadata = usage or FakeUsage()

        parts: list[types.Part] = []

        if text:
            parts.append(types.Part(text=text))

        for call in self.function_calls:
            parts.append(types.Part(function_call=call))

        self.candidates = [_candidate(parts)]


class FakeChunk:
    """Akis parcasi."""

    def __init__(
        self,
        text: str | None = None,
        call: types.FunctionCall | None = None,
        usage: FakeUsage | None = None,
    ):
        parts: list[types.Part] = []

        if text is not None:
            parts.append(types.Part(text=text))

        if call is not None:
            parts.append(types.Part(function_call=call))

        self.candidates = [_candidate(parts)]

        self.usage_metadata = usage


class ReadTimeout(Exception):
    """
    Adi "timeout" iceren bir hata: errors.is_timeout_error tipe
    degil ADA bakiyor (httpx'i import etmemek icin).
    """


def quota_error(retry_after: float | None = None) -> Exception:
    """Gercek 429 govdesine benzeyen hata."""

    text = "429 RESOURCE_EXHAUSTED: quota exceeded."

    if retry_after is not None:
        text += f" Please retry in {retry_after}s."

    error = Exception(text)

    error.code = 429  # type: ignore[attr-defined]

    return error


class FakeModels:
    """
    Onceden yazilmis bir senaryoyu sirayla oynatir.

    Senaryodaki her oge ya bir cevap ya bir hata. Hata ise
    firlatilir — kota devrini test etmenin yolu bu.
    """

    def __init__(
        self,
        script: list[Any],
        stream_script: list[Any] | None = None,
    ):
        self.script = list(script)
        self.stream_script = list(stream_script or [])
        self.calls: list[dict] = []

    def _next(self, script: list[Any], label: str) -> Any:

        if not script:
            raise AssertionError(
                f"Senaryo tukendi: beklenmeyen {label} cagrisi."
            )

        item = script.pop(0)

        if isinstance(item, BaseException):
            raise item

        return item

    def generate_content(self, *, model, contents, config):

        self.calls.append(
            {"model": model, "contents": list(contents), "config": config}
        )

        return self._next(self.script, "generate_content")

    def generate_content_stream(self, *, model, contents, config):

        self.calls.append(
            {"model": model, "contents": list(contents), "config": config}
        )

        chunks = self._next(self.stream_script, "generate_content_stream")

        # Hata ilk parcada cikacaksa iterator'un ICINDE olmali:
        # router ilk parcayi cekerken yakaliyor ve yedege
        # gecebiliyor.
        def _iterate():
            for chunk in chunks:
                if isinstance(chunk, BaseException):
                    raise chunk
                yield chunk

        return _iterate()


class FakeClient:
    def __init__(
        self,
        script: list[Any],
        stream_script: list[Any] | None = None,
    ):
        self.models = FakeModels(script, stream_script)

    @property
    def used_models(self) -> list[str]:
        return [call["model"] for call in self.models.calls]
