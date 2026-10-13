"""Store and instantiate native Packet Tracer device models.

Templates contain Packet Tracer's own ``DEVICE`` and physical ``NODE`` XML,
so hardware/module trees are never synthesized by this module. Use
``import_file`` on XML exported by ``unpacket`` (or exported directly by PT),
then ``add_device`` to add a clean instance to a :class:`ptbuild.Topology`.
Sanitization clears IOS configuration, interface addressing, DHCP client
leases, and learned switch VLANs. It is not a full reset of Packet Tracer
service/file-manager state, so import a clean native model source when those
model-specific services matter.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


SCHEMA_VERSION = 1
DEFAULT_LIBRARY_DIR = Path(__file__).resolve().parent / "model-templates"


def _library_dir(librarydir=None):
    return Path(librarydir) if librarydir is not None else DEFAULT_LIBRARY_DIR


def _normalize(value):
    return (value or "").strip().lower()


def _slug(value):
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    return text or "unknown"


def _template_identity(device):
    engine = device.find("ENGINE")
    if engine is None:
        raise ValueError("native device has no ENGINE element")
    type_el = engine.find("TYPE")
    if type_el is None or not (type_el.text or "").strip():
        raise ValueError("native device has no ENGINE/TYPE name")
    device_type = type_el.text.strip()
    model = (type_el.get("model") or type_el.get("customModel") or "").strip()
    if not model:
        raise ValueError(f"native {device_type!r} device has no model attribute")
    return device_type, model


def _uuid_key(value):
    return (value or "").strip().strip("{}").lower()


def _physical_node_for(device, node_by_uuid, nodes_by_name):
    workspace = device.find("WORKSPACE")
    if workspace is None:
        raise ValueError("native device has no WORKSPACE element")
    path = workspace.findtext("PHYSICAL") or ""
    leaf_uuid = _uuid_key(path.split(",")[-1]) if path else ""
    node = node_by_uuid.get(leaf_uuid) if leaf_uuid else None
    if node is None:
        name = device.findtext("ENGINE/NAME") or ""
        matches = nodes_by_name.get(_normalize(name), [])
        if len(matches) == 1:
            node = matches[0]
    if node is None:
        name = device.findtext("ENGINE/NAME") or "<unnamed>"
        raise ValueError(f"cannot find the physical NODE for device {name!r}")
    return node


def _safe_empty_config(device):
    """Replace user IOS state with a small, model-neutral boot configuration."""
    engine = device.find("ENGINE")
    device_type = (engine.findtext("TYPE") or "").strip().lower()
    name = engine.findtext("NAME") or "PT-DEVICE"
    power = engine.find("POWER")
    if power is not None:
        power.text = "true"
    description = engine.find("DESCRIPTION")
    if description is not None:
        description.text = ""

    # The version string is a simulator boot default. Do not copy user commands
    # from either config buffer into a new model instance.
    version = "15.1"
    for tag in ("RUNNINGCONFIG", "STARTUPCONFIG"):
        config = engine.find(tag)
        if config is not None:
            for line in config.findall("LINE"):
                match = re.match(r"\s*version\s+(\S+)", line.text or "", re.I)
                if match:
                    version = match.group(1)
                    break

    if device_type in {"router", "switch", "multilayerswitch"}:
        clean_lines = ["!", f"version {version}",
                       "no service timestamps log datetime msec",
                       "no service timestamps debug datetime msec",
                       "no service password-encryption", "!",
                       f"hostname {name}", "!", "end"]
    else:
        clean_lines = []

    for tag in ("RUNNINGCONFIG", "STARTUPCONFIG"):
        config = engine.find(tag)
        if config is None:
            config = ET.SubElement(engine, tag)
        config.clear()
        for line in clean_lines:
            ET.SubElement(config, "LINE").text = line

    # User addressing on a physical port belongs to the old network. Clear it
    # while preserving each native PORT and its hardware-specific settings.
    for port in engine.findall(".//PORT"):
        for tag in ("IP", "SUBNET", "PORT_GATEWAY", "PORT_DNS",
                    "IPV6_PORT_GATEWAY", "IPV6_PORT_DNS", "IPV6_LINK_LOCAL",
                    "IPV6_ADDRESSES", "IP_UNNUMBERED"):
            el = port.find(tag)
            if el is not None:
                el.text = ""
        for tag in ("PORT_DHCP_ENABLE", "IPV6_ENABLED",
                    "IPV6_ADDRESS_AUTOCONFIG", "IPV6_PORT_DHCP_ENABLED"):
            el = port.find(tag)
            if el is not None:
                el.text = "false"
        dhcp_server = port.find("DHCP_SERVER_IP")
        if dhcp_server is not None:
            dhcp_server.text = "0.0.0.0"

    for tag in ("GATEWAY", "GATEWAYV6"):
        el = engine.find(tag)
        if el is not None:
            el.text = ""

    dns_client = engine.find("DNS_CLIENT")
    if dns_client is not None:
        for tag in ("SERVER_IP", "SERVER_IPV6"):
            for server in dns_client.findall(tag):
                server.text = ""

    dhcp_client = engine.find("DHCP_CLIENT")
    if dhcp_client is not None:
        for entry in dhcp_client.findall(".//PORT_DATA_ENTRY"):
            port = entry.find("PORT")
            if port is not None:
                port_copy = ET.fromstring(_serialize(port))
                entry.clear()
                entry.append(port_copy)
            else:
                entry.clear()

    if device_type in {"switch", "multilayerswitch"}:
        vlans = engine.find("VLANS")
        if vlans is not None:
            vlans.clear()
            defaults = (("default", "1"), ("fddi-default", "1002"),
                        ("token-ring-default", "1003"),
                        ("fddinet-default", "1004"),
                        ("trnet-default", "1005"))
            for vlan_name, number in defaults:
                ET.SubElement(vlans, "VLAN", {
                    "name": vlan_name, "number": number, "rspan": "0"})

    security = engine.find("SECURITY")
    if security is not None:
        for tag in ("KEY_NAME", "TEMP_KEY_NAME", "RSA_KEY", "TEMP_RSA_KEY",
                    "TIME_DATE"):
            el = security.find(tag)
            if el is not None:
                el.text = ""
        enabled = security.find("ENABLED")
        if enabled is not None:
            enabled.text = "0"
        bits = security.find("MODULUS_BITS")
        if bits is not None:
            bits.text = "0"


def _serialize(element):
    return ET.tostring(element, encoding="unicode")


def _write_template(librarydir, device, physical_node, source_path):
    device_type, model = _template_identity(device)
    clean = ET.fromstring(_serialize(device))
    clean_node = ET.fromstring(_serialize(physical_node))
    _safe_empty_config(clean)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "type": device_type,
        "model": model,
        "source_device": clean.findtext("ENGINE/NAME") or "",
        "source_file": str(source_path),
        "device_xml": _serialize(clean),
        "physical_node_xml": _serialize(clean_node),
    }
    directory = _library_dir(librarydir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{_slug(device_type)}--{_slug(model)}.json"
    path = directory / filename
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(metadata, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    temporary.replace(path)
    return {"type": device_type, "model": model,
            "source_device": metadata["source_device"], "path": str(path)}


def import_file(decodedXMLpath, librarydir=None, deviceName=None):
    """Import native model template(s) from a decoded Packet Tracer XML file.

    If ``deviceName`` is supplied, only that device is imported. Otherwise one
    template per distinct type/model pair is imported from the file. Returns
    the imported model metadata rows.
    """
    source_path = Path(decodedXMLpath)
    root = ET.parse(source_path).getroot()
    devices = root.findall("NETWORK/DEVICES/DEVICE")
    if not devices:
        raise ValueError("XML contains no NETWORK/DEVICES/DEVICE templates")

    physical = root.find("PHYSICALWORKSPACE")
    if physical is None:
        raise ValueError("XML contains no PHYSICALWORKSPACE with native NODEs")
    node_by_uuid = {}
    nodes_by_name = {}
    for node in physical.iter("NODE"):
        uid = _uuid_key(node.findtext("UUID_STR"))
        if uid:
            node_by_uuid[uid] = node
        name = _normalize(node.findtext("NAME"))
        if name:
            nodes_by_name.setdefault(name, []).append(node)

    if deviceName is not None:
        needle = _normalize(deviceName)
        matches = [d for d in devices
                   if _normalize(d.findtext("ENGINE/NAME")) == needle]
        if not matches:
            raise KeyError(f"no device named {deviceName!r} in {source_path}")
        if len(matches) > 1:
            raise ValueError(f"device name {deviceName!r} is not unique in XML")
        selected = matches
    else:
        selected = []
        seen = set()
        for device in devices:
            try:
                key = tuple(_normalize(v) for v in _template_identity(device))
            except ValueError:
                continue
            if key not in seen:
                selected.append(device)
                seen.add(key)
        if not selected:
            raise ValueError("XML contains no devices with a type and model")

    imported = []
    for device in selected:
        node = _physical_node_for(device, node_by_uuid, nodes_by_name)
        imported.append(_write_template(librarydir, device, node, source_path))
    return imported


def _read_template(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported model template schema in {path}")
    if not data.get("device_xml") or not data.get("physical_node_xml"):
        raise ValueError(f"incomplete native model template in {path}")
    return data


def list_models(librarydir=None):
    """Return available native template metadata, sorted by type and model."""
    directory = _library_dir(librarydir)
    if not directory.exists():
        return []
    rows = []
    for path in sorted(directory.glob("*.json")):
        data = _read_template(path)
        rows.append({"type": data["type"], "model": data["model"],
                     "source_device": data.get("source_device", ""),
                     "source_file": data.get("source_file", ""),
                     "path": str(path)})
    return rows


def add_device(topology, type, model, name, x=None, y=None, librarydir=None):
    """Add a clean instance of a native ``type``/``model`` to a topology."""
    wanted = (_normalize(type), _normalize(model))
    matches = []
    for path in _library_dir(librarydir).glob("*.json"):
        data = _read_template(path)
        key = (_normalize(data.get("type")), _normalize(data.get("model")))
        if key == wanted:
            matches.append((path, data))
    if not matches:
        available = [f"{r['type']} ({r['model']})" for r in list_models(librarydir)]
        raise KeyError(f"native model {type!r} ({model!r}) is not in the library; "
                       f"available: {available}")
    if len(matches) > 1:
        raise ValueError(f"multiple templates match {type!r} ({model!r})")

    _, data = matches[0]
    device = ET.fromstring(data["device_xml"])
    node = ET.fromstring(data["physical_node_xml"])
    _safe_empty_config(device)
    return topology._add_native_device(device, node, name=name, x=x, y=y)
