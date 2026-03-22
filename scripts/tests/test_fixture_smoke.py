import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_module(name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FixtureSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("fixture_smoke_test_module", "fixture_smoke.py")

    def test_fixture_smoke_runs_all_cases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.module.run_fixture_smoke(
                self.module.SmokeConfig(
                    smoke_batch_id="fixture-smoke-test",
                    output_dir=str(Path(tmpdir) / "fixture-smoke"),
                )
            )

            self.assertTrue(result["summary_csv"].exists())
            self.assertTrue(result["summary_json"].exists())
            self.assertEqual(result["failed_count"], 0)

            with result["summary_csv"].open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 12)
            self.assertTrue(all(row["pass"] == "true" for row in rows))
            case_ids = {row["case_id"] for row in rows}
            self.assertIn("fixed_e2e", case_ids)
            self.assertIn("missing_columns", case_ids)
            self.assertIn("review_required", case_ids)
            self.assertIn("easy_clear_signal", case_ids)

            json_rows = json.loads(result["summary_json"].read_text(encoding="utf-8"))
            self.assertEqual(len(json_rows), 12)

    def test_fixture_smoke_can_rerun_same_batch_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.module.SmokeConfig(
                smoke_batch_id="fixture-smoke-rerun",
                output_dir=str(Path(tmpdir) / "fixture-smoke"),
            )
            first = self.module.run_fixture_smoke(config)
            second = self.module.run_fixture_smoke(config)

            self.assertEqual(first["failed_count"], 0)
            self.assertEqual(second["failed_count"], 0)
            self.assertTrue(second["summary_csv"].exists())
            with second["summary_csv"].open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 12)
            self.assertTrue(all(row["pass"] == "true" for row in rows))


if __name__ == "__main__":
    unittest.main()
