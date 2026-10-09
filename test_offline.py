"""Offline functional tests — no Ollama required."""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_sandbox():
    from src.core.sandbox_runner import SandboxRunner

    sb = SandboxRunner(timeout=10)

    stdout, stderr, rc = sb.execute("print('hello from sandbox')", "python")
    assert rc == 0 and "hello" in stdout, f"FAIL basic exec: rc={rc} err={stderr}"
    print("[OK] Sandbox: basic execution")

    stdout2, stderr2, rc2 = sb.execute("1/0", "python")
    assert rc2 != 0 and "ZeroDivisionError" in stderr2, f"FAIL error capture: rc={rc2}"
    print("[OK] Sandbox: error capture")


def test_event_bus():
    from src.core.event_bus import EventBus

    eb = EventBus()
    received = []
    eb.subscribe("test:evt", lambda t, d: received.append(d))
    eb.publish("test:evt", {"val": 42})
    assert received == [{"val": 42}], f"FAIL: {received}"
    print("[OK] EventBus")
    return eb


def test_memory():
    from src.core.memory_system import MemorySystem

    mem = MemorySystem(session_id="test-session", storage_dir="_test_mem")

    mem.stm.add("user", "hello world")
    recent = mem.stm.get_recent(5)
    assert any("hello world" in str(r) for r in recent), f"FAIL STM: {recent}"

    key = mem.ltm.write("pytest", "test value", importance=0.9)
    val = mem.ltm.read(key)
    assert val == "test value", f"FAIL LTM read: {val}"

    hits = mem.ltm.search("pytest")
    assert len(hits) > 0, f"FAIL LTM search"
    print("[OK] Memory STM + LTM")
    return mem


def test_agent_lifecycle(eb, mem):
    from src.core.hook_registry import HookRegistry
    from src.core.ralph_engine import RalphEngine
    from src.core.llm_client import OllamaClient
    from src.core.sandbox_runner import SandboxRunner
    from src.agents.executor_agent import ExecutorAgent
    from src.core.agent_registry import AgentStatus

    llm = OllamaClient()
    ralph = RalphEngine(llm)
    hreg = HookRegistry()

    exec_agent = ExecutorAgent(SandboxRunner(10), llm, eb, hreg, mem, ralph)
    assert exec_agent.status == AgentStatus.IDLE, f"FAIL: {exec_agent.status}"
    print("[OK] Agent instantiation + IDLE state")

    # Call execute() directly (bypasses RALPH so no LLM needed)
    result = exec_agent.execute("run code", {"code": "print(2+2)", "language": "python"})
    assert result["success"] and "4" in result["stdout"], f"FAIL exec: {result}"
    print("[OK] ExecutorAgent.execute() direct")


def test_hook_registry():
    from src.core.hook_registry import HookRegistry, HookType

    reg = HookRegistry()
    side = []
    reg.register(HookType.PRE_LLM_CALL, lambda *a, **kw: side.append(1))
    reg.execute(HookType.PRE_LLM_CALL, "agent", "prompt")
    assert side == [1], f"FAIL: {side}"
    print("[OK] HookRegistry")


def test_session():
    from src.core.session_manager import SessionManager

    sm = SessionManager(storage_dir="_test_sessions")
    s = sm.create_session()
    s.add_message("user", "hello")
    s.add_code_artifact("print(1)", "python", "test")
    ok = sm.save_session(s.session_id)
    assert ok, "FAIL: save returned False"
    loaded = sm.load_session(s.session_id)
    assert loaded is not None, "FAIL: load returned None"
    assert len(loaded.messages) == 1, f"FAIL msg count: {len(loaded.messages)}"
    print("[OK] Session persistence")
    shutil.rmtree("_test_sessions", ignore_errors=True)


if __name__ == "__main__":
    try:
        test_sandbox()
        eb = test_event_bus()
        mem = test_memory()
        test_agent_lifecycle(eb, mem)
        test_hook_registry()
        test_session()
        print()
        print("ALL TESTS PASSED")
    finally:
        shutil.rmtree("_test_mem", ignore_errors=True)
