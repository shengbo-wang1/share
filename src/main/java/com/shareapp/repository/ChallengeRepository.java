package com.shareapp.repository;

import java.util.Collection;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Repository;

import com.shareapp.domain.Challenge;

@Repository
public class ChallengeRepository {

    private final Map<String, Challenge> storage = new ConcurrentHashMap<String, Challenge>();

    public void save(Challenge challenge) {
        storage.put(challenge.getChallengeId(), challenge);
    }

    public Optional<Challenge> findById(String challengeId) {
        return Optional.ofNullable(storage.get(challengeId));
    }

    public Collection<Challenge> findAll() {
        return storage.values();
    }
}
