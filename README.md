# AI-Native Fashion E-Commerce Platform

Yeni nesil, yapay zekâ destekli ve kişiselleştirilmiş bir e-commerce deneyimi geliştirmeyi amaçlayan iki kişilik bir proje.

Projenin temel amacı, kullanıcıların yalnızca klasik kategori ve filtreler aracılığıyla değil; doğal dil, görseller ve kişisel tercihleri üzerinden ürün keşfedebilmesini sağlamaktır.

---

## Problem

Geleneksel e-commerce sitelerinde kullanıcıların ürün bulabilmesi için genellikle:

- kategori seçmesi,
- fiyat aralığı belirlemesi,
- renk seçmesi,
- marka seçmesi,
- çok sayıda filtre kullanması

gerekir.

Ancak kullanıcı çoğu zaman tam olarak hangi filtreleri seçmesi gerektiğini bilmez.

Örneğin kullanıcı aslında şunu söylemek isteyebilir:

> "3000 TL altında, günlük kullanabileceğim, siyah ve sade bir sneaker istiyorum."

Klasik bir arama sistemi bu isteğin anlamını tam olarak değerlendiremeyebilir.

Bu proje, kullanıcının ne istediğini doğal biçimde ifade edebilmesini ve sistemin bu isteğe uygun ürünleri bulmasını hedeflemektedir.

---

## Projenin Vizyonu

Kullanıcının filtrelerle ürün aramak zorunda olmadığı; ne istediğini:

- yazarak,
- fotoğraf göstererek,
- yapay zekâ ile konuşarak

anlatabildiği kişiselleştirilmiş bir alışveriş platformu oluşturmak.

Uzun vadede sistem yalnızca ürün arayan değil, kullanıcının alışveriş kararlarına yardımcı olan bir AI Shopping Assistant'a dönüşecektir.

---

# MVP — İlk Çalışan Sürüm

İlk sürümde bütün özellikleri aynı anda geliştirmek yerine, projenin temelini oluşturan küçük fakat uçtan uca çalışan bir sistem oluşturulacaktır.

## 1. Ürün Kataloğu

Sistemde gerçek veya gerçekçi bir fashion e-commerce ürün kataloğu bulunacaktır.

Her ürün için mümkün olduğunca şu bilgiler tutulacaktır:

- ürün ID
- ürün adı
- açıklama
- kategori
- marka
- fiyat
- görsel
- stok bilgisi
- renk
- diğer ürün özellikleri

---

## 2. Temel E-Commerce Arayüzü

Kullanıcı:

- ürünleri listeleyebilecek,
- ürün detaylarını görüntüleyebilecek,
- kategoriye göre filtreleyebilecek,
- fiyat aralığı belirleyebilecek,
- ürün arayabilecek.

İlerleyen aşamalarda:

- kullanıcı hesabı,
- favoriler,
- sepet,
- sipariş sistemi

eklenecektir.

---

## 3. Klasik Ürün Arama

Sistem ilk olarak geleneksel filtreleme ve arama özelliğine sahip olacaktır.

Örneğin:

- kategori = sneaker
- renk = siyah
- fiyat < 3000 TL

gibi filtreler kullanılabilecektir.

Bu sistem daha sonra AI tabanlı arama sistemimiz için karşılaştırma noktası olacaktır.

---

## 4. Doğal Dil ile Ürün Arama

Projenin ilk temel AI özelliği anlamsal ürün arama olacaktır.

Kullanıcı:

> "Yazın giyebileceğim rahat ve açık renk bir ayakkabı"

gibi bir sorgu yazabilecektir.

Sistem yalnızca kelimeleri eşleştirmek yerine sorgunun anlamını değerlendirecek ve ürün kataloğundaki en alakalı ürünleri getirecektir.

Örneğin kullanıcının "bol kesim" yazması durumunda açıklamasında "oversized" bulunan bir ürün de uygun sonuç olarak değerlendirilebilecektir.

---

# Temel Kavramlar

## Semantic Search

Semantic Search, kelimelerin birebir aynı olup olmadığı yerine anlamlarının birbirine ne kadar yakın olduğuna bakarak arama yapılmasıdır.

