import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Info, RefreshCw, Sparkles } from "lucide-react";

import AiAnalyzing, { runWithAnalyzing } from "./AiAnalyzing";
import ExploreCard from "./ExploreCard";
import QuickCheckout from "./QuickCheckout";
import StylePickerModal from "./StylePickerModal";
import WishlistBar from "./WishlistBar";
import { useExplore } from "./useExplore";
import { FALLBACK_TOASTS, useToast } from "./ToastProvider";

import {
    MAX_SELECTED_STYLES,
    getStoredUser,
    hasSeenStylePicker,
    installViewFlushHandlers,
    readStoredStyles,
    saveInitialStyles,
    writeStoredStyles,
} from "./auraApi";

/**
 * KEŞFET BÖLÜMÜ — bütün parçaları birleştirir.
 *
 * Akış:
 *   ilk ziyaret → 8 tarzlı picker (1-3 seçim)
 *   → AI analiz (~1 sn) → skorlu akış
 *   → kalp / thumbs-down (geri alınabilir) → toast
 *   → tek tıkla al → tek ekran ödeme
 *   → aşağı kaydır → sonsuz akış (cursor)
 *
 * SAYFA NUMARASI VE OK İŞARETİ YOK.
 * SEPET YOK: kartta iki eylem var, kalp ve satın al.
 */

const USD_TRY_FALLBACK = 47.98;

const STYLE_LABELS = {
    minimalist: "Minimalist",
    streetwear: "Streetwear",
    smart_casual: "Smart Casual",
    old_money: "Old Money",
    boho: "Boho",
    athleisure: "Athleisure",
    goth: "Goth",
    y2k: "Y2K",
};

const STYLE_EMOJI = {
    minimalist: "🌿",
    streetwear: "🛹",
    smart_casual: "💼",
    old_money: "🍷",
    boho: "🎨",
    athleisure: "🏋️",
    goth: "🖤",
    y2k: "✨",
};


