import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_campaign import evaluate_run, validate_campaign


class CampaignValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = ROOT / "assets"
        with (cls.assets / "campaign.example.json").open(encoding="utf-8") as handle:
            cls.example = json.load(handle)

    def setUp(self):
        self.config = copy.deepcopy(self.example)

    def errors(self):
        return validate_campaign(self.config, self.assets)

    def test_example_is_valid(self):
        self.assertEqual(self.errors(), [])

    def test_unknown_field_is_rejected(self):
        self.config["unexpected"] = True
        self.assertTrue(any("未知字段" in error for error in self.errors()))

    def test_design_lock_must_be_locked(self):
        self.config["design_lock"]["status"] = "draft"
        self.assertTrue(any("status 必须是 locked" in error for error in self.errors()))

    def test_retrospective_lock_requires_boolean_disclosure(self):
        self.config["design_lock"]["retrospective"] = "no"
        self.assertTrue(any("retrospective 必须是布尔值" in error for error in self.errors()))

    def test_confirmation_protocol_must_be_frozen(self):
        self.config["protocol"]["data_role"] = "confirmation"
        self.assertTrue(any("必须为 true" in error for error in self.errors()))

    def test_evidence_path_must_stay_within_root(self):
        self.config["evidence"][0]["source"] = {"path": "../outside.json", "locator": "/x"}
        self.assertTrue(any("超出来源目录" in error for error in self.errors()))

    def test_evidence_path_must_be_relative(self):
        self.config["evidence"][0]["source"] = {
            "path": str((self.assets / "campaign_source.example.json").resolve()),
            "locator": "/design",
        }
        self.assertTrue(any("超出来源目录" in error for error in self.errors()))

    def test_evidence_url_must_use_https(self):
        self.config["evidence"][0]["source"] = {"url": "http://example.com/result", "locator": "/x"}
        self.assertTrue(any("绝对 HTTPS URL" in error for error in self.errors()))

    def test_evidence_pointer_must_resolve(self):
        self.config["evidence"][0]["source"] = {
            "path": "campaign_source.example.json",
            "locator": "/missing",
        }
        self.assertTrue(any("无法解析" in error for error in self.errors()))

    def test_evidence_pointer_rejects_invalid_escape(self):
        self.config["evidence"][0]["source"] = {
            "path": "campaign_source.example.json",
            "locator": "/design~2",
        }
        self.assertTrue(any("无法解析" in error for error in self.errors()))

    def test_baseline_parameter_must_be_within_search_space(self):
        self.config["baseline_parameters"]["memory_slots"] = 9
        self.assertTrue(any("无效" in error for error in self.errors()))

    def test_baseline_parameters_must_match_search_space_keys(self):
        self.config["baseline_parameters"]["other"] = 1
        self.assertTrue(any("键必须与 search_space 完全一致" in error for error in self.errors()))

    def test_search_space_bounds_must_be_ordered(self):
        self.config["search_space"]["memory_slots"]["minimum"] = 5
        self.assertTrue(any("minimum 超过 maximum" in error for error in self.errors()))

    def test_sensitive_environment_variable_is_rejected(self):
        self.config["runner"]["environment_allowlist"] = ["ANTHROPIC_API_KEY"]
        self.assertTrue(any("不允许敏感变量" in error for error in self.errors()))

    def test_duplicate_environment_variable_is_rejected(self):
        self.config["runner"]["environment_allowlist"] = ["SLOW", "SLOW"]
        self.assertTrue(any("必须唯一" in error for error in self.errors()))

    def test_non_string_environment_variable_is_rejected(self):
        self.config["runner"]["environment_allowlist"] = [{}]
        self.assertTrue(any("名称无效" in error for error in self.errors()))

    def test_working_directory_cannot_escape_root(self):
        self.config["runner"]["working_directory"] = "../outside"
        self.assertTrue(any("必须位于项目根目录内" in error for error in self.errors()))

    def test_primary_metric_must_be_declared(self):
        self.config["evaluation"]["primary_metric"] = "unknown_metric"
        self.assertTrue(any("必须在 metrics 中声明" in error for error in self.errors()))

    def test_code_patch_paths_must_be_directory_prefixes(self):
        self.config["runner"]["code_patch"] = {"allowed_paths": ["src/model.py"]}
        self.assertTrue(any("目录前缀" in error for error in self.errors()))

    def test_budget_iterations_must_be_positive(self):
        self.config["budget"]["max_iterations"] = 0
        self.assertTrue(any("max_iterations 必须是正整数" in error for error in self.errors()))

    def test_duplicate_json_key_is_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.json"
            text = (self.assets / "campaign.example.json").read_text(encoding="utf-8")
            path.write_text(text.replace('"seed": 20261020,', '"seed": 20261020, "seed": 1,'), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_campaign.py"), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("重复的 JSON 键", result.stderr)


class CampaignEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = ROOT / "assets"
        with (cls.assets / "campaign.example.json").open(encoding="utf-8") as handle:
            cls.config = json.load(handle)
        with (cls.assets / "run_result.example.json").open(encoding="utf-8") as handle:
            cls.result = json.load(handle)
        with (cls.assets / "baseline_result.example.json").open(encoding="utf-8") as handle:
            cls.baseline = json.load(handle)

    def setUp(self):
        self.config = copy.deepcopy(self.config)
        self.result = copy.deepcopy(self.result)
        self.baseline = copy.deepcopy(self.baseline)

    def evaluate(self):
        return evaluate_run(self.config, self.result, self.baseline)

    def test_example_candidate_is_accepted(self):
        decision = self.evaluate()
        self.assertTrue(decision["accepted"])
        self.assertAlmostEqual(decision["improvement"], 0.25)

    def test_failed_run_is_rejected_even_with_good_metrics(self):
        self.result["status"] = "failed"
        self.result["errors"] = ["command exited with status 1"]
        decision = self.evaluate()
        self.assertFalse(decision["accepted"])
        self.assertIn("command exited with status 1", decision["reasons"])

    def test_missing_metric_is_rejected(self):
        del self.result["metrics"]["error_rate"]
        decision = self.evaluate()
        self.assertFalse(decision["accepted"])
        self.assertTrue(any("缺少必需指标" in reason for reason in decision["reasons"]))

    def test_non_finite_metric_is_rejected(self):
        self.result["metrics"]["paired_latency_seconds"] = math.inf
        decision = self.evaluate()
        self.assertFalse(decision["accepted"])
        self.assertTrue(any("不是有限数值" in reason for reason in decision["reasons"]))

    def test_metric_limit_is_enforced(self):
        self.result["metrics"]["error_rate"] = 0.2
        decision = self.evaluate()
        self.assertFalse(decision["accepted"])
        self.assertTrue(any("超过上限" in reason for reason in decision["reasons"]))

    def test_minimum_improvement_is_enforced(self):
        self.result["metrics"]["paired_latency_seconds"] = 1.45
        decision = self.evaluate()
        self.assertFalse(decision["accepted"])
        self.assertTrue(any("改善未达到要求" in reason for reason in decision["reasons"]))

    def test_guard_regression_is_enforced(self):
        self.result["metrics"]["error_rate"] = 0.02
        decision = self.evaluate()
        self.assertFalse(decision["accepted"])
        self.assertTrue(any("守卫指标退化" in reason for reason in decision["reasons"]))

    def test_guard_regression_within_tolerance_is_accepted(self):
        self.result["metrics"]["error_rate"] = 0.014
        self.assertTrue(self.evaluate()["accepted"])

    def test_maximize_direction_is_supported(self):
        self.config["evaluation"] = {
            "primary_metric": "quality",
            "minimum_improvement": 0.1,
            "metrics": {
                "quality": {"direction": "maximize", "limit": 0.5},
                "error_rate": {"direction": "minimize"},
            },
        }
        self.result["metrics"] = {"quality": 0.8, "error_rate": 0.01}
        self.baseline["metrics"] = {"quality": 0.6, "error_rate": 0.01}
        decision = self.evaluate()
        self.assertTrue(decision["accepted"])
        self.assertAlmostEqual(decision["improvement"], 0.2)

    def test_baseline_missing_metric_is_rejected(self):
        del self.baseline["metrics"]["error_rate"]
        decision = self.evaluate()
        self.assertFalse(decision["accepted"])
        self.assertTrue(any("基线指标不可用" in reason for reason in decision["reasons"]))

    def test_result_without_baseline_checks_gates_only(self):
        decision = evaluate_run(self.config, self.result, None)
        self.assertTrue(decision["accepted"])
        self.assertIsNone(decision["improvement"])

    def test_cli_returns_zero_for_accepted_candidate(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_campaign.py"),
                str(self.assets / "campaign.example.json"),
                "--result",
                str(self.assets / "run_result.example.json"),
                "--baseline",
                str(self.assets / "baseline_result.example.json"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"accepted": true', result.stdout)


if __name__ == "__main__":
    unittest.main()
