#!/usr/bin/env python3
"""Reviewed candidate publish tool（最小可运行版）。

用途：
1. 读取 reviewed_candidate_{generation_batch_id}.csv
2. 校验审核状态与人工微调边界
3. 构建 challenge / challenge_day
4. 输出 publish_success / publish_failed / challenge / challenge_day CSV
5. 可选写入 MySQL

依赖（自行安装）：
    pip install pandas sqlalchemy pymysql
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


WINDOW_DAYS = 20
DEFAULT_GENERATOR_OUTPUT_DIR = "output/challenge_generator"
DEFAULT_BOOTSTRAP_OUTPUT_DIR = "output/akshare_bootstrap"
DEFAULT_OUTPUT_DIR = "output/review_publish"

REVIEW_STATUS_APPROVED = "APPROVED"
PUBLISH_FLAG_YES = "YES"
TAG_SHORT_MAP = {
    "下跌中继 vs 真见底": "bottom",
    "放量突破 vs 假突破": "breakout",
    "高位放量阴线": "highvolbear",
    "缩量回踩均线": "pullback",
    "大盘恐慌日该不该抄底": "panic",
    "连续上涨后该持有还是止盈": "takeprofit",
}
VALID_TAGS = set(TAG_SHORT_MAP.keys())
VALID_DIFFICULTIES = {"easy", "normal", "hard"}


@dataclass
class Config:
    publish_batch_id: str
    reviewed_csv: Optional[str]
    raw_csv: Optional[str]
    feature_csv: Optional[str]
    output_dir: str
    generator_output_dir: str
    bootstrap_output_dir: str
    mysql_dsn: Optional[str]


class PublishError(RuntimeError):
    """Raised when the publish flow cannot continue."""


class PublishInputError(PublishError):
    """Raised when reviewed/raw/feature inputs are missing or invalid."""

    def __init__(self, message: str, issues: List[Dict[str, object]]):
        self.issues = issues
        super().__init__(message)


class DataBundle:
    def __init__(self, reviewed_df, raw_df, feature_df):
        self.reviewed_df = reviewed_df
        self.raw_df = raw_df
        self.feature_df = feature_df


REQUIRED_REVIEWED_COLUMNS = [
    "candidate_key",
    "code",
    "start_date",
    "end_date",
    "primary_tag",
    "difficulty",
    "generation_batch_id",
    "review_status",
    "review_comment",
    "adjusted_primary_tag",
    "adjusted_difficulty",
    "reviewer",
    "reviewed_at",
    "publish_flag",
]
REQUIRED_RAW_COLUMNS = ["code", "trade_date", "open_price", "close_price"]
REQUIRED_FEATURE_COLUMNS = [
    "code",
    "trade_date",
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
    "cap_bucket",
]


def lazy_import_pandas():
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise PublishError("缺少 pandas，请先执行: pip install pandas") from exc
    return pd


def lazy_import_sqlalchemy():
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise PublishError("缺少 sqlalchemy，请先执行: pip install sqlalchemy pymysql") from exc
    return create_engine, text


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Reviewed candidate publish minimal runner")
    parser.add_argument("--publish-batch-id", default=None, help="可选，不传则自动生成")
    parser.add_argument("--reviewed-csv", default=None, help="reviewed_candidate.csv 路径")
    parser.add_argument("--raw-csv", default=None, help="stock_daily_raw.csv 路径")
    parser.add_argument("--feature-csv", default=None, help="stock_daily_feature.csv 路径")
    parser.add_argument("--generator-output-dir", default=DEFAULT_GENERATOR_OUTPUT_DIR, help="generator 输出根目录")
    parser.add_argument("--bootstrap-output-dir", default=DEFAULT_BOOTSTRAP_OUTPUT_DIR, help="bootstrap 输出根目录")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="publish 输出目录")
    parser.add_argument("--mysql-dsn", default=None, help="可选，MySQL DSN，例如 mysql+pymysql://user:pass@host:3306/db")
    args = parser.parse_args()

    publish_batch_id = args.publish_batch_id or ("publish-" + uuid.uuid4().hex[:12])
    return Config(
        publish_batch_id=publish_batch_id,
        reviewed_csv=args.reviewed_csv,
        raw_csv=args.raw_csv,
        feature_csv=args.feature_csv,
        output_dir=args.output_dir,
        generator_output_dir=args.generator_output_dir,
        bootstrap_output_dir=args.bootstrap_output_dir,
        mysql_dsn=args.mysql_dsn or os.getenv("SHARE_MYSQL_DSN"),
    )


def latest_file(root_dir: str, pattern: str) -> Path:
    root = Path(root_dir)
    if not root.exists():
        raise PublishError("目录不存在: %s" % root)
    candidates = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise PublishError("未找到匹配文件: %s/%s" % (root, pattern))
    return candidates[-1]


def read_batch_status(batch_dir: Path) -> Optional[str]:
    job_log_path = batch_dir / "job_run_log.csv"
    if not job_log_path.exists():
        return None
    pd = lazy_import_pandas()
    frame = pd.read_csv(job_log_path)
    if frame.empty or "status" not in frame.columns:
        return None
    status = str(frame.iloc[0].get("status", "") or "").strip().upper()
    return status or None


def latest_batch_dir(root_dir: str) -> Path:
    root = Path(root_dir)
    if not root.exists():
        raise PublishError("目录不存在: %s" % root)
    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        raise PublishError("未找到批次目录: %s" % root)
    successful = [path for path in candidates if read_batch_status(path) in ["SUCCESS", "PARTIAL_SUCCESS"]]
    if successful:
        return max(successful, key=lambda path: path.stat().st_mtime)
    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_input_paths(config: Config) -> Dict[str, Path]:
    bootstrap_latest = None if (config.raw_csv and config.feature_csv) else latest_batch_dir(config.bootstrap_output_dir)

    reviewed_csv = Path(config.reviewed_csv) if config.reviewed_csv else latest_file(config.generator_output_dir, "reviewed_candidate_*.csv")
    raw_csv = Path(config.raw_csv) if config.raw_csv else bootstrap_latest / "stock_daily_raw.csv"
    feature_csv = Path(config.feature_csv) if config.feature_csv else bootstrap_latest / "stock_daily_feature.csv"

    for path, label in [(reviewed_csv, "reviewed_csv"), (raw_csv, "raw_csv"), (feature_csv, "feature_csv")]:
        if not path.exists():
            raise PublishError("缺少必要输入文件 %s: %s" % (label, path))

    return {"reviewed_csv": reviewed_csv, "raw_csv": raw_csv, "feature_csv": feature_csv}


def read_csv(path: Path):
    pd = lazy_import_pandas()
    return pd.read_csv(path)


def build_publish_issue(reason: str, detail: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    return {"reason": reason, "detail": detail or {}}


def validate_columns(frame, required_columns: Sequence[str]) -> List[str]:
    if frame.empty:
        return []
    return [column for column in required_columns if column not in frame.columns]


def summarize_publish_issues(issues: Sequence[Dict[str, object]]) -> str:
    parts = []
    for issue in issues:
        reason = str(issue.get("reason", "") or "")
        detail = json.dumps(issue.get("detail", {}), ensure_ascii=False, separators=(",", ":"))
        parts.append("%s%s" % (reason, ("(%s)" % detail) if detail and detail != "{}" else ""))
    return "; ".join(parts)


def summarize_fail_reasons(failed_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    counter = {}
    for row in failed_rows:
        reason = str(row.get("fail_reason", "") or "").strip()
        if not reason:
            continue
        counter[reason] = counter.get(reason, 0) + 1
    return [{"reason": reason, "count": count} for reason, count in sorted(counter.items(), key=lambda item: item[1], reverse=True)[:10]]


def emit_publish_run_log(summary_row: Dict[str, object], publish_batch_id: str, output_dir: str) -> Path:
    pd = lazy_import_pandas()
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / ("publish_run_log_%s.csv" % publish_batch_id)
    frame = pd.DataFrame(
        [summary_row],
        columns=[
            "publish_batch_id",
            "reviewed_row_count",
            "approved_row_count",
            "success_count",
            "failed_count",
            "top_fail_reasons_json",
            "status",
            "status_message",
            "input_summary_json",
        ],
    )
    frame.to_csv(path, index=False)
    return path


def load_data_bundle(config: Config) -> DataBundle:
    pd = lazy_import_pandas()
    paths = resolve_input_paths(config)
    reviewed_df = read_csv(paths["reviewed_csv"])
    raw_df = read_csv(paths["raw_csv"])
    feature_df = read_csv(paths["feature_csv"])
    issues: List[Dict[str, object]] = []

    if reviewed_df.empty:
        issues.append(build_publish_issue("REVIEWED_CSV_EMPTY", {"path": str(paths["reviewed_csv"])}))
    if raw_df.empty:
        issues.append(build_publish_issue("RAW_CSV_EMPTY", {"path": str(paths["raw_csv"])}))
    if feature_df.empty:
        issues.append(build_publish_issue("FEATURE_CSV_EMPTY", {"path": str(paths["feature_csv"])}))

    reviewed_missing = validate_columns(reviewed_df, REQUIRED_REVIEWED_COLUMNS)
    raw_missing = validate_columns(raw_df, REQUIRED_RAW_COLUMNS)
    feature_missing = validate_columns(feature_df, REQUIRED_FEATURE_COLUMNS)
    if reviewed_missing:
        issues.append(build_publish_issue("REVIEWED_CSV_MISSING_COLUMNS", {"missing_columns": reviewed_missing, "path": str(paths["reviewed_csv"])}))
    if raw_missing:
        issues.append(build_publish_issue("RAW_CSV_MISSING_COLUMNS", {"missing_columns": raw_missing, "path": str(paths["raw_csv"])}))
    if feature_missing:
        issues.append(build_publish_issue("FEATURE_CSV_MISSING_COLUMNS", {"missing_columns": feature_missing, "path": str(paths["feature_csv"])}))
    if issues:
        raise PublishInputError("publish 输入校验失败: %s" % summarize_publish_issues(issues), issues)

    for frame in [reviewed_df, raw_df, feature_df]:
        if "start_date" in frame.columns:
            frame["start_date"] = pd.to_datetime(frame["start_date"], errors="coerce").dt.date
        if "end_date" in frame.columns:
            frame["end_date"] = pd.to_datetime(frame["end_date"], errors="coerce").dt.date
        if "trade_date" in frame.columns:
            frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
        if "reviewed_at" in frame.columns:
            frame["reviewed_at"] = pd.to_datetime(frame["reviewed_at"], errors="coerce")

    for column in ["candidate_key", "code", "primary_tag", "secondary_tag", "difficulty", "generation_batch_id", "review_status", "review_comment", "adjusted_primary_tag", "adjusted_difficulty", "reviewer", "publish_flag"]:
        if column in reviewed_df.columns:
            reviewed_df[column] = reviewed_df[column].fillna("")

    raw_df["code"] = raw_df["code"].astype(str)
    feature_df["code"] = feature_df["code"].astype(str)
    reviewed_df["code"] = reviewed_df["code"].astype(str)
    return DataBundle(reviewed_df, raw_df, feature_df)


def pass_review_gate(row) -> Tuple[bool, Optional[str]]:
    review_status = str(row.get("review_status", "") or "")
    publish_flag = str(row.get("publish_flag", "") or "")
    reviewer = str(row.get("reviewer", "") or "").strip()
    reviewed_at = row.get("reviewed_at")
    adjusted_primary_tag = str(row.get("adjusted_primary_tag", "") or "").strip()
    adjusted_difficulty = str(row.get("adjusted_difficulty", "") or "").strip()

    if review_status != REVIEW_STATUS_APPROVED:
        return False, "REVIEW_STATUS_NOT_APPROVED"
    if publish_flag != PUBLISH_FLAG_YES:
        return False, "PUBLISH_FLAG_NOT_YES"
    if not reviewer:
        return False, "REVIEWER_REQUIRED"
    if reviewed_at is None or str(reviewed_at) == "NaT":
        return False, "REVIEWED_AT_REQUIRED"
    if adjusted_primary_tag and adjusted_difficulty:
        return False, "DUAL_ADJUSTMENT_NOT_ALLOWED"
    return True, None


def normalize_review_row(row) -> Dict[str, object]:
    primary_tag = str(row.get("adjusted_primary_tag", "") or "").strip() or str(row.get("primary_tag", "") or "").strip()
    difficulty = str(row.get("adjusted_difficulty", "") or "").strip() or str(row.get("difficulty", "") or "").strip()
    secondary_tag = str(row.get("secondary_tag", "") or "").strip() or None
    return {
        "candidate_key": str(row.get("candidate_key", "") or ""),
        "code": str(row.get("code", "") or ""),
        "start_date": row.get("start_date"),
        "end_date": row.get("end_date"),
        "primary_tag": primary_tag,
        "secondary_tag": secondary_tag,
        "difficulty": difficulty,
        "generation_batch_id": str(row.get("generation_batch_id", "") or ""),
        "review_status": str(row.get("review_status", "") or ""),
        "review_comment": str(row.get("review_comment", "") or ""),
        "reviewer": str(row.get("reviewer", "") or ""),
        "reviewed_at": row.get("reviewed_at"),
        "publish_flag": str(row.get("publish_flag", "") or ""),
        "score_explain_json": str(row.get("score_explain_json", "") or ""),
        "rule_flags_json": str(row.get("rule_flags_json", "") or ""),
        "adjusted_primary_tag": str(row.get("adjusted_primary_tag", "") or ""),
        "adjusted_difficulty": str(row.get("adjusted_difficulty", "") or ""),
        "version": "v1",
    }


def build_challenge_id(normalized_row: Dict[str, object]) -> str:
    primary_tag = normalized_row["primary_tag"]
    if primary_tag not in TAG_SHORT_MAP:
        raise PublishError("未知 primary_tag，无法生成 challenge_id: %s" % primary_tag)
    return "%s_%s_%s_%s" % (
        normalized_row["code"],
        normalized_row["start_date"],
        TAG_SHORT_MAP[primary_tag],
        normalized_row["version"],
    )


def build_tags_json(normalized_row: Dict[str, object]) -> str:
    payload = {
        "primaryTag": normalized_row["primary_tag"],
        "secondaryTag": normalized_row["secondary_tag"],
        "tagVersion": "v1",
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_challenge_row(normalized_row: Dict[str, object], challenge_id: str, publish_batch_id: str) -> Dict[str, object]:
    return {
        "challenge_id": challenge_id,
        "code": normalized_row["code"],
        "start_date": normalized_row["start_date"],
        "end_date": normalized_row["end_date"],
        "total_days": WINDOW_DAYS,
        "actionable_days": WINDOW_DAYS - 1,
        "difficulty": normalized_row["difficulty"],
        "tags_json": build_tags_json(normalized_row),
        "featured": 0,
        "reveal_stock_name": 0,
        "template_version": "v1",
        "generation_batch_id": publish_batch_id,
        "freeze_status": "FROZEN",
        "status": "ACTIVE",
    }


def build_challenge_day_rows(normalized_row: Dict[str, object], challenge_id: str, publish_batch_id: str, raw_df, feature_df) -> List[Dict[str, object]]:
    code = normalized_row["code"]
    start_date = normalized_row["start_date"]
    end_date = normalized_row["end_date"]

    raw_code = raw_df[raw_df["code"] == code].sort_values("trade_date").reset_index(drop=True)
    feature_code = feature_df[feature_df["code"] == code].sort_values("trade_date").reset_index(drop=True)
    merged = raw_code.merge(feature_code, on=["code", "trade_date"], suffixes=("_raw", "_feature"))

    if start_date not in set(merged["trade_date"].tolist()):
        raise PublishError("start_date 不在行情数据中: %s %s" % (code, start_date))

    start_idx = merged.index[merged["trade_date"] == start_date].tolist()[0]
    window = merged.iloc[start_idx : start_idx + WINDOW_DAYS].copy().reset_index(drop=True)
    if len(window) != WINDOW_DAYS:
        raise PublishError("challenge_day 不足 20 天: %s %s" % (code, start_date))
    if window["trade_date"].iloc[-1] != end_date:
        raise PublishError("reviewed end_date 与窗口结束日期不一致: %s %s" % (code, start_date))

    rows = []
    for idx, row in window.iterrows():
        rows.append(
            {
                "challenge_id": challenge_id,
                "day_index": idx,
                "trade_date": row["trade_date"],
                "generation_batch_id": publish_batch_id,
                "raw_open": row["open_price"],
                "raw_close": row["close_price"],
                "qfq_open": row["qfq_open"],
                "qfq_high": row["qfq_high"],
                "qfq_low": row["qfq_low"],
                "qfq_close": row["qfq_close"],
                "volume": row["volume_feature"],
                "ma5": row["ma5"],
                "ma10": row["ma10"],
                "ma20": row["ma20"],
                "k_value": row["k_value"],
                "d_value": row["d_value"],
                "j_value": row["j_value"],
                "dif": row["dif"],
                "dea": row["dea"],
                "macd": row["macd"],
                "cap_bucket": row["cap_bucket"],
            }
        )
    return rows


def pass_publish_validation(challenge_row: Dict[str, object], challenge_day_rows: List[Dict[str, object]]) -> Tuple[bool, Optional[str]]:
    if not challenge_row["primary_tag"] if "primary_tag" in challenge_row else False:
        return False, "PRIMARY_TAG_EMPTY"
    if not challenge_row["difficulty"]:
        return False, "DIFFICULTY_EMPTY"
    if len(challenge_day_rows) != WINDOW_DAYS:
        return False, "CHALLENGE_DAY_COUNT_INVALID"
    for row in challenge_day_rows:
        required = [
            "raw_open", "raw_close", "qfq_open", "qfq_high", "qfq_low", "qfq_close", "volume", "ma5", "ma10", "ma20", "k_value", "d_value", "j_value", "dif", "dea", "macd", "cap_bucket"
        ]
        for column in required:
            if row.get(column) is None or str(row.get(column)) == "nan":
                return False, "CHALLENGE_DAY_FIELD_MISSING_%s" % column.upper()
    return True, None


def collect_existing_challenge_ids(output_dir: str) -> Set[str]:
    pd = lazy_import_pandas()
    root = Path(output_dir)
    existing: Set[str] = set()
    if not root.exists():
        return existing
    for path in root.glob("challenge_*.csv"):
        try:
            if not path.is_file():
                continue
            if path.stat().st_size == 0:
                continue
            if not path.read_text(encoding="utf-8").strip():
                continue
            frame = pd.read_csv(path)
        except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
            continue
        if "challenge_id" in frame.columns:
            existing.update(frame["challenge_id"].dropna().astype(str).tolist())
    return existing


def fetch_existing_challenge_ids_from_mysql(mysql_dsn: str, challenge_ids: Sequence[str]) -> Set[str]:
    if not challenge_ids:
        return set()
    create_engine, text = lazy_import_sqlalchemy()
    engine = create_engine(mysql_dsn)
    placeholders = ", ".join(":id_%s" % idx for idx in range(len(challenge_ids)))
    params = {"id_%s" % idx: challenge_id for idx, challenge_id in enumerate(challenge_ids)}
    sql = text("SELECT challenge_id FROM challenge WHERE challenge_id IN (%s)" % placeholders)
    with engine.begin() as connection:
        rows = connection.execute(sql, params).fetchall()
    return {str(row[0]) for row in rows}


def chunked_records(frame, chunk_size: int = 500):
    records = frame.to_dict(orient="records")
    for start in range(0, len(records), chunk_size):
        yield records[start : start + chunk_size]


def insert_dataframe(engine, table_name: str, frame) -> None:
    if frame.empty:
        return
    _, text = lazy_import_sqlalchemy()
    columns = list(frame.columns)
    insert_columns = ", ".join("`%s`" % column for column in columns)
    values_clause = ", ".join(":%s" % column for column in columns)
    sql = text("INSERT INTO `{}` ({}) VALUES ({})".format(table_name, insert_columns, values_clause))
    with engine.begin() as connection:
        for records in chunked_records(frame):
            connection.execute(sql, records)


def persist_challenge_bundle(config: Config, challenge_rows: List[Dict[str, object]], challenge_day_rows: List[Dict[str, object]], success_rows: List[Dict[str, object]], failed_rows: List[Dict[str, object]]) -> Dict[str, Path]:
    pd = lazy_import_pandas()
    output_root = Path(config.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    challenge_df = pd.DataFrame(challenge_rows)
    challenge_day_df = pd.DataFrame(challenge_day_rows)
    success_df = pd.DataFrame(success_rows)
    failed_df = pd.DataFrame(failed_rows)

    challenge_path = output_root / ("challenge_%s.csv" % config.publish_batch_id)
    challenge_day_path = output_root / ("challenge_day_%s.csv" % config.publish_batch_id)
    success_path = output_root / ("publish_success_%s.csv" % config.publish_batch_id)
    failed_path = output_root / ("publish_failed_%s.csv" % config.publish_batch_id)

    challenge_df.to_csv(challenge_path, index=False)
    challenge_day_df.to_csv(challenge_day_path, index=False)
    success_df.to_csv(success_path, index=False)
    failed_df.to_csv(failed_path, index=False)

    if config.mysql_dsn and not challenge_df.empty:
        create_engine, _ = lazy_import_sqlalchemy()
        engine = create_engine(config.mysql_dsn)
        insert_dataframe(engine, "challenge", challenge_df)
        insert_dataframe(engine, "challenge_day", challenge_day_df)
        print("已写入 MySQL: %s" % config.mysql_dsn)

    return {
        "challenge": challenge_path,
        "challenge_day": challenge_day_path,
        "success": success_path,
        "failed": failed_path,
    }


def build_failed_row(row, challenge_id: Optional[str], fail_reason: str, fail_message: str) -> Dict[str, object]:
    return {
        "candidate_key": row.get("candidate_key", ""),
        "code": row.get("code", ""),
        "start_date": row.get("start_date"),
        "challenge_id": challenge_id or "",
        "fail_reason": fail_reason,
        "fail_message": fail_message,
    }


def build_success_row(row, challenge_id: str, publish_batch_id: str) -> Dict[str, object]:
    return {
        "candidate_key": row.get("candidate_key", ""),
        "code": row.get("code", ""),
        "start_date": row.get("start_date"),
        "challenge_id": challenge_id,
        "publish_batch_id": publish_batch_id,
    }


def publish_reviewed_candidates(config: Config) -> Dict[str, Path]:
    try:
        data = load_data_bundle(config)
    except PublishInputError as exc:
        run_log_path = emit_publish_run_log(
            {
                "publish_batch_id": config.publish_batch_id,
                "reviewed_row_count": 0,
                "approved_row_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "top_fail_reasons_json": json.dumps(exc.issues, ensure_ascii=False, separators=(",", ":")),
                "status": "FAILED",
                "status_message": str(exc),
                "input_summary_json": json.dumps({}, ensure_ascii=False, separators=(",", ":")),
            },
            config.publish_batch_id,
            config.output_dir,
        )
        raise PublishError("%s；详见 %s" % (exc, run_log_path))

    reviewed_df = data.reviewed_df

    existing_ids = collect_existing_challenge_ids(config.output_dir)
    batch_ids: Set[str] = set()

    success_rows: List[Dict[str, object]] = []
    failed_rows: List[Dict[str, object]] = []
    challenge_rows: List[Dict[str, object]] = []
    challenge_day_rows: List[Dict[str, object]] = []
    approved_row_count = 0

    candidate_conflict_check: List[str] = []
    normalized_rows: List[Tuple[Dict[str, object], Dict[str, object], str]] = []

    for _, row in reviewed_df.iterrows():
        gate_passed, gate_reason = pass_review_gate(row)
        if not gate_passed:
            failed_rows.append(build_failed_row(row, None, gate_reason or "REVIEW_GATE_FAILED", "review gate rejected"))
            continue
        approved_row_count += 1

        normalized = normalize_review_row(row)
        if normalized["primary_tag"] not in VALID_TAGS:
            failed_rows.append(build_failed_row(row, None, "INVALID_PRIMARY_TAG", "primary_tag 不在固定标签范围内"))
            continue
        if normalized["difficulty"] not in VALID_DIFFICULTIES:
            failed_rows.append(build_failed_row(row, None, "INVALID_DIFFICULTY", "difficulty 不在固定范围内"))
            continue
        challenge_id = build_challenge_id(normalized)
        normalized_rows.append((row, normalized, challenge_id))
        candidate_conflict_check.append(challenge_id)

    if config.mysql_dsn:
        existing_ids.update(fetch_existing_challenge_ids_from_mysql(config.mysql_dsn, candidate_conflict_check))

    for row, normalized, challenge_id in normalized_rows:
        if challenge_id in existing_ids or challenge_id in batch_ids:
            failed_rows.append(build_failed_row(row, challenge_id, "CHALLENGE_ID_CONFLICT", "challenge_id 已存在或本批次重复"))
            continue

        try:
            challenge_row = build_challenge_row(normalized, challenge_id, config.publish_batch_id)
            day_rows = build_challenge_day_rows(normalized, challenge_id, config.publish_batch_id, data.raw_df, data.feature_df)
            validation_payload = dict(challenge_row)
            validation_payload["primary_tag"] = normalized["primary_tag"]
            passed, reason = pass_publish_validation(validation_payload, day_rows)
            if not passed:
                failed_rows.append(build_failed_row(row, challenge_id, reason or "PUBLISH_VALIDATION_FAILED", "publish validation failed"))
                continue

            challenge_rows.append(challenge_row)
            challenge_day_rows.extend(day_rows)
            success_rows.append(build_success_row(row, challenge_id, config.publish_batch_id))
            batch_ids.add(challenge_id)
        except Exception as exc:
            failed_rows.append(build_failed_row(row, challenge_id, "PUBLISH_BUILD_FAILED", str(exc)))
    output_paths = persist_challenge_bundle(config, challenge_rows, challenge_day_rows, success_rows, failed_rows)
    top_fail_reasons = summarize_fail_reasons(failed_rows)
    status = "SUCCESS"
    if success_rows and failed_rows:
        status = "PARTIAL_SUCCESS"
    elif failed_rows and not success_rows:
        status = "FAILED"
    elif not success_rows and not failed_rows:
        status = "EMPTY"
    run_log_path = emit_publish_run_log(
        {
            "publish_batch_id": config.publish_batch_id,
            "reviewed_row_count": len(reviewed_df),
            "approved_row_count": approved_row_count,
            "success_count": len(success_rows),
            "failed_count": len(failed_rows),
            "top_fail_reasons_json": json.dumps(top_fail_reasons, ensure_ascii=False, separators=(",", ":")),
            "status": status,
            "status_message": "" if status == "SUCCESS" else ("请优先查看 publish_failed.csv 与 fail_reason 聚合" if failed_rows else "无可发布记录"),
            "input_summary_json": json.dumps(
                {
                    "reviewed_rows": len(reviewed_df),
                    "raw_rows": len(data.raw_df),
                    "feature_rows": len(data.feature_df),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
        config.publish_batch_id,
        config.output_dir,
    )
    output_paths["run_log"] = run_log_path
    return output_paths


def main() -> None:
    config = parse_args()
    output_paths = publish_reviewed_candidates(config)
    print("challenge csv=%s" % output_paths["challenge"])
    print("challenge_day csv=%s" % output_paths["challenge_day"])
    print("success csv=%s" % output_paths["success"])
    print("failed csv=%s" % output_paths["failed"])
    print("run log csv=%s" % output_paths["run_log"])


if __name__ == "__main__":
    main()
