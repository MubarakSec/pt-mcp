package com.ptmcp;
import java.util.*;

public final class ValidationEngineTest {
    static class Fake implements ValidationEngine.Source {
        int dispatches;boolean broken,pending,staticMode;
        public Map<String,Object> boot(String d) {return DiagnosticsPolicy.boot(true,false);}
        public Map<String,Object> terminal(String d) {return DiagnosticsPolicy.result(pending?"fail":"unknown",pending?"awaiting_terminal_completion":"no_terminal_history",Map.of());}
        public Boolean dhcpMode(String d,String i) {return !staticMode;}
        public ValidationEngine.Observation command(String device,String command,int timeout) {
            dispatches++;if(broken) throw new IllegalStateException("socket closed");
            return new ValidationEngine.Observation(DiagnosticsPolicyTest.IPCONFIG,"STATUS_OK",true,false);
        }
    }
    public static void main(String[] args) {
        var f=new Fake();
        var checks=DiagnosticsPolicy.validateChecks(List.of(Map.of("kind","boot","device","R"),
            Map.of("kind","dhcp_address","device","PC","iface","FastEthernet0"),
            Map.of("kind","dhcp_address","device","PC","iface","Bluetooth")));
        var result=ValidationEngine.evaluate(f,checks,false,new DiagnosticExecutor.Budget(1000),r -> {});
        assert f.dispatches==0;assert result.get("status").equals("unknown");
        result=ValidationEngine.evaluate(f,checks,true,new DiagnosticExecutor.Budget(1000),r -> {});
        assert f.dispatches==1; // same completed ipconfig observation, not a second dispatch
        assert result.get("status").equals("fail"); // Bluetooth observed at 0.0.0.0
        var progress=new ArrayList<Map<String,Object>>();f.broken=true;f.dispatches=0;
        result=ValidationEngine.evaluate(f,checks,true,new DiagnosticExecutor.Budget(1000),progress::add);
        assert f.dispatches==1;assert progress.get(0).get("status").equals("pass");
        assert progress.get(1).get("status").equals("unknown");
        assert progress.get(2).get("reason").equals("observation_unattempted");
        f.broken=false;f.pending=true;f.dispatches=0;
        ValidationEngine.evaluate(f,checks,true,new DiagnosticExecutor.Budget(1000),r -> {});
        assert f.dispatches==0;
        f.pending=false;f.staticMode=true;
        result=ValidationEngine.evaluate(f,checks,true,new DiagnosticExecutor.Budget(1000),r -> {});
        assert f.dispatches==0;assert result.get("status").equals("fail");
        var budget=new DiagnosticExecutor.Budget(1);
        try {Thread.sleep(5);}catch(InterruptedException e){throw new AssertionError(e);}
        result=ValidationEngine.evaluate(f,checks,true,budget,r -> {});
        assert result.get("status").equals("unknown");assert f.dispatches==0;
    }
}
