package com.ptmcp;

import com.cisco.pt.ipc.events.TerminalLineEvent;
import com.cisco.pt.ipc.events.TerminalLineEventListener;
import com.cisco.pt.ipc.events.TerminalLineEventRegistry;
import com.cisco.pt.ipc.sim.TerminalLine;
import com.cisco.pt.ptmp.PacketTracerSession;
import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;

/** One session listener survives request timeouts, so late completions are observed. */
final class TerminalMonitor implements AutoCloseable {
    private final TerminalActivity activity;
    private final TerminalLineEventRegistry registry;
    private final ConcurrentHashMap<String,String> prompts=new ConcurrentHashMap<>();
    private final TerminalLineEventListener listener=this::event;
    TerminalMonitor(PacketTracerSession session,TerminalActivity activity) {
        this.activity=activity;this.registry=session.getEventManager().getTerminalLineEvents();
        try {registry.addListener(listener);} catch(IOException e) {throw new IllegalStateException("Terminal event subscription failed",e);}
    }
    long begin(String uuid,String device,boolean needsPrompt,String prompt) {
        long token=activity.begin(uuid,device,needsPrompt,"terminal");
        prompts.put(uuid,prompt==null?"":prompt);return token;
    }
    private void event(TerminalLineEvent event) {
        if(event.objectUUID==null) return;
        String id=event.objectUUID.toString();
        if(!prompts.containsKey(id)) return;
        if(event instanceof TerminalLineEvent.CommandEnded e) {
            activity.ended(id,e.status==null?null:e.status.name());
        } else if(event instanceof TerminalLineEvent.PromptChanged e) {
            if(e.newPrompt!=null && !e.newPrompt.isBlank()) activity.prompt(id);
        } else if(event instanceof TerminalLineEvent.OutputWritten e) {
            activity.output(id,e.newOutput);
            String prompt=prompts.get(id);
            if(prompt!=null && !prompt.isBlank() && e.newOutput!=null && e.newOutput.trim().endsWith(prompt.trim())) activity.prompt(id);
        }
        if("pass".equals(activity.snapshot(id).get("status"))) prompts.remove(id);
    }
    void completed(String id,String status,String output) {activity.replaceOutput(id,output);activity.ended(id,status);prompts.remove(id);}
    void reset() {prompts.clear();activity.disconnect();}
    @Override public void close() {
        try {registry.removeListener(listener);} catch(IOException | RuntimeException ignored) { }
        reset();
    }
}
