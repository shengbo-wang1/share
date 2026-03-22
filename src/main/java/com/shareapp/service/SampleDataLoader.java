package com.shareapp.service;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import javax.annotation.PostConstruct;

import org.springframework.stereotype.Component;

import com.shareapp.domain.Challenge;
import com.shareapp.domain.ChallengeDay;
import com.shareapp.domain.MarketCapBucket;
import com.shareapp.repository.ChallengeRepository;
import com.shareapp.util.IndicatorUtils;

@Component
public class SampleDataLoader {

    private final ChallengeRepository challengeRepository;

    public SampleDataLoader(ChallengeRepository challengeRepository) {
        this.challengeRepository = challengeRepository;
    }

    @PostConstruct
    public void load() {
        if (!challengeRepository.findAll().isEmpty()) {
            return;
        }
        challengeRepository.save(buildChallenge("challenge-0001", "600519.SH", "历史样本A", LocalDate.of(2018, 6, 1),
                88.5D, 0.012D, MarketCapBucket.LARGE, Arrays.asList("趋势", "回撤控制"), true));
        challengeRepository.save(buildChallenge("challenge-0002", "300750.SZ", "历史样本B", LocalDate.of(2020, 9, 1),
                42.5D, 0.020D, MarketCapBucket.MID, Arrays.asList("震荡", "突破"), false));
        challengeRepository.save(buildChallenge("challenge-0003", "002594.SZ", "历史样本C", LocalDate.of(2021, 3, 15),
                65.0D, -0.006D, MarketCapBucket.SMALL, Arrays.asList("抄底", "高波动"), false));
    }

    private Challenge buildChallenge(String challengeId, String stockCode, String stockName, LocalDate startDate,
            double basePrice, double drift, MarketCapBucket bucket, List<String> tags, boolean featured) {
        int totalDays = 20;
        List<Double> rawOpenList = new ArrayList<Double>();
        List<Double> rawCloseList = new ArrayList<Double>();
        List<Double> qfqOpenList = new ArrayList<Double>();
        List<Double> qfqHighList = new ArrayList<Double>();
        List<Double> qfqLowList = new ArrayList<Double>();
        List<Double> qfqCloseList = new ArrayList<Double>();
        List<Double> volumes = new ArrayList<Double>();

        double close = basePrice;
        for (int i = 0; i < totalDays; i++) {
            double wave = Math.sin(i / 2.5D) * 0.018D + Math.cos(i / 4.2D) * 0.011D;
            double open = close * (1D + wave / 2D);
            close = open * (1D + drift + wave);
            double high = Math.max(open, close) * 1.018D;
            double low = Math.min(open, close) * 0.982D;
            double qfqFactor = 0.92D + i * 0.003D;
            rawOpenList.add(round(open));
            rawCloseList.add(round(close));
            qfqOpenList.add(round(open * qfqFactor));
            qfqHighList.add(round(high * qfqFactor));
            qfqLowList.add(round(low * qfqFactor));
            qfqCloseList.add(round(close * qfqFactor));
            volumes.add(round(1000000D + i * 56000D + Math.abs(wave) * 500000D));
        }

        List<Double> ma5 = IndicatorUtils.simpleMovingAverage(qfqCloseList, 5);
        List<Double> ma10 = IndicatorUtils.simpleMovingAverage(qfqCloseList, 10);
        List<Double> ma20 = IndicatorUtils.simpleMovingAverage(qfqCloseList, 20);
        List<double[]> kdj = IndicatorUtils.kdj(qfqHighList, qfqLowList, qfqCloseList, 9);
        List<double[]> macd = IndicatorUtils.macd(qfqCloseList, 12, 26, 9);

        List<ChallengeDay> days = new ArrayList<ChallengeDay>();
        for (int i = 0; i < totalDays; i++) {
            days.add(new ChallengeDay(startDate.plusDays(i), rawOpenList.get(i), rawCloseList.get(i), qfqOpenList.get(i),
                    qfqHighList.get(i), qfqLowList.get(i), qfqCloseList.get(i), volumes.get(i), ma5.get(i), ma10.get(i),
                    ma20.get(i), round(kdj.get(i)[0]), round(kdj.get(i)[1]), round(kdj.get(i)[2]),
                    round(macd.get(i)[0]), round(macd.get(i)[1]), round(macd.get(i)[2]), bucket));
        }

        return new Challenge(challengeId, stockCode, stockName, startDate, startDate.plusDays(totalDays - 1), totalDays,
                featured ? "normal" : "advanced", tags, featured, true, days);
    }

    private double round(double value) {
        return Math.round(value * 1000D) / 1000D;
    }
}
