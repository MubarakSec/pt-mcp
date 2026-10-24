package com.ptmcp;
import java.util.*;
public class TerminalActivityTest {
    public static void main(String[] args) {
        var activity=new TerminalActivity();
        assert activity.snapshot("a").get("status").equals("unknown");
        long token=activity.begin("a","PC0",true,"ipconfig");
        assert activity.snapshot("a").get("status").equals("fail");
        activity.output("a","partial output\n");
        assert activity.result("a",token).get("status").equals("unknown");
        assert activity.result("a",token).get("output").equals("partial output\n");
        try { activity.begin("a","PC0",true,"ipconfig");throw new AssertionError(); } catch(IllegalStateException expected) { }
        activity.prompt("a"); // prompt at command start is not completion readiness
        activity.ended("a","STATUS_OK");
        assert activity.snapshot("a").get("status").equals("fail"); // ended is not a ready prompt
        activity.output("a","late completed output");
        activity.prompt("a");
        assert activity.snapshot("a").get("status").equals("pass");
        assert activity.result("a",token).get("status").equals("pass");
        assert activity.result("a",token).get("output").toString().contains("late completed output");
        long next=activity.begin("a","Renamed PC",false,"show");
        assert activity.result("a",token).get("reason").equals("operation_not_retained");
        activity.uncertain("a",token); // old dispatch cannot corrupt a newer operation
        assert activity.snapshot("a").get("status").equals("fail");
        activity.uncertain("a",next);
        assert activity.snapshot("a").get("status").equals("unknown");
        try { activity.begin("a","PC",false,"show");throw new AssertionError(); } catch(IllegalStateException expected) { }
        activity.ended("a","ERROR_INVALID");
        assert activity.snapshot("a").get("status").equals("pass"); // terminal idle does not mean command succeeded
        assert activity.result("a",next).get("status").equals("fail");
        long truncated=activity.begin("b","PC1",false,"show");
        activity.output("b","x".repeat(40000));activity.ended("b","STATUS_OK");
        assert activity.result("b",truncated).get("status").equals("unknown");
        assert activity.result("b",truncated).get("output").toString().length()==32768;
        activity.disconnect();
        assert activity.snapshot("a").get("status").equals("unknown");
        assert !activity.snapshot("a").toString().contains("Renamed PC"); // IDs scope state, no raw commands persisted
    }
}
