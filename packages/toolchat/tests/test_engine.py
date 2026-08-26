"""
Sohbet dongusu: arac cagirma, kart secimi, on arama, akis.
"""

from __future__ import annotations

import pytest

from toolchat import (
    Assistant,
    AssistantConfig,
    GroundingPolicy,
    Prefetch,
    ToolResult,
    ToolSpec,
)

from .fakes import FakeCall, FakeChunk, FakeClient, FakeResponse, FakeUsage

CONFIG = AssistantConfig(
    model_chain=("model-a",),
    api_key="test",
    card_id_field="product_id",
    max_cards=3,
)

CATALOG = {
    "A1": {"product_id": "A1", "title": "Keten gomlek", "brand": "KuaiLu"},
    "B2": {"product_id": "B2", "title": "Sneaker", "brand": "Kizik"},
    "C3": {"product_id": "C3", "title": "Kot pantolon", "brand": "Levi"},
}

SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 12},
    },
    "required": ["query"],
}


def _search_tool(calls: list[dict] | None = None) -> ToolSpec:
    """Butun katalogu donduren sahte arama araci."""

    def handler(args, ctx):

        if calls is not None:
            calls.append(args)

        return ToolResult(
            payload={
                "found": len(CATALOG),
                "products": [
                    {"product_id": p["product_id"], "title": p["title"]}
                    for p in CATALOG.values()
                ],
            },
            cards=list(CATALOG.values()),
        )

    return ToolSpec(
        name="search_catalog",
        description="Katalogda arar.",
        parameters=SEARCH_SCHEMA,
        handler=handler,
    )


def _assistant(script, *, stream_script=None, **kwargs) -> Assistant:

    kwargs.setdefault("tools", [_search_tool()])
    kwargs.setdefault("system_prompt", "Sen bir asistansin.")
    kwargs.setdefault("config", CONFIG)

    return Assistant(
        client=FakeClient(script, stream_script),
        **kwargs,
    )


HELLO = [{"role": "user", "content": "siyah sneaker ariyorum"}]


# =========================================================
# TEMEL AKIS
# =========================================================


def test_arac_cagrilmadan_cevap():

    assistant = _assistant([FakeResponse(text="Merhaba, nasil yardim edebilirim?")])

    turn = assistant.run([{"role": "user", "content": "merhaba"}])

    assert turn.reply == "Merhaba, nasil yardim edebilirim?"
    assert turn.cards == []
    assert turn.tool_calls == []
    assert turn.model == "model-a"


def test_arac_turu_calisir_ve_kartlar_toplanir():

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "sneaker"})]),
            FakeResponse(text="Iki secenek buldum.\n[SHOW: B2, A1]"),
        ]
    )

    turn = assistant.run(HELLO)

    assert turn.tool_calls == ["search_catalog"]
    # Model sirasi korunuyor: onceligi kendisi belirledi.
    assert [c["product_id"] for c in turn.cards] == ["B2", "A1"]
    assert "[SHOW" not in turn.reply


def test_bulamadim_diyorsa_kart_gosterilmez():
    """
    Arama motoru her zaman bir sey donduruyor. Metin
    "bulamadim" derken altinda alakasiz kartlar durmasi
    kullaniciyi aldatir.
    """

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "rolex"})]),
            FakeResponse(text="Boyle bir sey bulamadim.\n[SHOW: none]"),
        ]
    )

    turn = assistant.run(HELLO)

    assert turn.cards == []
    assert turn.reply == "Boyle bir sey bulamadim."


def test_direktif_yoksa_hepsi_gosterilir():
    """Guvenli varsayilan: bozulma yonu 'fazla kart'."""

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "x"})]),
            FakeResponse(text="Sunlara bak."),
        ]
    )

    turn = assistant.run(HELLO)

    assert len(turn.cards) == 3


