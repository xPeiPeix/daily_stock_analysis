# -*- coding: utf-8 -*-
"""
===================================
Precious Metals Analysis - Data Fetcher
===================================

Fetches precious metals data from multiple sources:
- International metals: YFinance (GC=F gold, SI=F silver) - COMEX futures, US Eastern Time
- Domestic metals: AkShare (Shanghai futures AU0/AG0) - China Standard Time
- Correlations: YFinance (DX-Y.NYB USD index, ^TNX 10Y treasury)

Trading Session Detection (SHFE):
- Day session: 09:00-10:15, 10:30-11:30, 13:30-15:00 CST
- Night session: 21:00-02:30 CST (next day)
- During session: Uses minute K-line for realtime price
- After close: Uses daily close/settlement price

Price Change Calculation:
- Domestic: Uses settlement price (结算价) for accurate change%
  change = current_price - prev_settlement
  change_pct = (change / prev_settlement) * 100%
- International: Uses close price (YFinance does not provide settlement)

Time Zone Notes:
- COMEX (international): US Eastern Time (ET), closes ~17:00 ET
- Shanghai (domestic): China Standard Time (CST), closes ~15:00 CST
- When viewing in morning CST, international data is from previous US trading day

Includes caching with 30-minute TTL to reduce API calls.
"""

import logging
import math
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

from src.precious_metals.models import (
    MetalType,
    MetalQuote,
    CorrelationIndicator,
    PreciousMetalsOverview,
    COTPositions,
    OISignal,
)

logger = logging.getLogger(__name__)

# Cache TTL in seconds
CACHE_TTL = 1800  # 30 minutes

# YFinance symbols
YFINANCE_SYMBOLS = {
    MetalType.GOLD: "GC=F",  # COMEX Gold Futures
    MetalType.SILVER: "SI=F",  # COMEX Silver Futures
    "USD_INDEX": "DX-Y.NYB",  # US Dollar Index
    "TREASURY_10Y": "^TNX",  # 10-Year Treasury Yield
}

# AkShare symbols for Shanghai futures
AKSHARE_SYMBOLS = {
    MetalType.GOLD: "AU0",  # Shanghai Gold main contract
    MetalType.SILVER: "AG0",  # Shanghai Silver main contract
}


