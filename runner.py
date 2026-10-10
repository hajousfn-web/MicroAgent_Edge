"""Run MicroAgent-Edge against the offline Gemma developer-agent benchmark.

Configure an offline ``module:function`` backend accepting the structured prompt
built by agent.prompts and returning a JSON advisory. No network access or package
installation is performed by this runner.
"""
from __future__ import annotations

import argparse
import difflib
import importlib
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterable

from agent.code_graph import build_code_graph
from agent.reasoning_engine import GemmaAdvisoryAgent
from core.kernel import ExecutionKernel
from core.sandbox import Sandbox
from core.validator import PythonProposalValidator

LOGGER = logging.getLogger("microagent_edge.runner")
DEFAULT_DATA_DIR = Path("/kaggle/input/competitions/gemma-4-developer-agent")
DEFAULT_OUTPUT = Path("/kaggle/working/submission.parquet")
SOURCE_KEYS = ("source", "source_code", "code", "code_snippet", "file_content", "content")
DIAGNOSTIC_KEYS = ("problem_statement", "description", "error_log", "diagnostics", "issue")
PATH_KEYS = ("file_path", "filename", "path", "target_file")
GRAPH_KEYS = ("graph_path", "graph_file", "ast_graph", "graph")


def load_tasks(path: Path) -> list[dict[str, Any]]:
    """Load JSONL task objects, preserving input order."""
    tasks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                task = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(task, dict):
                raise ValueError(f"Expected a JSON object at {path}:{line_number}")
            tasks.append(task)
    return tasks


