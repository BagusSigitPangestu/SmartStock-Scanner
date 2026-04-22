"""
SmartStock Scanner — Database Models
Tables: MarketData, Analysis, Signal (as per PRD schema)
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from database.db import Base


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)


class Analysis(Base):
    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    kalman_val = Column(Float)
    kalman_slope = Column(Float)
    rsi = Column(Float)
    ma_status = Column(String(30))
    pattern_name = Column(String(100))
    score = Column(Integer)
    trade_type = Column(String(20))
    details = Column(Text)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    trade_type = Column(String(20))  # Day Trading / Swing / BSJP
    entry = Column(Float)
    tp = Column(Float)
    sl = Column(Float)
    score = Column(Integer)
    risk_pct = Column(Float)
    win_loss_status = Column(String(10), default="OPEN")  # OPEN / WIN / LOSS
