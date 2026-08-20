"""
user_interactions tablosunu Recommendation / Collaborative
Filtering egitimi icin hazir CSV dosyalarina cikarir.

Uretilen dosyalar (data/ klasoru, .gitignore kapsaminda):

    interactions_raw.csv      ham olay kaydi
    interactions_labeled.csv  agirlik + indeks eklenmis hali
    user_index.csv            user_id  -> user_idx
    item_index.csv            product_id -> item_idx

Kullanim:
    python scripts/07_export_training_data.py
    python scripts/07_export_training_data.py --since 2026-08-01
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text

from app.database import engine

OUT_DIR = ROOT / "data"


# ---------------------------------------------------------
# IMPLICIT FEEDBACK AGIRLIKLARI
# ---------------------------------------------------------

# Bu esleme bir MODEL KARARIDIR, veri degil. Farkli
# denemelerde degistirilebilir:
#
#   LIKE     guclu pozitif  (kullanici acikca istedi)
#   VIEW     zayif pozitif  (sadece gordu, ilgi belirsiz)
#   UNLIKE   zayif negatif  (favoriden cikardi, nefret degil)
#   DISLIKE  guclu negatif  (bir daha gostermeyin dedi)
#
# ALS / BPR gibi implicit modeller yalnizca pozitif sinyalle
# calisir; negatifleri "gostermeyecegimiz urunler" listesi
# olarak ayri kullanmak daha dogru sonuc verir.

# AGIRLIK ARTIK VERITABANINDAN GELIYOR.
#
# user_interactions.weight kolonu olay yazilirken
# dolduruluyor (models.INTERACTION_WEIGHTS). Asagidaki
# tablo yalnizca YEDEK: eski satirlarda weight 0 kalmissa
# kullanilir.
#
# Neden satirdan okumak daha dogru: agirlik esleme tablosu
# zamanla degisir. Export sirasinda hesaplarsak alti ay
# sonra gecmis olaylara BUGUNUN agirliklari uygulanir ve
# model farkli bir gecmis ogrenir.

FALLBACK_WEIGHTS = {
    "QUICK_BUY": 2.0,
    "LIKE": 1.0,
    "VIEW": 0.1,
    "UNLIKE": -0.3,
    "DISLIKE": -1.0,
    "INITIAL_STYLE": 0.0,
}

# QUICK_BUY en guclu pozitif: kullanici sadece begenmiyor,
# para harcamaya niyet ediyor.
POSITIVE_TYPES = ("QUICK_BUY", "LIKE")
NEGATIVE_TYPES = ("DISLIKE",)

# Kullanici-urun matrisine giren turler.
# INITIAL_STYLE haric: urun kimligi yoktur.
MATRIX_TYPES = ("QUICK_BUY", "LIKE", "VIEW", "UNLIKE", "DISLIKE")


QUERY = """
    SELECT
        ui.id                AS interaction_id,
        ui.user_id,
        ui.product_id,
        ui.interaction_type,
        ui.source,
        ui.position,
        ui.created_at,

        -- Etkilesim aninda kullaniciya gosterilen AI skoru
        ui.match_score,

        -- O anda aktif olan stil arketipi
        ui.style_archetype,

        -- Etkilesim anindaki butun secili tarzlar
        ui.selected_styles,

        -- Olay aninda gecerli olan ML agirligi
        ui.weight,

        u.gender             AS user_gender,
        u.age                AS user_age,

        -- Kullanicinin GUNCEL profili
        up.style_archetype   AS user_archetype,
        up.like_count        AS user_like_count,
        up.median_price      AS user_median_price,

        p.brand              AS product_brand,
        p.category           AS product_category,
        p.price              AS product_price,
        p.rating             AS product_rating,
        p.rating_count       AS product_rating_count,

        -- Urunun o arketipteki temel stil skoru
        pss.score            AS product_style_score
    FROM user_interactions ui
    JOIN users u
      ON u.id = ui.user_id
    LEFT JOIN user_preferences up
      ON up.user_id = ui.user_id
    LEFT JOIN products p
      ON p.product_id = ui.product_id
    LEFT JOIN product_style_scores pss
      ON pss.product_id = ui.product_id
     AND pss.archetype = ui.style_archetype
    {where}
    ORDER BY ui.created_at, ui.id