Örneğin:

> "günlük siyah spor ayakkabı"

ile

> "black casual sneaker"

anlam olarak birbirine yakın kabul edilebilir.

---

## Embedding

Embedding, bir metin veya görselin anlamını bilgisayarın karşılaştırabileceği sayısal bir temsile dönüştürme yöntemidir.

Örneğin bir ürün açıklaması ve kullanıcı sorgusu embedding'e dönüştürüldükten sonra birbirlerine ne kadar yakın oldukları hesaplanabilir.

Bu sayede anlam olarak benzer ürünler bulunabilir.

---

## Retrieval

Retrieval, büyük bir ürün kataloğundan kullanıcının sorgusuyla en alakalı ürünleri bulup getirme işlemidir.

Örneğin:

50.000 ürün

↓

kullanıcı sorgusu

↓

en alakalı 20 ürün

---

# Gelecekte Eklenecek Özellikler

MVP tamamlandıktan sonra sistem aşamalı olarak geliştirilecektir.

## Görselle Ürün Arama

Kullanıcı bir ürün fotoğrafı yükleyerek:

> "Bunun gibi ürünleri bul."

diyebilecektir.

Sistem yüklenen görselle katalogdaki ürünleri karşılaştırarak benzer ürünleri gösterecektir.

---

## Multimodal Search

Metin ve görüntü aynı anda kullanılabilecektir.

Örneğin kullanıcı bir ceket fotoğrafı yükleyip:

> "Bunun gibi ama siyah ve 2500 TL altında."

diyebilecektir.

---

## Recommendation System

Sistem kullanıcının:

- görüntülediği ürünler,
- favorileri,
- satın aldığı ürünler,
- kategorileri,
- fiyat tercihleri

gibi davranışlarından yararlanarak kişiselleştirilmiş ürün önerileri sunacaktır.

Örneğin:

> "Bunları beğenebilirsin."

bölümü oluşturulacaktır.

---

## AI Shopping Assistant

Kullanıcı sistemle konuşarak alışveriş yapabilecektir.

Örneğin:

> "6000 TL bütçem var. Düğünde giyebileceğim ama çok resmi olmayan bir kombin hazırla."

AI Shopping Assistant:

1. kullanıcının ihtiyacını anlayacak,
2. ürün kataloğunda arama yapacak,
3. fiyat ve stokları kontrol edecek,
4. uyumlu ürünleri bir araya getirecek,
5. bütçeye uygun alternatifler sunacaktır.

---

## AI Personal Stylist

Kullanıcı kendi gardırobundaki ürünleri sisteme ekleyebilecektir.

Örneğin:

> "Bu pantolonla ne giyebilirim?"

veya

> "Gardırobumda bunlar var. Yeni olarak ne almam mantıklı?"

gibi sorular sorabilecektir.

Sistem mevcut kıyafetleri ve mağaza kataloğunu birlikte değerlendirecektir.

---

## Product Comparison

Kullanıcı iki veya daha fazla ürünü AI yardımıyla karşılaştırabilecektir.

Örneğin:

> "Bu iki monttan hangisi benim için daha uygun?"

Sistem:

- fiyat,
- özellikler,
- kullanıcı tercihleri,
- kullanım amacı

gibi bilgileri kullanarak açıklamalı karşılaştırma yapacaktır.

---

# Uzun Vadeli Hedef

Projenin nihai amacı klasik bir e-commerce sitesi geliştirmek değil, AI'ın alışveriş sürecinin merkezinde olduğu bir sistem oluşturmaktır.

Uzun vadeli kullanıcı deneyimi:

Kullanıcı ihtiyacını anlatır

↓

AI ihtiyacı analiz eder

↓

Ürün kataloğunda arama yapılır

↓

Kullanıcı tercihleri dikkate alınır

↓

En uygun ürünler sıralanır

↓

AI ürünleri karşılaştırır ve açıklar

↓

Kullanıcı isterse ürünleri sepete ekler

---

# Proje Durumu

🚧 Development in progress

İlk hedef:

**Product Catalog + Traditional Search + Semantic Search MVP**