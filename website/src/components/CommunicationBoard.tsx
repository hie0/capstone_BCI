import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  Brain,
  Check,
  RotateCcw,
  Volume2,
} from "lucide-react";
import { Atlas2D } from "./Scenes";
import { Settings, Waveform, PlayButton } from "./Controls";
import { useBCI } from "../store";
import { selectedBackendModel, isStaticRecordedReplay } from "../data/backend";
import { RecordedMetrics } from "./RecordedMetrics";
import type { Direction } from "../data/research";
import "./CommunicationBoard.css";

type OptionData = {
  label: string;
  english: string;
  desc: string;
  symbol: string;
  subId?: string;
  speech?: string;
};

type DecisionNode = {
  id: string;
  depth: number;
  badge: string;
  left: OptionData;
  right: OptionData;
};

const THRESHOLD = 80;
const STEP = 10;

// 5 Channels to display in the EEG Control Monitor
const MONITOR_CHANNELS = ["F3", "F4", "C3", "Cz", "C4"];

// 3-Depth Hierarchical Decision Tree (8 Specific Messages)
const TREE_NODES: Record<string, DecisionNode> = {
  ROOT: {
    id: "ROOT",
    depth: 1,
    badge: "1단계: 대분류 선택",
    left: {
      label: "신체적·생리적 욕구",
      english: "PHYSICAL NEEDS",
      desc: "음료, 식사, 체위 변경, 실내 환경",
      symbol: "💧",
      subId: "PHYSICAL",
    },
    right: {
      label: "통증·의료 및 감정 전달",
      english: "MEDICAL & CARE",
      desc: "통증 부위 호소, 긴급 호출, 감사",
      symbol: "🩺",
      subId: "MEDICAL",
    },
  },
  PHYSICAL: {
    id: "PHYSICAL",
    depth: 2,
    badge: "2단계: 신체 욕구 세부 분류",
    left: {
      label: "음료 및 식사 (식음)",
      english: "BEVERAGE & MEAL",
      desc: "물 마시기, 식사하기",
      symbol: "🍚",
      subId: "FOOD",
    },
    right: {
      label: "자세 및 실내 환경",
      english: "POSTURE & CLIMATE",
      desc: "체위 변경, 실내 온도 조절",
      symbol: "🛏",
      subId: "ENV",
    },
  },
  MEDICAL: {
    id: "MEDICAL",
    depth: 2,
    badge: "2단계: 의료/감정 세부 분류",
    left: {
      label: "통증 부위 호소",
      english: "PAIN LOCATION",
      desc: "머리 통증, 복부 통증",
      symbol: "🤕",
      subId: "PAIN",
    },
    right: {
      label: "의료 호출 및 감정",
      english: "CALL & GRATITUDE",
      desc: "긴급 의료진 호출, 감사 표현",
      symbol: "🚨",
      subId: "CARE",
    },
  },
  FOOD: {
    id: "FOOD",
    depth: 3,
    badge: "3단계: 최종 문장 선택",
    left: {
      label: "목말라요. 물을 주세요.",
      english: "WATER",
      desc: "시원한 물 1컵 요청",
      symbol: "💧",
      speech: "목이 마릅니다. 시원한 물 한 잔만 주세요.",
    },
    right: {
      label: "배고파요. 밥 먹을래요.",
      english: "MEAL",
      desc: "식사 및 간식 요청",
      symbol: "🍚",
      speech: "배가 고픕니다. 식사를 준비해 주세요.",
    },
  },
  ENV: {
    id: "ENV",
    depth: 3,
    badge: "3단계: 최종 문장 선택",
    left: {
      label: "자세가 불편해요. 바꿔주세요.",
      english: "POSTURE",
      desc: "침대 각도 및 체위 변경",
      symbol: "🛏",
      speech: "자세가 불편합니다. 몸을 조금만 돌려주세요.",
    },
    right: {
      label: "실내 온도가 안 맞아요.",
      english: "CLIMATE",
      desc: "추위/더위 조절 요청",
      symbol: "🌡",
      speech: "실내 공기가 너무 춥거나 덥습니다. 온도 조절 부탁드립니다.",
    },
  },
  PAIN: {
    id: "PAIN",
    depth: 3,
    badge: "3단계: 최종 문장 선택",
    left: {
      label: "머리가 지끈거리고 아파요.",
      english: "HEADACHE",
      desc: "두통 완화 조치 요청",
      symbol: "🤕",
      speech: "머리가 욱신거리고 아픕니다. 진통제나 확인 부탁드립니다.",
    },
    right: {
      label: "배가 콕콕 쑤시고 아파요.",
      english: "STOMACH",
      desc: "복통 호소 및 상태 점검",
      symbol: "😣",
      speech: "배가 더부룩하고 통증이 있습니다. 확인해 주세요.",
    },
  },
  CARE: {
    id: "CARE",
    depth: 3,
    badge: "3단계: 최종 문장 선택",
    left: {
      label: "간호사님을 급히 불러주세요.",
      english: "NURSE CALL",
      desc: "긴급 의료진 호출",
      symbol: "🚨",
      speech: "응급 상황입니다. 간호사 선생님을 지금 불러주세요.",
    },
    right: {
      label: "도와주셔서 감사합니다.",
      english: "GRATITUDE",
      desc: "보호자·간병인 감사 인사",
      symbol: "❤️",
      speech: "항상 따뜻하게 보살펴 주셔서 진심으로 감사합니다.",
    },
  },
};

