using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Explore EEG의 실시간 채널 신호(C3 / C4) 및 모터 리듬(Mu/Beta ERD)을
/// 실시간 오실로스코프 파형과 전압 수치로 시각화하는 모니터 컴포넌트.
/// 
/// - 실시간 뇌파 파형 (동적 오실로스코프 텍스처)
/// - 채널 전압 (uV) 텔레메트리
/// - 운동 상상(MI) 집중도 / 활성도 바
/// </summary>
public class EEGWaveformMonitor : MonoBehaviour
{
    [Header("UI 바인딩")]
    public RawImage waveformImage;
    public Text channelNameText;
    public Text voltageText;
    public Text powerText;
    public Slider powerBar;

    [Header("모니터 설정")]
    public string channelName = "C3";
    public Color waveColor = new Color(0.0f, 0.90f, 1.0f);
    public int textureWidth = 200;
    public int textureHeight = 48;

    private Texture2D _tex;
    private Color[] _clearPixels;
    private float[] _samples;
    private float _phase = 0f;


    void Awake()
    {
        InitTexture();
    }

    public void InitTexture()
    {
        if (_samples == null || _samples.Length != textureWidth)
        {
            _samples = new float[textureWidth];
            for (int i = 0; i < textureWidth; i++) _samples[i] = textureHeight * 0.5f;
        }

        if (_tex == null)
        {
            _tex = new Texture2D(textureWidth, textureHeight, TextureFormat.RGBA32, false);
            _tex.filterMode = FilterMode.Bilinear;
            _tex.wrapMode = TextureWrapMode.Clamp;

            _clearPixels = new Color[textureWidth * textureHeight];
            Color bg = new Color(0.035f, 0.05f, 0.08f, 0.95f);
            Color grid = new Color(0.11f, 0.16f, 0.25f, 0.65f);
            Color gridAxis = new Color(0.18f, 0.28f, 0.42f, 0.9f);

            int midY = textureHeight / 2;
            int qY1 = textureHeight / 4;
            int qY2 = (textureHeight * 3) / 4;

            for (int y = 0; y < textureHeight; y++)
            {
                for (int x = 0; x < textureWidth; x++)
                {
                    bool isAxis = (y == midY);
                    bool isSubGrid = (y == qY1 || y == qY2 || (x % 28 == 0));
                    if (isAxis && (x % 2 == 0))
                        _clearPixels[y * textureWidth + x] = gridAxis;
                    else if (isSubGrid && ((x + y) % 3 == 0))
                        _clearPixels[y * textureWidth + x] = grid;
                    else
                        _clearPixels[y * textureWidth + x] = bg;
                }
            }
        }

        if (waveformImage != null && waveformImage.texture != _tex)
        {
            waveformImage.texture = _tex;
        }
    }

    /// <summary>
    /// 실시간 뇌파 상태를 갱신합니다 (매 프레임 또는 소켓 수신 시).
    /// </summary>
    /// <param name="intent">해당 방향 상상 강도 (0.0 ~ 1.0)</param>
    /// <param name="raw_uV">실제 또는 시뮬레이션된 전압 (uV)</param>
    public void UpdateTelemetry(float intent, float? raw_uV = null)
    {
        if (_samples == null || _tex == null)
            InitTexture();

        // 1. 전압 수치 계산
        float uV = raw_uV ?? (8.5f + Mathf.Sin(Time.time * 4f + _phase) * 2.2f + (1f - intent) * 3.5f);
        if (voltageText != null)
        {
            voltageText.text = $"{uV:F1} uV";
        }

        if (powerText != null)
        {
            int pct = Mathf.RoundToInt(intent * 100f);
            powerText.text = $"SYNC {pct}%";
        }

        if (powerBar != null)
        {
            powerBar.value = Mathf.Lerp(powerBar.value, intent, 10f * Time.deltaTime);
        }

        // 2. 오실로스코프 파형 갱신
        _phase += Time.deltaTime * (10f + intent * 15f);
        float noise = (Mathf.PerlinNoise(Time.time * 8f, _phase) - 0.5f) * 12f * (1f + (1f - intent) * 0.8f);
        float wave = Mathf.Sin(_phase) * (8f + (1f - intent) * 10f) + noise;

        float mid = textureHeight * 0.5f;
        float currentY = Mathf.Clamp(mid + wave, 2f, textureHeight - 3f);

        // 파형 시프트 (좌측으로 한 픽셀씩 밀림)
        for (int x = 0; x < textureWidth - 1; x++)
        {
            _samples[x] = _samples[x + 1];
        }
        _samples[textureWidth - 1] = currentY;

        RedrawWaveform();
    }

    void RedrawWaveform()
    {
        if (_tex == null || _clearPixels == null) return;

        // 사전 계산된 오실로스코프 그리드 배경 복원
        System.Array.Copy(_clearPixels, _tex.GetPixels(), _clearPixels.Length);

        // 파형 네온 발광 라인 렌더링
        for (int x = 0; x < textureWidth - 1; x++)
        {
            int y0 = Mathf.RoundToInt(_samples[x]);
            int y1 = Mathf.RoundToInt(_samples[x + 1]);

            int minY = Mathf.Min(y0, y1);
            int maxY = Mathf.Max(y0, y1);

            for (int y = minY; y <= maxY; y++)
            {
                _tex.SetPixel(x, y, waveColor);
                // 발광(글로우) 효과
                if (y + 1 < textureHeight) _tex.SetPixel(x, y + 1, new Color(waveColor.r, waveColor.g, waveColor.b, 0.45f));
                if (y - 1 >= 0) _tex.SetPixel(x, y - 1, new Color(waveColor.r, waveColor.g, waveColor.b, 0.45f));
            }
        }

        _tex.Apply();
    }


    void OnDestroy()
    {
        if (_tex != null)
        {
            Destroy(_tex);
            _tex = null;
        }
    }
}
