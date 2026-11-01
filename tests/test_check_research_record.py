import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_research_record import _resolve_json_pointer, validate_record


class ResearchRecordTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "assets" / "research_record.example.json").open(encoding="utf-8") as handle:
            cls.example = json.load(handle)

    def setUp(self):
        self.record = copy.deepcopy(self.example)
        self.source_root = ROOT / "assets"

    def test_example_is_valid(self):
        self.assertEqual(validate_record(self.record, self.source_root), [])

    def test_quantitative_claim_requires_denominator(self):
        del self.record["claims"][0]["denominator"]
        errors = validate_record(self.record, self.source_root)
        self.assertTrue(any("denominator" in error for error in errors))

    def test_supported_claim_requires_source(self):
        del self.record["claims"][0]["source"]
        errors = validate_record(self.record, self.source_root)
        self.assertTrue(any("source 必须是对象" in error for error in errors))

    def test_json_pointer_must_exist(self):
        self.record["claims"][0]["source"]["locator"] = "/comparison/missing"
        errors = validate_record(self.record, self.source_root)
        self.assertTrue(any("JSON Pointer 不存在" in error for error in errors))

    def test_source_must_stay_within_root(self):
        self.record["claims"][0]["source"]["path"] = "../outside.json"
        errors = validate_record(self.record, self.source_root)
        self.assertTrue(any("超出指定来源目录" in error for error in errors))

    def test_value_must_match_source(self):
        self.record["claims"][0]["value"] = 0.5
        errors = validate_record(self.record, self.source_root)
        self.assertTrue(any("与来源数值不一致" in error for error in errors))

    def test_url_must_be_string(self):
        self.record["claims"][0]["source"] = {"url": 123, "locator": "result"}
        errors = validate_record(self.record, self.source_root)
        self.assertTrue(any("url 必须是字符串" in error for error in errors))

    def test_invalid_url_returns_validation_error(self):
        self.record["claims"][0]["source"] = {"url": "https://[::1", "locator": "result"}
        errors = validate_record(self.record, self.source_root)
        self.assertTrue(any("url 无法解析" in error for error in errors))

    def test_null_character_in_path_returns_validation_error(self):
        self.record["claims"][0]["source"]["path"] = "bad\u0000path.json"
        errors = validate_record(self.record, self.source_root)
        self.assertTrue(any("path 无法解析" in error for error in errors))

    def test_json_pointer_rejects_invalid_escape(self):
        with self.assertRaises(ValueError):
            _resolve_json_pointer({"a": 1}, "/a~2")

    def test_json_pointer_rejects_noncanonical_array_indices(self):
        document = {"a": [10, 20]}
        for pointer in ("/a/01", "/a/١"):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                _resolve_json_pointer(document, pointer)

    def test_json_pointer_decodes_valid_escapes(self):
        document = {"a/b": {"~key": 7}}
        self.assertEqual(_resolve_json_pointer(document, "/a~1b/~0key"), 7)

    def test_pointer_errors_are_returned_by_record_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            source_root = Path(directory)
            with (source_root / "result.json").open("w", encoding="utf-8") as handle:
                json.dump({"a": [10, 20]}, handle)
            for pointer in ("/a~2", "/a/01", "/a/١"):
                with self.subTest(pointer=pointer):
                    self.record["claims"][0]["source"] = {
                        "path": "result.json",
                        "locator": pointer,
                    }
                    errors = validate_record(self.record, source_root)
                    self.assertTrue(any("source 无法解析" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
