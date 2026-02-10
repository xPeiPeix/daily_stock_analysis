# -*- coding: utf-8 -*-
"""
===================================
Precious Metals Analysis - AI Analyzer
===================================

AI analyzer for precious metals (Gold/Silver) with:
- Custom system prompt for commodity trading philosophy
- Emphasis on macro factors (USD, inflation, yields, geopolitics)
- Support/resistance levels instead of MA alignment
- Trend prediction (short-term and medium-term)

Reuses GeminiAnalyzer from src/analyzer.py for API calls.
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from json_repair import repair_json
except ImportError:
    repair_json = None

from src.config import get_config
from src.precious_metals.models import (
    MetalType,
    MetalQuote,
    CorrelationIndicator,
    PreciousMetalsOverview,
    PreciousMetalsAnalysisResult,
)

logger = logging.getLogger(__name__)


class PreciousMetalsAIAnalyzer:
    """
    AI Analyzer for Precious Metals

    Key differences from stock analysis:
    1. Macro focus: USD strength, real interest rates, inflation expectations
    2. Correlation analysis: How USD/yields/inflation affect gold/silver
    3. Safe-haven demand: Geopolitical risk assessment
    4. Technical levels: Support/resistance instead of MA alignment
    5. Trend prediction: Short-term (1-3 days) and medium-term (1-2 weeks)
    """

    SYSTEM_PROMPT = """你是一位专注于贵金属（黄金/白银）交易的资深分析师，负责生成专业的贵金属分析报告。

## 核心分析框架

### 1. 宏观因素分析（最重要）
贵金属价格主要受宏观因素驱动，而非个股基本面：

**美元指数（DXY）**：
- 与黄金呈负相关：美元走强 → 黄金承压
- 美元指数 > 105：对黄金形成压力
- 美元指数 < 100：利好黄金

**美债收益率**：
- 实际利率 = 名义利率 - 通胀预期
- 实际利率上升 → 持有黄金机会成本增加 → 利空
- 实际利率下降 → 黄金吸引力增加 → 利好

**通胀预期**：
- 高通胀预期 → 黄金作为抗通胀资产受追捧
- 通胀回落 → 黄金避险需求下降

**地缘政治**：
- 战争、危机 → 避险需求推升金价
- 局势缓和 → 避险溢价消退

### 2. 金银比分析
- 金银比 = 黄金价格 / 白银价格
- 历史均值约 60-70
- 金银比 > 80：白银相对低估，可能补涨
- 金银比 < 60：黄金相对低估，可能补涨

### 3. 技术分析要点
- 关注关键支撑/阻力位（整数关口、历史高低点）
- 趋势线和通道
- 成交量配合
- 不强调均线排列（与股票分析不同）

### 4. 操作建议原则
- **买入信号**：美元走弱 + 收益率下降 + 技术支撑有效
- **卖出信号**：美元走强 + 收益率上升 + 技术阻力明显
- **观望信号**：宏观信号矛盾 + 技术面震荡

## 输出格式：JSON

请严格按照以下 JSON 格式输出分析结果：

```json
{
    "metal_name": "黄金/白银",
    "sentiment_score": 0-100整数,
    "trend_prediction": "up/down/sideways",
    "operation_advice": "buy/hold/sell",
    "confidence_level": "high/medium/low",

    "core_conclusion": "一句话核心结论（30字以内，直接告诉用户做什么）",

    "macro_analysis": {
        "usd_impact": "美元指数对贵金属的影响分析",
        "yield_impact": "美债收益率对贵金属的影响分析",
        "inflation_outlook": "通胀预期分析",
        "geopolitical_risk": "地缘政治风险评估"
    },

    "correlation_summary": "关键相关性指标综合解读",

    "technical_analysis": {
        "trend": "up/down/sideways",
        "trend_strength": 0-100,
        "key_levels": "关键价位分析"
    },

    "support_levels": [支撑位1, 支撑位2],
    "resistance_levels": [阻力位1, 阻力位2],

    "trend_prediction_detail": {
        "short_term": "1-3日展望",
        "medium_term": "1-2周展望",
        "key_events": "需关注的重要事件"
    },

    "positive_catalysts": ["利好因素1", "利好因素2"],
    "negative_catalysts": ["利空因素1", "利空因素2"],

    "risk_warning": "风险提示",
    "news_summary": "近期重要新闻摘要",
    "analysis_summary": "100字综合分析摘要"
}
```

