package com.omniread.backend.error;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.yaml.snakeyaml.Yaml;

/**
 * {@link ErrorCode} 与内部契约的 `ErrorBody.code` 必须逐项一致。
 *
 * <p>两者的关系是**单向的运行时依赖**：`GlobalExceptionHandler` 用
 * `ErrorBody.CodeEnum.valueOf(code.name())` 把本枚举转成响应体里的 code。
 * 因此「枚举里多出一个契约没有的码」不是编译错，而是**只有走到那条错误路径才炸**——
 * 恰好是最不容易被测到的地方（它总在最不该再抛异常的时刻抛）。方向反过来
 * （契约有、枚举没有）则只是网关发不出这个码，也不会有人发现。
 *
 * <p>契约是唯一真相源，所以这个测试读的是 YAML，不是另一份 Java 常量。
 */
class ErrorCodeContractTest {

    /** 契约里有、但 Python 那份也会有——两侧列同一套，见 ErrorBody.code 的描述。 */
    private static final String CONTRACT_RELATIVE_PATH = "contracts/openapi/rag-internal-v1.yaml";

    @Test
    @DisplayName("ErrorCode 与契约 ErrorBody.code 逐项一致")
    void matchesContractExactly() {
        Set<String> contractCodes = contractErrorCodes();
        Set<String> javaCodes = Arrays.stream(ErrorCode.values())
                .map(Enum::name)
                .collect(Collectors.toSet());

        assertThat(javaCodes)
                .as("枚举里有而契约没有的码，会在构造错误响应时抛异常："
                        + "应补进契约的 ErrorBody.code 枚举，或从本枚举删掉")
                .isSubsetOf(contractCodes);
        assertThat(contractCodes)
                .as("契约里有而枚举没有的码：网关发不出它，但 CodeEnum 认得它——"
                        + "若它确实只由网关产生，就该落进本枚举")
                .isSubsetOf(javaCodes);
    }

    private static Set<String> contractErrorCodes() {
        Map<String, Object> document = loadContract();
        Map<String, Object> code = descend(document, "components", "schemas", "ErrorBody", "properties", "code");
        Object values = code.get("enum");
        assertThat(values).as("契约的 ErrorBody.code 应当是闭枚举").isInstanceOf(List.class);
        return ((List<?>) values).stream().map(String::valueOf).collect(Collectors.toSet());
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> descend(Map<String, Object> root, String... keys) {
        Map<String, Object> node = root;
        for (String key : keys) {
            Object next = node.get(key);
            assertThat(next).as("契约里找不到 %s", String.join(".", keys)).isInstanceOf(Map.class);
            node = (Map<String, Object>) next;
        }
        return node;
    }

    /** Maven 的工作目录是 `services/backend`，测试也可能从仓库根跑——向上找锚点文件。 */
    private static Map<String, Object> loadContract() {
        Path directory = Path.of("").toAbsolutePath();
        while (directory != null) {
            Path candidate = directory.resolve(CONTRACT_RELATIVE_PATH);
            if (Files.isRegularFile(candidate)) {
                try {
                    Object document = new Yaml().load(Files.newBufferedReader(candidate));
                    assertThat(document).isInstanceOf(Map.class);
                    return (Map<String, Object>) document;
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            }
            directory = directory.getParent();
        }
        throw new AssertionError("向上找不到 " + CONTRACT_RELATIVE_PATH + "，无法比对错误码");
    }
}
