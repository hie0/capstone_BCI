using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;

/// <summary>
/// CONTRA LABS // BCI-OS v1.09 군사 벙커 신경망 OS 부트스트랩.
/// ui참고 이미지 5장과 1:1로 정확하게 일치하는 화면 레이아웃을 코드로 구축한다.
/// - 상단: CONTRA LABS // BCI-OS v1.09 헤더 + 4대 자원 슬림 HUD
/// - 중앙: 좌측(LEFT MI), 중앙(벙커 원형 창문 생존자 카드), 우측(RIGHT MI) 3분할 뷰
/// - 하단: LEFT CONTROL INTENT, EEG DECISION BALANCE, RIGHT CONTROL INTENT 슬라이더
/// - 최하단: SYS.LOC // SECTOR-12 벙커 터미널 푸터
/// - 오버레이: Step 2 신경 보정(00.png), Step 4 결과 텔레메트리(01.png), 엔딩(02.png), 타이틀(03.png)
/// </summary>
[DefaultExecutionOrder(-100)]
public class UIBootstrap : MonoBehaviour
{
    // BCI-OS v1.09 하이테크 사이버네틱 컬러 팔레트 (전문 연구소/의료 BCI 무드)
    static readonly Color BG_DARK = new Color(0.045f, 0.058f, 0.088f);
    static readonly Color PANEL_BG = new Color(0.065f, 0.085f, 0.135f, 0.98f);
    static readonly Color LINE_DIVIDER = new Color(0.18f, 0.26f, 0.38f, 0.85f);

    static readonly Color CYAN = new Color(0.0f, 0.92f, 1.0f);
    static readonly Color CYAN_GLOW = new Color(0.0f, 0.75f, 0.95f, 0.70f);
    static readonly Color CYAN_DIM = new Color(0.0f, 0.65f, 0.75f, 0.45f);
    static readonly Color RED = new Color(1.0f, 0.28f, 0.38f);
    static readonly Color RED_GLOW = new Color(0.95f, 0.22f, 0.30f, 0.70f);
    static readonly Color RED_DIM = new Color(0.85f, 0.22f, 0.28f, 0.45f);

    static readonly Color AMBER = new Color(1.0f, 0.76f, 0.18f);
    static readonly Color GREEN = new Color(0.20f, 0.96f, 0.55f);

    static readonly Color TEXT_WHITE = new Color(0.98f, 0.99f, 1.0f);
    static readonly Color TEXT_MUTED = new Color(0.65f, 0.75f, 0.88f);
    static readonly Color TEXT_DARK = new Color(0.04f, 0.06f, 0.08f);

    private Font _font;

    void Awake()
    {
        _font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        if (_font == null) _font = Resources.GetBuiltinResource<Font>("Arial.ttf");
        if (_font == null)
        {
            try { _font = Font.CreateDynamicFontFromOSFont(new string[] { "Consolas", "Lucida Console", "Malgun Gothic", "Arial" }, 16); }
            catch { }
        }

        EnsureEventSystem();
        EnsureCamera();

        Canvas canvas = CreateCanvas();

        // ── 0. 배경 및 모니터 주사선 ───────────────────────────────────
        CreateImage(canvas.transform, "DeepBG", BG_DARK, Stretch());

        // 비네트 (외곽 어두움)
        var vignette = CreateImage(canvas.transform, "Vignette", Color.white, Stretch());
        vignette.sprite = UIAssetFactory.GetVignette(256);
        vignette.raycastTarget = false;

        // CRT 스캔라인 (텍스트 번짐/흐릿함 방지를 위해 기본 비활성화)
        // var scanline = CreateImage(canvas.transform, "Scanlines", new Color(1f, 1f, 1f, 0.4f), Stretch());
        // scanline.sprite = UIAssetFactory.GetScanline();
        // scanline.type = Image.Type.Tiled;
        // scanline.raycastTarget = false;

        // 화면 가로 격자 가이드 라인 (04.png 배경 느낌)
        CreateHorizontalLine(canvas.transform, 305f);
        CreateHorizontalLine(canvas.transform, -180f);
        CreateHorizontalLine(canvas.transform, -320f);

        // ── 1. 글로벌 헤더 (04.png 상단) ──────────────────────────────
        var headerGroup = CreateEmpty(canvas.transform, "GlobalHeader",
            Anchored(new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0, -14), new Vector2(1220, 36)));