## 评分标准

### 强烈看多（80-100分）：
- ✅ 美元走弱趋势明确
- ✅ 实际利率下降
- ✅ 避险需求上升
- ✅ 技术面突破阻力

### 看多（60-79分）：
- ✅ 宏观环境偏利好
- ✅ 技术面支撑有效
- ⚪ 允许一项次要因素不利

### 震荡/观望（40-59分）：
- ⚠️ 宏观信号矛盾
- ⚠️ 技术面方向不明
- ⚠️ 等待关键数据/事件

### 看空（0-39分）：
- ❌ 美元走强
- ❌ 实际利率上升
- ❌ 避险需求消退
- ❌ 技术面跌破支撑"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the analyzer

        Reuses the same API infrastructure as GeminiAnalyzer
        """
        config = get_config()
        self._api_key = api_key or config.gemini_api_key
        self._model = None
        self._current_model_name = None
        self._using_fallback = False
        self._use_openai = False
        self._openai_client = None

        # Check Gemini API Key validity
        gemini_key_valid = self._api_key and not self._api_key.startswith('your_') and len(self._api_key) > 10

        if gemini_key_valid:
            try:
                self._init_model()
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}, trying OpenAI")
                self._init_openai_fallback()
        else:
            logger.info("Gemini API Key not configured, trying OpenAI")
            self._init_openai_fallback()

        if not self._model and not self._openai_client:
            logger.warning("No AI API Key configured, analysis will be unavailable")

    def _init_model(self) -> None:
        """Initialize Gemini model"""
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)

            config = get_config()
            model_name = config.gemini_model
            fallback_model = config.gemini_model_fallback

            try:
                self._model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=self.SYSTEM_PROMPT,
                )
                self._current_model_name = model_name
                self._using_fallback = False
                logger.info(f"Gemini model initialized: {model_name}")
            except Exception as e:
                logger.warning(f"Primary model {model_name} failed: {e}, trying {fallback_model}")
                self._model = genai.GenerativeModel(
                    model_name=fallback_model,
                    system_instruction=self.SYSTEM_PROMPT,
                )
                self._current_model_name = fallback_model
                self._using_fallback = True
                logger.info(f"Gemini fallback model initialized: {fallback_model}")

        except Exception as e:
            logger.error(f"Gemini model init failed: {e}")
            self._model = None

    def _init_openai_fallback(self) -> None:
        """Initialize OpenAI compatible API as fallback"""
        config = get_config()

        openai_key_valid = (
            config.openai_api_key and
            not config.openai_api_key.startswith('your_') and
            len(config.openai_api_key) > 10
        )

        if not openai_key_valid:
            logger.debug("OpenAI API not configured")
            return

        try:
            from openai import OpenAI

            client_kwargs = {"api_key": config.openai_api_key}
            if config.openai_base_url and config.openai_base_url.startswith('http'):
                client_kwargs["base_url"] = config.openai_base_url

            self._openai_client = OpenAI(**client_kwargs)
            self._current_model_name = config.openai_model
            self._use_openai = True
            logger.info(f"OpenAI API initialized: {config.openai_model}")

        except Exception as e:
            logger.error(f"OpenAI API init failed: {e}")

    def is_available(self) -> bool:
        """Check if analyzer is available"""
        return self._model is not None or self._openai_client is not None

    def _call_api_with_retry(self, prompt: str, generation_config: dict) -> str:
        """Call AI API with retry mechanism"""
        if self._use_openai:
            return self._call_openai_api(prompt, generation_config)

        config = get_config()
        max_retries = config.gemini_max_retries
        base_delay = config.gemini_retry_delay

        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    delay = min(delay, 60)
                    logger.info(f"[Gemini] Retry {attempt + 1}, waiting {delay:.1f}s...")
                    time.sleep(delay)

                response = self._model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    request_options={"timeout": 120}
                )

                if response and response.text:
                    return response.text
                else:
                    raise ValueError("Gemini returned empty response")

            except Exception as e:
                last_error = e
                logger.warning(f"[Gemini] API call failed, attempt {attempt + 1}/{max_retries}: {str(e)[:100]}")

        # Try OpenAI fallback
        if self._openai_client:
            logger.warning("[Gemini] All retries failed, switching to OpenAI")
            try:
                return self._call_openai_api(prompt, generation_config)
            except Exception as e:
                logger.error(f"[OpenAI] Fallback also failed: {e}")
                raise last_error or e

        raise last_error or Exception("All AI API calls failed")

    def _call_openai_api(self, prompt: str, generation_config: dict) -> str:
        """Call OpenAI compatible API"""
        import httpx

        config = get_config()
        max_retries = config.gemini_max_retries
        base_delay = config.gemini_retry_delay

        base_url = config.openai_base_url or "https://api.openai.com/v1"
        url = f"{base_url.rstrip('/')}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.openai_api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        payload = {
            "model": self._current_model_name,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": generation_config.get('temperature', config.openai_temperature),
            "max_tokens": generation_config.get('max_output_tokens', 8192),
        }

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    delay = min(delay, 60)
                    logger.info(f"[OpenAI] Retry {attempt + 1}, waiting {delay:.1f}s...")
                    time.sleep(delay)

                with httpx.Client(timeout=120) as client:
                    response = client.post(url, headers=headers, json=payload)

                if response.status_code != 200:
                    raise Exception(f"API error: {response.text[:200]}")

                data = response.json()
                if data and "choices" in data and data["choices"]:
                    content = data["choices"][0].get("message", {}).get("content")
                    if content:
                        return content

                raise ValueError("OpenAI API returned empty response")

            except Exception as e:
                logger.warning(f"[OpenAI] API call failed, attempt {attempt + 1}/{max_retries}: {str(e)[:100]}")
                if attempt == max_retries - 1:
                    raise

        raise Exception("OpenAI API call failed after max retries")

    def analyze_metal(
        self,
        metal_type: MetalType,
        quote: MetalQuote,
        overview: PreciousMetalsOverview,
        news_context: Optional[str] = None
    ) -> PreciousMetalsAnalysisResult:
        """
        Analyze a precious metal

        Args:
            metal_type: GOLD or SILVER
            quote: Metal quote data
            overview: Full market overview with correlations
            news_context: Pre-fetched news content

        Returns:
            PreciousMetalsAnalysisResult
        """
        config = get_config()

        # Request delay
        request_delay = config.gemini_request_delay
        if request_delay > 0:
            logger.debug(f"[LLM] Waiting {request_delay:.1f}s before request...")
            time.sleep(request_delay)

        metal_name = "黄金" if metal_type == MetalType.GOLD else "白银"

        if not self.is_available():
            return PreciousMetalsAnalysisResult(
                metal_type=metal_type,
                sentiment_score=50,
                trend_prediction="sideways",
                operation_advice="hold",
                confidence_level="low",
                core_conclusion="AI分析功能未启用（未配置API Key）",
                risk_warning="请配置Gemini API Key后重试",
                success=False,
                error_message="AI API Key not configured",
                timestamp=datetime.now(),
            )

        try:
            prompt = self._format_prompt(metal_type, quote, overview, news_context)

            logger.info(f"========== AI Analysis: {metal_name} ==========")
            logger.info(f"[LLM] Model: {self._current_model_name}")
            logger.info(f"[LLM] Prompt length: {len(prompt)} chars")

            generation_config = {
                "temperature": config.gemini_temperature,
                "max_output_tokens": 8192,
            }

            start_time = time.time()
            response_text = self._call_api_with_retry(prompt, generation_config)
            elapsed = time.time() - start_time

            logger.info(f"[LLM] Response received in {elapsed:.2f}s, length: {len(response_text)} chars")

            result = self._parse_response(response_text, metal_type)
            result.raw_response = response_text
            result.timestamp = datetime.now()

            logger.info(f"[LLM] {metal_name} analysis complete: {result.trend_prediction}, score {result.sentiment_score}")

            return result

        except Exception as e:
            logger.error(f"AI analysis for {metal_name} failed: {e}")
            return PreciousMetalsAnalysisResult(
                metal_type=metal_type,
                sentiment_score=50,
                trend_prediction="sideways",
                operation_advice="hold",
                confidence_level="low",
                core_conclusion=f"分析过程出错: {str(e)[:100]}",
                risk_warning="分析失败，请稍后重试",
                success=False,
                error_message=str(e),
                timestamp=datetime.now(),
            )

    def _format_prompt(
        self,
        metal_type: MetalType,
        quote: MetalQuote,
        overview: PreciousMetalsOverview,
        news_context: Optional[str] = None
    ) -> str:
        """Format the analysis prompt"""
        metal_name = "黄金" if metal_type == MetalType.GOLD else "白银"

        # Format values safely
        def fmt_price(val):
            return f"${val:.2f}" if val is not None else "N/A"

        def fmt_pct(val):
            return f"{val:+.2f}%" if val is not None else "N/A"

        # Determine if international price is realtime
        intl_realtime_tag = ""
        if quote.data_source and "实时" in quote.data_source:
            intl_realtime_tag = "（实时）"
        elif quote.data_source and "收盘" in quote.data_source:
            intl_realtime_tag = "（收盘）"

        prompt = f"""# {metal_name}分析请求

