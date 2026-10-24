# Cloud development handoff

## Objective and scope

Improve pt-mcp for AI-driven network construction and presentation while retaining the existing Python saved-file tools and authenticated Java IPC live backend. The owner wants clearer designs and visuals, less repetitive tool use, and reliable verification. A second live transport is outside this work.

This document is an implementation brief. It does not mean any proposed tools are already available. The current documented release is 0.5.0 with 52 tools; verify current code before changing that number. `IMPROVEMENTS.md` provides the wider backlog and rationale.

Cloud development means working on this repository in a hosted coding environment. It does not mean deploying Packet Tracer as a cloud service or connecting a remote agent to the owner's simulator. `localhost:39000` in a cloud workspace does not point to the owner's computer. Do not enable remote IPC, arrange tunnels or publish credentials to make tests pass.

## Start here

1. Read `AGENTS.md`, `README.md`, `IMPROVEMENTS.md` and `docs/SDK-CAPABILITIES.md`.
2. Inspect git status and preserve unrelated work. Locate the current server registrations, cached catalog and test/build commands.
3. Determine which dependencies are actually available. Python offline work requires no live PT. Java compilation requires JDK 21 and the proprietary Cisco SDK. Live verification additionally needs PT and registered/authenticated IPC access.
4. Establish the offline baseline. Do not run `setup.py` just to execute Python tests: setup can generate credentials, registration metadata and build artifacts.
5. Implement the stages below in separate, reviewable increments. Start with the result-classification regression, then finish the first visual-tool slice before expanding the roadmap.

If the hosted checkout lacks ignored files, that is expected. `backend/java/libs/*.jar`, local credentials and model templates are not portable repository assets. Do not upload Cisco binaries or the owner's saved projects without an explicitly authorized transfer. Synthetic XML fixtures are suitable for offline tests.

## Stage 1 — Trustworthy configuration results

### Problem observed

In the company-network build, PT accepted an interface-range command, then returned `STATUS_OK` alongside `% Interface range command failed ...` / `% Command failed on interface ... Aborting`. The next command failed because the intended CLI context was no longer reliable. Checking only the SDK status missed the earlier error.

### Deliverables

- Classify known IOS failure messages as failures even when the SDK reports success. Keep original SDK status and output available; distinguish validation failures, CLI failures and uncertain transport outcomes.
- Preserve valid informational output. A percent sign or a word such as `failed` in arbitrary show output is not by itself a command failure.
- Add bounded batch configuration with per-command results, explicit initial CLI mode, stop-on-error by default and an explicitly requested continue option.
- Return completed, failed and unattempted command indexes. A batch is not atomic and does not imply rollback. Keep startup-config persistence separate and explicit.
- Do not automatically replay a batch or expand and rerun a partially applied interface range. After uncertain state, return evidence and require inspection before another mutation.

### Acceptance

Offline tests reproduce `STATUS_OK` plus IOS failure text, benign show output, a partial batch and a lost reply. Tests verify that no mutation is replayed. Compile Java if the SDK is available. Actual interface-range behavior and CLI context recovery require live PT verification.

## Stage 2 — Live presentation primitives

Expose these capabilities through the existing Java backend. The names below are proposed client-facing contracts; verify that the names are unused before registration.

| Proposed tool | Minimum behavior |
|---|---|
| `pt_live_rename_device` | Validate source/target names, reject collisions, rename and return the actual resulting name. Renaming a display name must not promise to change an IOS hostname. |
| `pt_live_move_device` | Validate finite, representable coordinates, move the device and return coordinate readback. Define whether coordinates refer to the icon origin or center. |
| `pt_live_get_canvas` | Read devices with names, types, models and positions, links and native note identifiers/text/positions. Do not change mode, layout or configuration. |
| `pt_live_add_note` | Add bounded text at an explicit position; return the native identifier and readback. |
| `pt_live_update_note` | Update only a known note identifier. Readback must reflect the actual result. |
| `pt_live_delete_note` | Remove only a verified note identifier; never allow a note operation to remove an arbitrary canvas item. |

