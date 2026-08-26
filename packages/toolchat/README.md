# toolchat

Arac cagiran (function calling), **dayanakli** LLM sohbet motoru.
Gemini uzerinde calisir, uygulamaya ozel hicbir sey bilmez.

Bu paket WishNN'in AI alisveris asistanindan cikarildi; orada
gercek kullanicilarla olculmus sorunlara verilen cevaplari
tasiyor. Tek bagimliligi `google-genai`: veritabani, web
cercevesi, ORM veya pydantic'e bagli degildir.

---

## Ne ise yarar

Modele kendi fonksiyonlarinizi tanitirsiniz; model onlari
cagirdikca motor calistirir, sonucu geri verir ve cevabi
kullaniciya hazir halde dondurur. Uzerine su dort sorunu cozer:

| Sorun | Cozum |
|---|---|
| Kota (429) ve kuyruk gecikmesi tek modele baglaninca sohbeti durduruyor | Sirali **model zinciri** + soguma listesi |
| Model var olmayan kayitlari uyduruyor | Kartlar **yalnizca** arac sonucundan uretilir; duzyazi icin ayri denetim |
| Her tur iki LLM cagrisi harciyor | **On arama** (prefetch) ile yaygin durumda tek cagri |
| Arama motoru her zaman "en yakin" sonucu donduruyor, alakasiz olsa bile | Modelin `[SHOW: ...]` karari |

---

## Kurulum

```bash
pip install -e ./packages/toolchat
```

Gemini anahtari: `AssistantConfig(api_key=...)` ya da
`GEMINI_API_KEY` ortam degiskeni.

---

## En kisa ornek

```python
from toolchat import Assistant, AssistantConfig, ToolResult, ToolSpec

def search(args, ctx):
    rows = my_db.search(args["query"], limit=args.get("limit", 6))

    return ToolResult(
        # MODELE giden kompakt temsil
        payload={"found": len(rows), "items": [r.brief() for r in rows]},
        # ARAYUZE giden zengin temsil (modele gitmez)
        cards=[r.card() for r in rows],
    )

assistant = Assistant(
    tools=[
        ToolSpec(
            name="search_catalog",
            description=(
                "Katalogda urun arar. Kullanici bir urun tarif "
                "ettiginde veya oneri istediginde CAGIR. Asla "
                "kendi bilgine dayanarak urun uydurma."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": "Dogal dil tarifi."},
                    "limit": {"type": "integer",
                              "minimum": 1, "maximum": 12},
                },
                "required": ["query"],
            },
            handler=search,
        )
    ],
    system_prompt="Sen bir alisveris asistanisin. ...",
    config=AssistantConfig(card_id_field="product_id"),
)

turn = assistant.run(
    [{"role": "user", "content": "3000 TL alti siyah sneaker"}],
    request=my_session,       # araclara oldugu gibi gecer
)

turn.reply       # kullaniciya gidecek metin
turn.cards       # gosterilecek kayitlar (dedupe + sinirli)
turn.tool_calls  # ["search_catalog"]
turn.model       # cevabi hangi model yazdi
turn.usage       # token sayimi
turn.ungrounded  # uydurulmus olabilecek adlar (bos olmali)
```

Arac tanimlarindaki aciklamalar **model icin** yazilir: ne zaman
cagiracagini oradan ogreniyor.

---

## Tasarim kararlari

### Model zinciri ve soguma

Ucretsiz katmanda kota **model basina** ayri veriliyor
(gemini-3.5-flash icin dakikada 5 istek). Tek modele baglanmak
dakikada iki mesaj demek. Motor 429 veya zaman asimi alan modeli
birakip siradakini deniyor; hata alan model bir sure soguma
listesine giriyor (olmasa her istek once tukenmis modele gidip
bosuna bir tur gecikme yasatirdi).

Zaman siniri **kademeli**: deneyecek baska model varsa cabuk
vazgec (`call_timeout`, 10s), son modeldeysen sabirli ol
(`last_call_timeout`, 25s). Sebep olculdu — ayni onemsiz istek
ust uste `1.27s / 105.52s / 13.37s / 2.61s / 0.66s` dondu; gecikme
uretimde degil kuyrukta.

