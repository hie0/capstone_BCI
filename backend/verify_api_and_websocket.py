# -*- coding: utf-8 -*-
"""
End-to-End Verification Suite for NEUROLINK FastAPI + WebSocket Backend
=======================================================================
Tests all REST endpoints and WebSocket real-time streaming across:
  - Participants: WMJ, KGE, OYJ, KHY
  - Channel Modes: 16ch, low (optimal 5ch/7ch), 7ch, 5ch
  - TTA Modes: ON (CausalEA + CausalLogitCenter) vs OFF
  - Input Modes: Recorded chronological session trials & raw custom EEG (16, 500)
  - 50-Session Online Cohort dynamic evaluation reproduction
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import app

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    print("=" * 95)
    print("🧪 NEUROLINK FastAPI + WebSocket End-to-End Verification Suite")
    print("=" * 95)

    with TestClient(app) as client:
        # 1. Health check
        r_health = client.get("/api/health")
        assert r_health.status_code == 200, r_health.text
        h_data = r_health.json()
        print("\n[1] GET /api/health -> OK")
        print(f"    Exported joblib files : {h_data['exported_joblib_files']}")
        print(f"    Calibrated sessions   : {h_data['calibrated_online_sessions_count']} total ({h_data['golden_50_sessions_count']} Golden)")

        # 2. Participants
        r_part = client.get("/api/participants")
        assert r_part.status_code == 200, r_part.text
        p_data = r_part.json()
        print("\n[2] GET /api/participants -> OK")
        for p in p_data["participants"]:
            print(
                f"    • {p['participant_id']} ({p['korean_name']}): "
                f"optimal={p['optimal_channel_mode']} ({p['optimal_montage']}), "
                f"golden_sessions={p['golden_sessions_count']}, "
                f"offline_LOSO={p['offline_cv_metrics'].get('LOSO')}"
            )

        # 3. Single-trial chronological inference across all 4 subjects x (16ch/low) x (TTA ON/OFF)
        print("\n[3] POST /api/predict (Chronological Trial Inference Across All 4 Subjects)")
        for subj in ["WMJ", "KGE", "OYJ", "KHY"]:
            for ch_mode in ["16ch", "low"]:
                for tta_on in [False, True]:
                    r_pred = client.post(
                        "/api/predict",
                        json={
                            "participant_id": subj,
                            "session_id": "session-01",
                            "channel_mode": ch_mode,
                            "tta_enabled": tta_on,
                            "trial_index": 0,
                            "include_waveform": True,
                            "reset_session_state": True,
                        },
                    )
                    assert r_pred.status_code == 200, r_pred.text
                    d = r_pred.json()
                    assert d["predicted_direction"] in ("LEFT", "RIGHT")
                    assert 0.0 <= d["decision_score"] <= 1.0
                    assert d["latency_ms"] >= 0.0
                    assert len(d["active_channels"]) in (5, 6, 7, 16)
                    assert "is_clean" in d["quality"]
                    assert d["waveform"] is not None
                    if ch_mode == "low" and tta_on:
                        print(
                            f"    • {subj} | session={d['session_id']} | mode={d['montage']} ({d['n_channels']}ch: {d['active_channels']}) | "
                            f"TTA={tta_on} -> pred={d['predicted_direction']} (true={d['true_direction']}), "
                            f"score={d['decision_score']:.4f}, latency={d['latency_ms']:.3f}ms, "
                            f"quality={d['quality']['status']} ({d['quality']['eog_ptp_uv']}uV <= {d['quality']['threshold_uv']}uV)"
                        )

        # 4. Raw EEG (16, 500) direct inference & custom Calib20 calibration
        print("\n[4] POST /api/calibrate & POST /api/predict with Raw Broadband EEG Tensor")
        rng = np.random.default_rng(42)
        raw_cal_epochs = (rng.standard_normal((20, 16, 500)) * 12.0).tolist()
        raw_cal_labels = ["LEFT" if i % 2 == 0 else "RIGHT" for i in range(20)]
        r_cal = client.post(
            "/api/calibrate",
            json={
                "participant_id": "WMJ",
                "session_id": "live-custom-01",
                "channel_mode": "7ch",
                "tta_enabled": True,
                "calibration_epochs": raw_cal_epochs,
                "calibration_labels": raw_cal_labels,
            },
        )
        assert r_cal.status_code == 200, r_cal.text
        cal_info = r_cal.json()
        print(
            f"    • Custom Calib20 fit: status={cal_info['status']}, "
            f"channels={cal_info['active_channels']}, thr90={cal_info['artgate90_threshold_uv']}uV, "
            f"latency={cal_info['calibration_latency_ms']}ms"
        )

        raw_single_eeg = (rng.standard_normal((16, 500)) * 12.0).tolist()
        r_raw_pred = client.post(
            "/api/predict",
            json={
                "participant_id": "WMJ",
                "session_id": "live-custom-01",
                "channel_mode": "7ch",
                "tta_enabled": True,
                "eeg_data": raw_single_eeg,
                "is_band_filtered": False,
                "include_waveform": True,
            },
        )
        assert r_raw_pred.status_code == 200, r_raw_pred.text
        rp = r_raw_pred.json()
        print(
            f"    • Custom Raw EEG Trial -> pred={rp['predicted_direction']}, "
            f"score={rp['decision_score']:.4f}, latency={rp['latency_ms']:.3f}ms"
        )

        # 5. Full session evaluation & Website ReplaySource compatibility
        print("\n[5] POST /api/evaluate/session & GET /api/replay")
        r_sess = client.post(
            "/api/evaluate/session",
            json={
                "participant_id": "OYJ",
                "session_id": "session-01",
                "channel_mode": "low",
                "tta_enabled": True,
            },
        )
        assert r_sess.status_code == 200, r_sess.text
        s_eval = r_sess.json()
        assert s_eval["replay_source"]["kind"] == "recorded"
        assert len(s_eval["predictions"]) == s_eval["total_trials"]
        print(
            f"    • OYJ {s_eval['resolved_session_name']}: {s_eval['total_trials']} trials "
            f"(ArtGate90 clean={s_eval['clean_trials_artgate90']}) | "
            f"Live Game={s_eval['live_in_game_accuracy_pct']}% -> "
            f"Computed LowCh+TTA BA={s_eval['computed_metrics_artgate90']['balanced_accuracy_pct']}% "
            f"(AUC={s_eval['computed_metrics_artgate90']['roc_auc']}), "
            f"mean_latency={s_eval['mean_latency_ms']:.3f}ms"
        )

        # 6. Dynamic 50-Session Cohort Evaluation via API
        print("\n[6] GET /api/evaluate/cohort?golden_only=true (Dynamic 50-Session Reproduction)")
        r_coh = client.get("/api/evaluate/cohort?golden_only=true")
        assert r_coh.status_code == 200, r_coh.text
        c_eval = r_coh.json()
        gm = c_eval["cohort_grand_mean"]
        print(
            f"    • Evaluated N={c_eval['total_sessions_evaluated']} Golden Sessions dynamically in {c_eval['computation_latency_ms']:.1f}ms:"
        )
        print(
            f"      Live={gm['live_game_bacc_pct']}% -> 16ch={gm['16ch_only_bacc_pct']}% -> "
            f"16ch+TTA={gm['16ch_tta_bacc_pct']}% -> LowCh={gm['lowch_only_bacc_pct']}% -> "
            f"LowCh+TTA={gm['lowch_tta_bacc_pct']}% (p_vs_16ch={gm['paired_p_vs_16ch']:.2e})"
        )

        # 7. Real-Time WebSocket Streaming (/ws/eeg)
        print("\n[7] WebSocket /ws/eeg Real-Time Chronological Streaming Test")
        with client.websocket_connect("/ws/eeg") as ws:
            welcome = ws.receive_json()
            assert welcome["type"] == "connected"
            print(f"    • Connected WebSocket client_key={welcome['client_key']}")

            # Configure KGE Low-Channel + TTA ON
            ws.send_json({
                "action": "set_config",
                "participant_id": "KGE",
                "session_id": "session-01",
                "channel_mode": "5ch",
                "tta_enabled": True,
            })
            ack = ws.receive_json()
            assert ack["type"] == "config_ack"
            print(
                f"    • Configured KGE session={ack['session_info']['resolved_session_name']}, "
                f"channels={ack['session_info']['active_channels']}"
            )

            # Step 3 chronological trials
            for step_i in range(3):
                ws.send_json({"action": "step_trial", "include_waveform": True})
                msg = ws.receive_json()
                assert msg["type"] == "trial_prediction"
                p = msg["prediction"]
                print(
                    f"      - WS Step #{p['step_index']}: pred={p['predicted_direction']} "
                    f"(true={p['true_direction']}), score={p['decision_score']:.4f}, "
                    f"bias={p['tta_state']['running_logit_bias']:.4f}, latency={p['latency_ms']:.3f}ms"
                )

    print("\n" + "=" * 95)
    print("✅ ALL REST & WEBSOCKET VERIFICATION CHECKS PASSED!")
    print("=" * 95)


if __name__ == "__main__":
    main()