Extend `pt_live_add_device` with an optional `name` while preserving the current required fields and automatic naming behavior. The SDK's add method returns a generated name; explicit naming therefore needs create-then-rename. If rename fails after creation, report the created device and partial outcome. Do not silently create a second device or remove the first as guessed rollback.

Validate identifiers and coordinates before changes; reject empty names, duplicates, NaN/infinity, unsupported fractional coordinates and integer overflow according to the documented coordinate contract. Use the same rules across individual and batch operations. Do not invent coordinate or text limits without documenting them.

### Acceptance

- Unit tests cover validation, collisions, same-name requests, failed/partial creation and unsuccessful move/note readback.
- New schemas work through the `pt_live_*` mapping; the cached catalog and Java descriptors agree.
- Existing add-device callers still work without the new argument.
- Local PT checks cover rename/move with attached cables, note lifecycle, Unicode text and save/reopen persistence.

## Stage 3 — Layout planning and diagram export

Primitives alone will not produce a good design. Add a deterministic planner and a standalone renderer with no mandatory network, browser or image-generation dependency.

### Plan first, apply explicitly

Accept an explicit topology snapshot or an opened saved-file topology, together with optional groups such as buildings/departments. Produce a bounded plan containing device positions and annotations. Identical inputs should produce identical results.

The first useful layouts are:

- **Grouped layout:** named building/department regions, infrastructure above endpoint grids, consistent spacing and group labels.
- **Tiered layout:** router/core/access/end-device rows when no groups are supplied. Preserve actual cross-links and disconnected components; do not invent a tree that changes connectivity.

Validate unknown devices, duplicate group membership, duplicate move targets, non-finite coordinates and excessive inputs. Account for label lengths, group padding and region bounds. Devices omitted from a partial plan stay in place. Simulator power-distribution items may be omitted from a presentation, but must never be deleted from the topology as a layout shortcut.

Provide an explicit apply operation for an existing plan. Preflight the whole requested set before mutation, then apply sequentially through the existing serialized session. Return per-item outcomes and stop according to the documented policy. If the transport disconnects, retain the set of confirmed items and mark the in-flight operation unknown. Never rerun the plan automatically.

For offline builds, operate only on the working copy and keep save explicit. For live builds, use SDK move/note APIs instead of an automatic save/edit/reopen cycle. Arbitrary rectangle creation has not been verified in the inspected SDK; do not invent a `drawRectangle` API. Native notes can label groups until further shape support is established.

### SVG export

- Render a portable, self-contained SVG from the snapshot and/or plan. Exporting must not mutate the simulator, apply the plan or save a `.pkt`.
- Use consistent vector symbols for routers, switches, hosts and other types, with a clear fallback for unknown models.
- Show group boundaries, device names and a title; make interface/cable labels optional so large networks remain readable.
- Size the viewBox to include all content, wrap long labels and support UTF-8/Arabic text without requiring a specific font download. Keep numeric IP/interface strings legible alongside RTL text.
- Escape XML content, validate style/color inputs, and exclude scripts and external images/resources.
- Display only observed cable/state data. Unknown connectivity stays unknown. A layout is a presentation of a network, not proof of reachability.
- Write to an explicit absolute path and refuse overwriting an existing artifact unless explicitly requested. Return the output path, counts and any omitted/unsupported elements.

A native PNG export is a later option: the SDK has `getWorkspaceImage(String)`, but its argument meaning, image encoding and runtime behavior have not been verified. Do not guess them or add a dependency just to claim screenshot support.

### Acceptance and examples

