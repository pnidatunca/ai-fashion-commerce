# -*- coding: utf-8 -*-
"""
ARAMA KALITESI OLCUMU — once / sonra

Iddia etmek yerine olcmek icin. Skorlama veya sozluk
degistirdikten sonra bunu kosun: sayilar duserse degisiklik
geri alinmali.

NEDEN ESKI FRONTEND MANTIGI TAKLIT EDILIYOR
-------------------------------------------
Ilk denemede eski uca DOGRU filtreler elle veriliyordu
(gender=women, category=dress...). Ama eski sistemde bu
filtreleri frontend'deki alt-dize sozlukleri hesapliyordu ve
o sozlukler hata yapiyordu:

    "topuklu ayakkabi" -> "top" eslesti -> category=shirt
    "manto ariyorum"   -> "man" eslesti -> gender=men

Dogru degeri elle vermek eski sistemin gercek davranisini
gizler ve karsilastirmayi anlamsiz yapar. Bu yuzden asagida
silinen JS fonksiyonlarinin birebir kopyasi duruyor.

OLCUT
-----
Ilk N sonucta niyetin karsiligi BASLIK + KATEGORIDE geciyor
mu. Aciklama metnini de saymak fazla comert: neredeyse her
urun geciyor ve fark gorunmez oluyor.

KULLANIM
--------
    # backend ayakta olmali
    python scripts/12_eval_search.py
    python scripts/12_eval_search.py --api http://127.0.0.1:8000
    python scripts/12_eval_search.py --top 20
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )


# =========================================================
# ESKI FRONTEND MANTIGI  (silinen JS'in birebir kopyasi)
# =========================================================

OLD_CATEGORY_TERMS = {
    "dress": ["elbise", "dress", "gown"],
    "shirt": [
        "gömlek", "gomlek", "shirt", "tişört", "tisort",
        "t-shirt", "tshirt", "tee", "polo", "bluz",
        "blouse", "top",
    ],
    "pants": ["pantolon", "pants", "trousers", "jean", "jeans"],
    "jacket": ["ceket", "jacket", "coat", "mont", "blazer"],
    "shoes": [
        "ayakkabı", "ayakkabi", "shoe", "shoes", "sneaker",
        "sneakers", "bot", "boots", "sandal", "sandals",
    ],
}

OLD_COLORS = {
    "beyaz": "white", "siyah": "black", "kırmızı": "red",
    "mavi": "blue", "lacivert": "navy", "yeşil": "green",
    "sarı": "yellow", "pembe": "pink", "mor": "purple",
    "gri": "gray", "kahverengi": "brown", "bej": "beige",
    "white": "white", "black": "black", "red": "red",
    "blue": "blue", "navy": "navy", "green": "green",
    "yellow": "yellow", "pink": "pink", "purple": "purple",
    "gray": "gray", "grey": "gray", "brown": "brown",
    "beige": "beige",
}


def old_detect_category(query: str) -> str | None:
    text = query.lower()

    for category, words in OLD_CATEGORY_TERMS.items():
        if any(word in text for word in words):
            return category

    return None


def old_detect_color(query: str) -> str | None:
    text = query.lower()

    for word, color in OLD_COLORS.items():
        if word in text:
            return color

    return None


def old_detect_gender(query: str) -> str | None:
    text = query.lower()

    if any(w in text for w in ("kadın", "kadin", "women", "woman", "female")):
        return "women"

    if any(w in text for w in ("erkek", "men", "man", "male")):
        return "men"

    return None


# =========================================================
# YARDIMCILAR
# =========================================================

_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s",
    "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


def fold(text: str) -> str:
    return str(text or "").translate(_FOLD).lower()


def strong_text(product: dict) -> str:
    """Yalnizca baslik + kategori: gorunur kanit."""

    return fold(
        " ".join(
            str(product.get(field) or "")
            for field in ("title", "title_tr", "category")
        )
    )


# =========================================================
# TEST DURUMLARI
# =========================================================
#
# Her olcut, katalogda GERCEKTEN gecen kelimelerle yazildi
# (bkz. docs/AI_SEARCH.md bolum 4). Katalogda bulunmayan
# kelimeyi olcut yapmak testi anlamsiz kilar.

CASES = [
    (
        "kadın yazlık renkli elbise arıyorum",
        {
            "yazlık": ["yazlik", "summer", "kisa kollu", "short sleeve",
                       "askili", "sleeveless", "ince", "lightweight"],
            "desenli": ["desen", "cicek", "floral", "print", "baskili",
                        "cizgili", "striped", "renkli"],
            "elbise": ["dresses"],
            "kadın": ["› women ›"],
        },
    ),
    (
        # Turkce karaktersiz yazim: yaygin klavye aliskanligi
        "kadin yazlik renkli elbise ariyorum",
        {
            "yazlık": ["yazlik", "summer", "kisa kollu", "short sleeve",
                       "askili", "sleeveless", "ince", "lightweight"],
            "desenli": ["desen", "cicek", "floral", "print", "baskili",
                        "cizgili", "striped", "renkli"],
            "elbise": ["dresses"],
        },
    ),
    (
        "erkek kışlık kalın mont",
        {
            "kışlık": ["kislik", "winter", "warm", "sicak", "polar",
                       "fleece", "yun", "wool", "kalin", "puffer",
                       "quilted", "insulated", "termal", "thermal"],
            "dış giyim": ["jackets", "coats", "outerwear"],
            "erkek": ["› men ›"],
        },
    ),
    (
        # Eskiden "top" eslesip kategori shirt oluyordu
        "topuklu ayakkabı",
        {"ayakkabı": ["› shoes"]},
    ),
    (
        # Eskiden "man" eslesip cinsiyet men oluyordu
        "manto arıyorum",
        {"dış giyim": ["jackets", "coats", "outerwear", "manto"]},
    ),
    (
        "çiçekli midi elbise",
        {
            "desenli": ["desen", "cicek", "floral", "print", "baskili"],
            "elbise": ["dresses"],
        },
    ),
]


# =========================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Arama kalitesi once/sonra olcumu",
    )
    parser.add_argument(
        "--api",
        default="http://127.0.0.1:8011",
        help="Backend adresi (varsayilan test sunucusu)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Kac sonuc uzerinden olculecek",
    )

    args = parser.parse_args()

    def get(path: str, **params):
        url = args.api + path + "?" + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )

        with urllib.request.urlopen(url, timeout=180) as response:
            return json.load(response)

    print("=" * 74)
    print(
        "ARAMA KALITESI: ONCE / SONRA   (ilk %d sonuc, baslik+kategori)"
        % args.top
    )
    print("=" * 74)
    print()

    totals = {"yeni": 0, "eski": 0, "olcut": 0}

    for query, checks in CASES:

        # Eski frontend'in GERCEKTEN gonderecegi parametreler
        legacy = {
            "gender": old_detect_gender(query),
            "category": old_detect_category(query),
            "color": old_detect_color(query),
        }

        print("-" * 74)
        print('SORGU: "%s"' % query)
        print(
            "  eski frontend'in gonderdigi: %s"
            % ({k: v for k, v in legacy.items() if v} or "-")
        )
        print("-" * 74)

        try:
            new = get("/api/search", q=query, limit=args.top)
            new_products = [item["product"] for item in new["items"]]

            old_products = get(
                "/products/semantic-search",
                q=query,
                limit=args.top,
                **legacy,
            )
        except urllib.error.URLError as error:
            print("  BACKEND'E ULASILAMADI: %s" % error)
            print("  Sunucuyu baslatip tekrar deneyin.")
            return 1

        print(
            "  yeni: %2d sonuc (asama %d: %s)"
            % (
                len(new_products),
                new["meta"]["stage"],
                new["meta"]["stage_label"],
            )
        )

        if new["meta"]["relaxed"]:
            print("        gevsetilen: %s" % ", ".join(new["meta"]["relaxed"]))

        print("  eski: %2d sonuc" % len(old_products))
        print()

        for name, words in checks.items():

            def hits(products):
                return sum(
                    1
                    for product in products
                    if any(word in strong_text(product) for word in words)
                )

            new_hit = hits(new_products)
            old_hit = hits(old_products)

            totals["yeni"] += new_hit
            totals["eski"] += old_hit
            totals["olcut"] += args.top

            if new_hit > old_hit:
                mark = "^ "
            elif new_hit < old_hit:
                mark = "v "
            else:
                mark = "  "

            print(
                "  %s%-12s yeni %2d/%-2d   eski %2d/%-2d"
                % (mark, name, new_hit, args.top, old_hit, args.top)
            )

        print()

    print("=" * 74)
    print(
        "TOPLAM  yeni %d/%d (%%%.1f)   eski %d/%d (%%%.1f)"
        % (
            totals["yeni"], totals["olcut"],
            100.0 * totals["yeni"] / totals["olcut"],
            totals["eski"], totals["olcut"],
            100.0 * totals["eski"] / totals["olcut"],
        )
    )
    print("=" * 74)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
