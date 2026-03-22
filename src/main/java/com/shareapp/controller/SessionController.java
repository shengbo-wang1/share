package com.shareapp.controller;

import javax.validation.Valid;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.shareapp.controller.dto.ResultResponse;
import com.shareapp.controller.dto.StartSessionRequest;
import com.shareapp.controller.dto.StartSessionResponse;
import com.shareapp.controller.dto.SubmitSessionRequest;
import com.shareapp.controller.dto.SubmitSessionResponse;
import com.shareapp.service.SessionService;

@RestController
@RequestMapping("/api/session")
public class SessionController {

    private final SessionService sessionService;

    public SessionController(SessionService sessionService) {
        this.sessionService = sessionService;
    }

    @PostMapping("/start")
    public StartSessionResponse start(@Valid @RequestBody StartSessionRequest request) {
        return sessionService.startSession(request.getUserId(), request.getChallengeId());
    }

    @PostMapping("/submit")
    public SubmitSessionResponse submit(@Valid @RequestBody SubmitSessionRequest request) {
        return sessionService.submit(request);
    }

    @GetMapping("/result/{sessionId}")
    public ResultResponse result(@PathVariable String sessionId) {
        return sessionService.getResult(sessionId);
    }
}
