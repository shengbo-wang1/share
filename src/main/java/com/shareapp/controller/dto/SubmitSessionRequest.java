package com.shareapp.controller.dto;

import java.time.LocalDate;
import java.util.List;

import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotEmpty;
import javax.validation.constraints.NotNull;

public class SubmitSessionRequest {

    @NotBlank
    private String sessionId;

    @NotBlank
    private String userId;

    @NotBlank
    private String signature;

    @Valid
    @NotEmpty
    private List<ActionItem> actions;

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getSignature() {
        return signature;
    }

    public void setSignature(String signature) {
        this.signature = signature;
    }

    public List<ActionItem> getActions() {
        return actions;
    }

    public void setActions(List<ActionItem> actions) {
        this.actions = actions;
    }

    public static class ActionItem {

        @NotNull
        private LocalDate tradeDate;

        @NotNull
        private Integer targetPosition;

        public LocalDate getTradeDate() {
            return tradeDate;
        }

        public void setTradeDate(LocalDate tradeDate) {
            this.tradeDate = tradeDate;
        }

        public Integer getTargetPosition() {
            return targetPosition;
        }

        public void setTargetPosition(Integer targetPosition) {
            this.targetPosition = targetPosition;
        }
    }
}
