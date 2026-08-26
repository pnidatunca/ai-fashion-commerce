"""
Kucuk parcalarin testleri: direktif ayiklama, arac argumani
duzeltme, dayanak denetimi, gecmis normalizasyonu, ayarlar.
"""

from __future__ import annotations

import pytest

from toolchat import (
    AssistantConfig,
    ConfigurationError,
    DirectiveParser,
    GroundingPolicy,
    Message,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    normalize,
)
from toolchat.messages import to_contents
from toolchat.tools import coerce_args, json_schema_to_genai

# =========================================================
# DIREKTIF
# =========================================================


def test_directive_yoksa_none_doner():
    """Direktif yoksa 'hepsini goster' anlamina gelen None."""

    text, ids = DirectiveParser().split("Iste birkac oneri.")

    assert text == "Iste birkac oneri."
    assert ids is None


def test_directive_kimlikleri_ayiklanir():

    text, ids = DirectiveParser().split(
        "Bunlar uygun.\n[SHOW: A1, B2 , C3]"
    )

    assert text == "Bunlar uygun."
    assert ids == ["A1", "B2", "C3"]


def test_directive_none_bos_liste():
    """'hicbiri' bilincli bir karar: bos liste, None degil."""

    for raw in ("[SHOW: none]", "[SHOW: yok]", "[SHOW:]"):

        text, ids = DirectiveParser().split("Bulamadim. " + raw)

        assert ids == []
        assert "SHOW" not in text


def test_directive_metnin_ortasinda_da_ayiklanir():
    """
    Ilk surum satir sonuna sabitliydi; model direktiften sonra
    bir cumle yazdiginda ham metin kullaniciya gidiyordu.
    """

    text, ids = DirectiveParser().split(
        "Sunlar var.\n[SHOW: A1]\nBaska bir sey ister misin?"
    )

    assert ids == ["A1"]
    assert "[SHOW" not in text
    assert "Baska bir sey ister misin?" in text


def test_directive_son_gecis_kazanir():

    _, ids = DirectiveParser().split("[SHOW: A1]\nDuzeltme:\n[SHOW: B2]")

    assert ids == ["B2"]


def test_stream_filter_direktifi_gizler():
    """Akista kullanici ham direktifi gormemeli."""

    flt = DirectiveParser().stream_filter()

    visible = "".join(
        flt.feed(delta)
        for delta in ["Iste ", "iki oneri.", "\n[SHOW", ": A1,", " B2]"]
    )

    visible += flt.close()

    assert visible.strip() == "Iste iki oneri."


def test_stream_filter_direktif_olmayan_parantezi_yayinlar():

    flt = DirectiveParser().stream_filter()

    visible = "".join(flt.feed(d) for d in ["Fiyat ", "[indirimli]", " gorunuyor"])

    visible += flt.close()

    assert visible == "Fiyat [indirimli] gorunuyor"


def test_stream_filter_yarim_direktifi_atar():
    """Model yarida kesilirse yarim '[SHOW: A1' metni gitmesin."""

    flt = DirectiveParser().stream_filter()

    visible = flt.feed("Tamam.\n[SHOW: A1")

    visible += flt.close()

    assert visible.strip() == "Tamam."


# =========================================================
# ARAC ARGUMANLARI
# =========================================================

SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "gender": {"type": "string", "enum": ["women", "men"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": 12},
        "max_price": {"type": "number"},
        "exact": {"type": "boolean"},
    },
    "required": ["query"],
}


def test_metin_sayiya_cevrilir():

    args = coerce_args(SCHEMA, {"query": "x", "limit": "6"})

    assert args["limit"] == 6


def test_para_birimi_yazisi_sayi_olarak_okunur():
    """Model bazen '3000 TL' yaziyor; butce kaybolmasin."""

    args = coerce_args(SCHEMA, {"query": "x", "max_price": "3000 TL"})

    assert args["max_price"] == 3000.0


def test_binlik_ayirici_bin_kat_kucultmez():

    args = coerce_args(SCHEMA, {"query": "x", "max_price": "3.000"})

    assert args["max_price"] == 3000.0


def test_limit_araliga_cekilir():

    assert coerce_args(SCHEMA, {"query": "x", "limit": 99})["limit"] == 12
    assert coerce_args(SCHEMA, {"query": "x", "limit": 0})["limit"] == 1


def test_enum_disi_deger_atilir():
    """Yanlis filtre, filtre yoklugundan kotudur."""

    args = coerce_args(SCHEMA, {"query": "x", "gender": "unisex"})

    assert "gender" not in args


def test_semada_olmayan_alan_atilir():

    args = coerce_args(SCHEMA, {"query": "x", "color": "siyah"})

    assert args == {"query": "x"}


def test_bool_metinden_okunur():

    assert coerce_args(SCHEMA, {"query": "x", "exact": "true"})["exact"] is True
    assert coerce_args(SCHEMA, {"query": "x", "exact": "hayir"})["exact"] is False


def test_json_schema_sdk_semasina_cevrilir():

    schema = json_schema_to_genai(SCHEMA)

    assert set(schema.properties) == {
        "query",
        "gender",
        "limit",
        "max_price",
        "exact",
    }
    assert schema.required == ["query"]
    assert schema.properties["gender"].enum == ["women", "men"]


# =========================================================
# ARAC CALISTIRMA
# =========================================================


def _spec(handler) -> ToolSpec:
    return ToolSpec(
        name="search",
        description="test",
        parameters=SCHEMA,
        handler=handler,
    )


