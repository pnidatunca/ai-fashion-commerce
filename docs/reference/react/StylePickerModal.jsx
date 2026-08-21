import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import {
    MAX_SELECTED_STYLES,
    fetchArchetypes,
    hasSeenStylePicker,
    markStylesSeen,
} from "./auraApi";

/**
 * 8 TARZLI VISUAL STYLE PICKER  (Cold Start)
 *
 * Form yok, soru yok: 8 görsel, 1-3 dokunuş.
 *
 * Neden gerekli: yeni kullanıcının hiç etkileşimi yoktur.
 * Collaborative filtering bu noktada çalışmaz — öğreneceği
 * geçmiş yoktur. Tek/çoklu tarz seçimi ilk saniyeden
 * itibaren anlamlı sıralama üretir.
 *
 * Neden 3 taneye kadar: tek tarz fazla dar (özellikle
 * katalogda az ürünü olan tarzlarda akış boşalır), 3'ten
 * fazlası "her şey" demektir ve kişiselleştirmeyi anlamsız
 * kılar.
 *
 * KARTLARDA GERÇEK ÜRÜN SAYISI YAZAR. Katalog kapsamı çok
 * dengesiz (ölçüldü: athleisure ~87, y2k ~0). Kullanıcı
 * "Y2K" seçip boş bir akışla karşılaşırsa sistemin bozuk
 * olduğunu düşünür. Sayıyı önceden göstermek hem dürüst
 * hem de daha iyi seçim yapmasını sağlıyor.
 */

const THIN_TOTAL_THRESHOLD = 25;


/* Framer Motion varyantları */

const overlayVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { duration: 0.3 } },
    exit: { opacity: 0, transition: { duration: 0.25 } },
};

const panelVariants = {
    hidden: { opacity: 0, y: 24, scale: 0.98 },
    visible: {
        opacity: 1,
        y: 0,
        scale: 1,
        transition: {
            duration: 0.45,
            ease: [0.2, 0.8, 0.2, 1],
            // Kartlar panelden sonra kademeli girsin
            staggerChildren: 0.05,
            delayChildren: 0.12,
        },
    },
    exit: { opacity: 0, y: 16, scale: 0.99, transition: { duration: 0.22 } },
};

const cardVariants = {
    hidden: { opacity: 0, y: 18 },
    visible: {
        opacity: 1,
        y: 0,
        transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] },
    },
};


