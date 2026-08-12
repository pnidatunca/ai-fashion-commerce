from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine


# FastAPI uygulamasını oluşturuyoruz.
app = FastAPI()


# Ana sayfa
# Bu endpoint database'e bağlanmaz.
# Sadece FastAPI'nin çalışıp çalışmadığını kontrol eder.
@app.get("/")
def home():

    return {
        "message": "AI Shopping API çalışıyor"
    }


# Database bağlantısını test etmek için kullanacağımız endpoint.
@app.get("/db-test")
def db_test():

    # Database'e bağlantı açıyoruz.
    with engine.connect() as connection:

        # PostgreSQL'e basit bir test sorgusu gönderiyoruz.
        result = connection.execute(text("SELECT 1"))

        # Database'den gelen sonucu döndürüyoruz.
        return {
            "database": "connected",
            "result": result.scalar()
        }