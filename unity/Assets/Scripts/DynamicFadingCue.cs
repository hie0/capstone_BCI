using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// neuro_feedback3_calibrated.py 의 OnlineTestUI(Dynamic Fading)를 유니티로 완벽하게 이식한 피드백 CUE 컴포넌트.
/// 
/// - Level 0: 중립 점선 원 (대기 / 탐색 상태)
/// - Level 1: 33% 진행 (연한 회색/청록 아크 + 방향 화살표)
/// - Level 2: 66% 진행 (중간 색상 + 뚜렷한 방향 화살표)
/// - Level 3: 100% 진행 임박 (강렬한 네온 원 + 화살표)
/// - SUCCESS / TRIGGER: 녹색 확정 펄스 (0, 175, 80)
/// - FAIL: 붉은색 실패 (191, 0, 0)
/// </summary>
public class DynamicFadingCue : MonoBehaviour
{
    [Header("UI 요소")]
    public Image dashedRing;       // Level 0 점선 링
    public Image activeFillRing;   // Level 1~3 채움 아크 링
    public Image leftArrow;        // ← 화살표
    public Image rightArrow;       // → 화살표
    public Text levelText;         // LEVEL 0 / 1 / 2 / 3
    public Text stateText;         // "NEUTRAL", "DETECTING LEFT", "LEFT ENGAGED", etc.

    // neuro_feedback3_calibrated.py 색상 팔레트
    public static readonly Color COLOR_LEVEL0 = new Color(0.35f, 0.45f, 0.55f, 0.6f);
    public static readonly Color COLOR_LEVEL1 = new Color(0.45f, 0.70f, 0.85f, 0.75f);
    public static readonly Color COLOR_LEVEL2 = new Color(0.0f, 0.85f, 1.0f, 0.95f);
    public static readonly Color COLOR_LEVEL3 = new Color(1.0f, 0.90f, 0.20f, 1.0f); // 황금색/하이라이트
    public static readonly Color COLOR_LEFT   = new Color(1.0f, 0.30f, 0.35f, 1.0f); // 레드 계열
    public static readonly Color COLOR_RIGHT  = new Color(0.0f, 0.90f, 1.0f, 1.0f); // 시안 계열
    public static readonly Color COLOR_SUCCESS = new Color(0.0f, 0.85f, 0.45f, 1.0f);
    public static readonly Color COLOR_FAIL    = new Color(0.95f, 0.20f, 0.25f, 1.0f);

    private int _currentLevel = 0;
    private string _currentCandidate = "NONE";
    private float _pulseTimer = 0f;

    void Update()
    {
        // 링의 미세한 회전 애니메이션으로 살아있는 뇌파 인터페이스 느낌 부여
        if (dashedRing != null)
        {
            dashedRing.rectTransform.Rotate(0, 0, -15f * Time.deltaTime);
        }

        // 레벨 3 또는 성공 상태일 때 펄스 효과
        if (_currentLevel >= 3 && activeFillRing != null)
        {
            _pulseTimer += Time.deltaTime * 6f;
            float scale = 1f + Mathf.Sin(_pulseTimer) * 0.05f;
            activeFillRing.rectTransform.localScale = new Vector3(scale, scale, 1f);
        }
        else if (activeFillRing != null)
        {
            activeFillRing.rectTransform.localScale = Vector3.one;
        }
    }

    /// <summary>
    /// neuro_feedback3_calibrated.py 로직에 따라 피드백을 실시간 갱신합니다.
    /// </summary>
    /// <param name="level">0 ~ 3 (또는 4)</param>
    /// <param name="candidate">"LEFT", "RIGHT", "NONE"</param>
    /// <param name="prob">해당 방향 확률 (0.0 ~ 1.0)</param>
    /// <param name="status">null, "SUCCESS", "FAIL"</param>
    public void SetFeedback(int level, string candidate, float prob, string status = null)
    {
        _currentLevel = level;
        _currentCandidate = candidate;

        bool isLeft = (candidate == "LEFT");
        bool isRight = (candidate == "RIGHT");

        // 1. 상태 텍스트 & 레벨 텍스트
        if (levelText != null)
        {
            levelText.text = (status == "SUCCESS") ? "LOCKED" : $"LVL {level}";
            levelText.color = (status == "SUCCESS") ? COLOR_SUCCESS : (isLeft ? COLOR_LEFT : (isRight ? COLOR_RIGHT : COLOR_LEVEL0));
        }

        if (stateText != null)
        {
            if (status == "SUCCESS")
            {
                stateText.text = $"[ {candidate} TRIGGER CONFIRMED ]";
                stateText.color = COLOR_SUCCESS;
            }
            else if (status == "FAIL")
            {
                stateText.text = "[ MI DECODING FAILED ]";
                stateText.color = COLOR_FAIL;
            }
            else if (level == 0 || candidate == "NONE")
            {
                stateText.text = "● NEUTRAL STATE (SEARCHING)";
                stateText.color = COLOR_LEVEL0;
            }
            else
            {
                int pct = Mathf.RoundToInt(prob * 100f);
                stateText.text = $"▶ {candidate} INTENT: {pct}% (LVL {level})";
                stateText.color = isLeft ? COLOR_LEFT : COLOR_RIGHT;
            }
        }

        // 2. Level 0 vs Level 1~3 시각 처리
        if (level == 0 && status == null)
        {
            if (dashedRing != null) { dashedRing.gameObject.SetActive(true); dashedRing.color = COLOR_LEVEL0; }
            if (activeFillRing != null) activeFillRing.gameObject.SetActive(false);
            if (leftArrow != null) leftArrow.gameObject.SetActive(false);
            if (rightArrow != null) rightArrow.gameObject.SetActive(false);
            return;
        }

        // Level 1 이상: 점선 링 유지하되 activeFillRing 활성화
        if (dashedRing != null)
        {
            dashedRing.gameObject.SetActive(true);
            dashedRing.color = new Color(COLOR_LEVEL0.r, COLOR_LEVEL0.g, COLOR_LEVEL0.b, 0.25f);
        }

        Color cueColor;
        if (status == "SUCCESS") cueColor = COLOR_SUCCESS;
        else if (status == "FAIL") cueColor = COLOR_FAIL;
        else cueColor = isLeft ? COLOR_LEFT : COLOR_RIGHT;

        if (activeFillRing != null)
        {
            activeFillRing.gameObject.SetActive(true);
            activeFillRing.color = cueColor;
            // Level 1: 0.33, Level 2: 0.66, Level 3: 1.0
            float fillTarget = Mathf.Clamp01(level / 3.0f);
            activeFillRing.fillAmount = fillTarget;
        }

        // 3. 화살표 CUE (LEFT / RIGHT)
        if (leftArrow != null)
        {
            leftArrow.gameObject.SetActive(isLeft);
            leftArrow.color = cueColor;
        }

        if (rightArrow != null)
        {
            rightArrow.gameObject.SetActive(isRight);
            rightArrow.color = cueColor;
        }
    }
}
