# AI Kişiselleştirme Katmanı

Keşfet ve Wishlist'in temel veri mimarisi için
[EXPLORE_AND_RECOMMENDATIONS.md](EXPLORE_AND_RECOMMENDATIONS.md).
Bu belge onun üstündeki AI katmanını anlatır.

---

## 1. Bu "AI" tam olarak nedir

Açık olalım: büyük dil modeli veya sinir ağı yok. Çalışan
şey **içeriğe dayalı (content-based) bir skorlama modeli**
artı kullanıcı davranışından türeyen bir yeniden sıralama
katmanı.

Neden böyle:

- **Yeni kullanıcının hiç etkileşimi yoktur.** Collaborative
  filtering bu noktada çalışmaz — öğreneceği geçmiş yoktur.
  Buna *cold start* deniyor ve senin asıl hedefin olan ML
  modelinin de aynı problemi olacak.
- İçerik tabanlı skor **ilk saniyeden** anlamlı sıralama
  üretir ve aynı zamanda ML modelinin öğreneceği **etiketli
  veriyi** biriktirir: kullanıcıya hangi skorla ne
  gösterdik, ne yaptı.

Kod: [`backend/app/style_engine.py`](../backend/app/style_engine.py)
(skorlama) ve [`backend/app/feed.py`](../backend/app/feed.py)
(sorgu + cursor).

---

## 2. Sekiz arketip

| | Kimlik | Etiket |
|---|---|---|
| 🌿 | `minimalist` | Minimalist & Basic |
| 🛹 | `streetwear` | Streetwear & Urban |
| 💼 | `smart_casual` | Smart Casual & Office |
| 🍷 | `old_money` | Old Money & Elegant |
| 🎨 | `boho` | Boho & Vintage |
| 🏋️ | `athleisure` | Athleisure & Sporty |
| 🖤 | `goth` | Goth & Dark Academia |
| ✨ | `y2k` | Y2K & Trendy |

Kullanıcı **1–3 tarz** seçer. Neden aralık: tek tarz bazı
arketiplerde akışı boşaltıyor (aşağıya bak), 3'ten fazlası
"her şey" demektir ve kişiselleştirmeyi anlamsız kılar.

### Katalog kapsamı — bilinmesi gereken en önemli sınır

Sözlükler yazılmadan önce 707 ürünlük katalogda her arketip
kelimesinin **gerçekten geçip geçmediği ölçüldü.** Sonuç
ciddi biçimde dengesiz:

| Arketip | Badge eşiğini geçen ürün | Durum |
|---|---|---|
| athleisure | 87 | iyi |
| streetwear | 64 | iyi |
| boho | 41 | iyi |
| smart_casual | 37 | iyi |
| minimalist | 23 | **ince** |
| goth | 14 | **ince** |
| old_money | 13 | **ince** |
| y2k | **0** | **ince** |

Y2K kelimelerinin neredeyse hiçbiri katalogda yok:
`crop top`, `halter`, `sequin`, `metallic`, `mini skirt`,
`butterfly`, `rhinestone` — hiçbiri geçmiyor. Katalog
Amazon'un genel giyim kategorisinden geldiği için trend
odaklı etiket taşımıyor.

**Bu bir formül problemi değil, veri problemi.** Yanlış
çözüm: skorları şişirip Y2K seçen kullanıcıya alakasız
ürünleri "%96 uyum" diye göstermek. Uygulanan çözüm:

1. **Havuz sayısı seçim kartında yazıyor** (`pool_count`).
   Kullanıcı "Y2K — 0 PARÇA / AZ SEÇENEK" görüyor.
2. **İnce seçimde uyarı çıkıyor**: "Bu seçimde katalogda
   yaklaşık N parça var. İkinci bir tarz eklersen akışın
   zenginleşir."
3. **Badge eşiğinin altında yüzde gösterilmiyor.** Y2K tek
   başına seçilirse kartlarda hiç yüzde çıkmaz — boş bir
   iddia yerine hiçbir iddia.

Çoklu seçim bu sınırın asıl telafisi: `y2k` tek başına 0
badge üretiyor, `y2k + streetwear` 86 üretiyor. Ölçüldü.

Katalog büyüdükçe kapsam da değişir. Ölçmek için:

```bash
python scripts/09_compute_style_scores.py --dry-run
```

---

## 3. Skor formülü

