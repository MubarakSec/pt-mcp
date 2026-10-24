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
