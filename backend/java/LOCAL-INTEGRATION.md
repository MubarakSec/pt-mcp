# Local integration with the existing Python toolkit

This bundled directory supplies the live Java backend for `../../server.py`. The Python server exposes upstream tools with a `pt_live_` prefix and keeps its 21 original saved-file tools. See [the combined setup guide](../../LIVE-SETUP.md). It is tracked in the same Git repository; no submodule or sibling checkout is required.

Local changes:

- `ConnectionManager` reconnects before a new call when needed, but does not replay a failed operation. A lost reply may follow an already applied change.
- `PtIpcClient` accepts `PT_MCP_HOST`, `PT_MCP_PORT`, and `PT_MCP_CONFIG`; it rejects example credential placeholders.
- The Gradle wrapper has executable permissions on Linux.

The SDK JAR is copied locally from Packet Tracer 9.0.1.0858. That installation ships the `pt-cep-java-framework-9.0.0.0.jar` required by this build. Credentials, encrypted registration metadata, and build artifacts stay ignored by Git.

Build with:

```sh
./gradlew installDist --console=plain
```

The Python bridge launches `build/install/pt-mcp/bin/pt-mcp` with this directory as its working directory. Packet Tracer must be running and have the local connector registered with IPC listening on port 39000. Register the connector once; the Python MCP manages Java startup and shutdown.

Verified locally: topology inspection, device creation, Ethernet cabling, IOS configuration/readback, endpoint static address and DHCP lease, save/reopen, and offline parsing of the saved file through the combined Python server. The raw IOS command call can return empty ping output. The added `pt_ping` helper now captures correlated ICMP results, while PC/server diagnostics capture terminal events. Gateway/DNS fields use in-memory live device XML, and HTTP requests use simulated browser completion events. See the combined guide for verified coverage and remaining scope.
