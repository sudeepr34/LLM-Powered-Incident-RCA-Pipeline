from __future__ import annotations

import os
from typing import Any

from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()
DATABASE_URL = settings.database_url or os.getenv("RCA_DATABASE_URL", "sqlite:///./rca.db")

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


class AlertRecord(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    service = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    summary = Column(String, nullable=False)
    timestamp = Column(String, nullable=True)
    source = Column(String, nullable=True)


class RCARecord(Base):
    __tablename__ = "rca_results"

    id = Column(Integer, primary_key=True, index=True)
    summary = Column(String, nullable=False)
    clusters = Column(String, nullable=False)
    recommendations = Column(String, nullable=False)


Base.metadata.create_all(bind=engine)
