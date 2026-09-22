using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// CONTRA LABS // BCI-OS v1.09 스타일 3분할 뷰 제어기.
/// - 중앙: 벙커 창문 속 생존자 카드 (틸팅 & 스와이프)
/// - 좌측 패널: ← LEFT MOTOR IMAGERY (붉은색 네온 하이라이트)
/// - 우측 패널: RIGHT MOTOR IMAGERY → (청록색 네온 하이라이트)
/// - 실시간 MI 확률에 따라 좌/우 패널과 중앙 카드가 유기적으로 반응
/// </summary>
public class CardView : MonoBehaviour
{
    [Header("중앙 생존자 카드 UI")]
    public RectTransform cardRect;
    public Text categoryBadgeText;      // [ CIVILIAN AT GATES ]
    public Text speakerNameText;        // NAME: HELENA (SURVIVOR)
    public Text promptText;             // 스토리 프롬프트 대사
    public Text avatarText;             // 창문 속 이모지/포트레이트

    [Header("좌측 패널 (LEFT MOTOR IMAGERY)")]
    public Image leftPanelBg;
    public Image leftPanelBorder;
    public Text leftHeader;
    public Text leftActionText;
    public Text leftSubText;

    [Header("우측 패널 (RIGHT MOTOR IMAGERY)")]
    public Image rightPanelBg;
    public Image rightPanelBorder;
    public Text rightHeader;
    public Text rightActionText;
    public Text rightSubText;
    public Text rightStatusText;

    [Header("연출 파라미터")]
    public float maxTiltDeg = 10f;
    public float maxTranslateX = 60f;
    public float followLerp = 14f;
    public float swipeSpeed = 2600f;
    public float swipeRotate = 25f;

    private bool _isSwiping = false;
    private int _swipeDir = 0;          // -1 왼쪽, +1 오른쪽
    private float _currentRotZ = 0f;
    private float _currentX = 0f;

    // 네온 컬러 상수
    private static readonly Color RED_ACTIVE_BORDER = new Color(1f, 0.28f, 0.35f, 1f);
    private static readonly Color RED_IDLE_BORDER = new Color(0.85f, 0.22f, 0.28f, 0.45f);
    private static readonly Color RED_IDLE_BG = new Color(0.06f, 0.05f, 0.07f, 0.95f);
    private static readonly Color RED_ACTIVE_BG = new Color(0.18f, 0.06f, 0.09f, 0.98f);

    private static readonly Color CYAN_ACTIVE_BORDER = new Color(0.0f, 0.90f, 1.0f, 1f);
    private static readonly Color CYAN_IDLE_BORDER = new Color(0.0f, 0.65f, 0.75f, 0.45f);
    private static readonly Color CYAN_IDLE_BG = new Color(0.04f, 0.07f, 0.09f, 0.95f);
    private static readonly Color CYAN_ACTIVE_BG = new Color(0.05f, 0.16f, 0.20f, 0.98f);

    /// <summary>새 카드 데이터 바인딩</summary>
    public void Bind(Card card)
    {
        if (card == null) return;

        if (categoryBadgeText)
            categoryBadgeText.text = $"[ {card.category?.ToUpper()} ]";
        if (speakerNameText)
            speakerNameText.text = $"NAME: {card.character?.ToUpper()}";
        if (avatarText)
            avatarText.text = string.IsNullOrEmpty(card.avatar) ? "👤" : card.avatar;
        if (promptText)
            promptText.text = $"\"{card.story_prompt}\"";

        // 좌측 옵션 바인딩
        if (card.left_option != null)
        {
            if (leftActionText) leftActionText.text = card.left_option.text;
            if (leftSubText)
            {
                string delta = FormatDelta(card.left_option.stat_delta);
                leftSubText.text = $"Imagine Left-Hand squeeze to reject request.\n{delta}";
            }
        }

        // 우측 옵션 바인딩
        if (card.right_option != null)
        {
            if (rightActionText) rightActionText.text = card.right_option.text;
            if (rightSubText)
            {
                string delta = FormatDelta(card.right_option.stat_delta);
                rightSubText.text = $"Imagine Right-Hand squeeze to accept request.\n{delta}";
            }
        }

        ResetPose();
    }

    private string FormatDelta(StatDelta d)
    {
        if (d == null) return "";
        var list = new List<string>();
        if (d.food != 0) list.Add($"🍖{(d.food > 0 ? "+" : "")}{d.food}%");
        if (d.ammo != 0) list.Add($"⚡{(d.ammo > 0 ? "+" : "")}{d.ammo}%");
        if (d.defense != 0) list.Add($"🛡{(d.defense > 0 ? "+" : "")}{d.defense}%");
        if (d.morale != 0) list.Add($"👥{(d.morale > 0 ? "+" : "")}{d.morale}%");
        return string.Join("  ", list);
    }

