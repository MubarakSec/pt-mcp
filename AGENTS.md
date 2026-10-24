# Working on pt-mcp

Read `README.md`, `IMPROVEMENTS.md` and `docs/CLOUD-HANDOFF.md` before implementing the improvement roadmap. `docs/SDK-CAPABILITIES.md` records the locally inspected Cisco SDK surface; signatures are evidence of API availability, not successful runtime tests.

## Architecture

- Keep the Python MCP server and the authenticated Java IPC live backend. Do not introduce a Socket.IO/`.pts` transport as part of this roadmap.
- Keep saved-file tools usable without Java, a Cisco SDK, credentials or a running Packet Tracer instance.
- Client-facing live tools use `pt_live_*`. Java registrations use `pt_*`; `live_bridge.py` maps the prefix. New registrations and `live_tools.json` must agree.
- Extend existing schemas compatibly. Preserve automatic naming when no explicit device name is supplied, and keep saves explicit.
- Reuse the persistent, serialized IPC session. Never automatically replay a mutation after a timeout or disconnect: it may already have happened.

## Code ownership

| Area | Files |
|---|---|
| Stdio MCP and offline dispatch | `server.py` |
| Java subprocess protocol, catalog and failure isolation | `live_bridge.py`, `live_tools.json` |
| Saved-file reading/building and native models | `ptread.py`, `ptbuild.py`, `model_library.py` |
| Live SDK operations and session lifecycle | `backend/java/src/main/java/com/ptmcp/` |
| Setup and local registration | `setup.py`, `LIVE-SETUP.md` |

Keep new visual/layout logic in focused modules. Avoid substantially growing the existing large dispatcher/client files with unrelated feature logic. Prefer the standard library and current dependencies.

## Verification

1. Discover the existing build and test setup. Add focused regression tests before changing behavior; historical `verification/*.json` captures are not a repeatable test suite.
2. Validate offline behavior, schemas and failure paths without requiring PT. Use small fake/proxy interfaces for unit tests; never introduce fake Cisco classes into production code or present mocked results as live verification.
3. Build the Java backend with JDK 21 and a legitimate local SDK when available. If the SDK is missing in a cloud workspace, continue independent Python/test/documentation work and report exactly which compilation/integration checks could not run.
4. Run live verification in a disposable scratch project with PT, SDK privileges and registered IPC available. Do not overwrite or replace an unrelated active user project. Save/reopen tests use new paths.
5. For every new mutation, cover invalid inputs, partial outcomes and readback. Report unknown outcomes explicitly. A returned SDK status, PDU creation or enabled DHCP flag alone does not prove the intended effect.

Keep MCP stdout exclusively for JSON-RPC. Send diagnostics to stderr and redact credentials. Do not commit Cisco binaries, local IPC secrets, generated registrations, private network projects or host-specific paths.

## Visual design contract

The goal is clearer network diagrams and easier agent workflows: meaningful device names, predictable positioning, building/department groups, readable notes, and portable SVG diagrams. Planning/export must preserve topology and configuration. Applying a layout changes only explicitly requested presentation state; it must not recable devices, change IP/VLAN/CLI state, power-cycle hardware or save automatically.

Validate all layout names and coordinates before mutation, bound batch sizes and return per-item results. Preserve unknown link state instead of drawing an unverified green/success indicator. Escape user-provided SVG text and avoid embedded scripts or external resources.

## Delivery

Implement and verify one coherent slice at a time. Update documentation and tool counts only when the implementation exists. Mark evidence as **offline tested**, **SDK compiled**, or **live verified** as appropriate. Keep unperformed checks visible in the handoff rather than declaring the whole release verified.
