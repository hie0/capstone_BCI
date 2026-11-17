import { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CircleDot,
} from "lucide-react";
import { Scene, Atlas2D } from "./Scenes";
import { HeroBust } from "./HeroBust";
import { channelConfigurations, fullMontage } from "../data/channels";
import { channelInfo, type ChannelMode } from "../data/research";
import "./WearableLanding.css";

export function WearableHero() {
  return (
    <section className="page-heading wearable-page-heading" aria-labelledby="wearable-hero-title">
      <div>
        <div className="eyebrow">
          <i className="status-dot" /> FROM LAB TO EVERYDAY LIFE
        </div>
        <h1 id="wearable-hero-title">더 적은 전극으로, 더 자유롭게.</h1>
        <p>더 간결한 연결로 일상에 이어지는 BCI를 상상합니다.</p>
      </div>
      <a href="#wearable-comparison" className="lab-status wearable-heading-reduction" title="착용의 변화 살펴보기" aria-label="16채널에서 5채널로">
        <span className="wearable-heading-caption">FEWER CHANNELS. MORE POSSIBILITIES.</span>
        <span className="wearable-heading-numbers">
          <b>16</b>
          <ArrowRight aria-hidden="true" />
          <strong>5<small>ch</small></strong>
        </span>
      </a>
    </section>
  );
}

