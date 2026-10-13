# Packet Tracer MCP: saved files and live IPC

The merged server is `server.py`, version **0.4.0**, in this folder. It exposes **52 tools**: the original 21 saved-file tools, three model-library tools, 27 live tools, and `pt_live_status`.

The Java backend is the sibling folder `../pt-mcp-live`, cloned from [jenaro1804/PacketTracer_mcp](https://github.com/jenaro1804/PacketTracer_mcp). Its source and Git history remain there; the Python server forwards live calls over MCP stdio. Both backends therefore retain their own behavior and code.

```text
Codex / OpenCode
       |
       v
Python server.py
       |-- pt_* and pt_build_* --> .pkt/XML inspection and copy-based edits
       |
       `-- pt_live_* --> Java MCP --> Cisco SDK --> running Packet Tracer
```

## Use it now

1. Start Cisco Packet Tracer. Save any project before asking to open another.
2. Confirm **Extensions → IPC → Options** is listening on port **39000**. Leave **Allow Remote Applications** off.
3. The local **PT MCP Connector** is already registered under **Extensions → IPC → Configure Apps**, set to **On Demand**. The MCP client starts the Java backend; you do not need to press Launch in Packet Tracer.
4. Start a new Codex session or reload the OpenCode MCP connection to discover the new tools. Both configurations point to `python3 /home/mobta/tools/pt-mcp/server.py`.
5. Ask for `pt_live_status`, then `pt_live_get_topology`. Status reports backend process availability; a successful topology call also demonstrates IPC authentication.

Example prompts:

- “Use pt_live_get_topology to inspect the open simulator.”
- “Use pt_live_run_cli to run show ip interface brief on Router0 in enable mode.”
- “Set PC0 FastEthernet0 to DHCP, read its endpoint configuration, then inspect the router's DHCP bindings.”
- “Save the live lab as a new absolute .pkt path, then use pt_open to inspect that saved file.”
- “Use pt_live_ping from PC0 to 192.0.2.1 and report the actual received count.”
- “Use pt_live_run_terminal on PC0 with ipconfig.”
- “Use pt_live_http_get on PC0 to fetch http://198.51.100.2.”
- “Import a clean model seed with pt_model_import, list it with pt_model_list, then use pt_build_add_device to add an absent model to an offline build copy.”

## Tool behavior

| Tools | Target | Effect |
|---|---|---|
| `pt_open`, `pt_devices`, `pt_config`, `pt_links`, etc. | A saved `.pkt` or XML file | Inspect saved state; opening does not replace the simulator workspace. |
| `pt_build_*` | A separate build copy | Preserve the original copy/edit/save workflow. |
| `pt_live_get_*` | The running simulator | Read live inventory, interfaces, endpoint settings, links, models, and modules. |
| `pt_live_add_device`, connection/module/endpoint tools | The running simulator | Change live topology or settings. |
| `pt_live_run_cli` | A Cisco router, switch, or ASA | Run IOS commands and return their status and output. PC/Server command prompts are outside this tool's scope. |
| `pt_live_open_file` | The running simulator | Replace the active workspace with the supplied file. |
| `pt_live_save_file` | The running simulator | Save to the supplied path; an existing destination can be overwritten. Use a new output path when preserving an original. |

Live and saved-file sessions are independent. After changing a live device, save with `pt_live_save_file`, then open that file with `pt_open` to inspect updated saved state. `pt_build_set_config` still writes saved configuration; it does not execute a live CLI command.

`pt_live_get_endpoint_config` now reads gateway and DNS from the live device's native XML, matching the requested interface by MAC address. Its `gateway_dns_source` identifies that fallback. No project is saved or reopened for this read. For DHCP, also inspect the serving router's `show ip dhcp binding` or the PC's `ipconfig`; the SDK's stored IP/mask can lag the active lease.

## Diagnostics added in 0.4.0

| Tool | What it does |
|---|---|
| `pt_live_ping` | Captures actual ping outcomes on Cisco devices and PCs/servers. Distinguishes success, failure, and unknown/timeouts. |
| `pt_live_run_terminal` | Captures supported read-only commands on PC/server prompts and Cisco terminals, including `ipconfig`, `arp -a`, `tracert`, and `show` commands. |
| `pt_live_http_get` | Requests a page using the simulated device's browser and returns its actual Cisco response type and content. |
| `pt_live_http_service` | Reads or configures a simulated server's HTTP service and page. |
| `pt_live_get_device_xml` | Reads native device XML without saving the project. It can include configuration data. |
| `pt_model_import`, `pt_model_list`, `pt_build_add_device` | Cache native templates and add models that are absent from an offline project's current device list. |

For ping results use `pt_live_ping`; the original raw `pt_live_run_cli` call can still return empty text for an asynchronous IOS ping. Cisco ping results use a correlated `DonePing` event. Packet Tracer destroys the finished ping process, so `sent` and standard `lossPercent` can remain null; `received`, `outcome`, and loss relative to requested probes are reported with their source. PC/server ping reports its printed sent/received summary.

`pt_live_http_get` checks simulated HTTP/HTTPS responses, not full visual rendering or clicking JavaScript forms. Interactive UI work still uses computer control. Cisco ping currently supports IPv4; unknown outcomes are not treated as successful connectivity. A custom terminal timeout shorter than a native command can return unknown while that command continues; allow it to finish before another terminal command.

The reusable library contains nine native templates from the integration seed, including eight common models plus Packet Tracer's power-distribution artifact. Templates live in ignored `model-templates/`. Import a clean native source: IOS/addressing/key/VLAN sanitization is scoped and is not a full factory reset of server services and files. Hardware trees are copied from Packet Tracer, not synthesized.

## What was verified

On installed **Packet Tracer 9.0.1.0858** and **OpenJDK 21**, using the Cisco **9.0.0.0 SDK JAR shipped inside that installation**:

| Check | Result |
|---|---|
| Java build | `installDist` completed successfully. |
| Combined MCP discovery | 44 unique tool names, including all 21 original names. |
| IPC authentication and topology read | Passed. |
| Create 2911 router and PC; connect Ethernet interfaces | Passed. |
| Configure router through IOS CLI; read interface state | Passed; Gi0/0 became `192.0.2.1`, up/up. |
| Apply static endpoint address | Passed; `192.0.2.60` was read back. |
| Switch endpoint to DHCP | Passed; PC obtained `192.0.2.50`, also visible in router DHCP bindings. |
| Save and reopen through live IPC | Passed; reopening returned `FILE_RETURN_OK`. |
| Original file tools inspect that live-created file | Passed for opening, devices, and running configuration. |
| Existing saved-file smoke workflow | Passed on the existing CCNA project, without modifying it. |
| Missing backend and invalid live settings | Original tools remained available; live calls returned errors. |
| Malformed request envelopes | Returned errors without terminating the server. |
| IOS `ping` through this SDK command call | Command accepted, but output was empty. Connectivity success is **not verified** by that result. |

Evidence is in [verification/runtime-results.json](verification/runtime-results.json), [verification/failure-isolation.json](verification/failure-isolation.json), and [verification/live-ping.json](verification/live-ping.json). The saved integration lab is `verification/demo-live.pkt`. Creating the first PC also caused Packet Tracer to add its standard power-distribution device.

These checks cover the merged transport and representative operations. They do not establish that all 22 upstream live operations, all device models, or the hospital access policies have been tested.

### Additional verification after the fixes

- Cisco ping: a reachable PC produced two matching replies and success; an unreachable IP produced zero replies and failure.
- PC ping: successful and unreachable targets produced complete sent/received summaries.
- PC and server command prompts: `ipconfig` output was captured through terminal events.
- Endpoint readback: gateway `192.0.2.1` and DNS `198.51.100.2` were read from live device XML.
- HTTP: the simulated browser returned `HTTP_OK` and the expected page; an unreachable server returned a timeout.
- Offline model creation: a 2960 absent from the original saved project was added from the library, cloned with unique MACs/physical identity, loaded, saved by Packet Tracer, and reopened successfully.
- Models checked: 2911, 1941, 2960-24TT, 3560-24PS, PC-PT, Laptop-PT, Server-PT, and AccessPoint-PT. Cisco fixtures also accepted `show version`.
- HWIC-2T insertion/removal, router power cycling, automatic cable creation, cable deletion, and device deletion passed.

Repeated HTTP requests captured two separately changed pages; see [http-repeat.json](verification/http-repeat.json). Back-to-back PC ping, `ipconfig`, and `arp -a` also passed after fixing SDK per-object event subscription reuse; see [terminal-sequence.json](verification/terminal-sequence.json).

Evidence: [fixed-features.json](verification/fixed-features.json), [ping-fixed.json](verification/ping-fixed.json), and [model-module-coverage.json](verification/model-module-coverage.json). This is verified coverage of common models and operations; it is not a guarantee for every catalog model or feature.

## Runtime settings

| Setting | Default / purpose |
|---|---|
| `PT_MCP_LIVE_COMMAND` | Optional JSON array overriding the Java command. Defaults to `../pt-mcp-live/build/install/pt-mcp/bin/pt-mcp`. |
| `PT_MCP_LIVE_TIMEOUT` | Positive finite number of seconds; default 45. |
| `PT_MCP_HOST` | Java IPC host; default localhost. |
| `PT_MCP_PORT` | Java IPC port; default 39000. |
| `PT_MCP_CONFIG` | Optional explicit path to Java credential properties. |
| `PT_MCP_AUTH_APPLICATION`, `PT_MCP_AUTH_SECRET` | Optional environment overrides for the IPC app ID and shared secret. |

The bridge sets the child's working directory to the Java repository, so its ignored `local.properties` file is found regardless of the MCP client's working directory. Credentials and plaintext app metadata are mode 0600; the proprietary JAR, generated `.pta`, credentials, and build output are excluded from Git.

The generated manifest requests seven privileges: `GET_NETWORK_INFO`, `CHANGE_NETWORK_INFO`, `SIMULATION_MODE`, `MISC_GUI`, `FILE`, `CHANGE_GUI`, and `APPLICATION`. Device creation failed at `getLogicalWorkspace` until `APPLICATION` was included; the successful integration check followed that change. Multiuser, Activity Wizard, preference changes, and IPC administration are not requested.

## Rebuild the Java backend

```sh
cd /home/mobta/tools/pt-mcp-live
./gradlew installDist --console=plain
```

It requires JDK 21 and `libs/pt-cep-java-framework-9.0.0.0.jar`. That JAR was copied from your installed Packet Tracer AppImage. It is proprietary and is not included in Git.

The local Linux `meta` utility created `pta/ptmcp/ptmcp.pta` from the ignored `ptmcp.xml` containing the local shared key. If you regenerate or change the app metadata, remove and re-add **PT MCP Connector** in Configure Apps so Packet Tracer uses the new privilege/key settings. Preserve the built-in **PT Exam Player** entry.

If upstream tools change, regenerate `live_tools.json` from the Java server's `tools/list` result before reloading clients. The checked-in catalog enables offline startup without launching Java. It contains schemas, descriptions, and annotations; it contains no credentials.

## Failure handling

Live operations are sent once. The Java connection manager and Python bridge do not automatically replay a failed operation. If the reply is lost after Packet Tracer applied a change, inspect the simulator before repeating the action. Timeouts and protocol failures discard the child; a subsequent call can establish a fresh connection.

The Python process closes its Java process group on shutdown. An absent Java installation, invalid live configuration, or failed live call does not disable the existing saved-file toolkit.

## Backups and rollback

Your original toolkit is preserved at `/home/mobta/tools/pt-mcp-backup-20261013-041405`. The Python repository's initial commit also preserves that baseline. The merge work is on `feature/live-ipc`; the Java clone's changes are on `integration/python-toolkit`.

To use the original toolkit independently, point an MCP entry at the backup's `server.py`. Keep the current backup until you are satisfied with the merged version. The Codex configuration was backed up alongside `~/.codex/config.toml` before adding the new server entry.

## Sources

- [Cisco IPC and ExApp registration](https://tutorials.ptnetacad.net/help/default/ipc.htm).
- [Upstream Java MCP](https://github.com/jenaro1804/PacketTracer_mcp); cloned commit `9cc8112dd8e67ce406f3786373725965fae56c14`.
- [OpenAI documentation: MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
