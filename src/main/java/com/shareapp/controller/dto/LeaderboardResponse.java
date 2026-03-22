package com.shareapp.controller.dto;

import java.util.List;

public class LeaderboardResponse {

    private String boardDate;
    private List<Entry> entries;

    public String getBoardDate() {
        return boardDate;
    }

    public void setBoardDate(String boardDate) {
        this.boardDate = boardDate;
    }

    public List<Entry> getEntries() {
        return entries;
    }

    public void setEntries(List<Entry> entries) {
        this.entries = entries;
    }

    public static class Entry {
        private int rank;
        private String userId;
        private String sessionId;
        private double score;
        private double finalReturn;
        private double maxDrawdown;
        private double percentile;

        public int getRank() {
            return rank;
        }

        public void setRank(int rank) {
            this.rank = rank;
        }

        public String getUserId() {
            return userId;
        }

        public void setUserId(String userId) {
            this.userId = userId;
        }

        public String getSessionId() {
            return sessionId;
        }

        public void setSessionId(String sessionId) {
            this.sessionId = sessionId;
        }

        public double getScore() {
            return score;
        }

        public void setScore(double score) {
            this.score = score;
        }

        public double getFinalReturn() {
            return finalReturn;
        }

        public void setFinalReturn(double finalReturn) {
            this.finalReturn = finalReturn;
        }

        public double getMaxDrawdown() {
            return maxDrawdown;
        }

        public void setMaxDrawdown(double maxDrawdown) {
            this.maxDrawdown = maxDrawdown;
        }

        public double getPercentile() {
            return percentile;
        }

        public void setPercentile(double percentile) {
            this.percentile = percentile;
        }
    }
}
