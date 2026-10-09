#!/usr/bin/env python3
"""
main.py — Multi-Agentic Code Builder & Executor System entry point.

Usage:
    python main.py [--model MODEL] [--timeout SECONDS]

Example:
    python main.py
    python main.py --model llama3:8b
"""

import argparse
import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.event_bus import EventBus
from src.core.hook_registry import HookRegistry, HookType
from src.core.agent_registry import AgentRegistry
from src.core.session_manager import SessionManager
from src.core.memory_system import MemorySystem
from src.core.ralph_engine import RalphEngine
from src.core.sandbox_runner import SandboxRunner
from src.core.task_decomposer import TaskDecomposer
from src.core.llm_client import OllamaClient

from src.agents.coder_agent import CoderAgent
from src.agents.executor_agent import ExecutorAgent
from src.agents.evaluator_agent import EvaluatorAgent
from src.agents.debugger_agent import DebuggerAgent
from src.agents.demo_runner_agent import DemoRunnerAgent
from src.agents.research_agent import ResearchAgent
from src.agents.memory_agent import MemoryAgent
from src.agents.orchestrator_agent import OrchestratorAgent

from src.ui.terminal_ui import (
    print_header,
    print_separator,
    print_code,
    print_execution_result,
    print_ralph_trace,
    print_evaluation,
    print_agent_dashboard,
    print_memory_results,
    print_help,
    print_section,
    print_demo_output,
    print_pipeline_summary,
    _colored,
    _BOLD,
    _GREEN,
    _YELLOW,
    _RED,
    _CYAN,
    _DIM,
)


# ──────────────────────────────────────────────────────── docker availability ──

def _check_docker() -> bool:
    """Return True when Docker daemon is reachable; print a warning otherwise."""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5
        )
        if result.returncode == 0:
            print("  Docker     : ONLINE")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    print(
        "  Docker     : OFFLINE\n"
        "  Sandbox will fall back to subprocess execution.\n"
        "  Install Docker and start the daemon for full isolation."
    )
    return False


# ─────────────────────────────────────────────────────────── event logging ──

def _setup_event_logging(event_bus: EventBus, session) -> None:
    """Wire EventBus events into the session audit trail."""

    def _on_event(event_type: str, data) -> None:
        session.add_event(event_type, data)

    for evt in [
        "agent:spawn", "agent:start", "agent:complete", "agent:error",
        "agent:ralph", "agent:status",
        "sandbox:execute", "sandbox:result",
        "memory:read", "memory:write",
    ]:
        event_bus.subscribe(evt, _on_event)


def _setup_default_hooks(hook_registry: HookRegistry) -> None:
    """Register built-in hooks (logging only; non-destructive)."""

    def _log_pre_llm(agent, prompt: str):
        # Trim prompt in the log to avoid flooding the terminal
        snippet = (prompt or "")[:60].replace("\n", " ")
        print(_colored(f"  [Hook:pre_llm] {agent} → {snippet}…", _DIM), flush=True)

    hook_registry.register(HookType.PRE_LLM_CALL, _log_pre_llm)


# ─────────────────────────────────────────────────────────────── bootstrap ──

def _bootstrap(model: str, timeout: int):
    """Instantiate and wire all system components."""

    # Core infrastructure
    event_bus = EventBus()
    hook_registry = HookRegistry()
    session_manager = SessionManager(storage_dir="sessions")
    session = session_manager.create_session()

    # LLM client
    llm = OllamaClient(model=model, timeout=timeout)

    # Memory, sandbox, RALPH
    memory = MemorySystem(session_id=session.session_id, storage_dir="memory")
    sandbox = SandboxRunner(timeout=30, session_id=session.session_id)
    sandbox.start()   # pull image + launch container (no-op if Docker absent)
    ralph = RalphEngine(llm)

    # Common constructor args for all agents
    agent_args = (llm, event_bus, hook_registry, memory, ralph)

    # Task decomposer
    decomposer = TaskDecomposer(llm)

    # Instantiate agents
    coder = CoderAgent(*agent_args)
    executor = ExecutorAgent(sandbox, *agent_args)
    evaluator = EvaluatorAgent(*agent_args)
    debugger = DebuggerAgent(*agent_args)
    researcher = ResearchAgent(*agent_args)
    mem_agent = MemoryAgent(*agent_args)
    demo_runner = DemoRunnerAgent(sandbox, *agent_args)
    orchestrator = OrchestratorAgent(
        coder, executor, evaluator, debugger, decomposer, demo_runner, *agent_args
    )

    # Registry
    agent_registry = AgentRegistry(event_bus)
    for agent in [coder, executor, evaluator, debugger, researcher, mem_agent, demo_runner, orchestrator]:
        agent_registry.register(agent)

    # Wiring
    _setup_event_logging(event_bus, session)
    _setup_default_hooks(hook_registry)

    return {
        "llm": llm,
        "session": session,
        "session_manager": session_manager,
        "memory": memory,
        "agent_registry": agent_registry,
        "orchestrator": orchestrator,
        "mem_agent": mem_agent,
        "researcher": researcher,
        "sandbox": sandbox,
    }