## 📊 {metal_name}行情数据

### 国际市场（COMEX）
| 指标 | 数值 |
|------|------|
| 当前价格 | {fmt_price(quote.intl_price)} {intl_realtime_tag} |
| 开盘价 | {fmt_price(quote.intl_open)} |
| 最高价 | {fmt_price(quote.intl_high)} |
| 最低价 | {fmt_price(quote.intl_low)} |
| 昨收价 | {fmt_price(quote.intl_prev_close)} |
| 涨跌幅 | {fmt_pct(quote.intl_change_pct)} |"""

        prompt += f"""

### 技术指标
| 均线 | 数值 |
|------|------|
| MA5 | {fmt_price(quote.ma5)} |
| MA10 | {fmt_price(quote.ma10)} |
| MA20 | {fmt_price(quote.ma20)} |
| MA60 | {fmt_price(quote.ma60)} |
"""

        if quote.domestic_price:
            unit = "元/克" if metal_type == MetalType.GOLD else "元/千克"
            # Format both change percentages
            pct_by_settlement = fmt_pct(quote.domestic_change_pct) if quote.domestic_change_pct is not None else "N/A"
            pct_by_close = fmt_pct(quote.domestic_change_pct_by_close) if quote.domestic_change_pct_by_close is not None else "N/A"
            prev_settlement = f"¥{quote.domestic_prev_settlement:.2f}" if quote.domestic_prev_settlement else "N/A"
            prev_close = f"¥{quote.domestic_prev_close:.2f}" if quote.domestic_prev_close else "N/A"
            price_time_desc = f" @ {quote.domestic_price_time}" if quote.domestic_price_time else ""
            realtime_tag = "（盘中）" if quote.domestic_is_realtime else "（收盘）"

            prompt += f"""
