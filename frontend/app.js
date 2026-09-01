/* =========================================================
   WISHNN FASHION
   FastAPI Backend Connected Version
========================================================= */


const API_BASE = "http://127.0.0.1:8000";

let usdTryRate = 47.88;

const CATEGORY_LABELS = {
    "": "Tüm Ürünler",
    women: "Kadın",
    men: "Erkek",
    dress: "Elbise",
    shirt: "Gömlek",
    pants: "Pantolon",
    jacket: "Ceket",
    shoes: "Ayakkabı"
};


const state = {
    /*
       SAYFALAMA KALDIRILDI.

       Sayfa numarasi yerine offset tutuluyor: sonsuz akis
       "kaldigim yerden devam" mantigiyle calisiyor, "3.
       sayfaya git" diye bir eylem yok.
    */
    offset: 0,
    limit: 12,

    searchQuery: "",
    searchMode: false,

    /*
       IKI ARAMA, IKI AYRI YER.

       Onceden tek bir arama kutusu vardi ve altindaki
       "AI Arama / Klasik Arama" dugmeleri bu degeri
       degistiriyordu. Problem: kullanici hangi modda
       oldugunu unutuyor, ayni kutuya "siyah gomlek" yazip
       bambaska iki sonuc aliyordu.

       Artik ayrildilar:

         KLASIK  -> sayfadaki arama kutusu + header'daki
                    buyutec. Anahtar kelime, /products/search.
         AI      -> header'in SOL ustundeki ✦ sembolu.
                    Konusan asistan, /api/chat.

       Bu yuzden urun izgarasi HER ZAMAN klasik arama yapar.
       setSearchType() ve semantik dal duruyor ama artik
       cagrilmiyor: /api/search ucu hala canli ve asistanin
       search_catalog araci onu kullaniyor.
    */
    searchType: "classic",

    category: "",

    /*
       ARAMA COZUMLEMESI BACKEND'DEN GELIYOR.

       Onceden cinsiyet/kategori/renk burada, app.js icindeki
       sozluklerle tahmin ediliyordu. Iki problemi vardi:

       1. Embedding backend'de uretiliyor; buradaki
          genisletme vektore hic giremiyordu.
       2. Ayni sozluk iki yerde duruyordu.

       Artik /api/search cozumlemeyi de donduruyor
       (backend/app/query_engine.py). Burasi yalnizca
       gosteriyor.
    */
    searchAnalysis: null,

    /*
       Gevsetme asamasi. Sonsuz akista sayfa 2 ayni asamada
       kalmali; yoksa filtre degisip urunler tekrar eder.
       feed.py'deki cursor dersinin aynisi.
    */
    searchStage: null,

    products: [],
    hasMore: true,
    loadingProducts: false,

    sortBy: "",

    /*
       Misafir hizli satin almaya bastiysa urun burada
       bekliyor; girisin ardindan islem devam ediyor.
    */
    pendingQuickBuy: null,

    /* Favorideki urun kimlikleri (kalp durumlari) */
    wishlist: new Set(),

    /* Favoriler panelindeki tam kayitlar */
    wishlistItems: [],

    /*
       Misafir kalp/begenmedim'e bastiysa niyeti burada
       tutuyoruz; girisin ardindan devam ediyor.
    */
    pendingInteraction: null,

    /* Sepetteki urunler: [{product_id, quantity, product}] */
    cart: [],

    /*
       Gardiroptaki kombinler. Sepetten farki: her kayit bir
       KOMPOZISYON, icinde parcalar var.
       [{id, title, items: [{product_id, slot, product}], ...}]
    */
    wardrobe: []
};


/* =========================================================
   DOM
========================================================= */

const $ = (id) => document.getElementById(id);

const productsGrid = $("products-grid");
const featuredGrid = $("featured-products-grid");

const loader = $("loader");
const emptyState = $("empty-state");

const resultsTitle = $("results-title");
const resultsCount = $("results-count");

const pagination = $("pagination");
const sortSelect = $("sort-select");

const searchInput = $("ai-search-input");
const searchButton = $("ai-search-btn");

/*
   AI/Klasik secim dugmeleri HTML'den KALDIRILDI; bu iki
   referans artik her zaman null. Dinleyiciler `?.` ile
   baglandigi icin sessizce hicbir sey yapmiyorlar.

   Kod bilerek silinmedi: setSearchType() ve loadProducts()
   icindeki semantik dal calisir durumda duruyor. Gun gelip
   izgarada da AI aramasi istenirse tek yapilacak sey
   dugmeleri HTML'e geri koymak.

   Iki aramanin neden ayrildigi: state.searchType yanindaki
   "IKI ARAMA, IKI AYRI YER" notu.
*/
const semanticSearchModeButton =
    $("semantic-search-mode");
const classicSearchModeButton =
    $("classic-search-mode");
const searchModeDescription =
    $("search-mode-description");

const productModal = $("product-modal");
const modalContent = $("modal-content");
const closeModalButton = $("close-modal-btn");

const openSearchButton = $("open-search-btn");
const searchOverlay = $("search-overlay");
const searchClose = $("search-close");
const globalSearchInput = $("global-search-input");

/*
   SEPET KALDIRILDI.

   cartButton / cartOverlay / cartItems / checkoutButton
   referanslari silindi. Satin alma tek urun uzerinden,
   Wishlist ise "sonra al" listesi olarak sepetin yerini
   aliyor.
*/

const authOverlay = $("auth-overlay");
const authCloseButton = $("auth-close");

const wishlistButton = $("wishlist-btn");
const wishlistOverlay = $("wishlist-overlay");
const closeWishlistButton = $("close-wishlist");
const wishlistItems = $("wishlist-items");

const cartButton = $("cart-btn");
const cartOverlay = $("cart-overlay");
const closeCartButton = $("close-cart");
const cartItemsHolder = $("cart-items");

const wardrobeButton = $("wardrobe-btn");
const wardrobeOverlay = $("wardrobe-overlay");
const closeWardrobeButton = $("close-wardrobe");
const wardrobeListHolder = $("wardrobe-list");

const exploreGrid = $("explore-grid");
const exploreCarousel = $("explore-carousel");
const exploreRefreshButton = $("explore-refresh");

const archetypeOverlay = $("archetype-overlay");

/* setupArchetype icinde atanir */
let archetypeGrid = null;

const loginForm = $("login-form");
const loginEmail = $("login-email");
const loginPassword = $("login-password");
const loginMessage = $("login-message");
const mobileMenu = $("mobile-menu");
const mobileMenuButton = $("mobile-menu-btn");
const mobileClose = $("mobile-close");


/* =========================================================
   START
========================================================= */

document.addEventListener("DOMContentLoaded", async () => {

    setupNavigation();
    setupSearch();
    setupAiChat();
    setupSocial();
    setupSearchAlternatives();
    setupScrollTop();
    setupCategories();
    setupSort();
    setupModal();
    setupAuth();
    setupQuickCheckout();
    setupWishlistBar();

    setupExplore();
    setupWishlistPanel();
    setupCartPanel();
    setupWardrobePanel();
    setupCustomize();
    setupProductGridActions();
    setupViewTracking();

    /* HTML'deki data-icon yer tutucularini SVG ile doldur */
    hydrateIcons();

    renderUserArea();
    renderExploreNotice();
    renderWishlistBar();

    await loadExchangeRate();

    /* Kalp durumlari kartlar cizilmeden once yuklenmeli */
    await loadWishlist();
    await loadCart();
    await loadWardrobe();

    /* Alt barin kucuk gorselleri icin tam liste */
    refreshWishlistItems();

    /* Okunmamis mesaj rozeti. Hem acilista hem oturum
       degisiminde tazeleniyor: cikis yapinca rozet
       birinin okunmamislarini gostermeye devam etmemeli. */
    refreshSocialBadge();

    /* Arketip: feed'den ONCE bilinmeli ki ilk istek
       dogru skorlarla gelsin */
    await setupArchetype();

    setupInfiniteScroll(
        "products-sentinel",
        "products-more-btn",
        () => loadProducts(),
        () =>
            !state.loadingProducts &&
            state.hasMore &&
            state.products.length > 0
    );

    await loadProducts({ reset: true });
    await loadFeaturedProducts();
    await loadExplore({ reset: true });

    /* Ilk ziyaretse stil secimi modali */
    maybeOpenArchetypeModal();
});

/* =========================================================
   API
========================================================= */

async function apiGet(path, params = {}) {

    const url = new URL(`${API_BASE}${path}`);

    Object.entries(params).forEach(([key, value]) => {

        if (
            value !== undefined &&
            value !== null &&
            value !== ""
        ) {
            url.searchParams.set(key, value);
        }
    });

    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(
            `${response.status} ${response.statusText}`
        );
    }

    return response.json();
}

async function loadExchangeRate() {
    try {
        const data = await apiGet("/exchange-rate");

        usdTryRate = data.rate;

        console.log("Güncel kur:", usdTryRate);

    } catch (error) {
        console.error("Kur alınamadı:", error);
    }
}

/* =========================================================
   PRODUCTS
========================================================= */

async function loadProducts({ reset = false } = {}) {

    if (state.loadingProducts) return;


    if (reset) {
        state.offset = 0;
        state.products = [];
        state.hasMore = true;

        if (productsGrid) {
            productsGrid.innerHTML = "";
        }
    }


    if (!state.hasMore) return;


    state.loadingProducts = true;

    setProductsMoreLoading(true);

    if (reset) {
        showLoader();
        hideEmpty();
    }


    try {

        const params = {
            limit: state.limit,
            offset: state.offset,
            sort: state.sortBy || undefined,
        };

        let data;

        if (state.searchMode && state.searchQuery) {

            if (state.searchType === "semantic") {

                /*
                   AKILLI ARAMA.

                   Sorgu cozumlemesi, zenginlestirme ve
                   filtre gevsetmesi backend'de yapiliyor;
                   burada yalnizca `stage` geri gonderiliyor
                   ki sayfa 2 ayni asamada devam etsin.
                */
                const response = await apiGet("/api/search", {
                    limit: state.limit,
                    offset: state.offset,
                    q: state.searchQuery,
                    stage: state.searchStage ?? undefined,
                });

                state.searchAnalysis = response?.query || null;
                state.searchStage = response?.meta?.stage ?? null;

                renderSearchAnalysis(response?.meta || null);

                /*
                   Kartlar duz urun nesnesi bekliyor. Arama
                   gerekcelerini urune baglayip kartta kucuk
                   bir etiket olarak gosteriyoruz.
                */
                data = (response?.items || []).map(item => ({
                    ...item.product,
                    _searchReasons: item.reasons || [],
                }));

            } else {

                data = await apiGet("/products/search", {
                    ...params,
                    q: state.searchQuery,
                });

                hideSearchAnalysis();
            }

        } else {

            data = await apiGet("/products", {
                ...params,
                category: state.category,
            });

            hideSearchAnalysis();
        }


        if (!Array.isArray(data)) {
            throw new Error("Backend ürün listesi döndürmedi.");
        }


        /*
           hasMore: donen kayit sayisi limite esitse devam
           var kabul ediyoruz. Toplam sayi ucu olmadigi icin
           son partide tam bolunme olursa bir kez bos istek
           atilir; bu tek fazla istek, her sayfa icin
           COUNT(*) calistirmaktan ucuz.
        */

        state.hasMore = data.length === state.limit;

        state.offset += data.length;

        const startIndex = state.products.length;

        state.products.push(...data);

        appendProducts(data, startIndex);

        updateResultsHeader();
        syncSortAvailability();


        if (!state.products.length) {

            showEmpty(
                "Ürün bulunamadı",
                "Farklı bir arama terimi deneyebilirsin."
            );
        }


    } catch (error) {

        console.error("Products API error:", error);

        if (resultsCount) {
            resultsCount.textContent = "Ürünler yüklenemedi";
        }

        if (!state.products.length) {
            showEmpty(
                "Ürünler yüklenemedi",
                "Backend bağlantısını kontrol et."
            );
        }

        state.hasMore = false;

    } finally {

        state.loadingProducts = false;

        hideLoader();

        setProductsMoreLoading(false);

        renderProductsMore();
    }
}


function updateResultsHeader() {

    if (resultsTitle) {

        resultsTitle.textContent =
            state.searchMode
                ? `"${state.searchQuery}" sonuçları`
                : (
                    CATEGORY_LABELS[state.category] ||
                    "Tüm Ürünler"
                );
    }


    if (!resultsCount) return;


    if (!state.products.length) {
        resultsCount.textContent = "Ürün bulunamadı";
        return;
    }


    resultsCount.textContent = state.hasMore
        ? `${state.products.length} ürün yüklendi`
        : `${state.products.length} ürün · tümü yüklendi`;
}


function renderProductsMore() {

    const wrapper = $("products-more");
    const end = $("products-end");
    const button = $("products-more-btn");

    if (!wrapper) return;


    const hasProducts = state.products.length > 0;

    wrapper.classList.toggle("hidden", !hasProducts);

    button?.classList.toggle("hidden", !state.hasMore);

    end?.classList.toggle("hidden", state.hasMore);
}


function setProductsMoreLoading(loading) {

    $("products-more")?.classList.toggle("loading", loading);
}


/* =========================================================
   RENDER PRODUCT CARDS
========================================================= */

/**
 * Yeni gelen ürünleri ızgaranın SONUNA ekler.
 *
 * Sonsuz akışta ızgarayı her seferinde sıfırdan çizmek
 * hem kaydırma konumunu bozar hem de görünen kartları
 * gereksiz yere yeniden oluşturur.
 *
 * startIndex kademeli giriş gecikmesi için: yeni parti
 * 0'dan değil, kaldığı yerden saymalı.
 */
function appendProducts(products, startIndex = 0) {

    if (!productsGrid) return;


    const fragment = document.createDocumentFragment();


    products.forEach((product, offset) => {

        const card = document.createElement("article");

        card.className = "product-card";

        /* Kademeli giris: her kart 45 ms sonra */
        card.style.setProperty(
            "--stagger",
            `${Math.min(offset, 11) * 45}ms`
        );


        const title = productTitle(product);
        const brand = product.brand || "";
        const price = formatPrice(product.price);

        const discount = Number(product.discount_percent || 0);
        const rating = Number(product.rating || 0);
        const ratingCount = Number(product.rating_count || 0);


        card.innerHTML = `

            <div class="card-image-wrap">

                <img
                    src="${escapeHTML(safeImage(product.image_url))}"
                    alt="${escapeHTML(title)}"
                    loading="lazy"
                    onerror="this.src='https://placehold.co/600x800?text=WishNN'"
                >

                ${
                    discount > 0
                        ? `<span class="discount-tag">-${discount}%</span>`
                        : ""
                }

                ${
                    brand
                        ? `<span class="brand-pill">${escapeHTML(brand)}</span>`
                        : ""
                }

            </div>


            <div class="card-details">

                <h4 class="product-title">
                    ${escapeHTML(title)}
                </h4>

                ${
                    /*
                       Bu urunun ARAMAYA neden uydugu.
                       Yalnizca gercekten tetiklenmis
                       gerekceler yaziliyor; uydurma gerekce
                       yazmak yanlis yuzde yazmaktan kotudur.
                    */
                    Array.isArray(product._searchReasons) &&
                    product._searchReasons.length
                        ? `
                            <span class="card-search-reason">
                                ${icon("sparkles")}
                                ${escapeHTML(
                                    product._searchReasons
                                        .slice(0, 2)
                                        .join(" · ")
                                )}
                            </span>
                        `
                        : ""
                }

                ${
                    rating > 0
                        ? `
                            <div class="product-rating">
                                <i class="fa-solid fa-star"></i>
                                <span>
                                    ${rating.toFixed(1)}
                                    ${
                                        ratingCount
                                            ? `(${ratingCount.toLocaleString("tr-TR")})`
                                            : ""
                                    }
                                </span>
                            </div>
                        `
                        : ""
                }

                <div class="price-row">

                    <span class="current-price">${price}</span>

                    ${
                        product.list_price &&
                        Number(product.list_price) >
                        Number(product.price || 0)
                            ? `
                                <span class="old-price">
                                    ${formatPrice(product.list_price)}
                                </span>
                            `
                            : ""
                    }

                </div>

                <div class="card-actions">

                    <button
                        type="button"
                        class="card-heart${
                            isWishlisted(product.product_id)
                                ? " active"
                                : ""
                        }"
                        data-grid-action="like"
                        data-product-id="${escapeHTML(product.product_id)}"
                        aria-label="Favorilere ekle"
                    >
                        ${
                            icon("heart", {
                                filled: isWishlisted(product.product_id),
                            })
                        }
                    </button>

                    <button
                        type="button"
                        class="card-cart-add${
                            isInCart(product.product_id)
                                ? " active"
                                : ""
                        }"
                        data-grid-action="add-cart"
                        data-product-id="${escapeHTML(product.product_id)}"
                        aria-label="Sepete ekle"
                        ${hasPrice(product) ? "" : "disabled"}
                    >
                        <i class="fa-solid fa-bag-shopping"></i>
                    </button>

                    <button
                        type="button"
                        class="card-quick-buy"
                        data-grid-action="quick-buy"
                        data-product-id="${escapeHTML(product.product_id)}"
                        ${hasPrice(product) ? "" : "disabled"}
                    >
                        ${icon("zap")}
                        ${
                            hasPrice(product)
                                ? "HIZLI AL"
                                : "FİYAT YOK"
                        }
                    </button>

                </div>

            </div>
        `;


        card.addEventListener("click", event => {

            /*
               Kalp ve hizli al butonlari kartin icinde;
               tiklamalari urun detayini acmamali.
            */
            if (event.target.closest("[data-grid-action]")) {
                return;
            }

            openProduct(product.product_id, product);
        });


        fragment.appendChild(card);
    });


    productsGrid.appendChild(fragment);

    hydrateIcons(productsGrid);
}


/**
 * Ürün ızgarasındaki kalp ve hızlı al butonları.
 *
 * Olay delegasyonu: kartlar sonsuz akışla sürekli
 * eklendiği için her karta ayrı dinleyici bağlamak
 * gereksiz.
 */
function setupProductGridActions() {

    productsGrid?.addEventListener("click", event => {

        const button = event.target.closest("[data-grid-action]");

        if (!button) return;

        event.stopPropagation();


        const productId = button.dataset.productId;

        const product = state.products.find(
            item => item.product_id === productId
        );

        if (!product) return;


        if (button.dataset.gridAction === "quick-buy") {

            openQuickCheckout({ product }, { source: "grid" });

            return;
        }


        if (button.dataset.gridAction === "add-cart") {

            handleGridAddToCart(product, button);

            return;
        }


        /* Kalp */

        handleGridLike(product, button);
    });
}


async function handleGridAddToCart(product, button) {

    if (!isUserLoggedIn()) {

        openAuth("Sepete eklemek için giriş yap.");

        return;
    }


    button.disabled = true;

    try {

        await addToCart(product.product_id, { source: "grid" });

        button.classList.add("active");

        showToast({
            title: "Sepete eklendi",
            message: `${productTitle(product)} sepetine eklendi.`,
            tone: "success",
        });


    } catch (error) {

        console.error("Sepete eklenemedi:", error);

        showToast({
            title: "Sepete eklenemedi",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });

    } finally {

        button.disabled = !hasPrice(product);
    }
}


async function handleGridLike(product, button) {

    const productId = product.product_id;

    if (!isUserLoggedIn()) {

        requestLoginForInteraction(
            { type: "GRID_LIKE", productId },
            "Favorilerine eklemek için giriş yap."
        );

        return;
    }


    const liked = isWishlisted(productId);

    /* İyimser arayüz */
    setGridHeart(button, !liked);

    try {

        const response = liked
            ? await removeFromWishlist(productId, { source: "grid" })
            : await addToWishlist(productId, {
                  source: "grid",
                  product,
              });

        syncWishlistButtons(productId, !liked);

        renderAiStatus();

        if (response?.toast) {
            showToast(response.toast);
        }

    } catch (error) {

        console.error("Favori güncellenemedi:", error);

        setGridHeart(button, liked);

        showToast({
            title: "Güncellenemedi",
            message: "Bağlantını kontrol edip tekrar dene.",
            tone: "error",
        });
    }
}


function setGridHeart(button, liked) {

    button.classList.toggle("active", liked);

    button.innerHTML = icon("heart", { filled: liked });

    hydrateIcons(button);
}


/* =========================================================
   FEATURED PRODUCTS
========================================================= */

async function loadFeaturedProducts() {

    if (!featuredGrid) return;


    try {

        const products = await apiGet(
            "/products",
            {
                limit: 100,
                offset: 0
            }
        );

        const featured =
            products
                .filter(
                    product =>
                        Number(
                            product.discount_percent || 0
                        ) > 0
                )
                .sort(
                    (a, b) =>
                        Number(
                            b.discount_percent || 0
                        ) -
                        Number(
                            a.discount_percent || 0
                        )
                )
                .slice(0, 4);


        featuredGrid.innerHTML = "";


        featured.forEach(product => {

            const card =
                document.createElement("article");

            card.className =
                "product-card";


            card.innerHTML = `

                <div class="card-image-wrap">

                    <img
                        src="${safeImage(product.image_url)}"
                        alt="${escapeHTML(product.title)}"
                        loading="lazy"
                        onerror="this.src='https://placehold.co/600x800?text=WishNN'"
                    >

                    <span class="discount-tag">
                        -${Number(product.discount_percent || 0)}%
                    </span>

                </div>


                <div class="card-details">

                    <h4 class="product-title">
                        ${escapeHTML(product.title)}
                    </h4>


                    <div class="price-row">

                        <span class="current-price">
                            ${formatPrice(product.price)}
                        </span>

                        ${
                            product.list_price
                                ? `
                                    <span class="old-price">
                                        ${formatPrice(product.list_price)}
                                    </span>
                                `
                                : ""
                        }

                    </div>

                </div>
            `;


            card.addEventListener(
                "click",
                () => {

                    openProduct(
                        product.product_id,
                        product
                    );
                }
            );


            featuredGrid.appendChild(card);
        });


    } catch (error) {

        console.error(
            "Featured products error:",
            error
        );
    }
}


/*=========================================================
   SEARCH
========================================================= */

function setSearchType(type) {

    state.searchType = type;

    semanticSearchModeButton?.classList.toggle(
        "active",
        type === "semantic"
    );

    classicSearchModeButton?.classList.toggle(
        "active",
        type === "classic"
    );

    if (searchModeDescription) {

        searchModeDescription.textContent =
            type === "semantic"
                ? "Ne aradığını doğal bir şekilde tarif et. WishNN anlamına göre en uygun ürünleri bulsun."
                : "Ürün adı, marka veya kategori üzerinden anahtar kelimeyle ara.";
    }

    syncSortAvailability();

    if (state.searchMode && state.searchQuery) {

        state.page = 1;

        loadProducts();
    }
}

/*
   setupAiGlow() KALDIRILDI.

   Fare imlecini takip eden isik efekti #ai-search-anchor
   bolumune aitti; o bolum silindi (arama artik header'da
   iki dugme). Fonksiyon her cagrisinda hemen return
   ediyordu — olu kod. Efektin CSS'i (.ai-glow,
   .glow-active) da bu yuzden kaldirildi.
*/


function setupSearch() {

    semanticSearchModeButton?.addEventListener(
        "click",
        () => {
            setSearchType("semantic");
        }
    );

    classicSearchModeButton?.addEventListener(
        "click",
        () => {
            setSearchType("classic");
        }
    );

    searchButton?.addEventListener(
        "click",
        () => {
            runSearch(
                searchInput?.value
            );
        }
    );

    searchInput?.addEventListener(
        "keydown",
        event => {

            if (event.key === "Enter") {
                runSearch(
                    searchInput.value
                );
            }
        }
    );


    document
        .querySelectorAll(".chip")
        .forEach(chip => {

            chip.addEventListener(
                "click",
                () => {

                    const query =
                        chip.dataset.query || "";

                    if (searchInput) {
                        searchInput.value = query;
                    }

                    runSearch(query);
                }
            );
        });


    openSearchButton?.addEventListener(
        "click",
        () => {

            searchOverlay
                ?.classList.add("open");

            setTimeout(
                () => globalSearchInput?.focus(),
                100
            );
        }
    );


    searchClose?.addEventListener(
        "click",
        closeSearchOverlay
    );


    searchOverlay?.addEventListener(
        "click",
        event => {

            if (
                event.target === searchOverlay
            ) {
                closeSearchOverlay();
            }
        }
    );


    globalSearchInput?.addEventListener(
        "keydown",
        event => {

            if (event.key !== "Enter") {
                return;
            }


            const query =
                globalSearchInput.value.trim();


            if (!query) return;


            if (searchInput) {
                searchInput.value = query;
            }


            closeSearchOverlay();

            runSearch(query);
        }
    );
}


function runSearch(value) {

    const query =
        String(value || "").trim();

    if (!query) {

        state.searchMode = false;
        state.searchQuery = "";
        state.category = "";
        state.searchAnalysis = null;
        state.searchStage = null;

        hideSearchAnalysis();

        loadProducts({ reset: true });

        return;
    }

    state.searchMode = true;
    state.searchQuery = query;

    /*
       Kategori/renk/cinsiyet TAHMINI ARTIK BURADA YAPILMIYOR.
       Backend cozumlemesi (/api/search -> query.gender,
       query.category...) tek kaynak. Burada eski kategori
       filtresini yalnizca temizliyoruz.
    */
    state.category = "";

    /* Yeni sorgu, yeni gevsetme asamasi */
    state.searchStage = null;
    state.searchAnalysis = null;

    /*
       Filtre cubugu aramanin arka planda sectigi kategoriyi
       degil hep "TUMU"yu aktif gosterir: yaniltici bir sekme
       aktif gorunmesin. Tespit edilen kategori zaten arama
       sonuclarinin ustundeki analiz panelinde yaziyor.
    */

    document
        .querySelectorAll("[data-category]")
        .forEach(item => {

            item.classList.toggle(
                "active",
                (item.dataset.category || "") === ""
            );
        });


    loadProducts({ reset: true });

    $("products-section")
        ?.scrollIntoView({
            behavior: "smooth"
        });
}


function closeSearchOverlay() {

    searchOverlay
        ?.classList.remove("open");
}


/* =========================================================
   CATEGORY QUICK SEARCH
========================================================= */

function setupCategories() {

    /*
       data-category tasiyan her ogeyi baglariz:
       header navigasyonu, mobil menu, kesfet seridi
       ve urun listesinin ustundeki filtre cubugu.
    */

    document
        .querySelectorAll("[data-category]")
        .forEach(element => {

            element.addEventListener(
                "click",
                event => {

                    /*
                       Header ve mobil menudeki ogeler <a> etiketi.
                       Tarayicinin ani anchor ziplamasini engelleyip
                       yumusak kaydirmayi kendimiz yapiyoruz.
                    */

                    if (element.tagName === "A") {
                        event.preventDefault();
                    }


                    applyCategory(
                        element.dataset.category || ""
                    );
                }
            );
        });
}


function applyCategory(category) {

    state.category = category;

    state.searchMode = false;
    state.searchQuery = "";


    if (searchInput) {
        searchInput.value = "";
    }


    if (globalSearchInput) {
        globalSearchInput.value = "";
    }


    /*
       Ayni kategori header'da, mobil menude, kesfet
       seridinde ve filtre cubugunda birlikte bulunabilir.
       Hepsinin aktif durumunu birlikte guncelliyoruz.
    */

    document
        .querySelectorAll("[data-category]")
        .forEach(item => {

            item.classList.toggle(
                "active",
                (item.dataset.category || "") === category
            );
        });


    /* Mobil menuden secildiyse menuyu kapat */

    mobileMenu?.classList.remove("open");

    closeSearchOverlay();


    loadProducts({ reset: true });


    $("products-section")
        ?.scrollIntoView({
            behavior: "smooth"
        });
}


/* =========================================================
   SORT
========================================================= */

function setupSort() {

    sortSelect?.addEventListener("change", event => {

        state.sortBy = event.target.value;

        /*
           SIRALAMA ARTIK SUNUCUDA.

           Onceden yalnizca ekrandaki 12 urun tarayicida
           siralaniyordu: "fiyat artan" secildiginde
           katalogun en ucuz urunleri degil o sayfadaki en
           ucuzu geliyordu. Sonsuz akista bu daha da bozuk
           gorunurdu — her yeni parti siralanmamis olarak
           sona eklenirdi.

           Bu yuzden siralama degisince akis bastan yuklenir.
        */

        loadProducts({ reset: true });
    });
}


/*
   AI ARAMADA SIRALAMA CALISMIYOR — VE BUNU SOYLUYORUZ.

   Anlamsal arama sonuclarini alaka duzeyine gore siralar
   (vektor benzerligi + kelime bonuslari). Uzerine "fiyat
   artan" uygulamak alaka sirasini yok eder: kullanici
   "kadın yazlık elbise" arayip en ucuz corabi gorur.

   Eski kodda `sort` parametresi semantic uca gonderiliyordu
   ama uc onu hic okumuyordu — menu sessizce hicbir sey
   yapmiyordu. Sessiz olu kontrol, calismayan bir ozellikten
   daha kotu: kullanici sectigini sanip yanlis sonuca guvenir.

   Cozum: AI aramada menu devre disi ve sebebi yaziyor.
*/
function syncSortAvailability() {

    if (!sortSelect) return;

    const aiSearch =
        state.searchMode &&
        state.searchQuery &&
        state.searchType === "semantic";

    sortSelect.disabled = Boolean(aiSearch);

    sortSelect.title = aiSearch
        ? "AI arama sonuçları alaka düzeyine göre sıralanır; "
          + "sıralama seçeneği bu modda kullanılamaz."
        : "";
}


/* =========================================================
   PRODUCT DETAIL
========================================================= */

async function openProduct(
    productId,
    fallbackProduct
) {

    if (!productId) return;


    showLoader();


    try {

        const encodedId =
            encodeURIComponent(productId);


        const results =
            await Promise.allSettled([

                apiGet(
                    `/products/${encodedId}`
                ),

                apiGet(
                    `/products/${encodedId}/reviews`,
                    {
                        limit: 20,
                        offset: 0
                    }
                )

            ]);


        const product =
            results[0].status === "fulfilled"
                ? results[0].value
                : fallbackProduct;


        const reviews =
            results[1].status === "fulfilled"
                ? results[1].value
                : [];


        if (!product) {
            throw new Error(
                "Ürün bulunamadı."
            );
        }


        renderProductModal(
            product,
            reviews
        );


        productModal
            ?.classList.remove("hidden");


        /*
           Urun detayinin acilmasi guclu bir ilgi sinyalidir:
           VIEW olarak kaydediyoruz.
        */

        queueView(
            productId,
            "detail",
            null,
            findExploreItem(productId)?.match_score ?? null
        );


    } catch (error) {

        console.error(
            "Product detail error:",
            error
        );


    } finally {

        hideLoader();
    }
}


/**
 * BEDEN/KALIP TAVSIYESİ KUTUSU.
 *
 * Veri /products/{id} cevabındaki `fit` alanından geliyor
 * (backend/app/fit_advice.py). Metni BACKEND kuruyor —
 * eşikler ve oy sayıları orada, burada yeniden hesaplamak
 * aynı kuralı iki yerde yaşatmak olurdu.
 *
 * fit YOKSA hiçbir şey çizilmiyor ve bu NORMAL: 728 ürünün
 * 526'sında karar verilebilecek kadar yorum kanıtı yok
 * (ölçüldü). Boş bir iddia yerine hiçbir iddia — kartlarda
 * eşiğin altında yüzde göstermeme kararının aynısı.
 *
 * Oy sayısı da gösteriliyor ("5 yorumdan 5'i"): kullanıcı
 * iddiayı kendisi tartabilmeli. Doğrulayamadığı bir tavsiye,
 * güvenemeyeceği bir tavsiyedir.
 */
function renderFitAdvice(fit) {

    if (!fit || !fit.verdict) return "";

    /* Beden değiştirme tavsiyesi mi, teyit mi? İkisi farklı
       ağırlıkta ve kullanıcı bunu bir bakışta görmeli. */
    const isChange = fit.verdict !== "true";

    const icon = isChange
        ? "fa-triangle-exclamation"
        : "fa-circle-check";

    return `
        <div class="fit-advice ${escapeHTML(fit.verdict)}">

            <div class="fit-advice-head">
                <i class="fa-solid ${icon}"></i>
                <strong>${escapeHTML(fit.title)}</strong>
            </div>

            <p class="fit-advice-text">
                ${escapeHTML(fit.advice)}
            </p>

            <span class="fit-advice-basis">
                ${fit.agree_count}/${fit.total_count} yorum
                bu yönde
            </span>

        </div>
    `;
}


