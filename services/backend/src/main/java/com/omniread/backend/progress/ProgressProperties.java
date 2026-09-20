package com.omniread.backend.progress;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 阅读进度的本地文件位置。进度只落在 Java 进程本地（M0-01 §1：Python 不保存用户进度），
 * 所以位置是一项部署参数而不是代码常量。
 */
@ConfigurationProperties(prefix = "omniread.progress")
public record ProgressProperties(Path file) {
}