def test_arac_hatasi_istegi_dusurmez():
    """
    Arac patlarsa modele hata anlatilir; sohbet komple olmez.
    """

    def boom(args, ctx):
        raise RuntimeError("veritabani dustu")

    result = ToolRegistry([_spec(boom)]).run("search", {"query": "x"}, None)

    assert "error" in result.payload


def test_bilinmeyen_arac_modele_aciklanir():

    registry = ToolRegistry([_spec(lambda args, ctx: {"ok": True})])

    result = registry.run("baska_arac", {}, None)

    assert "baska_arac" in result.payload["error"]
    assert "search" in result.payload["error"]


def test_duz_sozluk_donduren_arac_kabul_edilir():

    registry = ToolRegistry([_spec(lambda args, ctx: {"found": 0})])

    result = registry.run("search", {"query": "x"}, None)

    assert result.payload == {"found": 0}
    assert result.cards == []


def test_ayni_adli_iki_arac_reddedilir():

    with pytest.raises(ValueError):
        ToolRegistry([_spec(lambda a, c: {}), _spec(lambda a, c: {})])


# =========================================================
# DAYANAK DENETIMI
# =========================================================

CARDS = [{"brand": "KuaiLu", "title": "Erkek keten gomlek"}]


def test_denylist_uydurma_markayi_yakalar():

    policy = GroundingPolicy(denylist=("koton", "trendyol"))

    assert policy.audit("Koton modellerini listeledim.", CARDS) == ["koton"]


def test_sonucta_gecen_marka_isaretlenmez():

    policy = GroundingPolicy(denylist=("koton",))

    assert policy.audit("**KuaiLu** keten gomlegi rahat.", CARDS) == []


def test_kalin_yazilmis_bilinmeyen_ad_yakalanir():

    assert GroundingPolicy().audit("**Nike** onerdim.", CARDS) == ["Nike"]


def test_denetim_kapatilabilir():

    from toolchat import NO_GROUNDING

    assert NO_GROUNDING.audit("**Nike** onerdim.", CARDS) == []


# =========================================================
# GECMIS
# =========================================================


def test_normalize_farkli_temsilleri_kabul_eder():
    """Sozluk, nesne, dataclass — role/content okunabiliyorsa yeter."""

    class Obj:
        role = "assistant"
        content = "merhaba"

    history = normalize(
        [{"role": "user", "content": "selam"}, Obj(), Message("user", "  ")]
    )

    assert [(m.role, m.content) for m in history] == [
        ("user", "selam"),
        ("assistant", "merhaba"),
    ]


def test_system_mesaji_gecmise_karismaz():

    assert normalize([{"role": "system", "content": "kural"}]) == []


def test_pencere_kirpilir_ve_asistanla_baslamaz():

    history = [
        Message("user", "bir"),
        Message("assistant", "iki"),
        Message("user", "uc"),
    ]

    contents = to_contents(history, max_history=2)

    # Pencere ["iki", "uc"]; bastaki asistan mesaji atiliyor.
    assert [c.role for c in contents] == ["user"]
    assert contents[0].parts[0].text == "uc"


def test_gemini_rolleri_cevrilir():

    contents = to_contents(
        [Message("user", "a"), Message("assistant", "b")], max_history=16
    )

    assert [c.role for c in contents] == ["user", "model"]


# =========================================================
# AYARLAR
# =========================================================


def test_tercih_edilen_model_basa_gecer():

    config = AssistantConfig(preferred_model="gemini-3.1-flash-lite")

    chain = config.chain()

    assert chain[0] == "gemini-3.1-flash-lite"
    # Yedekler duruyor: tercih tukenirse sohbet devam etmeli.
    assert len(chain) == len(AssistantConfig().model_chain)


def test_bozuk_ayar_reddedilir():

    with pytest.raises(ConfigurationError):
        AssistantConfig(call_timeout=0)

    with pytest.raises(ConfigurationError):
        AssistantConfig(model_chain=())


def test_cok_kisa_zaman_siniri_yukari_cekilir():
    """
    Gemini 10 saniyenin altini reddediyor:
        400 "Manually set deadline 8s is too short."
    Bu hata kota da zaman asimi da olmadigi icin yedek modele
    gecilmiyor, cagri komple dusuyor. Yani kisa sinir "hizli
    vazgecmek" degil "hic cevap almamak" demek.
    """

    config = AssistantConfig(call_timeout=8.0, last_call_timeout=3.0)

    assert config.call_timeout == 10.0
    assert config.last_call_timeout == 10.0


def test_env_bozuk_degeri_varsayilana_duser(monkeypatch):
    """
    Bozuk env degeri uygulamayi import aninda cokertmesin.
    """

    monkeypatch.setenv("TOOLCHAT_CALL_TIMEOUT", "sekiz saniye")

    assert AssistantConfig.from_env().call_timeout == 10.0


def test_env_zinciri_okunur(monkeypatch):

    monkeypatch.setenv("TOOLCHAT_MODEL_CHAIN", "a-model, b-model")
    monkeypatch.setenv("TOOLCHAT_MAX_CARDS", "3")

    config = AssistantConfig.from_env()

    assert config.model_chain == ("a-model", "b-model")
    assert config.max_cards == 3


def test_anahtar_yoksa_yapilandirma_hatasi(monkeypatch):

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(ConfigurationError):
        AssistantConfig().resolve_api_key()


def test_tool_result_bozuk_donusu_hataya_cevirir():

    assert "error" in ToolResult.coerce("duz metin").payload
