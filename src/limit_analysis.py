# -*- coding: utf-8 -*-
"""
===================================
涨跌停分析模块（简化方案）
===================================

设计目标：
1. 不依赖额外 API，通过代码前缀 + 名称判断限幅规则
2. 基于日线数据检测涨跌停、触板、炸板
3. 统计历史连板/连跌与炸板次数
4. 提供参考性的开板预估信号（量能/换手率）
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import date, datetime

import math


@dataclass
class LimitRule:
    """限幅规则"""
    code: str
    name: str
    board: str           # 板块：主板/创业板/科创板
    is_st: bool          # 是否ST股
    limit_up_pct: float  # 涨停幅度（如0.10表示10%）
    limit_down_pct: float  # 跌停幅度

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "board": self.board,
            "is_st": self.is_st,
            "limit_up_pct": self.limit_up_pct,
            "limit_down_pct": self.limit_down_pct,
        }


@dataclass
class DailyLimitRecord:
    """每日涨跌停记录"""
    date: str
    close: float
    high: float
    low: float
    prev_close: float
    pct_chg: Optional[float]
    volume: Optional[float]
    amount: Optional[float]
    volume_ratio: Optional[float]
    limit_up_price: float      # 涨停价
    limit_down_price: float    # 跌停价
    is_limit_up: bool          # 收盘涨停
    is_limit_down: bool        # 收盘跌停
    touched_limit_up: bool     # 盘中触及涨停
    touched_limit_down: bool   # 盘中触及跌停
    broken_limit_up: bool      # 炸板（触及涨停但未封住）
    broken_limit_down: bool    # 跌停开板
    status: str                # 状态描述

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "close": self.close,
            "high": self.high,
            "low": self.low,
            "prev_close": self.prev_close,
            "pct_chg": self.pct_chg,
            "volume": self.volume,
            "amount": self.amount,
            "volume_ratio": self.volume_ratio,
            "limit_up_price": self.limit_up_price,
            "limit_down_price": self.limit_down_price,
            "is_limit_up": self.is_limit_up,
            "is_limit_down": self.is_limit_down,
            "touched_limit_up": self.touched_limit_up,
            "touched_limit_down": self.touched_limit_down,
            "broken_limit_up": self.broken_limit_up,
            "broken_limit_down": self.broken_limit_down,
            "status": self.status,
        }


@dataclass
class LimitStreak:
    """连板/连跌停统计"""
    up_days: int               # 当前连板天数
    down_days: int             # 当前连跌停天数
    max_up_streak: int         # 近期最长连板
    max_down_streak: int       # 近期最长连跌停
    limit_up_days: int         # 近期涨停总天数
    limit_down_days: int       # 近期跌停总天数
    break_up_count: int        # 近期炸板次数
    break_down_count: int      # 近期跌停开板次数
    last_limit_up_date: Optional[str]   # 最近涨停日期
    last_limit_down_date: Optional[str]  # 最近跌停日期
    limit_up_dates: List[str] = field(default_factory=list)  # 所有涨停日期列表
    limit_down_dates: List[str] = field(default_factory=list)  # 所有跌停日期列表

    def to_dict(self) -> Dict[str, Any]:
        return {
            "up_days": self.up_days,
            "down_days": self.down_days,
            "max_up_streak": self.max_up_streak,
            "max_down_streak": self.max_down_streak,
            "limit_up_days": self.limit_up_days,
            "limit_down_days": self.limit_down_days,
            "break_up_count": self.break_up_count,
            "break_down_count": self.break_down_count,
            "last_limit_up_date": self.last_limit_up_date,
            "last_limit_down_date": self.last_limit_down_date,
            "limit_up_dates": self.limit_up_dates,
            "limit_down_dates": self.limit_down_dates,
        }


@dataclass
class OpenBoardSignal:
    """开板风险信号"""
    score: int                 # 开板风险评分（0-100）
    level: str                 # 风险等级：高/中/低
    direction: str             # 方向：limit_up/limit_down/none
    reasons: List[str] = field(default_factory=list)
    volume_ratio: Optional[float] = None
    turnover_rate: Optional[float] = None
    volume_turning_point: bool = False  # 是否出现量能转折

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level,
            "direction": self.direction,
            "reasons": self.reasons,
            "volume_ratio": self.volume_ratio,
            "turnover_rate": self.turnover_rate,
            "volume_turning_point": self.volume_turning_point,
        }


@dataclass
class LimitAnalysisResult:
    """涨跌停分析结果"""
    rule: LimitRule
    latest: Optional[DailyLimitRecord]
    streak: LimitStreak
    open_board_signal: OpenBoardSignal
    recent_records: List[DailyLimitRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule.to_dict(),
            "latest": self.latest.to_dict() if self.latest else None,
            "streak": self.streak.to_dict(),
            "open_board_signal": self.open_board_signal.to_dict(),
            "recent_records": [r.to_dict() for r in self.recent_records],
        }


def analyze_limits(
    code: str,
    name: str,
    daily_records: List[Dict[str, Any]],
    turnover_rate: Optional[float] = None,
    price_tolerance: float = 0.01,
    pct_tolerance: float = 0.2,
    recent_days: int = 5,
) -> LimitAnalysisResult:
    """
    涨跌停分析入口

    Args:
        code: 股票代码
        name: 股票名称
        daily_records: 日线记录列表（字典，包含 date/open/high/low/close/pct_chg/volume/amount/volume_ratio）
        turnover_rate: 当日换手率（来自实时行情，可能为空）
        price_tolerance: 价格容差（单位：元）
        pct_tolerance: 涨跌幅容差（单位：百分点）
        recent_days: 返回的最近记录天数
    """
    rule = _detect_limit_rule(code, name)
    sorted_records = _sort_daily_records(daily_records)

    limit_records: List[DailyLimitRecord] = []
    prev_close: Optional[float] = None
    for row in sorted_records:
        close = _safe_float(row.get("close"))
        if close is None:
            prev_close = None
            continue
        if prev_close is None:
            prev_close = close
            continue
        record = _build_daily_record(
            row=row,
            prev_close=prev_close,
            rule=rule,
            price_tolerance=price_tolerance,
            pct_tolerance=pct_tolerance,
        )
        limit_records.append(record)
        prev_close = close

    latest = limit_records[-1] if limit_records else None
    streak = _compute_streak(limit_records)
    open_board_signal = _estimate_open_board_signal(
        latest=latest,
        previous=limit_records[-2] if len(limit_records) >= 2 else None,
        turnover_rate=turnover_rate,
    )
    recent_records = limit_records[-recent_days:] if limit_records else []

    return LimitAnalysisResult(
        rule=rule,
        latest=latest,
        streak=streak,
        open_board_signal=open_board_signal,
        recent_records=recent_records,
    )


def _detect_limit_rule(code: str, name: str) -> LimitRule:
    """
    检测限幅规则

    规则：
    - 科创板 (688/689): ±20%
    - 创业板 (300/301): ±20%
    - ST股（名称含ST）: ±5%
    - 主板: ±10%
    """
    upper_name = (name or "").upper()
    is_st = "ST" in upper_name

    if code.startswith(("688", "689")):
        board = "科创板"
        limit_pct = 0.20
    elif code.startswith(("300", "301")):
        board = "创业板"
        limit_pct = 0.20
    else:
        board = "主板"
        limit_pct = 0.10

    if is_st:
        limit_pct = 0.05

    return LimitRule(
        code=code,
        name=name,
        board=board,
        is_st=is_st,
        limit_up_pct=limit_pct,
        limit_down_pct=limit_pct,
    )


def _build_daily_record(
    row: Dict[str, Any],
    prev_close: float,
    rule: LimitRule,
    price_tolerance: float,
    pct_tolerance: float,
) -> DailyLimitRecord:
    """构建每日涨跌停记录"""
    close = _safe_float(row.get("close"), 0.0)
    high = _safe_float(row.get("high"), close)
    low = _safe_float(row.get("low"), close)
    pct_chg = _safe_float(row.get("pct_chg"))
    volume = _safe_float(row.get("volume"))
    amount = _safe_float(row.get("amount"))
    volume_ratio = _safe_float(row.get("volume_ratio"))

    # 计算涨跌停价（四舍五入到分）
    limit_up_price = _round_price(prev_close * (1.0 + rule.limit_up_pct))
    limit_down_price = _round_price(prev_close * (1.0 - rule.limit_down_pct))

    # 判断是否涨停（收盘价 >= 涨停价 - 容差 或 涨跌幅 >= 限幅% - 容差）
    is_limit_up = (
        close >= (limit_up_price - price_tolerance)
        or (pct_chg is not None and pct_chg >= rule.limit_up_pct * 100 - pct_tolerance)
    )
    is_limit_down = (
        close <= (limit_down_price + price_tolerance)
        or (pct_chg is not None and pct_chg <= -rule.limit_down_pct * 100 + pct_tolerance)
    )

    # 判断是否盘中触及涨跌停
    touched_limit_up = high >= (limit_up_price - price_tolerance)
    touched_limit_down = low <= (limit_down_price + price_tolerance)

    # 判断炸板（盘中触及但收盘未封住）
    broken_limit_up = touched_limit_up and not is_limit_up
    broken_limit_down = touched_limit_down and not is_limit_down

    # 状态描述
    status = "非涨跌停"
    if is_limit_up:
        status = "涨停封板"
    elif is_limit_down:
        status = "跌停封板"
    elif broken_limit_up:
        status = "炸板"
    elif broken_limit_down:
        status = "跌停开板"
    elif touched_limit_up:
        status = "触及涨停"
    elif touched_limit_down:
        status = "触及跌停"

    return DailyLimitRecord(
        date=_format_date(row.get("date")),
        close=close,
        high=high,
        low=low,
        prev_close=prev_close,
        pct_chg=pct_chg,
        volume=volume,
        amount=amount,
        volume_ratio=volume_ratio,
        limit_up_price=limit_up_price,
        limit_down_price=limit_down_price,
        is_limit_up=is_limit_up,
        is_limit_down=is_limit_down,
        touched_limit_up=touched_limit_up,
        touched_limit_down=touched_limit_down,
        broken_limit_up=broken_limit_up,
        broken_limit_down=broken_limit_down,
        status=status,
    )


def _compute_streak(records: List[DailyLimitRecord]) -> LimitStreak:
    """计算连板/连跌停统计"""
    if not records:
        return LimitStreak(
            up_days=0,
            down_days=0,
            max_up_streak=0,
            max_down_streak=0,
            limit_up_days=0,
            limit_down_days=0,
            break_up_count=0,
            break_down_count=0,
            last_limit_up_date=None,
            last_limit_down_date=None,
            limit_up_dates=[],
            limit_down_dates=[],
        )

    # 统计总数和收集日期
    limit_up_dates = [r.date for r in records if r.is_limit_up]
    limit_down_dates = [r.date for r in records if r.is_limit_down]
    limit_up_days = len(limit_up_dates)
    limit_down_days = len(limit_down_dates)
    break_up_count = sum(1 for r in records if r.broken_limit_up)
    break_down_count = sum(1 for r in records if r.broken_limit_down)

    # 最近涨跌停日期
    last_limit_up_date = limit_up_dates[-1] if limit_up_dates else None
    last_limit_down_date = limit_down_dates[-1] if limit_down_dates else None

    # 当前连板天数（从最近一天往前数）
    up_days = 0
    for r in reversed(records):
        if r.is_limit_up:
            up_days += 1
        else:
            break

    # 当前连跌停天数
    down_days = 0
    for r in reversed(records):
        if r.is_limit_down:
            down_days += 1
        else:
            break

    # 最长连板/连跌停
    max_up_streak = 0
    max_down_streak = 0
    current_up = 0
    current_down = 0
    for r in records:
        if r.is_limit_up:
            current_up += 1
            max_up_streak = max(max_up_streak, current_up)
        else:
            current_up = 0
        if r.is_limit_down:
            current_down += 1
            max_down_streak = max(max_down_streak, current_down)
        else:
            current_down = 0

    return LimitStreak(
        up_days=up_days,
        down_days=down_days,
        max_up_streak=max_up_streak,
        max_down_streak=max_down_streak,
        limit_up_days=limit_up_days,
        limit_down_days=limit_down_days,
        break_up_count=break_up_count,
        break_down_count=break_down_count,
        last_limit_up_date=last_limit_up_date,
        last_limit_down_date=last_limit_down_date,
        limit_up_dates=limit_up_dates,
        limit_down_dates=limit_down_dates,
    )


def _estimate_open_board_signal(
    latest: Optional[DailyLimitRecord],
    previous: Optional[DailyLimitRecord],
    turnover_rate: Optional[float],
) -> OpenBoardSignal:
    """
    预估开板风险

    评分逻辑：
    - 基础分50分
    - 炸板：+30分
    - 封板放量（量比>=2）：+15分
    - 换手率高（>=15%）：+15分
    - 量能转折点（缩量→放量）：+10分
    - 封板缩量（量比<=0.8）：-10分
    """
    if not latest:
        return OpenBoardSignal(score=0, level="低", direction="none", reasons=["数据不足"])

    score = 50
    reasons: List[str] = []
    direction = "none"

    # 确定方向
    if latest.is_limit_up or latest.touched_limit_up:
        direction = "limit_up"
    elif latest.is_limit_down or latest.touched_limit_down:
        direction = "limit_down"

    # 量能转折点检测
    volume_turning_point = False
    if previous and latest.volume_ratio is not None and previous.volume_ratio is not None:
        if previous.volume_ratio <= 0.8 and latest.volume_ratio >= 1.5:
            volume_turning_point = True
            score += 10
            reasons.append("量比出现缩量→放量转折")

    # 炸板判断
    if latest.broken_limit_up:
        score = max(score, 80)
        reasons.append("盘中触板但未封住（炸板）")
    elif latest.touched_limit_up and not latest.is_limit_up:
        score = max(score, 70)
        reasons.append("触及涨停后回落，开板已发生")

    # 涨停封板时的风险评估
    if latest.is_limit_up:
        if latest.volume_ratio is not None:
            if latest.volume_ratio >= 2.0:
                score += 15
                reasons.append("封板放量，封单稳定性下降")
            elif latest.volume_ratio <= 0.8:
                score -= 10
                reasons.append("封板缩量，封单相对稳定")
        if turnover_rate is not None and turnover_rate >= 15:
            score += 15
            reasons.append("换手率偏高，开板概率上升")

    # 跌停封板时的风险评估
    if latest.is_limit_down:
        if latest.volume_ratio is not None and latest.volume_ratio >= 2.0:
            score += 10
            reasons.append("跌停放量，存在开板风险")
        if turnover_rate is not None and turnover_rate >= 10:
            score += 10
            reasons.append("跌停换手偏高，封单稳定性弱")

    # 限制评分范围
    score = max(0, min(100, score))

    # 确定风险等级
    if score >= 75:
        level = "高"
    elif score >= 60:
        level = "中"
    else:
        level = "低"

    return OpenBoardSignal(
        score=score,
        level=level,
        direction=direction,
        reasons=reasons,
        volume_ratio=latest.volume_ratio,
        turnover_rate=turnover_rate,
        volume_turning_point=volume_turning_point,
    )


def _sort_daily_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按日期升序排序"""
    def _date_key(item: Dict[str, Any]) -> str:
        return _format_date(item.get("date"))

    return sorted(records, key=_date_key)


def _format_date(value: Any) -> str:
    """格式化日期为字符串"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        return str(value)
    except Exception:
        return ""


def _round_price(value: float) -> float:
    """四舍五入到分（两位小数）"""
    if value is None:
        return 0.0
    return round(value + 1e-8, 2)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """安全转换为浮点数"""
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return default
        f_val = float(value)
        if math.isnan(f_val):
            return default
        return f_val
    except (TypeError, ValueError):
        return default