function renderProductModal(
    product,
    reviews
) {

    if (!modalContent) return;

    const description =
    product.description_tr ||
    product.description ||
    "Bu ürün için açıklama bulunmuyor.";


    const features =
    product.features_tr ||
    product.features ||
    "";


    modalContent.innerHTML = `

        <div class="modal-grid">

            <div class="modal-img-wrap">

                <img
                    src="${safeImage(product.image_url)}"
                    alt="${escapeHTML(product.title)}"
                >

            </div>


            <div class="modal-product-info">

                ${
                    product.brand
                        ? `
                            <span class="badge">
                                ${escapeHTML(product.brand)}
                            </span>
                        `
                        : ""
                }


                <h2 class="modal-title">
                    ${escapeHTML(product.title)}
                </h2>


                ${
                    product.category
                        ? `
                            <p>
                                ${escapeHTML(product.category)}
                            </p>
                        `
                        : ""
                }


                ${
                    product.rating
                        ? `
                            <div class="product-rating">

                                <i class="fa-solid fa-star"></i>

                                <span>
                                    ${Number(product.rating).toFixed(1)}

                                    ${
                                        product.rating_count
                                            ? `(${Number(product.rating_count).toLocaleString("en-US")})`
                                            : ""
                                    }
                                </span>

                            </div>
                        `
                        : ""
                }


                <div class="price-row">

                    <span class="current-price">
                        ${formatPrice(product.price)}
                    </span>


                    ${
                        product.list_price
                            ? `
                                <span class="old-price">
                                    ${formatPrice(product.list_price)}
                                </span>
                            `
                            : ""
                    }

                </div>


                ${renderFitAdvice(product.fit)}


                ${
                    product.availability
                        ? `
                            <p>
                                <strong>
                                    Stok:
                                </strong>

                                ${escapeHTML(product.availability)}
                            </p>
                        `
                        : ""
                }


                <p style="margin-top:20px; line-height:1.8;">
                    ${escapeHTML(description)}
                </p>


                <!--
                    "AMAZON'DA GÖR" BAĞLANTISI KALDIRILDI.

                    product_url alanı veritabanında duruyor
                    (katalog Amazon kaynaklı), ama kullanıcıya
                    gösterilmiyor. Sebep: satın alma akışı
                    WishNN'in kendisinde — hemen altta TEK
                    TIKLA SATIN AL, SEPETE EKLE ve FAVORİLERE
                    EKLE var. Müşteriyi ürünü görmeye başka
                    bir siteye yollamak, kendi sepetini
                    boşaltmak demek.

                    Asistanın önerdiği ürünler de zaten bu
                    kataloğun kendisinden geliyor
                    (backend/app/assistant.py -> search_catalog
                    -> kendi Postgres'imiz); dışarı çıkan tek
                    şey bu bağlantıydı.
                -->


                <button
                    type="button"
                    class="modal-quick-buy"
                    id="modal-quick-buy"
                    ${hasPrice(product) ? "" : "disabled"}
                >
                    ${icon("zap")}
                    ${
                        hasPrice(product)
                            ? "TEK TIKLA SATIN AL"
                            : "FİYAT BİLGİSİ YOK"
                    }
                </button>


                <button
                    type="button"
                    class="modal-add-cart${
                        isInCart(product.product_id) ? " active" : ""
                    }"
                    id="modal-add-cart"
                    ${hasPrice(product) ? "" : "disabled"}
                >
                    <i class="fa-solid fa-bag-shopping"></i>
                    SEPETE EKLE
                </button>


                <button
                    type="button"
                    class="modal-wishlist-btn"
                    id="modal-wishlist-btn"
                >
                    <i class="fa-regular fa-heart"></i>
                    FAVORİLERE EKLE
                </button>


                <!-- Urunu arkadasa gonder. Secim penceresi
                     #share-overlay; oradan /social/messages'a
                     product_id ile gidiyor. -->
                <button
                    type="button"
                    class="modal-wishlist-btn"
                    id="modal-share-btn"
                >
                    <i class="fa-regular fa-paper-plane"></i>
                    ARKADAŞINA GÖNDER
                </button>

            </div>

        </div>


        <div class="reviews-section">

            <h3>
                Müşteri Yorumları
            </h3>

            <!-- Form yorumlarin USTUNDE: yuzlerce veri seti
                 yorumunun altina koymak, kullanicinin
                 yorum yazabildigini hic gormemesi demekti. -->
            ${renderReviewForm(product.product_id, findMyReview(reviews))}

            <div id="reviews-list">
                ${renderReviews(reviews)}
            </div>

        </div>
    `;


    $("modal-quick-buy")
        ?.addEventListener("click", () =>
            openQuickCheckout(
                { product },
                { source: "detail" }
            )
        );


    $("modal-add-cart")
        ?.addEventListener("click", event =>
            handleModalAddToCart(product, event.currentTarget)
        );


    $("modal-share-btn")
        ?.addEventListener("click", () => openShare(product));

    setupModalWishlistButton(product);

    setupReviewForm(product);

    hydrateIcons(modalContent);
}


/* =========================================================
   YORUM YAZMA
   ---------------------------------------------------------
   Veri setinden gelen yorumlar READ-ONLY; buradaki her sey
   kullanicinin KENDI yorumu icin. Bir kullanici urun basina
   tek yorum yazar, ikinci gonderim onu gunceller.
========================================================= */

/** Listedeki "benim" yorumum (yoksa null). */
function findMyReview(reviews) {

    if (!Array.isArray(reviews)) return null;

    return reviews.find(review => review.is_mine) || null;
}


function setupReviewForm(product) {

    /* Misafir: form yerine giris cagrisi duruyor */
    $("review-login-btn")?.addEventListener("click", () => {

        closeModal();

        openAuth("Yorum yazmak için giriş yap.");
    });


    /* Yildiz secimi */
    $("review-stars-input")?.addEventListener("click", event => {

        const star = event.target.closest("[data-rating]");

        if (!star) return;

        const value = Number(star.dataset.rating);

        const field = $("review-rating");

        if (field) {
            field.value = String(value);
        }

        /* Secilen ve solundaki yildizlar dolu gorunur */
        $("review-stars-input")
            ?.querySelectorAll("[data-rating]")
            .forEach(item => {

                item.classList.toggle(
                    "on",
                    Number(item.dataset.rating) <= value
                );
            });
    });


    $("review-form")?.addEventListener("submit", event => {

        event.preventDefault();

        submitReview(product);
    });


    /* Kendi yorumundaki sil / duzenle */
    $("reviews-list")?.addEventListener("click", event => {

        if (event.target.closest("[data-review-delete]")) {
            deleteMyReview(product);
            return;
        }

        if (event.target.closest("[data-review-edit]")) {

            /* Form zaten mevcut yorumla dolu aciliyor;
               yapilacak tek sey oraya goturmek. */
            $("review-form")?.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });

            $("review-text")?.focus();
        }
    });
}


async function submitReview(product) {

    const ratingField = $("review-rating");
    const textField = $("review-text");
    const titleField = $("review-title");
    const message = $("review-form-message");
    const button = $("review-submit");

    const rating = Number(ratingField?.value || 0);
    const text = (textField?.value || "").trim();


    /* Sunucu da dogruluyor; burada erken uyarmak
       gonderip hata almaktan iyi. */
    if (!rating) {
        setMessage(message, "Kaç yıldız verdiğini seç.", "error");
        return;
    }

    if (text.length < 3) {
        setMessage(message, "Birkaç kelime de yazar mısın?", "error");
        return;
    }


    setMessage(message, "");

    if (button) button.disabled = true;

    try {

        await apiFetch(
            `/products/${encodeURIComponent(product.product_id)}/reviews`,
            {
                method: "POST",
                body: JSON.stringify({
                    rating,
                    review_text: text,
                    review_title: (titleField?.value || "").trim() || null,
                }),
            }
        );

        showToast({
            title: "Yorumun kaydedildi",
            message: "Teşekkürler, yorumun yayında.",
            tone: "success",
        });

        await refreshModalReviews(product);


    } catch (error) {

        console.error("Yorum kaydedilemedi:", error);

        setMessage(
            message,
            error.message || "Yorum kaydedilemedi.",
            "error"
        );

    } finally {
        if (button) button.disabled = false;
    }
}


async function deleteMyReview(product) {

    if (!window.confirm("Yorumunu silmek istediğine emin misin?")) {
        return;
    }

    try {

        await apiFetch(
            `/products/${encodeURIComponent(product.product_id)}` +
            "/reviews/mine",
            { method: "DELETE" }
        );

        showToast({
            title: "Yorum silindi",
            message: "Yorumun kaldırıldı.",
            tone: "neutral",
        });

        await refreshModalReviews(product);


    } catch (error) {

        console.error("Yorum silinemedi:", error);

        showToast({
            title: "Silinemedi",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });
    }
}


/**
 * Yorum listesini ve formu yeniden cizer.
 *
 * Modalin tamamini yeniden cizmiyoruz: kullanicinin
 * kaydirma konumu ve galerideki secili gorsel korunuyor.
 */
async function refreshModalReviews(product) {

    const list = $("reviews-list");

    if (!list) return;

    try {

        const reviews = await apiFetch(
            `/products/${encodeURIComponent(product.product_id)}` +
            "/reviews?limit=20&offset=0"
        );

        const items = Array.isArray(reviews) ? reviews : [];

        list.innerHTML = renderReviews(items);

        /* Form da tazelensin: yorum silindiyse "gonder"e,
           eklendiyse "guncelle"ye donmeli. */
        const form = $("review-form");
        const mine = findMyReview(items);

        if (form) {

            const holder = document.createElement("div");

            holder.innerHTML = renderReviewForm(
                product.product_id,
                mine
            );

            const fresh = holder.firstElementChild;

            if (fresh) {
                form.replaceWith(fresh);
                setupReviewForm(product);
            }
        }


    } catch (error) {

        console.error("Yorumlar tazelenemedi:", error);
    }
}


async function handleModalAddToCart(product, button) {

    if (!isUserLoggedIn()) {

        openAuth("Sepete eklemek için giriş yap.");

        return;
    }


    button.disabled = true;

    try {

        await addToCart(product.product_id, { source: "detail" });

        button.classList.add("active");

        showToast({
            title: "Sepete eklendi",
            message: `${productTitle(product)} sepetine eklendi.`,
            tone: "success",
        });


    } catch (error) {

        console.error("Sepete eklenemedi:", error);

        showToast({
            title: "Sepete eklenemedi",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });

    } finally {

        button.disabled = !hasPrice(product);
    }
}


/* =========================================================
   REVIEWS
========================================================= */

/**
 * Yildiz gosterimi. Dolu/bos yildiz, 1-5.
 *
 * Veri setinde ondalikli puanlar var (4.3 gibi); en yakin
 * tam yildiza yuvarliyoruz — yarim yildiz cizmek icin ayri
 * bir ikon seti gerekirdi.
 */
function starRow(rating) {

    const value = Math.round(Number(rating) || 0);

    let out = "";

    for (let i = 1; i <= 5; i += 1) {
        out += i <= value ? "★" : "☆";
    }

    return out;
}


function formatReviewDate(value) {

    if (!value) return "";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "";

    return date.toLocaleDateString("tr-TR", {
        day: "numeric",
        month: "long",
        year: "numeric",
    });
}


function renderReviews(reviews) {

    if (!Array.isArray(reviews) || !reviews.length) {

        return `
            <p class="reviews-empty">
                Bu ürün için henüz yorum yok. İlk yorumu sen yaz.
            </p>
        `;
    }


    return reviews
        .map(review => {

            /*
               Kimin yorumu:
                 author_name dolu  -> bu sitede yazilmis
                 author_name None  -> Amazon veri setinden
               Veri seti yorumlarinda yazar adi YOK, uydurmuyoruz.
            */
            const author = review.author_name
                ? escapeHTML(review.author_name)
                : "Doğrulanmış alıcı";

            const date = formatReviewDate(review.created_at);

            return `
            <div class="review-card${review.is_mine ? " mine" : ""}">

                <div class="review-header">

                    <strong>
                        ${escapeHTML(
                            review.review_title ||
                            "Değerlendirme"
                        )}
                    </strong>

                    <span class="review-stars">
                        ${starRow(review.rating)}
                    </span>

                </div>


                <div class="review-meta">

                    <span class="review-author">${author}</span>

                    ${date ? `<span>${escapeHTML(date)}</span>` : ""}

                    ${
                        review.verified_purchase
                            ? '<span class="review-verified">✓ Satın aldı</span>'
                            : ""
                    }

                    ${
                        review.is_mine
                            ? '<span class="review-own-tag">Senin yorumun</span>'
                            : ""
                    }

                </div>


                ${
                    review.review_text
                        ? `
                            <p>
                                ${escapeHTML(
                                    review.review_text
                                )}
                            </p>
                        `
                        : ""
                }


                ${
                    review.is_mine
                        ? `
                            <div class="review-own-actions">
                                <button
                                    type="button"
                                    data-review-edit
                                >
                                    Düzenle
                                </button>
                                <button
                                    type="button"
                                    class="danger"
                                    data-review-delete
                                >
                                    Sil
                                </button>
                            </div>
                        `
                        : ""
                }

            </div>
        `;
        })
        .join("");
}


/**
 * "Yorum yaz" formu.
 *
 * Misafire form GOSTERILMIYOR: doldurup gonderemeyecegi bir
 * formu doldurtmak, girisi en sonda istemek demek olurdu.
 * Onun yerine giris cagrisi var.
 *
 * mine: kullanicinin bu urune yazdigi mevcut yorum (varsa).
 * Varsa form onun degerleriyle dolu aciliyor — bir kullanici
 * urun basina tek yorum yazabiliyor, ikinci gonderim
 * duzenleme oluyor (bkz. uq_review_user_product).
 */
function renderReviewForm(productId, mine) {

    if (!isUserLoggedIn()) {

        return `
            <div class="review-form-login">
                <p>Bu ürüne yorum yazmak için giriş yapmalısın.</p>
                <button type="button" id="review-login-btn">
                    GİRİŞ YAP
                </button>
            </div>
        `;
    }


    const rating = mine ? Math.round(Number(mine.rating) || 0) : 0;

    return `
        <form
            class="review-form"
            id="review-form"
            data-product-id="${escapeHTML(String(productId))}"
        >

            <span class="review-form-label">
                ${mine ? "Yorumunu düzenle" : "Bu ürünü değerlendir"}
            </span>


            <div class="review-stars-input" id="review-stars-input">
                ${
                    [1, 2, 3, 4, 5]
                        .map(value => `
                            <button
                                type="button"
                                class="review-star${value <= rating ? " on" : ""}"
                                data-rating="${value}"
                                aria-label="${value} yıldız"
                            >★</button>
                        `)
                        .join("")
                }
                <input
                    type="hidden"
                    id="review-rating"
                    value="${rating || ""}"
                >
            </div>


            <input
                type="text"
                id="review-title"
                maxlength="120"
                placeholder="Başlık (isteğe bağlı)"
                value="${escapeHTML(mine?.review_title || "")}"
            >

            <textarea
                id="review-text"
                rows="3"
                maxlength="2000"
                placeholder="Ürün hakkındaki düşüncelerin..."
            >${escapeHTML(mine?.review_text || "")}</textarea>

            <p class="review-form-message" id="review-form-message"></p>

            <button type="submit" id="review-submit">
                ${mine ? "YORUMU GÜNCELLE" : "YORUMU GÖNDER"}
            </button>

        </form>
    `;
}


/* =========================================================
   MODAL
========================================================= */

function setupModal() {

    closeModalButton?.addEventListener(
        "click",
        closeModal
    );


    productModal?.addEventListener(
        "click",
        event => {

            if (
                event.target === productModal
            ) {
                closeModal();
            }
        }
    );
}


function closeModal() {

    productModal
        ?.classList.add("hidden");
}


/* =========================================================
   SONSUZ AKIS  (sayfalama kaldirildi)
   ---------------------------------------------------------
   renderPagination() ve pageButton() silindi. Sayfa
   numaralari ve ok isaretleri yerine sentinel tabanli
   sonsuz akis var.

   IntersectionObserver desteklenmeyen ortamlarda "DAHA
   FAZLA GOSTER" butonu yedek olarak calisiyor.
========================================================= */

function setupInfiniteScroll(
    sentinelId,
    buttonId,
    loadMore,
    shouldLoad,
    observerOptions = {}
) {

    const button = $(buttonId);

    button?.addEventListener("click", () => loadMore());


    const sentinel = $(sentinelId);

    if (!sentinel || typeof IntersectionObserver === "undefined") {
        return null;
    }


    const observer = new IntersectionObserver(
        entries => {

            if (!entries[0].isIntersecting) return;

            if (shouldLoad && !shouldLoad()) return;

            loadMore();
        },
        {
            /*
               Sentinel ekrana girmeden onceden tetikle:
               kullanici bekleme gormesin. Dikey akista
               yukari/asagi, yatay akista sag tarafa dogru
               genisletiyoruz (bkz. root/rootMargin override).
            */
            root: observerOptions.root ?? null,
            rootMargin: observerOptions.rootMargin ?? "300px 0px",
            threshold: 0,
        }
    );

    observer.observe(sentinel);

    return observer;
}


/* =========================================================
   AUTH — DOM
========================================================= */

const registerOverlay = $("register-overlay");
const registerCloseButton = $("register-close");
const registerForm = $("register-form");
const registerMessage = $("register-message");

const userMenuButton = $("user-menu-btn");
const userDropdown = $("user-dropdown");
const userAvatarInitials = $("user-avatar-initials");

const userDropdownHead = $("user-dropdown-head");
const userDropdownName = $("user-dropdown-name");
const userDropdownEmail = $("user-dropdown-email");

const dropdownLoginButton = $("dropdown-login-btn");
const dropdownRegisterButton = $("dropdown-register-btn");
const dropdownAccountButton = $("dropdown-account-btn");
const dropdownLogoutButton = $("dropdown-logout-btn");


/* =========================================================
   HESABIM — DOM
========================================================= */

const accountOverlay = $("account-overlay");
const accountCloseButton = $("account-close");
const accountAvatarLarge = $("account-avatar-lg");

const accountProfileForm = $("account-profile-form");
const accountProfileMessage = $("account-profile-message");

const accountCurrentEmailInput = $("account-current-email");
const accountEmailForm = $("account-email-form");
const accountEmailMessage = $("account-email-message");

const accountPasswordForm = $("account-password-form");
const accountPasswordMessage = $("account-password-message");


/* =========================================================
   AUTH
========================================================= */

function setupAuth() {

    /* KULLANICI MENÜSÜ */

    userMenuButton?.addEventListener("click", event => {

        event.stopPropagation();

        userDropdown?.classList.toggle("open");
    });


    document.addEventListener("click", event => {

        if (
            !userMenuButton?.contains(event.target) &&
            !userDropdown?.contains(event.target)
        ) {
            userDropdown?.classList.remove("open");
        }
    });


    dropdownLoginButton?.addEventListener("click", () => {

        userDropdown?.classList.remove("open");

        openAuth();
    });


    dropdownRegisterButton?.addEventListener("click", () => {

        userDropdown?.classList.remove("open");

        openRegister();
    });


    dropdownAccountButton?.addEventListener("click", () => {

        userDropdown?.classList.remove("open");

        openAccount();
    });


    dropdownLogoutButton?.addEventListener("click", logout);


    /* İKİ EKRAN ARASINDA GEÇİŞ */

    $("go-register-btn")
        ?.addEventListener("click", openRegister);

    $("go-login-btn")
        ?.addEventListener("click", () => openAuth());


    /* KAPATMA */

    authCloseButton?.addEventListener("click", closeAuth);

    authOverlay?.addEventListener("click", event => {

        if (event.target === authOverlay) {
            closeAuth();
        }
    });


    registerCloseButton
        ?.addEventListener("click", closeRegister);

    registerOverlay?.addEventListener("click", event => {

        if (event.target === registerOverlay) {
            closeRegister();
        }
    });


    accountCloseButton
        ?.addEventListener("click", closeAccount);

    accountOverlay?.addEventListener("click", event => {

        if (event.target === accountOverlay) {
            closeAccount();
        }
    });


    /* ESC ile açık katmanı kapat */

    document.addEventListener("keydown", event => {

        if (event.key !== "Escape") return;

        closeAuth();
        closeRegister();
        closeAccount();
        closeQuickCheckout();
        closeWishlistPanel();
        closeModal();
        closeSearchOverlay();

        mobileMenu?.classList.remove("open");
    });


    /* ŞİFRE GÖSTER / GİZLE */

    document
        .querySelectorAll("[data-reveal]")
        .forEach(button => {

            button.addEventListener("click", () => {

                const input = $(button.dataset.reveal);

                if (!input) return;


                const show = input.type === "password";

                input.type = show ? "text" : "password";

                button.innerHTML =
                    show
                        ? '<i class="fa-regular fa-eye-slash"></i>'
                        : '<i class="fa-regular fa-eye"></i>';

                button.setAttribute(
                    "aria-label",
                    show
                        ? "Şifreyi gizle"
                        : "Şifreyi göster"
                );
            });
        });


    loginForm?.addEventListener("submit", handleLogin);

    registerForm?.addEventListener("submit", handleRegister);

    accountProfileForm
        ?.addEventListener("submit", handleAccountProfileSubmit);

    accountEmailForm
        ?.addEventListener("submit", handleAccountEmailSubmit);

    accountPasswordForm
        ?.addEventListener("submit", handleAccountPasswordSubmit);
}


/* ---------------------------------------------------------
   OVERLAY AÇ / KAPAT
--------------------------------------------------------- */

function openAuth(message = "") {

    closeRegister();

    loginForm?.reset();

    clearFieldErrors(loginForm);

    setMessage(loginMessage, message);

    authOverlay?.classList.add("open");

    setTimeout(() => loginEmail?.focus(), 220);
}


function closeAuth() {

    authOverlay?.classList.remove("open");
}


function openRegister() {

    closeAuth();

    clearFieldErrors(registerForm);

    setMessage(registerMessage, "");

    registerOverlay?.classList.add("open");

    setTimeout(
        () => $("register-first-name")?.focus(),
        220
    );
}


function closeRegister() {

    registerOverlay?.classList.remove("open");
}


/* ---------------------------------------------------------
   HESABIM
--------------------------------------------------------- */

function renderAccountAvatar() {

    const user = getCurrentUser();

    if (accountAvatarLarge) {

        accountAvatarLarge.textContent =
            user
                ? getInitials(user.first_name, user.last_name)
                : "";
    }
}


/**
 * Hesap ekranini acar ve formlari mevcut kullanici bilgisiyle
 * doldurur. Once localStorage'daki (anlik gorunum icin), sonra
 * /auth/me'den gelen guncel veriyle (bkz. arka planda cagri) —
 * boylece ekran hemen acilir ama gosterilen veri sunucudan
 * dogrulanmis olur.
 */
async function openAccount() {

    const user = getCurrentUser();

    if (!user) {

        openAuth("Hesabını görüntülemek için giriş yap.");

        return;
    }


    closeAuth();
    closeRegister();

    [
        accountProfileForm,
        accountEmailForm,
        accountPasswordForm,
    ].forEach(form => {

        clearFieldErrors(form);
    });

    setMessage(accountProfileMessage, "");
    setMessage(accountEmailMessage, "");
    setMessage(accountPasswordMessage, "");

    accountPasswordForm?.reset();

    fillAccountForms(user);
    renderAccountAvatar();

    accountOverlay?.classList.add("open");


    /* Ekran acildiktan sonra sunucudaki guncel veriyle
       senkronize et — baska bir sekmede degisiklik olmus
       olabilir. Basarisiz olursa sessizce onbellekte kalinir. */

    try {

        const fresh = await apiFetch("/auth/me");

        updateSessionUser(fresh);

        fillAccountForms(fresh);

    } catch (error) {

        console.warn(
            "Güncel hesap bilgisi alınamadı:",
            error
        );
    }
}


function closeAccount() {

    accountOverlay?.classList.remove("open");
}


function fillAccountForms(user) {

    if (!user) return;


    const firstNameInput = $("account-first-name");
    const lastNameInput = $("account-last-name");
    const genderInput = $("account-gender");
    const ageInput = $("account-age");
    const addressInput = $("account-address");

    if (firstNameInput) firstNameInput.value = user.first_name || "";
    if (lastNameInput) lastNameInput.value = user.last_name || "";
    if (genderInput) genderInput.value = user.gender || "";
    if (ageInput) ageInput.value = user.age ?? "";
    if (addressInput) addressInput.value = user.address || "";

    if (accountCurrentEmailInput) {
        accountCurrentEmailInput.value = user.email || "";
    }
}


async function handleAccountProfileSubmit(event) {

    event.preventDefault();

    clearFieldErrors(accountProfileForm);

    setMessage(accountProfileMessage, "");


    const firstNameInput = $("account-first-name");
    const lastNameInput = $("account-last-name");
    const genderInput = $("account-gender");
    const ageInput = $("account-age");
    const addressInput = $("account-address");

    const firstName = firstNameInput?.value.trim() || "";
    const lastName = lastNameInput?.value.trim() || "";
    const gender = genderInput?.value || "";
    const address = addressInput?.value.trim() || "";

    const ageRaw = ageInput?.value.trim() || "";
    const age = ageRaw ? Number(ageRaw) : null;


    let valid = true;

    if (!firstName) {
        setFieldError(firstNameInput, "Adını gir.");
        valid = false;
    }

    if (!lastName) {
        setFieldError(lastNameInput, "Soyadını gir.");
        valid = false;
    }

    if (
        age !== null &&
        (!Number.isFinite(age) || age < 13 || age > 100)
    ) {
        setFieldError(
            ageInput,
            "Yaş 13 ile 100 arasında olmalı."
        );
        valid = false;
    }

    if (!valid) return;


    const submitButton = $("account-profile-submit");

    setButtonLoading(submitButton, true);

    try {

        const updated = await apiFetch("/auth/profile", {
            method: "PATCH",
            body: JSON.stringify({
                first_name: firstName,
                last_name: lastName,
                gender: gender || null,
                age,
                address: address || null,
            }),
        });

        updateSessionUser(updated);
        fillAccountForms(updated);

        setMessage(
            accountProfileMessage,
            "Bilgilerin güncellendi.",
            "success"
        );

    } catch (error) {

        console.error("Profil güncelleme hatası:", error);

        setMessage(
            accountProfileMessage,
            error.message ||
            "Bilgiler güncellenirken bir hata oluştu.",
            "error"
        );

    } finally {

        setButtonLoading(submitButton, false);
    }
}


async function handleAccountEmailSubmit(event) {

    event.preventDefault();

    clearFieldErrors(accountEmailForm);

    setMessage(accountEmailMessage, "");


    const newEmailInput = $("account-new-email");
    const passwordInput = $("account-email-password");

    const newEmail = newEmailInput?.value.trim() || "";
    const currentPassword = passwordInput?.value || "";


    let valid = true;

    if (!isValidEmail(newEmail)) {
        setFieldError(
            newEmailInput,
            "Geçerli bir e-posta adresi gir."
        );
        valid = false;
    }

    if (!currentPassword) {
        setFieldError(passwordInput, "Mevcut şifreni gir.");
        valid = false;
    }

    if (!valid) return;


    const submitButton = $("account-email-submit");

    setButtonLoading(submitButton, true);

    try {

        const updated = await apiFetch("/auth/email", {
            method: "PATCH",
            body: JSON.stringify({
                new_email: newEmail,
                current_password: currentPassword,
            }),
        });

        updateSessionUser(updated);
        fillAccountForms(updated);

        if (newEmailInput) newEmailInput.value = "";
        if (passwordInput) passwordInput.value = "";

        setMessage(
            accountEmailMessage,
            "E-posta adresin güncellendi.",
            "success"
        );

    } catch (error) {

        console.error("E-posta güncelleme hatası:", error);

        setMessage(
            accountEmailMessage,
            error.message ||
            "E-posta güncellenirken bir hata oluştu.",
            "error"
        );

    } finally {

        setButtonLoading(submitButton, false);
    }
}


async function handleAccountPasswordSubmit(event) {

    event.preventDefault();

    clearFieldErrors(accountPasswordForm);

    setMessage(accountPasswordMessage, "");


    const currentInput = $("account-current-password");
    const newInput = $("account-new-password");
    const confirmInput = $("account-confirm-password");

    const currentPassword = currentInput?.value || "";
    const newPassword = newInput?.value || "";
    const confirmPassword = confirmInput?.value || "";


    let valid = true;

    if (!currentPassword) {
        setFieldError(currentInput, "Mevcut şifreni gir.");
        valid = false;
    }

    if (newPassword.length < 8) {

        setFieldError(
            newInput,
            "Şifre en az 8 karakter olmalı."
        );

        valid = false;

    } else if (
        !/[A-Za-z]/.test(newPassword) ||
        !/\d/.test(newPassword)
    ) {

        setFieldError(
            newInput,
            "Şifre en az bir harf ve bir rakam içermeli."
        );

        valid = false;
    }

    if (confirmPassword !== newPassword) {

        setFieldError(
            confirmInput,
            "Yeni şifreler eşleşmiyor."
        );

        valid = false;
    }

    if (
        valid &&
        currentPassword &&
        newPassword === currentPassword
    ) {

        setFieldError(
            newInput,
            "Yeni şifre mevcut şifreyle aynı olamaz."
        );

        valid = false;
    }

    if (!valid) return;


    const submitButton = $("account-password-submit");

    setButtonLoading(submitButton, true);

    try {

        await apiFetch("/auth/change-password", {
            method: "POST",
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword,
            }),
        });

        accountPasswordForm?.reset();

        setMessage(
            accountPasswordMessage,
            "Şifren başarıyla değiştirildi.",
            "success"
        );

    } catch (error) {

        console.error("Şifre değiştirme hatası:", error);

        setMessage(
            accountPasswordMessage,
            error.message ||
            "Şifre değiştirilirken bir hata oluştu.",
            "error"
        );

    } finally {

        setButtonLoading(submitButton, false);
    }
}


/* ---------------------------------------------------------
   LOGIN
--------------------------------------------------------- */

async function handleLogin(event) {

    event.preventDefault();

    clearFieldErrors(loginForm);

    setMessage(loginMessage, "");


    const email = loginEmail?.value.trim() || "";
    const password = loginPassword?.value || "";


    let valid = true;


    if (!isValidEmail(email)) {

        setFieldError(
            loginEmail,
            "Geçerli bir e-posta adresi gir."
        );

        valid = false;
    }


    if (!password) {

        setFieldError(loginPassword, "Şifreni gir.");

        valid = false;
    }


    if (!valid) return;


    const submitButton = $("login-submit-btn");

    setButtonLoading(submitButton, true);


    try {

        const response = await fetch(
            `${API_BASE}/auth/login`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({ email, password })
            }
        );


        const data =
            await response.json().catch(() => ({}));


        if (!response.ok) {

            throw new Error(
                extractApiError(
                    data,
                    "E-posta veya şifre hatalı."
                )
            );
        }


        signIn(data.user);

        setMessage(
            loginMessage,
            "Giriş başarılı.",
            "success"
        );


        setTimeout(() => {

            closeAuth();

            loginForm?.reset();

            setMessage(loginMessage, "");


            /* Satın almaya giderken giriş istenmişse devam et */

            if (state.pendingQuickBuy) {

                const pending = state.pendingQuickBuy;

                state.pendingQuickBuy = null;

                openQuickCheckout(pending.item, pending.context);
            }

        }, 650);


    } catch (error) {

        console.error("Login error:", error);

        setMessage(
            loginMessage,
            error.message ||
            "Giriş yapılırken bir hata oluştu.",
            "error"
        );

    } finally {

        setButtonLoading(submitButton, false);
    }
}


/* ---------------------------------------------------------
   REGISTER
--------------------------------------------------------- */

async function handleRegister(event) {

    event.preventDefault();

    clearFieldErrors(registerForm);

    setMessage(registerMessage, "");


    const firstNameInput = $("register-first-name");
    const lastNameInput = $("register-last-name");
    const emailInput = $("register-email");
    const genderInput = $("register-gender");
    const ageInput = $("register-age");
    const passwordInput = $("register-password");
    const addressInput = $("register-address");


    const firstName = firstNameInput?.value.trim() || "";
    const lastName = lastNameInput?.value.trim() || "";
    const email = emailInput?.value.trim() || "";
    const gender = genderInput?.value || "";
    const age = Number(ageInput?.value);
    const password = passwordInput?.value || "";
    const address = addressInput?.value.trim() || "";


    let valid = true;


    if (!firstName) {

        setFieldError(firstNameInput, "Adını gir.");

        valid = false;
    }


    if (!lastName) {

        setFieldError(lastNameInput, "Soyadını gir.");

        valid = false;
    }


    if (!isValidEmail(email)) {

        setFieldError(
            emailInput,
            "Geçerli bir e-posta adresi gir."
        );

        valid = false;
    }


    if (!gender) {

        setFieldError(genderInput, "Bir seçim yap.");

        valid = false;
    }


    if (!Number.isFinite(age) || age < 13 || age > 100) {

        setFieldError(
            ageInput,
            "Yaş 13 ile 100 arasında olmalı."
        );

        valid = false;
    }


    if (password.length < 6) {

        setFieldError(
            passwordInput,
            "Şifre en az 6 karakter olmalı."
        );

        valid = false;
    }


    if (!valid) return;


    const submitButton = $("register-submit-btn");

    setButtonLoading(submitButton, true);


    try {

        const response = await fetch(
            `${API_BASE}/auth/register`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    first_name: firstName,
                    last_name: lastName,
                    email,
                    gender,
                    age,
                    password,
                    address: address || null
                })
            }
        );


        const data =
            await response.json().catch(() => ({}));


        if (!response.ok) {

            throw new Error(
                extractApiError(
                    data,
                    "Hesap oluşturulamadı."
                )
            );
        }


        /*
           Kayit sonrasi kullaniciyi tekrar giris yapmaya
           zorlamiyoruz: backend kullanici bilgisini
           donduruyor, dogrudan oturum aciyoruz.
        */

        signIn(data.user);

        setMessage(
            registerMessage,
            "Hesabın oluşturuldu. Hoş geldin!",
            "success"
        );


        setTimeout(() => {

            closeRegister();

            registerForm?.reset();

            setMessage(registerMessage, "");


            if (state.pendingQuickBuy) {

                const pending = state.pendingQuickBuy;

                state.pendingQuickBuy = null;

                openQuickCheckout(pending.item, pending.context);
            }

        }, 900);


    } catch (error) {

        console.error("Register error:", error);

        setMessage(
            registerMessage,
            error.message ||
            "Hesap oluşturulurken bir hata oluştu.",
            "error"
        );

    } finally {

        setButtonLoading(submitButton, false);
    }
}


/* ---------------------------------------------------------
   OTURUM
--------------------------------------------------------- */

function signIn(user) {

    if (!user) return;

    localStorage.setItem(
        "user",
        JSON.stringify(user)
    );

    renderUserArea();

    /* Favoriler ve Kesfet yeni kullaniciya gore tazelenir */
    onSessionChanged();
}


function logout() {

    localStorage.removeItem("user");

    userDropdown?.classList.remove("open");

    state.pendingQuickBuy = null;

    /*
       Hizli satin alma formu kisisel bilgi tutuyor. Ayni
       tarayiciyi baska bir kullanici kullanabilecegi icin
       cikista temizliyoruz.
    */

    quickForm?.reset();
    clearFieldErrors(quickForm);

    closeQuickCheckout();
    closeAccount();

    accountPasswordForm?.reset();

    renderUserArea();

    state.wishlist = new Set();
    state.wishlistItems = [];

    closeWishlistPanel();

    state.cart = [];

    renderCartBadge();

    closeCartPanel();

    onSessionChanged();
}


/**
 * Ad/soyaddan avatar bas harflerini uretir.
 *
 * "Pınar Tunca" -> "PT", "Pınar" -> "P". Alanlar bastan/sondan
 * ve aradan fazla bosluktan arindirilir; sadece ilk harf
 * kullanildigi icin bir alan icindeki fazladan bosluklar
 * sonucu etkilemez. toLocaleUpperCase("tr") kullaniliyor ki
 * "i" -> "İ" gibi Turkce harf kurallarina uysun.
 */
function getInitials(firstName, lastName) {

    const first =
        String(firstName || "").trim().charAt(0);

    const last =
        String(lastName || "").trim().charAt(0);

    return (first + last).toLocaleUpperCase("tr");
}


function renderUserArea() {

    const user = getCurrentUser();

    const signedIn = Boolean(user);

    const initials =
        signedIn
            ? getInitials(user.first_name, user.last_name)
            : "";


    userMenuButton
        ?.classList.toggle("signed-in", signedIn);

    userMenuButton
        ?.classList.toggle("has-avatar", Boolean(initials));

    if (userAvatarInitials) {
        userAvatarInitials.textContent = initials;
    }

    userDropdownHead
        ?.classList.toggle("hidden", !signedIn);

    dropdownLoginButton
        ?.classList.toggle("hidden", signedIn);

    dropdownRegisterButton
        ?.classList.toggle("hidden", signedIn);

    dropdownAccountButton
        ?.classList.toggle("hidden", !signedIn);

    dropdownLogoutButton
        ?.classList.toggle("hidden", !signedIn);


    if (!signedIn) {

        userMenuButton?.setAttribute(
            "aria-label",
            "Kullanıcı Menüsü"
        );

        return;
    }


    const fullName =
        [user.first_name, user.last_name]
            .filter(Boolean)
            .join(" ");


    if (userDropdownName) {

        userDropdownName.textContent =
            fullName || "WishNN Üyesi";
    }


    if (userDropdownEmail) {

        userDropdownEmail.textContent =
            user.email || "";
    }


    userMenuButton?.setAttribute(
        "aria-label",
        `${fullName || "Hesabım"} — hesap menüsü`
    );
}