"""


def load_dataframe(since=None):
    where = "WHERE ui.created_at >= :since" if since else ""

    with engine.connect() as connection:
        result = connection.execute(
            text(QUERY.format(where=where)),
            {"since": since} if since else {},
        )
        rows = result.fetchall()
        columns = list(result.keys())

    return pd.DataFrame(rows, columns=columns)


def summarize(frame):
    print("=" * 70)
    print("ETKILESIM OZETI")
    print("=" * 70)

    if frame.empty:
        print("\nHenuz etkilesim kaydi yok.")
        print("Sitede Kesfet bolumunde kalp / begenmedim")
        print("butonlarini kullandiktan sonra tekrar dene.")
        return False

    print(f"\ntoplam olay      : {len(frame)}")
    print(f"tekil kullanici  : {frame['user_id'].nunique()}")
    print(f"tekil urun       : {frame['product_id'].nunique()}")
    print(f"ilk olay         : {frame['created_at'].min()}")
    print(f"son olay         : {frame['created_at'].max()}")

    print("\ntur dagilimi:")
    for kind, count in frame["interaction_type"].value_counts().items():
        print(f"  {kind:<9} {count}")

    print("\nkaynak dagilimi:")
    for source, count in (
        frame["source"].fillna("(bos)").value_counts().items()
    ):
        print(f"  {source:<10} {count}")

    print("\nagirlik toplamlari (tur bazinda):")
    grouped = frame.groupby("interaction_type")["weight"].agg(
        ["count", "mean", "sum"]
    )
    for kind, row in grouped.iterrows():
        print(
            f"  {kind:<14} {int(row['count']):>4} olay  "
            f"agirlik={row['mean']:+.2f}  toplam={row['sum']:+.1f}"
        )

    buys = frame[frame["interaction_type"] == "QUICK_BUY"]

    if len(buys):
        print(f"\nsatin alma niyeti : {len(buys)} olay")
        print("  (en guclu pozitif sinyal — oneri modelinde")
        print("   LIKE'tan daha agir tutulmali)")

    print("\narketip dagilimi (etkilesim anindaki):")
    for archetype, count in (
        frame["style_archetype"].fillna("(yok)").value_counts().items()
    ):
        print(f"  {archetype:<12} {count}")

    # AI skoru kaydedilmis olaylar: model degerlendirmesi
    # icin en degerli alt kume
    scored = frame[frame["match_score"].notna()]
    print(f"\nmatch_score kayitli olay : {len(scored)}/{len(frame)}")

    if len(scored):
        likes = scored[scored["interaction_type"] == "LIKE"]
        dislikes = scored[scored["interaction_type"] == "DISLIKE"]

        for kind, subset in (("LIKE", likes), ("DISLIKE", dislikes)):
            if len(subset):
                print(
                    f"  {kind:<8} ortalama gosterilen skor : "
                    f"{subset['match_score'].mean():.1f} "
                    f"({len(subset)} olay)"
                )

        if len(likes) and len(dislikes):
            gap = (
                likes["match_score"].mean()
                - dislikes["match_score"].mean()
            )
            print(f"\nLIKE - DISLIKE skor farki : {gap:+.1f}")
            print(
                "  (pozitif beklenir: yuksek skorlu urunler"
                " daha cok begenilmeli)"
            )

    # Collaborative filtering icin matris seyrekligi.
    # INITIAL_STYLE satirlari haric: urun kimligi yok.
    matrix = frame[frame["interaction_type"].isin(MATRIX_TYPES)]

    users = matrix["user_id"].nunique()
    items = matrix["product_id"].nunique()
    pairs = matrix.groupby(["user_id", "product_id"]).ngroups

    if users and items:
        density = pairs / (users * items)
        print(f"\nkullanici x urun hucre  : {users * items}")
        print(f"dolu hucre              : {pairs}")
        print(f"yogunluk                : {density:.4%}")
        print(f"seyreklik               : {1 - density:.4%}")

    return True


def add_training_columns(frame):
    frame = frame.copy()

    # Satirda yazili agirligi kullan; 0 ise (eski satir)
    # yedek tabloya dus.
    frame["weight"] = frame["weight"].where(
        frame["weight"].ne(0),
        frame["interaction_type"].map(FALLBACK_WEIGHTS).fillna(0.0),
    )

    frame["is_positive"] = frame["interaction_type"].isin(
        POSITIVE_TYPES
    )

    frame["is_negative"] = frame["interaction_type"].isin(
        NEGATIVE_TYPES
    )

    # Kullanici-urun matrisine girer mi
    frame["in_matrix"] = frame["interaction_type"].isin(
        MATRIX_TYPES
    ) & frame["product_id"].notna()

    # Matris ayristirma kutuphaneleri (implicit, surprise,
    # LightFM) string kimlik degil tamsayi indeks bekler.
    user_ids = sorted(frame["user_id"].astype(str).unique())
    item_ids = sorted(
        frame.loc[frame["product_id"].notna(), "product_id"]
        .astype(str)
        .unique()
    )

    user_index = {value: index for index, value in enumerate(user_ids)}
    item_index = {value: index for index, value in enumerate(item_ids)}

    frame["user_idx"] = frame["user_id"].astype(str).map(user_index)
    frame["item_idx"] = frame["product_id"].astype(str).map(item_index)

    user_frame = pd.DataFrame(
        {"user_id": user_ids, "user_idx": range(len(user_ids))}
    )

    item_frame = pd.DataFrame(
        {"product_id": item_ids, "item_idx": range(len(item_ids))}
    )

    return frame, user_frame, item_frame


def suggest_split(frame):
    """
    Oneri sistemlerinde rastgele bolme veri sizdirir:
    modelin gelecegi gormesine izin verir. Zaman bazli
    bolme dogru olanidir.
    """

    print("\n" + "=" * 70)
    print("ONERILEN TRAIN / TEST BOLMESI (temporal split)")
    print("=" * 70)

    ordered = frame.sort_values("created_at")
    cut = int(len(ordered) * 0.8)

    if cut == 0 or cut == len(ordered):
        print("\nBolme icin yeterli veri yok.")
        return

    boundary = ordered.iloc[cut]["created_at"]

    print(f"\nkesim zamani : {boundary}")
    print(f"train        : {cut} olay")
    print(f"test         : {len(ordered) - cut} olay")
    print("\nKod:")
    print("    train = df[df.created_at <  BOUNDARY]")
    print("    test  = df[df.created_at >= BOUNDARY]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--since",
        help="Sadece bu tarihten sonraki olaylar (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    frame = load_dataframe(since=args.since)

    if not summarize(frame):
        return

    OUT_DIR.mkdir(exist_ok=True)

    raw_path = OUT_DIR / "interactions_raw.csv"
    frame.to_csv(raw_path, index=False, encoding="utf-8")

    labeled, user_frame, item_frame = add_training_columns(frame)

    labeled_path = OUT_DIR / "interactions_labeled.csv"
    labeled.to_csv(labeled_path, index=False, encoding="utf-8")

    user_path = OUT_DIR / "user_index.csv"
    user_frame.to_csv(user_path, index=False, encoding="utf-8")

    item_path = OUT_DIR / "item_index.csv"
    item_frame.to_csv(item_path, index=False, encoding="utf-8")

    suggest_split(frame)

    print("\n" + "=" * 70)
    print("YAZILAN DOSYALAR")
    print("=" * 70)
    for path in (raw_path, labeled_path, user_path, item_path):
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size} bayt)")

    print("\nOrnek kullanim:")
    print("    import pandas as pd")
    print("    df = pd.read_csv('data/interactions_labeled.csv')")
    print("    positives = df[df.is_positive]")
    print("    blocked   = df[df.is_negative]  # onerilerden cikar")


if __name__ == "__main__":
    main()