def test_uydurulmus_kimlik_kart_olarak_cikmaz():
    """Modulun temel guvencesi: kart yalnizca arac sonucundan."""

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "x"})]),
            FakeResponse(text="Iste.\n[SHOW: A1, UYDURMA9]"),
        ]
    )

    turn = assistant.run(HELLO)

    assert [c["product_id"] for c in turn.cards] == ["A1"]


def test_ayni_kayit_iki_aramada_dondu_ise_tekrar_etmez():

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "a"})]),
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "b"})]),
            FakeResponse(text="Tamam."),
        ]
    )

    turn = assistant.run(HELLO)

    assert len(turn.cards) == 3
    assert turn.tool_calls == ["search_catalog", "search_catalog"]


def test_kart_sayisi_sinirlanir():

    config = CONFIG.with_overrides(max_cards=2)

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "x"})]),
            FakeResponse(text="Tamam."),
        ],
        config=config,
    )

    assert len(_run(assistant).cards) == 2


def _run(assistant):
    return assistant.run(HELLO)


def test_bos_cevapta_sessiz_kalinmaz():

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "x"})]),
            FakeResponse(text=""),
        ],
        empty_reply_with_cards="Birkac secenek buldum.",
    )

    assert _run(assistant).reply == "Birkac secenek buldum."


def test_arac_turu_siniri_sonsuz_donguyu_keser():
    """Model ayni araci tekrar tekrar cagirirsa istek kesilir."""

    config = CONFIG.with_overrides(max_tool_rounds=2)

    assistant = _assistant(
        [FakeResponse(calls=[FakeCall("search_catalog", {"query": "x"})])] * 3,
        config=config,
    )

    turn = assistant.run(HELLO)

    assert len(turn.tool_calls) == 2


def test_arac_argumanlari_semaya_gore_duzeltilir():

    seen: list[dict] = []

    assistant = _assistant(
        [
            FakeResponse(
                calls=[
                    FakeCall(
                        "search_catalog",
                        {"query": "x", "limit": "99", "renk": "siyah"},
                    )
                ]
            ),
            FakeResponse(text="Tamam."),
        ],
        tools=[_search_tool(seen)],
    )

    assistant.run(HELLO)

    assert seen == [{"query": "x", "limit": 12}]


def test_bos_gecmis_reddedilir():

    with pytest.raises(ValueError):
        _assistant([]).run([])


# =========================================================
# ON ARAMA
# =========================================================


def test_on_arama_llm_cagrisini_bire_indirir():
    """
    Onemli olan sayilar: bir LLM cagrisi, sifir arac turu, ama
    kartlar yine dolu.
    """

    client = FakeClient([FakeResponse(text="Sunlar uygun.\n[SHOW: A1]")])

    assistant = Assistant(
        tools=[_search_tool()],
        system_prompt="test",
        config=CONFIG,
        prefetch=lambda ctx: Prefetch(
            tool="search_catalog", args={"query": "sneaker"}
        ),
        client=client,
    )

    turn = assistant.run(HELLO)

    assert len(client.models.calls) == 1
    assert turn.tool_calls == ["search_catalog"]
    assert [c["product_id"] for c in turn.cards] == ["A1"]

    # Sonuc modele DUZ METIN sistem notu olarak veriliyor:
    # uydurma arac cagrisi eklemek "missing thought signature"
    # hatasina yol aciyordu.
    note = client.models.calls[0]["contents"][-1].parts[0].text

    assert "search_catalog" in note
    assert "A1" in note


def test_on_arama_patlarsa_sohbet_devam_eder():
    """On arama bir HIZLANDIRMA; olmazsa eski yol calisir."""

    def kirik(ctx):
        raise RuntimeError("sozluk yuklenemedi")

    assistant = _assistant(
        [FakeResponse(text="Merhaba.")],
        prefetch=kirik,
    )

    assert assistant.run(HELLO).reply == "Merhaba."


def test_on_arama_tanimsiz_araci_isterse_atlanir():

    assistant = _assistant(
        [FakeResponse(text="Merhaba.")],
        prefetch=lambda ctx: Prefetch(tool="yok_boyle", args={}),
    )

    turn = assistant.run(HELLO)

    assert turn.tool_calls == []


