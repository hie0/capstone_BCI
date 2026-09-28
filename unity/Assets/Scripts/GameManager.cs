using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// CONTRA LABS // BCI-OS v1.09 프로토콜 전체 흐름 제어기.
/// - 타이틀 시작 화면 (03.png)
/// - 메인 게임플레이 3분할 뷰 & 실시간 밸런스 (04.png)
/// - Step 2 신경 보정 카운트다운 & 전압 텔레메트리 (00.png)
/// - Step 4 결과 확정 텔레메트리 & 로그 창 (01.png)
/// - 8종 파멸 / 3종 승리 벙커 결산 엔딩 (02.png)
/// </summary>
public class GameManager : MonoBehaviour
{
    public enum Phase { Title, CardReading, Calibration, RealtimeMI, Feedback, Ending }

    [Header("의존성")]
    public BCIClient bci;
    public CardView cardView;

    [Header("실시간 뇌파 시각화 (neuro_feedback3 연동)")]
    public DynamicFadingCue fadingCue;
    public EEGWaveformMonitor leftEEGMonitor;  // C4 (Left Hand)
    public EEGWaveformMonitor rightEEGMonitor; // C3 (Right Hand)

    [Header("글로벌 헤더 & HUD")]
    public Text headerStatusText;
    public Text dayText;
    public Slider foodBar, ammoBar, defenseBar, moraleBar;
    public Text foodVal, ammoVal, defenseVal, moraleVal;

    [Header("하단 밸런스 HUD")]
    public Text leftIntentText;
    public Text rightIntentText;
    public Slider balanceSlider;
    public RectTransform balanceCursor;

    [Header("Step 2 신경 보정 오버레이 (00.png)")]
    public GameObject calibrationOverlay;
    public Text calibrationCountdownText;
    public RectTransform calibrationArcRect;
    public Text calibrationTelemetryText;

    [Header("Step 4 피드백 텔레메트리 오버레이 (01.png)")]
    public GameObject feedbackOverlay;
    public Text feedbackActionBadge;
    public Image feedbackActionBadgeBorder;
    public Text feedbackDeltaList;
    public Text feedbackLogText;

    [Header("엔딩 결산 오버레이 (02.png)")]
    public GameObject endingOverlay;
    public Text endingTagText;
    public Text endingBigTitle;
    public Text endingSubtitle;
    public Text endingDaysText;
    public Text endingSwipesText;
    public Text endingPopulationText;
    public Text endingFinalSuppliesText;
    public Text endingFinalIntegrityText;
    public Button restartButton;

    [Header("타이틀 시작 화면 (03.png)")]
    public GameObject titleScreen;
    public Button startButton;

    [Header("게임 규칙")]
    public int maxDays = 30;
    public float readDuration = 3.0f;     // 카드 읽기 시간 3초 (좌우 분류 잠금)
    public float miTimeout = 5.0f;        // 뇌파 상상 판단 시간 최대 5초

    public float feedbackDuration = 2.5f; // 결과 피드백 표시 2.5초
    public float triggerThreshold = 0.80f;

    // 자원 수치
    private int food = 50, ammo = 50, defense = 50, morale = 50;
    private int _cardIndex = 0;
    private int _day = 1;
    private int _totalSwipes = 0;
    private bool _gameOver = false;
    private CardDatabase _db;
    private bool _gameStarted = false;

    IEnumerator Start()
    {
        yield return StartCoroutine(LoadCards());
        if (_db == null || _db.cards == null || _db.cards.Count == 0)
        {
            Debug.LogError("[GameManager] 카드 데이터를 불러오지 못했습니다. StreamingAssets/cards.json 확인.");
            yield break;
        }

        if (startButton != null)
            startButton.onClick.AddListener(OnStartButtonClicked);
        if (restartButton != null)
            restartButton.onClick.AddListener(Restart);

        // 타이틀 화면 대기
        if (titleScreen != null)
        {
            titleScreen.SetActive(true);
            SetHeaderStatus("INITIALIZING SYSTEM...");
            while (!_gameStarted)
            {
                if (Input.GetKeyDown(KeyCode.Space) || Input.GetKeyDown(KeyCode.Return))
                    _gameStarted = true;
                yield return null;
            }
            titleScreen.SetActive(false);
        }

        ResetGame();
        StartCoroutine(GameLoop());
    }

    void OnStartButtonClicked()
    {
        _gameStarted = true;
    }