### 国内市场（上海期货）
| 指标 | 数值 |
|------|------|
| 当前价格 | ¥{quote.domestic_price:.2f} {unit}{price_time_desc} {realtime_tag} |
| 昨日结算价 | {prev_settlement} |
| 昨日收盘价 | {prev_close} |
| 涨跌幅（vs结算价） | {pct_by_settlement} |
| 涨跌幅（vs收盘价） | {pct_by_close} |

> 注：结算价为交易所官方加权均价，用于保证金计算；收盘价为当日最后成交价。
"""

        prompt += """
---

## 🔗 相关性指标
"""

        if overview.usd_index:
            prompt += f"""
### 美元指数
| 指标 | 数值 | 影响 |
|------|------|------|
| 当前值 | {overview.usd_index.value:.2f} | {overview.usd_index.impact_emoji} |
| 涨跌幅 | {overview.usd_index.change_pct:+.2f}% | {overview.usd_index.description} |
"""

        if overview.treasury_10y:
            prompt += f"""
### 10年期美债收益率
| 指标 | 数值 | 影响 |
|------|------|------|
| 当前值 | {overview.treasury_10y.value:.2f}% | {overview.treasury_10y.impact_emoji} |
| 变化 | {overview.treasury_10y.change:+.2f} | {overview.treasury_10y.description} |
"""

        if overview.gold_silver_ratio:
            prompt += f"""
