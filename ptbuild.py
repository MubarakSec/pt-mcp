#!/usr/bin/env python3
"""
ptbuild.py - programmatic Packet Tracer topology builder.

Works on the XML that `unpacket` produces, then `repacket` turns back into a
loadable .pkt.

    import ptbuild as B
    t = B.load("lab.xml")
    sw1 = t.device("SW1")
    pc = t.clone_device("PC0", name="PC10", x=700, y=560)
    t.add_cable("SW1", "FastEthernet0/11", "PC10", "FastEthernet0")
    t.save("lab.xml")

Identity model, learned from real files:
  ENGINE/SAVE_REF_ID      stable id; LINKS/FROM|TO, DCEDEV and PDU/SOURCE key on it
  WORKSPACE/LOGICAL/MEM_ADDR, DEV_ADDR
                          session memory pointers, must be unique per device
  PORT/MACADDRESS + BIA   must be unique per port
  ENGINE/SERIALNUMBER     unique per device
  WORKSPACE/PHYSICAL      UUID path into GEOVIEW_GRAPHICSITEMS (visual skin)

Native device templates can be imported into ``model_library`` and added
without synthesizing a hardware MODULE/PORT tree. A physical NODE is cloned
into the target's existing physical container so Packet Tracer can resolve
the device in both workspaces.
"""
import copy
import itertools
import re
import xml.etree.ElementTree as ET


