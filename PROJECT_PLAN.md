
# AI-Native Fashion E-Commerce
# Project Plan

## 1. Proje Hedefi

İki kişilik ekip olarak uçtan uca çalışan yapay zekâ destekli bir fashion e-commerce platformu geliştirmek.

İlk hedef bütün sistemi tamamlamak değil.

İlk hedef:

> Kullanıcının ürünleri görüntüleyebildiği ve doğal dil ile istediği ürünü arayabildiği çalışan bir MVP oluşturmak.

---

# 2. MVP Kapsamı

İlk sürüm aşağıdaki özelliklerle sınırlı olacaktır.

### Ürün kataloğu

Ürünler veritabanında tutulacak ve web sitesinde görüntülenebilecek.

### Ürün listeleme

Ana ürün sayfasında ürün kartları gösterilecek.

### Ürün detay sayfası

Bir ürüne tıklandığında:

- ürün adı
- görseli
- fiyatı
- açıklaması
- kategorisi
- özellikleri

görülebilecek.

### Klasik filtreleme

En az:

- kategori
- fiyat
- renk

filtreleri bulunacak.

### Klasik metin araması

Ürün adı veya açıklaması üzerinden temel arama yapılabilecek.

### Semantic Search

Kullanıcı doğal dilde sorgu yazabilecek.

Örneğin:

> "3000 TL altında günlük kullanabileceğim sade siyah sneaker"

Sistem sorguyla alakalı ürünleri getirecek.

---

# 3. MVP'de OLMAYACAK Özellikler

İlk sürümde aşağıdaki özelliklere başlamayacağız:

- AI Shopping Agent
- Personal Stylist
- Virtual Try-On
- Recommendation System
- gelişmiş kullanıcı profilleme
- gerçek ödeme sistemi
- otomatik kombin oluşturma
- fiyat tahmini
- rakip fiyat takibi
- gelişmiş analytics

Bu özellikler MVP tamamlandıktan sonra eklenecektir.

Amaç scope creep'i önlemek ve ilk çalışan sistemi hızlı şekilde ortaya çıkarmaktır.

---

# 4. İlk Teknik Milestone

İlk büyük milestone:

## Kullanıcı doğal dil ile ürün bulabilmeli.

Örnek sorgular:

> "siyah günlük sneaker"

> "yazın giyilecek açık renk gömlek"

> "çok resmi olmayan düğün ceketi"

> "3000 TL altında minimal ayakkabı"

> "kışın kullanılabilecek sıcak mont"

Sistem bu sorgular için alakalı ürünleri göstermelidir.

---

# 5. İlk Geliştirme Sırası

## Phase 0 — Planlama

- GitHub repository oluştur
- README oluştur
- PROJECT_PLAN oluştur
- görev yönetim sistemini oluştur
- coding conventions belirle
- branch yapısını oluştur

---

## Phase 1 — Dataset

Projeye uygun fashion/e-commerce dataset seçilecek.

Dataset değerlendirilirken şu kriterlere bakılacak:

- ürün sayısı
- ürün görsellerinin bulunması
- ürün açıklamalarının bulunması
- kategori bilgileri
- fiyat bilgileri
- marka bilgileri
- renk/özellik bilgileri
- lisans ve kullanım şartları

Hedef:

En az birkaç bin ürün içeren kaliteli bir katalog.

---

## Phase 2 — Product Database

Temel ürün modeli oluşturulacak.

Örnek:

product

- id
- name
- description
- category
- brand
- price
- color
- image
- stock

Dataset temizlenerek veritabanına aktarılacak.

---

## Phase 3 — Backend API

Temel API endpointleri oluşturulacak.

Örnek:

GET /products

GET /products/{id}

GET /categories

GET /search

POST /semantic-search

İlk aşamada backend'in temel görevi ürün verisini frontend'e sunmak olacaktır.

---

## Phase 4 — Basic Frontend

Basit fakat kullanılabilir bir e-commerce arayüzü oluşturulacak.

Sayfalar:

- Home
- Products
- Product Detail
- Search Results

İlk sürümde tasarımın mükemmel olması gerekmiyor.

Öncelik çalışan sistem.

---

## Phase 5 — Traditional Search Baseline

Önce AI kullanılmadan klasik arama sistemi geliştirilecek.

