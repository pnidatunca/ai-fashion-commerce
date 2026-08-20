# Keşfet (Explore) + Wishlist + Öneri Sistemi Veri Mimarisi

Bu belge Keşfet akışının, favorilerin ve bunların ürettiği
makine öğrenimi eğitim verisinin nasıl çalıştığını anlatır.

---

## 1. Genel akış

```
   Kullanıcı                Frontend                  Backend                Postgres
   ─────────                ────────                  ───────                ────────

   kart görür  ──────► IntersectionObserver
                       (0.5 görünür + 800ms)
                              │
                              ▼
                       viewQueue (biriktirir)
                              │  2.5 sn / 20 olay
                              ▼
                       POST /interactions/batch ────► record_interactions ──► user_interactions
                                                                                  (VIEW)

   kalp ❤      ──────► POST /wishlist/{id}     ────► add_to_wishlist ──────► wishlist_items
                                                     record_interactions ──► user_interactions
                                                                                  (LIKE)

   beğenmedim ✕ ─────► POST /interactions      ────► record_interactions ──► user_interactions
                       (DISLIKE)                                                  (DISLIKE)
                              │
                              ▼
                       kart animasyonla çıkar
                       yerine yedekten yenisi gelir

   feed ister  ──────► GET /explore            ────► get_explore_feed
                                                     └─ NOT IN (DISLIKE)
                                                     └─ NOT IN (wishlist)
                                                     └─ ORDER BY random()
```

**Tasarım kararı:** iki ayrı tablo var.

| Tablo | Rolü | Yazma biçimi |
|---|---|---|
| `user_interactions` | Olay geçmişi — ML eğitim verisi | **Append-only**: hiç UPDATE/DELETE yok |
| `wishlist_items` | Anlık durum — "şu an favorilerimde ne var" | Ekle / çıkar |

Favoriler `user_interactions`'tan türetilmiyor. Türetmek için her
kullanıcı-ürün çiftinin en son LIKE/UNLIKE olayını bulmak gerekirdi
(pencere fonksiyonu, her kalp ikonu için). Ayrı bir durum tablosu
hem sorguyu tek indekse indiriyor hem de `UNIQUE(user_id, product_id)`
ile aynı ürünün iki kez eklenmesini veritabanı seviyesinde engelliyor.

---

## 2. Şema

### `user_interactions`

```sql
CREATE TABLE user_interactions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id       VARCHAR NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    interaction_type VARCHAR(16) NOT NULL,
    source           VARCHAR(32),          -- explore | detail | grid | wishlist | featured
    position         INTEGER,              -- feed'de kaçıncı karttı
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_user_interactions_type
        CHECK (interaction_type IN ('VIEW', 'LIKE', 'UNLIKE', 'DISLIKE'))
);

CREATE INDEX ix_user_interactions_user_type    ON user_interactions (user_id, interaction_type);
CREATE INDEX ix_user_interactions_user_created ON user_interactions (user_id, created_at);
CREATE INDEX ix_user_interactions_user_product ON user_interactions (user_id, product_id);
```

Alanlarla ilgili notlar:

- **`created_at`, `timestamp` değil.** `timestamp` PostgreSQL'de tip
  adı; kolon adı olarak kullanılabilir ama her sorguda tırnak
  gerektirir ve karışıklık yaratır. Anlamı aynı: olayın zamanı.
  `TIMESTAMPTZ` seçildi, çünkü kullanıcılar farklı saat
  dilimlerinde olabilir ve zaman bazlı train/test bölmesi
  saat dilimi karışıklığına tahammül etmez.
- **`source`** istekte gelmesi zorunlu değil ama modelde bağlam
  özelliği (context feature) olarak değerli: Keşfet'te verilen
  kalp ile ürün detayında verilen kalp aynı güvende değildir.
- **`position`** position bias düzeltmesi için. Feed'in ilk
  kartı doğal olarak daha çok etkileşim alır; bunu bilmeden
  eğitilen model sıralamayı öğrenir, tercihi öğrenmez.
- **`CHECK` kısıtı** yeni bir etkileşim türü eklemek istediğinde
  hem `models.py` içindeki `INTERACTION_TYPES` hem de bu kısıt
  güncellenmeli (`ALTER TABLE ... DROP CONSTRAINT ... ADD CONSTRAINT`).

