/**
 * =========================================================
 * AURA — MONGOOSE MODELLERİ
 * =========================================================
 *
 * Bu dosya çalışan sistemin PORTUDUR, kaynağı değildir.
 * Üretimdeki şema: backend/app/models.py (SQLAlchemy + Postgres).
 *
 * MongoDB'ye taşınacaksa dikkat edilmesi gereken 3 fark
 * dosya içinde işaretlendi:
 *
 *   1. Wishlist tekilliği — unique index ŞART, aksi halde
 *      aynı ürün iki kez eklenir.
 *   2. $nin sorgusu — dislike listesi büyüdükçe belleğe
 *      alınan dizi de büyür; Postgres'teki alt sorgu
 *      avantajı kaybolur.
 *   3. Referans bütünlüğü — Mongo'da FOREIGN KEY yok.
 *      Ürün silindiğinde etkileşim kayıtları yalnız kalır;
 *      temizlik uygulama katmanının sorumluluğudur.
 */

const mongoose = require("mongoose");

const { Schema, model, Types } = mongoose;


/* =========================================================
   SABİTLER
========================================================= */

const INTERACTION_TYPES = [
    "VIEW",           // w = +0.1
    "LIKE",           // w = +1.0
    "UNLIKE",         // w = -0.3
    "DISLIKE",        // w = -1.0  (basparmak asagi)
    "QUICK_BUY",      // w = +2.0  (tek tikla satin alma)
    "INITIAL_STYLE",  // w =  0.0  (urune bagli degil)
];

/*
   Agirliklar OLAYLA BIRLIKTE yazilir.

   Neden: agirlik esleme tablosu zamanla degisir. Satirin
   uzerinde o an kullanilan agirlik yazili olmazsa, alti ay
   sonra egitim verisini yeniden cikarttiginda gecmis
   olaylara BUGUNUN agirliklari uygulanir.
*/
const INTERACTION_WEIGHTS = {
    QUICK_BUY: 2.0,
    LIKE: 1.0,
    VIEW: 0.1,
    UNLIKE: -0.3,
    DISLIKE: -1.0,
    INITIAL_STYLE: 0.0,
};

/*
   8 arketip. Katalog kapsami dengesiz oldugu icin her
   tarzin gercek urun sayisi product_style_scores'tan
   okunup kullaniciya secim aninda gosterilmeli.
*/
const STYLE_ARCHETYPES = [
    "minimalist",
    "streetwear",
    "smart_casual",
    "old_money",
    "boho",
    "athleisure",
    "goth",
    "y2k",
];

const MAX_SELECTED_STYLES = 3;


/* =========================================================
   ÜRÜN
========================================================= */

const productSchema = new Schema(
    {
        // Amazon ASIN — _id olarak kullanıyoruz ki
        // ObjectId ile ASIN arasında eşleme tutmak
        // gerekmesin.
        _id: { type: String, required: true },

        title: { type: String, required: true },
        titleTr: String,

        brand: String,
        category: String,

        description: String,
        descriptionTr: String,

        features: String,
        featuresTr: String,

        availability: String,
        productUrl: String,

        price: Number,
        listPrice: Number,
        discountPercent: Number,

        rating: Number,
        ratingCount: Number,

        imageUrl: String,

        searchText: String,
    },
    { timestamps: true, collection: "products" }
);

// Feed uygunluk filtresinin taradığı alanlar
productSchema.index({ price: 1, imageUrl: 1 });
productSchema.index({ category: 1 });
productSchema.index({ brand: 1 });


/* =========================================================
   YORUM
========================================================= */

const reviewSchema = new Schema(
    {
        _id: { type: String, required: true },

        productId: { type: String, ref: "Product", required: true, index: true },

        rating: Number,
        helpfulVotes: { type: Number, default: 0 },
        verifiedPurchase: { type: Boolean, default: false },

        reviewTitle: String,
        reviewText: String,
        sourceCleanedReviewText: String,

        sentimentScore: Number,
    },
    { collection: "reviews" }
);


/* =========================================================
   KULLANICI
========================================================= */