        // 좌측 타이틀: ☢ CONTRA LABS // BCI-OS v1.09
        var brand = CreateText(headerGroup.transform, "Brand", "☢  CONTRA LABS // BCI-OS v1.09", 14, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero, new Vector2(360, 24)));
        brand.fontStyle = FontStyle.Bold;
        brand.color = CYAN;

        // 우측 상태 라벨
        Text headerStatus = CreateText(headerGroup.transform, "Status", "LIVE OPERATIONAL SECTOR", 12, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 0.5f), new Vector2(1, 0.5f), new Vector2(-140, 0), new Vector2(320, 24)));
        headerStatus.fontStyle = FontStyle.Bold;
        headerStatus.color = CYAN;

        // 우측 SECURE LINK 뱃지 버튼
        var secLink = CreatePanel(headerGroup.transform, "SecureLink", new Color(0.04f, 0.08f, 0.12f, 0.9f),
            Anchored(new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(120, 26)));
        secLink.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 6, new Color(0.04f, 0.08f, 0.12f, 0.9f), CYAN_DIM, 1);
        secLink.GetComponent<Image>().type = Image.Type.Sliced;
        var secText = CreateText(secLink.transform, "Text", "SECURE LINK", 11, TextAnchor.MiddleCenter, Stretch());
        secText.fontStyle = FontStyle.Bold;
        secText.color = CYAN;

        // ── 2. 상단 4대 자원 HUD 바 (시인성 극대화 위젯형 대시보드) ─────────
        var metersGroup = CreateEmpty(canvas.transform, "MetersHUD",
            Anchored(new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0, -66), new Vector2(1220, 60)));

        Slider foodBar, ammoBar, defBar, moraleBar;
        Text foodVal, ammoVal, defVal, moraleVal;
        CreateMeterBox(metersGroup.transform, 0, "♨ SUPPLIES", GREEN, out foodBar, out foodVal);
        CreateMeterBox(metersGroup.transform, 1, "⚡ AMMO CAPACITY", AMBER, out ammoBar, out ammoVal);
        CreateMeterBox(metersGroup.transform, 2, "🛡 SHELTER INTEGRITY", CYAN, out defBar, out defVal);
        CreateMeterBox(metersGroup.transform, 3, "👤 SURVIVOR MORALE", new Color(0.95f, 0.45f, 0.95f), out moraleBar, out moraleVal);

        // ── 3. 메인 게임플레이 3분할 뷰 ─────────────────────────────
        // 3-1) 좌측 패널: ← LEFT MOTOR IMAGERY
        var leftPanelGo = CreatePanel(canvas.transform, "LeftMIPanel", PANEL_BG,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-425, 45), new Vector2(285, 165)));
        var leftPanelImg = leftPanelGo.GetComponent<Image>();
        leftPanelImg.sprite = UIAssetFactory.GetTechPanel(32, 10, PANEL_BG, RED_GLOW, 2);
        leftPanelImg.type = Image.Type.Sliced;

        var leftHeader = CreateText(leftPanelGo.transform, "Header", "←  LEFT MOTOR IMAGERY", 13, TextAnchor.UpperLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -14), new Vector2(244, 20)));
        leftHeader.fontStyle = FontStyle.Bold;
        leftHeader.color = RED;

        var leftAction = CreateText(leftPanelGo.transform, "Action", "문을 열지 않는다", 18, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -44), new Vector2(244, 36)));
        leftAction.fontStyle = FontStyle.Bold;
        leftAction.color = TEXT_WHITE;

        var leftSub = CreateText(leftPanelGo.transform, "Sub", "Imagine Left-Hand squeeze to reject.", 11, TextAnchor.UpperLeft,
            Anchored(new Vector2(0, 0), new Vector2(0, 0), new Vector2(18, 14), new Vector2(244, 46)));
        leftSub.color = TEXT_MUTED;
        leftSub.lineSpacing = 1.25f;

        // 좌측 실시간 뇌파 오실로스코프 모니터 (C4: Left Hand MI)
        var leftEEG = CreateEEGMonitor(canvas.transform, "LeftEEGMonitor", "C4: LEFT-HAND", RED, new Vector2(-425, -88));

        // 3-2) 중앙 생존자 카드 (벙커 원형 창문 + 대사창)
        var cardRoot = CreateEmpty(canvas.transform, "CenterCardRoot",
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -6), new Vector2(450, 390)));
        RectTransform cardRect = cardRoot.GetComponent<RectTransform>();

        // 카드 외곽 드롭 섀도우 & 네온 글로우
        var cardShadow = CreateImage(cardRoot.transform, "Shadow", Color.white,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -6), new Vector2(480, 420)));
        cardShadow.sprite = UIAssetFactory.GetGlow(64, new Color(0, 0, 0, 0.90f));
        cardShadow.type = Image.Type.Sliced;
        cardShadow.raycastTarget = false;

        // 카드 본체
        var cardBody = CreatePanel(cardRoot.transform, "CardBody", new Color(0.075f, 0.095f, 0.15f, 0.99f), Stretch());
        cardBody.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 12, new Color(0.075f, 0.095f, 0.15f, 0.99f), new Color(0.24f, 0.36f, 0.52f, 0.9f), 2);
        cardBody.GetComponent<Image>().type = Image.Type.Sliced;

        // 상단 카테고리 태그 뱃지: [ CIVILIAN AT GATES ]
        var catBadge = CreatePanel(cardBody.transform, "CatBadge", new Color(0.14f, 0.11f, 0.05f, 0.95f),
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -14), new Vector2(175, 26)));
        catBadge.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 4, new Color(0.14f, 0.11f, 0.05f, 0.95f), AMBER, 1);
        catBadge.GetComponent<Image>().type = Image.Type.Sliced;

        var catText = CreateText(catBadge.transform, "Text", "[ CIVILIAN AT GATES ]", 11, TextAnchor.MiddleCenter, Stretch());
        catText.fontStyle = FontStyle.Bold;
        catText.color = AMBER;

        // 중앙 벙커 잠망경/창문 (Porthole)
        var portholeGo = CreateImage(cardBody.transform, "Porthole", Color.white,
            Anchored(new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -42), new Vector2(190, 190)));
        portholeGo.sprite = UIAssetFactory.GetBunkerPorthole(256);

        // 창문 내부 캐릭터 아바타
        var avatar = CreateText(portholeGo.transform, "Avatar", "👤", 60, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(120, 120)));

        // 하단 화자 이름: NAME: HELENA (SURVIVOR)
        var speakerText = CreateText(cardBody.transform, "Speaker", "NAME: HELENA (SURVIVOR)", 13, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 0), new Vector2(0, 0), new Vector2(22, 102), new Vector2(400, 22)));
        speakerText.fontStyle = FontStyle.Bold;
        speakerText.color = CYAN;

        // 하단 전용 스토리 대사창 패널 (가독성 100% 보장 음각 박스)
        var promptBox = CreatePanel(cardBody.transform, "PromptBox", new Color(0.04f, 0.05f, 0.085f, 0.95f),
            Anchored(new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 14), new Vector2(414, 82)));
        promptBox.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(16, 4, new Color(0.04f, 0.05f, 0.085f, 0.95f), LINE_DIVIDER, 1);
        promptBox.GetComponent<Image>().type = Image.Type.Sliced;

        var promptText = CreateText(promptBox.transform, "Prompt", "\"쉘터 밖에서 아이를 안은 생존자가 문을 열어달라고 요청하고 있습니다. 문을 열어줄까요?\"", 14, TextAnchor.UpperLeft,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(390, 68)));
        promptText.color = TEXT_WHITE;
        promptText.lineSpacing = 1.35f;

        // 중앙 상단 neuro_feedback3 Dynamic Fading CUE 인터페이스
        var cuePanel = CreatePanel(canvas.transform, "DynamicFadingCuePanel", PANEL_BG,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 226), new Vector2(450, 48)));
        cuePanel.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 6, PANEL_BG, CYAN_GLOW, 2);
        cuePanel.GetComponent<Image>().type = Image.Type.Sliced;

        // CUE 원형 점선 링 (Level 0)
        var dashedRingImg = CreateImage(cuePanel.transform, "DashedRing", DynamicFadingCue.COLOR_LEVEL0,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-15, 0), new Vector2(38, 38)));
        dashedRingImg.sprite = UIAssetFactory.GetDashedRing(256, 16, 4f);

        // CUE 채움 아크 링 (Level 1~3)
        var fillRingImg = CreateImage(cuePanel.transform, "FillRing", DynamicFadingCue.COLOR_LEVEL1,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-15, 0), new Vector2(38, 38)));
        fillRingImg.sprite = UIAssetFactory.GetRingSprite(256, 6f);
        fillRingImg.type = Image.Type.Filled;
        fillRingImg.fillMethod = Image.FillMethod.Radial360;
        fillRingImg.fillOrigin = (int)Image.Origin360.Top;
        fillRingImg.fillClockwise = true;
        fillRingImg.fillAmount = 0f;
        fillRingImg.gameObject.SetActive(false);

        // CUE 방향 화살표들
        var leftArrowImg = CreateImage(cuePanel.transform, "LeftArrow", DynamicFadingCue.COLOR_LEFT,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-15, 0), new Vector2(22, 16)));
        leftArrowImg.sprite = UIAssetFactory.GetArrowSprite(96, 64, true);
        leftArrowImg.gameObject.SetActive(false);

        var rightArrowImg = CreateImage(cuePanel.transform, "RightArrow", DynamicFadingCue.COLOR_RIGHT,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-15, 0), new Vector2(22, 16)));
        rightArrowImg.sprite = UIAssetFactory.GetArrowSprite(96, 64, false);
        rightArrowImg.gameObject.SetActive(false);

        // CUE 좌측 레벨 뱃지
        var lvlBadge = CreatePanel(cuePanel.transform, "LvlBadge", new Color(0.09f, 0.13f, 0.19f, 0.95f),
            Anchored(new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(10, 0), new Vector2(66, 30)));
        lvlBadge.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(16, 3, new Color(0.09f, 0.13f, 0.19f, 0.95f), LINE_DIVIDER, 1);
        lvlBadge.GetComponent<Image>().type = Image.Type.Sliced;
        var lvlText = CreateText(lvlBadge.transform, "Text", "LVL 0", 12, TextAnchor.MiddleCenter, Stretch());
        lvlText.fontStyle = FontStyle.Bold;
        lvlText.color = DynamicFadingCue.COLOR_LEVEL0;

        // CUE 우측 상태 라벨
        var cueStateText = CreateText(cuePanel.transform, "StateText", "● NEUTRAL STATE (SEARCHING)", 12, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0, 0.5f), new Vector2(18, 0), new Vector2(195, 30)));
        cueStateText.fontStyle = FontStyle.Bold;
        cueStateText.color = DynamicFadingCue.COLOR_LEVEL0;

        var fadingCue = cuePanel.AddComponent<DynamicFadingCue>();
        fadingCue.dashedRing = dashedRingImg;
        fadingCue.activeFillRing = fillRingImg;
        fadingCue.leftArrow = leftArrowImg;
        fadingCue.rightArrow = rightArrowImg;
        fadingCue.levelText = lvlText;
        fadingCue.stateText = cueStateText;

        // 3-3) 우측 패널: RIGHT MOTOR IMAGERY →
        var rightPanelGo = CreatePanel(canvas.transform, "RightMIPanel", PANEL_BG,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(425, 45), new Vector2(285, 165)));
        var rightPanelImg = rightPanelGo.GetComponent<Image>();
        rightPanelImg.sprite = UIAssetFactory.GetTechPanel(32, 10, PANEL_BG, CYAN_GLOW, 2);
        rightPanelImg.type = Image.Type.Sliced;

        var rightHeader = CreateText(rightPanelGo.transform, "Header", "RIGHT MOTOR IMAGERY  →", 13, TextAnchor.UpperLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -14), new Vector2(244, 20)));
        rightHeader.fontStyle = FontStyle.Bold;
        rightHeader.color = CYAN;

        var rightAction = CreateText(rightPanelGo.transform, "Action", "생존자를 받아들인다", 18, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -44), new Vector2(244, 36)));
        rightAction.fontStyle = FontStyle.Bold;
        rightAction.color = TEXT_WHITE;

        var rightSub = CreateText(rightPanelGo.transform, "Sub", "Imagine Right-Hand squeeze to accept.", 11, TextAnchor.UpperLeft,
            Anchored(new Vector2(0, 0), new Vector2(0, 0), new Vector2(18, 14), new Vector2(244, 46)));
        rightSub.color = TEXT_MUTED;
        rightSub.lineSpacing = 1.25f;

        var rightStatus = CreateText(rightPanelGo.transform, "Status", "● COGNITIVE LINK READY", 10, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 0), new Vector2(0, 0), new Vector2(18, 2), new Vector2(244, 16)));
        rightStatus.fontStyle = FontStyle.Bold;
        rightStatus.color = CYAN;

        // 우측 실시간 뇌파 오실로스코프 모니터 (C3: Right Hand MI)
        var rightEEG = CreateEEGMonitor(canvas.transform, "RightEEGMonitor", "C3: RIGHT-HAND", CYAN, new Vector2(425, -88));


        // ── 4. 하단 밸런스 HUD & 슬라이더 ─────────────────────────────
        var balanceGroup = CreateEmpty(canvas.transform, "BalanceGroup",
            Anchored(new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 56), new Vector2(1220, 54)));

        // 상단 인텐트 레이블 3종
        Text leftIntent = CreateText(balanceGroup.transform, "LeftIntent", "LEFT CONTROL INTENT: 50%", 13, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 0), new Vector2(320, 20)));
        leftIntent.fontStyle = FontStyle.Bold;
        leftIntent.color = RED;

        Text centerLabel = CreateText(balanceGroup.transform, "CenterLabel", "⚡ EEG DECISION BALANCE ⚡", 13, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, 0), new Vector2(320, 20)));
        centerLabel.fontStyle = FontStyle.Bold;
        centerLabel.color = CYAN;

        Text rightIntent = CreateText(balanceGroup.transform, "RightIntent", "RIGHT CONTROL INTENT: 50%", 13, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(0, 0), new Vector2(320, 20)));
        rightIntent.fontStyle = FontStyle.Bold;
        rightIntent.color = CYAN;

        // 밸런스 슬라이더 트랙 (1220 x 18로 확대)
        var balTrack = CreatePanel(balanceGroup.transform, "Track", new Color(0.04f, 0.06f, 0.09f, 0.98f),
            Anchored(new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 4), new Vector2(1220, 18)));
        balTrack.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 6, new Color(0.04f, 0.06f, 0.09f, 0.98f), LINE_DIVIDER, 1);
        balTrack.GetComponent<Image>().type = Image.Type.Sliced;

        // 중앙 기준선
        CreateImage(balTrack.transform, "CenterDivider", new Color(1f, 1f, 1f, 0.4f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(2, 18)));

        // 슬라이더 커서 블록 (더 크고 뚜렷한 네온 블록)
        var balCursor = CreatePanel(balTrack.transform, "Cursor", CYAN,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(24, 18)));
        balCursor.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(16, 3, CYAN, Color.white, 2);
        balCursor.GetComponent<Image>().type = Image.Type.Sliced;


        var balSlider = balTrack.AddComponent<Slider>();
        balSlider.transition = Selectable.Transition.None;
        balSlider.targetGraphic = balCursor.GetComponent<Image>();
        balSlider.handleRect = balCursor.GetComponent<RectTransform>();
        balSlider.minValue = 0f; balSlider.maxValue = 1f; balSlider.value = 0.5f;

        // ── 5. 최하단 터미널 푸터 라인 (04.png) ────────────────────────
        var footerGroup = CreateEmpty(canvas.transform, "TerminalFooter",
            Anchored(new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 10), new Vector2(1220, 20)));

        var footLoc = CreateText(footerGroup.transform, "Location", "SYS.LOC // SECTOR-12 // bunker_command_terminal", 11, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero, new Vector2(400, 20)));
        footLoc.color = new Color(0.38f, 0.46f, 0.56f);

        var footAnt = CreateText(footerGroup.transform, "Antenna", "ANTENNA: OUTPOST_GAMMA   <color=#00E5FF>SIGNAL LOSS: 0.00%</color>", 11, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(400, 20)));
        footAnt.color = new Color(0.38f, 0.46f, 0.56f);

        // ── 6. Step 2 신경 보정 오버레이 (00.png) ─────────────────────
        var calibOverlay = CreatePanel(canvas.transform, "CalibrationOverlay", new Color(0.025f, 0.035f, 0.05f, 0.96f), Stretch());

        var calibNotice = CreateText(calibOverlay.transform, "Notice", "NEURAL SENSOR FEEDBACK INCOMING", 14, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 180), new Vector2(600, 24)));
        calibNotice.fontStyle = FontStyle.Bold;
        calibNotice.color = CYAN;

        var calibTitle = CreateText(calibOverlay.transform, "Title", "Focus and imagine LEFT or RIGHT hand movement", 24, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 145), new Vector2(800, 34)));
        calibTitle.fontStyle = FontStyle.Bold;
        calibTitle.color = TEXT_WHITE;

        // 원형 캘리브레이션 링
        var calibArc = CreateImage(calibOverlay.transform, "Arc", Color.white,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -10), new Vector2(240, 240)));
        calibArc.sprite = UIAssetFactory.GetCalibrationArc(256, CYAN);

        // 중앙 카운트다운 텍스트 ("3")
        var calibCount = CreateText(calibOverlay.transform, "Countdown", "3", 56, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -10), new Vector2(120, 120)));
        calibCount.fontStyle = FontStyle.Bold;
        calibCount.color = CYAN;

        // 하단 채널 전압 텔레메트리
        var calibTelem = CreateText(calibOverlay.transform, "Telem",
            "■ EEG-Ch1 [C3]: 7.4 uV    ■ EEG-Ch2 [C4]: 9.1 uV    SYSTEM STABLE // SYNCING...", 13, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -170), new Vector2(800, 24)));
        calibTelem.fontStyle = FontStyle.Bold;
        calibTelem.color = CYAN;
        calibOverlay.SetActive(false);

        // ── 7. Step 4 피드백 텔레메트리 오버레이 (01.png) ───────────────
        var feedbackOverlay = CreatePanel(canvas.transform, "FeedbackOverlay", new Color(0.03f, 0.04f, 0.06f, 0.94f), Stretch());

        // 좌측 TELEMETRY DELTA READOUT 박스
        var deltaBox = CreatePanel(feedbackOverlay.transform, "DeltaBox", new Color(0.05f, 0.07f, 0.10f, 0.95f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-360, -20), new Vector2(340, 200)));
        deltaBox.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 8, new Color(0.05f, 0.07f, 0.10f, 0.95f), LINE_DIVIDER, 1);
        deltaBox.GetComponent<Image>().type = Image.Type.Sliced;

        var deltaTitle = CreateText(deltaBox.transform, "Title", "TELEMETRY DELTA READOUT", 12, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -16), new Vector2(300, 20)));
        deltaTitle.fontStyle = FontStyle.Bold;
        deltaTitle.color = TEXT_MUTED;

        var deltaList = CreateText(deltaBox.transform, "List", "👥 Survivor Morale     +10%\n🍖 Supplies            -15%\n🛡 Shelter Integrity   +5%", 14, TextAnchor.UpperLeft,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -15), new Vector2(300, 120)));
        deltaList.fontStyle = FontStyle.Bold;
        deltaList.color = CYAN;
        deltaList.lineSpacing = 1.4f;

        // 우측 확정 뱃지: [ RIGHT ACTION ENGAGED // CONFIRMED ]
        var fbBadge = CreatePanel(feedbackOverlay.transform, "ActionBadge", new Color(0.04f, 0.08f, 0.12f, 0.95f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(260, 48), new Vector2(480, 48)));
        var fbBadgeImg = fbBadge.GetComponent<Image>();
        fbBadgeImg.sprite = UIAssetFactory.GetTechPanel(32, 6, new Color(0.04f, 0.08f, 0.12f, 0.95f), CYAN, 2);
        fbBadgeImg.type = Image.Type.Sliced;

        var fbBadgeText = CreateText(fbBadge.transform, "Text", "RIGHT ACTION ENGAGED // CONFIRMED", 14, TextAnchor.MiddleCenter, Stretch());
        fbBadgeText.fontStyle = FontStyle.Bold;
        fbBadgeText.color = CYAN;

        // 우측 LOG-SYSTEM ENGAGEMENT 박스
        var logBox = CreatePanel(feedbackOverlay.transform, "LogBox", new Color(0.05f, 0.07f, 0.10f, 0.95f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(260, -42), new Vector2(480, 100)));
        logBox.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 8, new Color(0.05f, 0.07f, 0.10f, 0.95f), LINE_DIVIDER, 1);
        logBox.GetComponent<Image>().type = Image.Type.Sliced;

        var logTitle = CreateText(logBox.transform, "Title", "LOG-SYSTEM ENGAGEMENT", 11, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -12), new Vector2(400, 18)));
        logTitle.fontStyle = FontStyle.Bold;
        logTitle.color = CYAN;

        var logText = CreateText(logBox.transform, "Text", "\"생존자를 받아들였습니다. 그녀는 간호사였습니다.\"", 15, TextAnchor.UpperLeft,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -10), new Vector2(444, 56)));
        logText.color = TEXT_WHITE;

        var fbWaitHint = CreateText(feedbackOverlay.transform, "WaitHint", "● WAITING FOR NEURAL FOCUS CYCLE [PRESS NEXT]", 12, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(260, -115), new Vector2(480, 20)));
        fbWaitHint.fontStyle = FontStyle.Bold;
        fbWaitHint.color = CYAN;
        feedbackOverlay.SetActive(false);

        // ── 8. 엔딩 오버레이 (02.png) ──────────────────────────────────
        var endingOverlay = CreatePanel(canvas.transform, "EndingOverlay", new Color(0.025f, 0.035f, 0.05f, 0.98f), Stretch());

        var endAlertTag = CreatePanel(endingOverlay.transform, "AlertTag", new Color(0.18f, 0.05f, 0.06f, 0.9f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 180), new Vector2(260, 28)));
        endAlertTag.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 4, new Color(0.18f, 0.05f, 0.06f, 0.9f), RED, 1);
        endAlertTag.GetComponent<Image>().type = Image.Type.Sliced;
        var endAlertText = CreateText(endAlertTag.transform, "Text", "SYS_SHIELD_ALERT // COMM_FAILURE", 11, TextAnchor.MiddleCenter, Stretch());
        endAlertText.fontStyle = FontStyle.Bold;
        endAlertText.color = RED;

        var endBigTitle = CreateText(endingOverlay.transform, "Title", "SHELTER FALLEN", 52, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 125), new Vector2(800, 60)));
        endBigTitle.fontStyle = FontStyle.Bold;
        endBigTitle.color = RED;

        var endSubtitle = CreateText(endingOverlay.transform, "Subtitle", "The gates were compromised. The signals are quiet now.", 16, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 75), new Vector2(800, 26)));
        endSubtitle.color = TEXT_MUTED;

        // 결산 좌측: SURVIVAL LOGS
        var survLogsBox = CreatePanel(endingOverlay.transform, "SurvLogs", new Color(0.05f, 0.07f, 0.10f, 0.95f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-190, -35), new Vector2(340, 150)));
        survLogsBox.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 8, new Color(0.05f, 0.07f, 0.10f, 0.95f), LINE_DIVIDER, 1);
        survLogsBox.GetComponent<Image>().type = Image.Type.Sliced;

        CreateText(survLogsBox.transform, "Head", "SURVIVAL LOGS", 11, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -14), new Vector2(200, 18))).color = TEXT_MUTED;

        CreateText(survLogsBox.transform, "L1", "Days Survived", 14, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -45), new Vector2(160, 20))).color = TEXT_WHITE;
        var endDaysVal = CreateText(survLogsBox.transform, "V1", "30 Days", 15, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -45), new Vector2(120, 20)));
        endDaysVal.fontStyle = FontStyle.Bold; endDaysVal.color = TEXT_WHITE;

        CreateText(survLogsBox.transform, "L2", "BCI Commands Confirmed", 14, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -78), new Vector2(190, 20))).color = TEXT_WHITE;
        var endSwipesVal = CreateText(survLogsBox.transform, "V2", "124 Swipes", 15, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -78), new Vector2(120, 20)));
        endSwipesVal.fontStyle = FontStyle.Bold; endSwipesVal.color = TEXT_WHITE;

        CreateText(survLogsBox.transform, "L3", "Shelter Population", 14, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -110), new Vector2(160, 20))).color = TEXT_WHITE;
        var endPopVal = CreateText(survLogsBox.transform, "V3", "42 Saved", 15, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -110), new Vector2(120, 20)));
        endPopVal.fontStyle = FontStyle.Bold; endPopVal.color = TEXT_WHITE;

        // 결산 우측: FINAL METRICS
        var finalMetricsBox = CreatePanel(endingOverlay.transform, "FinalMetrics", new Color(0.05f, 0.07f, 0.10f, 0.95f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(190, -35), new Vector2(340, 150)));
        finalMetricsBox.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 8, new Color(0.05f, 0.07f, 0.10f, 0.95f), LINE_DIVIDER, 1);
        finalMetricsBox.GetComponent<Image>().type = Image.Type.Sliced;

        CreateText(finalMetricsBox.transform, "Head", "FINAL METRICS", 11, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -14), new Vector2(200, 18))).color = TEXT_MUTED;

        CreateText(finalMetricsBox.transform, "L1", "🍖 Supplies", 14, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -45), new Vector2(160, 20))).color = TEXT_WHITE;
        var endFinalSupplies = CreateText(finalMetricsBox.transform, "V1", "15%", 14, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -45), new Vector2(80, 20)));
        endFinalSupplies.fontStyle = FontStyle.Bold; endFinalSupplies.color = TEXT_WHITE;

        CreateText(finalMetricsBox.transform, "L2", "🛡 Shelter Integrity", 14, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(20, -85), new Vector2(160, 20))).color = TEXT_WHITE;
        var endFinalIntegrity = CreateText(finalMetricsBox.transform, "V2", "0%", 14, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -85), new Vector2(80, 20)));
        endFinalIntegrity.fontStyle = FontStyle.Bold; endFinalIntegrity.color = RED;

        // 재시작 버튼: [ COGNITIVE SYNC [RESTART SYSTEM] ]
        var restartBtnGo = CreatePanel(endingOverlay.transform, "RestartBtn", new Color(0.04f, 0.08f, 0.12f, 0.95f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -150), new Vector2(380, 48)));
        restartBtnGo.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 6, new Color(0.04f, 0.08f, 0.12f, 0.95f), CYAN, 2);
        restartBtnGo.GetComponent<Image>().type = Image.Type.Sliced;

        var restartBtnTxt = CreateText(restartBtnGo.transform, "Text", "COGNITIVE SYNC [RESTART SYSTEM]", 14, TextAnchor.MiddleCenter, Stretch());
        restartBtnTxt.fontStyle = FontStyle.Bold;
        restartBtnTxt.color = CYAN;
        var restartBtn = restartBtnGo.AddComponent<Button>();
        endingOverlay.SetActive(false);

        // ── 9. 타이틀 시작 화면 (03.png) ───────────────────────────────
        var titleOverlay = CreatePanel(canvas.transform, "TitleScreen", new Color(0.035f, 0.045f, 0.065f, 0.98f), Stretch());

        var titleCategory = CreateText(titleOverlay.transform, "Cat", "BCI APOCALYPSE DECISION SYSTEMS", 14, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 150), new Vector2(600, 24)));
        titleCategory.fontStyle = FontStyle.Bold;
        titleCategory.color = CYAN;

        var titleLogo = CreateText(titleOverlay.transform, "Logo", "DEAD  SIGNAL", 54, TextAnchor.MiddleCenter,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 95), new Vector2(800, 68)));
        titleLogo.fontStyle = FontStyle.Bold;
        titleLogo.color = TEXT_WHITE;

        // 청록빛 가로 분할선
        var titleDiv = CreateImage(titleOverlay.transform, "Divider", CYAN,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 52), new Vector2(300, 2)));

        // 장치 상태 박스
        var devStatusBox = CreatePanel(titleOverlay.transform, "DeviceBox", new Color(0.04f, 0.07f, 0.10f, 0.95f),
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -30), new Vector2(520, 110)));
        devStatusBox.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 8, new Color(0.04f, 0.07f, 0.10f, 0.95f), CYAN, 1);
        devStatusBox.GetComponent<Image>().type = Image.Type.Sliced;

        var devStatusLine1 = CreateText(devStatusBox.transform, "L1", "● EEG DEVICE STATUS: ONLINE", 13, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(22, -16), new Vector2(280, 20)));
        devStatusLine1.fontStyle = FontStyle.Bold; devStatusLine1.color = CYAN;

        var devConnTag = CreateText(devStatusBox.transform, "Tag", "BCI CONNECTED", 11, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(-22, -16), new Vector2(160, 20)));
        devConnTag.color = CYAN;

        var devStatusLine2 = CreateText(devStatusBox.transform, "L2", "SIGNAL QUALITY: 98.4% (EXCELLENT)\nMOTOR IMAGERY CALIBRATION: ACTIVE (LEFT/RIGHT)", 12, TextAnchor.UpperLeft,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -18), new Vector2(476, 42)));
        devStatusLine2.color = TEXT_MUTED;
        devStatusLine2.lineSpacing = 1.3f;

        // 시작 버튼: [ ENTER COMMAND CODES [START GAME] ]
        var startBtnGo = CreatePanel(titleOverlay.transform, "StartBtn", CYAN,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -130), new Vector2(460, 52)));
        startBtnGo.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 6, CYAN, Color.white, 1);
        startBtnGo.GetComponent<Image>().type = Image.Type.Sliced;

        var startBtnTxt = CreateText(startBtnGo.transform, "Text", "ENTER COMMAND CODES [START GAME]", 15, TextAnchor.MiddleCenter, Stretch());
        startBtnTxt.fontStyle = FontStyle.Bold;
        startBtnTxt.color = TEXT_DARK;
        var startBtn = startBtnGo.AddComponent<Button>();

        // ── 10. 컴포넌트 배선 ──────────────────────────────────────────
        var bci = gameObject.AddComponent<BCIClient>();

        var cardView = cardRoot.AddComponent<CardView>();
        cardView.cardRect = cardRect;
        cardView.categoryBadgeText = catText;
        cardView.speakerNameText = speakerText;
        cardView.promptText = promptText;
        cardView.avatarText = avatar;

        cardView.leftPanelBg = leftPanelImg;
        cardView.leftPanelBorder = leftPanelImg;
        cardView.leftHeader = leftHeader;
        cardView.leftActionText = leftAction;
        cardView.leftSubText = leftSub;

        cardView.rightPanelBg = rightPanelImg;
        cardView.rightPanelBorder = rightPanelImg;
        cardView.rightHeader = rightHeader;
        cardView.rightActionText = rightAction;
        cardView.rightSubText = rightSub;
        cardView.rightStatusText = rightStatus;

        var gm = gameObject.AddComponent<GameManager>();
        gm.bci = bci;
        gm.cardView = cardView;
        gm.headerStatusText = headerStatus;
        gm.dayText = null;

        gm.foodBar = foodBar; gm.foodVal = foodVal;
        gm.ammoBar = ammoBar; gm.ammoVal = ammoVal;
        gm.defenseBar = defBar; gm.defenseVal = defVal;
        gm.moraleBar = moraleBar; gm.moraleVal = moraleVal;

        gm.leftIntentText = leftIntent;
        gm.rightIntentText = rightIntent;
        gm.balanceSlider = balSlider;
        gm.balanceCursor = balCursor.GetComponent<RectTransform>();

        // [추가] 실시간 뇌파 시각화 컴포넌트 전달
        gm.fadingCue = fadingCue;
        gm.leftEEGMonitor = leftEEG;
        gm.rightEEGMonitor = rightEEG;

        gm.calibrationOverlay = calibOverlay;
        gm.calibrationCountdownText = calibCount;
        gm.calibrationArcRect = calibArc.GetComponent<RectTransform>();
        gm.calibrationTelemetryText = calibTelem;

        gm.feedbackOverlay = feedbackOverlay;
        gm.feedbackActionBadge = fbBadgeText;
        gm.feedbackActionBadgeBorder = fbBadgeImg;
        gm.feedbackDeltaList = deltaList;
        gm.feedbackLogText = logText;

        gm.endingOverlay = endingOverlay;
        gm.endingTagText = endAlertText;
        gm.endingBigTitle = endBigTitle;
        gm.endingSubtitle = endSubtitle;
        gm.endingDaysText = endDaysVal;
        gm.endingSwipesText = endSwipesVal;
        gm.endingPopulationText = endPopVal;
        gm.endingFinalSuppliesText = endFinalSupplies;
        gm.endingFinalIntegrityText = endFinalIntegrity;
        gm.restartButton = restartBtn;

        gm.titleScreen = titleOverlay;
        gm.startButton = startBtn;
    }

    // ───────────────────────── 헬퍼들 ─────────────────────────

    void EnsureEventSystem()
    {
#if UNITY_2023_1_OR_NEWER
        if (FindFirstObjectByType<EventSystem>() == null)
#else
        if (FindObjectOfType<EventSystem>() == null)
#endif
        {
            var es = new GameObject("EventSystem");
            es.AddComponent<EventSystem>();
            es.AddComponent<StandaloneInputModule>();
        }
    }

    void EnsureCamera()
    {
        if (Camera.main == null)
        {
            var camGo = new GameObject("Main Camera");
            camGo.tag = "MainCamera";
            var cam = camGo.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = BG_DARK;
            cam.orthographic = true;
        }
    }

    Canvas CreateCanvas()
    {
        var go = new GameObject("Canvas");
        var canvas = go.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        var scaler = go.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1280, 720);
        scaler.matchWidthOrHeight = 0.5f;
        scaler.dynamicPixelsPerUnit = 2.5f;
        go.AddComponent<GraphicRaycaster>();
        return canvas;
    }

    EEGWaveformMonitor CreateEEGMonitor(Transform parent, string name, string chName, Color waveColor, Vector2 pos)
    {
        var panel = CreatePanel(parent, name, PANEL_BG,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), pos, new Vector2(285, 86)));
        Color stroke = new Color(waveColor.r, waveColor.g, waveColor.b, 0.55f);
        panel.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 6, PANEL_BG, stroke, 1);
        panel.GetComponent<Image>().type = Image.Type.Sliced;

        // 상단 헤더 라인
        var header = CreateText(panel.transform, "Header", $"■ EEG-Ch [{chName}] REAL-TIME", 11, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(12, -4), new Vector2(175, 18)));
        header.fontStyle = FontStyle.Bold;
        header.color = waveColor;

        var volt = CreateText(panel.transform, "Voltage", "8.5 uV", 12, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(-12, -4), new Vector2(85, 18)));
        volt.fontStyle = FontStyle.Bold;
        volt.color = TEXT_WHITE;

        // 중앙 실시간 오실로스코프 캔버스
        var waveGo = new GameObject("WaveImage", typeof(RectTransform));
        waveGo.transform.SetParent(panel.transform, false);
        Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, -6), new Vector2(261, 48))(waveGo.GetComponent<RectTransform>());
        var rawImg = waveGo.AddComponent<RawImage>();

        var monitor = panel.AddComponent<EEGWaveformMonitor>();
        monitor.waveformImage = rawImg;
        monitor.channelNameText = header;
        monitor.voltageText = volt;
        monitor.channelName = chName;
        monitor.waveColor = waveColor;
        monitor.textureWidth = 261;
        monitor.textureHeight = 48;
        monitor.InitTexture();

        return monitor;
    }

    void CreateMeterBox(Transform parent, int index, string label, Color barColor,
        out Slider bar, out Text valText)
    {
        float t = (index + 0.5f) / 4f;
        // 박스 높이 58px로 대폭 확장, 선명한 하이테크 위젯 스타일
        var box = CreatePanel(parent, $"Meter_{index}", new Color(0.065f, 0.085f, 0.135f, 0.98f),
            Anchored(new Vector2(t, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(295, 58)));
        Color strokeCol = new Color(barColor.r, barColor.g, barColor.b, 0.55f);
        box.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(32, 6, new Color(0.065f, 0.085f, 0.135f, 0.98f), strokeCol, 1);
        box.GetComponent<Image>().type = Image.Type.Sliced;

        // 자원 아이콘 + 라벨 (12pt Bold)
        var lbl = CreateText(box.transform, "Label", label, 12, TextAnchor.MiddleLeft,
            Anchored(new Vector2(0, 1), new Vector2(0, 1), new Vector2(14, -6), new Vector2(170, 20)));
        lbl.fontStyle = FontStyle.Bold;
        lbl.color = barColor;

        // 큼직하고 시원한 퍼센트 수치 (19pt Bold)
        valText = CreateText(box.transform, "Val", "50%", 19, TextAnchor.MiddleRight,
            Anchored(new Vector2(1, 1), new Vector2(1, 1), new Vector2(-14, -6), new Vector2(90, 24)));
        valText.fontStyle = FontStyle.Bold;
        valText.color = TEXT_WHITE;

        // 하단 게이지 트랙 (높이 4px -> 8px로 2배 확대!)
        var trackBg = CreatePanel(box.transform, "TrackBg", new Color(0.03f, 0.04f, 0.07f, 1f),
            Anchored(new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 10), new Vector2(267, 10)));
        trackBg.GetComponent<Image>().sprite = UIAssetFactory.GetTechPanel(16, 3, new Color(0.03f, 0.04f, 0.07f, 1f), new Color(1f, 1f, 1f, 0.12f), 1);
        trackBg.GetComponent<Image>().type = Image.Type.Sliced;

        var fill = CreateImage(trackBg.transform, "Fill", barColor, Stretch());
        fill.sprite = UIAssetFactory.GetTechPanel(16, 2, barColor, Color.clear, 0);
        fill.type = Image.Type.Sliced;

        bar = trackBg.AddComponent<Slider>();
        bar.transition = Selectable.Transition.None;
        bar.targetGraphic = fill;
        bar.fillRect = fill.rectTransform;
        bar.direction = Slider.Direction.LeftToRight;
        bar.minValue = 0f; bar.maxValue = 1f; bar.value = 0.5f;
    }


    void CreateHorizontalLine(Transform parent, float posY)
    {
        var line = CreateImage(parent, "HLine", LINE_DIVIDER,
            Anchored(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, posY), new Vector2(1280, 1)));
        line.raycastTarget = false;
    }

    GameObject CreateEmpty(Transform parent, string name, System.Action<RectTransform> layout)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        layout(go.GetComponent<RectTransform>());
        return go;
    }

    GameObject CreatePanel(Transform parent, string name, Color color, System.Action<RectTransform> layout)
    {
        var img = CreateImage(parent, name, color, layout);
        return img.gameObject;
    }

    Image CreateImage(Transform parent, string name, Color color, System.Action<RectTransform> layout)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        var img = go.AddComponent<Image>();
        img.color = color;
        layout(go.GetComponent<RectTransform>());
        return img;
    }

    Text CreateText(Transform parent, string name, string content, int size, TextAnchor anchor,
        System.Action<RectTransform> layout)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        var t = go.AddComponent<Text>();
        t.font = _font;
        t.text = content;
        t.fontSize = size;
        t.alignment = anchor;
        t.color = TEXT_WHITE;
        t.horizontalOverflow = HorizontalWrapMode.Wrap;
        t.verticalOverflow = VerticalWrapMode.Overflow;
        t.raycastTarget = false;
        layout(go.GetComponent<RectTransform>());
        return t;
    }

    static System.Action<RectTransform> Stretch() => rt =>
    {
        rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one;
        rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero;
    };

    static System.Action<RectTransform> Anchored(Vector2 anchor, Vector2 pivot, Vector2 pos, Vector2 size) => rt =>
    {
        rt.anchorMin = anchor; rt.anchorMax = anchor;
        rt.pivot = pivot;
        rt.anchoredPosition = pos;
        rt.sizeDelta = size;
    };
}
