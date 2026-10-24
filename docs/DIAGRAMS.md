# Configuration and presentation workflow

The 0.6.0 implementation keeps saved-file tools independent of Java and uses only
the persistent authenticated Java IPC backend for live operations. New SDK wrappers
are implemented but **not SDK compiled or live verified** in this workspace. See
[implementation evidence](IMPLEMENTATION-EVIDENCE.md) for checks and local acceptance.

## Reliable CLI configuration

`pt_live_run_cli` retains `status` and `output`, adds `outcome` and
`changes_may_have_applied`, and sets MCP `isError` for known IOS failure lines even
with `STATUS_OK`. Classification is deliberately restricted to recognized error
lines, including invalid/ambiguous/incomplete commands, interface-range failures,
per-interface aborts, authorization failures and `% Error` messages. Arbitrary
percent signs, counters or words such as “failed” do not suffice. Unrecognized
errors may still need caller inspection; this is not an exhaustive IOS parser.

`pt_live_run_cli_batch` accepts:

```json
{"device":"Access Switch","initial_mode":"global","commands":["interface FastEthernet0/1","description Accounting","no shutdown"]}
```

`initial_mode` is required (`user`, `enable`, `global`). Later commands inherit the
current context. Supply 1..100 nonempty single-line commands, at most 4096 characters
each. `continue_on_error` defaults to false; enabling it continues after a known
failure in the current, possibly changed context. Unknown transport outcomes always
stop. Results preserve each command/output/status and zero-based `completed`,
`failed`, `unknown`, `unattempted` lists. Completed means the command returned without
a recognized failure, not verified resulting configuration. Inspect running config
and interfaces separately. No batch is atomic; failed interface ranges can partially
apply. No retries, range expansion, rollback or automatic startup-config save occurs.
If the entire bridge reply is lost, the whole call is unknown; its per-item results
are unavailable. Inspect PT before submitting another mutation.

## Live presentation

- `pt_live_add_device`: existing `type`, `model`, `x`, `y` stay required; optional
  unique `name` creates then renames. Omit it for PT automatic naming. Naming failure
  reports the created name and partial/unknown outcome without creating again.
- `pt_live_rename_device`: `name`, `new_name`; same-name requests are allowed.
  Readback concerns display name; it does not promise an IOS hostname change.
- `pt_live_move_device`: `name`, `x`, `y`; coordinates refer to icon origin and must
  be signed 32-bit integers. NaN, infinity, fractions and overflow are rejected.
  The existing add-device API still permits finite fractional creation coordinates.
- `pt_live_get_canvas`: read-only devices/types/models/positions, observed cables
  and native note IDs/text/real coordinates. Cable health remains unknown.
- `pt_live_add_note`: `text`, `x`, `y`. `pt_live_update_note`: `id`, `text`.
  `pt_live_delete_note`: `id`. IDs come from native note membership, never arbitrary
  canvas item IDs. Notes use native real coordinates and return readback.
- `pt_live_apply_layout`: pass `moves` from a plan. Preflights all targets and then
  applies sequentially; stops on first failed/unknown result. Reports confirmed,
  failed, unknown and unattempted indexes. At most 500 moves; no implicit notes.

Names have 1..256 characters without controls. Note text has at most 16384 characters
without NUL. These are tool input limits, not claims about SDK limits. Live moves
and notes need local placement/persistence verification, especially coordinate semantics.
All operations retain explicit saves and leave cables, CLI/IP/VLAN state and power
alone. Whole-call transport failure remains unknown even if some items applied.

## Plan and export without a simulator

`pt_layout_plan` accepts an explicit `snapshot` (such as `pt_live_get_canvas`'s
structured content), or uses the saved file opened with `pt_open`. A snapshot has
`devices` (each with `name`, optional `type`, `model`, `x`, `y`), `links` (with
`dev_a`, `dev_b`, optional `if_a`, `if_b`, `cable_type`, observed `state`) and optional
`notes` (`text`, `x`, `y`). Saved-file `ptread` topology objects are also accepted.
Unknown endpoints are preserved and reported as omitted during export.

```json
{"groups":[{"name":"Engineering","devices":["Access Switch","Office PC"]}]}
```

The deterministic plan contains `moves`, bounded group regions and `annotations`.
Building/department regions put infrastructure above endpoint grids. Without groups,
rows follow router/core/access/endpoint tiers. Unassigned devices occupy a separate
region above the building groups. Links/configuration remain untouched. Devices
omitted from a manually shortened plan stay in place. No layout operation deletes
power-distribution devices or invents a tree to simplify real connectivity.

Limits: 500 devices, 2000 links, 500 notes/annotations and 50 input groups. Unknown
devices, duplicate names/membership/moves and invalid coordinates are rejected.
Groups use padding and wrapped labels; SVG viewBox includes labels and notes.

Preview/export using `pt_export_svg`:

```json
{"path":"/tmp/campus.svg","title":"Campus network","snapshot":{"devices":[],"links":[]},"plan":{"moves":[]},"labels":false,"overwrite":false}
```

Omit `snapshot` to use the opened saved file; omit `plan` to retain current positions.
The path must be absolute. Existing output requires explicit `overwrite:true`;
symlink output is rejected. Export does not apply a layout or save a project.
Vector symbols cover routers, switches and hosts with a fallback for other types.
Text is XML-escaped, wrapped and supports Unicode/Arabic with system fonts; no
scripts, embedded resources or downloaded fonts are required. Interface/cable
labels default off. Dashed gray means unknown; only explicitly observed `up`/`down`
state is colored. Saved cable `functional` flags are not proof of current health.
Native saved graphics are not rendered; export reports this limitation.

Apply offline with `pt_build_open` then `pt_build_apply_layout` (`plan`, optionally
`add_annotations:true`). It validates a copy before replacing the in-memory working
copy, modifies logical positions and explicitly requested notes only, and returns
readback. Use `pt_build_save` explicitly when ready. Read sessions and source files
remain separate from the build copy.

Apply live by passing the plan's `moves` to `pt_live_apply_layout`. To add native
group labels, explicitly submit each plan annotation to `pt_live_add_note`. SVG
boundaries are presentation elements; no unverified rectangle SDK API is used.

Review examples: [50-PC campus](../examples/campus-50.svg),
[small office](../examples/small-network.svg) and adjacent JSON inputs/plans.
Regenerate with `python3 examples/generate_diagrams.py` (overwrites these examples
only). These are synthetic diagrams, not live PT captures or reachability evidence.

## Repeatable checks

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py live_bridge.py diagrams.py diagram_tools.py
# With JDK 21 AND the legitimate local SDK:
cd backend/java
./gradlew test installDist
```

Python unittest runs pure Java policy harnesses using `javac`/`java` when available,
and explicitly skips them otherwise. No fake Cisco production classes are used.
The Gradle task alone does not execute these standalone harnesses; run Python's
suite with JDK 21 on PATH as well. Full SDK adapter compilation and local PT
acceptance remain separate checks.