const userSchema = new Schema(
    {
        firstName: { type: String, required: true },
        lastName: { type: String, required: true },

        email: {
            type: String,
            required: true,
            unique: true,
            lowercase: true,
            trim: true,
        },

        gender: String,
        age: Number,

        // bcrypt hash. select:false — kazara sorgu
        // sonucuna girmesin.
        passwordHash: { type: String, required: true, select: false },
    },
    { timestamps: true, collection: "users" }
);


/* =========================================================
   ETKİLEŞİM KAYDI  (ML EĞİTİM VERİSİ)
========================================================= */

/**
 * Append-only olay kaydı.
 *
 * Bu koleksiyon GÜNCELLENMEZ ve SİLİNMEZ. Öneri modelinin
 * eğitim verisi budur.
 */
const userInteractionSchema = new Schema(
    {
        userId: {
            type: Types.ObjectId,
            ref: "User",
            required: true,
            index: true,
        },

        // INITIAL_STYLE olayları bir ürüne bağlı değildir.
        productId: {
            type: String,
            ref: "Product",
            default: null,
            index: true,
        },

        interactionType: {
            type: String,
            enum: INTERACTION_TYPES,
            required: true,
        },

        // explore | detail | grid | wishlist | featured
        source: String,

        // Feed'de kaçıncı karttı (position bias için)
        position: Number,

        /**
         * Etkileşim anında kullanıcıya GÖSTERİLEN AI skoru.
         *
         * Model "kullanıcı neyi beğendi" değil "X skoruyla
         * gösterilen şeyi beğendi mi" sorusunu öğrenmeli.
         */
        matchScore: { type: Number, min: 0, max: 100 },

        styleArchetype: { type: String, enum: STYLE_ARCHETYPES },

        // Etkilesim anindaki butun secili tarzlar
        selectedStyles: [{ type: String, enum: STYLE_ARCHETYPES }],

        // Olay anindaki ML agirligi
        weight: { type: Number, default: 0 },
    },
    {
        // createdAt otomatik gelir; updatedAt'e gerek yok
        // çünkü kayıtlar hiç güncellenmiyor.
        timestamps: { createdAt: true, updatedAt: false },
        collection: "user_interactions",
    }
);

// Feed'in DISLIKE hariç tutma sorgusu
userInteractionSchema.index({ userId: 1, interactionType: 1 });

// Kronolojik eğitim verisi çıkarımı
userInteractionSchema.index({ userId: 1, createdAt: 1 });

// Kullanıcı-ürün çifti geçmişi
userInteractionSchema.index({ userId: 1, productId: 1 });

/**
 * Postgres'teki CHECK kısıtının karşılığı:
 * ürün kimliği yalnızca INITIAL_STYLE'da boş olabilir.
 *
 * Mongo'da koşullu NOT NULL yok; validasyonu şemaya
 * gömüyoruz. Bu kontrol olmasa boş productId'li LIKE
 * kayıtları eğitim verisini sessizce bozardı.
 */
/* Agirligi olay yazilirken doldur */
userInteractionSchema.pre("validate", function (next) {
    if (!this.weight) {
        this.weight = INTERACTION_WEIGHTS[this.interactionType] ?? 0;
    }
    next();
});

userInteractionSchema.pre("validate", function (next) {
    if (this.interactionType !== "INITIAL_STYLE" && !this.productId) {
        return next(
            new Error(
                `${this.interactionType} için productId zorunludur.`
            )
        );
    }
    next();
});


/* =========================================================
   WISHLIST  (ANLIK DURUM)
========================================================= */

const wishlistItemSchema = new Schema(
    {
        userId: {
            type: Types.ObjectId,
            ref: "User",
            required: true,
            index: true,
        },

        productId: {
            type: String,
            ref: "Product",
            required: true,
            index: true,
        },
    },
    { timestamps: true, collection: "wishlist_items" }
);

/**
 * ŞART. Uygulama katmanındaki "önce ara, yoksa ekle"
 * kontrolü yarışa (race condition) karşı yetmez: iki
 * sekmeden aynı anda kalp basılabilir.
 *
 * Eklemede upsert kullan:
 *
 *   await WishlistItem.updateOne(
 *       { userId, productId },
 *       { $setOnInsert: { userId, productId } },
 *       { upsert: true }
 *   );
 */
