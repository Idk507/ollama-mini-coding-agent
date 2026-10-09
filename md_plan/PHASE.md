# Implementation Phases

> **How to use this file:** Work through phases top-to-bottom. Each phase is self-contained and produces a working system. Never start a later phase until every item in the current phase passes its **Done Checklist**.
>
> Code scaffolding for every item below lives in [ARCHITECTURE_BLUEPRINT.md](ARCHITECTURE_BLUEPRINT.md) under the corresponding `§4.x` section.

---

## Phase 1 — Current Implementation ✅ (Complete)

**Goal:** A working local multi-agent code-execution system driven by Ollama.

### What Exists

| Layer | Component | File |
|---|---|---|
| Entry point | `main.py` — wires all components | `main.py` |
| LLM | `OllamaClient` — wraps `/api/chat` | `src/core/llm_client.py` |
| Reasoning | `RalphEngine` — 5-phase RALPH traces | `src/core/ralph_engine.py` |
| Sandbox | `SandboxRunner` — Docker + subprocess fallback, file_ops | `src/core/sandbox_runner.py` |
| Events | `EventBus` — thread-safe pub/sub with history | `src/core/event_bus.py` |
| Hooks | `HookRegistry` — pre/post hooks; 7 `HookType` values | `src/core/hook_registry.py` |
| Agents | `AgentRegistry` + `AgentStatus` lifecycle FSM | `src/core/agent_registry.py` |
| Memory | `MemorySystem` — STM (deque/20) + LTM (JSON KV) + WorkingMemory | `src/core/memory_system.py` |
| Sessions | `Session` — messages, tool_calls, artifacts, traces; JSON persistence | `src/core/session_manager.py` |
| Task split | `TaskDecomposer` — LLM-based, ≤8 subtasks, >300-char trigger | `src/core/task_decomposer.py` |
| Agents | Orchestrator → Coder → Executor → Debugger → Evaluator → Research → Memory | `src/agents/*.py` |
| UI | `TerminalUI` — colored Rich / ANSI output | `src/ui/terminal_ui.py` |

### Agent Lifecycle

```
CREATED → INITIALIZED → IDLE → RUNNING → SUCCESS ─┐
                                          └ FAILED ─┴→ TERMINATED
```

### Done Checklist

- [x] `python main.py` starts and accepts NL tasks
- [x] Code is generated, executed in Docker, debugged on failure, evaluated
- [x] Sessions persist to `sessions/` as JSON
- [x] LTM persists to `memory/ltm.json`
- [x] RALPH traces logged per agent turn

---

## Phase 2 — Foundation Layer

**Goal:** Give the system project-aware context and a hardened hook lifecycle — the two lowest-risk, highest-impact additions.

**Depends on:** Phase 1

### Items

| # | Feature | Blueprint Ref | Files Created / Modified |
|---|---|---|---|
| 2.1 | **Project Instruction Loading** — `PROJECT.md` + `.agent/rules/*.md` + `@import` support | §4.1 | **Create** `src/core/instruction_loader.py`; **Edit** `src/agents/base_agent.py` (`_build_system_prompt`) |
| 2.2 | **Hook System Hardening** — 10 new `HookType` values + blocking `fire_blocking()` | §4.2 | **Edit** `src/core/hook_registry.py` |
| 2.3 | **`PROJECT.md`** — project-wide agent instructions | §4.1 | **Create** `PROJECT.md` |

### New Pip Dependencies

None — standard library only.

### Acceptance Criteria

- [ ] `PROJECT.md` content appears in every agent's system prompt (verify via `hook:pre` event payload)
- [ ] `@import` in `PROJECT.md` correctly resolves referenced files
- [ ] Files in `.agent/rules/` load only when working inside the matching sub-path
- [ ] `HookType.SANDBOX_PRE` with `allow_block=True` can abort sandbox execution when it returns `{"decision": "block"}`
- [ ] `HookType.SESSION_START` fires once during `main.py` startup
- [ ] All existing Phase 1 tests still pass

---

## Phase 3 — Tool & Agent Extensibility

**Goal:** Let agents discover and call external tools via a typed registry, and define new agents/skills as YAML-frontmatter Markdown files — no Python required.

**Depends on:** Phase 2

### Items