```
skor = 32                                    taban
     + 38 * (1 - e^(-pozitif_ham / 12))      anahtar kelime (doygunluk)
     + 12 * kelime_kanıtı                    renk uyumu  ← KAPILI
     + 10                                    fiyat bandın içinde
     +  6 * kalite                            rating (yorum sayısıyla ağırlıklı)
     - min(28, negatif_ham * 2.4)            aykırı kelime cezası
```

Kalibrasyonda düzeltilen dört gerçek problem:

**1. Renk artık tek başına stil kanıtı değil.** İlk sürümde
siyah bir çocuk atleti `goth` arketipinde **85.6** ile birinci
sıraya çıktı — yalnızca "siyah" kelimesi yüzünden. Bir ürünün
rengi arketipin paletine uyması, o ürünün o tarza ait
olduğunu göstermez. Renk puanı artık anahtar kelime kanıtıyla
ölçekleniyor:

```python
color_evidence = min(1.0, positive_raw / 6.0)
color_score = raw_color_score * color_evidence
```

Hiç kelime eşleşmesi yoksa renk **0 puan** getirir.

**2. `features` / `description` skorlamaya girmiyor.** Bir
kot pantolonun pazarlama metninde "sneakers ile kombinleyin"
yazdığı için ürün streetwear sanıldı. Başlık ve kategori
ürünün ne *olduğunu* söyler, pazarlama metni ne ile
*giyilebileceğini*.

**3. Kelime eşleşmesi token tabanlı.** Alt dize araması
`"cap"` kelimesini başka kelimelerin içinde buluyordu. Tek
kelimeli anahtarlar için küme üyeliği, çok kelimeli
anahtarlar için alt dize.

**4. Athleisure sözlüğü kısıldı, Goth'un kimliği renkten
dokuya taşındı, Y2K'nin belirsiz kelimeleri atıldı.** Spor
ürünü başlıkları bu kelimeleri birlikte taşıma eğiliminde
("Atletik Şort — Hızlı Kuruyan, Nefes Alabilir, Performans")
ve athleisure 707 ürünün 221'inde en yüksek skoru alıp
katalogu domine ediyordu.

### Çoklu tarzda harmanlama

```python
score = max(seçili tarzların skorları)
      + min(5, 5 * ikinci_skor / birinci_skor)   # çok yönlülük
```

**Neden max, ortalama değil:** kullanıcı tarzları *birlikte*
değil *alternatif* olarak seçti. "Streetwear + Old Money"
seçiminde bir hoodie'nin ortalamaya vurulup düşmesi yanlış
olurdu — hoodie mükemmel bir streetwear parçasıdır ve
kullanıcı onu görmek istiyor.

İkinci skor da eşiği geçiyorsa küçük bir bonus veriliyor:
iki tarza da uyan parça gerçekten daha değerli.

### Gösterim: iki kademe ve 97 tavanı

| Skor | Kartta görünen |
|---|---|
| ≥ 72 | `%86 AI Stil Uyumu` (glassmorphic badge) + gerekçe cümlesi |
| 60–72 | sadece gerekçe cümlesi |
| < 60 | hiçbir şey |

**Tavan 97, 100 değil.** Bileşenlerin toplamı 111'e kadar
çıkabiliyor (temel 95 + çok yönlülük 5 + marka 8 + kategori
6 + fiyat 4). Kırpma olmasa "%100 AI Stil Uyumu" yazardı.
98–100 aralığı bilinçli olarak boş bırakıldı: hiçbir içerik
modeli dürüstçe "%100 uyum" diyemez.

Eşikler tek yerde: `style_engine.MATCH_BADGE_THRESHOLD` ve
`REASON_CHIP_THRESHOLD`. **Frontend eşik hesabı yapmaz**,
hazır metni basar (`build_match_display`).

### Gerekçe cümlesi

Kartta kısa bir çip değil, tam cümle var:

```
"Sık beğendiğin POLO RALPH LAUREN Store ve seçtiğin
 'Smart Casual' tarzına göre önerildi."

"'Streetwear' tarzının Siyah paletine uyduğu için önerildi."

"Seçtiğin birden fazla tarza uyuyor, özellikle 'Y2K'."

"Tarzının dışından bir deneme. Beğenmezsen akıştan
 eleyebilirsin."          ← keşif slotu
```

