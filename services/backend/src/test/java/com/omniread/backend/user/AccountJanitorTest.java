package com.omniread.backend.user;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 过期账户的清理。
 *
 * <p>有效期设成 1 毫秒，于是**任何账户一发放就算过期**——不必伪造 `created_at`
 * 就能覆盖「到期删除」这条路径，也不会让用例依赖墙上时间。
 *
 * <p>要钉的是：过期账户被整行删掉、账户名随之释放（可以重新发放）。
 */
@SpringBootTest(properties = "omniread.account.ttl=1ms")
class AccountJanitorTest {

    private static final Path DB_PATH = createDbPath();

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-janitor-test");
            dir.toFile().deleteOnExit();
            return dir.resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("无法建临时目录", e);
        }
    }

    @DynamicPropertySource
    static void storeFile(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
    }

    @Autowired
    private AccountService accountService;
    @Autowired
    private AccountJanitor janitor;
    @Autowired
    private UserMapper userMapper;

    private static String unique(String prefix) {
        return prefix + "-" + UUID.randomUUID();
    }

    @Test
    @DisplayName("过期账户被删除，且账户名可以重新发放")
    void purgesExpiredAccountAndReleasesName() throws InterruptedException {
        String username = unique("temp");
        accountService.create(username, "pw-" + UUID.randomUUID());
        assertThat(userMapper.findByUsername(username)).isNotNull();

        Thread.sleep(5); // ttl 是 1ms，等它确实跨过去

        assertThat(janitor.purgeExpired()).isGreaterThanOrEqualTo(1);
        assertThat(userMapper.findByUsername(username)).isNull();

        // 账户名释放：同一名字能再发一次（唯一约束没被旧行占着）
        accountService.create(username, "pw-" + UUID.randomUUID());
        assertThat(userMapper.findByUsername(username)).isNotNull();
    }
}