| # | Feature | Blueprint Ref | Files Created / Modified |
|---|---|---|---|
| 3.1 | **ToolRegistry** — programmatic + YAML `.agent/tools/*.yaml` tool registration; OpenAI-schema export | §4.3 | **Create** `src/core/tool_registry.py` |
| 3.2 | **Agent / Skill Definition Files** — `.agent/agents/*.md` + `.agent/skills/*.md` with YAML frontmatter | §4.4 | **Create** `src/core/agent_definition_loader.py`; **Create** `.agent/` directory tree |
| 3.3 | **PermissionEngine** — `allow/ask/deny` glob rules; `Decision` enum | §4.5 | **Create** `src/core/permission_engine.py` |
| 3.4 | **Wire `ToolRegistry` into `OllamaClient`** — pass tool schemas to Ollama function-call payload | §4.3 | **Edit** `src/core/llm_client.py` |
| 3.5 | **Wire `PermissionEngine` into `ExecutorAgent`** — gate sandbox execution | §4.5 | **Edit** `src/agents/executor_agent.py` |
| 3.6 | **Wire `AgentDefinitionLoader` into `OrchestratorAgent`** — load `.agent/agents/*.md` at session start | §4.4 | **Edit** `src/agents/orchestrator_agent.py` |

### New Pip Dependencies

```
pyyaml
```

### Directory Structure Added

```
.agent/
├── agents/          # *.md agent definition files
├── skills/          # *.md skill/prompt files
└── tools/           # *.yaml tool definitions
```

### Acceptance Criteria

- [ ] `ToolRegistry.load_from_directory(".agent/tools")` loads a sample YAML tool without error
- [ ] `ToolRegistry.get_schema()` returns valid OpenAI-style function definitions
- [ ] A YAML-defined tool can be called by name from `ExecutorAgent` via `ToolRegistry.call(name, **kwargs)`
- [ ] A `.agent/agents/test_agent.md` file is parsed into an `AgentDefinition` object with correct fields
- [ ] A `.agent/skills/test_skill.md` file is parsed into a `SkillDefinition` object
- [ ] `PermissionEngine.evaluate("sandbox", "rm -rf /")` returns `Decision.DENY` when rule is set
- [ ] `PermissionEngine.evaluate("tool", "read_file")` returns `Decision.ALLOW` for whitelisted tool
- [ ] Attempting blocked sandbox execution raises `PermissionError`
- [ ] All previous phase acceptance criteria still pass

---

## Phase 4 — Memory Upgrade

**Goal:** Upgrade short-term recall with per-agent persistent memory dirs and replace keyword LTM with semantic vector search.

**Depends on:** Phase 3

### Items

| # | Feature | Blueprint Ref | Files Created / Modified |
|---|---|---|---|
| 4.1 | **Persistent Agent Memory Directories** — per-agent `notes.md`, `facts.json`, `history.jsonl`; `as_context_block()` for prompt injection | §4.8 | **Create** `src/core/agent_memory.py`; **Edit** `src/agents/base_agent.py` |
| 4.2 | **Vector LTM (ChromaDB)** — semantic search replacing keyword search; backward-compatible; `use_vector` flag | §4.6 | **Create** `src/core/vector_memory.py`; **Edit** `src/core/memory_system.py` |

### New Pip Dependencies

```
chromadb
sentence-transformers
```

### Directory Structure Added

```
memory/
├── ltm.json            # existing keyword LTM (kept as fallback)
├── vector_ltm/         # ChromaDB persistent store (new)
└── agents/             # per-agent memory dirs (new)
    ├── coderagent/
    │   ├── notes.md
    │   ├── facts.json
    │   └── history.jsonl
    └── executoragent/
        └── ...
```

### Acceptance Criteria

- [ ] `AgentMemory("coder").set_fact("preferred_style", "type-hinted")` persists across process restarts
- [ ] `AgentMemory("coder").as_context_block()` returns non-empty string injected into system prompt
- [ ] `AgentMemory.log_event()` appends to `history.jsonl`; `read_history(last_n=10)` returns correct slice
- [ ] `VectorLTM.store(key, text)` + `VectorLTM.search(query)` returns semantically related entry (not just keyword match)
- [ ] `MemorySystem(use_vector=True)` routes `ltm_search()` through `VectorLTM`
- [ ] `MemorySystem(use_vector=False)` (default) uses existing JSON keyword search — no regression
- [ ] All previous phase acceptance criteria still pass

---

## Phase 5 — Real-time & API

**Goal:** Stream tokens to the terminal in real-time and expose the orchestrator as a local HTTP/WebSocket API for external tools and UIs.

**Depends on:** Phase 4

### Items

