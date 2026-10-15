package com.omniread.backend.audit;

import com.omniread.backend.error.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 审计行（`docs/方案.md（部署一节）` §三-4）：登录成败（账户 / 时间 / 来源 IP）、
 * 每账户问答次数。时间由日志本身带（格式串里有毫秒时间戳），不重复写一个字段。
 *
 * <p>**记什么、不记什么**：不记口令（也拿不到——校验在 BCrypt 里完成，明文只在请求体内）；
 * 默认不记问答全文。这三样是使用须知第 6 条向用户承诺过的范围，多记一样都得先改那句话。
 *
 * <p>单独一个 logger 名（`omniread.audit`）：审计与排障是两类读者，混在一堆 DEBUG 里
 * 等于没有审计。它按 INFO 输出，`logging.level` 里单独列出来。
 */
@Component
public class AuditLog {

    private static final Logger log = LoggerFactory.getLogger("omniread.audit");

    public void loginSuccess(String account, String ip) {
        log.info("event=login result=success account={} ip={}", clean(account), clean(ip));
    }

    public void loginFailure(String account, String ip, ErrorCode code) {
        log.info("event=login result=failure account={} ip={} code={}", clean(account), clean(ip), code);
    }

    public void query(String account, int usedToday, int limit) {
        log.info("event=query account={} used_today={} limit={}", clean(account), usedToday, limit);
    }

    /**
     * 账户名与来源 IP 都是**外部输入**，其中换行能把一行日志伪造成两行——
     * 而审计的全部价值就在于「这一行是一件事」。控制字符一律换成 `_`。
     */
    private static String clean(String value) {
        return value == null || value.isEmpty() ? "-" : value.replaceAll("\\p{Cntrl}", "_");
    }
}
