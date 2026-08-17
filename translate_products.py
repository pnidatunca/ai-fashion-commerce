from google import genai
from dotenv import load_dotenv
import os
import time

from backend.app.database import SessionLocal
from backend.app.models import Product


# =========================================================
# GEMINI
# =========================================================

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


# =========================================================
# EKSİK ÜRÜNLERİ BUL
# =========================================================

db = SessionLocal()

try:
    products = (
        db.query(Product)
        .filter(
            (Product.title_tr == None)
            | (Product.description_tr == None)
            | (Product.features_tr == None)
        )
        .all()
    )

    product_data = [
        {
            "product_id": p.product_id,
            "title": p.title or "",
            "description": p.description or "",
            "features": p.features or "",
        }
        for p in products
    ]

finally:
    db.close()


print("========================================")
print(f"Eksik ürün sayısı: {len(product_data)}")
print("========================================")


# =========================================================
# ÇEVİRİ
# =========================================================

for item in product_data:

    product_id = item["product_id"]

    while True:

        try:

            print(f"\nÇevriliyor: {product_id}")

            # =================================================
            # GEMINI
            # =================================================

            response = client.models.generate_content(

                model="gemini-3.1-flash-lite",

                contents=f"""Türkçeye çevir.
Doğal ve kısa e-ticaret dili kullan.
Bilgileri değiştirme.

TITLE:
{item["title"]}

DESCRIPTION:
{item["description"]}

FEATURES:
{item["features"]}

Sadece şu formatı kullan:

TITLE:
DESCRIPTION:
FEATURES:
""",

                config={
                    "max_output_tokens": 1500
                }
            )


            text = response.text.strip()


            # =================================================
            # FORMAT KONTROL
            # =================================================

            if (
                "TITLE:" not in text
                or "DESCRIPTION:" not in text
                or "FEATURES:" not in text
            ):

                print("⚠ Gemini cevabı beklenen formatta değil.")
                print("5 saniye sonra tekrar deneniyor...")

                time.sleep(5)

                continue


            # =================================================
            # ÇEVİRİLERİ AYIR
            # =================================================

            title_tr = (
                text
                .split("DESCRIPTION:")[0]
                .replace("TITLE:", "")
                .strip()
            )

            description_tr = (
                text
                .split("DESCRIPTION:")[1]
                .split("FEATURES:")[0]
                .strip()
            )

            features_tr = (
                text
                .split("FEATURES:")[1]
                .strip()
            )


            # =================================================
            # BOŞ CEVAP KONTROLÜ
            # =================================================

            if not title_tr or not description_tr:

                print("⚠ Çeviri boş geldi.")
                print("5 saniye sonra tekrar deneniyor...")

                time.sleep(5)

                continue


            # =================================================
            # DATABASE
            # =================================================

            db = SessionLocal()

            try:

                product = (
                    db.query(Product)
                    .filter(
                        Product.product_id == product_id
                    )
                    .first()
                )


                if product is None:

                    print(
                        f"⚠ Ürün bulunamadı: {product_id}"
                    )

                    break


                # Sadece eksik alanları doldur

                if not product.title_tr:
                    product.title_tr = title_tr

                if not product.description_tr:
                    product.description_tr = description_tr

                if not product.features_tr:
                    product.features_tr = features_tr


                db.commit()

                print(
                    f"✓ Kaydedildi: {product_id}"
                )


            except Exception as db_error:

                db.rollback()

                print(
                    f"❌ DATABASE HATASI: {product_id}"
                )

                print(db_error)

                time.sleep(5)

                continue


            finally:

                db.close()


            # =================================================
            # BAŞARILI
            # =================================================

            time.sleep(5)

            break


        # =====================================================
        # HATALAR
        # =====================================================

        except Exception as e:

            error_text = str(e)


            # =================================================
            # GEMINI KOTA
            # =================================================

            if "429" in error_text:

                print(
                    "⚠ Gemini kota limitine ulaşıldı."
                )

                print(
                    "60 saniye bekleniyor..."
                )

                time.sleep(60)

                continue


            # =================================================
            # DİĞER HATALAR
            # =================================================

            print(
                f"❌ HATA ({product_id}): {e}"
            )

            print(
                "Bu ürün atlanıyor."
            )

            break


# =========================================================
# BİTTİ
# =========================================================

print("\n========================================")
print("ÇEVİRİ İŞLEMİ TAMAMLANDI")
print("========================================")