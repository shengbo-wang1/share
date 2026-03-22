package com.shareapp.service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import com.shareapp.config.GameProperties;
import com.shareapp.controller.dto.ResultResponse;
import com.shareapp.controller.dto.StartSessionResponse;
import com.shareapp.controller.dto.SubmitSessionRequest;
import com.shareapp.controller.dto.SubmitSessionResponse;
import com.shareapp.domain.Challenge;
import com.shareapp.domain.SessionStatus;
import com.shareapp.domain.UserAction;
import com.shareapp.domain.UserResult;
import com.shareapp.domain.UserSession;
import com.shareapp.exception.ApiException;
import com.shareapp.repository.UserResultRepository;
import com.shareapp.repository.UserSessionRepository;

@Service
public class SessionService {

    private final ChallengeService challengeService;
    private final UserSessionRepository userSessionRepository;
    private final UserResultRepository userResultRepository;
    private final SettlementService settlementService;
    private final SignatureService signatureService;
    private final GameProperties gameProperties;

    public SessionService(ChallengeService challengeService, UserSessionRepository userSessionRepository,
            UserResultRepository userResultRepository, SettlementService settlementService,
            SignatureService signatureService, GameProperties gameProperties) {
        this.challengeService = challengeService;
        this.userSessionRepository = userSessionRepository;
        this.userResultRepository = userResultRepository;
        this.settlementService = settlementService;
        this.signatureService = signatureService;
        this.gameProperties = gameProperties;
    }

    public StartSessionResponse startSession(String userId, String challengeId) {
        Challenge challenge = challengeService.resolveChallenge(challengeId);
        String sessionId = UUID.randomUUID().toString();
        String signature = signatureService.sign(sessionId, challenge.getChallengeId(), userId);
        Instant startedAt = Instant.now();
        UserSession session = new UserSession(sessionId, userId, challenge.getChallengeId(), startedAt, signature,
                SessionStatus.STARTED);
        userSessionRepository.save(session);

        StartSessionResponse response = new StartSessionResponse();
        response.setSessionId(sessionId);
        response.setChallengeId(challenge.getChallengeId());
        response.setSignature(signature);
        response.setStartedAt(startedAt);
        response.setDifficulty(challenge.getDifficulty());
        response.setTags(challenge.getTags());
        response.setDays(challengeService.toDayViews(challenge));

        StartSessionResponse.RulesView rulesView = new StartSessionResponse.RulesView();
        rulesView.setTotalDays(challenge.getTotalDays());
        rulesView.setActionableDays(Math.max(0, challenge.getTotalDays() - 1));
        rulesView.setTargetPositions(Arrays.asList(0, 50, 100));
        rulesView.setInitialCash(gameProperties.getInitialCash());
        rulesView.setTradingCostRate(gameProperties.getTradingCostRate());
        rulesView.setExecutionTiming("next_open");
        rulesView.setScoreBasis("final_return_then_lower_drawdown");
        response.setRules(rulesView);
        return response;
    }

    public SubmitSessionResponse submit(SubmitSessionRequest request) {
        UserSession session = userSessionRepository.findById(request.getSessionId())
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Session not found"));
        validateSessionOwnership(session, request.getUserId(), request.getSignature());
        if (session.getStatus() == SessionStatus.SUBMITTED) {
            throw new ApiException(HttpStatus.CONFLICT, "Session already submitted");
        }

        Challenge challenge = challengeService.getChallenge(session.getChallengeId());
        SettlementService.SettlementSnapshot snapshot = settlementService.settle(session.getUserId(), session.getSessionId(), challenge,
                request.getActions());
        UserResult result = snapshot.getResult();
        session.replaceActions(snapshot.getAppliedActions());
        session.setSubmittedAt(Instant.now());
        session.setStatus(SessionStatus.SUBMITTED);

        userSessionRepository.save(session);
        userResultRepository.save(result);

        SubmitSessionResponse response = new SubmitSessionResponse();
        response.setSessionId(result.getSessionId());
        response.setFinalReturn(result.getFinalReturn());
        response.setMaxDrawdown(result.getMaxDrawdown());
        response.setScore(result.getScore());
        response.setPercentile(result.getPercentile());
        response.setStockCode(challenge.getStockCode());
        response.setStockName(challenge.getStockName());
        response.setActionSummary(buildActionSummary(snapshot.getAppliedActions()));
        return response;
    }

    public ResultResponse getResult(String sessionId) {
        UserResult result = userResultRepository.findBySessionId(sessionId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Result not found"));
        Challenge challenge = challengeService.getChallenge(result.getChallengeId());
        ResultResponse response = new ResultResponse();
        response.setSessionId(result.getSessionId());
        response.setChallengeId(result.getChallengeId());
        response.setStockCode(challenge.getStockCode());
        response.setStockName(challenge.getStockName());
        response.setFinalReturn(result.getFinalReturn());
        response.setMaxDrawdown(result.getMaxDrawdown());
        response.setScore(result.getScore());
        response.setPercentile(result.getPercentile());
        response.setActionSummary(buildActionSummary(result.getActions()));
        response.setPosterPayload(result.getPosterPayload());
        return response;
    }

    private void validateSessionOwnership(UserSession session, String userId, String signature) {
        if (!session.getUserId().equals(userId)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Session does not belong to user");
        }
        if (!session.getSignature().equals(signature)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Invalid session signature");
        }
        String expectedSignature = signatureService.sign(session.getSessionId(), session.getChallengeId(), userId);
        if (!expectedSignature.equals(signature)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Signature verification failed");
        }
    }

    private List<Map<String, Object>> buildActionSummary(List<UserAction> actions) {
        List<Map<String, Object>> summary = new ArrayList<Map<String, Object>>();
        for (UserAction action : actions) {
            Map<String, Object> item = new LinkedHashMap<String, Object>();
            item.put("tradeDate", action.getTradeDate());
            item.put("targetPosition", action.getTargetPosition());
            item.put("effectivePrice", action.getEffectivePrice());
            summary.add(item);
        }
        return summary;
    }
}
