# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 大盘复盘模块
===================================

职责：
1. 执行大盘复盘分析
2. 生成复盘报告
3. 保存和发送复盘报告
"""

import logging
from datetime import datetime
from typing import Optional

from src.notification import NotificationService
from src.market_analyzer import MarketAnalyzer, MarketOverview
from src.search_service import SearchService
from src.analyzer import GeminiAnalyzer


logger = logging.getLogger(__name__)


def _generate_market_email_subject(overview: MarketOverview) -> str:
    """
    根据市场概览生成智能邮件标题

    Args:
        overview: 市场概览数据

    Returns:
        智能生成的邮件标题
    """
    date_str = datetime.now().strftime('%m/%d')

    if not overview or not overview.indices:
        return f"🎯 {date_str} 大盘复盘"

    # 获取上证指数（通常是第一个）
    sh_index = None
    for idx in overview.indices:
        if '上证' in idx.name or idx.code == 'sh000001':
            sh_index = idx
            break
    if not sh_index and overview.indices:
        sh_index = overview.indices[0]

    # 判断市场情绪
    change_pct = sh_index.change_pct if sh_index else 0
    up_count = overview.up_count
    down_count = overview.down_count
    total = up_count + down_count
    up_ratio = up_count / total if total > 0 else 0.5

    # 涨停/跌停数据
    limit_up = overview.limit_up_count
    limit_down = overview.limit_down_count

    # 成交额（亿）
    amount = overview.total_amount

    # 生成标题
    if change_pct >= 2:
        emoji = "🚀"
        mood = "大涨"
    elif change_pct >= 1:
        emoji = "📈"
        mood = "上涨"
    elif change_pct >= 0.3:
        emoji = "🟢"
        mood = "飘红"
    elif change_pct <= -2:
        emoji = "💥"
        mood = "大跌"
    elif change_pct <= -1:
        emoji = "📉"
        mood = "下跌"
    elif change_pct <= -0.3:
        emoji = "🔴"
        mood = "飘绿"
    else:
        emoji = "⚖️"
        mood = "震荡"

    # 构建标题
    index_info = f"{sh_index.name}{change_pct:+.2f}%" if sh_index else ""
    market_info = f"涨{up_count}/跌{down_count}"

    # 亮点信息
    highlight = ""
    if limit_up >= 50:
        highlight = f"｜🔥涨停{limit_up}家"
    elif limit_down >= 30:
        highlight = f"｜⚠️跌停{limit_down}家"
    elif amount >= 15000:
        highlight = f"｜💰成交{amount/10000:.1f}万亿"
    elif amount >= 10000:
        highlight = f"｜成交破万亿"

    return f"{emoji} {date_str}｜{mood}｜{index_info}｜{market_info}{highlight}"


def run_market_review(
    notifier: NotificationService,
    analyzer: Optional[GeminiAnalyzer] = None,
    search_service: Optional[SearchService] = None,
    send_notification: bool = True
) -> Optional[str]:
    """
    执行大盘复盘分析

    Args:
        notifier: 通知服务
        analyzer: AI分析器（可选）
        search_service: 搜索服务（可选）
        send_notification: 是否发送通知

    Returns:
        复盘报告文本
    """
    logger.info("开始执行大盘复盘分析...")

    try:
        market_analyzer = MarketAnalyzer(
            search_service=search_service,
            analyzer=analyzer
        )

        # 1. 获取市场概览（用于生成智能标题）
        overview = market_analyzer.get_market_overview()

        # 2. 搜索市场新闻
        news = market_analyzer.search_market_news()

        # 3. 生成复盘报告
        review_report = market_analyzer.generate_market_review(overview, news)

        if review_report:
            # 保存报告到文件
            date_str = datetime.now().strftime('%Y%m%d')
            report_filename = f"market_review_{date_str}.md"
            filepath = notifier.save_report_to_file(
                f"# 🎯 大盘复盘\n\n{review_report}",
                report_filename
            )
            logger.info(f"大盘复盘报告已保存: {filepath}")

            # 推送通知
            if send_notification and notifier.is_available():
                report_content = f"🎯 大盘复盘\n\n{review_report}"

                # 生成智能邮件标题
                email_subject = _generate_market_email_subject(overview)
                logger.info(f"大盘复盘邮件标题: {email_subject}")

                success = notifier.send(report_content, email_subject=email_subject)
                if success:
                    logger.info("大盘复盘推送成功")
                else:
                    logger.warning("大盘复盘推送失败")
            elif not send_notification:
                logger.info("已跳过推送通知 (--no-notify)")
            
            return review_report
        
    except Exception as e:
        logger.error(f"大盘复盘分析失败: {e}")
    
    return None
