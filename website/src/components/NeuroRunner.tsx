import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, RoundedBox } from "@react-three/drei";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Battery, Gem, Heart, Pause, Play, Radio, RotateCcw, Trophy } from "lucide-react";
import type { Group } from "three";
import { CatmullRomCurve3, MathUtils, Vector3 } from "three";
import { useBCI } from "../store";
import { configuredChannels } from "../data/channels";
import type { Direction } from "../data/research";
import { Settings, Waveform } from "./Controls";
import { RecordedMetrics } from "./RecordedMetrics";
import "./NeuroRunner.css";

type GamePhase = "READY" | "RUNNING" | "WAITING_FOR_COMMAND" | "MOVING" | "SUCCESS" | "COLLISION" | "MISSION_COMPLETE" | "GAME_OVER" | "PAUSED";
type HistoryEntry = { id: number; trial: number; target: Direction; predicted: Direction; valid: boolean; success: boolean };
const TOTAL_MANUAL_STAGES = 20;

function Robot({ lane, phase }: { lane: Direction; phase: GamePhase }) {
  const group = useRef<Group>(null);
  useFrame(({ clock }, delta) => {
    if (!group.current) return;
    const targetX = lane === "LEFT" ? -1.15 : 1.15;
    group.current.position.x = MathUtils.damp(group.current.position.x, targetX, 8, delta);
    const moving = ["RUNNING", "MOVING"].includes(phase);
    group.current.position.y = 0.54 + Math.sin(clock.elapsedTime * (moving ? 9 : 3)) * (moving ? 0.06 : 0.025);
    group.current.rotation.z = MathUtils.damp(group.current.rotation.z, phase === "COLLISION" ? 0.22 : 0, 9, delta);
  });
  return (
    <group ref={group} position={[-1.15, .54, 2.2]} scale={1.18}>
      <RoundedBox args={[.72, .66, .58]} radius={.2} smoothness={4} castShadow>
        <meshStandardMaterial color={phase === "COLLISION" ? "#E3A07B" : "#4C8E88"} roughness={.38} />
      </RoundedBox>
      <mesh position={[0, .48, .02]} castShadow><sphereGeometry args={[.38, 32, 24]} /><meshStandardMaterial color="#FFFFFF" roughness={.28} /></mesh>
      {[-.14, .14].map((x) => <mesh key={x} position={[x, .5, -.36]}><sphereGeometry args={[.045, 16, 16]} /><meshStandardMaterial color="#4CB6A4" emissive="#54D0BB" emissiveIntensity={1.8} /></mesh>)}
      <mesh position={[0, .04, .302]}><circleGeometry args={[.1, 24]} /><meshStandardMaterial color="#66CBB7" emissive="#51BBA7" emissiveIntensity={1.1} /></mesh>
      <mesh position={[0, .24, .302]}><boxGeometry args={[.52, .07, .025]} /><meshStandardMaterial color="#DDEBEA" /></mesh>
      {[-.24,.24].map(x => <mesh key={`shoulder-${x}`} position={[x,.18,.3]} rotation={[0,0,x > 0 ? -.35 : .35]}><boxGeometry args={[.09,.26,.025]} /><meshStandardMaterial color="#DDEBEA" /></mesh>)}
      <mesh position={[0, .88, 0]}><cylinderGeometry args={[.025,.025,.18,12]} /><meshStandardMaterial color="#496C73" /></mesh>
      <mesh position={[0, .99, 0]}><sphereGeometry args={[.055,12,12]} /><meshStandardMaterial color="#64C8B4" emissive="#64C8B4" emissiveIntensity={1.3} /></mesh>
      {[-.25, .25].map((x) => <mesh key={x} position={[x, -.43, 0]}><capsuleGeometry args={[.08, .28, 5, 12]} /><meshStandardMaterial color="#E7EEF2" /></mesh>)}
      {[-.25, .25].map((x) => <mesh key={`boot-${x}`} position={[x, -.65, .06]}><sphereGeometry args={[.12,16,12]} /><meshStandardMaterial color="#294F5A" /></mesh>)}
      {[-.43, .43].map((x) => <mesh key={x} position={[x, .02, 0]} rotation={[0,0,Math.PI / 2]}><capsuleGeometry args={[.065, .26, 5, 12]} /><meshStandardMaterial color="#D8E5E7" /></mesh>)}
    </group>
  );
}

