from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading


@dataclass(frozen=True)
class TaskResult:
    generation: int
    data: dict | None = None
    error: str = ""


class ExtractorTasks:
    """One worker at a time; cancellation kills extraction and its JS children."""

    def __init__(self, callback, timeout: float = 90):
        self.callback = callback
        self.timeout = timeout
        self.generation = 0
        self.process = None
        self.thread = None
        self.lock = threading.Lock()
        self.closed = False

    @staticmethod
    def _terminate(process):
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)

    def cancel(self):
        with self.lock:
            self.generation += 1
            self._terminate(self.process)
            self.process = None
            thread, self.thread = self.thread, None
        # Join after releasing the lock so the worker can finish its stale-result
        # check and remove all temporary session copies before shutdown returns.
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)

    def submit(self, request: dict) -> int:
        self.cancel()
        generation = self.generation
        if self.closed:
            return generation
        self.thread = threading.Thread(target=self._run, args=(generation, request), daemon=True)
        self.thread.start()
        return generation

    def _run(self, generation, request):
        # Disk-backed output prevents unexpected extractor output growing UI memory.
        with tempfile.TemporaryDirectory(prefix="quiettube-task-") as scratch, tempfile.TemporaryFile() as output:
            with self.lock:
                if generation != self.generation or self.closed:
                    return
                try:
                    process = subprocess.Popen(
                        [sys.executable, "-m", "quiettube.worker"], stdin=subprocess.PIPE,
                        stdout=output, stderr=subprocess.DEVNULL, start_new_session=True,
                        cwd=Path(__file__).resolve().parent.parent,
                        env={**os.environ, "TMPDIR": scratch},
                    )
                except OSError:
                    self.callback(TaskResult(generation, error="The YouTube worker could not start."))
                    return
                self.process = process
            error, data = "", None
            try:
                timeout = self.timeout
                if timeout == 90 and request.get("action") == "oauth_connect":
                    timeout = 330  # includes consent, keyring unlock and API validation
                elif timeout == 90 and request.get("account_mode") == "oauth":
                    timeout = 180  # bounded first subscription sync
                process.communicate(json.dumps(request).encode(), timeout=timeout)
                if process.returncode:
                    error = "The YouTube worker stopped unexpectedly. Please retry."
                elif output.tell() > 1024 * 1024:
                    error = "YouTube returned too much data. Refine your request."
                else:
                    output.seek(0)
                    data = json.load(output)
                    if not data.get("ok"):
                        error = data.get("error", "YouTube could not load this content.")
            except subprocess.TimeoutExpired:
                self._terminate(process)
                error = "YouTube took too long to respond. Check your connection and retry."
            except (ValueError, OSError):
                error = "Could not read the YouTube response. Please retry."
            with self.lock:
                if generation != self.generation or self.closed:
                    return
                self.process = None
            self.callback(TaskResult(generation, data, error))

    def close(self):
        self.closed = True
        self.cancel()
