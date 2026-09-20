package com.omniread.backend.web;

import com.omniread.backend.contract.model.Health;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 存活探针：只报本进程，不探 Python、不探 provider（外部契约 /api/v1/health 的描述）。
 * 健康检查一旦带上外部调用，就把别人的抖动变成了自己的。
 */
@RestController
@RequestMapping("/api/v1")
public class HealthController {

    private static final Health ALIVE = new Health()
            .status(Health.StatusEnum.OK)
            .service(Health.ServiceEnum.OMNIREAD_BACKEND);

    @GetMapping("/health")
    public Health health() {
        return ALIVE;
    }
}