Use synthetic fixtures for an empty network, a small router/switch/host topology, a cycle, disconnected devices, long/Arabic/XML-special-character labels, and a 50-PC campus grouped 20/20/10 across three buildings. Tests must verify repeatability, no duplicate/missing device positions, sensible group bounds, unchanged links/configuration, XML-safe SVG and safe file handling. Do not merely compare a huge SVG string to itself.

Include small example inputs and generated SVGs suitable for review. Render and inspect the SVG where a renderer is available; report visual inspection as pending when it is not. Native PT placement and save/reopen behavior still need local verification.

## Stage 4 — Later roadmap

After the configuration and visual slices work, add simulation mode/status/stepping, native Simple PDU results, live command history and richer readiness checks using the inspected SDK APIs. These are separate increments, not requirements for calling the first visual slice complete.

Mode changes and simulation reset remain explicit. Adding a PDU does not prove delivery; a frame accepted at one device does not prove end-to-end reachability. Read-only command-log access must not enable, clear or replay logging as a side effect.

## Build and evidence rules

The current Gradle file provides an application build and a live `smoketest`, but no repository Java unit-test cases were found during this handoff. The root `smoke.py` references a particular external `.pkt`; it is not a cloud-portable baseline. Add portable tests rather than depending on that path or relabeling existing JSON captures as tests.

Typical commands, adapted to the actual test suite created by the implementation:

```sh
# Python syntax/import checks; these are not behavior tests.
python3 -m py_compile server.py live_bridge.py ptread.py ptbuild.py model_library.py setup.py

# Use after adding portable unittest tests in tests/.
python3 -m unittest discover -s tests -v

# Only with JDK 21 and the legitimate SDK available.
cd backend/java
./gradlew test installDist
```

Offline MCP integration tests should initialize the real Python server, enumerate tools and exercise synthetic saved-file fixtures with Java/PT absent or deliberately unavailable. Keep stdout valid JSON-RPC and verify optional-backend failure isolation. Catalog tests must compare names, required/optional parameters, result behavior and read-only annotations.

For every handoff, record three independent states:

| Evidence | What qualifies |
|---|---|
| Offline tested | Tests actually ran without PT and verified the stated behavior. |
| SDK compiled | Java compiled against the real installed/provided Cisco SDK. |
| Live verified | A recorded PT run exercised the operation and checked resulting state/persistence. |

Do not mark compile/live states successful merely because mocks passed. If live checks cannot run, list exact local reproduction steps, expected readbacks and unresolved assumptions. Continue useful independent cloud work rather than requesting secrets or treating a missing simulator as a reason to stop all development.

## Definition of done for the first implementation delivery

- Existing tools remain compatible; saved-file workflows still work without the optional backend.
- CLI failure regression is covered and batch partial outcomes are explicit.
- Named creation, rename/move and note tools are implemented with validation/readback.
- A layout planner and SVG exporter produce a readable grouped-campus example without changing connectivity or configuration.
- New tool schemas/catalog/docs are consistent. Tool/version counts describe actual implemented code.
- Portable tests pass; Java compilation and live verification are reported separately with truthful evidence.
- The change contains no second transport, bundled Cisco binaries, credentials or unrequested cloud deployment.

## Prompt to give the cloud coding agent

> Implement the first-delivery scope in `docs/CLOUD-HANDOFF.md`, following `AGENTS.md` and the IPC-only architecture in `IMPROVEMENTS.md`. Work in tested increments: reliable CLI results/batching, then live naming/layout/notes, then deterministic grouped-layout planning and SVG export. Preserve existing APIs, explicit saves, offline independence and no mutation replay. Use `docs/SDK-CAPABILITIES.md` for inspected signatures; do not invent SDK methods. Add portable tests and example visuals. Keep SDK compilation and real Packet Tracer verification distinct from mock/offline tests. If the cloud workspace lacks PT or the proprietary SDK, continue the independent implementation/tests and provide a precise local verification checklist. Do not add a Socket.IO backend, expose remote IPC, deploy a service or claim unperformed checks passed.
