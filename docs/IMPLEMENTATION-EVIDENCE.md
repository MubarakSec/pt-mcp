# Implementation evidence

Follow-up local results are recorded in [local verification — 2026-10-24](LOCAL-VERIFICATION-2026-10-24.md). The local SDK build and selected live presentation/CLI operations passed; native Unicode note corruption remains unresolved. The original cloud-workspace results below are retained as historical evidence, not the current local SDK-availability status.

## CLI results and batches

Implemented: known IOS error-line classification with original status/output retained;
`pt_live_run_cli_batch` (1..100 single-line commands, <=4096 characters each), required
`initial_mode` (`user`, `enable`, `global`), optional `continue_on_error` (false).
Indexes are zero-based. Later commands inherit CLI context. Failed commands can
have partially changed state, particularly interface ranges. No rollback, range
expansion, replay or automatic save occurs. Unknown outcomes always stop the batch.
Inspect running configuration/interfaces before further mutations after failure.

Offline tested: Python bridge timeout/disconnect regression proves one request and
no replay. Python syntax checks passed. The Java policy harness in
`tests/java/CliPolicyTest.java` also passed after obtaining isolated OpenJDK 21.
Its portable runner explicitly skips when no JDK is installed.

SDK compiled: **pending** — the proprietary Cisco SDK is missing.
Live verified: **pending** — no Packet Tracer simulator/registered IPC is available.

Local acceptance: in a disposable scratch network, boot a switch, submit an invalid
interface range followed by a configuration command. Check original SDK status,
IOS output, failed index, remaining unattempted indexes and actual interface state.
Repeat with continue enabled; inspect context before further work. Disconnect IPC
mid-batch and confirm unknown outcome/no replay. Save only explicitly to a new path.

## Presentation primitives

Implemented: optional add-device `name`, display-name rename, icon-origin move,
read-only canvas snapshot, native note lifecycle and sequential `pt_live_apply_layout`.
Move/note coordinates are signed 32-bit integers; fractional/nonfinite values are
rejected. Existing add-device callers retain finite fractional coordinates.
Names are 1..256 characters without control characters. Notes are bounded to
16384 characters without NUL. Note IDs are matched against native note membership
before update/delete; they are never parsed as arbitrary canvas IDs.
Layout application accepts 1..500 moves, preflights every name/coordinate/duplicate,
stops on any failed/unknown outcome and reports per-item readback/index lists.
Annotations in plans are not applied implicitly; add native notes explicitly.

Offline tested: isolated OpenJDK 21 downloaded under `/tmp` enabled both pure Java
policy harnesses. CLI and presentation tests passed, covering partial creation,
collisions, unchanged/failed setters, note membership, bounded input and preflight.
Catalog tests compare all Java registration schemas with cached descriptors,
required fields, optional naming, namespace mapping and read-only annotations.
This supersedes the earlier JDK-unavailable status for policy tests only.

SDK compiled: **pending** — Cisco SDK missing. The pure Java harness compilation
is not a compilation of the SDK adapter or full backend.
Live verified: **pending**.

Local acceptance: in a disposable project, create automatically/named, reject a
collision, rename with cables attached and check display name vs IOS hostname.
Move positive/negative origins, compare SDK coordinates with canvas; try out-of-
range/fractional inputs. Create/update/delete a Unicode note, reject device IDs
as note IDs. Apply a partial layout and check omitted devices/links/configuration.
Save to a fresh path, reopen and inspect names, positions, notes and cables.


## Layout planning, SVG and offline integration

Implemented: `pt_layout_plan`, `pt_export_svg`, `pt_build_apply_layout`, deterministic
building/department/tier positioning, group annotations and standalone vector SVG.
27 offline tools + 35 Java live registrations + status = 63 discovered tools.
Schemas and limits are documented in [DIAGRAMS.md](DIAGRAMS.md).

**Offline tested**, 2026-10-24:

- `python3 -m unittest discover -s tests -v` with OpenJDK 21 on PATH: **12 tests
  passed, none skipped**, including two standalone Java policy harnesses. Those
  compile only SDK-independent policy classes, not Cisco adapters.
- `python3 -m py_compile server.py live_bridge.py diagrams.py diagram_tools.py
  ptread.py ptbuild.py model_library.py setup.py`: passed.