    IEnumerator LoadCards()
    {
        string path = Path.Combine(Application.streamingAssetsPath, "cards.json");
        string json = null;

        if (path.Contains("://"))
        {
            using (var req = UnityEngine.Networking.UnityWebRequest.Get(path))
            {
                yield return req.SendWebRequest();
                if (req.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
                    json = req.downloadHandler.text;
            }
        }
        else if (File.Exists(path))
        {
            json = File.ReadAllText(path);
        }

        if (!string.IsNullOrEmpty(json))
            _db = JsonUtility.FromJson<CardDatabase>(json);
    }

    void ResetGame()
    {
        food = ammo = defense = morale = 50;
        _cardIndex = 0;
        _day = 1;
        _totalSwipes = 0;
        _gameOver = false;
        if (endingOverlay) endingOverlay.SetActive(false);
        if (feedbackOverlay) feedbackOverlay.SetActive(false);
        if (calibrationOverlay) calibrationOverlay.SetActive(false);

        UpdateHUD(instant: true);
        BindCurrentCard();
    }

    Card CurrentCard() => _db.cards[_cardIndex % _db.cards.Count];

    void BindCurrentCard()
    {
        if (cardView) cardView.Bind(CurrentCard());
    }

    /// <summary>온라인 프로토콜 4단계 상태머신 루프</summary>
    IEnumerator GameLoop()
    {
        while (!_gameOver)
        {
            // ── Step 1: Card Reading (5초간 좌우 분류 완전 잠금) ────────────────
            if (bci) bci.DecodingEnabled = false;
            if (calibrationOverlay) calibrationOverlay.SetActive(false);
            if (feedbackOverlay) feedbackOverlay.SetActive(false);
            if (fadingCue) fadingCue.SetFeedback(0, "NONE", 0.5f);
            if (cardView) cardView.UpdateTilt(0.5f, 0.5f);
            UpdateBalanceHUD(0.5f, 0.5f);

            float readTimer = 0f;
            while (readTimer < readDuration)
            {
                readTimer += Time.deltaTime;
                float remain = Mathf.Max(0f, readDuration - readTimer);
                SetHeaderStatus($"📖 READING PHASE // {remain:F1}s [INPUT LOCKED - SPACE TO SKIP]");

                // 뇌파 모니터는 기본 베이스라인 파형 유지
                if (leftEEGMonitor) leftEEGMonitor.UpdateTelemetry(0.5f);
                if (rightEEGMonitor) rightEEGMonitor.UpdateTelemetry(0.5f);

                // Space 누르면 즉시 읽기 스킵 가능
                if (Input.GetKeyDown(KeyCode.Space))
                    break;

                yield return null;
            }

            // ── Step 2: Realtime Motor Imagery (좌우 뇌파 분류 활성화!) ────────
            SetHeaderStatus("⚡ NEURAL FOCUS ACTIVE // IMAGINE LEFT OR RIGHT");
            if (bci) bci.DecodingEnabled = true;

            float miTimer = 0f;
            string decided = null;
            while (miTimer < miTimeout)
            {
                miTimer += Time.deltaTime;

                float pL = bci ? bci.LeftProb : 0.5f;
                float pR = bci ? bci.RightProb : 0.5f;

                if (cardView) cardView.UpdateTilt(pL, pR);
                UpdateBalanceHUD(pL, pR);

                // neuro_feedback3_calibrated.py 기반 Dynamic Fading Level 계산 (서버 값 우선 or 자동 계산)
                int lvl = (bci != null && bci.Level > 0) ? bci.Level : 0;
                string cand = "NONE";
                float prob = 0.5f;

                if (lvl == 0)
                {
                    if (pL >= triggerThreshold) { lvl = 3; cand = "LEFT"; prob = pL; }
                    else if (pR >= triggerThreshold) { lvl = 3; cand = "RIGHT"; prob = pR; }
                    else if (pL >= 0.70f) { lvl = 2; cand = "LEFT"; prob = pL; }
                    else if (pR >= 0.70f) { lvl = 2; cand = "RIGHT"; prob = pR; }
                    else if (pL >= 0.58f) { lvl = 1; cand = "LEFT"; prob = pL; }
                    else if (pR >= 0.58f) { lvl = 1; cand = "RIGHT"; prob = pR; }
                }
                else
                {
                    cand = (pL >= pR) ? "LEFT" : "RIGHT";
                    prob = Mathf.Max(pL, pR);
                }

                if (fadingCue) fadingCue.SetFeedback(lvl, cand, prob);

                float? rawC4 = (bci != null && bci.C4_uV > 0f) ? (float?)bci.C4_uV : null;
                float? rawC3 = (bci != null && bci.C3_uV > 0f) ? (float?)bci.C3_uV : null;
                if (leftEEGMonitor) leftEEGMonitor.UpdateTelemetry(pL, rawC4);
                if (rightEEGMonitor) rightEEGMonitor.UpdateTelemetry(pR, rawC3);


                if (pL >= triggerThreshold) { decided = "LEFT"; break; }
                if (pR >= triggerThreshold) { decided = "RIGHT"; break; }

                yield return null;
            }

            if (decided == null)
                decided = (bci != null && bci.LeftProb >= bci.RightProb) ? "LEFT" : "RIGHT";

            _totalSwipes++;

            // ── Step 4: Feedback & Rest (01.png) ──────────────────────
            SetHeaderStatus("COMMAND EXECUTION CONFIRMED");
            if (bci) bci.DecodingEnabled = false;
            if (fadingCue) fadingCue.SetFeedback(3, decided, 1.0f, "SUCCESS");

            if (cardView) cardView.StartSwipe(decided);

            Card playedCard = CurrentCard();
            CardOption chosenOpt = (decided == "LEFT") ? playedCard.left_option : playedCard.right_option;
            ApplyDecision(chosenOpt);

            // 스와이프 완료 대기
            float swTimer = 0f;
            while (cardView != null && !cardView.IsSwipeFinished() && swTimer < 1.0f)
            {
                swTimer += Time.deltaTime;
                yield return null;
            }

            // 피드백 텔레메트리 창 표시 (01.png)
            ShowFeedbackScreen(decided, playedCard, chosenOpt);
            UpdateHUD(instant: false);

            if (CheckEndings()) yield break;

            float fbTimer = 0f;
            while (fbTimer < feedbackDuration && !Input.GetKeyDown(KeyCode.Space))
            {
                fbTimer += Time.deltaTime;
                yield return null;
            }

            if (feedbackOverlay) feedbackOverlay.SetActive(false);

            _day++;
            _cardIndex++;
            BindCurrentCard();
        }
    }

    void ApplyDecision(CardOption opt)
    {
        if (opt == null || opt.stat_delta == null) return;
        food = Mathf.Clamp(food + opt.stat_delta.food, 0, 100);
        ammo = Mathf.Clamp(ammo + opt.stat_delta.ammo, 0, 100);
        defense = Mathf.Clamp(defense + opt.stat_delta.defense, 0, 100);
        morale = Mathf.Clamp(morale + opt.stat_delta.morale, 0, 100);
    }

    void ShowFeedbackScreen(string direction, Card card, CardOption opt)
    {
        if (feedbackOverlay == null) return;
        feedbackOverlay.SetActive(true);

        bool isRight = (direction == "RIGHT");
        if (feedbackActionBadge)
        {
            feedbackActionBadge.text = isRight
                ? "RIGHT ACTION ENGAGED // CONFIRMED"
                : "LEFT ACTION ENGAGED // CONFIRMED";
            feedbackActionBadge.color = isRight ? new Color(0.0f, 0.90f, 1.0f) : new Color(1.0f, 0.35f, 0.40f);
        }
        if (feedbackActionBadgeBorder)
        {
            feedbackActionBadgeBorder.color = isRight ? new Color(0.0f, 0.90f, 1.0f, 0.8f) : new Color(1.0f, 0.35f, 0.40f, 0.8f);
        }

        if (feedbackDeltaList)
        {
            var sb = new System.Text.StringBuilder();
            if (opt?.stat_delta != null)
            {
                var d = opt.stat_delta;
                if (d.morale != 0) sb.AppendLine($"👥 Survivor Morale     {(d.morale > 0 ? "+" : "")}{d.morale}%");
                if (d.food != 0)   sb.AppendLine($"🍖 Supplies            {(d.food > 0 ? "+" : "")}{d.food}%");
                if (d.defense != 0)sb.AppendLine($"🛡 Shelter Integrity   {(d.defense > 0 ? "+" : "")}{d.defense}%");
                if (d.ammo != 0)   sb.AppendLine($"⚡ Ammo Capacity       {(d.ammo > 0 ? "+" : "")}{d.ammo}%");
            }
            feedbackDeltaList.text = sb.Length > 0 ? sb.ToString() : "No telemetry change detected.";
        }

        if (feedbackLogText)
        {
            feedbackLogText.text = $"\"{opt?.text}\"\n-- {card?.character}: 결정을 수행하였습니다.";
        }
    }

    bool CheckEndings()
    {
        // 8종 파멸 (0% 또는 100%)
        if (food <= 0) return TriggerEnding("기아 전멸 엔딩", "식량이 고갈되어 쉘터 주민 전원이 아사하였습니다.", false);
        if (food >= 100) return TriggerEnding("약탈단 기습 유실 엔딩", "물자가 넘쳐 약탈단 렉스 패거리에 습격당했습니다.", false);
        if (ammo <= 0) return TriggerEnding("탄약 고갈 좀비 유입", "방어 탄약이 소진되어 좀비 떼에 무력하게 짓밟혔습니다.", false);
        if (ammo >= 100) return TriggerEnding("탄약고 유폭 붕괴", "탄약 과다 보관으로 유폭 사고가 발생했습니다.", false);
        if (defense <= 0) return TriggerEnding("바리케이드 완파 침몰", "방호 철문이 무너지며 좀비 호드가 진입했습니다.", false);
        if (defense >= 100) return TriggerEnding("완벽 봉쇄 질식 사망", "지하 배기구까지 밀폐하여 산소 고갈로 질식했습니다.", false);
        if (morale <= 0) return TriggerEnding("내부 폭동 리더 추방", "생존자 사기 파탄으로 지휘관이 축출당했습니다.", false);
        if (morale >= 100) return TriggerEnding("광신도 광란 자살 강행군", "광신적 사기로 무모한 돌진을 감행해 전멸했습니다.", false);

        // 3종 승리
        if (_day >= maxDays)
        {
            if (morale >= 80) return TriggerEnding("정부 구조 헬기 탈출", "생존자 사기를 80% 이상 유지하며 구원 헬기에 전원 탑승했습니다!", true);
            if (food >= 70 && defense >= 70) return TriggerEnding("인류 치료 백신 완제", "충분한 물자와 방어선 속에서 백신 항체를 완성했습니다!", true);
            return TriggerEnding("아포칼립스 요새 방어 성공", "30일간 벙커 신호를 유지하며 방어에 성공했습니다!", true);
        }
        return false;
    }

    bool TriggerEnding(string title, string desc, bool victory)
    {
        _gameOver = true;
        SetHeaderStatus(victory ? "MISSION ACCOMPLISHED // EVACUATION SUCCESSFUL" : "CRITICAL OUTPOST COMM FAILURE");

        if (endingOverlay) endingOverlay.SetActive(true);
        if (endingTagText)
            endingTagText.text = victory ? "[ SYS_EVAC_ALERT // PROTOCOL_SUCCESS ]" : "[ SYS_SHIELD_ALERT // COMM_FAILURE ]";
        if (endingBigTitle)
        {
            endingBigTitle.text = victory ? "MISSION ACCOMPLISHED" : "SHELTER FALLEN";
            endingBigTitle.color = victory ? new Color(0.2f, 0.95f, 0.55f) : new Color(1.0f, 0.28f, 0.32f);
        }
        if (endingSubtitle)
            endingSubtitle.text = desc;

        if (endingDaysText) endingDaysText.text = $"{_day} Days";
        if (endingSwipesText) endingSwipesText.text = $"{_totalSwipes} Swipes";
        if (endingPopulationText) endingPopulationText.text = $"{morale + 10} Saved";

        if (endingFinalSuppliesText) endingFinalSuppliesText.text = $"{food}%";
        if (endingFinalIntegrityText) endingFinalIntegrityText.text = $"{defense}%";

        return true;
    }

    void SetHeaderStatus(string status)
    {
        if (headerStatusText) headerStatusText.text = status;
    }

    void UpdateBalanceHUD(float pL, float pR)
    {
        int leftPct = Mathf.RoundToInt(pL * 100f);
        int rightPct = 100 - leftPct;

        if (leftIntentText) leftIntentText.text = $"LEFT CONTROL INTENT: {leftPct}%";
        if (rightIntentText) rightIntentText.text = $"RIGHT CONTROL INTENT: {rightPct}%";

        if (balanceSlider != null)
        {
            balanceSlider.value = Mathf.Lerp(balanceSlider.value, pR, 12f * Time.deltaTime);
        }
    }

    void UpdateHUD(bool instant = false)
    {
        if (dayText) dayText.text = $"DAY {_day:00} / {maxDays}";

        UpdateSingleStat(foodBar, foodVal, food, instant);
        UpdateSingleStat(ammoBar, ammoVal, ammo, instant);
        UpdateSingleStat(defenseBar, defenseVal, defense, instant);
        UpdateSingleStat(moraleBar, moraleVal, morale, instant);
    }

    void UpdateSingleStat(Slider bar, Text val, int targetVal, bool instant)
    {
        if (val) val.text = $"{targetVal}%";
        if (bar != null && instant) bar.value = targetVal / 100f;
    }

    void Update()
    {
        // 상단 슬림 게이지 부드러운 Lerp
        SmoothSlider(foodBar, food / 100f);
        SmoothSlider(ammoBar, ammo / 100f);
        SmoothSlider(defenseBar, defense / 100f);
        SmoothSlider(moraleBar, morale / 100f);
    }

    void SmoothSlider(Slider s, float target)
    {
        if (s != null)
            s.value = Mathf.Lerp(s.value, target, 8f * Time.deltaTime);
    }

    public void Restart()
    {
        StopAllCoroutines();
        ResetGame();
        StartCoroutine(GameLoop());
    }
}
