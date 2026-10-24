# pt-mcp — Packet Tracer saved files and live simulator

Version **0.6.0** exposes 63 MCP tools: 27 offline tools (22 saved-file/build, three native-model library, and two diagram tools), 35 live simulator tools, and `pt_live_status`. New live wrappers await SDK compilation and local Packet Tracer verification; see [implementation evidence](docs/IMPLEMENTATION-EVIDENCE.md).

The Python server handles `.pkt`/XML inspection and copy-based editing. Its optional Java backend controls a running Packet Tracer simulator over IPC. The Java source now lives inside this repository at `backend/java`; no sibling checkout is required.

## Setup

For offline `.pkt` reading and editing, Python 3 is enough:

```sh
python3 server.py
```

For the combined offline and live server, install JDK 21 and Cisco Packet Tracer, then run this once from the repository root:

```sh
python3 setup.py
```

The setup script locates Packet Tracer's SDK JAR and `meta` utility, copies the local proprietary SDK into the ignored Java build directory, creates or reuses local IPC credentials, builds the Java backend, and generates the Packet Tracer app registration file. Fresh installs still require adding that registration in Packet Tracer's Configure Apps screen and enabling IPC; see [LIVE-SETUP.md](LIVE-SETUP.md).

If auto-detection cannot find the Packet Tracer installation, pass explicit locations:

```sh
python3 setup.py --packet-tracer-root /path/to/extracted/packet-tracer
python3 setup.py --appimage /path/to/packettracer.AppImage
python3 setup.py --sdk-jar /path/to/pt-cep-java-framework-9.0.0.0.jar --meta /path/to/meta
```

Use `python3 setup.py --help` for all options, including `--pt-version`. Linux AppImage extraction requires `unsquashfs`. The live backend requires the locally installed Cisco SDK and `meta`; they are not redistributed here. The offline tools do not require JDK, Packet Tracer, or the Java SDK.

Once configured, keep the MCP client command pointed at this repository's `server.py`. For example:

```text
python3 /absolute/path/to/pt-mcp/server.py
```

Reload the MCP connection or start a new client session after setup to discover the combined tool set.

## Layout

```text
pt-mcp/
├── setup.py          one-command Java/IPC setup
├── server.py         combined MCP server
├── live_bridge.py    lazy stdio bridge to the live backend
├── live_tools.json   checked-in live tool catalog for offline startup
├── ptbuild.py        copy-based saved-topology builder
├── diagrams.py       deterministic planner and standalone SVG renderer
├── diagram_tools.py  offline diagram/build-copy tool contracts
├── model_library.py  native Packet Tracer model import/list/add
├── ptread.py         saved-topology reader
├── unpacket.py       .pkt → XML
├── repacket.py       XML → .pkt
├── Decipher/         vendored crypto implementation
└── backend/java/     bundled Java IPC backend and Gradle wrapper
```

See [LIVE-SETUP.md](LIVE-SETUP.md) for IPC registration, live tool behavior, verification scope, and troubleshooting.

## Development and cloud-agent handoff

For the next implementation work, read [AGENTS.md](AGENTS.md), the [improvement backlog](IMPROVEMENTS.md), the [cloud development brief](docs/CLOUD-HANDOFF.md), and the [inspected SDK capabilities](docs/SDK-CAPABILITIES.md).

Implemented additions include IOS failure classification and bounded CLI batches, live naming/positioning/notes, deterministic grouped layout planning, explicit layout application and portable SVG export. See the [workflow and input contracts](docs/DIAGRAMS.md) and [50-PC campus example](examples/campus-50.svg). Readiness, simulation/PDU and command-history expansion remain later roadmap work.

A cloud coding agent can implement code and run offline tests without a simulator. Java compilation needs the legitimate Cisco SDK; live acceptance tests additionally need Packet Tracer with registered IPC access. Cloud development does not automatically make the local simulator remotely accessible. Record offline tests, SDK compilation and live verification separately.

## Saved-file behavior

- Read tools inspect a saved `.pkt` or XML and only cache decoded XML under `/tmp/pt-mcp-cache/`.
- Build tools operate on a separate copy. Saving refuses to overwrite the source unless `allow_overwrite: true` is supplied.
- `pt_build_clone` duplicates models already present in the file. `pt_model_import`, `pt_model_list`, and `pt_build_add_device` support importing a native hardware template and adding a model absent from the file.
- `pt_build_set_config` writes the same CLI text to saved `STARTUPCONFIG` and `RUNNINGCONFIG`. A running device may show the change only after reboot.

The original saved-file tools remain available if the Java backend or live IPC is missing. Live operations affect the currently open simulator and are independent of saved-file build sessions.

## Preserved tools

The original 21 tools remain registered: `pt_list_files`, `pt_open`, `pt_overview`, `pt_devices`, `pt_device_detail`, `pt_config`, `pt_links`, `pt_notes`, `pt_pdus`, `pt_search`, `pt_command_logs`, and ten `pt_build_*` tools for copy, clone, cable, note, rename, delete, config, and save operations.

## Historical verification

The checked-in verification files record earlier integration runs, including runs made while the Java backend was a separate checkout. They remain evidence for those runs, not a guarantee that every Packet Tracer model, operation, or hospital policy has been tested. Current setup uses `backend/java` only. See the verification scope and notes in [LIVE-SETUP.md](LIVE-SETUP.md).

## Attribution

See [THIRD-PARTY.md](THIRD-PARTY.md) for provenance and licensing notes for the Python crypto code, Java backend, Cisco SDK, and Packet Tracer.
