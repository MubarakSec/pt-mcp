package com.ptmcp;

import java.util.*;

/** Tracks this connection's terminal dispatches only; never guesses GUI/global idleness. */
public final class TerminalActivity {
    private static final int LIMIT=256;
    private static final class Entry {
        long token;boolean needsPrompt,ended,prompt,uncertain;String status;
        Entry(long token,boolean needsPrompt){this.token=token;this.needsPrompt=needsPrompt;}
        boolean idle(){return ended && (!needsPrompt || prompt);}
    }
    private final Map<String,Entry> entries=new LinkedHashMap<>();
    private long nextToken;
    public synchronized long begin(String id,String device,boolean needsPrompt,String category) {
        Entry previous=entries.get(id);
        if(previous!=null && !previous.idle()) throw new IllegalStateException("Terminal has an unresolved command; inspect before issuing another");
        if(entries.size()>=LIMIT && previous==null) {
            String removable=entries.entrySet().stream().filter(e -> e.getValue().idle()).map(Map.Entry::getKey).findFirst().orElse(null);
            if(removable==null) throw new IllegalStateException("Too many unresolved terminal operations");
            entries.remove(removable);
        }
        Entry entry=new Entry(++nextToken,needsPrompt);entries.put(id,entry);return entry.token;
    }
    public synchronized void ended(String id,String status) {
        Entry e=entries.get(id);if(e!=null){e.ended=true;e.status=status;}
    }
    public synchronized void prompt(String id) {Entry e=entries.get(id);if(e!=null)e.prompt=true;}
    public synchronized void uncertain(String id,long token) {Entry e=entries.get(id);if(e!=null && e.token==token)e.uncertain=true;}
    public synchronized void disconnect() {entries.clear();}
    public synchronized Map<String,Object> snapshot(String id) {
        var e=new LinkedHashMap<String,Object>();e.put("scope","commands_tracked_by_this_backend_session");
        e.put("external_commands_observable",false);
        Entry entry=entries.get(id);
        if(entry==null) return DiagnosticsPolicy.result("unknown","no_terminal_history",e);
        e.put("operation_id",entry.token);e.put("command_ended",entry.ended);
        e.put("prompt_observed",entry.prompt);e.put("sdk_status",entry.status);
        return DiagnosticsPolicy.result(entry.idle()?"pass":entry.uncertain?"unknown":"fail",
            entry.idle()?"tracked_terminal_idle":entry.uncertain?"terminal_outcome_unknown":"awaiting_terminal_completion",e);
    }
}
