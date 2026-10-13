#!/usr/bin/env python3
"""Build the bundled live backend and prepare local Cisco IPC registration."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
JAVA = ROOT / "backend" / "java"
SDK_NAME = "pt-cep-java-framework-9.0.0.0.jar"
PRIVILEGES = (
    "GET_NETWORK_INFO", "CHANGE_NETWORK_INFO", "SIMULATION_MODE",
    "MISC_GUI", "FILE", "CHANGE_GUI", "APPLICATION",
)


def installed_roots(extra: Path | None) -> list[Path]:
    candidates = ([extra] if extra else []) + [
        Path("/opt/pt"), Path("/usr/local/PacketTracer"),
        *sorted(Path("/tmp").glob(".mount_packet*/opt/pt")),
    ]
    return [path for path in candidates if path.is_dir()]


def find_file(roots: list[Path], relative: str) -> Path | None:
    return next((root / relative for root in roots
                 if (root / relative).is_file()), None)


def credentials() -> tuple[str, str]:
    configured = Path(os.environ.get("PT_MCP_CONFIG", "local.properties"))
    path = configured if configured.is_absolute() else JAVA / configured
    values = {}
    if path.exists():
        # Read the credential entries, including Java Unicode and character escapes.
        for line in path.read_text(encoding="iso-8859-1").splitlines():
            if line.lstrip().startswith(("#", "!")):
                continue
            key, sep, value = line.partition("=")
            if sep:
                def unescape(match: re.Match) -> str:
                    if match.group(1):
                        return chr(int(match.group(1), 16))
                    char = match.group(2)
                    return {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}.get(char, char)
                decoded = re.sub(r"\\(?:u([0-9a-fA-F]{4})|(.))", unescape, value.strip())
                values[key.strip()] = decoded.encode("utf-16-be", errors="surrogatepass").decode("utf-16-be")
    app = (os.environ.get("PT_MCP_AUTH_APPLICATION")
           or values.get("pt.mcp.auth.application", ""))
    secret = (os.environ.get("PT_MCP_AUTH_SECRET")
              or values.get("pt.mcp.auth.secret", ""))
    if not path.exists():
        app = app or "local.ptmcp.connector"
        secret = secret or secrets.token_hex(32)
    if (not app or not secret or app == "com.example.ptmcp.connector"
            or app.startswith("REPLACE_") or secret.startswith("REPLACE_")):
        raise RuntimeError("Configure real IPC credentials in local.properties or PT_MCP_AUTH_*.")
    if not path.exists():
        # Escape properties values using UTF-16 units, as java.util.Properties reads them.
        def escaped(value: str) -> str:
            encoded = value.encode("utf-16-be")
            return "".join("\\u" + encoded[i:i + 2].hex()
                           for i in range(0, len(encoded), 2))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="ascii") as handle:
            # Defaults are ASCII and remain readable. Overrides are stored with
            # Java escaping so future launches can use them without environment overrides.
            stored_app = escaped(app) if os.environ.get("PT_MCP_AUTH_APPLICATION") else app
            stored_secret = escaped(secret) if os.environ.get("PT_MCP_AUTH_SECRET") else secret
            handle.write(f"pt.mcp.auth.application={stored_app}\npt.mcp.auth.secret={stored_secret}\n")
    path.chmod(0o600)
    return app, secret


def write_registration(meta: Path, version: str) -> Path:
    app, secret = credentials()
    manifest = ET.parse(JAVA / "pta/ptmcp/ptmcp.xml.template")
    root = manifest.getroot()
    for tag, value in {
        "PT_VERSION": version, "ID": app, "KEY": secret,
        "EXECUTABLE_PATH": str(JAVA / "build/install/pt-mcp/bin/pt-mcp"),
        "AUTHOR": "Local Packet Tracer MCP", "CONTACT": "local",
    }.items():
        root.find(tag).text = value
    security = root.find("SECURITY_SETTINGS")
    security.clear()
    for name in PRIVILEGES:
        ET.SubElement(security, "PRIVILEGE").text = name
    xml = JAVA / "pta/ptmcp/ptmcp.xml"
    pta = xml.with_suffix(".pta")
    # Use temporary output so a failed meta invocation preserves registration.
    with tempfile.TemporaryDirectory(prefix="pt-mcp-registration-") as temporary:
        temp_xml = Path(temporary) / "ptmcp.xml"
        temp_pta = Path(temporary) / "ptmcp.pta"
        manifest.write(temp_xml, encoding="iso-8859-1", xml_declaration=True)
        result = subprocess.run([str(meta), str(temp_pta), str(temp_xml)],
                                capture_output=True, text=True)
        if result.returncode or not temp_pta.is_file():
            raise RuntimeError("Cisco meta could not generate registration; check its local runtime libraries.")
        shutil.copy2(temp_xml, xml)
        shutil.copy2(temp_pta, pta)
    xml.chmod(0o600)
    pta.chmod(0o600)
    return pta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-jar", type=Path, help="Cisco SDK JAR from your PT installation")
    parser.add_argument("--meta", type=Path, help="Cisco meta executable from your PT installation")
    parser.add_argument("--packet-tracer-root", type=Path, help="Extracted PT directory containing bin/ and help/")
    parser.add_argument("--appimage", type=Path, help="Linux Packet Tracer AppImage to extract local SDK/meta")
    parser.add_argument("--pt-version", default="9.0.1", help="Installed PT version for registration (default: 9.0.1)")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        java_home = os.environ.get("JAVA_HOME")
        java = str(Path(java_home) / "bin/java") if java_home else shutil.which("java")
        javac = str(Path(java_home) / "bin/javac") if java_home else shutil.which("javac")
        if not java or not javac or not Path(java).is_file() or not Path(javac).is_file():
            raise RuntimeError("Install JDK 21 (java and javac) before running setup.")
        version = subprocess.run([javac, "-version"], capture_output=True, text=True, check=True)
        if not re.search(r"javac 21(?:\.|\s|$)", version.stdout + version.stderr):
            raise RuntimeError("Select JDK 21 using JAVA_HOME or PATH before running setup.")
        runtime = subprocess.run([java, "-version"], capture_output=True, text=True, check=True)
        if not re.search(r'version "21(?:\.|"|-)', runtime.stdout + runtime.stderr):
            raise RuntimeError("Select Java runtime 21 using JAVA_HOME or PATH before running setup.")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", args.pt_version):
            raise RuntimeError("--pt-version must be a numeric Packet Tracer version.")
        with ExitStack() as stack:
            roots = installed_roots(args.packet_tracer_root)
            destination = JAVA / "libs" / SDK_NAME
            sdk = args.sdk_jar or (destination if destination.is_file()
                                  else find_file(roots, "help/default/ipc/" + SDK_NAME))
            meta = args.meta or find_file(roots, "bin/meta")
            if not sdk or not meta:
                appimage = args.appimage or Path("/opt/pt/packettracer.AppImage")
                extractor = shutil.which("unsquashfs")
                if appimage.is_file() and extractor:
                    temporary = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="pt-mcp-sdk-")))
                    offset = subprocess.run([str(appimage.resolve()), "--appimage-offset"],
                                            capture_output=True, text=True, check=True).stdout.strip()
                    if not offset.isdecimal():
                        raise RuntimeError("Packet Tracer AppImage did not report a valid filesystem offset.")
                    extracted = subprocess.run([
                        extractor, "-no-xattrs", "-o", offset, "-d", str(temporary),
                        str(appimage.resolve()), "opt/pt/bin/meta",
                        "opt/pt/help/default/ipc/" + SDK_NAME,
                    ], capture_output=True, text=True)
                    if extracted.returncode:
                        raise RuntimeError("Could not extract Cisco SDK/meta from the supplied AppImage.")
                    roots.append(temporary / "opt/pt")
                    sdk = sdk or find_file(roots, "help/default/ipc/" + SDK_NAME)
                    meta = meta or find_file(roots, "bin/meta")
            if not sdk or not sdk.is_file():
                raise RuntimeError("Cisco SDK missing: supply --sdk-jar or --packet-tracer-root (or AppImage with unsquashfs).")
            if not meta or not meta.is_file() or not os.access(meta, os.X_OK):
                raise RuntimeError("Cisco meta missing: supply --meta or --packet-tracer-root (or AppImage with unsquashfs).")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if sdk.resolve() != destination.resolve():
                shutil.copy2(sdk, destination)
            credentials()
            wrapper = JAVA / "gradlew"
            wrapper.chmod(wrapper.stat().st_mode | 0o100)
            subprocess.run([str(wrapper), "installDist", "--console=plain"], cwd=JAVA, check=True)
            pta = write_registration(meta.resolve(), args.pt_version)
        print("\nSetup complete: bundled Java backend built; credentials preserved or generated locally.")
        print(f"Connector registration: {pta}")
        print("In Packet Tracer Configure Apps, add this registration (replace only PT MCP Connector if already listed).")
        print("Enable local IPC on port 39000; the MCP client starts Java automatically.")
        print(f"MCP command: {sys.executable} {ROOT / 'server.py'}")
        return 0
    except (OSError, RuntimeError, UnicodeError, subprocess.CalledProcessError) as exc:
        # Child command output may contain sensitive configuration; do not echo it.
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
