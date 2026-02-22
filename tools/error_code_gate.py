#!/usr/bin/env python3
"""CI gate for stable error-code contract compatibility."""


from pathlib import Path
from typing import Any
import json
import ast
import os


ROOT          = Path(__file__).resolve().parents[1]
MODEL_FILE    = ROOT / "pnp" / "error_model.py"
LOCK_FILE     = ROOT / "docs" / "error_code_lock.json"
APPROVAL_FILE = ROOT / ".error_code_breaking_change_approved"


def _extract_dict(name: str, text: str) -> dict[str, Any]:
    tree = ast.parse(text, filename=str(MODEL_FILE))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = ast.literal_eval(node.value)
                    if not isinstance(value, dict):
                        raise TypeError(f"{name} is not a dict literal")
                    return value
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name and node.value is not None:
                value = ast.literal_eval(node.value)
                if not isinstance(value, dict):
                    raise TypeError(f"{name} is not a dict literal")
                return value
    raise KeyError(f"{name} not found in {MODEL_FILE}")


def current_contract() -> dict[str, Any]:
    text = MODEL_FILE.read_text(encoding="utf-8")
    workflow = _extract_dict("WORKFLOW_STEP_CODES", text)
    aliases = _extract_dict("DEPRECATED_ERROR_CODE_ALIASES", text)
    policy = _extract_dict("ERROR_CODE_POLICY", text)
    normalized_policy: dict[str, dict[str, str]] = {}
    for code, meta in policy.items():
        if not isinstance(meta, dict):
            continue
        severity = str(meta.get("severity", "")).strip()
        category = str(meta.get("category", "")).strip()
        normalized_policy[str(code)] = {
            "severity": severity,
            "category": category,
        }
    return {
        "schema": "pnp.error_codes.v1",
        "schema_version": 1,
        "workflow_step_codes": workflow,
        "deprecated_aliases": aliases,
        "error_code_policy": normalized_policy,
    }


def compare_contracts(lock: dict[str, Any], curr: dict[str, Any]) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    notes: list[str] = []

    lock_workflow = dict(lock.get("workflow_step_codes", {}))
    curr_workflow = dict(curr.get("workflow_step_codes", {}))
    for step, code in lock_workflow.items():
        if step not in curr_workflow:
            issues.append(f"workflow step removed: {step}")
            continue
        if curr_workflow[step] != code:
            issues.append(f"workflow step mapping changed: {step} {code} -> {curr_workflow[step]}")
    for step in curr_workflow:
        if step not in lock_workflow:
            notes.append(f"new workflow step mapping added: {step} -> {curr_workflow[step]}")

    lock_aliases = dict(lock.get("deprecated_aliases", {}))
    curr_aliases = dict(curr.get("deprecated_aliases", {}))
    for old, canonical in lock_aliases.items():
        if old not in curr_aliases:
            issues.append(f"deprecated alias removed: {old}")
            continue
        if curr_aliases[old] != canonical:
            issues.append(f"deprecated alias target changed: {old} {canonical} -> {curr_aliases[old]}")
    for old in curr_aliases:
        if old not in lock_aliases:
            notes.append(f"new deprecated alias added: {old} -> {curr_aliases[old]}")

    lock_policy = dict(lock.get("error_code_policy", {}))
    curr_policy = dict(curr.get("error_code_policy", {}))
    for code, lock_meta in lock_policy.items():
        if code not in curr_policy:
            issues.append(f"stable error code removed: {code}")
            continue
        if curr_policy[code] != lock_meta:
            issues.append(f"stable error code policy changed: {code} {lock_meta} -> {curr_policy[code]}")
    for code in curr_policy:
        if code not in lock_policy:
            notes.append(f"new stable error code added: {code}")

    return issues, notes


def _override_active() -> bool:
    token = os.environ.get("PNP_ALLOW_ERROR_CODE_BREAK", "").strip().lower()
    if token in {"1", "true", "yes"}:
        return True
    return APPROVAL_FILE.exists()


def main() -> int:
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    curr = current_contract()
    issues, notes = compare_contracts(lock, curr)
    approved = _override_active()

    if issues and not approved:
        print("Error code gate failed:")
        for item in issues:
            print(f" - {item}")
        if notes:
            print("Non-breaking additions detected:")
            for item in notes:
                print(f" - {item}")
        print("Breaking changes require migration notes using docs/ERROR_CODE_MIGRATION_TEMPLATE.md")
        print(
            "Set PNP_ALLOW_ERROR_CODE_BREAK=1 or add "
            ".error_code_breaking_change_approved to override."
        )
        return 1

    if issues and approved:
        print("Error code gate override active; continuing despite breaking changes:")
        for item in issues:
            print(f" - {item}")
        return 0

    print("Error code gate passed.")
    if notes:
        print("Detected additions:")
        for item in notes:
            print(f" - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