- Real Python stdio MCP initialization/discovery, synthetic XML reading/build-copy
  edits, unchanged source/config/links, full-plan preflight and backend failure
  isolation ran with the live command deliberately unavailable.
- Synthetic empty/cycle/disconnected/XML-special/long/Arabic-label and 50-PC
  20/20/10 campus tests check deterministic unique positions, region bounds,
  immutable input, partial plans, XML validity and non-overwrite/symlink handling.
- Both example SVGs generated, rendered with temporary CairoSVG tooling and
  visually inspected. Both were also rendered inline in headless Chromium and
  screenshots inspected: Arabic shaping, mixed Arabic/IP labels, group boundaries,
  shared core above buildings and dashed unknown links are visible. Cairo's text
  handling differs; the browser inspection establishes browser presentation only.
  No renderer/browser dependency was added to the product.

**SDK compiled: pending.** No legitimate Cisco SDK JAR exists in this workspace;
`./gradlew test installDist` was not run. New adapter method use follows the checked
signature snapshot. MCP `ToolAnnotations` constructor was checked against the
published 1.0.0 source artifact; that is source inspection, not backend compilation.

**Live verified: pending.** No Packet Tracer/registered IPC is available. No scratch
project mutation, attached-cable canvas check, CLI range/context check, native note
lifecycle or save/reopen test was performed. Historical `verification/*.json`
records do not verify the new wrappers.

Finish locally with JDK 21 and the legitimate SDK: run Python tests, then
`cd backend/java && ./gradlew test installDist`. In a new disposable PT workspace,
execute the CLI and primitive acceptance cases above. Read a fresh canvas snapshot,
plan the synthetic grouped campus, explicitly apply the moves and requested native
notes, and verify coordinates, Unicode text, unchanged cables/config/power and
omitted-device positions. Save explicitly to a new `.pkt` path, reopen and inspect.
Interrupt an IPC reply and verify unknown outcomes with no automatic replay.
Rectangle groups are SVG-only; native group labels use explicit note calls.

## Readiness stage — first increment

Baseline update supplied by the owner: all 12 baseline tests and the full Cisco SDK
build passed locally at `b5d74c0`; live PT verification remained pending. This is
owner-reported local evidence, not a new build performed in this workspace.

Implemented `pt_live_probe_connection`, `pt_live_get_readiness` and
`pt_live_validate_network`, passive process/authentication distinction, per-check
pass/fail/unknown evidence, shared deadlines and tracked terminal completion across
timeouts. Active ipconfig/show probes require explicit opt-in. There is no mutation
replay or implicit save. See [READINESS.md](READINESS.md) for limits and gaps.

Offline tested: 20 Python test cases passed, including standalone JDK 21 policy
harnesses, catalog/schema/read-only parity, actual-address/trunk output evaluation,
no-probe and no-replay paths, pending terminal guards and bounded child startup.
The timeout test exposed subprocess pipe cleanup, which was fixed and rerun with
ResourceWarning promoted to errors. No mock/proxy result is live verification.

New SDK adapters compiled: **pending** — no legitimate Cisco SDK is present here.
New live PT verification: **pending**. In particular, per-interface DHCP flag
semantics, supported trunk formatting, boot model coverage, terminal prompt/event
ordering and save/reopen behavior need disposable local acceptance.

Readiness stage — CI increment: added pinned, read-only GitHub Actions jobs for
Python-only checks and Python 3.10/3.12 with required JDK 21 policy tests. Locally,
`--python-only` passed 15 tests with five intentional Java skips; `--require-java`
passed all 20 with no skips on Python 3.10 / JDK 21. Workflow YAML parsed and its
job/permissions/action pin structure checked. Hosted GitHub jobs and the Python
3.12 matrix entry were **not run here**. CI does not compile SDK adapters.

Readiness stage — integration harness increment: prepared
`scripts/pt_integration.py` and local instructions, including empty-workspace
preflight, unique scratch names, explicit startup/.pkt save and reopen, presentation
comparison and fresh network assertions. Defaults to plan-only; live execution and
saves require separate flags. Offline safety/orchestration tests passed with
synthetic tool replies; **no PT integration run was performed**. All 29 tests passed
locally with required JDK 21 and no skips. Terminal prompt-before-end regression and
history invalidation on project open are covered by the pure tracking policy;
SDK adapter lifecycle changes still require local SDK compilation/live testing.
