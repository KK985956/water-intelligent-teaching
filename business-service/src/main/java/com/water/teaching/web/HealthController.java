package com.water.teaching.web;

import com.water.teaching.client.PythonGenerationClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;

@RestController
@RequestMapping("/api/v1")
public class HealthController {

    private final PythonGenerationClient generationClient;

    public HealthController(PythonGenerationClient generationClient) {
        this.generationClient = generationClient;
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of(
                "status", "UP",
                "service", "spring-business-service",
                "generationService", generationClient.health(),
                "checkedAt", Instant.now().toString()
        );
    }
}
