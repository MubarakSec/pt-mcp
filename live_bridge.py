"""Small stdio JSON-RPC bridge to the optional Java Packet Tracer MCP server.

The Python MCP remains usable without the Java distribution. Live tools are
loaded from the Java child when available, with a checked-in catalog usable as
a discovery fallback when the launcher is missing.
"""

from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
JAVA_ROOT = ROOT / "backend" / "java"
DEFAULT_COMMAND = [str(JAVA_ROOT / "build/install/pt-mcp/bin/pt-mcp")]
CATALOG_PATH = ROOT / "live_tools.json"


class LiveBridgeError(RuntimeError):
    """A launch or JSON-RPC failure communicating with the live backend."""


class LiveBridge:
    def __init__(self, command: list[str] | None = None,
                 cwd: str | os.PathLike[str] | None = None,
                 timeout: float | None = None):
        if command is None:
            override = os.environ.get("PT_MCP_LIVE_COMMAND")
            if override:
                try:
                    command = json.loads(override)
                except json.JSONDecodeError as exc:
                    raise ValueError("PT_MCP_LIVE_COMMAND must be a JSON array") from exc
            else:
                command = DEFAULT_COMMAND
        if not isinstance(command, list) or not command or not all(
                isinstance(item, str) and item for item in command):
            raise ValueError("live command must be a non-empty list of strings")
        self.command = list(command)
        self.cwd = Path(cwd) if cwd is not None else JAVA_ROOT
        if timeout is None:
            try:
                timeout = float(os.environ.get("PT_MCP_LIVE_TIMEOUT", "45"))
            except ValueError as exc:
                raise ValueError("PT_MCP_LIVE_TIMEOUT must be a number") from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number")
        self.timeout = timeout

        self._proc: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[Any] = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=80)
        self._lock = threading.RLock()
        self._next_id = 1
        self._protocol = "stdio JSON-RPC"
        self._upstream_tools: list[dict[str, Any]] | None = None
        self._catalog = self._catalog_tools()

    def _launcher_available(self) -> bool:
        executable = self.command[0]
        path = Path(executable)
        if path.is_absolute() or path.parent != Path("."):
            if not path.is_absolute():
                path = self.cwd / path
            return path.is_file() and os.access(path, os.X_OK)
        return shutil.which(executable) is not None

    def _diagnostic(self) -> str:
        return "\n".join(self._stderr).strip()

    def _start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        self._proc = None
        if not self._launcher_available():
            raise LiveBridgeError(f"live backend launcher unavailable: {self.command[0]}")
        if not self.cwd.is_dir():
            raise LiveBridgeError(f"live backend working directory unavailable: {self.cwd}")
        try:
            kwargs: dict[str, Any] = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            self._proc = subprocess.Popen(
                self.command, cwd=self.cwd, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", bufsize=1, **kwargs)
        except OSError as exc:
            raise LiveBridgeError(f"could not start live backend: {exc}") from exc
        self._messages = queue.Queue()
        messages = self._messages
        self._stderr.clear()
        threading.Thread(target=self._read_stdout, args=(self._proc, messages), daemon=True,
                         name="pt-mcp-live-stdout").start()
        threading.Thread(target=self._read_stderr, args=(self._proc,), daemon=True,
                         name="pt-mcp-live-stderr").start()
        try:
            init = self._request("initialize", {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pt-mcp-python-bridge", "version": "1.0"},
            })
            self._protocol = str(init.get("protocolVersion", "stdio JSON-RPC"))
            self._notify("notifications/initialized")
        except Exception:
            self._stop_child()
            raise

    def _read_stdout(self, proc: subprocess.Popen[str], messages: queue.Queue[Any]) -> None:
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.put(json.loads(line))
                except json.JSONDecodeError:
                    messages.put(LiveBridgeError("backend emitted invalid JSON-RPC stdout"))
        except (OSError, ValueError):
            pass
        finally:
            messages.put(None)

    def _read_stderr(self, proc: subprocess.Popen[str]) -> None:
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                line = line.rstrip()
                sensitive = [value for key, value in os.environ.items()
                             if value and any(word in key.lower() for word in
                                              ("secret", "password", "token", "auth_key"))]
                config = Path(os.environ.get("PT_MCP_CONFIG", "local.properties"))
                properties = config if config.is_absolute() else self.cwd / config
                properties = properties.resolve()
                try:
                    for setting in properties.read_text(encoding="utf-8").splitlines():
                        if "=" in setting and any(word in setting.partition("=")[0].lower()
                                                   for word in ("secret", "password", "token", "key")):
                            value = setting.partition("=")[2].strip()
                            sensitive.append(value)
                            # setup.py can store environment credentials using Java
                            # Unicode escapes. Redact their decoded form as well.
                            decoded = re.sub(r"\\u([0-9a-fA-F]{4})",
                                             lambda match: chr(int(match.group(1), 16)), value)
                            try:
                                sensitive.append(decoded.encode("utf-16-be", errors="surrogatepass")
                                                 .decode("utf-16-be"))
                            except UnicodeError:
                                pass
                except OSError:
                    pass
                for value in sensitive:
                    if value:
                        line = line.replace(value, "[redacted]")
                self._stderr.append(line[-1000:])
        except (OSError, ValueError):
            pass

    def _write(self, message: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            raise LiveBridgeError("live backend disconnected" + self._stderr_suffix())
        try:
            proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            proc.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise LiveBridgeError("could not write to live backend" + self._stderr_suffix()) from exc

    def _stderr_suffix(self) -> str:
        diagnostic = self._diagnostic()
        return f": {diagnostic}" if diagnostic else ""

    def _next_response(self, request_id: int) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LiveBridgeError(f"live backend request timed out after {self.timeout:g}s"
                                      + self._stderr_suffix())
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise LiveBridgeError(f"live backend request timed out after {self.timeout:g}s"
                                      + self._stderr_suffix()) from exc
            if message is None:
                raise LiveBridgeError("live backend closed stdout" + self._stderr_suffix())
            if isinstance(message, LiveBridgeError):
                raise LiveBridgeError(str(message) + self._stderr_suffix())
            if not isinstance(message, dict):
                continue
            # Servers can send notifications or requests while a request is in
            # flight. Respond to ping and ignore notifications; never treat
            # either as the response for our own id.
            if "method" in message:
                if "id" in message:
                    reply = {"jsonrpc": "2.0", "id": message["id"]}
                    if message["method"] == "ping":
                        reply["result"] = {}
                    else:
                        reply["error"] = {"code": -32601, "message": "Method not found"}
                    self._write(reply)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise LiveBridgeError(f"backend JSON-RPC error: {error}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise LiveBridgeError("backend returned a malformed JSON-RPC result")
            return result

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)
        return self._next_response(request_id)

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    @staticmethod
    def _live_descriptor(tool: dict[str, Any]) -> dict[str, Any]:
        result = dict(tool)
        name = result.get("name")
        if isinstance(name, str) and name.startswith("pt_"):
            result["name"] = "pt_live_" + name[3:]
        description = result.get("description", "")
        result["description"] = "LIVE: affects running Packet Tracer. " + str(description)
        return result

    @staticmethod
    def _catalog_tools() -> list[dict[str, Any]]:
        try:
            with CATALOG_PATH.open(encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, list):
            tools = data
        elif isinstance(data, dict):
            tools = data.get("tools")
            if tools is None and isinstance(data.get("result"), dict):
                tools = data["result"].get("tools")
        else:
            tools = None
        return [tool for tool in tools if isinstance(tool, dict)] if isinstance(tools, list) else []

    def tools(self) -> list[dict[str, Any]]:
        """Return upstream descriptors with the `pt_live_` namespaced names."""
        with self._lock:
            if self._upstream_tools is not None:
                return [self._live_descriptor(tool) for tool in self._upstream_tools]
            # The generated catalog is enough for Python MCP initialization;
            # do not make offline startup depend on Java or Packet Tracer.
            if self._catalog:
                self._upstream_tools = self._catalog
                return [self._live_descriptor(tool) for tool in self._upstream_tools]
            try:
                if not self._launcher_available():
                    raise LiveBridgeError("live backend launcher unavailable")
                self._start()
                response = self._request("tools/list")
                tools = response.get("tools")
                if not isinstance(tools, list):
                    raise LiveBridgeError("backend tools/list response has no tools array")
                self._upstream_tools = [tool for tool in tools if isinstance(tool, dict)]
            except LiveBridgeError:
                cached = self._catalog
                if cached:
                    self._upstream_tools = cached
                else:
                    raise
            return [self._live_descriptor(tool) for tool in self._upstream_tools]

    @classmethod
    def cached_tools(cls) -> list[dict[str, Any]]:
        """Expose cached descriptors even when live configuration is invalid."""
        return [cls._live_descriptor(tool) for tool in cls._catalog_tools()]

    def call_tool(self, prefixed_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call one live tool once; a timeout/disconnect is never retried."""
        if not prefixed_name.startswith("pt_live_"):
            raise LiveBridgeError(f"not a live tool name: {prefixed_name}")
        upstream_name = "pt_" + prefixed_name[len("pt_live_"):]
        with self._lock:
            self._start()
            # Do not retry on timeout/disconnect: a mutation may have completed
            # even when its response was lost.
            try:
                return self._request("tools/call", {
                    "name": upstream_name,
                    "arguments": args if isinstance(args, dict) else {},
                })
            except LiveBridgeError as exc:
                self._stop_child()
                raise LiveBridgeError(
                    f"{exc}. Outcome may be unknown; inspect Packet Tracer before retrying."
                ) from exc

    def status(self) -> dict[str, Any]:
        """Report availability without starting a process or exposing secrets."""
        with self._lock:
            proc = self._proc
            alive = proc is not None and proc.poll() is None
            cached_count = len(self._catalog)
            return {
                "launcher_available": self._launcher_available(),
                "child_alive": alive,
                "cached_catalog_count": cached_count,
                "backend_protocol": self._protocol,
            }

    def _stop_child(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                proc.terminate()
            else:
                os.killpg(proc.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                if os.name == "nt":
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    def close(self) -> None:
        """Terminate the backend process group, including descendants."""
        with self._lock:
            proc = self._proc
            if proc is not None and proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            self._stop_child()

