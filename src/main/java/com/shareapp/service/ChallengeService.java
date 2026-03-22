package com.shareapp.service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

import com.shareapp.controller.dto.ChallengeDayView;
import com.shareapp.domain.Challenge;
import com.shareapp.domain.ChallengeDay;
import com.shareapp.exception.ApiException;
import com.shareapp.repository.ChallengeRepository;

import org.springframework.http.HttpStatus;

@Service
public class ChallengeService {

    private final ChallengeRepository challengeRepository;

    public ChallengeService(ChallengeRepository challengeRepository) {
        this.challengeRepository = challengeRepository;
    }

    public Challenge resolveChallenge(String requestedChallengeId) {
        if (requestedChallengeId != null && !requestedChallengeId.trim().isEmpty()) {
            return challengeRepository.findById(requestedChallengeId)
                    .filter(Challenge::isActive)
                    .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Challenge not found"));
        }
        Optional<Challenge> featured = challengeRepository.findAll().stream()
                .filter(Challenge::isActive)
                .sorted(Comparator.comparing(Challenge::isFeatured).reversed().thenComparing(Challenge::getChallengeId))
                .findFirst();
        return featured.orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "No active challenge configured"));
    }

    public Challenge getChallenge(String challengeId) {
        return challengeRepository.findById(challengeId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Challenge not found"));
    }

    public List<ChallengeDayView> toDayViews(Challenge challenge) {
        List<ChallengeDayView> views = new ArrayList<ChallengeDayView>();
        for (ChallengeDay day : challenge.getDays()) {
            ChallengeDayView view = new ChallengeDayView();
            view.setTradeDate(day.getTradeDate());
            ChallengeDayView.OhlcView ohlcView = new ChallengeDayView.OhlcView();
            ohlcView.setOpen(day.getQfqOpen());
            ohlcView.setHigh(day.getQfqHigh());
            ohlcView.setLow(day.getQfqLow());
            ohlcView.setClose(day.getQfqClose());
            view.setOhlc(ohlcView);
            view.setVolume(day.getVolume());

            ChallengeDayView.MaView maView = new ChallengeDayView.MaView();
            maView.setMa5(day.getMa5());
            maView.setMa10(day.getMa10());
            maView.setMa20(day.getMa20());
            view.setMa(maView);

            ChallengeDayView.KdjView kdjView = new ChallengeDayView.KdjView();
            kdjView.setK(day.getK());
            kdjView.setD(day.getD());
            kdjView.setJ(day.getJ());
            view.setKdj(kdjView);

            ChallengeDayView.MacdView macdView = new ChallengeDayView.MacdView();
            macdView.setDif(day.getDif());
            macdView.setDea(day.getDea());
            macdView.setMacd(day.getMacd());
            view.setMacd(macdView);
            view.setCapBucket(day.getCapBucket().name().toLowerCase());
            views.add(view);
        }
        return views;
    }

    public List<java.time.LocalDate> actionableTradeDates(Challenge challenge) {
        return challenge.getDays().stream()
                .limit(Math.max(0, challenge.getDays().size() - 1))
                .map(ChallengeDay::getTradeDate)
                .collect(Collectors.toList());
    }
}
