package com.omniread.backend.user;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * 登录请求体，与外部契约的 `LoginRequest` 一致（手写而不是生成：外部契约不喂生成器，
 * 同 {@code progress/Progress}）。
 *
 * <p>上下界照契约写（1..64 / 1..200），**不额外加「非空白」**：契约里没有这一条，
 * 加了会把一次本该 401 的登录尝试变成 400，而 400 是「请求本身不合法」——
 * 一个空格组成的账户名并不比一个打错的账户名更不合法。
 */
public record LoginRequest(
        @NotNull @Size(min = 1, max = 64) String username,
        @NotNull @Size(min = 1, max = 200) String password) {
}