export default function StylePickerModal({
    open,
    onClose,
    onConfirm,
    currentStyles = [],
    onLimitReached,
}) {
    const [options, setOptions] = useState([]);
    const [draft, setDraft] = useState(currentStyles);
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);

    /* Modal her açıldığında kayıtlı seçimden başlasın */
    useEffect(() => {
        if (open) setDraft(currentStyles);
    }, [open, currentStyles]);

    useEffect(() => {
        if (!open || options.length) return;

        let cancelled = false;

        fetchArchetypes()
            .then((data) => {
                if (!cancelled) setOptions(data.options || []);
            })
            .catch((cause) => {
                if (!cancelled) setError(cause.message);
            });

        return () => {
            cancelled = true;
        };
    }, [open, options.length]);

    /* ESC — yalnızca ilk gösterim değilse */
    useEffect(() => {
        if (!open || !hasSeenStylePicker()) return;

        const onKeyDown = (event) => {
            if (event.key === "Escape") onClose?.();
        };

        document.addEventListener("keydown", onKeyDown);
        return () => document.removeEventListener("keydown", onKeyDown);
    }, [open, onClose]);


    const atLimit = draft.length >= MAX_SELECTED_STYLES;

    /**
     * Seçili tarzların BİRLEŞİK havuzu.
     *
     * Tek tek toplamak kabaca doğru: aynı ürün iki tarzda da
     * eşiği geçebilir, yani gerçek sayı biraz daha az.
     * Sunucu /api/initial-style yanıtında tekil sayıyı
     * döndürüyor; burada yalnızca uyarı eşiği için kaba
     * bir tahmin yeterli.
     */
    const poolEstimate = useMemo(
        () =>
            options
                .filter((option) => draft.includes(option.id))
                .reduce(
                    (sum, option) => sum + Number(option.pool_count || 0),
                    0
                ),
        [options, draft]
    );

    const thinOnes = useMemo(
        () =>
            options.filter(
                (option) => draft.includes(option.id) && option.is_thin
            ),
        [options, draft]
    );

    const showThinWarning =
        draft.length > 0 && poolEstimate < THIN_TOTAL_THRESHOLD;


    function toggle(styleId) {
        setDraft((current) => {
            if (current.includes(styleId)) {
                return current.filter((id) => id !== styleId);
            }

            if (current.length >= MAX_SELECTED_STYLES) {
                /*
                   Sessizce en eskiyi atmıyoruz: kullanıcının
                   kendi seçimini kaybetmesi kötü bir sürpriz.
                   Sebebi söylüyoruz.
                */
                onLimitReached?.(MAX_SELECTED_STYLES);
                return current;
            }

            return [...current, styleId];
        });
    }

    async function confirm() {
        if (busy || !draft.length) return;

        setBusy(true);
        try {
            await onConfirm?.(draft);
        } finally {
            setBusy(false);
        }
    }

    function skip() {
        markStylesSeen();
        onClose?.();
    }

    return (
        <AnimatePresence>
            {open && (
                <motion.div
                    className="archetype-overlay open"
                    variants={overlayVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    onClick={(event) => {
                        /*
                           İlk gösterimde dışa tıklayınca
                           kapanmasın: kullanıcı kazara
                           kapatıp AI deneyimini kaçırmasın.
                        */
                        if (
                            event.target === event.currentTarget &&
                            hasSeenStylePicker()
                        ) {
                            onClose?.();
                        }
                    }}
                >
                    <motion.div
                        className="archetype-panel"
                        variants={panelVariants}
                    >
                        <button
                            type="button"
                            className="archetype-skip"
                            onClick={skip}
                        >
                            Şimdilik geç
                        </button>

                        <div className="archetype-head">
                            <span className="ai-chip">
                                <span className="ai-dot" />
                                AURA AI
                            </span>

                            <h2>
                                Tarzını <em>birkaç dokunuşta</em> tanıyalım
                            </h2>

                            <p>
                                Sana en yakın{" "}
                                <strong>1–{MAX_SELECTED_STYLES} tarzı</strong>{" "}
                                seç. Akışın buna göre kurulur, sonra
                                istediğin zaman değiştirirsin.
                            </p>
                        </div>

                        {error ? (
                            <p className="explore-error">
                                Stil seçenekleri yüklenemedi: {error}
                            </p>
                        ) : (
                            <div
                                className={
                                    "archetype-grid" +
                                    (atLimit ? " at-limit" : "")
                                }
                            >
                                {options.map((option) => {
                                    const order = draft.indexOf(option.id);
                                    const chosen = order !== -1;

                                    return (
                                        <motion.button
                                            key={option.id}
                                            type="button"
                                            variants={cardVariants}
                                            whileHover={{ y: -4 }}
                                            whileTap={{ scale: 0.98 }}
                                            className={
                                                "archetype-card" +
                                                (chosen ? " chosen" : "")
                                            }
                                            aria-pressed={chosen}
                                            onClick={() => toggle(option.id)}
                                        >
                                            <div className="archetype-card-image">
                                                <img
                                                    src={option.image_url}
                                                    alt={option.label}
                                                    loading="lazy"
                                                />

                                                <motion.span
                                                    className="archetype-check"
                                                    animate={{
                                                        opacity: chosen ? 1 : 0,
                                                        scale: chosen ? 1 : 0.6,
                                                    }}
                                                    transition={{
                                                        duration: 0.28,
                                                        ease: [0.2, 0.9, 0.3, 1.4],
                                                    }}
                                                >
                                                    {chosen ? order + 1 : ""}
                                                </motion.span>
                                            </div>

                                            <div className="archetype-card-body">
                                                <strong>
                                                    <span className="archetype-emoji">
                                                        {option.emoji}
                                                    </span>
                                                    {option.short_label}
                                                </strong>

                                                <span className="archetype-card-tagline">
                                                    {option.tagline}
                                                </span>

                                                <p>{option.description}</p>

                                                <div
                                                    className={
                                                        "archetype-pool" +
                                                        (option.is_thin
                                                            ? " thin"
                                                            : "")
                                                    }
                                                >
                                                    <span>
                                                        {option.pool_count} PARÇA
                                                    </span>
                                                    {option.is_thin && (
                                                        <span>AZ SEÇENEK</span>
                                                    )}
                                                </div>
                                            </div>
                                        </motion.button>
                                    );
                                })}
                            </div>
                        )}

                        <AnimatePresence>
                            {showThinWarning && (
                                <motion.p
                                    className="archetype-warning"
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: "auto" }}
                                    exit={{ opacity: 0, height: 0 }}
                                >
                                    <span aria-hidden="true">ⓘ</span>
                                    <span>
                                        Bu seçimde katalogda yaklaşık{" "}
                                        <strong>{poolEstimate} parça</strong> var.
                                        {thinOnes.length > 0 && (
                                            <>
                                                {" "}
                                                {thinOnes
                                                    .map((o) => o.short_label)
                                                    .join(", ")}{" "}
                                                için ürün az.
                                            </>
                                        )}{" "}
                                        İkinci bir tarz eklersen akışın
                                        zenginleşir.
                                    </span>
                                </motion.p>
                            )}
                        </AnimatePresence>

                        <div className="archetype-footer">
                            <span className="archetype-counter">
                                {draft.length === 0 ? (
                                    "Henüz seçim yapmadın"
                                ) : (
                                    <>
                                        <strong>{draft.length}</strong> /{" "}
                                        {MAX_SELECTED_STYLES} tarz seçildi
                                    </>
                                )}
                            </span>

                            <button
                                type="button"
                                className="auth-main-btn archetype-confirm"
                                disabled={!draft.length || busy}
                                onClick={confirm}
                            >
                                {busy ? "HAZIRLANIYOR..." : "AKIŞIMI HAZIRLA"}
                            </button>
                        </div>
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
