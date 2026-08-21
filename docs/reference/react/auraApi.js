/**
 * AURA API istemcisi  (React portu)
 *
 * Çalışan sistemin karşılığı: frontend/app.js
 * Uçlar birebir aynı; FastAPI backend'i hiç değiştirmeden
 * kullanır.
 */

export const API_BASE =
    import.meta.env?.VITE_API_BASE || "http://127.0.0.1:8000";


/* =========================================================
   KİMLİK
   ---------------------------------------------------------
   GEÇİCİ: projede henüz JWT yok, backend kullanıcıyı
   X-User-Id başlığından okuyor. Bu başlık istemci
   tarafından değiştirilebilir, yani TAKLİT EDİLEBİLİR.
   Üretime çıkmadan önce burası Authorization: Bearer
   olarak değiştirilmeli — dokunulacak tek yer bu fonksiyon.
========================================================= */

export function getStoredUser() {
    try {
        const raw = localStorage.getItem("user");
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

function authHeaders() {
    const user = getStoredUser();
    return user?.id ? { "X-User-Id": String(user.id) } : {};
}


/* =========================================================
   TEMEL İSTEK
========================================================= */

/** FastAPI 422'de `detail` bir dizi döner: [{loc, msg}]. */
function extractApiError(data, fallback) {
    const detail = data?.detail;

    if (typeof detail === "string" && detail) return detail;

    if (Array.isArray(detail) && detail.length && detail[0]?.msg) {
        return detail[0].msg;
    }

    return fallback;
}

export async function apiFetch(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...authHeaders(),
            ...(options.headers || {}),
        },
    });

    const data = await response.json().catch(() => ({}));

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
   TARZ SEÇİMİ  (8 arketip, 1-3 seçim)
========================================================= */

export const STYLES_KEY = "aura_styles";
export const STYLES_SEEN_KEY = "aura_archetype_seen";

/** Eski sürüm tek tarzı düz metin olarak saklıyordu. */
const LEGACY_KEY = "aura_archetype";

export const MAX_SELECTED_STYLES = 3;

export function readStoredStyles() {
    try {
        const raw = localStorage.getItem(STYLES_KEY);

        if (raw) {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed) && parsed.length) {
                return parsed.slice(0, MAX_SELECTED_STYLES);
            }
        }

        // Göç: eski tek-tarz kaydı
        const legacy = localStorage.getItem(LEGACY_KEY);

        if (legacy) {
            const migrated =
                legacy === "classic" ? "smart_casual" : legacy;

            writeStoredStyles([migrated]);
            localStorage.removeItem(LEGACY_KEY);

            return [migrated];
        }

        return [];
    } catch {
        return [];
    }
}

export function writeStoredStyles(styles) {
    try {
        localStorage.setItem(
            STYLES_KEY,
            JSON.stringify(styles.slice(0, MAX_SELECTED_STYLES))
        );
        localStorage.setItem(STYLES_SEEN_KEY, "1");
    } catch {
        /* localStorage kapalı olabilir; kritik değil */
    }
}

export function markStylesSeen() {
    try {
        localStorage.setItem(STYLES_SEEN_KEY, "1");
    } catch {
        /* yoksay */
    }
}

export function hasSeenStylePicker() {
    try {
        return localStorage.getItem(STYLES_SEEN_KEY) === "1";
    } catch {
        return false;
    }
}

/** 8 stil kartı + her birinin gerçek havuz sayısı. */
export function fetchArchetypes() {
    return apiFetch("/api/archetypes");
}

export function saveInitialStyles(selectedStyles) {
    return apiFetch("/api/initial-style", {
        method: "POST",
        body: JSON.stringify({ selected_styles: selectedStyles }),
    });
}


/* =========================================================
   KEŞFET  (cursor tabanlı sonsuz akış)
========================================================= */

/**
 * SAYFA NUMARASI YOK.
 *
 * Sunucu her yanıtta `meta.next_cursor` döner; onu aynen
 * geri gönderiyoruz. Cursor içinde "kaldığım skor + son
 * ürün + gösterilmiş kimlikler" var, bu yüzden ayrıca
 * exclude listesi göndermek gerekmiyor.
 *
 * Neden OFFSET değil: OFFSET her sayfada önceki satırları
 * yeniden tarar ve arada yeni etkileşim olursa sıralama
 * kayar; kullanıcı aynı ürünü iki kez görür.
 */
export function fetchExplore({
    limit = 12,
    cursor = null,
    styles = [],
} = {}) {
    const params = new URLSearchParams({ limit: String(limit) });

    if (cursor) params.set("cursor", cursor);

    // Giriş yapmışsa sunucu kayıtlı tercihi kullanır;
    // parametreyi yalnızca misafir için gönderiyoruz.
    if (styles.length && !getStoredUser()) {
        params.set("styles", styles.join(","));
    }

    return apiFetch(`/api/explore?${params}`);
}


