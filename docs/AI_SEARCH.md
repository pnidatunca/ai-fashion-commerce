# Akıllı Arama (AI Search)

Kullanıcının arama kutusuna yazdığı doğal dil cümlesini
anlayıp aramayı zenginleştiren katman.

Kod:
[`backend/app/query_engine.py`](../backend/app/query_engine.py) (anlama),
[`backend/app/search_service.py`](../backend/app/search_service.py) (sorgu),
`frontend/app.js` içindeki `renderSearchAnalysis` (gösterim).

---

## 1. Üç adım

```
"kadın yazlık renkli elbise arıyorum"
        │
        ├─ 1. ANLA        query_engine.analyze()
        │     dolgu kelimeler atılır, niyetler çıkarılır,
        │     eş anlamlılar genişletilir
        │
        ├─ 2. VEKTÖRLE    embed_query()
        │     ZENGİNLEŞTİRİLMİŞ metin embedding'e gider,
        │     ham cümle değil
        │
        └─ 3. ARA         search_service.search()
              hibrit sıralama + gerekirse filtre gevşetme
```

Örnek çözümleme:

| | |
|---|---|
| Ana terim | `kadın yazlık renkli elbise` |
| Cinsiyet | `women` (sert filtre) |
| Kategori | `dress` (sert filtre) |
| Sezon | `summer` (sıralama bonusu) |
| Desen niyeti | `pattern` (sert filtre, gevşetilebilir) |
| Embedding metni | `kadın yazlık renkli elbise kadın women desenli yazlık patterned summer çiçekli ince floral lightweight` |
| Alternatifler | kadın desenli elbise · kadın çiçekli elbise · kadın çok renkli elbise · kadın yazlık elbise |

---

## 2. Neden backend'de

Sözlükler daha önce `frontend/app.js` içindeydi
(`detectCategoryFromQuery`, `detectColorFromQuery`,
`detectGenderFromQuery`). İki problemi vardı:

1. **Embedding backend'de üretiliyor.** Frontend'deki
   genişletme vektöre hiç giremiyordu — vektör yalnızca
   kullanıcının yazdığı ham cümleyi görüyordu. Yani
   "yazlık → keten, şifon, ince" genişletmesi hiçbir işe
   yaramazdı.

2. **Aynı sözlük iki yerde.** Gün gelip birinin
   güncellenmemesi demek.

Artık tek kaynak `query_engine.py`. Frontend çözümlemeyi
`/api/search` cevabından okuyup gösteriyor, kendi tahminini
yapmıyor.

---

## 3. Düzeltilen gerçek hatalar

### Alt dize eşleşmesi

Eski kod `text.includes(word)` kullanıyordu:

| Sorgu | Eski davranış | Sonuç |
|---|---|---|
| `topuklu ayakkabı` | `"top"` eşleşti → kategori **shirt** | ilk 10 sonuçta **0 ayakkabı** |
| `manto arıyorum` | `"man"` eşleşti → cinsiyet **men** | kadın mantosu hiç gelmiyor |

Aynı hata `style_engine.py`'de de yaşanmıştı (`"cap"` kelimesi
başka kelimelerin içinde bulunuyordu). Çözüm aynı: tek
kelimeli anahtarlar için **token eşliği**, çok kelimeli
anahtarlar için alt dize.

Türkçe ekleme dili olduğu için token eşliği tek başına
yetmiyor (`elbiseler`, `gömlekleri`). 4 harf ve üzeri
anahtarlarda ön-ek eşleşmesi açık; 3 harfli anahtarların
çekimli halleri sözlüğe elle yazıldı.

`top` anahtarı **silindi**: İngilizce ürün başlıklarında meşru
bir kelime ama biz kullanıcı sorgusunu tarıyoruz ve Türkçe
yazan birinin "top" demesi giysi kastetmiyor.

### SQL tarafında da aynı hata

Renk filtresi `ILIKE '%term%'` kullanıyordu. Ölçüldü:

| Desen | Eşleşen ürün | Neden |
|---|---|---|
| `%mor%` | **174** (%24) | "more", "memory", "armor" |
| `\ymor\y` | 0 | — |
| `%red%` | **292** (%40) | "featured", "required", "colored" |
| `\yred\y` | 13 | — |

