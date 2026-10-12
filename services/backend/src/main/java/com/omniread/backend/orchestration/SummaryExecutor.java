package com.omniread.backend.orchestration;

import jakarta.annotation.PreDestroy;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 摘要任务的执行器 + **会话级锁**（`docs/m1/多轮会话落地方案.md` §三）。
 *
 * <p>「同一会话同一时刻只允许一个摘要任务」落在 {@link #submit} 上：这个会话已经在跑或
 * 已排队时，本次提交直接丢弃。丢弃是安全的——触发与否由会话状态决定，这一轮不压，
 * 下一轮状态仍然满足、还会再触发一次；而两个任务拿同一份旧摘要各算一遍，后写的覆盖先写的，
 * `summary_upto` 还可能推进到不同位置。
 *
 * <p>锁在进程内就够：会话数据在本机 SQLite，服务是单实例（方案 §一）。**多实例部署时这把锁
 * 会退化成「每个实例各一个」**——那时要换成库上的状态位或抢占式更新，不是现在。
 *
 * <p>线程是守护线程，关闭时直接 {@code shutdownNow}：摘要是后台动作，**没有理由让它拖着
 * JVM 不退**（同一个坑在账户命令行工具上踩过一次），被中断也不会留下不一致——失败不推进
 * `summary_upto`，下一轮重来。
 *
 * <p>队列是有界的，满了就拒绝并**记一条 WARN**：拒绝这件事本身无害（状态仍在、下轮还会触发），
 * 但静默丢弃会让人以为摘要一直在正常工作。
 */
@Component
public class SummaryExecutor {

    private static final Logger log = LoggerFactory.getLogger(SummaryExecutor.class);

    /**
     * 池子很小：摘要是每会话每积累一段才跑一次的偶发动作，而它一次要占着一次模型往返。
     * 大池子只会让同一时刻打出去的模型调用更多，不会让摘要更快到。
     */
    private static final int THREADS = 2;

    private static final int QUEUE_CAPACITY = 256;

    private final Executor pool;

    /** 只有自己建的池才由自己关；注入进来的执行器（测试）归注入方管。 */
    private final ExecutorService owned;

    /** 会话级锁：在跑的会话 id。`add` 返回 false 即「已经在跑」。 */
    private final Set<String> inFlight = ConcurrentHashMap.newKeySet();

    public SummaryExecutor() {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                THREADS,
                THREADS,
                0L,
                TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>(QUEUE_CAPACITY),
                SummaryExecutor::newThread,
                // 拒绝由 submit 兜住：它要顺手把会话锁放掉，否则那个会话再也触发不了。
                new ThreadPoolExecutor.AbortPolicy());
        this.owned = executor;
        this.pool = executor;
    }

    /**
     * 换一个执行器（测试用）。
     *
     * <p>异步的断言只能靠 sleep 或轮询，而两者都会变成偶发红的用例。把「换个执行器」做成
     * 构造器参数，测试就能传一个在调用线程上直接跑的，把这一段变回确定性的顺序执行。
     */
    public SummaryExecutor(Executor pool) {
        this.owned = null;
        this.pool = pool;
    }

    private static Thread newThread(Runnable task) {
        Thread thread = new Thread(task, "omniread-summary");
        thread.setDaemon(true);
        return thread;
    }

    /**
     * 提交一个摘要任务。返回 false 表示**这次没跑**（同一会话已有任务，或队列满）。
     *
     * <p>任务抛出的异常在这里收口：它是后台跑的，抛出去只会打到 stderr 上，
     * 与日志里的其它行对不上。会话锁在 `finally` 里放——不放的话这个会话永远触发不了摘要，
     * 而症状是「摘要只发生过一次」。
     */
    public boolean submit(String sessionId, Runnable task) {
        if (!inFlight.add(sessionId)) {
            log.debug("同一会话已有摘要在跑，本次丢弃：session={}", sessionId);
            return false;
        }
        try {
            pool.execute(() -> {
                try {
                    task.run();
                } catch (RuntimeException e) {
                    log.warn("摘要任务异常：session={} cause={}", sessionId, e.toString());
                } finally {
                    inFlight.remove(sessionId);
                }
            });
            return true;
        } catch (RejectedExecutionException e) {
            inFlight.remove(sessionId);
            log.warn("摘要队列已满，本次丢弃（下轮仍会触发）：session={}", sessionId);
            return false;
        }
    }

    @PreDestroy
    void shutdown() {
        if (owned != null) {
            owned.shutdownNow();
        }
    }
}
