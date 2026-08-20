import { AnimatePresence, motion } from "framer-motion";
import { Zap } from "lucide-react";

/**
 * WISHLIST ODAKLI ALT BAR
 *
 * Sepet kaldırıldığı için "devam eden alışveriş" hissini
 * bu bar taşıyor. Favorilere bir şey eklenince beliriyor,
 * son eklenenlerin küçük görsellerini ve tek dokunuşla
 * hızlı satın alma noktasını gösteriyor.
 *
 * Mobilde aşağıda durması önemli: baş parmak orada.
 *
 * "HIZLI AL" en son eklenen favoriyi satın almaya götürüyor.
 * Sepet olmadığı için "hepsini al" diye bir eylem yok; en
 * yeni niyet en olası niyet.
 */

const barVariants = {
    hidden: { opacity: 0, y: 90 },
    visible: {
        opacity: 1,
        y: 0,
        transition: { duration: 0.4, ease: [0.2, 0.8, 0.2, 1] },
    },
    exit: { opacity: 0, y: 90, transition: { duration: 0.28 } },
};


export default function WishlistBar({
    items = [],
    onOpen,
    onQuickBuy,
}) {
    const count = items.length;

    const latest = items[0]?.product;

    return (
        <AnimatePresence>
            {count > 0 && (
                <motion.div
                    className="wishlist-bar"
                    variants={barVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                >
                    <button
                        type="button"
                        className="wishlist-bar-main"
                        onClick={onOpen}
                    >
                        <span className="wishlist-bar-thumbs">
                            {items.slice(0, 3).map((entry) => (
                                <motion.img
                                    key={entry.product_id}
                                    layout
                                    initial={{ opacity: 0, scale: 0.8 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    src={entry.product?.image_url}
                                    alt=""
                                    loading="lazy"
                                />
                            ))}
                        </span>

                        <span className="wishlist-bar-text">
                            <strong>{count} favori</strong>
                            <small>
                                {latest
                                    ? (
                                          latest.title_tr || latest.title || ""
                                      ).slice(0, 42)
                                    : "Listeni aç"}
                            </small>
                        </span>
                    </button>

                    <button
                        type="button"
                        className="wishlist-bar-buy"
                        onClick={() => latest && onQuickBuy?.(latest)}
                        disabled={!latest}
                    >
                        <Zap size={13} />
                        <span className="wishlist-bar-buy-text">HIZLI AL</span>
                    </button>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
