package com.water.teaching.client;

import com.water.teaching.config.GenerationServiceProperties;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Map;

@Component
public class PythonGenerationClient {

    private final RestClient restClient;

    public PythonGenerationClient(GenerationServiceProperties properties) {
        this.restClient = RestClient.builder()
                .baseUrl(properties.baseUrl())
                .build();
    }

    public Map<String, Object> health() {
        return get("/api/v1/health");
    }

    public Map<String, Object> generatePlan(Map<String, Object> payload) {
        return post("/api/v1/generate/plan", payload);
    }

    public Map<String, Object> generateCourseware(Map<String, Object> payload) {
        return post("/api/v1/generate/courseware", payload);
    }

    public Map<String, Object> validatePlan(Map<String, Object> payload) {
        return post("/api/v1/validate/plan", payload);
    }

    public Map<String, Object> validateCourseware(Map<String, Object> payload) {
        return post("/api/v1/validate/courseware", payload);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> get(String path) {
        return restClient.get()
                .uri(path)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Map.class);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> post(String path, Map<String, Object> payload) {
        return restClient.post()
                .uri(path)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(payload)
                .retrieve()
                .body(Map.class);
    }
}
