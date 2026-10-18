package com.omniread.backend.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.omniread.backend.store.StoreProperties;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

/**
 * 账户管理命令的分发与拒绝路径。不起 Spring 上下文：这里要验的是「哪条命令走到了哪」，
 * 以及几条**必须报错而不是硬做**的分支——那些分支走错时不会有异常，只会默默建错东西。
 *
 * <p>测的是 {@code dispatch} / {@code execute} 而不是 {@code run}：后者带着一句
 * {@code System.exit}，把测试 JVM 一起带走。`run` 里只剩「从环境变量取命令」这一步。
 *
 * <p>口令在真实运行里从环境变量来（`scripts/account.sh` 注入）；测试里当成普通属性设进去，
 * 对 {@code Environment} 的查找路径而言两者是同一件事。
 */
class AccountAdminRunnerTest {

    private MockEnvironment environment;
    private AccountService accountService;
    private UserMapper userMapper;
    private AccountAdminRunner runner;

    @BeforeEach
    void setUp() {
        environment = new MockEnvironment();
        accountService = mock(AccountService.class);
        userMapper = mock(UserMapper.class);
        runner = new AccountAdminRunner(
                environment, accountService, userMapper, new StoreProperties("var/omniread.db"));
    }

    // ── 分发 ──

    @Test
    @DisplayName("没有 admin.command 时什么都不做——服务端启动走的是同一个 jar")
    void doesNothingOnNormalStartup() {
        assertThatCode(() -> runner.run(null)).doesNotThrowAnyException();
        verify(accountService, never()).create(anyString(), anyString());
    }

    @Test
    @DisplayName("create：用环境变量里的口令发放账户")
    void createUsesThePasswordFromTheEnvironment() {
        when(userMapper.findByUsername("alice")).thenReturn(null);
        environment.setProperty(AccountAdminRunner.USERNAME_PROPERTY, "alice");
        environment.setProperty(AccountAdminRunner.PASSWORD_ENV, "s3cret");

        runner.dispatch("create");

        verify(accountService).create("alice", "s3cret");
    }

    @Test
    @DisplayName("disable：按账户 id 走停用即清理，不是只改个状态")
    void disablePurgesTheAccount() {
        User user = new User();
        user.setUsername("bob");
        user.setId(7L);
        user.setStatus(User.STATUS_ACTIVE);
        when(userMapper.findByUsername("bob")).thenReturn(user);
        environment.setProperty(AccountAdminRunner.USERNAME_PROPERTY, "bob");

        runner.dispatch("disable");

        verify(accountService).disableAndPurge(7L);
    }

    @Test
    @DisplayName("list：只读账户名与状态，碰不到口令哈希")
    void listPrintsNameAndStatusOnly() {
        User user = new User();
        user.setUsername("carol");
        user.setStatus(User.STATUS_DISABLED);
        user.setCreatedAt("2026-10-10T00:00:00Z");
        user.setPasswordHash("$2a$10$must-not-appear");
        when(userMapper.findAll()).thenReturn(List.of(user));

        String output = captureStdout(() -> runner.dispatch("list"));

        assertThat(output).contains("carol").contains(User.STATUS_DISABLED);
        assertThat(output).as("口令哈希不进任何输出，终端也不行").doesNotContain("$2a$");
    }

    // ── 拒绝路径：这几条走错时不会有异常，只会默默建错东西 ──

    @Test
    @DisplayName("create 遇到已存在的账户直接报错，不静默复用也不覆盖")
    void createRefusesAnExistingAccount() {
        User existing = new User();
        existing.setUsername("alice");
        existing.setStatus(User.STATUS_ACTIVE);
        when(userMapper.findByUsername("alice")).thenReturn(existing);
        environment.setProperty(AccountAdminRunner.USERNAME_PROPERTY, "alice");
        environment.setProperty(AccountAdminRunner.PASSWORD_ENV, "s3cret");

        assertThatThrownBy(() -> runner.dispatch("create"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("账户已存在")
                .hasMessageContaining("active");
        verify(accountService, never()).create(anyString(), anyString());
    }

    @Test
    @DisplayName("create 没读到口令时拒绝执行，而不是发一个空口令的账户")
    void createRefusesWithoutAPassword() {
        when(userMapper.findByUsername("alice")).thenReturn(null);
        environment.setProperty(AccountAdminRunner.USERNAME_PROPERTY, "alice");

        assertThatThrownBy(() -> runner.dispatch("create"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining(AccountAdminRunner.PASSWORD_ENV);
        verify(accountService, never()).create(anyString(), anyString());
    }

    @Test
    @DisplayName("disable 一个不存在的账户报错，不静默成功")
    void disableRefusesAnUnknownAccount() {
        when(userMapper.findByUsername("ghost")).thenReturn(null);
        environment.setProperty(AccountAdminRunner.USERNAME_PROPERTY, "ghost");

        assertThatThrownBy(() -> runner.dispatch("disable"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("没有这个账户");
        verify(accountService, never()).disableAndPurge(anyLong());
    }

    @Test
    @DisplayName("未知命令报错并列出可用命令")
    void unknownCommandIsRejected() {
        assertThatThrownBy(() -> runner.dispatch("destroy"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("destroy")
                .hasMessageContaining("create");
    }

    // ── 退出码：脚本要靠它判断成败 ──

    @Test
    @DisplayName("成功退 0，失败退 1 且只往终端打一行")
    void exitCodeReflectsTheOutcome() {
        when(userMapper.findByUsername("alice")).thenReturn(null);
        environment.setProperty(AccountAdminRunner.USERNAME_PROPERTY, "alice");
        environment.setProperty(AccountAdminRunner.PASSWORD_ENV, "s3cret");
        assertThat(runner.execute("create")).isZero();

        String stderr = captureStderr(() -> assertThat(runner.execute("destroy")).isEqualTo(1));
        assertThat(stderr).contains("失败").contains("destroy");
    }

    // ── 夹具 ──

    private static String captureStdout(Runnable action) {
        return capture(System.out, action, true);
    }

    private static String captureStderr(Runnable action) {
        return capture(System.err, action, false);
    }

    private static String capture(PrintStream original, Runnable action, boolean stdout) {
        ByteArrayOutputStream captured = new ByteArrayOutputStream();
        PrintStream replacement = new PrintStream(captured, true, StandardCharsets.UTF_8);
        try {
            if (stdout) {
                System.setOut(replacement);
            } else {
                System.setErr(replacement);
            }
            action.run();
        } finally {
            if (stdout) {
                System.setOut(original);
            } else {
                System.setErr(original);
            }
        }
        return captured.toString(StandardCharsets.UTF_8);
    }
}
