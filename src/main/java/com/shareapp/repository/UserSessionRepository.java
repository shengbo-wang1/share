package com.shareapp.repository;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Repository;

import com.shareapp.domain.UserSession;

@Repository
public class UserSessionRepository {

    private final Map<String, UserSession> storage = new ConcurrentHashMap<String, UserSession>();

    public void save(UserSession session) {
        storage.put(session.getSessionId(), session);
    }

    public Optional<UserSession> findById(String sessionId) {
        return Optional.ofNullable(storage.get(sessionId));
    }
}
