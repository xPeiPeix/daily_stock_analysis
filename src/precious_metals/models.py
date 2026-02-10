# -*- coding: utf-8 -*-
"""
===================================
Precious Metals Analysis - Data Models
===================================

Data classes for precious metals (Gold/Silver) analysis:
- MetalQuote: Price data for gold/silver
- CorrelationIndicator: USD index, treasury yields, etc.
- PreciousMetalsOverview: Complete market snapshot
- PreciousMetalsAnalysisResult: AI analysis output
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class MetalType(Enum):
    """Precious metal types"""
    GOLD = "GOLD"
    SILVER = "SILVER"


class TrendDirection(Enum):
    """Trend direction"""
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"


@dataclass
class MetalQuote:
    """
    Price data for a precious metal

    Supports both international (COMEX) and domestic (Shanghai) prices.

    Trading session detection:
    - domestic_is_realtime: True if price from minute K-line during trading
    - domestic_settlement: Settlement price for accurate change calculation
    """
    metal_type: MetalType

    # International prices (COMEX, USD)
    intl_price: Optional[float] = None  # Current price (USD/oz for gold, USD/oz for silver)
    intl_open: Optional[float] = None
    intl_high: Optional[float] = None
    intl_low: Optional[float] = None
    intl_prev_close: Optional[float] = None
    intl_change: Optional[float] = None  # Price change
    intl_change_pct: Optional[float] = None  # Change percentage
    intl_volume: Optional[float] = None

    # Domestic prices (Shanghai, CNY)
    domestic_price: Optional[float] = None  # CNY/g for gold, CNY/kg for silver
    domestic_open: Optional[float] = None
    domestic_high: Optional[float] = None
    domestic_low: Optional[float] = None
    domestic_prev_close: Optional[float] = None
    # Change based on settlement price (交易所官方标准)
    domestic_change: Optional[float] = None
    domestic_change_pct: Optional[float] = None
    # Change based on close price (收盘价基准)
    domestic_change_by_close: Optional[float] = None
    domestic_change_pct_by_close: Optional[float] = None
    domestic_settlement: Optional[float] = None  # Today's settlement price (结算价)
    domestic_prev_settlement: Optional[float] = None  # Previous day settlement
    domestic_is_realtime: bool = False  # Whether price is from today's trading
    domestic_price_time: Optional[str] = None  # Time of the price (HH:MM)

    # Technical indicators
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None

    # Metadata
    timestamp: Optional[datetime] = None
    data_source: str = ""

    @property
    def name(self) -> str:
        """Get metal name in Chinese"""
        return "黄金" if self.metal_type == MetalType.GOLD else "白银"

    @property
    def name_en(self) -> str:
        """Get metal name in English"""
        return "Gold" if self.metal_type == MetalType.GOLD else "Silver"

    @property
    def trend_emoji(self) -> str:
        """Get trend emoji based on change percentage"""
        if self.intl_change_pct is None:
            return "⚪"
        if self.intl_change_pct > 0.5:
            return "🟢"
        elif self.intl_change_pct < -0.5:
            return "🔴"
        return "🟡"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "metal_type": self.metal_type.value,
            "name": self.name,
            "intl_price": self.intl_price,
            "intl_open": self.intl_open,
            "intl_high": self.intl_high,
            "intl_low": self.intl_low,
            "intl_prev_close": self.intl_prev_close,
            "intl_change": self.intl_change,
            "intl_change_pct": self.intl_change_pct,
            "domestic_price": self.domestic_price,
            "domestic_change_pct": self.domestic_change_pct,
            "ma5": self.ma5,
            "ma10": self.ma10,
            "ma20": self.ma20,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data_source": self.data_source,
        }


@dataclass
class CorrelationIndicator:
    """
    Correlation indicators for precious metals analysis

    Key factors affecting gold/silver prices:
    - USD Index (DXY): Inverse correlation with gold
    - Treasury Yields: Higher yields = bearish for gold
    - Inflation expectations: Higher inflation = bullish for gold
    """
    name: str
    value: Optional[float] = None
    prev_value: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    impact: str = ""  # "bullish", "bearish", "neutral"
    description: str = ""
    timestamp: Optional[datetime] = None

    @property
    def impact_emoji(self) -> str:
        """Get impact emoji for metals"""
        if self.impact == "bullish":
            return "🟢"
        elif self.impact == "bearish":
            return "🔴"
        return "🟡"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "value": self.value,
            "prev_value": self.prev_value,
            "change": self.change,
            "change_pct": self.change_pct,
            "impact": self.impact,
            "impact_emoji": self.impact_emoji,
            "description": self.description,
        }


@dataclass
class PreciousMetalsOverview:
    """
    Complete market snapshot for precious metals

    Contains:
    - Gold and Silver quotes
    - Correlation indicators (USD, yields, etc.)
    - Gold/Silver ratio
    - Market summary
    """
    # Metal quotes
    gold: Optional[MetalQuote] = None
    silver: Optional[MetalQuote] = None

    # Correlation indicators
    usd_index: Optional[CorrelationIndicator] = None
    treasury_10y: Optional[CorrelationIndicator] = None

    # Calculated metrics
    gold_silver_ratio: Optional[float] = None  # Gold price / Silver price
    gold_silver_ratio_change: Optional[float] = None

    # Metadata
    timestamp: Optional[datetime] = None
    data_complete: bool = False

    @property
    def gold_silver_ratio_status(self) -> str:
        """Interpret gold/silver ratio"""
        if self.gold_silver_ratio is None:
            return "数据缺失"
        if self.gold_silver_ratio > 90:
            return "极高（白银相对低估）"
        elif self.gold_silver_ratio > 80:
            return "偏高（白银可能补涨）"
        elif self.gold_silver_ratio > 70:
            return "正常区间"
        elif self.gold_silver_ratio > 60:
            return "偏低（黄金相对低估）"
        else:
            return "极低（黄金可能补涨）"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "gold": self.gold.to_dict() if self.gold else None,
            "silver": self.silver.to_dict() if self.silver else None,
            "usd_index": self.usd_index.to_dict() if self.usd_index else None,
            "treasury_10y": self.treasury_10y.to_dict() if self.treasury_10y else None,
            "gold_silver_ratio": self.gold_silver_ratio,
            "gold_silver_ratio_status": self.gold_silver_ratio_status,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data_complete": self.data_complete,
        }


@dataclass
class PreciousMetalsAnalysisResult:
    """
    AI analysis result for precious metals

    Similar to stock AnalysisResult but tailored for commodities:
    - Macro-driven analysis (USD, inflation, yields)
    - Support/resistance levels instead of MA alignment
    - Trend prediction (short-term and medium-term)
    """
    metal_type: MetalType

    # Core indicators
    sentiment_score: int = 50  # 0-100
    trend_prediction: str = "sideways"  # up/down/sideways
    operation_advice: str = "hold"  # buy/hold/sell
    confidence_level: str = "medium"  # high/medium/low

    # Core conclusion
    core_conclusion: str = ""  # One-sentence recommendation

    # Macro analysis
    macro_analysis: Optional[Dict[str, str]] = None
    correlation_summary: str = ""

    # Technical analysis
    technical_analysis: Optional[Dict[str, Any]] = None
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)

    # Trend prediction
    short_term_outlook: str = ""  # 1-3 days
    medium_term_outlook: str = ""  # 1-2 weeks

    # Risk and catalysts
    risk_warning: str = ""
    positive_catalysts: List[str] = field(default_factory=list)
    negative_catalysts: List[str] = field(default_factory=list)

    # News summary
    news_summary: str = ""

    # Metadata
    analysis_summary: str = ""
    raw_response: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None

    @property
    def name(self) -> str:
        """Get metal name in Chinese"""
        return "黄金" if self.metal_type == MetalType.GOLD else "白银"

    @property
    def advice_emoji(self) -> str:
        """Get emoji based on operation advice"""
        emoji_map = {
            "buy": "🟢",
            "strong_buy": "💚",
            "hold": "🟡",
            "sell": "🔴",
            "strong_sell": "❌",
        }
        return emoji_map.get(self.operation_advice, "🟡")

    @property
    def trend_emoji(self) -> str:
        """Get emoji based on trend prediction"""
        if self.trend_prediction == "up":
            return "📈"
        elif self.trend_prediction == "down":
            return "📉"
        return "➡️"

    def get_confidence_stars(self) -> str:
        """Return confidence level as stars"""
        star_map = {"high": "⭐⭐⭐", "medium": "⭐⭐", "low": "⭐"}
        return star_map.get(self.confidence_level, "⭐⭐")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "metal_type": self.metal_type.value,
            "name": self.name,
            "sentiment_score": self.sentiment_score,
            "trend_prediction": self.trend_prediction,
            "operation_advice": self.operation_advice,
            "confidence_level": self.confidence_level,
            "core_conclusion": self.core_conclusion,
            "macro_analysis": self.macro_analysis,
            "correlation_summary": self.correlation_summary,
            "technical_analysis": self.technical_analysis,
            "support_levels": self.support_levels,
            "resistance_levels": self.resistance_levels,
            "short_term_outlook": self.short_term_outlook,
            "medium_term_outlook": self.medium_term_outlook,
            "risk_warning": self.risk_warning,
            "positive_catalysts": self.positive_catalysts,
            "negative_catalysts": self.negative_catalysts,
            "news_summary": self.news_summary,
            "analysis_summary": self.analysis_summary,
            "success": self.success,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
