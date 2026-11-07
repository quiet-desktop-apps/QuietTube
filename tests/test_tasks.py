import os
from pathlib import Path
import subprocess
import sys
import time

from quiettube.tasks import ExtractorTasks


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Background task did not complete")


def test_real_worker_reports_validation_error_without_network():
    results = []
    tasks = ExtractorTasks(results.append)
    try:
        tasks.submit({"kind": "home"})
        wait_for(lambda: bool(results))
        assert "Connect your YouTube account" in results[0].error
    finally:
        tasks.close()


def install_sleep_worker(monkeypatch, captures):
    real_popen = subprocess.Popen
    def popen(_, **kwargs):
        process = real_popen([sys.executable, "-c",
            "import os,time,pathlib; pathlib.Path(os.environ['TMPDIR'],'private-cookie').write_text('test'); time.sleep(60)"], **kwargs)
        captures.append((process, Path(kwargs["env"]["TMPDIR"])))
        return process
    monkeypatch.setattr("quiettube.tasks.subprocess.Popen", popen)


def test_timeout_kills_worker_and_removes_session_scratch(monkeypatch):
    results, captures = [], []
    install_sleep_worker(monkeypatch, captures)
    tasks = ExtractorTasks(results.append, timeout=0.15)
    tasks.submit({"kind": "search", "query": "test"})
    wait_for(lambda: bool(results))
    wait_for(lambda: not captures[0][1].exists())
    assert "too long" in results[0].error
    assert captures[0][0].poll() is not None
    tasks.close()


def test_cancel_suppresses_stale_result_and_reaps_worker(monkeypatch):
    results, captures = [], []
    install_sleep_worker(monkeypatch, captures)
    tasks = ExtractorTasks(results.append)
    tasks.submit({"kind": "home"})
    wait_for(lambda: bool(captures))
    tasks.cancel()
    assert not captures[0][1].exists()
    assert captures[0][0].poll() is not None
    assert results == []
    tasks.close()
