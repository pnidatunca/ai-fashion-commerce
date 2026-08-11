import ast
import json
import re

from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = ROOT / "data" / "products.csv"

OUTPUT_JSONL = ROOT / "data" / "products_clean.jsonl"
OUTPUT_CSV = ROOT / "data" / "products_clean.csv"


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def clean_text(value):
    """
    NaN degerlerini bos string yapar.
    Fazladan bosluklari temizler.
    """

    if pd.isna(value):
        return ""

    return " ".join(str(value).split())


def parse_price(value):
    """
    Dataset price_value alaninda fiyat ile scrape edilen
    baska bilgi birbirine yapismis gorunuyor.

    Ornek:

        39.9926 -> 39.99
        19.9920 -> 19.99
        29.9950 -> 29.99
        42.9970 -> 42.99
        19.9890 -> 19.98
        32.9500 -> 32.95

    Burada ROUND kullanmiyoruz.

    Ilk iki ondalik basamagi koruyarak fiyati
    2 decimal'a truncate ediyoruz.
    """

    if pd.isna(value):
        return None

    try:
        number = Decimal(str(value))

        price = number.quantize(
            Decimal("0.01"),
            rounding=ROUND_DOWN,
        )

        return float(price)

    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_list_price(value):
    """
    Ornek:

        "List Price: $53.99"       -> 53.99
        "Typical price: $24.99"    -> 24.99
        "One-Time Price: $49.50"   -> 49.50
        NaN                         -> None
    """

    if pd.isna(value):
        return None

    text = str(value)

    match = re.search(
        r"\$([\d,]+(?:\.\d+)?)",
        text,
    )

    if not match:
        return None

    try:
        return float(
            match.group(1).replace(",", "")
        )

    except ValueError:
        return None


def calculate_discount_percent(price, list_price):
    """
    Indirim oranini guvenilir sekilde hesaplar.

    Ornek:

        current = 39.99
        list    = 53.99

        discount ~= 26%

    list_price yoksa indirim orani bilinmiyor.
    """

    if pd.isna(price) or pd.isna(list_price):
        return None

    if list_price <= 0:
        return None

    if price > list_price:
        return None

    discount = (
        (list_price - price)
        / list_price
        * 100
    )

    return round(discount)


def parse_rating(value):
    """
    Ornek:

        "4.6 out of 5 stars" -> 4.6
        "4.4 out of 5 stars" -> 4.4
        NaN                  -> None
    """

    if pd.isna(value):
        return None

    match = re.search(
        r"(\d+(?:\.\d+)?)",
        str(value),
    )

    if not match:
        return None

    try:
        return float(match.group(1))

    except ValueError:
        return None


def parse_rating_count(value):
    """
    Ornek:

        "1,654 ratings"  -> 1654
        "20 ratings"     -> 20
        "11,355 ratings" -> 11355
        NaN              -> None
    """

    if pd.isna(value):
        return None

    text = str(value).replace(",", "")

    match = re.search(
        r"(\d+)",
        text,
    )

    if not match:
        return None

    try:
        return int(match.group(1))

    except ValueError:
        return None


def extract_first_image(value):
    """
    all_images alani su sekilde geliyor:

        [
            "https://....jpg",
            "https://....jpg"
        ]

    Ilk resmi ana urun resmi olarak aliyoruz.
    """

    if pd.isna(value):
        return ""

    text = str(value).strip()

    try:
        images = ast.literal_eval(text)

        if isinstance(images, list) and len(images) > 0:
            return str(images[0]).strip()

    except (ValueError, SyntaxError):
        pass

    # Parsing basarisiz olsa bile bos birakmadan once
    # URL bulmaya calis.
    url_match = re.search(
        r"https?://[^\s,'\"\]]+",
        text,
    )

    if url_match:
        return url_match.group(0)

    return ""