class Topology:
    def __init__(self, root):
        self.root = root
        self.net = root.find("NETWORK")
        if self.net is None:
            raise ValueError("no <NETWORK> element; not a PACKETTRACER5 file")
        self.devices = self.net.find("DEVICES")
        self.links = self.net.find("LINKS")

    # ---------------------------------------------------------- load/save

    @classmethod
    def load(cls, path):
        return cls(ET.parse(path).getroot())

    def save(self, path):
        tree = ET.ElementTree(self.root)
        tree.write(path, encoding="utf-8", xml_declaration=True)
        return path

    # ---------------------------------------------------------- lookup

    def device(self, name):
        for d in self.devices.findall("DEVICE"):
            if d.find("ENGINE").findtext("NAME") == name:
                return d
        raise KeyError(f"no device named {name!r}")

    def ref(self, name):
        return self.device(name).find("ENGINE").findtext("SAVE_REF_ID")

    def name_of(self, ref):
        for d in self.devices.findall("DEVICE"):
            if d.find("ENGINE").findtext("SAVE_REF_ID") == ref:
                return d.find("ENGINE").findtext("NAME")
        return ref

    # ---------------------------------------------------------- id minting

    def _existing_refs(self):
        return {d.find("ENGINE").findtext("SAVE_REF_ID")
                for d in self.devices.findall("DEVICE")}

    def _existing_mem(self):
        vals = []
        for d in self.devices.findall("DEVICE"):
            log = d.find("WORKSPACE/LOGICAL")
            if log is None:
                continue
            for tag in ("MEM_ADDR", "DEV_ADDR"):
                v = log.findtext(tag)
                if v and v.isdigit():
                    vals.append(int(v))
        return vals

    def _existing_macs(self):
        macs = set()
        for e in self.root.iter("MACADDRESS"):
            if e.text:
                macs.add(e.text)
        for e in self.root.iter("BIA"):
            if e.text:
                macs.add(e.text)
        return macs

    def _existing_serials(self):
        out = set()
        for d in self.devices.findall("DEVICE"):
            s = d.find("ENGINE").findtext("SERIALNUMBER")
            if s:
                out.add(s)
        return out

    def _mint_ref(self):
        # 20-digit ids, same shape PT uses
        used = self._existing_refs()
        n = 10000000000000000000
        while f"save-ref-id:{n}" in used:
            n += 1
        return f"save-ref-id:{n}"

    def _mint_mac(self):
        used = self._existing_macs()
        return self._mint_mac_from(used)

    @staticmethod
    def _mint_mac_from(used):
        for n in itertools.count(2):
            mac = f"00E0.{n:04X}.{0x1000 + n:04X}"
            if mac not in used:
                used.add(mac)
                return mac
        raise RuntimeError("exhausted")

    def _mint_serial(self):
        used = self._existing_serials()
        for n in itertools.count(1):
            s = f"PTT{n:08d}X"
            if s not in used:
                return s
        raise RuntimeError("exhausted")

    # ------------------------------------------------------ physical placement

    def _find_physical_node(self, device):
        physical = self.root.find("PHYSICALWORKSPACE")
        if physical is None:
            raise ValueError("no PHYSICALWORKSPACE element")
        workspace = device.find("WORKSPACE")
        path = workspace.findtext("PHYSICAL") if workspace is not None else ""
        wanted = (path or "").split(",")[-1].strip().strip("{}").lower()
        if wanted:
            for node in physical.iter("NODE"):
                if (node.findtext("UUID_STR") or "").strip().strip("{}").lower() == wanted:
                    return node
        name = device.findtext("ENGINE/NAME")
        matches = [node for node in physical.iter("NODE")
                   if (node.findtext("NAME") or "").strip().lower() ==
                   (name or "").strip().lower()]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"cannot resolve physical NODE for {name!r}")

    @staticmethod
    def _next_physical_position(node, siblings):
        x_el, y_el = node.find("X"), node.find("Y")
        if x_el is None or y_el is None:
            return None
        try:
            x0, y0 = float(x_el.text or 0), float(y_el.text or 0)
        except ValueError:
            return None
        coords = set()
        for sibling in siblings:
            sx, sy = sibling.findtext("X"), sibling.findtext("Y")
            try:
                coords.add((float(sx), float(sy)))
            except (TypeError, ValueError):
                continue
        if (x0, y0) not in coords:
            return x0, y0
        max_coord = max([abs(x0), abs(y0)] + [abs(p[0]) for p in coords])
        step = 1 if max_coord < 20 else 100
        for offset in itertools.count(1):
            candidate = (x0 + offset * step, y0)
            if candidate not in coords:
                return candidate

    def _attach_physical_node(self, new, node_template, anchor):
        """Attach a native NODE under the target's existing physical parent."""
        physical = self.root.find("PHYSICALWORKSPACE")
        if physical is None:
            raise ValueError("no PHYSICALWORKSPACE element")
        anchor_node = self._find_physical_node(anchor)
        anchor_workspace = anchor.find("WORKSPACE")
        anchor_path = (anchor_workspace.findtext("PHYSICAL") or "").split(",")
        if not anchor_path or not anchor_path[-1].strip():
            raise ValueError("anchor device has no physical path")
        parent_map = {child: parent for parent in physical.iter()
                      for child in list(parent)}
        siblings = parent_map.get(anchor_node)
        if siblings is None or siblings.tag != "CHILDREN":
            raise ValueError("anchor physical NODE has no parent CHILDREN container")

        node = copy.deepcopy(node_template)
        name = new.findtext("ENGINE/NAME") or ""
        name_el = node.find("NAME")
        if name_el is None:
            name_el = ET.SubElement(node, "NAME")
        name_el.text = name
        uid = "{" + _uuid() + "}"
        uid_el = node.find("UUID_STR")
        if uid_el is None:
            uid_el = ET.SubElement(node, "UUID_STR")
        uid_el.text = uid

        # Avoid overlapping the anchor in the physical view while preserving
        # the coordinate scale used by its room/rack.
        for tag in ("X", "Y"):
            value = anchor_node.findtext(tag)
            target_el = node.find(tag)
            if value is not None and target_el is not None:
                target_el.text = value
        position = self._next_physical_position(node, list(siblings))
        if position is not None:
            node.find("X").text = str(position[0])
            node.find("Y").text = str(position[1])
        siblings.append(node)

        anchor_path[-1] = uid
        workspace = new.find("WORKSPACE")
        if workspace is None:
            workspace = ET.SubElement(new, "WORKSPACE")
        path_el = workspace.find("PHYSICAL")
        if path_el is None:
            path_el = ET.SubElement(workspace, "PHYSICAL")
        path_el.text = ",".join(anchor_path)

        # Path and container fields from the imported template belong to its
        # source file. Point them at the target's actual physical container.
        source_cpur = workspace.find("PHYSICAL_CPUR")
        anchor_cpur = (anchor_workspace.find("PHYSICAL_CPUR")
                       if anchor_workspace is not None else None)
        if source_cpur is not None and anchor_cpur is not None:
            for tag in ("PARENT_PATH", "CONTAINER_ID", "ICP_CONTAINER_SCENE_X",
                        "ICP_CONTAINER_SCENE_Y"):
                source_el, anchor_el = source_cpur.find(tag), anchor_cpur.find(tag)
                if source_el is not None and anchor_el is not None:
                    source_el.text = anchor_el.text
            if position is not None:
                for tag, value in zip(("X", "Y"), position):
                    el = source_cpur.find(tag)
                    if el is not None:
                        el.text = str(value)
        return node

    # ------------------------------------------------------ device identities

    def _prepare_device_identity(self, new, name, x=None, y=None, mac=None):
        eng = new.find("ENGINE")
        if eng is None:
            raise ValueError("device template has no ENGINE element")
        names = {d.findtext("ENGINE/NAME") for d in self.devices.findall("DEVICE")}
        if name in names:
            raise ValueError(f"device name already exists: {name!r}")

        ref = eng.find("SAVE_REF_ID")
        if ref is not None:
            ref.text = self._mint_ref()
        name_el = eng.find("NAME")
        if name_el is None:
            name_el = ET.SubElement(eng, "NAME")
        name_el.text = name

        # A PC's IOS hostname is stored separately from its displayed name.
        sys_name = eng.find("SYS_NAME")
        if sys_name is not None and sys_name.text:
            sys_name.text = name
        for config_tag in ("RUNNINGCONFIG", "STARTUPCONFIG"):
            config = eng.find(config_tag)
            if config is not None:
                for line in config.findall("LINE"):
                    if re.match(r"\s*hostname\s+", line.text or "", re.I):
                        line.text = f"hostname {name}"
        serial = eng.find("SERIALNUMBER")
        if serial is not None:
            serial.text = self._mint_serial()

        used_macs = self._existing_macs()
        requested_mac = mac
        for port in eng.findall(".//PORT"):
            mac_el, bia_el = port.find("MACADDRESS"), port.find("BIA")
            if mac_el is None and bia_el is None:
                continue
            if requested_mac is not None:
                new_mac = requested_mac
                if new_mac in used_macs:
                    raise ValueError(f"MAC address already exists: {new_mac}")
                used_macs.add(new_mac)
                requested_mac = None
            else:
                new_mac = self._mint_mac_from(used_macs)
            if mac_el is not None:
                mac_el.text = new_mac
            if bia_el is not None:
                bia_el.text = new_mac

            parts = new_mac.replace(".", "")
            if len(parts) == 12:
                first = int(parts[0:2], 16) ^ 0x02
                eui = f"{first:02x}{parts[2:6]}fffe{parts[6:12]}"
                groups = ":".join(eui[i:i + 4] for i in range(0, 16, 4))
                for tag in ("IPV6_LINK_LOCAL", "IPV6_DEFAULT_LINK_LOCAL"):
                    ll = port.find(tag)
                    if ll is not None and ll.text:
                        ll.text = "FE80::" + groups

        built_in = eng.find("BUILD_IN_ADDR")
        if built_in is not None and built_in.text:
            built_in.text = self._mint_mac_from(used_macs)

        base = max(self._existing_mem() or [97637700000000]) + 1_000_000
        log = new.find("WORKSPACE/LOGICAL")
        if log is not None:
            mem, dev = log.find("MEM_ADDR"), log.find("DEV_ADDR")
            if mem is not None:
                mem.text = str(base)
            if dev is not None:
                dev.text = str(base + 32)
            if x is not None and log.find("X") is not None:
                log.find("X").text = str(x)
            if y is not None and log.find("Y") is not None:
                log.find("Y").text = str(y)

    def _add_native_device(self, device, physical_node, name, x=None, y=None):
        """Internal entry used by model_library after loading a native template."""
        existing = self.devices.findall("DEVICE")
        if not existing:
            raise ValueError("cannot infer a physical container in an empty topology")
        anchor = existing[0]
        self._prepare_device_identity(device, name, x=x, y=y)
        self._attach_physical_node(device, physical_node, anchor)
        self.devices.append(device)
        return device

    def add_device(self, type, model, name, x=None, y=None, librarydir=None):
        """Add a clean imported native type/model from the local library."""
        try:
            from .model_library import add_device
        except ImportError:
            from model_library import add_device
        return add_device(self, type, model, name, x=x, y=y,
                          librarydir=librarydir)

    # ---------------------------------------------------------- clone

    def clone_device(self, source, name, x=None, y=None, mac=None):
        """Duplicate an existing device under a new name at a new position."""
        src = self.device(source)
        new = copy.deepcopy(src)
        self._prepare_device_identity(new, name, x=x, y=y, mac=mac)
        source_node = self._find_physical_node(src)
        self._attach_physical_node(new, source_node, src)
        self.devices.append(new)
        return new

    # ---------------------------------------------------------- cabling

    def _cable_template(self):
        for l in self.links.findall("LINK"):
            return l
        raise RuntimeError("file has no links to use as a template")

    def add_cable(self, a, a_port, b, b_port, kind="eCopper"):
        """Add a cable between two devices by interface name."""
        tpl = None
        for l in self.links.findall("LINK"):
            if l.findtext("TYPE") == kind:
                tpl = l
                break
        if tpl is None:
            tpl = self._cable_template()

        link = copy.deepcopy(tpl)
        link.find("TYPE").text = kind
        cab = link.find("CABLE")
        # a serial template carries DCE fields a copper cable must not keep
        for tag in ("DCEDEV", "DCEPORT"):
            el = cab.find(tag)
            if el is not None and kind != "eSerial":
                cab.remove(el)

        ports = cab.findall("PORT")
        ports[0].text = a_port
        ports[1].text = b_port
        cab.find("FROM").text = self.ref(a)
        cab.find("TO").text = self.ref(b)

        mem = self._existing_mem() or [97637700000000]
        base = max(mem) + 500_000
        cab.find("FROM_DEVICE_MEM_ADDR").text = str(base)
        cab.find("TO_DEVICE_MEM_ADDR").text = str(base + 32)
        cab.find("FROM_PORT_MEM_ADDR").text = str(base + 64)
        cab.find("TO_PORT_MEM_ADDR").text = str(base + 96)
        cab.find("LENGTH").text = "1"
        cab.find("FUNCTIONAL").text = "true"

        if kind == "eSerial":
            if cab.find("DCEDEV") is None:
                cab.append(ET.SubElement(cab, "DCEDEV"))
            cab.find("DCEDEV").text = self.ref(b)
            cab.find("DCEPORT").text = b_port

        self.links.append(link)
        return link

    # ---------------------------------------------------------- notes

    def add_note(self, text, x=100, y=100, z=40000):
        ws = self.root.find("PHYSICALWORKSPACE")
        notes = ws.find("NOTES")
        if notes is None:
            notes = ET.SubElement(ws, "NOTES")
        note = ET.SubElement(notes, "NOTE", {"uuid": "{%s}" % _uuid()})
        ET.SubElement(note, "X").text = str(x)
        ET.SubElement(note, "Y").text = str(y)
        ET.SubElement(note, "Z").text = str(z)
        ET.SubElement(note, "TEXT", {"translate": "true"}).text = text
        ET.SubElement(note, "NOTECLUSTERID").text = "1-1"
        return note

    # ---------------------------------------------------------- report

    def summary(self):
        devs = [d.find("ENGINE").findtext("NAME") for d in self.devices.findall("DEVICE")]
        return {"devices": len(devs), "links": len(self.links.findall("LINK")), "names": devs}


def _uuid():
    import uuid
    return str(uuid.uuid4())
