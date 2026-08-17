from backend.app.database import SessionLocal
from backend.app.models import Product

db = SessionLocal()

total = db.query(Product).count()

title_missing = (
    db.query(Product)
    .filter(Product.title_tr == None)
    .count()
)

description_missing = (
    db.query(Product)
    .filter(Product.description_tr == None)
    .count()
)

features_missing = (
    db.query(Product)
    .filter(Product.features_tr == None)
    .count()
)

print("Toplam ürün:", total)
print("Eksik title_tr:", title_missing)
print("Eksik description_tr:", description_missing)
print("Eksik features_tr:", features_missing)

db.close()