Örneğin:

query = "black sneaker"

veya:

category = sneaker
color = black
max_price = 3000

Bu sistem daha sonra Semantic Search ile karşılaştırılacaktır.

---

## Phase 6 — Semantic Search

Ürünlerin metin bilgileri hazırlanacak.

Örneğin:

Product Search Text:

"Adidas men's black casual sneaker.
Category: sneakers.
Color: black.
Suitable for everyday use.
Price: 2799."

Bu metin embedding modelinden geçirilecek.

Her ürün için bir embedding oluşturulacak.

Kullanıcının sorgusu da embedding'e dönüştürülecek.

Daha sonra sorguya en yakın ürünler bulunacak.

---

# 6. Arama Sistemini Nasıl Test Edeceğiz?

Sadece "güzel sonuç verdi" demek yeterli olmayacak.

Bir evaluation dataset oluşturacağız.

Örneğin 50 kullanıcı sorgusu:

1. "siyah günlük sneaker"
2. "yazlık açık renk gömlek"
3. "uygun fiyatlı kışlık mont"
4. "minimal beyaz spor ayakkabı"
5. "düğünde giyilebilecek sade ceket"

Her sorgu için uygun ürünler belirlenecek.

Daha sonra:

Traditional Search

vs.

Semantic Search

karşılaştırılacak.

---

# 7. İki Kişilik Görev Dağılımı

Görevler tamamen birbirinden ayrılmayacak ancak başlangıçta ağırlıklı sorumluluklar belirlenecek.

## Developer A — AI / Search / Data

Sorumluluklar:

- dataset analizi
- veri temizleme
- embedding pipeline
- semantic search
- vector search
- retrieval evaluation
- ileride image search
- ileride recommendation

---

## Developer B — Application / Backend / Frontend

Sorumluluklar:

- web frontend
- backend API
- database
- product pages
- filters
- cart/favorites altyapısı
- authentication
- deployment

---

## Ortak Alanlar

İki geliştirici birlikte:

- sistem mimarisi
- API contract
- database schema
- AI-backend entegrasyonu
- test
- deployment
- dokümantasyon

konularında çalışacaktır.

---

# 8. AI Search API Contract

AI tarafı frontend ile doğrudan konuşmayacak.

Backend üzerinden kullanılacaktır.

Örnek:

POST /semantic-search

Request:

{
  "query": "3000 TL altında siyah günlük sneaker",
  "limit": 10
}

Response:

[
  {
    "product_id": 1842,
    "score": 0.91
  },
  {
    "product_id": 923,
    "score": 0.87
  }
]

Backend bu product_id değerlerini kullanarak ürün bilgilerini veritabanından çekecektir.

Bu sayede AI sistemi ve uygulama sistemi birbirinden bağımsız geliştirilebilir.

---

# 9. MVP Başarı Kriterleri

MVP tamamlanmış kabul edilecekse:

- ürün kataloğu çalışıyor olmalı
- ürün detay sayfaları çalışmalı
- filtreleme çalışmalı
- klasik arama çalışmalı
- semantic search çalışmalı
- AI arama sonuçları web sitesinde gösterilmeli
- sistem local veya cloud ortamında deploy edilmiş olmalı
- README ve teknik dokümantasyon bulunmalı
- en az temel retrieval evaluation yapılmış olmalı

---

# 10. MVP Sonrası Roadmap

MVP
↓
Image Search
↓
Multimodal Search
↓
User Accounts + Behavioral Tracking
↓
Recommendation System
↓
AI Product Comparison
↓
AI Shopping Assistant
↓
Outfit Generation
↓
Personal Wardrobe
↓
AI Personal Stylist

---

# 11. Uzun Vadeli Mimari

User
↓
Web Application
↓
Backend API
↓
Product Database

AI tarafında:

User Query
↓
Embedding Model
↓
Vector Search
↓
Relevant Products
↓
Ranking / Personalization
↓
Results

Gelecekte:

AI Shopping Assistant
↓
Search Products
↓
Check Product
↓
Check Stock
↓
Compare Products
↓
Get Recommendations
↓
Add to Cart

---

# Current Milestone

## Milestone 0 — Project Definition

Status: In Progress

Sonraki görev:

**Fashion e-commerce ürün datasetinin seçilmesi.**