package com.omniread.backend.orchestration;

import com.omniread.backend.contract.model.HistoryMessage;
import com.omniread.backend.contract.model.SummarizeRequest;
import com.omniread.backend.contract.model.SummarizeResponse;
import com.omniread.backend.error.RagException;
import com.omniread.backend.gateway.RagGatewayClient;
import com.omniread.backend.session.ChatMessageMapper;
import com.omniread.backend.session.ChatSession;
import com.omniread.backend.session.ChatSessionMapper;
import com.omniread.backend.session.ContextBudget;
import com.omniread.backend.session.SummaryPlanner;
import com.omniread.backend.web.RequestIds;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 会话摘要：**阈值触发、后台执行、失败不推进**。
 *
 * <p>一次问答的收尾处调用 {@link #maybeSummarize}。它只做判定与投递，压缩本身在
 * {@link SummaryExecutor} 的线程上跑——摘要要等多一次模型往返，不能挂在用户等待的那条链上。
 *
 * <p>三条状态约定：
 *
 * <ul>
 *   <li><b>失败什么都不动</b>：`summary` 与 `summary_upto` 是同一个 UPDATE 写的（见
 *       {@code ChatSessionMapper.updateSummary}），调用失败时连 UPDATE 都不发，
 *       于是下次还能重来，也不会压重。
 *   <li><b>判定与执行各读一次库</b>：投递时读一次是为了不把无用的任务塞进队列，执行时再读
 *       一次是因为排队期间会话可能又长了几轮、或者一个更早的任务已经把这一段压掉了。
 *       第二次读到的东西才是要压的东西。
 *   <li><b>触发路径绝不抛异常</b>：它跑在用户那一轮的尾巴上，回答这时已经落库了。
 *       在这里抛出去，用户会看到一个失败的响应，然后重试——而那一轮其实已经成功，
 *       重试就写重了。
 * </ul>
 */
@Component
public class SessionSummarizer {

    private static final Logger log = LoggerFactory.getLogger(SessionSummarizer.class);

    private final ChatSessionMapper sessionMapper;
    private final ChatMessageMapper messageMapper;
    private final RagGatewayClient gateway;
    private final ContextBudget budget;
    private final SummaryExecutor executor;

    public SessionSummarizer(
            ChatSessionMapper sessionMapper,
            ChatMessageMapper messageMapper,
            RagGatewayClient gateway,
            ContextBudget budget,
            SummaryExecutor executor) {
        this.sessionMapper = sessionMapper;
        this.messageMapper = messageMapper;
        this.gateway = gateway;
        this.budget = budget;
        this.executor = executor;
    }

    /**
     * 一轮回答落库之后调用：该压就投一个后台任务，不该压就什么都不做。
     *
     * <p>**它不抛异常**，理由见类注释。
     */
    public void maybeSummarize(String sessionId) {
        try {
            Optional<Ready> ready = ready(sessionId);
            if (ready.isEmpty()) {
                log.debug("暂不摘要：session={}（待压缩区间未超阈值，或最近几轮之外没有内容）", sessionId);
                return;
            }
            Ready pending = ready.get();
            if (executor.submit(sessionId, () -> summarize(sessionId))) {
                log.info(
                        "摘要触发：session={} 待压 {} 条 / {} token，将覆盖到消息 {}",
                        sessionId,
                        pending.plan().messages().size(),
                        pending.plan().tokens(),
                        pending.plan().upto());
            }
        } catch (RuntimeException e) {
            log.warn("摘要触发失败（本轮不受影响）：session={} cause={}", sessionId, e.toString());
        }
    }

    /**
     * 后台任务体。包内可见，便于不走线程池直接测。
     *
     * <p>区间在这里**重新算一次**：从投递到执行之间，会话可能又长了、也可能已经被更早的任务
     * 压过一遍。按投递时算好的区间去压，会把已经进过摘要的那几条再压一次——症状是摘要里
     * 同一件事出现两遍，而它不会让任何东西报错。
     */
    void summarize(String sessionId) {
        Optional<Ready> pending = ready(sessionId);
        if (pending.isEmpty()) {
            log.debug("摘要任务无事可做（排队期间状态已变）：session={}", sessionId);
            return;
        }
        Ready ready = pending.get();
        ChatSession session = ready.session();
        SummaryPlanner.Plan plan = ready.plan();

        List<HistoryMessage> payload = UpstreamHistory.of(plan.messages());
        if (payload.isEmpty()) {
            // 要压的那一段全是不该出门的内容（空正文，见 UpstreamHistory）。契约的 messages 有
            // `minItems: 1`，发出去就是一个 400，而 summary_upto 照样推不动——那笔调用没有意义。
            log.debug("待压缩的那一段没有可发送的内容：session={}", sessionId);
            return;
        }

        String requestId = RequestIds.next();
        long startedAt = System.nanoTime();
        try {
            SummarizeResponse summary = gateway.summarize(
                    new SummarizeRequest(payload).previousSummary(session.getSummary()),
                    requestId);
            int rows = sessionMapper.updateSummary(sessionId, summary.getSummary(), plan.upto(),
                    summary.getPromptVersion());
            long millis = (System.nanoTime() - startedAt) / 1_000_000;
            if (rows == 0) {
                // 排队期间会话被删了。白跑一次模型调用，库上没有任何变化——这不是错误。
                log.info("摘要结果无处可写（会话已删除）：session={} request_id={}", sessionId, requestId);
                return;
            }
            log.info(
                    "摘要完成：session={} 压了 {} 条 / {} token，覆盖到消息 {}，prompt_version={}，用时 {}ms，request_id={}",
                    sessionId,
                    plan.messages().size(),
                    plan.tokens(),
                    plan.upto(),
                    summary.getPromptVersion(),
                    millis,
                    requestId);
        } catch (RagException e) {
            log.warn(
                    "摘要失败，summary_upto 不推进（下轮可重试）：session={} code={} message={} request_id={}",
                    sessionId,
                    e.code(),
                    e.getMessage(),
                    requestId);
        } catch (RuntimeException e) {
            // 兜底：库出错或契约模型反序列化失败。同样什么都不动。
            log.warn(
                    "摘要异常，summary_upto 不推进（下轮可重试）：session={} cause={} request_id={}",
                    sessionId,
                    e.toString(),
                    requestId);
        }
    }

    /** 会话（要它的旧摘要）与「这次该压哪一段」。判不出来时 `empty`。 */
    private Optional<Ready> ready(String sessionId) {
        ChatSession session = sessionMapper.findById(sessionId);
        if (session == null) {
            return Optional.empty();
        }
        return SummaryPlanner
                .plan(messageMapper.findBySession(sessionId), session.getSummaryUpto(), budget)
                .map(plan -> new Ready(session, plan));
    }

    private record Ready(ChatSession session, SummaryPlanner.Plan plan) {
    }
}
