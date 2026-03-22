package com.shareapp.domain;

import java.time.LocalDate;

public class StockDailyRaw {

    private final String code;
    private final LocalDate tradeDate;
    private final double open;
    private final double high;
    private final double low;
    private final double close;
    private final double volume;
    private final double amount;

    public StockDailyRaw(String code, LocalDate tradeDate, double open, double high, double low, double close,
            double volume, double amount) {
        this.code = code;
        this.tradeDate = tradeDate;
        this.open = open;
        this.high = high;
        this.low = low;
        this.close = close;
        this.volume = volume;
        this.amount = amount;
    }

    public String getCode() {
        return code;
    }

    public LocalDate getTradeDate() {
        return tradeDate;
    }

    public double getOpen() {
        return open;
    }

    public double getHigh() {
        return high;
    }

    public double getLow() {
        return low;
    }

    public double getClose() {
        return close;
    }

    public double getVolume() {
        return volume;
    }

    public double getAmount() {
        return amount;
    }
}
