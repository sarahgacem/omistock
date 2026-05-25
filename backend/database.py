from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL de la base de données (SQLite — racine projet, compatible Docker)
import os
BASE_DIR = os.environ.get(
    "OMISTOCK_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
db_path = os.environ.get("OMISTOCK_DB_PATH", os.path.join(BASE_DIR, "stock.db"))
SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

# Moteur de base de données
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Session pour interagir avec la DB
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base pour nos modèles
Base = declarative_base()

# Dépendance pour obtenir la session dans les routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
