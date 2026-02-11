# -*- coding: utf-8 -*-
"""
===================================
Precious Metals Analysis - Pipeline
===================================

Orchestrates the precious metals analysis workflow:
1. Fetch market data (gold, silver, correlations)
2. Search for relevant news
3. Run AI analysis for each metal
4. Generate formatted report

Similar pattern to src/core/pipeline.py but for commodities.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import get_config
from src.search_service import SearchService
from src.precious_metals.models import (
    MetalType,
    PreciousMetalsOverview,
    PreciousMetalsAnalysisResult,
)
from src.precious_metals.fetcher import PreciousMetalsFetcher
from src.precious_metals.analyzer import PreciousMetalsAIAnalyzer

logger = logging.getLogger(__name__)


class PreciousMetalsPipeline:
    """
    Pipeline for precious metals analysis

    Workflow:
    1. Fetch market overview (gold, silver, USD, yields)
    2. Search news for each metal
    3. Run AI analysis with error isolation
    4. Return structured results
    """

    def __init__(
        self,
        fetcher: Optional[PreciousMetalsFetcher] = None,
        analyzer: Optional[PreciousMetalsAIAnalyzer] = None,
        search_service: Optional[SearchService] = None,
    ):
        """
        Initialize the pipeline

        Args:
            fetcher: Data fetcher (created if not provided)
            analyzer: AI analyzer (created if not provided)
            search_service: News search service (optional)
        """
        self.fetcher = fetcher or PreciousMetalsFetcher()
        self.analyzer = analyzer or PreciousMetalsAIAnalyzer()

        # Initialize search service from config if not provided
        if search_service is None:
            config = get_config()
            if config.bocha_api_keys or config.tavily_api_keys or config.brave_api_keys or config.serpapi_keys:
                self.search_service = SearchService(
                    bocha_keys=config.bocha_api_keys,
                    tavily_keys=config.tavily_api_keys,
                    brave_keys=config.brave_api_keys,
                    serpapi_keys=config.serpapi_keys
                )
            else:
                self.search_service = None
        else:
            self.search_service = search_service

        self._overview: Optional[PreciousMetalsOverview] = None

    def search_metal_news(self, metal_type: MetalType) -> Optional[str]:
        """
        Search for news related to a precious metal

        Args:
            metal_type: GOLD or SILVER

        Returns:
            Formatted news context string
        """
        if not self.search_service:
            logger.debug("Search service not available, skipping news search")
            return None

        try:
            metal_name = "黄金" if metal_type == MetalType.GOLD else "白银"
            metal_name_en = "gold" if metal_type == MetalType.GOLD else "silver"

            # Enhanced search queries for precious metals
            queries = [
                f"{metal_name} 价格 走势 最新消息",
                f"{metal_name_en} price forecast analysis",
            ]

            # Add metal-specific queries
            if metal_type == MetalType.GOLD:
                queries.extend([
                    "央行购金 黄金储备",
                    "gold ETF holdings demand",
                ])
            else:
                queries.extend([
                    "白银 工业需求 光伏",
                    "silver industrial demand solar",
                ])

            all_results = []
            for query in queries[:3]:  # Limit to 3 queries
                try:
                    results = self.search_service.search(query, max_results=3, days=7)
                    if results:
                        all_results.extend(results)
                        logger.info(f"[News] '{query}' returned {len(results)} results")
                except Exception as e:
                    logger.warning(f"Search failed for '{query}': {e}")

            if not all_results:
                return None

            # Format results - SearchResult is a dataclass, use attribute access
            news_lines = [f"### {metal_name}相关新闻", ""]
            seen_titles = set()
            for item in all_results[:6]:  # Limit to 6 results
                # SearchResult is a dataclass with attributes: title, snippet, url, source, published_date
                title = item.title if hasattr(item, 'title') else item.get('title', '')
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    snippet = item.snippet if hasattr(item, 'snippet') else item.get('snippet', '')
                    snippet = snippet[:200] if snippet else ''
                    source = item.source if hasattr(item, 'source') else item.get('source', '')
                    date = item.published_date if hasattr(item, 'published_date') else item.get('published_date', '')

                    news_lines.append(f"- **{title}**")
                    if date:
                        news_lines.append(f"  日期: {date}")
                    if snippet:
                        news_lines.append(f"  {snippet}")
                    if source:
                        news_lines.append(f"  来源: {source}")
                    news_lines.append("")

            return "\n".join(news_lines) if len(news_lines) > 2 else None

        except Exception as e:
            logger.error(f"News search failed for {metal_type.value}: {e}")
            return None

    def search_macro_news(self) -> Optional[str]:
        """
        Search for macro-economic news affecting precious metals

        Returns:
            Formatted news context string
        """
        if not self.search_service:
            return None

        try:
            queries = [
                "美联储 利率决议 货币政策",
                "Federal Reserve interest rate decision",
                "美元指数 DXY 走势",
                "通胀 CPI 数据",
                "地缘政治 风险 避险",
            ]

            all_results = []
            for query in queries[:3]:  # Limit to 3 queries
                try:
                    results = self.search_service.search(query, max_results=2, days=7)
                    if results:
                        all_results.extend(results)
                        logger.info(f"[Macro] '{query}' returned {len(results)} results")
                except Exception as e:
                    logger.warning(f"Macro search failed for '{query}': {e}")

            if not all_results:
                return None

            news_lines = ["### 宏观经济新闻", ""]
            seen_titles = set()
            for item in all_results[:5]:
                # SearchResult is a dataclass with attributes
                title = item.title if hasattr(item, 'title') else item.get('title', '')
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    snippet = item.snippet if hasattr(item, 'snippet') else item.get('snippet', '')
                    snippet = snippet[:150] if snippet else ''
                    source = item.source if hasattr(item, 'source') else item.get('source', '')

                    news_lines.append(f"- **{title}**")
                    if snippet:
                        news_lines.append(f"  {snippet}")
                    if source:
                        news_lines.append(f"  来源: {source}")
                    news_lines.append("")

            return "\n".join(news_lines) if len(news_lines) > 2 else None

        except Exception as e:
            logger.error(f"Macro news search failed: {e}")
            return None

    def analyze_metal(
        self,
        metal_type: MetalType,
        overview: PreciousMetalsOverview,
        news_context: Optional[str] = None
    ) -> PreciousMetalsAnalysisResult:
        """
        Analyze a single metal

        Args:
            metal_type: GOLD or SILVER
            overview: Market overview data
            news_context: Pre-fetched news

        Returns:
            Analysis result
        """
        metal_name = "黄金" if metal_type == MetalType.GOLD else "白银"
        logger.info(f"Analyzing {metal_name}...")

        quote = overview.gold if metal_type == MetalType.GOLD else overview.silver

        if not quote:
            logger.warning(f"No quote data for {metal_name}")
            return PreciousMetalsAnalysisResult(
                metal_type=metal_type,
                sentiment_score=50,
                trend_prediction="sideways",
                operation_advice="hold",
                confidence_level="low",
                core_conclusion=f"{metal_name}数据获取失败",
                risk_warning="数据缺失，无法分析",
                success=False,
                error_message="Quote data unavailable",
                timestamp=datetime.now(),
            )

        # Run AI analysis
        result = self.analyzer.analyze_metal(
            metal_type=metal_type,
            quote=quote,
            overview=overview,
            news_context=news_context,
        )

        return result

    def run(
        self,
        metals: Optional[List[str]] = None,
        include_news: bool = True,
    ) -> Dict[str, Any]:
        """
        Run the full analysis pipeline

        Args:
            metals: List of metals to analyze ['GOLD', 'SILVER'], defaults to both
            include_news: Whether to search for news

        Returns:
            Dict with overview and analysis results
        """
        logger.info("=" * 60)
        logger.info("Precious Metals Analysis Pipeline Started")
        logger.info("=" * 60)

        # Parse metals list
        if metals is None:
            config = get_config()
            metals = getattr(config, 'precious_metals_list', ['GOLD', 'SILVER'])

        metal_types = []
        for m in metals:
            m_upper = m.upper()
            if m_upper == 'GOLD':
                metal_types.append(MetalType.GOLD)
            elif m_upper == 'SILVER':
                metal_types.append(MetalType.SILVER)

        if not metal_types:
            metal_types = [MetalType.GOLD, MetalType.SILVER]

        # Step 1: Fetch market overview
        logger.info("Step 1: Fetching market data...")
        overview = self.fetcher.get_precious_metals_overview()
        self._overview = overview

        if not overview.data_complete:
            logger.warning("Market data incomplete, analysis may be limited")

        # Step 2: Search news (parallel for each metal + macro)
        news_contexts: Dict[MetalType, Optional[str]] = {}
        macro_news: Optional[str] = None

        if include_news and self.search_service:
            logger.info("Step 2: Searching for news...")

            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {}

                # Submit news search tasks
                for metal_type in metal_types:
                    futures[executor.submit(self.search_metal_news, metal_type)] = metal_type

                # Submit macro news search
                macro_future = executor.submit(self.search_macro_news)

                # Collect results
                for future in as_completed(futures):
                    metal_type = futures[future]
                    try:
                        news_contexts[metal_type] = future.result()
                    except Exception as e:
                        logger.error(f"News search failed for {metal_type.value}: {e}")
                        news_contexts[metal_type] = None

                try:
                    macro_news = macro_future.result()
                except Exception as e:
                    logger.error(f"Macro news search failed: {e}")
        else:
            logger.info("Step 2: Skipping news search")

        # Step 3: Run AI analysis for each metal
        logger.info("Step 3: Running AI analysis...")
        results: Dict[MetalType, PreciousMetalsAnalysisResult] = {}

        for metal_type in metal_types:
            # Combine metal-specific news with macro news
            news_context = news_contexts.get(metal_type)
            if macro_news:
                if news_context:
                    news_context = f"{news_context}\n\n{macro_news}"
                else:
                    news_context = macro_news

            try:
                result = self.analyze_metal(metal_type, overview, news_context)
                results[metal_type] = result
            except Exception as e:
                logger.error(f"Analysis failed for {metal_type.value}: {e}")
                results[metal_type] = PreciousMetalsAnalysisResult(
                    metal_type=metal_type,
                    sentiment_score=50,
                    trend_prediction="sideways",
                    operation_advice="hold",
                    confidence_level="low",
                    core_conclusion=f"分析失败: {str(e)[:50]}",
                    success=False,
                    error_message=str(e),
                    timestamp=datetime.now(),
                )

        logger.info("=" * 60)
        logger.info("Precious Metals Analysis Pipeline Completed")
        logger.info("=" * 60)

        return {
            "overview": overview,
            "results": results,
            "news_contexts": news_contexts,  # Add news to return value
            "macro_news": macro_news,
            "timestamp": datetime.now(),
        }

    def get_overview(self) -> Optional[PreciousMetalsOverview]:
        """Get the cached market overview"""
        return self._overview


def get_precious_metals_pipeline() -> PreciousMetalsPipeline:
    """Get a PreciousMetalsPipeline instance"""
    return PreciousMetalsPipeline()


if __name__ == "__main__":
    # Test the pipeline
    logging.basicConfig(level=logging.INFO)

    pipeline = PreciousMetalsPipeline()
    result = pipeline.run(include_news=False)

    print("\n=== Pipeline Results ===")
    overview = result["overview"]
    if overview.gold:
        print(f"Gold: ${overview.gold.intl_price:.2f}")
    if overview.silver:
        print(f"Silver: ${overview.silver.intl_price:.2f}")

    for metal_type, analysis in result["results"].items():
        print(f"\n{analysis.name}: {analysis.core_conclusion}")
        print(f"  Score: {analysis.sentiment_score}, Trend: {analysis.trend_prediction}")
