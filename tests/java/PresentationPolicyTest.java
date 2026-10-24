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
        assert PresentationPolicy.name("😀".repeat(256)).codePointCount(0,512)==256;
        assert PresentationPolicy.noteText("safe ASCII\tline\nnext\r").contains("next");
        for(String unsafe:List.of("العربية","café","\u2014","😀","bad\u0001", "bad\u007f")) {
            var guarded=new NoteFake() {
                public String createNote(int x,int y,String text) {throw new AssertionError("Unsafe note reached SDK adapter");}
                public boolean changeNote(String id,String text) {throw new AssertionError("Unsafe note update reached SDK adapter");}
            };
            try {PresentationPolicy.addNote(guarded,0,0,unsafe);throw new AssertionError("Unsafe add accepted");}
            catch(IllegalArgumentException expected) { }
            try {PresentationPolicy.updateNote(guarded,"note-1",unsafe);throw new AssertionError("Unsafe update accepted");}
            catch(IllegalArgumentException expected) { }
        }
        var raced=new Fake() {
            public void rename(String from,String to) { devices.put(to,new LinkedHashMap<>(Map.of("name",to,"x",0,"y",0))); }
        };
        assert PresentationPolicy.rename(raced,"PC0","Office").get("outcome").equals("unknown");
        var uncertain=new Fake() {
            public void rename(String from,String to) { super.rename(from,to);throw new IllegalStateException("reply lost"); }
        };
        var uncertainResult=PresentationPolicy.create(uncertain,"pc","PC-PT",0,0,"Office");
        assert uncertainResult.get("outcome").equals("unknown");
        assert uncertainResult.get("name")==null;
        assert uncertain.creates==1;
        var unreadable=new NoteFake() {
            public Map<String,Object> readNote(String id) { throw new IllegalStateException("lost readback"); }
        };
        assert PresentationPolicy.addNote(unreadable,0,0,"hello").get("outcome").equals("unknown");
        var nativeNotes=new ArrayList<Map<String,Object>>();
        for(int i=0;i<122;i++) nativeNotes.add(Map.of("id","note-"+i,"text",i<16?"label "+i:" \n\t"));
        var compact=PresentationPolicy.canvasNotes(nativeNotes,false);
        assert ((List<?>)compact.get("notes")).size()==16;
        assert ((Map<?,?>)compact.get("note_counts")).get("total").equals(122);
        assert ((Map<?,?>)compact.get("note_counts")).get("omitted_empty").equals(106);
        assert ((List<?>)PresentationPolicy.canvasNotes(nativeNotes,true).get("notes")).size()==122;
        assert nativeNotes.size()==122;
        var notes=new NoteFake();
        assert PresentationPolicy.addNote(notes,20,30,"new text").get("outcome").equals("partial");
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
