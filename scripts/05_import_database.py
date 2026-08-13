import os
import sys
from pathlib import Path
import pandas as pd
from sqlalchemy.dialects.postgresql import insert
import math

# Backend import path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import engine, Base, SessionLocal
from app.models import Product, Review

PRODUCTS_CSV = ROOT / "data" / "products_clean.csv"
REVIEWS_CSV = ROOT / "data" / "reviews_clean.csv"

def clean_dict(d):
    """Replace NaN/NaT with None for SQLAlchemy"""
    return {k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in d.items()}

def main():
    print("=" * 70)
    print("DATABASE IMPORT SCRIPT")
    print("=" * 70)

    # 1. Create tables with retry for Neon cold start
    print("Creating tables in database (if they don't exist)...")
    import time
    for attempt in range(3):
        try:
            Base.metadata.create_all(bind=engine)
            print("Tables created.")
            break
        except Exception as e:
            if attempt < 2:
                print(f"Table creation attempt {attempt+1} failed: {e}. Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print(f"Failed to create tables after 3 attempts.")
                raise

    # 2. Load CSVs
    if not PRODUCTS_CSV.exists() or not REVIEWS_CSV.exists():
        raise FileNotFoundError("Clean CSV files are missing.")

    print(f"Loading {PRODUCTS_CSV.name}...")
    products_df = pd.read_csv(PRODUCTS_CSV)
    
    print(f"Loading {REVIEWS_CSV.name}...")
    reviews_df = pd.read_csv(REVIEWS_CSV)

    session = SessionLocal()

    try:
        # 3. Insert Products
        print(f"Importing {len(products_df)} products...")
        product_records = [clean_dict(row) for row in products_df.to_dict(orient="records")]
        
        if product_records:
            stmt = insert(Product).values(product_records)
            stmt = stmt.on_conflict_do_nothing(index_elements=['product_id'])
            result = session.execute(stmt)
            session.commit()
            print(f"Products import completed. Inserted/Ignored: {len(product_records)}")
        
        # 4. Insert Reviews
        print(f"Importing {len(reviews_df)} reviews...")
        review_records = [clean_dict(row) for row in reviews_df.to_dict(orient="records")]
        
        if review_records:
            stmt = insert(Review).values(review_records)
            stmt = stmt.on_conflict_do_nothing(index_elements=['review_id'])
            result = session.execute(stmt)
            session.commit()
            print(f"Reviews import completed. Inserted/Ignored: {len(review_records)}")

        # 5. Final Report
        product_count = session.query(Product).count()
        review_count = session.query(Review).count()

        print()
        print("=" * 70)
        print("IMPORT SUMMARY")
        print("=" * 70)
        print(f"Total Products in DB : {product_count}")
        print(f"Total Reviews in DB  : {review_count}")

    except Exception as e:
        session.rollback()
        print(f"Error during import: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()
