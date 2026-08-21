# Referans Portlar — Prisma / Mongoose / React

Bu klasördeki dosyalar **çalışan sistemin portudur, kaynağı
değildir.** Uygulamaya bağlı değiller; hiçbiri çalışan siteyi
etkilemez.

## Neden burada duruyorlar

Projenin gerçek mimarisi:

| Katman | Gerçek | Bu klasördeki port |
|---|---|---|
| Şema | SQLAlchemy — [`backend/app/models.py`](../../backend/app/models.py) | `schema.prisma`, `mongoose-models.js` |
| Skorlama | [`backend/app/style_engine.py`](../../backend/app/style_engine.py) | (port yok — Python'da kalıyor) |
| Feed sorgusu | [`backend/app/feed.py`](../../backend/app/feed.py) | `mongoose-models.js` içinde `getExploreFeed` |
| API | FastAPI — [`backend/app/main.py`](../../backend/app/main.py) | (aynı uçlar kullanılıyor) |
| Arayüz | Vanilla JS — [`frontend/app.js`](../../frontend/app.js) | `react/*` |

Prisma/Mongoose ve React tarafına geçmek istersen bu dosyalar
başlangıç noktası. Alan adları, kısıtlar, indeksler ve uç
yolları çalışan sistemle birebir aynı tutuldu.

## Dosyalar

```
schema.prisma            Prisma şeması — 7 model, 2 enum (8 arketip)
mongoose-models.js       Mongoose şemaları + $nin/cursor feed sorgusu
react/
  auraApi.js             API istemcisi, VIEW kuyruğu, tarz deposu
  ToastProvider.jsx      Toast context (sağ alt) + geri alma butonu
  StylePickerModal.jsx   8 tarzlı çoklu seçim modalı (1-3)
  AiAnalyzing.jsx        "AI tarzını analiz ediyor" ekranı
  ExploreCard.jsx        Glassmorphic AI badge + Heart/ThumbsDown + tek tıkla al
  useExplore.js          Cursor tabanlı sonsuz akış + geri alma penceresi
  QuickCheckout.jsx      Sepetsiz tek ekran satın alma
  WishlistBar.jsx        Sepetin yerini alan favori odaklı alt bar
  ExploreFeed.jsx        Hepsini birleştiren bölüm
```

## React tarafını çalıştırmak

```bash
npm create vite@latest aura-web -- --template react
cd aura-web
npm install framer-motion lucide-react
# react/ içindeki dosyaları src/explore/ altına kopyala
echo "VITE_API_BASE=http://127.0.0.1:8000" > .env
npm run dev
```

İkonların tamamı `lucide-react`. Vanilla sürümde aynı ikonlar
[`frontend/app.js`](../../frontend/app.js) içindeki `LUCIDE`
sözlüğünden satır içi SVG olarak basılıyor — iki taraf aynı
ikon setini kullanıyor, bir tarafta Font Awesome bir tarafta
Lucide olması karışıklık yaratırdı.

```jsx
// src/App.jsx
import { ToastProvider } from "./explore/ToastProvider";
import ExploreFeed from "./explore/ExploreFeed";

export default function App() {
    return (
        <ToastProvider>
            <ExploreFeed />
        </ToastProvider>
    );
}
```

CSS'i ayrıca taşımak gerekiyor. Bileşenler
[`frontend/styles.css`](../../frontend/styles.css) içindeki şu
bölümlerin class adlarını kullanıyor:

- `AI GORSEL DILI` (`.ai-chip`, `.ai-dot`)
- `COK SECIMLI TARZ SECIMI` (`.archetype-*`, `.archetype-check`, `.archetype-pool`)
- `AI ANALIZ EKRANI` (`.ai-analyzing`, `.ai-orbit`)
- `GLASSMORPHIC AI BADGE` (`.explore-match`, `.explore-match.high`)
- `AI GEREKCE CUMLESI` (`.explore-reason`)
- `KART ANIMASYONLARI` (`.explore-card`)
- `SONSUZ AKIS` (`.feed-sentinel`, `.feed-more`)
- `TOAST — SAG ALT` (`.toast-*`, `.toast-undo`, `.toast-timer`)
- `LUCIDE IKONLARI` (`[data-icon] svg` boyutlandırması)
- `TEK EKRAN HIZLI SATIN ALMA` (`.quick-panel`, `.quick-section`, `.quick-success`, `.card-quick-buy`, `.card-heart`)
- `WISHLIST ODAKLI ALT BAR` (`.wishlist-bar*`)
- `BEĞENMEDİM: SOLA KAYARAK ÇIKIŞ` (`.dismissing`, `.restoring`)

## Framer Motion kullanımı

| Nerede | Ne için |
|---|---|
| `StylePickerModal` | `staggerChildren` ile 8 kartın kademeli girişi, `whileHover`/`whileTap`, seçim tikinin yay animasyonu |
| `ExploreCard` | `custom` ile kademeli giriş gecikmesi, `exit` ile **sola kayarak** çıkış, `layout` ile kalan kartların kayması |
| `ExploreFeed` | `AnimatePresence mode="popLayout"` — kart silindiğinde çıkış animasyonu oynatılıyor |
| `ToastProvider` | Sağdan kayarak girme/çıkma, `layout` ile yığın kayması, `scaleX` ile geri alma süre çizgisi |
| `AiAnalyzing` | Üç halkanın eş zamanlı olmayan sonsuz dönüşü |
| `QuickCheckout` | Panelin aşağıdan gelmesi, onay işaretinin yay animasyonu |
| `WishlistBar` | `AnimatePresence` ile alttan girme, `layout` ile küçük görsellerin kayması |

Vanilla sürümde bunların hepsi CSS keyframe + `--stagger`
değişkeni ile yapıldı; karşılık tablosu
[AI_PERSONALIZATION.md § 9](../AI_PERSONALIZATION.md) içinde.

## Portlarda bilinçli bırakılan farklar

**Prisma → enum.** SQLAlchemy tarafında `CHECK` kısıtı var;
Prisma'da enum daha temiz ve Postgres'te enum CHECK'ten daha
katı. Karşılık olarak yeni bir arketip eklemek migration
gerektirir.

**Prisma → koşullu NOT NULL ve dizi uzunluğu yok.** İki kısıt
Prisma'da ifade edilemiyor, migration dosyasına elle SQL
eklenmeli:

```sql
CHECK (interaction_type = 'INITIAL_STYLE' OR product_id IS NOT NULL)
CHECK (jsonb_array_length(selected_styles) BETWEEN 1 AND 3)
```

İlki olmadan boş `productId` taşıyan `LIKE` kayıtları eğitim
verisini sessizce bozar.

**Prisma → `selectedStyles` Json, enum dizisi değil.** Prisma'da
enum dizisi native Postgres enum array'i gerektiriyor ve
migration'ı zorlaştırıyor. İçerik uygulama katmanında
doğrulanıyor (`style_engine.normalize_selected_styles`).

**Mongoose → `$nin` bellek maliyeti.** Postgres'te dislike
listesi bir alt sorgudur, veri veritabanından hiç çıkmaz.
Mongo'da diziyi belleğe alıp geri göndermek gerekiyor.
Kullanıcı başına binlerce DISLIKE'ta bu dizi sorguyu şişirir;
o noktada `$lookup` ile anti-join'e geçilmeli.

**Mongoose → keyset cursor `$lt` ile.** Postgres'te
`(final_score, product_id) < (:s, :p)` satır karşılaştırması
var; Mongo'da tek alanla (`bestScore: { $lt: cursor.s }`)
kuruldu. Skor eşitliğinde ayırt edicilik zayıflar; kesin
sonuç için `$expr` ile iki alanlı karşılaştırma gerekir.

**Mongoose → referans bütünlüğü yok.** Ürün silindiğinde
etkileşim kayıtları yalnız kalır. Postgres'te
`ON DELETE CASCADE` bunu otomatik yapıyor.

**React → eşik hesabı yok.** Kart hangi badge'i göstereceğine
karar vermiyor; backend hazır metni gönderiyor
(`match_label`, `reason_label`). Eşikler tek yerde:
[`style_engine.py`](../../backend/app/style_engine.py). İki
yerde eşik tutmak, gün gelip birinin güncellenmemesi demek.

**React → geri alma penceresi yazmayı geciktiriyor.**
`useExplore.dislike` sunucuya hemen yazmıyor; kaydı 5 saniye
bekletiyor (`UNDO_WINDOW_MS`) ve kullanıcı geri alırsa hiç
yazmıyor. Alternatif "yaz sonra sil" olurdu ama
`user_interactions` append-only bir olay kaydı ve eğitim
verisinin değeri buna dayanıyor. Ayrıca yanlışlıkla basılan
bir tuş anlamlı bir ML sinyali değil.

Bedeli: sekme 5 saniye içinde kapanırsa kayıt `pagehide`
üzerinden gönderiliyor (`keepalive`), ama tarayıcı bunu
garanti etmiyor. Kaybedilen tek bir DISLIKE, yanlış öğrenilmiş
bir tercihten iyi.

**React → sepet yok.** `QuickCheckout` tek ürün alıyor,
sepet state'i hiç yok. Wishlist "sonra al" listesi olarak
sepetin yerini alıyor; `WishlistBar` de "devam eden alışveriş"
hissini taşıyor. Bedeli açık: çok ürünlü sipariş ve sepet
üzerinden gelen ortalama sipariş tutarı artışı yok. Bilinçli
takas — buradaki amaç sürtünmeyi sıfıra indirmek.

**React → cursor ref'te, state'te değil.** `cursor`,
`buffer` ve `hasMoreRef` render'ı etkilemediği için `useRef`
içinde. State'e koymak her dolumda gereksiz render tetiklerdi.
Dolumlar `fillChain` ref'i ile zincirlenmiş — eşzamanlı iki
dolum aynı cursor'ı kullanıp ürünleri tekrar ediyordu.

## Kimlik doğrulama uyarısı

Her iki portta da kimlik `X-User-Id` başlığından okunuyor,
çünkü çalışan backend şu an böyle çalışıyor. **Bu başlık
istemci tarafından değiştirilebilir.** Üretime çıkmadan önce
JWT'ye geçilmeli; React tarafında dokunulacak tek yer
`auraApi.js` içindeki `authHeaders()`.
