import { useCallback, useEffect, useRef, useState } from "react";

import {
    fetchExplore,
    fetchWishlist,
    getStoredUser,
    readStoredStyles,
    sendInteraction,
    writeStoredStyles,
} from "./auraApi";

import { FALLBACK_TOASTS, useToast } from "./ToastProvider";

/**
 * KEŞFET AKIŞI HOOK'U  (cursor tabanlı sonsuz akış)
 *
 * Çalışan sistemin karşılığı: frontend/app.js explore bölümü.
 *
 * İki koleksiyon yönetiliyor:
 *   - items   ekranda duran kartlar
 *   - buffer  önden çekilmiş yedek kartlar (ref'te)
 *
 * Yedek havuzu neden var: "beğenmedim" sonrası kartın yerine
 * yenisi ANINDA gelmeli. Her silmede yeni istek atmak gözle
 * görülür bir boşluk yaratır.
 */

const PAGE_SIZE = 8;
const BUFFER_MIN = 4;

/*
   BEĞENMEDİM'İ GERİ ALMA PENCERESİ.

   Yanlışlıkla basmak çok kolay ve DISLIKE kalıcı bir karar:
   ürün bir daha hiç gösterilmiyor, üstüne benzer kategoriye
   de eksi puan yazılıyor. Bu yüzden sunucuya yazmayı bu
   süre kadar geciktiriyoruz.

   Neden "yaz sonra sil" değil: user_interactions append-only
   bir olay kaydı ve eğitim verisinin değeri buna dayanıyor.
   Ayrıca yanlışlıkla basılan bir tuş anlamlı bir ML sinyali
   değil — hiç yazılmaması daha doğru.

   Süre neden 5 saniye: geri alma isteği ilk bir iki saniyede
   geliyor. Daha uzun tutmak akışı yavaşlatır, kullanıcı
   kararın işlenip işlenmediğini bilemez.
*/
const UNDO_WINDOW_MS = 5000;