wishlistItemSchema.index(
    { userId: 1, productId: 1 },
    { unique: true, name: "uq_wishlist_user_product" }
);


/* =========================================================
   KULLANICI TERCİHLERİ  (TÜRETİLMİŞ PROFİL)
========================================================= */

const userPreferenceSchema = new Schema(
    {
        userId: {
            type: Types.ObjectId,
            ref: "User",
            required: true,
            unique: true,
        },

        // Birincil tarz: selectedStyles[0]
        styleArchetype: { type: String, enum: STYLE_ARCHETYPES },

        /*
           Secili tarzlar (1-3), SIRALI.
           Postgres'te CHECK ile siniriyoruz; Mongo'da
           validator gerekiyor.
        */
        selectedStyles: {
            type: [{ type: String, enum: STYLE_ARCHETYPES }],
            validate: {
                validator: (v) =>
                    !v ||
                    (v.length >= 1 && v.length <= MAX_SELECTED_STYLES),
                message: "1-3 tarz secilebilir.",
            },
        },

        archetypeSelectedAt: Date,

        // Sık değiştiren kullanıcıda arketip sinyaline
        // daha az güvenilir.
        archetypeChangeCount: { type: Number, default: 0 },

        // LIKE geçmişinden türetilmiş ağırlıklı özetler.
        // { "nike": 3.2, "levis": 1.0 }
        topBrands: { type: Map, of: Number, default: {} },
        topCategories: { type: Map, of: Number, default: {} },
        topColors: { type: Map, of: Number, default: {} },

        /*
           BEĞENİLMEYEN marka ve kategoriler.

           Ürünün kendisi kara listede (kalıcı); aynı
           kategorideki diğerleri yalnızca skor kaybediyor.
           Kategoriyi tamamen dışlamak akışı hızla boşaltırdı.
        */
        avoidBrands: { type: Map, of: Number, default: {} },
        avoidCategories: { type: Map, of: Number, default: {} },

        medianPrice: Number,

        likeCount: { type: Number, default: 0 },
        dislikeCount: { type: Number, default: 0 },

        profileComputedAt: Date,
    },
    { timestamps: true, collection: "user_preferences" }
);


/* =========================================================
   STİL SKORLARI  (MODEL ÇIKTISI)
========================================================= */

const productStyleScoreSchema = new Schema(
    {
        productId: { type: String, ref: "Product", required: true },

        archetype: {
            type: String,
            enum: STYLE_ARCHETYPES,
            required: true,
        },

        score: { type: Number, required: true, min: 0, max: 100 },

        // ["color:bej", "style:minimalist", "price:band"]
        reasons: [String],

        computedAt: { type: Date, default: Date.now },
    },
    { collection: "product_style_scores" }
);

productStyleScoreSchema.index(
    { productId: 1, archetype: 1 },
    { unique: true }
);

// Feed'in sıcak yolu: archetype eşitliği + score azalan
productStyleScoreSchema.index({ archetype: 1, score: -1 });


/* =========================================================
   MODELLER
========================================================= */

const Product = model("Product", productSchema);
const Review = model("Review", reviewSchema);
const User = model("User", userSchema);
const UserInteraction = model("UserInteraction", userInteractionSchema);
const WishlistItem = model("WishlistItem", wishlistItemSchema);
const UserPreference = model("UserPreference", userPreferenceSchema);
const ProductStyleScore = model(
    "ProductStyleScore",
    productStyleScoreSchema
);


/* =========================================================
   KEŞFET SORGUSU  ($nin)
   ---------------------------------------------------------
   Postgres'teki NOT IN mantığının Mongo karşılığı.
   backend/app/crud.py:_apply_feed_filters ile aynı iş.
========================================================= */

/**
 * @param {ObjectId} userId
 * @param {"minimalist"|"streetwear"|"classic"|null} archetype
 * @param {number} limit
 * @param {string[]} onScreen  ekranda duran ürün kimlikleri
 */
