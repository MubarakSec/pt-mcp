# Readiness and evidence-based validation

This stage retains Java IPC, independent offline tools and explicit saves. It adds
three Java tools, mapped to client-facing `pt_live_*` names by the Python bridge.
No configuration, power, boot skipping, DHCP renewals or project saves occur in
these tools. Simulation/PDU work and broader planning/visual changes are deferred.

## Process availability versus authentication

`pt_live_status` stays passive: it does not start Java or contact PT. Existing fields
remain; `ipc_authentication` is always `unknown`. `last_connection_probe`, when
present, is a historical observation with a timestamp, never current authentication
proof. A running Java child only establishes process availability.

Explicitly call `pt_live_probe_connection` with optional `timeout_ms` (default 10000,
range 1..30000). It attempts authentication through the existing session and reads
a fresh device count. `pass` requires both a live network read and a connected
session. An explicit authentication rejection is `fail`. A lost reply, unavailable
backend, unsupported observation or timeout is `unknown`; no transport retry occurs.
No credentials or native exception messages appear in diagnostic evidence.

## Passive device readiness

```json
{"devices":["Router0","PC0"],"timeout_ms":5000}
```

`pt_live_get_readiness` accepts 1..20 unique names. It returns boot/power and tracked
terminal-idle observations per device without sending any terminal command. Cisco
booting or powered-off state fails boot readiness. A powered device with an
unavailable/unsupported boot getter is unknown; PCs are not assumed booted because
power is on. A missing device is a failure based on `Network.getDevice`.

Terminal evidence is scoped to **commands tracked by this backend connection**.
It cannot establish whether a GUI user or another application has an outstanding
command. No terminal history is unknown. A tracked pending command fails the idle
check; an uncertain dispatch is unknown and blocks another tracked dispatch.
A completed tracked command passes idle readiness even if that command failed.
For PCs, both CommandEnded and a ready prompt are required. A session listener
survives request timeouts to observe late completion. Disconnect/restart loses this
history and returns unknown, never an idle claim. Inspect PT before resuming an
uncertain operation; restarting the backend is not evidence the operation ended.

## Network assertions

```json
{
  "checks":[
    {"kind":"boot","device":"Router0"},
    {"kind":"terminal_idle","device":"PC0"},
    {"kind":"dhcp_address","device":"PC0","iface":"FastEthernet0"},
    {"kind":"trunk_vlan","device":"Switch0","iface":"GigabitEthernet0/1","vlans":[10,20]}
  ],
  "allow_probes":true,
  "timeout_ms":10000
}
```

`pt_live_validate_network` accepts 1..20 checks, prevalidated in full before IPC.
Checks allow only their documented fields. Names follow the existing 1..256
character contract. Trunk VLANs are 1..128 unique integer IDs in 1..4094.

`allow_probes` defaults to false. Boot and tracked-terminal checks can still run;
address and trunk checks return `unknown / active_probe_required`. With explicit
permission, the tool may send **ipconfig** or **show interfaces trunk**, once per
device/command per validation call. It does not ping, renew DHCP, configure an
interface or save. IOS show commands select enable mode, so the explicit probe
can change CLI context. A pending/uncertain tracked terminal prevents a probe.

DHCP address success needs a per-interface DHCP-mode observation and a completed,
nontruncated, successful `ipconfig` block for the exact interface, containing a
usable IPv4 address. Stored HostPort addresses are never accepted as active-address
evidence. 0.0.0.0, loopback, multicast and 169.254/16 do not pass. Static mode fails.
A global PC DHCP flag without per-interface confirmation is unknown. The report
exposes `observed_address` when available and `lease_server_confirmed:false`:
this is an actual address observed while in DHCP mode, not a server-side lease or
reachability guarantee. IPv6, localized/ambiguous output and unsupported endpoint
models remain unknown.

Trunk success needs an operational `trunking` row and all three observed sections:
allowed VLANs, allowed/active VLANs and STP-forwarding/not-pruned VLANs. Every
requested VLAN must appear in all three. Recognized missing memberships fail.
Malformed ranges, wrapped/ambiguous sections, missing rows, unsupported CLI,
pagination, truncation and incomplete replies are unknown. Interface aliases such
as Gi/Gig/GigabitEthernet are normalized. Configuration alone never proves forwarding.

Each check returns `status:pass|fail|unknown`, `reason`, host UTC `observed_at` and
observed `evidence`; command evidence has a bounded excerpt. Whole-call status is
fail if any check conclusively fails, otherwise unknown if any is unknown, otherwise
pass. This is conjunction of the requested assertions, not global network health.
Diagnostic failures are ordinary tool results; malformed arguments set MCP isError.

## Deadlines and failure handling

One diagnostic can be in flight per Java server. Total diagnostic work has a shared
monotonic deadline, 1..30000 ms. Confirmed per-check results are preserved on timeout;
unresolved/unattempted observations remain unknown. The Python bridge includes
child initialization in a hard deadline, with at most one additional second for
protocol overhead (process termination may add up to four seconds).

A proprietary SDK call may not be interruptible. On timeout it is **not cancelled
or replayed**. The worker remains the single in-flight diagnostic, and later
diagnostics return unknown/busy until it finishes. It starts no subsequent checks
once its deadline expires. Other SDK operations remain serialized by the existing
connection manager; a stuck native call can prevent their progress. Inspect/restart
locally when needed. A bridge-level timeout loses unreturned Java progress and is
reported unknown. No mutation is automatically retried.

## Evidence and local verification

The owner reports all 12 baseline tests and the full Cisco SDK build passed locally
at `b5d74c0`. That report establishes baseline compilation only; live verification
remains pending. The current workspace still lacks the proprietary SDK. New pure
policy tests, synthetic parsing tests and bridge tests are offline evidence, not
SDK compilation or PT integration. New adapter compilation and live verification
must be performed locally; see the stage entry in IMPLEMENTATION-EVIDENCE.md.

## Portable CI

`.github/workflows/portable-tests.yml` runs Python-only checks and a Python
3.10/3.12 + JDK 21 matrix on pushes/PRs/manual dispatch. Actions are pinned to
upstream commit IDs; permissions are read-only. No credentials, PT, SDK downloads
or Gradle compilation are used. Catalog/schema/annotation checks are included.

Local equivalents:

```sh
python3 scripts/run_portable_tests.py --python-only
# With JDK 21+ on PATH; this mode fails if Java is missing or any test skips:
python3 scripts/run_portable_tests.py --require-java
```

Python-only mode deliberately skips the five Java harness cases. Normal unittest
still auto-runs them when Java is present. Hosted CI results must be checked after
pushing; a local run of equivalent commands is not a hosted CI result.
