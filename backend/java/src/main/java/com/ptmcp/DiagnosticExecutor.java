package com.ptmcp;

import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Function;

/** One in-flight diagnostic, bounded caller wait, no cancellation/replay of native calls. */
public final class DiagnosticExecutor {
    private final AtomicBoolean busy=new AtomicBoolean();
    public static final class Budget {
        private final long deadline;
        Budget(int timeoutMs) {deadline=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(timeoutMs);}
        public int remainingMs() {
            return (int)Math.max(0,TimeUnit.NANOSECONDS.toMillis(deadline-System.nanoTime()));
        }
        public void requireRemaining() {if(remainingMs()<=0) throw new DeadlineExceeded();}
    }
    public static final class DeadlineExceeded extends RuntimeException { }
    public boolean busy() {return busy.get();}
    public Map<String,Object> run(int timeoutMs,Function<Budget,Map<String,Object>> operation) {
        if(timeoutMs<1 || timeoutMs>30000) throw new IllegalArgumentException("timeout_ms must be 1..30000");
        if(!busy.compareAndSet(false,true)) return DiagnosticsPolicy.result("unknown","diagnostic_still_in_flight",Map.of("in_flight",true));
        var budget=new Budget(timeoutMs);
        var task=new FutureTask<Map<String,Object>>(() -> {
            try {budget.requireRemaining();return operation.apply(budget);} finally {busy.set(false);}
        });
        Thread thread=new Thread(task,"pt-mcp-diagnostic");thread.setDaemon(true);thread.start();
        try {return task.get(Math.max(1,budget.remainingMs()),TimeUnit.MILLISECONDS);}
        catch(TimeoutException e) {
            return DiagnosticsPolicy.result("unknown","deadline_exceeded",Map.of("timeout_ms",timeoutMs,"in_flight",busy.get(),"replayed",false));
        } catch(InterruptedException e) {
            Thread.currentThread().interrupt();return DiagnosticsPolicy.result("unknown","interrupted",Map.of("replayed",false));
        } catch(ExecutionException e) {
            return DiagnosticsPolicy.result("unknown","ipc_observation_failed",Map.of("replayed",false));
        }
    }
}