Yani "mor elbise" araması katalogun dörtte biriyle, "kırmızı"
%40'ıyla eşleşiyordu — **renk filtresi neredeyse hiç
filtrelemiyordu.** Artık kelime sınırlı regex (`~*` + `\y`)
kullanılıyor, aynı 4-harf kuralıyla.

### Kategori deseni takım elbiseyi dış giyim sanıyordu

`"%Coats%"` deseni `"Suits & Sport Coats"` ile de eşleşiyordu.
Sonuç: "manto" aramasında ilk sırada erkek sherwani takımları
çıkıyordu.

Desenler artık `›` ayırıcısıyla dal adına bağlı ve
katalogdan ölçülerek yazıldı. `crud.py`'deki iki kopyası da
düzeltildi.

---

## 4. Anlamsal genişletme

Kullanıcının asıl istediği davranış: "yazlık" diyene
askılı/ince/keten ürünleri de getirmek.

| Niyet | Tetikleyiciler | Genişletme |
|---|---|---|
| Yazlık | yazlık, yaz, summer, plaj, tatil | ince, lightweight, breathable, kısa kollu, askılı, pamuklu, keten, şifon |
| Kışlık | kışlık, kış, winter, soğuk | kalın, warm, polar, fleece, yün, termal, şişme, kapitone |
| Renkli / Desenli | renkli, desenli, çiçekli, baskılı, çizgili | desenli, patterned, çiçekli, floral, baskılı, printed, çok renkli, graphic |
| Kumaş | keten, pamuk, şifon, ipek, kot, deri, triko, dantel | iki dilde karşılıkları |
| Kalıp | oversize, dar, crop, maxi, midi, yüksek bel | slim fit, bol kesim, high waist... |
| Kullanım | ofis, davet, gece, spor, günlük | formal, party, evening, athletic, casual... |

### "renkli" bir renk değil

Ölçüm:

```
renkli      20 ürün
colorful     3 ürün
multicolor   0 ürün      <- literal arama boş
---
desen      103 ürün
print       91 ürün
floral      36 ürün
çiçek       35 ürün      <- gerçek karşılık burada
```

"renkli" kelimesini literal aramak boş dönüyor. Bu yüzden
`renkli` **sert renk filtresine düşmüyor**, desen niyeti
olarak karşılanıyor — kullanıcının istediği davranış da
tam olarak bu.

### Genişletme sınırı ve dönüşümlü dizilim

Embedding'e en fazla 8 terim giriyor (`MAX_EMBED_EXPANSIONS`).
Sebep: embedding anlamları ortalar; 15+ terim "elbise"
niyetini genel bir "yazlık giyim" bulutuna kaydırıyor.

İlk sürüm grupları sırayla tüketiyordu ve bu ölçülebilir bir
hata üretti:

> `kadın yazlık renkli elbise` sorgusunda desen grubu 14
> terim taşıyor, 8 slotun hepsini kapıyordu. Kullanıcının
> **açıkça yazdığı** "yazlık" niyeti embedding'e hiç
> girmiyordu.

Artık her gruptan sırayla birer terim alınıyor: tespit edilen
her niyet embedding metninde temsil ediliyor. Kalan terimler
kaybolmuyor, SQL tarafında leksikal bonusa gidiyor.

### Türkçe karaktersiz yazım

Katalogda `yazlık` 65 ürün, `yazlik` (ASCII) **0 ürün**. Aynı
şekilde `sifon`, `cicek`, `cizgili`, `dugun`, `yuksek bel`
hiç geçmiyor.

Kullanıcı Türkçe karakter kullanmadan yazarsa (yaygın klavye
alışkanlığı) eski sistemde hiçbir şey bulamıyordu. Artık hem
sorgu hem ürün metni ASCII'ye katlanarak karşılaştırılıyor
(`fold()`), ama **orijinal yazım korunuyor** çünkü "yazlık"
ile "yazlik" aynı embedding'i üretmiyor.

---

## 5. Hibrit sıralama

