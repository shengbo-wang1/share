package com.shareapp.controller.dto;

import java.util.List;
import java.util.Map;

public class ResultResponse {

    private String sessionId;
    private String challengeId;
    private String stockCode;
    private String stockName;
    private double finalReturn;
    private double maxDrawdown;
    private double score;
    private double percentile;
    private List<Map<String, Object>> actionSummary;
    private Map<String, Object> posterPayload;

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

    public String getStockCode() {
        return stockCode;
    }

    public void setStockCode(String stockCode) {
        this.stockCode = stockCode;
    }

    public String getStockName() {
        return stockName;
    }

    public void setStockName(String stockName) {
        this.stockName = stockName;
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

    public double getScore() {
        return score;
    }

    public void setScore(double score) {
        this.score = score;
    }

    public double getPercentile() {
        return percentile;
    }

    public void setPercentile(double percentile) {
        this.percentile = percentile;
    }

    public List<Map<String, Object>> getActionSummary() {
        return actionSummary;
    }

    public void setActionSummary(List<Map<String, Object>> actionSummary) {
        this.actionSummary = actionSummary;
    }

    public Map<String, Object> getPosterPayload() {
        return posterPayload;
    }

    public void setPosterPayload(Map<String, Object> posterPayload) {
        this.posterPayload = posterPayload;
    }
}
