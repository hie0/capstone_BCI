import {
  MathUtils,
  type Group,
  type AmbientLight,
  type DirectionalLight,
  type PointLight,
} from "three";
import {
  Component,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line, OrbitControls, RoundedBox } from "@react-three/drei";
import {
  core,
  electrodeNames,
  positions,
  channelInfo,
  type ChannelMode,
  type Direction,
} from "../data/research";
import { useBCI } from "../store";
export const activeChannels = (mode: ChannelMode) =>
  mode === "16ch"
    ? electrodeNames
    : mode === "5ch"
      ? core
      : [...core, "T7", "T8"];
class SceneBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
function supported() {
  try {
    const c = document.createElement("canvas");
    return !!c.getContext("webgl2");
  } catch {
    return false;
  }
}
export function Scene({
  children,
  room = false,
  fallback,
}: {
  children: ReactNode;
  room?: boolean;
  fallback: ReactNode;
}) {
  const [webgl, setWebgl] = useState(supported);
  return (
    <SceneBoundary fallback={fallback}>
      {webgl ? (
        <Canvas
          orthographic={room}
          camera={
            room
              ? { position: [7, 5.8, 8], zoom: 63 }
              : { position: [0, 3.8, 5], fov: 36 }
          }
          dpr={[1, 1.5]}
          gl={{ antialias: true }}
          onCreated={({ gl }) => {
            gl.domElement.addEventListener(
              "webglcontextlost",
              () => setWebgl(false),
              { once: true },
            );
            gl.domElement.setAttribute(
              "aria-label",
              room ? "인터랙티브 3D 거실" : "EEG 전극 3D 시각화",
            );
          }}
        >
          <Suspense
            fallback={
              <Html center>
                <span className="badge">3D 장면 로딩 중…</span>
              </Html>
            }
          >
            {room && <FitRoom />}
            {children}
          </Suspense>
        </Canvas>
      ) : (
        fallback
      )}
    </SceneBoundary>
  );
}
export function Atlas2D({
  mode,
  onSelect,
  selected,
  excluded = false,
  direction,
}: {
  mode: ChannelMode;
  onSelect: (s: string) => void;
  selected: string;
  excluded?: boolean;
  direction?: Direction;
}) {
  const active = activeChannels(mode);
  return (
    <svg
      viewBox="0 0 400 400"
      className="atlas-svg"
      aria-label="EEG 두피 전극 배치도"
    >
      <ellipse
        cx="200"
        cy="205"
        rx="150"
        ry="160"
        fill="#102b42"
        stroke="#47718c"
      />
      <path
        d="M180 45 L200 24 L220 45 M45 175 Q12 205 45 235 M355 175 Q388 205 355 235"
        fill="none"
        stroke="#47718c"
      />
      <path
        d="M200 48V362 M52 205H348"
        stroke="#2a4960"
        strokeDasharray="4 8"
      />
      {electrodeNames.map((n) => {
        const [x, y] = positions[n];
        const enabled = excluded ? !core.includes(n) : active.includes(n);
        const motor =
          direction === "LEFT"
            ? n === "C4"
            : direction === "RIGHT"
              ? n === "C3"
              : false;
        return (
          <g
            key={n}
            role="button"
            tabIndex={0}
            aria-label={`전극 ${n}`}
            onClick={() => onSelect(n)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(n);
              }
            }}
            style={{ cursor: "pointer" }}
          >
            <title>
              {n}: {channelInfo(n)}
            </title>
            <circle
              cx={200 + x * 144}
              cy={205 + y * 150}
              r={selected === n ? 15 : 11}
              fill={
                motor && enabled
                  ? direction === "LEFT"
                    ? "#00e5ff"
                    : "#b58cff"
                  : enabled
                    ? "#55a9bb"
                    : "#203c51"
              }
              stroke={selected === n ? "white" : "#45748c"}
            />
            <text
              x={200 + x * 144}
              y={205 + y * 150 + 29}
              fill={enabled ? "#e6f6ff" : "#8397a9"}
              textAnchor="middle"
              fontSize="12"
            >
              {n}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
export function Brain({
  mode = "5ch",
  direction = "LEFT",
  selected = "C4",
  onSelect = () => {},
}: {
  mode?: ChannelMode;
  direction?: Direction;
  selected?: string;
  onSelect?: (n: string) => void;
}) {
  const active = activeChannels(mode);
  const paths = useMemo(
    () =>
      Array.from({ length: 24 }, (_, k) =>
        Array.from({ length: 85 }, (_, i) => {
          const a = (i / 84) * Math.PI * 2;
          const y = -0.9 + k * 0.078;
          const r = Math.sqrt(Math.max(0, 1 - y * y));
          return [
            Math.cos(a) * r * (0.92 + 0.035 * Math.sin(a * 9 + k)),
            y * 1.25,
            Math.sin(a) * r * (1.04 + 0.035 * Math.cos(a * 11 + k)),
          ] as [number, number, number];
        }),
      ),
    [],
  );
  return (
    <>
      <ambientLight intensity={1} />
      <pointLight position={[3, 4, 5]} intensity={30} color="#5fe7ff" />
      <group rotation={[-0.18, 0, 0]}>
        <mesh scale={[0.96, 1.25, 1.08]}>
          <sphereGeometry args={[1, 48, 40]} />
          <meshPhysicalMaterial
            color="#254b65"
            roughness={0.4}
            transparent
            opacity={0.62}
            metalness={0.3}
          />
        </mesh>
        {paths.map((p, i) => (
          <Line
            key={i}
            points={p}
            color="#498498"
            transparent
            opacity={0.42}
            lineWidth={0.7}
          />
        ))}
        <Line
          points={[
            [0, 1.25, 0],
            [0, 1.1, 0.5],
            [0, 0.7, 1],
            [0, 0, 1.1],
            [0, -0.8, 0.8],
          ]}
          color="#071822"
          lineWidth={3}
        />
        <mesh position={[0, -0.1, 1.08]} scale={[0.12, 0.25, 0.16]}>
          <sphereGeometry />
          <meshStandardMaterial color="#284d65" />
        </mesh>
        {[-1, 1].map((s) => (
          <mesh
            key={s}
            position={[s * 0.96, -0.08, 0]}
            scale={[0.12, 0.3, 0.18]}
          >
            <sphereGeometry />
            <meshStandardMaterial color="#284d65" />
          </mesh>
        ))}
        {electrodeNames.map((n) => {
          const [x, z] = positions[n];
          const y = Math.sqrt(Math.max(0.04, 1 - x * x - z * z)) * 1.25;
          const enabled = active.includes(n);
          const motor =
            (direction === "LEFT" && n === "C4") ||
            (direction === "RIGHT" && n === "C3");
          return (
            <group key={n} position={[x, y, -z]}>
              <mesh
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(n);
                }}
              >
                <sphereGeometry args={[enabled ? 0.068 : 0.035, 16, 16]} />
                <meshStandardMaterial
                  color={
                    motor
                      ? direction === "LEFT"
                        ? "#00e5ff"
                        : "#b58cff"
                      : enabled
                        ? "#00e5ff"
                        : "#3e5667"
                  }
                  emissive={
                    motor && direction === "RIGHT" ? "#9a64ff" : "#00e5ff"
                  }
                  emissiveIntensity={enabled ? 1 : 0.1}
                />
              </mesh>
              {enabled && (
                <Html center distanceFactor={3.5} position={[0, 0.12, 0]}>
                  <button
                    className={`electrode ${selected === n ? "selected" : ""}`}
                    onClick={() => onSelect(n)}
                    title={channelInfo(n)}
                  >
                    {n}
                  </button>
                </Html>
              )}
            </group>
          );
        })}
      </group>
      <OrbitControls
        enablePan={false}
        enableZoom={false}
        minPolarAngle={0.15}
        maxPolarAngle={1.7}
        autoRotate={false}
      />
    </>
  );
}
function Box({
  position,
  size,
  color,
  rotation = [0, 0, 0],
}: {
  position: [number, number, number];
  size: [number, number, number];
  color: string;
  rotation?: [number, number, number];
}) {
  return (
    <RoundedBox
      args={size}
      radius={Math.min(0.035, ...size.map((v) => v / 4))}
      smoothness={2}
      position={position}
      rotation={rotation}
    >
      <meshStandardMaterial color={color} roughness={0.8} />
    </RoundedBox>
  );
}
export function Room() {
  const s = useBCI();
  return (
    <>
      <color attach="background" args={["#0b1c2b"]} />
      <RoomLighting on={s.light} />
      <Box position={[0, -0.1, 0]} size={[6, 0.2, 4.8]} color="#64757c" />
      <Box position={[0, 1.55, -2.4]} size={[6, 3.3, 0.13]} color="#8b9da5" />
      <Box position={[-3, 1.55, 0]} size={[0.13, 3.3, 4.8]} color="#6a808d" />
      {Array.from({ length: 12 }, (_, i) => (
        <Box
          key={i}
          position={[-2.8 + i * 0.5, 0.012, 0]}
          size={[0.012, 0.01, 4.7]}
          color="#53656c"
        />
      ))}
      <Box
        position={[-1.45, 1.8, -2.3]}
        size={[2.4, 2.1, 0.08]}
        color="#c4e8f3"
      />
      <Box
        position={[-1.45, 1.8, -2.22]}
        size={[0.055, 2.1, 0.06]}
        color="#4f6876"
      />
      {[-1, 1].map((side) => (
        <Curtain key={side} side={side} open={s.curtains} />
      ))}
      <Box
        position={[1.48, 1.65, -2.23]}
        size={[2.05, 1.25, 0.12]}
        color="#10202b"
      />
      <mesh position={[1.48, 1.65, -2.155]}>
        <planeGeometry args={[1.88, 1.08]} />
        <meshBasicMaterial
          color={
            ["#264e68", "#246f69", "#655177", "#92684b", "#32648b"][s.tv - 1]
          }
        />
      </mesh>
      <Html position={[1.48, 1.65, -2.05]} center>
        <div className="tv-content">
          <small>NEUROLINK TV</small>
          <strong>
            {["OCEAN", "FOREST", "COSMOS", "DESERT", "SKY"][s.tv - 1]}
          </strong>
          <span>CH. 0{s.tv}</span>
        </div>
      </Html>
      <Box
        position={[1.4, 0.39, -1.97]}
        size={[2.5, 0.65, 0.65]}
        color="#b6a58d"
      />
      <Box position={[-1.6, 0.4, 0.8]} size={[2.2, 0.58, 1]} color="#b4c3c6" />
      <Box
        position={[-1.6, 0.86, 1.19]}
        size={[2.2, 0.68, 0.24]}
        color="#a1b3b9"
      />
      {[-2.65, -0.55].map((x) => (
        <Box
          key={x}
          position={[x, 0.66, 0.75]}
          size={[0.22, 0.65, 1.15]}
          color="#a1b3b9"
        />
      ))}
      {[-2.15, -1.12].map((x) => (
        <Box
          key={x}
          position={[x, 0.77, 0.72]}
          size={[0.9, 0.15, 0.75]}
          color="#d1dcdd"
        />
      ))}
      <Box
        position={[-0.2, 0.04, 0.35]}
        size={[3.3, 0.03, 2.4]}
        color="#3c5869"
      />
      <Box
        position={[0.05, 0.4, 0.3]}
        size={[1.3, 0.12, 0.8]}
        color="#cfbba1"
      />
      {[-0.48, 0.48].map((x) => (
        <Box
          key={x}
          position={[x, 0.2, 0.3]}
          size={[0.06, 0.4, 0.5]}
          color="#283c48"
        />
      ))}
      <Box
        position={[1.5, 2.7, -2.2]}
        size={[1.65, 0.35, 0.22]}
        color="#d3e0e3"
      />
      <Html position={[1.5, 2.7, -2.05]} center>
        <span className="temperature-label">{s.temperature}°</span>
      </Html>
      <mesh position={[2.35, 0.32, 1.35]}>
        <cylinderGeometry args={[0.24, 0.18, 0.6, 20]} />
        <meshStandardMaterial color="#a2aaa3" />
      </mesh>
      {Array.from({ length: 7 }, (_, i) => (
        <mesh
          key={i}
          position={[
            2.35 + Math.sin(i) * 0.18,
            0.9 + (i % 3) * 0.15,
            1.35 + Math.cos(i) * 0.18,
          ]}
          rotation={[0.3, i, 0.3]}
          scale={[0.13, 0.5, 0.13]}
        >
          <sphereGeometry />
          <meshStandardMaterial color="#3d8975" />
        </mesh>
      ))}
      <mesh position={[0, 2.8, 0]}>
        <cylinderGeometry args={[0.45, 0.65, 0.18, 32]} />
        <meshStandardMaterial
          color="#e4d6b3"
          emissive="#ffe3a1"
          emissiveIntensity={s.light ? 1 : 0}
        />
      </mesh>
      <Line
        points={[
          [0, 2.8, 0],
          [0, 3.4, 0],
        ]}
        color="#647481"
      />
      <OrbitControls
        enablePan={false}
        enableZoom={false}
        minAzimuthAngle={-0.3}
        maxAzimuthAngle={1.2}
        minPolarAngle={0.6}
        maxPolarAngle={1.3}
        target={[0, 1, 0]}
      />
    </>
  );
}
export function RoomFallback() {
  const s = useBCI();
  return (
    <div className={`room-fallback ${s.light ? "lit" : ""}`}>
      <span>2D 대체 뷰 · WebGL 사용 불가</span>
      <div className={`window ${s.curtains ? "open" : ""}`}>
        <i />
        <i />
      </div>
      <div className="fallback-tv">
        CH. {s.tv}
        <strong>
          {["OCEAN", "FOREST", "COSMOS", "DESERT", "SKY"][s.tv - 1]}
        </strong>
      </div>
      <div className="sofa">━━━</div>
      <div className="room-temp">{s.temperature}°C</div>
      <div className="lamp">◉ {s.light ? "ON" : "OFF"}</div>
    </div>
  );
}

function Curtain({ side, open }: { side: number; open: boolean }) {
  const group = useRef<Group>(null);
  useFrame((_, dt) => {
    if (!group.current) return;
    group.current.position.x = MathUtils.damp(
      group.current.position.x,
      -1.45 + side * (open ? 1.04 : 0.59),
      6,
      dt,
    );
    group.current.scale.x = MathUtils.damp(
      group.current.scale.x,
      open ? 0.28 : 1,
      6,
      dt,
    );
  });
  return (
    <group ref={group} position={[-1.45 + side * 0.59, 1.8, -2.1]}>
      {Array.from({ length: 7 }, (_, i) => (
        <Box
          key={i}
          position={[(i - 3) * 0.16, 0, Math.sin(i) * 0.025]}
          size={[0.19, 2.24, 0.09]}
          color={i % 2 ? "#335064" : "#3c5c70"}
        />
      ))}
    </group>
  );
}
function RoomLighting({ on }: { on: boolean }) {
  const ambient = useRef<AmbientLight>(null);
  const directional = useRef<DirectionalLight>(null);
  const point = useRef<PointLight>(null);
  useFrame((_, dt) => {
    if (ambient.current)
      ambient.current.intensity = MathUtils.damp(
        ambient.current.intensity,
        on ? 1.3 : 0.3,
        5,
        dt,
      );
    if (directional.current)
      directional.current.intensity = MathUtils.damp(
        directional.current.intensity,
        on ? 3 : 0.4,
        5,
        dt,
      );
    if (point.current)
      point.current.intensity = MathUtils.damp(
        point.current.intensity,
        on ? 18 : 0,
        5,
        dt,
      );
  });
  return (
    <>
      <ambientLight ref={ambient} intensity={1.3} />
      <directionalLight
        ref={directional}
        position={[0, 6, 3]}
        intensity={3}
        color="#d8f2ff"
      />
      <pointLight
        ref={point}
        position={[0, 3, 0]}
        intensity={18}
        color="#fff1c7"
      />
    </>
  );
}

function FitRoom() {
  const { camera, size } = useThree();
  useEffect(() => {
    if ("isOrthographicCamera" in camera) {
      camera.zoom = Math.min(size.width / 8.3, size.height / 6);
      camera.updateProjectionMatrix();
    }
  }, [camera, size.width, size.height]);
  return null;
}