function RunnerCamera() {
  const { camera } = useThree();
  useEffect(() => {
    camera.position.set(0, 3.4, 7.2);
    camera.lookAt(0, .35, -2);
    camera.updateProjectionMatrix();
  }, [camera]);
  return null;
}

const ROAD_LENGTH = 2.76;
const ROAD_COUNT = 12;
function RoadTile({ index, moving }: { index: number; moving: boolean }) {
  const tile = useRef<Group>(null);
  useFrame((_, delta) => {
    if (!tile.current || !moving) return;
    tile.current.position.z += delta * 2.2;
    if (tile.current.position.z > 4.35)
      tile.current.position.z -= ROAD_LENGTH * ROAD_COUNT;
  });
  return (
    <group ref={tile} position={[0, 0, 3.1 - index * ROAD_LENGTH]}>
      <RoundedBox args={[3.4, .22, 2.8]} radius={.08} smoothness={3} receiveShadow>
        <meshStandardMaterial color={index % 2 ? "#68838E" : "#718B95"} roughness={.68} metalness={.08} />
      </RoundedBox>
      <mesh position={[0, .13, 0]}><boxGeometry args={[.045, .025, 2.58]} /><meshStandardMaterial color="#C5DDD8" emissive="#83BFB3" emissiveIntensity={.35} /></mesh>
      {[-1.72, 1.72].map(x => <mesh key={x} position={[x, .22, 0]}><boxGeometry args={[.07, .22, 2.64]} /><meshStandardMaterial color="#4F7883" emissive="#5BAA9B" emissiveIntensity={.45} /></mesh>)}
      {[-.82,.82].map(x => <mesh key={`lane-${x}`} position={[x,.125,0]}><boxGeometry args={[.018,.015,1.25]} /><meshStandardMaterial color="#91ADA9" transparent opacity={.55}/></mesh>)}
    </group>
  );
}

function Bomb({ x }: { x: number }) {
  const fuse = useMemo(() => new CatmullRomCurve3([
    new Vector3(.1,.35,0), new Vector3(.2,.58,.02), new Vector3(.42,.7,.03), new Vector3(.5,.54,.04),
  ]), []);
  return (
    <group position={[x,.62,0]}>
      <mesh castShadow scale={[1,1,.92]}><sphereGeometry args={[.43,32,24]} /><meshStandardMaterial color="#171D21" roughness={.42} metalness={.25} /></mesh>
      <mesh position={[.08,.39,0]} rotation={[0,0,-.32]} castShadow><cylinderGeometry args={[.14,.17,.2,18]} /><meshStandardMaterial color="#30383D" roughness={.5}/></mesh>
      <mesh><tubeGeometry args={[fuse,24,.035,8,false]} /><meshStandardMaterial color="#B66E3D" roughness={.48}/></mesh>
      <mesh position={[.51,.54,.04]}><sphereGeometry args={[.09,16,14]} /><meshStandardMaterial color="#FFB13B" emissive="#FF572F" emissiveIntensity={2.6}/></mesh>
      <pointLight position={[.51,.54,.1]} color="#FF6B3D" intensity={3.2} distance={2}/>
    </group>
  );
}

function RunnerWorld() {
  const clouds = [
    [-3.8, 1.8, 1], [3.9, 2.35, -1.8], [-4.5, 2.7, -5.4],
    [4.4, 1.7, -8.5], [-3.7, 2.15, -12], [3.8, 2.8, -15],
  ] as const;
  return (
    <group>
      {clouds.map(([x,y,z], index) => (
        <Float key={`${x}-${z}`} speed={.45 + index * .04} rotationIntensity={.03} floatIntensity={.12}>
          <group position={[x,y,z]} scale={index % 2 ? 1.05 : .85}>
            <mesh position={[-.55,0,0]}><sphereGeometry args={[.58,20,14]}/><meshStandardMaterial color="#FFFFFF" transparent opacity={.88} roughness={1}/></mesh>
            <mesh position={[0,.2,.02]}><sphereGeometry args={[.78,20,14]}/><meshStandardMaterial color="#F8FCFD" transparent opacity={.92} roughness={1}/></mesh>
            <mesh position={[.7,.02,0]}><sphereGeometry args={[.52,20,14]}/><meshStandardMaterial color="#FFFFFF" transparent opacity={.86} roughness={1}/></mesh>
            <mesh position={[.05,-.18,0]} scale={[1.7,.5,.72]}><sphereGeometry args={[.72,20,14]}/><meshStandardMaterial color="#F3FAFB" transparent opacity={.9} roughness={1}/></mesh>
          </group>
        </Float>
      ))}
    </group>
  );
}