Saf vektör araması yetmiyor: "kadın yazlık elbise"
sorgusunda vektör, başlığında "yazlık" yazan ürünü illa öne
almıyor — "elbise" benzerliği "yazlık" farkını bastırıyor.

```
skor = 100 * (1 - cosine_distance)     anlamsal yakınlık
     + facet bonusları                 kelime eşleşmesi
     + tam ifade bonusu (6)            sorgu başlıkta geçiyor
     + kalite bonusu (max 3)           rating, yorum sayısıyla ağırlıklı
```

Vektör **anlamı**, kelime eşleşmesi **kesinliği** getiriyor.

### Alan ağırlığı

`style_engine.py`'de öğrenilen ders: `features` ve
`description` pazarlama metni taşıyor ve skoru kirletiyor
("sneakers ile kombinleyin" yazan bir kot streetwear
sanılmıştı).

Ama aramada bu alanları tamamen atmak da yanlış: `keten` 9
üründe geçerken 7'si başlıkta, `polyester` 169 üründe
geçerken yalnızca 2'si başlıkta. Kumaş bilgisi çoğu zaman
açıklamada.

Çözüm: **başlık + kategori tam bonus, açıklama + özellikler
yarım bonus.** Güçlü kanıt ile zayıf kanıt aynı ağırlıkta
sayılmıyor.

---

## 6. Gevşetme merdiveni

Kullanıcının istediği "birebir sonuç çıkmazsa alternatif
terimlerle ara" davranışı.

| Aşama | Bırakılan | Etiket |
|---|---|---|
| 0 | — | tam eşleşme |
| 1 | desen zorunluluğu | desen filtresi gevşetildi |
| 2 | renk zorunluluğu | renk filtresi gevşetildi |
| 3 | kategori | kategori filtresi gevşetildi |
| 4 | cinsiyet | yalnızca anlamsal benzerlik |

Gevşetilen filtre **bonusa dönüşüyor**, tamamen kaybolmuyor:
renk filtresi düşse de eşleşen ürünler öne geliyor.

### Çıkarsanan ve açıkça yazılan kısıt aynı değil

Her filtreyi aynı kolaylıkta bırakmak yanlış. "siyah elbise"
arayan biri 2 tane siyah elbise görmeyi, 2 siyah + 4 rastgele
renk görmeye tercih eder. `crud.py`'de bu karar daha önce
alınmıştı ve yorumu duruyor:

> "Kullanıcı bir renk belirttiğinde SADECE o renk gelmeli.
> Yumuşak sıralama denenmişti ama 'beyaz gömlek' arayıp
> mavi/siyah ürünlerin de listede çıkmasına yol açtı."

Bu yüzden eşik filtrenin **kaynağına** göre değişiyor:

- **Çıkarsanan** kısıt (desen niyeti — kullanıcı "renkli"
  yazdı, "desenli" demedi) → sonuç azsa bırakılır (< 6).
- **Açıkça yazılan** kısıt (renk, kategori, cinsiyet) →
  yalnızca **sıfır** sonuçta bırakılır.

### Var olmayan kısıt "gevşetildi" diye yazılmıyor

Bir aşamanın numarası tek başına "şunu gevşettim" demek
değil: kullanıcı renk yazmadıysa renk aşamasından geçmek
hiçbir şeyi değiştirmiyor. Etiket ancak kısıt gerçekten
varsa yazılıyor — yoksa arayüzde "desen filtresi gevşetildi"
yazıp desen niyeti hiç olmamış oluyordu.

Var olmayan kısıtı bırakan aşamalar ayrıca **atlanıyor**:
aynı sorguyu ikinci kez çalıştırmak boş SQL turu demek.

### Sayfalama tutarlılığı

Merdiven sonuç **sayısına** göre karar veriyor, bu yüzden
sayfa 2'de yeniden çalıştırılırsa farklı bir aşamada durabilir
ve ürünler tekrar eder. `feed.py`'deki cursor dersinin aynısı.

Çözüm: çözülen aşama cevapta dönüyor (`meta.stage`), sonraki
sayfa onu `stage` parametresi olarak geri gönderiyor.

---