/**
 * Sunucudan donen guncel kullaniciyi oturuma yazar ve
 * baglayici butun UI'i (avatar, dropdown, hesap ekrani basligi)
 * sayfa yenilenmeden gunceller. signIn'den farki: yeni bir
 * "giris" degil, VAR OLAN oturumun bilgisini tazelemesi
 * (profil/e-posta guncellemesi sonrasi).
 */
function updateSessionUser(user) {

    if (!user) return;

    localStorage.setItem(
        "user",
        JSON.stringify(user)
    );

    renderUserArea();
    renderAccountAvatar();
}


/* ---------------------------------------------------------
   FORM YARDIMCILARI
   login, register ve checkout birlikte kullanir
--------------------------------------------------------- */

function isValidEmail(value) {

    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/
        .test(String(value || "").trim());
}


function setFieldError(input, message) {

    const field = input?.closest(".field");

    if (!field) return;


    field.classList.toggle("invalid", Boolean(message));


    let node = field.querySelector(".field-error");


    if (!message) {

        node?.remove();

        return;
    }


    if (!node) {

        node = document.createElement("span");

        node.className = "field-error";

        field.appendChild(node);
    }


    node.textContent = message;
}


function clearFieldErrors(form) {

    form
        ?.querySelectorAll(".field.invalid")
        .forEach(field =>
            field.classList.remove("invalid")
        );

    form
        ?.querySelectorAll(".field-error")
        .forEach(node => node.remove());
}


function setMessage(element, text, kind) {

    if (!element) return;

    element.textContent = text || "";

    element.classList.remove("error", "success");

    if (kind) {
        element.classList.add(kind);
    }
}


function setButtonLoading(button, loading) {

    if (!button) return;

    button.classList.toggle("loading", loading);

    button.disabled = loading;
}

/*
   FastAPI dogrulama hatalarinda detail bir dizi doner:
   [{loc, msg, type}, ...]. Duz metin mesaja ceviriyoruz.
*/

function extractApiError(data, fallback) {

    const detail = data?.detail;

    if (typeof detail === "string" && detail) {
        return detail;
    }

    if (Array.isArray(detail) && detail.length) {

        const first = detail[0];

        if (first?.msg) {
            return first.msg;
        }
    }

    return fallback;
}






/* =========================================================
   MOBILE
========================================================= */

function setupNavigation() {

    mobileMenuButton?.addEventListener(
        "click",
        () => {

            mobileMenu
                ?.classList.add("open");
        }
    );


    mobileClose?.addEventListener(
        "click",
        () => {

            mobileMenu
                ?.classList.remove("open");
        }
    );
}


/* =========================================================
   BAŞA DÖN
========================================================= */

function setupScrollTop() {

    const button = $("scroll-top-btn");

    if (!button) return;

    const SHOW_AFTER_PX = 120;

    const sync = () => {

        button.classList.toggle(
            "visible",
            window.scrollY > SHOW_AFTER_PX
        );
    };

    window.addEventListener("scroll", sync, { passive: true });

    /* Sayfa kaydirilmis halde acilabilir (yenileme, #anchor) */
    sync();

    button.addEventListener("click", () => {

        window.scrollTo({
            top: 0,
            behavior: "smooth",
        });
    });
}


/* =========================================================
   LOADING / EMPTY
========================================================= */

function showLoader() {

    loader?.classList.remove(
        "hidden"
    );
}


function hideLoader() {

    loader?.classList.add(
        "hidden"
    );
}


function showEmpty(
    title,
    message
) {

    if (!emptyState) return;


    emptyState
        .classList.remove("hidden");


    const heading =
        emptyState.querySelector("h3");

    const paragraph =
        emptyState.querySelector("p");


    if (heading) {
        heading.textContent = title;
    }


    if (paragraph) {
        paragraph.textContent = message;
    }
}


function hideEmpty() {

    emptyState
        ?.classList.add("hidden");
}


/* =========================================================
   HELPERS
========================================================= */
function getCurrentUser() {
    try {
        const user = localStorage.getItem("user");

        if (!user) {
            return null;
        }

        return JSON.parse(user);

    } catch (error) {

        console.error("Kullanıcı bilgisi okunamadı:", error);

        localStorage.removeItem("user");

        return null;
    }
}


function isUserLoggedIn() {
    return !!getCurrentUser();
}

/*
   Urun basligi: Turkce ceviri varsa onu kullanir.
*/

function productTitle(product) {

    return (
        product?.title_tr ||
        product?.title ||
        "Ürün"
    );
}


/*
   Fiyat okuma.

   Dikkat: Number(null) 0 dondurur ve Number.isFinite(0)
   true'dur. Bu yuzden "fiyat var mi" kontrolu dogrudan
   Number.isFinite ile yapilamaz; null, undefined ve bos
   metni ayrica ayiklamak gerekir.
*/

function priceOf(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return NaN;
    }


    const number = Number(value);

    return Number.isFinite(number)
        ? number
        : NaN;
}


function hasPrice(product) {

    return !Number.isNaN(
        priceOf(product?.price)
    );
}


/*
   Katalog fiyatlari USD tutuluyor.
   toTry cevirir, formatTry bicimlendirir.
*/

function toTry(usdValue) {

    return Number(usdValue) * usdTryRate;
}


function formatTry(value) {

    const number = priceOf(value);

    if (Number.isNaN(number)) {
        return "Fiyat yok";
    }

    return new Intl.NumberFormat(
        "tr-TR",
        {
            style: "currency",
            currency: "TRY"
        }
    ).format(number);
}


function formatPrice(value) {

    const number = priceOf(value);

    if (Number.isNaN(number)) {
        return "Fiyat yok";
    }

    return formatTry(toTry(number));
}


function safeImage(value) {

    if (
        typeof value === "string" &&
        value.startsWith("http")
    ) {
        return value;
    }


    return "https://placehold.co/600x800?text=WishNN";
}


