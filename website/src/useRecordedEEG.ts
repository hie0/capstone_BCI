import { useEffect } from "react";
import { useBCI } from "./store";
import {
  apiUrl,
  eegSocketUrl,
  type BackendSession,
  type BackendPrediction,
} from "./data/backend";

export function useRecordedEEG(controlDevices: boolean) {
  const {
    inputMode,
    participantId,
    sessionId,
    channelMode,
    recordedLowChannel,
    ttaEnabled,
    isPlaying,
  } = useBCI();
  useEffect(() => {
    if (inputMode !== "recorded") return;
    const controller = new AbortController();
    useBCI.getState().setBackend({
      backendStatus: "연결 중",
      backendError: null,
      backendSessions: [],
    });
    fetch(apiUrl(`/api/sessions?participant_id=${participantId}`), {
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw new Error("Backend 세션 조회 실패");
        return r.json() as Promise<{ sessions: BackendSession[] }>;
      })
      .then(({ sessions }) => {
        if (controller.signal.aborted) return;
        if (!sessions.length)
          throw new Error("연결 가능한 로컬 EEG 세션이 없습니다.");
        const s = useBCI.getState();
        s.setBackend({
          backendSessions: sessions,
          backendStatus: "실제 EEG 연결됨",
        });
        if (!sessions.some((x) => x.session_id === s.sessionId))
          s.setSettings({ sessionId: sessions[0].session_id });
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          useBCI.getState().setBackend({
            backendStatus: "연결 실패",
            backendError: String(e.message),
          });
      });
    return () => controller.abort();
  }, [inputMode, participantId]);

  useEffect(() => {
    if (inputMode !== "recorded" || !isPlaying) return;
    const s = useBCI.getState();
    const session = s.backendSessions.find((x) => x.session_id === sessionId);
    if (!session) {
      s.stop();
      return;
    }
    let closed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const socket = new WebSocket(eegSocketUrl());
    const fail = (message: string) => {
      if (closed) return;
      useBCI
        .getState()
        .setBackend({ backendStatus: "연결 실패", backendError: message });
      useBCI.getState().stop();
    };
    const next = () => {
      const current = useBCI.getState();
      if (closed || !current.isPlaying || socket.readyState !== WebSocket.OPEN)
        return;
      if (current.recordedCursor >= session.n_online_trials) {
        current.setBackend({ backendStatus: "세션 재생 완료" });
        current.stop();
        return;
      }
      socket.send(
        JSON.stringify({
          action: "step_trial",
          trial_index: current.recordedCursor,
          include_waveform: true,
        }),
      );
    };
    socket.onmessage = (event) => {
      if (closed) return;
      const state = useBCI.getState();
      if (
        !state.isPlaying ||
        state.participantId !== participantId ||
        state.sessionId !== sessionId ||
        state.channelMode !== channelMode ||
        state.recordedLowChannel !== recordedLowChannel ||
        state.ttaEnabled !== ttaEnabled
      )
        return;
      try {
        const message = JSON.parse(event.data);
        if (message.type === "connected")
          socket.send(
            JSON.stringify({
              action: "set_config",
              participant_id: participantId,
              session_id: sessionId,
              channel_mode: recordedLowChannel ? "low" : channelMode,
              tta_enabled: ttaEnabled,
            }),
          );
        else if (message.type === "config_ack") next();
        else if (message.type === "trial_prediction") {
          const prediction = message.prediction as BackendPrediction;
          if (
            prediction.session_id !== sessionId ||
            prediction.participant_id !== participantId
          )
            throw new Error("EEG 세션 응답 불일치");
          useBCI.getState().receivePrediction(prediction, controlDevices);
          timer = setTimeout(next, 2000 / useBCI.getState().speed);
        } else if (message.type === "error")
          fail(message.detail ?? "추론 실패");
      } catch (e) {
        fail(e instanceof Error ? e.message : "응답 해석 실패");
      }
    };
    socket.onerror = () =>
      fail(
        "EEG Backend에 연결할 수 없습니다. 로컬 서버 실행 상태를 확인하세요.",
      );
    socket.onclose = () => {
      if (!closed && useBCI.getState().isPlaying)
        fail("EEG 연결이 종료되었습니다.");
    };
    return () => {
      closed = true;
      clearTimeout(timer);
      socket.close();
    };
  }, [
    inputMode,
    participantId,
    sessionId,
    channelMode,
    recordedLowChannel,
    ttaEnabled,
    isPlaying,
    controlDevices,
  ]);
}