SDK'nin kendi yeniden denemesi kisiliyor: varsayilan haliyle
429'da ustel bekleyerek defalarca deniyor ve bizim zincir ancak
SDK pes ettikten sonra devreye giriyordu (olculdu: ilk mesaj 143
saniye).

Hepsi tukenirse `QuotaExceeded` (beklemeli), hepsi yavassa
`ModelTimeout` (tekrar denemeli) firlatilir — ikisi ayri tip,
cunku kullaniciya soylenecek sey ve yapilacak is farkli.

### Kartlar neden uydurulamaz

`turn.cards` yalnizca `ToolResult.cards` degerlerinden olusur.
Model bir kimlik uydurup `[SHOW: UYDURMA9]` yazarsa o kimlik
eslesmez ve kart olarak cikmaz. Ekranda gorunen kayit, modelin
gordugu kaydin ta kendisidir.

Duzyazi icin ayri bir katman var (`GroundingPolicy`): cevapta
gecen ama arac sonucunda gecmeyen adlar `turn.ungrounded`
listesine ve loga yaziliyor. **Metin duzeltilmiyor** — cumlenin
ortasindan ad silmek anlami bozar; burada yapilan is tespit ve
kayit.

### `[SHOW: ...]` direktifi

Arama motorlari her zaman "en yakin" sonucu donduruyor. Alakasiz
bir sorguda model dogru davranip "bulamadim" yaziyor, ama arac
sonucundaki kayitlar ekranda kaliyordu. Benzerlik esigi denendi
ve **calismadi** — dagilimlar cakisiyor:

```
gecerli sorgular (n=15): 0.480 ... 0.665
sacma sorgular   (n=10): 0.425 ... 0.529
```

Alakayi en iyi bilen taraf model; o karari makine-okunur
biciminde de istiyoruz. Ek API cagrisi yok. Direktif yoksa
guvenli varsayilan devreye giriyor: hepsi gosterilir.

Sistem promptunuza sunu ekleyin:

```
Cevabinin EN SON satirina hangi kayitlarin gosterilecegini yaz:
    [SHOW: A1, B2]
Hicbiri uygun degilse [SHOW: none] yaz.
```

### On arama (prefetch)

Yaygin durumda iki LLM cagrisini bire indirir: aramayi modele
sormadan once yapip sonucu elinde hazir veriyoruz.

```python
from toolchat import Prefetch

def decide(ctx):
    text = ctx.messages[-1].content
    if not has_search_signal(text):     # "merhaba" -> None
        return None
    return Prefetch(tool="search_catalog", args={"query": text})

Assistant(..., prefetch=decide)
```

Karar sizin, calistirmak motorun. On arama patlarsa sessizce
atlanir ve model araci kendisi cagirir — bu bir hizlandirma,
zorunluluk degil.

Sonuc modele **duz metin sistem notu** olarak veriliyor. Uydurma
bir `FunctionCall`/`FunctionResponse` ikilisi eklemek denendi ve
API reddetti: `400 INVALID_ARGUMENT — Function call is missing a
thought signature`. Gemini 3.x gecmisteki arac cagrilarinda
modelin kendi imzasini bekliyor ve o imzayi biz uretemiyoruz.

### `before_model_call` kancasi

Araclar genellikle veritabani okuyor ve ORM transaction'i acik
kaliyor; araya giren LLM cagrisi kuyrukta dakikalar
bekleyebiliyor ve sunucu bu sirada baglantiyi dusuruyor (Neon'da
yasandi: `idle_in_transaction_session_timeout`).

```python
Assistant(..., before_model_call=lambda request: request.db.rollback())
```

Motor veritabani bilmiyor; kancayi cagiriyor, ne yapilacagina
siz karar veriyorsunuz. Kanca patlarsa sohbet devam eder.

### Akis

```python
for event in assistant.stream(messages, request=req):
    if event.type == "text":
        send(event.text)          # direktif zaten ayiklanmis
    elif event.type == "tool":
        show_badge(event.tool)
    elif event.type == "done":
        cards = event.turn.cards
```