async function getExploreFeed(
    userId,
    selectedStyles = [],
    limit = 12,
    cursor = null
) {

    /*
       1. Hariç tutulacak ürünler.

       DİKKAT: Postgres'te bu bir alt sorgudur ve veri
       veritabanından hiç çıkmaz. Mongo'da diziyi belleğe
       alıp geri göndermek gerekiyor. Kullanıcı başına
       binlerce DISLIKE'a çıkıldığında bu dizi sorguyu
       şişirir. O noktada seçenekler:

         - $lookup ile anti-join (aggregation pipeline)
         - dislike listesini user_preferences içinde
           tek dizide tutmak (yazma maliyeti artar)
    */

    const [disliked, wishlisted] = await Promise.all([
        UserInteraction.distinct("productId", {
            userId,
            interactionType: "DISLIKE",
            productId: { $ne: null },
        }),
        WishlistItem.distinct("productId", { userId }),
    ]);

    /*
       CURSOR: Postgres'te keyset pagination kullaniyoruz
       ((final_score, product_id) < (cursor_score, cursor_id)).
       Mongo'da ayni mantik $lt ile kurulur; gosterilmis
       kimlikler de cursor icinde tasinir.

       OFFSET/skip KULLANMIYORUZ: her sayfada onceki
       satirlari yeniden tarar ve arada yeni etkilesim
       olursa siralama kayar.
    */
    const decoded = cursor
        ? JSON.parse(Buffer.from(cursor, "base64url").toString())
        : null;

    const blocked = [
        ...disliked,
        ...wishlisted,
        ...(decoded?.n || []),
    ];

    // Feed uygunluk kuralı: fiyatı ve görseli olmayan ürün
    // bozuk kart üretir ve eğitim verisini kirletir.
    const eligibility = {
        price: { $gt: 0 },
        imageUrl: { $nin: [null, ""] },
        _id: { $nin: blocked },

        // Bebek / çocuk ürünlerini yetişkin akışından çıkar
        category: {
            $not: /› (Baby|Boys|Girls)/,
        },
    };

    // ---- Tarz yok: rastgele akis ----

    if (!selectedStyles.length) {
        return Product.aggregate([
            { $match: eligibility },
            { $sample: { size: limit } },
        ]);
    }

    // ---- Tarz var: harmanla ve skora gore sirala ----
    //
    // Kullanici 1-3 tarz sectigi icin urun basina EN IYI
    // skoru aliyoruz (ortalama DEGIL: tarzlar alternatif,
    // birlikte degil — bir hoodie "Streetwear + Old Money"
    // seciminde ortalamaya vurulup dusmemeli).

    const candidates = await ProductStyleScore.aggregate([
        {
            $match: {
                archetype: { $in: selectedStyles },
                productId: { $nin: blocked },
            },
        },
        {
            $group: {
                _id: "$productId",
                bestScore: { $max: "$score" },
                styles: { $push: { s: "$score", a: "$archetype" } },
            },
        },
        {
            $addFields: {
                productId: "$_id",
                bestStyle: {
                    $let: {
                        vars: {
                            top: {
                                $first: {
                                    $sortArray: {
                                        input: "$styles",
                                        sortBy: { s: -1 },
                                    },
                                },
                            },
                        },
                        in: "$$top.a",
                    },
                },
            },
        },
        // Keyset: cursor skorundan kucuk olanlar
        ...(decoded ? [{ $match: { bestScore: { $lt: decoded.s } } }] : []),
        { $sort: { bestScore: -1, productId: -1 } },
        { $limit: limit },
        {
            $lookup: {
                from: "products",
                localField: "productId",
                foreignField: "_id",
                as: "product",
            },
        },
        { $unwind: "$product" },
        {
            $match: {
                "product.price": { $gt: 0 },
                "product.imageUrl": { $nin: [null, ""] },
            },
        },
    ]);

    return candidates;
}


module.exports = {
    Product,
    Review,
    User,
    UserInteraction,
    WishlistItem,
    UserPreference,
    ProductStyleScore,

    INTERACTION_TYPES,
    INTERACTION_WEIGHTS,
    STYLE_ARCHETYPES,
    MAX_SELECTED_STYLES,

    getExploreFeed,
};
