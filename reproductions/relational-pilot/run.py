"""Build, dry-run and resume the pilot with explicit provider configuration.

No API credentials are read until the run command. Provider mode payloads and
budgets must be supplied rather than guessed or silently downgraded.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from prepare import HERE, ROOT, digest, digest_bytes, read_json, write_new, validate_reviews
from prompts import METHODS, messages

FAMILIES = ("gpt5", "deepseek", "qwen")
MODES = ("low", "high")
UNFINISHED = {"api_error", "empty", "truncated", "execution_failed", "unknown"}


def build_tasks(data_path, output, exploratory=False):
    data = read_json(data_path)
    if exploratory:
        sources = data["drafts"]
        state = "exploratory_unreviewed_not_formal"
    else:
        if data.get("status") != "frozen_reviewed_150" or len(data["sources"]) != 150:
            raise ValueError("Formal tasks require a reviewed and frozen 150-source manifest")
        sources, state = data["sources"], "formal_reviewed"
        if len({s["source_id"] for s in sources}) != 150:
            raise ValueError("Formal sources must be distinct")
        for source in sources:
            validate_reviews(source)
            if not source.get("family_id"):
                raise ValueError("Formal sources require reviewed family IDs")
    tasks = []
    for source in sources:
        if digest(source["visible"]) != source["variant_sha256"]:
            raise ValueError("Variant hash mismatch")
        for family in FAMILIES:
            for mode in MODES:
                for method in METHODS:
                    identity = [source["source_id"], source["variant_sha256"], family, mode, method]
                    tasks.append({"id": digest(identity), "source_id": source["source_id"],
                                  "family_id": source["family_id"],
                                  "variant_sha256": source["variant_sha256"],
                                  "model_family": family, "mode": mode, "method": method,
                                  "comparison": "supplementary" if method == "cot_existing_abstention" else "core",
                                  "messages": messages(method, source["visible"])})
    write_new(output, {"status": state, "data_sha256": digest_bytes(Path(data_path).read_bytes()),
                       "source_count": len(sources), "task_count": len(tasks), "tasks": tasks})


def validate_config(config):
    if config.get("status") != "ready":
        raise ValueError("Fill and validate provider configuration before API use")
    if set(config["providers"]) != set(FAMILIES):
        raise ValueError("Exactly the three planned model families are required")
    for family, p in config["providers"].items():
        for key in ("endpoint_env", "api_key_env", "model", "weights_id", "common_request",
                    "low_request", "high_request", "mode_verification"):
            if not p.get(key):
                raise ValueError(f"Missing provider field {family}.{key}")
        if not p["mode_verification"].get("verified_by") or not p["mode_verification"].get("evidence"):
            raise ValueError("Mode parameters need documented endpoint verification")
        if family == "gpt5" and p["model"] != "gpt-5-2025-08-07":
            raise ValueError("GPT-5 snapshot differs from the experiment plan")
        if p["low_request"] == p["high_request"]:
            raise ValueError("Low/high requests must differ")
        if p["common_request"].get("n", 1) != 1:
            raise ValueError("One output per design cell is required")
        if not any(isinstance(p["common_request"].get(k), int) and p["common_request"][k] > 0
                   for k in ("max_tokens", "max_completion_tokens")):
            raise ValueError("An explicit output-token budget is required")
        if family == "gpt5" and (p["low_request"].get("reasoning_effort") != "minimal"
                                 or p["high_request"].get("reasoning_effort") != "high"):
            raise ValueError("GPT-5 requires minimal versus high reasoning effort")
        for fields in (p["common_request"], p["low_request"], p["high_request"]):
            if any(k in fields for k in ("model", "messages", "api_key", "authorization")):
                raise ValueError("Provider request overrides reserved fields")
        for mode in MODES:
            request = p[f"{mode}_request"]
            if any(k in request for k in ("max_tokens", "max_completion_tokens", "temperature", "top_p", "stop", "n")):
                raise ValueError("Keep decoding budgets/parameters shared across low/high modes")


def execute_pot(code, timeout):
    # Reuse the existing guarded worker. It is a compatibility guard, not a
    # security boundary against adversarial programs. No API keys in its env.
    worker = ROOT / "reproductions/pot/scripts/execute_worker.py"
    try:
        child = subprocess.run([sys.executable, str(worker)], input=json.dumps({"task": "finqa", "code": code}),
                               text=True, capture_output=True, cwd="/tmp", timeout=timeout,
                               env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1",
                                    "OPENBLAS_NUM_THREADS": "1"})
        if child.returncode:
            return {"status": "worker_error", "returncode": child.returncode}
        return json.loads(child.stdout.strip())
    except subprocess.TimeoutExpired:
        return {"status": "worker_timeout"}
    except (ValueError, OSError):
        return {"status": "worker_error"}


def parse_response(raw):
    choices = raw.get("choices", [])
    if len(choices) != 1:
        raise ValueError("Expected one chat-completion choice")
    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content")
    finish = choice.get("finish_reason")
    status = "truncated" if finish == "length" else "completed"
    if not isinstance(content, str) or not content.strip():
        content, status = content or "", "empty"
    if finish not in ("stop", "length"):
        status = "unknown"
    return content, status, finish


def run(tasks_path, config_path, out, limit, timeout):
    bundle, config = read_json(tasks_path), read_json(config_path)
    validate_config(config)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    identity = {"tasks_sha256": digest_bytes(Path(tasks_path).read_bytes()),
                "config_sha256": digest_bytes(Path(config_path).read_bytes()),
                "data_status": bundle["status"],
                "runtime_sha256": {f: digest_bytes((HERE / f).read_bytes())
                                   for f in ("run.py", "prompts.py")},
                "pot_worker_sha256": digest_bytes((ROOT / "reproductions/pot/scripts/execute_worker.py").read_bytes()),
                "pot_protocol_sha256": digest_bytes((ROOT / "reproductions/pot/scripts/protocol.py").read_bytes()),
                "pot_tool_sha256": digest_bytes((ROOT / "reproductions/pot/vendor/tool.py").read_bytes())}
    manifest = out / "run_identity.json"
    if manifest.exists():
        if read_json(manifest) != identity:
            raise ValueError("Resume configuration/source/runtime changed; use a new output directory")
    else:
        write_new(manifest, identity)
    done = set()
    if (out / "outputs.jsonl").exists():
        for line in (out / "outputs.jsonl").read_text().splitlines():
            item = json.loads(line)
            if item["id"] in done:
                raise ValueError("Duplicate output ID")
            done.add(item["id"])
    allowed = {t["id"] for t in bundle["tasks"]}
    if not done <= allowed:
        raise ValueError("Foreign output IDs in resume directory")
    # Fail before paid calls when the reused PoT runtime is missing libraries.
    if any(t["method"] == "pot" and t["id"] not in done for t in bundle["tasks"]):
        check = subprocess.run([sys.executable, "-c", "import func_timeout, sympy, numpy, cvxpy"], capture_output=True)
        if check.returncode:
            raise RuntimeError("Existing PoT worker dependencies unavailable; install in a dedicated runtime before calls")
    # Fail before the first request if any endpoint is missing.
    endpoints = {}
    for family, provider in config["providers"].items():
        endpoint = os.environ.get(provider["endpoint_env"], "")
        key = os.environ.get(provider["api_key_env"], "")
        if not endpoint.startswith("https://") or not key:
            raise ValueError(f"Missing HTTPS endpoint or API key environment variable for {family}")
        endpoints[family] = (endpoint, key)
    remaining = [t for t in bundle["tasks"] if t["id"] not in done]
    for task in remaining[:limit]:
        provider = config["providers"][task["model_family"]]
        request = {"model": provider["model"], "messages": task["messages"],
                   **provider["common_request"], **provider[f'{task["mode"]}_request']}
        record = {k: v for k, v in task.items() if k != "messages"}
        record.update(request=request, weights_id=provider["weights_id"], api_response=None)
        started = time.monotonic()
        endpoint, key = endpoints[task["model_family"]]
        req = urllib.request.Request(endpoint, data=json.dumps(request).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        # The pending file is written before submission: interruptions are never
        # silently retried because a paid response may already have been produced.
        pending = out / (task["id"] + ".pending.json")
        if pending.exists():
            raise RuntimeError("Unresolved interrupted request; reconcile its provider status before resuming")
        write_new(pending, {"id": task["id"], "request_sha256": digest(request)})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = json.loads(response.read())
            record["api_response"] = raw
            content, status, finish = parse_response(raw)
            record.update(content=content, status=status, finish_reason=finish,
                          returned_model=raw.get("model"), usage=raw.get("usage"),
                          reasoning_content=raw.get("choices", [{}])[0].get("message", {}).get("reasoning_content"))
            if task["method"] == "pot" and status == "completed":
                execution = execute_pot(content, 20)
                record["execution"] = execution
                if execution.get("status") != "executed":
                    record["status"] = "execution_failed"
        except urllib.error.HTTPError as e:
            record.update(status="api_error", http_status=e.code, content="")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            # Do not record exception URLs/headers or credential-bearing bodies.
            record.update(status="api_error", error_type=type(e).__name__, content="")
        record["seconds"] = time.monotonic() - started
        with (out / "outputs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        pending.unlink()
        print(json.dumps({"id": task["id"], "status": record["status"]}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--data", required=True)
    b.add_argument("--output", required=True)
    b.add_argument("--exploratory", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--tasks", required=True)
    r.add_argument("--config", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--limit", type=int, required=True)
    r.add_argument("--timeout", type=int, default=180)
    a = p.parse_args()
    if a.command == "build":
        build_tasks(a.data, a.output, a.exploratory)
    else:
        if a.limit <= 0:
            p.error("limit must be positive")
        run(a.tasks, a.config, a.output, a.limit, a.timeout)


if __name__ == "__main__":
    main()