export function CommunicationBoard() {
  const s = useBCI();
  const recorded = s.inputMode === "recorded";
  const channels = recorded ? selectedBackendModel(s)?.active_channels ?? MONITOR_CHANNELS : MONITOR_CHANNELS;
  const [currentNodeId, setCurrentNodeId] = useState<string>("ROOT");
  const [history, setHistory] = useState<string[]>([]);

  // Balance Gauge State: 50% Center, Threshold 80%
  const [left, setLeft] = useState(50);
  const [activeDirection, setActiveDirection] = useState<Direction | undefined>(undefined);
  const [result, setResult] = useState<string>("원하는 항목 카드를 선택하거나 상상하세요.");
  const [finalSpeech, setFinalSpeech] = useState<string | null>(null);
  const [isCommitting, setIsCommitting] = useState(false);

  const evidence = useRef(50);
  const node = useRef("ROOT");
  const committing = useRef(false);
  const processedTrial = useRef<number | null>(null);
  const action = useRef<{ run: () => void; remaining: number; started: number; speed: number; timer?: number } | null>(null);
  const right = 100 - left;
  const confidence = Math.max(left, right);
  const uncertain = confidence < THRESHOLD;
  const currentNode = TREE_NODES[currentNodeId];

  const clearAction = () => {
    if (action.current) window.clearTimeout(action.current.timer);
    action.current = null;
  };
  const armAction = () => {
    const pending = action.current;
    if (!pending || pending.timer !== undefined || (recorded && !useBCI.getState().isPlaying)) return;
    pending.speed = recorded ? useBCI.getState().speed : 1;
    pending.started = performance.now();
    pending.timer = window.setTimeout(() => {
      if (action.current !== pending) return;
      action.current = null;
      pending.run();
    }, pending.remaining / pending.speed);
  };
  const suspendAction = () => {
    const pending = action.current;
    if (!pending || pending.timer === undefined) return;
    window.clearTimeout(pending.timer);
    pending.remaining = Math.max(0, pending.remaining - (performance.now() - pending.started) * pending.speed);
    pending.timer = undefined;
  };
  const schedule = (run: () => void, remaining: number) => {
    clearAction();
    action.current = { run, remaining, started: 0, speed: 1 };
    armAction();
  };
  const resetEvidence = () => { evidence.current = 50; setLeft(50); };
  const resetBoard = () => {
    clearAction();
    node.current = "ROOT"; committing.current = false;
    setCurrentNodeId("ROOT"); setHistory([]); resetEvidence();
    setActiveDirection(undefined); setResult("표현할 항목을 선택하세요.");
    setFinalSpeech(null); setIsCommitting(false);
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  };
  const resetAll = () => {
    s.stop(); resetBoard(); processedTrial.current = null;
    s.setRecordedTrialReady(true);
    if (recorded) s.setSettings({ inputMode: "recorded", recordedLowChannel: s.recordedLowChannel });
  };
  const goBack = () => {
    if (!history.length) return;
    s.stop(); clearAction(); s.setRecordedTrialReady(true);
    const previous = history.slice(0, -1);
    node.current = history[history.length - 1];
    setHistory(previous); setCurrentNodeId(node.current); resetEvidence();
    committing.current = false; setIsCommitting(false); setActiveDirection(undefined);
    setFinalSpeech(null); setResult("이전 단계로 돌아왔습니다.");
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  };
  const startRecorded = () => {
    const total = s.backendSessions.find(session => session.session_id === s.sessionId)?.n_online_trials;
    if (total && s.recordedCursor >= total) resetAll();
    else if (finalSpeech) resetBoard();
    s.play();
  };
  useEffect(() => {
    s.stop(); resetBoard(); processedTrial.current = null;
    s.setRecordedTrialReady(true);
    if (recorded && (useBCI.getState().recordedPrediction || useBCI.getState().recordedCursor > 0)) {
      s.setSettings({ inputMode: "recorded", recordedLowChannel: s.recordedLowChannel });
    }
  }, [s.inputMode, s.participantId, s.sessionId, s.channelMode, s.recordedLowChannel, s.ttaEnabled]);
  useEffect(() => {
    suspendAction(); armAction();
  }, [s.isPlaying, s.speed]);
  useEffect(() => () => {
    clearAction(); useBCI.getState().setRecordedTrialReady(true);
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }, []);

  /**
   * TTS Speech: Plays stable, calm low-pitch Korean Female Voice
   */
  const speakFemale = (text: string) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "ko-KR";

    const assignVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      const koVoices = voices.filter((v) => v.lang.replace("_", "-").startsWith("ko"));
      // Prioritize natural stable Korean female voices (Yuna, Heami, Google, etc.)
      const female =
        koVoices.find((v) => /Yuna|Sora|Google|Heami|SunHi|Female|여성|Natural|Neural/i.test(v.name)) ||
        koVoices[0];

      if (female) utterance.voice = female;
    };

    assignVoice();
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = assignVoice;
    }

    // Stable, calm low-pitch female voice (no trembling)
    utterance.pitch = 0.86;
    utterance.rate = 0.92;
    window.speechSynthesis.speak(utterance);
  };

  const select = (direction: Direction) => {
    if (committing.current) return;
    setActiveDirection(direction);
    const next = Math.max(0, Math.min(100, evidence.current + (direction === "LEFT" ? STEP : -STEP)));
    evidence.current = next; setLeft(next);
    const current = TREE_NODES[node.current];
    if (next >= THRESHOLD || 100 - next >= THRESHOLD) {
      const selected = next >= THRESHOLD ? current.left : current.right;
      const from = node.current;
      committing.current = true; setIsCommitting(true);
      setResult(`✓ [${selected.label}] 확정 완료!`);
      schedule(() => {
        resetEvidence(); setActiveDirection(undefined);
        committing.current = false; setIsCommitting(false);
        if (selected.subId) {
          node.current = selected.subId;
          setHistory(previous => [...previous, from]);
          setCurrentNodeId(selected.subId);
          if (recorded) schedule(() => useBCI.getState().setRecordedTrialReady(true), 1400);
        } else if (selected.speech) {
          setFinalSpeech(selected.speech); speakFemale(selected.speech);
          if (recorded) {
            useBCI.getState().setBackend({ backendStatus: "문장 선택 완료" });
            useBCI.getState().stop();
            useBCI.getState().setRecordedTrialReady(true);
          }
        }
      }, 600);
    } else {
      setResult(`${direction === "LEFT" ? "LEFT" : "RIGHT"} ${recorded ? "예측 반영 · 선택" : "상상"} 누적: ${direction === "LEFT" ? next : 100 - next}% / ${THRESHOLD}%`);
      if (recorded) schedule(() => useBCI.getState().setRecordedTrialReady(true), 2000);
    }
  };
  useEffect(() => {
    const prediction = s.recordedPrediction;
    const current = useBCI.getState();
    if (!recorded || !current.isPlaying || !prediction || current.recordedPrediction !== prediction || prediction.trial_id === processedTrial.current) return;
    processedTrial.current = prediction.trial_id;
    if (!prediction.quality.is_clean) {
      setActiveDirection(undefined);
      setResult(`Trial ${prediction.trial_id}: 품질 기준 미달 · 선택 누적에 반영하지 않습니다.`);
      schedule(() => useBCI.getState().setRecordedTrialReady(true), 2000);
      return;
    }
    // Only model predictions drive selection. Ground truth is evaluation-only.
    select(prediction.predicted_direction);
  }, [recorded, s.isPlaying, s.recordedPrediction]);

  const isLeftSelectedInBranch = (targetSubId: string) => {
    return currentNodeId === targetSubId || history.includes(targetSubId);
  };

  return (
    <section className={`card communication-board ${recorded ? "recorded-communication" : ""}`} aria-label="AAC 소통 의사결정 트리">
      {/* Top Header */}
      <div className="comm-header application-heading">
        <div className="application-heading-copy">
          <span className="eyebrow">APPLICATION 03</span>
          <h2 aria-label="BCI Communication Board">MOTOR IMAGERY VOICE ASSIST</h2>
        </div>

        {/* Tree Breadcrumb Progress */}
        <div className="comm-steps-pills">
          <span className={`pill ${currentNode.depth === 1 ? "active" : ""}`}>
            <b>1</b> 대분류
          </span>
          <i>→</i>
          <span className={`pill ${currentNode.depth === 2 ? "active" : ""}`}>
            <b>2</b> 중분류
          </span>
          <i>→</i>
          <span className={`pill ${currentNode.depth === 3 ? "active" : ""}`}>
            <b>3</b> 최종 문장
          </span>
        </div>

        {/* Action Controls */}
        <div className="header-actions">
          {history.length > 0 && (
            <button className="button outline" onClick={goBack}>
              <ArrowLeft size={14} /> 이전 단계
            </button>
          )}
          <button className="button outline" onClick={resetAll}>
            <RotateCcw size={14} /> 처음으로
          </button>
        </div>
      </div>

      <p className="comm-intro">
        LEFT / RIGHT Motor Imagery를 단계형 Message Selection과 Voice Output으로 연결해, 움직임이나 말하기가 어려운 사용자의 의사표현을 돕습니다.
      </p>

      {/* Voice Output Speech Window */}
      {finalSpeech ? (
        <div className="comm-speech-window">
          <div className="speech-icon-wrapper">
            <Volume2 size={24} />
          </div>
          <div className="speech-content">
            <span className="speech-tag">음성 변환(TTS) 출력 완료</span>
            <strong>"{finalSpeech}"</strong>
          </div>
          <button className="speech-replay-btn" onClick={() => speakFemale(finalSpeech)}>
            <Volume2 size={14} /> 다시 듣기
          </button>
        </div>
      ) : null}

      {/* Tree Visualization Container (Refined Sage Green vs Slate Blue Harmony) */}
      <div className="tree-diagram-shell">
        <div className="curved-tree-container">
          <svg viewBox="0 0 760 300" className="curved-tree-svg" fill="none">
            {/* Connector Bezier Curves: Left is Sage Green, Right is Slate Blue */}
            <path
              d="M 380 35 C 380 65, 200 60, 200 90"
              stroke={isLeftSelectedInBranch("PHYSICAL") ? "#2F6B5C" : "#CBD5E1"}
              strokeWidth={isLeftSelectedInBranch("PHYSICAL") ? 3 : 1.8}
              strokeDasharray={isLeftSelectedInBranch("PHYSICAL") ? undefined : "4"}
            />
            <path
              d="M 380 35 C 380 65, 560 60, 560 90"
              stroke={isLeftSelectedInBranch("MEDICAL") ? "#345C7D" : "#CBD5E1"}
              strokeWidth={isLeftSelectedInBranch("MEDICAL") ? 3 : 1.8}
              strokeDasharray={isLeftSelectedInBranch("MEDICAL") ? undefined : "4"}
            />

            <path
              d="M 200 125 C 200 148, 110 145, 110 170"
              stroke={isLeftSelectedInBranch("FOOD") ? "#2F6B5C" : "#CBD5E1"}
              strokeWidth={isLeftSelectedInBranch("FOOD") ? 2.5 : 1.5}
              strokeDasharray={isLeftSelectedInBranch("FOOD") ? undefined : "3"}
            />
            <path
              d="M 200 125 C 200 148, 290 145, 290 170"
              stroke={isLeftSelectedInBranch("ENV") ? "#2F6B5C" : "#CBD5E1"}
              strokeWidth={isLeftSelectedInBranch("ENV") ? 2.5 : 1.5}
              strokeDasharray={isLeftSelectedInBranch("ENV") ? undefined : "3"}
            />

            <path
              d="M 560 125 C 560 148, 470 145, 470 170"
              stroke={isLeftSelectedInBranch("PAIN") ? "#345C7D" : "#CBD5E1"}
              strokeWidth={isLeftSelectedInBranch("PAIN") ? 2.5 : 1.5}
              strokeDasharray={isLeftSelectedInBranch("PAIN") ? undefined : "3"}
            />
            <path
              d="M 560 125 C 560 148, 650 145, 650 170"
              stroke={isLeftSelectedInBranch("CARE") ? "#345C7D" : "#CBD5E1"}
              strokeWidth={isLeftSelectedInBranch("CARE") ? 2.5 : 1.5}
              strokeDasharray={isLeftSelectedInBranch("CARE") ? undefined : "3"}
            />

            {/* Terminal Connection Lines */}
            <path d="M 110 205 C 110 220, 65 220, 65 240" stroke="#CBD5E1" strokeWidth={1.5} />
            <path d="M 110 205 C 110 220, 155 220, 155 240" stroke="#CBD5E1" strokeWidth={1.5} />
            <path d="M 290 205 C 290 220, 245 220, 245 240" stroke="#CBD5E1" strokeWidth={1.5} />
            <path d="M 290 205 C 290 220, 335 220, 335 240" stroke="#CBD5E1" strokeWidth={1.5} />
            <path d="M 470 205 C 470 220, 425 220, 425 240" stroke="#CBD5E1" strokeWidth={1.5} />
            <path d="M 470 205 C 470 220, 515 220, 515 240" stroke="#CBD5E1" strokeWidth={1.5} />
            <path d="M 650 205 C 650 220, 605 220, 605 240" stroke="#CBD5E1" strokeWidth={1.5} />
            <path d="M 650 205 C 650 220, 695 220, 695 240" stroke="#CBD5E1" strokeWidth={1.5} />

            {/* ROOT NODE */}
            <g transform="translate(315, 14)">
              <rect width="130" height="34" rx="17" fill="#1E293B" />
              <text x="65" y="22" fill="#FFFFFF" fontSize="11" fontWeight="800" textAnchor="middle">
                🧠 의사표현 시작
              </text>
            </g>

            {/* LEVEL 1 NODES: Left (Sage Green) vs Right (Slate Blue) */}
            <g transform="translate(115, 88)">
              <rect
                width="170"
                height="36"
                rx="18"
                fill={isLeftSelectedInBranch("PHYSICAL") ? "#F0F6F4" : "#FFFFFF"}
                stroke={isLeftSelectedInBranch("PHYSICAL") ? "#2F6B5C" : "#CBD5E1"}
                strokeWidth={isLeftSelectedInBranch("PHYSICAL") ? 2.5 : 1.5}
              />
              <text
                x="85"
                y="23"
                fill={isLeftSelectedInBranch("PHYSICAL") ? "#2F6B5C" : "#64748B"}
                fontSize="12"
                fontWeight="800"
                textAnchor="middle"
              >
                ← 신체 욕구 (L)
              </text>
            </g>

            <g transform="translate(475, 88)">
              <rect
                width="170"
                height="36"
                rx="18"
                fill={isLeftSelectedInBranch("MEDICAL") ? "#F0F4F8" : "#FFFFFF"}
                stroke={isLeftSelectedInBranch("MEDICAL") ? "#345C7D" : "#CBD5E1"}
                strokeWidth={isLeftSelectedInBranch("MEDICAL") ? 2.5 : 1.5}
              />
              <text
                x="85"
                y="23"
                fill={isLeftSelectedInBranch("MEDICAL") ? "#345C7D" : "#64748B"}
                fontSize="12"
                fontWeight="800"
                textAnchor="middle"
              >
                상태·도움 및 감정 (R) →
              </text>
            </g>

            {/* LEVEL 2 NODES */}
            <g transform="translate(45, 168)">
              <rect
                width="130"
                height="32"
                rx="16"
                fill={isLeftSelectedInBranch("FOOD") ? "#E3EFEA" : "#FFFFFF"}
                stroke={isLeftSelectedInBranch("FOOD") ? "#2F6B5C" : "#E2E8F0"}
                strokeWidth={isLeftSelectedInBranch("FOOD") ? 2 : 1.2}
              />
              <text x="65" y="21" fill="#2F6B5C" fontSize="10.5" fontWeight="800" textAnchor="middle">
                음료 & 식사 (L)
              </text>
            </g>

            <g transform="translate(225, 168)">
              <rect
                width="130"
                height="32"
                rx="16"
                fill={isLeftSelectedInBranch("ENV") ? "#E3EFEA" : "#FFFFFF"}
                stroke={isLeftSelectedInBranch("ENV") ? "#2F6B5C" : "#E2E8F0"}
                strokeWidth={isLeftSelectedInBranch("ENV") ? 2 : 1.2}
              />
              <text x="65" y="21" fill="#64748B" fontSize="10.5" fontWeight="700" textAnchor="middle">
                자세 & 환경 (R)
              </text>
            </g>

            <g transform="translate(405, 168)">
              <rect
                width="130"
                height="32"
                rx="16"
                fill={isLeftSelectedInBranch("PAIN") ? "#E2EBF2" : "#FFFFFF"}
                stroke={isLeftSelectedInBranch("PAIN") ? "#345C7D" : "#E2E8F0"}
                strokeWidth={isLeftSelectedInBranch("PAIN") ? 2 : 1.2}
              />
              <text x="65" y="21" fill="#345C7D" fontSize="10.5" fontWeight="700" textAnchor="middle">
                통증 호소 (L)
              </text>
            </g>

            <g transform="translate(585, 168)">
              <rect
                width="130"
                height="32"
                rx="16"
                fill={isLeftSelectedInBranch("CARE") ? "#E2EBF2" : "#FFFFFF"}
                stroke={isLeftSelectedInBranch("CARE") ? "#345C7D" : "#E2E8F0"}
                strokeWidth={isLeftSelectedInBranch("CARE") ? 2 : 1.2}
              />
              <text x="65" y="21" fill="#345C7D" fontSize="10.5" fontWeight="700" textAnchor="middle">
                호출 & 감정 (R)
              </text>
            </g>

            {/* LEVEL 3 TERMINAL NODES (8 Messages) */}
            {[
              { x: 18, text: "💧 물 주세요", active: currentNodeId === "FOOD", side: "left" },
              { x: 118, text: "🍚 밥 먹을래요", active: currentNodeId === "FOOD", side: "left" },
              { x: 208, text: "🛏 자세 변경", active: currentNodeId === "ENV", side: "left" },
              { x: 298, text: "🌡 추워요/더워요", active: currentNodeId === "ENV", side: "left" },
              { x: 388, text: "🤕 머리 아파요", active: currentNodeId === "PAIN", side: "right" },
              { x: 478, text: "😣 배가 아파요", active: currentNodeId === "PAIN", side: "right" },
              { x: 568, text: "🚨 간호사 호출", active: currentNodeId === "CARE", side: "right" },
              { x: 658, text: "❤️ 고마워요", active: currentNodeId === "CARE", side: "right" },
            ].map((item, idx) => (
              <g key={idx} transform={`translate(${item.x}, 242)`}>
                <rect
                  width="84"
                  height="38"
                  rx="8"
                  fill={item.active ? (item.side === "left" ? "#2F6B5C" : "#345C7D") : "#FFFFFF"}
                  stroke={item.active ? (item.side === "left" ? "#24584B" : "#284A65") : "#E2E8F0"}
                  strokeWidth={item.active ? 2 : 1}
                />
                <text
                  x="42"
                  y="24"
                  fill={item.active ? "#FFFFFF" : "#475569"}
                  fontSize="9.5"
                  fontWeight="800"
                  textAnchor="middle"
                >
                  {item.text}
                </text>
              </g>
            ))}
          </svg>
        </div>
      </div>

      {/* Dedicated Dual Option Selection Cards (Directly Above the Gauge) */}
      <div className="comm-option-cards-container">
        <button
          disabled={isCommitting || recorded}
          className={`option-card left-card ${activeDirection === "LEFT" ? "imagining" : ""}`}
          onClick={() => select("LEFT")}
        >
          <div className="card-top-bar">
            <span className="dir-tag">← LEFT (왼손 상상)</span>
            <span className="electrode-tag">C4 전극</span>
          </div>
          <div className="card-body">
            <span className="card-symbol">{currentNode.left.symbol}</span>
            <div>
              <strong className="card-label">{currentNode.left.label}</strong>
              <small className="card-english">{currentNode.left.english}</small>
              <p className="card-desc">{currentNode.left.desc}</p>
            </div>
          </div>
          {activeDirection === "LEFT" && (
            <div className="card-live-indicator left-ind">
              <Check size={14} /> {recorded ? `LEFT 예측 반영 · 선택 누적 ${left}%` : `왼손 상상 감지 중 (${left}%)`}
            </div>
          )}
        </button>

        <button
          disabled={isCommitting || recorded}
          className={`option-card right-card ${activeDirection === "RIGHT" ? "imagining" : ""}`}
          onClick={() => select("RIGHT")}
        >
          <div className="card-top-bar">
            <span className="dir-tag">RIGHT (오른손 상상) →</span>
            <span className="electrode-tag">C3 전극</span>
          </div>
          <div className="card-body">
            <span className="card-symbol">{currentNode.right.symbol}</span>
            <div>
              <strong className="card-label">{currentNode.right.label}</strong>
              <small className="card-english">{currentNode.right.english}</small>
              <p className="card-desc">{currentNode.right.desc}</p>
            </div>
          </div>
          {activeDirection === "RIGHT" && (
            <div className="card-live-indicator right-ind">
              <Check size={14} /> {recorded ? `RIGHT 예측 반영 · 선택 누적 ${right}%` : `오른손 상상 감지 중 (${right}%)`}
            </div>
          )}
        </button>
      </div>

      {/* User's Original 80% Balance Gauge */}
      <div className="evidence-bars balance-gauge" aria-live="polite">
        <div className="gauge-labels">
          <strong className="left-gauge-label">{recorded ? "LEFT 선택 누적" : "왼쪽 상상"}: {left}%</strong>
          <span>{recorded ? `선택 누적 ${THRESHOLD}%에서 확정 · 모델 확률과 별도` : `가운데(50%)에서 시작해 ${THRESHOLD}%까지 채우면 선택이 확정됩니다`}</span>
          <strong className="right-gauge-label">{recorded ? "RIGHT 선택 누적" : "오른쪽 상상"}: {right}%</strong>
        </div>
        <div className="balance-track">
          <i className="left-threshold" title="80% 임계점" />
          <i className="right-threshold" title="80% 임계점" />
          <em title="중앙 50%" />
          <span className="left-half">
            <b style={{ width: `${Math.max(0, (left - 50) * 2)}%` }} />
          </span>
          <span className="right-half">
            <b style={{ width: `${Math.max(0, (right - 50) * 2)}%` }} />
          </span>
        </div>
        <p className={uncertain ? "uncertain" : "ready"}>
          {uncertain
            ? recorded ? `선택 누적 ${confidence}% · 품질 기준을 통과한 예측만 반영합니다.` : `UNCERTAIN · ${THRESHOLD}%까지 같은 방향을 계속 상상하세요 (현재 최고: ${confidence}%).`
            : `✓ ${THRESHOLD}% 선택 임계값에 도달했습니다!`}
        </p>
      </div>

      {/* 3-Piece Neuro Suite: [ 1. Brain Map | 2. EEG Control Monitor | 3. Control Settings ] Under the Gauge! */}
      <div className="comm-neuro-suite">
        {/* 1. Left: Brain Stimulation Map (Atlas2D) */}
        <div className="neuro-suite-card brain-box">
          <div className="suite-card-header">
            <span className="suite-card-title">
              <Brain size={15} /> 뇌 자극 영역
            </span>
            <span className={`suite-badge ${activeDirection ? activeDirection.toLowerCase() : "idle"}`}>
              {activeDirection ? `${activeDirection} 활성` : "IDLE"}
            </span>
          </div>
          <div className="brain-canvas-wrap">
            <Atlas2D
              mode={recorded ? s.channelMode : "5ch"}
              activeOverride={recorded ? channels : undefined}
              selected={activeDirection === "LEFT" ? "C4" : activeDirection === "RIGHT" ? "C3" : ""}
              onSelect={() => {}}
              direction={activeDirection}
            />
          </div>
          <div className="suite-sub-note">
            <span>{activeDirection === "LEFT" ? "C4 전극 반응 (우측 운동피질)" : activeDirection === "RIGHT" ? "C3 전극 반응 (좌측 운동피질)" : "좌·우 운동상상 대기"}</span>
          </div>
        </div>

        {/* 2. Center: EEG Control Monitor (5 Channels F3, F4, C3, Cz, C4) */}
        <div className="neuro-suite-card wave-box">
          <div className="suite-card-header">
            <span className="suite-card-title">
              <Activity size={15} /> ((o)) EEG Control Monitor
            </span>
            <div className="wave-status-tags">
              <span className="wave-sub-tag">{recorded ? isStaticRecordedReplay ? "Recorded EEG · 추론 결과 재생" : "Recorded EEG · 모델 추론" : "Synthetic EEG Demo · μV illustrative"}</span>
              <strong className={`status-badge ${activeDirection ? activeDirection.toLowerCase() : "idle"}`}>
                {recorded ? s.isPlaying ? s.recordedPrediction?.quality.status ?? "READY" : s.backendStatus : activeDirection ? `${activeDirection} 활성` : "READY"}
              </strong>
            </div>
          </div>
          <Waveform
            channels={channels}
            recorded={recorded}
            samples={s.recordedPrediction?.waveform}
            playing={recorded ? s.isPlaying : Boolean(activeDirection)}
            phase={activeDirection === "RIGHT" ? 2.8 : 0.2}
          />
          {recorded && <div className="communication-playback">
            {finalSpeech ? <button className="button primary" onClick={startRecorded}>다음 문장 선택</button> : <PlayButton recorded playing={s.isPlaying} onClick={s.isPlaying ? s.stop : startRecorded} />}
            <span className="small muted">{s.backendStatus}</span>
          </div>}
          <div className="monitor-meta-grid">
            <div className="meta-item">
              <span className="meta-key">Current Trial</span>
              <span className="meta-val">{recorded ? s.recordedPrediction?.trial_id ?? "—" : history.length + 1}</span>
            </div>
            <div className="meta-item">
              <span className="meta-key">{recorded ? "Predicted Direction" : "Target Direction"}</span>
              <span className="meta-val highlight">{recorded ? s.recordedPrediction?.predicted_direction ?? "—" : activeDirection || "READY"}</span>
            </div>
            <div className="meta-item">
              <span className="meta-key">Active Channels</span>
              <span className="meta-val mono">{channels.join(" · ")}</span>
            </div>
            <div className="meta-item">
              <span className="meta-key">TTA Status</span>
              <span className={`meta-val ${s.ttaEnabled ? "status-on" : ""}`}>{s.ttaEnabled ? "ON" : "OFF"}</span>
            </div>
          </div>
          {recorded && <RecordedMetrics />}
        </div>

        {/* 3. Right: Control Settings (Settings2) */}
        <div className="neuro-suite-card settings-box">
          <Settings compact embedded />
        </div>
      </div>
    </section>
  );
}

export default CommunicationBoard;
