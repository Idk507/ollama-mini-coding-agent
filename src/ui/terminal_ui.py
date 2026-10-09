"""
terminal_ui.py — clean, structured terminal output for the multi-agent system.

All print helpers live here so orchestrator / main stay logic-only.
"""

import os
import textwrap
from typing import Any, Dict, List, Optional

# ── ANSI colours ──────────────────────────────────────────────────────────────
_RESET   = "\033[0m"
_BOLD    = "\033[1m"
_DIM     = "\033[2m"
_GREEN   = "\033[32m"
_RED     = "\033[31m"
_YELLOW  = "\033[33m"
_CYAN    = "\033[36m"
_MAGENTA = "\033[35m"
_BLUE    = "\033[34m"
_WHITE   = "\033[37m"

_W = 70   # column width


def _c(text: str, *codes: str) -> str:
    return "".join(codes) + str(text) + _RESET


# backward-compat alias used by main.py
def _colored(text: str, *codes: str) -> str:  # noqa: N802
    return _c(text, *codes)


def _hr(char: str = "─", color: str = _DIM) -> None:
    print(_c(char * _W, color))


# ── Header / Banner ───────────────────────────────────────────────────────────

def print_header() -> None:
    model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    print()
    _hr("═", _CYAN)
    print(_c("  Multi-Agent Code Builder & Executor  |  RALPH Mode", _BOLD + _CYAN))
    print(_c(f"  Powered by Ollama  ·  model: {model}", _DIM))
    _hr("═", _CYAN)
    print()


def print_task_banner(task: str) -> None:
    """Highlight the user task before the pipeline starts."""
    print()
    _hr("┄", _CYAN)
    label = _c("  Task  ", _BOLD + _CYAN)
    wrapped = textwrap.wrap(task, width=_W - 10)
    print(f"{label}{wrapped[0]}")
    for line in wrapped[1:]:
        print(f"          {line}")
    _hr("┄", _CYAN)
    print()


# ── Pipeline step tracker ─────────────────────────────────────────────────────

_ICONS = {
    "running": _c(" ▸ ", _YELLOW + _BOLD),
    "ok":      _c(" ✔ ", _GREEN  + _BOLD),
    "err":     _c(" ✘ ", _RED    + _BOLD),
    "warn":    _c(" ⚠ ", _YELLOW + _BOLD),
    "info":    _c(" ℹ ", _CYAN   + _BOLD),
    "skip":    _c(" ─ ", _DIM),
}


def print_step(label: str, status: str = "running", detail: str = "") -> None:
    """Print a single pipeline step line.

    status: running | ok | err | warn | info | skip
    """
    icon = _ICONS.get(status, _ICONS["info"])
    suffix = f"  {_c(detail, _DIM)}" if detail else ""
    print(f"  {icon}{label}{suffix}")


def print_subtask_row(sid: int, total: int, desc: str, status: str, attempts: int = 0) -> None:
    """Print a subtask progress row inside the decomposed pipeline."""
    icon = _ICONS.get(status, _ICONS["info"])
    badge = _c(f"[{sid}/{total}]", _DIM)
    short = (desc[:48] + "…") if len(desc) > 49 else desc
    attempt_str = ""
    if attempts > 0:
        word = "round" if attempts == 1 else "rounds"
        attempt_str = _c(f"  ({attempts} debug {word})", _YELLOW + _DIM)
    print(f"  {icon}{badge} {short}{attempt_str}")


# ── Code box ──────────────────────────────────────────────────────────────────

def print_code(code: str, title: str = "Generated Code") -> None:
    """Print code in a tidy labelled box."""
    if not code:
        return
    print()
    top    = "┌─ " + _c(title, _BOLD + _CYAN) + " " + _c("─" * max(0, _W - len(title) - 4), _DIM)
    bottom = _c("└" + "─" * (_W - 1), _DIM)
    print(top)
    for line in code.splitlines():
        print(_c("│ ", _DIM) + _c(line, _CYAN))
    print(bottom)


# ── Demo output ───────────────────────────────────────────────────────────────

def print_demo_output(demo_output: str, success: bool = True, error: str = "") -> None:
    """Print the demo run output in a highlighted box."""
    print()
    title = "Demo Output"
    top    = "┌─ " + _c(title, _BOLD + _GREEN) + " " + _c("─" * max(0, _W - len(title) - 4), _DIM)
    bottom = _c("└" + "─" * (_W - 1), _DIM)
    print(top)
    if demo_output:
        for line in demo_output.splitlines():
            print(_c("│ ", _DIM) + line)
    if not success and error:
        print(_c("│ ", _DIM) + _c("[Demo failed — stderr]", _RED))
        for line in error.splitlines()[:6]:
            print(_c("│   ", _DIM) + _c(line, _RED + _DIM))
    if not demo_output and not error:
        print(_c("│  (no output produced)", _DIM))
    print(bottom)


# ── Execution result ──────────────────────────────────────────────────────────

def print_execution_result(result: Dict[str, Any]) -> None:
    if not result:
        return
    ok       = result.get("success", False)
    code_str = result.get("returncode", "?")
    status   = _c("PASSED", _GREEN + _BOLD) if ok else _c("FAILED", _RED + _BOLD)
    print(f"\n  Execution  {status}  (exit {code_str})")

    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()

    if stdout:
        print(_c("  ┌ stdout " + "─" * (_W - 9), _GREEN + _DIM))
        for line in stdout.splitlines()[:20]:
            print(f"  │ {line}")
        if len(stdout.splitlines()) > 20:
            print(_c(f"  │ … ({len(stdout.splitlines()) - 20} more lines)", _DIM))
        print(_c("  └" + "─" * (_W - 2), _DIM))

    if not ok and stderr:
        print(_c("  ┌ stderr " + "─" * (_W - 9), _RED + _DIM))
        for line in stderr.splitlines()[:15]:
            print(f"  │ {_c(line, _RED + _DIM)}")
        print(_c("  └" + "─" * (_W - 2), _DIM))