### 金银比
| 指标 | 数值 | 解读 |
|------|------|------|
| 当前比值 | {overview.gold_silver_ratio:.2f} | {overview.gold_silver_ratio_status} |
"""

        prompt += """
---

## 📰 市场新闻
"""
        if news_context:
            prompt += f"""
以下是近期贵金属相关新闻，请重点提取：
1. 🏦 **央行动态**：各国央行购金/售金
2. 📊 **经济数据**：通胀、就业、GDP等
3. 🌍 **地缘政治**：战争、制裁、危机
4. 💵 **美联储政策**：加息/降息预期

```
{news_context}
```
"""
        else:
            prompt += """
未搜索到近期相关新闻。请主要依据行情数据和相关性指标进行分析。
"""

        prompt += f"""
---

## ✅ 分析任务

请为 **{metal_name}** 生成专业分析报告，严格按照 JSON 格式输出。

### 重点关注：
1. ❓ 美元指数走势对{metal_name}的影响？
2. ❓ 美债收益率变化对{metal_name}的影响？
3. ❓ 当前价格处于什么技术位置？（支撑/阻力）
4. ❓ 短期（1-3日）和中期（1-2周）趋势预判？
5. ❓ 有无重大风险事件需要关注？

### 输出要求：
- **核心结论**：一句话说清该买/该卖/该等
- **宏观分析**：美元、收益率、通胀的综合影响
- **技术点位**：具体的支撑位和阻力位（精确到美元）
- **趋势预判**：短期和中期展望

