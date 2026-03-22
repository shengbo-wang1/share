package com.shareapp.controller.dto;

import javax.validation.constraints.NotBlank;

public class StartSessionRequest {

    @NotBlank
    private String userId;

    private String challengeId;

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getChallengeId() {
        return challengeId;
    }

    public void setChallengeId(String challengeId) {
        this.challengeId = challengeId;
    }
}
