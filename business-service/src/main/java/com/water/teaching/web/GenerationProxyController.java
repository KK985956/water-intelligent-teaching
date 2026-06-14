package com.water.teaching.web;

import com.water.teaching.client.PythonGenerationClient;
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@Validated
@RestController
@RequestMapping("/api/v1/business")
public class GenerationProxyController {

    private final PythonGenerationClient generationClient;

    public GenerationProxyController(PythonGenerationClient generationClient) {
        this.generationClient = generationClient;
    }

    @PostMapping("/generation/plans")
    public Map<String, Object> generatePlan(@RequestBody @NotNull Map<String, Object> payload) {
        return generationClient.generatePlan(payload);
    }

    @PostMapping("/generation/coursewares")
    public Map<String, Object> generateCourseware(@RequestBody @NotNull Map<String, Object> payload) {
        return generationClient.generateCourseware(payload);
    }

    @PostMapping("/validation/plans")
    public Map<String, Object> validatePlan(@RequestBody @NotNull Map<String, Object> payload) {
        return generationClient.validatePlan(payload);
    }

    @PostMapping("/validation/coursewares")
    public Map<String, Object> validateCourseware(@RequestBody @NotNull Map<String, Object> payload) {
        return generationClient.validateCourseware(payload);
    }
}
