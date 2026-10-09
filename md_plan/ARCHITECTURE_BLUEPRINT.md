# Architecture Blueprint: Ollama Multi-Agent Code Execution System

> **Purpose:** This document maps the entire existing codebase, draws parallels with Claude Code's architecture, and provides a concrete, build-ready extension roadmap. Every section builds *on top of* existing classes — no rewrites, only additions.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Map](#2-current-architecture-map)
3. [Claude Code Concept Mappings](#3-claude-code-concept-mappings)
4. [Extension Roadmap](#4-extension-roadmap)
   - 4.1 [Project Instruction Loading (CLAUDE.md Equivalent)](#41-project-instruction-loading-claudemd-equivalent)
   - 4.2 [Hook System Hardening](#42-hook-system-hardening)
   - 4.3 [MCP-Style Tool Integration Layer](#43-mcp-style-tool-integration-layer)
   - 4.4 [Subagent / Skill Definition Files](#44-subagent--skill-definition-files)
   - 4.5 [Permission Rules Engine](#45-permission-rules-engine)
   - 4.6 [RAG / Vector Memory for LTM](#46-rag--vector-memory-for-ltm)
   - 4.7 [Streaming Response Support](#47-streaming-response-support)
   - 4.8 [Persistent Agent Memory Directories](#48-persistent-agent-memory-directories)
   - 4.9 [WebSocket / REST API Gateway](#49-websocket--rest-api-gateway)
   - 4.10 [Observability & Debug Logging](#410-observability--debug-logging)
   - 4.11 [CI/CD Headless Mode](#411-cicd-headless-mode)
   - 4.12 [Docker Compose Scaling](#412-docker-compose-scaling)
5. [Configuration Schema](#5-configuration-schema)
6. [API Reference for Extension Authors](#6-api-reference-for-extension-authors)
7. [Security Checklist](#7-security-checklist)
8. [Dependency Graph](#8-dependency-graph)

---

## 1. Executive Summary

This system is a **local-first multi-agent code execution platform** powered by Ollama (default model: `glm4:9b`). It chains specialized agents through a structured reasoning loop called **RALPH** (Reflect → Analyze → Learn → Plan → Hypothesize) to receive natural-language tasks, generate Python code, execute it in an isolated Docker sandbox, debug failures, and evaluate results.

### Key Properties

| Property | Value |
|---|---|
| LLM Backend | Ollama (`http://localhost:11434`) |
| Default Model | `glm4:9b` |
| Sandbox | Docker `python:3.12-slim`, `--network none`, `--memory 256m`, `--cpus 0.5` |
| Fallback Sandbox | `subprocess` (when Docker unavailable) |
| Agent Communication | Thread-safe `EventBus` pub/sub |
| Memory | STM (deque, 20 turns) + LTM (JSON-backed KV) + WorkingMemory |
| Reasoning Loop | RALPH 5-phase trace via LLM |
| Persistence | Session JSON in `sessions/`, LTM in `memory/ltm.json` |
| Entry Point | `main.py` |

---

## 2. Current Architecture Map


main.py
└── OrchestratorAgent          # Top-level planner & pipeline runner
    ├── TaskDecomposer          # Splits complex tasks into ≤8 subtasks
    ├── CoderAgent              # NL → Python code (extracts from ```python fences)
    ├── ExecutorAgent           # Runs code in SandboxRunner
    ├── DebuggerAgent           # Diagnoses failures, proposes fixes
    ├── EvaluatorAgent          # Scores output (correctness, safety)
    ├── ResearchAgent           # Retrieves context from memory/web
    └── MemoryAgent             # Reads/writes STM, LTM, WorkingMemory


### Core Infrastructure (`src/core/`)

| Module | Class | Responsibility |
|---|---|---|
| `llm_client.py` | `OllamaClient` | Wraps `/api/chat`; `chat()`, `is_available()`, `list_models()` |
| `ralph_engine.py` | `RalphEngine` | Generates 5-phase RALPH traces via LLM; parses output |
| `event_bus.py` | `EventBus` | Thread-safe pub/sub with history; named channels |
| `hook_registry.py` | `HookRegistry` | Pre/post hooks on tool calls and LLM calls |
| `agent_registry.py` | `AgentRegistry` | Register, pause, resume, terminate agents; thread-safe |
| `session_manager.py` | `Session` | Tracks messages, tool_calls, code_artifacts, ralph_traces; JSON persistence |
| `memory_system.py` | `MemorySystem` | STM (deque) + LTM (JSON KV + keyword search) + WorkingMemory |
| `sandbox_runner.py` | `SandboxRunner` | Docker isolation + file ops + self-healing restart |
| `task_decomposer.py` | `TaskDecomposer` | LLM-based task splitting (triggers on >300 chars or >3 ANALYZE steps) |

### Agent Lifecycle States


CREATED → INITIALIZED → IDLE → RUNNING → SUCCESS ─┐
                                          └ FAILED ─┴→ TERMINATED


### Event Bus Channels (existing)


agent:spawn, agent:start, agent:complete, agent:error, agent:ralph
hook:pre, hook:pos
memory:read, memory:write
sandbox:execute, sandbox:resul


### Hook Types (existing `HookType` enum)


PRE_TOOL_CALL, POST_TOOL_CALL
PRE_LLM_CALL, POST_LLM_CALL
ON_ERROR, ON_MEMORY_READ, ON_MEMORY_WRITE


---

## 3. Claude Code Concept Mappings

This table maps every major Claude Code architectural concept to its equivalent (or intended equivalent) in this codebase:

| Claude Code Concept | This Codebase Equivalent | Gap / Next Step |
|---|---|---|
| `CLAUDE.md` — project instructions | No equivalent yet | Add `InstructionLoader` (§4.1) |
| Auto memory (`MEMORY.md`) | `MemoryAgent` + `memory/ltm.json` | Add per-agent memory dirs (§4.8) |
| **Hooks** (PreToolUse, PostToolUse, Stop…) | `HookRegistry` with `HookType` enum | Add all missing event types (§4.2) |
| **Subagents** (`.claude/agents/*.md`) | `AgentRegistry` + agent classes | Add YAML-frontmatter agent definition files (§4.4) |
| **Skills** (`.claude/skills/*.md`) | No equivalent yet | Add Skill loader into system prompt (§4.4) |
| **MCP servers** (`.mcp.json`) | No equivalent yet | Add `ToolRegistry` with MCP-style protocol (§4.3) |
| **Permission rules** (`allow/deny/ask`) | No equivalent yet | Add `PermissionEngine` (§4.5) |
| **Settings hierarchy** (managed > project > user) | `main.py` hardcoded config | Add layered YAML config (§5) |
| **Session resume** | `Session` JSON persistence | Already works; wire `--resume` flag |
| **Headless / `-p` mode** | No equivalent yet | Add CLI `--task` flag (§4.11) |
| **RALPH loop** | `RalphEngine` ✓ | Fully implemented |
| **Task decomposition** | `TaskDecomposer` ✓ | Fully implemented |
| **Sandbox isolation** | `SandboxRunner` (Docker) ✓ | Fully implemented |
| **Streaming** | Not implemented | Add streaming endpoint (§4.7) |
| **Observability / debug log** | No structured tracing | Add `TraceLogger` (§4.10) |

---

## 4. Extension Roadmap

> Each subsection contains: **what to build**, **which existing class to extend**, and **ready-to-use code scaffolding**.

---

### 4.1 Project Instruction Loading (CLAUDE.md Equivalent)

**Goal:** Load `PROJECT.md` (and optionally `.agent/rules/*.md`) at session start and inject their content into every agent's system prompt — mirroring how Claude Code loads `CLAUDE.md`.

**Existing hook:** `HookType.PRE_LLM_CALL` in `HookRegistry`.

**New file:** `src/core/instruction_loader.py

```python
# src/core/instruction_loader.py
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional


_IMPORT_RE = re.compile(r"^@import\s+(.+)$", re.MULTILINE)


class InstructionLoader:
    """
    Loads PROJECT.md and .agent/rules/*.md files, resolves @import directives,
    and returns a flat instruction string to prepend to system prompts.

    Directory layout (mirrors Claude Code):
        PROJECT.md               — project-wide instructions
        .agent/rules/            — path-scoped rule files (loaded based on cwd match)
        .agent/rules/src.md      — applies when working in src/**
    """

    def __init__(self, project_root: str = "."):
        self.root = Path(project_root).resolve()

    def load(self, working_dir: Optional[str] = None) -> str:
        """Return merged instruction text for the given working directory."""
        parts: list[str] = []

        # 1. Project-wide instructions
        project_md = self.root / "PROJECT.md"
        if project_md.exists():
            parts.append(self._resolve_imports(project_md.read_text("utf-8"), project_md.parent))

        # 2. Path-scoped rules
        rules_dir = self.root / ".agent" / "rules"
        if rules_dir.is_dir() and working_dir:
            rel = Path(working_dir).resolve().relative_to(self.root)
            for rule_file in sorted(rules_dir.glob("*.md")):
                # Simple convention: filename (without .md) must be a prefix of the relative path
                stem = rule_file.stem  # e.g. "src" matches "src/agents/..."
                if str(rel).startswith(stem):
                    parts.append(self._resolve_imports(rule_file.read_text("utf-8"), rule_file.parent))

        return "\n\n---\n\n".join(parts)

    def _resolve_imports(self, text: str, base: Path) -> str:
        """Replace @import <path> directives with file contents."""
        def replacer(m: re.Match) -> str:
            target = (base / m.group(1).strip()).resolve()
            if target.exists():
                return target.read_text("utf-8")
            return f"<!-- @import {m.group(1)} not found -->"
        return _IMPORT_RE.sub(replacer, text)


**Wire into `BaseAgent`** (add to `src/agents/base_agent.py`, inside `_build_system_prompt`):

```python
# At the top of base_agent.py, add import:
from src.core.instruction_loader import InstructionLoader

# Inside BaseAgent.__init__ or _build_system_prompt:
_loader = InstructionLoader()
project_instructions = _loader.load()
if project_instructions:
    system_prompt = project_instructions + "\n\n" + system_promp


**Create `PROJECT.md` in your project root:**

```markdown
# Project Instructions

## Code Style
- Always use type hints
- Prefer pathlib over os.path
- All exceptions must be caught and logged via EventBus

## Sandbox Rules
- Do not write files outside /workspace
- Network access is disabled inside the sandbox

@import .agent/rules/security.md


---

### 4.2 Hook System Hardening

**Goal:** Add the missing lifecycle hook event types that exist in Claude Code but are absent from the current `HookType` enum.

**File to edit:** `src/core/hook_registry.py

Add these members to the existing `HookType` enum:

```python
# Additions to the HookType enum in hook_registry.py

class HookType(Enum):
    # --- existing ---
    PRE_TOOL_CALL   = "pre_tool_call"
    POST_TOOL_CALL  = "post_tool_call"
    PRE_LLM_CALL    = "pre_llm_call"
    POST_LLM_CALL   = "post_llm_call"
    ON_ERROR        = "on_error"
    ON_MEMORY_READ  = "on_memory_read"
    ON_MEMORY_WRITE = "on_memory_write"

    # --- new additions ---
    SESSION_START      = "session_start"    # fires once at session initialization
    SESSION_END        = "session_end"      # fires on graceful shutdown
    AGENT_SPAWN        = "agent_spawn"      # before a new agent is registered
    AGENT_STOP         = "agent_stop"       # after an agent reaches SUCCESS/FAILED
    SANDBOX_PRE        = "sandbox_pre"      # before sandbox execution (block-capable)
    SANDBOX_POST       = "sandbox_post"     # after sandbox execution
    TASK_CREATED       = "task_created"     # after TaskDecomposer produces subtasks
    TASK_COMPLETED     = "task_completed"   # after all subtasks complete
    CONFIG_CHANGE      = "config_change"    # when config/settings reload
    PERMISSION_REQUEST = "permission_request"  # before asking user to approve an action


**Add a blocking-capable `fire_blocking` method to `HookRegistry`:**

```python
# In HookRegistry class:

def fire_blocking(
    self,
    hook_type: HookType,
    payload: dict,
    *,
    allow_block: bool = False,
) -> dict:
    """
    Fire all registered hooks for hook_type synchronously.

    If allow_block=True, hooks may return {"decision": "block", "reason": "..."}
    to abort the operation. The caller must check the returned dict.

    Returns:
        {"proceed": True} on success, or
        {"proceed": False, "reason": str} if any hook blocked.
    """
    hooks = self._hooks.get(hook_type, [])
    for hook_fn in hooks:
        try:
            result = hook_fn(payload)
            if allow_block and isinstance(result, dict):
                if result.get("decision") == "block":
                    return {"proceed": False, "reason": result.get("reason", "Blocked by hook")}
                if result.get("decision") == "deny":
                    return {"proceed": False, "reason": result.get("reason", "Denied by hook")}
        except Exception as exc:
            # Hooks must never crash the pipeline
            self.fire(HookType.ON_ERROR, {"hook_type": hook_type.value, "error": str(exc)})
    return {"proceed": True}


**Example usage in `ExecutorAgent`** (before sandbox call):

```python
result = self.hook_registry.fire_blocking(
    HookType.SANDBOX_PRE,
    {"code": code, "agent_id": self.agent_id},
    allow_block=True,
)
if not result["proceed"]:
    raise PermissionError(result["reason"])


---

### 4.3 MCP-Style Tool Integration Layer

**Goal:** Allow external tools (web search, file I/O, database, HTTP APIs) to be registered and called by agents via a standardized protocol — mirroring MCP servers.

**New file:** `src/core/tool_registry.py

```python
# src/core/tool_registry.py
from __future__ import annotations
import importlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from pathlib import Path
import yaml  # pip install pyyaml


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict           # JSON Schema objec
    handler: Callable[..., Any]
    requires_permission: bool = False
    tags: list[str] = field(default_factory=list)


class ToolRegistry:
    """
    Central registry for all callable tools available to agents.
    Tools can be registered programmatically or loaded from .agent/tools/*.yaml.

    YAML tool file format (.agent/tools/web_search.yaml):
        name: web_search
        description: Search the web for information
        module: src.tools.web_search     # must expose a `run(**kwargs)` function
        requires_permission: false
        parameters:
          type: objec
          properties:
            query: {type: string}
          required: [query]
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def load_from_directory(self, tools_dir: str = ".agent/tools") -> None:
        """Load all *.yaml tool definitions from a directory."""
        p = Path(tools_dir)
        if not p.is_dir():
            return
        for yaml_file in p.glob("*.yaml"):
            with open(yaml_file) as f:
                spec = yaml.safe_load(f)
            mod = importlib.import_module(spec["module"])
            tool = ToolDefinition(
                name=spec["name"],
                description=spec["description"],
                parameters=spec.get("parameters", {}),
                handler=mod.run,
                requires_permission=spec.get("requires_permission", False),
                tags=spec.get("tags", []),
            )
            self.register(tool)

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered")
        return self._tools[name].handler(**kwargs)

    def get_schema(self) -> list[dict]:
        """Return OpenAI-style function definitions for all tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    def list(self) -> list[str]:
        return list(self._tools.keys())


**Wire into `OllamaClient`** to expose tools in system prompt or function-call payload:

```python
# In OllamaClient.chat(), add tools context to messages when tool_registry is provided:
def chat(self, messages, system=None, tools: list[dict] | None = None, **kw):
    payload = {"model": self.model, "messages": messages, "stream": False}
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = tools   # Ollama supports this in recent versions
    ...


---

### 4.4 Subagent / Skill Definition Files

**Goal:** Define agents and skills as Markdown files with YAML frontmatter, loaded at session start — identical to Claude Code's subagent definition system.

**Directory layout:**


.agent/
├── agents/
│   ├── sql_analyst.md       # project-scoped agen
│   └── security_auditor.md
├── skills/
│   ├── explain_code.md      # reusable prompt skill
│   └── generate_tests.md
└── tools/
    └── web_search.yaml      # MCP-style tool (§4.3)


**Agent definition file example** (`.agent/agents/sql_analyst.md`):

```markdown
---
name: sql_analys
description: Analyzes SQL queries, explains execution plans, and suggests optimizations
model: glm4:9b
tools: [read_file, execute_sql]
max_turns: 5
memory: projec
requires_permission: false
---

You are a senior SQL analyst. When given a query, you:
1. Parse the SQL structure
2. Identify potential N+1 problems, missing indexes, or full table scans
3. Suggest optimized rewrites with explanations
4. Always test your suggestions before presenting them

Use only SELECT statements. Never modify data.


**New file:** `src/core/agent_definition_loader.py

```python
# src/core/agent_definition_loader.py
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import yaml


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


@dataclass
class AgentDefinition:
    name: str
    description: str
    system_prompt: str
    model: str = "glm4:9b"
    tools: list[str] = field(default_factory=list)
    max_turns: int = 10
    memory: Optional[str] = None          # None | "project" | "user"
    requires_permission: bool = False
    raw_frontmatter: dict = field(default_factory=dict)


@dataclass
class SkillDefinition:
    name: str
    description: str
    prompt_template: str
    model: Optional[str] = None
    raw_frontmatter: dict = field(default_factory=dict)


def _parse_md(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body text)."""
    m = _FRONTMATTER_RE.match(text)
    if m:
        fm = yaml.safe_load(m.group(1)) or {}
        body = text[m.end():]
    else:
        fm, body = {}, tex
    return fm, body.strip()


class AgentDefinitionLoader:
    """
    Loads .agent/agents/*.md and .agent/skills/*.md files.
    Call load() once at session start; the returned dicts are keyed by name.
    """

    def __init__(self, project_root: str = "."):
        self.root = Path(project_root).resolve()

    def load_agents(self) -> dict[str, AgentDefinition]:
        agents: dict[str, AgentDefinition] = {}
        agents_dir = self.root / ".agent" / "agents"
        if not agents_dir.is_dir():
            return agents
        for md_file in agents_dir.glob("*.md"):
            fm, body = _parse_md(md_file.read_text("utf-8"))
            name = fm.get("name", md_file.stem)
            agents[name] = AgentDefinition(
                name=name,
                description=fm.get("description", ""),
                system_prompt=body,
                model=fm.get("model", "glm4:9b"),
                tools=fm.get("tools", []),
                max_turns=fm.get("max_turns", 10),
                memory=fm.get("memory"),
                requires_permission=fm.get("requires_permission", False),
                raw_frontmatter=fm,
            )
        return agents

    def load_skills(self) -> dict[str, SkillDefinition]:
        skills: dict[str, SkillDefinition] = {}
        skills_dir = self.root / ".agent" / "skills"
        if not skills_dir.is_dir():
            return skills
        for md_file in skills_dir.glob("*.md"):
            fm, body = _parse_md(md_file.read_text("utf-8"))
            name = fm.get("name", md_file.stem)
            skills[name] = SkillDefinition(
                name=name,
                description=fm.get("description", ""),
                prompt_template=body,
                model=fm.get("model"),
                raw_frontmatter=fm,
            )
        return skills


**Wire into `OrchestratorAgent`:**

```python
# In OrchestratorAgent.__init__:
from src.core.agent_definition_loader import AgentDefinitionLoader

loader = AgentDefinitionLoader()
self.agent_definitions = loader.load_agents()
self.skill_definitions = loader.load_skills()


---

### 4.5 Permission Rules Engine

**Goal:** Enforce `allow / ask / deny` rules on tool calls and sandbox operations — mirroring Claude Code's permission system.

**New file:** `src/core/permission_engine.py

```python
# src/core/permission_engine.py
from __future__ import annotations
import fnmatch
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Decision(str, Enum):
    ALLOW = "allow"
    ASK   = "ask"
    DENY  = "deny"


@dataclass
class PermissionRule:
    pattern: str          # e.g. "sandbox:*", "tool:execute_sql", "file:*.env"
    decision: Decision
    reason: Optional[str] = None


class PermissionEngine:
    """
    Evaluates permission rules in priority order: DENY > ASK > ALLOW.
    Rules use glob patterns matching "<category>:<subject>".

    Example config (from settings.yaml):
        permissions:
          deny:
            - pattern: "file:*.env"
              reason: "Environment files are protected"
            - pattern: "sandbox:rm -rf*"
              reason: "Destructive shell commands are blocked"
          ask:
            - pattern: "tool:execute_sql"
              reason: "SQL execution requires approval"
          allow:
            - pattern: "tool:read_file"
            - pattern: "sandbox:python *"
    """

    def __init__(self, rules: list[PermissionRule] | None = None):
        self._rules: list[PermissionRule] = rules or []

    def add_rule(self, rule: PermissionRule) -> None:
        self._rules.append(rule)

    def evaluate(self, category: str, subject: str) -> tuple[Decision, Optional[str]]:
        """
        Returns (Decision, reason_or_None).
        DENY beats ASK beats ALLOW. Default is ALLOW when no rules match.
        """
        key = f"{category}:{subject}"
        matched_deny = None
        matched_ask = None

        for rule in self._rules:
            if fnmatch.fnmatch(key, rule.pattern):
                if rule.decision == Decision.DENY:
                    matched_deny = rule
                elif rule.decision == Decision.ASK and matched_deny is None:
                    matched_ask = rule

        if matched_deny:
            return Decision.DENY, matched_deny.reason
        if matched_ask:
            return Decision.ASK, matched_ask.reason
        return Decision.ALLOW, None

    @classmethod
    def from_config(cls, config: dict) -> "PermissionEngine":
        """Build from the permissions section of settings.yaml."""
        rules = []
        perms = config.get("permissions", {})
        for decision_str, entries in perms.items():
            decision = Decision(decision_str)
            for entry in entries or []:
                if isinstance(entry, str):
                    rules.append(PermissionRule(pattern=entry, decision=decision))
                else:
                    rules.append(PermissionRule(
                        pattern=entry["pattern"],
                        decision=decision,
                        reason=entry.get("reason"),
                    ))
        return cls(rules)


**Usage in `ExecutorAgent` before sandbox execution:**

```python
decision, reason = permission_engine.evaluate("sandbox", code[:80])
if decision == Decision.DENY:
    raise PermissionError(f"Sandbox execution denied: {reason}")
elif decision == Decision.ASK:
    confirmed = input(f"Approve execution? ({reason}) [y/N]: ")
    if confirmed.lower() != "y":
        raise PermissionError("User denied execution")


---

### 4.6 RAG / Vector Memory for LTM

**Goal:** Replace keyword search in `MemorySystem.LTM` with semantic vector search using `chromadb` (local, no cloud dependency).

**Install:** `pip install chromadb sentence-transformers

**New file:** `src/core/vector_memory.py

```python
# src/core/vector_memory.py
from __future__ import annotations
from typing import Any
import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorLTM:
    """
    Drop-in replacement for the keyword-search LTM in MemorySystem.
    Uses ChromaDB with a local persistent store and sentence-transformers embeddings.

    Usage:
        ltm = VectorLTM(persist_dir="memory/vector_ltm")
        ltm.store("session_42", "Python list comprehensions are faster than for-loops", importance=0.9)
        results = ltm.search("how to make loops faster", top_k=5)
    """

    COLLECTION = "long_term_memory"

    def __init__(self, persist_dir: str = "memory/vector_ltm"):
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=self.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def store(self, key: str, text: str, metadata: dict[str, Any] | None = None, importance: float = 1.0) -> None:
        meta = {"importance": importance, **(metadata or {})}
        # Upsert: same key replaces old value
        self._col.upsert(
            ids=[key],
            documents=[text],
            metadatas=[meta],
        )

    def search(self, query: str, top_k: int = 5, min_importance: float = 0.0) -> list[dict]:
        """Return list of {key, text, importance, distance} dicts."""
        where = {"importance": {"$gte": min_importance}} if min_importance > 0 else None
        results = self._col.query(
            query_texts=[query],
            n_results=min(top_k, self._col.count() or 1),
            where=where,
        )
        out = []
        for i, doc_id in enumerate(results["ids"][0]):
            out.append({
                "key": doc_id,
                "text": results["documents"][0][i],
                "importance": results["metadatas"][0][i].get("importance", 1.0),
                "distance": results["distances"][0][i],
            })
        return ou

    def delete(self, key: str) -> None:
        self._col.delete(ids=[key])

    def count(self) -> int:
        return self._col.count()


**Swap into `MemorySystem`** (backward compatible — keep JSON LTM as fallback):

```python
# In MemorySystem.__init__, add optional parameter:
def __init__(self, ltm_path="memory/ltm.json", use_vector=False):
    ...
    if use_vector:
        from src.core.vector_memory import VectorLTM
        self._vector_ltm = VectorLTM()
    else:
        self._vector_ltm = None

# In MemorySystem.ltm_search(), try vector first:
def ltm_search(self, query: str, top_k: int = 5) -> list[dict]:
    if self._vector_ltm:
        return self._vector_ltm.search(query, top_k=top_k)
    # fallback to existing keyword search
    ...


---

### 4.7 Streaming Response Suppor

**Goal:** Yield tokens from Ollama as they arrive, enabling real-time terminal output and WebSocket streaming.

**Edit `src/core/llm_client.py`:**

```python
# Add to OllamaClient:

import json
from typing import Generator

def stream(
    self,
    messages: list[dict],
    system: str | None = None,
) -> Generator[str, None, None]:
    """
    Yields text tokens as they stream from Ollama.

    Usage:
        for token in client.stream(messages):
            print(token, end="", flush=True)
    """
    payload = {
        "model": self.model,
        "messages": messages,
        "stream": True,
    }
    if system:
        payload["system"] = system

    import requests
    with requests.post(
        f"{self.base_url}/api/chat",
        json=payload,
        stream=True,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
            if chunk.get("done"):
                break


**Use in `TerminalUI`** for live output:

```python
# In terminal_ui.py — add streaming display helper:
def stream_response(client, messages, system=None):
    print("\n[Agent] ", end="", flush=True)
    for token in client.stream(messages, system=system):
        print(token, end="", flush=True)
    print()   # newline after stream ends


---

### 4.8 Persistent Agent Memory Directories

**Goal:** Give each named agent its own persistent memory directory (like Claude Code's `~/.claude/agent-memory/<name>/`) so agents accumulate knowledge across sessions.

**New file:** `src/core/agent_memory.py

```python
# src/core/agent_memory.py
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime


class AgentMemory:
    """
    Persistent, per-agent memory stored as a directory of JSON + Markdown files.

    Directory layout:
        memory/agents/<agent_name>/
            notes.md            — free-form notes the agent writes to itself
            facts.json          — structured key-value facts
            history.jsonl       — append-only event log
    """

    def __init__(self, agent_name: str, base_dir: str = "memory/agents"):
        self.agent_name = agent_name
        self.dir = Path(base_dir) / agent_name
        self.dir.mkdir(parents=True, exist_ok=True)
        self._notes_file = self.dir / "notes.md"
        self._facts_file = self.dir / "facts.json"
        self._history_file = self.dir / "history.jsonl"

    # ── Notes (free-form Markdown) ──────────────────────────────────────────

    def read_notes(self) -> str:
        if self._notes_file.exists():
            return self._notes_file.read_text("utf-8")
        return ""

    def append_notes(self, text: str) -> None:
        with open(self._notes_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n<!-- {datetime.utcnow().isoformat()} -->\n{text}")

    def overwrite_notes(self, text: str) -> None:
        self._notes_file.write_text(text, encoding="utf-8")

    # ── Facts (structured KV) ───────────────────────────────────────────────

    def get_facts(self) -> dict:
        if self._facts_file.exists():
            return json.loads(self._facts_file.read_text("utf-8"))
        return {}

    def set_fact(self, key: str, value) -> None:
        facts = self.get_facts()
        facts[key] = value
        self._facts_file.write_text(json.dumps(facts, indent=2), encoding="utf-8")

    def delete_fact(self, key: str) -> None:
        facts = self.get_facts()
        facts.pop(key, None)
        self._facts_file.write_text(json.dumps(facts, indent=2), encoding="utf-8")

    # ── History (append-only log) ───────────────────────────────────────────

    def log_event(self, event_type: str, data: dict) -> None:
        entry = {"ts": datetime.utcnow().isoformat(), "type": event_type, **data}
        with open(self._history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def read_history(self, last_n: int = 50) -> list[dict]:
        if not self._history_file.exists():
            return []
        lines = self._history_file.read_text("utf-8").strip().splitlines()
        return [json.loads(l) for l in lines[-last_n:]]

    # ── Context injection ───────────────────────────────────────────────────

    def as_context_block(self) -> str:
        """Return a formatted string suitable for injection into a system prompt."""
        notes = self.read_notes()
        facts = self.get_facts()
        parts = [f"# Agent Memory: {self.agent_name}"]
        if notes:
            parts.append(f"## Notes\n{notes[:2000]}")
        if facts:
            import json as _j
            parts.append(f"## Facts\n```json\n{_j.dumps(facts, indent=2)}\n```")
        return "\n\n".join(parts) if len(parts) > 1 else ""


**Wire into `BaseAgent`:**

```python
# In BaseAgent.__init__:
from src.core.agent_memory import AgentMemory

self.memory = AgentMemory(agent_name=self.__class__.__name__.lower())

# In _build_system_prompt:
memory_context = self.memory.as_context_block()
if memory_context:
    system_prompt = memory_context + "\n\n---\n\n" + system_promp


---

### 4.9 WebSocket / REST API Gateway

**Goal:** Expose the orchestrator as a local HTTP API so IDEs, web UIs, or other tools can interact with it programmatically.

**Install:** `pip install fastapi uvicorn websockets

**New file:** `src/ui/api_server.py

```python
# src/ui/api_server.py
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnec
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class TaskRequest(BaseModel):
    task: str
    session_id: str | None = None
    stream: bool = False


class TaskResponse(BaseModel):
    session_id: str
    result: str
    artifacts: list[dict] = []
    ralph_trace: dict | None = None


def create_app(orchestrator_factory) -> FastAPI:
    """
    orchestrator_factory: callable() -> OrchestratorAgent instance

    Usage:
        app = create_app(lambda: OrchestratorAgent(...))
        uvicorn.run(app, host="127.0.0.1", port=8765)
    """
    app = FastAPI(title="Ollama Multi-Agent API", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:*"],   # restrict in production
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.post("/tasks", response_model=TaskResponse)
    async def run_task(req: TaskRequest):
        orchestrator = orchestrator_factory()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, orchestrator.run, req.task)
        return TaskResponse(
            session_id=req.session_id or str(uuid.uuid4()),
            result=str(result),
        )

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                data = await ws.receive_text()
                req = json.loads(data)
                task = req.get("task", "")
                orchestrator = orchestrator_factory()
                # Run in thread pool; send incremental updates via event bus subscription
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, orchestrator.run, task)
                await ws.send_json({"type": "result", "content": str(result)})
        except WebSocketDisconnect:
            pass

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


**Start the server from `main.py` with a `--server` flag:**

```python
# In main.py, add:
if "--server" in sys.argv:
    import uvicorn
    from src.ui.api_server import create_app
    app = create_app(lambda: build_orchestrator())
    uvicorn.run(app, host="127.0.0.1", port=8765)


---

### 4.10 Observability & Debug Logging

**Goal:** Emit structured trace events (OpenTelemetry-compatible JSON) so every agent turn, tool call, sandbox execution, and RALPH phase is traceable.

**New file:** `src/core/trace_logger.py

```python
# src/core/trace_logger.py
from __future__ import annotations
import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator


class Span:
    def __init__(self, name: str, parent_id: str | None, logger: "TraceLogger"):
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_id = parent_id
        self.name = name
        self.start_time = time.time()
        self._logger = logger
        self.attributes: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def end(self, status: str = "ok", error: str | None = None) -> None:
        duration_ms = int((time.time() - self.start_time) * 1000)
        self._logger._write({
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "start_time": self.start_time,
            "duration_ms": duration_ms,
            "status": status,
            "error": error,
            **self.attributes,
        })


class TraceLogger:
    """
    Writes OpenTelemetry-compatible JSONL traces to a file.
    Each line is one span (agent turn, tool call, sandbox execution, LLM call, etc.)

    Usage:
        tracer = TraceLogger("sessions/trace.jsonl")
        with tracer.span("llm_call", parent_id=turn_span.span_id) as s:
            s.set("model", "glm4:9b")
            s.set("prompt_tokens", 512)
            response = llm.chat(messages)
        # span auto-ends on context exi
    """

    def __init__(self, log_path: str = "sessions/trace.jsonl"):
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def span(self, name: str, parent_id: str | None = None) -> Generator[Span, None, None]:
        s = Span(name, parent_id, self)
        error = None
        try:
            yield s
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            s.end(status="error" if error else "ok", error=error)

    def _write(self, record: dict) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


**Usage pattern in `OllamaClient.chat()`:**

```python
with tracer.span("llm_call") as span:
    span.set("model", self.model)
    span.set("message_count", len(messages))
    response = self._do_chat(messages, system=system)
    span.set("response_tokens", len(response.split()))


---

### 4.11 CI/CD Headless Mode

**Goal:** Run a single task non-interactively (like `claude -p "task"`) from the command line or a CI pipeline, write results to stdout/file, and exit.

**Edit `main.py`** — add argument parsing:

```python
# main.py additions (add before the interactive loop)
import argparse
import sys

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ollama Multi-Agent Code Execution")
    p.add_argument("--task", "-t", help="Run a single task non-interactively and exit")
    p.add_argument("--output", "-o", help="Write result to this file (default: stdout)")
    p.add_argument("--model", "-m", default="glm4:9b", help="Ollama model to use")
    p.add_argument("--session", "-s", help="Resume an existing session ID")
    p.add_argument("--server", action="store_true", help="Start HTTP API server")
    p.add_argument("--port", type=int, default=8765, help="API server port")
    p.add_argument("--no-docker", action="store_true", help="Disable Docker sandbox, use subprocess")
    return p.parse_args()


# In main():
args = parse_args()

if args.task:
    # Headless single-task mode
    orchestrator = build_orchestrator(model=args.model, use_docker=not args.no_docker)
    result = orchestrator.run(args.task)
    output = str(result)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Result written to {args.output}")
    else:
        print(output)
    sys.exit(0)


**GitHub Actions example** (`.github/workflows/agent_task.yml`):

```yaml
name: Agent Task
on:
  workflow_dispatch:
    inputs:
      task:
        description: "Task for the agent"
        required: true

jobs:
  run-agent:
    runs-on: ubuntu-lates
    services:
      ollama:
        image: ollama/ollama
        ports: ["11434:11434"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -r requirements.tx
      - run: ollama pull glm4:9b
      - run: python main.py --task "${{ github.event.inputs.task }}" --no-docker --output result.tx
      - uses: actions/upload-artifact@v4
        with:
          name: agent-resul
          path: result.tx


---

### 4.12 Docker Compose Scaling

**Goal:** Run Ollama, the agent system, and optional services (ChromaDB, API gateway) together as a composable stack.

**New file:** `docker-compose.yml

```yaml
version: "3.9"

services:

  ollama:
    image: ollama/ollama:lates
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 10s
      retries: 5

  chromadb:
    image: chromadb/chroma:lates
    ports:
      - "8000:8000"
    volumes:
      - chroma_data:/chroma/chroma
    environment:
      ANONYMIZED_TELEMETRY: "false"
    profiles: ["vector"]   # only starts when --profile vector is passed

  agent:
    build: .
    depends_on:
      ollama:
        condition: service_healthy
    environment:
      OLLAMA_BASE_URL: "http://ollama:11434"
      OLLAMA_MODEL: "${OLLAMA_MODEL:-glm4:9b}"
      USE_VECTOR_MEMORY: "${USE_VECTOR_MEMORY:-false}"
    volumes:
      - ./sessions:/app/sessions
      - ./memory:/app/memory
    ports:
      - "8765:8765"
    command: ["python", "main.py", "--server"]

volumes:
  ollama_models:
  chroma_data:


**Dockerfile:**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.tx

COPY . .

# Non-root user for security
RUN useradd -m agentuser && chown -R agentuser /app
USER agentuser

EXPOSE 8765
CMD ["python", "main.py", "--server"]


**Run the full stack:**

```bash
# Standard stack (Ollama + Agent API):
docker compose up

# With vector memory (adds ChromaDB):
docker compose --profile vector up

# Pull the model on first run:
docker compose exec ollama ollama pull glm4:9b


---

## 5. Configuration Schema

All settings are loaded from `settings.yaml` in the project root. The system merges multiple files in priority order (later files override earlier ones):


settings.yaml                    ← committed project defaults
settings.local.yaml              ← local overrides (gitignored)
settings.managed.yaml            ← admin/org managed (highest priority)


**Full `settings.yaml` schema:**

```yaml
# settings.yaml — full reference

agent:
  model: glm4:9b                    # Ollama model name
  base_url: http://localhost:11434  # Ollama API endpoin
  max_debug_attempts: 3             # OrchestratorAgent retry limi
  max_turns: 20                     # STM window size

sandbox:
  enabled: true                     # false → subprocess fallback
  image: python:3.12-slim
  network: none
  memory: 256m
  cpus: 0.5
  timeout_seconds: 30
  workspace_dir: /workspace

memory:
  ltm_path: memory/ltm.json
  vector_enabled: false             # true → uses ChromaDB
  vector_dir: memory/vector_ltm
  agents_dir: memory/agents         # per-agent memory dirs

instructions:
  project_file: PROJECT.md
  rules_dir: .agent/rules

definitions:
  agents_dir: .agent/agents
  skills_dir: .agent/skills
  tools_dir: .agent/tools

permissions:
  deny:
    - pattern: "file:*.env"
      reason: "Environment files are protected"
    - pattern: "file:*.key"
      reason: "Private key files are protected"
    - pattern: "sandbox:rm -rf*"
      reason: "Destructive commands are blocked"
  ask:
    - pattern: "tool:execute_sql"
      reason: "SQL requires review"
  allow:
    - pattern: "tool:read_file"
    - pattern: "sandbox:python *"

server:
  enabled: false
  host: 127.0.0.1
  port: 8765
  cors_origins:
    - "http://localhost:3000"

logging:
  level: INFO                       # DEBUG | INFO | WARNING | ERROR
  trace_file: sessions/trace.jsonl  # set to null to disable
  session_dir: sessions/


**Config loader** (`src/core/config.py`):

```python
# src/core/config.py
from __future__ import annotations
from pathlib import Path
import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return resul


def load_config(project_root: str = ".") -> dict:
    root = Path(project_root)
    layers = ["settings.yaml", "settings.local.yaml", "settings.managed.yaml"]
    config: dict = {}
    for layer in layers:
        path = root / layer
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            config = _deep_merge(config, data)
    return config


---

## 6. API Reference for Extension Authors

### Extending `BaseAgen

```python
from src.agents.base_agent import BaseAgen

class MySpecialAgent(BaseAgent):
    AGENT_TYPE = "my_special"

    def __init__(self, llm_client, event_bus, hook_registry, memory_system, session):
        super().__init__(
            agent_id=f"my_special_{id(self)}",
            llm_client=llm_client,
            event_bus=event_bus,
            hook_registry=hook_registry,
            memory_system=memory_system,
            session=session,
        )

    def _get_system_prompt(self) -> str:
        return "You are a specialized agent that does X."

    def _execute(self, task: str) -> str:
        # 1. Use RALPH to reason about the task
        ralph_trace = self.ralph_engine.generate(task)
        # 2. Build messages
        messages = self._build_messages(task)
        # 3. Call LLM
        response = self.llm_client.chat(messages, system=self._get_system_prompt())
        # 4. Publish result even
        self.event_bus.publish("agent:complete", {"agent_id": self.agent_id, "result": response})
        return response


### Registering a Custom Hook

```python
from src.core.hook_registry import HookRegistry, HookType

registry = HookRegistry()

@registry.register(HookType.SANDBOX_PRE)
def my_safety_hook(payload: dict) -> dict | None:
    code = payload.get("code", "")
    if "os.system" in code:
        return {"decision": "deny", "reason": "os.system() is not allowed"}
    return None  # proceed


### Publishing a Custom Even

```python
event_bus.publish("my_namespace:my_event", {
    "agent_id": "coder_001",
    "custom_data": {"key": "value"},
})

# Subscribe elsewhere:
event_bus.subscribe("my_namespace:my_event", lambda payload: print(payload))


### Registering a Custom Tool

```python
from src.core.tool_registry import ToolRegistry, ToolDefinition

def web_search(query: str) -> str:
    import urllib.reques
    # ... implementation
    return results

registry = ToolRegistry()
registry.register(ToolDefinition(
    name="web_search",
    description="Search the web for factual information",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    handler=web_search,
    requires_permission=False,
    tags=["research", "web"],
))


---

## 7. Security Checklis

Security considerations for every extension. Review before deploying.

| Area | Risk | Mitigation |
|---|---|---|
| Sandbox | Code escape via Docker socket | Never mount `/var/run/docker.sock` into sandbox |
| Sandbox | Resource exhaustion | Keep `--memory 256m`, `--cpus 0.5`, add `--pids-limit 64` |
| Sandbox | Network exfiltration | Enforce `--network none`; whitelist only if required |
| LLM input | Prompt injection via task input | Validate and sanitize task strings; never interpolate raw user input into system prompts |
| File access | Path traversal | Use `pathlib.Path.resolve()` and check `.is_relative_to(root)` before every file read/write |
| API server | SSRF | Restrict CORS to `localhost`; add auth token for non-localhost access |
| Settings | Secret in YAML | Never commit `settings.local.yaml`; use env vars for secrets |
| Hook scripts | Shell injection | Pass data via JSON stdin, not shell arguments; avoid `$()` and string interpolation |
| Vector memory | Model poisoning | Validate importance scores; cap at `[0.0, 1.0]` |
| Dependencies | Supply chain | Pin versions in `requirements.txt`; run `pip-audit` in CI |

**OWASP Top 10 mitigations already present:**
- A01 (Broken Access Control) → `PermissionEngine` (§4.5)
- A03 (Injection) → Sandbox `--network none`, no shell-interpolated inputs
- A05 (Security Misconfiguration) → Settings hierarchy with managed overrides
- A09 (Logging Failures) → `TraceLogger` JSONL audit trail (§4.10)

---

## 8. Dependency Graph


main.py
├── config.py (load_config)
├── InstructionLoader        ← reads PROJECT.md, .agent/rules/
├── AgentDefinitionLoader    ← reads .agent/agents/*.md, .agent/skills/*.md
├── ToolRegistry             ← loads .agent/tools/*.yaml
├── PermissionEngine         ← evaluates allow/deny/ask rules
├── TraceLogger              ← writes sessions/trace.jsonl
├── MemorySystem
│   ├── STM (deque)
│   ├── LTM (JSON KV)  ←─ optionally replaced by VectorLTM (ChromaDB)
│   └── WorkingMemory
├── EventBus (pub/sub)
├── HookRegistry (all HookTypes)
├── AgentRegistry
├── SessionManager
├── OllamaClien
│   └── stream()             ← new streaming suppor
├── RalphEngine
├── SandboxRunner (Docker + subprocess fallback)
├── TaskDecomposer
└── Agents
    ├── OrchestratorAgent    ← uses all of the above
    ├── CoderAgen
    ├── ExecutorAgen
    ├── DebuggerAgen
    ├── EvaluatorAgen
    ├── ResearchAgen
    └── MemoryAgen


### Installation (adding new dependencies)

```bash
# Core additions
pip install pyyaml fastapi uvicorn pydantic

# Vector memory (optional)
pip install chromadb sentence-transformers

# Testing
pip install pytest pytest-asyncio httpx

# Security scanning
pip install pip-audi
pip-audi


**Updated `requirements.txt` additions:**


# --- existing ---
requests
# --- new additions ---
pyyaml>=6.0
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.0
# optional: vector memory
# chromadb>=0.5
# sentence-transformers>=3.0


---

*Last updated: generated from codebase exploration and Claude Code architecture research.*
*Build order recommendation: 4.1 → 4.2 → 4.5 → 4.3 → 4.4 → 4.8 → 4.6 → 4.7 → 4.9 → 4.10 → 4.11 → 4.12*
