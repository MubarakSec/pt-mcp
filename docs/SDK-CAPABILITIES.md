# Inspected Cisco SDK capabilities

Inspected locally on 2026-10-24 with `javap -public` against `pt-cep-java-framework-9.0.0.0.jar` from the Packet Tracer installation. This records signatures relevant to the backlog so a cloud agent does not have to guess them. The JAR is proprietary and remains gitignored; this document does not distribute it.

**The signatures below establish API availability only.** The local 0.6.0 build and selected naming/move/note/canvas runs are recorded separately. New readiness/retained-result adapters still require SDK compilation and live verification. Simulation/PDU/history wrappers remain later work. See [implementation evidence](IMPLEMENTATION-EVIDENCE.md). Compilation and successful local PT integration are separate requirements. The installed application used for previous network work was Packet Tracer 9.0.1; do not infer support for other versions.

## Existing access path

`PtIpcClient` holds a `com.cisco.pt.ptmp.PacketTracerSession` and a `com.cisco.pt.ipc.ui.IPC`. The IPC interface exposes:

```java
Network network();
AppWindow appWindow();
CommandLog commandLog();
Simulation simulation();
```

The current client already provides package-level `network()`, `logicalWorkspace()`, `appWindow()` and `session()` helpers. Its logical workspace comes from `ipc.appWindow().getActiveWorkspace().getLogicalWorkspace()`. Reuse the established client/session ownership; inspect the source before exposing additional helpers. Do not infer that `PacketTracerSession` itself has those IPC methods.

## Device naming and coordinates

`com.cisco.pt.ipc.sim.Device`:

```java
void setName(String name);
String getName();
double getXCoordinate();
double getYCoordinate();
double getCenterXCoordinate();
double getCenterYCoordinate();
boolean moveToLocation(int x, int y);
boolean moveToLocationCentered(int x, int y);
String serializeToXml();
```

The existing workspace creation method is:

```java
String addDevice(DeviceType type, String model, double x, double y);
```

It does not accept a requested name. Creation followed by naming can partially succeed, so callers need the actual created name and an explicit outcome. Define origin-versus-center coordinates and verify readback; SDK method names alone do not establish placement semantics or hostname behavior.

## Native notes and canvas

`com.cisco.pt.ipc.ui.LogicalWorkspace`:

```java
List<UUID> getCanvasItemIds();
List<UUID> getCanvasNoteIds();
int getCanvasItemX(UUID id);
int getCanvasItemY(UUID id);
int getCanvasItemRealX(UUID id);
int getCanvasItemRealY(UUID id);
void setCanvasItemRealPos(UUID id, int x, int y);
void setCanvasItemX(UUID id, int x);
void setCanvasItemY(UUID id, int y);
void moveCanvasItemBy(UUID id, int dx, int dy);
UUID addNote(int x, int y, double z, String text);
String getCanvasNoteText(UUID id);
double getIncNoteZOrder();
boolean changeNoteText(UUID id, String text);
boolean removeCanvasItem(UUID id);
List<Byte> getWorkspaceImage(String value);
```

`UUID` here is Cisco's `com.cisco.pt.UUID`, not `java.util.UUID`. Resolve/validate incoming identifiers against native note IDs instead of guessing constructor/parsing behavior. `removeCanvasItem` is broader than deleting a note; a note-delete tool must verify membership in `getCanvasNoteIds()` first.

The workspace also exposes `drawLine(...)` and `drawCircle(...)`. Arbitrary rectangle creation was not established. `getWorkspaceImage` exists, but the inspected signature does not explain the string parameter or returned encoding. Verify those details before shipping image export. Standalone SVG generation does not require this API.

## Simulation

`com.cisco.pt.ipc.system.Simulation`:

```java
boolean isSimulationMode();
void setSimulationMode(boolean enabled);
long getCurrentSimTime();
int getFrameInstanceCount();
FrameInstance getFrameInstanceAt(int index);
int getCurrentFrameInstanceIndex();
void forward();
void backward();
void resetSimulation();
```

The JAR also contains simulation event types including `ForwardStarted`, `ForwardEnded`, `NewFrameInstanceAdded`, `SimulationModeChanged` and `SimulationReset`. Inspect the event registry's actual API and correlate completion before claiming that a requested step finished. An invocation returning normally is not proof that all asynchronous simulation work completed.

## Simple PDU creation and frame results

`com.cisco.pt.ipc.ui.UserCreatedPDU`:

```java
ADD_PDU_ERROR addSimplePdu(String source, String destination);
```

Obtain the controller through the existing app-window API after checking its signature. Use the real `ADD_PDU_ERROR` enum rather than copying numeric assumptions from the JavaScript reference project. A successful creation result does not establish delivery.

Relevant `com.cisco.pt.ipc.sim.FrameInstance` methods:

```java
TrafficType getUserTrafficType();
String getSourceString();
String getDestinationString();
Device getDevice();
Device getPreviousDevice();
boolean isFrameAccepted();
boolean isFrameDropped();
boolean isFrameNotForwarded();
boolean isFrameUnexpected();
boolean isFrameBuffered();
boolean isFrameOnTransit();
boolean isFrameSent();
boolean isFrameCollidedOnLink();
boolean isFrameCollidedAtDevice();
long getStartSimTime();
```

Frames are per-stage observations. Define filtering, limits, ordering and end-to-end interpretation rather than flattening all successful frame flags into a successful ping.

## Live command history

`com.cisco.pt.ipc.system.CommandLog`:

```java
boolean isEnabled();
int getEntryCount();
CommandLogEntry getEntryAt(int index);
```

`CommandLogEntry`:

```java
String getTimeToString();
String getDeviceName();
String getPrompt();
String getCommand();
String getResolvedCommand();
```

The log also exposes `clear()` and `setEnabled(boolean)`. They are mutations and are not needed for a read-only history tool. Saved-file history already exists as `pt_command_logs` in `server.py`; new live history must be documented separately.

## Reproducing the inspection

Use a legitimately installed SDK in your environment. This example path is repository-relative and ignored:

```sh
javap -public \
  -classpath backend/java/libs/pt-cep-java-framework-9.0.0.0.jar \
  com.cisco.pt.ipc.ui.IPC \
  com.cisco.pt.ipc.sim.Device \
  com.cisco.pt.ipc.ui.LogicalWorkspace \
  com.cisco.pt.ipc.system.Simulation \
  com.cisco.pt.ipc.ui.UserCreatedPDU \
  com.cisco.pt.ipc.sim.FrameInstance \
  com.cisco.pt.ipc.system.CommandLog \
  com.cisco.pt.ipc.system.CommandLogEntry
```

This is a discovery command, not a live acceptance test. A cloud agent without the SDK should use this snapshot for planning and explicitly mark compilation/runtime checks pending.


## Readiness adapters — existing API use

The readiness stage reuses methods already present in the baseline source:
`Device.getPower`, `CiscoDevice.isBooting`, `Pc.getPort`,
`HostPort.isDhcpClientOn`, `Pc.getDhcpFlag`, `CiscoDevice.getIpcTerminalLine`,
`Pc.getCommandPrompt`, terminal UUID/prompt and the existing terminal event registry.
No uninspected lease/trunk SDK getter is invented. Actual IPv4 addresses and trunk
forwarding are evaluated from explicitly requested ipconfig/IOS show observations.
Pure evaluation/tracking tests run without Cisco classes. New adapter compilation,
per-interface DHCP mode semantics, CLI formats and event ordering remain local
checks; baseline compilation does not establish those new runtime results.
