#!/usr/bin/env python3
"""AKShare 历史行情初始化脚本（最小可运行版）。

用途：
1. 拉取原始日线与前复权日线
2. 计算 MA/KDJ/MACD
3. 估算历史流通市值并打 cap bucket
4. 输出 CSV，并在提供 MySQL DSN 时写入 MySQL

依赖（自行安装）：
    pip install akshare pandas sqlalchemy pymysql
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import random
import traceback
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


SOURCE = "AKSHARE"
FEATURE_VERSION = "v1"
DEFAULT_OUTPUT_DIR = "output/akshare_bootstrap"
RETRY_DELAYS_SECONDS = [1, 3, 5]
SYMBOL_PAUSE_SECONDS = 2
RETRY_JITTER_MAX_SECONDS = 0.6
SYMBOL_CHUNK_SIZE = 20
CHUNK_PAUSE_SECONDS = 15
STOCK_BASIC_CACHE_PATH = ".cache/akshare_stock_basic_snapshot.pkl"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_FETCH_DEBUG_BODY_MAX_CHARS = 800
FETCH_DEBUG_LOG_FILENAME = "fetch_debug_log.jsonl"
DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}
SENSITIVE_HEADER_NAMES = {"authorization", "cookie", "set-cookie", "proxy-authorization"}
INDEX_SYMBOLS = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
]


@dataclass
class Config:
    symbols: List[str]
    start_date: str
    end_date: str
    mysql_dsn: Optional[str]
    output_dir: str
    request_batch_id: str
    batch_date: str
    fetch_debug: bool
    fetch_debug_body_max_chars: int


@dataclass
class FetchResult:
    dataset: str
    success: bool
    frame: Optional[object]
    error_message: Optional[str]
    attempts: int
    error_type: Optional[str]


@dataclass
class HttpDebugSettings:
    enabled: bool
    body_max_chars: int
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS


class BootstrapError(RuntimeError):
    """Raised when the bootstrap flow cannot continue."""


class FetchFailure(BootstrapError):
    """Raised when a fetch step exhausts retries."""

    def __init__(self, dataset: str, symbol: str, error_message: str, attempts: int, error_type: str):
        self.dataset = dataset
        self.symbol = symbol
        self.error_message = error_message
        self.attempts = attempts
        self.error_type = error_type
        super().__init__("%s 抓取失败: %s" % (dataset, error_message))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_csv_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")


def lazy_import_pandas():
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise BootstrapError("缺少 pandas，请先执行: pip install pandas") from exc
    return pd


def lazy_import_akshare():
    try:
        import akshare as ak
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise BootstrapError("缺少 akshare，请先执行: pip install akshare") from exc
    return ak


def lazy_import_sqlalchemy():
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise BootstrapError("缺少 sqlalchemy，请先执行: pip install sqlalchemy pymysql") from exc
    return create_engine, text


def empty_fetch_debug_logs() -> List[Dict[str, object]]:
    return []


def env_proxy_usage() -> Dict[str, bool]:
    return {
        "http_proxy": bool(os.getenv("HTTP_PROXY") or os.getenv("http_proxy")),
        "https_proxy": bool(os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")),
        "all_proxy": bool(os.getenv("ALL_PROXY") or os.getenv("all_proxy")),
        "no_proxy": bool(os.getenv("NO_PROXY") or os.getenv("no_proxy")),
    }


def proxy_in_use(proxy_usage: Dict[str, bool]) -> bool:
    return any(proxy_usage.values())


def truncate_text(value: Optional[str], max_chars: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + "...(truncated)"


def summarize_headers(headers) -> Dict[str, str]:
    summary = {}
    if not headers:
        return summary
    items = headers.items() if hasattr(headers, "items") else headers
    for key, value in items:
        name = str(key)
        if name.lower() in SENSITIVE_HEADER_NAMES:
            summary[name] = "<redacted>"
        else:
            summary[name] = truncate_text(value, 200) or ""
    return summary


def summarize_params(value):
    if value is None:
        return None
    try:
        if isinstance(value, dict):
            return {str(key): truncate_text(value[key], 120) for key in sorted(value.keys(), key=lambda item: str(item))}
        if isinstance(value, (list, tuple)):
            return [truncate_text(item, 120) for item in value]
        return truncate_text(value, 200)
    except Exception:
        return truncate_text(repr(value), 200)


def summarize_response_headers(headers) -> Dict[str, str]:
    allowlist = {"content-type", "content-length", "server", "location", "set-cookie"}
    if not headers:
        return {}
    items = headers.items() if hasattr(headers, "items") else headers
    summary = {}
    for key, value in items:
        name = str(key)
        if name.lower() in allowlist:
            summary[name] = "<redacted>" if name.lower() in SENSITIVE_HEADER_NAMES else truncate_text(value, 200) or ""
    return summary


def extract_exception_chain(exc: Exception) -> List[str]:
    chain = []
    current = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append("%s: %s" % (current.__class__.__name__, current))
        next_exc = current.__cause__ or current.__context__
        if next_exc is None and getattr(current, "args", None):
            nested = [arg for arg in current.args if isinstance(arg, BaseException)]
            next_exc = nested[0] if nested else None
        current = next_exc
    return chain


def debug_event_has_http_problem(event: Dict[str, object]) -> bool:
    status_code = event.get("response_status_code")
    content_type = str(event.get("response_content_type") or "").lower()
    preview = str(event.get("response_body_preview") or "").lower()
    if isinstance(status_code, int) and status_code >= 300:
        return True
    if "text/html" in content_type:
        return True
    return "<html" in preview or "验证码" in preview or "captcha" in preview


def format_debug_event_console(event: Dict[str, object]) -> str:
    request_bits = [
        "method=%s" % (event.get("method") or "UNKNOWN"),
        "url=%s" % (event.get("final_url") or event.get("url") or ""),
        "timeout=%s" % (event.get("request_timeout") if event.get("request_timeout") is not None else "default"),
        "proxy_in_use=%s" % event.get("proxy_in_use"),
        "response_missing=%s" % event.get("response_missing"),
    ]
    status_code = event.get("response_status_code")
    if status_code is not None:
        request_bits.append("status=%s" % status_code)
    reason = event.get("response_reason")
    if reason:
        request_bits.append("reason=%s" % reason)
    preview = event.get("response_body_preview")
    if preview:
        request_bits.append("body_preview=%s" % truncate_text(preview, 240))
    error_chain = event.get("exception_chain") or []
    if error_chain:
        request_bits.append("exception_chain=%s" % " | ".join(error_chain))
    return " ".join(request_bits)


@contextmanager
def http_debug_capture(
    *,
    request_batch_id: str,
    dataset: str,
    symbol: str,
    attempt_no: int,
    max_attempts: int,
    debug_settings: HttpDebugSettings,
    fetch_debug_logs: List[Dict[str, object]],
):
    try:
        import requests
        import requests.api as requests_api
    except ImportError:  # pragma: no cover - runtime dependency
        yield
        return

    original_session_request = requests.sessions.Session.request
    original_api_request = requests_api.request
    original_requests_request = getattr(requests, "request", None)
    shared_session = requests.sessions.Session()

    def wrapped_session_request(session, method, url, **kwargs):
        started_at = utc_now()
        proxy_usage = env_proxy_usage()
        merged_headers = dict(DEFAULT_HTTP_HEADERS)
        if kwargs.get("headers"):
            merged_headers.update(dict(kwargs["headers"]))
        kwargs["headers"] = merged_headers
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = debug_settings.timeout_seconds
        timeout = kwargs.get("timeout")
        response = None
        event = {
            "request_batch_id": request_batch_id,
            "dataset": dataset,
            "symbol": safe_symbol_text(symbol),
            "attempt_no": attempt_no,
            "max_attempts": max_attempts,
            "started_at": format_csv_datetime(started_at),
            "method": str(method).upper(),
            "url": url,
            "final_url": url,
            "request_params": summarize_params(kwargs.get("params")),
            "request_timeout": timeout,
            "request_headers": summarize_headers(merged_headers),
            "proxy_usage": proxy_usage,
            "proxy_in_use": proxy_in_use(proxy_usage),
            "response_missing": True,
            "response_status_code": None,
            "response_reason": None,
            "response_content_type": None,
            "response_headers": {},
            "response_body_preview": None,
            "response_body_truncated": False,
            "exception_type": None,
            "exception_message": None,
            "exception_chain": [],
            "traceback_summary": None,
        }
        try:
            response = original_session_request(session, method, url, **kwargs)
            event["response_missing"] = False
            event["final_url"] = getattr(response, "url", url)
            event["response_status_code"] = getattr(response, "status_code", None)
            event["response_reason"] = getattr(response, "reason", None)
            event["response_headers"] = summarize_response_headers(getattr(response, "headers", {}))
            event["response_content_type"] = getattr(response, "headers", {}).get("Content-Type") if getattr(response, "headers", None) else None
            response_text = None
            try:
                response_text = response.text
            except Exception:
                response_text = None
            preview = truncate_text(response_text, debug_settings.body_max_chars)
            event["response_body_preview"] = preview
            event["response_body_truncated"] = bool(response_text and preview and len(preview) < len(response_text))
            return response
        except Exception as exc:
            response = getattr(exc, "response", None)
            event["exception_type"] = exc.__class__.__name__
            event["exception_message"] = str(exc)
            event["exception_chain"] = extract_exception_chain(exc)
            event["traceback_summary"] = truncate_text("".join(traceback.format_exception_only(type(exc), exc)).strip(), 400)
            if response is not None:
                event["response_missing"] = False
                event["final_url"] = getattr(response, "url", url)
                event["response_status_code"] = getattr(response, "status_code", None)
                event["response_reason"] = getattr(response, "reason", None)
                event["response_headers"] = summarize_response_headers(getattr(response, "headers", {}))
                event["response_content_type"] = getattr(response, "headers", {}).get("Content-Type") if getattr(response, "headers", None) else None
                response_text = None
                try:
                    response_text = response.text
                except Exception:
                    response_text = None
                preview = truncate_text(response_text, debug_settings.body_max_chars)
                event["response_body_preview"] = preview
                event["response_body_truncated"] = bool(response_text and preview and len(preview) < len(response_text))
            raise
        finally:
            ended_at = utc_now()
            event["ended_at"] = format_csv_datetime(ended_at)
            event["duration_ms"] = int((ended_at - started_at).total_seconds() * 1000)
            fetch_debug_logs.append(event)
            if debug_settings.enabled and (event["exception_type"] or debug_event_has_http_problem(event)):
                print("[HTTP DEBUG] dataset=%s symbol=%s %s" % (dataset, safe_symbol_text(symbol), format_debug_event_console(event)))

    def wrapped_api_request(method, url, **kwargs):
        return shared_session.request(method=method, url=url, **kwargs)

    requests.sessions.Session.request = wrapped_session_request
    requests_api.request = wrapped_api_request
    if original_requests_request is not None:
        requests.request = wrapped_api_request
    try:
        yield
    finally:
        requests.sessions.Session.request = original_session_request
        requests_api.request = original_api_request
        if original_requests_request is not None:
            requests.request = original_requests_request
        shared_session.close()


def execute_with_http_debug(
    fetch_func,
    *,
    request_batch_id: str,
    dataset: str,
    symbol: str,
    attempt_no: int,
    max_attempts: int,
    debug_settings: HttpDebugSettings,
    fetch_debug_logs: List[Dict[str, object]],
):
    with http_debug_capture(
        request_batch_id=request_batch_id,
        dataset=dataset,
        symbol=symbol,
        attempt_no=attempt_no,
        max_attempts=max_attempts,
        debug_settings=debug_settings,
        fetch_debug_logs=fetch_debug_logs,
    ):
        return fetch_func()


def empty_stock_basic_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "code",
            "stock_name",
            "exchange",
            "market",
            "board",
            "list_date",
            "delist_date",
            "industry",
            "status",
            "static_total_share",
            "static_float_share",
        ]
    )


def empty_raw_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "code",
            "stock_name",
            "trade_date",
            "source_batch_id",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "amount",
            "turnover_rate",
            "source",
        ]
    )


def empty_feature_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "code",
            "trade_date",
            "source_batch_id",
            "qfq_open",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "volume",
            "ma5",
            "ma10",
            "ma20",
            "k_value",
            "d_value",
            "j_value",
            "dif",
            "dea",
            "macd",
            "turnover_rate",
            "outstanding_share_est",
            "outstanding_share",
            "float_mv_est",
            "cap_bucket",
            "feature_version",
        ]
    )


def empty_staging_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=["source", "dataset", "biz_key", "request_batch_id", "payload_json", "checksum", "status", "fetched_at"]
    )


def empty_quality_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "job_id",
            "dataset",
            "biz_key",
            "check_type",
            "severity",
            "status",
            "actual_value",
            "expected_rule",
            "message",
            "checked_at",
        ]
    )


def empty_fetch_attempt_log_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "request_batch_id",
            "symbol",
            "dataset",
            "attempt_no",
            "max_attempts",
            "started_at",
            "ended_at",
            "duration_ms",
            "success",
            "soft_failure",
            "error_type",
            "error_message",
            "response_missing",
        ]
    )


def empty_symbol_run_log_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "request_batch_id",
            "symbol",
            "raw_status",
            "qfq_status",
            "share_status",
            "final_status",
            "retry_count",
            "raw_error_type",
            "qfq_error_type",
            "share_error_type",
            "error_message",
        ]
    )


def empty_trading_calendar_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(columns=["trade_date", "exchange", "is_open"])


def empty_stock_basic_snapshot_log_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(columns=["source_name", "status", "row_count", "error_message", "fetched_at"])


def empty_index_raw_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "index_code",
            "index_name",
            "trade_date",
            "source_batch_id",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "amount",
            "source",
        ]
    )


def empty_index_feature_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "index_code",
            "index_name",
            "trade_date",
            "source_batch_id",
            "pct_change_1d",
            "drawdown_5d",
            "vol_ratio_1d_5d",
            "panic_flag",
        ]
    )


def empty_index_fetch_log_df():
    pd = lazy_import_pandas()
    return pd.DataFrame(
        columns=[
            "request_batch_id",
            "index_code",
            "index_name",
            "status",
            "error_type",
            "error_message",
            "retry_count",
            "fetched_at",
        ]
    )


def canonical_code(symbol: str) -> str:
    raw = symbol.strip().upper()
    if not raw:
        raise BootstrapError("symbol 不能为空")

    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 6:
        raise BootstrapError("当前仅支持 6 位 A 股代码，例如 600519 或 300750.SZ")

    if raw.endswith(".SH") or raw.startswith("SH"):
        suffix = "SH"
    elif raw.endswith(".SZ") or raw.startswith("SZ"):
        suffix = "SZ"
    elif raw.endswith(".BJ") or raw.startswith("BJ"):
        suffix = "BJ"
    else:
        suffix = infer_exchange_from_code(digits)
    return "%s.%s" % (digits, suffix)


def infer_exchange_from_code(digits: str) -> str:
    if digits.startswith(("5", "6", "9")):
        return "SH"
    if digits.startswith(("0", "2", "3")):
        return "SZ"
    if digits.startswith(("4", "8")):
        return "BJ"
    raise BootstrapError("无法根据代码推断交易所: %s" % digits)


def akshare_hist_symbol(symbol: str) -> str:
    return canonical_code(symbol).split(".")[0]


def infer_board(code: str, exchange: str) -> str:
    if exchange == "BJ":
        return "BEIJING"
    if code.startswith("3"):
        return "GEM"
    if code.startswith("688"):
        return "STAR"
    if code.startswith("8"):
        return "BEIJING"
    return "MAIN"


def normalize_board_text(code: str, exchange: str, raw_board: Optional[str]) -> str:
    text = str(raw_board or "").strip().upper()
    if exchange == "BJ" or "北" in text:
        return "BEIJING"
    if code.startswith("688") or "科创" in text:
        return "STAR"
    if code.startswith("3") or "创业" in text:
        return "GEM"
    return "MAIN"


def parse_share_number(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() == "nan":
        return None
    multiplier = 1.0
    if text.endswith("亿"):
        multiplier = 100000000.0
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    try:
        return float(text) * multiplier
    except Exception:
        return None


def stock_basic_cache_path() -> Path:
    path = Path(STOCK_BASIC_CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_stock_basic_cache():
    pd = lazy_import_pandas()
    path = stock_basic_cache_path()
    if not path.exists():
        return empty_stock_basic_df(), empty_stock_basic_snapshot_log_df(), False
    try:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        stock_basic_df = payload.get("stock_basic_df")
        snapshot_log_df = payload.get("snapshot_log_df")
        if stock_basic_df is None or snapshot_log_df is None:
            raise BootstrapError("cache payload invalid")
        stock_basic_df = pd.DataFrame(stock_basic_df)
        snapshot_log_df = pd.DataFrame(snapshot_log_df)
        if "list_date" in stock_basic_df.columns:
            stock_basic_df["list_date"] = pd.to_datetime(stock_basic_df["list_date"], errors="coerce").dt.date
        return stock_basic_df, snapshot_log_df, True
    except Exception:
        return empty_stock_basic_df(), empty_stock_basic_snapshot_log_df(), False


def save_stock_basic_cache(stock_basic_df, snapshot_log_df) -> None:
    path = stock_basic_cache_path()
    payload = {
        "stock_basic_df": stock_basic_df.to_dict(orient="records"),
        "snapshot_log_df": snapshot_log_df.to_dict(orient="records"),
    }
    with path.open("wb") as handle:
        pickle.dump(payload, handle)


def normalize_spot_board(code: str) -> str:
    digits, exchange = canonical_code(code).split(".")
    return infer_board(digits, exchange)


def fetch_stock_spot_fallback(wanted_codes: Optional[Sequence[str]] = None):
    ak = lazy_import_akshare()
    pd = lazy_import_pandas()
    frame = ak.stock_zh_a_spot_em()
    if frame is None or frame.empty:
        return empty_stock_basic_df()
    columns = {str(column).strip(): column for column in frame.columns}
    rows = []
    wanted = {canonical_code(code) for code in wanted_codes} if wanted_codes else None
    for _, row in frame.iterrows():
        code_value = row.get(columns.get("代码"))
        if code_value is None:
            continue
        code = canonical_code(str(code_value))
        if wanted and code not in wanted:
            continue
        stock_name = row.get(columns.get("名称")) or code
        name_text = str(stock_name or code)
        status = "LISTED"
        if "ST" in name_text.upper():
            status = "RISK_WARNING"
        rows.append(
            {
                "code": code,
                "stock_name": name_text,
                "exchange": code.split(".")[1],
                "market": "A_SHARE",
                "board": normalize_spot_board(code),
                "list_date": None,
                "delist_date": None,
                "industry": None,
                "status": status,
                "static_total_share": None,
                "static_float_share": None,
            }
        )
    return pd.DataFrame(rows) if rows else empty_stock_basic_df()


def fetch_stock_basic_snapshot():
    ak = lazy_import_akshare()
    pd = lazy_import_pandas()
    rows = []
    snapshot_logs = []

    def record_snapshot(source_name: str, status: str, row_count: int, error_message: Optional[str] = None):
        snapshot_logs.append(
            {
                "source_name": source_name,
                "status": status,
                "row_count": row_count,
                "error_message": error_message,
                "fetched_at": format_csv_datetime(utc_now()),
            }
        )

    sources = [
        ("stock_info_sh_name_code", lambda: ak.stock_info_sh_name_code(symbol="主板A股"), "SH"),
        ("stock_info_sz_name_code", lambda: ak.stock_info_sz_name_code(symbol="A股列表"), "SZ"),
        ("stock_info_bj_name_code", lambda: ak.stock_info_bj_name_code(), "BJ"),
    ]

    for source_name, fetcher, exchange in sources:
        try:
            frame = fetcher()
            if frame is None or frame.empty:
                record_snapshot(source_name, "EMPTY", 0, "empty result")
                continue
            local = frame.copy()
            columns = {str(column).strip(): column for column in local.columns}
            for _, row in local.iterrows():
                code_value = row.get(columns.get("证券代码")) or row.get(columns.get("A股代码")) or row.get(columns.get("代码"))
                if code_value is None:
                    continue
                code = canonical_code(str(code_value))
                stock_name = (
                    row.get(columns.get("证券简称"))
                    or row.get(columns.get("A股简称"))
                    or row.get(columns.get("名称"))
                    or code
                )
                list_date = (
                    row.get(columns.get("上市日期"))
                    or row.get(columns.get("A股上市日期"))
                    or row.get(columns.get("上市时间"))
                )
                industry = row.get(columns.get("所属行业")) or row.get(columns.get("行业"))
                total_share = (
                    row.get(columns.get("总股本"))
                    or row.get(columns.get("A股总股本"))
                    or row.get(columns.get("总股本(亿)"))
                )
                float_share = (
                    row.get(columns.get("流通股本"))
                    or row.get(columns.get("A股流通股本"))
                    or row.get(columns.get("流通股本(亿)"))
                )
                board_value = row.get(columns.get("板块"))
                rows.append(
                    {
                        "code": code,
                        "stock_name": str(stock_name or code),
                        "exchange": exchange,
                        "market": "A_SHARE",
                        "board": normalize_board_text(code.split(".")[0], exchange, board_value),
                        "list_date": list_date,
                        "delist_date": None,
                        "industry": industry,
                        "status": "LISTED",
                        "static_total_share": parse_share_number(total_share),
                        "static_float_share": parse_share_number(float_share),
                    }
                )
            record_snapshot(source_name, "SUCCESS", len(local))
        except Exception as exc:  # pragma: no cover - runtime API/network path
            record_snapshot(source_name, "FAILED", 0, str(exc))

    stock_basic_df = pd.DataFrame(rows) if rows else empty_stock_basic_df()
    used_cache = False
    if not stock_basic_df.empty:
        stock_basic_df["code"] = stock_basic_df["code"].astype(str)
        stock_basic_df["list_date"] = pd.to_datetime(stock_basic_df["list_date"], errors="coerce").dt.date
        stock_basic_df = stock_basic_df.drop_duplicates(subset=["code"], keep="first").sort_values("code").reset_index(drop=True)
    snapshot_log_df = pd.DataFrame(snapshot_logs) if snapshot_logs else empty_stock_basic_snapshot_log_df()
    if stock_basic_df.empty:
        cached_df, cached_log_df, cache_hit = load_stock_basic_cache()
        if cache_hit and not cached_df.empty:
            used_cache = True
            stock_basic_df = cached_df
            snapshot_log_df = pd.concat(
                [
                    snapshot_log_df,
                    pd.DataFrame(
                        [
                            {
                                "source_name": "stock_basic_cache",
                                "status": "USED",
                                "row_count": len(cached_df),
                                "error_message": None,
                                "fetched_at": format_csv_datetime(utc_now()),
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
    elif not stock_basic_df.empty:
        save_stock_basic_cache(stock_basic_df, snapshot_log_df)
        snapshot_log_df = pd.concat(
            [
                snapshot_log_df,
                pd.DataFrame(
                    [
                        {
                            "source_name": "stock_basic_cache",
                            "status": "UPDATED",
                            "row_count": len(stock_basic_df),
                            "error_message": None,
                            "fetched_at": format_csv_datetime(utc_now()),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    if stock_basic_df.empty and not used_cache:
        try:
            spot_df = fetch_stock_spot_fallback()
            if not spot_df.empty:
                stock_basic_df = spot_df.drop_duplicates(subset=["code"], keep="first").sort_values("code").reset_index(drop=True)
                snapshot_log_df = pd.concat(
                    [
                        snapshot_log_df,
                        pd.DataFrame(
                            [
                                {
                                    "source_name": "stock_zh_a_spot_em_fallback",
                                    "status": "USED",
                                    "row_count": len(stock_basic_df),
                                    "error_message": None,
                                    "fetched_at": format_csv_datetime(utc_now()),
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
        except Exception as exc:  # pragma: no cover - runtime API/network path
            snapshot_log_df = pd.concat(
                [
                    snapshot_log_df,
                    pd.DataFrame(
                        [
                            {
                                "source_name": "stock_zh_a_spot_em_fallback",
                                "status": "FAILED",
                                "row_count": 0,
                                "error_message": str(exc),
                                "fetched_at": format_csv_datetime(utc_now()),
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
    return stock_basic_df, snapshot_log_df


def filter_stock_basic_for_symbols(stock_basic_df, symbols: Sequence[str]):
    pd = lazy_import_pandas()
    wanted = {canonical_code(symbol) for symbol in symbols}
    if stock_basic_df.empty:
        filtered = empty_stock_basic_df()
        missing = sorted(wanted)
    else:
        filtered = stock_basic_df[stock_basic_df["code"].isin(wanted)].copy()
        missing = sorted(wanted - set(filtered["code"].tolist()))
    if missing:
        try:
            spot_fallback_df = fetch_stock_spot_fallback(missing)
        except Exception:
            spot_fallback_df = empty_stock_basic_df()
        if not spot_fallback_df.empty:
            filtered = pd.concat([filtered, spot_fallback_df], ignore_index=True)
            missing = sorted(wanted - set(filtered["code"].tolist()))
    if missing:
        fallback_rows = []
        for code in missing:
            digits, exchange = code.split(".")
            fallback_rows.append(
                {
                    "code": code,
                    "stock_name": code,
                    "exchange": exchange,
                    "market": "A_SHARE",
                    "board": infer_board(digits, exchange),
                    "list_date": None,
                    "delist_date": None,
                    "industry": None,
                    "status": "LISTED",
                    "static_total_share": None,
                    "static_float_share": None,
                }
            )
        filtered = pd.concat([filtered, pd.DataFrame(fallback_rows)], ignore_index=True)
    return filtered.sort_values("code").reset_index(drop=True)


def fetch_trading_calendar(start_date: str, end_date: str):
    ak = lazy_import_akshare()
    pd = lazy_import_pandas()
    frame = ak.tool_trade_date_hist_sina()
    if frame is None or frame.empty:
        return empty_trading_calendar_df()
    column = frame.columns[0]
    dates = pd.to_datetime(frame[column], errors="coerce").dt.date
    start = datetime.strptime(normalize_date_arg(start_date), "%Y%m%d").date()
    end = datetime.strptime(normalize_date_arg(end_date), "%Y%m%d").date()
    filtered_dates = sorted([value for value in dates.dropna().tolist() if start <= value <= end])
    rows = []
    for trade_date in filtered_dates:
        for exchange in ["SH", "SZ", "BJ"]:
            rows.append({"trade_date": trade_date, "exchange": exchange, "is_open": 1})
    return pd.DataFrame(rows) if rows else empty_trading_calendar_df()


def fetch_index_history(index_code: str, start_date: str, end_date: str):
    ak = lazy_import_akshare()
    frame = ak.stock_zh_index_daily_em(symbol=index_code)
    if frame is None or frame.empty:
        return frame
    pd = lazy_import_pandas()
    local = frame.copy()
    local["日期"] = pd.to_datetime(local["日期"], errors="coerce").dt.date
    start = datetime.strptime(normalize_date_arg(start_date), "%Y%m%d").date()
    end = datetime.strptime(normalize_date_arg(end_date), "%Y%m%d").date()
    return local[(local["日期"] >= start) & (local["日期"] <= end)].copy()


def fetch_index_history_with_retry(
    index_code: str,
    index_name: str,
    start_date: str,
    end_date: str,
    request_batch_id: str,
    fetch_attempt_logs: List[Dict[str, object]],
    fetch_debug_logs: List[Dict[str, object]],
    http_debug_settings: HttpDebugSettings,
):
    last_error = None
    last_error_type = None
    attempts = 0
    for attempts, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
        started_at = utc_now()
        print("[FETCH] dataset=stock_zh_index_daily_em symbol=%s attempt=%s/%s" % (index_code, attempts, len(RETRY_DELAYS_SECONDS)))
        try:
            frame = execute_with_http_debug(
                lambda: fetch_index_history(index_code, start_date, end_date),
                request_batch_id=request_batch_id,
                dataset="stock_zh_index_daily_em",
                symbol=index_code,
                attempt_no=attempts,
                max_attempts=len(RETRY_DELAYS_SECONDS),
                debug_settings=http_debug_settings,
                fetch_debug_logs=fetch_debug_logs,
            )
            if frame is None or frame.empty:
                raise BootstrapError("%s index 返回空数据" % index_code)
            ended_at = utc_now()
            fetch_attempt_logs.append(
                build_fetch_attempt_row(
                    request_batch_id=request_batch_id,
                    symbol=index_code,
                    dataset="stock_zh_index_daily_em",
                    attempt_no=attempts,
                    max_attempts=len(RETRY_DELAYS_SECONDS),
                    started_at=started_at,
                    ended_at=ended_at,
                    success=True,
                    soft_failure=False,
                    error_type=None,
                    error_message=None,
                    response_missing=response_missing_for_attempt(
                        fetch_debug_logs,
                        request_batch_id=request_batch_id,
                        dataset="stock_zh_index_daily_em",
                        symbol=index_code,
                        attempt_no=attempts,
                    ),
                )
            )
            return frame, {
                "request_batch_id": request_batch_id,
                "index_code": index_code,
                "index_name": index_name,
                "status": "SUCCESS",
                "error_type": "",
                "error_message": "",
                "retry_count": max(attempts - 1, 0),
                "fetched_at": format_csv_datetime(utc_now()),
            }
        except Exception as exc:  # pragma: no cover - runtime API/network path
            last_error = exc
            last_error_type = classify_fetch_error(exc)
            ended_at = utc_now()
            response_missing = response_missing_for_attempt(
                fetch_debug_logs,
                request_batch_id=request_batch_id,
                dataset="stock_zh_index_daily_em",
                symbol=index_code,
                attempt_no=attempts,
            )
            fetch_attempt_logs.append(
                build_fetch_attempt_row(
                    request_batch_id=request_batch_id,
                    symbol=index_code,
                    dataset="stock_zh_index_daily_em",
                    attempt_no=attempts,
                    max_attempts=len(RETRY_DELAYS_SECONDS),
                    started_at=started_at,
                    ended_at=ended_at,
                    success=False,
                    soft_failure=False,
                    error_type=last_error_type,
                    error_message=str(exc),
                    response_missing=response_missing,
                )
            )
            print("[WARN] dataset=stock_zh_index_daily_em symbol=%s attempt=%s/%s error_type=%s error=%s" % (
                index_code,
                attempts,
                len(RETRY_DELAYS_SECONDS),
                last_error_type,
                exc,
            ))
            print_remote_disconnect_hint(last_error_type, response_missing)
            if attempts < len(RETRY_DELAYS_SECONDS):
                sleep_with_jitter(delay)
    return None, {
        "request_batch_id": request_batch_id,
        "index_code": index_code,
        "index_name": index_name,
        "status": "FAILED",
        "error_type": last_error_type or "UNKNOWN_FETCH_ERROR",
        "error_message": str(last_error) if last_error is not None else "未知错误",
        "retry_count": max(attempts - 1, 0),
        "fetched_at": format_csv_datetime(utc_now()),
    }


def normalize_date_arg(value: str) -> str:
    normalized = value.replace("-", "")
    if len(normalized) != 8 or not normalized.isdigit():
        raise BootstrapError("日期格式必须为 YYYY-MM-DD 或 YYYYMMDD: %s" % value)
    return normalized


def to_date_text(value: str) -> str:
    normalized = normalize_date_arg(value)
    return "%s-%s-%s" % (normalized[0:4], normalized[4:6], normalized[6:8])


def ensure_required_columns(frame, required_columns: Sequence[str], context: str) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise BootstrapError("%s 缺少必要字段: %s" % (context, ", ".join(missing)))


def first_present(frame, candidates: Sequence[str]) -> Optional[str]:
    for column in candidates:
        if column in frame.columns:
            return column
    return None


def to_numeric_series(pd, frame, column: Optional[str], default=None):
    if column is None:
        if default is None:
            return pd.Series([pd.NA] * len(frame), index=frame.index)
        return pd.Series([default] * len(frame), index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def classify_fetch_error(exc: Exception) -> str:
    if isinstance(exc, FetchFailure):
        return exc.error_type

    message = str(exc).lower()
    exc_name = exc.__class__.__name__

    if isinstance(exc, RemoteDisconnected) or "remote end closed connection without response" in message:
        return "REMOTE_DISCONNECTED"
    if "read timed out" in message or exc_name in ["ReadTimeout", "Timeout"]:
        return "READ_TIMEOUT"
    if "connection aborted" in message or "connection reset" in message or exc_name in ["ConnectionError", "ProxyError"]:
        return "CONNECTION_ERROR"
    if "返回空数据" in message or "empty" in message:
        return "EMPTY_RESPONSE"
    if "缺少必要字段" in message or "字段" in message or "schema" in message:
        return "AKSHARE_SCHEMA_ERROR"
    return "UNKNOWN_FETCH_ERROR"


def sleep_with_jitter(base_delay: float) -> None:
    time.sleep(base_delay + random.uniform(0.0, RETRY_JITTER_MAX_SECONDS))


def safe_symbol_text(symbol: str) -> str:
    try:
        return canonical_code(symbol)
    except Exception:
        return symbol


def build_fetch_attempt_row(
    request_batch_id: str,
    symbol: str,
    dataset: str,
    attempt_no: int,
    max_attempts: int,
    started_at: datetime,
    ended_at: datetime,
    success: bool,
    soft_failure: bool,
    error_type: Optional[str],
    error_message: Optional[str],
    response_missing: Optional[bool],
) -> Dict[str, object]:
    return {
        "request_batch_id": request_batch_id,
        "symbol": safe_symbol_text(symbol),
        "dataset": dataset,
        "attempt_no": attempt_no,
        "max_attempts": max_attempts,
        "started_at": format_csv_datetime(started_at),
        "ended_at": format_csv_datetime(ended_at),
        "duration_ms": int((ended_at - started_at).total_seconds() * 1000),
        "success": success,
        "soft_failure": soft_failure,
        "error_type": error_type,
        "error_message": error_message,
        "response_missing": response_missing,
    }


def response_missing_for_attempt(
    fetch_debug_logs: Sequence[Dict[str, object]],
    *,
    request_batch_id: str,
    dataset: str,
    symbol: str,
    attempt_no: int,
) -> Optional[bool]:
    normalized_symbol = safe_symbol_text(symbol)
    matched = [
        event
        for event in fetch_debug_logs
        if event.get("request_batch_id") == request_batch_id
        and event.get("dataset") == dataset
        and event.get("symbol") == normalized_symbol
        and event.get("attempt_no") == attempt_no
    ]
    if not matched:
        return None
    return all(bool(event.get("response_missing", True)) for event in matched)


def print_remote_disconnect_hint(error_type: Optional[str], response_missing: Optional[bool]) -> None:
    if error_type == "REMOTE_DISCONNECTED" and response_missing is not False:
        print("[HINT] 连接在收到 HTTP 响应前被对端关闭，因此无响应体可打印。")


def write_fetch_debug_jsonl(output_dir: Path, fetch_debug_logs: Sequence[Dict[str, object]]) -> None:
    path = output_dir / FETCH_DEBUG_LOG_FILENAME
    with path.open("w", encoding="utf-8") as handle:
        for event in fetch_debug_logs:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def print_batch_level_connection_hint(fetch_attempt_logs: Sequence[Dict[str, object]]) -> None:
    if not fetch_attempt_logs:
        return
    latest_by_target = {}
    for row in fetch_attempt_logs:
        key = (row.get("dataset"), row.get("symbol"))
        attempt_no = int(row.get("attempt_no") or 0)
        current = latest_by_target.get(key)
        current_attempt = int(current.get("attempt_no") or 0) if current else -1
        if current is None or attempt_no >= current_attempt:
            latest_by_target[key] = row
    latest_rows = list(latest_by_target.values())
    if not latest_rows or not all(not bool(row.get("success")) for row in latest_rows):
        return
    error_types = {str(row.get("error_type") or "") for row in latest_rows}
    durations = [int(row.get("duration_ms") or 0) for row in latest_rows]
    if len(error_types) == 1 and all(80 <= duration <= 250 for duration in durations):
        error_type = next(iter(error_types))
        print(
            "[HINT] 本批次股票/指数请求都在约 100~200ms 内以同类错误(%s)失败，更像上游连接级拒绝/风控，而不是 symbol/date 参数问题。"
            % error_type
        )


def new_symbol_run_record(request_batch_id: str, symbol: str) -> Dict[str, object]:
    return {
        "request_batch_id": request_batch_id,
        "symbol": safe_symbol_text(symbol),
        "raw_status": "PENDING",
        "qfq_status": "PENDING",
        "share_status": "PENDING",
        "final_status": "PENDING",
        "retry_count": 0,
        "raw_error_type": "",
        "qfq_error_type": "",
        "share_error_type": "",
        "error_message": "",
    }


def normalize_hist_frame(raw_frame, symbol: str, request_batch_id: str, adjust_label: str):
    pd = lazy_import_pandas()
    if raw_frame is None or raw_frame.empty:
        raise BootstrapError("%s %s 返回空数据" % (symbol, adjust_label))

    frame = raw_frame.copy()
    rename_map = {
        "日期": "trade_date",
        "date": "trade_date",
        "开盘": "open_price",
        "open": "open_price",
        "收盘": "close_price",
        "close": "close_price",
        "最高": "high_price",
        "high": "high_price",
        "最低": "low_price",
        "low": "low_price",
        "成交量": "volume",
        "volume": "volume",
        "成交额": "amount",
        "amount": "amount",
        "换手率": "turnover_rate",
        "turnover": "turnover_rate",
        "股票名称": "stock_name",
        "名称": "stock_name",
        "股票代码": "stock_code",
        "代码": "stock_code",
        "symbol": "stock_code",
    }
    frame = frame.rename(columns=rename_map)

    ensure_required_columns(
        frame,
        ["trade_date", "open_price", "high_price", "low_price", "close_price", "volume"],
        "%s %s" % (symbol, adjust_label),
    )

    code = canonical_code(symbol)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    frame["code"] = code
    frame["source_batch_id"] = request_batch_id
    frame["source"] = SOURCE
    stock_name_series = frame["stock_name"] if "stock_name" in frame.columns else pd.Series([code] * len(frame), index=frame.index)
    frame["stock_name"] = stock_name_series.fillna(code)
    frame["open_price"] = to_numeric_series(pd, frame, "open_price", 0.0)
    frame["high_price"] = to_numeric_series(pd, frame, "high_price", 0.0)
    frame["low_price"] = to_numeric_series(pd, frame, "low_price", 0.0)
    frame["close_price"] = to_numeric_series(pd, frame, "close_price", 0.0)
    frame["volume"] = to_numeric_series(pd, frame, "volume", 0.0).fillna(0.0)
    frame["amount"] = to_numeric_series(pd, frame, "amount", 0.0).fillna(0.0)
    frame["turnover_rate"] = to_numeric_series(pd, frame, "turnover_rate", None)

    frame = frame.sort_values("trade_date").drop_duplicates(subset=["trade_date"], keep="last")
    return frame[[
        "code",
        "stock_name",
        "trade_date",
        "source_batch_id",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "amount",
        "turnover_rate",
        "source",
    ]]


def fetch_raw_history(symbol: str, start_date: str, end_date: str):
    ak = lazy_import_akshare()
    return ak.stock_zh_a_hist(
        symbol=akshare_hist_symbol(symbol),
        period="daily",
        start_date=normalize_date_arg(start_date),
        end_date=normalize_date_arg(end_date),
        adjust="",
    )


def fetch_qfq_history(symbol: str, start_date: str, end_date: str):
    ak = lazy_import_akshare()
    return ak.stock_zh_a_hist(
        symbol=akshare_hist_symbol(symbol),
        period="daily",
        start_date=normalize_date_arg(start_date),
        end_date=normalize_date_arg(end_date),
        adjust="qfq",
    )


def fetch_with_retry(
    dataset: str,
    symbol: str,
    fetch_func,
    request_batch_id: str,
    fetch_attempt_logs: List[Dict[str, object]],
    fetch_debug_logs: List[Dict[str, object]],
    http_debug_settings: HttpDebugSettings,
    soft_failure: bool = False,
) -> FetchResult:
    last_error = None
    last_error_type = None
    attempts = 0
    max_attempts = len(RETRY_DELAYS_SECONDS)
    for attempts, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
        started_at = utc_now()
        print("[FETCH] dataset=%s symbol=%s attempt=%s/%s" % (dataset, symbol, attempts, max_attempts))
        try:
            frame = execute_with_http_debug(
                fetch_func,
                request_batch_id=request_batch_id,
                dataset=dataset,
                symbol=symbol,
                attempt_no=attempts,
                max_attempts=max_attempts,
                debug_settings=http_debug_settings,
                fetch_debug_logs=fetch_debug_logs,
            )
            if frame is None or frame.empty:
                raise BootstrapError("%s 返回空数据" % dataset)
            ended_at = utc_now()
            fetch_attempt_logs.append(
                build_fetch_attempt_row(
                    request_batch_id=request_batch_id,
                    symbol=symbol,
                    dataset=dataset,
                    attempt_no=attempts,
                    max_attempts=max_attempts,
                    started_at=started_at,
                    ended_at=ended_at,
                    success=True,
                    soft_failure=soft_failure,
                    error_type=None,
                    error_message=None,
                    response_missing=response_missing_for_attempt(
                        fetch_debug_logs,
                        request_batch_id=request_batch_id,
                        dataset=dataset,
                        symbol=symbol,
                        attempt_no=attempts,
                    ),
                )
            )
            return FetchResult(
                dataset=dataset,
                success=True,
                frame=frame,
                error_message=None,
                attempts=attempts,
                error_type=None,
            )
        except Exception as exc:  # pragma: no cover - runtime API/network path
            last_error = exc
            last_error_type = classify_fetch_error(exc)
            ended_at = utc_now()
            response_missing = response_missing_for_attempt(
                fetch_debug_logs,
                request_batch_id=request_batch_id,
                dataset=dataset,
                symbol=symbol,
                attempt_no=attempts,
            )
            fetch_attempt_logs.append(
                build_fetch_attempt_row(
                    request_batch_id=request_batch_id,
                    symbol=symbol,
                    dataset=dataset,
                    attempt_no=attempts,
                    max_attempts=max_attempts,
                    started_at=started_at,
                    ended_at=ended_at,
                    success=False,
                    soft_failure=soft_failure,
                    error_type=last_error_type,
                    error_message=str(exc),
                    response_missing=response_missing,
                )
            )
            print("[WARN] dataset=%s symbol=%s attempt=%s/%s error_type=%s error=%s" % (
                dataset,
                symbol,
                attempts,
                max_attempts,
                last_error_type,
                exc,
            ))
            print_remote_disconnect_hint(last_error_type, response_missing)
            if attempts < max_attempts:
                sleep_with_jitter(delay)

    error_message = "%s" % last_error if last_error is not None else "未知错误"
    if soft_failure:
        return FetchResult(
            dataset=dataset,
            success=False,
            frame=None,
            error_message=error_message,
            attempts=attempts,
            error_type=last_error_type or "UNKNOWN_FETCH_ERROR",
        )
    raise FetchFailure(
        dataset=dataset,
        symbol=symbol,
        error_message=error_message,
        attempts=attempts,
        error_type=last_error_type or "UNKNOWN_FETCH_ERROR",
    )


def compute_simple_moving_average(series, period: int):
    return series.rolling(window=period, min_periods=1).mean()


def compute_kdj(high_series, low_series, close_series, period: int = 9):
    k_values = []
    d_values = []
    j_values = []
    k = 50.0
    d = 50.0
    highs = high_series.tolist()
    lows = low_series.tolist()
    closes = close_series.tolist()
    for idx in range(len(closes)):
        start = max(0, idx - period + 1)
        highest = max(highs[start : idx + 1])
        lowest = min(lows[start : idx + 1])
        rsv = 50.0 if highest == lowest else (closes[idx] - lowest) / (highest - lowest) * 100.0
        k = (2.0 / 3.0) * k + (1.0 / 3.0) * rsv
        d = (2.0 / 3.0) * d + (1.0 / 3.0) * k
        j = 3.0 * k - 2.0 * d
        k_values.append(k)
        d_values.append(d)
        j_values.append(j)
    return k_values, d_values, j_values


def compute_macd(close_series, short_period: int = 12, long_period: int = 26, signal_period: int = 9):
    closes = close_series.tolist()
    ema_short = closes[0]
    ema_long = closes[0]
    dea = 0.0
    short_factor = 2.0 / (short_period + 1.0)
    long_factor = 2.0 / (long_period + 1.0)
    signal_factor = 2.0 / (signal_period + 1.0)

    dif_values = []
    dea_values = []
    macd_values = []
    for close in closes:
        ema_short = close * short_factor + ema_short * (1.0 - short_factor)
        ema_long = close * long_factor + ema_long * (1.0 - long_factor)
        dif = ema_short - ema_long
        dea = dif * signal_factor + dea * (1.0 - signal_factor)
        macd = (dif - dea) * 2.0
        dif_values.append(dif)
        dea_values.append(dea)
        macd_values.append(macd)
    return dif_values, dea_values, macd_values


def build_features(raw_df, qfq_df, share_df=None):
    pd = lazy_import_pandas()
    if raw_df.empty or qfq_df.empty:
        raise BootstrapError("raw 或 qfq 数据为空，无法构建特征")

    merged = raw_df[["code", "trade_date", "close_price", "turnover_rate"]].rename(
        columns={"close_price": "raw_close"}
    ).merge(
        qfq_df[["code", "trade_date", "open_price", "high_price", "low_price", "close_price", "volume"]],
        on=["code", "trade_date"],
        how="inner",
    )
    merged = merged.rename(
        columns={
            "open_price": "qfq_open",
            "high_price": "qfq_high",
            "low_price": "qfq_low",
            "close_price": "qfq_close",
        }
    )
    merged = merged.sort_values("trade_date").reset_index(drop=True)

    merged["ma5"] = compute_simple_moving_average(merged["qfq_close"], 5)
    merged["ma10"] = compute_simple_moving_average(merged["qfq_close"], 10)
    merged["ma20"] = compute_simple_moving_average(merged["qfq_close"], 20)

    k_values, d_values, j_values = compute_kdj(merged["qfq_high"], merged["qfq_low"], merged["qfq_close"], 9)
    dif_values, dea_values, macd_values = compute_macd(merged["qfq_close"], 12, 26, 9)
    merged["k_value"] = k_values
    merged["d_value"] = d_values
    merged["j_value"] = j_values
    merged["dif"] = dif_values
    merged["dea"] = dea_values
    merged["macd"] = macd_values
    merged["outstanding_share_est"] = merged.apply(
        lambda row: (row["volume"] * 10000.0 / row["turnover_rate"])
        if pd.notna(row["turnover_rate"]) and float(row["turnover_rate"]) > 0
        else pd.NA,
        axis=1,
    )
    merged["outstanding_share"] = merged["outstanding_share_est"]
    merged["float_mv_est"] = merged["raw_close"] * merged["outstanding_share_est"]
    merged["cap_bucket"] = "mid"
    merged["source_batch_id"] = raw_df["source_batch_id"].iloc[0]
    merged["feature_version"] = FEATURE_VERSION

    feature_df = merged[[
        "code",
        "trade_date",
        "source_batch_id",
        "qfq_open",
        "qfq_high",
        "qfq_low",
        "qfq_close",
        "volume",
        "ma5",
        "ma10",
        "ma20",
        "k_value",
        "d_value",
        "j_value",
        "dif",
        "dea",
        "macd",
        "turnover_rate",
        "outstanding_share_est",
        "outstanding_share",
        "float_mv_est",
        "cap_bucket",
        "feature_version",
    ]].copy()

    numeric_columns = [
        "qfq_open",
        "qfq_high",
        "qfq_low",
        "qfq_close",
        "volume",
        "ma5",
        "ma10",
        "ma20",
        "k_value",
        "d_value",
        "j_value",
        "dif",
        "dea",
        "macd",
        "turnover_rate",
        "outstanding_share_est",
        "outstanding_share",
        "float_mv_est",
    ]
    for column in numeric_columns:
        feature_df[column] = pd.to_numeric(feature_df[column], errors="coerce")
    return feature_df


def normalize_index_hist_frame(raw_frame, index_code: str, index_name: str, request_batch_id: str):
    pd = lazy_import_pandas()
    if raw_frame is None or raw_frame.empty:
        raise BootstrapError("%s index 返回空数据" % index_code)

    frame = raw_frame.copy()
    rename_map = {
        "日期": "trade_date",
        "date": "trade_date",
        "开盘": "open_price",
        "open": "open_price",
        "收盘": "close_price",
        "close": "close_price",
        "最高": "high_price",
        "high": "high_price",
        "最低": "low_price",
        "low": "low_price",
        "成交量": "volume",
        "volume": "volume",
        "成交额": "amount",
        "amount": "amount",
    }
    frame = frame.rename(columns=rename_map)
    ensure_required_columns(
        frame,
        ["trade_date", "open_price", "high_price", "low_price", "close_price", "volume"],
        "%s index" % index_code,
    )
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    frame["index_code"] = index_code
    frame["index_name"] = index_name
    frame["source_batch_id"] = request_batch_id
    frame["source"] = SOURCE
    frame["open_price"] = to_numeric_series(pd, frame, "open_price", 0.0)
    frame["high_price"] = to_numeric_series(pd, frame, "high_price", 0.0)
    frame["low_price"] = to_numeric_series(pd, frame, "low_price", 0.0)
    frame["close_price"] = to_numeric_series(pd, frame, "close_price", 0.0)
    frame["volume"] = to_numeric_series(pd, frame, "volume", 0.0).fillna(0.0)
    frame["amount"] = to_numeric_series(pd, frame, "amount", 0.0).fillna(0.0)
    frame = frame.sort_values("trade_date").drop_duplicates(subset=["trade_date"], keep="last")
    return frame[[
        "index_code",
        "index_name",
        "trade_date",
        "source_batch_id",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "amount",
        "source",
    ]]


def build_index_features(index_raw_df):
    pd = lazy_import_pandas()
    if index_raw_df.empty:
        return empty_index_feature_df()
    rows = []
    for index_code, frame in index_raw_df.groupby("index_code"):
        local = frame.sort_values("trade_date").reset_index(drop=True).copy()
        local["pct_change_1d"] = local["close_price"].pct_change()
        rolling_max_5d = local["close_price"].rolling(window=5, min_periods=1).max()
        local["drawdown_5d"] = (local["close_price"] / rolling_max_5d) - 1.0
        prev_avg_vol = local["volume"].shift(1).rolling(window=5, min_periods=1).mean()
        local["vol_ratio_1d_5d"] = local["volume"] / prev_avg_vol.replace({0: pd.NA})
        local["panic_flag"] = (
            (local["pct_change_1d"] <= -0.04)
            | ((local["drawdown_5d"] <= -0.10) & (local["vol_ratio_1d_5d"] >= 1.30))
        ).astype(int)
        for _, row in local.iterrows():
            rows.append(
                {
                    "index_code": index_code,
                    "index_name": row["index_name"],
                    "trade_date": row["trade_date"],
                    "source_batch_id": row["source_batch_id"],
                    "pct_change_1d": row["pct_change_1d"],
                    "drawdown_5d": row["drawdown_5d"],
                    "vol_ratio_1d_5d": row["vol_ratio_1d_5d"],
                    "panic_flag": int(row["panic_flag"]),
                }
            )
    feature_df = pd.DataFrame(rows) if rows else empty_index_feature_df()
    if not feature_df.empty:
        for column in ["pct_change_1d", "drawdown_5d", "vol_ratio_1d_5d"]:
            feature_df[column] = pd.to_numeric(feature_df[column], errors="coerce")
    return feature_df


def assign_cap_bucket(all_feature_df):
    pd = lazy_import_pandas()
    if all_feature_df.empty:
        return all_feature_df

    feature_df = all_feature_df.copy()
    feature_df["cap_bucket"] = "mid"
    for trade_date, index in feature_df.groupby("trade_date").groups.items():
        group = feature_df.loc[index, "float_mv_est"].dropna()
        if len(group) < 3 or group.nunique() < 3:
            continue
        q33 = group.quantile(0.33)
        q66 = group.quantile(0.66)
        feature_df.loc[index, "cap_bucket"] = feature_df.loc[index, "float_mv_est"].apply(
            lambda value: "small"
            if pd.notna(value) and value <= q33
            else ("large" if pd.notna(value) and value >= q66 else "mid")
        )
    return feature_df


def build_stock_basic_rows(raw_frames: Sequence) -> "object":
    pd = lazy_import_pandas()
    rows = []
    for raw_df in raw_frames:
        if raw_df.empty:
            continue
        code = raw_df["code"].iloc[0]
        stock_name = raw_df["stock_name"].iloc[0] if "stock_name" in raw_df.columns else code
        digits, exchange = code.split(".")
        rows.append(
            {
                "code": code,
                "stock_name": stock_name or code,
                "exchange": exchange,
                "market": "A_SHARE",
                "board": infer_board(digits, exchange),
                "list_date": None,
                "delist_date": None,
                "industry": None,
                "status": "LISTED",
            }
        )
    if not rows:
        return pd.DataFrame(columns=["code", "stock_name", "exchange", "market", "board", "list_date", "delist_date", "industry", "status"])
    return pd.DataFrame(rows).drop_duplicates(subset=["code"], keep="last")


def make_staging_record(symbol: str, dataset: str, request_batch_id: str, payload_frame) -> Dict[str, object]:
    payload_json = payload_frame.to_json(orient="records", force_ascii=False, date_format="iso")
    checksum = hashlib.md5(payload_json.encode("utf-8")).hexdigest()
    return {
        "source": SOURCE,
        "dataset": dataset,
        "biz_key": canonical_code(symbol),
        "request_batch_id": request_batch_id,
        "payload_json": payload_json,
        "checksum": checksum,
        "status": "FETCHED",
        "fetched_at": format_csv_datetime(utc_now()),
    }


def build_quality_check_row(dataset: str, biz_key: str, check_type: str, severity: str, status: str, actual_value: str, expected_rule: str, message: str) -> Dict[str, object]:
    return {
        "job_id": None,
        "dataset": dataset,
        "biz_key": biz_key,
        "check_type": check_type,
        "severity": severity,
        "status": status,
        "actual_value": actual_value,
        "expected_rule": expected_rule,
        "message": message,
        "checked_at": format_csv_datetime(utc_now()),
    }


def make_fetch_failure_check(symbol: str, dataset: str, error_message: str) -> Dict[str, object]:
    check_type_map = {
        "stock_zh_a_hist_raw": "fetch_raw_failed",
        "stock_zh_a_hist_qfq": "fetch_qfq_failed",
    }
    return build_quality_check_row(
        dataset=dataset,
        biz_key=canonical_code(symbol),
        check_type=check_type_map.get(dataset, "fetch_failed"),
        severity="ERROR",
        status="FAILED",
        actual_value="1",
        expected_rule="fetch_success=1",
        message=error_message,
    )


def make_quality_checks(config: Config, raw_df, feature_df) -> "object":
    pd = lazy_import_pandas()
    checks = []
    code = raw_df["code"].iloc[0]
    now = format_csv_datetime(utc_now())

    duplicate_count = int(raw_df.duplicated(subset=["trade_date"]).sum())
    checks.append(
        {
            "job_id": None,
            "dataset": "stock_daily_raw",
            "biz_key": code,
            "check_type": "duplicate_trade_date",
            "severity": "WARN" if duplicate_count else "INFO",
            "status": "FAILED" if duplicate_count else "PASSED",
            "actual_value": str(duplicate_count),
            "expected_rule": "duplicate_trade_date=0",
            "message": "raw 层交易日重复检查",
            "checked_at": now,
        }
    )

    invalid_ohlc = int(
        ((raw_df["high_price"] < raw_df[["open_price", "close_price"]].max(axis=1))
        | (raw_df["low_price"] > raw_df[["open_price", "close_price"]].min(axis=1))
        | (raw_df["high_price"] < raw_df["low_price"])).sum()
    )
    checks.append(
        {
            "job_id": None,
            "dataset": "stock_daily_raw",
            "biz_key": code,
            "check_type": "ohlc_validity",
            "severity": "WARN" if invalid_ohlc else "INFO",
            "status": "FAILED" if invalid_ohlc else "PASSED",
            "actual_value": str(invalid_ohlc),
            "expected_rule": "invalid_ohlc=0",
            "message": "OHLC 合法性检查",
            "checked_at": now,
        }
    )

    missing_share = int(feature_df["outstanding_share_est"].isna().sum()) if "outstanding_share_est" in feature_df.columns else 0
    checks.append(
        {
            "job_id": None,
            "dataset": "stock_daily_feature",
            "biz_key": code,
            "check_type": "missing_outstanding_share_est",
            "severity": "WARN" if missing_share else "INFO",
            "status": "FAILED" if missing_share else "PASSED",
            "actual_value": str(missing_share),
            "expected_rule": "missing_outstanding_share_est=0",
            "message": "估算流通股本缺失检查",
            "checked_at": now,
        }
    )

    missing_turnover_rate = int(raw_df["turnover_rate"].isna().sum()) if "turnover_rate" in raw_df.columns else 0
    checks.append(
        {
            "job_id": None,
            "dataset": "stock_daily_raw",
            "biz_key": code,
            "check_type": "missing_turnover_rate",
            "severity": "WARN" if missing_turnover_rate else "INFO",
            "status": "FAILED" if missing_turnover_rate else "PASSED",
            "actual_value": str(missing_turnover_rate),
            "expected_rule": "missing_turnover_rate=0",
            "message": "换手率缺失检查",
            "checked_at": now,
        }
    )

    return pd.DataFrame(checks)


def build_job_log(
    config: Config,
    success_count: int,
    fail_count: int,
    partial_fail_count: int,
    retry_count: int,
    error_message: Optional[str],
    start_time: datetime,
    end_time: datetime,
):
    pd = lazy_import_pandas()
    status = "SUCCESS"
    if fail_count > 0:
        status = "PARTIAL_SUCCESS" if success_count > 0 else "FAILED"
    elif partial_fail_count > 0:
        status = "PARTIAL_SUCCESS"
    return pd.DataFrame(
        [
            {
                "job_type": "BOOTSTRAP",
                "job_name": "akshare_bootstrap",
                "batch_date": datetime.strptime(config.batch_date, "%Y-%m-%d").date(),
                "request_batch_id": config.request_batch_id,
                "start_time": format_csv_datetime(start_time),
                "end_time": format_csv_datetime(end_time),
                "status": status,
                "success_count": success_count,
                "fail_count": fail_count + partial_fail_count,
                "retry_count": retry_count,
                "error_message": error_message,
            }
        ]
    )


def round_dataframe(frame, columns: Sequence[str], digits: int = 4):
    for column in columns:
        if column in frame.columns:
            frame[column] = frame[column].round(digits)
    return frame


def chunked_records(frame, chunk_size: int = 500) -> Iterable[List[Dict[str, object]]]:
    records = frame.to_dict(orient="records")
    for start in range(0, len(records), chunk_size):
        yield records[start : start + chunk_size]


def upsert_dataframe(engine, table_name: str, frame, update_columns: Sequence[str]) -> None:
    if frame.empty:
        return
    _, text = lazy_import_sqlalchemy()
    columns = list(frame.columns)
    insert_columns = ", ".join("`%s`" % column for column in columns)
    values_clause = ", ".join(":%s" % column for column in columns)
    update_clause = ", ".join("`{0}`=VALUES(`{0}`)".format(column) for column in update_columns)
    sql = text(
        "INSERT INTO `{table}` ({columns}) VALUES ({values}) ON DUPLICATE KEY UPDATE {updates}".format(
            table=table_name,
            columns=insert_columns,
            values=values_clause,
            updates=update_clause,
        )
    )
    with engine.begin() as connection:
        for records in chunked_records(frame):
            connection.execute(sql, records)


def append_dataframe(engine, table_name: str, frame) -> None:
    if frame.empty:
        return
    frame.to_sql(table_name, con=engine, if_exists="append", index=False)


def persist(
    config: Config,
    stock_basic_df,
    stock_basic_snapshot_log_df,
    trading_calendar_df,
    raw_df,
    feature_df,
    index_raw_df,
    index_feature_df,
    staging_df,
    job_log_df,
    quality_df,
    fetch_attempt_df,
    symbol_run_df,
    index_fetch_log_df,
    fetch_debug_logs: Sequence[Dict[str, object]],
):
    output_dir = Path(config.output_dir) / config.request_batch_id
    output_dir.mkdir(parents=True, exist_ok=True)

    stock_basic_df.to_csv(output_dir / "stock_basic.csv", index=False)
    stock_basic_snapshot_log_df.to_csv(output_dir / "stock_basic_snapshot_log.csv", index=False)
    trading_calendar_df.to_csv(output_dir / "trading_calendar.csv", index=False)
    raw_df.to_csv(output_dir / "stock_daily_raw.csv", index=False)
    feature_df.to_csv(output_dir / "stock_daily_feature.csv", index=False)
    index_raw_df.to_csv(output_dir / "index_daily_raw.csv", index=False)
    index_feature_df.to_csv(output_dir / "index_daily_feature.csv", index=False)
    staging_df.to_csv(output_dir / "staging_raw.csv", index=False)
    job_log_df.to_csv(output_dir / "job_run_log.csv", index=False)
    quality_df.to_csv(output_dir / "data_quality_check.csv", index=False)
    fetch_attempt_df.to_csv(output_dir / "fetch_attempt_log.csv", index=False)
    symbol_run_df.to_csv(output_dir / "symbol_run_log.csv", index=False)
    index_fetch_log_df.to_csv(output_dir / "index_fetch_log.csv", index=False)
    if config.fetch_debug:
        write_fetch_debug_jsonl(output_dir, fetch_debug_logs)

    print("CSV 输出目录: %s" % output_dir)

    if not config.mysql_dsn:
        return

    create_engine, _ = lazy_import_sqlalchemy()
    engine = create_engine(config.mysql_dsn)

    upsert_dataframe(
        engine,
        "stock_basic",
        stock_basic_df[["code", "stock_name", "exchange", "market", "board", "list_date", "delist_date", "industry", "status"]],
        ["stock_name", "exchange", "market", "board", "list_date", "delist_date", "industry", "status"],
    )
    upsert_dataframe(
        engine,
        "stock_daily_raw",
        raw_df[["code", "trade_date", "source_batch_id", "open_price", "high_price", "low_price", "close_price", "volume", "amount", "source"]],
        ["source_batch_id", "open_price", "high_price", "low_price", "close_price", "volume", "amount", "source"],
    )
    upsert_dataframe(
        engine,
        "stock_daily_feature",
        feature_df[[
            "code",
            "trade_date",
            "source_batch_id",
            "qfq_open",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "volume",
            "ma5",
            "ma10",
            "ma20",
            "k_value",
            "d_value",
            "j_value",
            "dif",
            "dea",
            "macd",
            "outstanding_share",
            "float_mv_est",
            "cap_bucket",
            "feature_version",
        ]],
        [
            "source_batch_id",
            "qfq_open",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "volume",
            "ma5",
            "ma10",
            "ma20",
            "k_value",
            "d_value",
            "j_value",
            "dif",
            "dea",
            "macd",
            "outstanding_share",
            "float_mv_est",
            "cap_bucket",
            "feature_version",
        ],
    )
    append_dataframe(engine, "staging_raw", staging_df)
    append_dataframe(engine, "job_run_log", job_log_df)
    append_dataframe(engine, "data_quality_check", quality_df)
    print("已写入 MySQL: %s" % config.mysql_dsn)


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="AKShare bootstrap minimal runner")
    parser.add_argument("--symbols", nargs="+", required=True, help="股票代码，例如 600519 或 300750.SZ")
    parser.add_argument("--start-date", required=True, help="开始日期，格式 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="结束日期，格式 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--mysql-dsn", required=False, help="可选，MySQL DSN，例如 mysql+pymysql://user:pass@host:3306/db")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="CSV 输出目录，默认 output/akshare_bootstrap")
    parser.add_argument("--request-batch-id", default=None, help="可选，批次号；不传则自动生成")
    parser.add_argument("--fetch-debug", action="store_true", help="开启抓取请求/响应级诊断日志，并输出 fetch_debug_log.jsonl")
    parser.add_argument(
        "--fetch-debug-body-max-chars",
        type=int,
        default=DEFAULT_FETCH_DEBUG_BODY_MAX_CHARS,
        help="调试时响应体预览的最大字符数，默认 %s" % DEFAULT_FETCH_DEBUG_BODY_MAX_CHARS,
    )
    args = parser.parse_args()

    request_batch_id = args.request_batch_id or ("bootstrap-" + uuid.uuid4().hex[:12])
    return Config(
        symbols=args.symbols,
        start_date=to_date_text(args.start_date),
        end_date=to_date_text(args.end_date),
        mysql_dsn=args.mysql_dsn or os.getenv("SHARE_MYSQL_DSN"),
        output_dir=args.output_dir,
        request_batch_id=request_batch_id,
        batch_date=date.today().isoformat(),
        fetch_debug=args.fetch_debug,
        fetch_debug_body_max_chars=max(int(args.fetch_debug_body_max_chars or DEFAULT_FETCH_DEBUG_BODY_MAX_CHARS), 0),
    )


def main() -> None:
    config = parse_args()
    pd = lazy_import_pandas()
    job_start_time = utc_now()
    http_debug_settings = HttpDebugSettings(
        enabled=config.fetch_debug,
        body_max_chars=config.fetch_debug_body_max_chars,
        timeout_seconds=DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
    fetch_debug_logs = empty_fetch_debug_logs()

    static_stock_basic_df, stock_basic_snapshot_log_df = execute_with_http_debug(
        fetch_stock_basic_snapshot,
        request_batch_id=config.request_batch_id,
        dataset="stock_basic_snapshot",
        symbol="GLOBAL",
        attempt_no=1,
        max_attempts=1,
        debug_settings=http_debug_settings,
        fetch_debug_logs=fetch_debug_logs,
    )
    stock_basic_df = filter_stock_basic_for_symbols(static_stock_basic_df, config.symbols)
    try:
        trading_calendar_df = execute_with_http_debug(
            lambda: fetch_trading_calendar(config.start_date, config.end_date),
            request_batch_id=config.request_batch_id,
            dataset="tool_trade_date_hist_sina",
            symbol="GLOBAL",
            attempt_no=1,
            max_attempts=1,
            debug_settings=http_debug_settings,
            fetch_debug_logs=fetch_debug_logs,
        )
    except Exception as exc:  # pragma: no cover - runtime API/network path
        trading_calendar_df = empty_trading_calendar_df()
        stock_basic_snapshot_log_df = pd.concat(
            [
                stock_basic_snapshot_log_df,
                pd.DataFrame(
                    [
                        {
                            "source_name": "tool_trade_date_hist_sina",
                            "status": "FAILED",
                            "row_count": 0,
                            "error_message": str(exc),
                            "fetched_at": format_csv_datetime(utc_now()),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    raw_frames = []
    feature_frames = []
    staging_records = []
    quality_frames = []
    index_raw_frames = []
    index_fetch_logs = []
    success_count = 0
    fail_count = 0
    partial_fail_count = 0
    retry_count = 0
    errors = []
    fetch_attempt_logs = []
    symbol_run_records = []

    for index, symbol in enumerate(config.symbols):
        print("bootstrap %s from %s to %s" % (symbol, config.start_date, config.end_date))
        symbol_run = new_symbol_run_record(config.request_batch_id, symbol)
        symbol_run["share_status"] = "NOT_USED"
        try:
            raw_result = fetch_with_retry(
                dataset="stock_zh_a_hist_raw",
                symbol=symbol,
                fetch_func=lambda: fetch_raw_history(symbol, config.start_date, config.end_date),
                request_batch_id=config.request_batch_id,
                fetch_attempt_logs=fetch_attempt_logs,
                fetch_debug_logs=fetch_debug_logs,
                http_debug_settings=http_debug_settings,
                soft_failure=False,
            )
            retry_count += max(raw_result.attempts - 1, 0)
            symbol_run["retry_count"] += max(raw_result.attempts - 1, 0)
            symbol_run["raw_status"] = "SUCCESS"
            time.sleep(SYMBOL_PAUSE_SECONDS)
            qfq_result = fetch_with_retry(
                dataset="stock_zh_a_hist_qfq",
                symbol=symbol,
                fetch_func=lambda: fetch_qfq_history(symbol, config.start_date, config.end_date),
                request_batch_id=config.request_batch_id,
                fetch_attempt_logs=fetch_attempt_logs,
                fetch_debug_logs=fetch_debug_logs,
                http_debug_settings=http_debug_settings,
                soft_failure=False,
            )
            retry_count += max(qfq_result.attempts - 1, 0)
            symbol_run["retry_count"] += max(qfq_result.attempts - 1, 0)
            symbol_run["qfq_status"] = "SUCCESS"

            raw_history = raw_result.frame
            qfq_history = qfq_result.frame

            raw_df = normalize_hist_frame(raw_history, symbol, config.request_batch_id, "raw")
            qfq_df = normalize_hist_frame(qfq_history, symbol, config.request_batch_id, "qfq")
            feature_df = build_features(raw_df, qfq_df)

            raw_frames.append(raw_df)
            feature_frames.append(feature_df)
            quality_frames.append(make_quality_checks(config, raw_df, feature_df))
            staging_records.append(make_staging_record(symbol, "stock_zh_a_hist_raw", config.request_batch_id, raw_history))
            staging_records.append(make_staging_record(symbol, "stock_zh_a_hist_qfq", config.request_batch_id, qfq_history))
            if symbol_run["final_status"] == "PENDING":
                symbol_run["final_status"] = "SUCCESS"
            success_count += 1
        except Exception as exc:  # pragma: no cover - runtime API/network path
            fail_count += 1
            if isinstance(exc, FetchFailure):
                retry_count += max(exc.attempts - 1, 0)
                symbol_run["retry_count"] += max(exc.attempts - 1, 0)
            message = "%s: %s" % (symbol, exc)
            errors.append(message)
            print("[ERROR] %s" % message)
            lowered = message.lower()
            if isinstance(exc, FetchFailure):
                dataset = exc.dataset
            elif "stock_zh_a_hist_qfq" in lowered:
                dataset = "stock_zh_a_hist_qfq"
            elif "stock_zh_a_hist_raw" in lowered:
                dataset = "stock_zh_a_hist_raw"
            else:
                dataset = "stock_zh_a_hist_raw"
            error_type = classify_fetch_error(exc)
            if dataset == "stock_zh_a_hist_raw":
                symbol_run["raw_status"] = "FAILED"
                symbol_run["raw_error_type"] = error_type
                if symbol_run["qfq_status"] == "PENDING":
                    symbol_run["qfq_status"] = "SKIPPED"
            elif dataset == "stock_zh_a_hist_qfq":
                if symbol_run["raw_status"] == "PENDING":
                    symbol_run["raw_status"] = "SUCCESS"
                symbol_run["qfq_status"] = "FAILED"
                symbol_run["qfq_error_type"] = error_type
            symbol_run["final_status"] = "FAILED"
            symbol_run["error_message"] = str(exc)
            quality_frames.append(pd.DataFrame([make_fetch_failure_check(symbol, dataset, str(exc))]))
        finally:
            if symbol_run["final_status"] == "PENDING":
                symbol_run["final_status"] = "FAILED"
            if symbol_run["qfq_status"] == "PENDING":
                symbol_run["qfq_status"] = "SKIPPED" if symbol_run["final_status"] == "FAILED" else "SUCCESS"
            symbol_run_records.append(symbol_run)

        if index < len(config.symbols) - 1:
            time.sleep(SYMBOL_PAUSE_SECONDS)
        if (index + 1) % SYMBOL_CHUNK_SIZE == 0 and index < len(config.symbols) - 1:
            print("[PAUSE] chunk completed=%s sleep=%ss" % (index + 1, CHUNK_PAUSE_SECONDS))
            time.sleep(CHUNK_PAUSE_SECONDS)

    for index_code, index_name in INDEX_SYMBOLS:
        frame, index_log = fetch_index_history_with_retry(
            index_code=index_code,
            index_name=index_name,
            start_date=config.start_date,
            end_date=config.end_date,
            request_batch_id=config.request_batch_id,
            fetch_attempt_logs=fetch_attempt_logs,
            fetch_debug_logs=fetch_debug_logs,
            http_debug_settings=http_debug_settings,
        )
        index_fetch_logs.append(index_log)
        if frame is not None and not frame.empty:
            try:
                index_raw_frames.append(normalize_index_hist_frame(frame, index_code, index_name, config.request_batch_id))
            except Exception as exc:  # pragma: no cover - runtime API/network path
                index_fetch_logs[-1]["status"] = "FAILED"
                index_fetch_logs[-1]["error_type"] = classify_fetch_error(exc)
                index_fetch_logs[-1]["error_message"] = str(exc)

    if raw_frames and feature_frames:
        raw_all = pd.concat(raw_frames, ignore_index=True)
        feature_all = pd.concat(feature_frames, ignore_index=True)
        feature_all = assign_cap_bucket(feature_all)
    else:
        raw_all = empty_raw_df()
        feature_all = empty_feature_df()

    if index_raw_frames:
        index_raw_all = pd.concat(index_raw_frames, ignore_index=True)
        index_feature_all = build_index_features(index_raw_all)
    else:
        index_raw_all = empty_index_raw_df()
        index_feature_all = empty_index_feature_df()

    raw_all = round_dataframe(raw_all, ["open_price", "high_price", "low_price", "close_price", "volume", "amount", "turnover_rate"])
    feature_all = round_dataframe(
        feature_all,
        [
            "qfq_open",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "volume",
            "ma5",
            "ma10",
            "ma20",
            "k_value",
            "d_value",
            "j_value",
            "dif",
            "dea",
            "macd",
            "turnover_rate",
            "outstanding_share_est",
            "outstanding_share",
            "float_mv_est",
        ],
    )
    index_raw_all = round_dataframe(index_raw_all, ["open_price", "high_price", "low_price", "close_price", "volume", "amount"])
    index_feature_all = round_dataframe(index_feature_all, ["pct_change_1d", "drawdown_5d", "vol_ratio_1d_5d"])

    staging_df = pd.DataFrame(staging_records) if staging_records else empty_staging_df()
    quality_df = pd.concat(quality_frames, ignore_index=True) if quality_frames else empty_quality_df()
    fetch_attempt_df = pd.DataFrame(fetch_attempt_logs) if fetch_attempt_logs else empty_fetch_attempt_log_df()
    symbol_run_df = pd.DataFrame(symbol_run_records) if symbol_run_records else empty_symbol_run_log_df()
    index_fetch_log_df = pd.DataFrame(index_fetch_logs) if index_fetch_logs else empty_index_fetch_log_df()
    print_batch_level_connection_hint(fetch_attempt_logs)
    job_end_time = utc_now()
    job_log_df = build_job_log(
        config,
        success_count,
        fail_count,
        partial_fail_count,
        retry_count,
        "; ".join(errors) if errors else None,
        job_start_time,
        job_end_time,
    )

    persist(
        config,
        stock_basic_df,
        stock_basic_snapshot_log_df,
        trading_calendar_df,
        raw_all,
        feature_all,
        index_raw_all,
        index_feature_all,
        staging_df,
        job_log_df,
        quality_df,
        fetch_attempt_df,
        symbol_run_df,
        index_fetch_log_df,
        fetch_debug_logs,
    )
    print(
        "完成: success=%s fail=%s partial=%s retries=%s batch=%s logs=%s"
        % (success_count, fail_count, partial_fail_count, retry_count, config.request_batch_id, Path(config.output_dir) / config.request_batch_id)
    )

    if not raw_frames or not feature_frames:
        raise BootstrapError("所有 symbol 执行失败: %s" % ("; ".join(errors) if errors else "未知错误"))


if __name__ == "__main__":
    main()
