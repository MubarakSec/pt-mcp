#!/usr/bin/env python3
"""Smoke-test the pt-mcp server over stdio with a real MCP handshake."""
import json
import subprocess
import sys

SERVER = ["python3", "/home/mobta/tools/pt-mcp/server.py"]
TARGET = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/pktprobe/probe.pkt"

REQS = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
     "params": {"name": "pt_open", "arguments": {"path": TARGET}}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
     "params": {"name": "pt_overview", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
     "params": {"name": "pt_devices", "arguments": {"type": "Router"}}},
    {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
     "params": {"name": "pt_config", "arguments": {"name": "R1"}}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
     "params": {"name": "pt_search", "arguments": {"pattern": "hsrp", "max": 5}}},
    {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
     "params": {"name": "pt_links", "arguments": {"filter": "Switch5"}}},
]

payload = "\n".join(json.dumps(r) for r in REQS) + "\n"
p = subprocess.run(SERVER, input=payload, capture_output=True, text=True, timeout=300)

if p.stderr.strip():
    print("STDERR:", p.stderr.strip()[:2000], "\n")

for line in p.stdout.splitlines():
    if not line.strip():
        continue
    m = json.loads(line)
    rid = m.get("id")
    if "error" in m:
        print(f"[{rid}] ERROR {m['error']}")
        continue
    r = m["result"]
    if rid == 1:
        print(f"[1] initialize -> {r['serverInfo']['name']} v{r['serverInfo']['version']} "
              f"proto={r['protocolVersion']}")
    elif rid == 2:
        print(f"[2] tools/list -> {len(r['tools'])} tools: "
              f"{', '.join(t['name'] for t in r['tools'])}")
    else:
        text = r["content"][0]["text"]
        tag = "ERR" if r.get("isError") else "ok"
        print(f"[{rid}] {tag} ({len(text)} chars) {text[:220].replace(chr(10), ' ')}")