| # | Feature | Blueprint Ref | Files Created / Modified |
|---|---|---|---|
| 5.1 | **Streaming Response Support** — `OllamaClient.stream()` generator yielding tokens | §4.7 | **Edit** `src/core/llm_client.py` |
| 5.2 | **Terminal streaming display** — `TerminalUI.stream_response()` helper | §4.7 | **Edit** `src/ui/terminal_ui.py` |
| 5.3 | **REST + WebSocket API Gateway** — FastAPI app with `/tasks`, `/ws`, `/health`; `create_app()` factory | §4.9 | **Create** `src/ui/api_server.py` |
| 5.4 | **`--server` CLI flag** — start API server from `main.py` | §4.9 | **Edit** `main.py` |

### New Pip Dependencies

```
fastapi
uvicorn[standard]
websockets
```

### Acceptance Criteria

- [ ] `OllamaClient.stream(messages)` yields at least one non-empty string token for a simple prompt
- [ ] Terminal shows tokens appearing progressively (no waiting for full response)
- [ ] `GET http://127.0.0.1:8765/health` returns `{"status": "ok"}`
- [ ] `POST http://127.0.0.1:8765/tasks` with `{"task": "print hello world"}` returns a `TaskResponse` JSON object
- [ ] WebSocket client connecting to `ws://127.0.0.1:8765/ws` can send a task and receive a result
- [ ] `python main.py --server` starts uvicorn and does not open the interactive loop
- [ ] CORS headers restrict origins to `localhost` (security check)
- [ ] All previous phase acceptance criteria still pass

---

## Phase 6 — Observability & Automation

**Goal:** Add structured tracing for every operation and support non-interactive headless execution for CI/CD pipelines.

**Depends on:** Phase 5

### Items

| # | Feature | Blueprint Ref | Files Created / Modified |
|---|---|---|---|
| 6.1 | **TraceLogger** — OpenTelemetry-compatible JSONL spans; `Span` context manager; per-call attributes | §4.10 | **Create** `src/core/trace_logger.py` |
| 6.2 | **Instrument key call sites** — wrap `OllamaClient.chat()`, `SandboxRunner.execute()`, each agent `run()` | §4.10 | **Edit** `src/core/llm_client.py`, `src/core/sandbox_runner.py`, `src/agents/base_agent.py` |
| 6.3 | **Headless `--task` mode** — single-shot CLI execution; `--output` file; `sys.exit(0)` on completion | §4.11 | **Edit** `main.py` |
| 6.4 | **Argument parser** — `argparse`-based: `--task`, `--output`, `--model`, `--session`, `--server`, `--port`, `--no-docker` | §4.11 | **Edit** `main.py` |
| 6.5 | **GitHub Actions workflow** — `.github/workflows/agent_task.yml` for workflow-dispatch runs | §4.11 | **Create** `.github/workflows/agent_task.yml` |

### New Pip Dependencies

None — standard library only (`argparse`, `json`, `time`, `uuid`, `contextlib`).

### Acceptance Criteria

- [ ] `sessions/trace.jsonl` is created after any agent run; each line is valid JSON with keys: `span_id`, `name`, `duration_ms`, `status`
- [ ] An `llm_call` span exists for every `OllamaClient.chat()` invocation
- [ ] A `sandbox_execute` span exists for every `SandboxRunner` call
- [ ] `python main.py --task "print hello" --output result.txt` writes result to `result.txt` and exits with code 0
- [ ] `python main.py --task "bad task"` writes an error to stdout and exits with non-zero code on failure
- [ ] `python main.py --model qwen2:7b` overrides the default model
- [ ] `python main.py --no-docker` uses subprocess sandbox
- [ ] All previous phase acceptance criteria still pass

---

## Phase 7 — Production Deployment

**Goal:** Package the entire stack (Ollama, ChromaDB, agent service) as a composable Docker Compose setup with a layered configuration system.

**Depends on:** Phase 6

### Items

| # | Feature | Blueprint Ref | Files Created / Modified |
|---|---|---|---|
| 7.1 | **`Dockerfile`** — non-root user, `python:3.12-slim`, exposes port 8765 | §4.12 | **Create** `Dockerfile` |
| 7.2 | **`docker-compose.yml`** — Ollama + ChromaDB (profile: `vector`) + agent service with health checks | §4.12 | **Create** `docker-compose.yml` |
| 7.3 | **Layered config system** — `settings.yaml` → `settings.local.yaml` → `settings.managed.yaml` merge loader | §5 | **Create** `src/core/config_loader.py`; **Create** `settings.yaml` |
| 7.4 | **`settings.yaml` schema** — full config reference: `llm`, `sandbox`, `memory`, `permissions`, `hooks`, `server`, `tracing` sections | §5 | **Create** `settings.yaml` |
| 7.5 | **Wire config loader into `main.py`** — replace hardcoded constants with config values | §5 | **Edit** `main.py` |

