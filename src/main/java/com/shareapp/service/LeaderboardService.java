package com.shareapp.service;

import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

import org.springframework.stereotype.Service;

import com.shareapp.controller.dto.LeaderboardResponse;
import com.shareapp.domain.UserResult;
import com.shareapp.repository.UserResultRepository;

@Service
public class LeaderboardService {

    private final UserResultRepository userResultRepository;

    public LeaderboardService(UserResultRepository userResultRepository) {
        this.userResultRepository = userResultRepository;
    }

    public LeaderboardResponse getDailyBoard(LocalDate boardDate) {
        LocalDate effectiveDate = boardDate == null ? LocalDate.now(ZoneOffset.UTC) : boardDate;
        List<UserResult> results = userResultRepository.findByBoardDate(effectiveDate);
        LeaderboardResponse response = new LeaderboardResponse();
        response.setBoardDate(effectiveDate.toString());
        List<LeaderboardResponse.Entry> entries = new ArrayList<LeaderboardResponse.Entry>();
        for (int i = 0; i < results.size(); i++) {
            UserResult result = results.get(i);
            LeaderboardResponse.Entry entry = new LeaderboardResponse.Entry();
            entry.setRank(i + 1);
            entry.setUserId(result.getUserId());
            entry.setSessionId(result.getSessionId());
            entry.setScore(result.getScore());
            entry.setFinalReturn(result.getFinalReturn());
            entry.setMaxDrawdown(result.getMaxDrawdown());
            entry.setPercentile(result.getPercentile());
            entries.add(entry);
        }
        response.setEntries(entries);
        return response;
    }
}
