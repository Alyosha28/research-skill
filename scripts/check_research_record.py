#!/usr/bin/env python3
"""检查通用研究记录及其本地 JSON 证据引用。"""

import argparse
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


STATUSES = {"supported", "contradicted", "inconclusive", "unverified"}
EVIDENCE_ROLES = {"primary", "diagnostic", "contextual"}
QUANTITATIVE_TEXT_FIELDS = (
    "object",
    "metric",
    "unit",
    "denominator",
    "comparison",
    "population_or_window",
    "statistical_unit",
)
INVALID_POINTER_ESCAPE = re.compile(r"~(?![01])")
ARRAY_INDEX = re.compile(r"0|[1-9][0-9]*")


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _resolve_json_pointer(document, pointer):
    current = document
    for raw_token in pointer[1:].split("/"):
        if INVALID_POINTER_ESCAPE.search(raw_token):
            raise ValueError(f"JSON Pointer 包含无效转义：{pointer}")
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"JSON Pointer 不存在：{pointer}")
            current = current[token]
        elif isinstance(current, list):
            if not ARRAY_INDEX.fullmatch(token):
                raise ValueError(f"JSON Pointer 的数组索引无效：{pointer}")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"JSON Pointer 的数组索引越界：{pointer}")
            current = current[index]
        else:
            raise ValueError(f"JSON Pointer 穿过标量值：{pointer}")
    return current


def _validate_string_list(container, field, prefix, errors, allow_empty=True):
    value = container.get(field)
    if not isinstance(value, list):
        errors.append(f"{prefix}.{field} 必须是数组")
        return
    if not allow_empty and not value:
        errors.append(f"{prefix}.{field} 至少需要一项")
    for index, item in enumerate(value):
        if not _nonblank(item):
            errors.append(f"{prefix}.{field}[{index}] 必须是非空字符串")


def _validate_source(claim, prefix, source_root, errors):
    source = claim.get("source")
    if not isinstance(source, dict):
        errors.append(f"{prefix}.source 必须是对象")
        return

    if not _nonblank(source.get("locator")):
        errors.append(f"{prefix}.source.locator 必须是非空字符串")

    path_value = source.get("path")
    url_value = source.get("url")
    if bool(path_value) == bool(url_value):
        errors.append(f"{prefix}.source 必须且只能指定 path 或 url")
        return

    if url_value:
        if not isinstance(url_value, str):
            errors.append(f"{prefix}.source.url 必须是字符串")
            return
        try:
            parsed = urlparse(url_value)
        except ValueError as exc:
            errors.append(f"{prefix}.source.url 无法解析：{exc}")
            return
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{prefix}.source.url 必须是有效的 HTTP 或 HTTPS URL")
        return

    if not _nonblank(path_value):
        errors.append(f"{prefix}.source.path 必须是非空字符串")
        return

    try:
        root = Path(source_root).resolve()
        source_path = (root / path_value).resolve()
    except (OSError, ValueError) as exc:
        errors.append(f"{prefix}.source.path 无法解析：{exc}")
        return
    try:
        source_path.relative_to(root)
    except ValueError:
        errors.append(f"{prefix}.source.path 超出指定来源目录")
        return
    if not source_path.is_file():
        errors.append(f"{prefix}.source.path 指向的文件不存在：{path_value}")
        return

    locator = source.get("locator")
    if source_path.suffix.lower() != ".json":
        return
    if not _nonblank(locator) or not locator.startswith("/"):
        errors.append(f"{prefix}.source.locator 对 JSON 来源必须使用 JSON Pointer")
        return

    try:
        with source_path.open(encoding="utf-8") as handle:
            source_document = json.load(handle)
        referenced_value = _resolve_json_pointer(source_document, locator)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{prefix}.source 无法解析：{exc}")
        return

    if "value" not in claim:
        return
    if isinstance(referenced_value, bool) or not isinstance(referenced_value, (int, float)):
        errors.append(f"{prefix}.source.locator 必须指向定量主张的数值")
    elif referenced_value != claim["value"]:
        errors.append(
            f"{prefix}.value 与来源数值不一致：记录为 {claim['value']}，来源为 {referenced_value}"
        )


def validate_record(record, source_root):
    """返回记录中的全部结构或本地引用错误。"""
    errors = []
    if not isinstance(record, dict):
        return ["研究记录必须是 JSON 对象"]

    if record.get("schema_version") != "research-record/v1":
        errors.append("schema_version 必须是 research-record/v1")
    if not _nonblank(record.get("question")):
        errors.append("question 必须是非空字符串")

    scope = record.get("scope")
    if not isinstance(scope, dict):
        errors.append("scope 必须是对象")
    else:
        for field in ("objective", "deliverable"):
            if not _nonblank(scope.get(field)):
                errors.append(f"scope.{field} 必须是非空字符串")
        _validate_string_list(scope, "allowed_sources", "scope", errors, allow_empty=False)
        _validate_string_list(scope, "excluded_sources", "scope", errors)

    claims = record.get("claims")
    if not isinstance(claims, list):
        errors.append("claims 必须是数组")
        return errors

    seen_ids = set()
    for index, claim in enumerate(claims):
        prefix = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{prefix} 必须是对象")
            continue

        claim_id = claim.get("id")
        if not _nonblank(claim_id):
            errors.append(f"{prefix}.id 必须是非空字符串")
        elif claim_id in seen_ids:
            errors.append(f"{prefix}.id 重复：{claim_id}")
        else:
            seen_ids.add(claim_id)

        if not _nonblank(claim.get("statement")):
            errors.append(f"{prefix}.statement 必须是非空字符串")
        status = claim.get("status")
        if status not in STATUSES:
            errors.append(f"{prefix}.status 必须是 {sorted(STATUSES)} 之一")
        if claim.get("evidence_role") not in EVIDENCE_ROLES:
            errors.append(f"{prefix}.evidence_role 必须是 {sorted(EVIDENCE_ROLES)} 之一")

        if "value" in claim:
            value = claim["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{prefix}.value 必须是有限数值")
            elif isinstance(value, float) and not math.isfinite(value):
                errors.append(f"{prefix}.value 必须是有限数值")
            for field in QUANTITATIVE_TEXT_FIELDS:
                if not _nonblank(claim.get(field)):
                    errors.append(f"{prefix}.{field} 是定量主张的必填字段")

        if status != "unverified" or "value" in claim:
            _validate_source(claim, prefix, source_root, errors)

    if "limitations" in record:
        _validate_string_list(record, "limitations", "研究记录", errors)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path, help="研究记录 JSON 路径")
    parser.add_argument(
        "--root",
        type=Path,
        help="本地来源根目录；默认使用研究记录所在目录",
    )
    args = parser.parse_args()
    source_root = args.root if args.root is not None else args.record.parent

    try:
        with args.record.open(encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"研究记录读取失败：{exc}\n")

    errors = validate_record(record, source_root)
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1

    print(f"研究记录有效：{len(record['claims'])} 项主张。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
