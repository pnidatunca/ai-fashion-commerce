import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

/**
 * AI ANALİZ EKRANI
 *
 * Tarz seçildiği an ~1 saniye görünür.
 *
 * Neden var: seçim ile yeni akış arasında görsel bir eşik
 * olmazsa kullanıcı bir şey olduğunu anlamaz. Adım
 * metinleri uydurma değil — arka planda gerçekten olan
 * işlerin (profil kaydı, katalog sorgusu, sıralama) adları.
 *
 * Ekran EN AZ minDuration kadar kalır ama işi de bekler:
 * boş bir akış göstermek 200 ms fazla beklemekten kötüdür.
 */

const DEFAULT_STEPS = [
    "Stil profili oluşturuluyor",
    "Katalog taranıyor",
    "Akışın hazırlanıyor",
];


export default function AiAnalyzing({
    open,
    label = "Tarzın analiz ediliyor...",
    steps = DEFAULT_STEPS,
}) {
    const [doneCount, setDoneCount] = useState(0);

    useEffect(() => {
        if (!open) {
            setDoneCount(0);
            return;
        }

        const timers = steps.map((_, index) =>
            setTimeout(
                () =>
                    setDoneCount((current) =>
                        Math.max(current, index + 1)
                    ),
                180 + index * 300
            )
        );

        return () => timers.forEach(clearTimeout);
    }, [open, steps]);

    return (
        <AnimatePresence>
            {open && (
                <motion.div
                    className="ai-analyzing open"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.3 }}
                    aria-live="polite"
                    aria-busy="true"
                >
                    <div className="ai-analyzing-inner">
                        {/* Üç halka: eş zamanlı olmayan dönüş */}
                        <div className="ai-orbit">
                            <motion.span
                                animate={{ rotate: 360 }}
                                transition={{
                                    duration: 1.1,
                                    repeat: Infinity,
                                    ease: "linear",
                                }}
                                style={{ borderTopColor: "var(--ai)" }}
                            />
                            <motion.span
                                animate={{ rotate: -360 }}
                                transition={{
                                    duration: 1.5,
                                    repeat: Infinity,
                                    ease: "linear",
                                }}
                                style={{
                                    inset: 11,
                                    borderRightColor:
                                        "rgba(255,255,255,.55)",
                                }}
                            />
                            <motion.span
                                animate={{ rotate: 360 }}
                                transition={{
                                    duration: 0.8,
                                    repeat: Infinity,
                                    ease: "linear",
                                }}
                                style={{
                                    inset: 22,
                                    borderBottomColor: "var(--ai)",
                                }}
                            />
                        </div>

                        <motion.p
                            className="ai-analyzing-text"
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 }}
                        >
                            {label}
                        </motion.p>

                        <div className="ai-analyzing-steps">
                            {steps.map((step, index) => (
                                <motion.span
                                    key={step}
                                    className={
                                        index < doneCount ? "done" : ""
                                    }
                                    initial={{ opacity: 0, x: -8 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{
                                        delay: 0.15 + index * 0.12,
                                    }}
                                >
                                    {step}
                                </motion.span>
                            ))}
                        </div>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}


/**
 * İşi yaparken analiz ekranını gösteren yardımcı.
 *
 * @example
 *   await runWithAnalyzing(setAnalyzing, async () => {
 *       await saveInitialStyles(styles);
 *       await reload();
 *   });
 */
export async function runWithAnalyzing(
    setOpen,
    work,
    { minDuration = 1100, maxDuration = 5000 } = {}
) {
    setOpen(true);

    const minimum = new Promise((resolve) =>
        setTimeout(resolve, minDuration)
    );

    const guard = new Promise((resolve) =>
        setTimeout(resolve, maxDuration)
    );

    try {
        /*
           Race: iş + minimum süre birlikte biter, ama guard
           süresi aşılırsa ekran yine kapanır. Ağ takılırsa
           kullanıcı sonsuza kadar beklemez.
        */
        await Promise.race([Promise.all([work(), minimum]), guard]);
    } finally {
        setOpen(false);
    }
}
