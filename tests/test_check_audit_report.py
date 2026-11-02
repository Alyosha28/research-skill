import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_audit_report import validate


class AuditReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "assets" / "audit_report.example.json").open(encoding="utf-8") as handle:
            cls.example = json.load(handle)

    def setUp(self):
        self.report = copy.deepcopy(self.example)

    def test_example_is_valid(self):
        self.assertEqual(validate(self.report), [])

    def test_unknown_field_is_rejected(self):
        self.report["unexpected"] = True
        self.assertTrue(any("未知字段" in error for error in validate(self.report)))

    def test_open_high_finding_blocks_pass(self):
        self.report["findings"][0]["severity"] = "high"
        self.report["findings"][0]["status"] = "open"
        self.assertTrue(any("未关闭的高严重度问题" in error for error in validate(self.report)))

    def test_failing_command_blocks_pass(self):
        self.report["commands"][0]["return_code"] = 1
        self.assertTrue(any("所有命令返回零" in error for error in validate(self.report)))

    def test_commit_mismatch_is_rejected(self):
        errors = validate(self.report, "abcdef0")
        self.assertTrue(any("提交不一致" in error for error in errors))

    def test_duplicate_finding_identifier_is_rejected(self):
        self.report["findings"].append(copy.deepcopy(self.report["findings"][0]))
        self.assertTrue(any("id 重复" in error for error in validate(self.report)))

    def test_invalid_severity_is_rejected(self):
        self.report["findings"][0]["severity"] = "blocker"
        self.assertTrue(any("severity 无效" in error for error in validate(self.report)))

    def test_non_pass_verdict_is_rejected(self):
        self.report["verdict"] = "fail"
        self.assertTrue(any("审计判定为 fail" in error for error in validate(self.report)))

    def test_residual_risks_must_be_strings(self):
        self.report["residual_risks"] = [1]
        self.assertTrue(any("residual_risks" in error for error in validate(self.report)))

    def test_cli_returns_zero_for_valid_report(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_audit_report.py"), str(ROOT / "assets" / "audit_report.example.json")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_rejects_invalid_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            self.report["verdict"] = "needs-human"
            path.write_text(json.dumps(self.report), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_audit_report.py"), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("审计判定为 needs-human", result.stderr)


if __name__ == "__main__":
    unittest.main()
