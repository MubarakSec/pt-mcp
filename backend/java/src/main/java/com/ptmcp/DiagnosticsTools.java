package com.ptmcp;

import io.modelcontextprotocol.json.McpJsonMapper;
import io.modelcontextprotocol.server.McpServerFeatures.SyncToolSpecification;
import io.modelcontextprotocol.spec.McpSchema.CallToolResult;
import java.util.*;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Supplier;

/** MCP descriptors and bounded, serialized diagnostic orchestration. */
final class DiagnosticsTools {
    private DiagnosticsTools() { }
    static List<SyncToolSpecification> tools(McpJsonMapper jm,ConnectionManager conn) {
        var gate=new DiagnosticExecutor();
        return List.of(
            PtMcpServer.tool(jm,"pt_probe_connection","Explicitly attempt authenticated IPC and a fresh network read once; process availability alone proves no authentication.",
                """
                {"type":"object","properties":{"timeout_ms":{"type":"integer","minimum":1,"maximum":30000,"default":10000}},"required":[],"additionalProperties":false}
                """,
                (ex,req) -> response(() -> probe(conn, gate, req.arguments()))),
            PtMcpServer.tool(jm,"pt_get_readiness","Observe boot/power and tracked terminal completion without terminal commands, boot skipping or traffic probes.",
                """
                {"type":"object","properties":{"devices":{"type":"array","minItems":1,"maxItems":20,"uniqueItems":true,"items":{"type":"string","minLength":1,"maxLength":256}},"timeout_ms":{"type":"integer","minimum":1,"maximum":30000,"default":10000}},"required":["devices"],"additionalProperties":false}
                """,
                (ex,req) -> response(() -> readiness(conn, gate, req.arguments()))),
            PtMcpServer.tool(jm,"pt_validate_network","Validate boot, tracked terminal idleness, actual DHCP-mode address and forwarding trunk VLANs. Terminal probes require allow_probes=true; no saves or replay.",
                """
                {"type":"object","properties":{"checks":{"type":"array","minItems":1,"maxItems":20,"items":{"oneOf":[{"type":"object","properties":{"kind":{"type":"string","const":"boot"},"device":{"type":"string","minLength":1,"maxLength":256}},"required":["kind","device"],"additionalProperties":false},{"type":"object","properties":{"kind":{"type":"string","const":"terminal_idle"},"device":{"type":"string","minLength":1,"maxLength":256}},"required":["kind","device"],"additionalProperties":false},{"type":"object","properties":{"kind":{"type":"string","const":"dhcp_address"},"device":{"type":"string","minLength":1,"maxLength":256},"iface":{"type":"string","minLength":1,"maxLength":256}},"required":["kind","device","iface"],"additionalProperties":false},{"type":"object","properties":{"kind":{"type":"string","const":"trunk_vlan"},"device":{"type":"string","minLength":1,"maxLength":256},"iface":{"type":"string","minLength":1,"maxLength":256},"vlans":{"type":"array","minItems":1,"maxItems":128,"uniqueItems":true,"items":{"type":"integer","minimum":1,"maximum":4094}}},"required":["kind","device","iface","vlans"],"additionalProperties":false}]}},"allow_probes":{"type":"boolean","default":false},"timeout_ms":{"type":"integer","minimum":1,"maximum":30000,"default":10000}},"required":["checks"],"additionalProperties":false}
                """,
                (ex,req) -> response(() -> validate(conn, gate, req.arguments())))
        );
    }
    private static int timeout(Map<String,Object> args) {
        int value=args.containsKey("timeout_ms")?PresentationPolicy.coordinate(args.get("timeout_ms")):10000;
        if(value<1 || value>30000) throw new IllegalArgumentException("timeout_ms must be 1..30000");
        return value;
    }
    private static void fields(Map<String,Object> args,Set<String> allowed) {
        if(args==null || !allowed.containsAll(args.keySet())) throw new IllegalArgumentException("unexpected argument");
    }
    private static CallToolResult response(Supplier<Map<String,Object>> operation) {
        try {
            var result=operation.get();
            return CallToolResult.builder().addTextContent(result.toString()).structuredContent(result).isError(false).build();
        } catch(IllegalArgumentException invalid) {
            var result=DiagnosticsPolicy.result("fail","invalid_arguments",Map.of("detail",invalid.getMessage(),"dispatched",false));
            return CallToolResult.builder().addTextContent(result.toString()).structuredContent(result).isError(true).build();
        }
    }
    private static Map<String,Object> probe(ConnectionManager conn,DiagnosticExecutor gate,Map<String,Object> args) {
        fields(args,Set.of("timeout_ms"));
        return gate.run(timeout(args),budget -> {
            try {
                return conn.withClient(c -> {
                    budget.requireRemaining();int count=c.network().getDeviceCount();budget.requireRemaining();
                    boolean authenticated=c.isConnected();
                    return DiagnosticsPolicy.result(authenticated?"pass":"unknown",authenticated?"authenticated_live_read":"session_not_confirmed",
                        Map.of("authenticated",authenticated,"observed_device_count",count,"source","authenticated IPC session + Network.getDeviceCount","replayed",false));
                });
            } catch(AuthenticationRejectedException rejected) {
                return DiagnosticsPolicy.result("fail","authentication_rejected",Map.of("authenticated",false,"replayed",false));
            }
        });
    }
    private static Map<String,Object> readiness(ConnectionManager conn,DiagnosticExecutor gate,Map<String,Object> args) {
        fields(args,Set.of("devices","timeout_ms"));
        if(!(args.get("devices") instanceof List<?> devices) || devices.isEmpty() || devices.size()>20)
            throw new IllegalArgumentException("devices must contain 1..20 unique names");
        var checks=new ArrayList<Map<String,Object>>();var seen=new HashSet<String>();
        for(Object v:devices) {
            String name=PresentationPolicy.name(v);if(!seen.add(name)) throw new IllegalArgumentException("duplicate device");
            checks.add(Map.of("kind","boot","device",name));checks.add(Map.of("kind","terminal_idle","device",name));
        }
        return runChecks(conn,gate,checks,false,timeout(args));
    }
    private static Map<String,Object> validate(ConnectionManager conn,DiagnosticExecutor gate,Map<String,Object> args) {
        fields(args,Set.of("checks","allow_probes","timeout_ms"));
        var checks=DiagnosticsPolicy.validateChecks(args.get("checks"));
        Object probes=args.getOrDefault("allow_probes",false);
        if(!(probes instanceof Boolean)) throw new IllegalArgumentException("allow_probes must be boolean");
        return runChecks(conn,gate,checks,(Boolean)probes,timeout(args));
    }
    private static Map<String,Object> runChecks(ConnectionManager conn,DiagnosticExecutor gate,List<Map<String,Object>> checks,boolean probes,int timeout) {
        var progress=new CopyOnWriteArrayList<Map<String,Object>>();
        Map<String,Object> report=gate.run(timeout,budget -> conn.withClient(c ->
            ValidationEngine.evaluate(new DiagnosticsFeatures(c,budget),checks,probes,budget,progress::add)));
        if(report.containsKey("checks")) return report;
        // A native call may outlive the caller deadline. Preserve confirmed observations;
        // never cancel/replay it or submit a second native operation in the background.
        var completed=new ArrayList<Map<String,Object>>(progress);
        for(int i=completed.size();i<checks.size();i++) {
            var item=DiagnosticsPolicy.result("unknown","observation_in_flight_or_unattempted",Map.of("replayed",false));
            item.put("index",i);item.put("check",checks.get(i));completed.add(item);
        }
        var result=new LinkedHashMap<>(report);result.put("checks",completed);
        result.put("status",DiagnosticsPolicy.aggregate(completed));result.put("active_probes_requested",probes);return result;
    }
}
