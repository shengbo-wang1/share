#!/usr/bin/env python3
"""Run manifest-driven local fixture smoke suites for generator/publish."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_OUTPUT_DIR = "output/fixture_smoke"
SCRIPT_DIR = Path(__file__).resolve().parent
TESTDATA_DIR = SCRIPT_DIR / "testdata"
FIXED_FIXTURE_ROOT = TESTDATA_DIR / "fixed_e2e_fixture"
PUBLISH_FAILURE_FIXTURE_ROOT = TESTDATA_DIR / "publish_failure_fixture"
GENERATOR_FAILURE_FIXTURE_ROOT = TESTDATA_DIR / "generator_failure_fixture"
GENERATOR_STABILITY_FIXTURE_ROOT = TESTDATA_DIR / "generator_stability_fixture"


def load_local_module(name: str, filename: str):
    module_path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


challenge_generator = load_local_module("fixture_smoke_challenge_generator", "challenge_generator.py")
review_publish = load_local_module("fixture_smoke_review_publish", "review_publish.py")


@dataclass
class SmokeConfig:
    smoke_batch_id: str
    output_dir: str


def parse_args() -> SmokeConfig:
    parser = argparse.ArgumentParser(description="Run repo fixture smoke suites")
    parser.add_argument("--smoke-batch-id", default=None, help="可选，不传则自动生成")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="smoke 输出根目录")
    args = parser.parse_args()
    return SmokeConfig(
        smoke_batch_id=args.smoke_batch_id or ("fixture-smoke-" + uuid.uuid4().hex[:12]),
        output_dir=args.output_dir,
    )


def read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def serialize_json(payload: Dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def derive_reviewed_from_candidate(candidate_row: Dict[str, str], reviewed_csv: Path, generation_batch_id: str) -> Path:
    reviewed_fields = [
        "candidate_key",
        "code",
        "start_date",
        "end_date",
        "primary_tag",
        "secondary_tag",
        "difficulty",
        "score_explain_json",
        "rule_flags_json",
        "generation_batch_id",
        "review_status",
        "review_comment",
        "adjusted_primary_tag",
        "adjusted_difficulty",
        "reviewer",
        "reviewed_at",
        "publish_flag",
    ]
    reviewed_row = dict(candidate_row)
    reviewed_row.update(
        {
            "generation_batch_id": generation_batch_id,
            "review_status": "APPROVED",
            "review_comment": "derived by fixture_smoke",
            "adjusted_primary_tag": "",
            "adjusted_difficulty": "",
            "reviewer": "fixture-smoke",
            "reviewed_at": "2026-03-22T10:00:00",
            "publish_flag": "YES",
        }
    )
    reviewed_csv.parent.mkdir(parents=True, exist_ok=True)
    with reviewed_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=reviewed_fields)
        writer.writeheader()
        writer.writerow(reviewed_row)
    return reviewed_csv


def build_summary_row(
    suite: str,
    case_id: str,
    expected_outcome: Dict[str, object],
    actual_status: str,
    passed: bool,
    key_output_path: Path,
    message: str,
) -> Dict[str, object]:
    return {
        "suite": suite,
        "case_id": case_id,
        "expected_outcome": serialize_json(expected_outcome),
        "actual_status": actual_status,
        "pass": str(bool(passed)).lower(),
        "key_output_path": str(key_output_path),
        "message": message,
    }


def run_fixed_success_suite(root_dir: Path) -> Dict[str, object]:
    fixed_manifest = read_json(FIXED_FIXTURE_ROOT / "manifest.json")
    case_root = ensure_dir(root_dir / "fixed_success")
    generator_output_dir = ensure_dir(case_root / "generator")
    publish_output_dir = ensure_dir(case_root / "publish")

    challenge_generator.run_generator(
        challenge_generator.Config(
            generation_batch_id=str(fixed_manifest["generator"]["generation_batch_id"]),
            output_dir=str(generator_output_dir),
            bootstrap_output_dir=str(FIXED_FIXTURE_ROOT / "bootstrap_output"),
            stock_basic_csv=None,
            raw_csv=None,
            feature_csv=None,
            index_feature_csv=None,
            calendar_csv=None,
            trade_date_from=str(fixed_manifest["generator"]["trade_date_from"]),
            trade_date_to=str(fixed_manifest["generator"]["trade_date_to"]),
        )
    )
    candidate_rows = read_csv_rows(generator_output_dir / ("candidate_%s.csv" % fixed_manifest["generator"]["generation_batch_id"]))
    reviewed_csv = derive_reviewed_from_candidate(
        candidate_rows[0],
        case_root / "reviewed_candidate_fixture-e2e.csv",
        str(fixed_manifest["generator"]["generation_batch_id"]),
    )
    output_paths = review_publish.publish_reviewed_candidates(
        review_publish.Config(
            publish_batch_id=str(fixed_manifest["publish"]["publish_batch_id"]),
            reviewed_csv=str(reviewed_csv),
            raw_csv=str(FIXED_FIXTURE_ROOT / "bootstrap_output" / "bootstrap-fixture-e2e" / "stock_daily_raw.csv"),
            feature_csv=str(FIXED_FIXTURE_ROOT / "bootstrap_output" / "bootstrap-fixture-e2e" / "stock_daily_feature.csv"),
            output_dir=str(publish_output_dir),
            generator_output_dir=str(generator_output_dir),
            bootstrap_output_dir=str(FIXED_FIXTURE_ROOT / "bootstrap_output"),
            mysql_dsn=None,
        )
    )
    run_log_rows = read_csv_rows(output_paths["run_log"])
    challenge_rows = read_csv_rows(output_paths["challenge"])
    passed = bool(
        run_log_rows
        and run_log_rows[0]["status"] == "SUCCESS"
        and len(candidate_rows) == 1
        and len(challenge_rows) == 1
        and challenge_rows[0]["challenge_id"] == fixed_manifest["publish"]["expected_challenge_id"]
    )
    return build_summary_row(
        suite="fixed_success",
        case_id="fixed_e2e",
        expected_outcome={
            "candidate_count": 1,
            "challenge_id": fixed_manifest["publish"]["expected_challenge_id"],
            "run_log_status": "SUCCESS",
        },
        actual_status=run_log_rows[0]["status"] if run_log_rows else "MISSING_RUN_LOG",
        passed=passed,
        key_output_path=output_paths["run_log"],
        message="" if passed else "fixed success suite mismatch",
    )


def run_publish_failure_suite(root_dir: Path) -> List[Dict[str, object]]:
    manifest = read_json(PUBLISH_FAILURE_FIXTURE_ROOT / "manifest.json")
    raw_csv = (PUBLISH_FAILURE_FIXTURE_ROOT / manifest["shared_input_source"]["raw_csv"]).resolve()
    feature_csv = (PUBLISH_FAILURE_FIXTURE_ROOT / manifest["shared_input_source"]["feature_csv"]).resolve()
    rows = []
    for case in manifest["cases"]:
        case_root = ensure_dir(root_dir / ("publish_fail_%s" % case["case_id"]))
        output_dir = ensure_dir(case_root / "publish")
        preseed_challenge_id = case.get("preseed_existing_challenge_id")
        if preseed_challenge_id:
            with (output_dir / "challenge_preseed.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["challenge_id", "code", "start_date", "end_date"])
                writer.writeheader()
                writer.writerow(
                    {
                        "challenge_id": preseed_challenge_id,
                        "code": "600519.SH",
                        "start_date": "2024-01-02",
                        "end_date": "2024-01-29",
                    }
                )

        reviewed_csv = (PUBLISH_FAILURE_FIXTURE_ROOT / case["reviewed_csv"]).resolve()
        expected = case["expected"]
        error_text = None
        output_paths = None
        try:
            output_paths = review_publish.publish_reviewed_candidates(
                review_publish.Config(
                    publish_batch_id=str(case["publish_batch_id"]),
                    reviewed_csv=str(reviewed_csv),
                    raw_csv=str(raw_csv),
                    feature_csv=str(feature_csv),
                    output_dir=str(output_dir),
                    generator_output_dir=str(case_root / "generator"),
                    bootstrap_output_dir=str(FIXED_FIXTURE_ROOT / "bootstrap_output"),
                    mysql_dsn=None,
                )
            )
        except review_publish.PublishError as exc:
            error_text = str(exc)

        if expected["raises_publish_error"]:
            run_log_path = output_dir / ("publish_run_log_%s.csv" % case["publish_batch_id"])
            run_log_rows = read_csv_rows(run_log_path)
            passed = bool(
                error_text
                and expected["expected_input_issue_reason"] in error_text
                and run_log_rows
                and run_log_rows[0]["status"] == expected["run_log_status"]
            )
            rows.append(
                build_summary_row(
                    suite="publish_failure",
                    case_id=str(case["case_id"]),
                    expected_outcome=expected,
                    actual_status=run_log_rows[0]["status"] if run_log_rows else "MISSING_RUN_LOG",
                    passed=passed,
                    key_output_path=run_log_path,
                    message=error_text or "",
                )
            )
            continue

        run_log_rows = read_csv_rows(output_paths["run_log"]) if output_paths else []
        failed_rows = read_csv_rows(output_paths["failed"]) if output_paths else []
        passed = bool(
            output_paths
            and run_log_rows
            and run_log_rows[0]["status"] == expected["run_log_status"]
            and len(failed_rows) == int(expected["failed_count"])
            and failed_rows
            and failed_rows[0]["fail_reason"] == expected["fail_reason"]
        )
        rows.append(
            build_summary_row(
                suite="publish_failure",
                case_id=str(case["case_id"]),
                expected_outcome=expected,
                actual_status=run_log_rows[0]["status"] if run_log_rows else "MISSING_RUN_LOG",
                passed=passed,
                key_output_path=output_paths["run_log"] if output_paths else output_dir,
                message=failed_rows[0]["fail_message"] if failed_rows else (error_text or ""),
            )
        )
    return rows


def run_generator_failure_suite(root_dir: Path) -> List[Dict[str, object]]:
    manifest = read_json(GENERATOR_FAILURE_FIXTURE_ROOT / "manifest.json")
    rows = []
    for case in manifest["cases"]:
        case_root = ensure_dir(root_dir / ("generator_fail_%s" % case["case_id"]))
        output_dir = ensure_dir(case_root / "generator")
        input_dir = (GENERATOR_FAILURE_FIXTURE_ROOT / case["input_dir"]).resolve()
        expected = case["expected"]
        error_text = None
        try:
            challenge_generator.run_generator(
                challenge_generator.Config(
                    generation_batch_id=str(case["generation_batch_id"]),
                    output_dir=str(output_dir),
                    bootstrap_output_dir=str(input_dir.parent),
                    stock_basic_csv=str(input_dir / "stock_basic.csv"),
                    raw_csv=str(input_dir / "stock_daily_raw.csv"),
                    feature_csv=str(input_dir / "stock_daily_feature.csv"),
                    index_feature_csv=None,
                    calendar_csv=None,
                    trade_date_from=str(case["trade_date_from"]),
                    trade_date_to=str(case["trade_date_to"]),
                    allow_empty=True,
                )
            )
        except challenge_generator.GeneratorError as exc:
            error_text = str(exc)

        run_log_path = output_dir / ("generator_run_log_%s.csv" % case["generation_batch_id"])
        debug_path = output_dir / ("generator_debug_%s.csv" % case["generation_batch_id"])
        candidate_path = output_dir / ("candidate_%s.csv" % case["generation_batch_id"])
        run_log_rows = read_csv_rows(run_log_path)
        debug_text = debug_path.read_text(encoding="utf-8") if debug_path.exists() else ""
        candidate_rows = read_csv_rows(candidate_path) if candidate_path.exists() else []
        passed = bool(
            not error_text
            and run_log_rows
            and run_log_rows[0]["status"] == expected["run_log_status"]
            and int(run_log_rows[0]["candidate_count"]) == int(expected["candidate_count"])
            and all(reason in debug_text for reason in expected["expected_debug_reasons"])
        )
        if passed and int(expected["candidate_count"]) > 0:
            for key, value in expected["candidate"].items():
                if not candidate_rows or candidate_rows[0].get(key) != value:
                    passed = False
                    break

        rows.append(
            build_summary_row(
                suite="generator_failure",
                case_id=str(case["case_id"]),
                expected_outcome=expected,
                actual_status=run_log_rows[0]["status"] if run_log_rows else "MISSING_RUN_LOG",
                passed=passed,
                key_output_path=run_log_path,
                message=error_text or "",
            )
        )
    return rows


def run_generator_stability_suite(root_dir: Path) -> List[Dict[str, object]]:
    manifest = read_json(GENERATOR_STABILITY_FIXTURE_ROOT / "manifest.json")
    rows = []
    for case in manifest["cases"]:
        case_root = ensure_dir(root_dir / ("generator_stability_%s" % case["case_id"]))
        output_dir = ensure_dir(case_root / "generator")
        input_dir = (GENERATOR_STABILITY_FIXTURE_ROOT / case["input_dir"]).resolve()
        expected = case["expected"]
        error_text = None
        try:
            challenge_generator.run_generator(
                challenge_generator.Config(
                    generation_batch_id=str(case["generation_batch_id"]),
                    output_dir=str(output_dir),
                    bootstrap_output_dir=str(input_dir.parent),
                    stock_basic_csv=str(input_dir / "stock_basic.csv"),
                    raw_csv=str(input_dir / "stock_daily_raw.csv"),
                    feature_csv=str(input_dir / "stock_daily_feature.csv"),
                    index_feature_csv=None,
                    calendar_csv=None,
                    trade_date_from=str(case["trade_date_from"]),
                    trade_date_to=str(case["trade_date_to"]),
                )
            )
        except challenge_generator.GeneratorError as exc:
            error_text = str(exc)

        run_log_path = output_dir / ("generator_run_log_%s.csv" % case["generation_batch_id"])
        debug_path = output_dir / ("generator_debug_%s.csv" % case["generation_batch_id"])
        candidate_path = output_dir / ("candidate_%s.csv" % case["generation_batch_id"])
        run_log_rows = read_csv_rows(run_log_path)
        debug_text = debug_path.read_text(encoding="utf-8") if debug_path.exists() else ""
        candidate_rows = read_csv_rows(candidate_path) if candidate_path.exists() else []
        passed = bool(
            not error_text
            and run_log_rows
            and run_log_rows[0]["status"] == expected["run_log_status"]
            and int(run_log_rows[0]["candidate_count"]) == int(expected["candidate_count"])
            and all(reason in debug_text for reason in expected["expected_debug_reasons"])
            and candidate_rows
        )
        if passed:
            for key, value in expected["candidate"].items():
                if candidate_rows[0].get(key) != value:
                    passed = False
                    break

        rows.append(
            build_summary_row(
                suite="generator_stability",
                case_id=str(case["case_id"]),
                expected_outcome=expected,
                actual_status=run_log_rows[0]["status"] if run_log_rows else "MISSING_RUN_LOG",
                passed=passed,
                key_output_path=run_log_path,
                message=error_text or "",
            )
        )
    return rows


def emit_summary(rows: List[Dict[str, object]], root_dir: Path, smoke_batch_id: str) -> Dict[str, Path]:
    csv_path = root_dir / ("smoke_summary_%s.csv" % smoke_batch_id)
    json_path = root_dir / ("smoke_summary_%s.json" % smoke_batch_id)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["suite", "case_id", "expected_outcome", "actual_status", "pass", "key_output_path", "message"],
        )
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"csv": csv_path, "json": json_path}


def run_fixture_smoke(config: SmokeConfig) -> Dict[str, object]:
    root_dir = Path(config.output_dir) / config.smoke_batch_id
    if root_dir.exists():
        shutil.rmtree(root_dir)
    ensure_dir(root_dir)
    rows: List[Dict[str, object]] = []
    rows.append(run_fixed_success_suite(root_dir))
    rows.extend(run_publish_failure_suite(root_dir))
    rows.extend(run_generator_failure_suite(root_dir))
    rows.extend(run_generator_stability_suite(root_dir))
    summary_paths = emit_summary(rows, root_dir, config.smoke_batch_id)
    passed_count = sum(1 for row in rows if row["pass"] == "true")
    failed_count = len(rows) - passed_count
    return {
        "root_dir": root_dir,
        "summary_csv": summary_paths["csv"],
        "summary_json": summary_paths["json"],
        "rows": rows,
        "passed_count": passed_count,
        "failed_count": failed_count,
    }


def main() -> None:
    config = parse_args()
    result = run_fixture_smoke(config)
    print("fixture smoke root=%s" % result["root_dir"])
    print("fixture smoke summary csv=%s" % result["summary_csv"])
    print("fixture smoke summary json=%s" % result["summary_json"])
    print("fixture smoke result: pass=%s fail=%s" % (result["passed_count"], result["failed_count"]))
    if result["failed_count"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