## 7. API

| Metot | Uç | Ne yapar |
|---|---|---|
| GET | `/api/search?q&limit&offset&stage` | Çözümleme + hibrit arama |
| GET | `/api/search/analyze?q` | **Yalnızca çözümleme** — veritabanına ve Gemini'ye dokunmaz |

`/api/search/analyze` sözlük kalibre ederken ve test yazarken
gerekli: "bu sorgudan ne anladın" sorusunu bedava sorabilmek
lazım, aksi halde her deneme bir Gemini çağrısı.

Cevap:

```json
{
  "query": {
    "raw": "kadın yazlık renkli elbise arıyorum",
    "cleaned": "kadın yazlık renkli elbise",
    "gender": "women",
    "category": "dress",
    "colors": [],
    "season": ["summer"],
    "patterns": ["pattern"],
    "embed_text": "kadın yazlık renkli elbise kadın women desenli yazlık ...",
    "alternatives": ["kadın desenli elbise", "kadın çiçekli elbise"],
    "chips": [
      {"kind": "gender",  "label": "Kadın",  "strict": true},
      {"kind": "season",  "label": "Yazlık", "strict": false}
    ],
    "note": "Birebir \"renkli\" yazmayan ama desenli, çiçekli ve baskılı ürünler de sonuçlara dahil edildi..."
  },
  "items": [{
    "product": { },
    "similarity_score": 0.625,
    "search_score": 80.04,
    "reasons": ["Yazlık", "Renkli / Desenli"]
  }],
  "meta": {
    "stage": 0,
    "stage_label": "tam eşleşme",
    "relaxed": [],
    "min_results": 6,
    "has_more": true,
    "semantic": true
  }
}
```

Eski `/products/semantic-search` ve `/products/search` uçları
**olduğu gibi duruyor** (klasik arama modu ve mevcut testler
onlara bağlı).

### Embedding önbelleği

Her arama bir Gemini çağrısı demek: hem para hem gecikme.
Aynı sorgu sürekli tekrar ediyor — sonsuz akışta sayfa 2/3,
popüler sorgular, gevşetme merdiveninin aynı vektörü tekrar
kullanması.

256 girişli süreç içi LRU önbellek var. Ölçülen etki:

```
yeni uç (önbellekli)         1.13 s
eski uç (önbelleksiz)        2.62 s
```

`embed_query()` ayrıca **hata fırlatmıyor**, `None` dönüyor.
API anahtarı eksikse veya servis hata verirse arama
tamamen çökmek yerine kelime eşleşmesine düşüyor ve bunu
kullanıcıya söylüyor (`meta.semantic = false`).

---

## 8. Arayüz

Arama sonuçlarının üstünde **AI analiz paneli**:

```
┌────────────────────────────────────────────────────────┐
│ ● AI ARAMA ANALİZİ    "kadın yazlık renkli elbise      │
│                        arıyorum" → "kadın yazlık       │
│                        renkli elbise"                  │
│                                                        │
│  [KADIN] [ELBİSE]  ┆YAZLIK┆ ┆RENKLİ / DESENLİ┆        │
│   ▲ dolu = sert filtre   ▲ kesikli = sıralama tercihi  │
│                                                        │
│  Birebir "renkli" yazmayan ama desenli, çiçekli ve     │
│  baskılı ürünler de sonuçlara dahil edildi.            │
│                                                        │
│  ŞUNLARI DA DENE  (kadın desenli elbise) (kadın ...)   │
└────────────────────────────────────────────────────────┘
```

**Neden gösteriyoruz:** sorguyu sessizce değiştiren bir arama
kullanıcıyı şaşırtır. "renkli" yazıp desenli ürünler gelince
sebebinin görünmesi lazım. Ayrıca yanlış anlaşılma olursa
kullanıcı bunu görüp sorguyu düzeltebiliyor.

Sert / yumuşak ayrımı görsel: dolu çerçeve o şartı taşımayan
ürünün hiç gelmediğini, kesikli çerçeve yalnızca sıralamayı
etkilediğini anlatıyor.

