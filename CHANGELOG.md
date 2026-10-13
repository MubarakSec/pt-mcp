# Changelog

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
