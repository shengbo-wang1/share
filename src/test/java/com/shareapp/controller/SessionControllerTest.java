package com.shareapp.controller;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SessionControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldStartSubmitAndFetchResult() throws Exception {
        String startPayload = "{\"userId\":\"user-1\"}";
        MvcResult startResult = mockMvc.perform(post("/api/session/start")
                .contentType(MediaType.APPLICATION_JSON)
                .content(startPayload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.days", hasSize(20)))
                .andReturn();

        String response = startResult.getResponse().getContentAsString();
        String sessionId = extract(response, "sessionId");
        String signature = extract(response, "signature");
        String day1 = extractDay(response, 0);
        String day2 = extractDay(response, 1);

        String submitPayload = "{"
                + "\"sessionId\":\"" + sessionId + "\"," 
                + "\"userId\":\"user-1\"," 
                + "\"signature\":\"" + signature + "\"," 
                + "\"actions\":["
                + "{\"tradeDate\":\"" + day1 + "\",\"targetPosition\":50},"
                + "{\"tradeDate\":\"" + day2 + "\",\"targetPosition\":100}"
                + "]}";

        mockMvc.perform(post("/api/session/submit")
                .contentType(MediaType.APPLICATION_JSON)
                .content(submitPayload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.stockCode").exists())
                .andExpect(jsonPath("$.actionSummary", hasSize(2)));

        mockMvc.perform(get("/api/session/result/{sessionId}", sessionId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.posterPayload.headline").exists());

        mockMvc.perform(get("/api/leaderboard/daily"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.entries", hasSize(1)));
    }

    private String extract(String response, String field) {
        String marker = "\"" + field + "\":\"";
        int start = response.indexOf(marker) + marker.length();
        int end = response.indexOf('"', start);
        return response.substring(start, end);
    }

    private String extractDay(String response, int index) {
        String marker = "\"tradeDate\":\"";
        int position = -1;
        for (int i = 0; i <= index; i++) {
            position = response.indexOf(marker, position + 1);
        }
        int start = position + marker.length();
        int end = response.indexOf('"', start);
        return response.substring(start, end);
    }
}