def _find_string(value: Any, keys: Iterable[str]) -> str | None:
    wanted = {key.casefold() for key in keys}
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in wanted and isinstance(child, str) and child.strip():
                return child
        for child in value.values():
            found = _find_string(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_string(child, keys)
            if found:
                return found
    return None


def _file_source(task: dict[str, Any]) -> tuple[str, str] | None:
    files = task.get("files") or task.get("repo_files")
    if isinstance(files, dict):
        choices = [(str(name), text) for name, text in files.items() if isinstance(text, str)]
    elif isinstance(files, list):
        choices = [(str(item.get("path", "solution.py")), item.get("content", ""))
                   for item in files if isinstance(item, dict) and isinstance(item.get("content"), str)]
    else:
        choices = []
    python_files = [item for item in choices if item[0].endswith(".py")]
    if python_files:
        return python_files[0]
    return choices[0] if choices else None


def _find_source(task: dict[str, Any], graph_text: str | None) -> tuple[str, str]:
    source = _find_string(task, SOURCE_KEYS)
    if source:
        return source, _find_string(task, PATH_KEYS) or "solution.py"
    file_entry = _file_source(task)
    if file_entry and file_entry[1].strip():
        return file_entry[1], _find_string(task, PATH_KEYS) or file_entry[0]
    if graph_text:
        try:
            graph_record = json.loads(graph_text)
        except json.JSONDecodeError:
            graph_record = None
        if graph_record is not None:
            source = _find_string(graph_record, SOURCE_KEYS)
            if source:
                return source, _find_string(graph_record, PATH_KEYS) or "solution.py"
    raise ValueError("No source text found in task, repository files, or graph record")


def _task_id(task: dict[str, Any], index: int) -> str:
    for key in ("instance_id", "id", "task_id"):
        value = task.get(key)
        if value is not None and str(value).strip():
            return str(value)
    raise ValueError(f"Task at index {index} has no instance_id/id/task_id")


def _safe_relative_path(raw: str) -> str:
    normalized = raw.replace("\\", "/").lstrip("/")
    parts = [part for part in normalized.split("/") if part not in ("", ".", "..")]
    return "/".join(parts) or "solution.py"


def _graph_index(graph_root: Path) -> dict[str, Path]:
    if not graph_root.is_dir():
        LOGGER.warning("AST graph directory is missing: %s", graph_root)
        return {}
    return {item.stem.casefold(): item for item in sorted(graph_root.rglob("*")) if item.is_file()}


def _load_graph_file(task: dict[str, Any], task_id: str, graph_root: Path,
                     index: dict[str, Path]) -> str | None:
    explicit = _find_string(task, GRAPH_KEYS)
    if explicit:
        candidate = (graph_root / explicit).resolve()
        if candidate.is_relative_to(graph_root.resolve()) and candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        LOGGER.warning("Task %s references missing/unsafe graph path %r", task_id, explicit)
    candidate = index.get(Path(task_id).stem.casefold())
    if candidate:
        return candidate.read_text(encoding="utf-8")
    for suffix in (".json", ".jsonl", ".py", ".txt", ".graph"):
        candidate = graph_root / f"{task_id}{suffix}"
        if candidate.is_file() and candidate.resolve().is_relative_to(graph_root.resolve()):
            return candidate.read_text(encoding="utf-8")
    LOGGER.warning("No matching AST graph file found for task %s", task_id)
    return None


def _graph_context(source: str, graph_file: str | None) -> str:
    """Build a compact AST call-graph context without executing source."""
    try:
        graph = build_code_graph(source)
    except SyntaxError as exc:
        LOGGER.warning("Source is not parseable as Python; using dataset graph: %s", exc)
        return graph_file or "{}"
    context: dict[str, Any] = {"python_ast": asdict(graph)}
    if graph_file:
        try:
            context["dataset_graph"] = json.loads(graph_file)
        except json.JSONDecodeError:
            context["dataset_graph"] = graph_file
    return json.dumps(context, ensure_ascii=False, sort_keys=True)


def _diagnostics(task: dict[str, Any]) -> str:
    lines = [f"{key}: {task[key]}" for key in DIAGNOSTIC_KEYS
             if isinstance(task.get(key), str) and task[key].strip()]
    if not lines:
        lines.append("Benchmark task: " + json.dumps(task, ensure_ascii=False, sort_keys=True))
    lines.append("Return proposed_patch as complete replacement source, or exactly NO_PATCH. Never return a diff.")
    return "\n".join(lines)


def _unified_patch(original: str, replacement: str, file_path: str) -> str:
    """Convert validated replacement source into a git-compatible patch."""
    old_lines = original.splitlines(keepends=True)
    new_lines = replacement.splitlines(keepends=True)
    if old_lines == new_lines:
        return "NO_PATCH"
    body = "".join(difflib.unified_diff(old_lines, new_lines,
                                        fromfile=f"a/{file_path}", tofile=f"b/{file_path}"))
    return f"diff --git a/{file_path} b/{file_path}\n{body}" if body else "NO_PATCH"


def _load_inference(specification: str) -> Callable[[str], str]:
    """Load an offline backend callable using ``local_module:function`` syntax."""
    if ":" not in specification:
        raise ValueError("Inference backend must use module:function syntax")
    module_name, function_name = specification.split(":", 1)
    backend = getattr(importlib.import_module(module_name), function_name, None)
    if not callable(backend):
        raise ValueError(f"Inference backend {specification!r} is not callable")
    return backend


def _write_parquet(rows: list[dict[str, str]], destination: Path) -> None:
    """Write exact submission columns with Kaggle's preinstalled local PyArrow."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Writing Parquet requires PyArrow preinstalled in the Kaggle image; no download is attempted") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pydict(
        {"id": [row["id"] for row in rows], "prediction": [row["prediction"] for row in rows]},
        schema=pa.schema([("id", pa.string()), ("prediction", pa.string())]),
    )
    pq.write_table(table, destination)


def run(data_dir: Path, output_path: Path, inference: Callable[[str], str],
        timeout_seconds: float, max_tasks: int | None = None) -> list[dict[str, str]]:
    """Evaluate tasks locally and write their predictions to Parquet."""
    tasks_path = data_dir / "tasks.jsonl"
    if not tasks_path.is_file():
        raise FileNotFoundError(f"Benchmark tasks file not found: {tasks_path}")
    tasks = load_tasks(tasks_path)
    if max_tasks is not None:
        tasks = tasks[:max_tasks]
    graph_root = data_dir / "graphs"
    graph_files = _graph_index(graph_root)
    predictions: list[dict[str, str]] = []
    for index, task in enumerate(tasks):
        task_id = _task_id(task, index)
        prediction = "NO_PATCH"
        try:
            graph_file = _load_graph_file(task, task_id, graph_root, graph_files)
            source, raw_path = _find_source(task, graph_file)
            graph_context = _graph_context(source, graph_file)
            candidate_box: dict[str, str] = {}
            def capture_candidate(prompt: str) -> str:
                response = inference(prompt)
                try:
                    record = json.loads(response)
                except (TypeError, json.JSONDecodeError):
                    return response
                if isinstance(record, dict) and isinstance(record.get("proposed_patch"), str):
                    candidate_box["source"] = record["proposed_patch"]
                return response
            advisor = GemmaAdvisoryAgent(inference_fn=capture_candidate)
            kernel = ExecutionKernel([PythonProposalValidator()], Sandbox(timeout_seconds=timeout_seconds))
            result = kernel.process_with_advisor(advisor, source, _diagnostics(task), graph_context)
            if result.status == "SUCCESS":
                candidate = candidate_box.get("source", "")
                if candidate.strip() and candidate.strip() != "NO_PATCH":
                    prediction = _unified_patch(source, candidate, _safe_relative_path(raw_path))
            else:
                LOGGER.info("Task %s produced no patch: %s", task_id, result.reason or result.status)
        except Exception:
            LOGGER.exception("Task %s failed; emitting NO_PATCH", task_id)
        predictions.append({"id": task_id, "prediction": prediction})
        LOGGER.info("Completed %d/%d tasks (%s)", index + 1, len(tasks), task_id)
    _write_parquet(predictions, output_path)
    LOGGER.info("Wrote %d predictions to %s", len(predictions), output_path)
    return predictions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--inference", default=os.environ.get("MICROAGENT_INFERENCE"),
                        help="Local module:function backend (or set MICROAGENT_INFERENCE)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="Per-proposal subprocess timeout in seconds")
    parser.add_argument("--max-tasks", type=int, default=None,
                        help="Optional task limit for local smoke runs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.max_tasks is not None and args.max_tasks < 0:
        parser.error("--max-tasks cannot be negative")
    if not args.inference:
        parser.error("Set --inference module:function to a local Gemma backend; no model is downloaded or simulated")
    try:
        run(args.data_dir, args.output, _load_inference(args.inference), args.timeout, args.max_tasks)
    except Exception as exc:
        LOGGER.error("Evaluation failed: %s", exc)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
