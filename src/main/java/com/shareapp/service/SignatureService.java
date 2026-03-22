package com.shareapp.service;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.stereotype.Service;

import com.shareapp.config.GameProperties;

@Service
public class SignatureService {

    private static final String HMAC_SHA_256 = "HmacSHA256";

    private final GameProperties gameProperties;

    public SignatureService(GameProperties gameProperties) {
        this.gameProperties = gameProperties;
    }

    public String sign(String sessionId, String challengeId, String userId) {
        String payload = sessionId + "|" + challengeId + "|" + userId;
        try {
            Mac mac = Mac.getInstance(HMAC_SHA_256);
            mac.init(new SecretKeySpec(gameProperties.getSigningSecret().getBytes(StandardCharsets.UTF_8), HMAC_SHA_256));
            byte[] signed = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(signed);
        } catch (Exception exception) {
            throw new IllegalStateException("Failed to sign session payload", exception);
        }
    }
}
