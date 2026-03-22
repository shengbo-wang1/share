package com.shareapp.service;

import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import com.shareapp.config.GameProperties;
import com.shareapp.controller.dto.SubmitSessionRequest;
import com.shareapp.domain.Challenge;
import com.shareapp.domain.ChallengeDay;
import com.shareapp.domain.UserAction;
import com.shareapp.domain.UserResult;
import com.shareapp.exception.ApiException;
import com.shareapp.repository.UserResultRepository;

@Service
public class SettlementService {

    private static final Set<Integer> ALLOWED_POSITIONS = Collections.unmodifiableSet(new HashSet<Integer>(Arrays.asList(0, 50, 100)));

    private final GameProperties gameProperties;
    private final UserResultRepository userResultRepository;

    public SettlementService(GameProperties gameProperties, UserResultRepository userResultRepository) {
        this.gameProperties = gameProperties;
        this.userResultRepository = userResultRepository;
    }

    public SettlementSnapshot settle(String userId, String sessionId, Challenge challenge,
            List<SubmitSessionRequest.ActionItem> requestActions) {
        List<ChallengeDay> days = challenge.getDays();
        if (days.size() < 2) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Challenge must contain at least 2 trading days");
        }

        List<SubmitSessionRequest.ActionItem> normalizedActions = normalizeActions(days, requestActions);
        Map<LocalDate, Integer> targetPositions = normalizedActions.stream()
                .collect(Collectors.toMap(SubmitSessionRequest.ActionItem::getTradeDate,
                        SubmitSessionRequest.ActionItem::getTargetPosition,
                        (left, right) -> right,
                        LinkedHashMap::new));

        double cash = gameProperties.getInitialCash();
        double shares = 0D;
        double peakValue = cash;
        double maxDrawdown = 0D;
        double previousPosition = 0D;
        List<UserAction> appliedActions = new ArrayList<UserAction>();
        List<Double> curve = new ArrayList<Double>();
        curve.add(cash);

        for (int i = 0; i < days.size() - 1; i++) {
            ChallengeDay currentDay = days.get(i);
            ChallengeDay nextDay = days.get(i + 1);
            Integer targetPosition = targetPositions.get(currentDay.getTradeDate());
            if (targetPosition != null && targetPosition.intValue() != (int) previousPosition) {
                double portfolioBeforeTrade = cash + shares * nextDay.getRawOpen();
                double targetRatio = targetPosition / 100D;
                double tradeAmount = Math.abs(targetRatio - previousPosition / 100D) * portfolioBeforeTrade;
                double tradingCost = tradeAmount * gameProperties.getTradingCostRate();
                double netPortfolio = portfolioBeforeTrade - tradingCost;
                double targetValue = netPortfolio * targetRatio;
                shares = targetValue / nextDay.getRawOpen();
                cash = netPortfolio - targetValue;
                previousPosition = targetPosition;
                appliedActions.add(new UserAction(currentDay.getTradeDate(), targetPosition, nextDay.getRawOpen()));
            }
            double endOfDayValue = cash + shares * nextDay.getRawClose();
            curve.add(endOfDayValue);
            if (endOfDayValue > peakValue) {
                peakValue = endOfDayValue;
            }
            double drawdown = peakValue == 0D ? 0D : (peakValue - endOfDayValue) / peakValue;
            if (drawdown > maxDrawdown) {
                maxDrawdown = drawdown;
            }
        }

        double finalPortfolioValue = curve.get(curve.size() - 1);
        double finalReturn = finalPortfolioValue / gameProperties.getInitialCash() - 1D;
        double score = finalReturn;
        double percentile = calculatePercentile(challenge.getChallengeId(), score, maxDrawdown);

        Map<String, Object> posterPayload = new LinkedHashMap<String, Object>();
        posterPayload.put("headline", buildHeadline(finalReturn, percentile));
        posterPayload.put("scoreLabel", formatPercent(finalReturn));
        posterPayload.put("drawdownLabel", formatPercent(maxDrawdown));
        posterPayload.put("stockName", challenge.getStockName());
        posterPayload.put("stockCode", challenge.getStockCode());
        posterPayload.put("percentileLabel", String.format("击败 %.0f%% 用户", percentile * 100D));

        return new SettlementSnapshot(new UserResult(sessionId, userId, challenge.getChallengeId(), finalReturn,
                maxDrawdown, score, percentile, posterPayload, appliedActions, Instant.now()), appliedActions, curve);
    }

    private String buildHeadline(double finalReturn, double percentile) {
        if (finalReturn >= 0.2D) {
            return "这段历史行情里，你的节奏感非常强";
        }
        if (percentile >= 0.8D) {
            return "这局你跑赢了大多数挑战者";
        }
        if (finalReturn >= 0D) {
            return "稳住回撤，继续优化进出场纪律";
        }
        return "再来一局，看看能否少踩一次追涨杀跌";
    }

    private List<SubmitSessionRequest.ActionItem> normalizeActions(List<ChallengeDay> days,
            List<SubmitSessionRequest.ActionItem> requestActions) {
        if (requestActions == null || requestActions.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "At least one action is required");
        }

        Set<LocalDate> legalDates = days.stream().limit(days.size() - 1).map(ChallengeDay::getTradeDate)
                .collect(Collectors.toSet());
        Map<LocalDate, SubmitSessionRequest.ActionItem> deduplicated = new HashMap<LocalDate, SubmitSessionRequest.ActionItem>();
        for (SubmitSessionRequest.ActionItem action : requestActions) {
            if (action.getTradeDate() == null || !legalDates.contains(action.getTradeDate())) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "Action trade date is outside the challenge range");
            }
            if (!ALLOWED_POSITIONS.contains(action.getTargetPosition())) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "Target position must be one of 0, 50, 100");
            }
            if (deduplicated.containsKey(action.getTradeDate())) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "Duplicate action trade date is not allowed");
            }
            deduplicated.put(action.getTradeDate(), action);
        }

        List<SubmitSessionRequest.ActionItem> normalized = new ArrayList<SubmitSessionRequest.ActionItem>(deduplicated.values());
        normalized.sort(Comparator.comparing(SubmitSessionRequest.ActionItem::getTradeDate));
        return normalized;
    }

    private double calculatePercentile(String challengeId, double score, double maxDrawdown) {
        List<UserResult> historicalResults = userResultRepository.findByChallengeId(challengeId);
        if (historicalResults.isEmpty()) {
            return 1D;
        }
        int beaten = 0;
        for (UserResult historical : historicalResults) {
            if (score > historical.getScore()) {
                beaten++;
            } else if (Double.compare(score, historical.getScore()) == 0
                    && maxDrawdown < historical.getMaxDrawdown()) {
                beaten++;
            }
        }
        return (beaten + 1D) / (historicalResults.size() + 1D);
    }

    private String formatPercent(double value) {
        return String.format("%.2f%%", value * 100D);
    }

    public static class SettlementSnapshot {
        private final UserResult result;
        private final List<UserAction> appliedActions;
        private final List<Double> equityCurve;

        public SettlementSnapshot(UserResult result, List<UserAction> appliedActions, List<Double> equityCurve) {
            this.result = result;
            this.appliedActions = appliedActions;
            this.equityCurve = equityCurve;
        }

        public UserResult getResult() {
            return result;
        }

        public List<UserAction> getAppliedActions() {
            return appliedActions;
        }

        public List<Double> getEquityCurve() {
            return equityCurve;
        }
    }
}