class PreciousMetalsFetcher:
    """
    Fetcher for precious metals data

    Data sources:
    - YFinance: International prices (COMEX), USD index, Treasury yields
    - AkShare: Domestic prices (Shanghai futures)

    Features:
    - Automatic fallback between sources
    - Caching with TTL
    - Error isolation per data point
    - Trading session detection for realtime vs closing prices
    """

    def __init__(self):
        """Initialize the fetcher"""
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._yfinance_available = self._check_yfinance()
        self._akshare_available = self._check_akshare()

    @staticmethod
    def is_shfe_trading_session() -> bool:
        """
        Check if Shanghai Futures Exchange is in trading session

        SHFE Trading Hours (China Standard Time):
        - Day session: 09:00-10:15, 10:30-11:30, 13:30-15:00
        - Night session: 21:00-02:30 (next day)

        Returns:
            True if currently in trading session
        """
        now = datetime.now()
        hour, minute = now.hour, now.minute
        current_time = hour * 60 + minute  # Convert to minutes

        # Day session
        day_sessions = [
            (9 * 60, 10 * 60 + 15),      # 09:00 - 10:15
            (10 * 60 + 30, 11 * 60 + 30), # 10:30 - 11:30
            (13 * 60 + 30, 15 * 60),      # 13:30 - 15:00
        ]

        # Night session (21:00 - 02:30 next day)
        night_sessions = [
            (21 * 60, 24 * 60),  # 21:00 - 24:00
            (0, 2 * 60 + 30),    # 00:00 - 02:30
        ]

        for start, end in day_sessions + night_sessions:
            if start <= current_time < end:
                return True

        return False

    def _check_yfinance(self) -> bool:
        """Check if yfinance is available"""
        try:
            import yfinance
            return True
        except ImportError:
            logger.warning("yfinance not installed, international data will be unavailable")
            return False

    def _check_akshare(self) -> bool:
        """Check if akshare is available"""
        try:
            import akshare
            return True
        except ImportError:
            logger.warning("akshare not installed, domestic data will be unavailable")
            return False

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=CACHE_TTL):
                logger.debug(f"Cache hit for {key}")
                return value
            else:
                del self._cache[key]
        return None

    def _set_cached(self, key: str, value: Any) -> None:
        """Set cached value with current timestamp"""
        self._cache[key] = (value, datetime.now())

    def get_metal_quote_yfinance(self, metal_type: MetalType) -> Optional[MetalQuote]:
        """
        Fetch metal quote from YFinance

        Uses realtime price from ticker.info when available,
        falls back to daily close price if not.

        Args:
            metal_type: GOLD or SILVER

        Returns:
            MetalQuote with international prices
        """
        cache_key = f"yf_{metal_type.value}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        if not self._yfinance_available:
            return None

        try:
            import yfinance as yf

            symbol = YFINANCE_SYMBOLS[metal_type]
            ticker = yf.Ticker(symbol)

            # Get realtime quote from ticker.info
            info = ticker.info
            hist = ticker.history(period="60d")

            if hist.empty:
                logger.warning(f"No data returned for {symbol}")
                return None

            # Try to get realtime price
            current_price = info.get('regularMarketPrice')
            prev_close = info.get('regularMarketPreviousClose')
            is_realtime = current_price is not None

            # Fallback to daily close if realtime not available
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            if not is_realtime:
                current_price = float(latest['Close'])
                prev_close = float(prev['Close'])

            # Calculate change
            if prev_close is not None and prev_close != 0:
                change = current_price - prev_close
                change_pct = (change / prev_close) * 100
            else:
                change = float(latest['Close'] - prev['Close'])
                change_pct = float(change / prev['Close'] * 100) if prev['Close'] else None

            # Calculate MAs from historical data
            ma5 = hist['Close'].tail(5).mean() if len(hist) >= 5 else None
            ma10 = hist['Close'].tail(10).mean() if len(hist) >= 10 else None
            ma20 = hist['Close'].tail(20).mean() if len(hist) >= 20 else None
            ma60 = hist['Close'].tail(60).mean() if len(hist) >= 60 else None

            quote = MetalQuote(
                metal_type=metal_type,
                intl_price=float(current_price),
                intl_open=float(info.get('regularMarketOpen') or latest['Open']),
                intl_high=float(info.get('regularMarketDayHigh') or latest['High']),
                intl_low=float(info.get('regularMarketDayLow') or latest['Low']),
                intl_prev_close=float(prev_close) if prev_close is not None else float(prev['Close']),
                intl_change=float(change),
                intl_change_pct=float(change_pct) if change_pct is not None else None,
                intl_volume=float(info.get('regularMarketVolume') or latest['Volume'] or 0),
                ma5=float(ma5) if ma5 is not None else None,
                ma10=float(ma10) if ma10 is not None else None,
                ma20=float(ma20) if ma20 is not None else None,
                ma60=float(ma60) if ma60 is not None else None,
                timestamp=datetime.now(),
                data_source="YFinance" + (" (实时)" if is_realtime else " (收盘)"),
            )

            self._set_cached(cache_key, quote)
            price_type = "实时" if is_realtime else "收盘"
            pct_str = f"{quote.intl_change_pct:+.2f}%" if quote.intl_change_pct is not None else "N/A"
            logger.info(f"Fetched {metal_type.value} from YFinance ({price_type}): ${quote.intl_price:.2f} ({pct_str})")
            return quote

        except Exception as e:
            logger.error(f"Failed to fetch {metal_type.value} from YFinance: {e}")
            return None

    def get_metal_quote_akshare(self, metal_type: MetalType) -> Optional[Dict[str, float]]:
        """
        Fetch domestic metal prices from AkShare (Shanghai futures)

        Price selection logic:
        - If today has trading data (minute K-line), use today's latest price
        - Otherwise, use yesterday's close/settlement price

        Examples:
        - 12:30 (lunch break): Use 11:30 latest price from minute K-line
        - 10:20 (break): Use 10:15 latest price
        - 15:30 (after close): Use 15:00 close price
        - 08:00 (before open): Use yesterday's settlement

        Price change calculation:
        - Uses settlement price (结算价) when available for accurate change%
        - Falls back to close price if settlement unavailable

        Args:
            metal_type: GOLD or SILVER

        Returns:
            Dict with domestic price data including:
            - price: current/latest price
            - settlement: settlement price (if available)
            - prev_settlement: previous day settlement
            - change/change_pct: based on settlement prices
            - is_realtime: whether price is from today's trading
        """
        cache_key = f"ak_{metal_type.value}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        if not self._akshare_available:
            return None

        try:
            import akshare as ak

            symbol = AKSHARE_SYMBOLS[metal_type]
            today = datetime.now().date()

            # Get daily data for settlement prices
            df_daily = ak.futures_main_sina(symbol=symbol)
            if df_daily is None or df_daily.empty:
                logger.warning(f"No daily data returned for {symbol}")
                return None

            # Determine which row is "yesterday" based on date
            # If latest row is today → prev row is yesterday
            # If latest row is before today → latest row IS yesterday
            latest_daily = df_daily.iloc[-1]
            latest_date = latest_daily['日期']
            if isinstance(latest_date, str):
                latest_date = datetime.strptime(latest_date, '%Y-%m-%d').date()

            if latest_date == today:
                # Daily data includes today, use iloc[-2] as yesterday
                prev_daily = df_daily.iloc[-2] if len(df_daily) > 1 else latest_daily
                today_daily = latest_daily
            else:
                # Daily data latest is yesterday (or earlier), use it as "yesterday"
                prev_daily = latest_daily
                today_daily = None  # No today's daily data yet

            # Extract settlement prices (动态结算价)
            # prev_settlement = yesterday's settlement (for change calculation)
            prev_settlement = None
            settlement = None

            def safe_float(val) -> Optional[float]:
                """Convert to float, return None if NaN or invalid"""
                if val is None:
                    return None
                try:
                    f = float(val)
                    return None if math.isnan(f) else f
                except (ValueError, TypeError):
                    return None

            if '动态结算价' in df_daily.columns:
                prev_settlement = safe_float(prev_daily['动态结算价'])
                if today_daily is not None:
                    settlement = safe_float(today_daily['动态结算价'])

            # Try to get today's latest price from minute K-line
            current_price = None
            is_realtime = False
            price_time = None
            today_open = None
            today_high = None
            today_low = None

            try:
                df_minute = ak.futures_zh_minute_sina(symbol=symbol, period='5')
                if df_minute is not None and not df_minute.empty:
                    # Check if latest minute data is from today
                    latest_minute = df_minute.iloc[-1]
                    latest_dt = latest_minute['datetime']

                    # Parse datetime if it's a string
                    if isinstance(latest_dt, str):
                        latest_dt = datetime.strptime(latest_dt, '%Y-%m-%d %H:%M:%S')

                    if latest_dt.date() == today:
                        # Today's data exists, use it
                        current_price = float(latest_minute['close'])
                        is_realtime = True
                        price_time = latest_dt.strftime('%H:%M')

                        # Get today's OHLC from minute data
                        today_minutes = df_minute[df_minute['datetime'].apply(
                            lambda x: (datetime.strptime(x, '%Y-%m-%d %H:%M:%S') if isinstance(x, str) else x).date() == today
                        )]
                        if not today_minutes.empty:
                            today_open = float(today_minutes.iloc[0]['open'])
                            today_high = float(today_minutes['high'].max())
                            today_low = float(today_minutes['low'].min())

                        logger.info(f"Got today's price for {symbol}: ¥{current_price:.2f} @ {price_time}")
            except Exception as e:
                logger.warning(f"Failed to get minute data for {symbol}: {e}")

            # Fallback to daily data if no today's minute data
            if current_price is None:
                if today_daily is not None:
                    current_price = float(today_daily['收盘价'])
                    today_open = float(today_daily['开盘价'])
                    today_high = float(today_daily['最高价'])
                    today_low = float(today_daily['最低价'])
                else:
                    # No today's data at all, use yesterday's close
                    current_price = float(prev_daily['收盘价'])
                    today_open = None
                    today_high = None
                    today_low = None
                is_realtime = False
                logger.info(f"Using daily data for {symbol}: ¥{current_price:.2f}")

            # Calculate change using both methods
            # Method 1: Based on settlement price (交易所官方标准)
            prev_close = safe_float(prev_daily['收盘价'])
            base_settlement = prev_settlement if prev_settlement is not None else prev_close

            change_by_settlement = None
            change_pct_by_settlement = None
            if current_price is not None and base_settlement is not None:
                change_by_settlement = current_price - base_settlement
                change_pct_by_settlement = (change_by_settlement / base_settlement * 100)

            # Method 2: Based on close price (收盘价)
            change_by_close = None
            change_pct_by_close = None
            if current_price is not None and prev_close is not None:
                change_by_close = current_price - prev_close
                change_pct_by_close = (change_by_close / prev_close * 100)

            result = {
                "price": current_price,
                "open": today_open,
                "high": today_high,
                "low": today_low,
                "prev_close": prev_close,
                "settlement": settlement,
                "prev_settlement": prev_settlement,
                # Primary change (based on settlement - official standard)
                "change": change_by_settlement,
                "change_pct": change_pct_by_settlement,
                # Secondary change (based on close price)
                "change_by_close": change_by_close,
                "change_pct_by_close": change_pct_by_close,
                "is_realtime": is_realtime,
                "price_time": price_time,  # Time of the price (HH:MM)
            }

            self._set_cached(cache_key, result)
            price_desc = f"今日{price_time}" if is_realtime else "昨收"
            logger.info(
                f"Fetched {metal_type.value} from AkShare ({price_desc}): "
                f"¥{result['price']:.2f} (结算价基准:{change_pct_by_settlement:+.2f}%, 收盘价基准:{change_pct_by_close:+.2f}%)"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to fetch {metal_type.value} from AkShare: {e}")
            return None

    def get_usd_index(self) -> Optional[CorrelationIndicator]:
        """
        Fetch USD Index (DXY) from YFinance

        USD Index has inverse correlation with gold:
        - USD up -> Gold down (bearish for metals)
        - USD down -> Gold up (bullish for metals)
        """
        cache_key = "usd_index"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        if not self._yfinance_available:
            return None

        try:
            import yfinance as yf

            ticker = yf.Ticker(YFINANCE_SYMBOLS["USD_INDEX"])
            hist = ticker.history(period="5d")

            if hist.empty:
                logger.warning("No data returned for USD Index")
                return None

            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            change = float(latest['Close'] - prev['Close'])
            change_pct = float(change / prev['Close'] * 100) if prev['Close'] else 0

            # Determine impact on metals (inverse correlation)
            if change_pct < -0.3:
                impact = "bullish"
                description = "美元走弱，利好贵金属"
            elif change_pct > 0.3:
                impact = "bearish"
                description = "美元走强，利空贵金属"
            else:
                impact = "neutral"
                description = "美元持平，影响有限"

            indicator = CorrelationIndicator(
                name="美元指数",
                value=float(latest['Close']),
                prev_value=float(prev['Close']),
                change=change,
                change_pct=change_pct,
                impact=impact,
                description=description,
                timestamp=datetime.now(),
            )

            self._set_cached(cache_key, indicator)
            logger.info(f"Fetched USD Index: {indicator.value:.2f} ({change_pct:+.2f}%)")
            return indicator

        except Exception as e:
            logger.error(f"Failed to fetch USD Index: {e}")
            return None

    def get_treasury_10y(self) -> Optional[CorrelationIndicator]:
        """
        Fetch 10-Year Treasury Yield from YFinance

        Treasury yields have inverse correlation with gold:
        - Yields up -> Gold down (higher opportunity cost)
        - Yields down -> Gold up (lower opportunity cost)
        """
        cache_key = "treasury_10y"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        if not self._yfinance_available:
            return None

        try:
            import yfinance as yf

            ticker = yf.Ticker(YFINANCE_SYMBOLS["TREASURY_10Y"])
            hist = ticker.history(period="5d")

            if hist.empty:
                logger.warning("No data returned for 10Y Treasury")
                return None

            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            change = float(latest['Close'] - prev['Close'])
            change_pct = float(change / prev['Close'] * 100) if prev['Close'] else 0

            # Determine impact on metals (inverse correlation)
            if change < -0.05:
                impact = "bullish"
                description = "收益率下降，利好贵金属"
            elif change > 0.05:
                impact = "bearish"
                description = "收益率上升，利空贵金属"
            else:
                impact = "neutral"
                description = "收益率持平，影响有限"

            indicator = CorrelationIndicator(
                name="10年期美债收益率",
                value=float(latest['Close']),
                prev_value=float(prev['Close']),
                change=change,
                change_pct=change_pct,
                impact=impact,
                description=description,
                timestamp=datetime.now(),
            )

            self._set_cached(cache_key, indicator)
            logger.info(f"Fetched 10Y Treasury: {indicator.value:.2f}% ({change:+.2f})")
            return indicator

        except Exception as e:
            logger.error(f"Failed to fetch 10Y Treasury: {e}")
            return None

    def get_cftc_cot_positions(self, metal_type: MetalType) -> Optional[COTPositions]:
        """
        Fetch CFTC COT (Commitment of Traders) speculator positions

        Data source: CFTC Public Reporting API
        URL: https://publicreporting.cftc.gov/resource/6dca-aqww.json

        COT reports are released every Friday, reflecting positions as of Tuesday.
        There's a 3-day data delay.

        Args:
            metal_type: GOLD or SILVER

        Returns:
            COTPositions with speculator long/short positions
        """
        cache_key = f"cot_{metal_type.value}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            import httpx

            commodity_name = "GOLD" if metal_type == MetalType.GOLD else "SILVER"
            url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

            params = {
                "$where": f"commodity_name='{commodity_name}'",
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": 2,  # Get current and previous week
            }

            with httpx.Client(timeout=30) as client:
                response = client.get(url, params=params)

            if response.status_code != 200:
                logger.warning(f"CFTC API returned {response.status_code}")
                return None

            data = response.json()
            if not data:
                logger.warning(f"No COT data for {commodity_name}")
                return None

            # Find the main contract (highest open interest)
            latest_date = data[0].get("report_date_as_yyyy_mm_dd", "")
            latest_records = [r for r in data if r.get("report_date_as_yyyy_mm_dd") == latest_date]

            if not latest_records:
                logger.warning(f"No records for latest date")
                return None

            # Pick record with highest open interest
            record = max(latest_records, key=lambda r: int(r.get("open_interest_all", 0) or 0))

            # Extract speculator (non-commercial) positions
            long_positions = int(record.get("noncomm_positions_long_all", 0) or 0)
            short_positions = int(record.get("noncomm_positions_short_all", 0) or 0)
            net_positions = long_positions - short_positions

            total_positions = long_positions + short_positions
            net_long_pct = (long_positions / total_positions * 100) if total_positions > 0 else 50

            # Try to get previous week's data
            prev_net = None
            weekly_change = None
            if len(data) >= 2:
                prev_date = data[1].get("report_date_as_yyyy_mm_dd", "")
                prev_records = [r for r in data if r.get("report_date_as_yyyy_mm_dd") == prev_date]
                if prev_records:
                    prev_record = max(prev_records, key=lambda r: int(r.get("open_interest_all", 0) or 0))
                    prev_long = int(prev_record.get("noncomm_positions_long_all", 0) or 0)
                    prev_short = int(prev_record.get("noncomm_positions_short_all", 0) or 0)
                    prev_net = prev_long - prev_short
                    weekly_change = net_positions - prev_net

            cot = COTPositions(
                metal_type=metal_type,
                report_date=latest_date,
                long_positions=long_positions,
                short_positions=short_positions,
                net_positions=net_positions,
                net_long_pct=net_long_pct,
                prev_net_positions=prev_net,
                weekly_change=weekly_change,
            )

            # Cache for 24 hours (COT updates weekly)
            self._cache[cache_key] = (cot, datetime.now())
            logger.info(
                f"Fetched COT for {metal_type.value}: "
                f"Net={net_positions:+,} ({net_long_pct:.1f}% long) [{cot.bias_cn}]"
            )
            return cot

        except ImportError:
            logger.warning("httpx not installed, COT data unavailable")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch COT for {metal_type.value}: {e}")
            return None

    def get_open_interest(self, metal_type: MetalType) -> Optional[Dict[str, Any]]:
        """
        Fetch Open Interest data

        Priority:
        1. AkShare (Shanghai futures) - for domestic OI
        2. YFinance - for COMEX OI (fallback)

        Args:
            metal_type: GOLD or SILVER

        Returns:
            Dict with OI data: {current, prev, change, change_pct}
        """
        cache_key = f"oi_{metal_type.value}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Try AkShare first (Shanghai futures)
        if self._akshare_available:
            try:
                import akshare as ak

                symbol = AKSHARE_SYMBOLS[metal_type]
                df = ak.futures_main_sina(symbol=symbol)

                if df is not None and not df.empty and '持仓量' in df.columns:
                    latest = df.iloc[-1]
                    prev = df.iloc[-2] if len(df) > 1 else latest

                    oi_current = int(latest['持仓量']) if latest['持仓量'] else 0
                    oi_prev = int(prev['持仓量']) if prev['持仓量'] else oi_current

                    if oi_current > 0:
                        oi_change = oi_current - oi_prev
                        oi_change_pct = (oi_change / oi_prev * 100) if oi_prev > 0 else 0

                        result = {
                            "current": oi_current,
                            "prev": oi_prev,
                            "change": oi_change,
                            "change_pct": oi_change_pct,
                            "source": "AkShare",
                        }

                        self._set_cached(cache_key, result)
                        logger.info(
                            f"Fetched OI for {metal_type.value} from AkShare: "
                            f"{oi_current:,} ({oi_change_pct:+.2f}%)"
                        )
                        return result

            except Exception as e:
                logger.warning(f"AkShare OI fetch failed for {metal_type.value}: {e}")

        # Fallback to YFinance
        if self._yfinance_available:
            try:
                import yfinance as yf

                symbol = YFINANCE_SYMBOLS[metal_type]
                ticker = yf.Ticker(symbol)
                info = ticker.info

                oi_current = info.get('openInterest')
                if oi_current and oi_current > 0:
                    # YFinance doesn't provide historical OI easily
                    # Use a simple estimate based on volume changes
                    hist = ticker.history(period="5d")
                    if not hist.empty and len(hist) > 1:
                        # Estimate prev OI based on volume ratio
                        vol_ratio = hist['Volume'].iloc[-2] / hist['Volume'].iloc[-1] if hist['Volume'].iloc[-1] > 0 else 1
                        oi_prev = int(oi_current * vol_ratio)
                        oi_change = oi_current - oi_prev
                        oi_change_pct = (oi_change / oi_prev * 100) if oi_prev > 0 else 0
                    else:
                        oi_prev = oi_current
                        oi_change = 0
                        oi_change_pct = 0

                    result = {
                        "current": oi_current,
                        "prev": oi_prev,
                        "change": oi_change,
                        "change_pct": oi_change_pct,
                        "source": "YFinance (估算)",
                    }

                    self._set_cached(cache_key, result)
                    logger.info(
                        f"Fetched OI for {metal_type.value} from YFinance: "
                        f"{oi_current:,} ({oi_change_pct:+.2f}%)"
                    )
                    return result

            except Exception as e:
                logger.warning(f"YFinance OI fetch failed for {metal_type.value}: {e}")

        logger.warning(f"Could not fetch OI for {metal_type.value}")
        return None

    def calculate_oi_signal(
        self,
        metal_type: MetalType,
        quote: MetalQuote
    ) -> Optional[OISignal]:
        """
        Calculate Price + OI combined signal

        Uses domestic (Shanghai futures) data for both price and OI
        to ensure data source consistency.

        Signal logic:
        - Price↑ + OI↑ → new_longs (多开): Bullish continuation
        - Price↑ + OI↓ → short_covering (空平): Rally may slow
        - Price↓ + OI↑ → new_shorts (空开): Bearish continuation
        - Price↓ + OI↓ → long_liquidation (多平): Decline may slow

        Args:
            metal_type: GOLD or SILVER
            quote: MetalQuote with price data

        Returns:
            OISignal with combined analysis
        """
        oi_data = self.get_open_interest(metal_type)
        if not oi_data:
            return None

        # Use domestic price change (Shanghai futures) for consistency with OI data
        # Priority: settlement-based change > close-based change > international change
        if quote.domestic_change_pct is not None:
            price_change = quote.domestic_change if quote.domestic_change is not None else 0
            price_change_pct = quote.domestic_change_pct
            price_source = "沪期货(结算价)"
        elif quote.domestic_change_pct_by_close is not None:
            price_change = quote.domestic_change_by_close if quote.domestic_change_by_close is not None else 0
            price_change_pct = quote.domestic_change_pct_by_close
            price_source = "沪期货(收盘价)"
        else:
            # Fallback to international price if domestic not available
            price_change = quote.intl_change if quote.intl_change is not None else 0
            price_change_pct = quote.intl_change_pct if quote.intl_change_pct is not None else 0
            price_source = "COMEX(回退)"

        signal = OISignal(
            metal_type=metal_type,
            price_change=price_change,
            price_change_pct=price_change_pct,
            oi_current=oi_data["current"],
            oi_prev=oi_data["prev"],
            oi_change=oi_data["change"],
            oi_change_pct=oi_data["change_pct"],
        )

        logger.info(
            f"OI Signal for {metal_type.value}: "
            f"Price[{price_source}] {price_change_pct:+.2f}% + OI {oi_data['change_pct']:+.2f}% → {signal.signal_cn}"
        )

        return signal

    def get_precious_metals_overview(self) -> PreciousMetalsOverview:
        """
        Get complete precious metals market overview

        Fetches all data points with error isolation:
        - Gold quote (international + domestic)
        - Silver quote (international + domestic)
        - USD Index
        - 10Y Treasury Yield
        - Gold/Silver ratio

        Returns:
            PreciousMetalsOverview with all available data
        """
        logger.info("Fetching precious metals overview...")

        # Fetch gold
        gold = self.get_metal_quote_yfinance(MetalType.GOLD)
        if gold:
            domestic_gold = self.get_metal_quote_akshare(MetalType.GOLD)
            if domestic_gold:
                gold.domestic_price = domestic_gold.get("price")
                gold.domestic_open = domestic_gold.get("open")
                gold.domestic_high = domestic_gold.get("high")
                gold.domestic_low = domestic_gold.get("low")
                gold.domestic_prev_close = domestic_gold.get("prev_close")
                gold.domestic_change = domestic_gold.get("change")
                gold.domestic_change_pct = domestic_gold.get("change_pct")
                gold.domestic_change_by_close = domestic_gold.get("change_by_close")
                gold.domestic_change_pct_by_close = domestic_gold.get("change_pct_by_close")
                gold.domestic_settlement = domestic_gold.get("settlement")
                gold.domestic_prev_settlement = domestic_gold.get("prev_settlement")
                gold.domestic_is_realtime = domestic_gold.get("is_realtime", False)
                gold.domestic_price_time = domestic_gold.get("price_time")

        # Fetch silver
        silver = self.get_metal_quote_yfinance(MetalType.SILVER)
        if silver:
            domestic_silver = self.get_metal_quote_akshare(MetalType.SILVER)
            if domestic_silver:
                silver.domestic_price = domestic_silver.get("price")
                silver.domestic_open = domestic_silver.get("open")
                silver.domestic_high = domestic_silver.get("high")
                silver.domestic_low = domestic_silver.get("low")
                silver.domestic_prev_close = domestic_silver.get("prev_close")
                silver.domestic_change = domestic_silver.get("change")
                silver.domestic_change_pct = domestic_silver.get("change_pct")
                silver.domestic_change_by_close = domestic_silver.get("change_by_close")
                silver.domestic_change_pct_by_close = domestic_silver.get("change_pct_by_close")
                silver.domestic_settlement = domestic_silver.get("settlement")
                silver.domestic_prev_settlement = domestic_silver.get("prev_settlement")
                silver.domestic_is_realtime = domestic_silver.get("is_realtime", False)
                silver.domestic_price_time = domestic_silver.get("price_time")

        # Fetch correlation indicators
        usd_index = self.get_usd_index()
        treasury_10y = self.get_treasury_10y()

        # Calculate gold/silver ratio
        gold_silver_ratio = None
        gold_silver_ratio_change = None
        if gold and silver and gold.intl_price and silver.intl_price:
            gold_silver_ratio = gold.intl_price / silver.intl_price
            if gold.intl_prev_close and silver.intl_prev_close:
                prev_ratio = gold.intl_prev_close / silver.intl_prev_close
                gold_silver_ratio_change = gold_silver_ratio - prev_ratio

        # Determine data completeness
        data_complete = all([gold, silver, usd_index, treasury_10y])

        overview = PreciousMetalsOverview(
            gold=gold,
            silver=silver,
            usd_index=usd_index,
            treasury_10y=treasury_10y,
            gold_silver_ratio=gold_silver_ratio,
            gold_silver_ratio_change=gold_silver_ratio_change,
            timestamp=datetime.now(),
            data_complete=data_complete,
        )

        # Fetch COT positions (macro sentiment)
        overview.gold_cot = self.get_cftc_cot_positions(MetalType.GOLD)
        overview.silver_cot = self.get_cftc_cot_positions(MetalType.SILVER)

        # Calculate OI signals (micro sentiment)
        if gold:
            overview.gold_oi_signal = self.calculate_oi_signal(MetalType.GOLD, gold)
        if silver:
            overview.silver_oi_signal = self.calculate_oi_signal(MetalType.SILVER, silver)

        logger.info(f"Precious metals overview complete. Data complete: {data_complete}")
        return overview

    def clear_cache(self) -> None:
        """Clear all cached data"""
        self._cache.clear()
        logger.info("Cache cleared")


# Convenience function
def get_precious_metals_fetcher() -> PreciousMetalsFetcher:
    """Get a PreciousMetalsFetcher instance"""
    return PreciousMetalsFetcher()


if __name__ == "__main__":
    # Test the fetcher
    logging.basicConfig(level=logging.INFO)

    fetcher = PreciousMetalsFetcher()
    overview = fetcher.get_precious_metals_overview()

    print("\n=== Precious Metals Overview ===")
    if overview.gold:
        print(f"Gold: ${overview.gold.intl_price:.2f} ({overview.gold.intl_change_pct:+.2f}%)")
    if overview.silver:
        print(f"Silver: ${overview.silver.intl_price:.2f} ({overview.silver.intl_change_pct:+.2f}%)")
    if overview.gold_silver_ratio:
        print(f"Gold/Silver Ratio: {overview.gold_silver_ratio:.2f}")
    if overview.usd_index:
        print(f"USD Index: {overview.usd_index.value:.2f} ({overview.usd_index.change_pct:+.2f}%)")
    if overview.treasury_10y:
        print(f"10Y Treasury: {overview.treasury_10y.value:.2f}%")