export default function WearableLanding({ onHome }: { onHome: () => void }) {
  // Product exploration only: never changes the model/participant/playback store.
  const [mode, setMode] = useState<ChannelMode>("5ch");
  const [selected, setSelected] = useState("Cz");
  const channels = channelConfigurations[mode].channels;
  const reduction = ((16 - channels.length) / 16) * 100;
  return (
    <div className="wearable-story">
      <section
        id="wearable-comparison"
        className="wearable-story-section"
        aria-labelledby="wearable-comparison-title"
      >
        <div className="wearable-section-heading">
          <div>
            <span className="eyebrow">01 / BEFORE &amp; AFTER</span>
            <h2 id="wearable-comparison-title">착용의 복잡함을 줄이다.</h2>
          </div>
          <p>
            다전극 연구 장비에서 최소 구성의 웨어러블로.
            <br />
            전극 수와 연결 구조의 변화를 비교해보세요.
          </p>
        </div>
        <div
          className="wearable-comparison-change"
          aria-label="16채널에서 5채널로 전극 수 68.75퍼센트 감소"
        >
          <span>16ch</span>
          <ArrowRight size={22} aria-hidden="true" />
          <strong>5ch</strong>
          <b>전극 수 68.75% 감소</b>
        </div>
        <div className="wearable-comparison-grid">
          <figure className="wearable-comparison-card">
            <div className="wearable-comparison-title">
              <span>
                <b>BEFORE</b>
                <small>기존 EEG 연구 장비</small>
              </span>
              <strong>
                16<small>ch</small>
              </strong>
            </div>
            <div className="wearable-photo wearable-before-photo">
              <img
                src="./images/wearable/eeg-wearing-16ch.webp"
                alt="기존 16채널 EEG 장비를 착용한 모습"
                width="1200"
                height="1024"
              />
            </div>
            <figcaption>
              <span className="eyebrow">CONVENTIONAL RESEARCH SETUP</span>
              <h3>더 많은 전극, 더 복잡한 연결</h3>
              <p>
                두피 전반의 전극과 연결 배선을 사용하는 다채널 연구 장비의 착용
                예시입니다.
              </p>
              <span className="wearable-image-note">
                기존 EEG 장비 실제 착용 예시
              </span>
            </figcaption>
          </figure>
          <figure className="wearable-comparison-card proposed">
            <div className="wearable-comparison-title">
              <span>
                <b>AFTER</b>
                <small>제안하는 웨어러블 디자인 컨셉</small>
              </span>
              <strong>
                5<small>ch</small>
              </strong>
            </div>
            <div className="wearable-photo">
              <img
                src="./images/wearable/concept-5ch.jpg"
                alt="다섯 개의 센서와 간결한 밴드로 구성한 5채널 Wearable BCI의 생성형 디자인 컨셉 이미지"
                width="1448"
                height="1086"
              />
            </div>
            <figcaption>
              <span className="eyebrow">PROPOSED WEARABLE CONCEPT</span>
              <h3>핵심 신호에 집중한, 간결한 구성</h3>
              <p>
                F3 · F4 · C3 · Cz · C4의 연구 채널 구성을 바탕으로 제안하는 경량
                밴드 디자인입니다.
              </p>
              <span className="wearable-image-note">
                AI 생성 컨셉 이미지 · 실제 제작·착용 검증 전 단계
              </span>
            </figcaption>
          </figure>
        </div>
      </section>

      <section
        className="wearable-story-section"
        aria-labelledby="wearable-reduction-title"
      >
        <div className="wearable-section-heading">
          <div>
            <span className="eyebrow">02 / CHANNEL REDUCTION</span>
            <h2 id="wearable-reduction-title">16ch → 5ch</h2>
          </div>
          <p>
            전극 수 <strong>68.75% 감소</strong>.<br />
            같은 3D 두상에서 채널 구성을 직접 비교하세요.
          </p>
        </div>
        <div className="wearable-explorer panel">
          <div className="wearable-explorer-controls">
            <span className="eyebrow">EXPLORE THE CONFIGURATION</span>
            <div
              className="wearable-channel-switch"
              role="group"
              aria-label="웨어러블 시각화 채널 구성"
            >
              {(["16ch", "7ch", "5ch"] as const).map((value) => (
                <button
                  key={value}
                  aria-pressed={mode === value}
                  onClick={() => {
                    setMode(value);
                    setSelected("Cz");
                  }}
                >
                  <b>{value}</b>
                  <span>
                    {value === "16ch"
                      ? "Full Montage"
                      : value === "7ch"
                        ? "PM Extended"
                        : "PM Core"}
                  </span>
                </button>
              ))}
            </div>
            <div className="wearable-explorer-numbers">
              <div>
                <b>{channels.length}</b>
                <span>Active Electrodes</span>
              </div>
              <div>
                <b>
                  {reduction.toFixed(mode === "5ch" ? 2 : 1)}
                  <small>%</small>
                </b>
                <span>Channel Reduction</span>
              </div>
            </div>
            <div className="wearable-electrode-list" aria-label="전극 선택">
              {fullMontage.map((name) => (
                <button
                  key={name}
                  aria-label={`전극 ${name}`}
                  aria-pressed={selected === name}
                  className={`${channels.includes(name) ? "enabled" : ""} ${selected === name ? "selected" : ""}`}
                  onClick={() => setSelected(name)}
                >
                  {name}
                </button>
              ))}
            </div>
            <p className="wearable-selected-channel">
              <CircleDot size={15} />
              <b>{selected}</b> ·{" "}
              {channels.includes(selected) ? "활성 전극" : "비활성 위치 마커"}
            </p>
            <p className="small muted">{channelInfo(selected)}</p>
            <p className="wearable-explorer-note">
              센서 수에 따른 배치 비교입니다. 실제 EEG 추론 모델의 설정은
              변경하지 않습니다.
            </p>
          </div>
          <div className="wearable-explorer-model">
            <div className="wearable-model-top">
              <span>
                <i className="status-dot" /> WEARABLE BCI CONCEPT
              </span>
              <span>3D · DRAG TO EXPLORE</span>
            </div>
            <div className="wearable-overview-scene">
              <Scene
                fallback={
                  <Atlas2D
                    mode={mode}
                    selected={selected}
                    onSelect={setSelected}
                    activeOverride={channels}
                  />
                }
              >
                <HeroBust
                  selected={selected}
                  onSelect={setSelected}
                  activeChannels={channels}
                  labelMode="selected"
                />
              </Scene>
            </div>
            <div className="wearable-model-bottom">
              <span>
                <i className="status-dot" /> {channels.length} ACTIVE ELECTRODES
              </span>
              <span>채널 배치 시각화 · 미제작 컨셉</span>
            </div>
          </div>
        </div>
      </section>

      <section
        className="wearable-story-section wearable-everyday"
        aria-labelledby="wearable-everyday-title"
      >
        <div className="wearable-everyday-image">
          <img
            src="./images/wearable/everyday-concept.jpg"
            alt="웨어러블 BCI를 착용하고 밝은 거실에서 스마트홈을 사용하는 미래 일상 컨셉"
            width="1600"
            height="900"
            loading="lazy"
          />
          <span className="wearable-photo-badge">
            EVERYDAY APPLICATION · CONCEPT
          </span>
        </div>
        <div className="wearable-everyday-copy">
          <span className="eyebrow">03 / EVERYDAY APPLICATION</span>
          <h2 id="wearable-everyday-title">
            생각의 신호가,
            <br />
            일상의 제어로.
          </h2>
          <p>
            조명을 켜고, 커튼을 열고, 공간의 온도를 바꾸는 일.
            <br />
            웨어러블 BCI가 일상과 만나는 가능성을 탐색합니다.
          </p>
          <ul>
            <li>
              <Check size={15} /> 조명 · 커튼 · 온도 · TV 제어
            </li>
            <li>
              <Check size={15} /> LEFT / RIGHT 운동 상상 인터랙션
            </li>
          </ul>
          <button className="button primary" onClick={onHome}>
            Smart Home 체험하기 <ArrowUpRight size={17} />
          </button>
          <p className="wearable-image-note">
            이미지는 AI 생성 활용 컨셉입니다. 실제 저채널 웨어러블 하드웨어의
            제작 또는 검증을 의미하지 않습니다.
          </p>
        </div>
      </section>
    </div>
  );
}