export default function ExploreFeed() {
    const { showToast } = useToast();

    const {
        items,
        meta,
        remaining,
        loading,
        exhausted,
        hasMore,
        wishlist,
        wishlistItems,
        busy,
        styles,
        setStyles,
        like,
        dislike,
        reload,
        loadMore,
        loadWishlist,
    } = useExplore();

    const [pickerOpen, setPickerOpen] = useState(false);
    const [analyzing, setAnalyzing] = useState(false);
    const [analyzeLabel, setAnalyzeLabel] = useState("");

    /* Hızlı satın alma: tek ürün, tek ekran */
    const [checkoutItem, setCheckoutItem] = useState(null);

    const signedIn = Boolean(getStoredUser());

    const sentinelRef = useRef(null);

    /* Sekme kapanırken bekleyen VIEW olaylarını gönder */
    useEffect(() => installViewFlushHandlers(), []);

    /* İlk ziyaret: picker'ı aç */
    useEffect(() => {
        if (readStoredStyles().length || hasSeenStylePicker()) return;

        // Sayfa boyansın, sonra aç
        const timer = setTimeout(() => setPickerOpen(true), 800);
        return () => clearTimeout(timer);
    }, []);


    /* -----------------------------------------------------
       SONSUZ AKIŞ
       ---------------------------------------------------
       Sentinel ekrana girmeden 300 px önce tetikleniyor ki
       kullanıcı bekleme görmesin.
    ----------------------------------------------------- */

    useEffect(() => {
        const node = sentinelRef.current;

        if (!node || typeof IntersectionObserver === "undefined") {
            return;
        }

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (!entry.isIntersecting) return;
                if (loading || !hasMore || !items.length) return;

                loadMore();
            },
            { rootMargin: "300px 0px", threshold: 0 }
        );

        observer.observe(node);

        return () => observer.disconnect();
    }, [loading, hasMore, items.length, loadMore]);


    /**
     * Fiyatlar katalogda USD tutuluyor, TL gösteriliyor.
     *
     * Fiyatı olmayan ürün "Fiyat yok" der: Number(null)
     * sıfırdır ve ₺0,00 göstermek kullanıcıyı yanıltır.
     */
    const formatPrice = useMemo(() => {
        const formatter = new Intl.NumberFormat("tr-TR", {
            style: "currency",
            currency: "TRY",
        });

        return (value) => {
            if (value === null || value === undefined || value === "") {
                return "Fiyat yok";
            }

            const number = Number(value);

            if (!Number.isFinite(number)) return "Fiyat yok";

            return formatter.format(number * USD_TRY_FALLBACK);
        };
    }, []);


    /* -----------------------------------------------------
       HIZLI SATIN ALMA
       ---------------------------------------------------
       Sepet kaldırıldı. Karttaki "TEK TIKLA AL" doğrudan
       ödeme ekranını açıyor; arada "sepete eklendi, sepete
       git, ödemeye geç" gibi üç adım yok.
    ----------------------------------------------------- */

    const openQuickBuy = useCallback(
        (item, index) => {
            if (!getStoredUser()) {
                showToast({
                    title: "Giriş gerekli",
                    message: "Sipariş vermek için giriş yap.",
                    tone: "info",
                });
                return;
            }

            setCheckoutItem({ ...item, position: index, source: "explore" });
        },
        [showToast]
    );

    /* Alt bardan gelen ürün: kart bağlamı yok */
    const openQuickBuyProduct = useCallback(
        (product) =>
            openQuickBuy({ product, match_score: null, matched_style: null }, null),
        [openQuickBuy]
    );

    const handleOrdered = useCallback(() => {
        /*
           Sipariş QUICK_BUY etkileşimi olarak yazılıyor
           (ağırlık 2.0 — beğenmekten güçlü sinyal), bu yüzden
           zevk profili değişti. Favorileri tazeliyoruz ki
           alt bar gerçeği göstersin.
        */
        loadWishlist();
        showToast(FALLBACK_TOASTS.QUICK_BUY);
    }, [loadWishlist, showToast]);


    const handleConfirm = useCallback(
        async (selected) => {
            writeStoredStyles(selected);
            setStyles(selected);
            setPickerOpen(false);

            const labels = selected.map((id) => STYLE_LABELS[id] || id);

            setAnalyzeLabel(
                labels.length === 1
                    ? `${labels[0]} tarzın analiz ediliyor...`
                    : `${labels.join(" + ")} analiz ediliyor...`
            );

            let response = null;

            await runWithAnalyzing(setAnalyzing, async () => {
                /*
                   Misafirse sunucuya yazmıyoruz: user_id
                   gerektiriyor. Seçim localStorage'da durur,
                   giriş yapıldığında taşınır. Böylece anonim
                   satır eğitim verisine hiç girmez.
                */
                if (getStoredUser()) {
                    try {
                        response = await saveInitialStyles(selected);
                    } catch (error) {
                        console.error("Stil kaydedilemedi:", error);
                    }
                }

                await reload();
            });

            showToast({
                title:
                    labels.length === 1
                        ? `${labels[0]} tarzı seçildi`
                        : `${labels.length} tarz seçildi`,
                message: response?.matched_products
                    ? `${response.matched_products} parça senin tarzında. Akışın hazır.`
                    : "Akışın seçimine göre yeniden düzenlendi.",
                tone: "success",
            });
        },
        [reload, setStyles, showToast]
    );


    return (
        <section className="explore-section" id="explore">
            <div className="explore-header">
                <div>
                    <span className="section-number">03</span>

                    <h2>Keşfet</h2>

                    <p className="explore-lead">
                        Beğendiğini kalple işaretle, istemediğini elemek
                        için baş parmağı aşağı çevir — yanlışlıkla
                        basarsan geri alabilirsin. Sepet yok: almak
                        istediğin parçaya tek dokunuş yeter.
                    </p>

                    {styles.length > 0 && (
                        <div className="ai-status">
                            <span className="ai-chip">
                                <span className="ai-dot" />
                                AURA AI
                            </span>

                            <span className="ai-status-text">
                                Akışın{" "}
                                <span className="ai-status-styles">
                                    {styles.map((id) => (
                                        <span
                                            key={id}
                                            className="ai-status-style"
                                        >
                                            {STYLE_EMOJI[id]}{" "}
                                            {STYLE_LABELS[id] || id}
                                        </span>
                                    ))}
                                </span>{" "}
                                {wishlist.size > 0 && (
                                    <>
                                        ve{" "}
                                        <strong>
                                            {wishlist.size} beğenine
                                        </strong>{" "}
                                    </>
                                )}
                                göre kuruldu.
                            </span>

                            <button
                                type="button"
                                className="ai-status-change"
                                onClick={() => setPickerOpen(true)}
                            >
                                değiştir
                            </button>
                        </div>
                    )}
                </div>

                <div className="explore-meta">
                    <button
                        type="button"
                        className={
                            "explore-refresh" + (loading ? " spinning" : "")
                        }
                        onClick={reload}
                        disabled={loading}
                    >
                        <RefreshCw size={12} /> YENİLE
                    </button>

                    <span className="explore-count">
                        {!hasMore && items.length
                            ? `${items.length} ürün · tümünü gördün`
                            : signedIn
                              ? `${items.length} ürün gösterildi · akış devam ediyor`
                              : `${remaining} ürün keşfedilmeyi bekliyor`}
                    </span>
                </div>
            </div>

            {!signedIn && (
                <div className="explore-notice">
                    <Info size={13} />
                    <span>
                        Seçimlerinin kaydedilmesi ve sana özel öneriler
                        için giriş yap.
                    </span>
                </div>
            )}

            {/*
               AnimatePresence: kart silindiğinde çıkış
               animasyonu (uçarak kaybolma) oynatılır.
               popLayout, kalan kartların yumuşak kaymasını
               sağlıyor.
            */}
            <div className="explore-grid">
                <AnimatePresence mode="popLayout">
                    {items.map((item, index) => (
                        <ExploreCard
                            key={item.product.product_id}
                            item={item}
                            index={index}
                            liked={wishlist.has(item.product.product_id)}
                            busy={busy.has(item.product.product_id)}
                            onLike={like}
                            onDislike={dislike}
                            onQuickBuy={openQuickBuy}
                            onOpen={(product) =>
                                console.log("ürün detayı:", product.product_id)
                            }
                            formatPrice={formatPrice}
                        />
                    ))}
                </AnimatePresence>
            </div>

            {loading && !items.length && (
                <div className="explore-loader">
                    <div className="loader" />
                    <p>Yeni ürünler getiriliyor...</p>
                </div>
            )}

            {/* Sonsuz akış: sentinel + yedek buton */}
            <div className="feed-sentinel" ref={sentinelRef} aria-hidden="true" />

            {items.length > 0 && hasMore && (
                <div className={"feed-more" + (loading ? " loading" : "")}>
                    <div className="feed-more-spinner">
                        <div className="loader" />
                    </div>

                    <button
                        type="button"
                        className="feed-more-btn"
                        onClick={loadMore}
                    >
                        DAHA FAZLA KEŞFET
                    </button>
                </div>
            )}

            {exhausted && (
                <div className="explore-exhausted">
                    <div className="empty-icon">
                        <Sparkles size={18} />
                    </div>
                    <h3>Şimdilik hepsi bu</h3>
                    <p>
                        Bu koleksiyondaki tüm ürünleri değerlendirdin.
                        Favorilerine göz atabilirsin.
                    </p>
                </div>
            )}

            <StylePickerModal
                open={pickerOpen}
                currentStyles={styles}
                onClose={() => setPickerOpen(false)}
                onConfirm={handleConfirm}
                onLimitReached={(max) =>
                    showToast({
                        title: `En fazla ${max} tarz`,
                        message:
                            "Yeni bir tarz eklemek için önce birini kaldır.",
                        tone: "info",
                    })
                }
            />

            <AiAnalyzing open={analyzing} label={analyzeLabel} />

            {/*
                Sepetin yerini alan alt bar. Favorilere bir
                şey eklenince beliriyor; "devam eden alışveriş"
                hissini o taşıyor.
            */}
            <WishlistBar
                items={wishlistItems}
                onOpen={() => console.log("favoriler açılıyor")}
                onQuickBuy={openQuickBuyProduct}
            />

            <QuickCheckout
                open={Boolean(checkoutItem)}
                item={checkoutItem}
                onClose={() => setCheckoutItem(null)}
                onOrdered={handleOrdered}
                formatPrice={formatPrice}
            />
        </section>
    );
}
