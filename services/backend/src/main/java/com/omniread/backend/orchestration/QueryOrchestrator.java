package com.omniread.backend.orchestration;

import com.omniread.backend.contract.model.HistoryMessage;
import com.omniread.backend.contract.model.InternalQueryRequest;
import com.omniread.backend.contract.model.QueryResponse;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import com.omniread.backend.gateway.RagGatewayClient;
import com.omniread.backend.gateway.RagStream;
import com.omniread.backend.session.ChatMessage;
import com.omniread.backend.session.ChatMessageMapper;
import com.omniread.backend.session.ChatMessageStore;
import com.omniread.backend.session.ChatSession;
import com.omniread.backend.session.ContextBudget;
import com.omniread.backend.session.HistoryAssembler;
import com.omniread.backend.session.HistorySelection;
import com.omniread.backend.session.SessionService;
import com.omniread.backend.session.TokenEstimator;
import com.omniread.backend.validation.RealmValidator;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 一轮问答的编排：**会话 → 上下文 → 落库 → 转发 → 落库**。
 *
 * <p>与 M0 相比多了会话：请求带着 `session_id` 进来，Java 先取会话（顺带验归属）、
 * 按预算拼出近轮原文与摘要，把用户这一问**立即落库**，再带着组装好的上下文问 Python，
 * 最后把回答落库。答案是 Python 给的原文，这里不做任何改写——网关不该有第二次判断。
 *
 * <p>**用户消息先写、回答后写**：中途失败时留下一条没有回答的提问，比丢掉「用户问过什么」
 * 要好；而 {@link HistoryAssembler} 对残缺形状本来就有规则（不丢内容、单独成轮），
 * 所以下一轮不会因此错乱。
 */
@Component
public class QueryOrchestrator {

    /** Jackson 3（`tools.jackson`）：本工程的运行时是它，新代码不要混 Jackson 2。 */
    private static final ObjectMapper MAPPER = JsonMapper.builder().build();

    private final RagGatewayClient gateway;
    private final BookCatalog bookCatalog;
    private final SessionService sessionService;
    private final ChatMessageMapper messageMapper;
    private final ChatMessageStore messageStore;
    private final ContextBudget budget;
    private final SessionSummarizer summarizer;

    public QueryOrchestrator(
            RagGatewayClient gateway,
            BookCatalog bookCatalog,
            SessionService sessionService,
            ChatMessageMapper messageMapper,
            ChatMessageStore messageStore,
            ContextBudget budget,
            SessionSummarizer summarizer) {
        this.gateway = gateway;
        this.bookCatalog = bookCatalog;
        this.sessionService = sessionService;
        this.messageMapper = messageMapper;
        this.messageStore = messageStore;
        this.budget = budget;
        this.summarizer = summarizer;
    }

    /**
     * 同步问答：走完一整轮并返回回答。
     *
     * <p>**顺序要紧**：`prepare` 先把历史读出来，之后才写用户这一问。反过来的话，
     * 本轮的问题会出现在它自己的历史里——模型会看到同一个问题被问了两遍，
     * 而两边都不报错。
     */
    public SessionQueryResponse query(SessionQueryRequest request, long userId, String requestId) {
        PreparedQuery prepared = prepare(request, userId);
        appendUserMessage(prepared.session(), request.getQuestion());

        QueryResponse answer = gateway.query(
                toUpstream(request, prepared.session(), prepared.history()), requestId);

        ChatMessage replied = recordAnswer(prepared.session(), answer);
        return SessionQueryResponse.of(answer, prepared.session().getId(), replied.getId());
    }

    /**
     * 取会话 + 校验 + （流式路径）拼上下文。两条路径共用，免得同一个校验写两遍而只改一处。
     */
    public PreparedQuery prepare(SessionQueryRequest request, long userId) {
        ChatSession session = sessionService.requireOwned(userId, request.getSessionId());
        checkBelongsToSession(session, request);
        validateRealm(request);
        return new PreparedQuery(session, assembleHistory(session));
    }

    /** 流式路径用：打开上游的 SSE 字节流（网关只经这里被调用）。 */
    public RagStream openStream(PreparedQuery prepared, SessionQueryRequest request, String requestId) {
        return gateway.openQueryStream(toUpstream(request, prepared.session(), prepared.history()), requestId);
    }

    /**
     * 把回答落库并给出它的 id（末帧要带这个 id 回前端）。两条路径共用。
     *
     * <p>摘要的判定挂在这里，因为**它是「回答已经落库」这件事本身**：放在别处就会出现
     * 「先判定、后落库」的顺序，而判定读的是库里有没有这一条。触发是异步的，
     * 用户等待的那条链上只多一次 SQLite 读。
     */
    public ChatMessage recordAnswer(ChatSession session, QueryResponse answer) {
        ChatMessage replied = appendAssistantMessage(session, answer);
        sessionService.touch(session.getId());
        summarizer.maybeSummarize(session.getId());
        return replied;
    }

