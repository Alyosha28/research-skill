#!/usr/bin/env python3
"""检查通用研究状态、路线、预算与恢复契约。"""

import argparse
import json
import math
from pathlib import Path
import sys


RESEARCH_LEVELS = {"candidate_search", "harness_evolution"}
DATA_ROLES = {"development", "selection", "confirmation", "independent_oos"}
PROPOSAL_STATUSES = {"proposed", "kept", "revised", "dropped", "inconclusive"}
ROUTES = {"EXPLOIT", "REPAIR", "FORK", "REFRAME", "STOP"}


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _mapping(parent, field, prefix, errors):
    value = parent.get(field)
    if not isinstance(value, dict):
        errors.append(f"{prefix}.{field} 必须是对象")
        return {}
    return value


def _required_text(mapping, field, prefix, errors):
    if not _nonblank(mapping.get(field)):
        errors.append(f"{prefix}.{field} 必须是非空字符串")


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def _required_enum(mapping, field, allowed, prefix, errors):
    value = mapping.get(field)
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{prefix}.{field} 必须是 {sorted(allowed)} 之一")
        return None
    return value


def _validate_usage(proposal, prefix, errors):
    _required_text(proposal, "model_id", prefix, errors)
    usage = proposal.get("usage")
    if not isinstance(usage, dict):
        errors.append(f"{prefix}.usage 必须是对象")
        return
    for field in ("input_tokens", "output_tokens"):
        value = usage.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{prefix}.usage.{field} 必须是非负整数")


def _validate_budget(budget, errors):
    if not budget:
        errors.append("budget 至少需要一种资源")
    for resource, limits in budget.items():
        prefix = f"budget.{resource}"
        if not isinstance(limits, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        used = limits.get("used")
        limit = limits.get("limit")
        if not _finite_number(used) or used < 0:
            errors.append(f"{prefix}.used 必须是非负有限数值")
        if not _finite_number(limit) or limit < 0:
            errors.append(f"{prefix}.limit 必须是非负有限数值")
        if _finite_number(used) and _finite_number(limit) and used > limit:
            errors.append(f"{prefix}.used 超过 limit")


def _validate_proposals(proposals, errors):
    if not isinstance(proposals, list):
        errors.append("proposals 必须是数组")
        return
    seen_ids = set()
    for index, proposal in enumerate(proposals):
        prefix = f"proposals[{index}]"
        if not isinstance(proposal, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        proposal_id = proposal.get("id")
        if not _nonblank(proposal_id):
            errors.append(f"{prefix}.id 必须是非空字符串")
        elif proposal_id in seen_ids:
            errors.append(f"{prefix}.id 重复：{proposal_id}")
        else:
            seen_ids.add(proposal_id)
        for field in ("hypothesis", "expected_mechanism", "applicability", "falsification"):
            _required_text(proposal, field, prefix, errors)
        edit = proposal.get("edit")
        if not isinstance(edit, dict) or not edit:
            errors.append(f"{prefix}.edit 必须是非空对象")
        _validate_usage(proposal, prefix, errors)
        _required_enum(proposal, "status", PROPOSAL_STATUSES, prefix, errors)


def _validate_route(route, protocol_id, run_id, errors):
    decision = _required_enum(route, "decision", ROUTES, "route", errors)
    _required_text(route, "reason", "route", errors)
    _required_text(route, "source_run", "route", errors)
    source_run = route.get("source_run")
    if _nonblank(source_run) and _nonblank(run_id) and source_run != run_id:
        errors.append("route.source_run 必须与 recovery.run_id 一致")

    if decision in {"FORK", "REFRAME"}:
        _required_text(route, "next_run", "route", errors)
        next_run = route.get("next_run")
        if _nonblank(next_run) and next_run == source_run:
            errors.append(f"route.next_run 在 {decision} 时必须指向新运行")
    if decision == "FORK":
        next_protocol = route.get("next_protocol")
        if next_protocol is not None and next_protocol != protocol_id:
            errors.append("route.next_protocol 在 FORK 时必须保持当前协议")
    if decision == "REFRAME":
        _required_text(route, "next_protocol", "route", errors)
        next_protocol = route.get("next_protocol")
        if _nonblank(next_protocol) and next_protocol == protocol_id:
            errors.append("route.next_protocol 在 REFRAME 时必须使用新协议")


def _validate_memory(memory, errors):
    used = memory.get("used")
    if not isinstance(used, list):
        errors.append("memory.used 必须是数组")
    else:
        for index, lesson in enumerate(used):
            prefix = f"memory.used[{index}]"
            if not isinstance(lesson, dict):
                errors.append(f"{prefix} 必须是对象")
                continue
            for field in ("id", "evidence", "applicability"):
                _required_text(lesson, field, prefix, errors)
    _required_text(memory, "route_history", "memory", errors)


def validate_state(state):
    """返回研究状态中的全部契约错误。"""
    errors = []
    if not isinstance(state, dict):
        return ["研究状态必须是 JSON 对象"]
    if state.get("schema_version") != "research-state/v1":
        errors.append("schema_version 必须是 research-state/v1")

    question = _mapping(state, "question", "研究状态", errors)
    for field in ("id", "statement", "primary_metric", "falsification"):
        _required_text(question, field, "question", errors)
    _required_enum(question, "research_level", RESEARCH_LEVELS, "question", errors)

    protocol = _mapping(state, "protocol", "研究状态", errors)
    _required_text(protocol, "id", "protocol", errors)
    data_role = _required_enum(protocol, "data_role", DATA_ROLES, "protocol", errors)
    for field in ("statistical_unit", "comparison"):
        _required_text(protocol, field, "protocol", errors)
    if not isinstance(protocol.get("frozen"), bool):
        errors.append("protocol.frozen 必须是布尔值")
    elif data_role in {"confirmation", "independent_oos"} and not protocol["frozen"]:
        errors.append(f"protocol.frozen 在 {data_role} 阶段必须为 true")

    states = _mapping(state, "states", "研究状态", errors)
    for field in ("active", "reference"):
        _required_text(states, field, "states", errors)

    budget = state.get("budget")
    if not isinstance(budget, dict):
        errors.append("budget 必须是对象")
    else:
        _validate_budget(budget, errors)

    _validate_proposals(state.get("proposals"), errors)

    recovery = _mapping(state, "recovery", "研究状态", errors)
    for field in ("run_id", "config", "result", "trace", "resume_command"):
        _required_text(recovery, field, "recovery", errors)

    route = _mapping(state, "route", "研究状态", errors)
    _validate_route(route, protocol.get("id"), recovery.get("run_id"), errors)

    memory = _mapping(state, "memory", "研究状态", errors)
    _validate_memory(memory, errors)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path, help="研究状态 JSON 路径")
    args = parser.parse_args()
    try:
        with args.state.open(encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"研究状态读取失败：{exc}\n")

    errors = validate_state(state)
    if errors:
        for error in errors:
            print(f"错误：{error}", file=sys.stderr)
        return 1
    route = state["route"]["decision"]
    print(f"研究状态有效：{len(state['proposals'])} 项提案，路线 {route}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
