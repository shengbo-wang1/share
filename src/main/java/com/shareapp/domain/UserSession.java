package com.shareapp.domain;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UserSession {

    private final String sessionId;
    private final String userId;
    private final String challengeId;
    private final Instant startedAt;
    private final String signature;
    private SessionStatus status;
    private Instant submittedAt;
    private final List<UserAction> actions = new ArrayList<UserAction>();

    public UserSession(String sessionId, String userId, String challengeId, Instant startedAt, String signature,
            SessionStatus status) {
        this.sessionId = sessionId;
        this.userId = userId;
        this.challengeId = challengeId;
        this.startedAt = startedAt;
        this.signature = signature;
        this.status = status;
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

    public Instant getStartedAt() {
        return startedAt;
    }

    public String getSignature() {
        return signature;
    }

    public SessionStatus getStatus() {
        return status;
    }

    public void setStatus(SessionStatus status) {
        this.status = status;
    }

    public Instant getSubmittedAt() {
        return submittedAt;
    }

    public void setSubmittedAt(Instant submittedAt) {
        this.submittedAt = submittedAt;
    }

    public void replaceActions(List<UserAction> newActions) {
        this.actions.clear();
        this.actions.addAll(newActions);
    }

    public List<UserAction> getActions() {
        return Collections.unmodifiableList(actions);
    }
}
