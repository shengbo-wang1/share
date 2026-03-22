import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "testdata" / "fixed_e2e_fixture"
FIXTURE_BOOTSTRAP_OUTPUT_DIR = FIXTURE_ROOT / "bootstrap_output"
FIXTURE_MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
GENERATOR_FAILURE_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "testdata" / "generator_failure_fixture"
GENERATOR_FAILURE_MANIFEST_PATH = GENERATOR_FAILURE_FIXTURE_ROOT / "manifest.json"
GENERATOR_STABILITY_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "testdata" / "generator_stability_fixture"
GENERATOR_STABILITY_MANIFEST_PATH = GENERATOR_STABILITY_FIXTURE_ROOT / "manifest.json"


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


def load_generator_failure_manifest():
    with GENERATOR_FAILURE_MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_generator_stability_manifest():
    with GENERATOR_STABILITY_MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_csv_rows(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class ChallengeGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("challenge_generator_test_module", "challenge_generator.py")

    def make_features(self, base_overrides=None, validation_overrides=None):
        base = {
            "pct_change_3": 0.02,
            "pct_change_10": 0.0,
            "pct_change_15": 0.0,
            "breakout_day_pct": 0.01,
            "body_ratio": 0.2,
            "upper_shadow_ratio": 0.1,
            "lower_shadow_ratio": 0.1,
            "above_ma5": False,
            "above_ma10": False,
            "above_ma20": False,
            "below_ma20_days": 2,
            "distance_to_ma20": 0.0,
            "vol_ratio_1d_5d": 1.0,
            "vol_ratio_1d_10d": 1.0,
            "vol_shrink_ratio": 1.0,
            "ma_bull_alignment": False,
            "ma_bear_alignment": False,
            "above_ma20_recent_days": 0,
            "near_ma5": False,
            "near_ma10": False,
            "trend_up_days": 1,
            "trend_down_days": 1,
            "amplitude_10": 0.1,
            "volatility_10": 0.02,
            "platform_width": 0.2,
            "false_break_retrace": 0.2,
            "kdj_golden_cross": False,
            "kdj_dead_cross": False,
            "j_extreme_high": False,
            "j_extreme_low": False,
            "macd_golden_cross": False,
            "macd_dead_cross": False,
            "macd_hist_shrinking": False,
            "pullback_amount": 0.02,
            "bearish_today": False,
            "stock_drop_1d": -0.01,
            "price_volume_divergence": False,
            "end_close": 10.0,
        }
        validation = {
            "repair_signal_next_day": False,
            "next_day_fade_signal": False,
            "long_lower_shadow_signal": False,
            "verify_closes": [10.1, 10.2, 10.3],
        }
        if base_overrides:
            base.update(base_overrides)
        if validation_overrides:
            validation.update(validation_overrides)
        return {"base": base, "validation": validation}

    def make_index_features(self, rows=None):
        pd = self.module.lazy_import_pandas()
        rows = rows or [
            {"index_code": "000001.SH", "trade_date": "2024-01-01", "pct_change_1d": -0.04, "drawdown_5d": -0.10, "vol_ratio_1d_5d": 1.4, "panic_flag": 1},
        ]
        frame = pd.DataFrame(rows)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
        return {"index_code": "000001.SH", "main": frame, "verify": frame.iloc[:0].copy()}

    def make_window(self):
        pd = self.module.lazy_import_pandas()
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(self.module.WINDOW_DAYS)]
        main_rows = pd.DataFrame(
            [
                {
                    "trade_date": trade_date,
                    "open_price": 10 + idx,
                    "close_price": 10.5 + idx,
                    "high_price": 11 + idx,
                    "low_price": 9.5 + idx,
                    "volume": 1000,
                }
                for idx, trade_date in enumerate(dates)
            ]
        )
        main_feature_rows = pd.DataFrame(
            [
                {
                    "trade_date": trade_date,
                    "qfq_close": 10.5 + idx,
                    "ma20": 10 + idx,
                    "k_value": 50,
                    "d_value": 49,
                    "j_value": 55,
                    "dif": 1,
                    "dea": 0.9,
                    "macd": 0.2,
                }
                for idx, trade_date in enumerate(dates)
            ]
        )
        return {
            "start_date": dates[0],
            "end_date": dates[-1],
            "main_rows": main_rows,
            "main_feature_rows": main_feature_rows,
        }

    def test_empty_required_inputs_still_emit_debug_and_run_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_basic = root / "stock_basic.csv"
            raw_csv = root / "stock_daily_raw.csv"
            feature_csv = root / "stock_daily_feature.csv"
            output_dir = root / "output"
            write_csv(
                stock_basic,
                [{"code": "600519.SH", "stock_name": "贵州茅台", "exchange": "SH", "status": "LISTED"}],
                ["code", "stock_name", "exchange", "status"],
            )
            write_csv(raw_csv, [], ["code", "trade_date", "open_price", "high_price", "low_price", "close_price", "volume"])
            write_csv(
                feature_csv,
                [],
                ["code", "trade_date", "qfq_open", "qfq_high", "qfq_low", "qfq_close", "volume", "ma5", "ma10", "ma20", "k_value", "d_value", "j_value", "dif", "dea", "macd", "cap_bucket"],
            )

            config = self.module.Config(
                generation_batch_id="generator-empty-input",
                output_dir=str(output_dir),
                bootstrap_output_dir=str(root / "bootstrap"),
                stock_basic_csv=str(stock_basic),
                raw_csv=str(raw_csv),
                feature_csv=str(feature_csv),
                index_feature_csv=None,
                calendar_csv=None,
                trade_date_from=None,
                trade_date_to=None,
            )

            with self.assertRaises(self.module.GeneratorError) as ctx:
                self.module.run_generator(config)

            self.assertIn("generator 输入校验失败", str(ctx.exception))
            debug_path = output_dir / "generator_debug_generator-empty-input.csv"
            run_log_path = output_dir / "generator_run_log_generator-empty-input.csv"
            self.assertTrue(debug_path.exists())
            self.assertTrue(run_log_path.exists())
            run_log_text = run_log_path.read_text(encoding="utf-8")
            self.assertIn("FAILED", run_log_text)
            self.assertIn("empty_raw_input", debug_path.read_text(encoding="utf-8"))

    def test_insufficient_trade_days_has_clear_hint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_basic = root / "stock_basic.csv"
            raw_csv = root / "stock_daily_raw.csv"
            feature_csv = root / "stock_daily_feature.csv"
            output_dir = root / "output"
            write_csv(
                stock_basic,
                [{"code": "600519.SH", "stock_name": "贵州茅台", "exchange": "SH", "status": "LISTED"}],
                ["code", "stock_name", "exchange", "status"],
            )
            raw_rows = [
                {"code": "600519.SH", "trade_date": "2024-01-02", "open_price": 1, "high_price": 2, "low_price": 1, "close_price": 2, "volume": 100},
                {"code": "600519.SH", "trade_date": "2024-01-03", "open_price": 2, "high_price": 3, "low_price": 2, "close_price": 3, "volume": 100},
            ]
            feature_rows = [
                {"code": "600519.SH", "trade_date": "2024-01-02", "qfq_open": 1, "qfq_high": 2, "qfq_low": 1, "qfq_close": 2, "volume": 100, "ma5": 2, "ma10": 2, "ma20": 2, "k_value": 50, "d_value": 50, "j_value": 50, "dif": 1, "dea": 1, "macd": 1, "cap_bucket": "large"},
                {"code": "600519.SH", "trade_date": "2024-01-03", "qfq_open": 2, "qfq_high": 3, "qfq_low": 2, "qfq_close": 3, "volume": 100, "ma5": 2, "ma10": 2, "ma20": 2, "k_value": 50, "d_value": 50, "j_value": 50, "dif": 1, "dea": 1, "macd": 1, "cap_bucket": "large"},
            ]
            write_csv(raw_csv, raw_rows, list(raw_rows[0].keys()))
            write_csv(feature_csv, feature_rows, list(feature_rows[0].keys()))

            config = self.module.Config(
                generation_batch_id="generator-short-window",
                output_dir=str(output_dir),
                bootstrap_output_dir=str(root / "bootstrap"),
                stock_basic_csv=str(stock_basic),
                raw_csv=str(raw_csv),
                feature_csv=str(feature_csv),
                index_feature_csv=None,
                calendar_csv=None,
                trade_date_from=None,
                trade_date_to=None,
            )

            with self.assertRaises(self.module.GeneratorError) as ctx:
                self.module.run_generator(config)

            self.assertIn("样本不足", str(ctx.exception))
            run_log_text = (output_dir / "generator_run_log_generator-short-window.csv").read_text(encoding="utf-8")
            self.assertIn("EMPTY", run_log_text)
            self.assertIn("insufficient_trade_days", (output_dir / "generator_debug_generator-short-window.csv").read_text(encoding="utf-8"))

    def test_fixed_e2e_fixture_emits_single_breakout_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = load_fixture_manifest()
            expected_candidate = manifest["generator"]["expected_candidate"]
            output_dir = Path(tmpdir) / "generator-output"
            candidate_path = self.module.run_generator(
                self.module.Config(
                    generation_batch_id=manifest["generator"]["generation_batch_id"],
                    output_dir=str(output_dir),
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

            self.assertTrue(candidate_path.exists())
            with candidate_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["candidate_key"], expected_candidate["candidate_key"])
            self.assertEqual(row["code"], expected_candidate["code"])
            self.assertEqual(row["start_date"], expected_candidate["start_date"])
            self.assertEqual(row["end_date"], expected_candidate["end_date"])
            self.assertEqual(row["primary_tag"], expected_candidate["primary_tag"])
            self.assertEqual(row["secondary_tag"], "")
            self.assertEqual(row["difficulty"], expected_candidate["difficulty"])
            self.assertEqual(row["review_status"], expected_candidate["review_status"])
            self.assertEqual(row["generation_batch_id"], manifest["generator"]["generation_batch_id"])

            run_log_path = output_dir / ("generator_run_log_%s.csv" % manifest["generator"]["generation_batch_id"])
            debug_path = output_dir / ("generator_debug_%s.csv" % manifest["generator"]["generation_batch_id"])
            self.assertTrue(run_log_path.exists())
            self.assertTrue(debug_path.exists())
            with run_log_path.open(newline="", encoding="utf-8") as handle:
                run_log_row = next(csv.DictReader(handle))
            self.assertEqual(run_log_row["status"], "SUCCESS")
            self.assertEqual(int(run_log_row["window_scanned_count"]), 1)
            self.assertEqual(int(run_log_row["candidate_count"]), 1)
            self.assertIn("tag_hit_放量突破 vs 假突破", debug_path.read_text(encoding="utf-8"))

    def test_generator_failure_fixtures_match_manifest(self):
        manifest = load_generator_failure_manifest()
        for case in manifest["cases"]:
            with self.subTest(case_id=case["case_id"]):
                case_dir = (GENERATOR_FAILURE_FIXTURE_ROOT / case["input_dir"]).resolve()
                with tempfile.TemporaryDirectory() as tmpdir:
                    output_dir = Path(tmpdir) / case["case_id"]
                    config = self.module.Config(
                        generation_batch_id=case["generation_batch_id"],
                        output_dir=str(output_dir),
                        bootstrap_output_dir=str(case_dir.parent),
                        stock_basic_csv=str(case_dir / "stock_basic.csv"),
                        raw_csv=str(case_dir / "stock_daily_raw.csv"),
                        feature_csv=str(case_dir / "stock_daily_feature.csv"),
                        index_feature_csv=None,
                        calendar_csv=None,
                        trade_date_from=case["trade_date_from"],
                        trade_date_to=case["trade_date_to"],
                    )
                    expected = case["expected"]

                    if expected["raises_generator_error"]:
                        with self.assertRaises(self.module.GeneratorError) as ctx:
                            self.module.run_generator(config)
                        self.assertIn(expected["error_message_contains"], str(ctx.exception))
                    else:
                        candidate_path = self.module.run_generator(config)
                        self.assertTrue(candidate_path.exists())

                    run_log_path = output_dir / ("generator_run_log_%s.csv" % case["generation_batch_id"])
                    debug_path = output_dir / ("generator_debug_%s.csv" % case["generation_batch_id"])
                    self.assertTrue(run_log_path.exists())
                    self.assertTrue(debug_path.exists())

                    run_log_rows = read_csv_rows(run_log_path)
                    self.assertEqual(len(run_log_rows), 1)
                    self.assertEqual(run_log_rows[0]["status"], expected["run_log_status"])
                    self.assertEqual(int(run_log_rows[0]["candidate_count"]), expected["candidate_count"])

                    debug_text = debug_path.read_text(encoding="utf-8")
                    for reason in expected["expected_debug_reasons"]:
                        self.assertIn(reason, debug_text)

                    candidate_file = output_dir / ("candidate_%s.csv" % case["generation_batch_id"])
                    if expected["candidate_count"] > 0:
                        candidate_rows = read_csv_rows(candidate_file)
                        self.assertEqual(len(candidate_rows), expected["candidate_count"])
                        for key, value in expected["candidate"].items():
                            self.assertEqual(candidate_rows[0][key], value)
                    else:
                        self.assertFalse(candidate_file.exists())

    def test_allow_empty_suppresses_expected_empty_exception(self):
        manifest = load_generator_failure_manifest()
        case = [item for item in manifest["cases"] if item["case_id"] == "no_candidate"][0]
        case_dir = (GENERATOR_FAILURE_FIXTURE_ROOT / case["input_dir"]).resolve()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generator-output"
            config = self.module.Config(
                generation_batch_id=case["generation_batch_id"],
                output_dir=str(output_dir),
                bootstrap_output_dir=str(case_dir.parent),
                stock_basic_csv=str(case_dir / "stock_basic.csv"),
                raw_csv=str(case_dir / "stock_daily_raw.csv"),
                feature_csv=str(case_dir / "stock_daily_feature.csv"),
                index_feature_csv=None,
                calendar_csv=None,
                trade_date_from=case["trade_date_from"],
                trade_date_to=case["trade_date_to"],
                allow_empty=True,
            )
            result = self.module.run_generator(config)
            self.assertIsNone(result)

            run_log_path = output_dir / ("generator_run_log_%s.csv" % case["generation_batch_id"])
            debug_path = output_dir / ("generator_debug_%s.csv" % case["generation_batch_id"])
            self.assertTrue(run_log_path.exists())
            self.assertTrue(debug_path.exists())
            run_log_row = read_csv_rows(run_log_path)[0]
            self.assertEqual(run_log_row["status"], "EMPTY")
            self.assertEqual(int(run_log_row["candidate_count"]), 0)
            self.assertIn("no_tag_hit", debug_path.read_text(encoding="utf-8"))

    def test_generator_stability_fixtures_match_manifest(self):
        manifest = load_generator_stability_manifest()
        for case in manifest["cases"]:
            with self.subTest(case_id=case["case_id"]):
                case_dir = (GENERATOR_STABILITY_FIXTURE_ROOT / case["input_dir"]).resolve()
                with tempfile.TemporaryDirectory() as tmpdir:
                    output_dir = Path(tmpdir) / case["case_id"]
                    candidate_path = self.module.run_generator(
                        self.module.Config(
                            generation_batch_id=case["generation_batch_id"],
                            output_dir=str(output_dir),
                            bootstrap_output_dir=str(case_dir.parent),
                            stock_basic_csv=str(case_dir / "stock_basic.csv"),
                            raw_csv=str(case_dir / "stock_daily_raw.csv"),
                            feature_csv=str(case_dir / "stock_daily_feature.csv"),
                            index_feature_csv=None,
                            calendar_csv=None,
                            trade_date_from=case["trade_date_from"],
                            trade_date_to=case["trade_date_to"],
                        )
                    )
                    self.assertTrue(candidate_path.exists())

                    expected = case["expected"]
                    run_log_path = output_dir / ("generator_run_log_%s.csv" % case["generation_batch_id"])
                    debug_path = output_dir / ("generator_debug_%s.csv" % case["generation_batch_id"])
                    candidate_rows = read_csv_rows(candidate_path)
                    run_log_rows = read_csv_rows(run_log_path)

                    self.assertEqual(len(candidate_rows), expected["candidate_count"])
                    self.assertEqual(len(run_log_rows), 1)
                    self.assertEqual(run_log_rows[0]["status"], expected["run_log_status"])
                    self.assertEqual(int(run_log_rows[0]["candidate_count"]), expected["candidate_count"])

                    for key, value in expected["candidate"].items():
                        self.assertEqual(candidate_rows[0][key], value)

                    debug_text = debug_path.read_text(encoding="utf-8")
                    for reason in expected["expected_debug_reasons"]:
                        self.assertIn(reason, debug_text)
                    if case["case_id"] == "index_missing_but_candidate_survives":
                        self.assertIn("index_features_missing", debug_text)
                        self.assertEqual(run_log_rows[0]["status"], "SUCCESS")

    def test_all_tag_positive_evaluators(self):
        bottom = self.module.evaluate_bottom(
            self.make_features(
                {
                    "pct_change_10": -0.15,
                    "below_ma20_days": 8,
                    "distance_to_ma20": 0.01,
                    "vol_ratio_1d_5d": 0.9,
                    "kdj_golden_cross": True,
                    "macd_golden_cross": True,
                    "above_ma5": True,
                }
            )
        )
        breakout = self.module.evaluate_breakout(
            self.make_features(
                {
                    "breakout_day_pct": 0.06,
                    "platform_width": 0.10,
                    "vol_ratio_1d_5d": 2.0,
                    "vol_ratio_1d_10d": 1.7,
                    "above_ma20": True,
                    "false_break_retrace": 0.2,
                }
            )
        )
        highvolbear = self.module.evaluate_highvolbear(
            self.make_features(
                {
                    "pct_change_15": 0.25,
                    "distance_to_ma20": 0.10,
                    "vol_ratio_1d_5d": 2.1,
                    "bearish_today": True,
                    "body_ratio": 0.45,
                    "upper_shadow_ratio": 0.40,
                }
            )
        )
        pullback = self.module.evaluate_pullback(
            self.make_features(
                {
                    "ma_bull_alignment": True,
                    "pullback_amount": 0.05,
                    "vol_shrink_ratio": 0.6,
                    "distance_to_ma20": -0.01,
                    "near_ma10": True,
                },
                {"repair_signal_next_day": True},
            )
        )
        panic = self.module.evaluate_panic(
            self.make_features(
                {"stock_drop_1d": -0.01},
                {"repair_signal_next_day": True, "long_lower_shadow_signal": True},
            ),
            self.make_index_features(),
        )
        takeprofit = self.module.evaluate_takeprofit(
            self.make_features(
                {
                    "trend_up_days": 6,
                    "pct_change_10": 0.20,
                    "distance_to_ma20": 0.09,
                    "j_extreme_high": True,
                    "price_volume_divergence": True,
                },
                {"next_day_fade_signal": True},
            )
        )

        self.assertTrue(bottom["hit"])
        self.assertTrue(breakout["hit"])
        self.assertTrue(highvolbear["hit"])
        self.assertTrue(pullback["hit"])
        self.assertTrue(panic["hit"])
        self.assertTrue(takeprofit["hit"])

    def test_conflict_resolution_difficulty_and_gate(self):
        hits = [
            {"tag_name": self.module.TAG_BREAKOUT, "score": 2.0, "hit": True},
            {"tag_name": self.module.TAG_TAKEPROFIT, "score": 1.8, "hit": True},
        ]
        resolved = self.module.resolve_tag_conflict({"hits": hits})
        self.assertEqual(resolved["primary_tag"], self.module.TAG_BREAKOUT)
        self.assertEqual(resolved["secondary_tag"], self.module.TAG_TAKEPROFIT)
        self.assertEqual(resolved["review_status"], "PENDING")

        conflict_hits = [
            {"tag_name": self.module.TAG_BREAKOUT, "score": 2.0, "hit": True},
            {"tag_name": self.module.TAG_HIGHVOLBEAR, "score": 1.9, "hit": True},
            {"tag_name": self.module.TAG_BOTTOM, "score": 1.8, "hit": True},
        ]
        conflict = self.module.resolve_tag_conflict({"hits": conflict_hits})
        difficulty, reason = self.module.classify_difficulty(
            self.make_window(),
            self.make_features({"volatility_10": 0.06, "false_break_retrace": 0.6}),
            conflict,
        )
        passed, reasons = self.module.evaluate_candidate_gate(
            {"list_date": date(2023, 12, 20)},
            self.make_window(),
            self.make_features({"volatility_10": 0.06, "false_break_retrace": 0.6}),
            conflict,
            difficulty,
        )
        self.assertEqual(conflict["review_status"], "REVIEW_REQUIRED")
        self.assertEqual(difficulty, "hard")
        self.assertEqual(reason, "high_conflict_or_false_signal_risk")
        self.assertFalse(passed)
        self.assertIn("recently_listed_window", reasons)
        self.assertIn("unresolvable_tag_conflict", reasons)

    def test_classify_tags_keeps_all_evaluations_when_no_hit(self):
        tag_result = self.module.classify_tags(self.make_window(), self.make_features(), None)
        self.assertFalse(tag_result["hit_any"])
        self.assertEqual(len(tag_result["evaluations"]), 6)
        debug_rows = self.module.build_tag_debug_records("batch", "600519.SH", date(2024, 1, 2), tag_result)
        self.assertEqual(len(debug_rows), 6)
        self.assertTrue(any("tag_miss_" in row["reason"] for row in debug_rows))
        panic_eval = [item for item in tag_result["evaluations"] if item["tag_name"] == self.module.TAG_PANIC][0]
        self.assertIn("index_features_missing", panic_eval["missed_conditions"])


if __name__ == "__main__":
    unittest.main()
