package com.water.teaching;

import com.water.teaching.config.GenerationServiceProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(GenerationServiceProperties.class)
public class WaterBusinessServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(WaterBusinessServiceApplication.class, args);
    }
}