function RunnerScene({ lane, safeLane, phase, stage }: { lane: Direction; safeLane: Direction; phase: GamePhase; stage: number }) {
  const moving = phase === "RUNNING";
  const obstacleLane = safeLane === "LEFT" ? 1.15 : -1.15;
  const crystalLane = safeLane === "LEFT" ? -1.15 : 1.15;
  return (
    <>
      <RunnerCamera />
      <color attach="background" args={["#EAF2F6"]} />
      <fog attach="fog" args={["#EAF2F6", 8, 19]} />
      <ambientLight intensity={1.8} />
      <directionalLight position={[4, 8, 5]} intensity={3.3} castShadow />
      <pointLight position={[0, 2, -2]} intensity={7} color="#8CCAC0" />
      <RunnerWorld />
      {Array.from({ length: ROAD_COUNT }, (_, i) => <RoadTile key={i} index={i} moving={moving} />)}
      <group position={[0, .38, -.8]}>
        <Bomb x={obstacleLane} />
        <Float speed={2.6} rotationIntensity={1.2} floatIntensity={.3}>
          <group position={[crystalLane, .82, 0]}>
            <mesh position={[0,.2,0]} castShadow>
              <cylinderGeometry args={[.34,.62,.3,8,1,false]} /><meshStandardMaterial color="#A7F7F0" emissive="#41D9D0" emissiveIntensity={1.8} metalness={.18} roughness={.12} flatShading />
            </mesh>
            <mesh position={[0,-.27,0]} castShadow>
              <cylinderGeometry args={[.62,.025,.66,8,1,false]} /><meshStandardMaterial color="#4ED5E4" emissive="#18B8C9" emissiveIntensity={2.1} metalness={.22} roughness={.1} flatShading />
            </mesh>
            <mesh position={[0,.37,0]}><cylinderGeometry args={[.34,.34,.025,8]} /><meshBasicMaterial color="#E6FFFF" transparent opacity={.9}/></mesh>
            <mesh position={[-.35,.24,.38]} rotation={[0,0,Math.PI/4]}><boxGeometry args={[.03,.3,.02]}/><meshBasicMaterial color="#FFFFFF"/></mesh>
            <mesh position={[-.35,.24,.38]} rotation={[0,0,-Math.PI/4]}><boxGeometry args={[.03,.3,.02]}/><meshBasicMaterial color="#FFFFFF"/></mesh>
          </group>
          <pointLight position={[crystalLane,.82,.3]} color="#4FFFE0" intensity={7} distance={4} />
        </Float>
      </group>
      <Robot lane={lane} phase={phase} />
      <mesh position={[0, 3.1, -6]}><planeGeometry args={[7, 2]} /><meshBasicMaterial color="#DCEAF0" transparent opacity={.24} /></mesh>
      <group position={[0, .15, -7.5]}>{Array.from({length: 9},(_,i)=><mesh key={`${stage}-${i}`} position={[(i%3-1)*1.7, Math.floor(i/3)*.65, 0]}><boxGeometry args={[.12,.12,.12]} /><meshStandardMaterial color="#79AAA4" emissive="#79AAA4" emissiveIntensity={.8}/></mesh>)}</group>
    </>
  );
}

