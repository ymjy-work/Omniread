package com.omniread.backend.user;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 登录会话的生命周期：种下、解析、撤销（`docs/方案.md（依赖与选型一节）` §十）。
 *
 * <p>口令校验不在这里，在 {@link AccountService#authenticate}——那一层已经保证
 * 「账户不存在」与「口令不对」返回同一种结果，这里只是把它的成功结果换成一条登录会话。
 *
 * <p>**这里没有「续期」**：8 小时到点就得重新登录。滑动过期会让一个一直开着的标签页
 * 永不掉线，而演示账户的可回收性比体验重要。
 */
@Service
public class AuthService {

    private static final Logger log = LoggerFactory.getLogger(AuthService.class);

    /** 距上次记录超过这么久才再写一次 `last_seen_at`，见 {@link #touchIfStale}。 */
    private static final Duration LAST_SEEN_REFRESH = Duration.ofMinutes(5);

    private final AccountService accountService;
    private final AuthSessionMapper authSessionMapper;
    private final UserMapper userMapper;
    private final AuthTokens tokens;
    private final AuthProperties properties;

    public AuthService(
            AccountService accountService,
            AuthSessionMapper authSessionMapper,
            UserMapper userMapper,
            AuthTokens tokens,
            AuthProperties properties) {
        this.accountService = accountService;
        this.authSessionMapper = authSessionMapper;
        this.userMapper = userMapper;
        this.tokens = tokens;
        this.properties = properties;
    }

    /** 一次登录的结果：token 原文**只在这里出现一次**，之后只有 cookie 里有。 */
    public record IssuedSession(String token, String username, Instant expiresAt) {
    }

    /**
     * 凭证登录并种下一条登录会话。
     *
     * <p>`createdAt` / `expiresAt` / cookie 的 `Max-Age` 都由**同一个** `now` 推出来：
     * 分别取两次当前时间，三者之间就会差几毫秒，而这种差值只会在边界时刻显形。
     */
    @Transactional
    public IssuedSession login(String username, String rawPassword) {
        User user = accountService
                .authenticate(username, rawPassword)
                .orElseThrow(() -> new RagException(ErrorCode.RAG_UNAUTHENTICATED, "账户名或口令不正确"));

        String token = tokens.newToken();
        Instant now = Instant.now();
        Instant expiresAt = now.plus(properties.sessionTtl());

        AuthSession session = new AuthSession();
        session.setTokenHash(tokens.hash(token));
        session.setUserId(user.getId());
        session.setCreatedAt(now.toString());
        session.setExpiresAt(expiresAt.toString());
        session.setLastSeenAt(now.toString());
        authSessionMapper.insert(session);

        log.info("登录会话已建立：{}（{} 到期）", user.getUsername(), expiresAt);
        return new IssuedSession(token, user.getUsername(), expiresAt);
    }

    /**
     * cookie 里的 token → 当前账户。任何一步不成立都返回空，由调用方统一给 401：
     * 「没这个 token」「过期了」「账户被停用了」对客户端是同一件事——重新登录。
     */
    public Optional<AuthenticatedUser> resolve(String token) {
        if (token == null || token.isBlank()) {
            return Optional.empty();
        }
        AuthSession session = authSessionMapper.findByTokenHash(tokens.hash(token));
        if (session == null) {
            return Optional.empty();
        }
        Instant expiresAt = parseExpiry(session);
        if (expiresAt == null || !expiresAt.isAfter(Instant.now())) {
            return Optional.empty();
        }
        User user = userMapper.findById(session.getUserId());
        // 停用时 D15 会删掉登录会话行，但那条 DELETE 与这次查询之间没有时序保证，
        // 所以状态在这里再判一次——否则「刚被停用」会有一个窗口还能用。
        if (user == null || !user.isActive()) {
            return Optional.empty();
        }
        touchIfStale(session);
        return Optional.of(new AuthenticatedUser(user.getId(), user.getUsername(), expiresAt));
    }

    /** 退出：只删自己那一条，别人的登录态不受影响。 */
    public void logout(String token) {
        if (token == null || token.isBlank()) {
            return;
        }
        authSessionMapper.deleteByTokenHash(tokens.hash(token));
    }

    /** 过期行清理。启动时一次、之后每日一次（{@link AuthSessionJanitor}）。 */
    public int purgeExpired() {
        return authSessionMapper.deleteExpired(Instant.now().toString());
    }

    /**
     * `expires_at` 读不出来时**当作已过期**（fail closed），并留一条日志。
     *
     * <p>反过来处理（当作有效）会让一条被改坏的记录变成永久登录态；而这一列只有本服务写，
     * 出现读不出来的值说明库被外部动过，正是该拒的时候。
     */
    private Instant parseExpiry(AuthSession session) {
        try {
            return Instant.parse(session.getExpiresAt());
        } catch (DateTimeParseException | NullPointerException e) {
            log.warn("登录会话的 expires_at 不可解析，按已过期处理：userId={}", session.getUserId());
            return null;
        }
    }

    /**
     * 刷新 `last_seen_at`，但**不是每个请求都写**：SQLite 是单写者，而这是每个受保护请求
     * 都会走到的路径，一次一写会把它变成写热点；而这个字段只用于「这个登录态还活着吗」，
     * 分钟级精度足够。
     *
     * <p>写失败**不挡请求**：走到这里登录态已经验证通过了，一次记账字段写不进去
     * 不该把合法用户关在门外。但不静默——WARN 带原因。
     */
    private void touchIfStale(AuthSession session) {
        Instant now = Instant.now();
        Instant lastSeen = parseInstantOrNull(session.getLastSeenAt());
        if (lastSeen != null && Duration.between(lastSeen, now).compareTo(LAST_SEEN_REFRESH) < 0) {
            return;
        }
        try {
            authSessionMapper.touch(session.getTokenHash(), now.toString());
        } catch (DataAccessException e) {
            log.warn("刷新 last_seen_at 失败（不影响本次请求）：userId={}，原因：{}",
                    session.getUserId(), e.getMessage());
        }
    }

    private static Instant parseInstantOrNull(String value) {
        try {
            return value == null ? null : Instant.parse(value);
        } catch (DateTimeParseException e) {
            return null;
        }
    }
}
