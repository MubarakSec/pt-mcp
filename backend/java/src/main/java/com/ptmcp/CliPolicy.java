package com.ptmcp;

import java.util.*;
import java.util.regex.Pattern;

/** SDK-independent result policy. Never retries, rolls back or repairs CLI context. */
public final class CliPolicy {
    private CliPolicy() { }
    private static final Pattern FAILURE = Pattern.compile(
        "(?im)^\\s*%\\s*(?:Invalid input detected|Incomplete command|Ambiguous command|"
        + "Unrecognized command|Unknown command|Interface range command failed|"
        + "Command failed on interface|Error(?:[: ]|$)|Access denied|Authorization failed).*$");

    public record Reply(String status, String output) { }
    @FunctionalInterface public interface Runner { Reply run(String command, String mode); }

    public static String classify(String status, String output) {
        if (FAILURE.matcher(output == null ? "" : output).find()) return "cli_failure";
        return "STATUS_OK".equals(status) ? "success" : "sdk_failure";
    }

    public static Map<String,Object> batch(List<String> commands, String mode, boolean keepGoing, Runner runner) {
        if (commands == null || commands.isEmpty() || commands.size() > 100)
            throw new IllegalArgumentException("commands must contain 1..100 single-line commands");
        if (!Set.of("user", "enable", "global").contains(mode))
            throw new IllegalArgumentException("initial_mode must be user, enable or global");
        for (String command : commands) {
            if (command == null || command.isBlank() || command.length() > 4096
                    || command.indexOf('\n') >= 0 || command.indexOf('\r') >= 0 || command.indexOf('\0') >= 0)
                throw new IllegalArgumentException("commands must be nonempty single lines, at most 4096 characters");
        }
        var results = new ArrayList<Map<String,Object>>();
        var completed = new ArrayList<Integer>();
        var failed = new ArrayList<Integer>();
        var unknown = new ArrayList<Integer>();
        var unattempted = new ArrayList<Integer>();
        boolean stopped = false;
        for (int i = 0; i < commands.size(); i++) {
            if (stopped) { unattempted.add(i); continue; }
            var item = new LinkedHashMap<String,Object>();
            item.put("index", i);
            item.put("command", commands.get(i));
            try {
                Reply reply = runner.run(commands.get(i), i == 0 ? mode : "");
                String outcome = classify(reply.status(), reply.output());
                item.put("status", reply.status());
                item.put("output", reply.output() == null ? "" : reply.output());
                item.put("outcome", outcome);
                if (outcome.equals("success")) completed.add(i);
                else { failed.add(i); stopped = !keepGoing; }
            } catch (RuntimeException e) {
                item.put("outcome", "unknown");
                item.put("error", "IPC operation failed; inspect device state before continuing");
                unknown.add(i);
                stopped = true; // continue_on_error never overrides an uncertain outcome
            }
            results.add(item);
        }
        var report = new LinkedHashMap<String,Object>();
        report.put("results", results);
        report.put("completed", completed);
        report.put("failed", failed);
        report.put("unknown", unknown);
        report.put("unattempted", unattempted);
        report.put("outcome", !unknown.isEmpty() ? "unknown" : !failed.isEmpty() ? "partial" : "success");
        report.put("changes_may_have_applied", true);
        report.put("inspection_required", !failed.isEmpty() || !unknown.isEmpty());
        return report;
    }
}
