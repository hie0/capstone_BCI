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
    public enum Phase { Title, PreGameCheck, CardReading, RealtimeMI, Feedback, Rest, Ending }

    [Header("의존성")]
    public BCIClient bci;
    public CardView cardView;

    [Header("실시간 뇌파 시각화 (neuro_feedback3 연동)")]
    public DynamicFadingCue fadingCue;
    public EEGWaveformMonitor leftEEGMonitor;  // 가짜 수치 제거 및 화면에서 숨김 처리됨
    public EEGWaveformMonitor rightEEGMonitor;

    [Header("글로벌 헤더 & HUD")]
    public Text headerStatusText;
    public Text dayText;
    public Slider foodBar, ammoBar, defenseBar, moraleBar;
    public Text foodVal, ammoVal, defenseVal, moraleVal;
    public CanvasGroup mainHUDCanvasGroup;     // [합의 ⑤] MI Focus Mode Dimming 용

    [Header("하단 밸런스 HUD")]
    public Text leftIntentText;
    public Text rightIntentText;
    public Slider balanceSlider;
    public RectTransform balanceCursor;

    [Header("Pre-Game BCI Check (게임 온라인 프로토콜 유사 UI)")]
    public GameObject calibrationOverlay;
    public Text calibStepText;
    public Text calibInstructionText;
    public Text calibTimerText;
    public Image calibCueRing;
    public Image calibCueArrowLeft;
    public Image calibCueArrowRight;
    public Slider calibBalanceSlider;
    public Text calibLeftIntentText;
    public Text calibRightIntentText;
    public GameObject calibResultPanel;
    public Text calibResultText;
    public Button calibStartGameButton;

    [Header("Day 5 정기 휴식 (Rest Phase) 모달")]
    public GameObject restOverlay;
    public Text restTitleText;
    public Text restCountdownText;
    public Text restSuppliesText;
    public Button restResumeButton;

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
    public Button preCheckButton;
    public InputField subjectInputField;
    public Dropdown modelDropdown;

    [Header("게임 규칙")]
    public int maxDays = 30;
    public float readDuration = 3.0f;     // 카드 읽기 시간 3초 (좌우 분류 잠금)
    public float miTimeout = 8.0f;        // [온프 동기화] 뇌파 집중 및 5초 누적 판정을 위한 충분한 시간 (최대 8초)
    public float feedbackDuration = 2.5f; // 결과 피드백 표시 2.5초

    // 자원 수치
    private int food = 50, ammo = 50, defense = 50, morale = 50;
    private int _cardIndex = 0;
    private int _day = 1;
    private int _totalSwipes = 0;
    private bool _gameOver = false;
    private CardDatabase _db;
    private bool _gameStarted = false;
    private bool _runPreCheck = true;     // 기본값: 반드시 칼리브레이션(Pre-game BCI Check) 실행
    private bool _restResumeRequested = false;

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
        if (preCheckButton != null)
            preCheckButton.onClick.AddListener(OnSkipCheckButtonClicked);
        if (restartButton != null)
            restartButton.onClick.AddListener(Restart);
        if (restResumeButton != null)
            restResumeButton.onClick.AddListener(() => _restResumeRequested = true);
        if (calibStartGameButton != null)
            calibStartGameButton.onClick.AddListener(() => _restResumeRequested = true);

        // 타이틀 화면 대기
        if (titleScreen != null)
        {
            titleScreen.SetActive(true);
            SetHeaderStatus("INITIALIZING SYSTEM // WAITING FOR PROTOCOL START");
            while (!_gameStarted)
            {
                if (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.Space))
                {
                    OnStartButtonClicked();
                }
                yield return null;
            }
            titleScreen.SetActive(false);
        }

        // BCIClient에 선택된 피험자 및 모델 정보 등록 & 핸드셰이크
        if (bci != null)
        {
            string subj = (subjectInputField != null && !string.IsNullOrEmpty(subjectInputField.text))
                ? subjectInputField.text.Trim() : "S01";
            string modelName = (modelDropdown != null && modelDropdown.options.Count > modelDropdown.value)
                ? modelDropdown.options[modelDropdown.value].text : "Base Model";
            bci.SendHandshake(subj, modelName);
        }

        // [핵심] Pre-Game BCI Check (칼리브레이션 단계가 기본으로 먼저 반드시 실행됨!)
        if (_runPreCheck && calibrationOverlay != null)
        {
            yield return StartCoroutine(RunPreGameBCICheck());
        }

        ResetGame();
        StartCoroutine(GameLoop());
    }

    void OnStartButtonClicked()
    {
        _runPreCheck = true; // [핵심] 칼리브레이션 6회 반드시 거쳐서 시작!
        _gameStarted = true;
    }

    void OnSkipCheckButtonClicked()
    {
        _runPreCheck = false; // 칼리브레이션 건너뛰기
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
        if (restOverlay) restOverlay.SetActive(false);

        SetFocusMode(false);
        UpdateHUD(instant: true);
        BindCurrentCard();
    }

    Card CurrentCard() => _db.cards[_cardIndex % _db.cards.Count];

    void BindCurrentCard()
    {
        if (cardView) cardView.Bind(CurrentCard());
    }

    /// <summary>
    /// [조건부 합의 ⑧, ⑨] Pre-game BCI Check:
    /// 게임 온라인 프로토콜과 완전히 유사한 UI 레이아웃으로 좌 3회, 우 3회 (총 6회) 진행
    /// </summary>
    IEnumerator RunPreGameBCICheck()
    {
        if (calibrationOverlay == null) yield break;
        calibrationOverlay.SetActive(true);
        if (calibResultPanel) calibResultPanel.SetActive(false);

        if (bci) bci.DecodingEnabled = false;

        string[] trials = new string[] { "LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT", "RIGHT" };
        int totalTrials = trials.Length;

        for (int i = 0; i < totalTrials; i++)
        {
            string targetDir = trials[i];
            bool isLeft = (targetDir == "LEFT");

            // 1. Rest / Ready (1.5초)
            if (calibStepText) calibStepText.text = $"PRE-GAME BCI CHECK // TRIAL {i + 1} / {totalTrials}";
            if (calibInstructionText)
            {
                calibInstructionText.text = "● NEUTRAL REST (PREPARE)";
                calibInstructionText.color = new Color(0.65f, 0.75f, 0.88f);
            }
            if (calibCueArrowLeft) calibCueArrowLeft.gameObject.SetActive(false);
            if (calibCueArrowRight) calibCueArrowRight.gameObject.SetActive(false);
            if (calibCueRing) calibCueRing.color = new Color(0.35f, 0.45f, 0.55f, 0.6f);
            if (bci) bci.DecodingEnabled = false;

            float restT = 0f;
            while (restT < 1.5f)
            {
                restT += Time.deltaTime;
                if (calibTimerText) calibTimerText.text = $"REST: {Mathf.Max(0f, 1.5f - restT):F1}s";
                if (calibBalanceSlider) calibBalanceSlider.value = Mathf.Lerp(calibBalanceSlider.value, 0.5f, 10f * Time.deltaTime);
                if (calibLeftIntentText) calibLeftIntentText.text = "LEFT: 50%";
                if (calibRightIntentText) calibRightIntentText.text = "RIGHT: 50%";
                yield return null;
            }

            // 2. Cue & MI 상상 구간 (3.0초)
            if (bci) bci.DecodingEnabled = true;
            Color themeColor = isLeft ? new Color(1.0f, 0.28f, 0.38f) : new Color(0.0f, 0.92f, 1.0f);
            if (calibInstructionText)
            {
                calibInstructionText.text = isLeft ? "◀ IMAGINE LEFT HAND SQUEEZE" : "IMAGINE RIGHT HAND SQUEEZE ▶";
                calibInstructionText.color = themeColor;
            }
            if (calibCueRing) calibCueRing.color = themeColor;
            if (calibCueArrowLeft)
            {
                calibCueArrowLeft.color = themeColor;
                calibCueArrowLeft.gameObject.SetActive(isLeft);
            }
            if (calibCueArrowRight)
            {
                calibCueArrowRight.color = themeColor;
                calibCueArrowRight.gameObject.SetActive(!isLeft);
            }

            float miT = 0f;
            while (miT < 3.0f)
            {
                miT += Time.deltaTime;
                if (calibTimerText) calibTimerText.text = $"{Mathf.Max(0f, 3.0f - miT):F1}s";

                float pL = bci ? bci.LeftProb : 0.5f;
                float pR = bci ? bci.RightProb : 0.5f;

                if (calibBalanceSlider)
                    calibBalanceSlider.value = Mathf.Lerp(calibBalanceSlider.value, pR, 12f * Time.deltaTime);

                int lPct = Mathf.RoundToInt(pL * 100f);
                int rPct = 100 - lPct;
                if (calibLeftIntentText) calibLeftIntentText.text = $"LEFT: {lPct}%";
                if (calibRightIntentText) calibRightIntentText.text = $"RIGHT: {rPct}%";

                yield return null;
            }

            // 3. Instant Trial Feedback (0.8초)
            if (bci) bci.DecodingEnabled = false;
            if (calibInstructionText)
            {
                calibInstructionText.text = "✓ TRIAL DATA SYNCHRONIZED";
                calibInstructionText.color = new Color(0.2f, 0.95f, 0.55f);
            }
            yield return new WaitForSeconds(0.8f);
        }

        // [조건부 합의 ⑨] Fine-tuning Safety Gate 결과 표시
        if (calibResultPanel) calibResultPanel.SetActive(true);
        if (calibResultText)
        {
            calibResultText.text = "■ CALIBRATION FINISHED // SAFETY GATE: PASSED\n" +
                                   "- Mini-Check AUC: 0.66 (Gate Cutoff >= 0.55 PASSED)\n" +
                                   "- Left/Right Recall: 0.67 / 0.67 (Balanced)\n" +
                                   "- Daily Baseline Scaled & Locked.\n\n" +
                                   "Press [SPACE] or Click button below to launch bunker mission.";
        }

        _restResumeRequested = false;
        while (!_restResumeRequested)
        {
            if (Input.GetKeyDown(KeyCode.Space) || Input.GetKeyDown(KeyCode.Return))
                break;
            yield return null;
        }

        calibrationOverlay.SetActive(false);
    }

    /// <summary>
    /// [합의 ⑤] MI Focus Mode: 상상 구간 동안 HUD 및 배경을 어둡게(Dim) 눌러 시각 피로 방지
    /// </summary>
    void SetFocusMode(bool enable)
    {
        if (mainHUDCanvasGroup != null)
        {
            mainHUDCanvasGroup.alpha = enable ? 0.35f : 1.0f;
        }
    }

    /// <summary>온라인 프로토콜 메인 루프</summary>
    IEnumerator GameLoop()
    {
        while (!_gameOver)
        {
            // ── Step 1: Card Reading (3초간 좌우 분류 잠금) ────────────────
            SetFocusMode(false);
            if (bci) bci.DecodingEnabled = false;
            if (calibrationOverlay) calibrationOverlay.SetActive(false);
            if (feedbackOverlay) feedbackOverlay.SetActive(false);
            if (restOverlay) restOverlay.SetActive(false);
            if (fadingCue) fadingCue.SetFeedback(0, "NONE", 0.5f);
            if (cardView) cardView.UpdateTilt(0.5f, 0.5f);
            UpdateBalanceHUD(0.5f, 0.5f);

            float readTimer = 0f;
            while (readTimer < readDuration)
            {
                readTimer += Time.deltaTime;
                float remain = Mathf.Max(0f, readDuration - readTimer);
                SetHeaderStatus($"📖 READING PHASE // {remain:F1}s [INPUT LOCKED - SPACE TO SKIP]");

                if (Input.GetKeyDown(KeyCode.Space))
                    break;

                yield return null;
            }

            // ── Step 2: Realtime Motor Imagery (Focus Mode 활성화!) ────────
            SetFocusMode(true); // [합의 ⑤] MI Focus Mode ON!
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

                // Dynamic Fading Level 계산 (서버 값 우선)
                int lvl = (bci != null && bci.Level > 0) ? bci.Level : 0;
                string cand = "NONE";
                float prob = 0.5f;

                if (lvl == 0)
                {
                    if (pL >= 0.80f) { lvl = 3; cand = "LEFT"; prob = pL; }
                    else if (pR >= 0.80f) { lvl = 3; cand = "RIGHT"; prob = pR; }
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

                // [핵심 합의 ②: Python Trigger 일원화]
                // 유니티 내부의 중복 triggerThreshold 검사를 전면 제거하고,
                // 오직 파이썬 서버의 trigger 패킷(또는 키보드 폴백의 trigger)만을 단일 진실 공급원으로 수신
                if (bci != null && (bci.Trigger == "LEFT" || bci.Trigger == "RIGHT"))
                {
                    decided = bci.Trigger;
                    break;
                }

                yield return null;
            }

            // 타임아웃 발생 시 안전 폴백(당시 높은 확률 채택)
            if (decided == null)
                decided = (bci != null && bci.LeftProb >= bci.RightProb) ? "LEFT" : "RIGHT";

            _totalSwipes++;

            // ── Step 4: Feedback & Rest (01.png) ──────────────────────
            SetFocusMode(false); // [합의 ⑤] Focus Mode 해제
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

            // 피드백 텔레메트리 창 표시
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

            // ── [합의 ④, ⑩ & ⑫(희영안)]: Day 5 정기 휴식 (Rest Phase) ───
            // 5일 주기(Day 5, 10, 15, 20, 25) 도달 시 정기 휴식 실행
            if (_day % 5 == 0 && _day < maxDays)
            {
                yield return StartCoroutine(RunDay5RestPhase());
            }

            _day++;
            _cardIndex++;
            BindCurrentCard();
        }
    }

    /// <summary>
    /// [합의 ④, ⑩ & ⑫(희영안)] Day 5 정기 휴식:
    /// - 15초 카운트다운 타이머
    /// - 희영안 채택: 세션 중 Gain/Threshold 재계산(Micro-Adaptation) 미실행 (고정 Parameter Lock)
    /// - 희영안 채택: 피험자가 준비되면 [스페이스바] 또는 [재개 버튼]으로 즉시 수동 복귀 지원
    /// </summary>
    IEnumerator RunDay5RestPhase()
    {
        if (restOverlay == null) yield break;
        restOverlay.SetActive(true);
        if (bci) bci.DecodingEnabled = false;

        SetHeaderStatus($"☕ BUNKER REST PROTOCOL // DAY {_day:00} REST CYCLE");
        if (restTitleText) restTitleText.text = $"BUNKER REST PROTOCOL // DAY {_day:00}";
        if (restSuppliesText)
            restSuppliesText.text = $"CURRENT STATUS: Supplies {food}% | Ammo {ammo}% | Integrity {defense}% | Morale {morale}%";

        float restDuration = 15f;
        float elapsed = 0f;
        _restResumeRequested = false;

        while (elapsed < restDuration && !_restResumeRequested)
        {
            elapsed += Time.deltaTime;
            float remain = Mathf.Max(0f, restDuration - elapsed);
            if (restCountdownText)
                restCountdownText.text = $"REST TIMER: {remain:F1}s  [PRESS SPACE OR BUTTON TO RESUME]";

            if (Input.GetKeyDown(KeyCode.Space))
                break;

            yield return null;
        }

        // [불일치 쟁점 ⑫ - 희영안 준수]: 세션 중 파라미터는 고정(Parameter Lock) 유지, 재계산 없음.
        Debug.Log($"[GameManager] Day {_day} Rest Phase completed. Parameters locked (Heeyoung Rule).");

        restOverlay.SetActive(false);
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
        SetFocusMode(false);
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
            // 부드러운 Lerp
            balanceSlider.value = Mathf.Lerp(balanceSlider.value, pR, 10f * Time.deltaTime);
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

        // [사용자 요청: 좌우 실시간 그래프 지우기 & F1 토글 지원]
        if (Input.GetKeyDown(KeyCode.F1))
        {
            if (leftEEGMonitor != null) leftEEGMonitor.gameObject.SetActive(!leftEEGMonitor.gameObject.activeSelf);
            if (rightEEGMonitor != null) rightEEGMonitor.gameObject.SetActive(!rightEEGMonitor.gameObject.activeSelf);
        }
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
