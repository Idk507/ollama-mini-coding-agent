"""
SandboxRunner — safe code execution via Docker container isolation.

Features:
  - One persistent named container per session (python:3.12-slim, no network)
  - Files written via `docker cp`, executed via `docker exec`
  - Configurable timeout enforced on docker exec calls
  - File operations: write, read, delete, list inside the container
  - Self-healing: restarts the container if it exits unexpectedly
  - Falls back to subprocess execution when Docker is unavailable
"""

import os
import subprocess
import sys
import tempfile
from typing import Tuple


class SandboxRunner:
    """Executes code in an isolated Docker container with timeout enforcement.

    Falls back transparently to subprocess-based execution when Docker is
    not available (so existing tests and offline usage continue to work).
    """

    _IMAGE = "python:3.12-slim"
    _WORKSPACE = "/workspace"

    def __init__(self, timeout: int = 30, session_id: str = "default"):
        self.timeout = timeout
        self._session_id = session_id
        self._container_name = f"ollama_sandbox_{session_id}"
        self._docker_available: bool = self._probe_docker()
        self._container_running: bool = False

    # ═══════════════════════════════════════════════ public lifecycle ══════

    def start(self) -> None:
        """Pull image if needed and start the persistent sandbox container."""
        if not self._docker_available:
            print(
                "  [Sandbox] Docker not available — using subprocess fallback."
            )
            return

        # Stop any stale container with the same name
        self._docker(["rm", "-f", self._container_name], check=False)

        _, err, rc = self._docker(
            [
                "run", "-d",
                "--name", self._container_name,
                "--network", "none",
                "--memory", "256m",
                "--cpus", "0.5",
                "--workdir", self._WORKSPACE,
                self._IMAGE,
                "sleep", "infinity",
            ]
        )
        if rc != 0:
            print(f"  [Sandbox] Warning: could not start Docker container: {err}")
            self._docker_available = False
            return

        self._container_running = True
        print(f"  [Sandbox] Docker container '{self._container_name}' started.")

    def stop(self) -> None:
        """Stop and remove the sandbox container."""
        if self._container_running:
            self._docker(["stop", self._container_name], check=False)
            self._container_running = False
            print(f"  [Sandbox] Docker container '{self._container_name}' stopped.")

    # ═══════════════════════════════════════════════ core execution ════════

    def execute(
        self, code: str, language: str = "python"
    ) -> Tuple[str, str, int]:
        """Run code and return (stdout, stderr, returncode).  0 = success."""
        if language != "python":
            return ("", f"Language '{language}' is not supported yet.", 1)

        if self._docker_available and self._container_running:
            return self._run_in_docker(code)
        return self._run_subprocess(code)

    # ═══════════════════════════════════════════════ file operations ═══════

    def write_file(self, path: str, content: str) -> Tuple[str, str, int]:
        """Write *content* to *path* inside the container (or local tmp dir)."""
        if self._docker_available and self._container_running:
            return self._docker_write_file(path, content)
        # Subprocess fallback: write to local CWD
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return ("", "", 0)
        except Exception as exc:
            return ("", str(exc), 1)

    def read_file(self, path: str) -> Tuple[str, str, int]:
        """Return the contents of *path* from the container."""
        if self._docker_available and self._container_running:
            return self._docker_exec(["cat", path])
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return (fh.read(), "", 0)
        except Exception as exc:
            return ("", str(exc), 1)

    def delete_file(self, path: str) -> Tuple[str, str, int]:
        """Remove *path* from the container."""
        if self._docker_available and self._container_running:
            return self._docker_exec(["rm", "-f", path])
        try:
            os.remove(path)
            return ("", "", 0)
        except Exception as exc:
            return ("", str(exc), 1)

    def list_files(self, directory: str = "/workspace") -> Tuple[str, str, int]:
        """List files in *directory* inside the container."""
        if self._docker_available and self._container_running:
            return self._docker_exec(["ls", "-la", directory])
        try:
            entries = os.listdir(directory if os.path.isabs(directory) else ".")
            return ("\n".join(entries), "", 0)
        except Exception as exc:
            return ("", str(exc), 1)

    # ═══════════════════════════════════════════════ internal helpers ══════

    def _probe_docker(self) -> bool:
        """Return True if Docker daemon is reachable."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _ensure_container(self) -> None:
        """Restart the container if it has exited unexpectedly."""
        if not self._container_running:
            return
        out, _, rc = self._docker(
            ["inspect", "--format={{.State.Running}}", self._container_name],
            check=False,
        )
        if rc != 0 or out.strip() != "true":
            print("  [Sandbox] Container not running — restarting …")
            self._container_running = False
            self.start()

    def _run_in_docker(self, code: str) -> Tuple[str, str, int]:
        """Copy code into container, execute, then remove the script."""
        self._ensure_container()
        if not self._container_running:
            return self._run_subprocess(code)

        tmp_host = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(code)
                tmp_host = fh.name

            remote_path = f"{self._WORKSPACE}/_run.py"

            # Copy script into container
            _, err, rc = self._docker(
                ["cp", tmp_host, f"{self._container_name}:{remote_path}"],
                check=False,
            )
            if rc != 0:
                return ("", f"docker cp failed: {err}", 1)

            # Execute
            stdout, stderr, returncode = self._docker_exec(
                ["python", remote_path]
            )

            # Cleanup
            self._docker_exec(["rm", "-f", remote_path])
            return stdout, stderr, returncode

        except Exception as exc:
            return ("", f"Docker execution error: {exc}", 1)
        finally:
            if tmp_host and os.path.exists(tmp_host):
                try:
                    os.unlink(tmp_host)
                except OSError:
                    pass

    def _docker_write_file(self, path: str, content: str) -> Tuple[str, str, int]:
        """Write content to path inside the container via docker cp."""
        tmp_host = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(content)
                tmp_host = fh.name

            # Ensure parent directory exists inside container
            parent = os.path.dirname(path) or self._WORKSPACE
            self._docker_exec(["mkdir", "-p", parent])

            _, err, rc = self._docker(
                ["cp", tmp_host, f"{self._container_name}:{path}"],
                check=False,
            )
            return ("", err, rc)
        except Exception as exc:
            return ("", str(exc), 1)
        finally:
            if tmp_host and os.path.exists(tmp_host):
                try:
                    os.unlink(tmp_host)
                except OSError:
                    pass

    def _docker_exec(self, cmd: list) -> Tuple[str, str, int]:
        """Run `docker exec <container> <cmd>` with timeout."""
        return self._docker(
            ["exec", self._container_name] + cmd,
            check=False,
        )

    def _docker(
        self, args: list, check: bool = False
    ) -> Tuple[str, str, int]:
        """Thin wrapper around subprocess for all docker calls."""
        try:
            result = subprocess.run(
                ["docker"] + args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if check and result.returncode != 0:
                raise RuntimeError(
                    f"docker {args[0]} failed: {result.stderr.strip()}"
                )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return ("", f"docker {args[0]} timed out after {self.timeout}s", 1)
        except FileNotFoundError:
            return ("", "docker command not found", 1)
        except Exception as exc:
            return ("", str(exc), 1)

    # ═══════════════════════════════════════════════ subprocess fallback ═══

    def _run_subprocess(self, code: str) -> Tuple[str, str, int]:
        """Original subprocess-based execution (Docker unavailable fallback)."""
        tmp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(code)
                tmp_file = fh.name

            result = subprocess.run(
                [sys.executable, tmp_file],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return result.stdout, result.stderr, result.returncode

        except subprocess.TimeoutExpired:
            return ("", f"Execution timed out after {self.timeout} seconds.", 1)
        except Exception as exc:
            return ("", f"Sandbox error: {exc}", 1)
        finally:
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass
