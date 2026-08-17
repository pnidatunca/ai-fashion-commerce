/* =========================================================
   AURA FASHION
   FastAPI Backend Connected Version
========================================================= */

const API_BASE = "http://127.0.0.1:8000";

const state = {
    page: 1,
    limit: 12,

    searchQuery: "",
    searchMode: false,

    category: "",

    products: [],
    hasNextPage: false,

    sortBy: "",
    cart: []
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

const productModal = $("product-modal");
const modalContent = $("modal-content");
const closeModalButton = $("close-modal-btn");

const openSearchButton = $("open-search-btn");
const searchOverlay = $("search-overlay");
const searchClose = $("search-close");
const globalSearchInput = $("global-search-input");

const cartButton = $("cart-btn");
const cartOverlay = $("cart-overlay");
const closeCartButton = $("close-cart");
const cartItems = $("cart-items");
const cartTotal = $("cart-total");

const mobileMenu = $("mobile-menu");
const mobileMenuButton = $("mobile-menu-btn");
const mobileClose = $("mobile-close");


/* =========================================================
   START
========================================================= */

document.addEventListener("DOMContentLoaded", () => {

    setupNavigation();
    setupSearch();
    setupCategories();
    setupSort();
    setupModal();
    setupCart();

    loadCart();
    updateCart();

    loadProducts();
    loadFeaturedProducts();
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


/* =========================================================
   PRODUCTS
========================================================= */

async function loadProducts() {

    showLoader();
    hideEmpty();

    const offset =
        (state.page - 1) * state.limit;

    try {

        let data;

        if (state.searchMode && state.searchQuery) {

            data = await apiGet(
                "/products/search",
                {
                    q: state.searchQuery,
                    limit: state.limit,
                    offset: offset
                }
            );

        } else {

            data = await apiGet(
                "/products",
                {
                    limit: state.limit,
                    offset: offset,
                    category: state.category
                }
            );
        }


        if (!Array.isArray(data)) {
            throw new Error(
                "Backend ürün listesi döndürmedi."
            );
        }


        state.products = data;

        state.hasNextPage =
            data.length === state.limit;


        renderProducts(
            sortProducts(data)
        );

        renderPagination();


        if (resultsTitle) {

            resultsTitle.textContent =
                state.searchMode
                    ? `"${state.searchQuery}" sonuçları`
                    : "Tüm Ürünler";
        }


        if (resultsCount) {

            if (data.length) {

                resultsCount.textContent =
                    `${data.length} ürün gösteriliyor · Sayfa ${state.page}`;

            } else {

                resultsCount.textContent =
                    "Ürün bulunamadı";
            }
        }


        if (!data.length) {

            showEmpty(
                "Ürün bulunamadı",
                "Farklı bir arama terimi deneyebilirsin."
            );
        }


    } catch (error) {

        console.error(
            "Products API error:",
            error
        );


        if (resultsCount) {
            resultsCount.textContent =
                "Ürünler yüklenemedi";
        }


        showEmpty(
            "Ürünler yüklenemedi",
            "Backend bağlantısını kontrol et."
        );

    } finally {

        hideLoader();
    }
}


/* =========================================================
   RENDER PRODUCT CARDS
========================================================= */

function renderProducts(products) {

    if (!productsGrid) return;

    productsGrid.innerHTML = "";


    products.forEach(product => {

        const card =
            document.createElement("article");

        card.className = "product-card";


        const title =
         product.title_tr || product.title || "Ürün";

        const brand =
            product.brand || "";

        const price =
            formatPrice(product.price);

        const discount =
            Number(
                product.discount_percent || 0
            );

        const rating =
            Number(product.rating || 0);

        const ratingCount =
            Number(product.rating_count || 0);


        card.innerHTML = `

            <div class="card-image-wrap">

                <img
                    src="${safeImage(product.image_url)}"
                    alt="${escapeHTML(title)}"
                    loading="lazy"
                    onerror="this.src='https://placehold.co/600x800?text=AURA'"
                >

                ${
                    discount > 0
                        ? `
                            <span class="discount-tag">
                                -${discount}%
                            </span>
                        `
                        : ""
                }


                ${
                    brand
                        ? `
                            <span class="brand-pill">
                                ${escapeHTML(brand)}
                            </span>
                        `
                        : ""
                }

            </div>


            <div class="card-details">

                <h4 class="product-title">
                    ${escapeHTML(title)}
                </h4>


                ${
                    rating > 0
                        ? `
                            <div class="product-rating">

                                <i class="fa-solid fa-star"></i>

                                <span>
                                    ${rating.toFixed(1)}
                                    ${
                                        ratingCount
                                            ? `(${ratingCount.toLocaleString("en-US")})`
                                            : ""
                                    }
                                </span>

                            </div>
                        `
                        : ""
                }


                <div class="price-row">

                    <span class="current-price">
                        ${price}
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


                <button
                    type="button"
                    class="view-detail-btn"
                >
                    ÜRÜNÜ GÖR
                </button>

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


        productsGrid.appendChild(card);
    });
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
                        onerror="this.src='https://placehold.co/600x800?text=AURA'"
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


/* =========================================================
   SEARCH
========================================================= */

function setupSearch() {

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
        state.page = 1;

        loadProducts();

        return;
    }


    state.searchMode = true;
    state.searchQuery = query;
    state.page = 1;


    loadProducts();


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

    document
        .querySelectorAll("[data-category]")
        .forEach(button => {

            button.addEventListener(
                "click",
                () => {

                    const category =
                        button.dataset.category || "";
                        console.log(
                                "CATEGORY CLICK:",
                                category
                            );
                            

                    state.category = category;

                    state.searchMode = false;
                    state.searchQuery = "";

                    state.page = 1;


                    if (searchInput) {
                        searchInput.value = "";
                    }


                    document
                        .querySelectorAll(
                            "[data-category]"
                        )
                        .forEach(item => {

                            item.classList.remove(
                                "active"
                            );
                        });


                    /*
                       Aynı kategori üst ve alt menüde
                       bulunabildiği için ikisini de aktif yap.
                    */

                    document
                        .querySelectorAll(
                            `[data-category="${category}"]`
                        )
                        .forEach(item => {

                            item.classList.add(
                                "active"
                            );
                        });


                    loadProducts();


                    $("products-section")
                        ?.scrollIntoView({
                            behavior: "smooth"
                        });
                }
            );
        });
}


/* =========================================================
   SORT
========================================================= */

function setupSort() {

    sortSelect?.addEventListener(
        "change",
        event => {

            state.sortBy =
                event.target.value;


            renderProducts(
                sortProducts(state.products)
            );
        }
    );
}


function sortProducts(products) {

    const sorted =
        [...products];


    switch (state.sortBy) {

        case "price_asc":

            return sorted.sort(
                (a, b) =>
                    Number(a.price ?? Infinity) -
                    Number(b.price ?? Infinity)
            );


        case "price_desc":

            return sorted.sort(
                (a, b) =>
                    Number(b.price ?? -Infinity) -
                    Number(a.price ?? -Infinity)
            );


        case "rating":

            return sorted.sort(
                (a, b) =>
                    Number(b.rating || 0) -
                    Number(a.rating || 0)
            );


        case "discount":

            return sorted.sort(
                (a, b) =>
                    Number(
                        b.discount_percent || 0
                    ) -
                    Number(
                        a.discount_percent || 0
                    )
            );


        default:

            return sorted;
    }
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


    } catch (error) {

        console.error(
            "Product detail error:",
            error
        );


    } finally {

        hideLoader();
    }
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


                ${
                    product.product_url
                        ? `
                            <a
                                href="${escapeHTML(product.product_url)}"
                                target="_blank"
                                rel="noopener noreferrer"
                                class="view-detail-btn"
                                style="
                                    display:block;
                                    text-align:center;
                                    margin-top:20px;
                                "
                            >
                                AMAZON'DA GÖR
                            </a>
                        `
                        : ""
                }


                <button
                    type="button"
                    class="checkout-btn"
                    id="modal-add-cart"
                    style="margin-top:12px;"
                >
                    DEMO SEPETE EKLE
                </button>

            </div>

        </div>


        <div class="reviews-section">

            <h3>
                Müşteri Yorumları
            </h3>

            ${renderReviews(reviews)}

        </div>
    `;


    $("modal-add-cart")
        ?.addEventListener(
            "click",
            () => addToCart(product)
        );
}


/* =========================================================
   REVIEWS
========================================================= */

function renderReviews(reviews) {

    if (!Array.isArray(reviews) || !reviews.length) {

        return `
            <p>
                Bu ürün için yorum bulunamadı.
            </p>
        `;
    }


    return reviews
        .map(review => `

            <div class="review-card">

                <div class="review-header">

                    <strong>
                        ${escapeHTML(
                            review.review_title ||
                            "Değerlendirme"
                        )}
                    </strong>

                    <span>
                        ★ ${
                            review.rating !== null
                                ? Number(
                                    review.rating
                                ).toFixed(1)
                                : "-"
                        }
                    </span>

                </div>


                ${
                    review.verified_purchase
                        ? `
                            <small>
                                ✓ Verified Purchase
                            </small>
                        `
                        : ""
                }


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

            </div>

        `)
        .join("");
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
   PAGINATION
========================================================= */

function renderPagination() {

    if (!pagination) return;


    pagination.innerHTML = "";


    const previous =
        state.page > 1;


    if (!previous && !state.hasNextPage) {

        pagination.classList.add(
            "hidden"
        );

        return;
    }


    pagination.classList.remove(
        "hidden"
    );


    if (previous) {

        pagination.appendChild(
            pageButton(
                "← ÖNCEKİ",
                state.page - 1
            )
        );
    }


    const pageLabel =
        document.createElement("span");

    pageLabel.textContent =
        `SAYFA ${state.page}`;

    pageLabel.className =
        "pagination-dots";

    pagination.appendChild(
        pageLabel
    );


    if (state.hasNextPage) {

        pagination.appendChild(
            pageButton(
                "SONRAKİ →",
                state.page + 1
            )
        );
    }
}


function pageButton(
    label,
    page
) {

    const button =
        document.createElement("button");

    button.className =
        "page-btn";

    button.textContent =
        label;


    button.addEventListener(
        "click",
        () => {

            state.page = page;

            loadProducts();

            $("products-section")
                ?.scrollIntoView({
                    behavior: "smooth"
                });
        }
    );


    return button;
}


/* =========================================================
   CART
========================================================= */

function setupCart() {

    cartButton?.addEventListener(
        "click",
        () => {

            cartOverlay
                ?.classList.add("open");
        }
    );


    closeCartButton?.addEventListener(
        "click",
        closeCart
    );


    cartOverlay?.addEventListener(
        "click",
        event => {

            if (
                event.target === cartOverlay
            ) {
                closeCart();
            }
        }
    );
}


function closeCart() {

    cartOverlay
        ?.classList.remove("open");
}


function addToCart(product) {

    const existing =
        state.cart.find(
            item =>
                item.product_id ===
                product.product_id
        );


    if (existing) {

        existing.quantity += 1;

    } else {

        state.cart.push({
            ...product,
            quantity: 1
        });
    }


    saveCart();

    updateCart();

    cartOverlay
        ?.classList.add("open");
}


function saveCart() {

    localStorage.setItem(
        "aura_cart",
        JSON.stringify(state.cart)
    );
}


function loadCart() {

    try {

        const saved =
            localStorage.getItem(
                "aura_cart"
            );


        state.cart =
            saved
                ? JSON.parse(saved)
                : [];


    } catch {

        state.cart = [];
    }
}


function updateCart() {

    const count =
        state.cart.reduce(
            (sum, product) =>
                sum +
                Number(product.quantity || 0),
            0
        );


    document
        .querySelectorAll(
            ".cart-number"
        )
        .forEach(element => {

            element.textContent =
                count;
        });


    if (!cartItems || !cartTotal) {
        return;
    }


    if (!state.cart.length) {

        cartItems.innerHTML = `

            <div class="cart-empty">

                <i class="fa-solid fa-bag-shopping"></i>

                <p>
                    Sepetiniz boş.
                </p>

            </div>
        `;


        cartTotal.textContent =
            formatPrice(0);

        return;
    }


    cartItems.innerHTML =
        state.cart
            .map(item => `

                <div class="cart-row">

                    <img
                        src="${safeImage(item.image_url)}"
                        alt="${escapeHTML(item.title)}"
                        width="70"
                    >

                    <div>

                        <strong>
                            ${escapeHTML(item.title)}
                        </strong>

                        <p>
                            ${formatPrice(item.price)}
                        </p>

                        <small>
                            Adet: ${item.quantity}
                        </small>

                    </div>

                </div>

            `)
            .join("");


    const total =
        state.cart.reduce(
            (sum, item) =>

                sum +
                Number(item.price || 0) *
                Number(item.quantity || 1),

            0
        );


    cartTotal.textContent =
        formatPrice(total);
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

function formatPrice(value) {

    const number =
        Number(value);


    if (!Number.isFinite(number)) {
        return "Fiyat yok";
    }


    return new Intl.NumberFormat(
        "en-US",
        {
            style: "currency",
            currency: "USD"
        }
    ).format(number);
}


function safeImage(value) {

    if (
        typeof value === "string" &&
        value.startsWith("http")
    ) {
        return value;
    }


    return "https://placehold.co/600x800?text=AURA";
}


function escapeHTML(value) {

    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}