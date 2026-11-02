#!/usr/bin/env python3
"""检查研究运行清单，并计算确定性的采纳结果。"""

import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


SCHEMA_VERSION = "research-campaign/v1"
RESEARCH_LEVELS = {"candidate_search", "harness_evolution"}
EVIDENCE_LEVELS = {"E1", "E2", "E3", "E4"}
DATA_ROLES = {"development", "selection", "confirmation", "independent_oos"}
PARAMETER_TYPES = {"number", "integer", "boolean", "string"}
DIRECTIONS = {"minimize", "maximize"}
METRIC_SOURCES = {"stdout_key_value", "json_file"}
CAMPAIGN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SENSITIVE_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
GIT_REF = re.compile(r"^[A-Za-z0-9_./@^~{}-]+$")
PLACEHOLDER = re.compile(r"\{[^{}]+\}")
ALLOWED_PLACEHOLDERS = {"{python}", "{run_dir}", "{metrics_path}", "{parameters_path}"}
INVALID_POINTER_ESCAPE = re.compile(r"~(?![01])")
ARRAY_INDEX = re.compile(r"0|[1-9][0-9]*")


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _integer(value, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return minimum is None or value >= minimum


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _iso_date(value):
    if not _nonblank(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_fields(value, required, optional, prefix, errors):
    if not isinstance(value, dict):
        errors.append(f"{prefix} 必须是对象")
        return {}
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        errors.append(f"{prefix} 缺少字段：{sorted(missing)}")
    if unknown:
        errors.append(f"{prefix} 包含未知字段：{sorted(unknown)}")
    return value


def _check_text(mapping, field, prefix, errors):
    if not _nonblank(mapping.get(field)):
        errors.append(f"{prefix}.{field} 必须是非空字符串")


def _check_enum(mapping, field, allowed, prefix, errors):
    value = mapping.get(field)
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{prefix}.{field} 必须是 {sorted(allowed)} 之一")


def _check_string_list(mapping, field, prefix, errors, allow_empty=True):
    value = mapping.get(field)
    if not isinstance(value, list):
        errors.append(f"{prefix}.{field} 必须是数组")
        return
    if not allow_empty and not value:
        errors.append(f"{prefix}.{field} 至少需要一项")
    for index, item in enumerate(value):
        if not _nonblank(item):
            errors.append(f"{prefix}.{field}[{index}] 必须是非空字符串")


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复的 JSON 键：{key}")
        result[key] = value
    return result


def _read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=_reject_duplicate_keys)


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


def _validate_evidence(entries, root, errors):
    if not isinstance(entries, list):
        errors.append("evidence 必须是数组")
        return
    if not entries:
        errors.append("evidence 至少需要一项")
    seen = set()
    for index, entry in enumerate(entries):
        prefix = f"evidence[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        _check_fields(entry, {"id", "title", "source", "claim", "accessed_at"}, set(), prefix, errors)
        identifier = entry.get("id")
        if not _nonblank(identifier):
            errors.append(f"{prefix}.id 必须是非空字符串")
        elif identifier in seen:
            errors.append(f"{prefix}.id 重复：{identifier}")
        else:
            seen.add(identifier)
        for field in ("title", "claim"):
            _check_text(entry, field, prefix, errors)
        if not _iso_date(entry.get("accessed_at")):
            errors.append(f"{prefix}.accessed_at 必须是 ISO 日期")

        source = entry.get("source")
        if not isinstance(source, dict):
            errors.append(f"{prefix}.source 必须是对象")
            continue
        _check_fields(source, {"locator"}, {"path", "url"}, f"{prefix}.source", errors)
        _check_text(source, "locator", f"{prefix}.source", errors)
        path_value = source.get("path")
        url_value = source.get("url")
        if bool(path_value) == bool(url_value):
            errors.append(f"{prefix}.source 必须且只能指定 path 或 url")
            continue
        if url_value:
            try:
                parsed = urlparse(url_value)
            except (TypeError, ValueError):
                errors.append(f"{prefix}.source.url 无法解析")
                continue
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append(f"{prefix}.source.url 必须是绝对 HTTPS URL")
            continue
        if not _nonblank(path_value):
            errors.append(f"{prefix}.source.path 必须是非空字符串")
            continue
        pure = PurePosixPath(path_value)
        if pure.is_absolute() or ".." in pure.parts:
            errors.append(f"{prefix}.source.path 超出来源目录")
            continue
        try:
            source_path = (Path(root) / path_value).resolve()
            source_path.relative_to(Path(root).resolve())
        except (OSError, ValueError):
            errors.append(f"{prefix}.source.path 超出来源目录")
            continue
        if not source_path.is_file():
            errors.append(f"{prefix}.source.path 指向的文件不存在：{path_value}")
            continue
        if source_path.suffix.lower() == ".json":
            locator = source.get("locator")
            if not _nonblank(locator) or not locator.startswith("/"):
                errors.append(f"{prefix}.source.locator 对 JSON 来源必须使用 JSON Pointer")
                continue
            try:
                with source_path.open(encoding="utf-8") as handle:
                    document = json.load(handle, object_pairs_hook=_reject_duplicate_keys)
                _resolve_json_pointer(document, locator)
            except (OSError, json.JSONDecodeError, ValueError) as error:
                errors.append(f"{prefix}.source 无法解析：{error}")


def _parameter_error(rule, value):
    kind = rule["type"]
    if kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "number":
        valid = _finite_number(value)
    else:
        valid = isinstance(value, str)
    if not valid:
        return f"类型必须为 {kind}"

    minimum = rule.get("minimum")
    maximum = rule.get("maximum")
    if minimum is not None and value < minimum:
        return f"数值低于最小值 {minimum}"
    if maximum is not None and value > maximum:
        return f"数值超过最大值 {maximum}"
    choices = rule.get("choices")
    if choices is not None and value not in choices:
        return "数值不在允许选项内"
    return None


def _parse_search_space(search_space, prefix, errors):
    rules = {}
    if not isinstance(search_space, dict):
        errors.append(f"{prefix} 必须是对象")
        return rules
    for name, raw_rule in search_space.items():
        rule_prefix = f"{prefix}.{name}"
        if not _nonblank(name):
            errors.append(f"{rule_prefix}.name 必须是非空字符串")
        if not isinstance(raw_rule, dict):
            errors.append(f"{rule_prefix} 必须是对象")
            continue
        _check_fields(raw_rule, {"type"}, {"minimum", "maximum", "choices"}, rule_prefix, errors)
        kind = raw_rule.get("type")
        if not isinstance(kind, str) or kind not in PARAMETER_TYPES:
            errors.append(f"{rule_prefix}.type 必须是 {sorted(PARAMETER_TYPES)} 之一")
            continue
        rule = {"type": kind}
        minimum = raw_rule.get("minimum")
        maximum = raw_rule.get("maximum")
        if kind in {"boolean", "string"} and (minimum is not None or maximum is not None):
            errors.append(f"{rule_prefix} 的类型不能声明数值边界")
        if minimum is not None:
            if not _finite_number(minimum):
                errors.append(f"{rule_prefix}.minimum 必须是有限数值")
            elif kind == "integer" and not float(minimum).is_integer():
                errors.append(f"{rule_prefix}.minimum 必须是整数")
            else:
                rule["minimum"] = int(minimum) if kind == "integer" else minimum
        if maximum is not None:
            if not _finite_number(maximum):
                errors.append(f"{rule_prefix}.maximum 必须是有限数值")
            elif kind == "integer" and not float(maximum).is_integer():
                errors.append(f"{rule_prefix}.maximum 必须是整数")
            else:
                rule["maximum"] = int(maximum) if kind == "integer" else maximum
        if "minimum" in rule and "maximum" in rule and rule["minimum"] > rule["maximum"]:
            errors.append(f"{rule_prefix}.minimum 超过 maximum")
        choices = raw_rule.get("choices")
        if choices is not None:
            if not isinstance(choices, list) or not choices:
                errors.append(f"{rule_prefix}.choices 必须是非空数组")
            elif len({json.dumps(item, sort_keys=True) for item in choices}) != len(choices):
                errors.append(f"{rule_prefix}.choices 必须唯一")
            else:
                rule["choices"] = tuple(choices)
                for choice in choices:
                    detail = _parameter_error(rule, choice)
                    if detail is not None:
                        errors.append(f"{rule_prefix}.choices 包含无效值：{detail}")
        rules[name] = rule
    return rules


def _validate_parameters(rules, parameters, prefix, errors):
    if not isinstance(parameters, dict):
        errors.append(f"{prefix} 必须是对象")
        return
    if set(parameters) != set(rules):
        errors.append(f"{prefix} 的键必须与 search_space 完全一致：{sorted(rules)}")
        return
    for name, rule in rules.items():
        detail = _parameter_error(rule, parameters[name])
        if detail is not None:
            errors.append(f"{prefix}.{name} 无效：{detail}")


def _validate_design_lock(value, errors):
    if not isinstance(value, dict):
        errors.append("design_lock 必须是对象")
        return
    _check_fields(value, {"status", "locked_at", "retrospective", "reference"}, set(), "design_lock", errors)
    if value.get("status") != "locked":
        errors.append("design_lock.status 必须是 locked")
    if not _iso_date(value.get("locked_at")):
        errors.append("design_lock.locked_at 必须是 ISO 日期")
    if not isinstance(value.get("retrospective"), bool):
        errors.append("design_lock.retrospective 必须是布尔值")
    _check_text(value, "reference", "design_lock", errors)


def _validate_protocol(value, errors):
    if not isinstance(value, dict):
        errors.append("protocol 必须是对象")
        return
    _check_fields(value, {"id", "data_role", "statistical_unit", "comparison", "frozen"}, set(), "protocol", errors)
    _check_text(value, "id", "protocol", errors)
    _check_enum(value, "data_role", DATA_ROLES, "protocol", errors)
    for field in ("statistical_unit", "comparison"):
        _check_text(value, field, "protocol", errors)
    frozen = value.get("frozen")
    if not isinstance(frozen, bool):
        errors.append("protocol.frozen 必须是布尔值")
    elif value.get("data_role") in {"confirmation", "independent_oos"} and not frozen:
        errors.append(f"protocol.frozen 在 {value.get('data_role')} 阶段必须为 true")


def _validate_runner(value, errors):
    if not isinstance(value, dict):
        errors.append("runner 必须是对象")
        return
    _check_fields(
        value,
        {"command", "working_directory", "timeout_seconds", "metrics_source", "environment_allowlist"},
        {"code_patch"},
        "runner",
        errors,
    )
    command = value.get("command")
    if not isinstance(command, list) or not command:
        errors.append("runner.command 必须是非空数组")
    elif any(not _nonblank(part) for part in command):
        errors.append("runner.command 的每一项必须是非空字符串")
    else:
        for part in command:
            unknown = set(PLACEHOLDER.findall(part)) - ALLOWED_PLACEHOLDERS
            if unknown:
                errors.append(f"runner.command 包含不支持的占位符：{sorted(unknown)}")

    working = value.get("working_directory")
    if not _nonblank(working):
        errors.append("runner.working_directory 必须是非空字符串")
    else:
        pure = PurePosixPath(working)
        if pure.is_absolute() or ".." in pure.parts:
            errors.append("runner.working_directory 必须位于项目根目录内")

    timeout = value.get("timeout_seconds")
    if not _finite_number(timeout) or timeout <= 0:
        errors.append("runner.timeout_seconds 必须是正有限数值")

    metrics_source = value.get("metrics_source")
    if not isinstance(metrics_source, str) or metrics_source not in METRIC_SOURCES:
        errors.append(f"runner.metrics_source 必须是 {sorted(METRIC_SOURCES)} 之一")

    allowlist = value.get("environment_allowlist")
    if not isinstance(allowlist, list):
        errors.append("runner.environment_allowlist 必须是数组")
    else:
        seen = set()
        for index, name in enumerate(allowlist):
            if not isinstance(name, str) or not ENVIRONMENT_NAME.fullmatch(name):
                errors.append(f"runner.environment_allowlist[{index}] 名称无效")
                continue
            if name in seen:
                errors.append("runner.environment_allowlist 必须唯一")
            seen.add(name)
            if SENSITIVE_NAME.search(name):
                errors.append(f"runner.environment_allowlist[{index}] 不允许敏感变量")

    if "code_patch" in value:
        _validate_patch(value["code_patch"], errors)


def _validate_patch(value, errors):
    if not isinstance(value, dict):
        errors.append("runner.code_patch 必须是对象")
        return
    _check_fields(
        value,
        {"allowed_paths"},
        {"base_ref", "max_patch_bytes", "max_files"},
        "runner.code_patch",
        errors,
    )
    paths = value.get("allowed_paths")
    if not isinstance(paths, list) or not paths:
        errors.append("runner.code_patch.allowed_paths 必须是非空数组")
    else:
        seen = set()
        for index, item in enumerate(paths):
            if not _nonblank(item):
                errors.append(f"runner.code_patch.allowed_paths[{index}] 必须是非空字符串")
                continue
            pure = PurePosixPath(item)
            if pure.is_absolute() or ".." in pure.parts or not item.endswith("/"):
                errors.append("allowed_paths 必须是相对于项目根目录、以 / 结尾的目录前缀")
            if item in seen:
                errors.append(f"runner.code_patch.allowed_paths 重复：{item}")
            seen.add(item)

    base_ref = value.get("base_ref", "HEAD")
    if not isinstance(base_ref, str) or not GIT_REF.fullmatch(base_ref) or base_ref.startswith("-"):
        errors.append("runner.code_patch.base_ref 不是安全的 Git 引用")

    max_bytes = value.get("max_patch_bytes", 200_000)
    if not _integer(max_bytes) or not 1 <= max_bytes <= 10_000_000:
        errors.append("runner.code_patch.max_patch_bytes 必须在 1 到 10000000 之间")

    max_files = value.get("max_files", 8)
    if not _integer(max_files) or not 1 <= max_files <= 64:
        errors.append("runner.code_patch.max_files 必须在 1 到 64 之间")


def _validate_evaluation(value, errors):
    if not isinstance(value, dict):
        errors.append("evaluation 必须是对象")
        return
    _check_fields(value, {"primary_metric", "minimum_improvement", "metrics"}, set(), "evaluation", errors)
    _check_text(value, "primary_metric", "evaluation", errors)

    minimum = value.get("minimum_improvement")
    if not _finite_number(minimum) or minimum < 0:
        errors.append("evaluation.minimum_improvement 必须是非负有限数值")

    metrics = value.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        errors.append("evaluation.metrics 必须是非空对象")
        return
    for name, raw_rule in metrics.items():
        prefix = f"evaluation.metrics.{name}"
        if not _nonblank(name):
            errors.append(f"{prefix}.name 必须是非空字符串")
        if not isinstance(raw_rule, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        _check_fields(raw_rule, {"direction"}, {"limit", "regression_tolerance"}, prefix, errors)
        _check_enum(raw_rule, "direction", DIRECTIONS, prefix, errors)
        limit = raw_rule.get("limit")
        if limit is not None and not _finite_number(limit):
            errors.append(f"{prefix}.limit 必须是有限数值")
        tolerance = raw_rule.get("regression_tolerance", 0)
        if not _finite_number(tolerance) or tolerance < 0:
            errors.append(f"{prefix}.regression_tolerance 必须是非负有限数值")

    primary = value.get("primary_metric")
    if isinstance(primary, str) and primary and primary not in metrics:
        errors.append("evaluation.primary_metric 必须在 metrics 中声明")


def _validate_budget(value, errors):
    if not isinstance(value, dict):
        errors.append("budget 必须是对象")
        return
    _check_fields(
        value,
        {"max_iterations", "max_consecutive_failures"},
        {"max_model_calls", "max_input_tokens", "max_output_tokens", "max_wall_seconds"},
        "budget",
        errors,
    )
    for field in ("max_iterations", "max_consecutive_failures"):
        if not _integer(value.get(field), 1):
            errors.append(f"budget.{field} 必须是正整数")
    for field in ("max_model_calls", "max_input_tokens", "max_output_tokens"):
        if field in value and not _integer(value[field], 0):
            errors.append(f"budget.{field} 必须是非负整数")
    if "max_wall_seconds" in value:
        wall = value["max_wall_seconds"]
        if not _finite_number(wall) or wall < 0:
            errors.append("budget.max_wall_seconds 必须是非负有限数值")


def validate_campaign(config, root):
    """返回研究运行清单中的全部契约错误。"""
    errors = []
    if not isinstance(config, dict):
        return ["研究运行清单必须是 JSON 对象"]

    _check_fields(
        config,
        {
            "schema_version",
            "campaign_id",
            "question",
            "research_level",
            "evidence_level",
            "design_lock",
            "protocol",
            "data_snapshot",
            "mapping_version",
            "seed",
            "evidence",
            "baseline_parameters",
            "search_space",
            "runner",
            "evaluation",
            "budget",
        },
        {"proposer"},
        "研究运行清单",
        errors,
    )
    if config.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION}")

    campaign_id = config.get("campaign_id")
    if not _nonblank(campaign_id) or not CAMPAIGN_ID.fullmatch(campaign_id):
        errors.append("campaign_id 必须是安全的单级路径名称")
    _check_text(config, "question", "研究运行清单", errors)
    _check_enum(config, "research_level", RESEARCH_LEVELS, "研究运行清单", errors)
    _check_enum(config, "evidence_level", EVIDENCE_LEVELS, "研究运行清单", errors)
    _validate_design_lock(config.get("design_lock"), errors)
    _validate_protocol(config.get("protocol"), errors)
    for field in ("data_snapshot", "mapping_version"):
        _check_text(config, field, "研究运行清单", errors)

    seed = config.get("seed")
    if not _integer(seed, 0) or seed > 4294967295:
        errors.append("seed 必须是 0 到 4294967295 之间的整数")

    _validate_evidence(config.get("evidence"), root, errors)
    rules = _parse_search_space(config.get("search_space"), "search_space", errors)
    _validate_parameters(rules, config.get("baseline_parameters"), "baseline_parameters", errors)
    _validate_runner(config.get("runner"), errors)
    _validate_evaluation(config.get("evaluation"), errors)
    _validate_budget(config.get("budget"), errors)

    if "proposer" in config:
        proposer = config["proposer"]
        if not isinstance(proposer, dict):
            errors.append("proposer 必须是对象")
        elif not _nonblank(proposer.get("type")):
            errors.append("proposer.type 必须是非空字符串")
    return errors


def _metric_rules(config):
    return config["evaluation"]["metrics"]


def evaluate_run(config, result, baseline=None):
    """根据运行结果与基线计算确定性采纳结果。"""
    reasons = []
    primary = config["evaluation"]["primary_metric"]
    metrics = result.get("metrics") if isinstance(result, dict) else None
    status = result.get("status") if isinstance(result, dict) else None

    if status != "succeeded":
        errors = result.get("errors") if isinstance(result, dict) else None
        if isinstance(errors, list) and errors:
            reasons.extend(item for item in errors if _nonblank(item))
        if not reasons:
            reasons.append("实验未成功完成")

    if not isinstance(metrics, dict):
        reasons.append("运行结果缺少 metrics 对象")
        metrics = {}

    rules = _metric_rules(config)
    for name, rule in rules.items():
        if name not in metrics:
            reasons.append(f"缺少必需指标：{name}")
            continue
        value = metrics[name]
        if not _finite_number(value):
            reasons.append(f"指标不是有限数值：{name}")
            continue
        limit = rule.get("limit")
        if limit is not None:
            if rule["direction"] == "minimize" and value > limit:
                reasons.append(f"指标超过上限：{name}")
            if rule["direction"] == "maximize" and value < limit:
                reasons.append(f"指标低于下限：{name}")

    after = metrics.get(primary)
    before = None
    improvement = None
    if not _finite_number(after):
        reasons.append("主要指标不可用")
    if baseline is not None:
        baseline_metrics = baseline.get("metrics") if isinstance(baseline, dict) else None
        if not isinstance(baseline_metrics, dict):
            reasons.append("基线缺少 metrics 对象")
            baseline_metrics = {}
        before = baseline_metrics.get(primary)
        if not _finite_number(before):
            reasons.append("基线主要指标不可用")
        elif _finite_number(after) and not any(
            reason.startswith("缺少必需指标") or reason.startswith("指标不是有限数值")
            for reason in reasons
        ):
            direction = rules[primary]["direction"]
            improvement = before - after if direction == "minimize" else after - before
            minimum = config["evaluation"]["minimum_improvement"]
            if improvement <= 0 or improvement < minimum:
                reasons.append("主要指标改善未达到要求")
            for name, rule in rules.items():
                if name == primary:
                    continue
                current = metrics.get(name)
                previous = baseline_metrics.get(name)
                if not _finite_number(current):
                    reasons.append(f"当前指标不可用：{name}")
                    continue
                if not _finite_number(previous):
                    reasons.append(f"基线指标不可用：{name}")
                    continue
                regression = current - previous if rule["direction"] == "minimize" else previous - current
                tolerance = rule.get("regression_tolerance", 0)
                if regression > tolerance:
                    reasons.append(f"守卫指标退化超过容差：{name}")

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "primary_before": before,
        "primary_after": after,
        "improvement": improvement,
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="研究运行清单 JSON 路径")
    parser.add_argument("--result", type=Path, help="运行结果 JSON 路径")
    parser.add_argument("--baseline", type=Path, help="基线运行结果 JSON 路径")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        config = _read_json(args.config)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(2, f"研究运行清单读取失败：{exc}\n")

    errors = validate_campaign(config, args.config.parent)
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1

    if args.result is None:
        if args.baseline is not None:
            parser.error("--baseline 需要与 --result 一起使用")
        print(
            f"研究运行清单有效：{config['campaign_id']}，"
            f"证据等级 {config['evidence_level']}。"
        )
        return 0

    try:
        result = _read_json(args.result)
        baseline = _read_json(args.baseline) if args.baseline is not None else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(2, f"运行结果读取失败：{exc}\n")

    decision = evaluate_run(config, result, baseline)
    print(json.dumps(decision, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if decision["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
