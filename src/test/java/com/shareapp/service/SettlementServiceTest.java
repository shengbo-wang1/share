package com.shareapp.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.shareapp.config.GameProperties;
import com.shareapp.controller.dto.SubmitSessionRequest;
import com.shareapp.domain.Challenge;
import com.shareapp.domain.ChallengeDay;
import com.shareapp.domain.MarketCapBucket;
import com.shareapp.repository.UserResultRepository;

class SettlementServiceTest {

    private SettlementService settlementService;

    @BeforeEach
    void setUp() {
        GameProperties properties = new GameProperties();
        properties.setInitialCash(100000D);
        properties.setTradingCostRate(0.0015D);
        settlementService = new SettlementService(properties, new UserResultRepository());
    }

    @Test
    void shouldExecuteOnNextOpenAndMarkToLastClose() {
        Challenge challenge = new Challenge("c1", "000001.SZ", "测试股", LocalDate.of(2024, 1, 1),
                LocalDate.of(2024, 1, 3), 3, "normal", Collections.singletonList("趋势"), true, true,
                Arrays.asList(
                        day(LocalDate.of(2024, 1, 1), 10D, 10D),
                        day(LocalDate.of(2024, 1, 2), 11D, 12D),
                        day(LocalDate.of(2024, 1, 3), 13D, 15D)));

        SubmitSessionRequest.ActionItem openToFull = new SubmitSessionRequest.ActionItem();
        openToFull.setTradeDate(LocalDate.of(2024, 1, 1));
        openToFull.setTargetPosition(100);

        SettlementService.SettlementSnapshot snapshot = settlementService.settle("u1", "s1", challenge,
                Collections.singletonList(openToFull));

        double expectedReturn = ((100000D * (1 - 0.0015D) / 11D) * 15D) / 100000D - 1D;
        assertEquals(expectedReturn, snapshot.getResult().getFinalReturn(), 0.0001D);
        assertEquals(11D, snapshot.getAppliedActions().get(0).getEffectivePrice(), 0.0001D);
        assertTrue(snapshot.getResult().getMaxDrawdown() >= 0D);
    }

    @Test
    void shouldChargeTradingCostOnPositionChanges() {
        Challenge challenge = new Challenge("c2", "000002.SZ", "测试股2", LocalDate.of(2024, 2, 1),
                LocalDate.of(2024, 2, 4), 4, "normal", Collections.singletonList("震荡"), true, true,
                Arrays.asList(
                        day(LocalDate.of(2024, 2, 1), 10D, 10D),
                        day(LocalDate.of(2024, 2, 2), 10D, 10D),
                        day(LocalDate.of(2024, 2, 3), 10D, 10D),
                        day(LocalDate.of(2024, 2, 4), 10D, 10D)));

        SubmitSessionRequest.ActionItem buyHalf = new SubmitSessionRequest.ActionItem();
        buyHalf.setTradeDate(LocalDate.of(2024, 2, 1));
        buyHalf.setTargetPosition(50);
        SubmitSessionRequest.ActionItem buyFull = new SubmitSessionRequest.ActionItem();
        buyFull.setTradeDate(LocalDate.of(2024, 2, 2));
        buyFull.setTargetPosition(100);
        SubmitSessionRequest.ActionItem sellFlat = new SubmitSessionRequest.ActionItem();
        sellFlat.setTradeDate(LocalDate.of(2024, 2, 3));
        sellFlat.setTargetPosition(0);

        SettlementService.SettlementSnapshot snapshot = settlementService.settle("u1", "s2", challenge,
                Arrays.asList(buyHalf, buyFull, sellFlat));

        assertEquals(3, snapshot.getAppliedActions().size());
        assertTrue(snapshot.getResult().getFinalReturn() < 0D);
        assertFalse(snapshot.getEquityCurve().isEmpty());
    }

    private ChallengeDay day(LocalDate tradeDate, double rawOpen, double rawClose) {
        return new ChallengeDay(tradeDate, rawOpen, rawClose, rawOpen, rawOpen, rawOpen, rawClose, 1000D,
                rawClose, rawClose, rawClose, 50D, 50D, 50D, 0.1D, 0.1D, 0.0D, MarketCapBucket.MID);
    }
}
