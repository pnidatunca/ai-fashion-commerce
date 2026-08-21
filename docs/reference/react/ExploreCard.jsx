import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Heart, Sparkles, ThumbsDown, Zap } from "lucide-react";

import { queueView } from "./auraApi";

/**
 * AI BADGE'Lİ KEŞFET KARTI
 *
 * Kart iki soruyu birlikte cevaplar:
 *   1. Bu ürün ne?
 *   2. Bu ürün NEDEN burada?
 *
 * İkinciyi üç işaret taşıyor:
 *   - match_label   "%86 AI Stil Uyumu"  (glassmorphic badge, skor ≥ 72)
 *   - reason_label  "Seçtiğin 'Streetwear' tarzı ve en çok
 *                    beğendiğin 'Siyah' tonuna göre önerildi."
 *   - KEŞFET etiketi  bu ürünü AI önermedi, deneme slotu
 *
 * Eşikleri frontend HESAPLAMAZ. Backend hangi etiketi
 * göstereceğine karar verip hazır metni gönderir
 * (style_engine.build_match_display). Eşikler iki yerde
 * durursa gün gelir biri güncellenmez.
 */

const VIEW_DWELL_MS = 800;

/* Yüksek uyumda badge daha güçlü parlar */
const HIGH_MATCH = 90;


const cardVariants = {
    hidden: { opacity: 0, y: 22, scale: 0.97 },

    visible: (index) => ({
        opacity: 1,
        y: 0,
        scale: 1,
        transition: {
            duration: 0.5,
            ease: [0.16, 1, 0.3, 1],
            // Kademeli giriş: her kart 55 ms sonra
            delay: Math.min(index, 11) * 0.055,
        },
    }),

    /*
       "Beğenmedim" çıkışı: kart SOLA KAYARAK gidiyor
       (swipe-left). Yumuşak ama fark edilir — kullanıcı
       kartın elendiğini anlamalı.
    */
    exit: {
        opacity: 0,
        x: "-110%",
        scale: 0.94,
        transition: { duration: 0.4, ease: [0.4, 0, 0.6, 0.2] },
    },
};


