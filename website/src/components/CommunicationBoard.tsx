import { useEffect, useRef, useState } from "react";
import { Accessibility, Droplets, HandHelping, RotateCcw, Soup, Stethoscope, Volume2 } from "lucide-react";
import { Atlas2D } from "./Scenes";
import { Waveform } from "./Controls";
import type { Direction } from "../data/research";
import "./CommunicationBoard.css";

type Branch = "BASIC" | "CARE" | null;
const THRESHOLD = 80;
const STEP = 10;

const choices = {
  BASIC: {
    LEFT: { label: "목말라요. 물을 주세요.", english: "WATER", icon: Droplets },
    RIGHT: { label: "배고파요.", english: "HUNGRY", icon: Soup },
  },
  CARE: {
    LEFT: { label: "아파요. 도와주세요.", english: "PAIN", icon: Stethoscope },
    RIGHT: { label: "소리를 키워주세요.", english: "VOLUME UP", icon: Accessibility },
  },
} as const;

export default function CommunicationBoard() {
  const [branch, setBranch] = useState<Branch>(null);
  const [left, setLeft] = useState(50);
  const [activeDirection, setActiveDirection] = useState<Direction>();
  const [result, setResult] = useState("표현할 항목을 선택하세요.");
  const [isCommitting, setIsCommitting] = useState(false);
  const commitTimer = useRef<number | undefined>(undefined);
  const right = 100 - left;
  const confidence = Math.max(left, right);
  const uncertain = confidence < THRESHOLD;

  const resetEvidence = () => setLeft(50);
  const reset = () => {
    window.clearTimeout(commitTimer.current);
    setBranch(null);
    resetEvidence();
    setActiveDirection(undefined);
    setResult("표현할 항목을 선택하세요.");
    setIsCommitting(false);
  };
  useEffect(() => () => window.clearTimeout(commitTimer.current), []);
  const speak = (text: string) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "ko-KR";
    window.speechSynthesis.speak(utterance);
  };
  const select = (direction: Direction) => {
    if (isCommitting) return;
    setActiveDirection(direction);
    const nextLeft = Math.max(0, Math.min(100, left + (direction === "LEFT" ? STEP : -STEP)));
    setLeft(nextLeft);
    const nextConfidence = direction === "LEFT" ? nextLeft : 100 - nextLeft;
    if (nextConfidence < THRESHOLD) {
      setResult(`${direction} 운동 상상을 유지해 주세요. ${nextConfidence}%`);
      return;
    }
    setIsCommitting(true);
    setResult(`${THRESHOLD}% 선택 기준에 도달했습니다.`);
    commitTimer.current = window.setTimeout(() => {
      if (!branch) {
        const nextBranch = direction === "LEFT" ? "BASIC" : "CARE";
        setBranch(nextBranch);
        resetEvidence();
        setActiveDirection(undefined);
        setResult(nextBranch === "BASIC" ? "기본 욕구를 선택했습니다. 세부 메시지를 선택하세요." : "상태·도움을 선택했습니다. 세부 메시지를 선택하세요.");
      } else {
        const choice = choices[branch][direction];
        setResult(choice.label);
        speak(choice.label);
        resetEvidence();
      }
      setIsCommitting(false);
    }, 450);
  };
  const options = branch
    ? [choices[branch].LEFT, choices[branch].RIGHT]
    : [
        { label: "기본 욕구", english: "BASIC NEEDS", icon: Droplets },
        { label: "상태·도움", english: "CARE & SUPPORT", icon: HandHelping },
      ];

  return (
    <section className="communication-board panel" aria-labelledby="communication-title">
      <header>
        <div>
          <span className="eyebrow">BCI COMMUNICATION</span>
          <h2 id="communication-title" aria-label="BCI Communication Board">무엇이 필요하세요?</h2>
        </div>
        <div className="communication-progress" aria-label="선택 단계">
          <span className="active"><b>1</b> {branch ? (branch === "BASIC" ? "기본 욕구" : "상태·도움") : "범주 선택"}</span><i>—</i>
          <span className={branch ? "active" : ""}><b>2</b> 세부 메시지</span><i>—</i><span><b>3</b> 음성 출력</span>
        </div>
        <button className="button subtle" onClick={reset}><RotateCcw size={15} /> 처음으로</button>
      </header>

      <p className="communication-intro">
        말을 하거나 몸을 움직이기 어려운 환자와 사용자를 위한 의사소통 보조 체험입니다.
        <span>전체 선택 구조를 먼저 확인한 뒤, 같은 방향을 80%까지 반복해 원하는 문장을 선택합니다.</span>
      </p>

      <div className="communication-neuro-feedback top-neuro">
        <div className="feedback-title"><span>뇌 자극 · EEG 신호</span><strong>{activeDirection ?? "READY"}</strong></div>
        <div className="neuro-compact">
          <div className="communication-brain"><Atlas2D mode="5ch" selected={activeDirection === "LEFT" ? "C4" : activeDirection === "RIGHT" ? "C3" : ""} onSelect={() => {}} direction={activeDirection} /></div>
          <Waveform channels={["C3", "Cz", "C4"]} playing={Boolean(activeDirection)} phase={activeDirection === "RIGHT" ? 2.8 : .2} />
          <small>{activeDirection === "LEFT" ? "왼손 상상 · 오른쪽 감각운동 영역 강조" : activeDirection === "RIGHT" ? "오른손 상상 · 왼쪽 감각운동 영역 강조" : "LEFT 또는 RIGHT를 반복해 상상하세요."}</small>
        </div>
      </div>

      <div className="communication-dashboard">
        <div className="communication-choice-area">
          <div className={`communication-options ${branch ? `second-step branch-${branch.toLowerCase()}` : "first-step"}`}>
            {options.map((option, index) => {
              const Icon = option.icon;
              const direction: Direction = index === 0 ? "LEFT" : "RIGHT";
              return (
                <button disabled={isCommitting} key={option.english} className={`${direction.toLowerCase()} ${activeDirection === direction ? "imagining" : ""}`} onClick={() => select(direction)}>
                  <span>{direction === "LEFT" ? "← LEFT" : "RIGHT →"}</span><Icon size={27} />
                  <strong>{option.label}</strong><small>{option.english}</small>
                </button>
              );
            })}
          </div>

          <div className="evidence-bars balance-gauge" aria-live="polite">
            <div className="gauge-labels"><strong>왼쪽 {left}%</strong><span>가운데에서 시작해 {THRESHOLD}%까지 채우면 선택돼요</span><strong>오른쪽 {right}%</strong></div>
            <div className="balance-track">
              <i className="left-threshold" /><i className="right-threshold" /><em />
              <span className="left-half"><b style={{ width: `${Math.max(0, (left - 50) * 2)}%` }} /></span>
              <span className="right-half"><b style={{ width: `${Math.max(0, (right - 50) * 2)}%` }} /></span>
            </div>
            <p className={uncertain ? "uncertain" : "ready"}>{uncertain ? `UNCERTAIN · ${THRESHOLD}%까지 같은 방향을 계속 상상하세요.` : `${THRESHOLD}% 선택 임계값에 도달했습니다.`}</p>
          </div>
        </div>

        <aside className="communication-rail">
          <div className="communication-tree" aria-label="의사소통 선택 구조">
            <div className="rail-title">선택 경로</div>
            <div className="tree-root">질문</div>
            <div className="tree-main-connector"><i /><span /><i /></div>
            <div className="tree-branches">
              <div className={branch === "BASIC" ? "active" : ""}>
                <strong>기본 욕구</strong>
                <div className="tree-child-connector"><i /><span /><i /></div>
                <div className="tree-children"><span>목말라요. 물을 주세요.</span><span>배고파요.</span></div>
              </div>
              <div className={branch === "CARE" ? "active" : ""}>
                <strong>상태·도움</strong>
                <div className="tree-child-connector"><i /><span /><i /></div>
                <div className="tree-children"><span>아파요. 도와주세요.</span><span>소리를 키워주세요.</span></div>
              </div>
            </div>
            <small>진한 선과 색은 현재 선택 경로입니다.</small>
          </div>

        </aside>
      </div>

      <div className="communication-output" aria-live="polite"><Volume2 size={24} /><div><span>VOICE OUTPUT</span><strong>“{result}”</strong></div></div>
      <p className="communication-note">교육용 합성 명령 시뮬레이션이며 실제 EEG 추론 결과가 아닙니다.</p>
    </section>
  );
}
