import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# ---------------------------------------------------------
# .ENV
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"

load_dotenv(ENV_FILE)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL bulunamadi. "
        "Repo kokundeki .env dosyasini kontrol et."
    )


# ---------------------------------------------------------
# PSYCOPG 3
# ---------------------------------------------------------

# Neon:
# postgresql://...
#
# SQLAlchemy + Psycopg 3:
# postgresql+psycopg://...

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )


# ---------------------------------------------------------
# ENGINE
# ---------------------------------------------------------

# connect_timeout NEDEN 10 DEGIL 5
#
# Neon uc bilgisi UC AYRI IP'ye cozuluyor ve psycopg
# hepsini SIRAYLA deniyor. Yani gercek bekleme suresi
# timeout'un UC KATI:
#
#     10 saniye  ->  kullanici 30 saniye bos ekrana bakiyor
#      5 saniye  ->  15 saniye
#
# Saglikli durumda Neon baglantisi 200 ms'nin altinda
# aciliyor; askidan uyanma bile birkac saniye. 5 saniye
# cok rahat yetiyor, tek etkisi ARIZADA daha hizli
# vazgecmek.
#
# pool_recycle: Neon bosta duran baglantilari kendisi
# kapatiyor. Havuzdaki olu baglantiyi kullanmaya calismak
# ilk istekte hataya yol aciyordu; 25 dakikada bir
# yenileniyor. pool_pre_ping bunu zaten yakaliyor ama
# recycle bir tur gidip gelmeyi de tasarruf ediyor.

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1500,
    connect_args={
        "connect_timeout": 5,
    },
)


# ---------------------------------------------------------
# SESSION
# ---------------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------
# BASE
# ---------------------------------------------------------

Base = declarative_base()


# ---------------------------------------------------------
# FASTAPI DEPENDENCY
# ---------------------------------------------------------

def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()