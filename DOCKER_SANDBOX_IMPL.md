# Docker Sandbox Implementation Plan

## What Changes

This document covers only the new work needed on top of the existing codebase.
Nothing in `src/core/llm_client.py`, `event_bus.py`, `hook_registry.py`,
`agent_registry.py`, `memory_system.py`, or `session_manager.py` changes.

---

## 1. Current State vs. Target State

| Area | Current | Target |
|---|---|---|
| `SandboxRunner` | subprocess + temp file | Docker container per execution |
| File ops | None | Create / read / delete files inside container |
| Large task handling | Single pipeline, 3 debug retries | RALPH-driven subtask decomposition → subagent loop |
| Feedback | Error passed to `DebuggerAgent` once per attempt | Full iteration context (code + stdout + stderr + eval score) passed forward |
| Subagent mode | `OrchestratorAgent` calls workers directly | Each subtask runs its own mini RALPH → Code → Execute → Evaluate cycle |

---

## 2. New / Modified Files

```
src/
  core/
    sandbox_runner.py       ← REPLACE entirely (Docker backend)
    task_decomposer.py      ← NEW: breaks big tasks into subtasks
  agents/
    orchestrator_agent.py   ← MODIFY: add decompose + subagent loop
    executor_agent.py       ← MODIFY: pass file_ops context
```

---

## 3. `SandboxRunner` — Docker Backend

### 3.1 Design

- One **persistent named container** per session (`ollama_sandbox_<session_id>`).
- Container image: `python:3.12-slim` (no network, no privileged).
- Files are written into the container via `docker cp`, executed, then optionally deleted.
- Timeout enforced via `docker exec --timeout` equivalent (`subprocess.run(timeout=…)`).

### 3.2 Interface (unchanged — drop-in replacement)

```python
class SandboxRunner:
    def __init__(self, timeout: int = 30, session_id: str = "default"): ...

    # Core execution — same signature as before
    def execute(self, code: str, language: str = "python") -> tuple[str, str, int]:
        """Returns (stdout, stderr, returncode)."""

    # NEW — file operations inside the container
    def write_file(self, path: str, content: str) -> tuple[str, str, int]:
        """Write content to <path> inside the container."""

    def read_file(self, path: str) -> tuple[str, str, int]:
        """Read and return content of <path> from the container."""

    def delete_file(self, path: str) -> tuple[str, str, int]:
        """Remove <path> from the container."""

    def list_files(self, directory: str = "/workspace") -> tuple[str, str, int]:
        """List files in a directory inside the container."""

    # Lifecycle
    def start(self) -> None:
        """Pull image if needed and start the container."""

    def stop(self) -> None:
        """Stop and remove the container."""
```

### 3.3 Implementation Notes

```
start():
  docker run -d --rm
    --name ollama_sandbox_<session_id>
    --network none
    --memory 256m
    --cpus 0.5
    -w /workspace
    python:3.12-slim
    sleep infinity          ← keep alive

execute():
  1. docker cp <tempfile> container:/workspace/run.py
  2. docker exec container python /workspace/run.py
     (captured via subprocess, timeout applied)
  3. docker exec container rm /workspace/run.py

write_file(path, content):
  1. Write content to host tempfile
  2. docker cp <tempfile> container:<path>

read_file(path):
  docker exec container cat <path>

delete_file(path):
  docker exec container rm -f <path>

list_files(directory):
  docker exec container ls -la <directory>

stop():
  docker stop ollama_sandbox_<session_id>
```

### 3.4 Error Handling

- If Docker daemon is not running → raise `RuntimeError` with clear message on `start()`.
- If container exits mid-session → `execute()` calls `start()` automatically (self-heal).
- All `docker` calls go through a private `_docker_exec(args, input_data)` helper that
  returns `(stdout, stderr, returncode)` so every public method has a uniform interface.

---

## 4. `TaskDecomposer` — New Core Module

**File:** `src/core/task_decomposer.py`

### 4.1 Purpose

For large tasks the LLM is asked to produce a numbered subtask list.
Each subtask is self-contained and can be executed independently.

### 4.2 Threshold

A task is "large" when either:
- The user's description exceeds **300 characters**, **OR**
- The RALPH `ANALYZE` phase contains the word `step` or lists more than 3 lines.

### 4.3 Interface

```python
class TaskDecomposer:
    def __init__(self, llm_client): ...

    def should_decompose(self, task: str, ralph_trace: dict) -> bool:
        """Return True when the task needs breakdown."""

    def decompose(self, task: str, ralph_trace: dict) -> list[dict]:
        """
        Returns a list of subtask dicts:
          {
            "id": 1,
            "description": "...",
            "depends_on": [],   # list of subtask ids this one needs output from
            "context_keys": []  # keys from previous outputs to inject
          }
        """
```

### 4.4 LLM Prompt (inside `decompose`)

```
You are a task planner. Break the following task into ordered, self-contained subtasks.

Task: {task}

RALPH Analysis: {ralph_trace['ANALYZE']}

Respond ONLY as a numbered list (no prose):
1. <subtask description>
2. <subtask description>
...

Each subtask must be executable independently or after the preceding ones.
Maximum 8 subtasks.
```

---

## 5. `OrchestratorAgent` — Modified

**File:** `src/agents/orchestrator_agent.py`

### 5.1 New Constructor Arg

```python
def __init__(
    self,
    coder, executor, evaluator, debugger,
    task_decomposer,   # ← NEW
    *args, **kwargs
): ...
```

### 5.2 New `execute()` Flow