def build_search_text(row):
    """
    Semantic Search icin kullanacagimiz tek bir
    zengin urun metni olusturur.
    """

    parts = []

    if row["title"]:
        parts.append(
            f"Product: {row['title']}."
        )

    if row["brand"]:
        parts.append(
            f"Brand: {row['brand']}."
        )

    if row["category"]:
        parts.append(
            f"Category: {row['category']}."
        )

    if row["features"]:
        parts.append(
            f"Features: {row['features']}."
        )

    if row["description"]:
        parts.append(
            f"Description: {row['description']}."
        )

    return " ".join(parts)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print(f"Loading: {INPUT_FILE}")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"products.csv bulunamadi:\n{INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    print(f"Raw products: {len(df)}")

    clean_df = pd.DataFrame()

    # -----------------------------------------------------
    # PRODUCT ID
    # -----------------------------------------------------

    clean_df["product_id"] = (
        df["asin"]
        .astype(str)
        .str.strip()
    )

    # -----------------------------------------------------
    # BASIC TEXT FIELDS
    # -----------------------------------------------------

    clean_df["title"] = (
        df["title"]
        .apply(clean_text)
    )

    clean_df["brand"] = (
        df["brand_name"]
        .apply(clean_text)
    )

    clean_df["category"] = (
        df["breadcrumbs"]
        .apply(clean_text)
    )

    clean_df["description"] = (
        df["product_description"]
        .apply(clean_text)
    )

    clean_df["features"] = (
        df["about_item"]
        .apply(clean_text)
    )

    clean_df["availability"] = (
        df["availability"]
        .apply(clean_text)
    )

    clean_df["product_url"] = (
        df["product_url"]
        .apply(clean_text)
    )

    # -----------------------------------------------------
    # PRICE
    # -----------------------------------------------------

    clean_df["price"] = (
        df["price_value"]
        .apply(parse_price)
    )

    clean_df["list_price"] = (
        df["list_price"]
        .apply(parse_list_price)
    )

    clean_df["discount_percent"] = clean_df.apply(
        lambda row: calculate_discount_percent(
            row["price"],
            row["list_price"],
        ),
        axis=1,
    )

    # -----------------------------------------------------
    # RATING
    # -----------------------------------------------------

    clean_df["rating"] = (
        df["rating_stars"]
        .apply(parse_rating)
    )

    clean_df["rating_count"] = (
        df["rating_count"]
        .apply(parse_rating_count)
    )

    # Nullable integer type
    clean_df["rating_count"] = (
        pd.array(
            clean_df["rating_count"],
            dtype="Int64",
        )
    )

    clean_df["discount_percent"] = (
        pd.array(
            clean_df["discount_percent"],
            dtype="Int64",
        )
    )

    # -----------------------------------------------------
    # IMAGE
    # -----------------------------------------------------

    clean_df["image_url"] = (
        df["all_images"]
        .apply(extract_first_image)
    )

    # -----------------------------------------------------
    # SEARCH TEXT
    # -----------------------------------------------------

    clean_df["search_text"] = clean_df.apply(
        build_search_text,
        axis=1,
    )

    # -----------------------------------------------------
    # DATA QUALITY
    # -----------------------------------------------------

    # Duplicate ASIN istemiyoruz.
    clean_df = clean_df.drop_duplicates(
        subset=["product_id"]
    )

    # En temel alanlar olmadan urun kullanmayalim.
    clean_df = clean_df[
        (clean_df["product_id"] != "")
        & (clean_df["title"] != "")
        & (clean_df["image_url"] != "")
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

    with OUTPUT_JSONL.open(
        "w",
        encoding="utf-8",
    ) as f:

        for record in clean_df.to_dict(
            orient="records"
        ):

            # pandas NA -> None
            cleaned_record = {}

            for key, value in record.items():

                if pd.isna(value):
                    cleaned_record[key] = None

                else:
                    cleaned_record[key] = value

            f.write(
                json.dumps(
                    cleaned_record,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

    # -----------------------------------------------------
    # REPORT
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("CLEANING COMPLETE")
    print("=" * 70)

    print(f"Original products     : {len(df)}")
    print(f"Clean products        : {len(clean_df)}")
    print(
        f"Unique products       : "
        f"{clean_df['product_id'].nunique()}"
    )

    print()
    print("=" * 70)
    print("MISSING VALUES AFTER CLEANING")
    print("=" * 70)

    print(
        "Missing price         :",
        clean_df["price"].isna().sum(),
    )

    print(
        "Missing list price    :",
        clean_df["list_price"].isna().sum(),
    )

    print(
        "Missing category      :",
        (clean_df["category"] == "").sum(),
    )

    print(
        "Missing description   :",
        (clean_df["description"] == "").sum(),
    )

    print(
        "Missing rating        :",
        clean_df["rating"].isna().sum(),
    )

    print(
        "Missing rating count  :",
        clean_df["rating_count"].isna().sum(),
    )

    print(
        "Missing image         :",
        (clean_df["image_url"] == "").sum(),
    )

    print()
    print("=" * 70)
    print("OUTPUT FILES")
    print("=" * 70)

    print(f"CSV   : {OUTPUT_CSV}")
    print(f"JSONL : {OUTPUT_JSONL}")

    # -----------------------------------------------------
    # SAMPLE OUTPUT
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("SAMPLE CLEAN PRODUCTS")
    print("=" * 70)

    sample_columns = [
        "product_id",
        "title",
        "price",
        "list_price",
        "discount_percent",
        "rating",
        "rating_count",
        "brand",
        "category",
        "image_url",
    ]

    print(
        clean_df[sample_columns]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()