# ── Evaluation scores ─────────────────────────────────────────────────────────

def print_evaluation(eval_result: Dict[str, Any]) -> None:
    if not eval_result:
        return
    print()
    top    = "┌─ " + _c("Evaluation", _BOLD + _MAGENTA) + " " + _c("─" * (_W - 14), _DIM)
    bottom = _c("└" + "─" * (_W - 1), _DIM)
    print(top)
    scores = eval_result.get("scores", {})
    if scores:
        for key in ("correctness", "efficiency", "readability", "security", "overall"):
            val = scores.get(key)
            if val is None:
                continue
            bar_len = int(val)
            color = _GREEN if val >= 7 else _YELLOW if val >= 4 else _RED
            bar = _c("█" * bar_len + "░" * (10 - bar_len), color)
            print(f"  │  {key.capitalize():<14} {bar}  {_c(str(val) + '/10', color + _BOLD)}")
        suggestions = scores.get("suggestions", "")
        if suggestions:
            print(_c("  │", _DIM))
            print(f"  │  {_c('Suggestions:', _BOLD)}")
            for line in suggestions.splitlines():
                s = line.strip()
                if s:
                    print(f"  │    {_c(s, _DIM)}")
    else:
        raw = eval_result.get("raw", "")[:500]
        for line in raw.splitlines():
            print(f"  │  {line}")
    print(bottom)


# ── Pipeline summary ──────────────────────────────────────────────────────────

def print_pipeline_summary(success: bool, debug_rounds: int, has_demo: bool) -> None:
    """One-line result summary at the end of a pipeline run."""
    print()
    _hr("─", _DIM)
    if success:
        msg = _c("  Pipeline complete", _GREEN + _BOLD)
    else:
        msg = _c("  Pipeline ended with errors", _RED + _BOLD)
    extras = []
    if debug_rounds:
        word = "round" if debug_rounds == 1 else "rounds"
        extras.append(_c(f"{debug_rounds} debug {word}", _YELLOW))
    if has_demo:
        extras.append(_c("demo output shown above", _CYAN + _DIM))
    extra_str = ("  │  " + "  ·  ".join(extras)) if extras else ""
    print(msg + extra_str)
    _hr("─", _DIM)
    print()


# ── Agent dashboard ───────────────────────────────────────────────────────────

def print_agent_dashboard(agents: List[Any]) -> None:
    print()
    top    = "┌─ " + _c("Agent Dashboard", _BOLD + _CYAN) + " " + _c("─" * (_W - 18), _DIM)
    bottom = _c("└" + "─" * (_W - 1), _DIM)
    print(top)
    icons = {
        "IDLE":        _c("●", _GREEN),
        "RUNNING":     _c("▶", _YELLOW),
        "SUCCESS":     _c("✔", _GREEN),
        "FAILED":      _c("✘", _RED),
        "PAUSED":      _c("‖", _YELLOW),
        "TERMINATED":  _c("○", _DIM),
        "INITIALIZED": _c("◌", _CYAN),
        "CREATED":     _c("◌", _DIM),
    }
    for agent in agents:
        sv   = agent.status.value
        icon = icons.get(sv, "?")
        print(f"  │  {icon}  {agent.agent_id:<38} [{_c(sv, _DIM)}]")
    print(bottom)


# ── Memory ────────────────────────────────────────────────────────────────────

def print_memory_results(results: List[Dict]) -> None:
    if not results:
        print(_c("  (no results found)", _DIM))
        return
    print()
    for item in results[:8]:
        topic = _c(item.get("topic", "?"), _CYAN)
        val   = str(item.get("value", ""))[:80]
        imp   = item.get("importance", 0)
        print(f"  [{topic}]  {val}  {_c(f'imp={imp:.1f}', _DIM)}")


# ── Help ──────────────────────────────────────────────────────────────────────

def print_help() -> None:
    print()
    _hr("─", _DIM)
    print(_c("  Available Commands", _BOLD + _WHITE))
    _hr("─", _DIM)
    cmds = [
        ("<task description>",  "Build, run, demo, and evaluate Python code"),
        ("/agents",             "Live agent status dashboard"),
        ("/memory <query>",     "Search long-term memory"),
        ("/history",            "Recent conversation (STM)"),
        ("/session",            "Current session summary"),
        ("/save",               "Persist session to disk"),
        ("/model <name>",       "Switch Ollama model at runtime"),
        ("/research <topic>",   "One-shot research lookup"),
        ("/help",               "Show this help"),
        ("/quit  /q",           "Save session and exit"),
    ]
    for cmd, desc in cmds:
        print(f"  {_c(cmd, _CYAN + _BOLD):<42} {_c(desc, _DIM)}")
    _hr("─", _DIM)
    print()


# ── Misc (kept for backward compatibility) ────────────────────────────────────

def print_separator(char: str = "─") -> None:
    _hr(char, _DIM)


def print_section(title: str) -> None:
    print(f"\n{_c('▶ ' + title, _BOLD + _YELLOW)}")
    _hr("─", _DIM)


def print_ralph_trace(trace: Dict[str, str], agent_name: str) -> None:
    """Verbose/debug only — kept for compatibility."""
    print(_c(f"\n  [RALPH — {agent_name}]", _MAGENTA))
    for phase in ("REFLECT", "ANALYZE", "LEARN", "PLAN", "HYPOTHESIZE"):
        content = trace.get(phase, "")
        if content:
            snippet = content[:100].replace("\n", " ")
            print(f"    {_c(phase + ':', _BOLD)} {snippet}")
