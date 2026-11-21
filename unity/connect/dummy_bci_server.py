#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dummy_bci_server.py
-------------------
실제 Explore 장비나 머신러닝 라이브러리(numpy, scipy, sklearn 등) 설치 없이도
순수 파이썬 표준 라이브러리(socket, json, math, time)만으로 동작하는
유니티 연동용 가상 BCI 서버입니다.

포트: 127.0.0.1:5000 (TCP)
패킷 포맷: JSON 라인 ('\\n' 구분)
지원 신호:
- left_prob / right_prob: 4단계 시나리오에 따른 부드러운 확률 변화
- trigger: 80% 이상 도달 시 'LEFT' 또는 'RIGHT', 불감대 'NEUTRAL', 미도달 'NONE'
- level: Dynamic Fading 단계 (0~4)
- c3_uV / c4_uV: 대뇌 반구 활성화에 따른 ERD/ERS 실시간 전압 텔레메트리
- elapsed_sec: 경과 시간 (초)
"""

import argparse
import json
import math
import random
import socket
import sys
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000
DEFAULT_INTERVAL = 0.25  # 250ms


def run_dummy_server(host=DEFAULT_HOST, port=DEFAULT_PORT, interval=DEFAULT_INTERVAL):
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(5)
    server_sock.settimeout(0.5)

    print("=" * 70)
    print(f"[*] [Pure Dummy BCI Server] Running on {host}:{port}")
    print(f"[*] [Interval] {interval*1000:.0f}ms per packet ({1/interval:.1f} Hz)")
    print("[*] [Unity] Waiting for BCIClient.cs to connect...")
    print("[*] [Scenario] 16s cycle (0~6s LEFT -> 6~8s NEUTRAL -> 8~14s RIGHT -> 14~16s NEUTRAL)")
    print("=" * 70 + "\n")

    clients = []
    clients_lock = threading.Lock()
    running = True

    def client_rx_loop(c, addr):
        buf = ""
        while running:
            try:
                data = c.recv(1024)
                if not data:
                    break
                buf += data.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "handshake":
                            print(f"\n[Handshake] Received from {addr}: Subject={msg.get('subject')}, Model={msg.get('model')}")
                    except Exception:
                        pass
            except Exception:
                break

    def accept_loop():
        while running:
            try:
                c, addr = server_sock.accept()
                with clients_lock:
                    clients.append(c)
                print(f"\n[+] Unity Connected from {addr[0]}:{addr[1]}")
                threading.Thread(target=client_rx_loop, args=(c, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    acc_thread = threading.Thread(target=accept_loop, daemon=True)
    acc_thread.start()

    start_time = time.time()
    phase = 0.0

    # [온프 neuro_feedback4_scaled.py Chae et al., 2012 Dynamic Fading 상태머신 이식]
    # Level 0 -> 1 -> 2 -> 3 -> 4 누적으로 보통 4~5초간 지속 집중해야 발화!
    selection_level = 0
    candidate = None
    accum_timer = 0.0
    eval_interval = 0.5  # 온프와 동일한 0.5초 단위 윈도우 평가
    trigger_cooldown = 0.0

    try:
        while True:
            t_start = time.time()
            elapsed = time.time() - start_time
            phase += 0.15
            accum_timer += interval

            # 16초 시나리오 (0~6s LEFT 집중 -> 6~8s REST -> 8~14s RIGHT 집중 -> 14~16s REST)
            cycle = elapsed % 16.0
            if cycle < 6.0:
                base_pL = 0.78
                mode_str = "LEFT FOCUS (~5s)"
                target_intent = "LEFT"
            elif cycle < 8.0:
                base_pL = 0.50
                mode_str = "RELAX / REST"
                target_intent = "NONE"
            elif cycle < 14.0:
                base_pL = 0.22
                mode_str = "RIGHT FOCUS (~5s)"
                target_intent = "RIGHT"
            else:
                base_pL = 0.50
                mode_str = "RELAX / REST"
                target_intent = "NONE"

            # 현실적인 뇌파 변동 (0.5s 윈도우 기준 노이즈)
            jitter = (random.random() - 0.5) * 0.10
            left_prob = max(0.05, min(0.95, base_pL + math.sin(phase) * 0.05 + jitter))
            right_prob = 1.0 - left_prob

            # 0.5초마다 온프 Dynamic Fading 상태머신 갱신
            if accum_timer >= eval_interval:
                accum_timer = 0.0

                # 윈도우 예측 방향 (단순 0.50 초과 or 불감대)
                if left_prob >= 0.58:
                    win_pred = "LEFT"
                elif right_prob >= 0.58:
                    win_pred = "RIGHT"
                else:
                    win_pred = "NONE"

                # 온프(neuro_feedback4_scaled.py:1950) 공식 누적 규칙
                if win_pred in {"LEFT", "RIGHT"}:
                    if selection_level == 0:
                        candidate = win_pred
                        selection_level = 1
                    elif win_pred == candidate:
                        selection_level = min(4, selection_level + 1)
                    else:
                        selection_level = max(0, selection_level - 1)
                else:
                    selection_level = max(0, selection_level - 1)

            # 트리거 판정: Level 4에 도달해야만 최종 Trigger 발화!
            trigger = "NONE"
            if selection_level >= 4 and candidate in {"LEFT", "RIGHT"}:
                trigger = candidate
                trigger_cooldown += interval
                if trigger_cooldown > 2.0:  # 2초간 트리거 유지 후 리셋
                    selection_level = 0
                    candidate = None
                    trigger_cooldown = 0.0
            else:
                trigger_cooldown = 0.0
                if selection_level == 0 and 0.45 <= left_prob <= 0.55:
                    trigger = "NEUTRAL"

            # 실시간 C3/C4 전압 (uV)
            c3_uV = round(7.0 + (1.0 - right_prob) * 4.2 + math.sin(phase * 1.5) * 1.1, 2)
            c4_uV = round(7.0 + (1.0 - left_prob) * 4.2 + math.cos(phase * 1.3) * 1.1, 2)

            packet = {
                "left_prob": round(left_prob, 3),
                "right_prob": round(right_prob, 3),
                "trigger": trigger,
                "level": selection_level,
                "c3_uV": c3_uV,
                "c4_uV": c4_uV,
                "elapsed_sec": round(elapsed, 2),
            }

            payload = (json.dumps(packet) + "\n").encode("utf-8")

            with clients_lock:
                dead = []
                for c in clients:
                    try:
                        c.sendall(payload)
                    except Exception:
                        dead.append(c)
                for d in dead:
                    try:
                        d.close()
                    except Exception:
                        pass
                    clients.remove(d)
                    print("\n[-] Unity Disconnected.")

            # 터미널 상태 출력
            bar_len = 20
            l_fill = int(round(left_prob * bar_len))
            r_fill = bar_len - l_fill
            bar = f"[{'#' * l_fill}{'-' * r_fill}]"
            with clients_lock:
                n_c = len(clients)
            tag = f"[UNITY:{n_c}]" if n_c > 0 else "[WAITING]"

            sys.stdout.write(
                f"\r{tag} P(L):{left_prob:.2f} {bar} P(R):{right_prob:.2f} | "
                f"Lvl:{level}/4 | Trg:{trigger:<5} | C3:{c3_uV:4.1f}uV C4:{c4_uV:4.1f}uV | {mode_str:<12}"
            )
            sys.stdout.flush()

            spent = time.time() - t_start
            time.sleep(max(0.005, interval - spent))

    except KeyboardInterrupt:
        print("\n\n[*] Server stopping...")
    finally:
        running = False
        with clients_lock:
            for c in clients:
                try:
                    c.close()
                except Exception:
                    pass
        try:
            server_sock.close()
        except Exception:
            pass
        print("[*] Server terminated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pure Dummy BCI Server for Unity")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host address (127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port (5000)")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Interval in sec (0.25)")
    args = parser.parse_args()

    run_dummy_server(args.host, args.port, args.interval)