Gecikmenin buyuk kismi ilk harfe kadar geciyor; akista ilk kelime
~1-2 saniyede dusuyor. Arac dongusu akista da calisiyor. Yedek
modele gecis yalnizca **ilk parcadan once** mumkun: bir parca
yayinlandiktan sonra model degistirmek, ekrandaki yarim cumlenin
ustune baska bir modelin cumlesini yazmak olurdu.

---

## Ayarlar

```python
AssistantConfig(
    model_chain=("gemini-3.5-flash", "gemini-3.5-flash-lite",
                 "gemini-3.1-flash-lite"),
    preferred_model=None,    # zincirin BASINA gecer, yedekler durur
    call_timeout=10.0,   # saglayicinin alt siniri; daha kisasi reddediliyor
    last_call_timeout=25.0,
    stream_timeout=60.0,
    cooldown_seconds=60.0,
    max_tool_rounds=4,       # sonsuz donguye karsi
    max_history_messages=16,
    max_cards=8,
    temperature=0.7,
    max_output_tokens=None,
    card_id_field="id",      # kart kimligi: dedupe + [SHOW] eslemesi
)
```

Ortamdan okumak icin:

```python
AssistantConfig.from_env(prefix="CHAT", card_id_field="product_id")
# CHAT_MODEL, CHAT_MODEL_CHAIN, CHAT_CALL_TIMEOUT,
# CHAT_LAST_CALL_TIMEOUT, CHAT_STREAM_TIMEOUT, CHAT_COOLDOWN,
# CHAT_TEMPERATURE, CHAT_MAX_TOOL_ROUNDS, CHAT_MAX_HISTORY,
# CHAT_MAX_CARDS, CHAT_API_KEY (yoksa GEMINI_API_KEY)
```

Bozuk bir env degeri uyari birakip varsayilana duser: yapilandirma
hatasi yuzunden servisin hic acilmamasi, yavas acilmasindan kotu.

Model surumleri **sabit**, `-latest` takma adi kullanilmiyor:
takma ad bir gun sessizce baska bir modele isaret eder ve
asistanin davranisi siz hicbir sey degistirmeden degisir.

---

## Arac argumanlari

Model semaya cogu zaman uyar, ama "cogu zaman" yetmez. Motor
argumanlari semaya gore duzeltir:

| Modelin yazdigi | Sonuc |
|---|---|
| `"limit": "6"` | `6` |
| `"max_price": "3000 TL"` | `3000.0` |
| `"max_price": "3.000"` | `3000.0` (binlik ayirici) |
| `"limit": 99` (maximum 12) | `12` |
| `"gender": "unisex"` (enum disi) | atilir |
| `"renk": "siyah"` (semada yok) | atilir |

Yanlis filtre, filtre yoklugundan kotudur. Zorunlu bir alan
eksikse dokunulmaz — o karari arac verir.

---

## Hatalar

| Tip | Ayrica | Anlami |
|---|---|---|
| `QuotaExceeded` | — | Butun modeller 429. `retry_after` saniye. |
| `ModelTimeout` | `TimeoutError` | Butun modeller yavas. Tekrar denenebilir. |
| `ConfigurationError` | `RuntimeError` | Anahtar/ayar eksik. Kendi kendine duzelmez. |
| `ValueError` | — | Gecmis bos. |

Dis tiplerden miras alinmasi bilincli: bu modulu bilmeyen bir kod
(`except TimeoutError`) yine calisir.

Arac hatalari **firlatilmaz**: modele hata anlatilir, o da
kullaniciya makul bir cevap yazar. Sohbet bir arac hatasi
yuzunden komple olmez.

---

## Test

```bash
cd packages/toolchat && python -m pytest
```

64 test; hicbiri aga cikmiyor. Sahte istemci gercek SDK
tipleriyle (`types.Content`, `types.Part`, `types.FunctionCall`)
cevap uretiyor — sahte bir `Part` testi gecirir ama uretimde
patlardi.

---

## Modulun bilmedigi seyler

Bilincli olarak disarida: oturum/gecmis saklama (durum cagirana
ait), kullanici kimligi, veritabani, HTTP, sema dogrulama,
onbellek. Bunlarin hepsi uygulamaya ozel ve hepsi kancalarla
disaridan verilebiliyor.
