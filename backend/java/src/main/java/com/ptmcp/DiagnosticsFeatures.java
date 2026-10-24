package com.ptmcp;

import com.cisco.pt.ipc.IPCError;
import com.cisco.pt.ipc.sim.CiscoDevice;
import com.cisco.pt.ipc.sim.Device;
import com.cisco.pt.ipc.sim.HostPort;
import com.cisco.pt.ipc.sim.Pc;
import java.util.*;
import java.util.function.Supplier;

/** Observations through existing SDK methods only. Never changes configuration or power. */
final class DiagnosticsFeatures implements ValidationEngine.Source {
    private final PtIpcClient client;
    private final DiagnosticExecutor.Budget budget;
    DiagnosticsFeatures(PtIpcClient client,DiagnosticExecutor.Budget budget) {this.client=client;this.budget=budget;}
    private <T> T read(Supplier<T> action) {
        budget.requireRemaining();
        try {return action.get();} catch(IPCError e) {throw new IllegalStateException("IPC observation failed",e);}
    }
    private Device device(String name) {return read(() -> client.network().getDevice(name));}
    private Map<String,Object> missing(String device) {
        return DiagnosticsPolicy.result("fail","device_not_found",Map.of("device",device,"source","Network.getDevice"));
    }
    public Map<String,Object> boot(String name) {
        Device d=device(name);if(d==null) return missing(name);
        boolean power=read(d::getPower);
        if(!power) return DiagnosticsPolicy.boot(false,null);
        Boolean booting=null;
        if(d instanceof CiscoDevice c) {
            try {booting=read(c::isBooting);} catch(IllegalStateException unavailable) {return DiagnosticsPolicy.boot(power,null);}
        }
        return DiagnosticsPolicy.boot(power,booting);
    }
    public Map<String,Object> terminal(String name) {
        Device d=device(name);if(d==null) return missing(name);
        try {
            String uuid=read(() -> PingTerminalFeatures.terminalLine(d).getObjectUUID().toString());
            return client.terminalActivity().snapshot(uuid);
        } catch(IllegalArgumentException unsupported) {
            return DiagnosticsPolicy.result("unknown","terminal_not_supported",Map.of("device",name));
        }
    }
    public Boolean dhcpMode(String name,String iface) {
        Device d=device(name);
        if(!(d instanceof Pc pc)) return null;
        var port=read(() -> pc.getPort(iface));
        if(!(port instanceof HostPort host)) return null;
        boolean perPort=read(host::isDhcpClientOn),global=read(pc::getDhcpFlag);
        // The global PC flag cannot establish the mode of a particular adapter.
        return perPort?Boolean.TRUE:global?null:Boolean.FALSE;
    }
    public ValidationEngine.Observation command(String name,String command,int timeoutMs) {
        Device d=device(name);
        if(d==null) throw new IllegalStateException("device missing");
        if(command.equals("ipconfig") && !(d instanceof Pc))
            throw new IllegalArgumentException("ipconfig requires a PC/server command prompt");
        if(command.equals("show interfaces trunk") && !(d instanceof CiscoDevice))
            throw new IllegalArgumentException("trunk inspection requires Cisco CLI");
        Map<String,Object> result=read(() -> PingTerminalFeatures.runTerminal(client,client.session(),name,command,timeoutMs));
        String output=(String)result.get("output");
        boolean truncated=Boolean.TRUE.equals(result.get("outputTruncated")) || (output!=null && output.length()>DiagnosticsPolicy.MAX_OUTPUT);
        return new ValidationEngine.Observation(output,(String)result.get("status"),Boolean.TRUE.equals(result.get("completed")),truncated);
    }
}
