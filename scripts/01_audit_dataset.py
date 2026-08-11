from pathlib import Path

import pandas as pd


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

PRODUCTS_FILE = ROOT / "data" / "products.csv"
REVIEWS_FILE = ROOT / "data" / "reviews.csv"


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    print("=" * 70)
    print("DATASET AUDIT")
    print("=" * 70)

    # Dosyalar var mı?
    if not PRODUCTS_FILE.exists():
        raise FileNotFoundError(
            f"products.csv bulunamadi:\n{PRODUCTS_FILE}"
        )

    if not REVIEWS_FILE.exists():
        raise FileNotFoundError(
            f"reviews.csv bulunamadi:\n{REVIEWS_FILE}"
        )

    # Datasetleri oku
    products = pd.read_csv(PRODUCTS_FILE)
    reviews = pd.read_csv(REVIEWS_FILE)

    # -----------------------------------------------------
    # PRODUCTS
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("PRODUCTS")
    print("=" * 70)

    print(f"Rows            : {len(products)}")
    print(f"Columns         : {len(products.columns)}")
    print(f"Unique ASIN     : {products['asin'].nunique()}")
    print(f"Duplicate ASIN  : {products['asin'].duplicated().sum()}")

    # -----------------------------------------------------
    # IMPORTANT PRODUCT FIELDS
    # -----------------------------------------------------

    important_columns = [
        "asin",
        "title",
        "product_description",
        "about_item",
        "brand_name",
        "price_value",
        "list_price",
        "breadcrumbs",
        "all_images",
        "rating_stars",
        "rating_count",
        "availability",
        "product_url",
    ]

    print()
    print("=" * 70)
    print("PRODUCT FIELD COMPLETENESS")
    print("=" * 70)

    for column in important_columns:

        if column not in products.columns:
            print(f"{column:25} COLUMN NOT FOUND")
            continue

        missing = products[column].isna().sum()
        filled = len(products) - missing

        filled_percent = (
            filled / len(products) * 100
            if len(products) > 0
            else 0
        )

        print(
            f"{column:25} "
            f"{missing:4} missing | "
            f"{filled_percent:6.2f}% filled"
        )

    # -----------------------------------------------------
    # REVIEWS
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("REVIEWS")
    print("=" * 70)

    product_ids = set(products["asin"].dropna().astype(str))

    review_product_ids = reviews["productASIN"].astype(str)

    matched_mask = review_product_ids.isin(product_ids)

    print(f"Review rows               : {len(reviews)}")
    print(
        f"Unique reviewed products  : "
        f"{reviews['productASIN'].nunique()}"
    )
    print(f"Matched reviews           : {matched_mask.sum()}")
    print(f"Unmatched reviews         : {(~matched_mask).sum()}")

    products_with_reviews = set(
        reviews.loc[matched_mask, "productASIN"]
        .dropna()
        .astype(str)
    )

    print(
        f"Products with reviews     : "
        f"{len(products_with_reviews)}"
    )

    print(
        f"Products without reviews  : "
        f"{len(product_ids - products_with_reviews)}"
    )

    # -----------------------------------------------------
    # RAW PRODUCT FIELD SAMPLES
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("RAW PRODUCT FIELD SAMPLES")
    print("=" * 70)

    sample_columns = [
        "asin",
        "price_value",
        "list_price",
        "rating_stars",
        "rating_count",
    ]

    print(
        products[sample_columns]
        .head(15)
        .to_string(index=False)
    )

    # -----------------------------------------------------
    # IMAGE SAMPLE
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("IMAGE FIELD SAMPLE")
    print("=" * 70)

    print(
        products[
            [
                "asin",
                "title",
                "all_images",
            ]
        ]
        .head(3)
        .to_string(index=False)
    )

    print()
    print("=" * 70)
    print("AUDIT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()