function escapeHTML(value) {

    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

/* =========================================================
   AI ARAMA ANALIZI PANELI
   ---------------------------------------------------------
   Arama motorunun sorguyu nasil anladigini gosterir.

   Neden gosteriyoruz: sorguyu sessizce degistiren bir arama
   kullaniciyi sasirtir. "renkli" yazip desenli urunler
   gelince sebebinin gorunmesi lazim. Ayrica yanlis
   anlasilma olursa kullanici bunu gorup sorguyu
   duzeltebiliyor.

   Butun metinler BACKEND'DEN geliyor (query_engine).
   Frontend esik hesabi veya sozluk tutmuyor — ayni gerekce
   explore kartlarindaki match_label icin de gecerliydi.
========================================================= */

const searchAnalysisPanel = $("search-analysis");
const searchAnalysisTerm = $("search-analysis-term");
const searchAnalysisChips = $("search-analysis-chips");
const searchAnalysisNote = $("search-analysis-note");
const searchAnalysisRelaxed = $("search-analysis-relaxed");
const searchAnalysisAlts = $("search-analysis-alts");
const searchAnalysisAltList = $("search-analysis-alt-list");


/* Etiket turune gore ikon. Hepsi Lucide. */
const SEARCH_CHIP_ICONS = {
    gender: "user",
    category: "shirt",
    color: "palette",
    price: "wallet",
    season: "sun",
    pattern: "sparkles",
    fabric: "layers",
    fit: "ruler",
    occasion: "calendar",
};


function hideSearchAnalysis() {

    if (!searchAnalysisPanel) return;

    searchAnalysisPanel.hidden = true;
}


function renderSearchAnalysis(meta) {

    if (!searchAnalysisPanel) return;

    const analysis = state.searchAnalysis;

    if (!analysis) {
        hideSearchAnalysis();
        return;
    }

    searchAnalysisPanel.hidden = false;


    /* ---- temizlenmis arama terimi ---- */

    if (searchAnalysisTerm) {

        const cleaned = analysis.cleaned || "";
        const raw = analysis.raw || "";

        /*
           Sadelestirme olduysa ikisini birlikte gosteriyoruz.
           "arıyorum" kelimesinin neden kaybolduğunu
           kullanicinin gormesi lazim.
        */
        searchAnalysisTerm.textContent =
            cleaned && fold(cleaned) !== fold(raw)
                ? `"${raw}" → "${cleaned}"`
                : `"${cleaned || raw}"`;
    }


    /* ---- etiketler ---- */

    if (searchAnalysisChips) {

        const chips = Array.isArray(analysis.chips)
            ? analysis.chips
            : [];

        searchAnalysisChips.innerHTML = chips
            .map(chip => `
                <span
                    class="search-chip${chip.strict ? " strict" : ""}"
                    title="${
                        chip.strict
                            ? "Kesin filtre: bu şartı taşımayan ürün gelmiyor"
                            : "Sıralama tercihi: bu şarta uyan ürünler öne alınıyor"
                    }"
                >
                    ${icon(SEARCH_CHIP_ICONS[chip.kind] || "sparkles")}
                    ${escapeHTML(chip.label)}
                </span>
            `)
            .join("");

        hydrateIcons(searchAnalysisChips);
    }


    /* ---- yonlendirme notu ---- */

    if (searchAnalysisNote) {
        searchAnalysisNote.textContent = analysis.note || "";
    }


    /* ---- gevsetilen filtreler ---- */

    if (searchAnalysisRelaxed) {

        const relaxed = meta?.relaxed || [];

        /*
           Filtre gevsetildiyse SOYLUYORUZ. Sessizce
           dusurmek, kullanicinin "ben kirmizi istemistim"
           demesine yol acar.
        */
        if (relaxed.length) {

            searchAnalysisRelaxed.hidden = false;

            searchAnalysisRelaxed.innerHTML = `
                ${icon("info")}
                <span>
                    Birebir eşleşme yetersiz kaldı, bu yüzden
                    ${escapeHTML(relaxed.join(", "))}.
                </span>
            `;

            hydrateIcons(searchAnalysisRelaxed);

        } else {
            searchAnalysisRelaxed.hidden = true;
        }
    }


    /* ---- alternatif sorgular ---- */

    if (searchAnalysisAlts && searchAnalysisAltList) {

        const alternatives = Array.isArray(analysis.alternatives)
            ? analysis.alternatives
            : [];

        if (alternatives.length) {

            searchAnalysisAlts.hidden = false;

            searchAnalysisAltList.innerHTML = alternatives
                .map(alt => `
                    <button
                        type="button"
                        class="search-alt"
                        data-search-alt="${escapeHTML(alt)}"
                    >
                        ${escapeHTML(alt)}
                    </button>
                `)
                .join("");

        } else {
            searchAnalysisAlts.hidden = true;
        }
    }


    /* ---- anlamsal arama calismiyorsa uyar ---- */

    if (meta && meta.semantic === false && searchAnalysisNote) {

        /*
           Embedding uretilemedi (API anahtari yok veya servis
           hatasi). Arama kelime eslesmesiyle calisiyor.
           Kullaniciya "AI" diye sunulan bir sey aslinda
           calismiyorsa bunu soylemek gerekiyor.
        */
        searchAnalysisNote.textContent =
            "Anlamsal arama şu an devre dışı; sonuçlar kelime "
            + "eşleşmesine göre sıralandı.";
    }
}


/* Turkce karakterleri ASCII'ye katlar — backend fold()
   fonksiyonunun karsiligi. Yalnizca "sadelestirme oldu mu"
   karsilastirmasi icin kullaniliyor. */
function fold(text) {

    return String(text || "")
        .replace(/[ıİ]/g, "i")
        .replace(/[şŞ]/g, "s")
        .replace(/[ğĞ]/g, "g")
        .replace(/[üÜ]/g, "u")
        .replace(/[öÖ]/g, "o")
        .replace(/[çÇ]/g, "c")
        .toLowerCase()
        .trim();
}


function setupSearchAlternatives() {

    /*
       Olay delegasyonu: butonlar her aramada yeniden
       cizildigi icin tek tek dinleyici baglamak sizinti
       yaratirdi.
    */
    searchAnalysisAltList?.addEventListener("click", event => {

        const button = event.target.closest("[data-search-alt]");

        if (!button) return;

        const alternative = button.dataset.searchAlt || "";

        if (!alternative) return;

        if (searchInput) searchInput.value = alternative;
        if (globalSearchInput) globalSearchInput.value = alternative;

        runSearch(alternative);
    });
}


/* =========================================================
   ARAMA SOZLUKLERI NEREDE?
   ---------------------------------------------------------
   detectCategoryFromQuery / detectColorFromQuery /
   detectGenderFromQuery fonksiyonlari BURADAN KALDIRILDI.

   Yerine backend/app/query_engine.py geldi. Sebepler:

   1. Embedding backend'de uretiliyor. Sorgu zenginlestirmesi
      (yazlik -> ince, keten, sifon...) embedding metnine
      girmezse hicbir ise yaramiyor.

   2. Ayni sozlugu iki yerde tutmak, gun gelip birinin
      guncellenmemesi demek.

   3. Buradaki `text.includes(word)` alt dize aramasi iki
      gercek hata uretiyordu:
        "topuklu ayakkabı" -> "top" eslesti -> kategori shirt
        "manto arıyorum"   -> "man" eslesti -> cinsiyet men
      Backend token tabanli esleme yapiyor.

   Cozumleme sonucu /api/search cevabinda `query` alaninda
   geliyor ve renderSearchAnalysis() ile gosteriliyor.
========================================================= */


/* =========================================================
   CHECKOUT / ÖDEME
========================================================= */

/*
   Kargo kurallari TL uzerinden tanimli.
   Urun fiyatlari USD tutuldugu icin once TL'ye ceviriyoruz.
*/

const SHIPPING_FEE_TRY = 49.90;
const FREE_SHIPPING_LIMIT_TRY = 2500;


/* Tek ekran hizli satin alma */
const checkoutOverlay = $("checkout-overlay");
const checkoutCloseButton = $("checkout-close");
const quickForm = $("quick-form");


/* ---------------------------------------------------------
   AÇ / KAPAT
--------------------------------------------------------- */

/* ---------------------------------------------------------
   ADIMLAR
--------------------------------------------------------- */

/* ---------------------------------------------------------
   SİPARİŞ ÖZETİ
--------------------------------------------------------- */

/* ---------------------------------------------------------
   ADIM 1 DOĞRULAMA — TESLİMAT
--------------------------------------------------------- */

/* ---------------------------------------------------------
   ADIM 2 DOĞRULAMA — KART
--------------------------------------------------------- */

/*
   Luhn kontrolu: yazim hatasi olan kart numaralarini
   yakalar. Gercek bir odeme dogrulamasi degildir.
*/

function isLuhnValid(digits) {

    let sum = 0;
    let double = false;


    for (let i = digits.length - 1; i >= 0; i--) {

        let value = Number(digits[i]);

        if (double) {

            value *= 2;

            if (value > 9) {
                value -= 9;
            }
        }

        sum += value;

        double = !double;
    }


    return sum % 10 === 0;
}


function isExpiryValid(value) {

    const match =
        /^(\d{2})\/(\d{2})$/.exec(
            String(value || "").trim()
        );

    if (!match) return false;


    const month = Number(match[1]);
    const year = 2000 + Number(match[2]);


    if (month < 1 || month > 12) return false;


    const now = new Date();

    /* Ayin son gunu: kart o ayin sonuna kadar gecerli */

    const expiry = new Date(year, month, 0, 23, 59, 59);


    return expiry >= now;
}


/* ---------------------------------------------------------
   SİPARİŞİ TAMAMLA
--------------------------------------------------------- */

/* =========================================================
   API — KIMLIKLI ISTEK
========================================================= */

/*
   Backend kullaniciyi X-User-Id basligindan okuyor
   (henuz JWT yok). Kimlik gerektiren butun istekler
   bu yardimcidan geciyor; JWT'ye gecildiginde
   yalnizca authHeaders degisecek.
*/

function authHeaders() {

    const user = getCurrentUser();

    return user?.id
        ? { "X-User-Id": String(user.id) }
        : {};
}


async function apiFetch(path, options = {}) {

    const response = await fetch(
        `${API_BASE}${path}`,
        {
            ...options,

            headers: {
                "Content-Type": "application/json",
                ...authHeaders(),
                ...(options.headers || {}),
            },
        }
    );


    const data =
        await response.json().catch(() => ({}));


    if (!response.ok) {

        throw new Error(
            extractApiError(
                data,
                `${response.status} ${response.statusText}`
            )
        );
    }


    return data;
}


/* =========================================================
   VIEW KAYDI
========================================================= */

/*
   VIEW olaylari cok sik uretilir. Her kart icin ayri istek
   atmak yerine kuyruga alip toplu gonderiyoruz.
*/

const VIEW_FLUSH_DELAY = 2500;
const VIEW_QUEUE_LIMIT = 20;
const VIEW_DWELL_MS = 800;

const viewQueue = [];
const viewedThisSession = new Set();

let viewFlushTimer = null;


function queueView(productId, source, position, matchScore = null) {

    if (!productId || !isUserLoggedIn()) {
        return;
    }


    /*
       Ayni urunu ayni oturumda tekrar tekrar kaydetmiyoruz:
       kaydirma sirasinda kart ekrana birkac kez girip cikar
       ve veri sisirilir.
    */

    const key = `${source}:${productId}`;

    if (viewedThisSession.has(key)) {
        return;
    }

    viewedThisSession.add(key);


    viewQueue.push({
        product_id: productId,
        interaction_type: "VIEW",
        source: source,
        position: position ?? null,

        /*
           Gorulme aninda gosterilen AI skoru. Egitimde
           "gosterildi ama etkilesim almadi" ornekleri
           (negative sampling) icin gerekli.
        */
        match_score:
            matchScore === null || matchScore === undefined
                ? null
                : matchScore,
    });


    if (viewQueue.length >= VIEW_QUEUE_LIMIT) {

        flushViews();

        return;
    }


    clearTimeout(viewFlushTimer);

    viewFlushTimer = setTimeout(
        flushViews,
        VIEW_FLUSH_DELAY
    );
}


function flushViews(useKeepalive = false) {

    clearTimeout(viewFlushTimer);

    if (!viewQueue.length || !isUserLoggedIn()) {
        return;
    }


    const items = viewQueue.splice(0, VIEW_QUEUE_LIMIT);


    /*
       keepalive: sekme kapanirken de istegin tamamlanmasini
       saglar. Basarisiz olursa sessizce vazgeciyoruz;
       VIEW kaybi kritik degil.
    */

    fetch(
        `${API_BASE}/interactions/batch`,
        {
            method: "POST",

            headers: {
                "Content-Type": "application/json",
                ...authHeaders(),
            },

            body: JSON.stringify({ items }),

            keepalive: useKeepalive,
        }
    ).catch(error => {

        console.warn("VIEW kaydi gonderilemedi:", error);
    });
}


function setupViewTracking() {

    /* Sekme kapanirken kuyrugu bosalt */

    const flushAll = () => {

        flushViews(true);

        /*
           Geri alma suresi icinde sekme kapanirsa: kullanici
           eylemi yapti ve geri almadi, kaydetmek dogru
           varsayilan.
        */
        flushPendingDislikes();
    };


    window.addEventListener("pagehide", flushAll);


    document.addEventListener("visibilitychange", () => {

        if (document.visibilityState === "hidden") {
            flushAll();
        }
    });
}


/* =========================================================
   WISHLIST
========================================================= */

async function loadWishlist() {

    if (!isUserLoggedIn()) {

        state.wishlist = new Set();

        renderWishlistBadge();

        return;
    }


    try {

        const data = await apiFetch("/wishlist/ids");

        state.wishlist = new Set(data.product_ids || []);


    } catch (error) {

        console.error("Favoriler yüklenemedi:", error);

        state.wishlist = new Set();
    }


    renderWishlistBadge();
}


function isWishlisted(productId) {

    return state.wishlist.has(String(productId));
}


function renderWishlistBadge() {

    const count = state.wishlist.size;


    document
        .querySelectorAll(".wishlist-number")
        .forEach(element => {

            element.textContent = count;
        });


    wishlistButton
        ?.classList.toggle("has-items", count > 0);


    /*
       Sepet kaldirildigi icin "devam eden alisveris" hissini
       alt bar tasiyor; rozet her degistiginde o da guncel
       kalmali.
    */
    renderWishlistBar();
}


/*
   Favori ekleme/cikarma tek bir uctan geciyor: /api/interact.
   Boylece her kalp ayni anda hem wishlist'i hem olay kaydini
   hem de zevk profilini guncelliyor. Iki ayri yol olsa
   biri gunun birinde profil tazelemeyi atlardi.
*/

async function addToWishlist(
    productId,
    {
        source = "explore",
        position = null,
        matchScore = null,
        matchedStyle = null,

        /*
           Cagiran taraf urun objesini de verirse alt barin
           kucuk gorselleri icin yeni bir API turu atmadan
           yerel listeye ekliyoruz.
        */
        product = null,
    } = {}
) {

    const data = await sendInteraction({
        productId,
        type: "LIKE",
        source,
        position,
        matchScore,
        matchedStyle,
    });


    state.wishlist.add(String(productId));

    if (product) {
        upsertWishlistItem(productId, product);
    }

    renderWishlistBadge();

    return data;
}


/**
 * Yerel favori listesini günceller (alt bar için).
 *
 * En yeni favori başa geliyor: alt bar "son eklediğin"
 * ürünü gösteriyor ve hızlı al onu satın alıyor.
 */
function upsertWishlistItem(productId, product) {

    state.wishlistItems = [
        { product_id: String(productId), product },
        ...state.wishlistItems.filter(
            item => item.product_id !== String(productId)
        ),
    ];
}


async function removeFromWishlist(
    productId,
    {
        source = "wishlist",
        matchScore = null,
        matchedStyle = null,
    } = {}
) {

    const data = await sendInteraction({
        productId,
        type: "UNLIKE",
        source,
        matchScore,
        matchedStyle,
    });


    state.wishlist.delete(String(productId));

    state.wishlistItems = state.wishlistItems.filter(
        item => item.product_id !== String(productId)
    );

    renderWishlistBadge();

    return data;
}


/* ---------------------------------------------------------
   FAVORİLER ÇEKMECESİ
--------------------------------------------------------- */

function setupWishlistPanel() {

    wishlistButton?.addEventListener("click", () => {

        if (!isUserLoggedIn()) {

            openAuth(
                "Favorilerini görmek için giriş yap."
            );

            return;
        }

        openWishlistPanel();
    });


    closeWishlistButton
        ?.addEventListener("click", closeWishlistPanel);


    wishlistOverlay?.addEventListener("click", event => {

        if (event.target === wishlistOverlay) {
            closeWishlistPanel();
        }
    });


    $("exhausted-wishlist-btn")
        ?.addEventListener("click", () => {

            if (!isUserLoggedIn()) {
                openAuth("Favorilerini görmek için giriş yap.");
                return;
            }

            openWishlistPanel();
        });


    /* Satır içi eylemler — olay delegasyonu */

    wishlistItems?.addEventListener("click", async event => {

        const button =
            event.target.closest("[data-wishlist-action]");

        if (!button) return;


        const action = button.dataset.wishlistAction;
        const productId = button.dataset.productId;


        if (action === "remove") {

            button.disabled = true;

            try {

                const response = await removeFromWishlist(
                    productId,
                    { source: "wishlist" }
                );

                syncWishlistButtons(productId, false);

                renderAiStatus();

                await renderWishlistPanel();

                if (response?.toast) {
                    showToast(response.toast);
                }


            } catch (error) {

                console.error("Favoriden çıkarılamadı:", error);

                button.disabled = false;

                showToast({
                    title: "Çıkarılamadı",
                    message: "Bağlantını kontrol edip tekrar dene.",
                    tone: "error",
                });
            }

            return;
        }


        if (action === "quick-buy") {

            const entry = state.wishlistItems.find(
                item => item.product_id === productId
            );

            if (entry?.product) {

                openQuickCheckout(
                    { product: entry.product },
                    { source: "wishlist" }
                );
            }
        }
    });
}


async function openWishlistPanel() {

    wishlistOverlay?.classList.add("open");

    await renderWishlistPanel();
}


function closeWishlistPanel() {

    wishlistOverlay?.classList.remove("open");
}


async function renderWishlistPanel() {

    if (!wishlistItems) return;


    if (!isUserLoggedIn()) {

        wishlistItems.innerHTML = `
            <div class="wishlist-empty">
                <i class="fa-regular fa-heart"></i>
                <p>Giriş yapmadın</p>
                <span>
                    Favorilerin hesabına kaydedilir.
                </span>
            </div>
        `;

        return;
    }


    /*
       Yukleme gostergesini yalnizca liste bosken gosteriyoruz.
       Bir urun cikarildiktan sonra listeyi tazelerken de bu
       fonksiyon calisiyor; her seferinde loader basmak listeyi
       goz kirpar gibi bosaltiyordu.
    */

    const hasRows =
        wishlistItems.querySelector(".wishlist-row") !== null;

    if (!hasRows) {

        wishlistItems.innerHTML = `
            <div class="loader-container">
                <div class="loader"></div>
            </div>
        `;
    }


    try {

        const items = await apiFetch("/wishlist");

        state.wishlistItems = Array.isArray(items) ? items : [];


        /* Sunucu kimlikleri: kalpler her zaman senkron kalsin */

        state.wishlist = new Set(
            state.wishlistItems.map(item => item.product_id)
        );

        renderWishlistBadge();


    } catch (error) {

        console.error("Favoriler alınamadı:", error);

        wishlistItems.innerHTML = `
            <div class="wishlist-empty">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p>Favoriler alınamadı</p>
                <span>Backend bağlantısını kontrol et.</span>
            </div>
        `;

        return;
    }


    if (!state.wishlistItems.length) {

        wishlistItems.innerHTML = `
            <div class="wishlist-empty">
                <i class="fa-regular fa-heart"></i>
                <p>Favorin yok</p>
                <span>
                    Keşfet bölümünde beğendiklerini
                    kalple işaretle.
                </span>
            </div>
        `;

        setWishlistNote("");

        return;
    }


    wishlistItems.innerHTML =
        state.wishlistItems
            .map(item => {

                const product = item.product || {};
                const id = escapeHTML(item.product_id);


                return `
                <div class="wishlist-row">

                    <img
                        src="${escapeHTML(safeImage(product.image_url))}"
                        alt="${escapeHTML(productTitle(product))}"
                        loading="lazy"
                        data-wishlist-open="${id}"
                    >

                    <div class="wishlist-row-body">

                        <strong>
                            ${escapeHTML(productTitle(product))}
                        </strong>

                        <div class="wishlist-row-price">
                            ${formatPrice(product.price)}
                        </div>

                        <div class="wishlist-row-actions">

                            <button
                                type="button"
                                class="wishlist-add-cart"
                                data-wishlist-action="quick-buy"
                                data-product-id="${id}"
                                ${hasPrice(product) ? "" : "disabled"}
                            >
                                HIZLI AL
                            </button>

                            <button
                                type="button"
                                class="wishlist-remove"
                                data-wishlist-action="remove"
                                data-product-id="${id}"
                            >
                                ÇIKAR
                            </button>

                        </div>

                    </div>

                </div>
            `;
            })
            .join("");


    setWishlistNote(
        `${state.wishlistItems.length} ürün favorilerinde.`
    );

    renderWishlistBar();

    hydrateIcons(wishlistItems);
}


function setWishlistNote(text) {

    const note = $("wishlist-footer-note");

    if (note) {
        note.textContent = text;
    }
}


/* =========================================================
   SEPET
   ---------------------------------------------------------
   Favoriler'den farki: miktar tasir ve /cart uclarindan
   besleniyor. Favoriler/Hizli Al'in yerini almaz, yaninda
   calisir — kullanici tek urunu hemen almak icin Hizli Al'i,
   birden cok urunu biriktirip tek seferde odemek icin
   Sepet'i kullanir.
========================================================= */

function isInCart(productId) {

    return state.cart.some(
        item => item.product_id === String(productId)
    );
}


async function loadCart() {

    if (!isUserLoggedIn()) {

        state.cart = [];

        renderCartBadge();

        return;
    }


    try {

        const data = await apiFetch("/cart");

        state.cart = Array.isArray(data.items) ? data.items : [];


    } catch (error) {

        console.error("Sepet yüklenemedi:", error);

        state.cart = [];
    }


    renderCartBadge();
}


function renderCartBadge() {

    const totalQuantity = state.cart.reduce(
        (sum, item) => sum + Number(item.quantity || 0),
        0
    );


    document
        .querySelectorAll(".cart-number")
        .forEach(element => {

            element.textContent = totalQuantity;

            element.classList.toggle(
                "hidden",
                totalQuantity === 0
            );
        });


    cartButton
        ?.classList.toggle("has-items", totalQuantity > 0);
}


/**
 * Sepete ekler. Zaten sepetteyse backend miktari artirir
 * (bkz. crud.add_to_cart) — burada yeniden GET atmak yerine
 * cevaptaki guncel listeyi dogrudan kullaniyoruz.
 */
async function addToCart(
    productId,
    { quantity = 1 } = {}
) {

    const data = await apiFetch(
        `/cart/${encodeURIComponent(productId)}`,
        {
            method: "POST",
            body: JSON.stringify({ quantity }),
        }
    );

    state.cart = Array.isArray(data.items) ? data.items : [];

    renderCartBadge();

    return data;
}


/**
 * Miktari MUTLAK bir degere ayarlar. 0'a dusurmek urunu
 * sepetten cikarir (bkz. crud.set_cart_quantity).
 */
async function updateCartItemQuantity(productId, quantity) {

    const data = await apiFetch(
        `/cart/${encodeURIComponent(productId)}`,
        {
            method: "PATCH",
            body: JSON.stringify({ quantity }),
        }
    );

    state.cart = Array.isArray(data.items) ? data.items : [];

    renderCartBadge();

    return data;
}


async function removeCartItem(productId) {

    const data = await apiFetch(
        `/cart/${encodeURIComponent(productId)}`,
        { method: "DELETE" }
    );

    state.cart = Array.isArray(data.items) ? data.items : [];

    renderCartBadge();

    return data;
}


/* ---------------------------------------------------------
   SEPET ÇEKMECESİ
--------------------------------------------------------- */

function setupCartPanel() {

    cartButton?.addEventListener("click", () => {

        if (!isUserLoggedIn()) {

            openAuth("Sepetini görmek için giriş yap.");

            return;
        }

        openCartPanel();
    });


    closeCartButton
        ?.addEventListener("click", closeCartPanel);


    cartOverlay?.addEventListener("click", event => {

        if (event.target === cartOverlay) {
            closeCartPanel();
        }
    });


    $("cart-checkout-btn")?.addEventListener(
        "click",
        openCartCheckout
    );


    /* Satır içi eylemler — olay delegasyonu */

    cartItemsHolder?.addEventListener("click", async event => {

        const button =
            event.target.closest("[data-cart-action]");

        if (!button || button.disabled) return;


        const action = button.dataset.cartAction;
        const productId = button.dataset.productId;

        const entry = state.cart.find(
            item => item.product_id === productId
        );

        if (!entry) return;


        if (action === "increase" || action === "decrease") {

            const nextQuantity =
                action === "increase"
                    ? entry.quantity + 1
                    : entry.quantity - 1;

            button.disabled = true;

            try {

                await updateCartItemQuantity(
                    productId,
                    nextQuantity
                );

                await renderCartPanel();


            } catch (error) {

                console.error("Miktar güncellenemedi:", error);

                showToast({
                    title: "Güncellenemedi",
                    message: error.message || "Tekrar dener misin?",
                    tone: "error",
                });

                button.disabled = false;
            }

            return;
        }


        if (action === "remove") {

            button.disabled = true;

            try {

                await removeCartItem(productId);

                await renderCartPanel();


            } catch (error) {

                console.error("Sepetten çıkarılamadı:", error);

                showToast({
                    title: "Çıkarılamadı",
                    message: error.message || "Tekrar dener misin?",
                    tone: "error",
                });

                button.disabled = false;
            }
        }
    });
}


async function openCartPanel() {

    cartOverlay?.classList.add("open");

    await renderCartPanel();
}


function closeCartPanel() {

    cartOverlay?.classList.remove("open");
}


async function renderCartPanel() {

    if (!cartItemsHolder) return;


    const hasRows =
        cartItemsHolder.querySelector(".cart-row") !== null;

    if (!hasRows) {

        cartItemsHolder.innerHTML = `
            <div class="loader-container">
                <div class="loader"></div>
            </div>
        `;
    }


    try {

        await loadCart();


    } catch (error) {

        console.error("Sepet alınamadı:", error);

        cartItemsHolder.innerHTML = `
            <div class="wishlist-empty">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p>Sepet alınamadı</p>
                <span>Backend bağlantısını kontrol et.</span>
            </div>
        `;

        $("cart-panel-footer")?.classList.add("hidden");

        return;
    }


    if (!state.cart.length) {

        cartItemsHolder.innerHTML = `
            <div class="wishlist-empty">
                <i class="fa-solid fa-bag-shopping"></i>
                <p>Sepetin boş</p>
                <span>
                    Ürünleri sepete eklemek için ürün
                    kartındaki çanta simgesine dokun.
                </span>
            </div>
        `;

        $("cart-panel-footer")?.classList.add("hidden");

        return;
    }


    cartItemsHolder.innerHTML =
        state.cart
            .map(item => {

                const product = item.product || {};
                const id = escapeHTML(item.product_id);


                return `
                <div class="wishlist-row cart-row" data-product-id="${id}">

                    <img
                        src="${escapeHTML(safeImage(product.image_url))}"
                        alt="${escapeHTML(productTitle(product))}"
                        loading="lazy"
                        data-cart-open="${id}"
                    >

                    <div class="wishlist-row-body">

                        <strong>
                            ${escapeHTML(productTitle(product))}
                        </strong>

                        <div class="wishlist-row-price">
                            ${formatPrice(product.price)}
                        </div>

                        <div class="cart-qty-stepper">

                            <button
                                type="button"
                                class="cart-qty-btn"
                                data-cart-action="decrease"
                                data-product-id="${id}"
                                aria-label="Azalt"
                            >−</button>

                            <span class="cart-qty-value">
                                ${Number(item.quantity)}
                            </span>

                            <button
                                type="button"
                                class="cart-qty-btn"
                                data-cart-action="increase"
                                data-product-id="${id}"
                                aria-label="Artır"
                            >+</button>

                        </div>

                        <div class="wishlist-row-actions">

                            <button
                                type="button"
                                class="wishlist-remove"
                                data-cart-action="remove"
                                data-product-id="${id}"
                            >
                                ÇIKAR
                            </button>

                        </div>

                    </div>

                </div>
            `;
            })
            .join("");


    const subtotal = state.cart.reduce(
        (sum, item) =>
            sum +
            Number(item.product?.price || 0) *
            Number(item.quantity || 0),
        0
    );

    const footer = $("cart-panel-footer");

    footer?.classList.remove("hidden");

    const subtotalValue = $("cart-panel-subtotal-value");

    if (subtotalValue) {
        subtotalValue.textContent = formatPrice(subtotal);
    }


    /* Resme tıklayınca ürün detayı açılsın */

    cartItemsHolder
        .querySelectorAll("[data-cart-open]")
        .forEach(img => {

            img.addEventListener("click", () => {

                const entry = state.cart.find(
                    item =>
                        item.product_id ===
                        img.dataset.cartOpen
                );

                if (entry?.product) {
                    openProduct(entry.product_id, entry.product);
                }
            });
        });
}


/* =========================================================
   GARDIROP  (kaydedilmis kombinler)
   ---------------------------------------------------------
   Sepet/favoriler tekil urun listeleridir; gardirop
   KOMBINLERI tutar. Bir kombin, birlikte giyilen parcalarin
   kompozisyonudur ve icindeki tek bir parca (orn. sadece
   ayakkabi) baskasiyla degistirilebilir — ozelligin kalbi bu.

   Panel iki gorunumlu:
     LISTE     kaydedilmis kombinler
     DEGISTIR  bir parcanin AI ile bulunmus alternatifleri

   Sepet endpoint'leriyle ayni sozlesme: her mutasyon GUNCEL
   veriyi doner, panel ikinci bir GET atmaz.
========================================================= */

/* Yuva kodlarinin ekranda gorunen hali. Sunucu "ust"
   yaziyor, kullanici "ÜST" goruyor. */
const WARDROBE_SLOT_LABELS = {
    ust: "Üst",
    alt: "Alt",
    dis_giyim: "Dış Giyim",
    ayakkabi: "Ayakkabı",
    aksesuar: "Aksesuar",
    diger: "Diğer",
};

/* Hangi kombinin hangi parcasi degistiriliyor.
   openWardrobeSwap doldurur, geri donunce temizlenir. */
const wardrobeSwap = {
    lookId: null,
    productId: null,
};


function slotLabel(slot) {

    if (!slot) return "";

    return WARDROBE_SLOT_LABELS[slot] || "";
}


async function loadWardrobe() {

    if (!isUserLoggedIn()) {

        state.wardrobe = [];

        renderWardrobeBadge();

        return;
    }


    try {

        const data = await apiFetch("/wardrobe");

        state.wardrobe = Array.isArray(data.looks) ? data.looks : [];


    } catch (error) {

        console.error("Gardırop yüklenemedi:", error);

        state.wardrobe = [];
    }


    renderWardrobeBadge();
}


function renderWardrobeBadge() {

    /* Rozette kombin SAYISI yaziyor, parca sayisi degil:
       kullanici "3 kombinim var" diye dusunuyor. */
    const count = state.wardrobe.length;

    document
        .querySelectorAll(".wardrobe-number")
        .forEach(element => {

            element.textContent = count;

            element.classList.toggle("hidden", count === 0);
        });


    wardrobeButton
        ?.classList.toggle("has-items", count > 0);
}


/**
 * Kombin kaydeder.
 *
 * items: [{product_id, slot?}] — en az iki parca.
 * Yuvayi sunucu urun kategorisinden tahmin ediyor, istemci
 * gondermek zorunda degil.
 */
async function saveLook(title, items, { source = null, note = null } = {}) {

    const data = await apiFetch("/wardrobe", {
        method: "POST",
        body: JSON.stringify({
            title,
            items,
            source,
            note,
        }),
    });

    /* Liste ucu tek kombin donuyor; onu listenin basina
       koyuyoruz (sunucu da yeniden eskiye siraliyor). */
    state.wardrobe = [data, ...state.wardrobe];

    renderWardrobeBadge();

    return data;
}


async function renameLook(lookId, title) {

    const data = await apiFetch(`/wardrobe/${encodeURIComponent(lookId)}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
    });

    state.wardrobe = state.wardrobe.map(
        look => (look.id === lookId ? data : look)
    );

    return data;
}


async function deleteLook(lookId) {

    const data = await apiFetch(`/wardrobe/${encodeURIComponent(lookId)}`, {
        method: "DELETE",
    });

    state.wardrobe = Array.isArray(data.looks) ? data.looks : [];

    renderWardrobeBadge();

    return data;
}


async function replaceLookItem(lookId, oldProductId, newProductId) {

    const data = await apiFetch(
        `/wardrobe/${encodeURIComponent(lookId)}` +
        `/items/${encodeURIComponent(oldProductId)}`,
        {
            method: "PUT",
            body: JSON.stringify({ new_product_id: newProductId }),
        }
    );

    state.wardrobe = state.wardrobe.map(
        look => (look.id === lookId ? data : look)
    );

    return data;
}


async function removeLookItem(lookId, productId) {

    const data = await apiFetch(
        `/wardrobe/${encodeURIComponent(lookId)}` +
        `/items/${encodeURIComponent(productId)}`,
        {
            method: "DELETE",
        }
    );

    state.wardrobe = state.wardrobe.map(
        look => (look.id === lookId ? data : look)
    );

    return data;
}


function setupWardrobePanel() {

    wardrobeButton?.addEventListener("click", () => {

        if (!isUserLoggedIn()) {
            openAuth("Gardırobunu görmek için giriş yap.");
            return;
        }

        openWardrobePanel();
    });


    closeWardrobeButton
        ?.addEventListener("click", closeWardrobePanel);


    wardrobeOverlay?.addEventListener("click", event => {

        if (event.target === wardrobeOverlay) {
            closeWardrobePanel();
        }
    });


    $("wardrobe-swap-back")
        ?.addEventListener("click", closeWardrobeSwap);


    /* Olay delegasyonu: kombin kartlari her render'da
       yeniden ciziliyor (sepet paneliyle ayni desen). */
    wardrobeListHolder
        ?.addEventListener("click", handleWardrobeListClick);

    $("wardrobe-swap-items")
        ?.addEventListener("click", handleWardrobeSwapClick);
}


async function openWardrobePanel() {

    wardrobeOverlay?.classList.add("open");

    closeWardrobeSwap();

    await renderWardrobePanel();
}


function closeWardrobePanel() {

    wardrobeOverlay?.classList.remove("open");
}


async function renderWardrobePanel() {

    if (!wardrobeListHolder) return;


    /* Liste zaten doluysa loader basmiyoruz: her acilista
       ekranin bosalip dolmasi titreme gibi gorunuyor. */
    if (!state.wardrobe.length) {

        wardrobeListHolder.innerHTML = `
            <div class="loader-container">
                <div class="loader"></div>
            </div>
        `;
    }


    let failed = false;

    try {
        await loadWardrobe();

    } catch (error) {
        console.error("Gardırop alınamadı:", error);
        failed = true;
    }


    if (failed) {

        wardrobeListHolder.innerHTML = `
            <div class="wishlist-empty">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p>Gardırop alınamadı</p>
                <span>Bağlantını kontrol edip tekrar dener misin?</span>
            </div>
        `;

        return;
    }


    if (!state.wardrobe.length) {

        wardrobeListHolder.innerHTML = `
            <div class="wishlist-empty">
                <i class="fa-solid fa-shirt"></i>
                <p>Gardırobun boş</p>
                <span>
                    AI Asistan sana kombin önerdiğinde
                    beğendiğin parçaları seçip
                    "Kombin olarak kaydet"e dokun.
                </span>
            </div>
        `;

        return;
    }


    wardrobeListHolder.innerHTML =
        state.wardrobe.map(renderWardrobeLook).join("");
}


function renderWardrobeLook(look) {

    const lookId = escapeHTML(String(look.id));

    const pieces = Array.isArray(look.items) ? look.items : [];

    const sourceBadge = look.source === "chat"
        ? '<span class="wardrobe-look-source">AI ÖNERİSİ</span>'
        : "";

    return `
        <div class="wardrobe-look" data-look-id="${lookId}">

            <div class="wardrobe-look-head">

                <div class="wardrobe-look-title">
                    <strong>${escapeHTML(look.title || "Kombin")}</strong>

                    <div class="wardrobe-look-meta">
                        <span>${pieces.length} parça</span>
                        ${sourceBadge}
                    </div>
                </div>

                <div class="wardrobe-look-tools">

                    <button
                        type="button"
                        data-wardrobe-action="rename"
                        data-look-id="${lookId}"
                        aria-label="Kombini yeniden adlandır"
                        title="Yeniden adlandır"
                    >
                        <i class="fa-solid fa-pen"></i>
                    </button>

                    <button
                        type="button"
                        class="danger"
                        data-wardrobe-action="delete-look"
                        data-look-id="${lookId}"
                        aria-label="Kombini sil"
                        title="Kombini sil"
                    >
                        <i class="fa-solid fa-trash"></i>
                    </button>

                </div>

            </div>

            <div class="wardrobe-pieces">
                ${pieces.map(piece => renderWardrobePiece(piece, look.id)).join("")}
            </div>

            <div class="wardrobe-look-foot">

                <span class="wardrobe-look-total">
                    Toplam
                    <strong>${escapeHTML(formatPrice(look.total_price))}</strong>
                </span>

                <button
                    type="button"
                    class="wardrobe-look-buy"
                    data-wardrobe-action="add-all"
                    data-look-id="${lookId}"
                >
                    TÜMÜNÜ SEPETE EKLE
                </button>

            </div>

        </div>
    `;
}


function renderWardrobePiece(piece, lookId) {

    const product = piece.product || {};

    const productId = escapeHTML(String(piece.product_id || ""));

    const label = slotLabel(piece.slot);

    return `
        <div class="wardrobe-piece" data-product-id="${productId}">

            <img
                class="wardrobe-piece-image"
                src="${escapeHTML(safeImage(product.image_url))}"
                alt=""
                loading="lazy"
                data-wardrobe-open="${productId}"
            >

            <div class="wardrobe-piece-body">

                ${
                    label
                        ? `<span class="wardrobe-piece-slot">${escapeHTML(label)}</span>`
                        : ""
                }

                <p class="wardrobe-piece-title">
                    ${escapeHTML(productTitle(product))}
                </p>

                <span class="wardrobe-piece-price">
                    ${escapeHTML(formatPrice(product.price))}
                </span>

            </div>

            <div class="wardrobe-piece-actions">

                <button
                    type="button"
                    class="swap"
                    data-wardrobe-action="swap"
                    data-look-id="${escapeHTML(String(lookId))}"
                    data-product-id="${productId}"
                    aria-label="Bu parçayı değiştir"
                    title="Bu parçayı değiştir"
                >
                    <i class="fa-solid fa-right-left"></i>
                </button>

                <button
                    type="button"
                    class="danger"
                    data-wardrobe-action="remove-piece"
                    data-look-id="${escapeHTML(String(lookId))}"
                    data-product-id="${productId}"
                    aria-label="Bu parçayı kombinden çıkar"
                    title="Kombinden çıkar"
                >
                    <i class="fa-solid fa-xmark"></i>
                </button>

            </div>

        </div>
    `;
}


async function handleWardrobeListClick(event) {

    /* Gorsel: urun detayini ac (buton degil, <img>) */
    const image = event.target.closest("[data-wardrobe-open]");

    if (image) {

        const productId = image.dataset.wardrobeOpen;

        const piece = findWardrobePiece(productId);

        openProduct(productId, piece?.product);

        return;
    }


    const button = event.target.closest("[data-wardrobe-action]");

    if (!button || button.disabled) return;

    const action = button.dataset.wardrobeAction;
    const lookId = button.dataset.lookId;
    const productId = button.dataset.productId;


    if (action === "swap") {
        await openWardrobeSwap(lookId, productId, button);
        return;
    }


    if (action === "rename") {
        await handleLookRename(lookId);
        return;
    }


    button.disabled = true;

    try {

        if (action === "delete-look") {

            await deleteLook(lookId);

            await renderWardrobePanel();

            showToast({
                title: "Kombin silindi",
                message: "Gardırobundan çıkarıldı.",
                tone: "neutral",
            });

            return;
        }


        if (action === "remove-piece") {

            await removeLookItem(lookId, productId);

            await renderWardrobePanel();

            return;
        }


        if (action === "add-all") {
            await addLookToCart(lookId);
            return;
        }


    } catch (error) {

        console.error("Gardırop işlemi başarısız:", error);

        showToast({
            title: "İşlem tamamlanamadı",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });

    } finally {
        button.disabled = false;
    }
}


/** Gardiroptaki tum kombinlerde parcayi arar. */
function findWardrobePiece(productId) {

    const target = String(productId);

    for (const look of state.wardrobe) {

        const piece = (look.items || []).find(
            item => String(item.product_id) === target
        );

        if (piece) return piece;
    }

    return null;
}


async function handleLookRename(lookId) {

    const look = state.wardrobe.find(entry => entry.id === lookId);

    if (!look) return;

    const next = window.prompt("Kombinin yeni adı:", look.title || "");

    if (next === null) return;

    const title = next.trim();

    if (!title || title === look.title) return;


    try {

        await renameLook(lookId, title);

        await renderWardrobePanel();


    } catch (error) {

        console.error("Kombin adlandırılamadı:", error);

        showToast({
            title: "Ad değiştirilemedi",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });
    }
}


/**
 * Kombindeki tum parcalari sepete ekler.
 *
 * Zaten sepette olanlar atlanmiyor: /cart/{id} POST'u
 * tekrar eklemede miktari artiriyor, bu da beklenen
 * davranis (bkz. crud.add_to_cart).
 */
async function addLookToCart(lookId) {

    const look = state.wardrobe.find(entry => entry.id === lookId);

    if (!look) return;

    const pieces = (look.items || []).filter(
        piece => hasPrice(piece.product)
    );

    if (!pieces.length) {

        showToast({
            title: "Sepete eklenemedi",
            message: "Bu kombindeki ürünlerin fiyat bilgisi yok.",
            tone: "error",
        });

        return;
    }


    let added = 0;

    for (const piece of pieces) {

        try {
            await addToCart(piece.product_id, 1);
            added += 1;

        } catch (error) {
            console.error("Parça sepete eklenemedi:", error);
        }
    }


    const skipped = (look.items || []).length - added;

    showToast({
        title: added ? "Sepete eklendi" : "Sepete eklenemedi",
        message: added
            ? `${added} parça sepetine eklendi.` +
              (skipped ? ` ${skipped} parça atlandı.` : "")
            : "Hiçbir parça eklenemedi.",
        tone: added ? "success" : "error",
    });
}


/* --- PARCA DEGISTIRME --- */

/**
 * "Bu parcayi degistir" gorunumunu acar.
 *
 * Alternatifler SUNUCUDAN geliyor ve statik bir filtre
 * degil: degistirilecek parcanin kategorisi + kombinin
 * diger parcalarinin renkleri bir sorguya cevrilip
 * aramanin normal zincirinden geciyor (bkz.
 * suggest_look_replacement).
 */
async function openWardrobeSwap(lookId, productId, button) {

    const swapView = $("wardrobe-swap");
    const itemsHolder = $("wardrobe-swap-items");
    const reasonHolder = $("wardrobe-swap-reason");

    if (!swapView || !itemsHolder) return;


    wardrobeSwap.lookId = lookId;
    wardrobeSwap.productId = productId;

    wardrobeListHolder?.classList.add("hidden");
    swapView.classList.remove("hidden");

    const titleHolder = $("wardrobe-title");

    if (titleHolder) {
        titleHolder.textContent = "Parçayı Değiştir";
    }

    if (reasonHolder) {
        reasonHolder.textContent = "Alternatifler aranıyor...";
    }

    itemsHolder.innerHTML = `
        <div class="loader-container">
            <div class="loader"></div>
        </div>
    `;


    if (button) button.disabled = true;

    try {

        const data = await apiFetch(
            `/api/wardrobe/suggest/${encodeURIComponent(lookId)}` +
            `/${encodeURIComponent(productId)}`
        );

        const items = Array.isArray(data.items) ? data.items : [];

        if (reasonHolder) {
            reasonHolder.textContent = data.reason
                ? `Neden bunlar: ${data.reason}`
                : "";
        }

        if (!items.length) {

            itemsHolder.innerHTML = `
                <div class="wishlist-empty">
                    <i class="fa-solid fa-magnifying-glass"></i>
                    <p>Alternatif bulunamadı</p>
                    <span>Bu parçaya uygun başka ürün çıkmadı.</span>
                </div>
            `;

            return;
        }

        itemsHolder.innerHTML =
            items.map(renderWardrobeSwapOption).join("");


    } catch (error) {

        console.error("Alternatifler alınamadı:", error);

        if (reasonHolder) {
            reasonHolder.textContent = "";
        }

        itemsHolder.innerHTML = `
            <div class="wishlist-empty">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p>Alternatifler alınamadı</p>
                <span>${escapeHTML(error.message || "Tekrar dener misin?")}</span>
            </div>
        `;

    } finally {
        if (button) button.disabled = false;
    }
}


function closeWardrobeSwap() {

    wardrobeSwap.lookId = null;
    wardrobeSwap.productId = null;

    $("wardrobe-swap")?.classList.add("hidden");
    wardrobeListHolder?.classList.remove("hidden");

    const titleHolder = $("wardrobe-title");

    if (titleHolder) {
        titleHolder.textContent = "Gardırop";
    }
}


function renderWardrobeSwapOption(product) {

    const productId = escapeHTML(String(product.product_id || ""));

    return `
        <div class="wardrobe-piece" data-product-id="${productId}">

            <img
                class="wardrobe-piece-image"
                src="${escapeHTML(safeImage(product.image_url))}"
                alt=""
                loading="lazy"
            >

            <div class="wardrobe-piece-body">

                ${
                    product.brand
                        ? `<span class="wardrobe-piece-slot">${escapeHTML(product.brand)}</span>`
                        : ""
                }

                <p class="wardrobe-piece-title">
                    ${escapeHTML(productTitle(product))}
                </p>

                <span class="wardrobe-piece-price">
                    ${escapeHTML(formatPrice(product.price))}
                </span>

            </div>

            <button
                type="button"
                class="wardrobe-swap-pick"
                data-wardrobe-pick="${productId}"
            >
                SEÇ
            </button>

        </div>
    `;
}


async function handleWardrobeSwapClick(event) {

    const button = event.target.closest("[data-wardrobe-pick]");

    if (!button || button.disabled) return;

    const newProductId = button.dataset.wardrobePick;

    const { lookId, productId } = wardrobeSwap;

    if (!lookId || !productId) return;


    button.disabled = true;

    try {

        await replaceLookItem(lookId, productId, newProductId);

        closeWardrobeSwap();

        await renderWardrobePanel();

        showToast({
            title: "Parça değişti",
            message: "Kombin güncellendi.",
            tone: "success",
        });


    } catch (error) {

        console.error("Parça değiştirilemedi:", error);

        showToast({
            title: "Değiştirilemedi",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });

        button.disabled = false;
    }
}


/*
   Ayni urun hem Kesfet kartinda hem urun detayinda
   gorunuyor olabilir. Kalp durumunu her yerde eslestiriyoruz.
*/

function syncWishlistButtons(productId, liked) {

    document
        .querySelectorAll(
            `.explore-card[data-product-id="${cssEscape(productId)}"]`
        )
        .forEach(card => {

            card.classList.toggle("liked", liked);

            /*
               Iki kalp butonu var: resmin sag ustundeki sembol
               (.explore-quick-like) ve govdenin altindaki
               metinli buton (.explore-action-like). Ayni urun
               ikisinde de gorunebildigi icin querySelectorAll
               ile hepsini guncelliyoruz; ikon-only olanin
               metnini degistirmiyoruz.
            */

            card
                .querySelectorAll(".explore-action-like")
                .forEach(button => {

                    button.classList.toggle("active", liked);

                    button.innerHTML =
                        button.classList.contains("explore-quick-like")
                            ? icon("heart", { filled: liked })
                            : icon("heart", { filled: liked }) +
                                (liked ? " FAVORİDE" : " BEĞENDİM");

                    hydrateIcons(button);
                });
        });


    const modalButton = $("modal-wishlist-btn");

    if (
        modalButton &&
        modalButton.dataset.productId === String(productId)
    ) {
        setModalWishlistButton(modalButton, liked);
    }
}


function setModalWishlistButton(button, liked) {

    button.classList.toggle("active", liked);

    button.innerHTML =
        icon("heart", { filled: liked }) +
        (liked ? " FAVORİLERİMDE" : " FAVORİLERE EKLE");

    hydrateIcons(button);
}


/*
   CSS.escape her ortamda yok (jsdom dahil).
   Urun kimlikleri ASIN oldugu icin basit kacis yeterli.
*/

function cssEscape(value) {

    const raw = String(value ?? "");

    return window.CSS?.escape
        ? window.CSS.escape(raw)
        : raw.replace(/["\\\]]/g, "\\$&");
}


/* =========================================================
   GİRİŞ GEREKTİREN ETKİLEŞİMLER
========================================================= */

/*
   Etkilesim kaydi user_id gerektiriyor. Misafir kalp veya
   begenmedim'e bastiginda niyeti saklayip giris ekranini
   aciyoruz; girisin ardindan islem kaldigi yerden devam eder.
*/

function requestLoginForInteraction(pending, message) {

    state.pendingInteraction = pending;

    openAuth(message);
}


async function resumePendingInteraction() {

    const pending = state.pendingInteraction;

    if (!pending || !isUserLoggedIn()) {
        return;
    }

    state.pendingInteraction = null;


    if (pending.type === "LIKE") {

        await handleExploreLike(
            pending.productId,
            pending.position
        );

        return;
    }


    if (pending.type === "DISLIKE") {

        const card = findExploreCard(pending.productId);

        if (card) {
            await handleExploreDislike(card);
        }

        return;
    }


    if (pending.type === "MODAL_LIKE") {

        await handleModalWishlistToggle();

        return;
    }


    if (pending.type === "GRID_LIKE") {

        const button = productsGrid?.querySelector(
            `[data-grid-action="like"][data-product-id="${cssEscape(pending.productId)}"]`
        );

        const product = state.products.find(
            item => item.product_id === pending.productId
        );

        if (button && product) {
            await handleGridLike(product, button);
        }
    }
}


function findExploreCard(productId) {

    return exploreGrid?.querySelector(
        `.explore-card[data-product-id="${cssEscape(productId)}"]`
    );
}


/* =========================================================
   TOAST BİLDİRİMLERİ
========================================================= */

const TOAST_DURATION = 4200;

const TOAST_ICONS = {
    success: "fa-solid fa-heart",
    neutral: "fa-solid fa-check",
    info: "fa-solid fa-wand-magic-sparkles",
    error: "fa-solid fa-triangle-exclamation",
};


function showToast({
    title,
    message = "",
    tone = "info",

    /*
       Geri alinabilir bildirim.

       onUndo verilirse toast'ta bir "GERI AL" butonu ve
       kalan sureyi gosteren ince bir cizgi cikiyor.
       Kullanici basarsa toast kapanir ve onUndo cagrilir.
    */
    undoLabel = null,
    onUndo = null,
    duration = TOAST_DURATION,
}) {

    const stack = $("toast-stack");

    if (!stack || !title) return null;


    const toast = document.createElement("div");

    toast.className = `toast ${tone}`;

    toast.innerHTML = `
        <div class="toast-icon">
            <i class="${TOAST_ICONS[tone] || TOAST_ICONS.info}"></i>
        </div>

        <div class="toast-body">
            <strong>${escapeHTML(title)}</strong>
            ${
                message
                    ? `<span>${escapeHTML(message)}</span>`
                    : ""
            }
        </div>

        ${
            onUndo
                ? `
                    <button type="button" class="toast-undo">
                        ${icon("undo-2")}
                        ${escapeHTML(undoLabel || "GERİ AL")}
                    </button>
                `
                : ""
        }

        <button
            type="button"
            class="toast-close"
            aria-label="Bildirimi kapat"
        >
            <i class="fa-solid fa-xmark"></i>
        </button>

        ${
            onUndo
                ? `<span
                       class="toast-timer"
                       style="animation-duration:${duration}ms"
                   ></span>`
                : ""
        }
    `;


    let closed = false;

    const dismiss = () => {

        if (closed) return;

        closed = true;

        toast.classList.add("leaving");

        setTimeout(() => toast.remove(), 320);
    };


    toast
        .querySelector(".toast-close")
        ?.addEventListener("click", dismiss);


    toast
        .querySelector(".toast-undo")
        ?.addEventListener("click", () => {

            dismiss();

            onUndo();
        });


    stack.appendChild(toast);

    hydrateIcons(toast);

    /* Ekrani doldurmasin: en fazla 3 bildirim dursun */
    while (stack.children.length > 3) {
        stack.firstElementChild?.remove();
    }

    setTimeout(dismiss, duration);

    return { dismiss };
}


/* =========================================================
   AI ANALİZ EKRANI
========================================================= */

const AI_ANALYZE_MIN_MS = 1100;
const AI_ANALYZE_MAX_MS = 5000;


function setAnalyzingText(text) {

    const node = $("ai-analyzing-text");

    if (node) {
        node.textContent = text;
    }
}


/*
   Adimlar sirayla isaretlenir. Amac sahte bir ilerleme
   cubugu degil; arka planda gercekten olan islerin
   (profil kaydi, katalog sorgusu, siralama) adlarini
   gostermek.
*/

function runAnalyzingSteps() {

    const steps = Array.from(
        $("ai-analyzing-steps")?.children || []
    );

    steps.forEach(step => step.classList.remove("done"));

    const timers = steps.map((step, index) =>
        setTimeout(
            () => step.classList.add("done"),
            180 + index * 300
        )
    );

    return () => timers.forEach(clearTimeout);
}


/**
 * İşi yaparken AI analiz ekranını gösterir.
 *
 * Ekran en az AI_ANALYZE_MIN_MS kalır (aksi halde 80 ms'de
 * kaybolur ve "bir şey oldu" hissi vermez), ama işi de
 * bekler — boş bir akış göstermekten iyidir.
 */
async function withAiAnalyzing(label, work) {

    const overlay = $("ai-analyzing");

    setAnalyzingText(label);

    const cancelSteps = runAnalyzingSteps();

    overlay?.classList.add("open");


    const minimum = new Promise(resolve =>
        setTimeout(resolve, AI_ANALYZE_MIN_MS)
    );

    const guard = new Promise(resolve =>
        setTimeout(resolve, AI_ANALYZE_MAX_MS)
    );


    let result;

    try {
        result = await Promise.race([
            Promise.all([work(), minimum]),
            guard,
        ]);

    } catch (error) {
        console.error("AI analiz sırasında hata:", error);

    } finally {
        cancelSteps();
        overlay?.classList.remove("open");
    }

    return Array.isArray(result) ? result[0] : undefined;
}


/* =========================================================
   ARKETİP (COLD START)
========================================================= */

const ARCHETYPE_STORAGE_KEY = "aura_styles";
const ARCHETYPE_SEEN_KEY = "aura_archetype_seen";

/* Eski surumde tek tarz saklaniyordu; goc icin okunuyor */
const LEGACY_ARCHETYPE_KEY = "aura_archetype";

const archetypeState = {
    options: [],

    /* Kayitli secim (1-3 tarz, sirali) */
    current: [],

    /* Modalda o an isaretli olanlar */
    draft: [],

    minChoices: 1,
    maxChoices: 3,

    loading: false,
};


function storedStyles() {

    try {
        const raw = localStorage.getItem(ARCHETYPE_STORAGE_KEY);

        if (raw) {
            const parsed = JSON.parse(raw);

            if (Array.isArray(parsed) && parsed.length) {
                return parsed.slice(0, 3);
            }
        }


        /*
           Goc: onceki surum tek tarzi duz metin olarak
           sakliyordu. Bir kez okuyup yeni bicime cevirip
           eskisini siliyoruz.
        */

        const legacy = localStorage.getItem(LEGACY_ARCHETYPE_KEY);

        if (legacy) {

            const migrated =
                legacy === "classic" ? "smart_casual" : legacy;

            storeStyles([migrated]);

            localStorage.removeItem(LEGACY_ARCHETYPE_KEY);

            return [migrated];
        }


        return [];

    } catch {
        return [];
    }
}


function storeStyles(styles) {

    try {
        localStorage.setItem(
            ARCHETYPE_STORAGE_KEY,
            JSON.stringify(styles.slice(0, 3))
        );

        localStorage.setItem(ARCHETYPE_SEEN_KEY, "1");

    } catch {
        /* localStorage kapali olabilir; kritik degil */
    }
}


function markArchetypeSeen() {

    try {
        localStorage.setItem(ARCHETYPE_SEEN_KEY, "1");
    } catch {
        /* yoksay */
    }
}


function archetypeSeen() {

    try {
        return localStorage.getItem(ARCHETYPE_SEEN_KEY) === "1";
    } catch {
        return false;
    }
}


function activeStyles() {

    if (archetypeState.current.length) {
        return archetypeState.current;
    }

    return storedStyles();
}


function hasActiveStyles() {

    return activeStyles().length > 0;
}


async function setupArchetype() {

    archetypeGrid = $("archetype-grid");

    $("archetype-skip")?.addEventListener("click", () => {

        markArchetypeSeen();

        closeArchetypeModal();

        showToast({
            title: "Tamam, sonra da seçebilirsin",
            message: "Keşfet başlığındaki bağlantıdan tarzını belirle.",
            tone: "info",
        });
    });


    archetypeOverlay?.addEventListener("click", event => {

        /*
           Ilk gosterimde dışa tıklayınca kapanmasın:
           kullanıcı kazara kapatıp AI deneyimini kaçırmasın.
           Sonradan "değiştir" ile açıldığında kapanabilir.
        */

        if (
            event.target === archetypeOverlay &&
            archetypeSeen()
        ) {
            closeArchetypeModal();
        }
    });


    $("ai-status-change")?.addEventListener(
        "click",
        () => openArchetypeModal()
    );


    $("archetype-confirm")?.addEventListener(
        "click",
        () => confirmArchetypeSelection()
    );


    await loadArchetypes();
}


async function loadArchetypes() {

    try {

        const data = await apiFetch("/api/archetypes");

        archetypeState.options = data.options || [];
        archetypeState.minChoices = data.min_choices ?? 1;
        archetypeState.maxChoices = data.max_choices ?? 3;

        /*
           Sunucudaki secim localStorage'i ezer: kullanici
           baska bir cihazda secmis olabilir.
        */

        if (Array.isArray(data.selected) && data.selected.length) {
            archetypeState.current = data.selected;
            storeStyles(data.selected);
        } else {
            archetypeState.current = storedStyles();
        }

        archetypeState.draft = [...archetypeState.current];


    } catch (error) {

        console.error("Stil kartları alınamadı:", error);
    }


    renderArchetypeCards();

    renderAiStatus();
}


function renderArchetypeCards() {

    if (!archetypeGrid) return;


    if (!archetypeState.options.length) {

        archetypeGrid.innerHTML = `
            <p class="explore-error">
                Stil seçenekleri yüklenemedi.
            </p>
        `;

        return;
    }


    const draft = archetypeState.draft;


    archetypeGrid.innerHTML =
        archetypeState.options
            .map(option => {

                const order = draft.indexOf(option.id);
                const chosen = order !== -1;

                return `
                <button
                    type="button"
                    class="archetype-card${chosen ? " chosen" : ""}"
                    data-archetype="${escapeHTML(option.id)}"
                    aria-pressed="${chosen}"
                >

                    <div class="archetype-card-image">
                        <img
                            src="${escapeHTML(option.image_url)}"
                            alt="${escapeHTML(option.label)}"
                            loading="lazy"
                        >

                        <span class="archetype-check">
                            ${chosen ? order + 1 : ""}
                        </span>
                    </div>

                    <div class="archetype-card-body">

                        <strong>
                            <span class="archetype-emoji">
                                ${escapeHTML(option.emoji || "")}
                            </span>
                            ${escapeHTML(option.short_label)}
                        </strong>

                        <span class="archetype-card-tagline">
                            ${escapeHTML(option.tagline)}
                        </span>

                        <p>${escapeHTML(option.description)}</p>

                        <div class="archetype-pool${
                            option.is_thin ? " thin" : ""
                        }">
                            <span>
                                ${Number(option.pool_count || 0)} PARÇA
                            </span>

                            ${
                                option.is_thin
                                    ? '<span>AZ SEÇENEK</span>'
                                    : ""
                            }
                        </div>

                    </div>

                </button>
            `;
            })
            .join("");


    archetypeGrid
        .querySelectorAll("[data-archetype]")
        .forEach(card => {

            card.addEventListener("click", () =>
                toggleArchetype(card.dataset.archetype)
            );
        });


    renderArchetypeFooter();
}


/**
 * Tarz secimini ac/kapat.
 *
 * En fazla 3 tarz. Sinir dolduysa yeni secim engellenir
 * (sessizce en eskiyi atmak yerine kullaniciya soyluyoruz:
 * kendi secimini kaybetmesi kotu bir surpriz olur).
 */
function toggleArchetype(archetype) {

    if (!archetype) return;


    const draft = archetypeState.draft;
    const index = draft.indexOf(archetype);


    if (index !== -1) {

        draft.splice(index, 1);

    } else {

        if (draft.length >= archetypeState.maxChoices) {

            showToast({
                title: `En fazla ${archetypeState.maxChoices} tarz`,
                message:
                    "Yeni bir tarz eklemek için önce birini kaldır.",
                tone: "info",
            });

            return;
        }

        draft.push(archetype);
    }


    renderArchetypeCards();
}


function renderArchetypeFooter() {

    const counter = $("archetype-counter");
    const confirm = $("archetype-confirm");
    const warning = $("archetype-warning");

    const draft = archetypeState.draft;


    archetypeGrid?.classList.toggle(
        "at-limit",
        draft.length >= archetypeState.maxChoices
    );


    if (counter) {

        counter.innerHTML =
            draft.length === 0
                ? "Henüz seçim yapmadın"
                : `<strong>${draft.length}</strong> / ${
                      archetypeState.maxChoices
                  } tarz seçildi`;
    }


    if (confirm) {
        confirm.disabled =
            draft.length < archetypeState.minChoices;
    }


    /*
       Ince havuz uyarisi.
       Katalog kapsami dengesiz; kullanici "Y2K" secip bos
       bir akisla karsilasirsa sistemin bozuk oldugunu
       dusunur. Secim aninda soylemek daha durust.
    */

    if (!warning) return;


    const chosen = archetypeState.options.filter(
        option => draft.includes(option.id)
    );

    const total = chosen.reduce(
        (sum, option) => sum + Number(option.pool_count || 0),
        0
    );

    const thinOnes = chosen.filter(option => option.is_thin);


    if (draft.length && total < 25) {

        warning.innerHTML = `
            <i class="fa-solid fa-circle-info"></i>
            <span>
                Bu seçimde katalogda
                <strong>${total} parça</strong> var.
                ${
                    thinOnes.length
                        ? `${thinOnes
                              .map(o => escapeHTML(o.short_label))
                              .join(", ")} için ürün az.`
                        : ""
                }
                İkinci bir tarz eklersen akışın zenginleşir.
            </span>
        `;

        warning.classList.remove("hidden");

    } else {

        warning.classList.add("hidden");
    }
}


function openArchetypeModal() {

    /* Modal her acildiginda kayitli secimden baslasin */
    archetypeState.draft = [...activeStyles()];

    renderArchetypeCards();

    archetypeOverlay?.classList.add("open");
}


function closeArchetypeModal() {

    archetypeOverlay?.classList.remove("open");
}


/**
 * Seçim onayı: kaydet, analiz ekranını göster, akışı yenile.
 */
async function confirmArchetypeSelection() {

    const styles = [...archetypeState.draft];

    if (!styles.length || archetypeState.loading) return;


    archetypeState.loading = true;

    archetypeState.current = styles;

    storeStyles(styles);

    closeArchetypeModal();


    const labels = styles.map(id => {

        const option = archetypeState.options.find(
            item => item.id === id
        );

        return option?.short_label || id;
    });


    let serverMessage = null;

    await withAiAnalyzing(
        labels.length === 1
            ? `${labels[0]} tarzın analiz ediliyor...`
            : `${labels.join(" + ")} analiz ediliyor...`,
        async () => {

            /*
               Giris yapmissa sunucuya yaziyoruz (INITIAL_STYLE
               olayi + tercih kaydi). Misafirde secim yalnizca
               localStorage'da durur; giris yapinca senkronlanir.
            */

            if (isUserLoggedIn()) {

                try {

                    serverMessage = await apiFetch(
                        "/api/initial-style",
                        {
                            method: "POST",
                            body: JSON.stringify({
                                selected_styles: styles,
                            }),
                        }
                    );

                } catch (error) {

                    console.error("Stil kaydedilemedi:", error);
                }
            }

            await refreshExplore({ silent: true });
        }
    );


    archetypeState.loading = false;

    renderAiStatus();


    const matched = serverMessage?.matched_products;

    showToast({
        title:
            labels.length === 1
                ? `${labels[0]} tarzı seçildi`
                : `${labels.length} tarz seçildi`,
        message: matched
            ? `${matched} parça senin tarzında. Akışın hazır.`
            : "Akışın seçimine göre yeniden düzenlendi.",
        tone: "success",
    });


    $("explore")?.scrollIntoView({ behavior: "smooth" });
}


/**
 * Misafirken seçilen tarzı, giriş sonrası sunucuya taşır.
 */
async function syncArchetypeAfterLogin() {

    if (!isUserLoggedIn()) return;


    try {

        const data = await apiFetch("/api/archetypes");

        if (Array.isArray(data.selected) && data.selected.length) {

            /* Sunucu biliyorsa onu kullan */
            archetypeState.current = data.selected;
            storeStyles(data.selected);

            return;
        }


        const local = storedStyles();

        if (!local.length) return;


        await apiFetch("/api/initial-style", {
            method: "POST",
            body: JSON.stringify({ selected_styles: local }),
        });

        archetypeState.current = local;


    } catch (error) {

        console.error("Tarz senkronize edilemedi:", error);
    }
}


function renderAiStatus() {

    const status = $("ai-status");
    const text = $("ai-status-text");

    const styles = activeStyles();


    if (!status || !text) return;


    if (!styles.length) {

        status.classList.add("hidden");

        return;
    }


    const chips = styles
        .map(id => {

            const option = archetypeState.options.find(
                item => item.id === id
            );

            const emoji = option?.emoji || "";
            const label = option?.short_label || id;

            return `
                <span class="ai-status-style">
                    ${escapeHTML(emoji)}
                    ${escapeHTML(label)}
                </span>
            `;
        })
        .join("");


    const liked = state.wishlist.size;


    text.innerHTML = `
        Akışın
        <span class="ai-status-styles">${chips}</span>
        ${
            liked > 0
                ? `ve <strong>${liked} beğenine</strong>`
                : ""
        }
        göre kuruldu.
    `;

    status.classList.remove("hidden");
}


/**
 * İlk ziyarette modalı açıp açmayacağımıza karar verir.
 */
function maybeOpenArchetypeModal() {

    if (hasActiveStyles() || archetypeSeen()) {
        return;
    }

    if (!archetypeOverlay) {
        return;
    }

    /* Sayfa boyansın, sonra aç */
    setTimeout(openArchetypeModal, 800);
}


/* =========================================================
   ÖZELLEŞTİR
   ---------------------------------------------------------
   Yas/cinsiyet/renk/tarz secimlerini /api/style-customize'a
   gonderir. Eslesme backend'de EMBEDDING benzerligiyle
   yapilir (bkz. style_customize.py) — burada renge/tarza
   gore statik bir if-else dallanma YOK, sadece secimleri
   toplayip API'ye ileten bir sihirbaz arayuzu var.
========================================================= */

const CUSTOMIZE_COLORS = [
    { id: "siyah", label: "Siyah", hex: "#111111" },
    { id: "beyaz", label: "Beyaz", hex: "#ffffff" },
    { id: "gri", label: "Gri", hex: "#9ca3af" },
    { id: "antrasit", label: "Antrasit", hex: "#3f3f46" },
    { id: "bej", label: "Bej", hex: "#d8c3a5" },
    { id: "krem", label: "Krem", hex: "#f0e6d2" },
    { id: "lacivert", label: "Lacivert", hex: "#1e2a4a" },
    { id: "mavi", label: "Mavi", hex: "#3b6fa0" },
    { id: "turkuaz", label: "Turkuaz", hex: "#2e8b8b" },
    { id: "kahverengi", label: "Kahve", hex: "#6b4226" },
    { id: "taba", label: "Taba", hex: "#a97c50" },
    { id: "bordo", label: "Bordo", hex: "#6b1f2a" },
    { id: "kırmızı", label: "Kırmızı", hex: "#b23a3a" },
    { id: "somon", label: "Somon", hex: "#e08e79" },
    { id: "pembe", label: "Pembe", hex: "#d98ca0" },
    { id: "gül kurusu", label: "Gül Kurusu", hex: "#b76e79" },
    { id: "mor", label: "Mor", hex: "#6b4b8a" },
    { id: "lila", label: "Lila", hex: "#b19cd9" },
    { id: "yeşil", label: "Yeşil", hex: "#4b6b4b" },
    { id: "zeytin yeşili", label: "Zeytin Yeşili", hex: "#6b6b3a" },
    { id: "sarı", label: "Sarı", hex: "#d9b93b" },
    { id: "hardal", label: "Hardal", hex: "#c9a227" },
    { id: "turuncu", label: "Turuncu", hex: "#c9702e" },
    { id: "petrol", label: "Petrol", hex: "#1f4e4e" },
];

/*
   Renk paleti gibi SABIT bir liste — /api/archetypes'e bagli
   degil. Her giris GERCEK bir kombin/outfit fotografi (duz
   yatirilmis flatlay ya da giyilmis look), sadece bir "stil
   adi" veya tek urun fotografi degil. Kullanici kombini
   GORUNUMUNE gore seçer (bkz. renderCustomizeComboGrid — kart
   uzerinde hicbir tarz ismi YAZMIYOR). Secilen kombinin
   "label"i /api/style-customize'e dogal dil ipucu olarak
   gidiyor, embedding tabanli eslestirmeyi yonlendiriyor.
*/
const CUSTOMIZE_COMBOS = [
    {
        id: "minimalist",
        label: "Minimalist & Sade",
        image_url:
            "https://images.unsplash.com/photo-1479064555552-3ef4979f8908" +
            "?auto=format&fit=crop&w=600&q=80",
    },
    {
        id: "vintage",
        label: "Vintage & Retro",
        image_url:
            "https://images.unsplash.com/photo-1717201395289-03e4700ca8b6" +
            "?auto=format&fit=crop&w=600&q=80",
    },
    {
        id: "streetwear",
        label: "Streetwear & Urban",
        image_url:
            "https://images.unsplash.com/photo-1616761512547-ea151d8a56d5" +
            "?auto=format&fit=crop&w=600&q=80",
    },
    {
        id: "office",
        label: "Smart Casual & Ofis",
        image_url:
            "https://images.unsplash.com/photo-1507707113652-f8a32c05046d" +
            "?auto=format&fit=crop&w=600&q=80",
    },
    {
        id: "old_money",
        label: "Old Money & Şık",
        image_url:
            "https://images.unsplash.com/photo-1593032470861-4509830938cb" +
            "?auto=format&fit=crop&w=600&q=80",
    },
    {
        id: "boho",
        label: "Bohem & Doğal",
        image_url:
            "https://images.unsplash.com/photo-1516763449302-78450e5a507d" +
            "?auto=format&fit=crop&w=600&q=80",
    },
    {
        id: "sporty",
        label: "Spor & Aktif",
        image_url:
            "https://images.unsplash.com/photo-1548606703-580672e56c26" +
            "?auto=format&fit=crop&w=600&q=80",
    },
    {
        id: "edgy",
        label: "Karanlık & İddialı",
        image_url:
            "https://images.unsplash.com/photo-1717766293805-df3a47dd819d" +
            "?auto=format&fit=crop&w=600&q=80",
    },
];

const CUSTOMIZE_MAX_COLORS = 6;
const CUSTOMIZE_MAX_COMBOS = 4;
const CUSTOMIZE_STEP_COUNT = 3;

const customizeState = {
    step: 1,
    age: null,
    gender: null,
    colors: [],

    /* Secili kombinlerin GORUNEN ETIKETLERI (id degil) —
       /api/style-customize'in "styles" alanina dogrudan
       gidiyor, prompt icinde metin olarak kullaniliyor. */
    combos: [],

    submitting: false,
};


function setupCustomize() {

    const fab = $("customize-fab");
    const overlay = $("customize-overlay");

    if (!fab || !overlay) return;


    fab.addEventListener("click", openCustomize);

    $("customize-close")
        ?.addEventListener("click", closeCustomize);

    overlay.addEventListener("click", event => {

        if (event.target === overlay) {
            closeCustomize();
        }
    });


    document
        .querySelectorAll(".customize-gender-options [data-gender]")
        .forEach(button => {

            button.addEventListener("click", () => {

                customizeState.gender =
                    customizeState.gender === button.dataset.gender
                        ? null
                        : button.dataset.gender;

                document
                    .querySelectorAll("[data-gender]")
                    .forEach(other => {

                        other.classList.toggle(
                            "active",
                            other.dataset.gender ===
                            customizeState.gender
                        );
                    });
            });
        });


    $("customize-age")?.addEventListener("input", event => {

        const value = Number(event.target.value);

        customizeState.age =
            Number.isFinite(value) && value > 0 ? value : null;
    });


    renderCustomizeColorGrid();
    renderCustomizeComboGrid();


    $("customize-back-btn")
        ?.addEventListener("click", () => {

            goToCustomizeStep(customizeState.step - 1);
        });


    $("customize-next-btn")
        ?.addEventListener("click", () => {

            if (customizeState.step < CUSTOMIZE_STEP_COUNT) {

                goToCustomizeStep(customizeState.step + 1);

            } else {

                submitCustomizeProfile();
            }
        });
}


function renderCustomizeColorGrid() {

    const grid = $("customize-color-grid");

    if (!grid) return;


    grid.innerHTML = CUSTOMIZE_COLORS
        .map(color => `
            <button
                type="button"
                class="customize-color-swatch"
                data-color-id="${escapeHTML(color.id)}"
            >
                <span
                    class="customize-color-circle"
                    style="background:${escapeHTML(color.hex)};"
                ></span>
                <span>${escapeHTML(color.label)}</span>
            </button>
        `)
        .join("");

    grid
        .querySelectorAll("[data-color-id]")
        .forEach(button => {

            button.addEventListener("click", () => {
                toggleCustomizeColor(button);
            });
        });
}


function toggleCustomizeColor(button) {

    const id = button.dataset.colorId;

    const isActive = customizeState.colors.includes(id);

    if (isActive) {

        customizeState.colors =
            customizeState.colors.filter(item => item !== id);

        button.classList.remove("active");

        return;
    }


    if (customizeState.colors.length >= CUSTOMIZE_MAX_COLORS) {

        showToast({
            title: "En fazla " + CUSTOMIZE_MAX_COLORS + " renk",
            message: "Önce bir rengin seçimini kaldır.",
            tone: "neutral",
        });

        return;
    }


    customizeState.colors.push(id);

    button.classList.add("active");
}


/**
 * Adim 3'un kombin kartlarini CUSTOMIZE_COMBOS'tan cizer.
 *
 * Her kart buyuk bir kombin fotografi + fotografin uzerine
 * bindirilmis (alt-gradient overlay) tarz adi. Kullanici hem
 * gorunume hem de isme bakarak seçebiliyor; secilen etiket
 * /api/style-customize'e "styles" olarak aynen gidiyor.
 */
function renderCustomizeComboGrid() {

    const grid = $("customize-combo-grid");

    if (!grid) return;

    grid.innerHTML = CUSTOMIZE_COMBOS
        .map(option => {

            const active = customizeState.combos.includes(option.label);

            return `
                <button
                    type="button"
                    class="customize-combo-card${active ? " active" : ""}"
                    data-combo-label="${escapeHTML(option.label)}"
                    aria-label="${escapeHTML(option.label)} kombinini seç"
                    aria-pressed="${active}"
                >
                    <div class="customize-combo-image">
                        <img
                            src="${escapeHTML(option.image_url)}"
                            alt=""
                            loading="lazy"
                        >
                        <span class="customize-combo-check">
                            <i class="fa-solid fa-check"></i>
                        </span>
                        <span class="customize-combo-label">
                            ${escapeHTML(option.label)}
                        </span>
                    </div>
                </button>
            `;
        })
        .join("");

    grid
        .querySelectorAll("[data-combo-label]")
        .forEach(button => {

            button.addEventListener("click", () => {
                toggleCustomizeCombo(button);
            });
        });
}


function toggleCustomizeCombo(button) {

    const label = button.dataset.comboLabel;

    const isActive = customizeState.combos.includes(label);

    if (isActive) {

        customizeState.combos =
            customizeState.combos.filter(item => item !== label);

        button.classList.remove("active");
        button.setAttribute("aria-pressed", "false");

        return;
    }


    if (customizeState.combos.length >= CUSTOMIZE_MAX_COMBOS) {

        showToast({
            title: "En fazla " + CUSTOMIZE_MAX_COMBOS + " kombin",
            message: "Önce bir seçimini kaldır.",
            tone: "neutral",
        });

        return;
    }


    customizeState.combos.push(label);

    button.classList.add("active");
    button.setAttribute("aria-pressed", "true");
}


function openCustomize() {

    goToCustomizeStep(1);

    setMessage($("customize-message"), "");

    $("customize-overlay")?.classList.add("open");
}


function closeCustomize() {

    $("customize-overlay")?.classList.remove("open");
}


function goToCustomizeStep(step) {

    const clamped = Math.min(
        Math.max(step, 1),
        CUSTOMIZE_STEP_COUNT
    );

    customizeState.step = clamped;


    document
        .querySelectorAll(".customize-step")
        .forEach(node => {

            node.classList.toggle(
                "active",
                Number(node.dataset.step) === clamped
            );
        });

    document
        .querySelectorAll("[data-step-dot]")
        .forEach(dot => {

            const dotStep = Number(dot.dataset.stepDot);

            dot.classList.toggle("active", dotStep === clamped);
            dot.classList.toggle("done", dotStep < clamped);
        });


    $("customize-back-btn")
        ?.classList.toggle("hidden", clamped === 1);

    const nextButton = $("customize-next-btn");

    if (nextButton) {

        nextButton.textContent =
            clamped === CUSTOMIZE_STEP_COUNT
                ? "PROFİLİMİ OLUŞTUR"
                : "DEVAM ET";
    }
}


async function submitCustomizeProfile() {

    if (customizeState.submitting) return;


    const hasAnySignal =
        customizeState.age ||
        customizeState.gender ||
        customizeState.colors.length ||
        customizeState.combos.length;

    if (!hasAnySignal) {

        setMessage(
            $("customize-message"),
            "Devam etmek için en az bir seçim yap.",
            "error"
        );

        return;
    }


    customizeState.submitting = true;

    setMessage($("customize-message"), "");

    const submitButton = $("customize-next-btn");

    setButtonLoading(submitButton, true);


    try {

        const response = await withAiAnalyzing(
            "Stil profilin oluşturuluyor...",
            () => apiFetch("/api/style-customize", {
                method: "POST",
                body: JSON.stringify({
                    age: customizeState.age,
                    gender: customizeState.gender,
                    colors: customizeState.colors,
                    styles: customizeState.combos,
                }),
            })
        );

        if (!response) {
            throw new Error("Profil oluşturulamadı.");
        }


        closeCustomize();

        await applyStyleCustomizationResults(response.items);

        showToast({
            title: "Profilin hazır",
            message:
                `${response.count} ürün, stil profiline göre ` +
                "seçildi. Beğen/beğenme ile akışı incelt.",
            tone: "success",
        });


    } catch (error) {

        console.error("Özelleştirme başarısız:", error);

        setMessage(
            $("customize-message"),
            error.message ||
            "Profil oluşturulurken bir hata oluştu.",
            "error"
        );

    } finally {

        customizeState.submitting = false;

        setButtonLoading(submitButton, false);
    }
}


/**
 * /api/style-customize'in dondurdugu urunleri, Kesfet
 * kartlarinin bekledigi sekle cevirir.
 *
 * match_label burada style_engine.py'nin ETIKET KURALINI
 * (bkz. build_match_display) taklit ediyor, ama skorun
 * KAYNAGI farkli: orada kelime agirligi, burada embedding
 * cosine benzerligi.
 */
function mapCustomizeItemToExploreItem(item, position) {

    const similarity = Number(item.similarity_score || 0);
    const percent = Math.round(similarity * 100);

    return {
        product: item,
        match_score: percent,
        match_label:
            percent >= 55 ? `%${percent} Profil Eşleşmesi` : null,
        reason_label: "Oluşturduğun stil profiline göre öneriliyor.",
        matched_style: null,
        is_exploration: false,
        position,
    };
}


/**
 * AI ile eslesen urunleri Kesfet akisina yerlestirir.
 *
 * Mevcut sonsuz-kaydirma/cursor durumunu SIFIRLAR: bu yeni
 * bir "oturum" — kullanici az once kendi profilini kurdu,
 * eski akisin kalintilariyla karismamali. hasMore=true
 * birakiliyor ki bu parti bitince normal AI akisi (feed.py)
 * kaldigi yerden devam etsin.
 */
async function applyStyleCustomizationResults(items) {

    if (!exploreGrid || !Array.isArray(items) || !items.length) {
        return;
    }


    explore.dwellTimers.forEach(timer => clearTimeout(timer));
    explore.dwellTimers.clear();

    Array.from(exploreGrid.children).forEach(card => {

        if (card.classList.contains("explore-card")) {
            unobserveCard(card);
        }
    });

    exploreGrid
        .querySelectorAll(".explore-card, .explore-error")
        .forEach(node => node.remove());

    exploreGrid.scrollLeft = 0;

    updateExploreEdgeFades();


    explore.rendered = [];
    explore.buffer = [];
    explore.cursor = null;
    explore.hasMore = true;
    explore.exhausted = false;

    hideExploreExhausted();


    const mapped = items.map(
        (item, index) => mapCustomizeItemToExploreItem(item, index)
    );

    appendExploreCards(mapped);

    updateExploreCount();
    renderAiStatus();
    renderExploreMore();


    $("explore")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
}


/* =========================================================
   KEŞFET / EXPLORE FEED
========================================================= */

const EXPLORE_PAGE_SIZE = 8;
const EXPLORE_BUFFER_MIN = 4;
const EXPLORE_BUFFER_FETCH = 8;
const EXPLORE_EXIT_MS = 340;


/*
   explore.rendered ve explore.buffer artik URUN degil,
   AI skorlu OGE tutuyor:

     { product, match_score, match_label,
       reason_label, is_exploration, position }
*/

const explore = {
    /* Ekranda duran ogeler */
    rendered: [],

    /*
       Onden cekilmis yedek ogeler.

       Iki ise yariyor:
         1. "Begenmedim" sonrasi kartin yerine ANINDA yenisi
            gelir; istek beklenmez.
         2. Sonsuz akis kaydirmada bekleme gostermez.
    */
    buffer: [],

    /* Cursor tabanli sayfalama */
    cursor: null,
    hasMore: true,

    loading: false,
    exhausted: false,
    remaining: 0,
    meta: null,

    /* Es zamanli dolumlari zincirlemek icin */
    fillChain: null,

    observer: null,
    scrollObserver: null,
    dwellTimers: new Map(),
};


function setupExplore() {

    if (!exploreGrid) return;


    setupExploreObserver();

    setupExploreWheelScroll();
    setupExploreEdgeFades();


    exploreRefreshButton
        ?.addEventListener("click", () => refreshExplore());


    /* Sonsuz akis — yatay kaydirma, root olarak
       exploreGrid'in kendisini kullaniyoruz (sag tarafa
       dogru genislet, ustte/altta degil). */

    explore.scrollObserver = setupInfiniteScroll(
        "explore-sentinel",
        "explore-more-btn",
        () => loadExplore(),
        () =>
            !explore.loading &&
            explore.hasMore &&
            explore.rendered.length > 0,
        {
            root: exploreGrid,
            rootMargin: "0px 400px 0px 0px",
        }
    );


    $("explore-login-btn")
        ?.addEventListener("click", () => {

            openAuth(
                "Seçimlerinin kaydedilmesi için giriş yap."
            );
        });


    exploreGrid.addEventListener("click", event => {

        const openTarget =
            event.target.closest("[data-explore-open]");

        if (openTarget) {

            const productId = openTarget.dataset.exploreOpen;

            const item = findExploreItem(productId);

            openProduct(productId, item?.product);

            return;
        }


        const button =
            event.target.closest("[data-explore-action]");

        if (!button) return;


        const card = button.closest(".explore-card");

        if (!card) return;


        if (button.dataset.exploreAction === "like") {

            handleExploreLike(
                card.dataset.productId,
                Number(card.dataset.position)
            );

            return;
        }


        if (button.dataset.exploreAction === "dislike") {

            handleExploreDislike(card);

            return;
        }


        if (button.dataset.exploreAction === "add-cart") {

            handleExploreAddToCart(
                card.dataset.productId,
                button
            );
        }
    });
}


async function handleExploreAddToCart(productId, button) {

    if (!isUserLoggedIn()) {

        openAuth("Sepete eklemek için giriş yap.");

        return;
    }


    const entry = findExploreItem(productId);
    const product = entry?.product;

    if (!product) return;


    button.disabled = true;

    try {

        await addToCart(productId, { source: "explore" });

        button.classList.add("active");

        showToast({
            title: "Sepete eklendi",
            message: `${productTitle(product)} sepetine eklendi.`,
            tone: "success",
        });


    } catch (error) {

        console.error("Sepete eklenemedi:", error);

        showToast({
            title: "Sepete eklenemedi",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });

    } finally {

        button.disabled = !hasPrice(product);
    }
}


/**
 * Masaustunde duz fare tekerlegi (trackpad degil) sadece
 * dikey scroll ureter. Kesfet yatay bir seritte ilerledigi
 * icin dikey tekerlek hareketini yatay kaydirmaya ceviriyoruz.
 *
 * Trackpad'in dogal yatay swipe'i (deltaX baskin) dokunulmadan
 * gecer; sadece dikey agirlikli hareketi (duz mouse tekerlegi)
 * yakalayip yonlendiriyoruz. Serit zaten sona/basa gelmisse
 * sayfanin normal dikey kaymasina izin veriyoruz.
 */
function setupExploreWheelScroll() {

    exploreGrid.addEventListener(
        "wheel",
        event => {

            if (
                Math.abs(event.deltaY) <=
                Math.abs(event.deltaX)
            ) {
                return;
            }


            const {
                scrollLeft,
                scrollWidth,
                clientWidth,
            } = exploreGrid;

            const atStart =
                scrollLeft <= 0 && event.deltaY < 0;

            const atEnd =
                scrollLeft + clientWidth >= scrollWidth - 1 &&
                event.deltaY > 0;

            if (atStart || atEnd) {
                return;
            }


            event.preventDefault();

            exploreGrid.scrollLeft += event.deltaY;
        },
        { passive: false }
    );
}


/**
 * Sagda/solda daha fazla urun oldugunu gosteren solma
 * efektlerini kaydirma konumuna gore acip kapatir.
 */
function updateExploreEdgeFades() {

    if (!exploreCarousel || !exploreGrid) return;


    const {
        scrollLeft,
        scrollWidth,
        clientWidth,
    } = exploreGrid;

    exploreCarousel.classList.toggle(
        "can-scroll-left",
        scrollLeft > 4
    );

    exploreCarousel.classList.toggle(
        "can-scroll-right",
        scrollLeft + clientWidth < scrollWidth - 4
    );
}


function setupExploreEdgeFades() {

    exploreGrid.addEventListener(
        "scroll",
        () => updateExploreEdgeFades(),
        { passive: true }
    );

    window.addEventListener(
        "resize",
        () => updateExploreEdgeFades()
    );

    updateExploreEdgeFades();
}


function findExploreItem(productId) {

    return explore.rendered.find(
        item => item.product.product_id === productId
    );
}


function cardMatchedStyle(card) {

    return card?.dataset.matchedStyle || null;
}


function cardMatchScore(card) {

    const raw = card?.dataset.matchScore;

    if (raw === undefined || raw === "") return null;

    const value = Number(raw);

    return Number.isFinite(value) ? value : null;
}


/* ---------------------------------------------------------
   GÖRÜNÜRLÜK TAKİBİ (VIEW)
--------------------------------------------------------- */

function setupExploreObserver() {

    if (typeof IntersectionObserver === "undefined") {
        return;
    }


    explore.observer = new IntersectionObserver(
        entries => {

            entries.forEach(entry => {

                const card = entry.target;
                const productId = card.dataset.productId;


                if (!entry.isIntersecting) {

                    clearTimeout(
                        explore.dwellTimers.get(productId)
                    );

                    explore.dwellTimers.delete(productId);

                    return;
                }


                const timer = setTimeout(() => {

                    queueView(
                        productId,
                        "explore",
                        Number(card.dataset.position),
                        cardMatchScore(card)
                    );

                    explore.dwellTimers.delete(productId);

                }, VIEW_DWELL_MS);


                explore.dwellTimers.set(productId, timer);
            });
        },
        { threshold: 0.5 }
    );
}


function observeCard(card) {

    explore.observer?.observe(card);
}


function unobserveCard(card) {

    const productId = card.dataset.productId;

    clearTimeout(explore.dwellTimers.get(productId));

    explore.dwellTimers.delete(productId);

    explore.observer?.unobserve(card);
}


/* ---------------------------------------------------------
   FEED YÜKLEME
--------------------------------------------------------- */

/**
 * Bir sonraki akış partisini getirir.
 *
 * SAYFA NUMARASI YOK. Sunucu her yanıtta `next_cursor`
 * döner, biz onu aynen geri gönderiyoruz. Cursor içinde
 * "kaldığım skor + son ürün + gösterilmiş kimlikler"
 * bilgisi var; bu yüzden ayrıca exclude listesi
 * göndermemiz gerekmiyor.
 */
async function fetchExplore(limit, { fresh = false } = {}) {

    const params = new URLSearchParams({ limit });

    if (!fresh && explore.cursor) {
        params.set("cursor", explore.cursor);
    }


    /*
       Misafir kullanicinin secimi sunucuda yok; parametre
       olarak gonderiyoruz. Giris yapmis kullanicida sunucu
       kayitli tercihi kullanir.
    */

    const styles = activeStyles();

    if (styles.length && !isUserLoggedIn()) {
        params.set("styles", styles.join(","));
    }


    const data = await apiFetch(`/api/explore?${params}`);

    explore.cursor = data.meta?.next_cursor || null;
    explore.hasMore = Boolean(data.meta?.has_more);
    explore.remaining = data.remaining ?? explore.remaining;
    explore.meta = data.meta || null;

    return data;
}


/**
 * Yedek havuzunu istenen sayıya kadar doldurur.
 *
 * Tek akış: hem sonsuz kaydırma hem "beğenmedim" sonrası
 * kart değişimi aynı yedekten besleniyor. İki ayrı
 * mekanizma olsa cursor iki yerden ilerletilir ve ürünler
 * tekrar ederdi.
 */
function ensureExploreBuffer(minimum) {

    /*
       YARIS KOSULU KORUMASI.

       Iki dolum islemi ayni anda calisirsa ikisi de AYNI
       explore.cursor degerini okur, ayni istegi atar ve
       ayni urunler iki kez akisa girer.

       Bu gercekten olusuyordu: loadExplore ilk partiyi
       cizdikten sonra refillExploreBuffer'i arka planda
       (await'siz) baslatiyor; kullanici o sirada "daha
       fazla"ya basarsa ikinci dolum devreye giriyordu.

       Cozum: dolumlari zincirle. Yeni cagri oncekinin
       bitmesini bekler, sonra kosulu YENIDEN degerlendirir
       (yedek bu arada dolmus olabilir).
    */

    explore.fillChain = (explore.fillChain || Promise.resolve())
        .then(() => fillExploreBufferOnce(minimum))
        .catch(error => {
            console.warn("Yedek doldurulamadi:", error);
            return explore.buffer.length;
        });

    return explore.fillChain;
}


async function fillExploreBufferOnce(minimum) {

    let guard = 0;

    while (
        explore.buffer.length < minimum &&
        explore.hasMore &&
        guard < 5
    ) {
        guard++;

        const data = await fetchExplore(EXPLORE_PAGE_SIZE);

        const items = data.items || [];

        if (!items.length) {
            explore.hasMore = false;
            break;
        }

        /*
           Ikinci koruma katmani: sunucudan gelen bir oge
           zaten ekranda veya yedekteyse alma. Cursor bunu
           halletmeli ama ekranda tekrar eden kart cok
           gorunur bir hata; iki kat guvenlik ucuz.
        */

        const known = new Set([
            ...explore.rendered.map(i => i.product.product_id),
            ...explore.buffer.map(i => i.product.product_id),
        ]);

        const fresh = items.filter(
            item => !known.has(item.product.product_id)
        );

        if (!fresh.length) {
            /* Hepsi tekrar: cursor ilerlemiyor, dur */
            explore.hasMore = false;
            break;
        }

        explore.buffer.push(...fresh);
    }

    return explore.buffer.length;
}


async function loadExplore({ reset = false } = {}) {

    if (!exploreGrid || explore.loading) return;


    explore.loading = true;

    if (reset) {
        explore.cursor = null;
        explore.hasMore = true;
        explore.fillChain = null;
        explore.buffer = [];
        explore.rendered = [];

        /* Sadece kartlari kaldir, sentinel (yatay kaydirma
           tetikleyicisi) grid'in child'i oldugu icin yerinde
           kalmali. */
        exploreGrid
            .querySelectorAll(".explore-card, .explore-error")
            .forEach(node => node.remove());

        exploreGrid.scrollLeft = 0;
        updateExploreEdgeFades();

        explore.exhausted = false;
        hideExploreExhausted();
    }

    setExploreMoreLoading(true);

    if (reset) {
        showExploreLoader(true);
    }


    try {

        /*
           YALNIZCA EKRANA KOYACAGIMIZ KADAR BEKLIYORUZ.

           Onceden yedek havuz da dolana kadar bekleniyordu
           (8 + 4 = 12 oge) ve bu iki API turu demekti;
           Kesfet bolumu saniyelerce bos kaliyordu.

           Simdi ilk parti gelir gelmez ciziliyor, yedek
           arkada dolduruluyor.
        */

        await ensureExploreBuffer(EXPLORE_PAGE_SIZE);

        const batch = explore.buffer.splice(0, EXPLORE_PAGE_SIZE);

        appendExploreCards(batch);

        updateExploreCount();

        renderAiStatus();

        renderExploreMore();


        /* Yedegi arkada doldur — await YOK */
        refillExploreBuffer();


        if (!explore.rendered.length) {

            explore.exhausted = true;

            showExploreExhausted();
        }


    } catch (error) {

        console.error("Keşfet yüklenemedi:", error);

        if (!explore.rendered.length) {

            const errorNode = document.createElement("div");

            errorNode.className = "explore-error";

            errorNode.textContent =
                "Keşfet akışı yüklenemedi. Backend bağlantısını kontrol et.";

            exploreGrid
                .querySelectorAll(".explore-error")
                .forEach(node => node.remove());

            exploreGrid.insertBefore(
                errorNode,
                exploreGrid.firstChild
            );
        }

        explore.hasMore = false;

    } finally {

        explore.loading = false;

        showExploreLoader(false);

        setExploreMoreLoading(false);
    }
}


/**
 * Kartları ızgaranın sonuna ekler.
 *
 * Kademeli giriş (stagger): her kart 55 ms sonra beliriyor.
 * Framer Motion'daki `staggerChildren` karşılığı; CSS
 * animation-delay ile yapılıyor.
 *
 * Sentinel (#explore-sentinel) grid'in son child'i olarak
 * duruyor (yatay kaydirmada sonsuz akis tetikleyicisi).
 * Yeni kartlar hep ONDAN ONCE eklenir ki sentinel her zaman
 * en sonda kalsin.
 */
function appendExploreCards(items) {

    if (!exploreGrid || !items.length) return;


    const fragment = document.createDocumentFragment();

    items.forEach((item, offset) => {

        explore.rendered.push(item);

        const card = buildExploreCard(
            item,
            explore.rendered.length - 1
        );

        card.style.setProperty(
            "--stagger",
            `${Math.min(offset, 11) * 55}ms`
        );

        fragment.appendChild(card);
    });


    const sentinel = $("explore-sentinel");

    if (sentinel && sentinel.parentElement === exploreGrid) {
        exploreGrid.insertBefore(fragment, sentinel);
    } else {
        exploreGrid.appendChild(fragment);
    }

    hydrateIcons(exploreGrid);


    /* Gozlemciyi yeni kartlara bagla */
    Array.from(exploreGrid.children).forEach(card => {

        if (card.classList.contains("explore-card")) {
            observeCard(card);
        }
    });


    /* Yeni kartlarla genislik degisti; sag solmayi guncelle. */
    updateExploreEdgeFades();
}


function renderExploreMore() {

    const wrapper = $("explore-more");

    if (!wrapper) return;


    wrapper.classList.toggle(
        "hidden",
        !explore.rendered.length || !explore.hasMore
    );
}


function setExploreMoreLoading(loading) {

    $("explore-more")?.classList.toggle("loading", loading);
}


async function refillExploreBuffer() {

    /* ensureExploreBuffer cursor'u dogru ilerletiyor */
    try {
        await ensureExploreBuffer(EXPLORE_BUFFER_MIN);

    } catch (error) {
        console.warn("Yedek ürünler alınamadı:", error);
    }

    renderExploreMore();
}


async function refreshExplore({ silent = false } = {}) {

    if (!silent) {
        exploreRefreshButton?.classList.add("spinning");
    }


    explore.dwellTimers.forEach(timer => clearTimeout(timer));
    explore.dwellTimers.clear();

    Array.from(exploreGrid?.children || []).forEach(card => {

        if (card.classList.contains("explore-card")) {
            unobserveCard(card);
        }
    });


    await loadExplore({ reset: true });


    if (!silent) {
        exploreRefreshButton?.classList.remove("spinning");
    }
}


/* ---------------------------------------------------------
   KART
--------------------------------------------------------- */

function buildExploreCard(item, position) {

    const product = item.product;

    const card = document.createElement("article");

    card.className = "explore-card";

    card.dataset.productId = product.product_id;
    card.dataset.position = position;

    if (item.match_score !== null && item.match_score !== undefined) {
        card.dataset.matchScore = item.match_score;
    }

    if (item.matched_style) {
        card.dataset.matchedStyle = item.matched_style;
    }

    if (item.is_exploration) {
        card.dataset.exploration = "1";
    }


    const liked = isWishlisted(product.product_id);

    if (liked) {
        card.classList.add("liked");
    }


    const discount = Number(product.discount_percent || 0);


    /*
       Sag ust kose: ya AI eslesme yuzdesi ya da kesif
       isareti. Ikisi ayni yerde cunku ayni soruyu
       cevapliyorlar: "bu urun neden burada?"
    */

    /*
       Yuksek uyumda (>=90) badge daha guclu parliyor.
       Esik hesabini frontend yapmiyor — sunucu match_label'i
       hazir gonderiyor, biz yalnizca gorsel siddeti
       ayarliyoruz.
    */

    const isHighMatch = Number(item.match_score || 0) >= 90;

    const cornerBadge = item.match_label
        ? `
            <span class="explore-match${isHighMatch ? " high" : ""}">
                <span class="ai-dot"></span>
                ${escapeHTML(item.match_label)}
            </span>
        `
        : item.is_exploration
            ? `
                <span class="explore-explore-tag">
                    KEŞFET
                </span>
            `
            : "";


    card.innerHTML = `

        <div
            class="explore-card-image"
            data-explore-open="${escapeHTML(product.product_id)}"
        >

            <img
                src="${escapeHTML(safeImage(product.image_url))}"
                alt="${escapeHTML(productTitle(product))}"
                loading="lazy"
                onerror="this.src='https://placehold.co/600x800?text=WishNN'"
            >

            ${
                discount > 0
                    ? `<span class="explore-badge">-${discount}%</span>`
                    : ""
            }

            <div class="explore-quick-actions">

                <button
                    type="button"
                    class="explore-quick-btn explore-quick-like explore-action-like${
                        liked ? " active" : ""
                    }"
                    data-explore-action="like"
                    aria-label="Favorilere ekle"
                >
                    ${icon("heart", { filled: liked })}
                </button>

                <button
                    type="button"
                    class="explore-quick-btn explore-quick-cart${
                        isInCart(product.product_id) ? " active" : ""
                    }"
                    data-explore-action="add-cart"
                    aria-label="Sepete ekle"
                    ${hasPrice(product) ? "" : "disabled"}
                >
                    <i class="fa-solid fa-bag-shopping"></i>
                </button>

            </div>

            ${cornerBadge}

            <span class="explore-liked-badge">
                ${icon("heart", { filled: true })}
                FAVORİDE
            </span>

        </div>


        <div class="explore-card-body">

            ${
                item.reason_label
                    ? `
                        <span class="explore-reason">
                            ${icon("sparkles")}
                            ${escapeHTML(item.reason_label)}
                        </span>
                    `
                    : ""
            }

            ${
                product.brand
                    ? `
                        <div class="explore-card-brand">
                            ${escapeHTML(product.brand)}
                        </div>
                    `
                    : ""
            }

            <h4 class="explore-card-title">
                ${escapeHTML(productTitle(product))}
            </h4>

            <div class="explore-card-price">

                <span class="current-price">
                    ${formatPrice(product.price)}
                </span>

                ${
                    product.list_price &&
                    Number(product.list_price) >
                    Number(product.price || 0)
                        ? `
                            <span class="old-price">
                                ${formatPrice(product.list_price)}
                            </span>
                        `
                        : ""
                }

            </div>

        </div>


        <div class="explore-actions">

            <button
                type="button"
                class="explore-action explore-action-dislike"
                data-explore-action="dislike"
                aria-label="Bu ürünü beğenmedim"
            >
                ${icon("thumbs-down")}
                BEĞENMEDİM
            </button>

            <button
                type="button"
                class="explore-action explore-action-like${
                    liked ? " active" : ""
                }"
                data-explore-action="like"
                aria-label="Favorilere ekle"
            >
                ${icon("heart", { filled: liked })}
                ${liked ? "FAVORİDE" : "BEĞENDİM"}
            </button>

        </div>
    `;


    return card;
}


/* ---------------------------------------------------------
   KALP (LIKE)
--------------------------------------------------------- */

async function handleExploreLike(productId, position) {

    if (!productId) return;


    if (!isUserLoggedIn()) {

        requestLoginForInteraction(
            { type: "LIKE", productId, position },
            "Favorilerine eklemek için giriş yap."
        );

        return;
    }


    const card = findExploreCard(productId);

    const button = card?.querySelector(".explore-action-like");


    /* Zaten favorideyse ikinci tık favoriden çıkarır */

    if (isWishlisted(productId)) {

        try {

            /*
               sendInteraction'i dogrudan cagirmiyoruz:
               removeFromWishlist ayni istegi atip ustune
               state.wishlist ve header rozetini de
               guncelliyor. Ikisini ayirmak durum ile
               sunucuyu birbirinden koparirdi.
            */

            const response = await removeFromWishlist(
                productId,
                {
                    source: "explore",
                    matchScore: cardMatchScore(card),
                    matchedStyle: cardMatchedStyle(card),
                }
            );

            syncWishlistButtons(productId, false);

            renderAiStatus();

            if (wishlistOverlay?.classList.contains("open")) {
                renderWishlistPanel();
            }

            if (response?.toast) {
                showToast(response.toast);
            }


        } catch (error) {

            console.error("Favoriden çıkarılamadı:", error);

            showToast({
                title: "Çıkarılamadı",
                message: "Bağlantını kontrol edip tekrar dene.",
                tone: "error",
            });
        }

        return;
    }


    /* İyimser arayüz */

    syncWishlistButtons(productId, true);

    button?.classList.add("pulse");

    card?.classList.add("just-liked");

    setTimeout(() => {
        button?.classList.remove("pulse");
        card?.classList.remove("just-liked");
    }, 650);


    try {

        const response = await addToWishlist(productId, {
            source: "explore",
            position,
            matchScore: cardMatchScore(card),
            matchedStyle: cardMatchedStyle(card),
            product: findExploreItem(productId)?.product,
        });


        renderAiStatus();


        if (wishlistOverlay?.classList.contains("open")) {
            renderWishlistPanel();
        }


        showToast(
            response?.toast || {
                title: "Favorilerine eklendi",
                message: "Benzer ürünler akışına önceliklendirildi.",
                tone: "success",
            }
        );


    } catch (error) {

        console.error("Favorilere eklenemedi:", error);

        state.wishlist.delete(String(productId));

        renderWishlistBadge();

        syncWishlistButtons(productId, false);

        showToast({
            title: "Kaydedilemedi",
            message: "Bağlantını kontrol edip tekrar dene.",
            tone: "error",
        });
    }
}


/* ---------------------------------------------------------
   BEĞENMEDİM (DISLIKE)
--------------------------------------------------------- */

async function handleExploreDislike(card) {

    if (!card || card.classList.contains("dismissing")) {
        return;
    }


    const productId = card.dataset.productId;
    const position = Number(card.dataset.position);


    if (!isUserLoggedIn()) {

        requestLoginForInteraction(
            { type: "DISLIKE", productId, position },
            "Seçimini kaydetmek için giriş yap."
        );

        return;
    }


    /*
       SUNUCUYA HEMEN YAZMIYORUZ.

       Yanlislikla basmak cok kolay ve DISLIKE kalici bir
       karar (urun bir daha hic gosterilmiyor). Yazma islemi
       UNDO_WINDOW_MS kadar geciktiriliyor; kullanici geri
       alirsa sunucuya hicbir sey gitmiyor.

       Neden "yaz sonra sil" degil: user_interactions
       append-only bir olay kaydi ve egitim verisinin
       butunlugu buna dayaniyor. Ayrica yanlislikla basilan
       bir tus anlamli bir ML sinyali degil — hic
       yazilmamasi daha dogru.
    */

    const snapshot = {
        item: findExploreItem(productId),
        nextSibling: card.nextElementSibling,
        parent: card.parentElement,
        position,
        matchScore: cardMatchScore(card),
        matchedStyle: cardMatchedStyle(card),
    };


    card
        .querySelectorAll(".explore-action")
        .forEach(button => {
            button.disabled = true;
        });


    /* Sola kayarak cikis */

    card.classList.add("dismissing");

    unobserveCard(card);

    explore.rendered = explore.rendered.filter(
        entry => entry.product.product_id !== productId
    );


    if (isWishlisted(productId)) {

        state.wishlist.delete(String(productId));

        renderWishlistBadge();
    }


    scheduleDislike(productId, snapshot);


    showToast({
        title: "Anlaşıldı, bu tarz elendi",
        message: "Bu ürün ve benzer kesimler geri planda kalacak.",
        tone: "neutral",
        undoLabel: "GERİ AL",
        duration: UNDO_WINDOW_MS,
        onUndo: () => undoDislike(productId),
    });


    setTimeout(
        () => replaceExploreCard(card),
        EXPLORE_EXIT_MS
    );
}


/**
 * Beğenmedim'i geri alır.
 *
 * Sunucuya hiçbir şey yazılmadığı için geri alma tamamen
 * arayüz işi: yerine gelen kart çıkarılıyor, eski kart
 * eski konumuna geri konuyor.
 */
function undoDislike(productId) {

    const pending = cancelPendingDislike(productId);

    if (!pending?.item) return;


    /* Yerine gelen kartı geri al */

    if (pending.replacementId) {

        const replacement = findExploreCard(pending.replacementId);

        explore.rendered = explore.rendered.filter(
            entry =>
                entry.product.product_id !== pending.replacementId
        );

        /* Yedeğin başına koy: sırası kaybolmasın */
        if (pending.replacementItem) {
            explore.buffer.unshift(pending.replacementItem);
        }

        if (replacement) {
            unobserveCard(replacement);
            replacement.remove();
        }
    }


    /* Kartı eski konumuna yerleştir */

    const restored = buildExploreCard(
        pending.item,
        pending.position
    );

    restored.classList.add("restoring");

    const parent = pending.parent || exploreGrid;

    if (
        pending.nextSibling &&
        pending.nextSibling.parentElement === parent
    ) {
        parent.insertBefore(restored, pending.nextSibling);
    } else {
        parent.appendChild(restored);
    }

    explore.rendered.push(pending.item);

    observeCard(restored);

    hydrateIcons(restored);

    setTimeout(
        () => restored.classList.remove("restoring"),
        500
    );


    updateExploreCount();

    renderExploreMore();


    showToast({
        title: "Geri alındı",
        message: "Ürün akışına geri döndü.",
        tone: "info",
    });
}


function replaceExploreCard(card) {

    const next = explore.buffer.shift();

    /*
       Geri alma senaryosu icin: bu kartin yerine hangi urun
       geldigini bekleyen kayda yaziyoruz. Geri alinirsa yeni
       kart cikarilip eski kart yerine konabilsin.
    */
    const pending = pendingDislikes.get(card.dataset.productId);

    if (pending && next) {
        pending.replacementId = next.product.product_id;
        pending.replacementItem = next;
    }


    if (next) {

        explore.rendered.push(next);

        const replacement = buildExploreCard(
            next,
            explore.rendered.length - 1
        );

        card.replaceWith(replacement);

        observeCard(replacement);


    } else {

        card.remove();

        if (!exploreGrid?.children.length) {

            explore.exhausted = true;

            showExploreExhausted();
        }
    }


    updateExploreCount();

    renderExploreMore();

    /* Yedek azaldiysa arka planda doldur */
    refillExploreBuffer();
}


/* ---------------------------------------------------------
   ETKİLEŞİM GÖNDERİMİ
--------------------------------------------------------- */

/**
 * /api/interact — tek uç, bütün ürün etkileşimleri.
 *
 * matchScore mutlaka gönderilir: model "kullanıcı neyi
 * beğendi" değil "X skoruyla gösterilen şeyi beğendi mi"
 * sorusunu öğrenmeli.
 */
async function sendInteraction({
    productId,
    type,
    source = "explore",
    position = null,
    matchScore = null,
    matchedStyle = null,
}) {

    return apiFetch("/api/interact", {
        method: "POST",

        body: JSON.stringify({
            product_id: productId,
            interaction_type: type,
            source,
            position: Number.isFinite(position) ? position : null,
            match_score:
                matchScore === null || matchScore === undefined
                    ? null
                    : matchScore,

            /* Hangi tarz eslesmisti — ML baglami */
            matched_style: matchedStyle,
        }),
    });
}


/* ---------------------------------------------------------
   DURUM GÖSTERGELERİ
--------------------------------------------------------- */

function updateExploreCount() {

    const label = $("explore-count");

    if (!label) return;


    const shown = explore.rendered.length;


    if (!explore.hasMore && shown) {

        label.textContent = `${shown} ürün · tümünü gördün`;

        return;
    }


    if (!isUserLoggedIn()) {

        label.textContent =
            `${explore.remaining} ürün keşfedilmeyi bekliyor`;

        return;
    }


    label.textContent = shown
        ? `${shown} ürün gösterildi · akış devam ediyor`
        : `Senin için ${explore.remaining} ürün var`;
}


function showExploreLoader(visible) {

    $("explore-loader")
        ?.classList.toggle("hidden", !visible);
}


function showExploreExhausted() {

    $("explore-exhausted")
        ?.classList.remove("hidden");
}


function hideExploreExhausted() {

    $("explore-exhausted")
        ?.classList.add("hidden");
}


function renderExploreNotice() {

    $("explore-notice")
        ?.classList.toggle("hidden", isUserLoggedIn());
}


/* ---------------------------------------------------------
   OTURUM DEĞİŞİNCE
--------------------------------------------------------- */

async function onSessionChanged() {

    renderExploreNotice();

    await loadWishlist();
    await loadCart();
    await loadWardrobe();

    /* Alt barin kucuk gorselleri icin tam liste */
    refreshWishlistItems();

    /* Okunmamis mesaj rozeti. Hem acilista hem oturum
       degisiminde tazeleniyor: cikis yapinca rozet
       birinin okunmamislarini gostermeye devam etmemeli. */
    refreshSocialBadge();

    await syncArchetypeAfterLogin();


    explore.rendered.forEach(item => {

        syncWishlistButtons(
            item.product.product_id,
            isWishlisted(item.product.product_id)
        );
    });


    updateExploreCount();

    renderAiStatus();


    await resumePendingInteraction();
}


/* =========================================================
   ÜRÜN DETAYINDA FAVORİ BUTONU
========================================================= */

function setupModalWishlistButton(product) {

    const button = $("modal-wishlist-btn");

    if (!button || !product) return;


    button.dataset.productId = product.product_id;

    setModalWishlistButton(
        button,
        isWishlisted(product.product_id)
    );


    button.addEventListener(
        "click",
        handleModalWishlistToggle
    );
}


async function handleModalWishlistToggle() {

    const button = $("modal-wishlist-btn");

    if (!button) return;


    const productId = button.dataset.productId;

    if (!productId) return;


    if (!isUserLoggedIn()) {

        requestLoginForInteraction(
            { type: "MODAL_LIKE", productId },
            "Favorilerine eklemek için giriş yap."
        );

        return;
    }


    button.disabled = true;


    try {

        let response;

        if (isWishlisted(productId)) {

            response = await removeFromWishlist(
                productId,
                { source: "detail" }
            );

            syncWishlistButtons(productId, false);

        } else {

            response = await addToWishlist(
                productId,
                {
                    source: "detail",
                    product: findExploreItem(productId)?.product,
                }
            );

            syncWishlistButtons(productId, true);
        }


        renderAiStatus();


        if (wishlistOverlay?.classList.contains("open")) {
            renderWishlistPanel();
        }


        if (response?.toast) {
            showToast(response.toast);
        }


    } catch (error) {

        console.error("Favori güncellenemedi:", error);

        showToast({
            title: "Güncellenemedi",
            message: "Bağlantını kontrol edip tekrar dene.",
            tone: "error",
        });

    } finally {

        button.disabled = false;
    }
}


/* =========================================================
   LUCIDE IKONLARI
   ---------------------------------------------------------
   Lucide bir React kutuphanesi. Vanilla tarafta ihtiyac
   duyulan ikonlarin SVG govdelerini satir ici basiyoruz;
   boylece ek bir CDN istegi yok ve ikonlar currentColor
   ile temaya uyuyor.

   Sitenin geri kalani Font Awesome kullanmaya devam ediyor.
   Yalnizca ETKILESIM ikonlari Lucide'a gecti cunku istenen
   "basparmak asagi" ikonu Lucide'da.
========================================================= */

const LUCIDE = {
    heart:
        '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',

    "thumbs-down":
        '<path d="M17 14V2"/>' +
        '<path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/>',

    "undo-2":
        '<path d="M9 14 4 9l5-5"/>' +
        '<path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5 5.5 5.5 0 0 1-5.5 5.5H11"/>',

    zap:
        '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',

    sparkles:
        '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/>',

    check: '<path d="M20 6 9 17l-5-5"/>',

    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',

    lock:
        '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>' +
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>',

    "rotate-cw":
        '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>' +
        '<path d="M21 3v5h-5"/>',

    info:
        '<circle cx="12" cy="12" r="10"/>' +
        '<path d="M12 16v-4"/><path d="M12 8h.01"/>',

    /* Arama analizi etiketleri */

    user:
        '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>' +
        '<circle cx="12" cy="7" r="4"/>',

    shirt:
        '<path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0' +
        '-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2' +
        ' 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34' +
        '-2.23z"/>',

    palette:
        '<path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746' +
        ' 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652' +
        '-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555' +
        '-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>' +
        '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>' +
        '<circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>' +
        '<circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>' +
        '<circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>',

    sun:
        '<circle cx="12" cy="12" r="4"/>' +
        '<path d="M12 2v2"/><path d="M12 20v2"/>' +
        '<path d="m4.93 4.93 1.41 1.41"/>' +
        '<path d="m17.66 17.66 1.41 1.41"/>' +
        '<path d="M2 12h2"/><path d="M20 12h2"/>' +
        '<path d="m6.34 17.66-1.41 1.41"/>' +
        '<path d="m19.07 4.93-1.41 1.41"/>',

    layers:
        '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0' +
        ' 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/>' +
        '<path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>' +
        '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',

    ruler:
        '<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1' +
        '-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1' +
        ' 3.4 0Z"/>' +
        '<path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/>' +
        '<path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/>',

    calendar:
        '<path d="M8 2v4"/><path d="M16 2v4"/>' +
        '<rect width="18" height="18" x="3" y="4" rx="2"/>' +
        '<path d="M3 10h18"/>',

    /* Bütçe etiketi ve trend/yer bölümleri için. icon()
       tanımadığı ada boş string döndürüyor — yani eksik
       ikon sessizce kayboluyor, bu yüzden kullanılan her
       adın burada olması gerekiyor. */
    wallet:
        '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15' +
        'a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2"/>' +
        '<path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',

    "map-pin":
        '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/>' +
        '<circle cx="12" cy="10" r="3"/>',
};


/**
 * Lucide ikonunu SVG olarak döndürür.
 *
 * `filled` true ise (kalp için) gövde currentColor ile
 * dolduruluyor — dolu/boş kalp ayrımı bu.
 */
function icon(name, { filled = false } = {}) {

    const body = LUCIDE[name];

    if (!body) return "";

    const key = filled ? `${name}-filled` : name;

    return (
        `<span data-icon="${escapeHTML(key)}" aria-hidden="true">` +
        '<svg viewBox="0 0 24 24">' +
        body +
        "</svg>" +
        "</span>"
    );
}


/**
 * HTML'de `<span data-icon="heart">` gibi yer tutucuları
 * gerçek SVG ile doldurur.
 *
 * Sayfa açılışında bir kez, sonra dinamik eklenen
 * bölümlerde tekrar çağrılıyor.
 */
function hydrateIcons(root = document) {

    root.querySelectorAll("[data-icon]:empty").forEach(node => {

        const name = node.dataset.icon.replace(/-filled$/, "");

        const body = LUCIDE[name];

        if (!body) return;

        node.innerHTML = `<svg viewBox="0 0 24 24">${body}</svg>`;
    });
}


/* =========================================================
   BEĞENMEDİM: GERİ ALMA PENCERESİ
   ---------------------------------------------------------
   Yanlislikla basmak cok kolay ve DISLIKE kalici bir karar.
   Bu yuzden sunucuya yazmayi kisa bir sure GECIKTIRIYORUZ.

   Neden gecikme, neden "yaz sonra sil" degil:
   user_interactions append-only bir olay kaydi — egitim
   verisinin butunlugu buna dayaniyor. Satir silmek o
   garantiyi bozar. Ayrica yanlislikla basilan bir tus
   anlamli bir ML sinyali degil; hic yazilmamasi daha dogru.

   Kullanici geri almazsa sure sonunda yaziliyor. Sekme
   kapanirsa bekleyenler keepalive ile gonderiliyor:
   kullanici eylemi yapti ve geri almadi.
========================================================= */

const UNDO_WINDOW_MS = 5000;

/* productId -> { timer, item, card, position } */
const pendingDislikes = new Map();


function scheduleDislike(productId, payload) {

    /* Ayni urun icin ikinci kez basildiysa sureyi yenile */
    cancelPendingDislike(productId, { silent: true });

    const timer = setTimeout(
        () => commitDislike(productId),
        UNDO_WINDOW_MS
    );

    pendingDislikes.set(productId, { ...payload, timer });
}


async function commitDislike(productId) {

    const pending = pendingDislikes.get(productId);

    if (!pending) return;

    clearTimeout(pending.timer);

    pendingDislikes.delete(productId);


    try {

        await sendInteraction({
            productId,
            type: "DISLIKE",
            source: "explore",
            position: pending.position,
            matchScore: pending.matchScore,
            matchedStyle: pending.matchedStyle,
        });


        /*
           Kaydedildi. Kategori cezasi da uygulandigi icin
           akisin geri kalanini tazelemek gerekmiyor —
           bir sonraki sayfa zaten yeni skorlarla gelecek.
        */

    } catch (error) {

        console.error("Beğenmedim kaydedilemedi:", error);

        showToast({
            title: "Kaydedilemedi",
            message: "Bağlantını kontrol edip tekrar dene.",
            tone: "error",
        });
    }
}


function cancelPendingDislike(productId, { silent = false } = {}) {

    const pending = pendingDislikes.get(productId);

    if (!pending) return null;

    clearTimeout(pending.timer);

    pendingDislikes.delete(productId);

    if (!silent) {
        console.debug("Beğenmedim geri alındı:", productId);
    }

    return pending;
}


/**
 * Sekme kapanırken bekleyen beğenmedimleri gönderir.
 *
 * Kullanıcı eylemi yaptı ve geri alma süresi içinde geri
 * almadı; commit etmek doğru varsayılan.
 */
function flushPendingDislikes() {

    if (!pendingDislikes.size || !isUserLoggedIn()) return;


    const items = [];

    pendingDislikes.forEach((pending, productId) => {

        clearTimeout(pending.timer);

        items.push({
            product_id: productId,
            interaction_type: "DISLIKE",
            source: "explore",
            position: pending.position ?? null,
            match_score: pending.matchScore ?? null,
        });
    });

    pendingDislikes.clear();


    fetch(
        `${API_BASE}/interactions/batch`,
        {
            method: "POST",

            headers: {
                "Content-Type": "application/json",
                ...authHeaders(),
            },

            body: JSON.stringify({ items }),

            keepalive: true,
        }
    ).catch(() => {});
}


/* =========================================================
   HIZLI SATIN ALMA  (sepetsiz, tek ekran)
========================================================= */

const quickState = {
    /* "single": tek urun (Hizli Al) | "cart": sepetteki tumu */
    mode: "single",

    /* Su an satin alinmakta olan urun (mode: "single") */
    item: null,

    submitting: false,
};


function setupQuickCheckout() {

    checkoutCloseButton
        ?.addEventListener("click", closeQuickCheckout);


    checkoutOverlay?.addEventListener("click", event => {

        if (event.target === checkoutOverlay) {
            closeQuickCheckout();
        }
    });


    $("quick-done")?.addEventListener(
        "click",
        closeQuickCheckout
    );


    quickForm?.addEventListener("submit", event => {

        event.preventDefault();

        submitQuickOrder();
    });


    /* Kart alanı maskeleri */

    $("quick-card")?.addEventListener("input", event => {

        const digits = event.target.value
            .replace(/\D/g, "")
            .slice(0, 19);

        event.target.value =
            digits.replace(/(.{4})/g, "$1 ").trim();
    });


    $("quick-expiry")?.addEventListener("input", event => {

        const digits = event.target.value
            .replace(/\D/g, "")
            .slice(0, 4);

        event.target.value =
            digits.length > 2
                ? `${digits.slice(0, 2)}/${digits.slice(2)}`
                : digits;
    });


    $("quick-cvc")?.addEventListener("input", event => {

        event.target.value = event.target.value
            .replace(/\D/g, "")
            .slice(0, 4);
    });
}


/**
 * Tek ürünle hızlı satın almayı açar.
 *
 * item: explore öğesi ({product, match_score, ...}) veya
 *       sade ürün objesi. İkisini de kabul ediyor çünkü
 *       ürün ızgarasından ve detaydan da çağrılıyor.
 */
function openQuickCheckout(input, context = {}) {

    const item = input?.product
        ? input
        : { product: input, match_score: null, matched_style: null };

    if (!item.product?.product_id) return;


    if (!hasPrice(item.product)) {

        showToast({
            title: "Satın alınamıyor",
            message: "Bu ürünün fiyat bilgisi bulunmuyor.",
            tone: "error",
        });

        return;
    }


    if (!isUserLoggedIn()) {

        state.pendingQuickBuy = { item, context };

        openAuth("Satın almak için giriş yap.");

        return;
    }


    quickState.mode = "single";
    quickState.item = { ...item, ...context };

    closeModal();

    closeWishlistPanel();
    closeCartPanel();


    /* Formu sıfırla, onay ekranını gizle */

    clearFieldErrors(quickForm);

    $("quick-body")?.classList.remove("hidden");
    $("quick-success")?.classList.add("hidden");

    renderQuickProduct(item);

    prefillQuickForm();

    checkoutOverlay?.classList.add("open");

    hydrateIcons(checkoutOverlay);

    setTimeout(() => $("quick-name")?.focus(), 250);
}


function closeQuickCheckout() {

    checkoutOverlay?.classList.remove("open");
}


/**
 * Sepetteki TUM urunleri tek seferde odemeye acar.
 *
 * Ayni checkout-overlay/quick-panel'i (teslimat + kart formu)
 * kullanir; farki #quick-product'ta tek urun yerine sepet
 * ozetinin gosterilmesi ve gonderimde /cart/checkout'un
 * cagrilmasidir (bkz. submitQuickOrder, quickState.mode).
 */
function openCartCheckout() {

    if (!state.cart.length) return;


    if (!isUserLoggedIn()) {

        openAuth("Ödeme yapmak için giriş yap.");

        return;
    }


    quickState.mode = "cart";
    quickState.item = null;

    closeCartPanel();
    closeModal();
    closeWishlistPanel();


    clearFieldErrors(quickForm);

    $("quick-body")?.classList.remove("hidden");
    $("quick-success")?.classList.add("hidden");

    renderQuickCartSummary();

    prefillQuickForm();

    checkoutOverlay?.classList.add("open");

    hydrateIcons(checkoutOverlay);

    setTimeout(() => $("quick-name")?.focus(), 250);
}


function renderQuickCartSummary() {

    const holder = $("quick-product");

    if (!holder) return;


    const rows = state.cart
        .map(item => {

            const product = item.product || {};

            return `
                <div class="quick-cart-row">

                    <img
                        src="${escapeHTML(safeImage(product.image_url))}"
                        alt="${escapeHTML(productTitle(product))}"
                        loading="lazy"
                    >

                    <div class="quick-cart-row-body">

                        <strong>
                            ${escapeHTML(productTitle(product))}
                        </strong>

                        <span>
                            ${Number(item.quantity)} adet ·
                            ${formatPrice(product.price)}
                        </span>

                    </div>

                </div>
            `;
        })
        .join("");


    const subtotal = state.cart.reduce(
        (sum, item) =>
            sum +
            Number(item.product?.price || 0) *
            Number(item.quantity || 0),
        0
    );

    const totalQuantity = state.cart.reduce(
        (sum, item) => sum + Number(item.quantity || 0),
        0
    );


    holder.innerHTML = `
        <div class="quick-cart-summary">
            ${rows}
        </div>

        <div class="quick-cart-total">
            <span>${totalQuantity} ürün · Ara Toplam</span>
            <strong>${formatPrice(subtotal)}</strong>
        </div>
    `;
}


function renderQuickProduct(item) {

    const holder = $("quick-product");

    if (!holder) return;


    const product = item.product;

    const hasOldPrice =
        product.list_price &&
        Number(product.list_price) > Number(product.price || 0);


    holder.innerHTML = `

        <img
            src="${escapeHTML(safeImage(product.image_url))}"
            alt="${escapeHTML(productTitle(product))}"
            loading="lazy"
        >

        <div class="quick-product-info">

            <strong>${escapeHTML(productTitle(product))}</strong>

            <div class="quick-product-price">

                <span>${formatPrice(product.price)}</span>

                ${
                    hasOldPrice
                        ? `<span class="old-price">${formatPrice(product.list_price)}</span>`
                        : ""
                }

            </div>

            ${
                item.match_label
                    ? `
                        <span class="quick-product-match">
                            ${icon("sparkles")}
                            ${escapeHTML(item.match_label)}
                        </span>
                    `
                    : ""
            }

        </div>
    `;


    hydrateIcons(holder);
}


function prefillQuickForm() {

    const user = getCurrentUser();

    if (!user) return;


    const nameInput = $("quick-name");

    if (nameInput && !nameInput.value) {

        nameInput.value = [user.first_name, user.last_name]
            .filter(Boolean)
            .join(" ");
    }


    /*
       Hesapta kayitli adres varsa Hizli Al'da tekrar
       yazdirmiyoruz. Kullanici yine de bu siparise ozel
       farkli bir adres girmek isterse alani duzenleyebilir;
       degisiklik hesabina geri yazilmaz, sadece bu siparis
       icindir.
    */

    const addressInput = $("quick-address");

    if (addressInput && !addressInput.value && user.address) {

        addressInput.value = user.address;
    }
}


function validateQuickForm() {

    clearFieldErrors(quickForm);

    let valid = true;


    const name = $("quick-name");
    const phone = $("quick-phone");
    const address = $("quick-address");
    const card = $("quick-card");
    const expiry = $("quick-expiry");
    const cvc = $("quick-cvc");
    const terms = $("quick-terms");


    if ((name?.value.trim() || "").length < 3) {
        setFieldError(name, "Ad ve soyadını gir.");
        valid = false;
    }

    if ((phone?.value || "").replace(/\D/g, "").length < 10) {
        setFieldError(phone, "Telefon en az 10 haneli olmalı.");
        valid = false;
    }

    if ((address?.value.trim() || "").length < 10) {
        setFieldError(address, "Adresi biraz daha ayrıntılı yaz.");
        valid = false;
    }


    const digits = (card?.value || "").replace(/\D/g, "");

    if (digits.length < 13 || !isLuhnValid(digits)) {
        setFieldError(card, "Kart numarası geçersiz.");
        valid = false;
    }

    if (!isExpiryValid(expiry?.value)) {
        setFieldError(expiry, "AA/YY biçiminde geçerli bir tarih gir.");
        valid = false;
    }

    if ((cvc?.value || "").replace(/\D/g, "").length < 3) {
        setFieldError(cvc, "CVC 3 haneli.");
        valid = false;
    }


    if (terms && !terms.checked) {

        const error = document.createElement("span");

        error.className = "field-error";
        error.textContent = "Devam etmek için sözleşmeyi onayla.";

        terms
            .closest(".checkbox-field")
            ?.insertAdjacentElement("afterend", error);

        valid = false;
    }


    if (!valid) {
        quickForm
            ?.querySelector(".field.invalid input, .field.invalid textarea")
            ?.focus();
    }


    return valid;
}


async function submitQuickOrder() {

    if (quickState.submitting) return;

    if (quickState.mode === "cart") {

        if (!state.cart.length) return;

    } else if (!quickState.item) {

        return;
    }

    if (!validateQuickForm()) return;


    const button = $("quick-submit");

    quickState.submitting = true;

    setButtonLoading(button, true);


    try {

        if (quickState.mode === "cart") {

            await submitCartOrder();

        } else {

            await submitSingleQuickOrder(quickState.item);
        }


    } catch (error) {

        console.error("Sipariş oluşturulamadı:", error);

        showToast({
            title: "Sipariş oluşturulamadı",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });

    } finally {

        quickState.submitting = false;

        setButtonLoading(button, false);
    }
}


async function submitSingleQuickOrder(item) {

    /*
       Kart bilgisi SUNUCUYA GONDERILMIYOR. Dogrulama
       istemcide yapildi; bu uc yalnizca satin alma
       niyetini kaydediyor (ML icin en guclu sinyal).
    */

    const response = await apiFetch("/api/quick-order", {
        method: "POST",

        body: JSON.stringify({
            product_id: item.product.product_id,
            source: "quick_checkout",
            position: Number.isFinite(item.position)
                ? item.position
                : null,
            match_score: item.match_score ?? null,
            matched_style: item.matched_style ?? null,
        }),
    });


    /* Satın alınan ürün favorilerden düştü */

    if (isWishlisted(item.product.product_id)) {

        state.wishlist.delete(String(item.product.product_id));

        renderWishlistBadge();

        syncWishlistButtons(item.product.product_id, false);
    }


    showQuickSuccess(response);

    renderAiStatus();

    if (response?.toast) {
        showToast(response.toast);
    }
}


async function submitCartOrder() {

    const response = await apiFetch("/cart/checkout", {
        method: "POST",
        body: JSON.stringify({ source: "cart" }),
    });


    /* Satın alınan ürünler favorilerden düştü (backend
       zaten cikardi; burada sadece istemci durumunu ve
       kalp ikonlarini senkronize ediyoruz) */

    (response.items || []).forEach(item => {

        if (isWishlisted(item.product_id)) {

            state.wishlist.delete(String(item.product_id));

            syncWishlistButtons(item.product_id, false);
        }
    });

    renderWishlistBadge();


    state.cart = [];

    renderCartBadge();


    showQuickSuccess(response);

    renderAiStatus();

    if (response?.toast) {
        showToast(response.toast);
    }
}


function showQuickSuccess(response) {

    $("quick-body")?.classList.add("hidden");

    const success = $("quick-success");

    if (!success) return;


    const number = $("quick-order-number");

    if (number) {
        number.textContent = response?.order_number || "-";
    }


    const note = $("quick-success-note");

    if (note) {
        note.textContent =
            "Benzer parçalar akışında öne çıkarılacak.";
    }


    success.classList.remove("hidden");

    hydrateIcons(success);

    quickForm?.reset();
}


/* =========================================================
   WISHLIST ODAKLI ALT BAR
========================================================= */

function setupWishlistBar() {

    $("wishlist-bar-open")?.addEventListener("click", () => {

        if (!isUserLoggedIn()) {
            openAuth("Favorilerini görmek için giriş yap.");
            return;
        }

        openWishlistPanel();
    });


    $("wishlist-bar-buy")?.addEventListener("click", () => {

        /*
           Alt bardaki hizli al: favorilerin EN SON eklenen
           urununu satin almaya goturuyor. Sepet olmadigi
           icin "hepsini al" diye bir eylem yok; en yeni
           niyet en olasi niyet.
        */

        const latest = state.wishlistItems[0];

        if (latest?.product) {

            openQuickCheckout(
                { product: latest.product },
                { source: "wishlist" }
            );

            return;
        }


        /* Panel henüz yüklenmediyse aç, kullanıcı seçsin */
        openWishlistPanel();
    });
}


function renderWishlistBar() {

    const bar = $("wishlist-bar");

    if (!bar) return;


    const count = state.wishlist.size;

    if (!count || !isUserLoggedIn()) {

        bar.classList.add("hidden");

        return;
    }


    bar.classList.remove("hidden");


    const countNode = $("wishlist-bar-count");

    if (countNode) {
        countNode.textContent = `${count} favori`;
    }


    const hint = $("wishlist-bar-hint");

    if (hint) {

        const latest = state.wishlistItems[0]?.product;

        hint.textContent = latest
            ? productTitle(latest).slice(0, 42)
            : "Listeni aç";
    }


    /* Son üç favorinin küçük görselleri */

    const thumbs = $("wishlist-bar-thumbs");

    if (thumbs) {

        thumbs.innerHTML = state.wishlistItems
            .slice(0, 3)
            .map(entry => `
                <img
                    src="${escapeHTML(safeImage(entry.product?.image_url))}"
                    alt=""
                    loading="lazy"
                >
            `)
            .join("");
    }
}


/**
 * Alt barın küçük görselleri için favori listesini sessizce
 * yükler.
 *
 * renderWishlistPanel() ile aynı veriyi kullanıyor ama
 * çekmeceyi açmıyor: bar her zaman güncel kalmalı.
 */
async function refreshWishlistItems() {

    if (!isUserLoggedIn()) {

        state.wishlistItems = [];

        renderWishlistBar();

        return;
    }


    try {

        const items = await apiFetch("/wishlist");

        state.wishlistItems = Array.isArray(items) ? items : [];

        state.wishlist = new Set(
            state.wishlistItems.map(item => item.product_id)
        );

        renderWishlistBadge();


    } catch (error) {

        console.warn("Favori listesi alınamadı:", error);
    }


    renderWishlistBar();
}


/* =========================================================
   AI STİL ASİSTANI — SOHBET

   Klasik aramadan ayrı bir giriş noktası: header'ın sol
   üstündeki ✦ sembolü. Backend ucu /api/chat
   (backend/app/assistant.py).

   NEDEN AYRI BİR ŞEY
   ------------------
   Arama kutusu tek atışlıktır: yazarsın, sonuç gelir, biter.
   Kullanıcı "spor ayakkabı lazım" derse arama motorunun
   yapabileceği tek şey 700 sonuç göstermektir. Asistan ise
   bütçeyi sorabilir, cevabı hatırlar ve bir sonraki aramaya
   taşır.

   GEÇMİŞİ İSTEMCİ TUTUYOR
   -----------------------
   Backend oturum saklamıyor; her istekte konuşmanın tamamını
   gönderiyoruz. Sonucu: sunucuda temizlenecek durum yok,
   sekme kapanınca sohbet biter. Kalıcı geçmiş istenirse
   burası bir tabloya bağlanacak yer.

   KARTLAR MODELİN GÖRDÜĞÜ ÜRÜNLERDİR
   ----------------------------------
   products dizisi modelin uydurduğu bir liste değil; arama
   aracının döndürdüğü GERÇEK katalog satırları. Model olmayan
   bir ürünü anlatmaya kalkarsa kart olarak çıkmaz ve
   tutarsızlık anında görünür.
========================================================= */

const aiChatOverlay = $("ai-chat-overlay");
const aiChatLog = $("ai-chat-log");
const aiChatForm = $("ai-chat-form");
const aiChatInput = $("ai-chat-input");
const aiChatSend = $("ai-chat-send");
const aiChatSuggest = $("ai-chat-suggest");
const aiChatStatus = $("ai-chat-status");

const AI_CHAT_GREETING =
    "Merhaba! Ben WishNN'in stil asistanıyım. Ne aradığını " +
    "anlat; bütçeni, tarzını ya da gideceğin yeri söylemen " +
    "yeterli, gerisini ben bulayım.";


const aiChat = {
    open: false,
    sending: false,

    /* Açılış önerileri (/api/chat/starters) — bir kez
       yükleniyor, panel her açılışta yeniden istek atmıyor. */
    suggestions: null,
    suggestLoaded: false,

    /*
       Backend'e AYNEN gönderilen geçmiş: [{role, content}].
       Ürün kartları buraya girmiyor — model kendi önceki
       cevabında ürünlerden zaten bahsetmiş oluyor ve kart
       verisini tekrar göndermek boşuna token.
    */
    messages: [],
};


function setupAiChat() {

    $("open-ai-chat-btn")
        ?.addEventListener("click", openAiChat);

    $("mobile-ai-chat-btn")
        ?.addEventListener("click", () => {

            /* Mobil menü açıksa önce o kapanmalı */
            $("mobile-menu")?.classList.remove("open");

            openAiChat();
        });

    $("ai-chat-close")
        ?.addEventListener("click", closeAiChat);

    $("ai-chat-reset")
        ?.addEventListener("click", resetAiChat);


    /* Panelin dışına tıklama kapatır */
    aiChatOverlay?.addEventListener("click", event => {

        if (event.target === aiChatOverlay) {
            closeAiChat();
        }
    });


    document.addEventListener("keydown", event => {

        if (event.key === "Escape" && aiChat.open) {
            closeAiChat();
        }
    });


    aiChatForm?.addEventListener("submit", event => {

        event.preventDefault();

        sendAiChatMessage(aiChatInput?.value || "");
    });


    /*
       Enter gönderir, Shift+Enter satır atlar.

       textarea kullanmamızın sebebi uzun tarifler: "düğüne
       gidiyorum, lacivert bir takım arıyorum ama bütçem..."
       tek satırlık input'ta okunmuyor.
    */
    aiChatInput?.addEventListener("keydown", event => {

        if (event.key === "Enter" && !event.shiftKey) {

            event.preventDefault();

            sendAiChatMessage(aiChatInput.value);
        }
    });


    /* Yazdıkça yükseklik büyüsün (max-height CSS'te) */
    aiChatInput?.addEventListener("input", autoGrowChatInput);


    setupAiChatSuggest();


    aiChatLog?.addEventListener("click", handleAiChatLogClick);


    /*
       Kartlar div + role="button" olarak ciziliyor (icinde
       ayri bir kalp butonu var, ic ice buton gecersiz HTML).
       role="button" ve tabindex="0" vermek klavyeyle
       calisacagi SOZUNU veriyor; o sozu burada tutuyoruz.
       Space'te sayfa kaymasini da engellemek gerekiyor.
    */
    aiChatLog?.addEventListener("keydown", event => {

        if (event.key !== "Enter" && event.key !== " ") {
            return;
        }

        /*
           Kartin ICINDEKI gercek butonlar (kalp, kombin
           secimi) klavyeyi kendileri zaten isliyor. Onlari
           burada ele almazsak Space hem butonu hem karti
           tetikler ve urun modali istenmeden acilir.
        */
        if (event.target.closest("button")) {
            return;
        }

        const target =
            event.target.closest("[data-chat-product]");

        if (!target) return;

        event.preventDefault();

        openProduct(target.dataset.chatProduct);
    });
}


function autoGrowChatInput() {

    if (!aiChatInput) return;

    aiChatInput.style.height = "auto";

    aiChatInput.style.height =
        `${aiChatInput.scrollHeight}px`;
}


/* =========================================================
   AÇILIŞ ÖNERİLERİ: YILLIK TREND + GİDİLECEK YER

   NEDEN VAR
   Boş sohbette "ne yazsam" tereddüdü en büyük terk sebebi.
   Dört hazır cümle bunu kısmen çözüyordu ama hepsi aynı
   kalıptaydı. Burada iki farklı giriş kapısı var:

     TREND  — sezonun rengi/tarzı/kumaşı. "Ne moda?" sorusunun
              cevabını görüp o yönde arama başlatmak.
     YER    — "Nereye gidiyorsun?" Kıyafet seçimi çoğu zaman
              üründen değil OLAYDAN başlar (düğün, iş yemeği).

   İÇERİK SUNUCUDAN GELİYOR
   Trend öğeleri katalogda gerçekten kaç ürünle karşılandığına
   göre süzülüyor ve renk hedefleri aramanın kullandığı
   paletten geliyor. Burada ikinci bir liste tutmak, zamanla
   ikisinin ayrışması demekti.

   İSTEK BAŞARISIZ OLURSA blok boş kalır ve HTML'deki dört
   hazır cümle görünmeye devam eder.
========================================================= */

const AI_SUGGEST_GROUPS = [
    { key: "colors", label: "Renk", icon: "palette" },
    { key: "styles", label: "Tarz", icon: "sparkles" },
    { key: "fabrics", label: "Kumaş", icon: "layers" },
];


async function loadAiChatSuggestions() {

    if (!aiChatSuggest || aiChat.suggestLoaded) return;

    /* Bir kez denenir: başarısız olursa her açılışta tekrar
       istek atıp kullanıcıyı bekletmenin anlamı yok. */
    aiChat.suggestLoaded = true;

    try {
        const data = await apiGet("/api/chat/starters");

        aiChat.suggestions = data;

        renderAiChatSuggest();

    } catch (error) {

        console.error("Sohbet önerileri alınamadı:", error);
    }
}


function renderAiChatSuggestItem(item) {

    const swatch = item?.swatch
        ? `<span
               class="ai-suggest-swatch"
               style="background:${escapeHTML(item.swatch)};"
           ></span>`
        : "";

    /* Ürün sayısı GÖSTERİLİYOR: "bu sezon zeytin yeşili" deyip
       tıklayınca üç ürün çıkması hayal kırıklığı. Kaç seçenek
       olduğunu önceden bilmek beklentiyi doğru kuruyor. */
    const count = Number.isFinite(Number(item?.available))
        ? `<span class="ai-suggest-count">${Number(item.available)}</span>`
        : "";

    return `
        <button
            type="button"
            class="ai-suggest-chip"
            data-suggest-prompt="${escapeHTML(item?.prompt || "")}"
            title="${escapeHTML(item?.note || "")}"
        >
            ${swatch}
            <span>${escapeHTML(item?.label || "")}</span>
            ${count}
        </button>
    `;
}


function renderAiChatSuggest() {

    if (!aiChatSuggest) return;

    const data = aiChat.suggestions;

    if (!data) return;

    const trend = data.trend || {};

    const groups = AI_SUGGEST_GROUPS
        .map(group => {

            const items = Array.isArray(trend[group.key])
                ? trend[group.key]
                : [];

            if (!items.length) return "";

            return `
                <div class="ai-suggest-row">

                    <span class="ai-suggest-row-label">
                        ${icon(group.icon)}
                        ${escapeHTML(group.label)}
                    </span>

                    <div class="ai-suggest-chips">
                        ${items.map(renderAiChatSuggestItem).join("")}
                    </div>

                </div>
            `;
        })
        .join("");


    const destination = data.destination || {};

    const options = Array.isArray(destination.options)
        ? destination.options
        : [];

    /*
       IKISI DE KAPALI BASLIYOR.

       Onceki halde sezon seckisi acik duruyordu ve panelin
       ustunu tumuyle kaplıyordu: sohbete baslamak isteyen
       kullanici once bir icerik duvarini geciyordu. Simdi iki
       ayri kapi var, ikisi de kullanici isteyince aciliyor
       (bkz. setupAiChatSuggest icindeki toggle mantigi).
    */

    const trendPanel = groups
        ? `
            <section
                class="ai-suggest-block"
                data-suggest-panel="trend"
                hidden
            >

                <header class="ai-suggest-head">
                    <span class="ai-suggest-title">
                        ${escapeHTML(trend.title || "Sezon seçkisi")}
                    </span>
                    <span class="ai-suggest-note">
                        ${escapeHTML(trend.note || "")}
                    </span>
                </header>

                ${groups}

            </section>
        `
        : "";

    const destinationPanel = `
        <section
            class="ai-suggest-block"
            data-suggest-panel="destination"
            hidden
        >

            <div class="ai-suggest-destination">

                <div class="ai-suggest-chips">
                    ${
                        options
                            .map(option => `
                                <button
                                    type="button"
                                    class="ai-suggest-chip"
                                    data-suggest-prompt="${escapeHTML(option.prompt || "")}"
                                >
                                    <span>${escapeHTML(option.label || "")}</span>
                                </button>
                            `)
                            .join("")
                    }
                </div>

                <form class="ai-suggest-place-form" data-destination-form>

                    <input
                        type="text"
                        class="ai-suggest-place-input"
                        maxlength="80"
                        autocomplete="off"
                        placeholder="${escapeHTML(destination.placeholder || "")}"
                        aria-label="Gideceğin yer"
                    >

                    <button type="submit" class="ai-suggest-place-send">
                        Sor
                    </button>

                </form>

            </div>

        </section>
    `;


    const trendTab = groups
        ? `
            <button
                type="button"
                class="ai-suggest-toggle"
                data-suggest-toggle="trend"
                aria-expanded="false"
            >
                ${icon("sparkles")}
                <span>Moda &amp; sezon</span>
            </button>
        `
        : "";

    const destinationTab = `
        <button
            type="button"
            class="ai-suggest-toggle"
            data-suggest-toggle="destination"
            aria-expanded="false"
        >
            ${icon("map-pin")}
            <span>${escapeHTML(destination.hint || "Nereye gidiyorsun?")}</span>
        </button>
    `;


    aiChatSuggest.innerHTML = `
        <div class="ai-suggest-tabs">
            ${trendTab}
            ${destinationTab}
        </div>

        ${trendPanel}
        ${destinationPanel}
    `;

    hydrateIcons(aiChatSuggest);
}


/**
 * Açık duran "Moda & sezon" / "Nereye gidiyorsun?" panelini
 * kapatır. Tuşların kendisine dokunmaz — onlar sohbet
 * boyunca yerinde kalıyor.
 */
function collapseAiChatSuggestPanels() {

    if (!aiChatSuggest) return;

    aiChatSuggest
        .querySelectorAll("[data-suggest-panel]")
        .forEach(panel => {
            panel.hidden = true;
        });

    aiChatSuggest
        .querySelectorAll("[data-suggest-toggle]")
        .forEach(toggle => {
            toggle.setAttribute("aria-expanded", "false");
        });
}


/**
 * Serbest yazılan yerden sohbet mesajı kurar.
 *
 * Kalıp sunucudan geliyor ({place} içeren bir cümle): iki
 * yerde iki farklı cümle olsa, seçilen yer ile yazılan yer
 * farklı sorular üretirdi.
 */
function buildDestinationPrompt(place) {

    const cleaned = String(place || "").trim();

    if (!cleaned) return "";

    const template =
        aiChat.suggestions?.destination?.prompt_template ||
        "{place} için ne giyebilirim? Bana uygun parçalar önerir misin?";

    /* İlk harf büyük: cümle başı gibi okunsun. */
    const shaped =
        cleaned.charAt(0).toLocaleUpperCase("tr-TR") + cleaned.slice(1);

    return template.replace("{place}", shaped);
}


function setupAiChatSuggest() {

    if (!aiChatSuggest) return;

    aiChatSuggest.addEventListener("click", event => {

        const toggle =
            event.target.closest("[data-suggest-toggle]");

        if (toggle) {

            const key = toggle.dataset.suggestToggle;

            const panel = aiChatSuggest.querySelector(
                `[data-suggest-panel="${key}"]`
            );

            if (!panel) return;

            const willOpen = panel.hidden;

            /* Akordiyon: panel dar, ikisi birden acikken
               kullanici kaydirmadan hicbirini goremiyor. */
            collapseAiChatSuggestPanels();

            panel.hidden = !willOpen;

            toggle.setAttribute(
                "aria-expanded",
                willOpen ? "true" : "false",
            );

            if (willOpen && key === "destination") {
                panel
                    .querySelector(".ai-suggest-place-input")
                    ?.focus();
            }

            return;
        }


        const chip = event.target.closest("[data-suggest-prompt]");

        if (!chip) return;

        sendAiChatMessage(chip.dataset.suggestPrompt || "");
    });


    aiChatSuggest.addEventListener("submit", event => {

        const form = event.target.closest("[data-destination-form]");

        if (!form) return;

        event.preventDefault();

        const input = form.querySelector(".ai-suggest-place-input");

        const prompt = buildDestinationPrompt(input?.value);

        if (!prompt) {
            input?.focus();
            return;
        }

        if (input) input.value = "";

        sendAiChatMessage(prompt);
    });
}


function openAiChat() {

    if (!aiChatOverlay) return;

    aiChatOverlay.classList.add("open");

    aiChat.open = true;

    /*
       body scroll'u BILEREK kilitlenmiyor. Sitedeki hiçbir
       katman (sepet, favoriler, ürün modalı, özelleştir)
       kilitlemiyor; burada kilitlemek iki sorun doğuruyordu:

         1. Sohbetten bir karta basınca ürün modalı üste
            açılıyor. Sohbet o sırada kapatılırsa overflow
            sıfırlanıyor ve modalın arkası kaymaya başlıyor —
            modal kendi kilidini yönetmiyor.
         2. İki katman aynı global stili yazarsa hangisinin
            son sözü söylediği çağrı sırasına bağlı kalıyor.

       Panelin kendi içi zaten kayıyor (.ai-chat-log).
    */

    /* İlk açılışta karşılama mesajı */
    if (!aiChat.messages.length && !aiChatLog?.children.length) {

        appendAiChatMessage({
            role: "assistant",
            content: AI_CHAT_GREETING,
        });
    }


    /* Öneriler panel açılınca yükleniyor: sayfa yüklenirken
       istek atmak, sohbeti hiç açmayan kullanıcı için boşuna
       bir tur demek. */
    loadAiChatSuggestions();

    setTimeout(() => aiChatInput?.focus(), 350);
}


function closeAiChat() {

    if (!aiChatOverlay) return;

    aiChatOverlay.classList.remove("open");

    aiChat.open = false;
}


function resetAiChat() {

    aiChat.messages = [];

    if (aiChatLog) {
        aiChatLog.innerHTML = "";
    }

    /* Iki giris kapisi hic gizlenmiyor (bkz. index.html
       #ai-chat-suggest), sifirlamada da acilacak bir sey yok.
       Yalnizca acik panel varsa kapatiyoruz. */
    collapseAiChatSuggestPanels();

    setAiChatStatus("Katalogdan gerçek ürünler önerir");

    appendAiChatMessage({
        role: "assistant",
        content: AI_CHAT_GREETING,
    });

    aiChatInput?.focus();
}


function setAiChatStatus(text) {

    if (aiChatStatus) {
        aiChatStatus.textContent = text;
    }
}


async function sendAiChatMessage(rawText) {

    const text = String(rawText || "").trim();

    /*
       Aynı anda iki istek gitmemeli: ikincisi birincinin
       cevabını içermeyen bir geçmişle gider ve model kendi
       söylediğini görmeden cevap yazar.
    */
    if (!text || aiChat.sending) return;


    /*
       Iki giris kapisi GIZLENMIYOR: sohbet boyunca yerinde
       kaliyor ki kullanici ikinci, ucuncu soruyu da oradan
       baslatabilsin. Yalnizca acik duran panel kapaniyor —
       secim yapildi, listeyi acik tutmanin isi bitti.
    */
    collapseAiChatSuggestPanels();


    appendAiChatMessage({
        role: "user",
        content: text,
    });

    aiChat.messages.push({
        role: "user",
        content: text,
    });


    if (aiChatInput) {
        aiChatInput.value = "";
        autoGrowChatInput();
    }


    setAiChatSending(true);

    const typing = appendAiChatTyping();


    try {

        const data = await apiFetch("/api/chat", {
            method: "POST",
            body: JSON.stringify({
                messages: aiChat.messages,
            }),
        });

        typing?.remove();


        const reply = String(data?.reply || "").trim();

        const products = Array.isArray(data?.products)
            ? data.products
            : [];


        appendAiChatMessage({
            role: "assistant",
            content: reply,
            products,
        });

        /*
           Geçmişe YALNIZCA metin giriyor. Kartlar ekranda
           duruyor ama modele geri gönderilmiyor: model zaten
           kendi arama sonucunu görmüştü.

           Boş cevap geçmişe GİRMEZ: backend ChatMessage
           content'i min_length=1 doğruluyor, boş bir satır
           bir sonraki isteği 422 ile düşürür ve sohbetin
           tamamı kilitlenirdi.
        */
        if (reply) {

            aiChat.messages.push({
                role: "assistant",
                content: reply,
            });

        } else {

            /* Cevapsız tur: kullanıcı mesajını da bırakma */
            aiChat.messages.pop();
        }


        setAiChatStatus(
            (data?.tool_calls || []).includes("search_catalog")
                ? "Katalogda arama yaptı"
                : "Katalogdan gerçek ürünler önerir"
        );


    } catch (error) {

        typing?.remove();

        console.error("Sohbet hatası:", error);

        appendAiChatMessage({
            role: "assistant",
            error: true,
            content:
                error?.message ||
                "Asistana ulaşamadım. Birazdan tekrar dene.",
        });

        /*
           BAŞARISIZ TUR GEÇMİŞTEN ÇIKARILIYOR.

           Kullanıcının mesajı gönderildi ama cevap gelmedi.
           Geçmişte cevapsız bir kullanıcı mesajı bırakırsak
           bir sonraki istekte model iki kullanıcı mesajını
           arka arkaya görür ve ilkini görmezden gelir.
           Kullanıcı tekrar yazınca temiz bir tur başlasın.
        */
        aiChat.messages.pop();

    } finally {

        setAiChatSending(false);
    }
}


function setAiChatSending(sending) {

    aiChat.sending = sending;

    if (aiChatSend) {
        aiChatSend.disabled = sending;
    }

    if (aiChatInput) {
        aiChatInput.disabled = sending;
    }

    if (!sending) {
        aiChatInput?.focus();
    }
}


function appendAiChatTyping() {

    if (!aiChatLog) return null;

    const wrapper = document.createElement("div");

    wrapper.className = "ai-chat-msg assistant";

    wrapper.innerHTML = `
        <div class="ai-chat-typing">
            <span></span><span></span><span></span>
        </div>
    `;

    aiChatLog.appendChild(wrapper);

    scrollAiChatToBottom();

    return wrapper;
}


function appendAiChatMessage({
    role,
    content,
    products = [],
    error = false,
}) {

    if (!aiChatLog) return;


    const wrapper = document.createElement("div");

    wrapper.className =
        `ai-chat-msg ${role}${error ? " error" : ""}`;


    const parts = [];

    if (content) {

        parts.push(`
            <div class="ai-chat-bubble">${formatAiChatText(content)}</div>
        `);
    }

    if (products.length) {

        parts.push(`
            <div class="ai-chat-products">
                ${products.map(renderAiChatProduct).join("")}
            </div>
        `);

        /*
           GARDIROP IPUCUSU.

           Eskiden burada "kombin yapmak istedigin parcalari
           isaretle" yazisi ve iki secim olunca beliren bir
           kaydet seridi vardi. Kaldirildi: kombin artik tek
           bir parcadan kuruluyor (karttaki "Kombinle"
           dugmesi -> /api/outfit) ve kullanicidan liste
           icinden esleme yapmasi beklenmiyor.

           Ipucu KALIYOR ama isi degisti: dugmenin ne
           yaptigini soyluyor. Olculdu, ilk surumde ipucu
           olmadan bos daireye kimse basmamisti; adi konmamis
           bir dugme yine gorunmez olurdu.
        */
        parts.push(`
            <div class="ai-chat-look-hint">
                <i class="fa-solid fa-wand-magic-sparkles"></i>
                Bir parçada <strong>Kombinle</strong>'ye bas —
                altını ve ayakkabısını ben seçeyim
            </div>
        `);
    }

    wrapper.innerHTML = parts.join("");

    /*
       Urun verisini DOM'a degil buraya baglıyoruz: kombin
       kaydederken product_id yeterli ama slot tahmini icin
       kategori de gerekebiliyor ve kartta yapilandirilmis
       veri yok. aiChat.messages'a KOYMUYORUZ — o dizi
       backend'e aynen gidiyor, fazladan alan 422 uretir.
    */
    if (products.length) {
        wrapper._chatProducts = products;
    }

    aiChatLog.appendChild(wrapper);

    scrollAiChatToBottom();
}


/**
 * Asistan cevabını güvenli biçimde HTML'e çevirir.
 *
 * NEDEN GEREKLİ
 * Sistem talimatı modelden düz metin istiyor ama modeller
 * markdown'a alışkındır ve "**Calvin Klein**" yazması sık.
 * Ham bırakılırsa kullanıcı yıldızları görür.
 *
 * SIRALAMA ÖNEMLİ: ÖNCE escapeHTML, SONRA kalın dönüşümü.
 * Tersi olursa modelin ürettiği metin HTML olarak yorumlanır
 * — model çıktısı da sonuçta güvenilmeyen girdi. Escape'ten
 * sonra metinde `<` kalmadığı için buradaki <strong>
 * enjeksiyon yüzeyi açmıyor.
 *
 * Yalnızca kalın destekleniyor: sohbet balonunda başlık,
 * liste ve tablonun işi yok — sistem talimatı ürünleri madde
 * madde saymayı zaten yasaklıyor.
 */
function formatAiChatText(text) {

    return escapeHTML(text)
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}


function renderAiChatProduct(product) {

    const id = String(product?.product_id || "");

    const liked = isWishlisted(id);

    /*
       FİYAT SUNUCUDAN GELİYORSA ONU KULLAN.

       price_try, asistanın bütçe filtresinde kullandığı kurla
       hesaplanmış TL fiyatı. Burada kendi kurumuzla yeniden
       çevirirsek (formatPrice -> toTry) ve /exchange-rate
       alınamamışsa sabit yedeğe (47.88) düşeriz: asistan
       "3000 TL altında" der, kartta 3100 TL yazar. Aynı sayıyı
       göstermek bu çelişkiyi imkânsız kılıyor.

       Eski alan (USD price) yedek olarak duruyor: sohbet dışı
       çağrılar ve eski cevaplar bozulmasın.
    */
    const priceTry = Number(product?.price_try);

    const price = Number.isFinite(priceTry) && priceTry > 0
        ? formatTry(priceTry)
        : (hasPrice(product) ? formatPrice(product.price) : "Fiyat yok");

    const rating = product?.rating
        ? `★ ${Number(product.rating).toFixed(1)}`
        : "";

    /*
       data-chat-product taşıyan sarmalayıcı bir DIV, buton
       değil: içinde ayrı bir kalp butonu var ve iç içe
       buton geçersiz HTML.
    */
    return `
        <div
            class="ai-chat-product"
            data-chat-product="${escapeHTML(id)}"
            role="button"
            tabindex="0"
        >
            <img
                class="ai-chat-product-image"
                src="${escapeHTML(safeImage(product?.image_url))}"
                alt=""
                loading="lazy"
            >

            <div class="ai-chat-product-body">

                ${
                    product?.brand
                        ? `<span class="ai-chat-product-brand">${escapeHTML(product.brand)}</span>`
                        : ""
                }

                <p class="ai-chat-product-title">
                    ${escapeHTML(productTitle(product))}
                </p>

                <div class="ai-chat-product-meta">
                    <span class="ai-chat-product-price">${escapeHTML(price)}</span>
                    <span class="ai-chat-product-rating">${escapeHTML(rating)}</span>
                </div>

            </div>

            <button
                type="button"
                class="ai-chat-product-like${liked ? " liked" : ""}"
                data-chat-like="${escapeHTML(id)}"
                aria-label="${liked ? "Favorilerden çıkar" : "Favorilere ekle"}"
            >
                <i class="fa-${liked ? "solid" : "regular"} fa-heart"></i>
            </button>

            <!-- KOMBINLE — tek dokunus.

                 Burada eskiden bir SECIM KUTUSU vardi:
                 kullanicidan listeden iki parca isaretlemesi
                 bekleniyordu. Ama asistan tek kategori
                 donduruyor (tisort arandiginda tisort), yani
                 isaretlenen iki kart iki tisort oluyordu ve
                 ortaya kombin degil ayni seyin iki adedi
                 cikiyordu.

                 Simdi eksik yuvalari (alt, ayakkabi, dis
                 giyim) sistem ariyor: /api/outfit. Kullanici
                 yalnizca "evet, ekle" diyor. -->
            <button
                type="button"
                class="ai-chat-product-outfit"
                data-chat-outfit="${escapeHTML(id)}"
                aria-label="Bu parçayla kombin kur"
                title="Bu parçayla kombin kur"
            >
                <i class="fa-solid fa-wand-magic-sparkles"></i>
                <span>Kombinle</span>
            </button>

        </div>
    `;
}


function handleAiChatLogClick(event) {

    /* Kalp önce kontrol edilmeli: karta da gömülü */
    const likeButton =
        event.target.closest("[data-chat-like]");

    if (likeButton) {

        event.stopPropagation();

        toggleAiChatLike(likeButton);

        return;
    }


    /* KOMBINLE — kalpten sonra, karttan ONCE: o da karta
       gomulu ve karta basmak urun detayini aciyor. */
    const outfitButton =
        event.target.closest("[data-chat-outfit]");

    if (outfitButton) {

        event.stopPropagation();

        requestChatOutfit(outfitButton);

        return;
    }


    /* Onerideki bir yuvanin alternatifi — secimi degistirir */
    const optionButton =
        event.target.closest("[data-outfit-option]");

    if (optionButton) {

        event.stopPropagation();

        selectOutfitOption(optionButton);

        return;
    }


    const outfitSave =
        event.target.closest("[data-outfit-save]");

    if (outfitSave) {

        event.stopPropagation();

        saveOutfitFromChat(outfitSave);

        return;
    }


    const outfitCancel =
        event.target.closest("[data-outfit-cancel]");

    if (outfitCancel) {

        event.stopPropagation();

        dismissOutfitProposal(outfitCancel);

        return;
    }


    const card =
        event.target.closest("[data-chat-product]");

    if (!card) return;


    /*
       Ürün detayı modalı panelin ÜZERİNDE açılıyor
       (z-index 4000 > 3500). Sohbet kapanmıyor: kullanıcı
       modalı kapatınca konuşmaya kaldığı yerden devam etsin.
    */
    openProduct(card.dataset.chatProduct);
}


async function toggleAiChatLike(button) {

    const productId = button.dataset.chatLike || "";

    if (!productId) return;


    if (!isUserLoggedIn()) {

        /*
           Misafir kalbe bastı. Mevcut bekleyen-etkileşim
           mekanizması giriş sonrası işlemi tamamlıyor
           (bkz. resumePendingInteraction).
        */
        closeAiChat();

        requestLoginForInteraction(
            {
                type: "LIKE",
                productId,
                source: "chat",
            },
            "Favorilere eklemek için giriş yapmalısın."
        );

        return;
    }


    const liked = isWishlisted(productId);


    try {

        if (liked) {

            await removeFromWishlist(productId, {
                source: "chat",
            });

        } else {

            await addToWishlist(productId, {
                source: "chat",
            });
        }


        /*
           Sohbetteki KOPYALARIN HEPSİ güncelleniyor: aynı
           ürün konuşma boyunca birden fazla cevapta çıkmış
           olabilir ve yalnızca tıklananı boyamak tutarsız
           görünürdü.
        */
        syncAiChatHearts(productId, !liked);

        /* Sitenin geri kalanındaki kalpler de aynı üründe */
        syncWishlistButtons(productId, !liked);


    } catch (error) {

        console.error("Favori güncellenemedi:", error);

        showToast({
            title: "Favori güncellenemedi",
            message: error?.message || "Tekrar dene.",
            tone: "neutral",
        });
    }
}


/* ---------------------------------------------------------
   SOHBETTEN KOMBIN KURMA

   Asistan bir "kombin" kavrami dondurmuyor: [SHOW:]
   direktifiyle duz, gruplanmamis bir urun listesi veriyor.
   Hangi parcalarin BIRLIKTE bir kombin oldugunu kullanici
   seciyor; bu yuzden burada secim durumu tutuluyor ve
   asistan/prompt tarafina hic dokunulmuyor.

   Secim, mesaj balonunun KENDI icinde: iki ayri cevaptaki
   kartlar tek kombine karismasin.
--------------------------------------------------------- */

/* ---------------------------------------------------------
   SOHBETTEN KOMBIN

   AKIS
     1. Kullanici bir urun kartinda "Kombinle"ye basar.
     2. /api/outfit eksik yuvalari doldurur (alt, ayakkabi,
        dis giyim) ve bir oneri doner.
     3. Sohbete oneri balonu dusuyor: her yuva icin secili
        bir parca ve tek dokunusla degistirilebilen
        alternatifler.
     4. Kullanici "GARDIROBA EKLE" derse kombin kaydedilir.

   NEDEN BOYLE
   Eski akista kombin kurmak kullanicinin isiydi: liste
   icinden iki karti isaretliyordu. Ama asistan tek kategori
   donduruyor — "tisort" arandiginda tisort — yani
   isaretlenen iki kart iki tisort oluyordu. Ortaya kombin
   degil ayni seyin iki adedi cikiyordu.

   ONERI MODELDEN GECMIYOR (bkz. backend/app/outfit.py):
   karta basildigi anda cevap gelmesi gerekiyor ve Gemini
   ucretsiz katmani dakikada 5 istek veriyor.
--------------------------------------------------------- */

async function requestChatOutfit(button) {

    const productId = button.dataset.chatOutfit || "";

    if (!productId) return;


    /*
       Ayni karta iki kez basilirsa iki oneri balonu duser.
       Dugme istek boyunca kilitleniyor.
    */
    if (button.disabled) return;

    button.disabled = true;

    button.classList.add("loading");


    const typing = appendAiChatTyping();


    try {

        const data = await apiGet(
            `/api/outfit/${encodeURIComponent(productId)}`
        );

        typing?.remove();

        appendAiChatOutfit(data);


    } catch (error) {

        typing?.remove();

        console.error("Kombin onerisi alinamadi:", error);

        /*
           TEKNIK METIN KULLANICIYA GOSTERILMIYOR. apiGet
           hata govdesini ayiklamiyor, mesaji "404 Not Found"
           gibi geliyor (bkz. apiGet — apiFetch'in aksine
           extractApiError cagirmiyor). Kullaniciya bunu
           gostermek bilgi vermiyor; konsola dusen satir
           gelistirici icin yeterli.
        */
        appendAiChatMessage({
            role: "assistant",
            error: true,
            content:
                "Kombin önerisini hazırlayamadım. Tekrar dener misin?",
        });

    } finally {

        button.disabled = false;

        button.classList.remove("loading");
    }
}


/**
 * Kombin onerisini sohbete basar.
 *
 * Oneri GECMISE GIRMIYOR (aiChat.messages'a eklenmiyor):
 * o dizi backend'e aynen gidiyor ve modelin kendi
 * uretmedigi bir metni "kendi cevabi" olarak gormesi,
 * sonraki turda ondan alintı yapmasına yol aciyor.
 */
function appendAiChatOutfit(data) {

    if (!aiChatLog) return;


    const slots = Array.isArray(data?.slots) ? data.slots : [];

    const wrapper = document.createElement("div");

    wrapper.className = "ai-chat-msg assistant";


    /* Tamamlayici bulunamadi: durust bir cevap ve kaydet
       dugmesi YOK. Tek parcali bir "kombin" sunucu
       tarafinda da gecersiz (min_length=2). */
    if (!slots.length) {

        wrapper.innerHTML = `
            <div class="ai-chat-bubble">
                ${formatAiChatText(
                    data?.reason ||
                    "Bu parçaya uygun tamamlayıcı bulamadım."
                )}
            </div>
        `;

        aiChatLog.appendChild(wrapper);

        scrollAiChatToBottom();

        return;
    }


    const question =
        `${data.reason} Kombin olarak gardıroba ekleyeyim mi?`;


    wrapper.innerHTML = `
        <div class="ai-chat-bubble">${formatAiChatText(question)}</div>

        <div
            class="ai-chat-outfit"
            data-outfit
            data-outfit-seed="${escapeHTML(String(data.seed.product_id))}"
            data-outfit-title="${escapeHTML(String(data.title || "Kombin"))}"
        >
            ${renderOutfitSeed(data.seed, data.seed_slot)}

            ${slots.map(renderOutfitSlot).join("")}

            <div class="ai-chat-outfit-actions">

                <button
                    type="button"
                    class="ai-chat-outfit-save"
                    data-outfit-save
                >
                    <i class="fa-solid fa-check"></i>
                    GARDIROBA EKLE
                </button>

                <button
                    type="button"
                    class="ai-chat-outfit-cancel"
                    data-outfit-cancel
                >
                    Vazgeç
                </button>

            </div>

            <p class="ai-chat-outfit-note">
                Parçalara dokunarak değiştirebilirsin.
            </p>

        </div>
    `;


    /*
       Urun verisi DOM'a degil buraya baglanıyor: kaydederken
       product_id yeterli ama kombin adini ve yuvalari
       uretirken tam kayit isimize yariyor. Kartlardaki
       veriyle ayni gerekce (bkz. appendAiChatMessage).
    */
    wrapper._outfit = data;

    aiChatLog.appendChild(wrapper);

    /* Not satirini bastan dogru yaz: her yuvanin ilk adayi
       secili geliyor, sayiyi elle yazmak iki yerde
       tutulacak bir sayi olurdu. */
    refreshOutfitActions(wrapper.querySelector("[data-outfit]"));

    scrollAiChatToBottom();
}


/**
 * Kullanicinin sectigi parca — onerinin cikis noktasi.
 *
 * Degistirilemiyor ve secimi kaldirilamiyor: kombin bu
 * parcanin ETRAFINDA kuruldu. Kullanici baska bir parcadan
 * baslamak isterse onun kartindaki "Kombinle"ye basar.
 */
function renderOutfitSeed(seed, seedSlot) {

    const label =
        OUTFIT_SLOT_LABELS[seedSlot] || "Seçtiğin parça";

    return `
        <div class="ai-chat-outfit-slot seed">

            <div class="ai-chat-outfit-slot-head">
                <span class="ai-chat-outfit-slot-label">
                    ${escapeHTML(label)}
                </span>
                <span class="ai-chat-outfit-slot-color">
                    seçtiğin parça
                </span>
            </div>

            <div class="ai-chat-outfit-options">
                ${renderOutfitOption(seed, true, false)}
            </div>

        </div>
    `;
}


/* Yuva anahtari -> baslik. Sunucu da label gonderiyor ama
   tohum parcasinin yuvasi icin (seed_slot) etiket gelmiyor:
   o bir oneri degil, kullanicinin kendi secimi. */
const OUTFIT_SLOT_LABELS = {
    ust: "Üst",
    alt: "Alt",
    dis_giyim: "Dış giyim",
    ayakkabi: "Ayakkabı",
    aksesuar: "Aksesuar",
};


function renderOutfitSlot(slot) {

    const options = Array.isArray(slot?.options) ? slot.options : [];

    if (!options.length) return "";


    /* Renk gerekcesi: "neden lacivert bir pantolon?"
       sorusunun cevabi kullanicinin gozunun onunde dursun. */
    const color = slot.color_label
        ? `${slot.color_label} tonlar`
        : "";

    return `
        <div
            class="ai-chat-outfit-slot"
            data-outfit-slot="${escapeHTML(String(slot.slot))}"
        >

            <div class="ai-chat-outfit-slot-head">
                <span class="ai-chat-outfit-slot-label">
                    ${escapeHTML(String(slot.label || slot.slot))}
                </span>
                <span class="ai-chat-outfit-slot-color">
                    ${escapeHTML(color)}
                </span>
            </div>

            <div class="ai-chat-outfit-options">
                ${
                    options
                        .map((option, index) =>
                            renderOutfitOption(
                                option.product,
                                index === 0,
                                true
                            )
                        )
                        .join("")
                }
            </div>

        </div>
    `;
}


/**
 * Tek bir aday.
 *
 * selectable=false ise tohum parcasi: gorunuyor ama
 * secimi degistirilemiyor.
 */
function renderOutfitOption(product, selected, selectable) {

    const id = String(product?.product_id || "");

    const priceTry = Number(product?.price_try);

    /* Fiyat sunucudan geliyorsa onu kullan — sohbet
       kartlariyla ayni gerekce (bkz. renderAiChatProduct). */
    const price = Number.isFinite(priceTry) && priceTry > 0
        ? formatTry(priceTry)
        : (hasPrice(product) ? formatPrice(product.price) : "");

    const attributes = selectable
        ? `data-outfit-option="${escapeHTML(id)}"
           aria-pressed="${selected ? "true" : "false"}"`
        : `data-outfit-fixed="${escapeHTML(id)}" disabled`;

    return `
        <button
            type="button"
            class="ai-chat-outfit-option${selected ? " selected" : ""}"
            ${attributes}
        >
            <img
                class="ai-chat-outfit-option-image"
                src="${escapeHTML(safeImage(product?.image_url))}"
                alt=""
                loading="lazy"
            >

            <span class="ai-chat-outfit-option-title">
                ${escapeHTML(productTitle(product))}
            </span>

            <span class="ai-chat-outfit-option-price">
                ${escapeHTML(price)}
            </span>

            <i class="ai-chat-outfit-option-tick fa-solid fa-check"></i>
        </button>
    `;
}


/**
 * Bir yuvada baska adayi secer.
 *
 * SECILI OLANA TEKRAR BASMAK yuvayi bosaltiyor: kullanici
 * "ayakkabi istemiyorum, sadece ust + alt" diyebilmeli.
 * Bos yuva kaydedilirken atlanıyor.
 */
function selectOutfitOption(button) {

    const slot = button.closest("[data-outfit-slot]");

    if (!slot) return;


    const wasSelected = button.classList.contains("selected");

    slot.querySelectorAll("[data-outfit-option]").forEach(option => {
        option.classList.remove("selected");
        option.setAttribute("aria-pressed", "false");
    });

    if (!wasSelected) {
        button.classList.add("selected");
        button.setAttribute("aria-pressed", "true");
    }

    refreshOutfitActions(button.closest("[data-outfit]"));
}


/**
 * Kaydet dugmesinin durumu.
 *
 * Sunucu en az IKI parca istiyor (SaveLookRequest
 * min_length=2) ve tohum her zaman icinde. Yani en az bir
 * yuva secili olmali; hepsi bosaltilirsa dugme kapaniyor
 * ve kullanici 422 yerine sebebini goruyor.
 */
function refreshOutfitActions(root) {

    if (!root) return;


    const chosen = root.querySelectorAll(
        "[data-outfit-option].selected"
    ).length;

    const save = root.querySelector("[data-outfit-save]");

    if (!save) return;

    save.disabled = chosen < 1;

    const note = root.querySelector(".ai-chat-outfit-note");

    if (note) {

        note.textContent = chosen
            ? `${chosen + 1} parça seçili — parçalara dokunarak değiştirebilirsin.`
            : "En az bir tamamlayıcı parça seçmelisin.";
    }
}


/**
 * Oneriyi kombin olarak kaydeder.
 *
 * KULLANICIYA AD SORULMUYOR. Eski akista bir window.prompt
 * aciliyordu; akisin en can sikici adimi oydu ve mobilde
 * prompt bazi tarayicilarda hic gorunmuyor. Ad sunucudan
 * geliyor (outfit._title), kullanici gardiroptan
 * degistirebiliyor.
 */
async function saveOutfitFromChat(button) {

    const root = button.closest("[data-outfit]");

    if (!root) return;


    if (!isUserLoggedIn()) {

        closeAiChat();

        openAuth("Kombin kaydetmek için giriş yapmalısın.");

        return;
    }


    /*
       Tohum HER ZAMAN ilk parca: kombin onun etrafinda
       kuruldu, listede de basta gorunmeli. Sunucu sirayi
       koruyor (position alani).
    */
    const items = [
        {
            product_id: root.dataset.outfitSeed,
            slot: null,
        },
    ];

    root.querySelectorAll("[data-outfit-slot]").forEach(slot => {

        const selected = slot.querySelector(
            "[data-outfit-option].selected"
        );

        if (!selected) return;

        items.push({
            product_id: selected.dataset.outfitOption,

            /*
               Yuvayi ISTEMCI gonderiyor cunku burada kesin
               biliniyor: parca o yuva icin arandi. Sunucu
               bos gelirse kategoriden tahmin ediyor
               (outfit.guess_slot) — tahmine gerek yok.
            */
            slot: slot.dataset.outfitSlot || null,
        });
    });


    if (items.length < 2) return;


    const title = root.dataset.outfitTitle || "Kombin";

    button.disabled = true;


    try {

        await saveLook(title, items, { source: "chat" });


        /*
           Oneri KILITLENIYOR: kaydedildi, ayni onerinin
           ikinci kez kaydedilmesi kullanicinin istedigi sey
           degil. Blok ekranda kaliyor ki ne kaydedildigi
           gorunsun.
        */
        root.classList.add("saved");

        root.querySelectorAll("button").forEach(item => {
            item.disabled = true;
        });

        const actions = root.querySelector(".ai-chat-outfit-actions");

        if (actions) {

            actions.innerHTML = `
                <span class="ai-chat-outfit-done">
                    <i class="fa-solid fa-circle-check"></i>
                    Gardıroba eklendi
                </span>
            `;
        }

        const note = root.querySelector(".ai-chat-outfit-note");

        if (note) {
            note.textContent =
                `"${title}" — ${items.length} parça. ` +
                "Gardıroptan parçalarını değiştirebilirsin.";
        }

        showToast({
            title: "Kombin gardıroba eklendi",
            message:
                `"${title}" — ${items.length} parça. ` +
                "Gardıroptan parçalarını değiştirebilirsin.",
            tone: "success",
        });


    } catch (error) {

        console.error("Kombin kaydedilemedi:", error);

        button.disabled = false;

        showToast({
            title: "Kombin kaydedilemedi",
            message: error.message || "Tekrar dener misin?",
            tone: "error",
        });
    }
}


/**
 * Oneriyi kapatir.
 *
 * Mesaj akistan SILINMIYOR, yerine tek satirlik bir iz
 * kaliyor: sohbet gecmisinde bosluk olmasin ve kullanici
 * ne oldugunu hatirlasin.
 */
function dismissOutfitProposal(button) {

    const wrapper = button.closest(".ai-chat-msg");

    if (!wrapper) return;

    wrapper.innerHTML = `
        <div class="ai-chat-bubble muted">
            Kombin önerisini kapattım. İstediğin zaman bir parçada
            <strong>Kombinle</strong>'ye basabilirsin.
        </div>
    `;
}


function syncAiChatHearts(productId, liked) {

    aiChatLog
        ?.querySelectorAll(
            `[data-chat-like="${cssEscape(productId)}"]`
        )
        .forEach(button => {

            button.classList.toggle("liked", liked);

            button.setAttribute(
                "aria-label",
                liked
                    ? "Favorilerden çıkar"
                    : "Favorilere ekle"
            );

            const glyph = button.querySelector("i");

            if (glyph) {

                glyph.className =
                    `fa-${liked ? "solid" : "regular"} fa-heart`;
            }
        });
}


function scrollAiChatToBottom() {

    if (!aiChatLog) return;

    /*
       requestAnimationFrame: yeni düğüm henüz yerleşmeden
       scrollHeight eski değeri verir ve son mesaj yarım
       kalır.
    */
    requestAnimationFrame(() => {
        aiChatLog.scrollTop = aiChatLog.scrollHeight;
    });
}


/* =========================================================
   SOSYAL — ARKADAŞLIK, MESAJLAŞMA, ÜRÜN PAYLAŞIMI

   Backend: /social/* uçları (backend/app/main.py),
   kurallar backend/app/social.py'de.

   TEK PANEL, İKİ GÖRÜNÜM
     #social-home    sekmeler (sohbetler / arkadaşlar / istekler)
     #social-thread  tek sohbet + yazma alanı
   Gardırop'taki look/swap deseninin aynısı.

   POLLING YOK
   Gerçek zamanlı mesajlaşma WebSocket ister. Bu sürümde yok:
   panel açıldığında ve mesaj gönderildiğinde yeniden
   yükleniyor, okunmamış rozeti sayfa yüklenişinde bir kez
   çekiliyor. Sürekli polling, kullanıcı paneli hiç açmasa
   bile sunucuya dakikada bir istek demek olurdu; karşılığı
   olmayan bir maliyet. Canlı bildirim istenirse doğru adım
   WebSocket, daha sık polling değil.
========================================================= */

const socialState = {
    open: false,

    /* "chats" | "friends" | "requests" */
    tab: "chats",

    /* Açık sohbet: {id, user} — null ise liste görünümü */
    thread: null,

    sending: false,

    /* Ürün paylaşımı için seçili ürün */
    shareProduct: null,
};


function setupSocial() {

    $("social-btn")?.addEventListener("click", openSocial);
    $("close-social")?.addEventListener("click", closeSocial);
    $("social-back")?.addEventListener("click", showSocialHome);

    $("social-overlay")?.addEventListener("click", event => {

        if (event.target === $("social-overlay")) {
            closeSocial();
        }
    });


    /* Sekmeler */
    document
        .querySelectorAll("[data-social-tab]")
        .forEach(button => {

            button.addEventListener("click", () => {
                setSocialTab(button.dataset.socialTab);
            });
        });


    /* Kullanıcı arama — her tuşta istek atmıyoruz */
    let searchTimer = null;

    $("social-search-input")?.addEventListener("input", event => {

        clearTimeout(searchTimer);

        const value = event.target.value;

        /*
           300ms bekleme: "nurgul" yazmak 6 tuş, yani 6 istek
           demekti. Kullanıcı yazmayı bıraktığında tek istek
           gidiyor.
        */
        searchTimer = setTimeout(
            () => runSocialSearch(value),
            300
        );
    });


    /* Liste tıklamaları — olay delegasyonu, satırlar
       her yüklemede yeniden çiziliyor */
    $("social-conversations")
        ?.addEventListener("click", handleConversationClick);

    $("social-friends")
        ?.addEventListener("click", handleFriendListClick);

    $("social-search-results")
        ?.addEventListener("click", handleFriendListClick);

    $("social-requests")
        ?.addEventListener("click", handleRequestClick);

    $("social-messages")
        ?.addEventListener("click", handleSocialMessageClick);


    /* Mesaj gönderme */
    $("social-composer")?.addEventListener("submit", event => {

        event.preventDefault();

        sendSocialMessage();
    });

    $("social-input")?.addEventListener("keydown", event => {

        if (event.key === "Enter" && !event.shiftKey) {

            event.preventDefault();

            sendSocialMessage();
        }
    });


    /* Ürün paylaşma penceresi */
    $("close-share")?.addEventListener("click", closeShare);

    $("share-overlay")?.addEventListener("click", event => {

        if (event.target === $("share-overlay")) {
            closeShare();
        }
    });

    $("share-friends")?.addEventListener("click", handleShareClick);
}


/* =========================================================
   PANEL AÇ / KAPA
========================================================= */

function openSocial() {

    if (!isUserLoggedIn()) {

        requestLoginForInteraction(
            null,
            "Mesajlar için giriş yapmalısın."
        );

        return;
    }

    $("social-overlay")?.classList.add("open");

    socialState.open = true;

    showSocialHome();

    loadSocialHome();
}


function closeSocial() {

    $("social-overlay")?.classList.remove("open");

    socialState.open = false;
}


function showSocialHome() {

    socialState.thread = null;

    $("social-home")?.classList.remove("hidden");
    $("social-thread")?.classList.add("hidden");
    $("social-back")?.classList.add("hidden");

    const title = $("social-title");

    if (title) title.textContent = "Mesajlar";
}


function setSocialTab(tab) {

    socialState.tab = tab;

    document
        .querySelectorAll("[data-social-tab]")
        .forEach(button => {

            button.classList.toggle(
                "active",
                button.dataset.socialTab === tab
            );
        });

    document
        .querySelectorAll("[data-social-pane]")
        .forEach(pane => {

            pane.classList.toggle(
                "hidden",
                pane.dataset.socialPane !== tab
            );
        });

    loadSocialHome();
}


/**
 * Açık sekmenin verisini yükler.
 *
 * Yalnızca GÖRÜNEN sekme çekiliyor: panel açılışında üç
 * isteği birden atmak, kullanıcının bakmadığı iki listeyi
 * de yüklemek olurdu.
 */
async function loadSocialHome() {

    if (socialState.tab === "chats") {
        await loadConversations();
    } else if (socialState.tab === "friends") {
        await loadFriends();
    } else {
        await loadRequests();
    }

    /* İstek rozeti sekmeden bağımsız: kullanıcı "İstekler"e
       bakmasa da orada bir şey olduğunu görmeli. */
    refreshRequestBadge();
}


/* =========================================================
   SOHBET LİSTESİ
========================================================= */

async function loadConversations() {

    const box = $("social-conversations");

    if (!box) return;

    box.innerHTML = `<p class="social-empty">Yükleniyor...</p>`;

    try {

        const rows = await apiFetch("/social/conversations");

        if (!rows.length) {

            box.innerHTML = `
                <p class="social-empty">
                    Henüz mesajın yok. Arkadaşlar sekmesinden
                    birini bulup sohbet başlatabilirsin.
                </p>
            `;

            return;
        }

        box.innerHTML = rows
            .map(renderConversationRow)
            .join("");

    } catch (error) {

        console.error("Sohbetler yüklenemedi:", error);

        box.innerHTML = `
            <p class="social-empty">Sohbetler yüklenemedi.</p>
        `;
    }
}


function renderConversationRow(row) {

    const preview = row.last_from_me
        ? `Sen: ${row.last_message}`
        : row.last_message;

    return `
        <button
            type="button"
            class="social-row"
            data-conversation="${escapeHTML(row.id)}"
            data-name="${escapeHTML(row.user.name)}"
        >
            <span class="social-avatar">
                ${escapeHTML(row.user.initials)}
            </span>

            <span class="social-row-body">
                <strong>${escapeHTML(row.user.name)}</strong>
                <small>${escapeHTML(preview || "—")}</small>
            </span>

            ${
                row.unread
                    ? `<span class="social-unread">${row.unread}</span>`
                    : ""
            }
        </button>
    `;
}


function handleConversationClick(event) {

    const row = event.target.closest("[data-conversation]");

    if (!row) return;

    openThread(row.dataset.conversation, row.dataset.name);
}


/* =========================================================
   ARKADAŞLAR + ARAMA
========================================================= */

async function loadFriends() {

    const box = $("social-friends");

    if (!box) return;

    try {

        const friends = await apiFetch("/social/friends");

        if (!friends.length) {

            box.innerHTML = `
                <p class="social-empty">
                    Henüz arkadaşın yok. Yukarıdan isim veya
                    e-posta ile arayabilirsin.
                </p>
            `;

            return;
        }

        box.innerHTML =
            `<span class="quick-section-label">ARKADAŞLARIN</span>` +
            friends
                .map(user => renderPersonRow(user, "friends"))
                .join("");

    } catch (error) {

        console.error("Arkadaşlar yüklenemedi:", error);
    }
}


async function runSocialSearch(query) {

    const box = $("social-search-results");

    if (!box) return;

    const cleaned = String(query || "").trim();

    /* Backend en az 2 karakter istiyor; boşuna istek atma */
    if (cleaned.length < 2) {

        box.classList.add("hidden");
        box.innerHTML = "";

        return;
    }

    try {

        const results = await apiGet("/social/users/search", {
            q: cleaned,
        });

        box.classList.remove("hidden");

        if (!results.length) {

            box.innerHTML = `
                <p class="social-empty">Kullanıcı bulunamadı.</p>
            `;

            return;
        }

        box.innerHTML =
            `<span class="quick-section-label">SONUÇLAR</span>` +
            results
                .map(user => renderPersonRow(user, user.relation))
                .join("");

    } catch (error) {

        console.error("Arama başarısız:", error);
    }
}


/**
 * Kişi satırı. Sağdaki buton İLİŞKİ DURUMUNA göre değişiyor.
 *
 * Durumu backend söylüyor (relation alanı) — frontend kendi
 * hesaplamıyor. Aynı gerekçe arama analizinde de vardı:
 * kuralı bilen taraf tek olsun.
 */
function renderPersonRow(user, relation) {

    let action = "";

    if (relation === "none" || relation === "declined") {

        action = `
            <button
                type="button"
                class="social-action"
                data-add-friend="${escapeHTML(user.id)}"
            >
                Ekle
            </button>
        `;

    } else if (relation === "outgoing") {

        action = `<span class="social-note">İstek gönderildi</span>`;

    } else if (relation === "incoming") {

        action = `
            <button
                type="button"
                class="social-action"
                data-accept="${escapeHTML(user.friendship_id || "")}"
            >
                Kabul et
            </button>
        `;

    } else if (relation === "friends") {

        action = `
            <button
                type="button"
                class="social-action ghost"
                data-message="${escapeHTML(user.id)}"
                data-name="${escapeHTML(user.name)}"
            >
                Mesaj
            </button>
        `;
    }

    return `
        <div class="social-row static">

            <span class="social-avatar">
                ${escapeHTML(user.initials)}
            </span>

            <span class="social-row-body">
                <strong>${escapeHTML(user.name)}</strong>
            </span>

            ${action}
        </div>
    `;
}


async function handleFriendListClick(event) {

    const add = event.target.closest("[data-add-friend]");

    if (add) {

        add.disabled = true;

        try {

            await apiFetch("/social/requests", {
                method: "POST",
                body: JSON.stringify({
                    user_id: add.dataset.addFriend,
                }),
            });

            showToast({
                title: "İstek gönderildi",
                tone: "success",
            });

            runSocialSearch($("social-search-input")?.value || "");

        } catch (error) {

            add.disabled = false;

            showToast({
                title: "Gönderilemedi",
                message: error?.message || "",
                tone: "neutral",
            });
        }

        return;
    }


    const accept = event.target.closest("[data-accept]");

    if (accept) {

        await respondToRequest(accept.dataset.accept, true);

        return;
    }


    const message = event.target.closest("[data-message]");

    if (message) {

        /*
           Sohbet henüz olmayabilir. Panelde boş bir eşik
           açıyoruz; ilk mesaj gönderilince backend sohbeti
           kendisi oluşturuyor (get_or_create_conversation).
        */
        openThread(
            null,
            message.dataset.name,
            message.dataset.message
        );
    }
}


/* =========================================================
   İSTEKLER
========================================================= */

async function loadRequests() {

    const box = $("social-requests");

    if (!box) return;

    try {

        const rows = await apiFetch("/social/requests");

        if (!rows.length) {

            box.innerHTML = `
                <p class="social-empty">
                    Bekleyen arkadaşlık isteğin yok.
                </p>
            `;

            return;
        }

        box.innerHTML = rows
            .map(row => `
                <div class="social-row static">

                    <span class="social-avatar">
                        ${escapeHTML(row.initials)}
                    </span>

                    <span class="social-row-body">
                        <strong>${escapeHTML(row.name)}</strong>
                        <small>arkadaş olmak istiyor</small>
                    </span>

                    <button
                        type="button"
                        class="social-action"
                        data-accept="${escapeHTML(row.friendship_id)}"
                    >
                        Kabul
                    </button>

                    <button
                        type="button"
                        class="social-action ghost"
                        data-decline="${escapeHTML(row.friendship_id)}"
                    >
                        Yoksay
                    </button>
                </div>
            `)
            .join("");

    } catch (error) {

        console.error("İstekler yüklenemedi:", error);
    }
}


function handleRequestClick(event) {

    const accept = event.target.closest("[data-accept]");

    if (accept) {
        respondToRequest(accept.dataset.accept, true);
        return;
    }

    const decline = event.target.closest("[data-decline]");

    if (decline) {
        respondToRequest(decline.dataset.decline, false);
    }
}


async function respondToRequest(friendshipId, accept) {

    if (!friendshipId) return;

    try {

        await apiFetch(`/social/requests/${friendshipId}`, {
            method: "POST",
            body: JSON.stringify({ accept }),
        });

        showToast({
            title: accept ? "Arkadaş eklendi" : "İstek yoksayıldı",
            tone: accept ? "success" : "neutral",
        });

        loadSocialHome();

    } catch (error) {

        showToast({
            title: "İşlem başarısız",
            message: error?.message || "",
            tone: "neutral",
        });
    }
}


async function refreshRequestBadge() {

    const badge = $("social-requests-badge");

    if (!badge) return;

    try {

        const rows = await apiFetch("/social/requests");

        badge.textContent = rows.length;
        badge.classList.toggle("hidden", rows.length === 0);

    } catch (error) {
        badge.classList.add("hidden");
    }
}


/* =========================================================
   SOHBET GÖRÜNÜMÜ
========================================================= */

/**
 * Sohbeti açar.
 *
 * conversationId null olabilir: arkadaş listesinden "Mesaj"
 * denince henüz sohbet yoktur. O durumda boş bir eşik
 * gösteriliyor ve ilk mesajla birlikte backend sohbeti
 * oluşturuyor.
 */
async function openThread(conversationId, name, userId = null) {

    socialState.thread = {
        id: conversationId,
        userId,
        name: name || "Sohbet",
    };

    $("social-home")?.classList.add("hidden");
    $("social-thread")?.classList.remove("hidden");
    $("social-back")?.classList.remove("hidden");

    const title = $("social-title");

    if (title) title.textContent = socialState.thread.name;

    const box = $("social-messages");

    if (!conversationId) {

        if (box) {
            box.innerHTML = `
                <p class="social-empty">
                    İlk mesajı sen yaz.
                </p>
            `;
        }

        $("social-input")?.focus();

        return;
    }

    if (box) {
        box.innerHTML = `<p class="social-empty">Yükleniyor...</p>`;
    }

    try {

        const data = await apiFetch(
            `/social/conversations/${conversationId}`
        );

        socialState.thread.userId = data.user.id;

        renderThreadMessages(data.messages || []);

        /* Açılış okundu sayıldı; header rozetini tazele */
        refreshSocialBadge();

    } catch (error) {

        console.error("Sohbet açılamadı:", error);

        if (box) {
            box.innerHTML = `
                <p class="social-empty">Sohbet açılamadı.</p>
            `;
        }
    }

    $("social-input")?.focus();
}


function renderThreadMessages(messages) {

    const box = $("social-messages");

    if (!box) return;

    if (!messages.length) {

        box.innerHTML = `
            <p class="social-empty">İlk mesajı sen yaz.</p>
        `;

        return;
    }

    box.innerHTML = messages.map(renderSocialMessage).join("");

    /* requestAnimationFrame: düğümler yerleşmeden
       scrollHeight eski değeri verir */
    requestAnimationFrame(() => {
        box.scrollTop = box.scrollHeight;
    });
}


function renderSocialMessage(message) {

    const side = message.from_me ? "me" : "them";

    const product = message.product;

    /*
       ÜRÜN KARTI. Mesaj başına en fazla bir ürün — bu bir
       şema garantisi (messages.product_id tek kolon), arayüz
       varsayımı değil.
    */
    const productHtml = product
        ? `
            <button
                type="button"
                class="social-product"
                data-social-product="${escapeHTML(product.product_id)}"
            >
                <img
                    src="${escapeHTML(safeImage(product.image_url))}"
                    alt=""
                    loading="lazy"
                >

                <span class="social-product-body">
                    <small>${escapeHTML(product.brand || "")}</small>
                    <strong>${escapeHTML(productTitle(product))}</strong>
                    <span>${escapeHTML(
                        hasPrice(product)
                            ? formatPrice(product.price)
                            : ""
                    )}</span>
                </span>
            </button>
        `
        : "";

    return `
        <div class="social-msg ${side}">

            ${productHtml}

            ${
                message.body
                    ? `<div class="social-bubble">${escapeHTML(message.body)}</div>`
                    : ""
            }
        </div>
    `;
}


function handleSocialMessageClick(event) {

    const card = event.target.closest("[data-social-product]");

    if (!card) return;

    /*
       Ürün modalı sosyal panelin ÜZERİNDE açılıyor. Panel
       kapanmıyor: kullanıcı modalı kapatınca sohbete kaldığı
       yerden dönsün.
    */
    openProduct(card.dataset.socialProduct);
}


async function sendSocialMessage() {

    const input = $("social-input");

    const text = (input?.value || "").trim();

    if (!text || socialState.sending || !socialState.thread) return;

    socialState.sending = true;

    const sendButton = $("social-send");

    if (sendButton) sendButton.disabled = true;

    try {

        const payload = socialState.thread.id
            ? { conversation_id: socialState.thread.id, body: text }
            : { to_user_id: socialState.thread.userId, body: text };

        const data = await apiFetch("/social/messages", {
            method: "POST",
            body: JSON.stringify(payload),
        });

        if (input) input.value = "";

        /* İlk mesajda sohbet yeni oluştu; kimliğini sakla */
        socialState.thread.id = data.conversation_id;

        await openThread(
            data.conversation_id,
            socialState.thread.name
        );

    } catch (error) {

        showToast({
            title: "Mesaj gönderilemedi",
            message: error?.message || "",
            tone: "neutral",
        });

    } finally {

        socialState.sending = false;

        if (sendButton) sendButton.disabled = false;
    }
}


/* =========================================================
   OKUNMAMIŞ ROZETİ
========================================================= */

async function refreshSocialBadge() {

    const badge = document.querySelector(".social-number");

    if (!badge) return;

    if (!isUserLoggedIn()) {
        badge.classList.add("hidden");
        return;
    }

    try {

        const data = await apiFetch("/social/unread");

        const count = Number(data?.unread || 0);

        badge.textContent = count;
        badge.classList.toggle("hidden", count === 0);

    } catch (error) {
        badge.classList.add("hidden");
    }
}


/* =========================================================
   ÜRÜN PAYLAŞIMI
========================================================= */

/**
 * Ürün detayındaki "Arkadaşına Gönder" düğmesinden açılıyor.
 *
 * Arkadaş listesi HER AÇILIŞTA tazeleniyor: kullanıcı bu
 * arada yeni birini eklemiş olabilir ve eski listeyi
 * göstermek "arkadaşım yok" gibi yanlış bir izlenim verirdi.
 */
async function openShare(product) {

    if (!isUserLoggedIn()) {

        requestLoginForInteraction(
            null,
            "Ürün paylaşmak için giriş yapmalısın."
        );

        return;
    }

    socialState.shareProduct = product;

    const preview = $("share-product");

    if (preview) {

        preview.innerHTML = `
            <img
                src="${escapeHTML(safeImage(product.image_url))}"
                alt=""
            >
            <div>
                <strong>${escapeHTML(productTitle(product))}</strong>
                <span>${escapeHTML(
                    hasPrice(product) ? formatPrice(product.price) : ""
                )}</span>
            </div>
        `;
    }

    const note = $("share-note");

    if (note) note.value = "";

    $("share-overlay")?.classList.add("open");

    const box = $("share-friends");

    if (box) {
        box.innerHTML = `<p class="social-empty">Yükleniyor...</p>`;
    }

    try {

        const friends = await apiFetch("/social/friends");

        if (!friends.length) {

            box.innerHTML = `
                <p class="social-empty">
                    Henüz arkadaşın yok. Mesajlar panelinden
                    arkadaş ekleyebilirsin.
                </p>
            `;

            return;
        }

        box.innerHTML = friends
            .map(user => `
                <button
                    type="button"
                    class="social-row"
                    data-share-to="${escapeHTML(user.id)}"
                    data-name="${escapeHTML(user.name)}"
                >
                    <span class="social-avatar">
                        ${escapeHTML(user.initials)}
                    </span>

                    <span class="social-row-body">
                        <strong>${escapeHTML(user.name)}</strong>
                    </span>

                    <span class="social-note">Gönder</span>
                </button>
            `)
            .join("");

    } catch (error) {

        console.error("Arkadaşlar yüklenemedi:", error);
    }
}


function closeShare() {

    $("share-overlay")?.classList.remove("open");

    socialState.shareProduct = null;
}


async function handleShareClick(event) {

    const row = event.target.closest("[data-share-to]");

    if (!row || !socialState.shareProduct) return;

    row.disabled = true;

    try {

        await apiFetch("/social/messages", {
            method: "POST",
            body: JSON.stringify({
                to_user_id: row.dataset.shareTo,
                product_id: socialState.shareProduct.product_id,
                body: ($("share-note")?.value || "").trim() || null,
            }),
        });

        closeShare();

        showToast({
            title: "Gönderildi",
            message: `${row.dataset.name} kişisine ürünü yolladın.`,
            tone: "success",
        });

        refreshSocialBadge();

    } catch (error) {

        row.disabled = false;

        showToast({
            title: "Gönderilemedi",
            message: error?.message || "",
            tone: "neutral",
        });
    }
}