    /** 流式路径用：用户这一问先落库。 */
    public ChatMessage recordQuestion(ChatSession session, String question) {
        return appendUserMessage(session, question);
    }

    /** 已经验过归属的会话 + 拼好的上下文。 */
    public record PreparedQuery(ChatSession session, HistorySelection history) {
    }

    /**
     * `book_id` / `level` 与会话冗余，但**不删字段**：前端在「切会话」与「切档位」之间
     * 串味时的症状是「这轮怎么把后面的剧情说出来了」，而那是防剧透约束被绕过。
     * 与其猜用户想要哪一个，不如当场 409 让前端把自己修对。
     */
    private void checkBelongsToSession(ChatSession session, SessionQueryRequest request) {
        if (!session.getBookId().equals(request.getBookId())) {
            throw new RagException(
                    ErrorCode.RAG_SESSION_MISMATCH,
                    "这本书不是该会话的书（会话是 " + session.getBookId() + "）");
        }
        if (!session.getLevel().equalsIgnoreCase(request.getLevel().getValue())) {
            throw new RagException(
                    ErrorCode.RAG_SESSION_MISMATCH,
                    "档位与该会话不符（会话是 " + session.getLevel() + "；切档位请走分叉）");
        }
    }

    private void validateRealm(SessionQueryRequest request) {
        Integer bookId = request.getBookId();
        if (bookId == null) {
            // 契约里 book_id 是 required；走到这里说明校验注解没拦住，仍按同一出口拒绝。
            throw new RagException(ErrorCode.RAG_INVALID_REQUEST, "book_id 必填");
        }
        int chapterCount = bookCatalog.chapterCount(bookId);
        RealmValidator.validateQuery(request.getLevel(), request.getProgress(), chapterCount);
    }

    private HistorySelection assembleHistory(ChatSession session) {
        List<ChatMessage> messages = messageMapper.findBySession(session.getId());
        return HistoryAssembler.assemble(messages, budget);
    }

    /**
     * 用户这一问落库。**会话标题的起名也挂在这里**（两条路径共用）：契约说标题由首轮那句问话
     * 生成，而这句话就是那句问话。
     */
    private ChatMessage appendUserMessage(ChatSession session, String question) {
        sessionService.renameFromFirstQuestion(session, question);
        return messageStore.append(
                session.getId(),
                ChatMessage.ROLE_USER,
                question,
                TokenEstimator.estimate(question),
                null);
    }

    private ChatMessage appendAssistantMessage(ChatSession session, QueryResponse answer) {
        return messageStore.append(
                session.getId(),
                ChatMessage.ROLE_ASSISTANT,
                answer.getAnswer(),
                TokenEstimator.estimate(answer.getAnswer()),
                describe(answer));
    }

    /**
     * 回答那一条的 `meta`：引用范围、改写前后、模型与 `prompt_version`。
     *
     * <p>这条列是内部诊断用的，**不下发给前端**（详情接口刻意不带它）。多轮出问题时的第一个
     * 问题是「当时到底带了什么上下文、用的哪个问题」，那些只有这里留得住。
     */
    private static String describe(QueryResponse answer) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("status", answer.getStatus() == null ? null : answer.getStatus().getValue());
        meta.put("context_chapters", chapterIndexes(answer));
        meta.put("rewritten_query", answer.getRewrittenQuery());
        if (answer.getUsage() != null) {
            meta.put("answer_provider", answer.getUsage().getAnswerProvider());
            meta.put("answer_model", answer.getUsage().getAnswerModel());
            meta.put("latency_ms", answer.getUsage().getLatencyMs());
        }
        try {
            return MAPPER.writeValueAsString(meta);
        } catch (JacksonException e) {
            // 诊断字段写不出来不该毁掉一条已经拿到的回答：留一个可辨认的占位。
            return "{\"meta_error\":\"unserializable\"}";
        }
    }

    private static List<Integer> chapterIndexes(QueryResponse answer) {
        List<Integer> indexes = new ArrayList<>();
        if (answer.getContextChapters() != null) {
            answer.getContextChapters().forEach(chapter -> indexes.add(chapter.getChapterIndex()));
        }
        return indexes;
    }

    private InternalQueryRequest toUpstream(
            SessionQueryRequest request, ChatSession session, HistorySelection history) {
        InternalQueryRequest upstream = new InternalQueryRequest()
                .bookId(request.getBookId())
                // 用 InternalQueryRequest 自己的枚举：两个 schema 各有各的 LevelEnum，
                // 靠 value 转一次，不要靠下标或名字——那是两个独立生成的类型。
                .level(InternalQueryRequest.LevelEnum.fromValue(request.getLevel().getValue()))
                .question(request.getQuestion())
                .progress(request.getProgress())
                .options(request.getOptions())
                .history(UpstreamHistory.of(history.messages()))
                .summary(session.getSummary());
        return upstream;
    }
}
