#!/usr/bin/env python3
"""检查研究审计报告，并作为发布门槛使用。"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


SCHEMA_VERSION = "research-audit/v1"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
TOP_FIELDS = {
    "schema_version",
    "report_id",
    "auditor",
    "scope",
    "commit",
    "created_at",
    "commands",
    "findings",
    "verdict",
    "residual_risks",
}
FINDING_FIELDS = {
    "id",
    "severity",
    "file",
    "line",
    "summary",
    "failure_scenario",
    "evidence",
    "status",
    "recommendation",
}


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _integer(value, minimum=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _string_list(value):
    return isinstance(value, list) and all(_nonblank(item) for item in value)


def _timestamp(value):
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复的 JSON 键：{key}")
        result[key] = value
    return result


def _check_fields(value, required, prefix, errors):
    missing = required - set(value)
    unknown = set(value) - required
    if missing:
        errors.append(f"{prefix} 缺少字段：{sorted(missing)}")
    if unknown:
        errors.append(f"{prefix} 包含未知字段：{sorted(unknown)}")


def validate(report, expected_commit=None):
    """返回审计报告中的全部契约错误。"""
    errors = []
    if not isinstance(report, dict):
        return ["审计报告必须是 JSON 对象"]

    _check_fields(report, TOP_FIELDS, "审计报告", errors)
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION}")
    if not _nonblank(report.get("report_id")):
        errors.append("report_id 必须是非空字符串")
    if not _nonblank(report.get("auditor")):
        errors.append("auditor 必须是非空字符串")
    if not _string_list(report.get("scope")) or not report.get("scope"):
        errors.append("scope 必须是非空字符串数组")

    commit = report.get("commit")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        errors.append("commit 必须是十六进制提交标识")
    if not _timestamp(report.get("created_at")):
        errors.append("created_at 必须是带时区的 ISO 时间戳")
    if report.get("verdict") not in {"pass", "fail", "needs-human"}:
        errors.append("verdict 必须是 pass、fail 或 needs-human")
    if expected_commit and isinstance(commit, str) and COMMIT_PATTERN.fullmatch(commit):
        if not expected_commit.startswith(commit) and not commit.startswith(expected_commit):
            errors.append(f"提交不一致：报告 {commit}，期望 {expected_commit}")

    commands = report.get("commands")
    if not isinstance(commands, list) or not commands:
        errors.append("commands 必须是非空数组")
        commands = []
    for index, command in enumerate(commands):
        prefix = f"commands[{index}]"
        if not isinstance(command, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        _check_fields(command, {"command", "return_code"}, prefix, errors)
        if not _nonblank(command.get("command")):
            errors.append(f"{prefix}.command 必须是非空字符串")
        if not isinstance(command.get("return_code"), int) or isinstance(command.get("return_code"), bool):
            errors.append(f"{prefix}.return_code 必须是整数")
    if report.get("verdict") == "pass" and any(
        isinstance(command, dict) and command.get("return_code") != 0 for command in commands
    ):
        errors.append("pass 判定要求所有命令返回零")

    findings = report.get("findings")
    if not isinstance(findings, list):
        errors.append("findings 必须是数组")
        findings = []
    identifiers = set()
    open_blocking = []
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        _check_fields(finding, FINDING_FIELDS, prefix, errors)
        identifier = finding.get("id")
        if not _nonblank(identifier):
            errors.append(f"{prefix}.id 必须是非空字符串")
        elif identifier in identifiers:
            errors.append(f"{prefix}.id 重复：{identifier}")
        else:
            identifiers.add(identifier)
        if finding.get("severity") not in {"critical", "high", "medium", "low"}:
            errors.append(f"{prefix}.severity 无效")
        if finding.get("status") not in {"open", "resolved", "accepted-risk"}:
            errors.append(f"{prefix}.status 无效")
        if not _nonblank(finding.get("file")):
            errors.append(f"{prefix}.file 必须是非空字符串")
        if not _integer(finding.get("line"), 1):
            errors.append(f"{prefix}.line 必须是正整数")
        for field in ("summary", "failure_scenario", "evidence", "recommendation"):
            if not _nonblank(finding.get(field)):
                errors.append(f"{prefix}.{field} 必须是非空字符串")
        if finding.get("severity") in {"critical", "high"} and finding.get("status") == "open":
            open_blocking.append(identifier if _nonblank(identifier) else prefix)

    if report.get("verdict") == "pass" and open_blocking:
        errors.append(f"pass 判定存在未关闭的高严重度问题：{open_blocking}")
    if report.get("verdict") != "pass":
        errors.append(f"审计判定为 {report.get('verdict')}")
    if not _string_list(report.get("residual_risks")):
        errors.append("residual_risks 必须是字符串数组")
    return errors


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="审计报告 JSON 路径")
    parser.add_argument("--commit", help="期望提交标识")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        report = json.loads(
            args.report.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(2, f"审计报告读取失败：{exc}\n")

    errors = validate(report, args.commit)
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1
    print(f"审计报告有效：{report['report_id']}，提交 {report['commit']}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
