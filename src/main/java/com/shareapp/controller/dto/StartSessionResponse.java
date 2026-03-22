package com.shareapp.controller.dto;

import java.time.Instant;
import java.util.List;

public class StartSessionResponse {

    private String sessionId;
    private String challengeId;
    private String signature;
    private Instant startedAt;
    private String difficulty;
    private List<String> tags;
    private RulesView rules;
    private List<ChallengeDayView> days;

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getChallengeId() {
        return challengeId;
    }

    public void setChallengeId(String challengeId) {
        this.challengeId = challengeId;
    }

    public String getSignature() {
        return signature;
    }

    public void setSignature(String signature) {
        this.signature = signature;
    }

    public Instant getStartedAt() {
        return startedAt;
    }

    public void setStartedAt(Instant startedAt) {
        this.startedAt = startedAt;
    }

    public String getDifficulty() {
        return difficulty;
    }

    public void setDifficulty(String difficulty) {
        this.difficulty = difficulty;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public RulesView getRules() {
        return rules;
    }

    public void setRules(RulesView rules) {
        this.rules = rules;
    }

    public List<ChallengeDayView> getDays() {
        return days;
    }

    public void setDays(List<ChallengeDayView> days) {
        this.days = days;
    }

    public static class RulesView {
        private int totalDays;
        private int actionableDays;
        private List<Integer> targetPositions;
        private double initialCash;
        private double tradingCostRate;
        private String executionTiming;
        private String scoreBasis;

        public int getTotalDays() {
            return totalDays;
        }

        public void setTotalDays(int totalDays) {
            this.totalDays = totalDays;
        }

        public int getActionableDays() {
            return actionableDays;
        }

        public void setActionableDays(int actionableDays) {
            this.actionableDays = actionableDays;
        }

        public List<Integer> getTargetPositions() {
            return targetPositions;
        }

        public void setTargetPositions(List<Integer> targetPositions) {
            this.targetPositions = targetPositions;
        }

        public double getInitialCash() {
            return initialCash;
        }

        public void setInitialCash(double initialCash) {
            this.initialCash = initialCash;
        }

        public double getTradingCostRate() {
            return tradingCostRate;
        }

        public void setTradingCostRate(double tradingCostRate) {
            this.tradingCostRate = tradingCostRate;
        }

        public String getExecutionTiming() {
            return executionTiming;
        }

        public void setExecutionTiming(String executionTiming) {
            this.executionTiming = executionTiming;
        }

        public String getScoreBasis() {
            return scoreBasis;
        }

        public void setScoreBasis(String scoreBasis) {
            this.scoreBasis = scoreBasis;
        }
    }
}
