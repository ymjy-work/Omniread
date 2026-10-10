package com.omniread.backend.user;

import com.omniread.backend.store.StoreProperties;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * 账户管理命令：发放 / 停用 / 列出（`docs/m1/用户管理需求.md` §三）。
 *
 * <p>**这是管理方动作的唯一入口**：账户由开发者发放、不开放注册（§一），而 §四 明确
 * 不做管理后台 UI，所以只能是一个命令行工具。包装脚本是 `scripts/account.sh`。
 *
 * <p>**口令只从环境变量读，不接受命令行参数**：argv 会进 shell 历史、会出现在进程列表里，
 * 在同一个终端里按一次上箭头就能原样捞回来。
 *
 * <p>没有 {@code omniread.admin.command} 时什么都不做——服务端启动走的是同一个 jar。
 * 命令的结果打在**标准输出**（脚本要读它），诊断留在日志里：两种读者，两种去处。
 */
@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class AccountAdminRunner implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AccountAdminRunner.class);

    static final String COMMAND_PROPERTY = "omniread.admin.command";

    static final String USERNAME_PROPERTY = "omniread.admin.username";

    /** 口令走环境变量。名字固定，包装脚本与文档都按它写。 */
    static final String PASSWORD_ENV = "OMNIREAD_ADMIN_PASSWORD";

    private final Environment environment;
    private final AccountService accountService;
    private final UserMapper userMapper;
    private final StoreProperties storeProperties;

    public AccountAdminRunner(
            Environment environment,
            AccountService accountService,
            UserMapper userMapper,
            StoreProperties storeProperties) {
        this.environment = environment;
        this.accountService = accountService;
        this.userMapper = userMapper;
        this.storeProperties = storeProperties;
    }

    @Override
    public void run(ApplicationArguments args) {
        String command = environment.getProperty(COMMAND_PROPERTY);
        if (command == null || command.isBlank()) {
            return;
        }
        System.exit(execute(command));
    }

    /**
     * 执行一条命令并返回进程退出码。
     *
     * <p>**必须显式退出**：这是个命令行工具，跑完就该结束进程。不退出的话任务本身做完了、
     * 进程却一直吊着不退——实测卡在这里，而卡住的不是任务是「谁来关灯」：
     * {@code @EnableScheduling} 建的调度线程池是非守护线程，JVM 会一直等它。
     *
     * <p>单独拆成一个返回退出码的方法是为了**能测**：{@link #run} 里那句
     * {@code System.exit} 会把测试 JVM 一起带走。
     */
    int execute(String command) {
        try {
            dispatch(command);
            return 0;
        } catch (IllegalStateException e) {
            // 「账户已存在」「没读到口令」这类是**操作者能直接改的**，不该给他一屏栈：
            // 栈里全是框架帧，真正要看的那句在最后一行。一行说清就够了。
            System.err.println("失败：" + e.getMessage());
            return 1;
        } catch (RuntimeException e) {
            // 其余的（写库失败之类）才留全栈——那种时候栈里的信息比一行 message 值钱。
            log.error("账户管理命令异常退出：{}", command, e);
            System.err.println("失败：" + e.getMessage() + "（细节见日志）");
            return 1;
        }
    }

    void dispatch(String command) {
        switch (command) {
            case "create" -> create();
            case "disable" -> disable();
            case "list" -> list();
            default -> throw new IllegalStateException(
                    "未知命令：" + command + "（可用：create / disable / list）");
        }
    }

    private void create() {
        String username = requireUsername();
        User existing = userMapper.findByUsername(username);
        if (existing != null) {
            // 不静默复用也不覆盖：发放一个已存在的账户，多半是操作者以为自己在建另一个，
            // 而「口令没生效」在客户端看起来是「密码错了」——两个都不好查。
            throw new IllegalStateException(
                    "账户已存在：" + username + "（状态 " + existing.getStatus() + "）");
        }
        accountService.create(username, requirePassword());
        report("已发放账户：" + username);
    }

    private void disable() {
        String username = requireUsername();
        User user = userMapper.findByUsername(username);
        if (user == null) {
            throw new IllegalStateException("没有这个账户：" + username);
        }
        // D15：一个事务里删登录会话 / 对话会话 / 消息 / 进度，账户行留 disabled。
        accountService.disableAndPurge(user.getId());
        report("已停用并清理账户：" + username);
    }

    /** 只列账户名与状态：口令哈希不进任何输出，连终端也不行。 */
    private void list() {
        report("账户（名字 \t 状态 \t 建立时间）：");
        for (User user : userMapper.findAll()) {
            System.out.println(user.getUsername() + "\t" + user.getStatus() + "\t" + user.getCreatedAt());
        }
    }

    private String requireUsername() {
        String username = environment.getProperty(USERNAME_PROPERTY);
        if (username == null || username.isBlank()) {
            throw new IllegalStateException("缺少账户名：" + USERNAME_PROPERTY);
        }
        return username;
    }

    private String requirePassword() {
        String password = environment.getProperty(PASSWORD_ENV);
        if (password == null || password.isEmpty()) {
            throw new IllegalStateException("没有从环境变量 " + PASSWORD_ENV + " 读到口令。"
                    + "口令不接受命令行参数——它会进 shell 历史，也会出现在进程列表里");
        }
        return password;
    }

    /**
     * 每次都把「动的是哪个库」打出来。
     *
     * <p>相对路径按进程工作目录解析，于是同一个 jar 从仓库根跑与从 `services/backend` 跑
     * 会落到**两个不同的文件**上——而两边的日志都正常。让命令自己报出门牌号，
     * 比事后去猜它在哪一层目录下跑的要强。
     */
    private void report(String message) {
        System.out.println(message);
        System.out.println("库文件：" + Path.of(storeProperties.file()).toAbsolutePath().normalize());
    }
}
