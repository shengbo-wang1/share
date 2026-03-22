package com.shareapp.controller.dto;

import java.time.LocalDate;

public class ChallengeDayView {

    private LocalDate tradeDate;
    private OhlcView ohlc;
    private double volume;
    private MaView ma;
    private KdjView kdj;
    private MacdView macd;
    private String capBucket;

    public LocalDate getTradeDate() {
        return tradeDate;
    }

    public void setTradeDate(LocalDate tradeDate) {
        this.tradeDate = tradeDate;
    }

    public OhlcView getOhlc() {
        return ohlc;
    }

    public void setOhlc(OhlcView ohlc) {
        this.ohlc = ohlc;
    }

    public double getVolume() {
        return volume;
    }

    public void setVolume(double volume) {
        this.volume = volume;
    }

    public MaView getMa() {
        return ma;
    }

    public void setMa(MaView ma) {
        this.ma = ma;
    }

    public KdjView getKdj() {
        return kdj;
    }

    public void setKdj(KdjView kdj) {
        this.kdj = kdj;
    }

    public MacdView getMacd() {
        return macd;
    }

    public void setMacd(MacdView macd) {
        this.macd = macd;
    }

    public String getCapBucket() {
        return capBucket;
    }

    public void setCapBucket(String capBucket) {
        this.capBucket = capBucket;
    }

    public static class OhlcView {
        private double open;
        private double high;
        private double low;
        private double close;

        public double getOpen() {
            return open;
        }

        public void setOpen(double open) {
            this.open = open;
        }

        public double getHigh() {
            return high;
        }

        public void setHigh(double high) {
            this.high = high;
        }

        public double getLow() {
            return low;
        }

        public void setLow(double low) {
            this.low = low;
        }

        public double getClose() {
            return close;
        }

        public void setClose(double close) {
            this.close = close;
        }
    }

    public static class MaView {
        private double ma5;
        private double ma10;
        private double ma20;

        public double getMa5() {
            return ma5;
        }

        public void setMa5(double ma5) {
            this.ma5 = ma5;
        }

        public double getMa10() {
            return ma10;
        }

        public void setMa10(double ma10) {
            this.ma10 = ma10;
        }

        public double getMa20() {
            return ma20;
        }

        public void setMa20(double ma20) {
            this.ma20 = ma20;
        }
    }

    public static class KdjView {
        private double k;
        private double d;
        private double j;

        public double getK() {
            return k;
        }

        public void setK(double k) {
            this.k = k;
        }

        public double getD() {
            return d;
        }

        public void setD(double d) {
            this.d = d;
        }

        public double getJ() {
            return j;
        }

        public void setJ(double j) {
            this.j = j;
        }
    }

    public static class MacdView {
        private double dif;
        private double dea;
        private double macd;

        public double getDif() {
            return dif;
        }

        public void setDif(double dif) {
            this.dif = dif;
        }

        public double getDea() {
            return dea;
        }

        public void setDea(double dea) {
            this.dea = dea;
        }

        public double getMacd() {
            return macd;
        }

        public void setMacd(double macd) {
            this.macd = macd;
        }
    }
}
