package com.ptmcp;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Synthetic observations, not Packet Tracer verification. */
public final class DiagnosticsPolicyTest {
    static void status(String expected, Map<String,Object> result) {
        if (!expected.equals(result.get("status"))) throw new AssertionError(result);
    }
    static final String IPCONFIG = """
        ipconfig
        FastEthernet0 Connection:(default port)
           IPv4 Address....................: 192.0.2.50
           Subnet Mask.....................: 255.255.255.0
        Bluetooth Connection:
           IPv4 Address....................: 0.0.0.0
        C:\\>
        """;
    static final String TRUNK = """
        Port        Mode         Encapsulation  Status        Native vlan
        Gig0/1      on           802.1q         trunking      1

        Port        Vlans allowed on trunk
        Gig0/1      1,10,20-22

        Port        Vlans allowed and active in management domain
        Gig0/1      1,10,20

        Port        Vlans in spanning tree forwarding state and not pruned
        Gig0/1      1,10
        """;
    public static void main(String[] args) throws Exception {
        status("pass", DiagnosticsPolicy.boot(true, false));
        status("fail", DiagnosticsPolicy.boot(true, true));
        status("fail", DiagnosticsPolicy.boot(false, false));
        status("unknown", DiagnosticsPolicy.boot(true, null));
        status("unknown", DiagnosticsPolicy.address(true, "FastEthernet0", null, false, "STATUS_OK", false));
        status("pass", DiagnosticsPolicy.address(true, "FastEthernet0", IPCONFIG, true, "STATUS_OK", false));
        status("fail", DiagnosticsPolicy.address(false, "FastEthernet0", IPCONFIG, true, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.address(null, "FastEthernet0", IPCONFIG, true, "STATUS_OK", false));
        status("fail", DiagnosticsPolicy.address(true, "Bluetooth", IPCONFIG, true, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.address(true, "Missing", IPCONFIG, true, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.address(true, "FastEthernet0", IPCONFIG, false, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.address(true, "FastEthernet0", IPCONFIG, true, "ERROR_INVALID", false));
        status("unknown", DiagnosticsPolicy.address(true, "FastEthernet0", IPCONFIG, true, "STATUS_OK", true));
        status("unknown", DiagnosticsPolicy.address(true, "FastEthernet0", IPCONFIG+IPCONFIG, true, "STATUS_OK", false));
        status("fail", DiagnosticsPolicy.address(true, "FastEthernet0", IPCONFIG.replace("192.0.2.50","169.254.1.2"), true, "STATUS_OK", false));
        status("pass", DiagnosticsPolicy.trunk("GigabitEthernet0/1", List.of(1,10), TRUNK, true, "STATUS_OK", false));
        status("fail", DiagnosticsPolicy.trunk("Gi0/1", List.of(20), TRUNK, true, "STATUS_OK", false));
        status("fail", DiagnosticsPolicy.trunk("Gi0/1", List.of(30), TRUNK, true, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.trunk("Gi0/1", List.of(10), "", true, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.trunk("Gi0/2", List.of(10), TRUNK, true, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.trunk("Gi0/1", List.of(10), TRUNK, false, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.trunk("Gi0/1", List.of(10), TRUNK, true, "STATUS_OK", true));
        status("unknown", DiagnosticsPolicy.trunk("Gi0/1", List.of(10), TRUNK.replace("1,10,20-22","10,bad"), true, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.trunk("Gi0/1", List.of(10), TRUNK.substring(0, TRUNK.indexOf("Port        Vlans in spanning")), true, "STATUS_OK", false));
        status("unknown", DiagnosticsPolicy.trunk("Gi0/1", List.of(10), "% Invalid input detected", true, "STATUS_OK", false));
        status("pass", DiagnosticsPolicy.trunk("Gi0/1", List.of(21), TRUNK.replace("1,10,20-22","all").replace("1,10,20\n","all\n").replace("1,10\n","all\n"), true, "STATUS_OK", false));

        var gate=new DiagnosticExecutor();var release=new CountDownLatch(1);var calls=new AtomicInteger();
        var timeout=gate.run(30, budget -> { calls.incrementAndGet();
            try { release.await(); } catch (InterruptedException e) { throw new RuntimeException(e); }
            return DiagnosticsPolicy.result("pass","synthetic",Map.of());
        });
        status("unknown",timeout);
        status("unknown",gate.run(30,b -> { calls.incrementAndGet();return Map.of(); }));
        assert calls.get()==1; // no retry or second SDK operation while the timed-out call is in flight
        release.countDown();
        for(int i=0;i<100 && gate.busy();i++) Thread.sleep(5);
        assert !gate.busy();
        status("pass",gate.run(1000,b -> DiagnosticsPolicy.result("pass","synthetic",Map.of())));
        try { gate.run(0,b -> Map.of());throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        try { DiagnosticsPolicy.validateChecks(List.of(Map.of("kind","trunk_vlan","device","SW","iface","Gi0/1","vlans",List.of(4095))));throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        try { DiagnosticsPolicy.validateChecks(List.of(Map.of("kind","boot","device","SW","typo",true)));throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        try { DiagnosticsPolicy.validateChecks(List.of());throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        assert DiagnosticsPolicy.aggregate(List.of(DiagnosticsPolicy.result("pass","a",Map.of()), DiagnosticsPolicy.result("unknown","b",Map.of()))).equals("unknown");
        assert DiagnosticsPolicy.aggregate(List.of(DiagnosticsPolicy.result("fail","a",Map.of()), DiagnosticsPolicy.result("unknown","b",Map.of()))).equals("fail");
    }
}
