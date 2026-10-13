#!/usr/bin/env python3
"""
ptread.py - Read a decoded Packet Tracer XML topology.

Usage:
    ptread.py topology.xml                # human-readable report
    ptread.py topology.xml --configs DIR  # dump each device config to DIR/
    ptread.py topology.xml --json         # machine-readable topology

Companion to Unpacket (https://github.com/Punkcake21/Unpacket).
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET


def text(node, tag, default=""):
    if node is None:
        return default
    el = node.find(tag)
    if el is None or el.text is None:
        return default
    return el.text


def parse(root):
    """Extract devices, links, notes and scenarios from a PACKETTRACER5 tree."""
    net = root.find("NETWORK")
    if net is None:
        raise SystemExit("not a PACKETTRACER5 network file (no <NETWORK>)")

    devices = {}
    order = []
    for dev in net.findall("DEVICES/DEVICE"):
        eng = dev.find("ENGINE")
        ws = dev.find("WORKSPACE")
        if eng is None:
            continue
        ref = text(eng, "SAVE_REF_ID")
        name = text(eng, "NAME") or text(eng, "SYS_NAME")
        entry = {
            "ref": ref,
            "name": name,
            "type": text(eng, "TYPE"),
            "model": text(eng, "MODEL"),
            "power": text(eng, "POWER"),
            "description": text(eng, "DESCRIPTION"),
            "x": text(ws, "LOGICAL/X"),
            "y": text(ws, "LOGICAL/Y"),
            "running": config_text(eng, "RUNNINGCONFIG"),
            "startup": config_text(eng, "STARTUPCONFIG"),
        }
        devices[ref] = entry
        order.append(ref)

    def resolve(ref):
        d = devices.get(ref)
        return d["name"] if d else ref

    links = []
    for lnk in net.findall("LINKS/LINK"):
        cab = lnk.find("CABLE")
        if cab is None:
            continue
        fp, tp = cab.findall("PORT")
        links.append({
            "type": text(lnk, "TYPE"),
            "from": resolve(text(cab, "FROM")),
            "from_port": fp.text if fp is not None and fp.text else "",
            "to": resolve(text(cab, "TO")),
            "to_port": tp.text if tp is not None and tp.text else "",
            "length": text(cab, "LENGTH"),
            "functional": text(cab, "FUNCTIONAL"),
        })

    pdus = []
    for sc in root.findall("SCENARIOSET/SCENARIO"):
        for pdu in sc.findall("PDU"):
            pdus.append({
                "scenario": text(sc, "NAME"),
                "type": text(pdu, "TYPE"),
                "custom": text(pdu, "CUSTOM_TYPE"),
                "source": resolve(text(pdu, "SOURCE")),
                "port": text(pdu, "PORT"),
                "dest": resolve(text(pdu, "DESTINATION")),
            })

    description = text(net, "DESCRIPTION")

    # Canvas notes live under PHYSICALWORKSPACE/NOTES/NOTE, not on the devices.
    notes = []
    for i, n in enumerate(root.findall("PHYSICALWORKSPACE/NOTES/NOTE")):
        notes.append({
            "id": i,
            "x": text(n, "X"),
            "y": text(n, "Y"),
            "z": text(n, "Z"),
            "text": text(n, "TEXT"),
        })

    # Free-floating text/graphics (labels drawn on the canvas).
    labels = []
    for gi in root.findall("GEOVIEW_GRAPHICSITEMS"):
        body = (gi.text or "").strip() or ET.tostring(gi, encoding="unicode")
        if body.strip():
            labels.append(body)

    return {"devices": order, "by_ref": devices, "links": links,
            "pdus": pdus, "notes": notes, "labels": labels,
            "description": description}


def config_text(eng, tag):
    """RUNNINGCONFIG/STARTUPCONFIG hold the CLI as a sequence of LINE elements."""
    node = eng.find(tag)
    if node is None:
        return ""
    lines = []
    for ln in node.iter():
        if ln.tag == "LINE" and ln.text is not None:
            lines.append(ln.text.rstrip("\n"))
    if lines:
        return "\n".join(lines)
    return (node.text or "").strip()


def main():
    ap = argparse.ArgumentParser(description="Read a decoded Packet Tracer XML topology")
    ap.add_argument("xml", help="topology .xml produced by unpacket")
    ap.add_argument("--configs", metavar="DIR", help="write per-device CLI configs into DIR")
    ap.add_argument("--json", action="store_true", help="emit topology as JSON")
    args = ap.parse_args()

    root = ET.parse(args.xml).getroot()
    topo = parse(root)

    if args.json:
        print(json.dumps(topo, indent=2))
        return

    dev = topo["by_ref"]
    print(f"Packet Tracer topology: {args.xml}")
    print(f"PT version {text(root, 'VERSION')}   devices: {len(topo['devices'])}"
          f"   links: {len(topo['links'])}   saved PDUs: {len(topo['pdus'])}")
    if topo["description"]:
        print(f"Description: {topo['description']}")
    print()

    print("== DEVICES ==")
    for ref in topo["devices"]:
        d = dev[ref]
        cfg = d["running"] or d["startup"]
        print(f"  {d['name']:<22} {d['type']:<18} "
              f"cfg={'startup' if d['startup'] and not d['running'] else ('running' if d['running'] else 'none'):<8} "
              f"lines={len(cfg.splitlines()):>3}")
    print()

    print("== CABLING ==")
    for l in topo["links"]:
        print(f"  {l['from']:<22} {l['from_port']:<16} --[{l['type']}]--> {l['to']:<22} {l['to_port']}")
    print()

    if topo["pdus"]:
        print("== SAVED TESTS (PDUs) ==")
        for p in topo["pdus"]:
            print(f"  [{p['scenario']}] {p['type']:<12} {p['custom']:<10} "
                  f"{p['source']} {p['port']} -> {p['dest']}")
        print()

    live = [n for n in topo["notes"] if n["text"].strip()]
    print("== NOTES ==")
    if live:
        for n in live:
            print(f"  @({n['x']},{n['y']}) {n['text'].strip()[:160]}")
    else:
        print("  (none)")
    print()

    if topo["labels"]:
        print(f"== CANVAS GRAPHICS ==\n  ({len(topo['labels'])} geoview graphic items -- "
              f"use --json to inspect)\n")

    if args.configs:
        os.makedirs(args.configs, exist_ok=True)
        for ref in topo["devices"]:
            d = dev[ref]
            cfg = d["running"] or d["startup"]
            if not cfg:
                continue
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in d["name"] or ref)
            path = os.path.join(args.configs, f"{safe}.cfg")
            with open(path, "w") as fh:
                fh.write(cfg + "\n")
            print(f"  wrote {path}")


if __name__ == "__main__":
    main()
