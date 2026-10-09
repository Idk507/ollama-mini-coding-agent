"""
OrchestratorAgent — top-level planner implementing the full code pipeline.

Small tasks (single pipeline):
  User Request → RALPH → CoderAgent → ExecutorAgen
       ↓ (error)
  DebuggerAgent → patch → re-execute  (up to MAX_DEBUG_ATTEMPTS times)
       ↓ (pass)
  EvaluatorAgent → Memory write → Final outpu

Large tasks (subtask decomposition loop):
  User Request → RALPH → TaskDecomposer → [subtask1, subtask2, …]
  For each subtask (RALPH mode):
    feedback from prior iterations → CoderAgent → ExecutorAgen
       ↓ (error)
    DebuggerAgent loop
       ↓ (pass)
    EvaluatorAgent → accumulate results → pass feedback to next subtask
"""

from typing import Any, Dict, List, Optional

from .base_agent import BaseAgen
from .coder_agent import CoderAgen
from .debugger_agent import DebuggerAgen
from .demo_runner_agent import DemoRunnerAgen
from .evaluator_agent import EvaluatorAgen
from .executor_agent import ExecutorAgen
from ..core.task_decomposer import TaskDecomposer
from ..ui.terminal_ui import (
    print_task_banner,
    print_step,
    print_subtask_row,
    print_pipeline_summary,
)

MAX_DEBUG_ATTEMPTS = 3


