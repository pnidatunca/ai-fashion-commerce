# İşletim sistemi değişkenlerine erişmek için kullanıyoruz.
# Burada .env içerisindeki DATABASE_URL değerini okuyacağız.
import os

# .env dosyasını Python'a okutmak için kullanıyoruz.
from dotenv import find_dotenv, load_dotenv

# PostgreSQL bağlantısı oluşturmak için SQLAlchemy'den create_engine'i alıyoruz.
from sqlalchemy import create_engine

# Database oturumları (session) oluşturmak için kullanıyoruz.
from sqlalchemy.orm import sessionmaker, declarative_base


# .env dosyasındaki değişkenleri yükler (otomatik olarak kök dizine kadar arar).
load_dotenv(find_dotenv(usecwd=True))


# .env içerisindeki DATABASE_URL değerini alıyoruz.
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)



# Neon PostgreSQL ile bağlantı oluşturuyoruz.
#
# DATABASE_URL:
# Neon'a ait bağlantı adresimiz.
#
# pool_pre_ping=True:
# Kullanılmadan önce database bağlantısının çalışıp çalışmadığını
# kontrol etmeye yardımcı olur.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "connect_timeout": 15,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
)


# Database ile işlem yaparken kullanacağımız session'ları oluşturur.
#
# Örneğin ileride:
# - ürün ekleme
# - ürün silme
# - ürün arama
# gibi işlemlerde bu session'ı kullanacağız.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# SQLAlchemy modellerimizin temelini oluşturur.
#
# Örneğin ileride:
#
# class Product(Base):
#     ...
#
# dediğimizde Product modeli bu Base'i kullanacak.
Base = declarative_base()


# API endpointlerinde database bağlantısı almak için kullanacağımız fonksiyon.
def get_db():

    # Yeni bir database session oluşturuyoruz.
    db = SessionLocal()

    try:
        # Oluşturduğumuz database bağlantısını endpoint'e veriyoruz.
        yield db

    finally:
        # İşlem bittikten sonra database bağlantısını kapatıyoruz.
        db.close()  