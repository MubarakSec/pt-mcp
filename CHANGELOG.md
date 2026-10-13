# Changelog

## 0.4.0 — 2026-10-13

### Added

- Live ping outcomes with correlated reply events and PC/server packet summaries.
- PC/server terminal output capture and simulated browser HTTP/HTTPS requests.
- Server HTTP service inspection/configuration and native live device XML reads.
- Reusable native model import/list/add tools for offline projects.

### Fixed

- Endpoint gateway and DNS readback now uses live XML instead of hardcoded nulls.
- Cloned devices receive unique MACs on every port and valid unique physical placements.
- SDK prints cannot corrupt MCP protocol stdout.
- Repeated terminal/browser requests use UUID-filtered global event listeners so SDK per-object subscription reuse does not silently lose output.
- Completed Cisco ping processes are not queried after Packet Tracer destroys them; event listeners are cleaned up without dereferencing destroyed objects.

### Verified

- Positive/negative ping, endpoint fields, terminal output, HTTP success/timeout, absent-model offline creation and clone/load/save/reopen.
- Eight common models, module insertion/removal, power cycling, and cable operations.

## 0.3.0 — 2026-10-13

### Added

- 22 `pt_live_*` tools backed by Cisco's Java IPC SDK, alongside all 21 existing tools.
- `pt_live_status` for backend availability.
- A cached live-tool catalog so saved-file workflows start without Java or a running simulator.
- Linux setup documentation and recorded live/save/offline integration results.

### Fixed

- Invalid live-backend settings no longer prevent existing tools from starting.
- Non-object JSON requests no longer terminate the server.
- Timeouts and lost connections do not replay live mutations; ambiguous outcomes return an error.
- Java credential settings support an explicit config path and reject example placeholders.

### Known limits

- The live IOS ping call returned an empty output during verification; no connectivity-success claim is made from it.
- Endpoint gateway/DNS getters are not exposed by the upstream wrapper.
- Offline build tools retain their existing model/schema limitations.
