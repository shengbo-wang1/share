#!/usr/bin/env python3
"""Challenge candidate generator（最小可运行版）。

用途：
1. 读取 stock_basic / stock_daily_raw / stock_daily_feature / 可选 index_daily_feature
2. 扫描 20 日主窗口 + 3 日验证窗口
3. 按既有阈值规则生成 candidate.csv
4. 输出人工审核所需字段：primary_tag / secondary_tag / difficulty / explain / flags

依赖（自行安装）：
    pip install pandas
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


WINDOW_DAYS = 20
VERIFY_DAYS = 3
DEFAULT_BOOTSTRAP_OUTPUT_DIR = "output/akshare_bootstrap"
DEFAULT_OUTPUT_DIR = "output/challenge_generator"
EPS = 1e-8
RECENT_LISTING_MIN_DAYS = 60

TAG_PANIC = "大盘恐慌日该不该抄底"
TAG_BREAKOUT = "放量突破 vs 假突破"
TAG_HIGHVOLBEAR = "高位放量阴线"
TAG_TAKEPROFIT = "连续上涨后该持有还是止盈"
TAG_BOTTOM = "下跌中继 vs 真见底"
TAG_PULLBACK = "缩量回踩均线"

TAG_PRIORITY_ORDER = [
    TAG_PANIC,
    TAG_BREAKOUT,
    TAG_HIGHVOLBEAR,
    TAG_TAKEPROFIT,
    TAG_BOTTOM,
    TAG_PULLBACK,
]

EXPLANATORY_SECONDARY = {
    (TAG_BOTTOM, TAG_PULLBACK),
    (TAG_BREAKOUT, TAG_TAKEPROFIT),
    (TAG_HIGHVOLBEAR, TAG_TAKEPROFIT),
}

INDEX_ALIAS = {
    "SH": ["000001.SH", "SH000001", "000001", "上证指数"],
    "SZ": ["399001.SZ", "SZ399001", "399001", "深证成指"],
    "GEM": ["399006.SZ", "SZ399006", "399006", "创业板指"],
}


@dataclass
class Config:
    generation_batch_id: str
    output_dir: str
    bootstrap_output_dir: str
    stock_basic_csv: Optional[str]
    raw_csv: Optional[str]
    feature_csv: Optional[str]
    index_feature_csv: Optional[str]
    calendar_csv: Optional[str]
    trade_date_from: Optional[str]
    trade_date_to: Optional[str]
    allow_empty: bool = False


class GeneratorError(RuntimeError):
    """Raised when the generator cannot continue."""


class GeneratorInputError(GeneratorError):
    """Raised when required generator inputs are missing or invalid."""

    def __init__(self, message: str, issues: List[Dict[str, object]]):
        self.issues = issues
        super().__init__(message)


class DataBundle:
    def __init__(self, stock_basic, raw_df, feature_df, index_feature_df, calendar_df):
        self.stock_basic = stock_basic
        self.raw_df = raw_df
        self.feature_df = feature_df
        self.index_feature_df = index_feature_df
        self.calendar_df = calendar_df


REQUIRED_COLUMNS = {
    "stock_basic": ["code"],
    "raw": ["code", "trade_date", "open_price", "high_price", "low_price", "close_price", "volume"],
    "feature": ["code", "trade_date", "qfq_open", "qfq_high", "qfq_low", "qfq_close", "volume", "ma5", "ma10", "ma20", "k_value", "d_value", "j_value", "dif", "dea", "macd", "cap_bucket"],
    "index_feature": ["index_code", "trade_date", "panic_flag"],
    "calendar": ["exchange", "trade_date", "is_open"],
}


def output_root_dir(output_dir: str) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def lazy_import_pandas():
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise GeneratorError("缺少 pandas，请先执行: pip install pandas") from exc
    return pd


def normalize_date_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = value.replace("-", "")
    if len(raw) != 8 or not raw.isdigit():
        raise GeneratorError("日期格式必须为 YYYY-MM-DD 或 YYYYMMDD: %s" % value)
    return "%s-%s-%s" % (raw[0:4], raw[4:6], raw[6:8])


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Challenge generator minimal runner")
    parser.add_argument("--generation-batch-id", default=None, help="可选，不传则自动生成")
    parser.add_argument("--bootstrap-output-dir", default=DEFAULT_BOOTSTRAP_OUTPUT_DIR, help="bootstrap 输出根目录")
    parser.add_argument("--stock-basic-csv", default=None, help="stock_basic.csv 路径")
    parser.add_argument("--raw-csv", default=None, help="stock_daily_raw.csv 路径")
    parser.add_argument("--feature-csv", default=None, help="stock_daily_feature.csv 路径")
    parser.add_argument("--index-feature-csv", default=None, help="可选，index_daily_feature.csv 路径")
    parser.add_argument("--calendar-csv", default=None, help="可选，trading_calendar.csv 路径")
    parser.add_argument("--trade-date-from", default=None, help="可选，限制 start_date 起点")
    parser.add_argument("--trade-date-to", default=None, help="可选，限制 start_date 终点")
    parser.add_argument("--allow-empty", action="store_true", help="允许 0 candidate 场景返回 0 退出码；仍会写出 EMPTY run log")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="candidate 输出目录")
    args = parser.parse_args()

    batch_id = args.generation_batch_id or ("generator-" + uuid.uuid4().hex[:12])
    return Config(
        generation_batch_id=batch_id,
        output_dir=args.output_dir,
        bootstrap_output_dir=args.bootstrap_output_dir,
        stock_basic_csv=args.stock_basic_csv,
        raw_csv=args.raw_csv,
        feature_csv=args.feature_csv,
        index_feature_csv=args.index_feature_csv,
        calendar_csv=args.calendar_csv,
        trade_date_from=normalize_date_text(args.trade_date_from),
        trade_date_to=normalize_date_text(args.trade_date_to),
        allow_empty=args.allow_empty,
    )


def read_batch_status(batch_dir: Path) -> Optional[str]:
    job_log_path = batch_dir / "job_run_log.csv"
    if not job_log_path.exists():
        return None
    with job_log_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        first_row = next(reader, None)
    if not first_row:
        return None
    status = str(first_row.get("status", "") or "").strip().upper()
    return status or None


def latest_batch_dir(root_dir: str) -> Path:
    root = Path(root_dir)
    if not root.exists():
        raise GeneratorError("bootstrap 输出目录不存在: %s" % root)
    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        raise GeneratorError("未找到 bootstrap 批次目录: %s" % root)

    successful_batches = []
    for path in candidates:
        status = read_batch_status(path)
        if status in ["SUCCESS", "PARTIAL_SUCCESS"]:
            successful_batches.append(path)

    if not successful_batches:
        raise GeneratorError(
            "未找到可用 bootstrap 成功批次: %s；请先重跑 bootstrap，或显式传入 --stock-basic-csv / --raw-csv / --feature-csv"
            % root
        )
    return max(successful_batches, key=lambda path: path.stat().st_mtime)


def resolve_input_paths(config: Config) -> Dict[str, Optional[Path]]:
    explicit_required = all([config.stock_basic_csv, config.raw_csv, config.feature_csv])
    latest_dir = None if explicit_required else latest_batch_dir(config.bootstrap_output_dir)

    def choose(explicit_value: Optional[str], filename: str) -> Optional[Path]:
        if explicit_value:
            return Path(explicit_value)
        if latest_dir is None:
            return None
        default_path = latest_dir / filename
        return default_path if default_path.exists() else None

    paths = {
        "stock_basic": choose(config.stock_basic_csv, "stock_basic.csv"),
        "raw": choose(config.raw_csv, "stock_daily_raw.csv"),
        "feature": choose(config.feature_csv, "stock_daily_feature.csv"),
        "index_feature": choose(config.index_feature_csv, "index_daily_feature.csv"),
        "calendar": choose(config.calendar_csv, "trading_calendar.csv"),
    }

    for required_key in ["stock_basic", "raw", "feature"]:
        if paths[required_key] is None or not paths[required_key].exists():
            raise GeneratorError("缺少必要输入文件: %s" % required_key)
    return paths


def validate_frame_columns(frame, frame_name: str, required_columns: Sequence[str]) -> List[str]:
    if frame.empty:
        return []
    return [column for column in required_columns if column not in frame.columns]


def build_input_issue_record(
    generation_batch_id: str,
    reason: str,
    detail: Optional[Dict[str, object]] = None,
    *,
    code: str = "GLOBAL",
    status: str = "FAILED",
) -> Dict[str, object]:
    return build_debug_record(
        generation_batch_id=generation_batch_id,
        code=code,
        start_date=None,
        stage="input_validate",
        status=status,
        reason=reason,
        detail=detail or {},
    )


def format_issue_summary(issues: Sequence[Dict[str, object]]) -> str:
    parts = []
    for issue in issues:
        reason = str(issue.get("reason", "") or "")
        detail = str(issue.get("detail_json", "") or "")
        parts.append("%s%s" % (reason, ("(%s)" % detail) if detail and detail != "{}" else ""))
    return "; ".join(parts)


def read_csv(path: Optional[Path]):
    pd = lazy_import_pandas()
    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_data_bundle(config: Config) -> DataBundle:
    pd = lazy_import_pandas()
    paths = resolve_input_paths(config)

    stock_basic = read_csv(paths["stock_basic"])
    raw_df = read_csv(paths["raw"])
    feature_df = read_csv(paths["feature"])
    index_feature_df = read_csv(paths["index_feature"])
    calendar_df = read_csv(paths["calendar"])
    issues: List[Dict[str, object]] = []
    required_frames = {
        "stock_basic": stock_basic,
        "raw": raw_df,
        "feature": feature_df,
    }
    optional_frames = {
        "index_feature": index_feature_df,
        "calendar": calendar_df,
    }

    for name, frame in required_frames.items():
        if frame.empty:
            issues.append(
                build_input_issue_record(
                    config.generation_batch_id,
                    reason="empty_%s_input" % name,
                    detail={"path": str(paths[name]), "hint": "CSV 为空或只有表头"},
                )
            )
        missing_columns = validate_frame_columns(frame, name, REQUIRED_COLUMNS[name])
        if missing_columns:
            issues.append(
                build_input_issue_record(
                    config.generation_batch_id,
                    reason="missing_%s_columns" % name,
                    detail={"path": str(paths[name]), "missing_columns": missing_columns},
                )
            )

    for name, frame in optional_frames.items():
        if not frame.empty:
            missing_columns = validate_frame_columns(frame, name, REQUIRED_COLUMNS[name])
            if missing_columns:
                issues.append(
                    build_input_issue_record(
                        config.generation_batch_id,
                        reason="missing_%s_columns" % name,
                        detail={"path": str(paths[name]), "missing_columns": missing_columns},
                        status="WARN",
                    )
                )

    if issues and any(issue["status"] == "FAILED" for issue in issues):
        raise GeneratorInputError("generator 输入校验失败: %s" % format_issue_summary(issues), issues)

    for frame in [raw_df, feature_df, index_feature_df, calendar_df]:
        if not frame.empty:
            if "trade_date" in frame.columns:
                frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date

    stock_basic["code"] = stock_basic["code"].astype(str)
    stock_basic["stock_name"] = stock_basic.get("stock_name", stock_basic["code"]).fillna(stock_basic["code"])
    stock_basic["status"] = stock_basic.get("status", "LISTED").fillna("LISTED")
    if "list_date" in stock_basic.columns:
        stock_basic["list_date"] = pd.to_datetime(stock_basic["list_date"], errors="coerce").dt.date

    raw_df["code"] = raw_df["code"].astype(str)
    feature_df["code"] = feature_df["code"].astype(str)
    if not index_feature_df.empty and "index_code" in index_feature_df.columns:
        index_feature_df["index_code"] = index_feature_df["index_code"].astype(str)
    if not calendar_df.empty and "exchange" in calendar_df.columns:
        calendar_df["exchange"] = calendar_df["exchange"].astype(str)

    return DataBundle(stock_basic, raw_df, feature_df, index_feature_df, calendar_df)


def build_debug_record(
    generation_batch_id: str,
    code: str,
    start_date,
    stage: str,
    status: str,
    reason: str,
    detail: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    return {
        "generation_batch_id": generation_batch_id,
        "code": code,
        "start_date": start_date or "",
        "stage": stage,
        "status": status,
        "reason": reason,
        "detail_json": serialize_json(detail or {}),
    }


def evaluate_stock_level_filter(stock_row) -> Tuple[bool, List[str], List[str]]:
    code = str(stock_row.get("code", "") or "")
    stock_name = str(stock_row.get("stock_name", "") or "").upper()
    status = str(stock_row.get("status", "LISTED") or "LISTED").upper()
    list_date = stock_row.get("list_date")

    hard_reasons = []
    warn_reasons = []
    if not code:
        hard_reasons.append("missing_code")
    if status in ["DELISTING", "DELISTED_RISK"]:
        hard_reasons.append("stock_status_filtered")
    if stock_name.startswith("ST") or stock_name.startswith("*ST"):
        hard_reasons.append("st_name_filtered")
    if list_date is None or str(list_date) == "NaT":
        warn_reasons.append("missing_list_date")
    return len(hard_reasons) == 0, hard_reasons, warn_reasons


def pass_stock_level_filter(stock_row) -> bool:
    passed, _, _ = evaluate_stock_level_filter(stock_row)
    return passed


def tradable_start_dates(stock_row, raw_rows, calendar_df, trade_date_from: Optional[str], trade_date_to: Optional[str]):
    pd = lazy_import_pandas()
    exchange = str(stock_row.get("exchange", "") or "")
    code_dates = sorted(raw_rows["trade_date"].dropna().unique().tolist())
    if not code_dates:
        return []

    if not calendar_df.empty and "exchange" in calendar_df.columns and "is_open" in calendar_df.columns:
        cal = calendar_df[(calendar_df["exchange"] == exchange) & (calendar_df["is_open"] == 1)].copy()
        trade_dates = sorted(set(date_value for date_value in cal["trade_date"].dropna().tolist() if date_value in set(code_dates)))
    else:
        trade_dates = code_dates

    if trade_date_from:
        date_from = pd.to_datetime(trade_date_from).date()
        trade_dates = [value for value in trade_dates if value >= date_from]
    if trade_date_to:
        date_to = pd.to_datetime(trade_date_to).date()
        trade_dates = [value for value in trade_dates if value <= date_to]
    return trade_dates


def build_window(code: str, start_date, raw_rows, feature_rows, total_days: int = WINDOW_DAYS):
    code_dates = sorted(set(raw_rows["trade_date"].dropna().tolist()) & set(feature_rows["trade_date"].dropna().tolist()))
    if start_date not in code_dates:
        return None
    start_index = code_dates.index(start_date)
    needed_count = total_days + VERIFY_DAYS
    date_slice = code_dates[start_index : start_index + needed_count]
    if len(date_slice) < needed_count:
        return None

    main_dates = date_slice[:total_days]
    verify_dates = date_slice[total_days : total_days + VERIFY_DAYS]
    main_raw = raw_rows[raw_rows["trade_date"].isin(main_dates)].sort_values("trade_date").reset_index(drop=True)
    verify_raw = raw_rows[raw_rows["trade_date"].isin(verify_dates)].sort_values("trade_date").reset_index(drop=True)
    main_feature = feature_rows[feature_rows["trade_date"].isin(main_dates)].sort_values("trade_date").reset_index(drop=True)
    verify_feature = feature_rows[feature_rows["trade_date"].isin(verify_dates)].sort_values("trade_date").reset_index(drop=True)

    if len(main_raw) != total_days or len(main_feature) != total_days or len(verify_raw) != VERIFY_DAYS or len(verify_feature) != VERIFY_DAYS:
        return None

    return {
        "code": code,
        "start_date": main_dates[0],
        "end_date": main_dates[-1],
        "main_trade_dates": main_dates,
        "verify_trade_dates": verify_dates,
        "main_rows": main_raw,
        "verify_rows": verify_raw,
        "main_feature_rows": main_feature,
        "verify_feature_rows": verify_feature,
        "raw_rows": raw_rows,
        "feature_rows": feature_rows,
    }


def build_window_with_reason(code: str, start_date, raw_rows, feature_rows, total_days: int = WINDOW_DAYS):
    code_dates = sorted(set(raw_rows["trade_date"].dropna().tolist()) & set(feature_rows["trade_date"].dropna().tolist()))
    needed_count = total_days + VERIFY_DAYS
    if not code_dates or len(code_dates) < needed_count:
        return None, "insufficient_trade_days", {
            "available_trade_days": len(code_dates),
            "needed_trade_days": needed_count,
        }
    if start_date not in code_dates:
        return None, "start_date_missing", {"available_trade_days": len(code_dates)}

    window = build_window(code, start_date, raw_rows, feature_rows, total_days=total_days)
    if window is None:
        start_index = code_dates.index(start_date)
        remaining_days = len(code_dates) - start_index
        return None, "window_incomplete", {
            "remaining_trade_days": remaining_days,
            "needed_trade_days": needed_count,
        }
    return window, None, {
        "main_trade_days": len(window["main_trade_dates"]),
        "verify_trade_days": len(window["verify_trade_dates"]),
    }


def has_invalid_ohlc(frame) -> bool:
    if frame.empty:
        return True
    high = frame["high_price"]
    low = frame["low_price"]
    max_open_close = frame[["open_price", "close_price"]].max(axis=1)
    min_open_close = frame[["open_price", "close_price"]].min(axis=1)
    return bool(((high < low) | (high < max_open_close) | (low > min_open_close)).any())


def has_missing_volume(frame) -> bool:
    return bool(frame["volume"].isna().any())


def has_indicator_gap(frame) -> bool:
    required = ["ma20", "k_value", "d_value", "j_value", "dif", "dea", "macd"]
    for column in required:
        if column not in frame.columns or frame[column].isna().any():
            return True
    return False


def has_long_suspension(window) -> bool:
    frame = window["main_rows"]
    zero_volume_days = int((frame["volume"].fillna(0) <= 0).sum())
    return zero_volume_days >= 3


def is_limit_one_word_dominant(window) -> bool:
    frame = window["main_rows"]
    same_price_days = int((frame["high_price"] == frame["low_price"]).sum())
    return same_price_days >= 5


def pass_window_filter(window) -> Tuple[bool, List[str]]:
    reasons = []
    if len(window["main_rows"]) != WINDOW_DAYS:
        reasons.append("main_window_incomplete")
    if has_invalid_ohlc(window["main_rows"]):
        reasons.append("invalid_ohlc")
    if has_missing_volume(window["main_rows"]):
        reasons.append("missing_volume")
    if has_indicator_gap(window["main_feature_rows"]):
        reasons.append("indicator_gap")
    if has_long_suspension(window):
        reasons.append("long_suspension")
    if is_limit_one_word_dominant(window):
        reasons.append("limit_one_word_dominant")
    return len(reasons) == 0, reasons


def safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator is None or abs(denominator) < EPS:
        return None
    return numerator / denominator


def pct_change(current: float, base: float) -> Optional[float]:
    ratio = safe_div(current, base)
    return None if ratio is None else ratio - 1.0


def bool_value(value) -> bool:
    return bool(value) if value is not None and not (isinstance(value, float) and math.isnan(value)) else False


def consecutive_trend_days(close_values: Sequence[float], direction: str) -> int:
    if len(close_values) < 2:
        return 0
    count = 0
    for idx in range(len(close_values) - 1, 0, -1):
        change = close_values[idx] - close_values[idx - 1]
        if direction == "up" and change > 0:
            count += 1
        elif direction == "down" and change < 0:
            count += 1
        else:
            break
    return count


def detect_cross(prev_left, prev_right, current_left, current_right) -> Tuple[bool, bool]:
    golden = prev_left <= prev_right and current_left > current_right
    dead = prev_left >= prev_right and current_left < current_right
    return golden, dead


def detect_macd_hist_shrinking(current_macd, previous_macd) -> bool:
    if current_macd is None or previous_macd is None:
        return False
    return abs(current_macd) < abs(previous_macd)


def make_condition(ok: bool, label: str) -> Dict[str, object]:
    return {"ok": bool(ok), "label": label}


def summarize_conditions(conditions: Sequence[Dict[str, object]]) -> Tuple[List[str], List[str]]:
    matched = [str(item["label"]) for item in conditions if item.get("ok")]
    missed = [str(item["label"]) for item in conditions if not item.get("ok")]
    return matched, missed


def condition_score(matched_conditions: Sequence[str], bonus: float = 0.0) -> float:
    return float(len(matched_conditions)) + float(bonus)


def build_generator_features(window):
    main_feature = window["main_feature_rows"].reset_index(drop=True)
    verify_feature = window["verify_feature_rows"].reset_index(drop=True)
    main_raw = window["main_rows"].reset_index(drop=True)
    verify_raw = window["verify_rows"].reset_index(drop=True)

    if len(main_feature) != WINDOW_DAYS or len(verify_feature) != VERIFY_DAYS:
        return None

    end_idx = len(main_feature) - 1
    qfq_close = main_feature["qfq_close"].tolist()
    qfq_open = main_feature["qfq_open"].tolist()
    qfq_high = main_feature["qfq_high"].tolist()
    qfq_low = main_feature["qfq_low"].tolist()
    volumes = main_feature["volume"].tolist()

    def pct_change_n(n: int) -> Optional[float]:
        if end_idx - n < 0:
            return None
        return pct_change(qfq_close[end_idx], qfq_close[end_idx - n])

    current_range = qfq_high[end_idx] - qfq_low[end_idx]
    body_ratio = safe_div(abs(qfq_close[end_idx] - qfq_open[end_idx]), current_range if current_range else EPS)
    upper_shadow_ratio = safe_div(qfq_high[end_idx] - max(qfq_open[end_idx], qfq_close[end_idx]), current_range if current_range else EPS)
    lower_shadow_ratio = safe_div(min(qfq_open[end_idx], qfq_close[end_idx]) - qfq_low[end_idx], current_range if current_range else EPS)

    ma5 = main_feature["ma5"].iloc[end_idx]
    ma10 = main_feature["ma10"].iloc[end_idx]
    ma20 = main_feature["ma20"].iloc[end_idx]
    distance_to_ma20 = pct_change(qfq_close[end_idx], ma20)

    vol_ratio_1d_5d = safe_div(volumes[end_idx], sum(volumes[max(0, end_idx - 5) : end_idx]) / max(1, len(volumes[max(0, end_idx - 5) : end_idx])))
    vol_ratio_1d_10d = safe_div(volumes[end_idx], sum(volumes[max(0, end_idx - 10) : end_idx]) / max(1, len(volumes[max(0, end_idx - 10) : end_idx])))

    recent_high = max(qfq_close[-10:])
    recent_low = min(qfq_close[-10:])
    platform_width = pct_change(recent_high, recent_low)

    verify_closes = verify_feature["qfq_close"].tolist()
    false_break_retrace = None
    if verify_closes:
        breakout_gain = qfq_close[end_idx] - qfq_close[end_idx - 1]
        if abs(breakout_gain) >= EPS:
            false_break_retrace = (qfq_close[end_idx] - min(verify_closes)) / breakout_gain

    recent_high_10 = max(qfq_close[-10:])
    pullback_amount = pct_change(qfq_close[end_idx], recent_high_10)
    if pullback_amount is not None:
        pullback_amount = abs(pullback_amount)

    rise_range = volumes[max(0, end_idx - 9) : max(0, end_idx - 4)]
    pullback_range = volumes[max(0, end_idx - 4) : end_idx + 1]
    vol_shrink_ratio = safe_div(sum(pullback_range) / max(1, len(pullback_range)), sum(rise_range) / max(1, len(rise_range)))

    prev_k = main_feature["k_value"].iloc[end_idx - 1]
    prev_d = main_feature["d_value"].iloc[end_idx - 1]
    cur_k = main_feature["k_value"].iloc[end_idx]
    cur_d = main_feature["d_value"].iloc[end_idx]
    kdj_golden_cross, kdj_dead_cross = detect_cross(prev_k, prev_d, cur_k, cur_d)

    prev_dif = main_feature["dif"].iloc[end_idx - 1]
    prev_dea = main_feature["dea"].iloc[end_idx - 1]
    cur_dif = main_feature["dif"].iloc[end_idx]
    cur_dea = main_feature["dea"].iloc[end_idx]
    macd_golden_cross, macd_dead_cross = detect_cross(prev_dif, prev_dea, cur_dif, cur_dea)

    current_macd = main_feature["macd"].iloc[end_idx]
    previous_macd = main_feature["macd"].iloc[end_idx - 1]
    macd_hist_shrinking = detect_macd_hist_shrinking(current_macd, previous_macd)

    j_extreme_high = main_feature["j_value"].iloc[end_idx] >= 90
    j_extreme_low = main_feature["j_value"].iloc[end_idx] <= 10

    trend_up_days = consecutive_trend_days(qfq_close, "up")
    trend_down_days = consecutive_trend_days(qfq_close, "down")

    above_ma5 = qfq_close[end_idx] >= ma5 if ma5 is not None else None
    above_ma10 = qfq_close[end_idx] >= ma10 if ma10 is not None else None
    above_ma20 = qfq_close[end_idx] >= ma20 if ma20 is not None else None
    below_ma20_days = int((main_feature.tail(10)["qfq_close"] < main_feature.tail(10)["ma20"]).sum())
    ma_bull_alignment = bool(ma5 > ma10 > ma20)
    ma_bear_alignment = bool(ma5 < ma10 < ma20)

    amplitude_10 = pct_change(max(qfq_high[-10:]), min(qfq_low[-10:]))
    volatility_10 = float(main_feature.tail(10)["qfq_close"].pct_change().std()) if len(main_feature) >= 10 else None

    breakout_day_pct = pct_change(qfq_close[end_idx], qfq_close[end_idx - 1]) if end_idx >= 1 else None
    above_ma20_recent_days = int((main_feature.tail(5)["qfq_close"] >= main_feature.tail(5)["ma20"]).sum())
    near_ma10 = abs(pct_change(qfq_close[end_idx], ma10) or 0.0) <= 0.03 if ma10 is not None else False
    near_ma5 = abs(pct_change(qfq_close[end_idx], ma5) or 0.0) <= 0.03 if ma5 is not None else False
    price_volume_divergence = bool(
        (pct_change_n(10) is not None and pct_change_n(10) >= 0.15)
        and (vol_ratio_1d_5d is not None and vol_ratio_1d_5d <= 1.0)
    )

    long_lower_shadow_signal = (lower_shadow_ratio or 0.0) >= 0.35
    repair_signal_next_day = False
    if len(verify_feature) >= 1:
        repair_signal_next_day = verify_feature["qfq_close"].iloc[0] > qfq_close[end_idx]
    next_day_fade_signal = False
    if len(verify_feature) >= 1:
        next_day_fade_signal = verify_feature["qfq_close"].iloc[0] < qfq_close[end_idx]

    bearish_today = main_raw["close_price"].iloc[end_idx] < main_raw["open_price"].iloc[end_idx]
    stock_drop_1d = pct_change(main_feature["qfq_close"].iloc[end_idx], main_feature["qfq_close"].iloc[end_idx - 1])

    return {
        "base": {
            "pct_change_3": pct_change_n(3),
            "pct_change_10": pct_change_n(10),
            "pct_change_15": pct_change_n(15),
            "breakout_day_pct": breakout_day_pct,
            "body_ratio": body_ratio,
            "upper_shadow_ratio": upper_shadow_ratio,
            "lower_shadow_ratio": lower_shadow_ratio,
            "above_ma5": above_ma5,
            "above_ma10": above_ma10,
            "above_ma20": above_ma20,
            "below_ma20_days": below_ma20_days,
            "distance_to_ma20": distance_to_ma20,
            "vol_ratio_1d_5d": vol_ratio_1d_5d,
            "vol_ratio_1d_10d": vol_ratio_1d_10d,
            "vol_shrink_ratio": vol_shrink_ratio,
            "ma_bull_alignment": ma_bull_alignment,
            "ma_bear_alignment": ma_bear_alignment,
            "above_ma20_recent_days": above_ma20_recent_days,
            "near_ma5": near_ma5,
            "near_ma10": near_ma10,
            "trend_up_days": trend_up_days,
            "trend_down_days": trend_down_days,
            "amplitude_10": amplitude_10,
            "volatility_10": volatility_10,
            "platform_width": platform_width,
            "false_break_retrace": false_break_retrace,
            "kdj_golden_cross": kdj_golden_cross,
            "kdj_dead_cross": kdj_dead_cross,
            "j_extreme_high": j_extreme_high,
            "j_extreme_low": j_extreme_low,
            "macd_golden_cross": macd_golden_cross,
            "macd_dead_cross": macd_dead_cross,
            "macd_hist_shrinking": macd_hist_shrinking,
            "pullback_amount": pullback_amount,
            "bearish_today": bearish_today,
            "stock_drop_1d": stock_drop_1d,
            "price_volume_divergence": price_volume_divergence,
            "end_close": qfq_close[end_idx],
        },
        "validation": {
            "repair_signal_next_day": repair_signal_next_day,
            "next_day_fade_signal": next_day_fade_signal,
            "long_lower_shadow_signal": long_lower_shadow_signal,
            "verify_closes": verify_closes,
        },
    }


def normalize_index_code(value: str) -> str:
    return str(value).upper().replace(" ", "")


def pick_index_code(stock_row, index_feature_df) -> Optional[str]:
    if index_feature_df.empty or "index_code" not in index_feature_df.columns:
        return None
    exchange = str(stock_row.get("exchange", "") or "")
    board = str(stock_row.get("board", "") or "")
    if board == "GEM":
        aliases = INDEX_ALIAS["GEM"]
    elif exchange == "SH":
        aliases = INDEX_ALIAS["SH"]
    else:
        aliases = INDEX_ALIAS["SZ"]

    available_codes = {normalize_index_code(code): code for code in index_feature_df["index_code"].dropna().unique().tolist()}
    for alias in aliases:
        normalized_alias = normalize_index_code(alias)
        if normalized_alias in available_codes:
            return available_codes[normalized_alias]
    return None


def load_index_features_for_window(stock_row, window, index_feature_df):
    if index_feature_df.empty:
        return None
    index_code = pick_index_code(stock_row, index_feature_df)
    if not index_code:
        return None
    trade_dates = window["main_trade_dates"] + window["verify_trade_dates"]
    frame = index_feature_df[(index_feature_df["index_code"] == index_code) & (index_feature_df["trade_date"].isin(trade_dates))].sort_values("trade_date")
    if len(frame) < WINDOW_DAYS:
        return None
    main_frame = frame[frame["trade_date"].isin(window["main_trade_dates"])]
    verify_frame = frame[frame["trade_date"].isin(window["verify_trade_dates"])]
    if len(main_frame) != WINDOW_DAYS:
        return None
    return {"index_code": index_code, "main": main_frame.reset_index(drop=True), "verify": verify_frame.reset_index(drop=True)}


def hit_result(
    tag_name: str,
    hit: bool,
    reason: str,
    score: float,
    metrics: Dict[str, object],
    *,
    matched_conditions: Optional[Sequence[str]] = None,
    missed_conditions: Optional[Sequence[str]] = None,
    exclusion_reasons: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    return {
        "tag_name": tag_name,
        "hit": hit,
        "reason": reason,
        "score": score,
        "metrics": metrics,
        "matched_conditions": list(matched_conditions or []),
        "missed_conditions": list(missed_conditions or []),
        "exclusion_reasons": list(exclusion_reasons or []),
    }


def evaluate_bottom(features) -> Dict[str, object]:
    base = features["base"]
    conditions = [
        make_condition(base["pct_change_10"] is not None and base["pct_change_10"] <= -0.12, "pct_change_10<=-0.12"),
        make_condition(base["below_ma20_days"] >= 7, "below_ma20_days>=7"),
        make_condition(base["distance_to_ma20"] is not None and base["distance_to_ma20"] < 0.02, "distance_to_ma20<0.02"),
        make_condition(base["vol_ratio_1d_5d"] is not None and base["vol_ratio_1d_5d"] < 1.2, "vol_ratio_1d_5d<1.2"),
    ]
    matched, missed = summarize_conditions(conditions)
    confirm_count = sum([bool_value(base["kdj_golden_cross"]), bool_value(base["macd_golden_cross"]), bool_value(base["above_ma5"])])
    score = condition_score(matched, 0.3 * confirm_count)
    hit = len(matched) == len(conditions)
    return hit_result(
        TAG_BOTTOM,
        hit,
        ", ".join(matched if hit else (missed or matched)),
        score,
        {"confirm_count": confirm_count},
        matched_conditions=matched,
        missed_conditions=missed,
    )


def evaluate_breakout(features) -> Dict[str, object]:
    base = features["base"]
    breakout_gain = base["breakout_day_pct"] is not None and base["breakout_day_pct"] >= 0.04
    platform_ok = base["platform_width"] is not None and base["platform_width"] <= 0.12
    vol_ok = base["vol_ratio_1d_5d"] is not None and base["vol_ratio_1d_5d"] >= 1.8 and base["vol_ratio_1d_10d"] is not None and base["vol_ratio_1d_10d"] >= 1.5
    above_ma20 = bool_value(base["above_ma20"])
    retrace = base["false_break_retrace"]
    retrace_ok = retrace is None or retrace < 0.5
    conditions = [
        make_condition(platform_ok, "platform_width<=0.12"),
        make_condition(breakout_gain, "breakout_day_pct>=0.04"),
        make_condition(vol_ok, "volume_breakout"),
        make_condition(above_ma20, "above_ma20"),
        make_condition(retrace_ok, "false_break_retrace<0.5"),
    ]
    matched, missed = summarize_conditions(conditions)
    score = condition_score(matched, 0.5 if retrace is not None and retrace < 0.3 else 0.0)
    hit = platform_ok and breakout_gain and vol_ok and above_ma20 and retrace_ok
    return hit_result(
        TAG_BREAKOUT,
        hit,
        ", ".join(matched if hit else (missed or matched)),
        score,
        {"false_break_retrace": retrace, "breakout_day_pct": base["breakout_day_pct"]},
        matched_conditions=matched,
        missed_conditions=missed,
    )


def evaluate_highvolbear(features) -> Dict[str, object]:
    base = features["base"]
    conditions = [
        make_condition(base["pct_change_15"] is not None and base["pct_change_15"] >= 0.20, "pct_change_15>=0.20"),
        make_condition(base["distance_to_ma20"] is not None and base["distance_to_ma20"] >= 0.08, "distance_to_ma20>=0.08"),
        make_condition(base["vol_ratio_1d_5d"] is not None and base["vol_ratio_1d_5d"] >= 1.8, "vol_ratio_1d_5d>=1.8"),
        make_condition(bool_value(base["bearish_today"]), "bearish_today"),
        make_condition(base["body_ratio"] is not None and base["body_ratio"] >= 0.4, "body_ratio>=0.4"),
    ]
    matched, missed = summarize_conditions(conditions)
    score = condition_score(matched, 0.4 if base["upper_shadow_ratio"] is not None and base["upper_shadow_ratio"] >= 0.35 else 0.0)
    hit = len(matched) == len(conditions)
    return hit_result(
        TAG_HIGHVOLBEAR,
        hit,
        ", ".join(matched if hit else (missed or matched)),
        score,
        {"upper_shadow_ratio": base["upper_shadow_ratio"]},
        matched_conditions=matched,
        missed_conditions=missed,
    )


def evaluate_pullback(features) -> Dict[str, object]:
    base = features["base"]
    conditions = [
        make_condition(bool_value(base["ma_bull_alignment"]), "ma_bull_alignment"),
        make_condition(base["pullback_amount"] is not None and 0.03 <= base["pullback_amount"] <= 0.08, "pullback_amount_in_range"),
        make_condition(base["vol_shrink_ratio"] is not None and base["vol_shrink_ratio"] <= 0.75, "vol_shrink_ratio<=0.75"),
        make_condition(base["distance_to_ma20"] is not None and base["distance_to_ma20"] >= -0.03, "not_far_below_ma20"),
        make_condition(bool_value(base["near_ma5"]) or bool_value(base["near_ma10"]) or bool_value(base["above_ma20"]), "near_support_ma"),
    ]
    matched, missed = summarize_conditions(conditions)
    score = condition_score(matched, 0.5 if bool_value(features["validation"]["repair_signal_next_day"]) else 0.0)
    hit = len(matched) >= 4
    return hit_result(
        TAG_PULLBACK,
        hit,
        ", ".join(matched if hit else (missed or matched)),
        score,
        {"pullback_amount": base["pullback_amount"]},
        matched_conditions=matched,
        missed_conditions=missed,
    )


def evaluate_takeprofit(features) -> Dict[str, object]:
    base = features["base"]
    gate = [
        make_condition(base["trend_up_days"] >= 5, "trend_up_days>=5"),
        make_condition(base["pct_change_10"] is not None and base["pct_change_10"] >= 0.15, "pct_change_10>=0.15"),
        make_condition(base["distance_to_ma20"] is not None and base["distance_to_ma20"] >= 0.08, "distance_to_ma20>=0.08"),
    ]
    signal_count = sum([
        bool_value(base["j_extreme_high"]),
        bool_value(base["macd_hist_shrinking"]),
        bool_value(base["kdj_dead_cross"]),
        bool_value(base["price_volume_divergence"]),
        bool_value(features["validation"]["next_day_fade_signal"]),
    ])
    matched, missed = summarize_conditions(gate)
    score = condition_score(matched, signal_count)
    hit = len(matched) == len(gate) and signal_count >= 1
    return hit_result(
        TAG_TAKEPROFIT,
        hit,
        ", ".join(matched if hit else (missed or matched)),
        score,
        {"signal_count": signal_count, "price_volume_divergence": base["price_volume_divergence"]},
        matched_conditions=matched,
        missed_conditions=missed,
    )


def evaluate_panic(features, index_features) -> Dict[str, object]:
    if index_features is None:
        return hit_result(
            TAG_PANIC,
            False,
            "index_features_missing",
            0.0,
            {"index_available": False},
            matched_conditions=[],
            missed_conditions=["index_features_missing"],
        )

    main_index = index_features["main"].reset_index(drop=True)
    verify_index = index_features["verify"].reset_index(drop=True)
    idx = len(main_index) - 1

    index_drop_1d = float(main_index["pct_change_1d"].iloc[idx])
    index_drawdown_5d = float(main_index["drawdown_5d"].iloc[idx])
    index_vol_ratio = float(main_index["vol_ratio_1d_5d"].iloc[idx])
    index_panic_flag = bool(main_index["panic_flag"].iloc[idx])
    index_vol_spike = index_vol_ratio >= 1.30

    panic_trigger = index_drop_1d <= -0.03 or index_drawdown_5d <= -0.08
    panic_flag = index_panic_flag or (index_drop_1d <= -0.04) or (index_drawdown_5d <= -0.10 and index_vol_spike)

    base = features["base"]
    validation = features["validation"]
    relative_strength_vs_index = base["stock_drop_1d"] is not None and base["stock_drop_1d"] > index_drop_1d
    independent_crash = base["stock_drop_1d"] is not None and base["stock_drop_1d"] < index_drop_1d - 0.05
    repair_signals = sum([
        bool_value(validation["long_lower_shadow_signal"]),
        bool_value(relative_strength_vs_index),
        bool_value(validation["repair_signal_next_day"]),
    ])
    matched = []
    missed = []
    if panic_trigger:
        matched.append("panic_trigger")
    else:
        missed.append("panic_trigger")
    if index_vol_spike or panic_flag:
        matched.append("index_confirmed")
    else:
        missed.append("index_confirmed")
    if repair_signals >= 1:
        matched.append("repair_signals>=1")
    else:
        missed.append("repair_signals>=1")
    exclusion_reasons = ["independent_stock_crash"] if independent_crash else []
    hit = panic_trigger and (index_vol_spike or panic_flag) and (repair_signals >= 1) and not independent_crash
    return hit_result(
        TAG_PANIC,
        hit,
        ", ".join(matched if hit else (exclusion_reasons or missed or matched)),
        condition_score(matched, repair_signals),
        {
            "index_available": True,
            "index_code": index_features["index_code"],
            "index_drop_1d": index_drop_1d,
            "index_drawdown_5d": index_drawdown_5d,
            "index_vol_ratio": index_vol_ratio,
            "repair_signals": repair_signals,
            "independent_stock_crash": independent_crash,
        },
        matched_conditions=matched,
        missed_conditions=missed,
        exclusion_reasons=exclusion_reasons,
    )


def classify_tags(window, features, index_features):
    evaluators = [
        lambda: evaluate_bottom(features),
        lambda: evaluate_breakout(features),
        lambda: evaluate_highvolbear(features),
        lambda: evaluate_pullback(features),
        lambda: evaluate_panic(features, index_features),
        lambda: evaluate_takeprofit(features),
    ]
    hits = []
    evaluations = []
    for evaluator in evaluators:
        result = evaluator()
        evaluations.append(result)
        if result["hit"]:
            hits.append(result)
    return {"hit_any": len(hits) > 0, "hits": hits, "evaluations": evaluations}


def build_tag_debug_records(generation_batch_id: str, code: str, start_date, tag_result: Dict[str, object]) -> List[Dict[str, object]]:
    rows = []
    for result in tag_result.get("evaluations", []):
        rows.append(
            build_debug_record(
                generation_batch_id=generation_batch_id,
                code=code,
                start_date=start_date,
                stage="tag_rule",
                status="PASSED" if result.get("hit") else "SKIPPED",
                reason=("tag_hit_%s" % result["tag_name"]) if result.get("hit") else ("tag_miss_%s" % result["tag_name"]),
                detail={
                    "tag_name": result["tag_name"],
                    "matched_conditions": result.get("matched_conditions", []),
                    "missed_conditions": result.get("missed_conditions", []),
                    "exclusion_reasons": result.get("exclusion_reasons", []),
                    "metrics": result.get("metrics", {}),
                },
            )
        )
    return rows


def sort_by_priority(hits: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    priority_index = {name: idx for idx, name in enumerate(TAG_PRIORITY_ORDER)}
    return sorted(hits, key=lambda item: (priority_index[item["tag_name"]], -float(item.get("score", 0.0))))


def resolve_tag_conflict(tag_result):
    if not tag_result["hits"]:
        return {
            "primary_tag": None,
            "secondary_tag": None,
            "review_status": "PENDING",
            "conflict_flags": {"tag_hit_count": 0, "review_required_reason": None, "strong_conflict": False},
            "ordered_hits": [],
        }

    ordered_hits = sort_by_priority(tag_result["hits"])
    primary = ordered_hits[0]
    secondary = None
    review_status = "PENDING"
    review_reason = None
    strong_conflict = False

    if len(ordered_hits) >= 2:
        candidate_secondary = ordered_hits[1]
        if (primary["tag_name"], candidate_secondary["tag_name"]) in EXPLANATORY_SECONDARY:
            secondary = candidate_secondary
        else:
            review_status = "REVIEW_REQUIRED"
            review_reason = "multiple_strong_tags"
            score_gap = abs(float(primary.get("score", 0.0)) - float(candidate_secondary.get("score", 0.0)))
            strong_conflict = score_gap <= 0.5 or len(ordered_hits) >= 3

    return {
        "primary_tag": primary["tag_name"],
        "secondary_tag": secondary["tag_name"] if secondary else None,
        "review_status": review_status,
        "conflict_flags": {
            "tag_hit_count": len(ordered_hits),
            "review_required_reason": review_reason,
            "hit_tags": [item["tag_name"] for item in ordered_hits],
            "strong_conflict": strong_conflict,
        },
        "ordered_hits": ordered_hits,
    }


def classify_difficulty(window, features, resolved_tag_result):
    base = features["base"]
    hit_count = len(resolved_tag_result["ordered_hits"])
    false_signal_risk = bool(
        resolved_tag_result["review_status"] == "REVIEW_REQUIRED"
        or bool_value(resolved_tag_result["conflict_flags"].get("strong_conflict"))
        or (base["false_break_retrace"] is not None and base["false_break_retrace"] >= 0.5)
        or (base["volatility_10"] is not None and base["volatility_10"] >= 0.05)
        or bool_value(base.get("price_volume_divergence"))
        or hit_count >= 3
    )
    clear_signal = bool(
        hit_count == 1
        and resolved_tag_result["review_status"] == "PENDING"
        and resolved_tag_result["primary_tag"] in [TAG_PULLBACK, TAG_BOTTOM]
        and (base["vol_shrink_ratio"] is None or base["vol_shrink_ratio"] <= 0.75)
        and (base["volatility_10"] is None or base["volatility_10"] < 0.035)
    )

    if clear_signal:
        return "easy", "single_clear_signal_low_conflict"
    if false_signal_risk or resolved_tag_result["primary_tag"] == TAG_HIGHVOLBEAR:
        return "hard", "high_conflict_or_false_signal_risk"
    return "normal", "multi_signal_but_explainable"


def recently_listed_window(stock_row, window) -> bool:
    list_date = stock_row.get("list_date")
    if list_date is None or str(list_date) == "NaT":
        return False
    start_date = window["start_date"]
    return (start_date - list_date).days < RECENT_LISTING_MIN_DAYS


def pass_candidate_gate(stock_row, window, features, resolved_tag_result, difficulty) -> bool:
    passed, _ = evaluate_candidate_gate(stock_row, window, features, resolved_tag_result, difficulty)
    return passed


def evaluate_candidate_gate(stock_row, window, features, resolved_tag_result, difficulty) -> Tuple[bool, List[str]]:
    reasons = []
    if resolved_tag_result["primary_tag"] is None:
        reasons.append("missing_primary_tag")
    if recently_listed_window(stock_row, window):
        reasons.append("recently_listed_window")
    if has_long_suspension(window):
        reasons.append("long_suspension")
    if has_invalid_ohlc(window["main_rows"]):
        reasons.append("invalid_ohlc")
    if has_missing_volume(window["main_rows"]):
        reasons.append("missing_volume")
    if has_indicator_gap(window["main_feature_rows"]):
        reasons.append("indicator_gap")
    if bool_value(resolved_tag_result["conflict_flags"].get("strong_conflict")) and len(resolved_tag_result["ordered_hits"]) >= 3:
        reasons.append("unresolvable_tag_conflict")
    return len(reasons) == 0, reasons


def serialize_json(payload: Dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def build_candidate_row(stock_row, window, features, resolved_tag_result, difficulty, difficulty_reason, generation_batch_id, excluded_reasons, tag_result=None):
    ordered_hits = resolved_tag_result["ordered_hits"]
    score_explain = {
        "feature_snapshot": {
            "breakout_day_pct": features["base"].get("breakout_day_pct"),
            "pct_change_10": features["base"].get("pct_change_10"),
            "pct_change_15": features["base"].get("pct_change_15"),
            "distance_to_ma20": features["base"].get("distance_to_ma20"),
            "vol_ratio_1d_5d": features["base"].get("vol_ratio_1d_5d"),
            "vol_ratio_1d_10d": features["base"].get("vol_ratio_1d_10d"),
            "vol_shrink_ratio": features["base"].get("vol_shrink_ratio"),
            "false_break_retrace": features["base"].get("false_break_retrace"),
            "trend_up_days": features["base"].get("trend_up_days"),
            "below_ma20_days": features["base"].get("below_ma20_days"),
            "price_volume_divergence": features["base"].get("price_volume_divergence"),
        },
        "hit_reasons": [
            {
                "tag": hit["tag_name"],
                "reason": hit["reason"],
                "score": hit["score"],
                "matched_conditions": hit.get("matched_conditions", []),
                "missed_conditions": hit.get("missed_conditions", []),
            }
            for hit in ordered_hits
        ],
        "difficulty_reason": difficulty_reason,
    }
    rule_flags = {
        "tag_hits": [hit["tag_name"] for hit in ordered_hits],
        "hit_metrics": {hit["tag_name"]: hit.get("metrics", {}) for hit in ordered_hits},
        "conflict_flags": resolved_tag_result["conflict_flags"],
        "excluded_reasons": excluded_reasons,
        "needs_index_review": TAG_PANIC in [hit["tag_name"] for hit in ordered_hits],
        "tag_miss_summary": [
            {
                "tag": item["tag_name"],
                "missed_conditions": item.get("missed_conditions", []),
                "exclusion_reasons": item.get("exclusion_reasons", []),
            }
            for item in (tag_result or {}).get("evaluations", [])
            if not item.get("hit")
        ],
    }

    return {
        "candidate_key": "%s_%s" % (stock_row["code"], window["start_date"]),
        "code": stock_row["code"],
        "start_date": window["start_date"],
        "end_date": window["end_date"],
        "primary_tag": resolved_tag_result["primary_tag"],
        "secondary_tag": resolved_tag_result["secondary_tag"],
        "difficulty": difficulty,
        "score_explain_json": serialize_json(score_explain),
        "rule_flags_json": serialize_json(rule_flags),
        "review_status": resolved_tag_result["review_status"],
        "review_comment": "",
        "adjusted_primary_tag": "",
        "adjusted_difficulty": "",
        "generation_batch_id": generation_batch_id,
    }


def emit_candidate_csv(candidate_rows, generation_batch_id: str, output_dir: str) -> Path:
    pd = lazy_import_pandas()
    output_root = output_root_dir(output_dir)
    path = output_root / ("candidate_%s.csv" % generation_batch_id)
    frame = pd.DataFrame(candidate_rows)
    frame.to_csv(path, index=False)
    return path


def emit_generator_debug_csv(debug_rows, generation_batch_id: str, output_dir: str) -> Path:
    pd = lazy_import_pandas()
    output_root = output_root_dir(output_dir)
    path = output_root / ("generator_debug_%s.csv" % generation_batch_id)
    frame = pd.DataFrame(
        debug_rows,
        columns=["generation_batch_id", "code", "start_date", "stage", "status", "reason", "detail_json"],
    )
    frame.to_csv(path, index=False)
    return path


def summarize_reject_reasons(debug_rows) -> List[Dict[str, object]]:
    counter = Counter()
    for row in debug_rows:
        if row.get("status") in ["SKIPPED", "FAILED"]:
            reason = str(row.get("reason", "") or "").strip()
            if reason:
                counter[reason] += 1
    return [{"reason": reason, "count": count} for reason, count in counter.most_common(10)]


def format_top_reason_summary(reason_rows: Sequence[Dict[str, object]]) -> str:
    if not reason_rows:
        return "none"
    return ", ".join("%s=%s" % (row.get("reason"), row.get("count")) for row in reason_rows)


def build_empty_candidate_hint(top_reject_reasons: Sequence[Dict[str, object]]) -> str:
    if not top_reject_reasons:
        return "请先查看 generator_debug，确认是输入缺失还是规则未命中。"
    top_reason = str(top_reject_reasons[0].get("reason", "") or "")
    if top_reason == "insufficient_trade_days":
        return "样本不足：单股、单月通常少于 20+3 个交易日，请扩大股票数量或日期范围。"
    if top_reason == "missing_price_or_feature_data":
        return "输入缺少 raw/feature 有效数据，请先检查 bootstrap 成功批次或显式指定成功 CSV。"
    if top_reason == "no_tag_hit":
        return "窗口已扫描但标签规则未命中，请先查看 generator_debug 中 tag_classify 阶段。"
    if top_reason.startswith("tag_miss_"):
        return "规则未命中，请先查看 generator_debug 中 stage=tag_rule 的 matched_conditions / missed_conditions。"
    if top_reason.startswith("missing_") or top_reason.startswith("empty_"):
        return "输入文件缺列或为空，请先检查所选 bootstrap 批次与 CSV 结构。"
    return "请优先查看 generator_debug 中出现次数最多的 reason。"


def emit_generator_run_log(summary_row: Dict[str, object], generation_batch_id: str, output_dir: str) -> Path:
    pd = lazy_import_pandas()
    output_root = output_root_dir(output_dir)
    path = output_root / ("generator_run_log_%s.csv" % generation_batch_id)
    frame = pd.DataFrame(
        [summary_row],
        columns=[
            "generation_batch_id",
            "stock_count",
            "tradable_stock_count",
            "window_scanned_count",
            "window_passed_count",
            "tag_hit_count",
            "candidate_count",
            "top_reject_reasons_json",
            "status",
            "status_message",
            "input_summary_json",
        ],
    )
    frame.to_csv(path, index=False)
    return path


def iter_stock_pool(stock_basic) -> Iterable:
    for _, row in stock_basic.iterrows():
        yield row


def run_generator(config: Config) -> Optional[Path]:
    candidate_rows = []
    debug_rows = []
    stock_count = 0
    tradable_stock_count = 0
    window_scanned_count = 0
    window_passed_count = 0
    tag_hit_count = 0
    input_summary = {}

    try:
        data = load_data_bundle(config)
    except GeneratorInputError as exc:
        debug_rows.extend(exc.issues)
        debug_path = emit_generator_debug_csv(debug_rows, config.generation_batch_id, config.output_dir)
        run_log_path = emit_generator_run_log(
            {
                "generation_batch_id": config.generation_batch_id,
                "stock_count": 0,
                "tradable_stock_count": 0,
                "window_scanned_count": 0,
                "window_passed_count": 0,
                "tag_hit_count": 0,
                "candidate_count": 0,
                "top_reject_reasons_json": serialize_json(summarize_reject_reasons(debug_rows)),
                "status": "FAILED",
                "status_message": str(exc),
                "input_summary_json": serialize_json({}),
            },
            config.generation_batch_id,
            config.output_dir,
        )
        raise GeneratorError("%s；详见 %s 和 %s" % (exc, debug_path, run_log_path))
    except GeneratorError as exc:
        debug_rows.append(
            build_input_issue_record(
                config.generation_batch_id,
                reason="input_resolution_failed",
                detail={"message": str(exc)},
            )
        )
        debug_path = emit_generator_debug_csv(debug_rows, config.generation_batch_id, config.output_dir)
        run_log_path = emit_generator_run_log(
            {
                "generation_batch_id": config.generation_batch_id,
                "stock_count": 0,
                "tradable_stock_count": 0,
                "window_scanned_count": 0,
                "window_passed_count": 0,
                "tag_hit_count": 0,
                "candidate_count": 0,
                "top_reject_reasons_json": serialize_json(summarize_reject_reasons(debug_rows)),
                "status": "FAILED",
                "status_message": str(exc),
                "input_summary_json": serialize_json({}),
            },
            config.generation_batch_id,
            config.output_dir,
        )
        raise GeneratorError("%s；详见 %s 和 %s" % (exc, debug_path, run_log_path))

    stock_count = len(data.stock_basic)
    input_summary = {
        "stock_basic_rows": len(data.stock_basic),
        "raw_rows": len(data.raw_df),
        "feature_rows": len(data.feature_df),
        "index_feature_rows": len(data.index_feature_df),
        "calendar_rows": len(data.calendar_df),
    }

    for stock in iter_stock_pool(data.stock_basic):
        code = str(stock.get("code", "") or "")
        passed_stock_filter, hard_reasons, warn_reasons = evaluate_stock_level_filter(stock)
        for reason in warn_reasons:
            debug_rows.append(
                build_debug_record(
                    generation_batch_id=config.generation_batch_id,
                    code=code,
                    start_date=None,
                    stage="stock_filter",
                    status="WARN",
                    reason=reason,
                    detail={"status": str(stock.get("status", "") or ""), "stock_name": str(stock.get("stock_name", "") or "")},
                )
            )
        if not passed_stock_filter:
            for reason in hard_reasons:
                debug_rows.append(
                    build_debug_record(
                        generation_batch_id=config.generation_batch_id,
                        code=code,
                        start_date=None,
                        stage="stock_filter",
                        status="SKIPPED",
                        reason=reason,
                        detail={"status": str(stock.get("status", "") or ""), "stock_name": str(stock.get("stock_name", "") or "")},
                    )
                )
            continue
        tradable_stock_count += 1
        debug_rows.append(
            build_debug_record(
                generation_batch_id=config.generation_batch_id,
                code=code,
                start_date=None,
                stage="stock_filter",
                status="PASSED",
                reason="stock_filter_passed",
                detail={"exchange": str(stock.get("exchange", "") or ""), "board": str(stock.get("board", "") or "")},
            )
        )
        raw_rows = data.raw_df[data.raw_df["code"] == code].sort_values("trade_date").reset_index(drop=True)
        feature_rows = data.feature_df[data.feature_df["code"] == code].sort_values("trade_date").reset_index(drop=True)
        if raw_rows.empty or feature_rows.empty:
            debug_rows.append(
                build_debug_record(
                    generation_batch_id=config.generation_batch_id,
                    code=code,
                    start_date=None,
                    stage="window_build",
                    status="SKIPPED",
                    reason="missing_price_or_feature_data",
                    detail={"raw_rows": len(raw_rows), "feature_rows": len(feature_rows)},
                )
            )
            continue

        code_dates = sorted(set(raw_rows["trade_date"].dropna().tolist()) & set(feature_rows["trade_date"].dropna().tolist()))
        if len(code_dates) < WINDOW_DAYS + VERIFY_DAYS:
            debug_rows.append(
                build_debug_record(
                    generation_batch_id=config.generation_batch_id,
                    code=code,
                    start_date=None,
                    stage="window_build",
                    status="SKIPPED",
                    reason="insufficient_trade_days",
                    detail={"available_trade_days": len(code_dates), "needed_trade_days": WINDOW_DAYS + VERIFY_DAYS},
                )
            )
            continue

        for start_date in tradable_start_dates(stock, raw_rows, data.calendar_df, config.trade_date_from, config.trade_date_to):
            window_scanned_count += 1
            window, window_reason, window_detail = build_window_with_reason(code, start_date, raw_rows, feature_rows, WINDOW_DAYS)
            if window is None:
                debug_rows.append(
                    build_debug_record(
                        generation_batch_id=config.generation_batch_id,
                        code=code,
                        start_date=start_date,
                        stage="window_build",
                        status="SKIPPED",
                        reason=window_reason or "window_incomplete",
                        detail=window_detail,
                    )
                )
                continue
            debug_rows.append(
                build_debug_record(
                    generation_batch_id=config.generation_batch_id,
                    code=code,
                    start_date=start_date,
                    stage="window_build",
                    status="PASSED",
                    reason="window_ready",
                    detail=window_detail,
                )
            )

            passed, excluded_reasons = pass_window_filter(window)
            if not passed:
                for reason in excluded_reasons:
                    debug_rows.append(
                        build_debug_record(
                            generation_batch_id=config.generation_batch_id,
                            code=code,
                            start_date=start_date,
                            stage="window_filter",
                            status="SKIPPED",
                            reason=reason,
                            detail={"excluded_reasons": excluded_reasons},
                        )
                    )
                continue
            window_passed_count += 1
            debug_rows.append(
                build_debug_record(
                    generation_batch_id=config.generation_batch_id,
                    code=code,
                    start_date=start_date,
                    stage="window_filter",
                    status="PASSED",
                    reason="window_filter_passed",
                    detail={"excluded_reasons": excluded_reasons},
                )
            )

            features = build_generator_features(window)
            if features is None:
                debug_rows.append(
                    build_debug_record(
                        generation_batch_id=config.generation_batch_id,
                        code=code,
                        start_date=start_date,
                        stage="feature_build",
                        status="FAILED",
                        reason="feature_build_failed",
                        detail={"main_rows": len(window["main_rows"]), "verify_rows": len(window["verify_rows"])},
                    )
                )
                continue
            debug_rows.append(
                build_debug_record(
                    generation_batch_id=config.generation_batch_id,
                    code=code,
                    start_date=start_date,
                    stage="feature_build",
                    status="PASSED",
                    reason="feature_ready",
                    detail={"end_date": str(window["end_date"])},
                )
            )

            index_features = load_index_features_for_window(stock, window, data.index_feature_df)
            tag_result = classify_tags(window, features, index_features)
            debug_rows.extend(build_tag_debug_records(config.generation_batch_id, code, start_date, tag_result))
            if not tag_result["hit_any"]:
                debug_rows.append(
                    build_debug_record(
                        generation_batch_id=config.generation_batch_id,
                        code=code,
                        start_date=start_date,
                        stage="tag_classify",
                        status="SKIPPED",
                        reason="no_tag_hit",
                        detail={
                            "index_available": bool(index_features is not None),
                            "tag_miss_summary": [
                                {
                                    "tag_name": item["tag_name"],
                                    "missed_conditions": item.get("missed_conditions", []),
                                    "exclusion_reasons": item.get("exclusion_reasons", []),
                                }
                                for item in tag_result.get("evaluations", [])
                            ],
                        },
                    )
                )
                continue
            tag_hit_count += 1
            debug_rows.append(
                build_debug_record(
                    generation_batch_id=config.generation_batch_id,
                    code=code,
                    start_date=start_date,
                    stage="tag_classify",
                    status="PASSED",
                    reason="tag_hit",
                    detail={"hit_tags": [item["tag_name"] for item in tag_result["hits"]]},
                )
            )

            resolved = resolve_tag_conflict(tag_result)
            difficulty, difficulty_reason = classify_difficulty(window, features, resolved)
            gate_passed, gate_reasons = evaluate_candidate_gate(stock, window, features, resolved, difficulty)
            if not gate_passed:
                for reason in gate_reasons:
                    debug_rows.append(
                        build_debug_record(
                            generation_batch_id=config.generation_batch_id,
                            code=code,
                            start_date=start_date,
                            stage="candidate_gate",
                            status="SKIPPED",
                            reason=reason,
                            detail={"difficulty": difficulty, "primary_tag": resolved["primary_tag"], "conflict_flags": resolved["conflict_flags"]},
                        )
                    )
                continue

            candidate_rows.append(
                build_candidate_row(
                    stock_row=stock,
                    window=window,
                    features=features,
                resolved_tag_result=resolved,
                difficulty=difficulty,
                difficulty_reason=difficulty_reason,
                generation_batch_id=config.generation_batch_id,
                excluded_reasons=excluded_reasons,
                tag_result=tag_result,
            )
            )
            debug_rows.append(
                build_debug_record(
                    generation_batch_id=config.generation_batch_id,
                    code=code,
                    start_date=start_date,
                    stage="candidate_emit",
                    status="PASSED",
                    reason="candidate_emitted",
                    detail={"primary_tag": resolved["primary_tag"], "difficulty": difficulty, "review_status": resolved["review_status"]},
                )
            )

    debug_path = emit_generator_debug_csv(debug_rows, config.generation_batch_id, config.output_dir)
    top_reject_reasons = summarize_reject_reasons(debug_rows)
    run_log_path = emit_generator_run_log(
        {
            "generation_batch_id": config.generation_batch_id,
            "stock_count": stock_count,
            "tradable_stock_count": tradable_stock_count,
            "window_scanned_count": window_scanned_count,
            "window_passed_count": window_passed_count,
            "tag_hit_count": tag_hit_count,
            "candidate_count": len(candidate_rows),
            "top_reject_reasons_json": serialize_json(top_reject_reasons),
            "status": "SUCCESS" if candidate_rows else "EMPTY",
            "status_message": "" if candidate_rows else build_empty_candidate_hint(top_reject_reasons),
            "input_summary_json": serialize_json(input_summary),
        },
        config.generation_batch_id,
        config.output_dir,
    )
    if not candidate_rows:
        hint = build_empty_candidate_hint(top_reject_reasons)
        if config.allow_empty:
            print("completed (EMPTY): no candidate emitted")
            print("generator debug=%s" % debug_path)
            print("generator run log=%s" % run_log_path)
            return None
        raise GeneratorError(
            "本次未生成任何 candidate；hint=%s；top reasons=%s；详见 %s 和 %s"
            % (hint, format_top_reason_summary(top_reject_reasons), debug_path, run_log_path)
        )

    path = emit_candidate_csv(candidate_rows, config.generation_batch_id, config.output_dir)
    print("candidate rows=%s" % len(candidate_rows))
    print("generator debug=%s" % debug_path)
    print("generator run log=%s" % run_log_path)
    print("candidate csv=%s" % path)
    return path


def main() -> None:
    config = parse_args()
    run_generator(config)


if __name__ == "__main__":
    main()
