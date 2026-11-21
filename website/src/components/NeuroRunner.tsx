import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, RoundedBox } from "@react-three/drei";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Battery, Brain, Heart, Pause, Play, Radio, RotateCcw, Sliders, Star, Trophy } from "lucide-react";
import type { Group, Mesh } from "three";
import { CatmullRomCurve3, MathUtils, Shape, Vector3 } from "three";
import { useBCI } from "../store";
import { configuredChannels } from "../data/channels";
import type { Direction } from "../data/research";
import type { BackendPrediction } from "../data/backend";
import { Settings, Waveform } from "./Controls";
import { RecordedMetrics } from "./RecordedMetrics";
import { Atlas2D } from "./Scenes";
import "./NeuroRunner.css";

type GamePhase = "READY" | "RUNNING" | "WAITING_FOR_COMMAND" | "SUCCESS" | "COLLISION" | "PASSING" | "MISSION_COMPLETE" | "GAME_OVER" | "PAUSED" | "NEXT_TRIAL";
type HistoryEntry = { id: number; trial: number; target: Direction; predicted: Direction; valid: boolean; success: boolean };
const TOTAL_MANUAL_STAGES = 20;
const OBSTACLE_START_Z = -24;
const STAR_EXTRUSION_OPTIONS = { depth: 0.18, bevelEnabled: true, bevelSegments: 3, steps: 1, bevelSize: 0.04, bevelThickness: 0.04 };

/**
 * Fall Guys Style Cute Yellow Jelly Bean Character
 */
