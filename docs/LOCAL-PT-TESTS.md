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
- Named creation, attached-cable rename/move, Unicode note add/update/delete.
- With `--save-reopen`: explicit `write memory` on scratch Cisco devices, explicit
  save to a new `.pkt`, reopen that file, compare names/positions/notes/cables
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
Current per-interface DHCP flag semantics, CLI formatting and event ordering still
need this live run. Unit tests exercise harness guards with synthetic replies; they
are not Packet Tracer integration evidence. Do not use existing historical captures
as a substitute for running this harness against the new tools.
