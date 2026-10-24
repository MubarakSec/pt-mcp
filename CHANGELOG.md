# Changelog

## 0.7.0 — 2026-10-24

- Add explicit authenticated IPC probing, passive boot/terminal readiness, and opt-in actual-address/trunk validation with pass/fail/unknown evidence and shared deadlines.
- Retain terminal completion/output after caller timeouts and expose read-only result collection by operation ID; never replay an uncertain mutation.
- Compact canvas notes by default with meaningful/total/omitted counts and an all-note view option.
- Reject unsafe native Unicode/control note text before mutation following the pulled local saved-XML corruption report. Offline/SVG Unicode remains supported.
- Add SDK-free Python/catalog/JDK policy CI and a guarded local PT harness with explicit saves, XML validation, save/reopen checks and opt-in failure cases.
- Baseline SDK/presentation verification is recorded locally in `docs/LOCAL-VERIFICATION-2026-10-24.md`. New SDK compilation, new live PT acceptance and hosted CI execution remain separate pending checks.

## 0.6.0 — 2026-10-24

- Classify recognized IOS error lines even with SDK success; add bounded CLI batches with per-command outputs and explicit partial/unknown outcomes.
- Add optional live device naming, rename/move, native note lifecycle, canvas reads and preflighted layout moves through Java IPC.
- Add deterministic grouped/tiered planning, explicit offline build-copy layout application, self-contained SVG export and synthetic review examples.
- Preserve existing APIs, offline independence, explicit saves and no mutation replay.
- Offline Python/MCP and pure Java policy tests passed. Full Cisco SDK compilation and live Packet Tracer verification remain pending; see [evidence](docs/IMPLEMENTATION-EVIDENCE.md).

## 0.5.0 — 2026-10-13

### Added

- Root `setup.py` prepares the combined project in one command: locates or accepts the local Cisco SDK and `meta`, checks JDK 21, builds the nested Java backend, preserves or creates IPC credentials, and generates the local `.pta` registration.
- Java backend source and build now live under `backend/java`; the combined MCP client command still targets the root `server.py`.
- `THIRD-PARTY.md` records Python, Java-backend, Cisco SDK, and Packet Tracer provenance and licensing notes.

### Changed

- Replaced sibling-checkout live setup instructions with the nested-backend layout and fresh-install GUI registration steps.
- Clarified that earlier verification files came from recorded integration runs and do not establish compatibility for every model, operation, or Packet Tracer version.

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
