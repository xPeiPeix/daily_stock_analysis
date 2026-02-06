# -*- coding: utf-8 -*-
"""
===================================
代理绕过模块 - 强制国内金融接口直连
===================================

问题背景：
当系统运行 Clash/V2Ray 等代理软件（尤其是 TUN 模式）时，
即使设置了 NO_PROXY 环境变量，requests 库仍可能通过代理发送请求，
导致国内金融数据接口（东方财富、新浪、腾讯等）连接失败。

解决方案：
通过 monkey-patch requests 库，强制对国内域名使用直连（不走代理）。

使用方式：
在程序入口处（main.py）导入此模块即可：
    import data_provider._proxy_bypass  # noqa: F401
"""

import os
import logging

logger = logging.getLogger(__name__)

# 国内金融数据源域名列表（需要绕过代理直连）
DOMESTIC_DOMAINS = [
    'eastmoney.com',
    'push2.eastmoney.com',
    'push2ex.eastmoney.com',
    'quote.eastmoney.com',
    'datacenter.eastmoney.com',
    'data.eastmoney.com',
    'emweb.securities.eastmoney.com',
    'sina.com.cn',
    'hq.sinajs.cn',
    'finance.sina.com.cn',
    '163.com',
    'money.163.com',
    'tushare.pro',
    'baostock.com',
    'sse.com.cn',
    'szse.cn',
    'csindex.com.cn',
    'cninfo.com.cn',
    'gtimg.cn',
    'qt.gtimg.cn',
    'web.ifzq.gtimg.cn',
    'localhost',
    '127.0.0.1',
]


def _is_domestic_host(host: str) -> bool:
    """检查是否为国内金融数据源域名"""
    if not host:
        return False
    host_lower = host.lower()
    for domain in DOMESTIC_DOMAINS:
        if host_lower == domain or host_lower.endswith('.' + domain):
            return True
    return False


def _patch_requests():
    """
    Monkey-patch requests 库，强制国内域名直连

    原理：
    1. 拦截 requests.Session.request 方法
    2. 对国内域名，强制设置 proxies={} 禁用代理
    3. 对其他域名，保持原有行为
    """
    try:
        import requests
        from urllib.parse import urlparse

        # 保存原始方法
        _original_request = requests.Session.request

        def _patched_request(self, method, url, **kwargs):
            """拦截请求，对国内域名禁用代理"""
            try:
                parsed = urlparse(url)
                host = parsed.hostname or ''

                if _is_domestic_host(host):
                    # 强制禁用代理（仅对当前请求生效，不修改 Session 状态）
                    kwargs['proxies'] = {}
                    logger.debug(f"[代理绕过] 国内域名直连: {host}")
            except Exception as e:
                logger.debug(f"[代理绕过] URL 解析失败: {e}")

            return _original_request(self, method, url, **kwargs)

        # 应用 patch
        requests.Session.request = _patched_request
        logger.info("[代理绕过] requests 库已 patch，国内金融接口将直连")

    except ImportError:
        logger.warning("[代理绕过] requests 库未安装，跳过 patch")
    except Exception as e:
        logger.error(f"[代理绕过] patch 失败: {e}")


def _patch_urllib3():
    """
    Monkey-patch urllib3 库，强制国内域名直连

    这是更底层的 patch，用于处理 requests 内部使用 urllib3 的情况
    """
    try:
        import urllib3
        from urllib3.util.proxy import connection_requires_http_tunnel

        # 保存原始函数
        _original_requires_tunnel = connection_requires_http_tunnel

        def _patched_requires_tunnel(proxy_headers, proxy_url, destination_scheme):
            """对国内域名，返回 False 表示不需要代理隧道"""
            # 这个函数在 urllib3 内部用于判断是否需要建立代理隧道
            # 我们无法直接获取目标 host，所以这个 patch 效果有限
            return _original_requires_tunnel(proxy_headers, proxy_url, destination_scheme)

        # urllib3 的 patch 效果有限，主要依赖 requests 层面的 patch

    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"[代理绕过] urllib3 patch 失败: {e}")


def _clear_proxy_env():
    """清除代理环境变量"""
    proxy_vars = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']
    for var in proxy_vars:
        if var in os.environ:
            logger.debug(f"[代理绕过] 清除环境变量: {var}")
            del os.environ[var]


def _set_no_proxy():
    """设置 NO_PROXY 环境变量"""
    no_proxy_value = ','.join(DOMESTIC_DOMAINS)
    current = os.environ.get('NO_PROXY', '')
    if current:
        merged = set(current.split(',') + DOMESTIC_DOMAINS)
        no_proxy_value = ','.join(merged)
    os.environ['NO_PROXY'] = no_proxy_value
    os.environ['no_proxy'] = no_proxy_value
    logger.debug(f"[代理绕过] NO_PROXY 已设置: {len(DOMESTIC_DOMAINS)} 个域名")


# 模块加载时自动执行
_clear_proxy_env()
_set_no_proxy()
_patch_requests()
