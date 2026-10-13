# Packet Tracer MCP: saved files and live IPC

The merged server is `server.py`, version **0.3.0**, in this folder. It exposes **44 tools**: the original 21 saved-file tools, 22 live tools from the Java backend, and `pt_live_status`.

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

`pt_live_get_endpoint_config` can return `null` for gateway/DNS because the upstream SDK wrapper lacks those getters. This does not mean those settings are absent. For DHCP, also inspect the serving router's `show ip dhcp binding`; a stale static address from an SDK getter is not sufficient lease evidence.

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
