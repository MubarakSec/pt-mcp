package com.ptmcp;

import java.util.*;

/** Validation and mutation/readback policy, independent of the proprietary SDK. */
public final class PresentationPolicy {
    private PresentationPolicy() { }
    public interface Canvas {
        Set<String> names();
        Map<String,Object> device(String name);
        String create(String type,String model,double x,double y);
        void rename(String from,String to);
        boolean move(String name,int x,int y);
    }
    public interface Notes {
        Set<String> noteIds();
        Map<String,Object> readNote(String id);
        String createNote(int x,int y,String text);
        boolean changeNote(String id,String text);
        boolean removeNote(String id);
    }
    private static void requireNote(Notes n,String id) {
        name(id);
        if (!n.noteIds().contains(id)) throw new IllegalArgumentException("unknown native note ID");
    }
    public static Map<String,Object> addNote(Notes n,int x,int y,String text) {
        noteText(text);
        String id=n.createNote(x,y,text);
        if (id==null) return Map.of("outcome","unknown","error","No identifier returned; inspect before retrying");
        try {
            requireNote(n,id);
            var r=new LinkedHashMap<>(n.readNote(id));
            r.put("outcome",text.equals(r.get("text")) && ((Number)r.get("x")).doubleValue()==x
                    && ((Number)r.get("y")).doubleValue()==y ? "success":"partial");
            return r;
        } catch (RuntimeException e) { return Map.of("id",id,"outcome","unknown","error","Note created; readback failed"); }
    }
    public static Map<String,Object> updateNote(Notes n,String id,String text) {
        noteText(text);requireNote(n,id);
        boolean accepted=n.changeNote(id,text);
        var r=new LinkedHashMap<>(n.readNote(id));r.put("sdk_accepted",accepted);
        r.put("outcome",text.equals(r.get("text"))?"success":"failed");return r;
    }
    public static Map<String,Object> deleteNote(Notes n,String id) {
        requireNote(n,id);
        boolean accepted=n.removeNote(id);
        boolean absent=!n.noteIds().contains(id);
        return Map.of("id",id,"sdk_accepted",accepted,"removed",absent,"outcome",absent?"success":"failed");
    }
    public static String name(Object value) {
        if (!(value instanceof String s) || s.isBlank() || s.length() > 256
                || s.codePoints().anyMatch(Character::isISOControl))
            throw new IllegalArgumentException("names must be 1..256 characters without control characters");
        return s;
    }
    public static int coordinate(Object value) {
        if (!(value instanceof Number n) || !Double.isFinite(n.doubleValue())
                || n.doubleValue() != Math.rint(n.doubleValue())
                || n.doubleValue() < Integer.MIN_VALUE || n.doubleValue() > Integer.MAX_VALUE)
            throw new IllegalArgumentException("coordinates must be signed 32-bit integers (icon origin)");
        return n.intValue();
    }
    public static String noteText(Object value) {
        if (!(value instanceof String s) || s.length() > 16384 || s.indexOf('\0') >= 0)
            throw new IllegalArgumentException("note text must be at most 16384 characters, without NUL");
        return s;
    }
    static void require(Canvas c,String n) {
        name(n);
        if (!c.names().contains(n)) throw new IllegalArgumentException("unknown device: " + n);
    }
    public static Map<String,Object> rename(Canvas c,String from,String to) {
        require(c,from); name(to);
        if (!from.equals(to) && c.names().contains(to)) throw new IllegalArgumentException("duplicate name: " + to);
        if (!from.equals(to)) c.rename(from,to);
        // Fetch by old and new name; a setter return is not evidence of success.
        var names=c.names();
        String actual=names.contains(to) ? to : names.contains(from) ? from : null;
        var r=new LinkedHashMap<String,Object>();
        r.put("requested_name",to); r.put("name",actual);
        r.put("outcome",to.equals(actual) ? "success" : actual == null ? "unknown" : "failed");
        return r;
    }
    public static Map<String,Object> create(Canvas c,String type,String model,double x,double y,String requested) {
        name(type); name(model);
        // Keep legacy addDevice's finite fractional coordinates compatible.
        if (!Double.isFinite(x) || !Double.isFinite(y) || x < Integer.MIN_VALUE || x > Integer.MAX_VALUE
                || y < Integer.MIN_VALUE || y > Integer.MAX_VALUE)
            throw new IllegalArgumentException("add coordinates must be finite and within signed 32-bit range");
        if (requested != null && c.names().contains(name(requested))) throw new IllegalArgumentException("duplicate name: " + requested);
        String created=c.create(type,model,x,y);
        var result=new LinkedHashMap<String,Object>();
        result.put("created_name",created); result.put("name",created); result.put("outcome","success");
        if (requested != null) {
            try {
                result.putAll(rename(c,created,requested));
                if (!"success".equals(result.get("outcome"))) result.put("outcome","partial");
            } catch (RuntimeException e) {
                result.put("outcome","unknown");
                result.put("name",null);
                result.put("error","Device was created; naming/readback failed. Inspect before retrying.");
            }
        }
        if ("success".equals(result.get("outcome"))) {
            try { result.putAll(c.device((String)result.get("name"))); }
            catch (RuntimeException e) { result.put("outcome","unknown");result.put("error","Created; device readback failed"); }
        }
        return result;
    }
    public static Map<String,Object> move(Canvas c,String n,int x,int y) {
        require(c,n);
        boolean accepted=c.move(n,x,y);
        var r=new LinkedHashMap<>(c.device(n));
        boolean readback=((Number)r.get("x")).doubleValue()==x && ((Number)r.get("y")).doubleValue()==y;
        r.put("sdk_accepted",accepted); r.put("outcome",readback ? "success" : "failed");
        return r;
    }
    public static Map<String,Object> apply(Canvas c,List<Map<String,Object>> moves) {
        if (moves.isEmpty() || moves.size()>500) throw new IllegalArgumentException("moves must contain 1..500 items");
        var seen=new HashSet<String>();
        for (var m:moves) {
            String n=name(m.get("name")); require(c,n);
            if (!seen.add(n)) throw new IllegalArgumentException("duplicate move: " + n);
            coordinate(m.get("x")); coordinate(m.get("y"));
        }
        var items=new ArrayList<Map<String,Object>>();
        var completed=new ArrayList<Integer>(); var failed=new ArrayList<Integer>();
        var unknown=new ArrayList<Integer>(); var unattempted=new ArrayList<Integer>();
        boolean stopped=false;
        for (int i=0;i<moves.size();i++) {
            if (stopped) { unattempted.add(i); continue; }
            var m=moves.get(i); Map<String,Object> r;
            try {
                r=move(c,(String)m.get("name"),coordinate(m.get("x")),coordinate(m.get("y")));
                if ("success".equals(r.get("outcome"))) completed.add(i);
                else { failed.add(i); stopped=true; }
            } catch (RuntimeException e) {
                r=new LinkedHashMap<>(Map.of("name",m.get("name"),"outcome","unknown"));
                unknown.add(i); stopped=true;
            }
            r.put("index",i); items.add(r);
        }
        return Map.of("results",items,"completed",completed,"failed",failed,"unknown",unknown,"unattempted",unattempted,
                "outcome",!unknown.isEmpty()?"unknown":!failed.isEmpty()?"partial":"success");
    }
}
