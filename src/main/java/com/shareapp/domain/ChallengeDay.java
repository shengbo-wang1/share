package com.shareapp.domain;

import java.time.LocalDate;

public class ChallengeDay {

    private final LocalDate tradeDate;
    private final double rawOpen;
    private final double rawClose;
    private final double qfqOpen;
    private final double qfqHigh;
    private final double qfqLow;
    private final double qfqClose;
    private final double volume;
    private final double ma5;
    private final double ma10;
    private final double ma20;
    private final double k;
    private final double d;
    private final double j;
    private final double dif;
    private final double dea;
    private final double macd;
    private final MarketCapBucket capBucket;

    public ChallengeDay(LocalDate tradeDate, double rawOpen, double rawClose, double qfqOpen, double qfqHigh,
            double qfqLow, double qfqClose, double volume, double ma5, double ma10, double ma20, double k, double d,
            double j, double dif, double dea, double macd, MarketCapBucket capBucket) {
        this.tradeDate = tradeDate;
        this.rawOpen = rawOpen;
        this.rawClose = rawClose;
        this.qfqOpen = qfqOpen;
        this.qfqHigh = qfqHigh;
        this.qfqLow = qfqLow;
        this.qfqClose = qfqClose;
        this.volume = volume;
        this.ma5 = ma5;
        this.ma10 = ma10;
        this.ma20 = ma20;
        this.k = k;
        this.d = d;
        this.j = j;
        this.dif = dif;
        this.dea = dea;
        this.macd = macd;
        this.capBucket = capBucket;
    }

    public LocalDate getTradeDate() {
        return tradeDate;
    }

    public double getRawOpen() {
        return rawOpen;
    }

    public double getRawClose() {
        return rawClose;
    }

    public double getQfqOpen() {
        return qfqOpen;
    }

    public double getQfqHigh() {
        return qfqHigh;
    }

    public double getQfqLow() {
        return qfqLow;
    }

    public double getQfqClose() {
        return qfqClose;
    }

    public double getVolume() {
        return volume;
    }

    public double getMa5() {
        return ma5;
    }

    public double getMa10() {
        return ma10;
    }

    public double getMa20() {
        return ma20;
    }

    public double getK() {
        return k;
    }

    public double getD() {
        return d;
    }

    public double getJ() {
        return j;
    }

    public double getDif() {
        return dif;
    }

    public double getDea() {
        return dea;
    }

    public double getMacd() {
        return macd;
    }

    public MarketCapBucket getCapBucket() {
        return capBucket;
    }
}