class OrchestratorAgent(BaseAgent):
    """
    Coordinates all worker agents to fulfil a user task end-to-end.
    Supports both single-pipeline and multi-subtask decomposed execution.
    """

    def __init__(
        self,
        coder: CoderAgent,
        executor: ExecutorAgent,
        evaluator: EvaluatorAgent,
        debugger: DebuggerAgent,
        task_decomposer: TaskDecomposer,
        demo_runner: Optional["DemoRunnerAgent"] = None,
        *args,
        **kwargs,
    ):
        self._coder = coder
        self._executor = executor
        self._evaluator = evaluator
        self._debugger = debugger
        self._decomposer = task_decomposer
        self._demo_runner = demo_runner
        super().__init__("OrchestratorAgent", *args, **kwargs)

    # ─────────────────────────────────────────────────────── main entry ────

    def execute(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        ctx = context or {}

        # ── Step 1: RALPH reasoning on the full task ──────────────────────
        print_task_banner(task)
        ralph_trace = self._run_ralph(task, ctx)

        # ── Step 2: Decide single vs. decomposed ─────────────────────────
        if self._decomposer.should_decompose(task, ralph_trace):
            print_step("Large task detected — decomposing into subtasks", "info")
            subtasks = self._decomposer.decompose(task, ralph_trace)
            print_step(f"{len(subtasks)} subtask(s) identified", "ok")
            return self._run_subtask_loop(subtasks, task)

        # Small task — single pipeline
        return self._run_single_pipeline(task, ctx, subtask_id=None)

    # ─────────────────────────────────────────────────── subtask loop ─────

    def _run_subtask_loop(
        self, subtasks: List[Dict[str, Any]], original_task: str
    ) -> Dict[str, Any]:
        accumulated_context: Dict[str, Any] = {}
        results: List[Dict[str, Any]] = []

        for subtask in subtasks:
            sid = subtask["id"]
            description = subtask["description"]
            context_keys = subtask.get("context_keys", [])

            print_subtask_row(sid, len(subtasks), description, "running")

            # Build feedback from all previous iterations
            feedback = self._build_feedback(results)

            # Inject requested outputs from prior subtasks
            ctx: Dict[str, Any] = {
                "parent_task": original_task,
                "subtask_id": sid,
                "feedback": feedback,
            }
            for key in context_keys:
                if key in accumulated_context:
                    ctx[key] = accumulated_context[key]

            # Run the mini pipeline for this subtask
            result = self._run_single_pipeline(description, ctx, subtask_id=sid)
            result["subtask_id"] = sid

            # Store output for downstream subtasks
            accumulated_context[f"subtask_{sid}_output"] = resul
            results.append(result)

            # Update subtask row with final status
            exec_ok = result.get("execution", {}).get("success", False)
            debug_rounds = len(result.get("debug_attempts", []))
            print_subtask_row(
                sid, len(subtasks), description,
                "ok" if exec_ok else "err",
                attempts=debug_rounds,
            )

            # Hard-fail: stop loop if subtask exhausted all debug attempts
            if not exec_ok and debug_rounds >= MAX_DEBUG_ATTEMPTS:
                print_step(
                    f"Subtask {sid} failed after {MAX_DEBUG_ATTEMPTS} debug attempts — stopping",
                    "err",
                )
                break

        return {
            "task": original_task,
            "mode": "decomposed",
            "subtasks": results,
            "accumulated_context": accumulated_context,
            # Convenience: expose the last subtask's code/execution
            "final_code": (results[-1].get("final_code", "") if results else ""),
            "execution": (results[-1].get("execution", {}) if results else {}),
        }

    # ─────────────────────────────────────────────────── single pipeline ───

    def _run_single_pipeline(
        self,
        task: str,
        context: Dict[str, Any],
        subtask_id: Optional[int],
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "task": task,
            "subtask_id": subtask_id,
            "debug_attempts": [],
        }

        # ── Generate code ─────────────────────────────────────────────────
        label = f"subtask {subtask_id}" if subtask_id is not None else "task"
        print_step("Generating code", "running")
        code = self._coder.run(task, context)
        results["generated_code"] = code
        print_step("Code generated", "ok", f"{len(code.splitlines())} lines")

        # ── Execute ───────────────────────────────────────────────────────
        print_step("Executing code", "running")
        exec_ctx = dict(context)
        exec_ctx["code"] = code
        exec_ctx["language"] = "python"
        exec_result = self._executor.run(task, exec_ctx)
        results["execution"] = exec_resul

        if exec_result["success"]:
            print_step("Execution passed", "ok")
        else:
            print_step("Execution failed — entering debug loop", "warn")

        # ── Debug loop ────────────────────────────────────────────────────
        attempt = 0
        while not exec_result["success"] and attempt < MAX_DEBUG_ATTEMPTS:
            attempt += 1
            print_step(
                f"Debugger — attempt {attempt}/{MAX_DEBUG_ATTEMPTS}", "running"
            )
            debug_result = self._debugger.run(
                task, {"code": code, "error": exec_result["stderr"]}
            )
            code = debug_result.get("fixed_code", code)
            results["debug_attempts"].append(
                {
                    "attempt": attempt,
                    "explanation": debug_result.get("explanation", ""),
                    "fixed_code": code,
                }
            )

            print_step("Re-executing fixed code", "running")
            exec_ctx["code"] = code
            exec_result = self._executor.run(task, exec_ctx)
            results["execution"] = exec_resul

            if exec_result["success"]:
                print_step(f"Fixed on attempt {attempt}", "ok")
            elif attempt < MAX_DEBUG_ATTEMPTS:
                print_step("Still failing — retrying", "warn")
            else:
                print_step("Max debug attempts reached", "err")

        results["final_code"] = code

        # ── Evaluate (only on success) ────────────────────────────────────
        if exec_result["success"]:
            print_step("Evaluating code quality", "running")
            eval_result = self._evaluator.run(
                task, {"code": code, "execution_result": exec_result}
            )
            results["evaluation"] = eval_resul
            print_step("Evaluation complete", "ok")

        # ── Demo run (only on success) ─────────────────────────────────────
        if exec_result["success"] and self._demo_runner is not None:
            print_step("Running live demo with sample inputs", "running")
            demo_result = self._demo_runner.run(task, {"code": code})
            results["demo"] = demo_resul
            if demo_result.get("success"):
                print_step("Demo executed successfully", "ok")
            else:
                print_step("Demo run failed", "warn", demo_result.get("demo_error", "")[:60])

        # ── Persist to memory ─────────────────────────────────────────────
        self._memory.stm.add(
            "system", f"Completed {label}: {task[:80]}"
        )
        self._memory.ltm.write(
            topic="completed_task",
            value={
                "task": task,
                "subtask_id": subtask_id,
                "code": code,
                "success": exec_result["success"],
                "debug_rounds": attempt,
            },
            importance=0.7,
        )

        return results

    # ─────────────────────────────────────────────────── feedback builder ──

    @staticmethod
    def _build_feedback(results: List[Dict[str, Any]]) -> str:
        """Summarise all prior subtask results into a feedback string."""
        if not results:
            return ""
        lines: List[str] = ["Results from previous subtasks:"]
        for r in results:
            sid = r.get("subtask_id", "?")
            exec_info = r.get("execution", {})
            success = exec_info.get("success", False)
            status = "SUCCESS" if success else "FAILED"
            stdout = exec_info.get("stdout", "")[:300].strip()
            stderr = exec_info.get("stderr", "")[:300].strip()

            lines.append(f"\n[Subtask {sid}] Status: {status}")
            if stdout:
                lines.append(f"  Output: {stdout}")
            if not success and stderr:
                lines.append(f"  Error:  {stderr}")

            # Include evaluator feedback when available
            eval_feedback = (
                r.get("evaluation", {}).get("raw", "")[:200].strip()
            )
            if eval_feedback:
                lines.append(f"  Eval:   {eval_feedback}")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────── util ──────
