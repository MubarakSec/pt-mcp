package com.ptmcp;

import com.cisco.pt.UUID;
import com.cisco.pt.ipc.IPCError;
import com.cisco.pt.ipc.sim.Device;
import com.cisco.pt.ipc.ui.LogicalWorkspace;
import java.util.*;
import java.util.function.Supplier;

/** The only presentation adapter: calls the existing authenticated Java IPC session. */
public final class PresentationFeatures implements PresentationPolicy.Canvas, PresentationPolicy.Notes {
    private final PtIpcClient client;
    public PresentationFeatures(PtIpcClient client) { this.client=client; }
    // Cisco IPCError extends Error. Convert just this SDK error so policy can report unknown outcomes.
    private static <T> T ipc(Supplier<T> operation) {
        try { return operation.get(); } catch (IPCError | RuntimeException e) { throw new IllegalStateException("IPC operation failed",e); }
    }
    public Set<String> names() {
        return ipc(() -> { var names=new LinkedHashSet<String>();
            for (var d:client.getTopology().devices) names.add(d.name);
            return names;
        });
    }
    private Device get(String name) {
        Device d=client.network().getDevice(name);
        if (d==null) throw new IllegalArgumentException("unknown device: " + name);
        return d;
    }
    public Map<String,Object> device(String name) {
        return ipc(() -> { var d=get(name); return new LinkedHashMap<>(Map.of(
            "name",d.getName(),"type",d.getType().name(),"model",d.getModel(),
            "x",d.getXCoordinate(),"y",d.getYCoordinate())); });
    }
    public String create(String type,String model,double x,double y) {
        PtIpcClient.parseDeviceType(type); // local validation before entering the mutating SDK call
        return ipc(() -> client.addDevice(type,model,x,y));
    }
    public void rename(String from,String to) { ipc(() -> { get(from).setName(to); return null; }); }
    public boolean move(String name,int x,int y) { return ipc(() -> get(name).moveToLocation(x,y)); }
    private LogicalWorkspace workspace() { return client.logicalWorkspace(); }
    private UUID noteId(String id) {
        for (UUID nativeId:workspace().getCanvasNoteIds())
            if (nativeId.getDecoratedHexString().equals(id)) return nativeId;
        throw new IllegalArgumentException("unknown native note ID");
    }
    private Map<String,Object> note(UUID id) {
        return new LinkedHashMap<>(Map.of("id",id.getDecoratedHexString(),"text",workspace().getCanvasNoteText(id),
            "x",workspace().getCanvasItemRealX(id),"y",workspace().getCanvasItemRealY(id)));
    }
    public Map<String,Object> canvas() {
        return ipc(() -> {
            var devices=new ArrayList<Map<String,Object>>(); for (String n:names()) devices.add(device(n));
            var links=new ArrayList<Map<String,Object>>();
            for (var l:client.getLinks()) {
                var m=new LinkedHashMap<String,Object>();
                m.put("dev_a",l.devA);m.put("if_a",l.ifA);m.put("dev_b",l.devB);m.put("if_b",l.ifB);
                m.put("cable_type",l.cableType);m.put("state","unknown");links.add(m);
            }
            var notes=new ArrayList<Map<String,Object>>(); for (UUID id:workspace().getCanvasNoteIds()) notes.add(note(id));
            return Map.of("devices",devices,"links",links,"notes",notes,"coordinate_contract","icon origin; native note real position");
        });
    }
    public Set<String> noteIds() {
        return ipc(() -> { var ids=new LinkedHashSet<String>();
            for (UUID id:workspace().getCanvasNoteIds()) ids.add(id.getDecoratedHexString());return ids; });
    }
    public Map<String,Object> readNote(String id) { return ipc(() -> note(noteId(id))); }
    public String createNote(int x,int y,String text) {
        return ipc(() -> { UUID id=workspace().addNote(x,y,workspace().getIncNoteZOrder(),text);
            return id==null ? null : id.getDecoratedHexString(); });
    }
    public boolean changeNote(String id,String text) { return ipc(() -> workspace().changeNoteText(noteId(id),text)); }
    public boolean removeNote(String id) { return ipc(() -> workspace().removeCanvasItem(noteId(id))); }
    public Map<String,Object> addNote(int x,int y,String text) { return PresentationPolicy.addNote(this,x,y,text); }
    public Map<String,Object> updateNote(String id,String text) { return PresentationPolicy.updateNote(this,id,text); }
    public Map<String,Object> deleteNote(String id) { return PresentationPolicy.deleteNote(this,id); }
}