/* =========================================================
   ETKİLEŞİM
========================================================= */

/**
 * Tek uç, bütün ürün etkileşimleri.
 *
 * matchScore ve matchedStyle MUTLAKA gönderilir: model
 * "kullanıcı neyi beğendi" değil "X skoruyla, Y tarzına
 * uyduğu söylenerek gösterilen şeyi beğendi mi" sorusunu
 * öğrenmeli. Kart bu değerleri kendi üzerinde taşıdığı
 * için aynen geri gönderilir.
 */
/**
 * Etkileşim kaydı.
 *
 * ML ağırlıkları sunucuda belirleniyor ve olayla birlikte
 * satıra yazılıyor:
 *   QUICK_BUY +2 · LIKE +1 · VIEW +0.1
 *   UNLIKE -0.3 · DISLIKE -1
 */
export function sendInteraction({
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
            match_score: matchScore ?? null,
            matched_style: matchedStyle ?? null,
        }),
    });
}


/* =========================================================
   VIEW KUYRUĞU
========================================================= */

const VIEW_FLUSH_DELAY = 2500;
const VIEW_QUEUE_LIMIT = 20;

const viewQueue = [];
const viewedThisSession = new Set();

let viewTimer = null;

export function queueView({
    productId,
    source = "explore",
    position = null,
    matchScore = null,
}) {
    if (!productId || !getStoredUser()) return;

    // Aynı ürünü aynı oturumda tekrar tekrar kaydetmiyoruz:
    // kaydırma sırasında kart ekrana birkaç kez girip çıkar.
    const key = `${source}:${productId}`;
    if (viewedThisSession.has(key)) return;
    viewedThisSession.add(key);

    viewQueue.push({
        product_id: productId,
        interaction_type: "VIEW",
        source,
        position,
        match_score: matchScore ?? null,
    });

    if (viewQueue.length >= VIEW_QUEUE_LIMIT) {
        flushViews();
        return;
    }

    clearTimeout(viewTimer);
    viewTimer = setTimeout(flushViews, VIEW_FLUSH_DELAY);
}

export function flushViews(useKeepalive = false) {
    clearTimeout(viewTimer);

    if (!viewQueue.length || !getStoredUser()) return;

    const items = viewQueue.splice(0, VIEW_QUEUE_LIMIT);

    // NOT: toplu VIEW ucu /api altında değil — AI katmanı
    // /api/* altında, wishlist ve batch uçları kök altında.
    fetch(`${API_BASE}/interactions/batch`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...authHeaders(),
        },
        body: JSON.stringify({ items }),
        keepalive: useKeepalive,
    }).catch(() => {});
}

/** Uygulama kökünde bir kez çağır. */
export function installViewFlushHandlers() {
    const flush = () => flushViews(true);

    window.addEventListener("pagehide", flush);

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") flush();
    });

    return () => window.removeEventListener("pagehide", flush);
}


/* =========================================================
   HIZLI SATIN ALMA  (sepetsiz)
========================================================= */

/**
 * Tek ürünlük sipariş.
 *
 * SEPET YOK. Çok ürünlü sipariş de yok — bilinçli bir
 * takas: tek tıkla satın alma sürtünmeyi kaldırıyor ama
 * sepet ortalama sipariş tutarını etkiler.
 *
 * DİKKAT: kart bilgisi BU İSTEĞE GİRMİYOR. Doğrulama
 * istemcide yapılıyor; sunucu yalnızca satın alma niyetini
 * kaydediyor (QUICK_BUY, ML ağırlığı +2 — LIKE'tan güçlü).
 * Gerçek bir ödeme sağlayıcısı eklendiğinde tokenizasyon
 * yapılmalı; kart numarası asla bu gövdeye girmemeli.
 */
export function createQuickOrder({
    productId,
    source = "quick_checkout",
    position = null,
    matchScore = null,
    matchedStyle = null,
}) {
    return apiFetch("/api/quick-order", {
        method: "POST",
        body: JSON.stringify({
            product_id: productId,
            source,
            position: Number.isFinite(position) ? position : null,
            match_score: matchScore ?? null,
            matched_style: matchedStyle ?? null,
        }),
    });
}


/* =========================================================
   WISHLIST / PROFİL
========================================================= */

export async function fetchWishlistIds() {
    const data = await apiFetch("/wishlist/ids");
    return data.product_ids || [];
}

export function fetchWishlist() {
    return apiFetch("/wishlist");
}

export function fetchPreferences() {
    return apiFetch("/api/preferences");
}