请输出完整的 JSON 格式分析报告。"""

        return prompt

    def _parse_response(
        self,
        response_text: str,
        metal_type: MetalType
    ) -> PreciousMetalsAnalysisResult:
        """Parse AI response into structured result"""
        try:
            # Clean response text
            cleaned_text = response_text
            if '```json' in cleaned_text:
                cleaned_text = cleaned_text.replace('```json', '').replace('```', '')
            elif '```' in cleaned_text:
                cleaned_text = cleaned_text.replace('```', '')

            # Find JSON content
            json_start = cleaned_text.find('{')
            json_end = cleaned_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = cleaned_text[json_start:json_end]
                json_str = self._fix_json_string(json_str)
                data = json.loads(json_str)

                # Parse trend prediction detail
                trend_detail = data.get('trend_prediction_detail', {})
                if not isinstance(trend_detail, dict):
                    trend_detail = {}

                # Safe parsing helpers
                def safe_int(val, default=50):
                    try:
                        return int(val) if val is not None else default
                    except (ValueError, TypeError):
                        return default

                def safe_float_list(val):
                    if not isinstance(val, list):
                        return []
                    result = []
                    for item in val:
                        try:
                            result.append(float(item))
                        except (ValueError, TypeError):
                            pass
                    return result

                def safe_str_list(val):
                    if not isinstance(val, list):
                        return []
                    return [str(item) for item in val if item is not None]

                def safe_dict(val):
                    """Ensure value is a dict, return None otherwise"""
                    return val if isinstance(val, dict) else None

                def normalize_trend(val):
                    """Normalize trend_prediction to expected values"""
                    val_str = str(val).lower().strip()
                    mapping = {
                        'up': 'up', '上涨': 'up', '看涨': 'up', '涨': 'up', 'bullish': 'up',
                        'down': 'down', '下跌': 'down', '看跌': 'down', '跌': 'down', 'bearish': 'down',
                        'sideways': 'sideways', '震荡': 'sideways', '横盘': 'sideways', 'neutral': 'sideways',
                    }
                    return mapping.get(val_str, 'sideways')

                def normalize_advice(val):
                    """Normalize operation_advice to expected values"""
                    val_str = str(val).lower().strip()
                    mapping = {
                        'buy': 'buy', '买入': 'buy', '买': 'buy', 'strong_buy': 'strong_buy',
                        'sell': 'sell', '卖出': 'sell', '卖': 'sell', 'strong_sell': 'strong_sell',
                        'hold': 'hold', '持有': 'hold', '观望': 'hold', '等待': 'hold',
                    }
                    return mapping.get(val_str, 'hold')

                return PreciousMetalsAnalysisResult(
                    metal_type=metal_type,
                    sentiment_score=safe_int(data.get('sentiment_score'), 50),
                    trend_prediction=normalize_trend(data.get('trend_prediction', 'sideways')),
                    operation_advice=normalize_advice(data.get('operation_advice', 'hold')),
                    confidence_level=str(data.get('confidence_level', 'medium')),
                    core_conclusion=str(data.get('core_conclusion', '')),
                    macro_analysis=safe_dict(data.get('macro_analysis')),
                    correlation_summary=str(data.get('correlation_summary', '')),
                    technical_analysis=safe_dict(data.get('technical_analysis')),
                    support_levels=safe_float_list(data.get('support_levels', [])),
                    resistance_levels=safe_float_list(data.get('resistance_levels', [])),
                    short_term_outlook=str(trend_detail.get('short_term', data.get('short_term_outlook', ''))),
                    medium_term_outlook=str(trend_detail.get('medium_term', data.get('medium_term_outlook', ''))),
                    risk_warning=str(data.get('risk_warning', '')),
                    positive_catalysts=safe_str_list(data.get('positive_catalysts', [])),
                    negative_catalysts=safe_str_list(data.get('negative_catalysts', [])),
                    news_summary=str(data.get('news_summary', '')),
                    analysis_summary=str(data.get('analysis_summary', '')),
                    success=True,
                )
            else:
                logger.warning("Could not extract JSON from response")
                return self._parse_text_response(response_text, metal_type)

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
            return self._parse_text_response(response_text, metal_type)
        except (ValueError, TypeError) as e:
            logger.warning(f"Data parsing failed: {e}")
            return self._parse_text_response(response_text, metal_type)

    def _fix_json_string(self, json_str: str) -> str:
        """Fix common JSON format issues"""
        import re

        # Remove comments
        json_str = re.sub(r'//.*?\n', '\n', json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)

        # Fix trailing commas
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)

        # Fix boolean values
        json_str = json_str.replace('True', 'true').replace('False', 'false')

        # Use json-repair if available
        if repair_json:
            json_str = repair_json(json_str)

        return json_str

    def _parse_text_response(
        self,
        response_text: str,
        metal_type: MetalType
    ) -> PreciousMetalsAnalysisResult:
        """Parse plain text response as fallback"""
        sentiment_score = 50
        trend = "sideways"
        advice = "hold"

        text_lower = response_text.lower()

        positive_keywords = ['看多', '买入', '上涨', '突破', '利好', 'bullish', 'buy', '支撑']
        negative_keywords = ['看空', '卖出', '下跌', '跌破', '利空', 'bearish', 'sell', '阻力']

        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)

        if positive_count > negative_count + 1:
            sentiment_score = 65
            trend = "up"
            advice = "buy"
        elif negative_count > positive_count + 1:
            sentiment_score = 35
            trend = "down"
            advice = "sell"

        summary = response_text[:500] if response_text else '无分析结果'

        return PreciousMetalsAnalysisResult(
            metal_type=metal_type,
            sentiment_score=sentiment_score,
            trend_prediction=trend,
            operation_advice=advice,
            confidence_level="low",
            core_conclusion=summary[:100],
            analysis_summary=summary,
            risk_warning="JSON解析失败，结果仅供参考",
            success=True,
        )


def get_precious_metals_analyzer() -> PreciousMetalsAIAnalyzer:
    """Get a PreciousMetalsAIAnalyzer instance"""
    return PreciousMetalsAIAnalyzer()
