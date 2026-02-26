#!/usr/bin/env python3
"""
Smoke test workflow launcher for aviation backend.

Starts UI-equivalent runs, captures SSE events and pod logs, and loops until all
configured scenarios pass for consecutive rounds or until max rounds are exhausted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TERMINAL_EVENTS = {"run_completed", "run_failed"}


@dataclass
class CaseResult:
    name: str
    attempt: int
    run_id: Optional[str]
    success: bool
    terminal_event: Optional[str]
    terminal_error: Optional[str]
    terminal_error_context: Optional[Dict[str, Any]]
    elapsed_seconds: float
    events: List[Dict[str, Any]]
    backend_log_lines: List[str]
    backend_stderr_like_lines: List[str]
    trace_context: Dict[str, Optional[str]]


DEFAULT_CASES = [
    {
        "name": "ui-handoff-llm-directed",
        "workflow_type": "handoff",
        "orchestration_mode": "llm_directed",
        "problem": (
            "Severe thunderstorm at Chicago O'Hare (ORD) has caused a ground stop. "
            "47 flights are delayed or cancelled, affecting approximately 6,800 passengers. "
            "12 aircraft are grounded, 3 runways closed. Develop a recovery plan to minimize "
            "total delay and passenger impact while maintaining crew legality and safety compliance."
        ),
    },
    {
        "name": "ui-handoff-deterministic",
        "workflow_type": "handoff",
        "orchestration_mode": "deterministic",
        "problem": (
            "Flight AA1847 (B737-800, N735AA) is en route from JFK to ORD and is "
            "severely delayed by weather at destination. Fuel remaining is 90 minutes and "
            "the destination visibility is below minimums with thunderstorms. Recommend the "
            "best diversion and recovery alternative."
        ),
    },
    {
        "name": "ui-sequential",
        "workflow_type": "sequential",
        "problem": (
            "Aviation incident simulation: Gate gate-handoff at JFK for mixed baggage and "
            "maintenance exceptions. Create a safe, practical recovery recommendation with "
            "passenger communication and resource balancing."
        ),
    },
]

LOG_MATCHERS = ("error", "failed", "failure", "exception", "traceback", "tenant", "403", "401", "400")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run workflow smoke tests against backend API")
    parser.add_argument("--backend-url", default="http://localhost:5001", help="Backend base URL")
    parser.add_argument("--namespace", default="aviation-multi-agent", help="Kubernetes namespace")
    parser.add_argument("--pod-selector", default="app=aviation-multi-agent-backend", help="Pod label selector")
    parser.add_argument("--rounds", type=int, default=3, help="Max verification rounds")
    parser.add_argument("--consecutive-success", type=int, default=3, help="Consecutive successful rounds required")
    parser.add_argument("--run-timeout", type=int, default=600, help="Per-run timeout for /events (seconds)")
    parser.add_argument("--backend-log-window", default="20m", help="kubectl --since window for backend logs")
    parser.add_argument("--output-dir", default="artifacts/workflow-smoke", help="Directory to write run artifacts")
    parser.add_argument("--round-delay", type=int, default=8, help="Delay between rounds when failures occur")
    parser.add_argument("--case", action="append", dest="cases", default=None,
                        help="Override case list JSON object(s)")
    return parser.parse_args()


def _http_request(method: str, url: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 60) -> tuple[int, str]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, str(exc.reason) if hasattr(exc, "reason") else str(exc)


def _parse_event_stream(url: str, timeout_seconds: int, terminal_events: Iterable[str]) -> tuple[Optional[str], List[Dict[str, Any]]]:
    terminal_set = set(terminal_events)
    events: List[Dict[str, Any]] = []
    terminal_event: Optional[str] = None
    current_event = "message"
    deadline = time.time() + timeout_seconds

    req = urllib.request.Request(f"{url}?since=0", headers={"Accept": "text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=max(5, timeout_seconds // 2)) as resp:
            while time.time() < deadline:
                raw_line = resp.readline()
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_event = line[6:].strip() or "message"
                    continue
                if line.startswith("data:"):
                    data_text = line[5:].strip()
                    if not data_text:
                        continue
                    payload: Dict[str, Any]
                    try:
                        payload = json.loads(data_text)
                    except json.JSONDecodeError:
                        payload = {"raw": data_text}
                    event = {"kind": current_event, "payload": payload}
                    events.append(event)
                    if current_event in terminal_set:
                        terminal_event = current_event
                        return terminal_event, events
    except urllib.error.URLError as exc:
        return None, [{"kind": "stream_error", "payload": {"error": str(exc)}}]

    return terminal_event, events


def _extract_error(terminal_kind: Optional[str], payload: Dict[str, Any]) -> Optional[str]:
    if terminal_kind != "run_failed":
        return None

    def _first_message(source: Dict[str, Any]) -> Optional[str]:
        for key in ("error", "summary", "resultSummary", "reason"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    direct = _first_message(payload)
    if direct:
        return direct

    nested = payload.get("payload")
    if isinstance(nested, dict):
        nested_value = _first_message(nested)
        if nested_value:
            return nested_value
        nested_error = nested.get("error")
        if isinstance(nested_error, str) and nested_error.strip():
            return nested_error.strip()

    message = payload.get("message")
    if isinstance(message, str) and message.strip() and message != "workflow.failed":
        return message.strip()

    return None


def _get_pod_names(namespace: str, selector: str) -> List[str]:
    try:
        completed = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "-l", selector, "-o", "jsonpath={.items[*].metadata.name}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    output = (completed.stdout or "").strip()
    if not output:
        return []
    return output.split()


def _collect_backend_logs(namespace: str, selector: str, run_id: str, since: str) -> List[str]:
    pod_names = _get_pod_names(namespace, selector)
    if not pod_names:
        return []

    relevant_lines: List[str] = []
    for pod in pod_names:
        try:
            logs = subprocess.run(
                ["kubectl", "logs", pod, "-n", namespace, f"--since={since}", "--timestamps"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            continue

        for line in logs.stdout.splitlines():
            if run_id and run_id in line:
                relevant_lines.append(f"{pod}: {line}")

    return relevant_lines


def _write_run_artifact(path: Path, result: CaseResult) -> None:
    payload = {
        "name": result.name,
        "attempt": result.attempt,
        "run_id": result.run_id,
        "success": result.success,
        "terminal_event": result.terminal_event,
        "terminal_error": result.terminal_error,
        "terminal_error_context": result.terminal_error_context,
        "elapsed_seconds": result.elapsed_seconds,
        "event_count": len(result.events),
        "events": result.events,
        "backend_log_lines": result.backend_log_lines,
        "backend_stderr_like_lines": result.backend_stderr_like_lines,
        "trace_context": result.trace_context,
    }
    path.write_text(json.dumps(payload, indent=2))


def _start_run(backend_url: str, case: Dict[str, str]) -> tuple[Optional[str], Optional[str]]:
    payload: Dict[str, Any] = {
        "problem": case["problem"],
        "workflow_type": case["workflow_type"],
    }
    if case.get("orchestration_mode"):
        payload["orchestration_mode"] = case["orchestration_mode"]

    status, body = _http_request("POST", f"{backend_url}/api/av/solve", payload=payload)
    if status not in {200, 201}:
        return None, f"solve_failed_http_status_{status}_{body[:200]}"

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, f"solve_response_json_error:{exc}"

    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return None, "solve_response_missing_run_id"
    return run_id, None


def _discover_workflow_cases(backend_url: str) -> Optional[List[Dict[str, str]]]:
    status, body = _http_request("GET", f"{backend_url}/api/av/workflows")
    if status != 200:
        return None

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None

    workflows = data.get("workflows") or data.get("cases")
    if not isinstance(workflows, list):
        return None

    cases: List[Dict[str, str]] = []
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        case = {
            "name": str(workflow.get("id") or workflow.get("name", "")).strip(),
            "workflow_type": str(workflow.get("workflow_type") or "").strip(),
            "problem": str(workflow.get("problem") or workflow.get("prompt") or "").strip(),
        }
        if not case["name"] or not case["workflow_type"] or not case["problem"]:
            continue
        orchestration_mode = workflow.get("orchestration_mode")
        if isinstance(orchestration_mode, str) and orchestration_mode.strip():
            case["orchestration_mode"] = orchestration_mode.strip()
        cases.append(case)

    return cases or None


def _pick_stderr_like_lines(lines: List[str], limit: int = 10) -> List[str]:
    lowered = [line.lower() for line in lines]
    matched: List[str] = []
    for index, line in enumerate(lines):
        if any(token in lowered[index] for token in LOG_MATCHERS):
            matched.append(line)
            if len(matched) >= limit:
                return matched

    if matched:
        return matched[:limit]
    return lines[:limit]


def _extract_trace_context(events: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    if not events:
        return {"trace_id": None, "span_id": None, "parent_span_id": None}

    for event in reversed(events):
        for field in ("payload", "meta", "trace"):
            value = event.get(field)
            if not isinstance(value, dict):
                continue

            trace_id = value.get("trace_id") or value.get("traceId")
            span_id = value.get("span_id") or value.get("spanId")
            parent_span_id = value.get("parent_span_id") or value.get("parentSpanId")

            if trace_id or span_id or parent_span_id:
                return {
                    "trace_id": str(trace_id) if trace_id else None,
                    "span_id": str(span_id) if span_id else None,
                    "parent_span_id": str(parent_span_id) if parent_span_id else None,
                }

    return {"trace_id": None, "span_id": None, "parent_span_id": None}


def _run_single_case(backend_url: str, namespace: str, selector: str, case: Dict[str, str], attempt: int, timeout: int,
                     log_window: str, output_dir: Path) -> CaseResult:
    start = time.monotonic()

    run_id, start_error = _start_run(backend_url, case)
    if not run_id:
        result = CaseResult(
            name=case["name"],
            attempt=attempt,
            run_id=None,
            success=False,
            terminal_event="start_failed",
            terminal_error=start_error or "unknown_start_error",
            terminal_error_context={"http_status": start_error},
            elapsed_seconds=round(time.monotonic() - start, 2),
            events=[],
            backend_log_lines=[],
            backend_stderr_like_lines=[],
            trace_context={"trace_id": None, "span_id": None, "parent_span_id": None},
        )
        _write_run_artifact(output_dir / f"{case['name']}_attempt_{attempt}.json", result)
        return result

    logs_start_time = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future_logs = executor.submit(_collect_backend_logs, namespace, selector, run_id, log_window)
        terminal_event, events = _parse_event_stream(
            f"{backend_url}/api/av/runs/{run_id}/events",
            timeout,
            TERMINAL_EVENTS,
        )
        backend_log_lines = future_logs.result(timeout=max(1, timeout / 2))

    elapsed = round(time.monotonic() - start, 2)
    payload = events[-1].get("payload", {}) if events else {}
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    terminal_error = _extract_error(terminal_event, payload)
    terminal_error_context: Dict[str, Any] = payload if terminal_event == "run_failed" and isinstance(payload, dict) else {}
    success = terminal_event == "run_completed"

    # Keep trace continuity in artifacts for quick triage.
    trace_context = _extract_trace_context(events)
    result = CaseResult(
        name=case["name"],
        attempt=attempt,
        run_id=run_id,
        success=success,
        terminal_event=terminal_event,
        terminal_error=terminal_error,
        terminal_error_context=terminal_error_context,
        elapsed_seconds=elapsed,
        events=events,
        backend_log_lines=backend_log_lines[-200:],
        backend_stderr_like_lines=_pick_stderr_like_lines(backend_log_lines[-200:]),
        trace_context=trace_context,
    )
    _write_run_artifact(output_dir / f"{case['name']}_attempt_{attempt}.json", result)
    return result


def _load_cases(args: argparse.Namespace) -> List[Dict[str, str]]:
    if not args.cases:
        discovered = _discover_workflow_cases(args.backend_url)
        if discovered:
            return discovered
        return DEFAULT_CASES

    cases = []
    for case_json in args.cases:
        case = json.loads(case_json)
        if not isinstance(case, dict) or "name" not in case:
            raise ValueError(f"Invalid case payload: {case_json}")
        cases.append(case)
    return cases


def main() -> int:
    args = parse_args()
    cases = _load_cases(args)
    output_dir = Path(args.output_dir) / time.strftime("run_%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.backend_url:
        print("backend-url is required", file=sys.stderr)
        return 2

    backend_url = args.backend_url.rstrip("/")
    rounds = max(1, args.rounds)
    required_streak = max(1, args.consecutive_success)

    streak: Dict[str, int] = {case["name"]: 0 for case in cases}
    attempts = 0

    print(f"[smoke] writing artifacts to {output_dir}")
    print(f"[smoke] cases: {[case['name'] for case in cases]}")

    while attempts < rounds:
        attempts += 1
        print(f"\n[smoke] round {attempts}/{rounds}")
        round_failed = 0

        for case in cases:
            result = _run_single_case(
                backend_url=backend_url,
                namespace=args.namespace,
                selector=args.pod_selector,
                case=case,
                attempt=attempts,
                timeout=args.run_timeout,
                log_window=args.backend_log_window,
                output_dir=output_dir,
            )

            status_icon = "[OK]" if result.success else "[FAIL]"
            last_error = f" error={result.terminal_error}" if result.terminal_error else ""
            print(
                f"  {status_icon} {case['name']} attempt={attempts} "
                f"run_id={result.run_id or 'n/a'} terminal={result.terminal_event} "
                f"events={len(result.events)} elapsed={result.elapsed_seconds}s{last_error}"
            )

            if result.success:
                streak[case["name"]] += 1
            else:
                streak[case["name"]] = 0
                round_failed += 1

        if round_failed == 0 and all(value >= required_streak for value in streak.values()):
            print(f"\n[smoke] all workflows passed {required_streak}x consecutively")
            return 0

        if attempts < rounds:
            if all(value >= required_streak for value in streak.values()):
                print("[smoke] no failures this round; continuing for stability checks")
            else:
                print(f"\n[smoke] failures observed; retrying after {args.round_delay}s delay")
            time.sleep(args.round_delay)

    final_report = {"cases": []}
    for case_name, count in streak.items():
        final_report["cases"].append({"name": case_name, "consecutive_success": count})
    summary_file = output_dir / "summary.json"
    summary_file.write_text(json.dumps(final_report, indent=2))

    print(f"[smoke] completed with failures, review {summary_file}")
    for item in final_report["cases"]:
        if item["consecutive_success"] < required_streak:
            print(f"[smoke][FAIL] {item['name']} only {item['consecutive_success']} consecutive successes")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
