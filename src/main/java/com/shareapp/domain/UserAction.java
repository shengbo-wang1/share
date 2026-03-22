package com.shareapp.domain;

import java.time.LocalDate;

public class UserAction {

    private final LocalDate tradeDate;
    private final int targetPosition;
    private final double effectivePrice;

    public UserAction(LocalDate tradeDate, int targetPosition, double effectivePrice) {
        this.tradeDate = tradeDate;
        this.targetPosition = targetPosition;
        this.effectivePrice = effectivePrice;
    }

    public LocalDate getTradeDate() {
        return tradeDate;
    }

    public int getTargetPosition() {
        return targetPosition;
    }

    public double getEffectivePrice() {
        return effectivePrice;
    }
}
