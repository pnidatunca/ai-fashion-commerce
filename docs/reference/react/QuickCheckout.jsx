import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Lock, X, Zap } from "lucide-react";

import { createQuickOrder, getStoredUser } from "./auraApi";

/**
 * TEK EKRAN HIZLI SATIN ALMA  (sepetsiz)
 *
 * Sepet ve üç adımlı ödeme akışı kaldırıldı. Tek ürün,
 * tek ekran: özet + teslimat + kart aynı görünümde.
 *
 * Neden tek ekran: üç adım demek üç kez "devam"a basmak
 * demek. Tek ürün alan biri için bu gereksiz sürtünme.
 *
 * BEDELİ: çok ürünlü sipariş yok. Wishlist "sonra al"
 * listesi olarak sepetin yerini alıyor ama sepet ortalama
 * sipariş tutarını etkileyen bir şey — bilinçli takas.
 *
 * KART BİLGİSİ SUNUCUYA GİTMİYOR. Doğrulama burada
 * yapılıyor; /api/quick-order yalnızca satın alma niyetini
 * kaydediyor.
 */

/* Luhn: yazım hatası olan kart numaralarını yakalar.
   Gerçek bir ödeme doğrulaması DEĞİLDİR. */
function isLuhnValid(digits) {
    let sum = 0;
    let double = false;

    for (let i = digits.length - 1; i >= 0; i--) {
        let value = Number(digits[i]);
        if (double) {
            value *= 2;
            if (value > 9) value -= 9;
        }
        sum += value;
        double = !double;
    }

    return digits.length > 0 && sum % 10 === 0;
}

function isExpiryValid(value) {
    const match = /^(\d{2})\/(\d{2})$/.exec(String(value || "").trim());

    if (!match) return false;

    const month = Number(match[1]);
    const year = 2000 + Number(match[2]);

    if (month < 1 || month > 12) return false;

    // Ayın son günü: kart o ayın sonuna kadar geçerli
    return new Date(year, month, 0, 23, 59, 59) >= new Date();
}


const EMPTY_FORM = {
    name: "",
    phone: "",
    address: "",
    card: "",
    expiry: "",
    cvc: "",
    terms: false,
};


