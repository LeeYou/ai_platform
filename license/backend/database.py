import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Support AI_LICENSE_DB (path set in docker-compose) or DATABASE_URL (standard)
_license_db = os.environ.get("AI_LICENSE_DB")
if _license_db:
    DATABASE_URL = f"sqlite:///{_license_db}"
else:
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/license.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