function JellyBeanCharacter({ lane, phase }: { lane: Direction; phase: GamePhase }) {
  const group = useRef<Group>(null);
  const legLeft = useRef<Group>(null);
  const legRight = useRef<Group>(null);
  const armLeft = useRef<Group>(null);
  const armRight = useRef<Group>(null);
  const propeller = useRef<Mesh>(null);

  useFrame(({ clock }, delta) => {
    if (!group.current) return;
    const targetX = lane === "LEFT" ? -1.15 : 1.15;
    group.current.position.x = MathUtils.damp(group.current.position.x, targetX, 12, delta);

    const moving = phase === "RUNNING" || phase === "PASSING" || phase === "NEXT_TRIAL";
    const runSpeed = moving ? 13 : 3.5;
    const time = clock.elapsedTime;

    if (propeller.current) {
      propeller.current.rotation.y += delta * (moving ? 18 : 3.5);
    }

    if (moving) {
      const roll = Math.sin(time * runSpeed) * 0.14;
      group.current.rotation.z = MathUtils.damp(group.current.rotation.z, roll, 12, delta);
      group.current.rotation.y = Math.cos(time * runSpeed) * 0.08;
      group.current.rotation.x = MathUtils.damp(group.current.rotation.x, 0.08, 10, delta);
      group.current.position.y = 0.62 + Math.abs(Math.sin(time * runSpeed)) * 0.09;

      const legAngle = Math.sin(time * runSpeed) * 0.55;
      if (legLeft.current) legLeft.current.rotation.x = legAngle;
      if (legRight.current) legRight.current.rotation.x = -legAngle;

      if (armLeft.current) armLeft.current.rotation.x = -legAngle * 0.7;
      if (armRight.current) armRight.current.rotation.x = legAngle * 0.7;
    } else if (phase === "COLLISION") {
      group.current.position.y = MathUtils.damp(group.current.position.y, 0.38, 12, delta);
      group.current.rotation.z = MathUtils.damp(group.current.rotation.z, 0.55, 12, delta);
      group.current.rotation.x = MathUtils.damp(group.current.rotation.x, -0.65, 12, delta);
      if (armLeft.current) armLeft.current.rotation.z = 0.8;
      if (armRight.current) armRight.current.rotation.z = -0.8;
    } else if (phase === "SUCCESS") {
      group.current.position.y = 0.68 + Math.abs(Math.sin(time * 12)) * 0.18;
      group.current.rotation.z = MathUtils.damp(group.current.rotation.z, 0, 12, delta);
      group.current.rotation.x = MathUtils.damp(group.current.rotation.x, -0.1, 10, delta);
      if (armLeft.current) armLeft.current.rotation.z = -0.7 + Math.sin(time * 12) * 0.3;
      if (armRight.current) armRight.current.rotation.z = 0.7 - Math.sin(time * 12) * 0.3;
    } else {
      group.current.position.y = 0.6 + Math.sin(time * 3) * 0.025;
      group.current.rotation.z = MathUtils.damp(group.current.rotation.z, 0, 8, delta);
      group.current.rotation.x = MathUtils.damp(group.current.rotation.x, 0, 8, delta);
      group.current.rotation.y = MathUtils.damp(group.current.rotation.y, 0, 8, delta);
      if (legLeft.current) legLeft.current.rotation.x = 0;
      if (legRight.current) legRight.current.rotation.x = 0;
      if (armLeft.current) armLeft.current.rotation.set(0, 0, 0);
      if (armRight.current) armRight.current.rotation.set(0, 0, 0);
    }
  });

  return (
    <group ref={group} position={[-1.15, 0.6, 2.2]} scale={1.22}>
      {/* Cute Lemon Yellow Jelly Bean Body */}
      <mesh castShadow position={[0, 0.15, 0]}>
        <capsuleGeometry args={[0.38, 0.48, 16, 24]} />
        <meshStandardMaterial
          color={phase === "COLLISION" ? "#FCA5A5" : "#FACC15"}
          roughness={0.28}
          metalness={0.04}
        />
      </mesh>

      {/* Cute White Tail Accent */}
      <mesh position={[0, -0.06, 0.28]}>
        <sphereGeometry args={[0.16, 16, 14]} />
        <meshStandardMaterial color="#FFFFFF" roughness={0.35} />
      </mesh>

      {/* Propeller Beanie (Red & Orange Hat on head) */}
      <group position={[0, 0.72, 0]}>
        <mesh position={[0, 0.02, 0]}>
          <sphereGeometry args={[0.2, 20, 14, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#FB923C" roughness={0.3} />
        </mesh>
        <mesh position={[0, 0.08, 0]}>
          <cylinderGeometry args={[0.02, 0.02, 0.1, 10]} />
          <meshStandardMaterial color="#333333" />
        </mesh>
        <mesh ref={propeller} position={[0, 0.13, 0]}>
          <boxGeometry args={[0.54, 0.02, 0.08]} />
          <meshStandardMaterial color="#EF4444" roughness={0.25} />
        </mesh>
      </group>

      {/* Toned-down Sage BCI Sensor Headband */}
      <mesh position={[0, 0.58, 0]}>
        <torusGeometry args={[0.385, 0.028, 12, 32]} />
        <meshStandardMaterial color="#4D7C5F" roughness={0.35} />
      </mesh>
      {[-0.22, 0, 0.22].map((x, i) => (
        <mesh key={i} position={[x, 0.6, 0.34]}>
          <sphereGeometry args={[0.045, 14, 12]} />
          <meshStandardMaterial color="#38BDF8" emissive="#0284C7" emissiveIntensity={1.8} />
        </mesh>
      ))}

      {/* Mini Green/Mint Backpack */}
      <group position={[0, 0.16, 0.32]}>
        <RoundedBox args={[0.36, 0.38, 0.15]} radius={0.06} smoothness={3} castShadow>
          <meshStandardMaterial color="#10B981" roughness={0.3} />
        </RoundedBox>
        <mesh position={[0, -0.04, 0.08]}>
          <boxGeometry args={[0.26, 0.18, 0.04]} />
          <meshStandardMaterial color="#F0FDF4" roughness={0.3} />
        </mesh>
        <mesh position={[0, 0.1, 0.08]}>
          <sphereGeometry args={[0.035, 12, 12]} />
          <meshStandardMaterial color="#FACC15" emissive="#EAB308" emissiveIntensity={2.2} />
        </mesh>
      </group>

      {/* Left Leg & Shoe */}
      <group ref={legLeft} position={[-0.18, -0.22, 0]}>
        <mesh position={[0, -0.14, 0]} castShadow>
          <capsuleGeometry args={[0.085, 0.18, 8, 12]} />
          <meshStandardMaterial color="#FACC15" roughness={0.3} />
        </mesh>
        <mesh position={[0, -0.27, 0.04]} castShadow>
          <sphereGeometry args={[0.13, 16, 12]} />
          <meshStandardMaterial color="#365314" roughness={0.35} />
        </mesh>
      </group>

      {/* Right Leg & Shoe */}
      <group ref={legRight} position={[0.18, -0.22, 0]}>
        <mesh position={[0, -0.14, 0]} castShadow>
          <capsuleGeometry args={[0.085, 0.18, 8, 12]} />
          <meshStandardMaterial color="#FACC15" roughness={0.3} />
        </mesh>
        <mesh position={[0, -0.27, 0.04]} castShadow>
          <sphereGeometry args={[0.13, 16, 12]} />
          <meshStandardMaterial color="#365314" roughness={0.35} />
        </mesh>
      </group>

      {/* Left Arm */}
      <group ref={armLeft} position={[-0.38, 0.18, 0.05]}>
        <mesh rotation={[0, 0, 0.35]} castShadow>
          <capsuleGeometry args={[0.07, 0.22, 6, 10]} />
          <meshStandardMaterial color="#FACC15" roughness={0.3} />
        </mesh>
        <mesh position={[-0.08, -0.14, 0]}>
          <sphereGeometry args={[0.09, 12, 10]} />
          <meshStandardMaterial color="#FFFFFF" roughness={0.4} />
        </mesh>
      </group>

      {/* Right Arm */}
      <group ref={armRight} position={[0.38, 0.18, 0.05]}>
        <mesh rotation={[0, 0, -0.35]} castShadow>
          <capsuleGeometry args={[0.07, 0.22, 6, 10]} />
          <meshStandardMaterial color="#FACC15" roughness={0.3} />
        </mesh>
        <mesh position={[0.08, -0.14, 0]}>
          <sphereGeometry args={[0.09, 12, 10]} />
          <meshStandardMaterial color="#FFFFFF" roughness={0.4} />
        </mesh>
      </group>
    </group>
  );
}

function RunnerCamera() {
  const { camera } = useThree();
  useEffect(() => {
    camera.position.set(0, 3.5, 7.3);
    camera.lookAt(0, 0.45, -2);
    camera.updateProjectionMatrix();
  }, [camera]);
  return null;
}

/**
 * Continuous Seamless Track with Toned-down Green / Olive Guardrails
 */
const ROAD_LENGTH = 3.0;
const ROAD_COUNT = 16;
function RoadTile({ index, moving }: { index: number; moving: boolean }) {
  const tile = useRef<Group>(null);
  useFrame((_, delta) => {
    if (!tile.current || !moving) return;
    tile.current.position.z += delta * 2.8;
    if (tile.current.position.z > 6.0) {
      tile.current.position.z -= ROAD_LENGTH * ROAD_COUNT;
    }
  });

  const isEven = index % 2 === 0;
  return (
    <group ref={tile} position={[0, 0, 4.5 - index * ROAD_LENGTH]}>
      {/* Floor Block: Toned-down Soft Sage and Light Cream */}
      <mesh receiveShadow position={[0, -0.1, 0]}>
        <boxGeometry args={[3.6, 0.2, ROAD_LENGTH]} />
        <meshStandardMaterial
          color={isEven ? "#86B393" : "#EDE6CE"}
          roughness={0.45}
          metalness={0.02}
        />
      </mesh>

      {/* Center White Line */}
      <mesh position={[0, 0.005, 0]}>
        <boxGeometry args={[0.08, 0.01, ROAD_LENGTH]} />
        <meshStandardMaterial color="#FFFFFF" roughness={0.3} />
      </mesh>

      {/* Toned-down Green Pillars / Guardrails on both sides */}
      {[-1.82, 1.82].map((x) => (
        <group key={x} position={[x, 0.18, 0]}>
          <mesh rotation={[Math.PI / 2, 0, 0]} castShadow>
            <cylinderGeometry args={[0.14, 0.14, ROAD_LENGTH, 16]} />
            <meshStandardMaterial
              color="#4D7C5F"
              roughness={0.35}
            />
          </mesh>
          <mesh position={[0, -0.14, 0]}>
            <cylinderGeometry args={[0.06, 0.07, 0.24, 10]} />
            <meshStandardMaterial color="#E2E8F0" roughness={0.4} />
          </mesh>
        </group>
      ))}

      {/* Lane divider soft dots */}
      {[-0.92, 0.92].map((x) => (
        <group key={`dots-${x}`}>
          {[-0.75, 0.75].map((z) => (
            <mesh key={z} position={[x, 0.01, z]}>
              <cylinderGeometry args={[0.07, 0.07, 0.015, 14]} />
              <meshStandardMaterial color="#FFFFFF" transparent opacity={0.65} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}

/**
 * Cartoon Bomb Obstacle
 */
function CartoonBomb({ x, isHit }: { x: number; isHit: boolean }) {
  const fuseCurve = useMemo(() => new CatmullRomCurve3([
    new Vector3(0.05, 0.42, 0),
    new Vector3(0.16, 0.62, 0.02),
    new Vector3(0.35, 0.74, 0.04),
    new Vector3(0.48, 0.64, 0.05),
  ]), []);

  const bombRef = useRef<Group>(null);
  const sparkRef = useRef<Mesh>(null);

  useFrame(({ clock }, delta) => {
    if (bombRef.current) {
      const targetScale = isHit ? 1.45 : 1.0;
      bombRef.current.scale.x = MathUtils.damp(bombRef.current.scale.x, targetScale, 15, delta);
      bombRef.current.scale.y = MathUtils.damp(bombRef.current.scale.y, targetScale, 15, delta);
      bombRef.current.scale.z = MathUtils.damp(bombRef.current.scale.z, targetScale, 15, delta);
    }
    if (sparkRef.current) {
      const s = 0.85 + Math.sin(clock.elapsedTime * 24) * 0.35;
      sparkRef.current.scale.set(s, s, s);
    }
  });

  return (
    <group ref={bombRef} position={[x, 0.64, 0]}>
      <mesh castShadow>
        <sphereGeometry args={[0.48, 32, 24]} />
        <meshStandardMaterial
          color={isHit ? "#EF4444" : "#1E293B"}
          emissive={isHit ? "#DC2626" : "#000000"}
          emissiveIntensity={isHit ? 1.8 : 0}
          roughness={0.32}
          metalness={0.2}
        />
      </mesh>
      <mesh position={[0.06, 0.42, 0]} rotation={[0, 0, -0.15]} castShadow>
        <cylinderGeometry args={[0.16, 0.19, 0.16, 18]} />
        <meshStandardMaterial color="#FBBF24" metalness={0.7} roughness={0.25} />
      </mesh>
      <mesh>
        <tubeGeometry args={[fuseCurve, 20, 0.038, 8, false]} />
        <meshStandardMaterial color="#D97706" roughness={0.6} />
      </mesh>
      <mesh ref={sparkRef} position={[0.48, 0.64, 0.05]}>
        <sphereGeometry args={[0.11, 16, 14]} />
        <meshStandardMaterial color="#EF4444" emissive="#F59E0B" emissiveIntensity={3.2} />
      </mesh>
      <pointLight position={[0.48, 0.64, 0.12]} color={isHit ? "#EF4444" : "#F59E0B"} intensity={isHit ? 12 : 4.5} distance={3} />
    </group>
  );
}

/**
 * 3D Golden Star Coin Collectible
 */
function GoldenStarCoin({ x, isCollected }: { x: number; isCollected: boolean }) {
  const starShape = useMemo(() => {
    const shape = new Shape();
    const points = 5;
    const outerRadius = 0.52;
    const innerRadius = 0.25;
    for (let i = 0; i < points * 2; i++) {
      const radius = i % 2 === 0 ? outerRadius : innerRadius;
      const angle = (i * Math.PI) / points - Math.PI / 2;
      const px = Math.cos(angle) * radius;
      const py = Math.sin(angle) * radius;
      if (i === 0) shape.moveTo(px, py);
      else shape.lineTo(px, py);
    }
    shape.closePath();
    return shape;
  }, []);

  const starGroup = useRef<Group>(null);
  const starMesh = useRef<Mesh>(null);

  useFrame((_, delta) => {
    if (starMesh.current) {
      starMesh.current.rotation.y += delta * (isCollected ? 8.5 : 2.2);
    }
    if (starGroup.current) {
      if (isCollected) {
        starGroup.current.position.y = MathUtils.damp(starGroup.current.position.y, 1.6, 10, delta);
        const curScale = starGroup.current.scale.x;
        const targetScale = MathUtils.damp(curScale, 1.4, 10, delta);
        starGroup.current.scale.set(targetScale, targetScale, targetScale);
      } else {
        starGroup.current.position.y = 0.9;
        starGroup.current.scale.set(1, 1, 1);
      }
    }
  });

  return (
    <Float speed={2.8} rotationIntensity={0.2} floatIntensity={0.3}>
      <group ref={starGroup} position={[x, 0.9, 0]}>
        <mesh ref={starMesh} castShadow position={[0, 0, -0.09]}>
          <extrudeGeometry
            args={[
              starShape,
              STAR_EXTRUSION_OPTIONS,
            ]}
          />
          <meshStandardMaterial
            color="#FBBF24"
            emissive={isCollected ? "#FDE047" : "#D97706"}
            emissiveIntensity={isCollected ? 1.5 : 0.45}
            metalness={0.88}
            roughness={0.16}
          />
        </mesh>
        <mesh position={[0, 0, 0.14]}>
          <sphereGeometry args={[0.07, 14, 12]} />
          <meshStandardMaterial color="#FFFFFF" emissive="#FEF08A" emissiveIntensity={2.5} />
        </mesh>
        <pointLight position={[0, 0, 0.25]} color="#FDE047" intensity={isCollected ? 14 : 5} distance={4} />
      </group>
    </Float>
  );
}

/**
 * Obstacle Track Group
 */
const MemoCartoonBomb = memo(CartoonBomb);
const MemoGoldenStarCoin = memo(GoldenStarCoin);

function ObstacleStageGroup({
  safeLane,
  phase,
  progress,
  obstacleKey,
}: {
  safeLane: Direction;
  phase: GamePhase;
  progress: { current: number };
  obstacleKey: string;
}) {
  const obstacleLane = safeLane === "LEFT" ? 1.15 : -1.15;
  const starLane = safeLane === "LEFT" ? -1.15 : 1.15;
  const group = useRef<Group>(null);

  useLayoutEffect(() => {
    if (!group.current) return;
    // Reposition between frames while fully hidden by distant fog. Keep the
    // meshes/materials mounted so no geometry upload occurs at stage changes.
    group.current.visible = false;
    group.current.position.z = OBSTACLE_START_Z;
  }, [obstacleKey]);

  useFrame((_, delta) => {
    if (!group.current) return;
    // Only visible forward motion is interpolated. Recycling is instantaneous
    // off screen, with fog revealing the next obstacle as it approaches.
    if (phase === "PAUSED") return;
    group.current.visible = ![
      "NEXT_TRIAL",
      "MISSION_COMPLETE",
      "GAME_OVER",
    ].includes(phase);
    let targetZ = OBSTACLE_START_Z;
    if (phase === "RUNNING") targetZ = OBSTACLE_START_Z + progress.current * (0.5 - OBSTACLE_START_Z);
    else if (["WAITING_FOR_COMMAND", "SUCCESS", "COLLISION"].includes(phase))
      targetZ = 0.5;
    else if (phase === "PASSING") targetZ = 12;
    if (phase === "READY") group.current.position.z = OBSTACLE_START_Z;
    else if (group.current.visible) {
      group.current.position.z = Math.max(
        group.current.position.z,
        MathUtils.damp(
          group.current.position.z,
          targetZ,
          phase === "PASSING" ? 5 : 7.5,
          delta,
        ),
      );
    }
  });

  return (
    <group ref={group} position={[0, 0.38, OBSTACLE_START_Z]}>
      <MemoCartoonBomb x={obstacleLane} isHit={phase === "COLLISION"} />
      <MemoGoldenStarCoin x={starLane} isCollected={phase === "SUCCESS"} />
    </group>
  );
}

/**
 * Clear Sky Blue Environment with Clear White Clouds
 */
function RunnerWorld() {
  const clouds = [
    [-4.5, 2.8, 1], [4.4, 3.2, -2.5], [-5.2, 3.8, -7],
    [5.0, 3.0, -11], [-4.8, 3.6, -16], [4.8, 4.0, -21],
  ] as const;

  return (
    <group>
      {clouds.map(([x, y, z], index) => (
        <Float key={`${x}-${z}`} speed={0.35 + index * 0.04} rotationIntensity={0.03} floatIntensity={0.12}>
          <group position={[x, y, z]} scale={index % 2 ? 1.25 : 1.05}>
            <mesh position={[-0.55, 0, 0]}>
              <sphereGeometry args={[0.68, 20, 16]} />
              <meshStandardMaterial color="#FFFFFF" roughness={0.9} />
            </mesh>
            <mesh position={[0, 0.22, 0.02]}>
              <sphereGeometry args={[0.88, 20, 16]} />
              <meshStandardMaterial color="#FFFFFF" roughness={0.9} />
            </mesh>
            <mesh position={[0.68, 0.02, 0]}>
              <sphereGeometry args={[0.62, 20, 16]} />
              <meshStandardMaterial color="#FFFFFF" roughness={0.9} />
            </mesh>
            <mesh position={[0.05, -0.18, 0]} scale={[1.7, 0.5, 0.75]}>
              <sphereGeometry args={[0.82, 20, 16]} />
              <meshStandardMaterial color="#FFFFFF" roughness={0.9} />
            </mesh>
          </group>
        </Float>
      ))}

      {/* Floating Balloons */}
      {[
        [-3.6, 5.0, -9, "#10B981"],
        [3.8, 5.4, -13, "#38BDF8"],
        [-2.8, 5.8, -17, "#FBBF24"],
        [3.2, 5.2, -7, "#6EE7B7"],
      ].map(([x, y, z, color], idx) => (
        <Float key={`balloon-${idx}`} speed={0.5 + idx * 0.1} floatIntensity={0.3}>
          <group position={[Number(x), Number(y), Number(z)]}>
            <mesh>
              <sphereGeometry args={[0.44, 18, 14]} />
              <meshStandardMaterial color={String(color)} roughness={0.25} />
            </mesh>
            <mesh position={[0, -0.48, 0]}>
              <cylinderGeometry args={[0.015, 0.015, 0.36, 8]} />
              <meshStandardMaterial color="#FFFFFF" transparent opacity={0.65} />
            </mesh>
          </group>
        </Float>
      ))}
    </group>
  );
}

function RunnerScene({
  lane,
  safeLane,
  phase,
  progress,
  obstacleKey,
}: {
  lane: Direction;
  safeLane: Direction;
  phase: GamePhase;
  progress: { current: number };
  obstacleKey: string;
}) {
  const moving = phase === "RUNNING" || phase === "PASSING" || phase === "NEXT_TRIAL";

  return (
    <>
      <RunnerCamera />
      <color attach="background" args={["#BAE6FD"]} />
      <fog attach="fog" args={["#BAE6FD", 12, 28]} />

      <ambientLight intensity={2.4} />
      <directionalLight position={[5, 10, 6]} intensity={3.5} castShadow />
      <pointLight position={[0, 4, -2]} intensity={5} color="#FEF08A" />

      <RunnerWorld />

      {Array.from({ length: ROAD_COUNT }, (_, i) => (
        <RoadTile key={i} index={i} moving={moving} />
      ))}

      <ObstacleStageGroup obstacleKey={obstacleKey} safeLane={safeLane} phase={phase} progress={progress} />
      <JellyBeanCharacter lane={lane} phase={phase} />
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
  const [round, setRound] = useState(0);
  const processedTrial = useRef<number | null>(null);
  const pendingTrial = useRef<BackendPrediction | null>(null);
  const settledTrial = useRef<number | null>(null);
  const phaseRef = useRef<GamePhase>(phase);
  const phaseBeforePause = useRef<GamePhase>("READY");
  const progressRef = useRef(0);
  const livesRef = useRef(3);
  const onArrival = useRef<() => void>(() => {});
  phaseRef.current = phase;
  const timers = useRef<number[]>([]);
  const animFrame = useRef<number | null>(null);
  const channels = recorded && s.recordedPrediction?.active_channels?.length ? s.recordedPrediction.active_channels : configuredChannels(s.channelMode);

  const setGamePhase = (next: GamePhase) => {
    phaseRef.current = next;
    setPhase(next);
  };
  const clearTimers = () => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    if (animFrame.current !== null) cancelAnimationFrame(animFrame.current);
    animFrame.current = null;
  };
  const later = (fn: () => void, delay: number) => {
    timers.current.push(window.setTimeout(fn, delay));
  };
  const duration = (ms: number) =>
    ms / (s.inputMode === "manual" ? 1 : useBCI.getState().speed);
  const chooseSafeLane = useCallback(
    (): Direction => (Math.random() > 0.5 ? "LEFT" : "RIGHT"),
    [],
  );

  const resetGame = () => {
    clearTimers();
    s.stop();
    if (recorded) s.setSettings({ inputMode: "recorded", recordedLowChannel: s.recordedLowChannel });
    s.setRecordedTrialReady(true);
    pendingTrial.current = null;
    processedTrial.current = null;
    settledTrial.current = null;
    progressRef.current = 0;
    livesRef.current = 3;
    setRound((v) => v + 1);
    setGamePhase("READY");
    setStage(1);
    setScore(0);
    setLives(3);
    setLane("LEFT");
    setSafeLane(chooseSafeLane());
    setHistory([]);
    setAvoided(0);
    setCollisions(0);
    setExcluded(0);
  };
  useEffect(() => {
    resetGame();
  }, [
    s.participantId,
    s.sessionId,
    s.channelMode,
    s.recordedLowChannel,
    s.ttaEnabled,
    s.inputMode,
  ]);
  useEffect(
    () => () => {
      clearTimers();
      useBCI.getState().setRecordedTrialReady(true);
    },
    [],
  );

  const beginStage = (fromProgress = 0) => {
    clearTimers();
    setGamePhase("RUNNING");
    progressRef.current = fromProgress;
    const runningTime = duration(recorded ? 4500 : 3400);
    const started = performance.now();
    const updateProgress = (now: number) => {
      const next = Math.min(1, fromProgress + (now - started) / runningTime);
      progressRef.current = next;
      if (next < 1) animFrame.current = requestAnimationFrame(updateProgress);
      else {
        animFrame.current = null;
        setGamePhase("WAITING_FOR_COMMAND");
        onArrival.current();
      }
    };
    animFrame.current = requestAnimationFrame(updateProgress);
  };

  const endStage = (trial: number) => {
    pendingTrial.current = null;
    if (livesRef.current <= 0) {
      setGamePhase("GAME_OVER");
      if (recorded) s.setBackend({ backendStatus: "게임 종료" });
      s.stop();
      return;
    }
    if (trial >= totalStages) {
      setGamePhase("MISSION_COMPLETE");
      if (recorded) s.setBackend({ backendStatus: "세션 재생 완료" });
      s.stop();
      return;
    }
    if (recorded) {
      setGamePhase("NEXT_TRIAL");
      s.setRecordedTrialReady(true);
    } else {
      setStage(trial + 1);
      setSafeLane(chooseSafeLane());
      beginStage();
    }
  };
  const passObstacle = (trial: number) => {
    setGamePhase("PASSING");
    later(() => endStage(trial), duration(1200));
  };
  const finishStage = (
    direction: Direction,
    target: Direction,
    trial = stage,
    valid = true,
  ) => {
    if (settledTrial.current === trial) return;
    settledTrial.current = trial;
    if (!valid) {
      setExcluded((v) => v + 1);
      passObstacle(trial);
      return;
    }
    setLane(direction);
    const success = direction === target;
    setHistory((old) => [
      {
        id: old.length + 1,
        trial,
        target,
        predicted: direction,
        valid,
        success,
      },
      ...old,
    ]);
    if (success) {
      setScore((v) => v + 10);
      setAvoided((v) => v + 1);
      setGamePhase("SUCCESS");
    } else {
      setCollisions((v) => v + 1);
      livesRef.current = Math.max(0, livesRef.current - 1);
      setLives(livesRef.current);
      setGamePhase("COLLISION");
    }
    later(() => passObstacle(trial), duration(900));
  };
  onArrival.current = () => {
    const prediction = pendingTrial.current;
    if (recorded && prediction)
      finishStage(
        prediction.predicted_direction,
        prediction.true_direction ?? safeLane,
        prediction.trial_id,
        prediction.quality.is_clean && prediction.true_direction !== null,
      );
  };

  const start = () => {
    const previous = phaseRef.current;
    if (["MISSION_COMPLETE", "GAME_OVER"].includes(previous)) resetGame();
    if (recorded) {
      s.play();
      if (previous === "PAUSED" && pendingTrial.current) {
        const resume = phaseBeforePause.current;
        const trial = pendingTrial.current.trial_id;
        if (resume === "RUNNING") beginStage(progressRef.current);
        else if (resume === "PASSING") passObstacle(trial);
        else if (resume === "SUCCESS" || resume === "COLLISION") {
          setGamePhase(resume);
          later(() => passObstacle(trial), duration(900));
        }
      } else setGamePhase("NEXT_TRIAL");
    } else if (
      previous === "PAUSED" &&
      phaseBeforePause.current === "WAITING_FOR_COMMAND"
    ) {
      setGamePhase("WAITING_FOR_COMMAND");
    } else if (
      previous === "PAUSED" &&
      ["SUCCESS", "COLLISION", "PASSING"].includes(phaseBeforePause.current)
    ) {
      if (phaseBeforePause.current === "PASSING") passObstacle(stage);
      else {
        setGamePhase(phaseBeforePause.current);
        later(() => passObstacle(stage), duration(900));
      }
    } else beginStage(previous === "PAUSED" ? progressRef.current : 0);
  };
  const pause = () => {
    phaseBeforePause.current = phaseRef.current;
    clearTimers();
    s.stop();
    setGamePhase("PAUSED");
  };
  const manualCommand = (direction: Direction) => {
    if (s.inputMode !== "manual" || phaseRef.current !== "WAITING_FOR_COMMAND")
      return;
    finishStage(direction, safeLane);
  };
  useEffect(() => {
    const prediction = s.recordedPrediction;
    if (
      !recorded ||
      !s.isPlaying ||
      !prediction ||
      prediction.trial_id === processedTrial.current
    )
      return;
    processedTrial.current = prediction.trial_id;
    pendingTrial.current = prediction;
    setStage(prediction.trial_id);
    setSafeLane(prediction.true_direction ?? chooseSafeLane());
    beginStage();
  }, [recorded, s.isPlaying, s.recordedPrediction]);

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (
        event.repeat ||
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLSelectElement
      )
        return;
      if (event.key === "ArrowLeft") manualCommand("LEFT");
      if (event.key === "ArrowRight") manualCommand("RIGHT");
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
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

  const activeStimulusDirection = s.recordedPrediction?.predicted_direction ?? (phase === "WAITING_FOR_COMMAND" ? undefined : lane);

  return (
    <div className="neuro-runner">
      <section className="runner-shell panel">
        <div className="runner-titlebar application-heading">
          <div><span className="eyebrow">APPLICATION 02</span><h2>Neuro Runner</h2><p>LEFT / RIGHT 운동 상상 명령으로 젤리빈을 움직여 폭탄을 피하고 황금 별을 획득하세요.</p></div>
          <div className="runner-title-actions">
            {["READY", "PAUSED", "MISSION_COMPLETE", "GAME_OVER"].includes(phase) ? <button className="button primary" onClick={start}><Play size={15}/> Start</button> : <button className="button primary" onClick={pause}><Pause size={15}/> Pause</button>}
            <button className="button subtle" onClick={resetGame}><RotateCcw size={14}/> Reset</button>
          </div>
        </div>

        <div className="runner-console">
          {/* Top Row: Main 3D Canvas (Left) + Brain Stimulation EEG Map (Right Up!) */}
          <div className="runner-stage-row">
            <div className="runner-play-area">
              <div className={`runner-canvas phase-${phase.toLowerCase()}`}>
                <Canvas shadows camera={{ position: [0, 3.5, 7.3], fov: 40 }}>
                  <RunnerScene lane={lane} safeLane={safeLane} phase={phase} progress={progressRef} obstacleKey={`${round}-${stage}`} />
                </Canvas>
                <div className="runner-hud">
                  <div><Trophy size={15}/><span>Score</span><strong>{score}</strong></div>
                  <div><Battery size={15}/><span>Stage</span><strong>{stage} / {totalStages}</strong></div>
                  <div><Heart size={15}/><span>Lives</span><strong>{"♥".repeat(lives) || "0"}</strong></div>
                  <div><Radio size={15}/><span>Command</span><strong>{s.recordedPrediction?.predicted_direction ?? (phase === "WAITING_FOR_COMMAND" ? "WAITING" : lane)}</strong></div>
                </div>

                {/* Embedded Mini Brain Stimulation Box (Rounded Square Inside Canvas) */}
                <div className="runner-mini-brain-box" title="실시간 뇌 활성화 맵">
                  <div className="mini-brain-header">
                    <Brain size={12} />
                    <span>EEG Map</span>
                    <span className={`mini-brain-dot ${activeStimulusDirection ? activeStimulusDirection.toLowerCase() : "idle"}`} />
                  </div>
                  <div className="mini-brain-svg-wrap">
                    <Atlas2D
                      mode={s.channelMode}
                      selected={activeStimulusDirection === "LEFT" ? "C4" : activeStimulusDirection === "RIGHT" ? "C3" : ""}
                      onSelect={() => {}}
                      direction={activeStimulusDirection}
                    />
                  </div>
                  <span className="mini-brain-label">
                    {activeStimulusDirection ? (activeStimulusDirection === "LEFT" ? "C4 활성" : "C3 활성") : "대기 중"}
                  </span>
                </div>

                <div className="runner-lane-hints"><span>← LEFT</span><span>RIGHT →</span></div>
                {["WAITING_FOR_COMMAND","MISSION_COMPLETE","GAME_OVER","PAUSED"].includes(phase) && (
                  <div className="runner-message">
                    <strong>{phase === "WAITING_FOR_COMMAND" ? "💣 폭탄을 피하고 ⭐ 황금 별을 잡으세요!" : phase.replaceAll("_", " ")}</strong>
                    <span>{phase === "WAITING_FOR_COMMAND" ? "LEFT 또는 RIGHT 안전 차선을 선택하세요." : phase === "MISSION_COMPLETE" ? "축하합니다! 모든 스테이지를 클리어했습니다 🎉" : phase === "GAME_OVER" ? "아쉽네요! 생명을 모두 소진했습니다." : "게임이 일시정지되었습니다."}</span>
                  </div>
                )}
                {phase === "SUCCESS" && <div className="runner-feedback success"><Star size={18} fill="currentColor"/> +10 STAR COIN!</div>}
                {phase === "COLLISION" && <div className="runner-feedback collision">💥 BOMB HIT!</div>}
              </div>
              <div className="runner-controls">
                <button disabled={s.inputMode !== "manual" || phase !== "WAITING_FOR_COMMAND"} onClick={() => manualCommand("LEFT")}><ArrowLeft/> LEFT</button>
                <button disabled={s.inputMode !== "manual" || phase !== "WAITING_FOR_COMMAND"} onClick={() => manualCommand("RIGHT")}>RIGHT <ArrowRight/></button>
              </div>
              <div className="runner-status-line"><span>EEG 추론 상태</span><strong>{recorded ? s.backendStatus : "Manual Demo · Backend 불필요"}</strong></div>
            </div>
          </div>

          {/* Bottom Row: Settings (Left, Compact) + Monitor (Right, Wide) */}
          <div className="runner-side-stack two-columns">
            <section className="runner-side-card runner-settings compact">
              <div className="panel-title"><Sliders size={15}/> 제어 설정</div>
              <Settings embedded />
            </section>

            <aside className="runner-side-card runner-monitor">
              <div className="panel-title"><Radio size={15}/> EEG Control Monitor <i className="status-dot"/></div>
              <Waveform channels={channels} playing={s.isPlaying || !recorded} recorded={recorded} samples={s.recordedPrediction?.waveform} replayDurationMs={6600}/>
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
              <div className="command-history">{history.length ? history.slice(0, 10).map(row => <div key={row.id}><span className={row.success ? "cyan" : "purple"}>{row.predicted === "LEFT" ? "←" : "→"}</span><p>Trial {row.trial} · {row.success ? "별 획득" : "폭탄 충돌"}<small>Target {row.target}</small></p><span className="mono">{row.success ? "+10" : "MISS"}</span></div>) : <p className="empty">게임 명령 기록이 여기에 표시됩니다.</p>}</div>
            </aside>
          </div>
        </div>
      </section>

      {["MISSION_COMPLETE","GAME_OVER"].includes(phase) && <section className="runner-results panel"><span className="eyebrow">GAME RESULT</span><h3>{phase.replaceAll("_", " ")}</h3><div><p><span>Final Score</span><strong>{score}</strong></p><p><span>Obstacles Avoided</span><strong>{avoided}</strong></p><p><span>Collisions</span><strong>{collisions}</strong></p>{recorded && <><p><span>Valid EEG Trials</span><strong>{validTrials.length}</strong></p><p><span>LEFT / RIGHT Recall</span><strong>{percent(leftRecall)} / {percent(rightRecall)}</strong></p><p><span>Macro-F1</span><strong>{percent(macroF1)}</strong></p><p><span>Configuration</span><strong>{s.recordedLowChannel ? "Low Channel" : s.channelMode} · TTA {s.ttaEnabled ? "ON" : "OFF"}</strong></p></>}</div><button className="button primary" onClick={resetGame}>다시 플레이하기</button></section>}
    </div>
  );
}
