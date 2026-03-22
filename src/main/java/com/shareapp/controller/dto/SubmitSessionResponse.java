package com.shareapp.controller.dto;

import java.util.List;
import java.util.Map;

public class SubmitSessionResponse {

    private String sessionId;
    private double finalReturn;
    private double maxDrawdown;
    private double score;
    private double percentile;
    private String stockCode;
    private String stockName;
    private List<Map<String, Object>> actionSummary;

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
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

    public List<Map<String, Object>> getActionSummary() {
        return actionSummary;
    }

    public void setActionSummary(List<Map<String, Object>> actionSummary) {
        this.actionSummary = actionSummary;
    }
}