export function useExplore() {
    const { showToast } = useToast();

    const [items, setItems] = useState([]);
    const [meta, setMeta] = useState(null);
    const [remaining, setRemaining] = useState(0);
    const [loading, setLoading] = useState(false);
    const [exhausted, setExhausted] = useState(false);
    const [hasMore, setHasMore] = useState(true);

    const [wishlist, setWishlist] = useState(() => new Set());
    const [busy, setBusy] = useState(() => new Set());

    /*
       Alt bar için tam kayıtlar.

       wishlist yalnızca id tutuyor (kalpleri işaretlemeye
       yeter) ama alt bar küçük görsel ve başlık gösteriyor.
       En yeni başta: bar "az önce ne beğendim" sorusunu
       yanıtlıyor.
    */
    const [wishlistItems, setWishlistItems] = useState([]);

    const [styles, setStyles] = useState(readStoredStyles);

    /* Render'ı etkilemeyen durumlar ref'te */
    const buffer = useRef([]);
    const cursor = useRef(null);
    const hasMoreRef = useRef(true);

    /*
       YARIŞ KOŞULU KORUMASI.

       İki dolum işlemi aynı anda çalışırsa ikisi de AYNI
       cursor değerini okur, aynı isteği atar ve aynı ürünler
       iki kez akışa girer. Gerçekten oluşuyor: ilk parti
       çizildikten sonra yedek arka planda dolduruluyor;
       kullanıcı o sırada kaydırırsa ikinci dolum devreye
       giriyor.

       Çözüm: dolumları zincirle.
    */
    const fillChain = useRef(null);

    /*
       Geri alma penceresi bekleyen beğenmedimler.

       productId -> { item, index, replacement, timer }
    */
    const pendingDislikes = useRef(new Map());


    const fillOnce = useCallback(async (minimum) => {
        let guard = 0;

        while (
            buffer.current.length < minimum &&
            hasMoreRef.current &&
            guard < 5
        ) {
            guard++;

            const data = await fetchExplore({
                limit: PAGE_SIZE,
                cursor: cursor.current,
                styles: readStoredStyles(),
            });

            cursor.current = data.meta?.next_cursor || null;
            hasMoreRef.current = Boolean(data.meta?.has_more);

            setHasMore(hasMoreRef.current);
            setRemaining(data.remaining ?? 0);
            setMeta(data.meta || null);

            /*
               Sunucu kendi kayıtlı tercihini kullanmış olabilir
               (başka cihazda seçilmiş ya da yerel depo
               temizlenmiş). Arayüzün akışla çelişmemesi için
               sunucuyu benimsiyoruz.
            */
            const serverStyles = data.meta?.selected_styles || [];

            if (
                serverStyles.length &&
                serverStyles.join() !== readStoredStyles().join()
            ) {
                writeStoredStyles(serverStyles);
                setStyles(serverStyles);
            }

            const incoming = data.items || [];

            if (!incoming.length) {
                hasMoreRef.current = false;
                setHasMore(false);
                break;
            }

            /*
               İkinci koruma katmanı: zaten ekranda veya
               yedekte olan bir öğeyi almıyoruz. Cursor bunu
               halletmeli ama ekranda tekrar eden kart çok
               görünür bir hata; iki kat güvenlik ucuz.
            */
            const known = new Set([
                ...buffer.current.map((i) => i.product.product_id),
            ]);

            const fresh = incoming.filter(
                (item) => !known.has(item.product.product_id)
            );

            if (!fresh.length) {
                hasMoreRef.current = false;
                setHasMore(false);
                break;
            }

            buffer.current.push(...fresh);
        }

        return buffer.current.length;
    }, []);


    const ensureBuffer = useCallback(
        (minimum) => {
            fillChain.current = (fillChain.current || Promise.resolve())
                .then(() => fillOnce(minimum))
                .catch((error) => {
                    console.warn("Yedek doldurulamadı:", error);
                    return buffer.current.length;
                });

            return fillChain.current;
        },
        [fillOnce]
    );


    /* -----------------------------------------------------
       YÜKLEME
    ----------------------------------------------------- */

    const load = useCallback(
        async ({ reset = false } = {}) => {
            if (loading) return;

            setLoading(true);

            if (reset) {
                cursor.current = null;
                hasMoreRef.current = true;
                fillChain.current = null;
                buffer.current = [];
                setItems([]);
                setExhausted(false);
                setHasMore(true);
            }

            try {
                /*
                   YALNIZCA EKRANA KOYACAĞIMIZ KADAR BEKLİYORUZ.

                   Önceden yedek havuz da dolana kadar
                   bekleniyordu (8+4=12 öğe) ve bu iki API
                   turu demekti; Keşfet bölümü saniyelerce
                   boş kalıyordu.
                */
                await ensureBuffer(PAGE_SIZE);

                const batch = buffer.current.splice(0, PAGE_SIZE);

                if (batch.length) {
                    setItems((current) =>
                        reset ? batch : [...current, ...batch]
                    );
                } else if (reset) {
                    setExhausted(true);
                }

                /* Yedeği arkada doldur — await YOK */
                ensureBuffer(BUFFER_MIN);
            } catch (error) {
                console.error("Keşfet yüklenemedi:", error);
                hasMoreRef.current = false;
                setHasMore(false);
            } finally {
                setLoading(false);
            }
        },
        [loading, ensureBuffer]
    );


    /* -----------------------------------------------------
       WISHLIST
    ----------------------------------------------------- */

    const loadWishlist = useCallback(async () => {
        if (!getStoredUser()) {
            setWishlist(new Set());
            setWishlistItems([]);
            return;
        }

        try {
            const records = await fetchWishlist();

            setWishlist(new Set(records.map((entry) => entry.product_id)));
            setWishlistItems(records);
        } catch (error) {
            console.error("Favoriler yüklenemedi:", error);
        }
    }, []);


    useEffect(() => {
        (async () => {
            await loadWishlist();
            await load({ reset: true });
        })();
        // Bilinçli olarak yalnızca mount'ta.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);


    /* -----------------------------------------------------
       KALP
    ----------------------------------------------------- */

    const like = useCallback(
        async (item, index) => {
            const productId = item.product.product_id;

            if (!getStoredUser()) {
                showToast({
                    title: "Giriş gerekli",
                    message: "Favorilerine eklemek için giriş yap.",
                    tone: "info",
                });
                return;
            }

            const alreadyLiked = wishlist.has(productId);

            /* İyimser arayüz: önce işaretle */
            setWishlist((current) => {
                const next = new Set(current);
                if (alreadyLiked) next.delete(productId);
                else next.add(productId);
                return next;
            });

            setWishlistItems((current) =>
                alreadyLiked
                    ? current.filter((entry) => entry.product_id !== productId)
                    : [
                          { product_id: productId, product: item.product },
                          ...current.filter(
                              (entry) => entry.product_id !== productId
                          ),
                      ]
            );

            try {
                const response = await sendInteraction({
                    productId,
                    type: alreadyLiked ? "UNLIKE" : "LIKE",
                    source: "explore",
                    position: index,
                    matchScore: item.match_score,
                    matchedStyle: item.matched_style,
                });

                showToast(
                    response?.toast ||
                        FALLBACK_TOASTS[alreadyLiked ? "UNLIKE" : "LIKE"]
                );
            } catch (error) {
                console.error("Favori güncellenemedi:", error);

                /* Başarısız: işareti geri al */
                setWishlist((current) => {
                    const next = new Set(current);
                    if (alreadyLiked) next.add(productId);
                    else next.delete(productId);
                    return next;
                });

                setWishlistItems((current) =>
                    alreadyLiked
                        ? [
                              { product_id: productId, product: item.product },
                              ...current,
                          ]
                        : current.filter(
                              (entry) => entry.product_id !== productId
                          )
                );

                showToast(FALLBACK_TOASTS.ERROR);
            }
        },
        [wishlist, showToast]
    );


    /* -----------------------------------------------------
       BEĞENMEDİM
    ----------------------------------------------------- */

    /**
     * Geri alma süresi dolunca sunucuya yazar.
     *
     * Buraya gelmek "kullanıcı kararında ısrar etti" demek;
     * kalıcı kara liste kaydı ancak bu noktada oluşuyor.
     */
    const commitDislike = useCallback(
        async (productId) => {
            const pending = pendingDislikes.current.get(productId);

            if (!pending) return;

            clearTimeout(pending.timer);
            pendingDislikes.current.delete(productId);

            try {
                await sendInteraction({
                    productId,
                    type: "DISLIKE",
                    source: "explore",
                    position: pending.index,
                    matchScore: pending.item.match_score,
                    matchedStyle: pending.item.matched_style,
                });
            } catch (error) {
                /*
                   Kart çoktan gitti; geri getirmek daha kafa
                   karıştırıcı olurdu. Ürün bu oturumda
                   görünmeyecek, sonraki oturumda yeniden
                   çıkacak — kabul edilebilir bir bozulma.
                */
                console.error("Beğenmedim kaydedilemedi:", error);
                showToast(FALLBACK_TOASTS.ERROR);
            }
        },
        [showToast]
    );


    /**
     * Beğenmedim'i geri alır.
     *
     * Sunucuya hiçbir şey yazılmadığı için bu tamamen arayüz
     * işi: yerine gelen kart çıkarılıyor, eski kart eski
     * konumuna geri konuyor, yedek de bozulmuyor.
     */
    const undoDislike = useCallback(
        (productId) => {
            const pending = pendingDislikes.current.get(productId);

            /* Süre dolmuş: artık geri alınamaz */
            if (!pending) return false;

            clearTimeout(pending.timer);
            pendingDislikes.current.delete(productId);

            /* Yerine gelen kartı yedeğin başına iade et */
            if (pending.replacement) {
                buffer.current.unshift(pending.replacement);
            }

            setItems((current) => {
                const next = [...current];

                if (pending.replacement) {
                    const at = next.findIndex(
                        (entry) =>
                            entry.product.product_id ===
                            pending.replacement.product.product_id
                    );

                    if (at !== -1) next.splice(at, 1, pending.item);
                    else next.splice(pending.index, 0, pending.item);
                } else {
                    next.splice(pending.index, 0, pending.item);
                }

                return next;
            });

            setExhausted(false);

            showToast({
                title: "Geri alındı",
                message: "Ürün akışına geri döndü.",
                tone: "info",
            });

            return true;
        },
        [showToast]
    );


    const dislike = useCallback(
        (item, index) => {
            const productId = item.product.product_id;

            if (!getStoredUser()) {
                showToast({
                    title: "Giriş gerekli",
                    message: "Seçimini kaydetmek için giriş yap.",
                    tone: "info",
                });
                return;
            }

            /* Aynı ürüne ikinci basış: zaten bekliyor */
            if (pendingDislikes.current.has(productId)) return;

            /*
               SUNUCUYA HEMEN YAZMIYORUZ. Arayüz anında tepki
               veriyor, kayıt geri alma penceresinden sonra
               gidiyor. Kullanıcı açısından fark yok; veri
               açısından fark büyük.
            */
            const replacement = buffer.current.shift();

            pendingDislikes.current.set(productId, {
                item,
                index,
                replacement,
                timer: setTimeout(
                    () => commitDislike(productId),
                    UNDO_WINDOW_MS
                ),
            });

            /*
               AnimatePresence çıkış animasyonunu (sola kayma)
               kendisi yönetiyor: öğeyi listeden çıkarmak
               yeterli. Yerine yedekten yenisi giriyor.
            */
            setItems((current) => {
                const position = current.findIndex(
                    (entry) => entry.product.product_id === productId
                );

                if (position === -1) return current;

                const next = [...current];

                if (replacement) next.splice(position, 1, replacement);
                else next.splice(position, 1);

                if (!next.length) setExhausted(true);

                return next;
            });

            /* Favorideyse artık değil */
            setWishlist((current) => {
                if (!current.has(productId)) return current;
                const next = new Set(current);
                next.delete(productId);
                return next;
            });

            showToast({
                title: "Anlaşıldı, bu tarz elendi",
                message: "Bu ürün ve benzer kesimler geri planda kalacak.",
                tone: "neutral",
                undoLabel: "GERİ AL",
                duration: UNDO_WINDOW_MS,
                onUndo: () => undoDislike(productId),
            });

            ensureBuffer(BUFFER_MIN);
        },
        [showToast, ensureBuffer, commitDislike, undoDislike]
    );


    /*
       Sekme kapanırken bekleyenleri gönder.

       Kullanıcı eylemi yaptı ve geri almadı; commit etmek
       doğru varsayılan. sendInteraction keepalive kullanıyor,
       bu yüzden sayfa kapanırken de gidiyor.
    */
    useEffect(() => {
        const flush = () => {
            pendingDislikes.current.forEach((_, productId) =>
                commitDislike(productId)
            );
        };

        window.addEventListener("pagehide", flush);

        return () => window.removeEventListener("pagehide", flush);
    }, [commitDislike]);


    return {
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
        undoDislike,

        reload: () => load({ reset: true }),
        loadMore: () => load(),
        loadWishlist,
    };
}
