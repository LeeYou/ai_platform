"""AI Pipeline orchestration engine.

Manages pipeline definitions (stored as JSON files) and executes
multi-step AI capability pipelines with conditional branching and
result pass-through.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger("prod")

# ---------------------------------------------------------------------------
# Default pipeline storage directory
# ---------------------------------------------------------------------------
PIPELINE_DIR = os.getenv(
    "PIPELINE_DIR",
    os.path.join(os.getenv("MOUNT_ROOT", "/mnt/ai_platform"), "pipelines"),
)


# ---------------------------------------------------------------------------
# Pipeline definition schema helpers
# ---------------------------------------------------------------------------

def _validate_step(step: dict, available_capabilities: list[str]) -> list[str]:
    """Validate a single pipeline step definition. Returns a list of errors."""
    errors: list[str] = []
    if not step.get("step_id"):
        errors.append("step missing 'step_id'")
    if not step.get("capability"):
        errors.append(f"step '{step.get('step_id', '?')}' missing 'capability'")
    elif step["capability"] not in available_capabilities:
        errors.append(
            f"step '{step.get('step_id', '?')}': capability "
            f"'{step['capability']}' not available"
        )
    on_fail = step.get("on_failure", "abort")
    if on_fail not in ("abort", "skip", "default"):
        errors.append(f"step '{step.get('step_id', '?')}': invalid on_failure '{on_fail}'")
    return errors


def validate_pipeline(pipeline: dict, available_capabilities: list[str]) -> list[str]:
    """Validate a full pipeline definition. Returns a list of error messages."""
    errors: list[str] = []
    if not pipeline.get("pipeline_id"):
        errors.append("missing 'pipeline_id'")
    if not pipeline.get("name"):
        errors.append("missing 'name'")
    steps = pipeline.get("steps", [])
    if not steps:
        errors.append("pipeline has no steps")
    seen_ids: set[str] = set()
    for step in steps:
        sid = step.get("step_id", "")
        if sid in seen_ids:
            errors.append(f"duplicate step_id '{sid}'")
        seen_ids.add(sid)
        errors.extend(_validate_step(step, available_capabilities))
    return errors


# ---------------------------------------------------------------------------
# Simple expression evaluator for conditions and output mapping
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\$\{([a-zA-Z0-9_]+)\.([a-zA-Z0-9_.]+)\}")


def _resolve_var(match: re.Match, context: dict[str, dict]) -> str:
    """Resolve ${step_id.key} variable references."""
    step_id = match.group(1)
    key = match.group(2)
    step_data = context.get(step_id, {})
    val = step_data.get(key)
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    return json.dumps(val)


def _eval_expression(expr: str, context: dict[str, dict]) -> Any:
    """Evaluate a simple expression with variable substitution.

    Supports:
    - Variable references: ${step_id.key}
    - Comparisons: ==, !=, >=, <=, >, <
    - Logical: &&, ||
    - Literals: true, false, numbers
    """
    if not expr or not expr.strip():
        return True  # empty condition = always true

    # Substitute variables
    resolved = _VAR_RE.sub(lambda m: _resolve_var(m, context), expr)

    # Simple boolean eval (safe subset)
    resolved = resolved.strip()
    if resolved in ("true", "True"):
        return True
    if resolved in ("false", "False", "null"):
        return False

    # Handle && and || by splitting
    if "&&" in resolved:
        parts = [p.strip() for p in resolved.split("&&")]
        return all(_eval_single_comparison(p) for p in parts)
    if "||" in resolved:
        parts = [p.strip() for p in resolved.split("||")]
        return any(_eval_single_comparison(p) for p in parts)

    return _eval_single_comparison(resolved)


def _eval_single_comparison(expr: str) -> bool:
    """Evaluate a single comparison expression like 'value >= 0.5'."""
    expr = expr.strip()
    if expr in ("true", "True"):
        return True
    if expr in ("false", "False", "null"):
        return False

    for op in (">=", "<=", "!=", "==", ">", "<"):
        if op in expr:
            parts = expr.split(op, 1)
            if len(parts) == 2:
                left = _parse_value(parts[0].strip())
                right = _parse_value(parts[1].strip())
                if op == ">=":
                    return left >= right
                if op == "<=":
                    return left <= right
                if op == "!=":
                    return left != right
                if op == "==":
                    return left == right
                if op == ">":
                    return left > right
                if op == "<":
                    return left < right

    # Try as a truthy value
    val = _parse_value(expr)
    return bool(val)


def _parse_value(s: str) -> Any:
    """Parse a string value into a Python type."""
    s = s.strip()
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s == "null":
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    # Strip quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


# ---------------------------------------------------------------------------
# JSONPath-like extraction (simplified)
# ---------------------------------------------------------------------------

def _extract_jsonpath(data: Any, path: str) -> Any:
    """Extract a value from nested data using a simplified JSONPath.

    Supports: $.key.subkey, $.key[0].subkey
    """
    if not path.startswith("$."):
        return data
    parts = path[2:]  # strip "$."
    current = data
    for token in re.split(r"\.|\[(\d+)\]\.?", parts):
        if not token:
            continue
        if token.isdigit():
            idx = int(token)
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(token)
        else:
            return None
        if current is None:
            return None
    return current


# ---------------------------------------------------------------------------
# Pipeline file CRUD
# ---------------------------------------------------------------------------

def _ensure_pipeline_dir() -> None:
    os.makedirs(PIPELINE_DIR, exist_ok=True)


def _pipeline_path(pipeline_id: str) -> str:
    # Sanitize pipeline_id to prevent path traversal
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", pipeline_id)
    if not safe_id:
        raise ValueError("Invalid pipeline_id")
    return os.path.join(PIPELINE_DIR, f"{safe_id}.json")


def list_pipelines() -> list[dict]:
    """List all pipeline definitions."""
    _ensure_pipeline_dir()
    pipelines = []
    for fname in sorted(os.listdir(PIPELINE_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(PIPELINE_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            pipelines.append(data)
        except Exception as exc:
            logger.warning("Failed to read pipeline %s: %s", fpath, exc)
    return pipelines


def get_pipeline(pipeline_id: str) -> dict | None:
    """Get a single pipeline definition by ID."""
    fpath = _pipeline_path(pipeline_id)
    if not os.path.exists(fpath):
        return None
    with open(fpath, encoding="utf-8") as f:
        return json.load(f)


def save_pipeline(pipeline: dict) -> None:
    """Save a pipeline definition to file."""
    _ensure_pipeline_dir()
    fpath = _pipeline_path(pipeline["pipeline_id"])
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(pipeline, f, ensure_ascii=False, indent=2)
    logger.info("Saved pipeline %s to %s", pipeline["pipeline_id"], fpath)


def delete_pipeline_file(pipeline_id: str) -> bool:
    """Delete a pipeline definition file. Returns True if deleted."""
    fpath = _pipeline_path(pipeline_id)
    if os.path.exists(fpath):
        os.remove(fpath)
        logger.info("Deleted pipeline %s", pipeline_id)
        return True
    return False


# ---------------------------------------------------------------------------
# Pipeline execution engine
# ---------------------------------------------------------------------------

def execute_pipeline(
    pipeline: dict,
    image_bytes: bytes,
    infer_fn,
    check_license_fn,
    global_options: dict | None = None,
) -> dict:
    """Execute a pipeline and return the full result.

    Args:
        pipeline: The pipeline definition dict.
        image_bytes: Raw image bytes from the uploaded file.
        infer_fn: Callable(capability, image_bytes, options) -> dict with inference result.
        check_license_fn: Callable(capability) -> None, raises if not licensed.
        global_options: Optional per-step option overrides {step_id: {options}}.

    Returns:
        Full pipeline execution result dict.
    """
    global_options = global_options or {}
    steps = pipeline.get("steps", [])
    context: dict[str, dict] = {}  # step_id -> output_mapping values
    step_results: list[dict] = []
    total_start = time.perf_counter()

    for step in steps:
        step_id = step["step_id"]
        capability = step["capability"]

        # Evaluate condition
        condition = step.get("condition", "")
        if condition:
            try:
                cond_result = _eval_expression(condition, context)
            except Exception as exc:
                step_results.append({
                    "step_id": step_id,
                    "capability": capability,
                    "status": "error",
                    "time_ms": 0,
                    "error": f"Condition evaluation error: {exc}",
                })
                if step.get("on_failure", "abort") == "abort":
                    break
                context[step_id] = {}
                continue

            if not cond_result:
                step_results.append({
                    "step_id": step_id,
                    "capability": capability,
                    "status": "skipped",
                    "time_ms": 0,
                    "reason": "condition not met",
                })
                context[step_id] = {}
                continue

        # License check
        try:
            check_license_fn(capability)
        except Exception as exc:
            step_results.append({
                "step_id": step_id,
                "capability": capability,
                "status": "error",
                "time_ms": 0,
                "error": str(exc),
            })
            if step.get("on_failure", "abort") == "abort":
                break
            context[step_id] = {}
            continue

        # Merge step options with global overrides
        opts = dict(step.get("options", {}))
        if step_id in global_options:
            opts.update(global_options[step_id])

        # Execute inference
        t0 = time.perf_counter()
        try:
            result = infer_fn(capability, image_bytes, opts)
            elapsed = round((time.perf_counter() - t0) * 1000, 2)

            step_results.append({
                "step_id": step_id,
                "capability": capability,
                "status": "success",
                "time_ms": elapsed,
                "result": result,
            })

            # Extract output_mapping values
            output_mapping = step.get("output_mapping", {})
            mapped = {}
            for key, path_expr in output_mapping.items():
                if path_expr.startswith("$."):
                    mapped[key] = _extract_jsonpath(result, path_expr)
                else:
                    mapped[key] = _parse_value(path_expr)
            context[step_id] = mapped

        except Exception as exc:
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            step_results.append({
                "step_id": step_id,
                "capability": capability,
                "status": "error",
                "time_ms": elapsed,
                "error": str(exc),
            })
            context[step_id] = {}
            on_failure = step.get("on_failure", "abort")
            if on_failure == "abort":
                break

    total_elapsed = round((time.perf_counter() - total_start) * 1000, 2)

    # Compute final output
    final_output = {}
    final_output_def = pipeline.get("final_output", {})
    for key, expr in final_output_def.items():
        try:
            final_output[key] = _eval_expression(expr, context)
        except Exception:
            final_output[key] = None

    return {
        "code": 0,
        "message": "success",
        "pipeline_id": pipeline.get("pipeline_id"),
        "pipeline_version": pipeline.get("version", "1.0.0"),
        "total_time_ms": total_elapsed,
        "steps": step_results,
        "final_result": final_output,
    }
