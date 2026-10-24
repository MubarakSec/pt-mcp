package com.ptmcp;
import java.util.*;
public class TerminalActivityTest {
    public static void main(String[] args) {
        var activity=new TerminalActivity();
        assert activity.snapshot("a").get("status").equals("unknown");
        long token=activity.begin("a","PC0",true,"ipconfig");
        assert activity.snapshot("a").get("status").equals("fail");
        try { activity.begin("a","PC0",true,"ipconfig");throw new AssertionError(); } catch(IllegalStateException expected) { }
        activity.ended("a","STATUS_OK");
        assert activity.snapshot("a").get("status").equals("fail"); // ended is not a ready prompt
        activity.prompt("a");
        assert activity.snapshot("a").get("status").equals("pass");
        long next=activity.begin("a","Renamed PC",false,"show");
        activity.uncertain("a",token); // old dispatch cannot corrupt a newer operation
        assert activity.snapshot("a").get("status").equals("fail");
        activity.uncertain("a",next);
        assert activity.snapshot("a").get("status").equals("unknown");
        try { activity.begin("a","PC",false,"show");throw new AssertionError(); } catch(IllegalStateException expected) { }
        activity.ended("a","ERROR_INVALID");
        assert activity.snapshot("a").get("status").equals("pass"); // terminal idle does not mean command succeeded
        activity.disconnect();
        assert activity.snapshot("a").get("status").equals("unknown");
        assert !activity.snapshot("a").toString().contains("Renamed PC"); // IDs scope state, no raw commands persisted
    }
}
