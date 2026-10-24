package com.ptmcp;
import java.util.*;
public class CliPolicyTest {
    public static void main(String[] args) {
        assert CliPolicy.classify("STATUS_OK", "% Interface range command failed on FastEthernet0/2").equals("cli_failure");
        assert CliPolicy.classify("STATUS_OK", "% Command failed on interface FastEthernet0/2. Aborting").equals("cli_failure");
        assert CliPolicy.classify("STATUS_OK", "0 failed, 100% success\n%LINK-5-CHANGED: up").equals("success");
        assert CliPolicy.classify("ERROR_INVALID", "").equals("sdk_failure");
        var calls = new ArrayList<String>();
        var result = CliPolicy.batch(List.of("interface range fa0/1-4", "shutdown"), "global", false, (cmd, mode) -> {
            calls.add(cmd + ":" + mode);
            return new CliPolicy.Reply("STATUS_OK", "% Interface range command failed");
        });
        assert calls.size() == 1;
        assert result.get("failed").equals(List.of(0));
        assert result.get("unattempted").equals(List.of(1));
        calls.clear();
        result = CliPolicy.batch(List.of("hostname x", "end", "show run"), "global", true, (cmd, mode) -> {
            calls.add(cmd);
            if (calls.size() == 2) throw new IllegalStateException("socket closed");
            return new CliPolicy.Reply("STATUS_OK", "");
        });
        assert calls.size() == 2;
        assert result.get("completed").equals(List.of(0));
        assert result.get("unknown").equals(List.of(1));
        assert result.get("unattempted").equals(List.of(2));
        try { CliPolicy.batch(List.of("ok", "bad\ncmd"), "global", false, (c,m) -> {throw new AssertionError();}); throw new AssertionError(); }
        catch (IllegalArgumentException expected) { }
    }
}
