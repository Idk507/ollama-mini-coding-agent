# Multi-Agentic Code Builder & Executor

A fully local, offline-capable multi-agent system that takes a plain-English task description, generates Python code, executes it in a sandbox, self-debugs on failure, and evaluates the result — all powered by Ollama LLMs running on your machine.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [How To Run](#how-to-run)
6. [Interactive Commands](#interactive-commands)
7. [Pipeline Workflow](#pipeline-workflow)
8. [RALPH Reasoning](#ralph-reasoning)
9. [Recommended Models](#recommended-models)
10. [Project Structure](#project-structure)
11. [Configuration](#configuration)

---

## What It Does

You type a task like:

```
write a function to calculate fibonacci numbers
```

The system:
1. **Generates** Python code using an LLM (CoderAgent)
2. **Executes** the code safely in a subprocess sandbox (ExecutorAgent)
3. **Debugs** automatically if execution fails, up to 3 attempts (DebuggerAgent)
4. **Evaluates** the final code for correctness, efficiency, readability, and security (EvaluatorAgent)
5. **Persists** results to long-term memory for future sessions

All agents think using the **RALPH reasoning loop** (Reflect → Analyze → Learn → Plan → Hypothesize) before taking any action.

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Python      | 3.9+    |
| Ollama      | Latest  |
| requests    | ≥ 2.28.0 |

- **Ollama** must be installed and running: https://ollama.com/download  
- At least one local model must be pulled (see [Recommended Models](#recommended-models))

---

## Installation

### 1. Install Ollama

Download from https://ollama.com/download and install for your OS.

### 2. Pull a Model

```powershell
# Best quality (recommended)
ollama pull qwen2.5:3b

# Lightweight / fast (low memory)
ollama pull qwen2.5:0.5b
```

### 3. Install Python Dependencies

```powershell
cd ollama_code_execution
pip install -r requirements.txt
```

---

## Quick Start

```powershell
# Start Ollama (if not already running)
ollama serve

# Run with recommended model
python main.py --model qwen2.5:3b
```

You will see:

```
========================================================================
  Multi-Agentic Code Builder & Executor  |  RALPH Mode
  Powered by Ollama qwen2.5:3b
========================================================================

  Initialising system …
  Session ID : a1b2c3d4
  Ollama     : ONLINE  (model: qwen2.5:3b)

You: _
```

Type any coding task and press Enter.

---

## How To Run

### Interactive Mode (default)

```powershell
python main.py
```

Uses the default model (`glm4:9b`). If that model is not installed, the system automatically selects the best available local model.

### Specify a Model

```powershell
python main.py --model qwen2.5:3b
```

### Adjust LLM Timeout

```powershell
python main.py --model qwen2.5:3b --timeout 180
```

Default timeout is `120` seconds per LLM call.

### Piped / Non-Interactive Mode

```powershell
echo write a fibonacci function | python main.py --model qwen2.5:3b
```

Runs a single task and exits cleanly. Useful for scripting or CI.

### Run Offline Tests

```powershell
python test_offline.py
```

Validates all 8 core components without needing Ollama online.

---

## Interactive Commands

While in the REPL, these commands are available:

| Command | Description |
|---------|-------------|
| `<task description>` | Generate, execute, debug, and evaluate Python code |
| `/agents` | Live status dashboard of all agents |
| `/memory <query>` | Search long-term memory for past tasks |
| `/history` | Show recent conversation (short-term memory) |
| `/session` | Show current session summary (messages, artifacts, events) |
| `/save` | Persist the current session to disk |
| `/model <name>` | Switch to a different Ollama model mid-session |
| `/help` | Show this command list |
| `/quit` or `/exit` | Save session and exit |

---

## Pipeline Workflow

```
User Input
    │
    ▼
┌─────────────────────────────────────┐
│  OrchestratorAgent                  │
│  (RALPH reasoning first)            │
│                                     │
│  Step 1: CoderAgent                 │
│    └─ Generate Python code via LLM  │
│                                     │
│  Step 2: ExecutorAgent              │
│    └─ Run code in subprocess sandbox│
│                                     │
│  Step 3: DebuggerAgent (if failed)  │
│    └─ LLM diagnoses + patches code  │
│    └─ Re-execute (up to 3 attempts) │
│                                     │
│  Step 4: EvaluatorAgent (if success)│
│    └─ Score quality 1–10 per metric │
│                                     │
│  Step 5: Memory write               │
│    └─ Persist task + code to LTM    │
└─────────────────────────────────────┘
    │
    ▼
Terminal Output
  ▶ Final Code
  ▶ Execution result (stdout / stderr)
  ▶ Code Evaluation scores
```

### Example Run

```
You: write a function to sort a list of numbers

  Running pipeline …
  [Orchestrator] → CoderAgent: generating code …
  [Orchestrator] → ExecutorAgent: running code …
  [Orchestrator] → EvaluatorAgent: scoring code …

▶ Final Code
  def sort_numbers(numbers):
      return sorted(numbers)

  print(sort_numbers([3, 1, 4, 1, 5, 9, 2, 6]))

  Execution: SUCCESS  (exit code 0)
  STDOUT: [1, 1, 2, 3, 4, 5, 6, 9]

▶ Code Evaluation
  Correctness    10/10
  Efficiency      9/10
  Readability    10/10
  Security        9/10
  Overall        10/10
  Suggestions:
  - Add input validation for non-list inputs
```

---

## RALPH Reasoning

Every agent runs **RALPH** before acting. This is a 5-phase internal reasoning trace:

| Phase | What the agent does |
|-------|---------------------|
| **R**eflect | Recalls past experience with this type of task |
| **A**nalyze | Breaks the problem into sub-tasks, identifies risks |
| **L**earn | Applies relevant knowledge and patterns |
| **P**lan | Creates a step-by-step execution plan |
| **H**ypothesize | Predicts outcome and defines success criteria |

The trace is stored in the session log and viewable via `/session`. It makes the system transparent and auditable — you can see exactly why an agent made a given decision.

---

## Recommended Models

| Model | Size | Quality | Speed | Command |
|-------|------|---------|-------|---------|
| `qwen2.5:3b` | 1.9 GB | ★★★★ | Fast | `ollama pull qwen2.5:3b` |
| `qwen2.5:0.5b` | 397 MB | ★★ | Very fast | `ollama pull qwen2.5:0.5b` |
| `llama3.2:3b` | 2.0 GB | ★★★★ | Fast | `ollama pull llama3.2:3b` |
| `deepseek-coder:6.7b` | 3.8 GB | ★★★★★ | Moderate | `ollama pull deepseek-coder:6.7b` |

`qwen2.5:3b` is the recommended default — it reliably follows structured prompts (including the evaluation score format) and runs on most consumer hardware.

Switch models at runtime without restarting:

```
You: /model qwen2.5:3b
```

---

## Project Structure

```
ollama_code_execution/
├── main.py                    ← Entry point / REPL
├── requirements.txt           ← Python dependencies
├── test_offline.py            ← Unit tests (no Ollama needed)
├── copilot.md                 ← Original design specification
│
├── src/
│   ├── core/
│   │   ├── llm_client.py      ← Ollama HTTP client
│   │   ├── ralph_engine.py    ← RALPH reasoning loop
│   │   ├── sandbox_runner.py  ← Subprocess code execution
│   │   ├── memory_system.py   ← STM + LTM + WorkingMemory
│   │   ├── event_bus.py       ← Pub/sub event system
│   │   ├── hook_registry.py   ← Lifecycle hooks
│   │   ├── agent_registry.py  ← Agent lifecycle management
│   │   └── session_manager.py ← Session persistence
│   │
│   ├── agents/
│   │   ├── base_agent.py      ← Abstract base (RALPH + lifecycle)
│   │   ├── orchestrator_agent.py ← Pipeline coordinator
│   │   ├── coder_agent.py     ← Code generation
│   │   ├── executor_agent.py  ← Code execution
│   │   ├── debugger_agent.py  ← Error diagnosis + patching
│   │   ├── evaluator_agent.py ← Code quality scoring
│   │   ├── research_agent.py  ← LTM-backed research
│   │   └── memory_agent.py    ← Memory read/write/search
│   │
│   └── ui/
│       └── terminal_ui.py     ← ANSI colour terminal output
│
├── sessions/                  ← JSON session files (auto-created)
└── memory/
    └── ltm.json               ← Long-term memory store (auto-created)
```

---

## Configuration

All configuration is passed via CLI arguments. There is no config file.

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `glm4:9b` | Ollama model name. Auto-selects best local model if not found. |
| `--timeout` | `120` | Seconds to wait for each LLM response. |

The sandbox execution timeout is fixed at **30 seconds** per code run (configurable in `SandboxRunner`).

Memory is stored in:
- `memory/ltm.json` — long-term memory (persists across sessions)
- `sessions/<id>.json` — per-session audit trail