Filtre gevşetildiyse **söylüyoruz**. Sessizce düşürmek,
kullanıcının "ben kırmızı istemiştim" demesine yol açar.

Ürün kartlarında da kısa gerekçe etiketi var (`Yazlık ·
Renkli / Desenli`) — yalnızca gerçekten tetiklenmiş
gerekçeler. Uydurma gerekçe yazmak, yanlış yüzde yazmaktan
kötüdür.

### Sıralama menüsü AI aramada devre dışı

Anlamsal arama sonuçları alaka düzeyine göre sıralanır;
üzerine "fiyat artan" uygulamak bu sırayı yok eder.

Eski kodda `sort` parametresi semantic uca gönderiliyordu ama
uç onu hiç okumuyordu — menü **sessizce hiçbir şey
yapmıyordu**. Artık AI aramada devre dışı ve sebebi
`title` olarak yazıyor. Sessiz ölü kontrol, çalışmayan bir
özellikten daha kötü: kullanıcı seçtiğini sanıp yanlış
sonuca güvenir.

---

## 9. Ölçüm

`scripts/12_eval_search.py` önce/sonra karşılaştırması
yapıyor. Eski frontend mantığı aynen taklit ediliyor
(silinen `detect*` fonksiyonları), böylece karşılaştırma
gerçek öncesi-sonrası oluyor.

Ölçüt: ilk 10 sonuçta niyetin **başlık + kategoride**
karşılığı var mı.

```
SORGU                            ÖLÇÜT       YENİ    ESKİ
kadın yazlık renkli elbise       yazlık      10/10    9/10
                                 desenli      9/10    6/10
kadin yazlik renkli elbise       yazlık      10/10    9/10
  (Türkçe karaktersiz)           desenli      9/10    6/10
erkek kışlık kalın mont          kışlık      10/10   10/10
topuklu ayakkabı                 ayakkabı    10/10    0/10   <--
manto arıyorum                   dış giyim   10/10   10/10
çiçekli midi elbise              desenli     10/10    6/10
--------------------------------------------------------------
TOPLAM                                    138/140  116/140
                                            %98.6    %82.9
```

Not: vektör benzerliğinde beraberlik olduğunda sıralama
değişebildiği için sayılar koşudan koşuya ±1 oynayabiliyor.

`topuklu ayakkabı` satırı en çarpıcı: eski sistem
`category=shirt` gönderip **hiç ayakkabı döndürmüyordu**.

---

## 10. Bilinen sınırlar

| Konu | Durum |
|---|---|
| **Katalogda renk bilgisi çok az** | 41 elbisenin yalnızca 2'si "siyah/black" kelimesini geçiriyor. Renk filtresi bu yüzden doğal olarak ince sonuç veriyor — formül değil veri problemi. Çözüm: ürünlere renk kolonu eklemek. |
| Sözlükler elle yazılmış | Ürün verisinden çıkarmak daha ölçeklenebilir olur. Yeni bir niyet eklemek `query_engine.py` düzenlemek demek. |
| Regex indeks kullanmıyor | `~*` karşılaştırması trigram/GIN indeksinden yararlanamaz, her satırı tarar. 728 üründe önemsiz; on binlerde tsvector veya materyalize edilmiş facet kolonları gerekir. |
| Merdiven birden çok SQL turu | En kötü durumda 4 vektör taraması. Aynı embedding tekrar kullanılıyor (yeni API çağrısı yok) ama SQL tekrar koşuyor. |
| Fiyat niyeti yok | "uygun fiyatlı", "500 TL altı" gibi sorgular anlaşılmıyor. `uygun` kelimesi yalnızca `fiyat` takip ederse korunuyor; sayısal aralık çıkarma yok. |
| Çocuk / bebek ürünleri elenmiyor | Keşfet akışı bunları dışlıyor (`EXCLUDED_CATEGORY_PATTERNS`) ama arama dışlamıyor: kullanıcı aradıysa katalogda ne varsa görüyor. "elbise" araması bebek elbisesi de getirebilir. |
| Yazım hatası toleransı yok | "elbse" hiçbir şey bulmaz. Trigram benzerliği (`pg_trgm`) veya Levenshtein eklenebilir. |
