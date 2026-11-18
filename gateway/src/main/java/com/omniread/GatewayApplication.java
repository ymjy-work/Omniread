package com.omniread;

import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GatewayApplication {

	public static void main(String[] args) throws Exception {
		// SQLite JDBC 不会创建父目录，启动前先建好
		String db = System.getenv().getOrDefault("OMNIREAD_GATEWAY_DB", "./var/gateway.db");
		Files.createDirectories(Path.of(db).toAbsolutePath().getParent());
		SpringApplication.run(GatewayApplication.class, args);
	}

}