### `wishlist_items`

```sql
CREATE TABLE wishlist_items (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id VARCHAR NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_wishlist_user_product UNIQUE (user_id, product_id)
);
```

Tabloları oluşturmak için:

```bash
python scripts/06_create_feedback_tables.py
```

Script idempotenttir: yalnızca eksik tabloları oluşturur, mevcut
`products` / `reviews` / `users` tablolarına dokunmaz.

---

## 3. Beğenilmeyen ürünleri dışlayan sorgu

Gereksinim: **DISLIKE edilen ürün bir daha o kullanıcıya
önerilmez.** `user_interactions` append-only olduğu ve DISLIKE
satırları hiç silinmediği için bu dışlama kalıcıdır.

### Uygulanan hâli (PostgreSQL, `NOT IN`)

```sql
SELECT p.*
FROM products p
WHERE p.price IS NOT NULL
  AND p.price > 0
  AND p.image_url IS NOT NULL
  AND p.image_url <> ''

  -- Beğenilmeyenler
  AND p.product_id NOT IN (
      SELECT product_id
      FROM user_interactions
      WHERE user_id = :user_id
        AND interaction_type = 'DISLIKE'
  )

  -- Zaten favorilerde olanlar
  AND p.product_id NOT IN (
      SELECT product_id
      FROM wishlist_items
      WHERE user_id = :user_id
  )

  -- Ekranda duran kartlar (frontend gönderir)
  AND p.product_id NOT IN (:exclude_ids)

ORDER BY random()
LIMIT :limit;
```

SQLAlchemy karşılığı [`crud._apply_feed_filters`](../backend/app/crud.py)
içinde.

### `NOT IN` ile ilgili iki tuzak

1. **NULL zehirlenmesi.** Alt sorgu tek bir NULL döndürürse
   `NOT IN` **tüm sonucu boşaltır** (`x NOT IN (1, NULL)` asla
   TRUE olmaz). Burada güvenliyiz çünkü her iki tabloda da
   `product_id NOT NULL`. Nullable bir kolonla çalışıyorsan
   `NOT EXISTS` kullan.

2. **Ölçek.** Kullanıcı başına on binlerce DISLIKE'a çıkıldığında
   anti-join daha iyi plan üretir:

```sql
SELECT p.*
FROM products p
WHERE NOT EXISTS (
    SELECT 1 FROM user_interactions ui
    WHERE ui.user_id = :user_id
      AND ui.product_id = p.product_id
      AND ui.interaction_type = 'DISLIKE'
)
```

### MongoDB karşılığı

Aynı mantığın belge veritabanı hâli (referans olsun diye —
proje Postgres kullanıyor):

```js
const disliked = await db.collection("user_interactions")
    .distinct("productId", { userId, interactionType: "DISLIKE" });

const wishlisted = await db.collection("wishlist_items")
    .distinct("productId", { userId });

const feed = await db.collection("products").aggregate([
    {
        $match: {
            price:    { $gt: 0 },
            imageUrl: { $nin: [null, ""] },
            productId: { $nin: [...disliked, ...wishlisted, ...onScreen] }
        }
    },
    { $sample: { size: limit } }     // ORDER BY random() karşılığı
]).toArray();
```

### `ORDER BY random()` ne zamana kadar yeterli?

Katalog 728 satır; `random()` ile tam tarama maliyeti ihmal
edilebilir. Katalog ~100 bin satıra çıktığında her istekte tam
tarama yapılır. O noktada seçenekler:

- `TABLESAMPLE SYSTEM (1)` — yaklaşık örnekleme, çok hızlı
- Önceden hesaplanmış `recommendations(user_id, product_id, score)`
  tablosu — ki bu zaten eğittiğin modelin çıktısı olacak

---

## 4. API

Kimlik şu an `X-User-Id` başlığından okunuyor
(`get_current_user` / `get_optional_user`). **Bu başlık istemci
tarafından değiştirilebilir, yani taklit edilebilir.** Projede
henüz JWT yok. Üretime çıkmadan önce yalnızca bu iki
dependency'nin JWT doğrulamasına çevrilmesi yeterli — bütün uçlar
onları kullanıyor.

