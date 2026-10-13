package com.omniread.backend.user;

import com.omniread.backend.quota.UsageDailyMapper;
import com.omniread.backend.session.ChatSessionMapper;
import java.time.Instant;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 账户的发放、认证与停用。**没有注册、没有找回、没有自助改密**——账户由管理方发放
 * （`docs/m1/用户管理需求.md` §一：演示账户，不开放注册）。
 *
 * <p>发放与停用都是管理方动作，不走 HTTP：本期不做管理后台 UI（同文档 §四），
 * 所以这两个方法由命令行脚本或测试调用。等真需要了再加端点，不必现在先开一个没人用的口子。
 */
@Service
public class AccountService {

    private static final Logger log = LoggerFactory.getLogger(AccountService.class);

    private final UserMapper userMapper;
    private final AuthSessionMapper authSessionMapper;
    private final ChatSessionMapper chatSessionMapper;
    private final UserProgressMapper userProgressMapper;
    private final UsageDailyMapper usageDailyMapper;
    private final PasswordHasher passwordHasher;

    public AccountService(
            UserMapper userMapper,
            AuthSessionMapper authSessionMapper,
            ChatSessionMapper chatSessionMapper,
            UserProgressMapper userProgressMapper,
            UsageDailyMapper usageDailyMapper,
            PasswordHasher passwordHasher) {
        this.userMapper = userMapper;
        this.authSessionMapper = authSessionMapper;
        this.chatSessionMapper = chatSessionMapper;
        this.userProgressMapper = userProgressMapper;
        this.usageDailyMapper = usageDailyMapper;
        this.passwordHasher = passwordHasher;
    }

    /** 发放一个账户。账户名重复时由唯一约束拦下，不在这里先查一次——查了也挡不住并发。 */
    @Transactional
    public User create(String username, String rawPassword) {
        User user = new User();
        user.setUsername(username);
        user.setPasswordHash(passwordHasher.hash(rawPassword));
        user.setStatus(User.STATUS_ACTIVE);
        user.setCreatedAt(Instant.now().toString());
        userMapper.insert(user);
        log.info("发放账户：{}（id={}）", username, user.getId());
        return user;
    }

    /**
     * 凭证登录。
     *
     * <p>**失败一律返回空，不区分「没有这个账户」与「口令不对」**：区分开等于给了一个
     * 枚举账户名的接口。日志里也只记账户名与结果，不记口令。
     *
     * <p>停用的账户登不进来——`status` 与口令一起判。
     */
    @Transactional
    public Optional<User> authenticate(String username, String rawPassword) {
        User user = userMapper.findByUsername(username);
        if (user == null || !passwordHasher.matches(rawPassword, user.getPasswordHash())) {
            log.info("登录失败：{}", username);
            return Optional.empty();
        }
        if (!user.isActive()) {
            log.info("登录被拒（账户已停用）：{}", username);
            return Optional.empty();
        }
        userMapper.updateLastLogin(user.getId(), Instant.now().toString());
        log.info("登录成功：{}", username);
        return Optional.of(user);
    }

    /**
     * 停用账户并**清理它的全部内容数据**（D15）。
     *
     * <p>账户是一次性的测试账户，清理掉就不留原文片段。删的是：登录会话（登录态立即失效）、
     * 对话会话（消息由外键 `ON DELETE CASCADE` 带走）、阅读进度、每日用量。
     * **账户行保留为 `disabled`**
     * ——审计与复用需要，而这一行不含任何内容。
     *
     * <p>整个过程在一个事务里：删了一半就中断会留下「登录态还在、会话已经没了」的中间态，
     * 而那个状态从外面看起来是正常的。
     */
    @Transactional
    public void disableAndPurge(long userId) {
        int sessions = authSessionMapper.deleteByUserId(userId);
        int chats = chatSessionMapper.deleteByUserId(userId);
        int progress = userProgressMapper.deleteByUserId(userId);
        int turns = usageDailyMapper.deleteByUserId(userId);
        userMapper.updateStatus(userId, User.STATUS_DISABLED);
        log.info(
                "停用并清理账户 id={}：登录会话 {} 条、对话会话 {} 个、进度 {} 条、用量 {} 行",
                userId,
                sessions,
                chats,
                progress,
                turns);
    }
}
