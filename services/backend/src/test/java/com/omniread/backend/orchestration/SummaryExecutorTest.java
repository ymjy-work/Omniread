package com.omniread.backend.orchestration;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 会话级锁：同一会话同一时刻只有一个摘要任务。
 *
 * <p>锁错了的症状不响：两个任务拿同一份旧摘要各算一遍，后写的覆盖先写的，
 * `summary_upto` 还可能推进到不同位置——摘要里同一件事出现两遍或者少一段，
 * 两边都不报错。而**锁不放**的症状同样不响，只是这个会话从此再也不摘要。
 */
class SummaryExecutorTest {

    /**
     * 手动执行器：任务先攒着，由测试决定什么时候跑。
     *
     * <p>用一个「立刻就跑」的执行器测不到锁——任务在 submit 返回之前就跑完了，锁早放掉了。
     */
    private static final class Manual implements Executor {

        private final Deque<Runnable> queued = new ArrayDeque<>();

        @Override
        public void execute(Runnable command) {
            queued.add(command);
        }

        int runAll() {
            int count = queued.size();
            while (!queued.isEmpty()) {
                queued.poll().run();
            }
            return count;
        }
    }

    @Test
    @DisplayName("同一会话在跑（或已排队）时，第二次提交被丢弃")
    void sameSessionIsSingleFlight() {
        Manual manual = new Manual();
        SummaryExecutor executor = new SummaryExecutor(manual);
        AtomicInteger runs = new AtomicInteger();

        assertThat(executor.submit("s-1", runs::incrementAndGet)).isTrue();
        assertThat(executor.submit("s-1", runs::incrementAndGet))
                .as("已有任务 → 丢弃；踢掉的是这一次，不是正在跑的那一次")
                .isFalse();

        assertThat(manual.runAll()).isEqualTo(1);
        assertThat(runs).hasValue(1);
        assertThat(executor.submit("s-1", runs::incrementAndGet))
                .as("跑完就放开——不放的话这个会话再也触发不了摘要")
                .isTrue();
    }

    @Test
    @DisplayName("锁在任务**运行期间**也持有：跑到一半再提交同一个会话，照样被丢弃")
    void lockIsHeldWhileTheTaskIsRunning() {
        Manual manual = new Manual();
        SummaryExecutor executor = new SummaryExecutor(manual);
        AtomicBoolean acceptedWhileRunning = new AtomicBoolean(true);

        assertThat(executor.submit("s-1", () -> acceptedWhileRunning.set(executor.submit("s-1", () -> { }))))
                .isTrue();
        manual.runAll();

        assertThat(acceptedWhileRunning)
                .as("释放点若早于 task.run() 结束，同一会话就会有两个摘要任务并行——"
                        + "拿同一份旧摘要各算一遍，后写的覆盖先写的")
                .isFalse();
    }

    @Test
    @DisplayName("不同会话互不阻塞")
    void differentSessionsRunIndependently() {
        Manual manual = new Manual();
        SummaryExecutor executor = new SummaryExecutor(manual);
        AtomicInteger runs = new AtomicInteger();

        assertThat(executor.submit("s-1", runs::incrementAndGet)).isTrue();
        assertThat(executor.submit("s-2", runs::incrementAndGet)).isTrue();

        assertThat(manual.runAll()).isEqualTo(2);
        assertThat(runs).hasValue(2);
    }

    @Test
    @DisplayName("任务抛异常也放锁，且异常不往外冒")
    void failingTaskReleasesTheLock() {
        SummaryExecutor executor = new SummaryExecutor(Runnable::run);

        assertThat(executor.submit("s-1", () -> {
            throw new IllegalStateException("桩：摘要炸了");
        })).isTrue();

        assertThat(executor.submit("s-1", () -> { }))
                .as("异常不能让这个会话永远触发不了摘要")
                .isTrue();
    }

    @Test
    @DisplayName("队列满被拒时也要放锁")
    void rejectedTaskReleasesTheLock() {
        AtomicBoolean rejectNext = new AtomicBoolean(true);
        Executor flaky = task -> {
            if (rejectNext.getAndSet(false)) {
                throw new RejectedExecutionException("桩：队列满了");
            }
            task.run();
        };
        SummaryExecutor executor = new SummaryExecutor(flaky);

        assertThat(executor.submit("s-1", () -> { })).isFalse();
        assertThat(executor.submit("s-1", () -> { }))
                .as("被拒时如果不放锁，这个会话就再也触发不了摘要了")
                .isTrue();
    }
}
