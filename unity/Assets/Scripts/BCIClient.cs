using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

/// <summary>
/// bci_tcp_server.py (127.0.0.1:5000) 와 TCP 로 연결하여
/// 0.25초 슬라이딩 윈도우 추론 패킷(JSON 라인)을 실시간 수신한다.
///
/// 소켓 수신은 백그라운드 스레드에서 수행하고, 파싱된 최신 패킷을
/// volatile 필드로 노출한다(메인 스레드 GameManager 가 매 프레임 소비).
///
/// 서버가 꺼져 있어도 게임이 멈추지 않도록:
///  - 자동 재연결(재시도) 루프
///  - 키보드 폴백(A/←=LEFT, D/→=RIGHT)으로 확률을 직접 상승/감쇄
/// 을 지원한다.
/// </summary>
public class BCIClient : MonoBehaviour
{
    [Header("서버 연결 설정")]
    public string host = "127.0.0.1";
    public int port = 5000;
    [Tooltip("서버 연결에 실패하면 이 간격(초)마다 재연결을 시도한다.")]
    public float reconnectInterval = 2.0f;

    [Header("키보드 폴백 (서버 미연결 시 시뮬레이션)")]
    [Tooltip("서버가 없거나 연결 전이어도 키보드로 MI 확률을 조작해 테스트할 수 있다.")]
    public bool enableKeyboardFallback = true;
    [Tooltip("키를 누르고 있을 때 초당 확률 상승량.")]
    public float keyboardRampPerSec = 1.4f;
    [Tooltip("키를 떼면 baseline(0.5)로 복귀하는 감쇄 속도.")]
    public float keyboardDecayPerSec = 3.0f;

    // ── 외부(GameManager)에서 읽는 최신 상태 ──────────────────────────
    public float LeftProb { get; private set; } = 0.5f;
    public float RightProb { get; private set; } = 0.5f;
    public string Trigger { get; private set; } = "NONE";   // NONE | LEFT | RIGHT | NEUTRAL
    public bool IsConnected { get; private set; } = false;
    public int Level { get; private set; } = 0;             // neuro_feedback3 Level (0~3)
    public float C3_uV { get; private set; } = 0f;
    public float C4_uV { get; private set; } = 0f;

    // ── 소켓 수신 스레드 관련 ─────────────────────────────────────────
    private Thread _rxThread;
    private volatile bool _running = false;

    // 스레드 → 메인 스레드로 넘기는 최신 패킷(락으로 보호)
    private readonly object _lock = new object();
    private BCIPacket _latestPacket;
    private bool _hasNewPacket = false;

    // 게임이 EEG 를 무시해야 하는 구간(카드 읽기/휴식)에서 true.
    // 이 상태에서는 트리거를 NONE 으로 강제한다.
    public bool DecodingEnabled { get; set; } = true;

    void OnEnable()
    {
        StartReceiver();
    }

    void OnDisable()
    {
        StopReceiver();
    }

    void StartReceiver()
    {
        if (_running) return;
        _running = true;
        _rxThread = new Thread(ReceiveLoop) { IsBackground = true, Name = "BCI-RX" };
        _rxThread.Start();
    }

    void StopReceiver()
    {
        _running = false;
        try { _rxThread?.Join(500); } catch { /* ignore */ }
        _rxThread = null;
        IsConnected = false;
    }

