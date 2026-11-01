import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_research_state import validate_state


class ResearchStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "assets" / "research_state.example.json").open(encoding="utf-8") as handle:
            cls.example = json.load(handle)

    def setUp(self):
        self.state = copy.deepcopy(self.example)

    def test_example_is_valid(self):
        self.assertEqual(validate_state(self.state), [])

    def test_budget_cannot_be_exceeded(self):
        self.state["budget"]["model_calls"]["used"] = 3
        errors = validate_state(self.state)
        self.assertTrue(any("used 超过 limit" in error for error in errors))

    def test_fork_requires_new_run(self):
        self.state["route"]["decision"] = "FORK"
        errors = validate_state(self.state)
        self.assertTrue(any("next_run 必须是非空字符串" in error for error in errors))

    def test_reframe_requires_new_protocol(self):
        self.state["route"].update({
            "decision": "REFRAME",
            "next_run": "run-002",
            "next_protocol": "protocol-001",
        })
        errors = validate_state(self.state)
        self.assertTrue(any("必须使用新协议" in error for error in errors))

    def test_confirmation_protocol_must_be_frozen(self):
        self.state["protocol"]["data_role"] = "confirmation"
        errors = validate_state(self.state)
        self.assertTrue(any("必须为 true" in error for error in errors))

    def test_proposal_requires_falsification(self):
        del self.state["proposals"][0]["falsification"]
        errors = validate_state(self.state)
        self.assertTrue(any("falsification 必须是非空字符串" in error for error in errors))

    def test_memory_use_requires_applicability(self):
        del self.state["memory"]["used"][0]["applicability"]
        errors = validate_state(self.state)
        self.assertTrue(any("applicability 必须是非空字符串" in error for error in errors))

    def test_proposal_ids_must_be_unique(self):
        self.state["proposals"].append(copy.deepcopy(self.state["proposals"][0]))
        errors = validate_state(self.state)
        self.assertTrue(any("id 重复" in error for error in errors))

    def test_route_source_must_match_recovery_run(self):
        self.state["route"]["source_run"] = "run-other"
        errors = validate_state(self.state)
        self.assertTrue(any("必须与 recovery.run_id 一致" in error for error in errors))

    def test_enum_fields_reject_non_string_values(self):
        self.state["question"]["research_level"] = {}
        self.state["protocol"]["data_role"] = []
        self.state["proposals"][0]["status"] = {}
        self.state["route"]["decision"] = []
        errors = validate_state(self.state)
        self.assertEqual(len([error for error in errors if "之一" in error]), 4)

    def test_proposal_requires_applicability(self):
        del self.state["proposals"][0]["applicability"]
        errors = validate_state(self.state)
        self.assertTrue(any("applicability 必须是非空字符串" in error for error in errors))

    def test_proposal_requires_model_usage(self):
        del self.state["proposals"][0]["model_id"]
        del self.state["proposals"][0]["usage"]
        errors = validate_state(self.state)
        self.assertTrue(any("model_id 必须是非空字符串" in error for error in errors))
        self.assertTrue(any("usage 必须是对象" in error for error in errors))

    def test_fork_cannot_change_protocol(self):
        self.state["route"].update({
            "decision": "FORK",
            "next_run": "run-002",
            "next_protocol": "protocol-002",
        })
        errors = validate_state(self.state)
        self.assertTrue(any("必须保持当前协议" in error for error in errors))

    def test_invalid_utf8_returns_cli_error(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "invalid.json"
            state_path.write_bytes(b"\xff")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_research_state.py"), str(state_path)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("研究状态读取失败", result.stderr)


if __name__ == "__main__":
    unittest.main()
