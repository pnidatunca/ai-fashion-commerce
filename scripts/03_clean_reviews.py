from pathlib import Path

import pandas as pd
from ftfy import fix_text


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

REVIEWS_FILE = ROOT / "data" / "reviews.csv"
PRODUCTS_FILE = ROOT / "data" / "products_clean.csv"

OUTPUT_CSV = ROOT / "data" / "reviews_clean.csv"
OUTPUT_JSONL = ROOT / "data" / "reviews_clean.jsonl"


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def clean_text(value):
    """
    Metnin anlamini degistirmeden:

    - encoding/mojibake problemlerini duzeltir
    - gereksiz bosluklari temizler

    Stopword silmez.
    'not', 'no' gibi anlam tasiyan kelimeleri korur.
    """

    if pd.isna(value):
        return ""

    text = str(value)

    # Ornek:
    # Men‚Äôs -> Men’s
    text = fix_text(text)

    # Fazladan bosluklari temizle
    text = " ".join(text.split())

    return text


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print(f"Loading reviews : {REVIEWS_FILE}")
    print(f"Loading products: {PRODUCTS_FILE}")

    if not REVIEWS_FILE.exists():
        raise FileNotFoundError(
            f"reviews.csv bulunamadi:\n{REVIEWS_FILE}"
        )

    if not PRODUCTS_FILE.exists():
        raise FileNotFoundError(
            f"products_clean.csv bulunamadi:\n{PRODUCTS_FILE}"
        )

    reviews = pd.read_csv(REVIEWS_FILE)
    products = pd.read_csv(PRODUCTS_FILE)

    print()
    print(f"Raw reviews: {len(reviews)}")

    # -----------------------------------------------------
    # CREATE CLEAN DATAFRAME
    # -----------------------------------------------------

    clean_df = pd.DataFrame()

    # products.csv asin ile baglanacak alan
    clean_df["product_id"] = (
        reviews["productASIN"]
        .astype(str)
        .str.strip()
    )

    clean_df["review_id"] = (
        reviews["reviewID"]
        .astype(str)
        .str.strip()
    )

    # Zaten numeric
    clean_df["rating"] = pd.to_numeric(
        reviews["rating"],
        errors="coerce",
    )

    clean_df["helpful_votes"] = pd.to_numeric(
        reviews["helpfulVoteCount"],
        errors="coerce",
    ).fillna(0).astype(int)

    # Zaten bool ama garantiye aliyoruz
    clean_df["verified_purchase"] = (
        reviews["verifiedPurchase"]
        .fillna(False)
        .astype(bool)
    )

    # -----------------------------------------------------
    # TEXT
    # -----------------------------------------------------

    clean_df["review_title"] = (
        reviews["reviewTitle"]
        .apply(clean_text)
    )

    clean_df["review_text"] = (
        reviews["reviewText"]
        .apply(clean_text)
    )

    # Datasetin kendi temizlenmis versiyonunu
    # sadece referans olarak sakliyoruz.
    clean_df["source_cleaned_review_text"] = (
        reviews["cleaned_review_text"]
        .apply(clean_text)
    )

    # -----------------------------------------------------
    # SENTIMENT
    # -----------------------------------------------------

    clean_df["sentiment_score"] = pd.to_numeric(
        reviews["sentiment_score"],
        errors="coerce",
    )

    # -----------------------------------------------------
    # DATA QUALITY
    # -----------------------------------------------------

    original_count = len(clean_df)

    # Aynı review iki defa bulunuyorsa tekini tut.
    clean_df = clean_df.drop_duplicates(
        subset=["review_id"]
    ).copy()

    duplicate_count = original_count - len(clean_df)

    # Review mutlaka bizim temiz product katalogundaki
    # bir urune ait olmali.
    valid_product_ids = set(
        products["product_id"]
        .dropna()
        .astype(str)
    )

    unmatched_mask = ~clean_df["product_id"].isin(
        valid_product_ids
    )

    unmatched_count = unmatched_mask.sum()

    # Eslestirilemeyenleri ana datasetten cikar.
    clean_df = clean_df[
        ~unmatched_mask
    ].copy()

    # Review ID veya product ID yoksa kullanma.
    clean_df = clean_df[
        (clean_df["review_id"] != "")
        & (clean_df["product_id"] != "")
    ].copy()

    clean_df.reset_index(
        drop=True,
        inplace=True,
    )

    # -----------------------------------------------------
    # SAVE CSV
    # -----------------------------------------------------

    clean_df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    # -----------------------------------------------------
    # SAVE JSONL
    # -----------------------------------------------------

    clean_df.to_json(
        OUTPUT_JSONL,
        orient="records",
        lines=True,
        force_ascii=False,
    )

    # -----------------------------------------------------
    # REPORT
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("REVIEW CLEANING COMPLETE")
    print("=" * 70)

    print(f"Original reviews       : {len(reviews)}")
    print(f"Duplicate reviews      : {duplicate_count}")
    print(f"Unmatched reviews      : {unmatched_count}")
    print(f"Clean reviews          : {len(clean_df)}")

    print()
    print("=" * 70)
    print("MISSING VALUES AFTER CLEANING")
    print("=" * 70)

    print(
        "Missing rating        :",
        clean_df["rating"].isna().sum(),
    )

    print(
        "Missing review title  :",
        (clean_df["review_title"] == "").sum(),
    )

    print(
        "Missing review text   :",
        (clean_df["review_text"] == "").sum(),
    )

    print(
        "Missing sentiment     :",
        clean_df["sentiment_score"].isna().sum(),
    )

    print()
    print("=" * 70)
    print("REVIEW STATISTICS")
    print("=" * 70)

    print(
        "Unique reviewed products:",
        clean_df["product_id"].nunique(),
    )

    print(
        "Verified purchases      :",
        clean_df["verified_purchase"].sum(),
    )

    print(
        "Average rating          :",
        round(clean_df["rating"].mean(), 2),
    )

    print(
        "Average sentiment score :",
        round(clean_df["sentiment_score"].mean(), 4),
    )

    print()
    print("Rating distribution:")

    print(
        clean_df["rating"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print("=" * 70)
    print("OUTPUT FILES")
    print("=" * 70)

    print(f"CSV   : {OUTPUT_CSV}")
    print(f"JSONL : {OUTPUT_JSONL}")

    # -----------------------------------------------------
    # SAMPLE
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("SAMPLE CLEAN REVIEWS")
    print("=" * 70)

    sample_columns = [
        "product_id",
        "review_id",
        "rating",
        "helpful_votes",
        "verified_purchase",
        "review_title",
        "review_text",
        "sentiment_score",
    ]

    print(
        clean_df[sample_columns]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()