    public void ResetPose()
    {
        _isSwiping = false;
        _swipeDir = 0;
        _currentRotZ = 0f;
        _currentX = 0f;
        if (cardRect)
        {
            cardRect.anchoredPosition = new Vector2(0, 15);
            cardRect.localRotation = Quaternion.identity;
            cardRect.localScale = Vector3.one;
        }

        SetIdleStyles();
    }

    private void SetIdleStyles()
    {
        if (leftPanelBorder) leftPanelBorder.color = RED_IDLE_BORDER;
        if (leftPanelBg) leftPanelBg.color = RED_IDLE_BG;
        if (rightPanelBorder) rightPanelBorder.color = CYAN_IDLE_BORDER;
        if (rightPanelBg) rightPanelBg.color = CYAN_IDLE_BG;
        if (rightStatusText) rightStatusText.color = new Color(0.0f, 0.90f, 1.0f, 0.6f);
    }

    /// <summary>매 프레임 확률에 따라 카드 틸팅 및 좌/우 패널 네온 하이라이트</summary>
    public void UpdateTilt(float probLeft, float probRight)
    {
        if (_isSwiping || cardRect == null) return;

        float diff = probRight - probLeft; // -1 ~ +1
        float targetRotZ = -diff * maxTiltDeg;
        float targetX = diff * maxTranslateX;

        _currentRotZ = Mathf.Lerp(_currentRotZ, targetRotZ, followLerp * Time.deltaTime);
        _currentX = Mathf.Lerp(_currentX, targetX, followLerp * Time.deltaTime);

        cardRect.anchoredPosition = new Vector2(_currentX, 15f);
        cardRect.localRotation = Quaternion.Euler(0, 0, _currentRotZ);

        // 좌/우 패널 네온 점등 연출
        if (diff < -0.1f)
        {
            float t = Mathf.Clamp01((-diff - 0.1f) / 0.7f);
            if (leftPanelBorder) leftPanelBorder.color = Color.Lerp(RED_IDLE_BORDER, RED_ACTIVE_BORDER, t);
            if (leftPanelBg) leftPanelBg.color = Color.Lerp(RED_IDLE_BG, RED_ACTIVE_BG, t);
            if (rightPanelBorder) rightPanelBorder.color = Color.Lerp(CYAN_IDLE_BORDER, new Color(0.1f, 0.15f, 0.2f, 0.25f), t);
            if (rightPanelBg) rightPanelBg.color = Color.Lerp(CYAN_IDLE_BG, new Color(0.03f, 0.04f, 0.05f, 0.8f), t);
        }
        else if (diff > 0.1f)
        {
            float t = Mathf.Clamp01((diff - 0.1f) / 0.7f);
            if (rightPanelBorder) rightPanelBorder.color = Color.Lerp(CYAN_IDLE_BORDER, CYAN_ACTIVE_BORDER, t);
            if (rightPanelBg) rightPanelBg.color = Color.Lerp(CYAN_IDLE_BG, CYAN_ACTIVE_BG, t);
            if (leftPanelBorder) leftPanelBorder.color = Color.Lerp(RED_IDLE_BORDER, new Color(0.2f, 0.1f, 0.12f, 0.25f), t);
            if (leftPanelBg) leftPanelBg.color = Color.Lerp(RED_IDLE_BG, new Color(0.03f, 0.04f, 0.05f, 0.8f), t);
        }
        else
        {
            if (leftPanelBorder) leftPanelBorder.color = Color.Lerp(leftPanelBorder.color, RED_IDLE_BORDER, 8f * Time.deltaTime);
            if (leftPanelBg) leftPanelBg.color = Color.Lerp(leftPanelBg.color, RED_IDLE_BG, 8f * Time.deltaTime);
            if (rightPanelBorder) rightPanelBorder.color = Color.Lerp(rightPanelBorder.color, CYAN_IDLE_BORDER, 8f * Time.deltaTime);
            if (rightPanelBg) rightPanelBg.color = Color.Lerp(rightPanelBg.color, CYAN_IDLE_BG, 8f * Time.deltaTime);
        }
    }

    /// <summary>80% 트리거 시 카드 스와이프 발화</summary>
    public void StartSwipe(string direction)
    {
        _isSwiping = true;
        _swipeDir = (direction == "LEFT") ? -1 : 1;
    }

    public bool IsSwipeFinished()
    {
        if (!_isSwiping || cardRect == null) return true;
        return Mathf.Abs(cardRect.anchoredPosition.x) > 1300f;
    }

    void Update()
    {
        if (_isSwiping && cardRect != null)
        {
            Vector2 pos = cardRect.anchoredPosition;
            pos.x += _swipeDir * swipeSpeed * Time.deltaTime;
            cardRect.anchoredPosition = pos;

            _currentRotZ += -_swipeDir * swipeRotate * Time.deltaTime;
            cardRect.localRotation = Quaternion.Euler(0, 0, _currentRotZ);
            cardRect.localScale = Vector3.Lerp(cardRect.localScale, Vector3.one * 0.7f, 8f * Time.deltaTime);
        }
    }
}
