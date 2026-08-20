"""
product_style_scores tablosunu doldurur.

Her (arketip, urun) cifti icin stil eslesme skorunu
onceden hesaplar. Bu tablo modelin "egitilmis agirliklari"
gibidir: feed sorgusu JOIN edip ORDER BY yapar, istek
aninda metin analizi yapilmaz.

NE ZAMAN YENIDEN KOSTURULMALI:
  - katalog degistiginde (yeni urun aktarimi)
  - style_engine.py sozlukleri veya agirliklari degistiginde

Kullanim:
    python scripts/09_compute_style_scores.py
    python scripts/09_compute_style_scores.py --dry-run
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import SessionLocal
from app.models import Product, ProductStyleScore
from app.style_engine import (
    ARCHETYPES,
    MATCH_BADGE_THRESHOLD,
    REASON_CHIP_THRESHOLD,
    THIN_POOL_THRESHOLD,
    build_reason_sentence,
    score_product_for_archetype,
)

BATCH_SIZE = 500


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hesaplar ama veritabanina yazmaz",
    )
    args = parser.parse_args()

    session = SessionLocal()

    try:
        products = list(
            session.scalars(
                select(Product).where(
                    Product.price.is_not(None),
                    Product.price > 0,
                    Product.image_url.is_not(None),
                    Product.image_url != "",
                )
            ).all()
        )

        print("=" * 70)
        print("STIL SKORU HESAPLAMA")
        print("=" * 70)
        print(f"\nuygun urun     : {len(products)}")
        print(f"arketip        : {len(ARCHETYPES)}")
        print(f"hesaplanacak   : {len(products) * len(ARCHETYPES)} satir")

        if not products:
            print("\nSkorlanacak urun yok.")
            return

        rows = []
        stats = {archetype: [] for archetype in ARCHETYPES}

        for product in products:
            for archetype in ARCHETYPES:

                score, reasons, _ = score_product_for_archetype(
                    product, archetype
                )

                stats[archetype].append(score)

                rows.append(
                    {
                        "product_id": product.product_id,
                        "archetype": archetype,
                        "score": score,
                        "reasons": reasons,
                    }
                )

        # ---- Dagilim raporu ----

        print("\n" + "-" * 70)
        print("DAGILIM")
        print("-" * 70)
        print(
            f"{'arketip':<14}{'min':>7}{'medyan':>9}{'max':>7}"
            f"{'badge':>8}{'cip':>7}"
        )

        for archetype in ARCHETYPES:
            values = sorted(stats[archetype])
            badge = sum(
                1 for v in values if v >= MATCH_BADGE_THRESHOLD
            )
            chip = sum(
                1 for v in values
                if REASON_CHIP_THRESHOLD <= v < MATCH_BADGE_THRESHOLD
            )

            state = (
                "INCE HAVUZ"
                if badge < THIN_POOL_THRESHOLD
                else ""
            )

            print(
                f"{archetype:<14}"
                f"{values[0]:>7.1f}"
                f"{values[len(values) // 2]:>9.1f}"
                f"{values[-1]:>7.1f}"
                f"{badge:>8}"
                f"{chip:>7}"
                f"   {state}"
            )

        # ---- En iyi ornekler ----

        print("\n" + "-" * 70)
        print("HER ARKETIPTE EN IYI 3")
        print("-" * 70)

        by_product = {p.product_id: p for p in products}

        for archetype in ARCHETYPES:
            selected = [r for r in rows if r["archetype"] == archetype]
            selected.sort(key=lambda r: -r["score"])

            print(f"\n{archetype}:")
            for row in selected[:3]:
                product = by_product[row["product_id"]]
                title = (product.title_tr or product.title)[:52]
                label = build_reason_sentence(
                    row["reasons"], archetype, product
                ) or "-"
                print(f"  {row['score']:5.1f}  {title}")
                print(f"         {label}")

        if args.dry_run:
            print("\n--dry-run: veritabanina yazilmadi.")
            return

        # ---- Yazma ----
        #
        # ON CONFLICT DO UPDATE: script tekrar kosturuldugunda
        # eski satirlar guncellenir, cift kayit olusmaz.

        print("\n" + "-" * 70)
        print("YAZILIYOR")
        print("-" * 70)

        written = 0

        for start in range(0, len(rows), BATCH_SIZE):
            chunk = rows[start:start + BATCH_SIZE]

            statement = pg_insert(ProductStyleScore).values(chunk)

            statement = statement.on_conflict_do_update(
                index_elements=["product_id", "archetype"],
                set_={
                    "score": statement.excluded.score,
                    "reasons": statement.excluded.reasons,
                    "computed_at": ProductStyleScore.__table__.c
                    .computed_at.server_default.arg,
                },
            )

            session.execute(statement)
            session.commit()

            written += len(chunk)
            print(f"  {written}/{len(rows)}")

        total = session.scalar(
            select(ProductStyleScore.product_id).limit(1)
        )

        print(f"\nTamam. Tabloda ornek kayit: {total}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
