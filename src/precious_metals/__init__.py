# -*- coding: utf-8 -*-
"""
===================================
Precious Metals Analysis Module
===================================

International precious metals (Gold/Silver) analysis with:
- Macro correlation indicators (USD Index, Treasury Yields)
- AI-powered trend prediction
- Support/resistance level analysis

Usage:
    from src.precious_metals import run_precious_metals_review
    run_precious_metals_review()

Or use individual components:
    from src.precious_metals import (
        PreciousMetalsFetcher,
        PreciousMetalsAIAnalyzer,
        PreciousMetalsPipeline,
    )
"""

from src.precious_metals.models import (
    MetalType,
    TrendDirection,
    MetalQuote,
    CorrelationIndicator,
    PreciousMetalsOverview,
    PreciousMetalsAnalysisResult,
)

from src.precious_metals.fetcher import (
    PreciousMetalsFetcher,
    get_precious_metals_fetcher,
)

from src.precious_metals.analyzer import (
    PreciousMetalsAIAnalyzer,
    get_precious_metals_analyzer,
)

from src.precious_metals.pipeline import (
    PreciousMetalsPipeline,
    get_precious_metals_pipeline,
)

from src.precious_metals.review import (
    run_precious_metals_review,
    generate_precious_metals_report,
)

__all__ = [
    # Models
    "MetalType",
    "TrendDirection",
    "MetalQuote",
    "CorrelationIndicator",
    "PreciousMetalsOverview",
    "PreciousMetalsAnalysisResult",
    # Fetcher
    "PreciousMetalsFetcher",
    "get_precious_metals_fetcher",
    # Analyzer
    "PreciousMetalsAIAnalyzer",
    "get_precious_metals_analyzer",
    # Pipeline
    "PreciousMetalsPipeline",
    "get_precious_metals_pipeline",
    # Review
    "run_precious_metals_review",
    "generate_precious_metals_report",
]
