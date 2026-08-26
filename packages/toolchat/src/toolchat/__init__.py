"""
toolchat — arac cagiran, dayanakli (grounded) sohbet asistani
motoru.

Ne yapar
--------
Bir LLM'e kendi fonksiyonlarinizi tanitir, model onlari
cagirdikca calistirir, sonuclari geri verir ve cevabi
kullaniciya hazir halde dondurur. Uzerine su uc sorunu cozer:

  1. KOTA/GECIKME. Sirali model zinciri: 429 veya zaman asimi
     alan model birakilip siradaki denenir, hata alan model bir
     sure soguma listesine girer.
  2. UYDURMA. Ekranda gosterilen kartlar YALNIZCA arac
     sonucundan uretilir; model bir kimlik uydurursa kart olarak
     cikmaz. Duzyazidaki uydurma adlar icin ayri bir denetim var.
  3. TUR SAYISI. On arama (prefetch) ile yaygin durumda iki LLM
     cagrisi bire iniyor.

Uygulamaya ozel hicbir sey bilmez: veritabani, urun, kullanici
kavrami yok. Hepsi disaridan verilir.

En kisa ornek
-------------
    from toolchat import Assistant, ToolSpec, ToolResult

    def search(args, ctx):
        rows = my_db.search(args["query"])
        return ToolResult(
            payload={"found": len(rows), "items": [r.brief() for r in rows]},
            cards=[r.card() for r in rows],
        )

    assistant = Assistant(
        tools=[
            ToolSpec(
                name="search_catalog",
                description="Katalogda urun arar. Kullanici bir "
                            "urun tarif ettiginde CAGIR.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string",
                                  "description": "Dogal dil tarifi."},
                    },
                    "required": ["query"],
                },
                handler=search,
            )
        ],
        system_prompt="Sen bir alisveris asistanisin. ...",
    )

    turn = assistant.run([{"role": "user", "content": "siyah sneaker"}])

    print(turn.reply, turn.cards, turn.model)

Ayrintili kullanim ve secenekler icin: paketin README dosyasi.
"""

from .config import (
    DEFAULT_MODEL_CHAIN,
    MIN_CALL_TIMEOUT,
    AssistantConfig,
)
from .directives import DirectiveParser, DirectiveStreamFilter
from .engine import (
    DEFAULT_PREFETCH_NOTE,
    Assistant,
    ChatTurn,
    Prefetch,
    StreamEvent,
    Usage,
)
from .errors import (
    AssistantError,
    ConfigurationError,
    ModelTimeout,
    QuotaExceeded,
    ToolError,
)
from .grounding import NO_GROUNDING, GroundingPolicy
from .messages import Message, normalize
from .router import ModelRouter
from .tools import ToolContext, ToolRegistry, ToolResult, ToolSpec

__version__ = "0.1.0"

__all__ = [
    "Assistant",
    "AssistantConfig",
    "AssistantError",
    "ChatTurn",
    "ConfigurationError",
    "DEFAULT_MODEL_CHAIN",
    "DEFAULT_PREFETCH_NOTE",
    "DirectiveParser",
    "DirectiveStreamFilter",
    "GroundingPolicy",
    "MIN_CALL_TIMEOUT",
    "Message",
    "ModelRouter",
    "ModelTimeout",
    "NO_GROUNDING",
    "Prefetch",
    "QuotaExceeded",
    "StreamEvent",
    "ToolContext",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "Usage",
    "normalize",
    "__version__",
]
