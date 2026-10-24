package com.ptmcp;

import com.cisco.pt.ipc.enums.DeviceType;
import com.cisco.pt.ipc.events.PingProcessEvent;
import com.cisco.pt.ipc.events.PingProcessEventListener;
import com.cisco.pt.ipc.events.TerminalLineEvent;
import com.cisco.pt.ipc.events.TerminalLineEventListener;
import com.cisco.pt.ipc.events.PingProcessEventRegistry;
import com.cisco.pt.ipc.events.TerminalLineEventRegistry;
import com.cisco.pt.ipc.sim.CiscoDevice;
import com.cisco.pt.ipc.sim.Device;
import com.cisco.pt.ipc.sim.ICMPProcess;
import com.cisco.pt.ipc.sim.Pc;
import com.cisco.pt.ipc.sim.PingProcess;
import com.cisco.pt.ipc.sim.Process;
import com.cisco.pt.ipc.sim.TerminalLine;
import com.cisco.pt.impl.IPAddressImpl;
import com.cisco.pt.ptmp.PacketTracerSession;

import java.net.InetAddress;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.concurrent.atomic.AtomicReference;

/** Live terminal operations backed by Packet Tracer's terminal event stream. */
public final class PingTerminalFeatures {
    private static final int DEFAULT_TIMEOUT_MS = 30_000;
    private static final int MAX_TIMEOUT_MS = 120_000;
    private static final int MAX_COUNT = 20;
    private static final int MAX_OUTPUT_CHARS = 32_768;

    private PingTerminalFeatures() { }

    /**
     * Runs one real ping command and reports its captured terminal output. The
     * packet counts are extracted only when the device prints them; otherwise
     * they are null and the caller must not infer success from command return.
     */
    public static Map<String, Object> livePing(PtIpcClient client,
                                                PacketTracerSession session,
                                                String deviceName,
                                                String target,
                                                int timeoutMs,
                                                int count) {
        if (client == null || session == null) throw new IllegalArgumentException("IPC client/session is required.");
        if (count < 1 || count > MAX_COUNT) throw new IllegalArgumentException("count must be between 1 and " + MAX_COUNT + ".");
        if (target == null || target.length() > 45 || !isIpAddress(target)) {
            throw new IllegalArgumentException("target must be an IPv4 or IPv6 address.");
        }
        Device device = requireDevice(client, deviceName);
        if (device.getType() == DeviceType.ROUTER || device.getType() == DeviceType.SWITCH
                || device.getType() == DeviceType.MULTI_LAYER_SWITCH || device.getType() == DeviceType.SWITCH3650) {
            return liveCiscoPing(session, device, target, boundedTimeout(timeoutMs), count);
        }
        String command;
        if (device.getType() == DeviceType.PC || device.getType() == DeviceType.SERVER) {
            command = "ping -n " + count + " " + target;
        } else {
            throw new IllegalArgumentException("live ping supports routers, switches, PCs, and servers only.");
        }
        return runOnTerminal(client, session, device, command, boundedTimeout(timeoutMs), true, count, true);
    }