export default function ExploreCard({
    item,
    index,
    liked,
    busy,
    onOpen,
    onLike,
    onDislike,
    onQuickBuy,
    formatPrice,
}) {
    const { product } = item;
    const cardRef = useRef(null);

    /*
       VIEW kaydı.

       İki filtre var, ikisi de veri kalitesi için:
         1. Kart en az %50 görünür ve 800 ms ekranda kalmalı.
            Hızlı kaydırmada onlarca kart ekrandan geçer;
            hepsini "gördü" saymak eğitim verisini bozar.
         2. Aynı ürün oturum başına bir kez (auraApi içinde).
    */
    useEffect(() => {
        const node = cardRef.current;

        if (!node || typeof IntersectionObserver === "undefined") {
            return;
        }

        let timer = null;

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (!entry.isIntersecting) {
                    clearTimeout(timer);
                    return;
                }

                timer = setTimeout(() => {
                    queueView({
                        productId: product.product_id,
                        source: "explore",
                        position: index,
                        matchScore: item.match_score,
                    });
                }, VIEW_DWELL_MS);
            },
            { threshold: 0.5 }
        );

        observer.observe(node);

        return () => {
            clearTimeout(timer);
            observer.disconnect();
        };
    }, [product.product_id, index, item.match_score]);


    const title = product.title_tr || product.title || "Ürün";
    const discount = Number(product.discount_percent || 0);
    const isHigh = Number(item.match_score || 0) >= HIGH_MATCH;

    const hasOldPrice =
        product.list_price &&
        Number(product.list_price) > Number(product.price || 0);

    return (
        <motion.article
            ref={cardRef}
            layout
            custom={index}
            variants={cardVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className={"explore-card" + (liked ? " liked" : "")}
            data-product-id={product.product_id}
            data-matched-style={item.matched_style || undefined}
            data-exploration={item.is_exploration ? "1" : undefined}
        >
            <div
                className="explore-card-image"
                onClick={() => onOpen?.(product)}
            >
                <img
                    src={product.image_url}
                    alt={title}
                    loading="lazy"
                    onError={(event) => {
                        event.currentTarget.src =
                            "https://placehold.co/600x800?text=AURA";
                    }}
                />

                {discount > 0 && (
                    <span className="explore-badge">-{discount}%</span>
                )}

                {/* Sağ üst köşe: cam efektli AI badge ya da keşif işareti */}
                {item.match_label ? (
                    <motion.span
                        className={
                            "explore-match" + (isHigh ? " high" : "")
                        }
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.12 + index * 0.03 }}
                    >
                        <span className="ai-dot" />
                        {item.match_label}
                    </motion.span>
                ) : item.is_exploration ? (
                    <span className="explore-explore-tag">KEŞFET</span>
                ) : null}

                <span className="explore-liked-badge">
                    <Heart size={9} fill="currentColor" />
                    FAVORİDE
                </span>
            </div>

            <div className="explore-card-body">
                {/*
                    AI Neden Önerdi? — Explainable AI etiketi.
                    Metni backend üretiyor; yalnızca gerçekten
                    tetiklenmiş sinyaller cümleye giriyor.
                */}
                {item.reason_label && (
                    <span className="explore-reason">
                        <Sparkles size={9} />
                        {item.reason_label}
                    </span>
                )}

                {product.brand && (
                    <div className="explore-card-brand">{product.brand}</div>
                )}

                <h4 className="explore-card-title">{title}</h4>

                <div className="explore-card-price">
                    <span className="current-price">
                        {formatPrice(product.price)}
                    </span>

                    {hasOldPrice && (
                        <span className="old-price">
                            {formatPrice(product.list_price)}
                        </span>
                    )}
                </div>
            </div>

            {/*
                SEPET YOK. Kartta ya kalp (Wishlist) ya da
                doğrudan tek tıkla satın alma var.
            */}
            {onQuickBuy && (
                <button
                    type="button"
                    className="card-quick-buy"
                    onClick={() => onQuickBuy(item, index)}
                    disabled={busy || !product.price}
                >
                    <Zap size={12} />
                    {product.price ? "TEK TIKLA AL" : "FİYAT YOK"}
                </button>
            )}

            <div className="explore-actions">
                {/*
                   Beğenmedim: önce sunucuya yazılır, SONRA kart
                   çıkar. Ters sırada olsa kaydedilmemiş bir
                   DISLIKE'ta kart kaybolur ama ürün geri gelir
                   ve kullanıcı aynı ürünü tekrar görür.
                */}
                {/*
                    Kırık kalp yerine ThumbsDown: "beğenmedim"
                    bir his değil bir değerlendirme, el işareti
                    bunu daha net anlatıyor.
                */}
                <motion.button
                    type="button"
                    className="explore-action explore-action-dislike"
                    disabled={busy}
                    whileTap={{ scale: 0.94 }}
                    onClick={() => onDislike?.(item, index)}
                    aria-label="Bu ürünü beğenmedim"
                >
                    <ThumbsDown size={14} />
                    BEĞENMEDİM
                </motion.button>

                {/* Kalp: iyimser arayüz — anında kırmızı,
                    istek başarısız olursa geri alınır. */}
                <motion.button
                    type="button"
                    className={
                        "explore-action explore-action-like" +
                        (liked ? " active" : "")
                    }
                    disabled={busy}
                    whileTap={{ scale: 0.94 }}
                    onClick={() => onLike?.(item, index)}
                    aria-label={
                        liked ? "Favorilerden çıkar" : "Favorilere ekle"
                    }
                >
                    <motion.span
                        animate={liked ? { scale: [1, 1.45, 1] } : { scale: 1 }}
                        transition={{ duration: 0.45 }}
                        style={{ display: "inline-flex" }}
                    >
                        <Heart
                            size={14}
                            fill={liked ? "currentColor" : "none"}
                        />
                    </motion.span>
                    {liked ? "FAVORİDE" : "BEĞENDİM"}
                </motion.button>
            </div>
        </motion.article>
    );
}