```
execute(task):
  1. Run RALPH on full task
  2. if task_decomposer.should_decompose(task, ralph_trace):
       subtasks = task_decomposer.decompose(task, ralph_trace)
       return _run_subtask_loop(subtasks, task)
     else:
       return _run_single_pipeline(task, context={})

_run_subtask_loop(subtasks, original_task):
  accumulated_context = {}
  results = []

  for subtask in subtasks:
      feedback = _build_feedback(results)   # from all previous iterations
      ctx = {
          "parent_task": original_task,
          "subtask_id": subtask["id"],
          "feedback": feedback,
          **{k: accumulated_context[k] for k in subtask["context_keys"] if k in accumulated_context}
      }
      result = _run_single_pipeline(subtask["description"], ctx)
      accumulated_context[f"subtask_{subtask['id']}_output"] = result
      results.append(result)

      if not result["execution"]["success"] and result["debug_attempts"] >= MAX_DEBUG_ATTEMPTS:
          # Hard fail: report which subtask failed and accumulated context
          break

  return {"subtasks": results, "accumulated_context": accumulated_context}

_build_feedback(results):
  """Summarise all previous results into a feedback string for the next iteration."""
  lines = []
  for r in results:
      status = "✓" if r["execution"]["success"] else "✗"
      lines.append(f"{status} Subtask {r['subtask_id']}: {r.get('stdout','')[:200]}")
      if not r["execution"]["success"]:
          lines.append(f"  Error: {r['execution']['stderr'][:200]}")
  return "\n".join(lines)
```

### 5.3 `_run_single_pipeline` (renamed from current `execute`)

Same as the current pipeline (Coder → Execute → Debug loop → Evaluate → Memory),
but now accepts a `context` dict that may contain `feedback` from prior subtasks.

The `feedback` key is forwarded to `CoderAgent` so it generates code aware of
what previous subtasks produced or failed with.

---

## 6. `CoderAgent` — Minor Change

Add `feedback` injection into the prompt when present in context:

```python
if context.get("feedback"):
    prompt += f"\n\nFeedback from previous subtasks:\n{context['feedback']}"
if context.get("parent_task"):
    prompt += f"\n\nThis is subtask {context['subtask_id']} of: {context['parent_task']}"
```

---

## 7. `ExecutorAgent` — File-Op Awareness

Add handling for `file_ops` key in context:

```python
# context["file_ops"] = [{"op": "write", "path": "...", "content": "..."}, ...]
file_ops = (context or {}).get("file_ops", [])
for op in file_ops:
    if op["op"] == "write":
        self._sandbox.write_file(op["path"], op["content"])
    elif op["op"] == "delete":
        self._sandbox.delete_file(op["path"])
```

This lets the Coder or Orchestrator pre-stage files before execution.

---

## 8. Feedback Loop — Data Contract

Each iteration result dict carries:

```python
{
  "subtask_id": int,
  "task": str,
  "generated_code": str,
  "execution": {
    "stdout": str,
    "stderr": str,
    "returncode": int,
    "success": bool
  },
  "debug_attempts": [
    {"attempt": int, "explanation": str, "fixed_code": str}
  ],
  "evaluation": {          # only on success
    "score": float,
    "feedback": str
  },
  "final_code": str
}
```

`_build_feedback()` reads `execution.stdout`, `execution.stderr`, and `evaluation.feedback`
from every prior result to construct the context string passed into the next subtask's
Coder prompt.

---

## 9. `main.py` Changes

### 9.1 Bootstrap

```python
from src.core.task_decomposer import TaskDecomposer

sandbox = SandboxRunner(timeout=30, session_id=session.session_id)
sandbox.start()   # ← starts Docker container

decomposer = TaskDecomposer(llm)

orchestrator = OrchestratorAgent(
    coder, executor, evaluator, debugger,
    decomposer,    # ← new arg
    llm, event_bus, hooks, memory, ralph
)
```

### 9.2 Shutdown

```python
# In the finally / atexit block:
sandbox.stop()   # ← stops and removes Docker container
```

---

## 10. Docker Prerequisites Check

Add a startup check in `main.py` before `sandbox.start()`:

```python
import subprocess, sys

def _check_docker():
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=5)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("ERROR: Docker is not running or not installed. "
              "Start Docker Desktop and retry.")
        sys.exit(1)
```

---

## 11. Sequence Diagram — Large Task

```
User
 │
 ▼
OrchestratorAgent.execute(task)
 │
 ├── RalphEngine.run()  →  ralph_trace
 │
 ├── TaskDecomposer.should_decompose()  →  True
 │
 ├── TaskDecomposer.decompose()  →  [subtask1, subtask2, subtask3]
 │
 ├── ITERATION 1: subtask1
 │    ├── CoderAgent.run(subtask1, context={feedback: ""})
 │    ├── ExecutorAgent.run(code)  →  result1
 │    │    └── SandboxRunner.execute()  (Docker)
 │    ├── [DebuggerAgent loop if failed]
 │    └── EvaluatorAgent.run()
 │
 ├── ITERATION 2: subtask2
 │    ├── feedback = _build_feedback([result1])
 │    ├── CoderAgent.run(subtask2, context={feedback: feedback})
 │    ├── ExecutorAgent.run(code)  →  result2
 │    │    └── SandboxRunner.execute()  (Docker)
 │    ├── [DebuggerAgent loop if failed]
 │    └── EvaluatorAgent.run()
 │
 └── ITERATION N: subtaskN  ...same pattern...
      └── return accumulated results
```

---

## 12. What Is NOT Changing

- `OllamaClient` — no changes
- `RalphEngine` — no changes
- `MemorySystem` / `EventBus` / `HookRegistry` / `AgentRegistry` / `SessionManager` — no changes
- `DebuggerAgent` / `EvaluatorAgent` / `ResearchAgent` / `MemoryAgent` — no changes
- `terminal_ui.py` — no changes (result dict schema is backward-compatible)
- `BaseAgent` — no changes
