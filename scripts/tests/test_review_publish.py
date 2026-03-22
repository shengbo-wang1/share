import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "testdata" / "fixed_e2e_fixture"
FIXTURE_BOOTSTRAP_BATCH_DIR = FIXTURE_ROOT / "bootstrap_output" / "bootstrap-fixture-e2e"
FIXTURE_REVIEWED_CSV = FIXTURE_ROOT / "reviewed_candidate_fixture-e2e.csv"
FIXTURE_BOOTSTRAP_OUTPUT_DIR = FIXTURE_ROOT / "bootstrap_output"
FIXTURE_MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
FAILURE_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "testdata" / "publish_failure_fixture"
FAILURE_FIXTURE_MANIFEST_PATH = FAILURE_FIXTURE_ROOT / "manifest.json"


def load_module(name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_fixture_manifest():
    with FIXTURE_MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_failure_fixture_manifest():
    with FAILURE_FIXTURE_MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_csv_rows(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class ReviewPublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("review_publish_test_module", "review_publish.py")
        cls.generator_module = load_module("challenge_generator_for_publish_test_module", "challenge_generator.py")

    def build_reviewed_from_candidate(self, candidate_row, reviewed_csv: Path, generation_batch_id: str) -> Path:
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
                "review_comment": "derived from candidate fixture smoke test",
                "adjusted_primary_tag": "",
                "adjusted_difficulty": "",
                "reviewer": "fixture-bot",
                "reviewed_at": "2026-03-22T10:00:00",
                "publish_flag": "YES",
            }
        )
        write_csv(reviewed_csv, [reviewed_row], reviewed_fields)
        return reviewed_csv

    def test_missing_reviewed_columns_emit_run_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reviewed_csv = root / "reviewed.csv"
            raw_csv = root / "raw.csv"
            feature_csv = root / "feature.csv"
            output_dir = root / "output"

            write_csv(
                reviewed_csv,
                [{"candidate_key": "a", "code": "600519.SH", "start_date": "2024-01-02", "end_date": "2024-01-29", "primary_tag": "下跌中继 vs 真见底", "difficulty": "easy", "generation_batch_id": "g1", "review_status": "APPROVED"}],
                ["candidate_key", "code", "start_date", "end_date", "primary_tag", "difficulty", "generation_batch_id", "review_status"],
            )
            write_csv(
                raw_csv,
                [{"code": "600519.SH", "trade_date": "2024-01-02", "open_price": 1, "close_price": 2}],
                ["code", "trade_date", "open_price", "close_price"],
            )
            write_csv(
                feature_csv,
                [{"code": "600519.SH", "trade_date": "2024-01-02", "qfq_open": 1, "qfq_high": 2, "qfq_low": 1, "qfq_close": 2, "volume": 1, "ma5": 1, "ma10": 1, "ma20": 1, "k_value": 1, "d_value": 1, "j_value": 1, "dif": 1, "dea": 1, "macd": 1, "cap_bucket": "large"}],
                ["code", "trade_date", "qfq_open", "qfq_high", "qfq_low", "qfq_close", "volume", "ma5", "ma10", "ma20", "k_value", "d_value", "j_value", "dif", "dea", "macd", "cap_bucket"],
            )

            config = self.module.Config(
                publish_batch_id="publish-missing-cols",
                reviewed_csv=str(reviewed_csv),
                raw_csv=str(raw_csv),
                feature_csv=str(feature_csv),
                output_dir=str(output_dir),
                generator_output_dir=str(root / "generator"),
                bootstrap_output_dir=str(root / "bootstrap"),
                mysql_dsn=None,
            )

            with self.assertRaises(self.module.PublishError) as ctx:
                self.module.publish_reviewed_candidates(config)

            self.assertIn("REVIEWED_CSV_MISSING_COLUMNS", str(ctx.exception))
            run_log_path = output_dir / "publish_run_log_publish-missing-cols.csv"
            self.assertTrue(run_log_path.exists())
            self.assertIn("FAILED", run_log_path.read_text(encoding="utf-8"))

    def test_latest_batch_dir_prefers_success_batch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_success = root / "bootstrap-success"
            new_failed = root / "bootstrap-failed"
            old_success.mkdir()
            new_failed.mkdir()
            write_csv(old_success / "job_run_log.csv", [{"status": "SUCCESS"}], ["status"])
            write_csv(new_failed / "job_run_log.csv", [{"status": "FAILED"}], ["status"])

            chosen = self.module.latest_batch_dir(str(root))
            self.assertEqual(chosen.name, "bootstrap-success")

    def test_collect_existing_challenge_ids_skips_empty_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "challenge_empty.csv").write_text("\n", encoding="utf-8")
            write_csv(
                output_dir / "challenge_valid.csv",
                [{"challenge_id": "600519.SH_2024-01-02_breakout_v1"}],
                ["challenge_id"],
            )

            existing_ids = self.module.collect_existing_challenge_ids(str(output_dir))
            self.assertEqual(existing_ids, {"600519.SH_2024-01-02_breakout_v1"})

    def test_publish_failure_fixture_still_runs_with_empty_existing_challenge_csv(self):
        manifest = load_failure_fixture_manifest()
        case = [item for item in manifest["cases"] if item["case_id"] == "dual_adjustment"][0]
        shared_input = manifest["shared_input_source"]
        raw_csv = (FAILURE_FIXTURE_ROOT / shared_input["raw_csv"]).resolve()
        feature_csv = (FAILURE_FIXTURE_ROOT / shared_input["feature_csv"]).resolve()
        reviewed_csv = (FAILURE_FIXTURE_ROOT / case["reviewed_csv"]).resolve()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "publish-output"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "challenge_stale_empty.csv").write_text("\n", encoding="utf-8")

            output_paths = self.module.publish_reviewed_candidates(
                self.module.Config(
                    publish_batch_id=case["publish_batch_id"],
                    reviewed_csv=str(reviewed_csv),
                    raw_csv=str(raw_csv),
                    feature_csv=str(feature_csv),
                    output_dir=str(output_dir),
                    generator_output_dir=str(Path(tmpdir) / "generator"),
                    bootstrap_output_dir=str(FIXTURE_BOOTSTRAP_OUTPUT_DIR),
                    mysql_dsn=None,
                )
            )

            failed_rows = read_csv_rows(output_paths["failed"])
            self.assertEqual(len(failed_rows), 1)
            self.assertEqual(failed_rows[0]["fail_reason"], "DUAL_ADJUSTMENT_NOT_ALLOWED")

    def test_static_reviewed_fixture_matches_manifest(self):
        manifest = load_fixture_manifest()
        expected = manifest["static_reviewed_fixture"]
        with FIXTURE_REVIEWED_CSV.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        for key, value in expected["expected_core_fields"].items():
            self.assertEqual(row[key], value)
        self.assertEqual(json.loads(row["score_explain_json"]), expected["minimal_score_explain_json"])
        self.assertEqual(json.loads(row["rule_flags_json"]), expected["minimal_rule_flags_json"])

    def test_fixed_e2e_fixture_publish_succeeds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = load_fixture_manifest()
            generator_output_dir = Path(tmpdir) / "generator-output"
            publish_output_dir = Path(tmpdir) / "publish-output"
            candidate_path = self.generator_module.run_generator(
                self.generator_module.Config(
                    generation_batch_id=manifest["generator"]["generation_batch_id"],
                    output_dir=str(generator_output_dir),
                    bootstrap_output_dir=str(FIXTURE_BOOTSTRAP_OUTPUT_DIR),
                    stock_basic_csv=None,
                    raw_csv=None,
                    feature_csv=None,
                    index_feature_csv=None,
                    calendar_csv=None,
                    trade_date_from=manifest["generator"]["trade_date_from"],
                    trade_date_to=manifest["generator"]["trade_date_to"],
                )
            )
            with candidate_path.open(newline="", encoding="utf-8") as handle:
                candidate_rows = list(csv.DictReader(handle))
            self.assertEqual(len(candidate_rows), 1)

            reviewed_csv = self.build_reviewed_from_candidate(
                candidate_rows[0],
                Path(tmpdir) / "reviewed_candidate_fixture-e2e.csv",
                manifest["generator"]["generation_batch_id"],
            )

            output_paths = self.module.publish_reviewed_candidates(
                self.module.Config(
                    publish_batch_id=manifest["publish"]["publish_batch_id"],
                    reviewed_csv=str(reviewed_csv),
                    raw_csv=str(FIXTURE_BOOTSTRAP_BATCH_DIR / "stock_daily_raw.csv"),
                    feature_csv=str(FIXTURE_BOOTSTRAP_BATCH_DIR / "stock_daily_feature.csv"),
                    output_dir=str(publish_output_dir),
                    generator_output_dir=str(generator_output_dir),
                    bootstrap_output_dir=str(FIXTURE_BOOTSTRAP_OUTPUT_DIR),
                    mysql_dsn=None,
                )
            )

            for key in ["challenge", "challenge_day", "success", "failed", "run_log"]:
                self.assertTrue(output_paths[key].exists())

            with output_paths["challenge"].open(newline="", encoding="utf-8") as handle:
                challenge_rows = list(csv.DictReader(handle))
            with output_paths["challenge_day"].open(newline="", encoding="utf-8") as handle:
                day_rows = list(csv.DictReader(handle))
            with output_paths["success"].open(newline="", encoding="utf-8") as handle:
                success_rows = list(csv.DictReader(handle))

            self.assertEqual(len(challenge_rows), 1)
            self.assertEqual(len(day_rows), manifest["publish"]["expected_challenge_day_count"])
            self.assertEqual(len(success_rows), 1)
            self.assertEqual(challenge_rows[0]["challenge_id"], manifest["publish"]["expected_challenge_id"])
            self.assertEqual(challenge_rows[0]["difficulty"], manifest["generator"]["expected_candidate"]["difficulty"])
            self.assertEqual(success_rows[0]["challenge_id"], manifest["publish"]["expected_challenge_id"])
            self.assertEqual(output_paths["failed"].read_text(encoding="utf-8").strip(), "")
            self.assertIn("SUCCESS", output_paths["run_log"].read_text(encoding="utf-8"))

    def test_publish_failure_fixtures_match_manifest(self):
        manifest = load_failure_fixture_manifest()
        shared_input = manifest["shared_input_source"]
        raw_csv = (FAILURE_FIXTURE_ROOT / shared_input["raw_csv"]).resolve()
        feature_csv = (FAILURE_FIXTURE_ROOT / shared_input["feature_csv"]).resolve()

        for case in manifest["cases"]:
            with self.subTest(case_id=case["case_id"]):
                reviewed_csv = (FAILURE_FIXTURE_ROOT / case["reviewed_csv"]).resolve()
                expected = case["expected"]
                with tempfile.TemporaryDirectory() as tmpdir:
                    output_dir = Path(tmpdir) / "publish-output"
                    output_dir.mkdir(parents=True, exist_ok=True)

                    preseed_challenge_id = case.get("preseed_existing_challenge_id")
                    if preseed_challenge_id:
                        write_csv(
                            output_dir / "challenge_preseed.csv",
                            [
                                {
                                    "challenge_id": preseed_challenge_id,
                                    "code": "600519.SH",
                                    "start_date": "2024-01-02",
                                    "end_date": "2024-01-29",
                                }
                            ],
                            ["challenge_id", "code", "start_date", "end_date"],
                        )

                    config = self.module.Config(
                        publish_batch_id=case["publish_batch_id"],
                        reviewed_csv=str(reviewed_csv),
                        raw_csv=str(raw_csv),
                        feature_csv=str(feature_csv),
                        output_dir=str(output_dir),
                        generator_output_dir=str(Path(tmpdir) / "generator"),
                        bootstrap_output_dir=str(FIXTURE_BOOTSTRAP_OUTPUT_DIR),
                        mysql_dsn=None,
                    )

                    if expected["raises_publish_error"]:
                        with self.assertRaises(self.module.PublishError) as ctx:
                            self.module.publish_reviewed_candidates(config)
                        self.assertIn(expected["expected_input_issue_reason"], str(ctx.exception))
                        run_log_path = output_dir / ("publish_run_log_%s.csv" % case["publish_batch_id"])
                        self.assertTrue(run_log_path.exists())
                        run_log_rows = read_csv_rows(run_log_path)
                        self.assertEqual(len(run_log_rows), 1)
                        self.assertEqual(run_log_rows[0]["status"], expected["run_log_status"])
                        self.assertIn(expected["expected_input_issue_reason"], run_log_rows[0]["top_fail_reasons_json"])
                        continue

                    output_paths = self.module.publish_reviewed_candidates(config)
                    run_log_rows = read_csv_rows(output_paths["run_log"])
                    failed_rows = read_csv_rows(output_paths["failed"])
                    challenge_rows = read_csv_rows(output_paths["challenge"])
                    challenge_day_rows = read_csv_rows(output_paths["challenge_day"])
                    success_rows = read_csv_rows(output_paths["success"])

                    self.assertEqual(len(run_log_rows), 1)
                    self.assertEqual(run_log_rows[0]["status"], expected["run_log_status"])
                    self.assertEqual(int(run_log_rows[0]["failed_count"]), expected["failed_count"])
                    self.assertEqual(int(run_log_rows[0]["success_count"]), expected["success_count"])
                    self.assertEqual(len(failed_rows), expected["failed_count"])
                    self.assertEqual(len(success_rows), expected["success_count"])
                    self.assertEqual(len(challenge_rows), expected["challenge_rows"])
                    self.assertEqual(len(challenge_day_rows), expected["challenge_day_rows"])
                    self.assertEqual(failed_rows[0]["fail_reason"], expected["fail_reason"])
                    self.assertIn(expected["fail_reason"], run_log_rows[0]["top_fail_reasons_json"])
                    if "fail_message_contains" in expected:
                        self.assertIn(expected["fail_message_contains"], failed_rows[0]["fail_message"])


if __name__ == "__main__":
    unittest.main()
