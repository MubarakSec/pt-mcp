# Local verification — 2026-10-24

Environment: Packet Tracer 9.0.1, JDK 21 and the legitimate local Cisco 9.0.0.0 SDK. The current connection discovered 63 tools, including 35 live tools, and started the installed Java backend. No Socket.IO transport was added.

## Checks completed

- `python3 -m unittest discover -s tests -v`: all 12 tests passed, including the two standalone Java policy harnesses.
- `cd backend/java && ./gradlew test installDist --offline`: successful. Compilation/distribution tasks were up to date against the local source and SDK. Gradle reported no test sources; the Python suite executes the policy harnesses.
- An initially empty scratch workspace accepted caller-chosen names, attached cabling, live rename, a two-device layout batch, canvas readback and a two-command read-only IOS batch.
- Native ASCII note update and deletion returned successful readback.
- A separate existing lab copy accepted 54 layout moves and 13 ASCII notes. Save/reopen preserved the device set, all 53 cable endpoints/types and every startup/running configuration. The simulator's physical power-distribution object was retained and omitted only from the portable network illustration.
- Router/PC positions persisted exactly. Three switch X coordinates shifted by one pixel on reopen; treat this as observed serialization rounding, not exact persistence.
- Portable SVG export included all 54 logical network devices and 53 links. English and Arabic group labels rendered successfully to PNG/PDF. Gray/dashed link states were retained as unknown rather than inferred from reachability.
- Post-reopen inter-department pings succeeded. Initial first-probe losses disappeared on the subsequent two-probe checks.

## Native Unicode note failure

Adding Arabic text containing U+2014 through the live SDK produced corrupted readback and a `partial` outcome. U+2014 became U+0014, which made that disposable scratch project's saved XML invalid. ASCII update/delete worked afterward. The company lab was loaded separately and only received ASCII native notes; its saved XML parsed successfully. Arabic remained in UTF-8 SVG output.

This is an unresolved release issue: add/update must reject unsafe text before mutation or use a verified Unicode-preserving SDK path. A post-mutation `partial` result does not prevent file corruption. Cover Arabic, accented characters, U+2014 and supplementary characters, then verify both readback and saved XML. Do not mark native Unicode notes supported on this environment until that passes.

## Remaining acceptance work

This run does not verify every 0.6.0 path. Live invalid/partial CLI ranges, disconnect injection, negative coordinates, naming collisions and other PT versions still need their documented acceptance tests. No full-release live-verification claim is made.