| Metot | Uç | Kimlik | Açıklama |
|---|---|---|---|
| GET | `/explore?limit=&exclude=` | opsiyonel | Feed. Giriş varsa DISLIKE + favoriler dışlanır |
| POST | `/interactions` | zorunlu | Tek olay. LIKE/UNLIKE gelirse wishlist de senkronlanır |
| POST | `/interactions/batch` | zorunlu | En fazla 100 olay (VIEW için) |
| GET | `/wishlist` | zorunlu | Favoriler, ürün detaylarıyla (`joinedload`, N+1 yok) |
| GET | `/wishlist/ids` | zorunlu | Sadece kimlikler — kalp ikonlarını tek istekte doldurmak için |
| POST | `/wishlist/{product_id}?source=&position=` | zorunlu | Ekle (idempotent) + LIKE kaydı |
| DELETE | `/wishlist/{product_id}?source=` | zorunlu | Çıkar + UNLIKE kaydı |
| GET | `/me/interactions/stats` | zorunlu | Kullanıcının etkileşim dağılımı |
| GET | `/ml/interactions?limit=&offset=&since=` | `X-ML-Token` | Ham olay kaydı (tüm kullanıcılar) |

Notlar:

- `/wishlist/ids` rotası `/wishlist/{product_id}`'den **önce**
  tanımlı olmalı, aksi halde `ids` bir ürün kimliği sanılır.
- `POST /wishlist/{id}` idempotenttir (`ON CONFLICT DO NOTHING`):
  iki sekmeden aynı anda kalp basılırsa tek satır oluşur.
- **`UNLIKE` ≠ `DISLIKE`.** UNLIKE sadece favoriden çıkarır, ürün
  feed'e geri döner. DISLIKE kalıcı dışlamadır.
- `/ml/interactions` tüm kullanıcıların verisini döndürdüğü için
  `.env` içindeki `ML_EXPORT_TOKEN` ile korunuyor; token tanımlı
  değilse uç kapalı (503). Toplu eğitim verisi için HTTP yerine
  export scriptini kullan, doğrudan veritabanından okuyor.

---

## 5. Frontend

Kod [`frontend/app.js`](../frontend/app.js) içinde, sonda yer alan
`KEŞFET / EXPLORE FEED` bölümünde.

**Kart yenileme (yedek havuzu).** Beğenilmeyen kart çıkarken
yerine yeni kart gelmesi gerekiyor. Her seferinde istek atmak
gözle görülür bir boşluk yaratırdı; bu yüzden `explore.buffer`
içinde önceden 8 ürün tutuluyor. Kart çıktığında yedekten
biri alınıyor ve arkaplanda yedek yeniden dolduruluyor.

**VIEW gürültü kontrolü.** Kartın ekranda görünmesi tek başına
"gördü" demek değil; hızlı kaydırmada onlarca kart ekrandan
geçer. İki filtre var:

1. Kart en az %50 görünür ve **800 ms** ekranda kalmalı
   (`VIEW_DWELL_MS`).
2. Aynı `source:product_id` çifti oturum başına bir kez
   kaydedilir (`viewedThisSession`).

**Misafir kullanıcı.** Feed misafire de gösterilir ama kalp veya
beğenmedim'e basıldığında niyet `state.pendingInteraction`
içinde saklanıp giriş ekranı açılır; giriş başarılı olduğunda
işlem kaldığı yerden devam eder. Böylece anonim satır
`user_interactions`'a hiç girmiyor ve eğitim verisi temiz kalıyor.

**İyimser arayüz.** Kalp anında kırmızıya döner, istek arkada
gider; başarısız olursa işaret geri alınır. Beğenmedim'de tersi:
önce sunucuya yazılır, **sonra** kart çıkar — çünkü kaydedilmemiş
bir DISLIKE ürünün geri gelmesine yol açar ve kullanıcı aynı
ürünü tekrar görür.

**Senkronizasyon.** Aynı ürün hem Keşfet kartında hem ürün
detayında görünebilir. `syncWishlistButtons(productId, liked)`
her iki yerdeki kalbi, kart kenarlığını, "FAVORİDE" etiketini ve
header sayacını birlikte güncelliyor.

---

