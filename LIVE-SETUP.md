# Live Packet Tracer setup

This repository combines the saved-file Python tools with a Java backend under `backend/java/`. The Python MCP server starts the Java process on demand; the live tools talk to the running simulator through Cisco IPC. No sibling Java checkout is needed.

## One-command setup

For saved `.pkt` and XML tools alone, run `python3 server.py`; no Java or Packet Tracer installation is needed. To enable live tools, install JDK 21 and Cisco Packet Tracer, then run once from the repository root:

```sh
python3 setup.py
```

The script checks JDK 21, searches the local Packet Tracer installation for the Cisco SDK and `meta`, copies the SDK into the ignored `backend/java/libs/` directory, reuses or generates local IPC credentials, builds the Java distribution, and generates `backend/java/pta/ptmcp/ptmcp.pta` with the required seven privileges.

If auto-detection does not find the local Packet Tracer files, pass the locations explicitly:

```sh
python3 setup.py --packet-tracer-root /path/to/extracted/packet-tracer
python3 setup.py --appimage /path/to/packettracer.AppImage
python3 setup.py --sdk-jar /path/to/pt-cep-java-framework-9.0.0.0.jar --meta /path/to/meta
```

Linux AppImage extraction needs `unsquashfs`. Use `python3 setup.py --help` for the complete option list; `--pt-version` defaults to `9.0.1`. You may also set explicit IPC credentials in `backend/java/local.properties` before setup. Setup creates this gitignored file with mode `0600` if it does not exist.

### Register the connector in Packet Tracer

Packet Tracer GUI registration remains a one-time manual step on a fresh install or after regenerating the registration metadata:

1. Start Packet Tracer and open **Extensions → IPC → Configure Apps**.
2. Add `backend/java/pta/ptmcp/ptmcp.pta` and set **PT MCP Connector** to **On Demand**. If replacing an old registration, remove only this connector; preserve **PT Exam Player**.
3. Open **Extensions → IPC → Options**, enable Listening on port `39000`, and enable **Always Listen On Start** if you want IPC available after each PT launch. Keep **Allow Remote Applications** off for local use.
4. Start or reload the MCP client connection. The Python server starts the Java backend; do not launch the Java app manually from PT.

After setup, point the MCP client at this repository's `server.py`, for example:

```text
python3 /absolute/path/to/pt-mcp/server.py
```

The command is unchanged from the saved-file server. Start a new session or reload the MCP server to discover all 52 tools. Begin with `pt_live_status`, then `pt_live_get_topology`.

## Requirements and setup options

| Component | Requirement | Notes |
|---|---|---|
| Python tools | Python 3 | Saved-file tools use the standard library plus vendored `Decipher/`. |
| Live backend build | JDK 21 | Setup rejects other Java compiler versions. |
| Live simulator | Cisco Packet Tracer, locally installed or mounted | The registration PT version defaults to `9.0.1`; use `--pt-version` when appropriate. |
| Cisco SDK | `pt-cep-java-framework-9.0.0.0.jar` from the local PT installation | Proprietary; copied to ignored `backend/java/libs/`, not redistributed. |
| Registration tool | Cisco `meta` from the local PT installation | Used to produce the `.pta` app registration. |
| AppImage extraction | `unsquashfs` on Linux | Needed only when using `--appimage` instead of installed/extracted files. |

If the local install is at a custom extracted path, use `--packet-tracer-root`. Use `--sdk-jar` and `--meta` to provide individual files. Setup does not download Cisco binaries or register the generated app in Packet Tracer's GUI.

## What runs where

```text
MCP client
   |
   v
server.py (stdio MCP)
   |-- saved-file tools --> .pkt/XML reader and copy-based builder
   `-- pt_live_* tools --> backend/java/build/install/pt-mcp/bin/pt-mcp
                                      |
                                      v
                             Packet Tracer IPC :39000
