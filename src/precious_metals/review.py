# -*- coding: utf-8 -*-
"""
===================================
Precious Metals Analysis - Review Entry Point
===================================

Entry point for precious metals daily review:
- Similar to run_market_review() in src/core/market_review.py
- Generates and sends precious metals report
- Supports notification via configured channels
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from src.config import get_config
from src.notification import NotificationService
from src.search_service import SearchService
from src.precious_metals.models import (
    MetalType,
    PreciousMetalsOverview,
    PreciousMetalsAnalysisResult,
    COTPositions,
    OISignal,
)
from src.precious_metals.pipeline import PreciousMetalsPipeline
from src.precious_metals.analyzer import PreciousMetalsAIAnalyzer

logger = logging.getLogger(__name__)


def generate_precious_metals_report(
    overview: PreciousMetalsOverview,
    results: Dict[MetalType, PreciousMetalsAnalysisResult],
    news_contexts: Optional[Dict[MetalType, str]] = None,
    macro_news: Optional[str] = None,
) -> str:
    """
    Generate markdown report for precious metals

    Args:
        overview: Market overview data
        results: Analysis results for each metal
        news_contexts: News context for each metal
        macro_news: Macro economic news

    Returns:
        Formatted markdown report
    """
    date_str = datetime.now().strftime('%Y-%m-%d')

    report_lines = [
        f"# 🥇 贵金属日报 - {date_str}",
        "",
        "## 📊 国际市场 (COMEX)",
        "",
        "| 品种 | 价格 | 涨跌幅 | 趋势 |",
        "|------|------|--------|------|",
    ]

    # Gold row - International
    if overview.gold:
        gold_emoji = overview.gold.trend_emoji
        realtime_tag = "🔴" if overview.gold.data_source and "实时" in overview.gold.data_source else ""
        gold_price = f"${overview.gold.intl_price:.2f}" if overview.gold.intl_price is not None else "N/A"
        gold_change = f"{overview.gold.intl_change_pct:+.2f}%" if overview.gold.intl_change_pct is not None else "N/A"
        report_lines.append(f"| 黄金 {realtime_tag} | {gold_price} | {gold_change} | {gold_emoji} |")

    # Silver row - International
    if overview.silver:
        silver_emoji = overview.silver.trend_emoji
        realtime_tag = "🔴" if overview.silver.data_source and "实时" in overview.silver.data_source else ""
        silver_price = f"${overview.silver.intl_price:.2f}" if overview.silver.intl_price is not None else "N/A"
        silver_change = f"{overview.silver.intl_change_pct:+.2f}%" if overview.silver.intl_change_pct is not None else "N/A"
        report_lines.append(f"| 白银 {realtime_tag} | {silver_price} | {silver_change} | {silver_emoji} |")

    # Gold/Silver ratio
    if overview.gold_silver_ratio is not None:
        ratio_change = f"{overview.gold_silver_ratio_change:+.2f}" if overview.gold_silver_ratio_change is not None else ""
        report_lines.append(f"| 金银比 | {overview.gold_silver_ratio:.2f} | {ratio_change} | - |")

    report_lines.extend(["", "> 🔴 = 实时价格", ""])

    # Domestic market section
    has_domestic = (overview.gold and overview.gold.domestic_price) or \
                   (overview.silver and overview.silver.domestic_price)

    if has_domestic:
        report_lines.extend([
            "## 📊 国内市场 (上海期货)",
            "",
            "| 品种 | 价格 | vs结算价 | vs收盘价 |",
            "|------|------|----------|----------|",
        ])

        # Gold - Domestic
        if overview.gold and overview.gold.domestic_price:
            unit = "元/克"
            price_time = f" @{overview.gold.domestic_price_time}" if overview.gold.domestic_price_time else ""
            realtime_tag = "🔴" if overview.gold.domestic_is_realtime else ""
            price_str = f"¥{overview.gold.domestic_price:.2f}{unit}{price_time}"
            pct_settlement = f"{overview.gold.domestic_change_pct:+.2f}%" if overview.gold.domestic_change_pct is not None else "N/A"
            pct_close = f"{overview.gold.domestic_change_pct_by_close:+.2f}%" if overview.gold.domestic_change_pct_by_close is not None else "N/A"
            report_lines.append(f"| 沪金 {realtime_tag} | {price_str} | {pct_settlement} | {pct_close} |")

        # Silver - Domestic
        if overview.silver and overview.silver.domestic_price:
            unit = "元/千克"
            price_time = f" @{overview.silver.domestic_price_time}" if overview.silver.domestic_price_time else ""
            realtime_tag = "🔴" if overview.silver.domestic_is_realtime else ""
            price_str = f"¥{overview.silver.domestic_price:.0f}{unit}{price_time}"
            pct_settlement = f"{overview.silver.domestic_change_pct:+.2f}%" if overview.silver.domestic_change_pct is not None else "N/A"
            pct_close = f"{overview.silver.domestic_change_pct_by_close:+.2f}%" if overview.silver.domestic_change_pct_by_close is not None else "N/A"
            report_lines.append(f"| 沪银 {realtime_tag} | {price_str} | {pct_settlement} | {pct_close} |")

        report_lines.extend([
            "",
            "> 结算价=交易所官方均价，收盘价=最后成交价",
            "",
        ])

    # Correlation indicators section
    report_lines.extend([
        "## 🔗 相关性指标",
        "",
        "| 指标 | 数值 | 变化 | 影响 |",
        "|------|------|------|------|",
    ])

    if overview.usd_index:
        usd_change = f"{overview.usd_index.change_pct:+.2f}%" if overview.usd_index.change_pct else "N/A"
        report_lines.append(
            f"| 美元指数 | {overview.usd_index.value:.2f} | {usd_change} | "
            f"{overview.usd_index.impact_emoji} {overview.usd_index.description} |"
        )

    if overview.treasury_10y:
        yield_change = f"{overview.treasury_10y.change:+.2f}" if overview.treasury_10y.change else "N/A"
        report_lines.append(
            f"| 10年期美债 | {overview.treasury_10y.value:.2f}% | {yield_change} | "
            f"{overview.treasury_10y.impact_emoji} {overview.treasury_10y.description} |"
        )

    report_lines.append("")

    # COT positions section
    if overview.gold_cot or overview.silver_cot:
        # Get report date and clean format
        report_date = overview.gold_cot.report_date if overview.gold_cot else overview.silver_cot.report_date
        if 'T' in report_date:
            report_date = report_date.split('T')[0]

        # Calculate delay days
        try:
            cot_date_obj = datetime.strptime(report_date, '%Y-%m-%d')
            delay_days = (datetime.now() - cot_date_obj).days
            delay_text = f"距今 {delay_days} 天"
        except ValueError:
            delay_text = "约3-8天延迟"

        report_lines.extend([
            "## 📈 CFTC 投机者持仓 (历史参考)",
            "",
            f"> ⚠️ **滞后数据**: 截至 {report_date}，{delay_text}。COT报告每周五发布，反映周二持仓，仅供宏观情绪参考。",
            "",
            "| 品种 | 多头 | 空头 | 净持仓 | 多头占比 | 历史偏向 |",
            "|------|------|------|--------|----------|----------|",
        ])

        if overview.gold_cot:
            cot = overview.gold_cot
            report_lines.append(
                f"| 黄金 | {cot.long_positions:,} | {cot.short_positions:,} | "
                f"{cot.net_positions:+,} | {cot.net_long_pct:.1f}% | {cot.bias_cn} |"
            )

        if overview.silver_cot:
            cot = overview.silver_cot
            report_lines.append(
                f"| 白银 | {cot.long_positions:,} | {cot.short_positions:,} | "
                f"{cot.net_positions:+,} | {cot.net_long_pct:.1f}% | {cot.bias_cn} |"
            )

        report_lines.append("")

    # OI signals section
    if overview.gold_oi_signal or overview.silver_oi_signal:
        report_lines.extend([
            "## 🔄 价格+持仓信号 (上海期货)",
            "",
            "| 品种 | 价格变化 | OI变化 | 信号 |",
            "|------|----------|--------|------|",
        ])

        if overview.gold_oi_signal:
            sig = overview.gold_oi_signal
            report_lines.append(
                f"| 🥇 黄金 | {sig.price_change_pct:+.2f}% | {sig.oi_change_pct:+.2f}% | "
                f"{sig.signal_emoji} **{sig.signal_cn}** |"
            )

        if overview.silver_oi_signal:
            sig = overview.silver_oi_signal
            report_lines.append(
                f"| 🥈 白银 | {sig.price_change_pct:+.2f}% | {sig.oi_change_pct:+.2f}% | "
                f"{sig.signal_emoji} **{sig.signal_cn}** |"
            )

        report_lines.extend([
            "",
            "> **信号解读**：",
            "> - 多开：价格↑ + OI↑ = 新多头入场（趋势可能延续）",
            "> - 空平：价格↑ + OI↓ = 空头平仓（止损或获利，上涨动能可能减弱）",
            "> - 空开：价格↓ + OI↑ = 新空头入场（趋势可能延续）",
            "> - 多平：价格↓ + OI↓ = 多头平仓（止损或获利，下跌动能可能减弱）",
            "",
        ])

    # News section - 优先使用 AI 返回的 news_summary，fallback 到原始搜索结果
    ai_news_summaries = []
    for metal_type in [MetalType.GOLD, MetalType.SILVER]:
        if metal_type in results and results[metal_type].news_summary:
            ai_news_summaries.append((metal_type, results[metal_type].news_summary))

    if ai_news_summaries:
        # 使用 AI 清理后的新闻摘要
        report_lines.extend([
            "## 📰 市场新闻动态",
            "",
        ])
        for metal_type, summary in ai_news_summaries:
            metal_name = "🥇 黄金" if metal_type == MetalType.GOLD else "🥈 白银"
            report_lines.append(f"### {metal_name}相关")
            report_lines.append(summary)
            report_lines.append("")
    elif (news_contexts and any(news_contexts.values())) or macro_news:
        # Fallback: 使用原始搜索结果（已经过清理函数处理）
        report_lines.extend([
            "## 📰 市场新闻动态",
            "",
        ])

        # Macro news first
        if macro_news:
            report_lines.append(macro_news)
            report_lines.append("")

        # Metal-specific news
        if news_contexts:
            for metal_type in [MetalType.GOLD, MetalType.SILVER]:
                if metal_type in news_contexts and news_contexts[metal_type]:
                    report_lines.append(news_contexts[metal_type])
                    report_lines.append("")

    # Analysis sections for each metal
    for metal_type in [MetalType.GOLD, MetalType.SILVER]:
        if metal_type not in results:
            continue

        result = results[metal_type]
        metal_emoji = "🥇" if metal_type == MetalType.GOLD else "🥈"

        report_lines.extend([
            f"## {metal_emoji} {result.name}分析",
            "",
            "### 核心结论",
            f"> {result.core_conclusion}" if result.core_conclusion else "> 暂无结论",
            "",
            f"**评分**: {result.sentiment_score}/100 | "
            f"**趋势**: {result.trend_emoji} {result.trend_prediction} | "
            f"**建议**: {result.advice_emoji} {result.operation_advice} | "
            f"**置信度**: {result.get_confidence_stars()}",
            "",
        ])

        # Macro analysis
        if result.macro_analysis and isinstance(result.macro_analysis, dict):
            report_lines.extend([
                "### 宏观分析",
                "",
            ])
            if result.macro_analysis.get('usd_impact'):
                report_lines.append(f"**美元影响**: {result.macro_analysis['usd_impact']}")
            if result.macro_analysis.get('yield_impact'):
                report_lines.append(f"**收益率影响**: {result.macro_analysis['yield_impact']}")
            if result.macro_analysis.get('inflation_outlook'):
                report_lines.append(f"**通胀预期**: {result.macro_analysis['inflation_outlook']}")
            report_lines.append("")

        # Technical levels
        if result.support_levels or result.resistance_levels:
            report_lines.extend([
                "### 技术点位",
                "",
            ])
            if result.support_levels:
                try:
                    support_str = " / ".join([f"${float(s):.2f}" for s in result.support_levels[:3]])
                except (ValueError, TypeError):
                    support_str = str(result.support_levels[:3])
                report_lines.append(f"**支撑位**: {support_str}")
            if result.resistance_levels:
                try:
                    resistance_str = " / ".join([f"${float(r):.2f}" for r in result.resistance_levels[:3]])
                except (ValueError, TypeError):
                    resistance_str = str(result.resistance_levels[:3])
                report_lines.append(f"**阻力位**: {resistance_str}")
            report_lines.append("")

        # Trend prediction
        if result.short_term_outlook or result.medium_term_outlook:
            report_lines.extend([
                "### 趋势预判",
                "",
            ])
            if result.short_term_outlook:
                report_lines.append(f"**短期 (1-3日)**: {result.short_term_outlook}")
            if result.medium_term_outlook:
                report_lines.append(f"**中期 (1-2周)**: {result.medium_term_outlook}")
            report_lines.append("")

        # Operation advice by timeframe
        if result.ultra_short_advice or result.short_term_advice or result.medium_term_advice:
            report_lines.extend([
                "### 🎯 分周期操作建议",
                "",
            ])
            if result.ultra_short_advice:
                report_lines.append(f"**⚡ 超短线（日内/隔日）**: {result.ultra_short_advice}")
            if result.short_term_advice:
                report_lines.append(f"**📅 短期（1-2天）**: {result.short_term_advice}")
            if result.medium_term_advice:
                report_lines.append(f"**📆 中期（1-2周）**: {result.medium_term_advice}")
            report_lines.append("")

        # Catalysts
        if result.positive_catalysts or result.negative_catalysts:
            report_lines.extend([
                "### 关注因素",
                "",
            ])
            if result.positive_catalysts:
                report_lines.append("**利好因素**:")
                for catalyst in result.positive_catalysts[:3]:
                    report_lines.append(f"- 🟢 {catalyst}")
            if result.negative_catalysts:
                report_lines.append("**利空因素**:")
                for catalyst in result.negative_catalysts[:3]:
                    report_lines.append(f"- 🔴 {catalyst}")
            report_lines.append("")

        # Risk warning
        if result.risk_warning:
            report_lines.extend([
                "### ⚠️ 风险提示",
                f"> {result.risk_warning}",
                "",
            ])

    # Footer
    report_lines.extend([
        "---",
        f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "*数据来源: YFinance, AkShare*",
    ])

    return "\n".join(report_lines)


def _generate_email_subject(overview: PreciousMetalsOverview) -> str:
    """Generate smart email subject based on market data"""
    date_str = datetime.now().strftime('%m/%d')

    if not overview.gold:
        return f"🥇 {date_str} 贵金属日报"

    gold_change = overview.gold.intl_change_pct or 0

    if gold_change >= 1.5:
        emoji = "🚀"
        mood = "大涨"
    elif gold_change >= 0.5:
        emoji = "📈"
        mood = "上涨"
    elif gold_change <= -1.5:
        emoji = "💥"
        mood = "大跌"
    elif gold_change <= -0.5:
        emoji = "📉"
        mood = "下跌"
    else:
        emoji = "⚖️"
        mood = "震荡"

    gold_price = f"${overview.gold.intl_price:.0f}" if overview.gold.intl_price else ""

    return f"{emoji} {date_str} 黄金{mood} {gold_price} ({gold_change:+.1f}%)"


def run_precious_metals_review(
    notifier: Optional[NotificationService] = None,
    analyzer: Optional[PreciousMetalsAIAnalyzer] = None,
    search_service: Optional[SearchService] = None,
    send_notification: bool = True,
) -> Optional[str]:
    """
    Execute precious metals daily review

    Args:
        notifier: Notification service (created if not provided)
        analyzer: AI analyzer (created if not provided)
        search_service: Search service (optional)
        send_notification: Whether to send notifications

    Returns:
        Report text if successful
    """
    logger.info("Starting precious metals review...")

    try:
        # Initialize services
        if notifier is None:
            notifier = NotificationService()

        # Create pipeline
        pipeline = PreciousMetalsPipeline(
            analyzer=analyzer,
            search_service=search_service,
        )

        # Run analysis
        result = pipeline.run(include_news=True)

        overview = result["overview"]
        analysis_results = result["results"]
        news_contexts = result.get("news_contexts", {})
        macro_news = result.get("macro_news")

        # Generate report
        report = generate_precious_metals_report(
            overview,
            analysis_results,
            news_contexts=news_contexts,
            macro_news=macro_news,
        )

        if report:
            # Save report to file
            date_str = datetime.now().strftime('%Y%m%d')
            report_filename = f"precious_metals_review_{date_str}.md"
            filepath = notifier.save_report_to_file(report, report_filename)
            logger.info(f"Precious metals report saved: {filepath}")

            # Send notification
            if send_notification and notifier.is_available():
                email_subject = _generate_email_subject(overview)
                logger.info(f"Email subject: {email_subject}")

                success = notifier.send(report, email_subject=email_subject)
                if success:
                    logger.info("Precious metals report sent successfully")
                else:
                    logger.warning("Precious metals report send failed")
            elif not send_notification:
                logger.info("Skipping notification (--no-notify)")

            return report

    except Exception as e:
        logger.error(f"Precious metals review failed: {e}")

    return None


if __name__ == "__main__":
    # Test the review
    logging.basicConfig(level=logging.INFO)

    report = run_precious_metals_review(send_notification=False)

    if report:
        print("\n" + "=" * 60)
        print(report)
        print("=" * 60)
