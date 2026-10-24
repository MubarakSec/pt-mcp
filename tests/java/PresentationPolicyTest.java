package com.ptmcp;
import java.util.*;
public class PresentationPolicyTest {
    static class Fake implements PresentationPolicy.Canvas {
        Map<String,Map<String,Object>> devices = new LinkedHashMap<>();
        boolean refuseRename, refuseMove;
        int creates;
        Fake() { devices.put("PC0", new LinkedHashMap<>(Map.of("name","PC0","x",0,"y",0))); }
        public Set<String> names() { return devices.keySet(); }
        public Map<String,Object> device(String name) { return devices.get(name); }
        public String create(String t,String m,double x,double y) { creates++; devices.put("PC1",new LinkedHashMap<>(Map.of("name","PC1","x",x,"y",y))); return "PC1"; }
        public void rename(String from,String to) { if (!refuseRename) { var d=devices.remove(from); d.put("name",to); devices.put(to,d); } }
        public boolean move(String n,int x,int y) { if (refuseMove) return false; devices.get(n).put("x",x);devices.get(n).put("y",y);return true; }
    }
    static class NoteFake implements PresentationPolicy.Notes {
        Map<String,Object> note=new LinkedHashMap<>(Map.of("id","note-1","text","old","x",0,"y",0));
        boolean deleted;
        public Set<String> noteIds() { return deleted?Set.of():Set.of("note-1"); }
        public Map<String,Object> readNote(String id) { return note; }
        public String createNote(int x,int y,String text) { return "note-1"; }
        public boolean changeNote(String id,String text) { return true; } // dishonest setter: readback must catch it
        public boolean removeNote(String id) { deleted=true;return true; }
    }
    public static void main(String[] args) {
        var notes=new NoteFake();
        assert PresentationPolicy.addNote(notes,20,30,"العربية").get("outcome").equals("partial");
        assert PresentationPolicy.updateNote(notes,"note-1","new").get("outcome").equals("failed");
        try { PresentationPolicy.deleteNote(notes,"device-id"); throw new AssertionError(); } catch (IllegalArgumentException expected) { }
        assert !notes.deleted;
        assert PresentationPolicy.deleteNote(notes,"note-1").get("removed").equals(true);
        try { PresentationPolicy.noteText("x".repeat(16385));throw new AssertionError(); } catch (IllegalArgumentException expected) { }

        for (Object n : List.of(Double.NaN, Double.POSITIVE_INFINITY, 1.5, 2147483648L, true, "1")) {
            try { PresentationPolicy.coordinate(n); throw new AssertionError(n); } catch (IllegalArgumentException expected) { }
        }
        var f = new Fake();
        assert PresentationPolicy.rename(f,"PC0","PC0").get("outcome").equals("success");
        f.refuseRename=true;
        var created=PresentationPolicy.create(f,"pc","PC-PT",0,0,"Office");
        assert created.get("outcome").equals("partial");
        assert created.get("name").equals("PC1");
        assert f.creates == 1;
        try { PresentationPolicy.rename(f,"PC0","PC1"); throw new AssertionError(); } catch (IllegalArgumentException expected) { }
        f.refuseMove=true;
        assert PresentationPolicy.move(f,"PC0",10,20).get("outcome").equals("failed");
        assert PresentationPolicy.move(f,"PC0",10,20).get("x").equals(0);
        try { PresentationPolicy.apply(f,List.of(Map.of("name","PC0","x",10,"y",20),Map.of("name","missing","x",0,"y",0))); throw new AssertionError(); } catch (IllegalArgumentException expected) { }
        assert f.device("PC0").get("x").equals(0);
        var r=PresentationPolicy.apply(f,List.of(Map.of("name","PC0","x",10,"y",20),Map.of("name","PC1","x",0,"y",0)));
        assert r.get("unattempted").equals(List.of(1));
    }
}
