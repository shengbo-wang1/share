package com.shareapp.controller;

import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.shareapp.controller.dto.LeaderboardResponse;
import com.shareapp.service.LeaderboardService;

@RestController
@RequestMapping("/api/leaderboard")
public class LeaderboardController {

    private final LeaderboardService leaderboardService;

    public LeaderboardController(LeaderboardService leaderboardService) {
        this.leaderboardService = leaderboardService;
    }

    @GetMapping("/daily")
    public LeaderboardResponse daily(
            @RequestParam(value = "boardDate", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate boardDate) {
        return leaderboardService.getDailyBoard(boardDate);
    }
}
