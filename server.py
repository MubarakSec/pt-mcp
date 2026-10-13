#!/usr/bin/env python3
"""
pt-mcp - read + build MCP server for Cisco Packet Tracer topologies.

Speaks MCP over stdio with zero third-party dependencies (pure stdlib) and
zero external projects: the Unpacket crypto stack is vendored in ./Decipher
and the XML tooling (ptread / ptbuild) lives beside this file.

This folder is self-contained. Move it anywhere and it still runs.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ptread import parse, text, config_text  # noqa: E402
import ptbuild  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
CACHE_DIR = os.path.join(tempfile.gettempdir(), "pt-mcp-cache")

# ---------------------------------------------------------------- state

_state = {"path": None, "root": None, "topo": None}

# The build session is deliberately separate from the read session: reading a
# file never implies you may modify it. A build session only exists after an
# explicit pt_build_open, and it always works on a COPY of the XML.
_build = {"src": None, "xml": None, "topo": None, "base": None, "log": []}


def _err(msg, code=-32603):
    return {"content": [{"type": "text", "text": msg}], "isError": True}


def _ok(payload):
    if not isinstance(payload, str):
        payload = json.dumps(payload, indent=2, ensure_ascii=False)
    return {"content": [{"type": "text", "text": payload}]}


def _decode_to_xml(path):
    """Return XML path for a .pkt (decrypt+cache) or a .xml (used as-is)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    os.makedirs(CACHE_DIR, exist_ok=True)
    if path.lower().endswith(".xml"):
        return path
    if not path.lower().endswith(".pkt"):
        raise ValueError(f"unsupported file type: {path} (expected .pkt or .xml)")
    out = os.path.join(CACHE_DIR, os.path.basename(path) + ".xml")
    stamp = os.path.getmtime(path)
    prev = os.path.getmtime(out) if os.path.exists(out) else 0
    if prev < stamp:
        script = os.path.join(HERE, "unpacket.py")
        r = subprocess.run([sys.executable, script, path, "-o", out],
                           capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError(f"unpacket failed: {r.stderr.strip() or r.stdout.strip()}")
    return out


def _load(path):
    xml_path = _decode_to_xml(path)
    root = ET.parse(xml_path).getroot()
    topo = parse(root)
    _state.update(path=path, xml=xml_path, root=root, topo=topo)
    return topo


def _require():
    if _state["topo"] is None:
        raise RuntimeError("no file open -- call pt_open first")
    return _state


def _device(topo, needle):
    """Find a device by exact name, then case-insensitive, then unique substring."""
    ordered = [topo["by_ref"][r] for r in topo["devices"]]
    names = [d["name"] for d in ordered]
    if needle in names:
        return ordered[names.index(needle)]
    low = needle.lower()
    for d in ordered:
        if d["name"].lower() == low:
            return d
    hits = [d for d in ordered if low in d["name"].lower()]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise LookupError(f"ambiguous name '{needle}': {[h['name'] for h in hits]}")
    raise LookupError(f"no device named '{needle}'. Have: {names}")


# ---------------------------------------------------------------- tools

def t_pt_list_files(args):
    d = os.path.expanduser(args["path"])
    if not os.path.isdir(d):
        raise NotADirectoryError(d)
    rows = []
    for f in sorted(os.listdir(d)):
        fp = os.path.join(d, f)
        if os.path.isfile(fp) and f.lower().endswith((".pkt", ".xml")):
            rows.append({"name": f, "bytes": os.path.getsize(fp),
                         "path": fp,
                         "modified": os.path.getmtime(fp)})
    return {"directory": d, "count": len(rows), "files": rows}


def t_pt_open(args):
    p = os.path.abspath(os.path.expanduser(args["path"]))
    topo = _load(p)
    st = _state
    return {
        "opened": p,
        "pt_version": text(st["root"], "VERSION"),
        "xml_cache": st["xml"],
        "xml_bytes": os.path.getsize(st["xml"]),
        "devices": len(topo["devices"]),
        "links": len(topo["links"]),
        "notes": len([n for n in topo["notes"] if n["text"].strip()]),
        "saved_pdus": len(topo["pdus"]),
        "description": topo["description"],
        "device_names": [topo["by_ref"][r]["name"] for r in topo["devices"]],
    }


def t_pt_overview(args):
    st = _require()
    topo, root = st["topo"], st["root"]
    by_type = {}
    for r in topo["devices"]:
        by_type[topo["by_ref"][r]["type"]] = by_type.get(topo["by_ref"][r]["type"], 0) + 1
    logs = root.findall("COMMAND_LOGS")
    return {
        "file": st["path"],
        "pt_version": text(root, "VERSION"),
        "counts": {
            "devices": len(topo["devices"]),
            "links": len(topo["links"]),
            "notes": len([n for n in topo["notes"] if n["text"].strip()]),
            "pdus": len(topo["pdus"]),
            "command_logs": len(logs[0]) if logs else 0,
        },
        "devices_by_type": by_type,
        "description": topo["description"],
    }


def t_pt_devices(args):
    topo = _require()["topo"]
    rows = []
    for r in topo["devices"]:
        d = topo["by_ref"][r]
        if args.get("type") and args["type"].lower() not in d["type"].lower():
            continue
        if args.get("filter") and args["filter"].lower() not in d["name"].lower():
            continue
        cfg = d["running"] or d["startup"]
        rows.append({
            "name": d["name"], "type": d["type"],
            "x": d["x"], "y": d["y"],
            "has_running": bool(d["running"]),
            "has_startup": bool(d["startup"]),
            "config_lines": len(cfg.splitlines()),
        })
    return {"count": len(rows), "devices": rows}


def t_pt_device_detail(args):
    st = _require()
    topo = st["topo"]
    d = _device(topo, args["name"])
    eng = None
    for dev in st["root"].findall("NETWORK/DEVICES/DEVICE"):
        e = dev.find("ENGINE")
        if e is not None and e.findtext("SAVE_REF_ID") == d["ref"]:
            eng = e
            break
    detail = {
        "name": d["name"], "type": d["type"], "ref": d["ref"],
        "x": d["x"], "y": d["y"], "description": d["description"],
        "has_running_config": bool(d["running"]),
        "has_startup_config": bool(d["startup"]),
    }
    if eng is not None:
        vlans = eng.find("VLANS")
        if vlans is not None and len(vlans):
            detail["vlans"] = [ET.tostring(v, encoding="unicode").strip()
                               for v in vlans]
        detail["description_attr"] = text(eng, "DESCRIPTION")
        detail["config_register"] = text(eng, "CONFIG_REGISTER")
    # interfaces mentioned by the saved cabling
    ports = []
    for l in topo["links"]:
        if d["name"] in (l["from"], l["to"]):
            other = l["to"] if l["from"] == d["name"] else l["from"]
            myport = l["from_port"] if l["from"] == d["name"] else l["to_port"]
            otherport = l["to_port"] if l["from"] == d["name"] else l["from_port"]
            ports.append(f"{myport} --[{l['type']}]--> {other} {otherport}")
    detail["cabled_ports"] = ports
    return detail


def t_pt_config(args):
    topo = _require()["topo"]
    d = _device(topo, args["name"])
    which = args.get("which", "auto")
    if which == "startup":
        cfg = d["startup"]
        src = "startup"
    elif which == "running":
        cfg = d["running"]
        src = "running"
    else:
        cfg = d["running"] or d["startup"]
        src = "running" if d["running"] else "startup"
    if not cfg:
        return {"name": d["name"], "source": None, "config": ""}
    return {"name": d["name"], "source": src, "lines": len(cfg.splitlines()),
            "config": cfg}


def t_pt_links(args):
    topo = _require()["topo"]
    f = args.get("filter")
    fl = f.lower() if f else None
    rows = []
    for l in topo["links"]:
        blob = f"{l['from']} {l['from_port']} {l['to']} {l['to_port']} {l['type']}".lower()
        if fl and fl not in blob:
            continue
        rows.append(l)
    return {"count": len(rows), "links": rows}


def t_pt_notes(args):
    topo = _require()["topo"]
    f = args.get("filter")
    rows = [n for n in topo["notes"]
            if not f or f.lower() in n["text"].lower()]
    return {"count": len(rows), "notes": rows}


def t_pt_pdus(args):
    return {"count": len(_require()["topo"]["pdus"]), "pdus": _require()["topo"]["pdus"]}


def t_pt_search(args):
    """Grep a pattern across every device config plus canvas notes."""
    st = _require()
    topo = st["topo"]
    pattern = args["pattern"]
    ignore_case = args.get("ignore_case", True)

    def matches(line):
        return pattern.lower() in line.lower() if ignore_case else pattern in line

    hits = []
    for r in topo["devices"]:
        d = topo["by_ref"][r]
        for label, cfg in (("running", d["running"]), ("startup", d["startup"])):
            for i, line in enumerate(cfg.splitlines(), 1):
                if matches(line):
                    hits.append({"where": f"{d['name']}:{label}", "line": i, "text": line})
    for n in topo["notes"]:
        for i, line in enumerate(n["text"].splitlines(), 1):
            if matches(line):
                hits.append({"where": f"note@{n['x']},{n['y']}", "line": i, "text": line})
    return {"pattern": pattern, "count": len(hits), "hits": hits[:args.get("max", 200)]}


def t_pt_command_logs(args):
    """Raw CLI command history stored in the file (PT stores it hex-encoded)."""
    st = _require()
    logs = st["root"].findall("COMMAND_LOGS")
    if not logs:
        return {"count": 0, "entries": []}
    n = args.get("limit", 50)
    entries = []
    for e in list(logs[0])[:n]:
        raw = (e.text or "").strip()
        if not raw:
            continue
        decoded = raw
        try:
            candidate = bytes.fromhex(raw)
            printable = candidate.decode("utf-8", "replace")
            if printable.isprintable() or all(c.isprintable() or c in "\r\n\t\x00"
                                               for c in printable):
                decoded = printable.replace("\x00", " | ")
        except ValueError:
            pass
        entries.append(decoded)
    return {"count": len(logs[0]), "entries": entries}




# ---------------------------------------------------------------- build

def _build_require():
    if _build["topo"] is None:
        raise RuntimeError("no build session -- call pt_build_open first")
    return _build


def _build_diff(b):
    """What changed since pt_build_open."""
    now = b["topo"].summary()
    was = b["base"]
    added = [n for n in now["names"] if n not in was["names"]]
    removed = [n for n in was["names"] if n not in now["names"]]
    return {
        "devices": {"before": was["devices"], "after": now["devices"],
                    "added": added, "removed": removed},
        "links": {"before": was["links"], "after": now["links"],
                  "delta": now["links"] - was["links"]},
        "operations": b["log"],
    }


def b_open(args):
    src = os.path.abspath(os.path.expanduser(args["path"]))
    xml = _decode_to_xml(src)
    work = os.path.join(CACHE_DIR, "build", os.path.basename(src) + ".build.xml")
    os.makedirs(os.path.dirname(work), exist_ok=True)
    shutil.copyfile(xml, work)

    topo = ptbuild.Topology.load(work)
    _build.update(src=src, xml=work, topo=topo, base=topo.summary(), log=[])
    return {
        "source_pkt": src,
        "working_xml": work,
        "note": "source .pkt is never modified; edits go to working_xml until pt_build_save",
        **_build_diff(_build),
    }


def b_clone(args):
    b = _build_require()
    t = b["topo"]
    t.clone_device(args["source"], name=args["name"],
                   x=args.get("x"), y=args.get("y"), mac=args.get("mac"))
    b["log"].append(f"clone {args['source']} -> {args['name']}")
    d = t.device(args["name"])
    log = d.find("WORKSPACE/LOGICAL")
    return {"cloned": args["name"], "from": args["source"],
            "x": log.findtext("X"), "y": log.findtext("Y"),
            "new_ref": d.find("ENGINE").findtext("SAVE_REF_ID"),
            "devices": t.summary()["devices"]}


def b_cable(args):
    b = _build_require()
    t = b["topo"]
    t.add_cable(args["device_a"], args["port_a"],
                args["device_b"], args["port_b"],
                args.get("kind", "eCopper"))
    desc = (f"{args['device_a']} {args['port_a']} -- "
            f"{args.get('kind', 'eCopper')} --> "
            f"{args['device_b']} {args['port_b']}")
    b["log"].append(f"cable {desc}")
    return {"cabled": desc, "links": t.summary()["links"]}


def b_note(args):
    b = _build_require()
    b["topo"].add_note(args["text"], x=args.get("x", 100),
                       y=args.get("y", 100), z=args.get("z", 40000))
    b["log"].append(f"note at ({args.get('x', 100)},{args.get('y', 100)})")
    return {"note_added": True, "at": [args.get("x", 100), args.get("y", 100)]}


def b_rename(args):
    b = _build_require()
    t = b["topo"]
    eng = t.device(args["device"]).find("ENGINE")
    old = eng.findtext("NAME")
    eng.find("NAME").text = args["to"]
    sn = eng.find("SYS_NAME")
    if sn is not None and sn.text:
        sn.text = args["to"]
    b["log"].append(f"rename {old} -> {args['to']}")
    return {"renamed": old, "to": args["to"]}


def b_delete_device(args):
    """Remove a device and every cable touching it."""
    b = _build_require()
    t = b["topo"]
    ref = t.ref(args["device"])
    for d in t.devices.findall("DEVICE"):
        if d.find("ENGINE").findtext("SAVE_REF_ID") == ref:
            t.devices.remove(d)
            break
    dropped = 0
    for l in list(t.links.findall("LINK")):
        cab = l.find("CABLE")
        if cab is not None and ref in (cab.findtext("FROM"), cab.findtext("TO"),
                                       cab.findtext("DCEDEV")):
            t.links.remove(l)
            dropped += 1
    b["log"].append(f"delete {args['device']} (+{dropped} cables)")
    return {"deleted": args["device"], "cables_removed": dropped,
            "devices": t.summary()["devices"], "links": t.summary()["links"]}


def b_delete_cable(args):
    b = _build_require()
    t = b["topo"]
    ra, rb = t.ref(args["device_a"]), t.ref(args["device_b"])
    dropped = 0
    for l in list(t.links.findall("LINK")):
        cab = l.find("CABLE")
        if cab is None:
            continue
        ends = {cab.findtext("FROM"), cab.findtext("TO")}
        if {ra, rb} <= ends:
            t.links.remove(l)
            dropped += 1
    b["log"].append(f"delete cable {args['device_a']}<->{args['device_b']}")
    return {"cables_removed": dropped, "links": t.summary()["links"]}


def b_set_config(args):
    """Replace a device's saved startup AND running config with given CLI."""
    b = _build_require()
    eng = b["topo"].device(args["device"]).find("ENGINE")
    lines = args["config"].splitlines()
    changed = []
    for tag in ("STARTUPCONFIG", "RUNNINGCONFIG"):
        node = eng.find(tag)
        if node is None:
            node = ET.SubElement(eng, tag)
        for child in list(node):
            node.remove(child)
        for line in lines:
            ET.SubElement(node, "LINE").text = line
        changed.append(tag)
    b["log"].append(f"set config on {args['device']} ({len(lines)} lines)")
    return {"device": args["device"], "lines": len(lines), "updated": changed,
            "warning": "written as both startup and running; they will not match a booted device until PT boots it"}


def b_status(args):
    b = _build_require()
    return {"source_pkt": b["src"], "working_xml": b["xml"], **_build_diff(b)}


def b_save(args):
    """Write XML, repacket to .pkt. Refuses to clobber the source file."""
    b = _build_require()
    out = os.path.abspath(os.path.expanduser(args["path"]))
    if out == b["src"] and not args.get("allow_overwrite"):
        raise PermissionError(
            f"refusing to overwrite the source lab {out}. "
            f"Pass allow_overwrite=true if you really mean it, or choose another path.")

    xml_out = os.path.splitext(out)[0] + ".xml"
    b["topo"].save(xml_out)
    script = os.path.join(HERE, "repacket.py")
    r = subprocess.run([sys.executable, script, xml_out, "-o", out],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"repacket failed: {r.stderr.strip() or r.stdout.strip()}")
    b["log"].append(f"saved {out}")
    return {"written": out, "bytes": os.path.getsize(out),
            "sidecar_xml": xml_out, **_build_diff(b)}



TOOLS = [
    ("pt_list_files", "List .pkt/.xml files in a directory.", {
        "type": "object",
        "properties": {"path": {"type": "string",
                                "description": "Directory to list."}},
        "required": ["path"]}),
    ("pt_open", "Decrypt and open a .pkt (or a .xml) as the active topology. Read-only.", {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Absolute path to .pkt or .xml"}},
        "required": ["path"]}),
    ("pt_overview", "Summary of the open file: version, counts, devices by type.", {
        "type": "object", "properties": {}}),
    ("pt_devices", "List devices. Filter by type or name substring.", {
        "type": "object",
        "properties": {"type": {"type": "string"}, "filter": {"type": "string"}}}),
    ("pt_device_detail", "One device: position, VLANs, description, cabled ports.", {
        "type": "object",
        "properties": {"name": {"type": "string"}}, "required": ["name"]}),
    ("pt_config", "Get a device's CLI config (running or startup).", {
        "type": "object",
        "properties": {"name": {"type": "string"},
                       "which": {"type": "string", "enum": ["auto", "running", "startup"]}},
        "required": ["name"]}),
    ("pt_links", "Cabling table between devices.", {
        "type": "object",
        "properties": {"filter": {"type": "string", "description": "substring of either endpoint"}}}),
    ("pt_notes", "Canvas notes with coordinates.", {
        "type": "object", "properties": {"filter": {"type": "string"}}}),
    ("pt_pdus", "Saved ping/trace tests.", {
        "type": "object", "properties": {}}),
    ("pt_search", "Grep a string across all device configs and notes.", {
        "type": "object",
        "properties": {"pattern": {"type": "string"},
                       "ignore_case": {"type": "boolean"},
                       "max": {"type": "integer"}},
        "required": ["pattern"]}),
    ("pt_command_logs", "Raw CLI command history stored in the file.", {
        "type": "object", "properties": {"limit": {"type": "integer"}}}),
] + [
    ("pt_build_open", "Start an editable copy of a .pkt. Source file is never modified.", {
        "type": "object",
        "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    ("pt_build_status", "What has changed in the current build session.", {
        "type": "object", "properties": {}}),
    ("pt_build_clone", "Duplicate an existing device under a new name at a position.", {
        "type": "object",
        "properties": {"source": {"type": "string", "description": "device to copy"},
                       "name": {"type": "string"},
                       "x": {"type": "number"}, "y": {"type": "number"},
                       "mac": {"type": "string"}},
        "required": ["source", "name"]}),
    ("pt_build_cable", "Connect two devices by interface name.", {
        "type": "object",
        "properties": {"device_a": {"type": "string"}, "port_a": {"type": "string"},
                       "device_b": {"type": "string"}, "port_b": {"type": "string"},
                       "kind": {"type": "string", "enum": ["eCopper", "eSerial"]}},
        "required": ["device_a", "port_a", "device_b", "port_b"]}),
    ("pt_build_note", "Add a canvas note.", {
        "type": "object",
        "properties": {"text": {"type": "string"},
                       "x": {"type": "integer"}, "y": {"type": "integer"},
                       "z": {"type": "integer"}},
        "required": ["text"]}),
    ("pt_build_rename", "Rename a device.", {
        "type": "object",
        "properties": {"device": {"type": "string"}, "to": {"type": "string"}},
        "required": ["device", "to"]}),
    ("pt_build_delete_device", "Remove a device and all cables touching it.", {
        "type": "object",
        "properties": {"device": {"type": "string"}}, "required": ["device"]}),
    ("pt_build_delete_cable", "Remove cables between two devices.", {
        "type": "object",
        "properties": {"device_a": {"type": "string"}, "device_b": {"type": "string"}},
        "required": ["device_a", "device_b"]}),
    ("pt_build_set_config", "Replace a device's saved CLI config.", {
        "type": "object",
        "properties": {"device": {"type": "string"}, "config": {"type": "string"}},
        "required": ["device", "config"]}),
    ("pt_build_save", "Write the build out as a .pkt (XML + repacket).", {
        "type": "object",
        "properties": {"path": {"type": "string"},
                       "allow_overwrite": {"type": "boolean"}},
        "required": ["path"]}),
]

HANDLERS = {
    "pt_list_files": t_pt_list_files,
    "pt_open": t_pt_open,
    "pt_overview": t_pt_overview,
    "pt_devices": t_pt_devices,
    "pt_device_detail": t_pt_device_detail,
    "pt_config": t_pt_config,
    "pt_links": t_pt_links,
    "pt_notes": t_pt_notes,
    "pt_pdus": t_pt_pdus,
    "pt_search": t_pt_search,
    "pt_command_logs": t_pt_command_logs,
    "pt_build_open": b_open,
    "pt_build_status": b_status,
    "pt_build_clone": b_clone,
    "pt_build_cable": b_cable,
    "pt_build_note": b_note,
    "pt_build_rename": b_rename,
    "pt_build_delete_device": b_delete_device,
    "pt_build_delete_cable": b_delete_cable,
    "pt_build_set_config": b_set_config,
    "pt_build_save": b_save,
}

# ---------------------------------------------------------------- protocol

def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _result(rid, payload):
    _send({"jsonrpc": "2.0", "id": rid, "result": payload})


def _error(rid, msg, code=-32603):
    _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}})


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if os.environ.get("PT_MCP_DEBUG"):
        with open(os.path.join(CACHE_DIR, "last-request.json"), "w") as fh:
            json.dump(req, fh, indent=2)

    if method == "initialize":
        ver = params.get("protocolVersion") or PROTOCOL_VERSION
        _result(rid, {
            "protocolVersion": ver,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "pt-mcp", "version": "0.2.0",
                           "description": "Packet Tracer topology reader and builder"},
        })
    elif method in ("notifications/initialized", "initialized"):
        return
    elif method == "ping":
        _result(rid, {})
    elif method == "tools/list":
        _result(rid, {"tools": [
            {"name": n, "description": d, "inputSchema": s}
            for n, d, s in TOOLS
        ]})
    elif method == "tools/call":
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            _result(rid, _err(f"unknown tool: {name}"))
            return
        try:
            _result(rid, _ok(fn(params.get("arguments") or {})))
        except Exception as exc:
            _result(rid, _err(f"{type(exc).__name__}: {exc}"))
    elif rid is not None:
        _error(rid, f"method not found: {method}", -32601)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            handle(req)
        except Exception as exc:  # never die on one bad request
            if req.get("id") is not None:
                _error(req["id"], f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
