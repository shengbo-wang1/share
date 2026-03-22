package com.shareapp.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "game")
public class GameProperties {

    private double initialCash = 100000.0D;
    private double tradingCostRate = 0.0015D;
    private String signingSecret = "change-this-secret";

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

    public String getSigningSecret() {
        return signingSecret;
    }

    public void setSigningSecret(String signingSecret) {
        this.signingSecret = signingSecret;
    }
}
