package com.shareapp.domain;

import java.time.Instant;
import java.util.Collections;
import java.util.List;
import java.util.Map;

public class UserResult {

    private final String sessionId;
    private final String userId;
    private final String challengeId;
    private final double finalReturn;
    private final double maxDrawdown;
    private final double score;
    private final double percentile;
    private final Map<String, Object> posterPayload;
    private final List<UserAction> actions;
    private final Instant createdAt;

    public UserResult(String sessionId, String userId, String challengeId, double finalReturn, double maxDrawdown,
            double score, double percentile, Map<String, Object> posterPayload, List<UserAction> actions,
            Instant createdAt) {
        this.sessionId = sessionId;
        this.userId = userId;
        this.challengeId = challengeId;
        this.finalReturn = finalReturn;
        this.maxDrawdown = maxDrawdown;
        this.score = score;
        this.percentile = percentile;
        this.posterPayload = Collections.unmodifiableMap(posterPayload);
        this.actions = Collections.unmodifiableList(actions);
        this.createdAt = createdAt;
    }

    public String getSessionId() {
        return sessionId;
    }

    public String getUserId() {
        return userId;
    }

    public String getChallengeId() {
        return challengeId;
    }

    public double getFinalReturn() {
        return finalReturn;
    }

    public double getMaxDrawdown() {
        return maxDrawdown;
    }

    public double getScore() {
        return score;
    }

    public double getPercentile() {
        return percentile;
    }

    public Map<String, Object> getPosterPayload() {
        return posterPayload;
    }

    public List<UserAction> getActions() {
        return actions;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
