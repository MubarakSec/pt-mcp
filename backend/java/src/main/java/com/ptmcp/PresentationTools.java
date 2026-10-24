package com.ptmcp;
import io.modelcontextprotocol.json.McpJsonMapper;
import io.modelcontextprotocol.server.McpServerFeatures.SyncToolSpecification;
import java.util.*;
public final class PresentationTools {
    private PresentationTools() { }
    public static List<SyncToolSpecification> tools(McpJsonMapper jm,ConnectionManager conn) {
        return List.of(
            PtMcpServer.tool(jm, "pt_rename_device", "Rename a display name, not IOS hostname; return actual name.",
                """
                {"type":"object","properties":{"name":{"type":"string","minLength":1,"maxLength":256},"new_name":{"type":"string","minLength":1,"maxLength":256}},"required":["name","new_name"],"additionalProperties":false}
                """,
                (ex,req) -> PtMcpServer.mutationResult(conn,c -> {
                    var p=new PresentationFeatures(c);var a=req.arguments();return PresentationPolicy.rename(p, PresentationPolicy.name(a.get("name")), PresentationPolicy.name(a.get("new_name")));
                })),
            PtMcpServer.tool(jm, "pt_move_device", "Move icon origin to signed 32-bit integer coordinates; return readback.",
                """
                {"type":"object","properties":{"name":{"type":"string","minLength":1,"maxLength":256},"x":{"type":"integer","minimum":-2147483648,"maximum":2147483647},"y":{"type":"integer","minimum":-2147483648,"maximum":2147483647}},"required":["name","x","y"],"additionalProperties":false}
                """,
                (ex,req) -> PtMcpServer.mutationResult(conn,c -> {
                    var p=new PresentationFeatures(c);var a=req.arguments();return PresentationPolicy.move(p, PresentationPolicy.name(a.get("name")), PresentationPolicy.coordinate(a.get("x")), PresentationPolicy.coordinate(a.get("y")));
                })),
            PtMcpServer.tool(jm, "pt_get_canvas", "Read live devices/links and meaningful notes by default, with note counts. Set include_empty_notes for all native note objects; link state stays unknown.",
                """
                {"type":"object","properties":{"include_empty_notes":{"type":"boolean","default":false}},"required":[],"additionalProperties":false}
                """,
                (ex,req) -> PtMcpServer.mutationResult(conn,c -> {
                    var p=new PresentationFeatures(c);var a=req.arguments();
                    Object raw=a.getOrDefault("include_empty_notes",false);
                    if(!(raw instanceof Boolean)) throw new IllegalArgumentException("include_empty_notes must be boolean");
                    return p.canvas((Boolean)raw);
                })),
            PtMcpServer.tool(jm, "pt_add_note", "Add a native note at real integer coordinates; ASCII text only until native Unicode serialization is verified; bounded text and readback.",
                """
                {"type":"object","properties":{"text":{"type":"string","maxLength":16384},"x":{"type":"integer","minimum":-2147483648,"maximum":2147483647},"y":{"type":"integer","minimum":-2147483648,"maximum":2147483647}},"required":["text","x","y"],"additionalProperties":false}
                """,
                (ex,req) -> PtMcpServer.mutationResult(conn,c -> {
                    var p=new PresentationFeatures(c);var a=req.arguments();return p.addNote(PresentationPolicy.coordinate(a.get("x")), PresentationPolicy.coordinate(a.get("y")), PresentationPolicy.noteText(a.get("text")));
                })),
            PtMcpServer.tool(jm, "pt_update_note", "Update ASCII text of an existing verified native note ID; reject unsafe Unicode before mutation and return readback.",
                """
                {"type":"object","properties":{"id":{"type":"string"},"text":{"type":"string","maxLength":16384}},"required":["id","text"],"additionalProperties":false}
                """,
                (ex,req) -> PtMcpServer.mutationResult(conn,c -> {
                    var p=new PresentationFeatures(c);var a=req.arguments();return p.updateNote(PresentationPolicy.name(a.get("id")), PresentationPolicy.noteText(a.get("text")));
                })),
            PtMcpServer.tool(jm, "pt_delete_note", "Remove a verified native note ID only; return absence readback.",
                """
                {"type":"object","properties":{"id":{"type":"string"}},"required":["id"],"additionalProperties":false}
                """,
                (ex,req) -> PtMcpServer.mutationResult(conn,c -> {
                    var p=new PresentationFeatures(c);var a=req.arguments();return p.deleteNote(PresentationPolicy.name(a.get("id")));
                })),
            PtMcpServer.tool(jm, "pt_apply_layout", "Preflight then sequentially move 1..500 devices; stop on any failure/unknown. Does not apply annotations or save.",
                """
                {"type":"object","properties":{"moves":{"type":"array","minItems":1,"maxItems":500,"items":{"type":"object","properties":{"name":{"type":"string","minLength":1,"maxLength":256},"x":{"type":"integer","minimum":-2147483648,"maximum":2147483647},"y":{"type":"integer","minimum":-2147483648,"maximum":2147483647}},"required":["name","x","y"],"additionalProperties":false}}},"required":["moves"],"additionalProperties":false}
                """,
                (ex,req) -> PtMcpServer.mutationResult(conn,c -> {
                    var p=new PresentationFeatures(c);var a=req.arguments();return PresentationPolicy.apply(p, moves(a.get("moves")));
                }))
        );
    }
    private static List<Map<String,Object>> moves(Object value) {
        if (!(value instanceof List<?> list) || list.stream().anyMatch(v -> !(v instanceof Map)))
            throw new IllegalArgumentException("moves must be objects");
        var result=new ArrayList<Map<String,Object>>();
        for (Object item:list) {
            Map<?,?> source=(Map<?,?>)item;
            var m=new LinkedHashMap<String,Object>();
            for (var e:source.entrySet()) {
                if (!(e.getKey() instanceof String key)) throw new IllegalArgumentException("invalid key");
                m.put(key,e.getValue());
            }
            result.add(m);
        }
        return result;
    }
}
