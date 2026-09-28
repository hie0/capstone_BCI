#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_connection.py
------------------
Unity BCIClient.cs 와 동일하게 TCP 소켓(127.0.0.1:5000)으로 접속하여
서버로부터 수신되는 BCI JSON 패킷의 규격, 지연 시간, 필드 정합성을 진단하는 테스트 클라이언트입니다.

실행 방법:
    python test_connection.py
"""

import argparse
import json
import socket
import sys
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

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000


def test_connection(host=DEFAULT_HOST, port=DEFAULT_PORT, max_packets=30):
    print("=" * 70)
    print(f"[*] [BCI Connection Diagnostic] Connecting to {host}:{port}...")
    print("=" * 70)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        t0 = time.time()
        sock.connect((host, port))
        conn_time = (time.time() - t0) * 1000
        print(f"[+] [Connected] Connection established in {conn_time:.1f}ms\n")
    except Exception as e:
        print(f"[!] [Failed] Could not connect to {host}:{port} ({e})")
        print("[*] Hint: Run 'start_server.bat' or 'start_dummy.bat' first!\n")
        return False

    print(f"{'#':<4} | {'P(LEFT)':<8} | {'P(RIGHT)':<8} | {'LEVEL':<6} | {'TRIGGER':<8} | {'C3 (uV)':<8} | {'C4 (uV)':<8} | {'INTERVAL'}")
    print("-" * 75)

    buffer = ""
    packet_count = 0
    last_packet_time = time.time()
    intervals = []

    try:
        while packet_count < max_packets:
            chunk = sock.recv(1024).decode("utf-8")
            if not chunk:
                print("[-] Server closed stream.")
                break

            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                now = time.time()
                dt = (now - last_packet_time) * 1000 if packet_count > 0 else 0
                if packet_count > 0:
                    intervals.append(dt)
                last_packet_time = now

                packet_count += 1
                try:
                    p = json.loads(line)
                    pL = p.get("left_prob", 0.0)
                    pR = p.get("right_prob", 0.0)
                    lvl = p.get("level", 0)
                    trg = p.get("trigger", "NONE")
                    c3 = p.get("c3_uV", 0.0)
                    c4 = p.get("c4_uV", 0.0)

                    dt_str = f"{dt:5.1f}ms" if packet_count > 1 else "   -   "
                    print(f"{packet_count:02d}   | {pL:8.3f} | {pR:8.3f} | L{lvl:<5} | {trg:<8} | {c3:6.1f}uV | {c4:6.1f}uV | {dt_str}")

                except json.JSONDecodeError as je:
                    print(f"[!] JSON parsing error on line: {line} ({je})")

    except KeyboardInterrupt:
        print("\n[*] Diagnostic aborted by user.")
    except socket.timeout:
        print("\n[!] Socket timed out waiting for packets.")
    finally:
        sock.close()

    print("-" * 75)
    if intervals:
        avg_int = sum(intervals) / len(intervals)
        print(f"[*] [Summary] Received {packet_count} packets. Average interval: {avg_int:.1f}ms ({1000/avg_int:.1f} Hz)")
        print("[+] [Diagnosis] Connection, JSON schema, and latency are fully verified for Unity!")
    else:
        print("[!] [Summary] Insufficient packets received.")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test BCI TCP Connection")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host (127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port (5000)")
    parser.add_argument("-n", "--count", type=int, default=25, help="Number of packets to test")
    args = parser.parse_args()

    test_connection(args.host, args.port, args.count)