Kural: **yalnızca gerçekten tetiklenmiş sinyaller cümleye
girer.** Uydurma gerekçe yazmak, yanlış yüzde yazmaktan daha
kötüdür — kullanıcı bir kez yakalarsa bütün sisteme güvenmeyi
bırakır.

---

## 4. Sıralamanın tamamı SQL'de — ve nedeni

Önceki sürümde skor iki parçada üretiliyordu: temel skor
SQL'den, kişiselleştirme Python'da. **Cursor tabanlı
sayfalamaya geçerken bu çalışmıyor:**

> Python sıralamayı değiştiriyorsa, cursor "kaldığım yer"
> bilgisini taşıyamaz. Sayfa 2'de bazı ürünler tekrar eder,
> bazıları hiç görünmez.

Bu yüzden sıralama ifadesinin bütünü SQL'e taşındı:

```sql
final_score = LEAST(97,
      best_score                                    -- en iyi seçili tarz
    + CASE WHEN second_score >= 60                  -- çok yönlülük
           THEN LEAST(5, 5 * second_score / best_score) ELSE 0 END
    + CASE WHEN lower(brand) IN (:top_brands) THEN 8 ELSE 0 END
    + CASE WHEN leaf_category IN (:top_categories) THEN 6 ELSE 0 END
    + CASE WHEN abs(price - :median) <= :median * 0.45 THEN 4 ELSE 0 END
)
```

Python artık skoru **değiştirmiyor**; yalnızca gerekçe
cümlesini kuruyor. Böylece gösterilen yüzde, sıralamada
kullanılan yüzdenin aynısı — kart üzerindeki sayı ile kartın
sırası asla çelişmez.

