package com.shareapp.util;

import java.util.ArrayList;
import java.util.List;

public final class IndicatorUtils {

    private IndicatorUtils() {
    }

    public static List<Double> simpleMovingAverage(List<Double> values, int period) {
        List<Double> result = new ArrayList<Double>(values.size());
        double sum = 0D;
        for (int i = 0; i < values.size(); i++) {
            sum += values.get(i);
            if (i >= period) {
                sum -= values.get(i - period);
            }
            int denominator = Math.min(i + 1, period);
            result.add(sum / denominator);
        }
        return result;
    }

    public static List<double[]> kdj(List<Double> highs, List<Double> lows, List<Double> closes, int period) {
        List<double[]> result = new ArrayList<double[]>(closes.size());
        double k = 50D;
        double d = 50D;
        for (int i = 0; i < closes.size(); i++) {
            double highest = highs.get(i);
            double lowest = lows.get(i);
            for (int j = Math.max(0, i - period + 1); j <= i; j++) {
                highest = Math.max(highest, highs.get(j));
                lowest = Math.min(lowest, lows.get(j));
            }
            double rsv = highest == lowest ? 50D : (closes.get(i) - lowest) / (highest - lowest) * 100D;
            k = (2D / 3D) * k + (1D / 3D) * rsv;
            d = (2D / 3D) * d + (1D / 3D) * k;
            double j = 3D * k - 2D * d;
            result.add(new double[] { k, d, j });
        }
        return result;
    }

    public static List<double[]> macd(List<Double> closes, int shortPeriod, int longPeriod, int signalPeriod) {
        List<double[]> result = new ArrayList<double[]>(closes.size());
        double emaShort = closes.get(0);
        double emaLong = closes.get(0);
        double dea = 0D;
        double shortFactor = 2D / (shortPeriod + 1D);
        double longFactor = 2D / (longPeriod + 1D);
        double signalFactor = 2D / (signalPeriod + 1D);
        for (Double close : closes) {
            emaShort = close * shortFactor + emaShort * (1 - shortFactor);
            emaLong = close * longFactor + emaLong * (1 - longFactor);
            double dif = emaShort - emaLong;
            dea = dif * signalFactor + dea * (1 - signalFactor);
            double macd = (dif - dea) * 2D;
            result.add(new double[] { dif, dea, macd });
        }
        return result;
    }
}
