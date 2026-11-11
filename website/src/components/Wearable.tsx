import { useState } from "react";
import { ArrowRight, CircleDot, Layers3 } from "lucide-react";
import { useBCI } from "../store";
import { Brain, Scene, Atlas2D, activeChannels } from "./Scenes";
import {
  channelInfo,
  type ChannelMode,
  type Direction,
} from "../data/research";
export default function Wearable({ onHome }: { onHome: () => void }) {
  const s = useBCI();
  const [selected, setSelected] = useState("C4");
  const [direction, setDirection] = useState<Direction>("LEFT");
  const [flat, setFlat] = useState(false);
  const count = activeChannels(s.channelMode).length;
  return (
    <>
      <div className="workspace-heading">
        <div>
          <span className="eyebrow">APPLICATION 02</span>
          <h2>
            Wearable BCI Experience <span>작은 구성, 새로운 가능성</span>
          </h2>
        </div>
        <span className="badge">가상 디바이스 콘셉트</span>
      </div>
      <div className="wearable-layout">
        <div className="panel wearable-settings">
          <div className="panel-title">
            <Layers3 size={16} /> Headset configuration
          </div>
          {(["16ch", "5ch", "7ch"] as ChannelMode[]).map((mode, i) => (
            <button
              className={`config-card ${s.channelMode === mode ? "active" : ""}`}
              key={mode}
              onClick={() => s.setSettings({ channelMode: mode })}
            >
              <span className="config-number">
                {parseInt(mode)}
                <small>CH</small>
              </span>
              <span>
                <strong>
                  {["Full montage", "Core channels", "Extended concept"][i]}
                </strong>
                <small>
                  {
                    [
                      "전체 전극 구성",
                      "감각운동 중심 핵심 구성",
                      "Core + T7 / T8 · 미검증 예시",
                    ][i]
                  }
                </small>
              </span>
              <i />
            </button>
          ))}
          <p className="note">
            7ch 피험자별 검증 프로파일은 제공되지 않았습니다. 현재 7ch는 배치
            체험용 콘셉트이며 연구의 실제 선정 결과가 아닙니다.
          </p>
          <label className="wearable-model">
            Model
            <select
              value={s.modelId}
              onChange={(e) => s.setSettings({ modelId: e.target.value })}
            >
              <option value="low-channel-tta">Low-channel pipeline</option>
              <option value="baseline">16ch baseline pipeline</option>
            </select>
          </label>
          <div className="toggle-row">
            <span>TTA · 설정 공유</span>
            <button
              role="switch"
              aria-label="Wearable TTA"
              aria-checked={s.ttaEnabled}
              className={`switch ${s.ttaEnabled ? "on" : ""}`}
              onClick={() => s.setSettings({ ttaEnabled: !s.ttaEnabled })}
            >
              <i />
            </button>
          </div>
          <div className="panel-title">Motor imagery</div>
          <div className="segmented">
            <button
              className={direction === "LEFT" ? "active" : ""}
              onClick={() => setDirection("LEFT")}
            >
              LEFT MI
            </button>
            <button
              className={direction === "RIGHT" ? "active purple" : ""}
              onClick={() => setDirection("RIGHT")}
            >
              RIGHT MI
            </button>
          </div>
          <p className="small muted">
            {direction === "LEFT"
              ? "왼손 → 우측 감각운동 영역(C4)"
              : "오른손 → 좌측 감각운동 영역(C3)"}
            <br />
            대측성 관계의 교육용 표현입니다. 실제 뇌 활성도 측정이 아닙니다.
          </p>
        </div>
        <div className="panel head-panel">
          <div className="room-top">
            <span>CHANNEL EXPLORER</span>
            <button className="text-button" onClick={() => setFlat(!flat)}>
              {flat ? "3D 보기" : "2D 배치도"}
            </button>
          </div>
          <div className="head-scene">
            {flat ? (
              <Atlas2D
                mode={s.channelMode}
                selected={selected}
                onSelect={setSelected}
                direction={direction}
              />
            ) : (
              <Scene
                fallback={
                  <Atlas2D
                    mode={s.channelMode}
                    selected={selected}
                    onSelect={setSelected}
                    direction={direction}
                  />
                }
              >
                <Brain
                  mode={s.channelMode}
                  selected={selected}
                  onSelect={setSelected}
                  direction={direction}
                />
              </Scene>
            )}
          </div>
          <div className="head-footer">
            <span>
              <i className="status-dot" /> {count} ACTIVE ELECTRODES
            </span>
            <span>전극 클릭 · 드래그 회전</span>
          </div>
        </div>
        <div className="panel channel-details">
          <div className="panel-title">
            <CircleDot size={16} /> Channel details
          </div>
          <strong className="electrode-name">{selected}</strong>
          <span className="badge">
            {activeChannels(s.channelMode).includes(selected)
              ? "활성 전극"
              : "제외 전극"}
          </span>
          <h3>해부학적 위치와 역할</h3>
          <p>{channelInfo(selected)}</p>
          <h3>선정과 잡음</h3>
          <p>
            핵심 구성은 감각운동 정보를 유지하면서 입력 차원을 줄이는 데 초점을
            둡니다. 모든 전극은 접촉 상태와 움직임에 따른 잡음의 영향을 받을 수
            있습니다.
          </p>
          <div className="mini-metrics">
            <div>
              <strong>{count}</strong>
              <span>활성 채널</span>
            </div>
            <div>
              <strong>
                {(((16 - count) / 16) * 100).toFixed(1)}
                <small>%</small>
              </strong>
              <span>전극 감축률</span>
            </div>
          </div>
          <button className="button primary" onClick={onHome}>
            이 구성으로 스마트홈 체험 <ArrowRight size={16} />
          </button>
        </div>
      </div>
      <div className="panel comparison-table">
        <div className="panel-title">
          Device comparison{" "}
          <span className="muted">하드웨어 제작·검증 전 단계</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>비교 항목</th>
              <th>Full 16ch</th>
              <th>Core 5ch</th>
              <th>현재 {s.channelMode}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>전극 수 / 감축률</td>
              <td>16 / 0%</td>
              <td>5 / 68.75%</td>
              <td>
                {count} / {(((16 - count) / 16) * 100).toFixed(2)}%
              </td>
            </tr>
            <tr>
              <td>대칭 공분산 독립 원소 n(n+1)/2</td>
              <td>136</td>
              <td>15</td>
              <td>{(count * (count + 1)) / 2}</td>
            </tr>
            <tr>
              <td>공분산 행렬 전체 원소 n²</td>
              <td>256</td>
              <td>25</td>
              <td>{count * count}</td>
            </tr>
            <tr>
              <td>온라인 사후 재분석 · TTA 적용 BA</td>
              <td>70.11%</td>
              <td colSpan={2}>
                Low-channel 통합 74.66% · 5ch/7ch 개별 값 미제공
              </td>
            </tr>
            <tr>
              <td>웨어러블 가능성</td>
              <td>전체 두피 배치</td>
              <td colSpan={2}>
                소형화 설계 가능성 탐색 · 비용·착용시간·배터리 미검증
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
