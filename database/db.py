"""
SmartStock Scanner — Database Engine Setup (SQLite + SQLAlchemy)
"""

import os
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./smartstock.db")

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    """Create all tables if they don't exist."""
    from database.models import MarketData, Analysis, Signal  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully.")


def get_session():
    """Get a new database session."""
    return SessionLocal()
