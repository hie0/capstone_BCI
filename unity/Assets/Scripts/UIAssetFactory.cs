using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// CONTRA LABS // BCI-OS v1.09 스타일 런타임 텍스처/스프라이트 생성기.
/// 벙커 잠망경(Porthole) 창문, 테크 아웃라인 패널, 원형 캘리브레이션 아크,
/// 슬림 게이지, 비네트 및 스캔라인 등을 절차적으로 생성한다.
/// </summary>
public static class UIAssetFactory
{
    private static readonly Dictionary<string, Sprite> _cache = new Dictionary<string, Sprite>();

    /// <summary>테크 아웃라인 패널 9-slice 스프라이트</summary>
    public static Sprite GetTechPanel(int size = 64, int radius = 10, Color? fillColor = null, Color? strokeColor = null, int strokeWidth = 1)
    {
        Color fill = fillColor ?? new Color(0.04f, 0.06f, 0.09f, 0.95f);
        Color stroke = strokeColor ?? new Color(0.15f, 0.25f, 0.35f, 0.8f);
        string key = $"TechPanel_{size}_{radius}_{fill.GetHashCode()}_{stroke.GetHashCode()}_{strokeWidth}";
        if (_cache.TryGetValue(key, out var cached)) return cached;

        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Bilinear;
        tex.wrapMode = TextureWrapMode.Clamp;

        Color[] pixels = new Color[size * size];
        float centerOffset = size * 0.5f;

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float dx = Mathf.Max(0, Mathf.Abs(x - centerOffset + 0.5f) - (centerOffset - radius));
                float dy = Mathf.Max(0, Mathf.Abs(y - centerOffset + 0.5f) - (centerOffset - radius));
                float dist = Mathf.Sqrt(dx * dx + dy * dy);

                float dOut = dist - radius;
                float alphaOut = Mathf.Clamp01(0.5f - dOut);

                if (alphaOut <= 0f)
                {
                    pixels[y * size + x] = Color.clear;
                    continue;
                }

                if (strokeWidth > 0 && stroke.a > 0f)
                {
                    float dIn = dist - (radius - strokeWidth);
                    float alphaIn = Mathf.Clamp01(0.5f - dIn);
                    Color col = Color.Lerp(fill, stroke, 1f - alphaIn);
                    col.a *= alphaOut;
                    pixels[y * size + x] = col;
                }
                else
                {
                    Color col = fill;
                    col.a *= alphaOut;
                    pixels[y * size + x] = col;
                }
            }
        }

        tex.SetPixels(pixels);
        tex.Apply();

        float b = radius + strokeWidth + 2;
        Vector4 border = new Vector4(b, b, b, b);
        var sprite = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect, border);
        _cache[key] = sprite;
        return sprite;
    }

    /// <summary>벙커 잠망경 / 원형 방호문 창문 (Porthole) 스프라이트</summary>
    public static Sprite GetBunkerPorthole(int size = 512)
    {
        string key = $"BunkerPorthole_{size}";
        if (_cache.TryGetValue(key, out var cached)) return cached;

        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Bilinear;
        tex.wrapMode = TextureWrapMode.Clamp;

        Color[] pixels = new Color[size * size];
        Vector2 center = new Vector2(size * 0.5f, size * 0.5f);
        float rMax = (size - 4) * 0.5f;
        float rRingIn = rMax * 0.82f;
        float rGlassIn = rRingIn * 0.96f;

        Color metalOuter = new Color(0.22f, 0.25f, 0.28f);
        Color metalInner = new Color(0.12f, 0.14f, 0.17f);
        Color glassBg = new Color(0.04f, 0.06f, 0.08f, 0.95f);
        Color boltCol = new Color(0.35f, 0.40f, 0.45f);

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                Vector2 pos = new Vector2(x + 0.5f, y + 0.5f);
                float dist = Vector2.Distance(pos, center);
                float angle = Mathf.Atan2(pos.y - center.y, pos.x - center.x) * Mathf.Rad2Deg;
                if (angle < 0) angle += 360f;

                float dOut = dist - rMax;
                float alphaOut = Mathf.Clamp01(0.5f - dOut);
                if (alphaOut <= 0f)
                {
                    pixels[y * size + x] = Color.clear;
                    continue;
                }

                Color col;
                if (dist > rRingIn)
                {
                    // 외곽 메탈 림 (볼트 리벳 8개 배치)
                    float rimT = (dist - rRingIn) / (rMax - rRingIn);
                    col = Color.Lerp(metalInner, metalOuter, rimT);

                    // 8방향 리벳 볼트 (45도 간격)
                    float boltAngleDist = Mathf.Abs((angle + 22.5f) % 45f - 22.5f);
                    float rBolt = (rMax + rRingIn) * 0.5f;
                    float dBolt = Mathf.Sqrt(Mathf.Pow(dist - rBolt, 2) + Mathf.Pow((boltAngleDist * Mathf.Deg2Rad * rBolt), 2));
                    if (dBolt < size * 0.024f)
                    {
                        col = Color.Lerp(boltCol, Color.black, dBolt / (size * 0.024f));
                    }
                }
                else if (dist > rGlassIn)
                {
                    // 어두운 이음새 베벨
                    col = new Color(0.02f, 0.02f, 0.03f);
                }
                else
                {
                    // 내부 유리 영역 (은은한 상단 하이라이트)
                    float glassT = 1f - (dist / rGlassIn);
                    col = glassBg;
                    if (pos.y > center.y)
                    {
                        col += new Color(0.04f, 0.08f, 0.10f, 0f) * ((pos.y - center.y) / rGlassIn);
                    }
                }

                col.a *= alphaOut;
                pixels[y * size + x] = col;
            }
        }

        tex.SetPixels(pixels);
        tex.Apply();

        var sprite = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
        _cache[key] = sprite;
        return sprite;
    }

    /// <summary>Step 2 원형 캘리브레이션 아크 링 (00.png 레퍼런스)</summary>
    public static Sprite GetCalibrationArc(int size = 512, Color? arcColor = null)
    {
        Color col = arcColor ?? new Color(0.0f, 0.90f, 1.0f);
        string key = $"CalibArc_{size}_{col.GetHashCode()}";
        if (_cache.TryGetValue(key, out var cached)) return cached;

        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Bilinear;
        tex.wrapMode = TextureWrapMode.Clamp;

        Color[] pixels = new Color[size * size];
        Vector2 center = new Vector2(size * 0.5f, size * 0.5f);
        float rOut = size * 0.46f;
        float rIn = size * 0.435f;

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                Vector2 pos = new Vector2(x + 0.5f, y + 0.5f);
                float dist = Vector2.Distance(pos, center);
                float angle = Mathf.Atan2(pos.y - center.y, pos.x - center.x) * Mathf.Rad2Deg;
                if (angle < 0) angle += 360f;

                // 90도 ~ 270도 구간의 원형 아크 (레퍼런스 00.png)
                bool inArc = (angle >= 70f && angle <= 290f);
                float alpha = 0f;

                if (inArc && dist >= rIn && dist <= rOut)
                {
                    alpha = 0.95f;
                }
                else if (dist >= rIn && dist <= rOut)
                {
                    // 나머지 구간은 얇은 희미한 가이드 링
                    alpha = 0.15f;
                }

                // 중앙 십자선 마커
                bool centerCross = (Mathf.Abs(pos.x - center.x) < 1.2f && Mathf.Abs(pos.y - center.y) < size * 0.08f)
                                || (Mathf.Abs(pos.y - center.y) < 1.2f && Mathf.Abs(pos.x - center.x) < size * 0.08f);
                if (centerCross)
                {
                    alpha = Mathf.Max(alpha, 0.9f);
                }

                Color pCol = col;
                pCol.a *= alpha;
                pixels[y * size + x] = pCol;
            }
        }

        tex.SetPixels(pixels);
        tex.Apply();

        var sprite = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
        _cache[key] = sprite;
        return sprite;
    }

    /// <summary>원형 채우기 스프라이트</summary>
    public static Sprite GetCircle(int size = 128, Color? fillColor = null, Color? strokeColor = null, int strokeWidth = 0)
    {
        Color fill = fillColor ?? Color.white;
        Color stroke = strokeColor ?? Color.clear;
        string key = $"Circle_{size}_{fill.GetHashCode()}_{stroke.GetHashCode()}_{strokeWidth}";
        if (_cache.TryGetValue(key, out var cached)) return cached;

        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Bilinear;
        tex.wrapMode = TextureWrapMode.Clamp;

        Color[] pixels = new Color[size * size];
        float radius = (size - 2) * 0.5f;
        Vector2 center = new Vector2(size * 0.5f, size * 0.5f);

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float dist = Vector2.Distance(new Vector2(x + 0.5f, y + 0.5f), center);
                float dOut = dist - radius;
                float alphaOut = Mathf.Clamp01(0.5f - dOut);

                if (alphaOut <= 0f)
                {
                    pixels[y * size + x] = Color.clear;
                    continue;
                }

                if (strokeWidth > 0 && stroke.a > 0f)
                {
                    float dIn = dist - (radius - strokeWidth);
                    float alphaIn = Mathf.Clamp01(0.5f - dIn);
                    Color col = Color.Lerp(fill, stroke, 1f - alphaIn);
                    col.a *= alphaOut;
                    pixels[y * size + x] = col;
                }
                else
                {
                    Color col = fill;
                    col.a *= alphaOut;
                    pixels[y * size + x] = col;
                }
            }
        }

        tex.SetPixels(pixels);
        tex.Apply();

        var sprite = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
        _cache[key] = sprite;
        return sprite;
    }

    /// <summary>화면 비네트</summary>
    public static Sprite GetVignette(int size = 256)
    {
        string key = $"Vignette_{size}";
        if (_cache.TryGetValue(key, out var cached)) return cached;

        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Bilinear;
        tex.wrapMode = TextureWrapMode.Clamp;

        Color[] pixels = new Color[size * size];
        Vector2 center = new Vector2(size * 0.5f, size * 0.5f);
        float maxDist = size * 0.5f;

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float dist = Vector2.Distance(new Vector2(x, y), center) / maxDist;
                float a = Mathf.Clamp01(Mathf.Pow(dist, 2.0f) * 0.88f);
                pixels[y * size + x] = new Color(0f, 0f, 0f, a);
            }
        }

        tex.SetPixels(pixels);
        tex.Apply();

        var sprite = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
        _cache[key] = sprite;
        return sprite;
    }

    /// <summary>스캔라인</summary>
    public static Sprite GetScanline()
    {
        string key = "Scanline_4x4";
        if (_cache.TryGetValue(key, out var cached)) return cached;

        var tex = new Texture2D(4, 4, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Point;
        tex.wrapMode = TextureWrapMode.Repeat;

        Color[] pixels = new Color[16];
        for (int y = 0; y < 4; y++)
        {
            Color c = (y % 2 == 0) ? new Color(0, 0, 0, 0.16f) : Color.clear;
            for (int x = 0; x < 4; x++)
            {
                pixels[y * 4 + x] = c;
            }
        }

        tex.SetPixels(pixels);
        tex.Apply();

        var sprite = Sprite.Create(tex, new Rect(0, 0, 4, 4), new Vector2(0.5f, 0.5f), 100f);
        _cache[key] = sprite;
        return sprite;
    }

    /// <summary>소프트 글로우 스프라이트</summary>
    public static Sprite GetGlow(int size = 64, Color? color = null)
    {
        Color baseCol = color ?? new Color(0f, 0f, 0f, 0.7f);
        string key = $"Glow_{size}_{baseCol.GetHashCode()}";
        if (_cache.TryGetValue(key, out var cached)) return cached;

        var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.filterMode = FilterMode.Bilinear;
        tex.wrapMode = TextureWrapMode.Clamp;

        Color[] pixels = new Color[size * size];
        Vector2 center = new Vector2(size * 0.5f, size * 0.5f);
        float radius = size * 0.5f;

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float dist = Vector2.Distance(new Vector2(x, y), center) / radius;
                float falloff = Mathf.Clamp01(1f - dist);
                falloff = Mathf.SmoothStep(0f, 1f, falloff);
                Color c = baseCol;
                c.a *= falloff;
                pixels[y * size + x] = c;
            }
        }

        tex.SetPixels(pixels);
        tex.Apply();

        var sprite = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect, new Vector4(20, 20, 20, 20));
        _cache[key] = sprite;
        return sprite;
    }
}
