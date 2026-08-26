"""
Model zinciri: kota devri, zaman asimi, soguma.

Bu davranislarin hepsi olculmus gercek sorunlara cevap; testler
o sorunlarin geri gelmedigini kontrol ediyor.
"""

from __future__ import annotations

import pytest
from google.genai import types

from toolchat import AssistantConfig, ModelTimeout, QuotaExceeded
from toolchat.router import ModelRouter

from .fakes import FakeClient, FakeResponse, ReadTimeout, quota_error

CHAIN = ("model-a", "model-b", "model-c")

GEN_CONFIG = types.GenerateContentConfig(temperature=0.7)


def _router(script, *, clock=None, cooldown=60.0):

    config = AssistantConfig(
        model_chain=CHAIN,
        api_key="test",
        cooldown_seconds=cooldown,
        call_timeout=12.0,
        last_call_timeout=25.0,
    )

    client = FakeClient(script)

    router = ModelRouter(
        config=config,
        client=client,
        clock=clock or (lambda: 0.0),
    )

    return router, client


def test_kota_hatasinda_siradaki_model_denenir():

    router, client = _router([quota_error(), FakeResponse(text="tamam")])

    state: dict = {}

    response = router.generate([], GEN_CONFIG, state)

    assert response.text == "tamam"
    assert client.used_models == ["model-a", "model-b"]
    assert state["model"] == "model-b"


def test_butun_modeller_tukenirse_kota_hatasi():
    """
    Kullaniciya "kotan doldu, N saniye sonra tekrar dene"
    diyebilmek icin retry suresi tasinmali.
    """

    router, _ = _router([quota_error(30.5), quota_error(), quota_error()])

    with pytest.raises(QuotaExceeded) as info:
        router.generate([], GEN_CONFIG, {})

    assert info.value.retry_after == 31


def test_butun_modeller_yavassa_zaman_asimi_hatasi():
    """
    Hepsi zaman asimina ugradiysa bu KOTA sorunu degil; yanlis
    teshis kullaniciya yanlis sey yaptirir (beklemek yerine
    tekrar denemek gerekiyor).
    """

    router, _ = _router([ReadTimeout(), ReadTimeout(), ReadTimeout()])

    with pytest.raises(ModelTimeout):
        router.generate([], GEN_CONFIG, {})


def test_son_denemeye_daha_uzun_sure_taniniyor():
    """
    Mantik: baska model varsa cabuk vazgec, sondaysan sabirli
    ol. Olculen hata: 18s beklenip sonra ucuncu model 5
    saniyede cevap veriyordu — 18 saniye tamamen bosa.
    """

    router, client = _router([ReadTimeout(), ReadTimeout(), FakeResponse(text="ok")])

    router.generate([], GEN_CONFIG, {})

    timeouts = [
        call["config"].http_options.timeout for call in client.models.calls
    ]

    assert timeouts == [12000, 12000, 25000]


def test_hata_alan_model_bir_sure_atlanir():
    """
    Soguma olmasa her istek once tukenmis modele gidip 429
    yiyecek, sonra digerine gececekti: her mesaja bosuna bir
    tur gecikme.
    """

    now = [0.0]

    router, client = _router(
        [quota_error(), FakeResponse(text="bir"), FakeResponse(text="iki")],
        clock=lambda: now[0],
        cooldown=60.0,
    )

    router.generate([], GEN_CONFIG, {})

    # Yeni istek: model-a hala sogumada, dogrudan model-b.
    now[0] = 10.0

    router.generate([], GEN_CONFIG, {})

    assert client.used_models == ["model-a", "model-b", "model-b"]


def test_soguma_suresi_gecince_model_geri_doner():

    now = [0.0]

    router, client = _router(
        [quota_error(), FakeResponse(text="bir"), FakeResponse(text="iki")],
        clock=lambda: now[0],
        cooldown=60.0,
    )

    router.generate([], GEN_CONFIG, {})

    now[0] = 120.0

    router.generate([], GEN_CONFIG, {})

    assert client.used_models[-1] == "model-a"


def test_secili_model_basa_alinir_ama_tek_aday_degil():
    """
    Arac turundan sonra bastan denemek tukenmis modele bosuna
    gitmek olurdu. Ama tek adayla kalmak da "cevap yok" demek:
    kuyruk sikismasi istegin ortasinda da olabiliyor.
    """

    router, client = _router([quota_error(), FakeResponse(text="ok")])

    state = {"model": "model-c"}

    router.generate([], GEN_CONFIG, state)

    assert client.used_models[0] == "model-c"
    assert len(client.used_models) == 2


def test_bilinmeyen_hata_maskelenmez():
    """
    Kota/zaman asimi disindaki bir hatayi yedek modelle
    denemek, gercek arizayi gizlemek olur.
    """

    router, client = _router([ValueError("sema hatasi")])

    with pytest.raises(ValueError):
        router.generate([], GEN_CONFIG, {})

    assert client.used_models == ["model-a"]


def test_deneme_kayitlari_tutuluyor():
    """Hangi modele kac saniye harcandi — teshis icin."""

    router, _ = _router([quota_error(), FakeResponse(text="ok")])

    state: dict = {}

    router.generate([], GEN_CONFIG, state)

    assert [a["outcome"] for a in state["attempts"]] == ["quota", "ok"]
