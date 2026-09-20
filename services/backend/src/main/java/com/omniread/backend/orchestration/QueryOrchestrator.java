package com.omniread.backend.orchestration;

import com.omniread.backend.contract.model.QueryRequest;
import com.omniread.backend.contract.model.QueryResponse;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import com.omniread.backend.gateway.RagGatewayClient;
import com.omniread.backend.gateway.RagStream;
import com.omniread.backend.validation.RealmValidator;
import org.springframework.stereotype.Component;

/**
 * 查询编排：先按 M0-01 §7 校验 realm，再转发给 Python。
 *
 * 作答与拒答都是 Python 回的正常业务结果，这里不做任何改写 —— 网关不该有第二次判断。
 */
@Component
public class QueryOrchestrator {

    private final RagGatewayClient gateway;
    private final BookCatalog bookCatalog;

    public QueryOrchestrator(RagGatewayClient gateway, BookCatalog bookCatalog) {
        this.gateway = gateway;
        this.bookCatalog = bookCatalog;
    }

    public QueryResponse query(QueryRequest request, String requestId) {
        validateRealm(request);
        return gateway.query(request, requestId);
    }

    /** SSE 只用字节流，Java 不解析事件：帧语义的唯一实现方是 Python 适配器。 */
    public RagStream stream(QueryRequest request, String requestId) {
        validateRealm(request);
        return gateway.openQueryStream(request, requestId);
    }

    private void validateRealm(QueryRequest request) {
        Integer bookId = request.getBookId();
        if (bookId == null) {
            // 契约里 book_id 是 required；走到这里说明校验注解没拦住，仍按同一出口拒绝。
            throw new RagException(ErrorCode.RAG_INVALID_REALM, "book_id 必填");
        }
        int chapterCount = bookCatalog.chapterCount(bookId);
        RealmValidator.validateQuery(request.getLevel(), request.getProgress(), chapterCount);
    }
}