**Bedeli:** renk *geçmişi* bonusu kaldırıldı (ürün renklerini
SQL'de tespit etmek gerekirdi). Renk yine skora giriyor ama
arketip paleti üzerinden, temel skorun içinde. Bu bilinçli
bir takas: tutarlı sayı > bir bonus bileşeni.

---

## 5. Cursor tabanlı sonsuz akış

**Sayfa numaraları ve ok işaretleri tamamen kaldırıldı.**
`renderPagination()` / `pageButton()` silindi, `#pagination`
öğesi ve CSS'i çıkarıldı.

### Keyset pagination

```sql
WHERE (final_score, product_id) < (:cursor_score, :cursor_id)
ORDER BY final_score DESC, product_id DESC
LIMIT :limit
```

Cursor içeriği (base64, şifreleme değil):

```json
{ "s": 84.4, "p": "B07XYZ123", "n": ["...gösterilmiş kimlikler..."] }
```

**Neden OFFSET değil:**

- OFFSET her sayfada önceki satırları yeniden tarar; sayfa
  numarası büyüdükçe maliyet artar.
- Arada yeni bir etkileşim olursa (kullanıcı bir ürünü
  dislike etti → havuz küçüldü) sıralama kayar; kullanıcı
  aynı ürünü iki kez görür veya bazı ürünler hiç görünmez.

Keyset ikisini de yaşamaz. Ölçüldü: **12 sayfa, 96 ürün, 0
tekrar**, skorlar sayfalar boyunca monoton azalan.

Keşif slotları rastgele olduğu için keyset'e girmiyor;
gösterilmiş kimlikler cursor içinde taşınıyor
(`CURSOR_SEEN_LIMIT = 300`).

### Ürün ızgarasında da sonsuz akış

`/products` uçlu ana ızgara da offset tabanlı sonsuz akışa
geçti. Bunun bir yan etkisi vardı: **sıralama sunucuya
taşınmak zorunda kaldı.**

Önceden yalnızca ekrandaki 12 ürün tarayıcıda sıralanıyordu.
Sonsuz akışta bu görünür biçimde bozuk: her yeni parti
sıralanmamış olarak sona eklenir. Artık
`/products?sort=price_asc` sunucuda sıralıyor ve sıralama
değişince akış baştan yükleniyor.

```
featured | price_asc | price_desc | rating | discount
```

Her sıralamanın sonunda `product_id` var: eşit değerlerde
deterministik sıra sağlıyor, aksi halde sayfalar arası kayma
olur. NULL değerler sona (`NULLS LAST`) — fiyatı olmayan ürün
"en ucuz", puanı olmayan ürün "en yüksek puanlı"
görünmemeli.

### Yarış koşulu — testin yakaladığı gerçek hata

İlk parti çizildikten sonra yedek havuz arka planda
doldurulur. Kullanıcı o sırada kaydırırsa **iki eşzamanlı
dolum** aynı cursor değerini okuyup aynı isteği atıyordu ve
ürünler tekrar ediyordu.

Çözüm: dolumları zincirle.

```js
explore.fillChain = (explore.fillChain || Promise.resolve())
    .then(() => fillExploreBufferOnce(minimum));
```

Ayrıca ikinci bir koruma katmanı: sunucudan gelen bir öğe
zaten ekranda veya yedekteyse alınmıyor. Cursor bunu
halletmeli ama ekranda tekrar eden kart çok görünür bir hata;
iki kat güvenlik ucuz.

---

## 6. Keşif slotları — en önemli tasarım kararı

Feed'in **%25'i bilinçli olarak rastgele** ürüne ayrılmış
(`feed.EXPLORATION_RATIO`).

Neden: akış yalnızca modelin yüksek skorladığı ürünleri
gösterirse, biriken eğitim verisi **modelin kendi
önyargısını tekrar eder**. Model hiç göstermediği ürün
hakkında hiçbir şey öğrenemez. Buna *feedback loop* /
*filter bubble* deniyor ve ileride eğiteceğin modelin
offline skorlarını sistematik olarak yanıltır.

Keşif ürünleri sona konmuyor, **her 4. slota
serpiştiriliyor** — sona konsa her zaman en altta olan ürün
az etkileşim alır ve veri yine yanlı olur (position bias).

Kartta `KEŞFET` etiketiyle işaretli ve gerekçesi farklı:
"Tarzının dışından bir deneme."

---

## 7. Şema

Önceki turdaki `user_interactions` + `wishlist_items` +
`user_preferences` + `product_style_scores` üstüne:

```sql
-- user_preferences
selected_styles JSONB   -- ["streetwear", "y2k"] SIRALI, 1-3
    CHECK (jsonb_array_length(selected_styles) BETWEEN 1 AND 3)

style_archetype         -- BIRINCIL tarz = selected_styles[0]
    CHECK (... IN (8 arketip))

-- user_interactions
selected_styles JSONB   -- etkileşim anındaki bütün tarzlar
style_archetype         -- birincil / eşleşen tarz
match_score             -- gösterilen AI skoru
weight FLOAT NOT NULL DEFAULT 0   -- olayın sinyal ağırlığı

-- user_preferences
avoid_brands JSONB      -- DISLIKE'lardan çıkan markalar
avoid_categories JSONB  -- DISLIKE'lardan çıkan kategoriler
```

### Ağırlıklar

```python
QUICK_BUY     +2.0   # satın alma niyeti — en güçlü sinyal
LIKE          +1.0
VIEW          +0.1
UNLIKE        -0.3   # fikir değiştirmek, reddetmek değil
DISLIKE       -1.0
INITIAL_STYLE  0.0   # tercih beyanı, ürün sinyali değil
```

`weight` neden veritabanında duruyor: eğitim verisi
çıkarılırken ağırlıkları yeniden hesaplamak, o günkü tabloyu
geçmişe uygulamak demek. Ağırlıklar değiştiğinde eski olaylar
eski ağırlıklarıyla kalıyor — olay kaydı ne olduğunu değil
o an ne anlama geldiğini de saklıyor. Export scripti kolonu
okuyor, yoksa `FALLBACK_WEIGHTS`e düşüyor.

`QUICK_BUY` neden `LIKE`ın iki katı: para harcamak beğenmekten
kuvvetli bir tercih beyanı. Sepet olmadığı için satın alma
tek adımda oluyor ve bu sinyal seyrek değil.

**Benzer kategoriye de eksi puan.** DISLIKE yalnızca o ürünü
elemiyor; ürünün markası `avoid_brands`e, kategorisi
`avoid_categories`e girebiliyor ve feed sorgusunda
`BRAND_PENALTY = -7.0` / `CATEGORY_PENALTY = -9.0` olarak
işliyor. Kullanıcı "bu tarz olmaz" derken tek bir ürünü değil
bir kesimi kastediyor.

`selected_styles` neden JSONB ve neden `style_archetype` de
duruyor: dizi kullanıcının gerçek seçimi, tek değer ise
indekslenebilir/raporlanabilir birincil tarz. İkisini
birlikte tutmak sorguları basitleştiriyor.

`product_style_scores` artık **5656 satır** (707 ürün × 8
arketip).

### Göç

```bash
python scripts/08_migrate_ai_layer.py       # match_score, INITIAL_STYLE
python scripts/10_migrate_multi_style.py    # 8 arketip, selected_styles
python scripts/11_migrate_cartless.py       # weight, QUICK_BUY, avoid_*
python scripts/09_compute_style_scores.py   # skorları hesapla
```

`10` idempotenttir, veri silmez ve eski `classic` değerini
`smart_casual`a taşır. 5 kısıt testi koşuyor (4 tarz reddi,
boş dizi reddi, geçersiz arketip reddi...).

### Feed'den dışlanan kategoriler

```python
EXCLUDED_CATEGORY_PATTERNS = (
    "%› Baby%", "%› Boys%", "%› Girls%",
    "%Underwear%", "%Lingerie%", "%Sleep & Lounge%",
    "%Sleepwear%", "%Costumes%", "%Novelty%",
)
```

Kalibrasyonda "ABAFIP Erkek Sissy Tanga" ürünü Y2K
arketipinde **1. sıraya** çıktı. Eşleşen kelimeler doğruydu
(`low rise`, `düşük bel`) ama ürün iç giyim. Stil keşif
akışı dış giyim ve ayakkabı göstermeli. Çocuk ürünleri de
aynı sebeple dışarıda: yetişkin stil arketipine göre
sıralanan bir akışta bebek tulumu göstermek yanlış öneri.

---

## 8. API

| Metot | Uç | Kimlik | Ne yapar |
|---|---|---|---|
| GET | `/api/archetypes` | opsiyonel | 8 stil kartı + **gerçek havuz sayıları** + mevcut seçim |
| POST | `/api/initial-style` | zorunlu | `{selected_styles: [...]}` 1-3 tarz + `INITIAL_STYLE` olayı |
| GET | `/api/explore?limit&cursor&styles` | opsiyonel | **Cursor tabanlı** AI skorlu akış |
| POST | `/api/interact` | zorunlu | Tek uçtan bütün etkileşimler + toast |
| POST | `/api/quick-order` | zorunlu | Sepetsiz tek ürün siparişi + `QUICK_BUY` olayı |
| GET | `/api/preferences` | zorunlu | "AI hakkımda ne biliyor" |
| GET | `/products?sort=` | — | **Sunucu tarafı sıralama** (sonsuz akış için) |

`/api/explore` yanıtı:

```json
{
  "items": [{
    "product": { ... },
    "match_score": 86.71,
    "match_label": "%87 AI Stil Uyumu",
    "reason_label": "Seçtiğin 'Streetwear' tarzı ve ...",
    "matched_style": "streetwear",
    "is_exploration": false,
    "position": 0
  }],
  "meta": {
    "personalized": true,
    "selected_styles": ["streetwear", "y2k"],
    "liked_count": 3,
    "exploration_slots": 2,
    "next_cursor": "eyJzIjo4My45OSwicCI6...",
    "has_more": true
  },
  "exhausted": false,
  "remaining": 620
}
```

Toast metnini backend üretiyor:

```json
"toast": {
  "title": "Favorilerine eklendi",
  "message": "Springrain Store parçaları akışında öne çıkarılacak.",
  "tone": "success"
}
```

Mesaj marka adını içeriyor çünkü o marka gerçekten
`top_brands`'e girdi ve bir sonraki feed sorgusu onu
gerçekten yükseltecek. "Önceliklendirildi" yazıp hiçbir şey
yapmamak kullanıcıyı aldatmak olurdu.

---

## 9. Arayüz

```
İlk ziyaret
   │
   ├─ 800 ms sonra 8 tarzlı picker
   │     ├─ 1-3 seçim, sıra numarası gösterilir
   │     ├─ 4. seçim engellenir + sebebi söylenir
   │     ├─ ince havuzda uyarı + ikinci tarz önerisi
   │     └─ "Şimdilik geç" → bir daha sorulmaz
   │
   ├─ Onay → AI analiz ekranı (~1.1 sn, 3 adım)
   │
   ├─ Skorlu akış: cam badge + gerekçe cümlesi + KEŞFET etiketi
   │
   ├─ Kalp         → kırmızı + nabız + toast + profil güncellenir
   ├─ Thumbs-down  → kart sola kayar → yedekten yenisi
   │                 → 5 sn "GERİ AL" penceresi → sonra sunucuya yazılır
   ├─ Tek tıkla al → tek ekran ödeme → QUICK_BUY
   └─ Aşağı kaydır → sonsuz akış (cursor)
```

**Sepet yok.** Kartta iki eylem var: kalp ve satın al. "Sepete
ekle → sepeti aç → ödemeye geç → 3 adımlı form" zinciri
kaldırıldı; yerine tek ürünlük tek ekran geldi. Wishlist
"sonra al" listesi olarak sepetin yerini alıyor ve alt bar
(`.wishlist-bar`) "devam eden alışveriş" hissini taşıyor.

Bedeli açık: çok ürünlü sipariş yok, sepetin ortalama sipariş
tutarına katkısı yok. Bilinçli takas — buradaki amaç
sürtünmeyi sıfıra indirmek.

**Kırık kalp yerine thumbs-down.** Kırık kalp duygusal bir
ifade ("üzüldüm"); istenen anlam bir değerlendirme ("bu bana
göre değil"). Baş parmağı aşağı çevirmek bunu daha net
anlatıyor ve kalple karışmıyor — iki ikon da kalp olduğunda
kullanıcı yanlış olana basıyordu.

**Animasyonlar** — Framer Motion'un vanilla karşılıkları:

| Framer Motion | Vanilla karşılığı |
|---|---|
| `staggerChildren` | `--stagger` CSS değişkeni + `animation-delay` |
| `exit` | `.dismissing` sınıfı + `swipeLeftOut` keyframe |
| `whileTap` | `:active` + `.pulse` |
| `layout` | `transition` + `transform` |
| geri dönüş | `.restoring` sınıfı + `swipeLeftBack` keyframe |

Çıkış animasyonu: kart düz sola kayarak siliniyor
(`translateX(-110%) scale(.94)`, 400 ms). Geri alınırsa aynı
yol tersine oynuyor — kullanıcı kartın *geri geldiğini*
görüyor, birden beliren bir kart değil.

**İkonların tamamı Lucide.** Vanilla tarafta `app.js`
içindeki `LUCIDE` sözlüğünden satır içi SVG basılıyor
(`icon("thumbs-down")` → `<span data-icon>`), React tarafında
`lucide-react`. Font Awesome bağımlılığı ikonlardan kaldırıldı;
iki tarafın aynı ikon setini kullanması, tasarımın portlar
arasında kaymasını engelliyor.

**Cam badge (glassmorphism):**
`rgba(20,18,14,.55)` + `backdrop-filter: blur(14px)
saturate(180%)` + ince parlak kenar + altın neon gölge.
Üzerinden 4.5 saniyede bir ışık hüzmesi geçiyor. Skor ≥ 90
ise `.high` sınıfıyla parlama güçleniyor.

**`prefers-reduced-motion`** saygı gösteriliyor: nabız, ışık
hüzmesi ve uçuş animasyonu kapanıyor, çıkış basit bir
opacity geçişine dönüyor.

**Misafir kullanıcı** tarz seçebilir; seçim localStorage'da
durur ve giriş yapıldığında sunucuya taşınır. Böylece anonim
satır `user_interactions`'a hiç girmez ve eğitim verisi temiz
kalır. Kalp, thumbs-down ve satın alma giriş istiyor.

### Beğenmedim: geri alma penceresi

Önceki sürümde sıra "önce sunucuya yaz, sonra kartı çıkar"
idi. Artık **hiç yazmıyoruz** — 5 saniye bekliyoruz:

```
tıklama → kart sola kayar → yedekten yenisi gelir
        → toast + "GERİ AL" + süre çizgisi
        → 5 sn dolar   → sunucuya DISLIKE yazılır
        → geri alınır  → hiç yazılmaz, kart eski yerine döner
```

Neden "yaz sonra sil" değil: `user_interactions` append-only
bir olay kaydı ve eğitim verisinin değeri buna dayanıyor.
Silinmiş satırlar bir yana, yanlışlıkla basılan bir tuş
anlamlı bir ML sinyali de değil — hiç yazılmaması daha doğru.

Neden 5 saniye: geri alma isteği ilk bir iki saniyede geliyor.
Daha uzun tutmak kullanıcıyı kararın işlenip işlenmediği
konusunda belirsiz bırakır.

Bedeli: sekme 5 saniye içinde kapanırsa kayıt `pagehide`
üzerinden `keepalive` ile gönderiliyor, ama tarayıcı bunu
garanti etmiyor. Kaybedilen tek bir DISLIKE, yanlış öğrenilmiş
bir tercihten iyi.

Geri alma yalnızca arayüz işi olduğu için ucuz: yerine gelen
kart yedeğin başına iade ediliyor, eski kart eski konumuna
geri konuyor. Sıra bozulmuyor, ekstra istek atılmıyor.

**Kalpte farklı:** iyimser arayüz — anında kırmızı, istek
arkada gider, başarısız olursa işaret geri alınır. Kalp
zaten geri alınabilir (`UNLIKE`), beğenmedim ise pencere
kapandıktan sonra kalıcı.

---

## 10. Eğitim verisi

```bash
python scripts/07_export_training_data.py
```

Kolonlar: `match_score`, `style_archetype`,
`user_archetype`, `user_like_count`, `product_style_score`,
`in_matrix` + ham olay alanları.

> `products`'a **LEFT JOIN**. `INITIAL_STYLE` olayları ürüne
> bağlı olmadığı için INNER JOIN kullanılsa tarz seçimleri
> eğitim verisinden sessizce düşerdi.

Script en yalın başarı ölçüsünü basıyor:

```
LIKE     ortalama gösterilen skor : 86.7
DISLIKE  ortalama gösterilen skor : 83.2
LIKE - DISLIKE skor farkı : +3.5
```

Bu fark pozitif ve büyüyorsa skorlama işe yarıyor. Sıfıra
yakınsa veya negatifse sözlükler yanlış — formülü değiştirme
zamanı.

**Keşif slotları yansız değerlendirme sağlar.** Skoru düşük
olup yine de gösterilen ürünler modelin görmediği bölgeden
örneklerdir. Offline değerlendirmede bu alt kümeyi ayırmak,
skorların gerçek mi yoksa kendi kendini doğrulayan mı
olduğunu gösterir.

**`match_score` ile negatif örnekleme.** VIEW alıp etkileşim
almayan ürünler skorlarıyla kayıtlı. Implicit feedback
modellerinde (BPR, ALS) negatif örnek seçimi kritiktir;
rastgele seçmek yerine "yüksek skorla gösterildi ama
tıklanmadı" örneklerini kullanmak çok daha bilgilendirici.

---

## 11. Bilinen sınırlar

| Konu | Durum |
|---|---|
| **Katalog kapsamı** | En büyük sınır. Y2K'de 0, Goth'ta 14 badge'lik ürün var. Çözüm katalogu genişletmek ya da ürünleri yeniden etiketlemek; formül değiştirmek değil. |
| Kimlik doğrulama | `X-User-Id` başlığı taklit edilebilir. JWT gerekli — artık ortada kişisel zevk profili de olduğu için daha acil. |
| Sözlükler elle yazılmış | Ürün verisinden kümeleme ile çıkarmak daha ölçeklenebilir olur. Yeni arketip eklemek `style_engine.py` düzenlemek demek. |
| Renk geçmişi bonusu yok | Cursor doğruluğu için kaldırıldı (bkz. bölüm 4). Ürün renkleri önceden hesaplanıp bir kolona yazılırsa geri eklenebilir. |
| Keşif oranı sabit | %25. İdeali kullanıcının etkileşim sayısına göre azalması (yeni kullanıcıda çok keşif, olgunda az). |
| Skorlar statik | `product_style_scores` elle yeniden hesaplanıyor. Katalog sık değişiyorsa cron gerekir. |
| DISLIKE penceresi kapandıktan sonra geri alınamaz | 5 saniyelik pencere yazmayı geciktiriyor ama süre dolduktan sonra dönüş yok. Kalıcı geri alma için `UNDISLIKE` türü + "son olay DISLIKE mı" sorgusu gerekir. |
| Sepetsizliğin bedeli | Çok ürünlü sipariş yok. Ortalama sipariş tutarı sepetli bir akışa göre düşük kalabilir; ölçülmesi gerekiyor. |
| Ödeme gerçek değil | `/api/quick-order` yalnızca niyeti kaydediyor, kart bilgisi sunucuya hiç gitmiyor. Gerçek tahsilat için ödeme sağlayıcısı entegrasyonu şart. |
| Cursor boyutu | Gösterilmiş kimlikler cursor içinde taşınıyor, 300'de kesiliyor. Çok uzun oturumlarda keşif slotu tekrarı olabilir. |