### New Pip Dependencies

```
pyyaml          # already added in Phase 3
```

### Full Settings Schema (`settings.yaml`)

```yaml
llm:
  base_url: "http://localhost:11434"
  model: "glm4:9b"
  timeout_s: 120
  max_retries: 3

sandbox:
  backend: docker           # docker | subprocess
  image: python:3.12-slim
  memory_limit: 256m
  cpu_limit: "0.5"
  network: none
  timeout_s: 30

memory:
  ltm_path: memory/ltm.json
  stm_max_turns: 20
  use_vector: false
  vector_persist_dir: memory/vector_ltm
  agent_memory_dir: memory/agents

permissions:
  deny:
    - pattern: "file:*.env"
      reason: "Environment files are protected"
  ask:
    - pattern: "tool:execute_sql"
      reason: "SQL execution requires approval"
  allow:
    - pattern: "tool:read_file"
    - pattern: "sandbox:python *"

hooks: {}                   # hook handler module paths (future extension)

server:
  host: "127.0.0.1"
  port: 8765
  cors_origins: ["http://localhost:3000"]

tracing:
  enabled: true
  output: sessions/trace.jsonl
```

### Acceptance Criteria

- [ ] `docker compose up` (standard stack) starts Ollama + agent service; `GET /health` returns 200
- [ ] `docker compose --profile vector up` also starts ChromaDB
- [ ] Agent container runs as non-root user (`agentuser`)
- [ ] `settings.local.yaml` values override `settings.yaml` values at runtime
- [ ] `settings.managed.yaml` (if present) overrides all other config files
- [ ] `python main.py --model qwen2:7b` still overrides config-file model (CLI > config file)
- [ ] `docker compose exec ollama ollama pull glm4:9b` works end-to-end
- [ ] Volumes (`sessions/`, `memory/`) survive container restarts
- [ ] All previous phase acceptance criteria still pass

---

## Summary Table

| Phase | Name | Key Deliverables | New Files | Dependencies |
|---|---|---|---|---|
| **1** | Current Implementation | Full multi-agent pipeline, RALPH, Docker sandbox | *(existing)* | — |
| **2** | Foundation Layer | `InstructionLoader`, hook hardening, `PROJECT.md` | `src/core/instruction_loader.py`, `PROJECT.md` | Phase 1 |
| **3** | Tool & Agent Extensibility | `ToolRegistry`, `AgentDefinitionLoader`, `PermissionEngine` | `src/core/tool_registry.py`, `src/core/agent_definition_loader.py`, `src/core/permission_engine.py` | Phase 2 + `pyyaml` |
| **4** | Memory Upgrade | Per-agent dirs, Vector LTM (ChromaDB) | `src/core/agent_memory.py`, `src/core/vector_memory.py` | Phase 3 + `chromadb`, `sentence-transformers` |
| **5** | Real-time & API | Streaming tokens, REST + WebSocket API | `src/ui/api_server.py` | Phase 4 + `fastapi`, `uvicorn` |
| **6** | Observability & Automation | TraceLogger, headless `--task` CLI, GitHub Actions | `src/core/trace_logger.py`, `.github/workflows/agent_task.yml` | Phase 5 |
| **7** | Production Deployment | Docker Compose stack, layered config system | `Dockerfile`, `docker-compose.yml`, `settings.yaml`, `src/core/config_loader.py` | Phase 6 |

---

## Recommended Incremental Commit Order

```
Phase 2:  instruction_loader → hook_registry edits → PROJECT.md
Phase 3:  tool_registry → agent_definition_loader → permission_engine → wiring
Phase 4:  agent_memory → vector_memory → memory_system edits
Phase 5:  llm_client stream → terminal_ui stream helper → api_server → main.py --server
Phase 6:  trace_logger → instrumentation edits → main.py argparse → GitHub Actions
Phase 7:  Dockerfile → docker-compose.yml → config_loader → settings.yaml → main.py wiring
```

Each commit group can be reviewed, tested, and merged independently before the next group begins.
