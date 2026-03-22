package com.shareapp.repository;

import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

import org.springframework.stereotype.Repository;

import com.shareapp.domain.UserResult;

@Repository
public class UserResultRepository {

    private final Map<String, UserResult> storage = new ConcurrentHashMap<String, UserResult>();

    public void save(UserResult result) {
        storage.put(result.getSessionId(), result);
    }

    public Optional<UserResult> findBySessionId(String sessionId) {
        return Optional.ofNullable(storage.get(sessionId));
    }

    public List<UserResult> findByChallengeId(String challengeId) {
        return storage.values().stream()
                .filter(result -> result.getChallengeId().equals(challengeId))
                .sorted(scoreComparator())
                .collect(Collectors.toList());
    }

    public List<UserResult> findByBoardDate(LocalDate boardDate) {
        List<UserResult> results = new ArrayList<UserResult>();
        for (UserResult result : storage.values()) {
            LocalDate createdDate = result.getCreatedAt().atZone(ZoneOffset.UTC).toLocalDate();
            if (boardDate.equals(createdDate)) {
                results.add(result);
            }
        }
        results.sort(scoreComparator());
        return results;
    }

    private Comparator<UserResult> scoreComparator() {
        return Comparator.comparingDouble(UserResult::getScore).reversed()
                .thenComparingDouble(UserResult::getMaxDrawdown)
                .thenComparing(UserResult::getCreatedAt);
    }
}