# ─────────────────────────────────────────────────────────────────── main ──

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-Agentic Code Builder & Executor (RALPH Mode)"
    )
    parser.add_argument(
        "--model", default=OllamaClient.DEFAULT_MODEL,
        help=f"Ollama model name (default: {OllamaClient.DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--timeout", type=int, default=120,
        help="LLM request timeout in seconds (default: 120)"
    )
    args = parser.parse_args()

    print_header()

    # ── Initialise ─────────────────────────────────────────────────────────
    print(f"\n  Initialising system …")
    _check_docker()
    components = _bootstrap(args.model, args.timeout)

    llm: OllamaClient = components["llm"]
    session = components["session"]
    session_manager: SessionManager = components["session_manager"]
    agent_registry: AgentRegistry = components["agent_registry"]
    orchestrator: OrchestratorAgent = components["orchestrator"]
    mem_agent: MemoryAgent = components["mem_agent"]
    researcher: ResearchAgent = components["researcher"]

    print(f"  Session ID : {_colored(session.session_id, _CYAN)}")

    # ── Ollama connectivity check ──────────────────────────────────────────
    if llm.is_available():
        models = llm.list_models()
        if models and llm.model not in models:
            best = llm.select_best_model()
            print(
                f"  {_colored('WARNING', _YELLOW)}: model '{llm.model}' not found. "
                f"Switching to '{best}'."
            )
            llm.model = best
        print(f"  Ollama     : {_colored('ONLINE', _GREEN)}  (model: {llm.model})")
    else:
        print(
            f"  Ollama     : {_colored('OFFLINE', _RED)}\n"
            f"  {_colored('Run: ollama serve', _YELLOW)} — then retry.\n"
            f"  Continuing in degraded mode (LLM calls will return error messages)."
        )

    print()
    print_help()

    # ── REPL ───────────────────────────────────────────────────────────────
    # Detect if running with piped stdin (non-interactive mode)
    _is_piped = not sys.stdin.isatty()

    while True:
        try:
            user_input = input(_colored("You: ", _BOLD + _GREEN)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            # In piped/non-interactive mode, empty line signals end of input
            if _is_piped:
                break
            continue

        # ── Built-in commands ──────────────────────────────────────────────
        if user_input in ("/quit", "/exit", "/q"):
            session_manager.save_session(session.session_id)
            components["sandbox"].stop()
            print(f"  Session saved. Goodbye!")
            break

        if user_input in ("/help", "/?"):
            print_help()
            continue

        if user_input == "/agents":
            print_agent_dashboard(agent_registry.list_agents())
            continue

        if user_input == "/session":
            print_section("Session Summary")
            print(f"    ID        : {session.session_id}")
            print(f"    Messages  : {len(session.messages)}")
            print(f"    Artifacts : {len(session.code_artifacts)}")
            print(f"    Events    : {len(session.events)}")
            print(f"    RALPH traces: {len(session.ralph_traces)}")
            continue

        if user_input == "/save":
            ok = session_manager.save_session(session.session_id)
            msg = "saved" if ok else "save FAILED"
            print(f"  Session {msg}: {session.session_id}")
            continue

        if user_input == "/history":
            recent = components["memory"].stm.get_recent(10)
            print_section("Recent Conversation (STM)")
            for entry in recent:
                role_str = _colored(entry["role"].upper(), _CYAN)
                print(f"    [{role_str}] {entry['content'][:120]}")
            continue

        if user_input.startswith("/model "):
            new_model = user_input[7:].strip()
            llm.model = new_model
            print(f"  Model switched to: {_colored(new_model, _CYAN)}")
            continue

        if user_input.startswith("/memory"):
            query = user_input[7:].strip() or "task"
            print_section(f"Memory Search: '{query}'")
            results = mem_agent.run(query, {"operation": "search", "query": query})
            print_memory_results(results or [])
            continue

        if user_input.startswith("/research "):
            topic = user_input[10:].strip()
            print_section(f"Research: {topic}")
            result = researcher.run(topic)
            print(result.get("answer", "No answer returned."))
            continue

        # ── Task → full pipeline ───────────────────────────────────────────
        session.add_message("user", user_input)
        components["memory"].stm.add("user", user_input)

        try:
            results = orchestrator.run(user_input)
        except Exception as exc:
            print(_colored(f"\n  [PIPELINE ERROR] {exc}", _RED))
            session.add_event("pipeline:error", str(exc))
            continue

        # ── Display results ────────────────────────────────────────────────
        final_code = results.get("final_code", results.get("generated_code", ""))
        if final_code:
            print_code(final_code, "Final Code")

        exec_result = results.get("execution", {})
        print_execution_result(exec_result)

        # Demo output
        demo = results.get("demo", {})
        if demo:
            print_demo_output(
                demo.get("demo_output", ""),
                success=demo.get("success", False),
                error=demo.get("demo_error", ""),
            )

        if results.get("evaluation"):
            print_evaluation(results["evaluation"])

        debug_attempts: list = results.get("debug_attempts", [])
        print_pipeline_summary(
            success=exec_result.get("success", False),
            debug_rounds=len(debug_attempts),
            has_demo=bool(demo.get("demo_output")),
        )

        # Persist code artifact
        if final_code:
            session.add_code_artifact(final_code, "python", user_input[:100])

        session.add_message(
            "assistant",
            f"Pipeline complete. Success={exec_result.get('success', False)}",
        )


if __name__ == "__main__":
    main()