## 6. ML boru hattı

### Veriyi çıkar

```bash
python scripts/07_export_training_data.py
python scripts/07_export_training_data.py --since 2026-09-01
```

Üretilen dosyalar (`data/`, `.gitignore` kapsamında):

| Dosya | İçerik |
|---|---|
| `interactions_raw.csv` | Ham olaylar + kullanıcı ve ürün özellikleri |
| `interactions_labeled.csv` | `weight`, `is_positive`, `is_negative`, `user_idx`, `item_idx` eklenmiş |
| `user_index.csv` | `user_id` → `user_idx` |
| `item_index.csv` | `product_id` → `item_idx` |

Script ayrıca kullanıcı × ürün matrisinin **seyrekliğini** ve
önerilen zaman bazlı bölme noktasını yazdırır.

### Ağırlıklar

`scripts/07_export_training_data.py` içindeki `WEIGHTS` sözlüğü
bir **model kararıdır**, veri değil — deneyerek değiştir:

```python
WEIGHTS = {
    "LIKE":     1.0,   # açık pozitif
    "VIEW":     0.1,   # zayıf sinyal, ilgi belirsiz
    "UNLIKE":  -0.3,   # fikir değiştirdi, nefret değil
    "DISLIKE": -1.0,   # açık negatif
}
```

### Model seçimi

Şu anki veri **implicit feedback** (yıldız puanı yok, davranış
var). Bu, model seçimini belirler:

- **ALS / BPR** (`implicit` kütüphanesi) — yalnızca pozitif
  sinyalle çalışır. DISLIKE'ları eğitime negatif örnek olarak
  vermek yerine, **öneri çıktısından filtrelemek** için kullan;
  zaten `/explore` bunu yapıyor.
- **LightFM** — kullanıcı (`gender`, `age`) ve ürün (`brand`,
  `category`, `price`) özelliklerini de alabildiği için soğuk
  başlangıçta (yeni kullanıcı / yeni ürün) belirgin biçimde daha
  iyi. Export dosyaları bu kolonları zaten içeriyor.

### Bölme

Rastgele bölme öneri sistemlerinde **veri sızdırır**: model
geleceği görmüş olur ve offline skorlar gerçeği yansıtmaz.
Zaman bazlı bölme kullan:

```python
df = pd.read_csv("data/interactions_labeled.csv", parse_dates=["created_at"])
boundary = df.created_at.quantile(0.8)

train = df[df.created_at <  boundary]
test  = df[df.created_at >= boundary]
```

### Modeli geri bağlama

Model eğitildiğinde döngüyü kapatmak için:

1. `recommendations(user_id, product_id, score, generated_at)`
   tablosu oluştur.
2. Modeli periyodik çalıştırıp bu tabloyu doldur.
3. `crud.get_explore_feed` içindeki `ORDER BY random()` yerine
   bu tablodan skora göre sırala — DISLIKE / wishlist dışlama
   filtreleri aynen kalsın.

Böylece Keşfet akışı rastgele bir vitrinden kişiselleştirilmiş
bir öneri akışına dönüşür, arayüzde hiçbir değişiklik gerekmez.

---

## 7. Bilinen sınırlar

| Konu | Durum |
|---|---|
| Kimlik doğrulama | `X-User-Id` başlığı taklit edilebilir. JWT gerekli. |
| Anonim etkileşim | Kaydedilmiyor (bilinçli tercih: FK `user_id` gerektiriyor). Anonim veri de istenirse `session_id` kolonu + nullable `user_id` gerekir. |
| DISLIKE geri alma | Arayüzde yok. Gerekirse `interaction_type='UNDISLIKE'` ekleyip dışlama sorgusunu "son olay DISLIKE mı" biçimine çevirmek gerekir. |
| `ORDER BY random()` | ~100 bin ürüne kadar sorunsuz. Sonrası için bkz. bölüm 3. |
| Soğuk başlangıç | Yeni kullanıcının hiç etkileşimi yok; feed rastgele. `users.gender` / `age` ile içerik tabanlı bir ilk sıralama yapılabilir. |
| Fiyatsız ürünler | Katalogdaki 21 fiyatsız ürün feed havuzuna hiç girmiyor (bozuk kart + kirli veri). |