export default function QuickCheckout({
    open,
    item,
    onClose,
    onOrdered,
    formatPrice,
}) {
    const [form, setForm] = useState(EMPTY_FORM);
    const [errors, setErrors] = useState({});
    const [busy, setBusy] = useState(false);
    const [order, setOrder] = useState(null);

    const product = item?.product;

    /* Açılışta formu profil bilgisiyle doldur */
    useEffect(() => {
        if (!open) return;

        const user = getStoredUser();

        setOrder(null);
        setErrors({});
        setForm({
            ...EMPTY_FORM,
            name: user
                ? [user.first_name, user.last_name].filter(Boolean).join(" ")
                : "",
        });
    }, [open]);

    /* ESC ile kapat */
    useEffect(() => {
        if (!open) return;

        const onKeyDown = (event) => {
            if (event.key === "Escape") onClose?.();
        };

        document.addEventListener("keydown", onKeyDown);
        return () => document.removeEventListener("keydown", onKeyDown);
    }, [open, onClose]);


    const hasOldPrice = useMemo(
        () =>
            product?.list_price &&
            Number(product.list_price) > Number(product.price || 0),
        [product]
    );


    function update(field, value) {
        setForm((current) => ({ ...current, [field]: value }));
    }

    /* Kart alanı maskeleri */

    function onCardChange(event) {
        const digits = event.target.value.replace(/\D/g, "").slice(0, 19);
        update("card", digits.replace(/(.{4})/g, "$1 ").trim());
    }

    function onExpiryChange(event) {
        const digits = event.target.value.replace(/\D/g, "").slice(0, 4);
        update(
            "expiry",
            digits.length > 2
                ? `${digits.slice(0, 2)}/${digits.slice(2)}`
                : digits
        );
    }

    function onCvcChange(event) {
        update("cvc", event.target.value.replace(/\D/g, "").slice(0, 4));
    }


    function validate() {
        const next = {};

        if (form.name.trim().length < 3) {
            next.name = "Ad ve soyadını gir.";
        }

        if (form.phone.replace(/\D/g, "").length < 10) {
            next.phone = "Telefon en az 10 haneli olmalı.";
        }

        if (form.address.trim().length < 10) {
            next.address = "Adresi biraz daha ayrıntılı yaz.";
        }

        const digits = form.card.replace(/\D/g, "");

        if (digits.length < 13 || !isLuhnValid(digits)) {
            next.card = "Kart numarası geçersiz.";
        }

        if (!isExpiryValid(form.expiry)) {
            next.expiry = "AA/YY biçiminde geçerli bir tarih gir.";
        }

        if (form.cvc.replace(/\D/g, "").length < 3) {
            next.cvc = "CVC 3 haneli.";
        }

        if (!form.terms) {
            next.terms = "Devam etmek için sözleşmeyi onayla.";
        }

        setErrors(next);

        return Object.keys(next).length === 0;
    }


    async function submit(event) {
        event.preventDefault();

        if (busy || !validate() || !product) return;

        setBusy(true);

        try {
            const response = await createQuickOrder({
                productId: product.product_id,
                source: item.source || "quick_checkout",
                position: item.position,
                matchScore: item.match_score,
                matchedStyle: item.matched_style,
            });

            setOrder(response);

            onOrdered?.(response, product);
        } catch (error) {
            console.error("Sipariş oluşturulamadı:", error);

            setErrors({
                submit: error.message || "Tekrar dener misin?",
            });
        } finally {
            setBusy(false);
        }
    }


    function field(name, label, extra = {}) {
        return (
            <div className={"field" + (errors[name] ? " invalid" : "")}>
                <label htmlFor={`quick-${name}`}>{label}</label>

                {extra.textarea ? (
                    <textarea
                        id={`quick-${name}`}
                        rows={2}
                        value={form[name]}
                        placeholder={extra.placeholder}
                        onChange={(e) => update(name, e.target.value)}
                    />
                ) : (
                    <input
                        id={`quick-${name}`}
                        type={extra.type || "text"}
                        value={form[name]}
                        placeholder={extra.placeholder}
                        inputMode={extra.inputMode}
                        maxLength={extra.maxLength}
                        autoComplete={extra.autoComplete}
                        onChange={extra.onChange || ((e) => update(name, e.target.value))}
                    />
                )}

                {errors[name] && (
                    <span className="field-error">{errors[name]}</span>
                )}
            </div>
        );
    }


    return (
        <AnimatePresence>
            {open && product && (
                <motion.div
                    className="checkout-overlay open"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={(event) => {
                        if (event.target === event.currentTarget) onClose?.();
                    }}
                >
                    <motion.div
                        className="quick-panel"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 14 }}
                        transition={{ duration: 0.38, ease: [0.2, 0.7, 0.2, 1] }}
                    >
                        <button
                            type="button"
                            className="checkout-close"
                            onClick={onClose}
                            aria-label="Kapat"
                        >
                            <X size={16} />
                        </button>

                        {order ? (
                            <motion.div
                                className="quick-success"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                            >
                                <motion.div
                                    className="success-mark"
                                    initial={{ scale: 0.5, opacity: 0 }}
                                    animate={{ scale: 1, opacity: 1 }}
                                    transition={{
                                        duration: 0.45,
                                        ease: [0.2, 0.9, 0.3, 1.3],
                                    }}
                                >
                                    <Check size={24} />
                                </motion.div>

                                <h3>Siparişin alındı</h3>

                                <p>
                                    Sipariş numaran{" "}
                                    <strong>{order.order_number}</strong>. Benzer
                                    parçalar akışında öne çıkarılacak.
                                </p>

                                <button
                                    type="button"
                                    className="auth-main-btn"
                                    onClick={onClose}
                                >
                                    KEŞFETMEYE DEVAM ET
                                </button>
                            </motion.div>
                        ) : (
                            <div className="quick-body">
                                <div className="quick-head">
                                    <span className="ai-chip">
                                        <span className="ai-dot" />
                                        HIZLI SATIN ALMA
                                    </span>

                                    <h2>
                                        Tek ürün, <em>tek ekran</em>
                                    </h2>
                                </div>

                                <div className="quick-product">
                                    <img
                                        src={product.image_url}
                                        alt={product.title_tr || product.title}
                                        loading="lazy"
                                    />

                                    <div className="quick-product-info">
                                        <strong>
                                            {product.title_tr || product.title}
                                        </strong>

                                        <div className="quick-product-price">
                                            <span>
                                                {formatPrice(product.price)}
                                            </span>

                                            {hasOldPrice && (
                                                <span className="old-price">
                                                    {formatPrice(
                                                        product.list_price
                                                    )}
                                                </span>
                                            )}
                                        </div>

                                        {item.match_label && (
                                            <span className="quick-product-match">
                                                {item.match_label}
                                            </span>
                                        )}
                                    </div>
                                </div>

                                <form
                                    className="auth-form quick-form"
                                    onSubmit={submit}
                                    noValidate
                                >
                                    <div className="quick-section">
                                        <span className="quick-section-label">
                                            TESLİMAT
                                        </span>

                                        <div className="field-row">
                                            {field("name", "AD SOYAD", {
                                                placeholder: "Ad Soyad",
                                                autoComplete: "name",
                                            })}
                                            {field("phone", "TELEFON", {
                                                type: "tel",
                                                placeholder: "5XX XXX XX XX",
                                                inputMode: "numeric",
                                                autoComplete: "tel",
                                            })}
                                        </div>

                                        {field("address", "ADRES", {
                                            textarea: true,
                                            placeholder:
                                                "Mahalle, sokak, bina, daire · İlçe / İl",
                                        })}
                                    </div>

                                    <div className="quick-section">
                                        <span className="quick-section-label">
                                            ÖDEME
                                        </span>

                                        {field("card", "KART NUMARASI", {
                                            placeholder: "0000 0000 0000 0000",
                                            inputMode: "numeric",
                                            maxLength: 23,
                                            autoComplete: "cc-number",
                                            onChange: onCardChange,
                                        })}

                                        <div className="field-row">
                                            {field("expiry", "SON KULLANMA", {
                                                placeholder: "AA/YY",
                                                inputMode: "numeric",
                                                maxLength: 5,
                                                autoComplete: "cc-exp",
                                                onChange: onExpiryChange,
                                            })}
                                            {field("cvc", "CVC", {
                                                placeholder: "123",
                                                inputMode: "numeric",
                                                maxLength: 4,
                                                autoComplete: "cc-csc",
                                                onChange: onCvcChange,
                                            })}
                                        </div>
                                    </div>

                                    <label className="checkbox-field">
                                        <input
                                            type="checkbox"
                                            checked={form.terms}
                                            onChange={(e) =>
                                                update("terms", e.target.checked)
                                            }
                                        />
                                        <span>
                                            Mesafeli satış sözleşmesini okudum,
                                            onaylıyorum.
                                        </span>
                                    </label>

                                    {errors.terms && (
                                        <span className="field-error">
                                            {errors.terms}
                                        </span>
                                    )}

                                    {errors.submit && (
                                        <span className="field-error">
                                            {errors.submit}
                                        </span>
                                    )}

                                    <button
                                        type="submit"
                                        className="auth-main-btn quick-submit"
                                        disabled={busy}
                                    >
                                        <Zap size={14} />
                                        {busy
                                            ? "GÖNDERİLİYOR..."
                                            : "SİPARİŞİ TAMAMLA"}
                                    </button>

                                    <p className="checkout-secure">
                                        <Lock size={11} />
                                        Demo ödeme ekranı. Kart bilgileri hiçbir
                                        yere gönderilmez.
                                    </p>
                                </form>
                            </div>
                        )}
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