```

Saved-file and live sessions are independent. `pt_open` reads a saved file without replacing the simulator workspace. `pt_build_*` edits a copy. Live operations change the currently open simulator; use `pt_live_save_file` to save a new project, then `pt_open` to inspect that saved result.

## Tool scope and behavior

- `pt_*` and `pt_build_*` retain the original 21 saved-file tools.
- `pt_model_import`, `pt_model_list`, and `pt_build_add_device` use native Packet Tracer model templates for offline projects.
- 27 `pt_live_*` tools plus `pt_live_status` inspect, configure, or change the running simulator.
- `pt_live_run_cli` is for Cisco CLI devices. PCs and servers use endpoint and terminal tools.
- `pt_live_open_file` replaces the active simulator workspace. Save changes first.
- `pt_live_save_file` writes to the PT machine's filesystem; use an absolute new path when preserving an original.
- Live operations are sent once. If a reply times out, inspect Packet Tracer before repeating a mutation because the action may already have completed.

### Diagnostics

| Tool | Use |
|---|---|
| `pt_live_ping` | Reports observed ICMP outcome. Unknown/timeouts are not counted as success. |
| `pt_live_run_terminal` | Captures supported PC/server commands such as `ipconfig`, plus Cisco terminal commands. |
| `pt_live_http_get` | Checks simulated HTTP/HTTPS response, not full browser rendering or JavaScript interaction. |
| `pt_live_http_service` | Reads or configures a simulated server's HTTP service and page. |
| `pt_live_get_device_xml` | Reads native live device XML; it may include configuration data. |
| `pt_live_get_endpoint_config` | Reads endpoint gateway and DNS from live device XML. Check router DHCP bindings or `ipconfig` as well because stored address fields may lag an active lease. |

For Cisco pings, Packet Tracer destroys the completed ping process. The tool uses correlated events; `received`, `outcome`, and loss relative to requested probes are the useful result fields. `sent` and standard `lossPercent` may remain null. A custom terminal timeout shorter than a native command can produce an unknown result while that command continues; let it finish before issuing another terminal command.

## Verification and evidence

Version 0.5.0 setup built the bundled backend successfully. After migrating the local connector registration and reopening the saved integration lab, a live topology read returned 11 devices and two links from the nested backend. See [packaging-0.5.0.json](verification/packaging-0.5.0.json) for the migration record. This packaging change used a build and manual inventory inspection; no automated test suite was run.

The checked-in verification records include earlier runs made while Java lived in a separate checkout. They are retained historical evidence and are not regenerated by setup. Paths such as `verification/runtime-results.json`, `verification/fixed-features.json`, and `verification/model-module-coverage.json` describe those recorded runs. They do not prove that every live operation, model, or hospital network policy has been tested.

Recorded coverage on Packet Tracer **9.0.1.0858**, OpenJDK 21, and Cisco's **9.0.0.0 SDK JAR** includes MCP discovery, IPC authentication, topology inspection, router/PC creation, cabling, IOS configuration/readback, endpoint static IP and DHCP, save/reopen, and offline inspection. Later records include ping results, terminal output, HTTP responses, common native models, module insertion/removal, power cycling, and cable/device deletion. See the individual JSON records in `verification/` for the scope and limitations of each run.

These runs used a local integration checkout and local Packet Tracer installation. They are historical compatibility evidence, not a guarantee of support for every Packet Tracer release or device catalog entry.

## Runtime settings

| Variable | Default / purpose |
|---|---|
| `PT_MCP_LIVE_COMMAND` | Optional JSON argv override for the Java command. Defaults to `backend/java/build/install/pt-mcp/bin/pt-mcp`. |
| `PT_MCP_LIVE_TIMEOUT` | Positive timeout in seconds; default 45. |
| `PT_MCP_HOST` | IPC host; default localhost. |
| `PT_MCP_PORT` | IPC port; default 39000. |
| `PT_MCP_CONFIG` | Optional explicit Java credential-properties path. |
| `PT_MCP_AUTH_APPLICATION`, `PT_MCP_AUTH_SECRET` | Optional environment overrides for IPC app ID and shared secret. |

The bridge launches the child with `backend/java/` as its working directory, so the ignored `backend/java/local.properties` is found regardless of the MCP client's working directory. Generated credentials and app metadata use restrictive permissions. SDK JARs, credentials, registration output, and build artifacts are not versioned.

Setup honors `PT_MCP_CONFIG` and the same per-key credential environment overrides as Java. When an existing properties file is present, its values are preserved; keep any overrides consistent when running the MCP. Both Java and its compiler must be version 21, selected through `JAVA_HOME` or `PATH`. Gradle downloads its wrapper distribution and declared Maven dependencies on the first uncached build, so that build needs internet access.

## Rebuild after Java source changes

Run the root setup command again:

```sh
python3 setup.py
```

It rebuilds the nested Java distribution and refreshes the registration metadata using the existing local credentials. If the app registration was already added in Packet Tracer and its privileges or key changed, remove and re-add **PT MCP Connector** in Configure Apps.

## Rollback and provenance

The former sibling path `../pt-mcp-live` is retained locally for rollback/history only; the combined project has no active dependency on it. For this checkout, the active Java source and build are under `backend/java/`. Older standalone backend setup notes are historical; use the root `setup.py` instructions here. Java provenance, upstream revision, and third-party licensing notes are in [THIRD-PARTY.md](THIRD-PARTY.md).
