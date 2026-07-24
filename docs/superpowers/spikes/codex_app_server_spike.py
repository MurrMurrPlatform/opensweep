#!/usr/bin/env python3
"""Codex app-server concurrency spike — does ONE app-server process run TWO
concurrent threads (each its own cwd) off ONE auth.json, streaming both, with
central token refresh and no rotation race?

Transport: stdio, newline-delimited JSON-RPC 2.0 (per the app-server README).
Reads credentials ONLY from $CODEX_HOME (a throwaway copy you make). Contains no
secrets. Writes nothing but two scratch temp dirs it cleans up.

Run:
    CODEX_HOME=/tmp/codex-spike/.codex python3 codex_app_server_spike.py

Exit 0 = both threads completed concurrently with no auth/refresh error.
"""

import asyncio
import json
import os
import sys
import tempfile
import time

MODEL = os.environ.get("SPIKE_MODEL", "")  # empty → server default
SANDBOX = "read-only"                       # spike is read-only; nothing destructive
TIMEOUT_S = 120


def _log(tag, msg):
    print(f"[{time.strftime('%H:%M:%S')}] {tag}: {msg}", flush=True)


def _read_access_token(codex_home):
    try:
        with open(os.path.join(codex_home, "auth.json"), encoding="utf-8") as f:
            return (json.load(f).get("tokens") or {}).get("access_token") or ""
    except Exception as e:  # noqa: BLE001
        return f"<unreadable: {e}>"


class AppServer:
    def __init__(self, proc):
        self.proc = proc
        self._id = 0
        self._pending = {}
        self.completed = set()      # threadIds that reached turn/completed
        self.errors = []            # error notifications / refresh failures
        self.messages = []          # (threadId, agent text) seen

    def _next_id(self):
        self._id += 1
        return self._id

    async def _send(self, method, params=None, is_request=True):
        msg = {"method": method}
        if is_request:
            msg["id"] = self._next_id()
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        await self.proc.stdin.drain()
        return msg.get("id")

    async def request(self, method, params=None):
        mid = await self._send(method, params, is_request=True)
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        return await fut

    async def notify(self, method, params=None):
        await self._send(method, params, is_request=False)

    async def read_loop(self):
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                return
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                _log("raw", line[:200])
                continue
            if "id" in obj and ("result" in obj or "error" in obj):
                fut = self._pending.pop(obj["id"], None)
                if fut and not fut.done():
                    fut.set_result(obj)
                continue
            self._on_notification(obj)

    def _on_notification(self, obj):
        method = obj.get("method", "?")
        params = obj.get("params") or {}
        tid = params.get("threadId") or (params.get("thread") or {}).get("id") or "-"
        low = json.dumps(obj).lower()
        if "could not be refreshed" in low or "log out and sign in" in low or method in (
            "error", "thread/realtimeError",
        ):
            self.errors.append(obj)
            _log("ERROR", f"{method} thread={tid} :: {json.dumps(params)[:300]}")
            return
        if method == "turn/completed":
            self.completed.add(tid)
            usage = params.get("usage") or {}
            _log("done", f"thread={tid} turn/completed usage={json.dumps(usage)[:160]}")
            return
        if method in ("item/completed",) and (params.get("item") or {}).get("type") == "agent_message":
            text = (params["item"].get("text") or "")[:120]
            self.messages.append((tid, text))
            _log("msg", f"thread={tid} :: {text!r}")
            return
        # everything else: compact trace
        _log("evt", f"{method} thread={tid}")


async def main():
    codex_home = os.environ.get("CODEX_HOME")
    if not codex_home or not os.path.exists(os.path.join(codex_home, "auth.json")):
        print("FAIL: set CODEX_HOME to a dir containing a throwaway auth.json", file=sys.stderr)
        return 2

    tok_before = _read_access_token(codex_home)
    _log("auth", f"access_token[:12] before = {tok_before[:12]!r}")

    cwd_a = tempfile.mkdtemp(prefix="codex-spike-a-")
    cwd_b = tempfile.mkdtemp(prefix="codex-spike-b-")

    _log("boot", "spawning: codex app-server --stdio")
    proc = await asyncio.create_subprocess_exec(
        "codex", "app-server", "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "CODEX_HOME": codex_home},
    )
    srv = AppServer(proc)
    reader = asyncio.create_task(srv.read_loop())

    async def _stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            _log("stderr", line.decode('utf-8', 'replace').rstrip()[:200])
    stderr_task = asyncio.create_task(_stderr())

    try:
        init = await srv.request("initialize", {
            "clientInfo": {"name": "opensweep-spike", "version": "0.1.0"},
            "capabilities": {"experimentalApi": True},
        })
        if "error" in init:
            _log("FAIL", f"initialize error: {init['error']}")
            return 1
        _log("init", f"ok: {json.dumps(init.get('result', {}))[:200]}")
        await srv.notify("initialized")

        async def start_thread(cwd, label):
            params = {"cwd": cwd, "sandbox": SANDBOX, "approvalPolicy": "never"}
            if MODEL:
                params["model"] = MODEL
            resp = await srv.request("thread/start", params)
            if "error" in resp:
                raise RuntimeError(f"thread/start {label} error: {resp['error']}")
            tid = (resp["result"].get("thread") or {}).get("id")
            _log("thread", f"{label} started id={tid} cwd={cwd}")
            return tid

        tid_a = await start_thread(cwd_a, "A")
        tid_b = await start_thread(cwd_b, "B")

        # Fire BOTH turns before awaiting either → true concurrency in one process.
        async def start_turn(tid, text):
            resp = await srv.request("turn/start", {
                "threadId": tid, "input": [{"type": "text", "text": text}],
            })
            if "error" in resp:
                raise RuntimeError(f"turn/start error: {resp['error']}")
            _log("turn", f"thread={tid} turn started")

        await start_turn(tid_a, "Reply with exactly: HELLO-A. Do not run any commands.")
        await start_turn(tid_b, "Reply with exactly: HELLO-B. Do not run any commands.")

        # Wait until both threads report turn/completed (or timeout).
        deadline = time.monotonic() + TIMEOUT_S
        while len(srv.completed) < 2 and not srv.errors and time.monotonic() < deadline:
            await asyncio.sleep(0.3)

        tok_after = _read_access_token(codex_home)
        _log("auth", f"access_token[:12] after  = {tok_after[:12]!r} "
                     f"({'ROTATED (central refresh)' if tok_after != tok_before else 'unchanged'})")

        print("\n===== SPIKE RESULT =====")
        print(f"threads completed : {sorted(srv.completed)} ({len(srv.completed)}/2)")
        print(f"agent messages    : {len(srv.messages)} (expect >=2, one per thread)")
        print(f"errors/refresh    : {len(srv.errors)}")
        print(f"one auth.json     : shared by both threads in ONE process (no per-run copy)")
        ok = len(srv.completed) == 2 and not srv.errors
        print(f"VERDICT           : {'PASS — concurrent threads, one credential, no rotation race' if ok else 'FAIL'}")
        return 0 if ok else 1
    finally:
        with contextlib_suppress():
            proc.terminate()
        reader.cancel()
        stderr_task.cancel()
        for d in (cwd_a, cwd_b):
            _rmtree(d)


class contextlib_suppress:
    def __enter__(self): return self
    def __exit__(self, *a): return True


def _rmtree(d):
    try:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