    /// <summary>백그라운드 스레드: 연결·수신·재연결을 담당.</summary>
    private void ReceiveLoop()
    {
        while (_running)
        {
            TcpClient client = null;
            try
            {
                client = new TcpClient();
                client.Connect(host, port);
                IsConnected = true;
                Debug.Log($"[BCIClient] Connected to {host}:{port}");

                using (var stream = client.GetStream())
                using (var reader = new StreamReader(stream, Encoding.UTF8))
                {
                    while (_running && client.Connected)
                    {
                        string line = reader.ReadLine();   // '\n' 단위 JSON
                        if (line == null) break;            // 서버가 스트림을 닫음
                        line = line.Trim();
                        if (line.Length == 0) continue;

                        try
                        {
                            var packet = JsonUtility.FromJson<BCIPacket>(line);
                            if (packet != null)
                            {
                                lock (_lock)
                                {
                                    _latestPacket = packet;
                                    _hasNewPacket = true;
                                }
                            }
                        }
                        catch (Exception pe)
                        {
                            Debug.LogWarning($"[BCIClient] JSON parse skip: {pe.Message} | raw={line}");
                        }
                    }
                }
            }
            catch (SocketException)
            {
                // 서버가 아직 안 떠 있음 → 조용히 재시도
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[BCIClient] Receive error: {e.Message}");
            }
            finally
            {
                IsConnected = false;
                try { client?.Close(); } catch { }
            }

            if (_running)
                Thread.Sleep((int)(reconnectInterval * 1000));
        }
    }

    void Update()
    {
        // 1) 소켓으로 들어온 최신 패킷을 메인 스레드에서 소비
        bool consumedPacket = false;
        lock (_lock)
        {
            if (_hasNewPacket && _latestPacket != null)
            {
                LeftProb = Mathf.Clamp01(_latestPacket.left_prob);
                RightProb = Mathf.Clamp01(_latestPacket.right_prob);
                Trigger = string.IsNullOrEmpty(_latestPacket.trigger) ? "NONE" : _latestPacket.trigger;
                Level = _latestPacket.level;
                C3_uV = _latestPacket.c3_uV;
                C4_uV = _latestPacket.c4_uV;
                _hasNewPacket = false;
                consumedPacket = true;
            }
        }

        // 2) 서버가 없을 때(또는 연결 전) 키보드 폴백으로 확률 시뮬레이션
        if (!IsConnected && enableKeyboardFallback)
        {
            SimulateWithKeyboard();
            consumedPacket = true;
        }

        // 3) 디코딩이 비활성인 구간에서는 트리거를 막고 baseline 로 부드럽게 복귀
        if (!DecodingEnabled)
        {
            Trigger = "NONE";
            LeftProb = Mathf.MoveTowards(LeftProb, 0.5f, keyboardDecayPerSec * Time.deltaTime);
            RightProb = 1f - LeftProb;
            return;
        }

        // 4) 소켓/키보드 어느 쪽도 갱신이 없으면 트리거만 최신 확률로 재계산
        if (!consumedPacket)
            RecomputeTrigger();
    }

    private void SimulateWithKeyboard()
    {
        bool left = Input.GetKey(KeyCode.LeftArrow) || Input.GetKey(KeyCode.A);
        bool right = Input.GetKey(KeyCode.RightArrow) || Input.GetKey(KeyCode.D);

        if (left && !right)
        {
            LeftProb = Mathf.Min(1f, LeftProb + keyboardRampPerSec * Time.deltaTime);
        }
        else if (right && !left)
        {
            LeftProb = Mathf.Max(0f, LeftProb - keyboardRampPerSec * Time.deltaTime);
        }
        else
        {
            // 손을 떼면 0.5 baseline 으로 감쇄
            LeftProb = Mathf.MoveTowards(LeftProb, 0.5f, keyboardDecayPerSec * Time.deltaTime * 0.5f);
        }

        RightProb = 1f - LeftProb;
        RecomputeTrigger();
    }

    /// <summary>현재 확률로 트리거 상태를 재계산(80% 임계값 / 40~60% 불감대).</summary>
    private void RecomputeTrigger()
    {
        if (LeftProb >= 0.80f) Trigger = "LEFT";
        else if (RightProb >= 0.80f) Trigger = "RIGHT";
        else if (LeftProb >= 0.40f && LeftProb <= 0.60f) Trigger = "NEUTRAL";
        else Trigger = "NONE";
    }
}
