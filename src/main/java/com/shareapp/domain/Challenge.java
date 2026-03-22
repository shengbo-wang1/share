package com.shareapp.domain;

import java.time.LocalDate;
import java.util.Collections;
import java.util.List;

public class Challenge {

    private final String challengeId;
    private final String stockCode;
    private final String stockName;
    private final LocalDate startDate;
    private final LocalDate endDate;
    private final int totalDays;
    private final String difficulty;
    private final List<String> tags;
    private final boolean featured;
    private final boolean active;
    private final List<ChallengeDay> days;

    public Challenge(String challengeId, String stockCode, String stockName, LocalDate startDate, LocalDate endDate,
            int totalDays, String difficulty, List<String> tags, boolean featured, boolean active,
            List<ChallengeDay> days) {
        this.challengeId = challengeId;
        this.stockCode = stockCode;
        this.stockName = stockName;
        this.startDate = startDate;
        this.endDate = endDate;
        this.totalDays = totalDays;
        this.difficulty = difficulty;
        this.tags = tags;
        this.featured = featured;
        this.active = active;
        this.days = Collections.unmodifiableList(days);
    }

    public String getChallengeId() {
        return challengeId;
    }

    public String getStockCode() {
        return stockCode;
    }

    public String getStockName() {
        return stockName;
    }

    public LocalDate getStartDate() {
        return startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }

    public int getTotalDays() {
        return totalDays;
    }

    public String getDifficulty() {
        return difficulty;
    }

    public List<String> getTags() {
        return tags;
    }

    public boolean isFeatured() {
        return featured;
    }

    public boolean isActive() {
        return active;
    }

    public List<ChallengeDay> getDays() {
        return days;
    }
}
