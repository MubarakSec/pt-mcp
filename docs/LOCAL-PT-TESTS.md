# Disposable local Packet Tracer acceptance

The harness is prepared, not live verified. Run it on the same machine as PT with
JDK 21, the legitimate SDK build and registered authenticated IPC. It uses the
existing Python-to-Java stdio bridge only. Never point it at an unrelated project.

```sh
# No Java process, IPC, project edits or saves:
python3 scripts/pt_integration.py

# First run the portable suite and build against your local SDK:
python3 scripts/run_portable_tests.py --require-java
cd backend/java
./gradlew test installDist
# Return to the repository root.
```

Open a **new, empty disposable workspace manually** in PT. The harness requires an
explicit confirmation and independently checks that devices, links and notes are
empty before sending any mutation. It refuses an incomplete canvas response.

```sh
python3 scripts/pt_integration.py --run-live --confirm-empty-workspace \
  --scratch-dir /tmp/pt-mcp-readiness-new-run --save-reopen
```

The scratch directory must be a new absolute path with an existing parent; the
harness will create it. It leaves a local `report.json` and, only with
`--save-reopen`, a new `scratch.pkt`. It never overwrites an existing scratch
project, automatically opens an empty project, or cleans up/rolls back a failed
mutation. Inspect partial results in PT. Do not publish private projects or reports.
Paths refer to the local PT host, not another computer or a remote cloud localhost.

The fixture uses one 2911 router, two 2960 switches and one PC-PT, with unique names,
192.0.2.0/24 DHCP, VLAN 10, two access links and a trunk. These model/port defaults
need an installed compatible catalog. A rejected model/CLI command stops the run;
no fallback mutation or creation retry occurs. Default boot wait is bounded to
90 seconds per wait; `--wait-seconds` accepts 1..300. `--skip-boot` is a separate
explicit opt-in to the existing mutation, never a diagnostic side effect.

Checks cover:

- Authenticated connection versus process availability and read-only readiness.
- Default validation declining active evidence without `allow_probes:true`.
- Actual ipconfig address in DHCP mode and the scratch subnet; VLAN allowed,
  active and STP-forwarding state, plus a negative assertion for VLAN 3999.
- Tracked terminal readiness after completed ipconfig.
- Named creation, attached-cable rename/move, ASCII note add/update/delete; unsafe native Unicode is rejected by the server.
- With `--save-reopen`: explicit `write memory` on scratch Cisco devices, explicit
  save to a new `.pkt`, decode it with the bundled offline decoder and check XML
  well-formedness before reopening (60-second decode bound), then compare names/positions/notes/cables
  independently of native IDs, then recheck boot, DHCP and trunks.

Fresh read probes may repeat after conclusive negative observations while waiting
for boot/DHCP/STP convergence. Unknown output, transport failure, an unresolved
terminal or a lost mutation reply stops the run; it never replays that mutation.

Optionally add `--exercise-terminal-timeout` to explicitly send **one** short-timeout
ping to 203.0.113.254 from the scratch PC and observe late completion through passive
terminal-idle checks. It does not replay the ping. A command that finishes too quickly
or never yields a conclusive completion produces unknown/incomplete evidence.
Interactive PT/other-app terminal commands remain outside this backend's tracking.

Exit 0 means the requested harness checks completed. Nonzero means failure or
unknown; inspect the report's per-step observations. An enabled DHCP flag or an SDK
save/command status alone is not accepted as the final network/persistence result.
Native Unicode note mutation is excluded after the reported PT serialization corruption;
portable unit tests verify Arabic, accents, U+2014, supplementary characters and invalid
controls are rejected before any add/update adapter call. Rebuild the backend before
using this guard. SVG/offline Unicode remains supported.

Current per-interface DHCP flag semantics, CLI formatting and event ordering still
need this live run. Unit tests exercise harness guards with synthetic replies; they
are not Packet Tracer integration evidence. Do not use existing historical captures
as a substitute for running this harness against the new tools.

The pulled 0.6.0 local record reports one-pixel switch X shifts on reopen. The
harness currently compares coordinates exactly and reports such a difference as
a persistence failure; it does not silently relax the criterion. See
[the local record](LOCAL-VERIFICATION-2026-10-24.md) when interpreting that result.

## Opt-in live failure cases

On another empty disposable workspace, add `--exercise-failures`. It checks named
creation/rename collisions against a full before/after canvas view, then sends one
batch containing `interface range FastEthernet0/1-25` and a description marker tail.
The 2960 fixture normally has 24 FastEthernet ports. Acceptance requires index 0
failed, index 1 unattempted, no unknown indexes, and unchanged running configuration
on explicit readback. It never expands/retries the range or repairs CLI context.
An unexpected model behavior, applied tail or uncertain reply stops the harness
and leaves the scratch state for inspection. Run this separately from persistence
acceptance when investigating an SDK/model failure.

For native interrupted-reply acceptance, use only this disposable fixture. Record
a uniquely marked CLI batch call; disable IPC locally in PT while it is in flight,
then inspect the single call's result/report. A genuinely lost reply must be unknown,
with no automatic second submission. Re-enable IPC and inspect actual configuration
and device inventory before any further mutation. If the original reply completed
before IPC was interrupted, record the case as not exercised. This fault injection
requires a local operator; it is **not automated or verified** by the portable suite.
No tunnels, remote IPC or credentials are required or exposed by this procedure.

`--exercise-terminal-timeout` now collects the retained operation ID/output with
`pt_live_get_terminal_result`; it does not rerun the timed-out command. Native event
ordering and late-output capture need the local run. A successful terminal result
collection is not proof the ping destination was reachable.
