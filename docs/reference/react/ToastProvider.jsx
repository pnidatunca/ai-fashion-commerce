import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Check, Heart, Sparkles, Undo2, X } from "lucide-react";

/**
 * TOAST BİLDİRİMLERİ  (sağ alt köşe)
 *
 * Tasarım kararı: toast metnini BACKEND üretiyor
 * (`/api/interact` yanıtındaki `toast` alanı).
 *
 * Neden: "Anlaşıldı, bu tarz ürünler akışına
 * önceliklendirildi" yazıp hiçbir şey yapmamak kullanıcıyı
 * aldatmak olur. Mesajı gerçekten işi yapan katman
 * üretirse mesaj her zaman doğru kalır — backend
 * taste profile tazelemesini çalıştırdığı için bir sonraki
 * feed isteği o markayı gerçekten yükseltiyor.
 *
 * Sunucu mesaj döndürmezse aşağıdaki yedekler kullanılır.
 *
 * GERİ ALMA. Toast aynı zamanda geri alma yüzeyi:
 * `undoLabel` + `onUndo` verildiğinde bir buton ve kalan
 * süreyi gösteren ince bir çizgi çiziliyor. Ayrı bir
 * "emin misin?" penceresi açmaktan iyi — akışı kesmiyor,
 * yalnızca hata yapan kullanıcıya bir çıkış kapısı bırakıyor.
 */

const ToastContext = createContext(null);

const DURATION = 4200;
const MAX_VISIBLE = 3;

const ICONS = {
    success: Heart,
    neutral: Check,
    info: Sparkles,
    error: AlertCircle,
};

const toastVariants = {
    hidden: { opacity: 0, x: 40, scale: 0.96 },
    visible: {
        opacity: 1,
        x: 0,
        scale: 1,
        transition: { duration: 0.42, ease: [0.16, 1, 0.3, 1] },
    },
    exit: {
        opacity: 0,
        x: 30,
        scale: 0.97,
        transition: { duration: 0.3 },
    },
};


export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);

    /* Artan kimlik: iki toast aynı ms'de eklenirse
       Date.now() çakışır ve React key uyarısı verir. */
    const nextId = useRef(1);

    /* Kapatma zamanlayıcıları: geri alınınca iptal edilmeli */
    const timers = useRef(new Map());

    const dismiss = useCallback((id) => {
        const timer = timers.current.get(id);

        if (timer) {
            clearTimeout(timer);
            timers.current.delete(id);
        }

        setToasts((current) => current.filter((t) => t.id !== id));
    }, []);

    const showToast = useCallback(
        ({
            title,
            message = "",
            tone = "info",
            undoLabel,
            onUndo,
            duration,
        }) => {
            if (!title) return null;

            const id = nextId.current++;

            /*
               Geri alınabilir toast, geri alma penceresi
               kadar durmalı. Daha kısa durursa kullanıcı
               butonu kaçırır; daha uzun durursa artık
               çalışmayan bir buton göstermiş oluruz.
            */
            const life = duration || DURATION;

            setToasts((current) =>
                [
                    ...current,
                    { id, title, message, tone, undoLabel, onUndo, life },
                ].slice(-MAX_VISIBLE)
            );

            timers.current.set(
                id,
                setTimeout(() => dismiss(id), life)
            );

            return id;
        },
        [dismiss]
    );

    /* Unmount'ta bekleyen zamanlayıcıları temizle */
    useEffect(
        () => () => {
            timers.current.forEach((timer) => clearTimeout(timer));
            timers.current.clear();
        },
        []
    );

    const value = useMemo(() => ({ showToast, dismiss }), [showToast, dismiss]);

    return (
        <ToastContext.Provider value={value}>
            {children}

            <div
                className="toast-stack"
                aria-live="polite"
                aria-atomic="false"
            >
                <AnimatePresence mode="popLayout">
                    {toasts.map((toast) => {
                        const Icon = ICONS[toast.tone] || ICONS.info;

                        return (
                            <motion.div
                                key={toast.id}
                                layout
                                variants={toastVariants}
                                initial="hidden"
                                animate="visible"
                                exit="exit"
                                className={"toast " + toast.tone}
                            >
                                <div className="toast-icon">
                                    <Icon
                                        size={13}
                                        fill={
                                            toast.tone === "success"
                                                ? "currentColor"
                                                : "none"
                                        }
                                    />
                                </div>

                                <div className="toast-body">
                                    <strong>{toast.title}</strong>

                                    {toast.message && (
                                        <span>{toast.message}</span>
                                    )}

                                    {toast.undoLabel && (
                                        <button
                                            type="button"
                                            className="toast-undo"
                                            onClick={() => {
                                                toast.onUndo?.();
                                                dismiss(toast.id);
                                            }}
                                        >
                                            <Undo2 size={11} />
                                            {toast.undoLabel}
                                        </button>
                                    )}
                                </div>

                                <button
                                    type="button"
                                    className="toast-close"
                                    onClick={() => dismiss(toast.id)}
                                    aria-label="Bildirimi kapat"
                                >
                                    <X size={12} />
                                </button>

                                {/*
                                    Kalan süre çizgisi. Geri alma
                                    butonunun ne kadar süre daha
                                    çalışacağını göstermenin en
                                    sessiz yolu.
                                */}
                                {toast.undoLabel && (
                                    <motion.span
                                        className="toast-timer"
                                        initial={{ scaleX: 1 }}
                                        animate={{ scaleX: 0 }}
                                        transition={{
                                            duration: toast.life / 1000,
                                            ease: "linear",
                                        }}
                                    />
                                )}
                            </motion.div>
                        );
                    })}
                </AnimatePresence>
            </div>
        </ToastContext.Provider>
    );
}


export function useToast() {
    const context = useContext(ToastContext);

    if (!context) {
        throw new Error("useToast, ToastProvider içinde kullanılmalı.");
    }

    return context;
}


/* Sunucu mesaj döndürmezse kullanılacak yedekler */

export const FALLBACK_TOASTS = {
    LIKE: {
        title: "Favorilerine eklendi",
        message: "Anlaşıldı, bu tarz ürünler akışına önceliklendirildi.",
        tone: "success",
    },
    DISLIKE: {
        title: "Anlaşıldı, bu tarz elendi",
        message: "Bu ürün ve benzer kesimler geri planda kalacak.",
        tone: "neutral",
    },
    UNLIKE: {
        title: "Favorilerden çıkarıldı",
        message: "Ürün akışına geri dönebilir.",
        tone: "info",
    },
    QUICK_BUY: {
        title: "Siparişin alındı",
        message: "Benzer parçalar akışında öne çıkarılacak.",
        tone: "success",
    },
    ERROR: {
        title: "Kaydedilemedi",
        message: "Bağlantını kontrol edip tekrar dene.",
        tone: "error",
    },
};
