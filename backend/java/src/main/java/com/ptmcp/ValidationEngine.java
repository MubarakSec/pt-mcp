package com.ptmcp;

import java.util.*;
import java.util.function.Consumer;

/** Bounded one-pass validation. Commands are an explicit opt-in and never retried. */
public final class ValidationEngine {
    private ValidationEngine() { }
    public record Observation(String output,String sdkStatus,boolean completed,boolean truncated) { }
    public interface Source {
        Map<String,Object> boot(String device);
        Map<String,Object> terminal(String device);
        Boolean dhcpMode(String device,String iface);
        Observation command(String device,String command,int timeoutMs);
    }
    public static Map<String,Object> evaluate(Source source,List<Map<String,Object>> checks,boolean probes,
            DiagnosticExecutor.Budget budget,Consumer<Map<String,Object>> progress) {
        var results=new ArrayList<Map<String,Object>>();
        var observations=new HashMap<String,Observation>();
        boolean stopped=false;
        for(int i=0;i<checks.size();i++) {
            var check=checks.get(i);Map<String,Object> result;
            if(stopped || budget.remainingMs()<=0) {
                result=DiagnosticsPolicy.result("unknown","observation_unattempted",Map.of());
            } else {
                try {
                    result=one(source,check,probes,budget,observations);
                } catch(DiagnosticExecutor.DeadlineExceeded e) {
                    stopped=true;result=DiagnosticsPolicy.result("unknown","deadline_exceeded",Map.of());
                } catch(RuntimeException e) {
                    stopped=true;result=DiagnosticsPolicy.result("unknown","ipc_observation_failed",Map.of("replayed",false));
                }
            }
            result=new LinkedHashMap<>(result);result.put("index",i);result.put("check",check);
            results.add(result);progress.accept(result);
        }
        return new LinkedHashMap<>(Map.of("status",DiagnosticsPolicy.aggregate(results),"checks",results,
                "active_probes_requested",probes,"replayed",false));
    }
    @SuppressWarnings("unchecked")
    private static Map<String,Object> one(Source source,Map<String,Object> c,boolean probes,
            DiagnosticExecutor.Budget budget,Map<String,Observation> observations) {
        String kind=(String)c.get("kind"),device=(String)c.get("device");
        budget.requireRemaining();
        if(kind.equals("boot")) return source.boot(device);
        if(kind.equals("terminal_idle")) return source.terminal(device);
        String command=kind.equals("dhcp_address")?"ipconfig":"show interfaces trunk";
        if(!probes) return DiagnosticsPolicy.result("unknown","active_probe_required",Map.of("required_command",command));
        String iface=(String)c.get("iface");
        Boolean dhcp=null;
        if(kind.equals("dhcp_address")) {
            dhcp=source.dhcpMode(device,iface);budget.requireRemaining();
            if(Boolean.FALSE.equals(dhcp)) return DiagnosticsPolicy.address(false,iface,null,false,null,false);
        }
        String key=device+"\0"+command;
        Observation observed=observations.get(key);
        if(observed==null) {
            var terminal=source.terminal(device);budget.requireRemaining();
            if("device_not_found".equals(terminal.get("reason"))) return terminal;
            if("fail".equals(terminal.get("status")) || "terminal_outcome_unknown".equals(terminal.get("reason")))
                return DiagnosticsPolicy.result("unknown","terminal_unresolved",Map.of("terminal",terminal));
            observed=source.command(device,command,Math.max(1,budget.remainingMs()));
            observations.put(key,observed); // reuse one observation; never execute again within this request
        }
        budget.requireRemaining();
        return kind.equals("dhcp_address")
            ? DiagnosticsPolicy.address(dhcp,iface,observed.output(),observed.completed(),observed.sdkStatus(),observed.truncated())
            : DiagnosticsPolicy.trunk(iface,(List<Integer>)c.get("vlans"),observed.output(),observed.completed(),observed.sdkStatus(),observed.truncated());
    }
}