    private static Map<String, Object> liveCiscoPing(PacketTracerSession session, Device device,
                                                      String target, int timeoutMs, int count) {
        if (target.indexOf(':') >= 0) {
            throw new IllegalArgumentException("Cisco ICMPProcess live ping currently supports IPv4 targets only.");
        }
        Process processObject = device.getProcess("IcmpProcess");
        if (!(processObject instanceof ICMPProcess)) {
            throw new IllegalStateException("Device does not expose the Packet Tracer ICMP process required for live ping.");
        }
        ICMPProcess icmp = (ICMPProcess) processObject;
        // Create first, attach a listener to this unique process ID, then start.
        // This prevents an old global DonePing event or a fast completion from
        // being mistaken for this request.
        int perProbeTimeout = Math.max(1, Math.min(1000, timeoutMs / (count + 1)));
        Short id = icmp.createPingProcess(IPAddressImpl.parseIPAddress(target), count,
                perProbeTimeout, 0, "");
        if (id == null) throw new IllegalStateException("Packet Tracer did not create a ping process.");
        PingProcess ping = icmp.getPingProcess(id);
        if (ping == null) throw new IllegalStateException("Packet Tracer created ping process " + id + " but did not return it.");
        String processUuid = ping.getObjectUUID().toString();
        int plannedCount = ping.getTotalCount();

        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Integer> eventReceived = new AtomicReference<>();
        PingProcessEventListener listener = event -> {
            if (event instanceof PingProcessEvent.DonePing && event.objectUUID != null
                    && processUuid.equals(event.objectUUID.toString())) {
                eventReceived.set(((PingProcessEvent.DonePing) event).receiveCount);
                done.countDown();
            }
        };
        PingProcessEventRegistry registry = session.getEventManager().getPingProcessEvents();
        boolean registered = false;
        long started = System.currentTimeMillis();
        try {
            // Use the global registry and filter by the cached UUID. PT destroys
            // completed PingProcess objects before listener cleanup; the SDK's
            // specific-listener removal then dereferences a null object UUID.
            registry.addListener(listener);
            registered = true;
            ping.start();
            boolean completed = done.await(timeoutMs, TimeUnit.MILLISECONDS);
            Integer received = eventReceived.get();
            Integer sent = null;
            if (!completed) {
                // While still active, counters may be readable. A finished
                // process is destroyed by PT, so never query it after DonePing.
                if (received == null) {
                    try {
                        sent = ping.getSentCount();
                        received = ping.getReceivedCount();
                    } catch (com.cisco.pt.ipc.IPCError | RuntimeException ignored) {
                        sent = null;
                        received = eventReceived.get();
                    }
                }
                try { ping.cancel(); } catch (com.cisco.pt.ipc.IPCError | RuntimeException ignored) { }
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("device", device.getName());
            result.put("command", "ICMPProcess.startPing(" + target + ")");
            result.put("completed", completed);
            result.put("timedOut", !completed);
            result.put("durationMs", System.currentTimeMillis() - started);
            result.put("status", completed ? "DONE_PING" : null);
            result.put("requestedCount", count);
            result.put("countApplied", true);
            result.put("plannedCount", plannedCount);
            result.put("sent", sent);
            result.put("received", received);
            result.put("lossPercent", null);
            result.put("lossRelativeToRequestedProbes", received == null ? null
                    : 100.0 * (count - received) / count);
            result.put("lossBasis", "requestedCount");
            result.put("resultNote", "Packet Tracer destroys the completed ping process, so its sent counter is unavailable. Received replies come from the matching DonePing event.");
            String outcome = received == null ? "unknown"
                    : (completed ? (received > 0 ? "success" : "failure") : "unknown");
            result.put("outcome", outcome);
            result.put("success", "success".equals(outcome) ? Boolean.TRUE
                    : ("failure".equals(outcome) ? Boolean.FALSE : null));
            return result;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            try { ping.cancel(); } catch (com.cisco.pt.ipc.IPCError | RuntimeException ignored) { }
            throw new IllegalStateException("Interrupted while waiting for Packet Tracer ping results.", e);
        } catch (java.io.IOException e) {
            throw new IllegalStateException("Could not subscribe to Packet Tracer ping events: " + e.getMessage(), e);
        } finally {
            if (registered) {
                try { registry.removeListener(listener); } catch (java.io.IOException ignored) { }
            }
        }
    }

    /** Runs one command on the device's own CLI/command prompt and captures SDK events. */
    public static Map<String, Object> runTerminal(PtIpcClient client,
                                                   PacketTracerSession session,
                                                   String deviceName,
                                                   String command,
                                                   int timeoutMs) {
        if (client == null || session == null) throw new IllegalArgumentException("IPC client/session is required.");
        if (command == null || command.trim().isEmpty() || command.length() > 512
                || command.indexOf('\n') >= 0 || command.indexOf('\r') >= 0 || command.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("command must be a single non-empty line of at most 512 characters.");
        }
        Device device = requireDevice(client, deviceName);
        validateTerminalCommand(device, command);
        if (device instanceof CiscoDevice && command.trim().toLowerCase(java.util.Locale.ROOT).startsWith("show ")) {
            PtIpcClient.CliResult cli = client.runCli(deviceName, command, "enable");
            Map<String,Object> result = new LinkedHashMap<>();
            result.put("device", deviceName);
            result.put("command", command);
            result.put("completed", true);
            result.put("timedOut", false);
            result.put("status", cli.status);
            result.put("output", cli.output);
            result.put("source", "CiscoDevice.enterCommand");
            result.put("operation_id",cli.operationId);
            return result;
        }
        return runOnTerminal(client, session, device, command, boundedTimeout(timeoutMs), false, 0, false);
    }

    private static Map<String, Object> runOnTerminal(PtIpcClient client, PacketTracerSession session, Device device,
                                                      String command, int timeoutMs, boolean ping,
                                                      int requestedCount, boolean countApplied) {
        TerminalLine line = terminalLine(device);
        String terminalUuid = line.getObjectUUID().toString();
        CountDownLatch ended = new CountDownLatch(1);
        CountDownLatch promptReady = new CountDownLatch(1);
        String expectedPrompt = line.getPrompt();
        StringBuilder output = new StringBuilder();
        final String[] status = {null};
        TerminalLineEventListener listener = event -> {
            if (event.objectUUID == null || !terminalUuid.equals(event.objectUUID.toString())) return;
            if (event instanceof TerminalLineEvent.OutputWritten) {
                String part = ((TerminalLineEvent.OutputWritten) event).newOutput;
                synchronized (output) {
                    if (part != null && output.length() < MAX_OUTPUT_CHARS) {
                        int remaining = MAX_OUTPUT_CHARS - output.length();
                        output.append(part, 0, Math.min(part.length(), remaining));
                    }
                }
                if (part != null && expectedPrompt != null && !expectedPrompt.isBlank()
                        && part.trim().endsWith(expectedPrompt.trim())) promptReady.countDown();
            } else if (event instanceof TerminalLineEvent.PromptChanged) {
                String prompt = ((TerminalLineEvent.PromptChanged) event).newPrompt;
                if (prompt != null && !prompt.isBlank()) promptReady.countDown();
            } else if (event instanceof TerminalLineEvent.CommandEnded) {
                TerminalLineEvent.CommandEnded endedEvent = (TerminalLineEvent.CommandEnded) event;
                status[0] = endedEvent.status == null ? null : endedEvent.status.name();
                ended.countDown();
            }
        };
        TerminalLineEventRegistry registry = session.getEventManager().getTerminalLineEvents();
        boolean registered = false;
        long token=0;
        TerminalMonitor monitor=client.terminalMonitor();
        long started = System.currentTimeMillis();
        try {
            // A globally registered, UUID-filtered listener also avoids the
            // SDK's stale per-object subscription after remove/add cycles.
            registry.addListener(listener);
            registered = true;
            token=monitor.begin(terminalUuid,device.getName(),device instanceof Pc,expectedPrompt);
            line.enterCommand(command);
            boolean completed = ended.await(timeoutMs, TimeUnit.MILLISECONDS);
            // CommandEnded can precede the host prompt becoming ready. Keep
            // listening until the prompt arrives before returning to the caller.
            if (completed && device instanceof Pc) promptReady.await(1000, TimeUnit.MILLISECONDS);
            String text;
            synchronized (output) { text = output.toString(); }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("device", device.getName());
            result.put("command", command);
            result.put("completed", completed);
            result.put("timedOut", !completed);
            result.put("durationMs", System.currentTimeMillis() - started);
            result.put("status", status[0]);
            result.put("output", text);
            result.put("outputTruncated", text.length() >= MAX_OUTPUT_CHARS);
            result.put("operation_id",token);
            result.put("terminal_activity",client.terminalActivity().snapshot(terminalUuid));
            if (!completed) result.put("note", "Native terminal command may still be running; its session listener remains attached. Do not replay it.");
            if (ping) {
                Integer[] counts = parseCounts(text);
                result.put("sent", counts[0]);
                result.put("received", counts[1]);
                result.put("requestedCount", requestedCount);
                result.put("countApplied", countApplied);
                result.put("lossPercent", counts[0] == null || counts[1] == null || counts[0] == 0
                        ? null : 100.0 * (counts[0] - counts[1]) / counts[0]);
                String outcome = counts[1] == null ? "unknown"
                        : (completed && "STATUS_OK".equals(status[0])
                                ? (counts[1] > 0 ? "success" : "failure") : "unknown");
                result.put("outcome", outcome);
                result.put("success", "success".equals(outcome) ? Boolean.TRUE
                        : ("failure".equals(outcome) ? Boolean.FALSE : null));
            }
            return result;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            if(token!=0) client.terminalActivity().uncertain(terminalUuid,token);
            throw new IllegalStateException("Interrupted while waiting for Packet Tracer terminal output.", e);
        } catch(com.cisco.pt.ipc.IPCError | RuntimeException failure) {
            if(token!=0) client.terminalActivity().uncertain(terminalUuid,token);
            throw failure;
        } catch (java.io.IOException e) {
            throw new IllegalStateException("Could not subscribe to Packet Tracer terminal events: " + e.getMessage(), e);
        } finally {
            if (registered) {
                try { registry.removeListener(listener); } catch (java.io.IOException ignored) { }
            }
        }
    }

    static TerminalLine terminalLine(Device device) {
        DeviceType type = device.getType();
        if (type == DeviceType.ROUTER || type == DeviceType.SWITCH
                || type == DeviceType.MULTI_LAYER_SWITCH || type == DeviceType.SWITCH3650) {
            if (!(device instanceof CiscoDevice)) throw new IllegalArgumentException("Device has no Cisco CLI terminal.");
            TerminalLine line = ((CiscoDevice) device).getIpcTerminalLine();
            if (line == null) throw new IllegalStateException("Device CLI terminal is unavailable.");
            return line;
        }
        if (type == DeviceType.PC || type == DeviceType.SERVER) {
            if (!(device instanceof Pc)) throw new IllegalArgumentException("Device has no PC command prompt.");
            TerminalLine line = ((Pc) device).getCommandPrompt();
            if (line == null) throw new IllegalStateException("Device command prompt is unavailable.");
            return line;
        }
        throw new IllegalArgumentException("Terminal operations support routers, switches, PCs, and servers only.");
    }

    private static Device requireDevice(PtIpcClient client, String name) {
        if (name == null || name.trim().isEmpty()) throw new IllegalArgumentException("device is required.");
        Device device = client.network().getDevice(name);
        if (device == null) throw new IllegalArgumentException("No device named '" + name + "'.");
        return device;
    }

    private static void validateTerminalCommand(Device device, String command) {
        String normalized = command.trim().toLowerCase(java.util.Locale.ROOT);
        if (normalized.matches("show(?:\\s+[a-z0-9./:_-]+)*")) return;
        if (normalized.matches("ping\\s+[0-9a-f:.]+(?:\\s+repeat\\s+[1-9][0-9]?)?")) return;
        if (device.getType() == DeviceType.PC || device.getType() == DeviceType.SERVER) {
            if (normalized.matches("ipconfig(?:\\s+/all)?") || normalized.equals("arp -a")
                    || normalized.equals("netstat") || normalized.equals("route print")
                    || normalized.matches("tracert\\s+[0-9a-f:.]+")
                    || normalized.matches("nslookup\\s+[a-z0-9.-]+")) return;
        }
        throw new IllegalArgumentException("Unsupported terminal command. Use a read-only 'show ...' command on network devices, or ipconfig, arp -a, netstat, route print, tracert <IP>, or nslookup <host> on PCs/servers.");
    }

    private static int boundedTimeout(int timeoutMs) {
        int value = timeoutMs <= 0 ? DEFAULT_TIMEOUT_MS : timeoutMs;
        if (value > MAX_TIMEOUT_MS) throw new IllegalArgumentException("timeoutMs must not exceed " + MAX_TIMEOUT_MS + ".");
        return value;
    }

    private static boolean isIpAddress(String value) {
        try {
            if (value.indexOf(':') < 0 && !value.matches("[0-9.]+")) return false;
            InetAddress.getByName(value);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private static Integer[] parseCounts(String output) {
        // IOS: "Success rate is 80 percent (4/5)"; PC: "Sent = 5, Received = 4".
        Matcher ios = Pattern.compile("(?i)success rate is\\s+\\d+\\s+percent\\s*\\((\\d+)\\s*/\\s*(\\d+)\\)").matcher(output);
        if (ios.find()) return new Integer[]{Integer.parseInt(ios.group(2)), Integer.parseInt(ios.group(1))};
        Matcher pc = Pattern.compile("(?i)sent\\s*=\\s*(\\d+).*?received\\s*=\\s*(\\d+)", Pattern.DOTALL).matcher(output);
        if (pc.find()) return new Integer[]{Integer.parseInt(pc.group(1)), Integer.parseInt(pc.group(2))};
        return new Integer[]{null, null};
    }

}