def test_on_arama_karari_gecmisi_gorur():
    """
    Karar veren tarafin son kullanici mesajina ve request
    nesnesine erisimi olmali.
    """

    seen: dict = {}

    def decide(ctx):
        seen["last"] = ctx.messages[-1].content
        seen["request"] = ctx.request
        return None

    assistant = _assistant([FakeResponse(text="ok")], prefetch=decide)

    assistant.run(HELLO, request={"user": "emre"})

    assert seen["last"] == "siyah sneaker ariyorum"
    assert seen["request"] == {"user": "emre"}


# =========================================================
# KANCALAR VE DENETIM
# =========================================================


def test_llm_cagrisindan_once_kanca_calisir():
    """
    Veritabani transaction'ini kapatmak icin var: LLM cagrisi
    kuyrukta dakikalarca bekleyebiliyor ve acik transaction
    baglantiyi dusuruyor.
    """

    hits = []

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "x"})]),
            FakeResponse(text="Tamam."),
        ],
        before_model_call=hits.append,
    )

    assistant.run(HELLO, request="oturum")

    assert hits == ["oturum"]


def test_kanca_patlarsa_sohbet_devam_eder():

    def kirik(request):
        raise RuntimeError("rollback basarisiz")

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "x"})]),
            FakeResponse(text="Tamam."),
        ],
        before_model_call=kirik,
    )

    assert assistant.run(HELLO).reply == "Tamam."


def test_uydurma_ad_denetimi_cevabi_bozmaz():
    """
    Tespit ve kayit yapiliyor, metne DOKUNULMUYOR: cumlenin
    ortasindan ad silmek anlami bozar.
    """

    assistant = _assistant(
        [
            FakeResponse(calls=[FakeCall("search_catalog", {"query": "x"})]),
            FakeResponse(text="Koton modellerini listeledim.\n[SHOW: A1]"),
        ],
        grounding=GroundingPolicy(
            fields=("brand", "title"), denylist=("koton",)
        ),
    )

    turn = assistant.run(HELLO)

    assert turn.ungrounded == ["koton"]
    assert turn.reply == "Koton modellerini listeledim."


def test_token_sayimi_toplanir():

    assistant = _assistant(
        [
            FakeResponse(
                calls=[FakeCall("search_catalog", {"query": "x"})],
                usage=FakeUsage(100, 20, 120),
            ),
            FakeResponse(text="Tamam.", usage=FakeUsage(200, 30, 230)),
        ]
    )

    usage = assistant.run(HELLO).usage

    assert usage.calls == 2
    assert usage.prompt_tokens == 300
    assert usage.total_tokens == 350


# =========================================================
# AKIS
# =========================================================


def test_akis_metni_parca_parca_verir():

    assistant = _assistant(
        [],
        stream_script=[
            [
                FakeChunk(text="Iste "),
                FakeChunk(text="iki oneri."),
                FakeChunk(text="\n[SHOW: A1]", usage=FakeUsage()),
            ]
        ],
    )

    events = list(assistant.stream(HELLO))

    texts = [e.text for e in events if e.type == "text"]

    assert "".join(texts).strip() == "Iste iki oneri."

    done = events[-1]

    assert done.type == "done"
    assert done.turn.reply == "Iste iki oneri."


def test_akis_arac_turunu_de_yurutur():

    assistant = _assistant(
        [],
        stream_script=[
            [FakeChunk(call=FakeCall("search_catalog", {"query": "x"}))],
            [FakeChunk(text="Buldum.\n[SHOW: B2]")],
        ],
    )

    events = list(assistant.stream(HELLO))

    tools = [e.tool for e in events if e.type == "tool"]

    assert tools == ["search_catalog"]

    turn = events[-1].turn

    assert [c["product_id"] for c in turn.cards] == ["B2"]
    assert turn.reply == "Buldum."
