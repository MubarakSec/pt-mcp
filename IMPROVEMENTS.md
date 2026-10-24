# Improvement backlog — IPC-first agent automation

Status: first-delivery implementation is present in 0.6.0 (63 tools). CLI classification/
batches, live presentation primitives and deterministic layout/SVG tools are implemented.
Offline policy, schema, renderer and MCP tests ran; SDK adapter compilation and live
Packet Tracer acceptance are pending. See [workflow](docs/DIAGRAMS.md) and
[evidence](docs/IMPLEMENTATION-EVIDENCE.md). The sections below retain the wider
backlog and original design rationale; simulation, PDU/history and richer readiness
remain later work. The architecture remains authenticated Java IPC only.

Reference project: [muhammadbalawal/cisco-pt-mcp](https://github.com/muhammadbalawal/cisco-pt-mcp), MIT; reviewed at commit `4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e` on 2026-10-24. Its 18 tools use an in-PT JavaScript extension and a local Socket.IO bridge. Its `userfunctions.js` also calls PT's `ipc` object: this is a different access path to PT APIs, not evidence that those APIs are unavailable to Java.

**Architecture decision: retain Java IPC as the single live backend.** Keep the offline toolkit independent. Borrow useful capabilities and improve setup within this architecture. A Socket.IO/`.pts` backend is not part of this backlog. Reconsider a second transport only after a required operation demonstrably cannot work through the installed SDK and a separate proposal establishes its benefit, failure behavior and maintenance cost.

The reference has fewer installation prerequisites. That is an onboarding advantage, not a reliability comparison. Our existing implementation has authenticated IPC setup, a persistent serialized session, correlated command/event results, explicit save operations and no automatic mutation replay after timeout/disconnect. Those are concrete properties to preserve for agents. Neither project has been benchmarked against the other here, so do not claim universal reliability or performance superiority for either transport.

## 0. Priorities from actual agent use

1. **P0 — Reliable configuration results:** detect IOS failures in output even when the SDK returns `STATUS_OK`. Add bounded batch configuration with per-command output, explicit stop/continue behavior and a report of changes that may already have been applied. Do not retry or expand a partially applied interface-range command automatically. Report the affected range and inspect state before continuing.
2. **P1 — Live naming and layout:** caller-chosen names, rename, move and notes remove the save/edit/reopen cycle used to finish the company network. Return readback after mutation and preserve compatibility with existing add-device calls.
3. **P1 — Readiness and diagnostics:** distinguish launcher/Java process availability from authenticated IPC connectivity. Keep the existing status call read-only; expose an explicit connection probe separately if needed. Add bounded checks for boot, DHCP leases, VLAN/trunk state, negotiated speed and outstanding terminal commands. A timeout or enabled DHCP flag is not connectivity success.
4. **P2 — Simulation, PDU inspection and live command history:** expose and verify the existing Java SDK APIs described below.
5. **P3 — Packaging and setup:** improve dependency discovery and actionable setup output without changing the live transport. Packaging a Python launcher with `uvx` would not remove Java/SDK/registration prerequisites.

The visual delivery must include more than move/rename primitives: a deterministic building/department layout planner and a portable SVG exporter. Plan/apply/export are separate operations; diagrams must preserve real connectivity and must not invent successful link state. Stage 3 of the cloud brief defines these acceptance checks, including the 50-PC campus and Arabic labels.

The original 0.5.0 baseline lacked these additions. Consult the implementation status above before interpreting the retained backlog descriptions.

## 1. Useful capabilities to add through Java IPC

### 1.1 Easier setup with the existing backend
- Their documented launch path is `uvx cisco-pt-mcp` plus an installed/running `.pts` extension. It has fewer Java build prerequisites but still requires PT-side configuration and a live bridge connection.
- **Our current requirements:** `setup.py` uses JDK 21, the locally installed proprietary SDK JAR, `meta`, and PT app registration. Offline saved-file tools only require Python.
- **Plan:** improve prerequisite detection, version diagnostics, setup idempotence and client registration examples. Evaluate packaging and a Java build/runtime split separately; do not promise redistribution of Cisco components or a JRE-only install before checking licensing and packaging constraints. Keep credentials and local paths out of shared diagnostics.

### 1.2 Simulation control (missing entirely from our live tools)
- `setSimulationMode(toSimMode)` — switch realtime <-> simulation.
- `getSimulationStatus()` — mode, elapsed time, PDU frame count, current frame.
- `stepSimulation(direction, steps)` — forward / backward / reset.
- **Our gap:** Live `pt_live_ping` and `pt_live_run_terminal` capture traffic/output, but do not expose timeline controls.
- **SDK confirmed:** `Simulation` exposes mode get/set, current time, frame count/index, `forward()`, `backward()` and `resetSimulation()` in the installed 9.0.0.0 JAR.
- **Plan:** implement Java wrappers, bounded step counts and event-correlated completion. Report the resulting mode/frame position. Changing mode or resetting the timeline must be explicit; reads must not change simulation mode. SDK method presence still requires live verification.

### 1.3 Native Simple PDU + results (partial overlap)
- `sendPdu(source, destination)` — adds an ICMP PDU using PT's native Simple PDU.
- `getPduResults(types?)` — reads frame outcomes (accepted/dropped/in_transit, src/dst, traffic type), filterable by type (ICMP/ARP/etc.) to hide STP/DTP noise.
- **Our gap:** Live terminal ping does not expose native frame outcomes. Saved-file `pt_pdus` already reads stored tests; that is a separate capability.
- **SDK confirmed:** `UserCreatedPDU.addSimplePdu(source, destination)`, `Simulation.getFrameInstanceAt()` and `FrameInstance` source/destination, traffic-type and outcome getters exist.
- **Plan:** add explicit live Simple PDU creation and bounded/filterable frame reads. Distinguish PDU creation from eventual delivery and a frame accepted at an intermediate device from end-to-end success. Do not silently change mode or replace the existing verified ping path.

### 1.4 Live command log (saved-file support already exists)
- `getCommandLog(deviceName?, limit?)` — IOS command history logged by PT, filterable per device, newest first.
- **Our gap:** `pt_command_logs` already reads history from an opened saved file. What is missing is a structured, bounded read of PT's live history, not all command-log support.
- **SDK confirmed:** `CommandLog.getEntryCount()/getEntryAt()` and `CommandLogEntry` device, timestamp, prompt, command and resolved-command getters exist.
- **Plan:** add a read-only live tool with device filtering and a result limit. Do not clear, enable or replay the command log as a side effect of reading it. Account for sensitive commands before persisting/exporting history.

### 1.5 Rename / move devices (missing from live)
- `renameDevice(deviceName, newName)` — rename in place (unique name required).
- `moveDevice(deviceName, x, y)` — reposition on canvas.
- **Our gap:** We have `pt_build_rename` and `pt_build_*` for saved files, but the live side has no rename/move. (Our live `pt_add_device` lets PT assign the name; we cannot rename afterwards.)
- **SDK confirmed:** `Device.setName()`, `moveToLocation()`, `moveToLocationCentered()` and coordinate getters exist. `LogicalWorkspace.addNote()` and note read/edit methods also exist.
- **Plan:** add live rename/move/note tools with unique-name validation and readback. Verify canvas and saved-file persistence. Do not assume display-name changes also change an IOS hostname.

### 1.6 Caller-chosen device names
- Their `addDevice` takes `deviceName` from the caller (must be unique); ours lets PT assign the name and returns it.
- **Plan:** add an optional `name` to `pt_live_add_device`, preserving automatic naming when omitted. The installed `LogicalWorkspace.addDevice(type, model, x, y)` has no name parameter, so create and rename with `Device.setName()`. Check uniqueness first; if rename fails after creation, report the actual created device and partial outcome rather than claiming nothing changed or retrying creation.

### 1.7 Remove multiple devices/links in one call
- `removeDevice` accepts an array of names; `removeLink` accepts an array of endpoints.
- **Plan:** add bounded batch variants with preflight checks, per-item results and explicit stop/continue behavior. Preserve current single-item schemas. A batch is not atomic: report completed/failed/unattempted items and never replay the entire batch after a disconnect.

## 2. What we do better (keep, do not regress)

- **Offline saved-file toolkit (21 tools):** read/edit `.pkt`/XML, copy-based builds, clone, cable, notes, PDUs, configs. They have no offline mode at all.
- **Native model library import:** `pt_model_import/list/add` imports hardware templates absent from a file. They are limited to a fixed enum of models.
- **Verified ping + terminal capture:** `pt_ping`, `pt_run_terminal`, `pt_http_get`, `pt_http_service` exercise real simulated traffic and capture output/events.
- **Deep device state:** modules, ports, endpoint IP/DHCP/DNS, config, device XML.
- **One authenticated live backend:** keep the persistent serialized Java IPC session and existing request/event correlation. Additional transports would add their own connection, lifecycle, timeout and result-handling behavior to maintain; fewer installation prerequisites alone do not justify that complexity.

## 3. SDK coverage checked on 2026-10-24

Inspected public interfaces with `javap -public -classpath <local-sdk.jar>` against `backend/java/build/install/pt-mcp/lib/pt-cep-java-framework-9.0.0.0.jar`.

| Capability | Installed Java SDK surface | Verification status |
|---|---|---|
| Rename and move | `com.cisco.pt.ipc.sim.Device`: `setName`, `moveToLocation`, coordinate getters | API present; new wrappers and live tests pending |
| Simulation controls | `com.cisco.pt.ipc.system.Simulation`: mode/time/frame reads, forward/backward/reset | API present; asynchronous completion semantics need testing |
| Simple PDU creation | `com.cisco.pt.ipc.ui.UserCreatedPDU.addSimplePdu` | API present; native result enum and lifecycle need testing |
| PDU frame inspection | `Simulation.getFrameInstanceAt`, `com.cisco.pt.ipc.sim.FrameInstance` getters | API present; frame/result interpretation needs testing |
| Live command history | `com.cisco.pt.ipc.system.CommandLog` and `CommandLogEntry` | API present; read-only filtering and limits need testing |
| Canvas notes | `com.cisco.pt.ipc.ui.LogicalWorkspace`: add/read/edit/remove notes | API present; persistence and coordinates need testing |

This establishes API availability, not runtime compatibility across every Packet Tracer version. No second backend is justified by a missing API in the checked feature list. Reuse the existing session and event conventions, then verify each wrapper in PT before marking it supported.

## 4. Concrete next steps (if we proceed)

1. Fix CLI result classification and add regression coverage for `STATUS_OK` plus failure text, partial interface-range application and timeout/disconnect outcomes. Design batch configuration around those guarantees.
2. Implement live rename/move/notes and optional add-device naming using the existing Java SDK. Verify duplicate names, coordinates, partial creation failures and save/reopen persistence.
3. Add bounded readiness/terminal-result handling without weakening the no-replay rule. Keep read-only availability status separate from an active connectivity probe.
4. Implement simulation/PDU/history wrappers in small verified increments. Keep mode changes explicit, bound frame/log reads and preserve native error/unknown outcomes.
5. Register exposed tools in `PtMcpServer`, synchronize `live_tools.json` and verify the Python bridge's existing `pt_live_*` prefix mapping. Use `pt_live_*` names in client-facing documentation; Java backend registrations use `pt_*`.
6. Add offline tests for schema/catalog consistency and failure handling, plus live integration cases for each new capability. The reference's offline smoke tests are useful examples, not proof that live simulation or traffic works. Retain the existing recorded verification evidence and distinguish it from repeatable tests.
7. Update `README.md`, `LIVE-SETUP.md` and changelog only for capabilities actually implemented and verified. Improve setup packaging after the P0/P1 agent workflow gaps.

## 5. Things NOT to copy

- Their fixed model enum (our native-model library is more general).
- Their "auto write memory after configureIosDevice" default — keep explicit save semantics to avoid surprising writes.
- Replacing our offline toolkit — theirs has none; our offline mode is a differentiator.
- Adding a second transport solely to reduce installation prerequisites.
- Equating tool count, GitHub stars, fewer dependencies or the presence of SDK methods with proven reliability.

## 6. Open questions

- Which inspected APIs work across the Packet Tracer versions we intend to support, and which operations need event-correlated completion?
- What bounded result/partial-failure schema should batch configuration and deletion use without promising rollback or safe automatic replay?
- How should capabilities report supported, unsupported and unverified states without turning availability checks into implicit mutations?
- Can a packaged launcher and clearer dependency checks improve onboarding while preserving the authenticated Java IPC backend and Cisco redistribution constraints?

## 7. Evidence and comparison limits

- Local implementation: `live_bridge.py` request-ID matching, serialization and no-replay handling; `ConnectionManager.java` persistent synchronized IPC session; `PingTerminalFeatures.java` UUID-correlated traffic events; `server.py` saved-file `pt_command_logs`; local SDK inspection above.
- Reference source: [tool schemas](https://github.com/muhammadbalawal/cisco-pt-mcp/blob/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e/mcp_server/tools.py), [PT operations](https://github.com/muhammadbalawal/cisco-pt-mcp/blob/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e/extension/source/userfunctions.js), [bridge](https://github.com/muhammadbalawal/cisco-pt-mcp/blob/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e/mcp_server/bridge.py), [offline smoke tests](https://github.com/muhammadbalawal/cisco-pt-mcp/blob/4b277cba5d6ef5cee2d4fc6fa1768206eb841e8e/tests/test_smoke.py).
- Their bridge also correlates request IDs and handles disconnects/timeouts. Socket.IO alone does not establish unreliable behavior. The decision here follows our existing verified workflows, requirements and maintenance scope; a comparative reliability claim would need equivalent workloads and injected-failure measurements.
