package com.water.teaching.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

@ConfigurationProperties(prefix = "water.generation-service")
public record GenerationServiceProperties(String baseUrl, Duration timeout) {

    public GenerationServiceProperties {
        if (baseUrl == null || baseUrl.isBlank()) {
            baseUrl = "http://127.0.0.1:5001";
        }
        if (timeout == null) {
            timeout = Duration.ofSeconds(30);
        }
    }
}
