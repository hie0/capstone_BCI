using System;
using System.Collections.Generic;
using UnityEngine;

// cards.json 스키마에 대응하는 직렬화 모델.
// Unity의 JsonUtility가 파싱하며, story_cards_zombie.json / web_app/cards.json 과 동일한 구조를 사용한다.

[Serializable]
public class StatDelta
{
    public int food;
    public int ammo;
    public int defense;
    public int morale;
}

[Serializable]
public class CardOption
{
    public string text;
    public StatDelta stat_delta;
}

[Serializable]
public class Card
{
    public string id;
    public string category;
    public string character;
    public string avatar;        // 이모지 (선택). 폰트가 없으면 fallback 처리됨
    public string story_prompt;
    public CardOption left_option;
    public CardOption right_option;
}

[Serializable]
public class CardDatabase
{
    public string project;
    public string version;
    public string story_title;
    public List<Card> cards = new List<Card>();
}

// 서버(bci_tcp_server.py)가 0.25초마다 보내는 JSON 라인 패킷.
// { "left_prob": 0.842, "right_prob": 0.158, "trigger": "LEFT", "elapsed_sec": 1.25 }
[Serializable]
public class BCIPacket
{
    public float left_prob = 0.5f;
    public float right_prob = 0.5f;
    public string trigger = "NONE";   // NONE | LEFT | RIGHT | NEUTRAL
    public float elapsed_sec = 0f;
    public int level = 0;             // neuro_feedback3 Dynamic Fading Level (0~3)
    public float c3_uV = 0f;          // 실시간 C3 전압
    public float c4_uV = 0f;          // 실시간 C4 전압
}

