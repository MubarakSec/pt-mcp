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

Everything else is cloned verbatim. The one thing this cannot yet do is
synthesise a device *model* that was not already in the file -- a brand new
model needs a hand-written MODULE/PORT tree.
"""
import copy
import itertools
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
        for n in itertools.count(2):
            mac = f"00E0.{n:04X}.{0x1000 + n:04X}"
            if mac not in used:
                return mac
        raise RuntimeError("exhausted")

    def _mint_serial(self):
        used = self._existing_serials()
        for n in itertools.count(1):
            s = f"PTT{n:08d}X"
            if s not in used:
                return s
        raise RuntimeError("exhausted")

    # ---------------------------------------------------------- clone

    def clone_device(self, source, name, x=None, y=None, mac=None):
        """Duplicate an existing device under a new name at a new position."""
        src = self.device(source)
        new = copy.deepcopy(src)
        eng = new.find("ENGINE")

        eng.find("SAVE_REF_ID").text = self._mint_ref()
        eng.find("NAME").text = name

        # a PC's identity inside IOS is its hostname; keep it consistent
        sn = eng.find("SYS_NAME")
        if sn is not None and sn.text:
            sn.text = name

        ser = eng.find("SERIALNUMBER")
        if ser is not None:
            ser.text = self._mint_serial()

        new_mac = mac or self._mint_mac()
        for tag in ("MACADDRESS", "BIA"):
            el = eng.find(f".//{tag}")
            if el is not None:
                el.text = new_mac
        ll = eng.find(".//IPV6_LINK_LOCAL")
        if ll is not None and ll.text:
            ll.text = "FE80::" + new_mac.replace(".", "").lower()

        # unique session pointers
        base = max(self._existing_mem() or [97637700000000])
        base += 1_000_000
        log = new.find("WORKSPACE/LOGICAL")
        if log is not None:
            m = log.find("MEM_ADDR")
            d = log.find("DEV_ADDR")
            if m is not None:
                m.text = str(base)
            if d is not None:
                d.text = str(base + 32)

        if x is not None:
            log.find("X").text = str(x)
        if y is not None:
            log.find("Y").text = str(y)

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