export default function NeuroRunner() {
  const s = useBCI();
  const recorded = s.inputMode === "recorded";
  const totalStages = recorded ? (s.backendSessions.find(x => x.session_id === s.sessionId)?.n_online_trials ?? 20) : TOTAL_MANUAL_STAGES;
  const [phase, setPhase] = useState<GamePhase>("READY");
  const [stage, setStage] = useState(1);
  const [score, setScore] = useState(0);
  const [lives, setLives] = useState(3);
  const [lane, setLane] = useState<Direction>("LEFT");
  const [safeLane, setSafeLane] = useState<Direction>("RIGHT");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [avoided, setAvoided] = useState(0);
  const [collisions, setCollisions] = useState(0);
  const [excluded, setExcluded] = useState(0);
  const processedTrial = useRef<number | null>(null);
  const timers = useRef<number[]>([]);
  const channels = recorded && s.recordedPrediction?.active_channels?.length ? s.recordedPrediction.active_channels : configuredChannels(s.channelMode);
  const clearTimers = () => { timers.current.forEach(window.clearTimeout); timers.current = []; };
  const later = (fn: () => void, delay: number) => { timers.current.push(window.setTimeout(fn, delay)); };
  const chooseSafeLane = useCallback((): Direction => Math.random() > .5 ? "LEFT" : "RIGHT", []);

  const resetGame = () => {
    clearTimers();
    s.stop();
    if (recorded) s.setSettings({ inputMode: "recorded" });
    setPhase("READY"); setStage(1); setScore(0); setLives(3); setLane("LEFT"); setSafeLane(chooseSafeLane());
    setHistory([]); setAvoided(0); setCollisions(0); setExcluded(0); processedTrial.current = null;
  };

  useEffect(() => {
    clearTimers();
    s.stop();
    setPhase("READY"); setStage(1); setScore(0); setLives(3); setLane("LEFT"); setSafeLane(chooseSafeLane());
    setHistory([]); setAvoided(0); setCollisions(0); setExcluded(0); processedTrial.current = null;
  }, [s.participantId, s.sessionId, s.channelMode, s.recordedLowChannel, s.ttaEnabled, s.inputMode, chooseSafeLane]);
  useEffect(() => () => clearTimers(), []);

  const beginStage = useCallback(() => {
    setPhase("RUNNING");
    const runningTime = s.inputMode === "manual" ? 3400 : 3400 / s.speed;
    later(() => setPhase("WAITING_FOR_COMMAND"), runningTime);
  }, [s.inputMode, s.speed]);

  const finishStage = useCallback((direction: Direction, target: Direction, trial = stage, valid = true) => {
    if (!valid) { setExcluded(v => v + 1); setPhase("WAITING_FOR_COMMAND"); return; }
    setLane(direction); setPhase("MOVING");
    later(() => {
      const success = direction === target;
      setHistory(old => [{ id: old.length + 1, trial, target, predicted: direction, valid, success }, ...old]);
      if (success) { setScore(v => v + 10); setAvoided(v => v + 1); setPhase("SUCCESS"); }
      else { setCollisions(v => v + 1); setLives(v => recorded ? v : Math.max(0, v - 1)); setPhase("COLLISION"); }
      later(() => {
        const nextLives = success || recorded ? lives : lives - 1;
        if (!recorded && nextLives <= 0) { setPhase("GAME_OVER"); return; }
        if (trial >= totalStages) { setPhase("MISSION_COMPLETE"); return; }
        setStage(v => v + 1); setSafeLane(chooseSafeLane()); beginStage();
      }, 700);
    }, 560);
  }, [beginStage, chooseSafeLane, lives, recorded, stage, totalStages]);

  const start = () => {
    if (["MISSION_COMPLETE", "GAME_OVER"].includes(phase)) resetGame();
    if (recorded) s.play();
    beginStage();
  };
  const pause = () => { clearTimers(); s.stop(); setPhase("PAUSED"); };
  const manualCommand = (direction: Direction) => {
    if (s.inputMode !== "manual" || phase !== "WAITING_FOR_COMMAND") return;
    finishStage(direction, safeLane);
  };

  useEffect(() => {
    const p = s.recordedPrediction;
    if (!recorded || !s.isPlaying || !p || p.trial_id === processedTrial.current) return;
    processedTrial.current = p.trial_id;
    if (!p.quality.is_clean || !p.true_direction) {
      setExcluded(v => v + 1); setPhase("WAITING_FOR_COMMAND"); return;
    }
    setStage(p.trial_id); setSafeLane(p.true_direction); setPhase("WAITING_FOR_COMMAND");
    later(() => finishStage(p.predicted_direction, p.true_direction!, p.trial_id), 260);
  }, [recorded, s.isPlaying, s.recordedPrediction, finishStage]);

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.repeat || event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
      if (event.key === "ArrowLeft") manualCommand("LEFT");
      if (event.key === "ArrowRight") manualCommand("RIGHT");
    };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  });

  const validTrials = history.filter(x => x.valid);
  const recall = (label: Direction) => {
    const rows = validTrials.filter(x => x.target === label);
    return rows.length ? rows.filter(x => x.predicted === label).length / rows.length : null;
  };
  const leftRecall = recall("LEFT"), rightRecall = recall("RIGHT");
  const macroF1 = useMemo(() => {
    if (!recorded || leftRecall === null || rightRecall === null) return null;
    const f1 = (["LEFT", "RIGHT"] as Direction[]).map(label => {
      const tp = validTrials.filter(x => x.target === label && x.predicted === label).length;
      const fp = validTrials.filter(x => x.target !== label && x.predicted === label).length;
      const fn = validTrials.filter(x => x.target === label && x.predicted !== label).length;
      return tp ? 2 * tp / (2 * tp + fp + fn) : 0;
    });
    return (f1[0] + f1[1]) / 2;
  }, [recorded, validTrials.length, leftRecall, rightRecall]);
  const percent = (v: number | null) => v === null ? "—" : `${(v * 100).toFixed(1)}%`;

  return (
    <div className="neuro-runner">
      <section className="runner-shell panel">
        <div className="runner-titlebar">
          <div><span className="eyebrow">APPLICATION 02</span><h2>Neuro Runner</h2><p>LEFT / RIGHT 운동 상상 명령으로 로봇을 움직여 장애물을 피하세요.</p></div>
          <div className="runner-title-actions">
            {phase === "READY" || phase === "PAUSED" ? <button className="button primary" onClick={start}><Play size={15}/> Start</button> : <button className="button primary" onClick={pause}><Pause size={15}/> Pause</button>}
            <button className="button subtle" onClick={resetGame}><RotateCcw size={14}/> Reset</button>
          </div>
        </div>
        <div className="runner-console">
          <div className="runner-play-area">
            <div className={`runner-canvas phase-${phase.toLowerCase()}`}>
              <Canvas shadows camera={{ position: [0, 3.4, 7.2], fov: 40 }}><RunnerScene lane={lane} safeLane={safeLane} phase={phase} stage={stage}/></Canvas>
              <div className="runner-hud">
                <div><Trophy size={15}/><span>Score</span><strong>{score}</strong></div>
                <div><Battery size={15}/><span>Stage</span><strong>{stage} / {totalStages}</strong></div>
                <div><Heart size={15}/><span>Lives</span><strong>{recorded ? "∞" : "♥".repeat(lives) || "0"}</strong></div>
                <div><Radio size={15}/><span>Command</span><strong>{s.recordedPrediction?.predicted_direction ?? (phase === "WAITING_FOR_COMMAND" ? "WAITING" : lane)}</strong></div>
              </div>
              <div className="runner-lane-hints"><span>← LEFT</span><span>RIGHT →</span></div>
              {["WAITING_FOR_COMMAND","MISSION_COMPLETE","GAME_OVER","PAUSED"].includes(phase) && <div className="runner-message"><strong>{phase === "WAITING_FOR_COMMAND" ? "폭탄을 피하고, 크리스털을 획득하세요!" : phase.replaceAll("_", " ")}</strong><span>{phase === "WAITING_FOR_COMMAND" ? "LEFT 또는 RIGHT 안전 차선을 선택하세요." : phase === "MISSION_COMPLETE" ? "모든 스테이지를 완료했습니다." : phase === "GAME_OVER" ? "생명을 모두 사용했습니다." : "게임이 일시정지되었습니다."}</span></div>}
              {phase === "SUCCESS" && <div className="runner-feedback success"><Gem/> +10 CRYSTAL</div>}
              {phase === "COLLISION" && <div className="runner-feedback collision">COLLISION</div>}
            </div>
            <div className="runner-controls">
              <button disabled={s.inputMode !== "manual" || phase !== "WAITING_FOR_COMMAND"} onClick={() => manualCommand("LEFT")}><ArrowLeft/> LEFT</button>
              <button disabled={s.inputMode !== "manual" || phase !== "WAITING_FOR_COMMAND"} onClick={() => manualCommand("RIGHT")}>RIGHT <ArrowRight/></button>
            </div>
            <div className="runner-status-line"><span>EEG 추론 상태</span><strong>{recorded ? s.backendStatus : "Manual Demo · Backend 불필요"}</strong></div>
          </div>
          <div className="runner-side-stack">
            <section className="runner-side-card runner-settings">
              <Settings embedded />
            </section>
            <aside className="runner-side-card runner-monitor">
          <div className="panel-title"><Radio size={16}/> EEG Control Monitor <i className="status-dot"/></div>
          <Waveform channels={channels} playing={s.isPlaying || !recorded} recorded={recorded} samples={s.recordedPrediction?.waveform}/>
          <dl className="monitor-stats">
            <div><dt>Current Trial</dt><dd>{recorded ? s.recordedPrediction?.trial_id ?? "—" : stage}</dd></div>
            <div><dt>Target Direction</dt><dd>{recorded ? s.recordedPrediction?.true_direction ?? "—" : safeLane}</dd></div>
            <div><dt>Predicted Direction</dt><dd>{recorded ? s.recordedPrediction?.predicted_direction ?? "—" : lane}</dd></div>
            <div><dt>Active Channels</dt><dd>{channels.join(" · ")}</dd></div>
            <div><dt>TTA Status</dt><dd>{s.ttaEnabled ? "ON" : "OFF"}</dd></div>
            <div><dt>Macro-F1</dt><dd>{recorded ? percent(macroF1) : "Manual Demo"}</dd></div>
            <div><dt>Valid / Excluded</dt><dd>{validTrials.length} / {excluded}</dd></div>
            <div><dt>Observed classes</dt><dd>{[leftRecall !== null ? "LEFT" : "", rightRecall !== null ? "RIGHT" : ""].filter(Boolean).join(" · ") || "—"}</dd></div>
          </dl>
          {recorded && <RecordedMetrics />}
          <div className="log-heading">COMMAND HISTORY <span>현재 게임</span></div>
          <div className="command-history">{history.length ? history.slice(0, 12).map(row => <div key={row.id}><span className={row.success ? "cyan" : "purple"}>{row.predicted === "LEFT" ? "←" : "→"}</span><p>Trial {row.trial} · {row.success ? "장애물 회피" : "충돌"}<small>Target {row.target}</small></p><span className="mono">{row.success ? "+10" : "MISS"}</span></div>) : <p className="empty">게임 명령 기록이 여기에 표시됩니다.</p>}</div>
            </aside>
          </div>
        </div>
      </section>

      {["MISSION_COMPLETE","GAME_OVER"].includes(phase) && <section className="runner-results panel"><span className="eyebrow">GAME RESULT</span><h3>{phase.replaceAll("_", " ")}</h3><div><p><span>Final Score</span><strong>{score}</strong></p><p><span>Obstacles Avoided</span><strong>{avoided}</strong></p><p><span>Collisions</span><strong>{collisions}</strong></p>{recorded && <><p><span>Valid EEG Trials</span><strong>{validTrials.length}</strong></p><p><span>LEFT / RIGHT Recall</span><strong>{percent(leftRecall)} / {percent(rightRecall)}</strong></p><p><span>Macro-F1</span><strong>{percent(macroF1)}</strong></p><p><span>Configuration</span><strong>{s.recordedLowChannel ? "Low Channel" : s.channelMode} · TTA {s.ttaEnabled ? "ON" : "OFF"}</strong></p></>}</div><button className="button primary" onClick={resetGame}>다시 플레이하기</button></section>}
    </div>
  );
}
