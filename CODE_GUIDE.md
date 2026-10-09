# Code Implementation Guide — End-to-End Technical Reference

This document explains every module, class, and design decision in the Multi-Agentic Code Builder & Executor system. Read this to understand how all the pieces fit together.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Dependency Graph](#dependency-graph)
3. [Entry Point — main.py](#entry-point--mainpy)
4. [Core Modules](#core-modules)
   - [OllamaClient](#ollamaclient--srccorollm_clientpy)
   - [RalphEngine](#ralphengine--srccoreralph_enginepy)
   - [SandboxRunner](#sandboxrunner--srccore sandbox_runnerpy)
   - [MemorySystem](#memorysystem--srccoremem ory_systempy)
   - [EventBus](#eventbus--srccoreevent_buspy)
   - [HookRegistry](#hookregistry--srccorehook_registrypy)
   - [AgentRegistry](#agentregistry--srccoreagent_registrypy)
   - [SessionManager](#sessionmanager--srccore session_managerpy)
5. [Agents](#agents)
   - [BaseAgent](#baseagent--srcagentsbase_agentpy)
   - [OrchestratorAgent](#orchestratoragent--srcagentsorchestrator_agentpy)
   - [CoderAgent](#coderagent--srcagentscoder_agentpy)
   - [ExecutorAgent](#executoragent--srcagentsexecutor_agentpy)
   - [DebuggerAgent](#debuggeragent--srcagentsdebugger_agentpy)
   - [EvaluatorAgent](#evaluatoragent--srcagentsevaluator_agentpy)
   - [ResearchAgent](#researchagent--srcagentsresearch_agentpy)
   - [MemoryAgent](#memoryagent--srcagentsmemory_agentpy)
6. [UI Layer](#ui-layer--srcuitermin al_uipy)
7. [Data Flow — Full Pipeline Trace](#data-flow--full-pipeline-trace)
8. [Agent Lifecycle State Machine](#agent-lifecycle-state-machine)
9. [Memory Architecture](#memory-architecture)
10. [Hook System](#hook-system)
11. [Session Persistence](#session-persistence)
12. [Error Handling Strategy](#error-handling-strategy)
13. [Key Design Patterns](#key-design-patterns)

---

## Architecture Overview


┌─────────────────────────────────────────────────────────────────────┐
│                         main.py (REPL)                              │
│  argparse → _bootstrap() → interactive loop                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ orchestrates
┌──────────────────────────────▼──────────────────────────────────────┐
│                      OrchestratorAgent                              │
│   Coder → Executor → [Debugger loop] → Evaluator → Memory write     │
└────┬──────────┬──────────┬──────────┬──────────────────────────────┘
     │          │          │          │
  CoderAgent  Executor  Debugger  Evaluator
  Agent       Agent     Agent     Agen
     │
     └─────── All agents inherit BaseAgent ──────────────────────────┐
                                                                      │
     ┌─────────────────── Shared Infrastructure ─────────────────────┤
     │  OllamaClient  RalphEngine  SandboxRunner  MemorySystem        │
     │  EventBus      HookRegistry AgentRegistry  SessionManager      │
     └───────────────────────────────────────────────────────────────┘


The system is divided into three layers:
- **Infrastructure** (`src/core/`) — stateful services wired together at startup
- **Agents** (`src/agents/`) — stateless workers that call infrastructure
- **UI** (`src/ui/`) — pure output formatting, no logic

---

## Dependency Graph


main.py
  ├── OllamaClient           ← HTTP adapter for Ollama API
  ├── RalphEngine            ← uses OllamaClien
  ├── SandboxRunner          ← standalone (subprocess only)
  ├── MemorySystem           ← standalone (file + deque)
  ├── EventBus               ← standalone (threading)
  ├── HookRegistry           ← standalone
  ├── AgentRegistry          ← uses EventBus
  ├── SessionManager         ← standalone (json files)
  │
  ├── BaseAgent              ← uses all of the above
  │   ├── CoderAgen
  │   ├── ExecutorAgent      ← also uses SandboxRunner
  │   ├── DebuggerAgen
  │   ├── EvaluatorAgen
  │   ├── ResearchAgen
  │   ├── MemoryAgen
  │   └── OrchestratorAgent  ← uses the 4 worker agents above
  │
  └── terminal_ui            ← pure output, no dependencies


All dependencies flow inward — no agent imports another agent except `OrchestratorAgent`, which holds explicit references to the 4 worker agents it coordinates.

---

## Entry Point — `main.py

**File:** `main.py

### Bootstrap (`_bootstrap`)


_bootstrap(model, timeout)
    │
    ├── EventBus()
    ├── HookRegistry()
    ├── SessionManager(storage_dir="sessions")
    ├── session = session_manager.create_session()
    │
    ├── OllamaClient(model, timeout)
    ├── MemorySystem(session.session_id, storage_dir="memory")
    ├── SandboxRunner(timeout=30)
    ├── RalphEngine(llm)
    │
    ├── CoderAgent(llm, event_bus, hooks, memory, ralph)
    ├── ExecutorAgent(sandbox, llm, event_bus, hooks, memory, ralph)
    ├── DebuggerAgent(llm, event_bus, hooks, memory, ralph)
    ├── EvaluatorAgent(llm, event_bus, hooks, memory, ralph)
    ├── ResearchAgent(llm, event_bus, hooks, memory, ralph)
    ├── MemoryAgent(llm, event_bus, hooks, memory, ralph)
    ├── OrchestratorAgent(coder, executor, evaluator, debugger,
    │                     llm, event_bus, hooks, memory, ralph)
    │
    ├── AgentRegistry.register(all agents)
    ├── _setup_event_logging(event_bus, session)   ← wires events → session
    └── _setup_default_hooks(hook_registry)        ← logs pre-LLM calls


### Model Auto-Selection

After creating `OllamaClient`, `main.py` checks if the requested model exists locally. If not, it calls `llm.select_best_model()` which:
1. Fetches all local models via `GET /api/tags
2. Filters out any model ending in `:cloud` (requires paid subscription)
3. Returns the first free local model found

### REPL Loop

```python
while True:
    user_input = input("You: ").strip()   # blocks for inpu
    # catches EOFError → break (handles piped stdin / Ctrl+C)
    # empty string → break if piped, continue if interactive
    # /command → run built-in command
    # task text → run_pipeline(user_input)


### `run_pipeline

Calls `orchestrator.run(task)` which returns a `results` dict, then calls terminal_ui functions to render the output.

---

## Core Modules

### `OllamaClient` — `src/core/llm_client.py

**Purpose:** Single HTTP client for all LLM calls.

**Key attributes:**
```python
DEFAULT_MODEL = "glm4:9b"
DEFAULT_BASE_URL = "http://localhost:11434"


**Key methods:**

| Method | HTTP call | Returns |
|--------|-----------|---------|
| `chat(prompt, system, history)` | `POST /api/chat` | `str` response text or `[LLM_ERROR] ...` |
| `is_available()` | `GET /api/tags` | `bool` |
| `list_models()` | `GET /api/tags` | `List[str]` model names |
| `select_best_model()` | calls `list_models()` | `str` best free model name |

**Request format** sent to Ollama:
```json
{
  "model": "qwen2.5:3b",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user",   "content": "..."}
  ],
  "stream": false
}


**Error handling:** All network exceptions are caught and returned as strings prefixed with `[LLM_ERROR]` so callers never need to catch exceptions from `chat()`.

---

### `RalphEngine` — `src/core/ralph_engine.py

**Purpose:** Implements the RALPH (Reflect → Analyze → Learn → Plan → Hypothesize) reasoning loop.

**How it works:**

1. `run(agent_name, task, context)` formats a structured prompt:

   Agent: CoderAgen
   Task: write a fibonacci function
   Context: {...}

   Respond ONLY in this format:
   REFLECT: ...
   ANALYZE: ...
   LEARN: ...
   PLAN: ...
   HYPOTHESIZE: ...


2. Sends the prompt to the LLM via `OllamaClient.chat()

3. `_parse_ralph(response)` scans for each phase marker and extracts the text between consecutive markers, returning:
   ```python
   {
     "REFLECT": "...",
     "ANALYZE": "...",
     "LEARN": "...",
     "PLAN": "...",
     "HYPOTHESIZE": "..."
   }


Every agent calls `self._ralph.run()` inside `BaseAgent.run()` **before** its own `execute()` method runs. The trace is published as an `agent:ralph` event and stored in the session.

---

### `SandboxRunner` — `src/core/sandbox_runner.py

**Purpose:** Run untrusted code safely in a subprocess.

**Why subprocess (not `exec`/`eval`):** The subprocess runs in a completely separate Python process. If the code crashes, loops forever, or raises an unhandled exception, it cannot corrupt the host process state.

**Execution flow:**

execute(code, language="python")
    │
    ├── write code to tempfile (NamedTemporaryFile, suffix=".py")
    ├── subprocess.run([sys.executable, tmp_file],
    │       capture_output=True, text=True, timeout=self.timeout)
    ├── return (stdout, stderr, returncode)
    └── finally: os.unlink(tmp_file)   ← always clean up


**Timeout:** Default 30 seconds. If exceeded, `subprocess.TimeoutExpired` is caught and `returncode=1` with a timeout message in stderr is returned.

**Return tuple:** `(stdout: str, stderr: str, returncode: int)

---

### `MemorySystem` — `src/core/memory_system.py

**Purpose:** Three-tier memory system for agent context.

#### STM (Short-Term Memory)

```python
class STM:
    _buffer: deque(maxlen=20)   # last 20 turns, FIFO eviction


- `.add(role, content)` — append a message
- `.get_recent(n)` — last N entries as dicts
- `.to_messages()` — format for LLM history (`[{role, content}, ...]`)
- `.clear()` — wipe on session end

#### LTM (Long-Term Memory)

```python
class LTM:
    _path = "memory/ltm.json"
    _store = {}   # loaded from file on ini


Storage format per entry:
```json
{
  "ltm:completed_task:a1b2c3d4": {
    "value": {"task": "...", "code": "...", "success": true},
    "topic": "completed_task",
    "importance": 0.7,
    "timestamp": 1234567890.0,
    "access_count": 0
  }
}


Key is `ltm:<topic>:<md5 of value[:8]>` — deterministic so duplicate writes are detected.

- `.write(topic, value, importance)` — serializes to JSON, saves to disk
- `.read(key)` — returns value dict or `None
- `.search(query)` — case-insensitive keyword match against stored values

#### WorkingMemory

Plain `dict`, cleared at end of each task. Used for passing intermediate results between agent steps within a single pipeline run.

#### MemorySystem (Facade)

```python
class MemorySystem:
    stm: STM
    ltm: LTM
    working: WorkingMemory


Instantiated with `(session_id, storage_dir)`. The LTM path is `<storage_dir>/ltm.json`.

---

### `EventBus` — `src/core/event_bus.py

**Purpose:** Decouple agents from each other using pub/sub messaging.

**Thread safety:** All subscribe/unsubscribe/publish operations use `threading.Lock`.

**Event types used:**

| Event | Published by | Data |
|-------|-------------|------|
| `agent:spawn` | AgentRegistry | `{agent_id, type}` |
| `agent:start` | BaseAgent | `{agent_id, task}` |
| `agent:complete` | BaseAgent | `{agent_id, result}` |
| `agent:error` | BaseAgent | `{agent_id, error}` |
| `agent:ralph` | BaseAgent | `{agent_id, trace}` |
| `agent:status` | BaseAgent | `{agent_id, status}` |
| `sandbox:execute` | ExecutorAgent | `{agent_id, language, code_preview}` |
| `sandbox:result` | ExecutorAgent | `{stdout, stderr, returncode, success}` |
| `memory:read` | MemoryAgent | `{agent_id, operation}` |
| `memory:write` | MemoryAgent | `{agent_id, operation}` |

**History:** All published events are appended to `_history`. Queryable via `get_history(event_type)`.

**Session wiring:** In `main.py`, `_setup_event_logging()` subscribes to all events and calls `session.add_event()` — building a full audit trail.

---

### `HookRegistry` — `src/core/hook_registry.py

**Purpose:** Plugin points for intercepting agent lifecycle events.

**7 hook types (HookType enum):**

| Hook | Trigger point |
|------|---------------|
| `PRE_TOOL_CALL` | Before any tool/function call |
| `POST_TOOL_CALL` | After any tool/function call |
| `PRE_LLM_CALL` | Before sending prompt to LLM |
| `POST_LLM_CALL` | After receiving LLM response |
| `ON_ERROR` | When an agent transitions to FAILED |
| `ON_MEMORY_READ` | Before reading from memory |
| `ON_MEMORY_WRITE` | Before writing to memory |

**Usage:**
```python
hook_registry.register(HookType.PRE_LLM_CALL, my_callback)
hook_registry.execute(HookType.PRE_LLM_CALL, agent, prompt)


**Built-in hook:** `main.py` registers a `PRE_LLM_CALL` hook that prints a dim preview of every LLM prompt (first 60 chars) to the terminal. This makes LLM calls visible during debugging.

---

### `AgentRegistry` — `src/core/agent_registry.py

**Purpose:** Central map of all agent instances. Thread-safe.

**Agent status enum (8 states):**

CREATED → INITIALIZED → IDLE → RUNNING → SUCCESS → IDLE
                                        → FAILED  → IDLE
                                        → PAUSED  → IDLE
                              TERMINATED (terminal state)


**Key methods:**
- `register(agent)` — store agent, emit `agent:spawn` even
- `get(agent_id)` — lookup by ID
- `list_agents()` — all agents
- `terminate(agent_id)` — mark as TERMINATED
- `pause(agent_id)` / `resume(agent_id)` — pause/resume RUNNING agents
- `get_summary()` — list of `{agent_id, type, status}` dicts (used by `/agents` command)

---

### `SessionManager` — `src/core/session_manager.py

**Purpose:** Create and persist sessions to JSON files.

**Session fields:**
```python
session.session_id       # 8-char UUID prefix
session.created_at       # float timestamp
session.messages         # [{role, content, timestamp}]
session.tool_calls       # [{agent_id, tool, args, result, timestamp}]
session.code_artifacts   # [{code, language, description, timestamp}]
session.ralph_traces     # [{agent_id, trace, timestamp}]
session.events           # [{type, data, timestamp}]


**Storage:** `sessions/<session_id>.json

**Methods:**
- `create_session()` → new `Session
- `save_session(session_id)` → write JSON file, return `bool
- `load_session(session_id)` → read JSON file, return `Session` or `None

---

## Agents

### `BaseAgent` — `src/agents/base_agent.py

**Purpose:** Abstract base that every agent inherits. Provides lifecycle management, RALPH integration, and event publishing.

**Constructor signature:**
```python
BaseAgent.__init__(
    agent_type: str,
    llm_client,
    event_bus,
    hook_registry,
    memory_system,
    ralph_engine,
)


**Unique ID:** Each agent gets `agent_id = f"{agent_type}_{uuid4()[:6]}"`, e.g. `CoderAgent_a1b2c3`.

**`run()` method (the main entry point for all agents):**

run(task, context)
    │
    ├── _transition(RUNNING)
    ├── publish "agent:start"
    ├── _run_ralph(task, context)      ← RALPH reasoning firs
    │     └── ralph_engine.run()
    │     └── publish "agent:ralph"
    │
    ├── execute(task, context)         ← abstract: implemented per agen
    │
    ├── _transition(SUCCESS)           ← or FAILED on exception
    ├── publish "agent:complete"
    └── return resul


**Abstract method:** `execute(task, context)` must be implemented by every subclass.

---

### `OrchestratorAgent` — `src/agents/orchestrator_agent.py

**Purpose:** Coordinates the full code pipeline.

**Constructor:** Takes 4 worker agents + standard BaseAgent args:
```python
OrchestratorAgent(coder, executor, evaluator, debugger, *args, **kwargs)


**`execute()` — 5-step pipeline:**


Step 1: CoderAgent.run(task)
    → returns Python code string

Step 2: ExecutorAgent.run(task, {code, language})
    → returns {stdout, stderr, returncode, success}

Step 3: Debug loop (max 3 iterations, only if Step 2 failed)
    ├── DebuggerAgent.run(task, {code, error})
    │     → returns {fixed_code, explanation, original_code}
    └── ExecutorAgent.run(task, {fixed_code})
          → returns new execution resul

Step 4: EvaluatorAgent.run(task, {code, execution_result})
    (only if final execution succeeded)
    → returns {raw, scores}

Step 5: Memory write
    ├── STM: "Completed task: <task[:80]>"
    └── LTM: {task, code, success, debug_rounds}  importance=0.7


**`_print_code_preview(code)`** — static helper that prints first 6 lines with `… (N more lines)` suffix.

---

### `CoderAgent` — `src/agents/coder_agent.py

**Purpose:** Generate Python code from a plain-English task.

**System prompt key rules:**
- Respond with code only, in ` ```python ... ``` ` fences
- Write complete, runnable scripts
- Prefer stdlib

**`execute(task, context)`:**
1. Builds prompt. If `context['requirements']` exists, appends additional requirements. If `context['previous_error']` exists, appends error context.
2. Calls `llm.chat(prompt, system=_SYSTEM_PROMPT)
3. `_extract_code()` strips markdown fences — tries ` ```python ` first, then ` ``` `, then returns raw tex
4. Writes to STM: `"Generated code for: <task[:80]>"
5. Returns code string

---

### `ExecutorAgent` — `src/agents/executor_agent.py

**Purpose:** Run code in the sandbox and return structured results.

**Constructor:** Takes `sandbox: SandboxRunner` as first arg (before BaseAgent args):
```python
ExecutorAgent(sandbox, llm, event_bus, hooks, memory, ralph)

The sandbox is stored as `self._sandbox` before calling `super().__init__()`.

**`execute(task, context)`:**
1. Reads `context['code']` (falls back to `task` if missing)
2. Reads `context['language']` (defaults to `"python"`)
3. Publishes `sandbox:execute` even
4. Calls `self._sandbox.execute(code, language)` → `(stdout, stderr, returncode)
5. Publishes `sandbox:result` even
6. Returns `{stdout, stderr, returncode, success: returncode==0}

---

### `DebuggerAgent` — `src/agents/debugger_agent.py

**Purpose:** Diagnose execution errors and return fixed code.

**System prompt rules:**
- Label bug explanation with `BUG:
- Provide fixed code in ` ```python ``` ` fence labeled `FIX:
- Do NOT change functionality — only fix the bug

**`execute(task, context)`:**
1. Reads `context['code']` and `context['error']
2. Builds prompt with original code + error message
3. Calls `llm.chat(prompt, system=_SYSTEM_PROMPT)
4. `_extract_code()` extracts fixed code from fences
5. Returns `{fixed_code, explanation: full_response, original_code}

**OrchestratorAgent** uses `result['fixed_code']` for the next execution attempt.

---

### `EvaluatorAgent` — `src/agents/evaluator_agent.py

**Purpose:** Score code quality on 5 dimensions using LLM.

**System prompt** instructs the LLM to output this exact format:

SCORE_CORRECTNESS: X/10
SCORE_EFFICIENCY: X/10
SCORE_READABILITY: X/10
SCORE_SECURITY: X/10
OVERALL: X/10
SUGGESTIONS:
- ...


**`execute(task, context)`:**
1. Reads `context['code']` and `context['execution_result']
2. Appends execution status/stdout/stderr to the promp
3. Calls `llm.chat(prompt, system=_SYSTEM_PROMPT)
4. `_parse_scores(response)` extracts numeric scores
5. Returns `{raw: full_response, scores: {correctness, efficiency, readability, security, overall, suggestions}}

**`_parse_scores()` — multi-pattern regex:**

For each metric, tries patterns from strictest to most lenient:
1. `SCORE_CORRECTNESS:\s*(\d+)/10` — exact forma
2. `[Cc]orrectness[:\s]+(\d+)\s*/\s*10` — case-insensitive with fraction
3. `[Cc]orrectness[:\s]+(\d+)` — any number after the word

Any extracted number outside 1–10 is rejected. `n/a` is displayed when no pattern matches — this occurs with very small models (< 1B parameters) that don't follow structured output reliably.

---

### `ResearchAgent` — `src/agents/research_agent.py

**Purpose:** Answer research questions using the LLM's training knowledge.

**When used:** Not part of the default pipeline. Can be invoked directly for enriching task context (e.g., "What is the best algorithm for sorting large datasets?").

**`execute(task, context)`:**
1. Reads optional `context['focus']` to narrow the research
2. Calls `llm.chat(prompt, system=_SYSTEM_PROMPT)
3. Writes result to LTM with `importance=0.4
4. Returns `{query, answer}

**Note:** The system has no internet access. Research is based solely on the LLM's training data.

---

### `MemoryAgent` — `src/agents/memory_agent.py

**Purpose:** Unified interface for reading/writing/searching memory programmatically.

**Operations (via `context['operation']`):**

| Operation | Action | Required context keys |
|-----------|--------|-----------------------|
| `read` | LTM key lookup | `key` |
| `write` | LTM write | `topic`, `value`, `importance` |
| `search` | LTM keyword search | `query` |
| `stm_history` | Recent STM turns | `n` |

Default operation if not specified: `search`.

Used internally by the REPL's `/memory <query>` command.

---

## UI Layer — `src/ui/terminal_ui.py

**Purpose:** All terminal output formatting. No business logic.

Uses raw ANSI escape codes (no external library). Colours are applied via `_colored(text, code)` which wraps text with `\033[...m` and `\033[0m` reset.

**Key functions:**

| Function | Output |
|----------|--------|
| `print_header()` | Banner with system name |
| `print_separator(char)` | Horizontal rule |
| `print_section(title)` | `▶ Title` with underline |
| `print_code(code)` | Cyan-coloured code block |
| `print_execution_result(result)` | Green SUCCESS / Red FAILED + stdout/stderr |
| `print_ralph_trace(trace, agent)` | 5-phase RALPH trace, each line dim |
| `print_evaluation(scores)` | Score table with `n/a` fallback |
| `print_agent_dashboard(agents)` | Status table for `/agents` command |
| `print_memory_results(results)` | Search results for `/memory` command |
| `print_help()` | Command reference table |

---

## Data Flow — Full Pipeline Trace

Here is the exact data flow when a user types `"write a fibonacci function"`:


User input: "write a fibonacci function"
│
▼ main.py → run_pipeline("write a fibonacci function")
│
▼ orchestrator.run("write a fibonacci function", context={})
  │
  ├─ BaseAgent.run() is called
  │   ├─ _transition(RUNNING)
  │   ├─ event_bus.publish("agent:start", {task: "write..."})
  │   ├─ ralph_engine.run("OrchestratorAgent", "write...", {})
  │   │     LLM call #1: RALPH trace
  │   │     → {REFLECT: "...", ANALYZE: "...", PLAN: "...", ...}
  │   └─ execute() called:
  │
  ├─ coder.run("write a fibonacci function", {})
  │   ├─ RALPH reasoning (LLM call #2)
  │   ├─ llm.chat(code_prompt, system=coder_system)  ← LLM call #3
  │   └─ returns: "def fibonacci(n): ..."
  │
  ├─ executor.run("write...", {code: "def fibonacci...", language: "python"})
  │   ├─ RALPH reasoning (LLM call #4)
  │   ├─ sandbox.execute("def fibonacci...", "python")
  │   │     write to /tmp/tmpXXX.py
  │   │     subprocess.run([python, /tmp/tmpXXX.py], timeout=30)
  │   │     os.unlink(/tmp/tmpXXX.py)
  │   └─ returns: {stdout: "8\n", stderr: "", returncode: 0, success: True}
  │
  │  [No debug loop needed — success on first try]
  │
  ├─ evaluator.run("write...", {code: "...", execution_result: {...}})
  │   ├─ RALPH reasoning (LLM call #5)
  │   ├─ llm.chat(eval_prompt, system=evaluator_system)  ← LLM call #6
  │   └─ returns: {raw: "SCORE_CORRECTNESS: 9/10...", scores: {correctness: 9, ...}}
  │
  ├─ memory.stm.add("system", "Completed task: write a fibonacci function")
  ├─ memory.ltm.write("completed_task", {task, code, success, debug_rounds})
  │     write to memory/ltm.json
  │
  └─ returns results dict to main.py
       │
       ▼ terminal_ui renders:
         ▶ Final Code
         ▶ Execution: SUCCESS
         ▶ Code Evaluation


---

## Agent Lifecycle State Machine


                ┌──────────┐
                │  CREATED │
                └────┬─────┘
                     │ __init__
                ┌────▼──────────┐
                │  INITIALIZED  │
                └────┬──────────┘
                     │
                ┌────▼─────┐
       ┌───────►│   IDLE   │◄──────────────────────┐
       │        └────┬─────┘                       │
       │             │ run()                        │
       │        ┌────▼──────┐                      │
       │        │  RUNNING  │                      │
       │        └────┬──────┘                      │
       │             │                             │
       │    ┌────────┴────────┐                   │
       │    │                 │                   │
       │ ┌──▼──────┐    ┌─────▼────┐             │
       └─│ SUCCESS │    │  FAILED  ├─────────────┘
         └─────────┘    └──────────┘

    ┌────────┐     PAUSED is reachable from RUNNING
    │ PAUSED │     (via AgentRegistry.pause())
    └────────┘

    TERMINATED is a terminal state reached via AgentRegistry.terminate()


State transitions are published as `agent:status` events, which are logged to the session.

---

## Memory Architecture


MemorySystem
├── STM (deque, max 20)
│   ├── User messages during REPL session
│   ├── Agent completions ("Generated code for: ...")
│   └── Wiped when session ends
│
├── LTM (JSON file: memory/ltm.json)
│   ├── Key: "ltm:<topic>:<md5[:8]>"
│   ├── completed_task entries (importance=0.7) ← from OrchestratorAgen
│   ├── research entries (importance=0.4)       ← from ResearchAgen
│   └── Persists ACROSS sessions
│
└── WorkingMemory (plain dict)
    └── Task-scoped scratch space, cleared between tasks


**LTM search algorithm:**
- Case-insensitive keyword match against `json.dumps(entry)` string
- Returns all entries containing the query term
- No vector embeddings — purely lexical (fast, no deps)

---

## Hook System


Hook registration (at startup in main.py):

hook_registry.register(HookType.PRE_LLM_CALL, _log_pre_llm)

↓ When an agent (or future code) calls:

hook_registry.execute(HookType.PRE_LLM_CALL, agent_name, prompt)

↓ All registered callbacks are invoked sequentially
↓ Last non-None return value is returned to caller


**Extending the system with a hook example:**
```python
def rate_limit_hook(agent, prompt):
    import time
    time.sleep(0.5)   # throttle LLM calls

hook_registry.register(HookType.PRE_LLM_CALL, rate_limit_hook)


---

## Session Persistence

Every run creates a `sessions/<8-char-id>.json` file:

```json
{
  "session_id": "a1b2c3d4",
  "created_at": 1234567890.123,
  "messages": [
    {"role": "user", "content": "write a fibonacci function", "timestamp": 1234567890.5}
  ],
  "tool_calls": [],
  "code_artifacts": [],
  "ralph_traces": [
    {"agent_id": "CoderAgent_abc123", "trace": {"REFLECT": "...", "PLAN": "..."}, "timestamp": ...}
  ],
  "events": [
    {"type": "agent:start", "data": {"agent_id": "...", "task": "..."}, "timestamp": ...},
    {"type": "sandbox:result", "data": {"success": true, "stdout": "55\n"}, "timestamp": ...}
  ]
}


Sessions are loaded on restart via `/session` command or `SessionManager.load_session(session_id)`.

---

## Error Handling Strategy

| Layer | Failure mode | Handled by |
|-------|-------------|------------|
| HTTP/network | Ollama unreachable, timeout | `OllamaClient.chat()` catches all → `[LLM_ERROR]` string |
| LLM response | Unexpected format, missing keys | `OllamaClient.chat()` catches `KeyError`, `JSONDecodeError` |
| Code parsing | No fences in LLM response | `_extract_code()` falls back to raw text |
| Score parsing | LLM doesn't use expected format | Multi-pattern fallback regex; `None` → displayed as `n/a` |
| Sandbox timeout | Code runs > 30s | `subprocess.TimeoutExpired` caught → returncode=1 |
| Agent exception | Unexpected error in `execute()` | `BaseAgent.run()` catches all → `FAILED` status + event |
| LTM I/O | Disk write fails | `LTM._save()` catches `OSError`, prints warning |
| Session I/O | Load fails | `SessionManager.load_session()` returns `None` |

**Principle:** No exception propagates to the user as a traceback. All errors are caught and returned as structured error values.

---

## Key Design Patterns

### 1. Dependency Injection

All infrastructure is created once in `_bootstrap()` and passed explicitly to every agent. No global state, no singletons.

### 2. Template Method Pattern

`BaseAgent.run()` defines the algorithm skeleton (RALPH → execute → lifecycle events). Subclasses override only `execute()`.

### 3. Strategy Pattern

`SandboxRunner.execute()` dispatches on `language` parameter. Adding a new language (e.g., JavaScript) only requires adding `elif language == "javascript": return self._run_node(code)`.

### 4. Observer Pattern

`EventBus` decouples publishers (agents) from subscribers (session logger, future monitors). New observers can be added without modifying agent code.

### 5. Facade Pattern

`MemorySystem` is a single object that provides access to STM, LTM, and WorkingMemory through a unified interface. Agents access `self._memory.stm`, `self._memory.ltm`, and `self._memory.working` without knowing the underlying implementations.

### 6. Chain of Responsibility

The debug loop in `OrchestratorAgent` is a limited chain — each `DebuggerAgent` call sees the latest code state and error. After 3 failures the chain stops and the result is reported as FAILED.
