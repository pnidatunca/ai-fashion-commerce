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

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": 10,
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