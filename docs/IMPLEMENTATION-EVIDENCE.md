# Implementation evidence

## CLI results and batches

Implemented: known IOS error-line classification with original status/output retained;
`pt_live_run_cli_batch` (1..100 single-line commands, <=4096 characters each), required
`initial_mode` (`user`, `enable`, `global`), optional `continue_on_error` (false).
Indexes are zero-based. Later commands inherit CLI context. Failed commands can
have partially changed state, particularly interface ranges. No rollback, range
expansion, replay or automatic save occurs. Unknown outcomes always stop the batch.
Inspect running configuration/interfaces before further mutations after failure.

Offline tested: Python bridge timeout/disconnect regression proves one request and
no replay. Python syntax checks passed. Java policy harness is supplied in
`tests/java/CliPolicyTest.java`; its runner explicitly skips if no JDK is installed.

SDK compiled: **pending** — this workspace has no JDK or Cisco SDK.
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
