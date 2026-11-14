import {
  BufferGeometry,
  CatmullRomCurve3,
  Float32BufferAttribute,
  MathUtils,
  Vector3,
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
import { configuredChannels } from "../data/channels";
export const activeChannels = (mode: ChannelMode) => configuredChannels(mode);
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
          <Suspense fallback={null}>
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
      <defs>
        <filter
          id="electrode-neutral-glow"
          x="-120%"
          y="-120%"
          width="340%"
          height="340%"
        >
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feFlood floodColor="#6F879A" floodOpacity="0.48" />
          <feComposite in2="blur" operator="in" />
          <feMerge>
            <feMergeNode />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <ellipse
        cx="200"
        cy="205"
        rx="150"
        ry="160"
        fill="#F2F5F7"
        stroke="#9CAAB6"
      />
      <path
        d="M180 45 L200 24 L220 45 M45 175 Q12 205 45 235 M355 175 Q388 205 355 235"
        fill="none"
        stroke="#9CAAB6"
      />
      <path
        d="M200 48V362 M52 205H348"
        stroke="#DCE5EB"
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
            className={`electrode-node ${selected === n ? "selected" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={`전극 ${n}`}
            aria-pressed={selected === n}
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
            {selected === n && (
              <>
                <circle
                  className="electrode-diffusion-ring ring-one"
                  cx={200 + x * 144}
                  cy={205 + y * 150}
                  r="18"
                />
                <circle
                  className="electrode-diffusion-ring ring-two"
                  cx={200 + x * 144}
                  cy={205 + y * 150}
                  r="18"
                />
              </>
            )}
            <circle
              className="electrode-dot"
              cx={200 + x * 144}
              cy={205 + y * 150}
              r={selected === n ? 14 : 11}
              fill={
                motor && enabled
                  ? direction === "LEFT"
                    ? "#527C98"
                    : "#8A79AF"
                  : enabled
                    ? n === "P7" || n === "P8"
                      ? "#527C98"
                      : "#82B5AD"
                    : "#CBD5DF"
              }
              stroke={selected === n ? "#607D92" : "#9CAAB6"}
              strokeWidth={selected === n ? 3 : 1.5}
              filter={
                selected === n ? "url(#electrode-neutral-glow)" : undefined
              }
            />
            <text
              x={200 + x * 144}
              y={205 + y * 150 + 29}
              fill={enabled ? "#263746" : "#697B89"}
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
function WearableConceptBrain({
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
  const headGeometry = useMemo(() => createMannequinHead(), []);
  const sensorPositions: Record<string, [number, number, number]> = {
    Fp1: [-0.3, 0.53, 0.79],
    Fp2: [0.3, 0.53, 0.79],
    F7: [-0.63, 0.38, 0.57],
    F3: [-0.22, 0.62, 0.81],
    F4: [0.22, 0.62, 0.81],
    F8: [0.63, 0.38, 0.57],
    T7: [-0.78, 0.15, 0.03],
    C3: [-0.55, 0.91, 0.18],
    Cz: [0, 1.18, 0.02],
    C4: [0.55, 0.91, 0.18],
    T8: [0.78, 0.15, 0.03],
    P7: [-0.62, 0.46, -0.5],
    Pz: [0, 0.84, -0.58],
    P8: [0.62, 0.46, -0.5],
    O1: [-0.28, 0.23, -0.73],
    O2: [0.28, 0.23, -0.73],
  };
  const labelOffsets: Partial<Record<string, [number, number, number]>> = {
    F3: [-0.04, -0.18, 0.22],
    F4: [0.18, 0.22, 0.12],
    C3: [-0.12, 0.18, 0],
    Cz: [0, 0.19, 0],
    C4: [0.12, 0.18, 0],
  };
  return (
    <>
      <BrainCamera />
      <color attach="background" args={["#F5F7FA"]} />
      <ambientLight intensity={1.25} />
      <directionalLight position={[4, 6, 5]} intensity={2.5} color="#FFFFFF" />
      <directionalLight
        position={[-4, 2, 3]}
        intensity={1.15}
        color="#C8DDD8"
      />
      <pointLight position={[0, -1, 4]} intensity={2.2} color="#FFFFFF" />
      <group rotation={[-0.03, 0, 0]} scale={1.02} position={[0, 0.1, 0]}>
        <mesh geometry={headGeometry} castShadow receiveShadow>
          <meshPhysicalMaterial
            color="#DDE6EC"
            roughness={0.82}
            metalness={0.02}
            clearcoat={0.08}
          />
        </mesh>
        <EEGHardware mode={mode} />
        {active.map((n) => {
          const position = sensorPositions[n];
          const motor =
            (direction === "LEFT" && n === "C4") ||
            (direction === "RIGHT" && n === "C3");
          const front = n.startsWith("F");
          const side = n === "T7" || n === "T8";
          return (
            <group key={n} position={position}>
              <mesh
                rotation={
                  front
                    ? [Math.PI / 2, 0, 0]
                    : side
                      ? [0, 0, Math.PI / 2]
                      : [0, 0, 0]
                }
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(n);
                }}
              >
                <cylinderGeometry args={[0.105, 0.105, 0.065, 32]} />
                <meshStandardMaterial
                  color={
                    selected === n ? "#39776F" : motor ? "#527C98" : "#82B5AD"
                  }
                  roughness={0.32}
                  metalness={0.22}
                />
              </mesh>
              <mesh position={[0, front ? 0.04 : 0.055, front ? 0.04 : 0]}>
                <cylinderGeometry args={[0.062, 0.062, 0.022, 24]} />
                <meshStandardMaterial
                  color="#C7D0D7"
                  metalness={0.62}
                  roughness={0.28}
                />
              </mesh>
              {!(["F3", "F4"] as string[]).includes(n) && (
                <Html
                  center
                  distanceFactor={3.2}
                  position={labelOffsets[n] ?? [0, 0.18, 0]}
                  zIndexRange={[1000 - active.indexOf(n), 0]}
                >
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
        {active.includes("F3") && (
          <Html
            center
            distanceFactor={3.2}
            position={[-0.29, 0.55, 1.03]}
            zIndexRange={[1100, 0]}
          >
            <button
              className={`electrode ${selected === "F3" ? "selected" : ""}`}
              onClick={() => onSelect("F3")}
              title={channelInfo("F3")}
            >
              F3
            </button>
          </Html>
        )}
        {active.includes("F4") && (
          <Html
            center
            distanceFactor={3.2}
            position={[0.28, 0.73, 1.02]}
            zIndexRange={[1090, 0]}
          >
            <button
              className={`electrode ${selected === "F4" ? "selected" : ""}`}
              onClick={() => onSelect("F4")}
              title={channelInfo("F4")}
            >
              F4
            </button>
          </Html>
        )}
        <group position={[0.77, 0.05, -0.27]} rotation={[0, 0.2, 0]}>
          <RoundedBox args={[0.18, 0.42, 0.32]} radius={0.055} smoothness={4}>
            <meshStandardMaterial
              color="#253F55"
              roughness={0.42}
              metalness={0.12}
            />
          </RoundedBox>
          <mesh position={[0.095, 0.08, 0]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.035, 0.035, 0.012, 20]} />
            <meshStandardMaterial color="#82B5AD" />
          </mesh>
        </group>
      </group>
      <OrbitControls
        enablePan={false}
        enableZoom
        target={[0, -0.12, 0]}
        minDistance={3.8}
        maxDistance={7.2}
        minPolarAngle={0.35}
        maxPolarAngle={1.75}
        autoRotate={false}
      />
    </>
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
      <ambientLight intensity={1.45} />
      <pointLight position={[3, 4, 5]} intensity={17} color="#FFFFFF" />
      <pointLight position={[-3, 2, 2]} intensity={7} color="#D8EAE5" />
      <group rotation={[-0.18, 0, 0]}>
        <mesh scale={[0.96, 1.25, 1.08]}>
          <sphereGeometry args={[1, 48, 40]} />
          <meshPhysicalMaterial
            color="#91AEB4"
            roughness={0.52}
            transparent
            opacity={0.72}
            metalness={0.12}
          />
        </mesh>
        {paths.map((p, i) => (
          <Line
            key={i}
            points={p}
            color="#527C98"
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
          color="#253F55"
          lineWidth={3}
        />
        <mesh position={[0, -0.1, 1.08]} scale={[0.12, 0.25, 0.16]}>
          <sphereGeometry />
          <meshStandardMaterial color="#78959F" />
        </mesh>
        {[-1, 1].map((s) => (
          <mesh
            key={s}
            position={[s * 0.96, -0.08, 0]}
            scale={[0.12, 0.3, 0.18]}
          >
            <sphereGeometry />
            <meshStandardMaterial color="#78959F" />
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
                        ? "#527C98"
                        : "#8A79AF"
                      : enabled
                        ? "#82B5AD"
                        : "#CBD5DF"
                  }
                  emissive={
                    motor && direction === "RIGHT" ? "#8A79AF" : "#82B5AD"
                  }
                  emissiveIntensity={enabled ? 0.18 : 0}
                  roughness={0.38}
                  metalness={0.12}
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

function BrainCamera() {
  const { camera } = useThree();
  useEffect(() => {
    camera.position.set(3.7, 1.65, 6.2);
    camera.lookAt(0, -0.08, 0);
    camera.updateProjectionMatrix();
  }, [camera]);
  return null;
}

function createMannequinHead() {
  const geometry = new BufferGeometry();
  const rings = [
    [-1.72, 0.34, 0.32, -0.12],
    [-1.34, 0.4, 0.36, -0.08],
    [-1.16, 0.3, 0.44, 0.16],
    [-0.96, 0.5, 0.58, 0.14],
    [-0.7, 0.66, 0.67, 0.1],
    [-0.36, 0.76, 0.75, 0.08],
    [0.02, 0.77, 0.8, 0.06],
    [0.4, 0.74, 0.81, 0.02],
    [0.72, 0.73, 0.76, -0.02],
    [0.98, 0.62, 0.64, -0.05],
    [1.17, 0.34, 0.35, -0.06],
    [1.24, 0.05, 0.05, -0.06],
  ] as const;
  const segments = 64;
  const vertices: number[] = [];
  const indices: number[] = [];
  rings.forEach(([y, width, depth, zShift]) => {
    for (let i = 0; i < segments; i += 1) {
      const angle = (i / segments) * Math.PI * 2;
      const front = Math.max(0, Math.cos(angle));
      const jawTaper = y < -0.7 ? 0.92 + front * 0.08 : 1;
      vertices.push(
        Math.sin(angle) * width * jawTaper,
        y,
        Math.cos(angle) * depth +
          zShift +
          front * (y > -0.9 && y < 0.45 ? 0.055 : 0),
      );
    }
  });
  for (let ring = 0; ring < rings.length - 1; ring += 1) {
    for (let i = 0; i < segments; i += 1) {
      const next = (i + 1) % segments;
      const a = ring * segments + i;
      const b = ring * segments + next;
      const c = (ring + 1) * segments + i;
      const d = (ring + 1) * segments + next;
      indices.push(a, c, b, b, c, d);
    }
  }
  const bottomCenter = vertices.length / 3;
  vertices.push(0, rings[0][0], rings[0][3]);
  const topCenter = vertices.length / 3;
  const top = rings[rings.length - 1];
  vertices.push(0, top[0], top[3]);
  for (let i = 0; i < segments; i += 1) {
    const next = (i + 1) % segments;
    indices.push(bottomCenter, next, i);
    const topStart = (rings.length - 1) * segments;
    indices.push(topCenter, topStart + i, topStart + next);
  }
  geometry.setAttribute("position", new Float32BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function DeviceBand({
  points,
  radius = 0.045,
  color = "#253F55",
}: {
  points: [number, number, number][];
  radius?: number;
  color?: string;
}) {
  const curve = useMemo(
    () => new CatmullRomCurve3(points.map((point) => new Vector3(...point))),
    [points],
  );
  return (
    <mesh castShadow>
      <tubeGeometry args={[curve, 48, radius, 10, false]} />
      <meshStandardMaterial color={color} roughness={0.46} metalness={0.12} />
    </mesh>
  );
}

function EEGHardware({ mode }: { mode: ChannelMode }) {
  const frontBand: [number, number, number][] = [
    [-0.73, 0.42, 0.5],
    [-0.38, 0.59, 0.76],
    [0, 0.64, 0.82],
    [0.38, 0.59, 0.76],
    [0.73, 0.42, 0.5],
  ];
  const motorBand: [number, number, number][] = [
    [-0.73, 0.43, 0.08],
    [-0.55, 0.91, 0.18],
    [0, 1.18, 0.02],
    [0.55, 0.91, 0.18],
    [0.73, 0.43, 0.08],
  ];
  const sideBand: [number, number, number][] = [
    [-0.78, 0.14, 0.03],
    [-0.7, 0.55, -0.35],
    [0, 0.86, -0.62],
    [0.7, 0.55, -0.35],
    [0.78, 0.14, 0.03],
  ];
  return (
    <group>
      <DeviceBand points={frontBand} radius={0.055} />
      <DeviceBand points={motorBand} radius={0.05} color="#527C98" />
      {mode !== "5ch" && (
        <DeviceBand points={sideBand} radius={0.042} color="#527C98" />
      )}
      {mode === "16ch" && (
        <>
          <DeviceBand
            points={[
              [-0.7, 0.35, 0.5],
              [-0.7, 0.7, 0],
              [-0.6, 0.45, -0.52],
            ]}
            radius={0.032}
          />
          <DeviceBand
            points={[
              [0.7, 0.35, 0.5],
              [0.7, 0.7, 0],
              [0.6, 0.45, -0.52],
            ]}
            radius={0.032}
          />
          <DeviceBand
            points={[
              [0, 0.64, 0.82],
              [0, 1.18, 0.02],
              [0, 0.84, -0.62],
            ]}
            radius={0.036}
          />
        </>
      )}
    </group>
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

function Television({ on }: { on: boolean }) {
  const screen = useRef<Group>(null);
  useFrame((_, dt) => {
    if (!screen.current) return;
    screen.current.scale.y = MathUtils.damp(
      screen.current.scale.y,
      on ? 1 : 0.015,
      8,
      dt,
    );
    screen.current.scale.x = MathUtils.damp(
      screen.current.scale.x,
      on ? 1 : 0.55,
      8,
      dt,
    );
  });
  return (
    <group>
      <Box
        position={[1.48, 1.65, -2.23]}
        size={[2.05, 1.25, 0.12]}
        color="#1C2B36"
      />
      <mesh position={[1.48, 1.65, -2.155]}>
        <planeGeometry args={[1.88, 1.08]} />
        <meshBasicMaterial color="#030608" />
      </mesh>
      <group ref={screen} position={[1.48, 1.65, -2.145]}>
        <mesh>
          <planeGeometry args={[1.86, 1.06]} />
          <meshBasicMaterial color="#7CCED5" />
        </mesh>
      </group>
      <mesh position={[2.35, 1.08, -2.14]}>
        <sphereGeometry args={[0.035, 16, 16]} />
        <meshStandardMaterial
          color={on ? "#55E7C7" : "#59646B"}
          emissive={on ? "#55E7C7" : "#000000"}
          emissiveIntensity={on ? 1.4 : 0}
        />
      </mesh>
    </group>
  );
}

export function Room() {
  const s = useBCI();
  return (
    <>
      <color attach="background" args={["#F4F1EA"]} />
      <RoomLighting on={s.light} />
      <Box position={[0, -0.1, 0]} size={[6, 0.2, 4.8]} color="#D8C8B2" />
      <Box position={[0, 1.55, -2.4]} size={[6, 3.3, 0.13]} color="#F7F4EC" />
      <Box position={[-3, 1.55, 0]} size={[0.13, 3.3, 4.8]} color="#E9EEF0" />
      {Array.from({ length: 12 }, (_, i) => (
        <Box
          key={i}
          position={[-2.8 + i * 0.5, 0.012, 0]}
          size={[0.012, 0.01, 4.7]}
          color="#BCA98F"
        />
      ))}
      <Box
        position={[-1.45, 1.8, -2.3]}
        size={[2.4, 2.1, 0.08]}
        color="#DDECF0"
      />
      <Box
        position={[-1.45, 1.8, -2.22]}
        size={[0.055, 2.1, 0.06]}
        color="#9CAAB6"
      />
      {[-1, 1].map((side) => (
        <Curtain key={side} side={side} open={s.curtains} />
      ))}
      <Television on={s.tv} />
      <Box
        position={[1.4, 0.39, -1.97]}
        size={[2.5, 0.65, 0.65]}
        color="#C8AA82"
      />
      <Box position={[-1.6, 0.4, 0.8]} size={[2.2, 0.58, 1]} color="#E9EEEC" />
      <Box
        position={[-1.6, 0.86, 1.19]}
        size={[2.2, 0.68, 0.24]}
        color="#C4D4CF"
      />
      {[-2.65, -0.55].map((x) => (
        <Box
          key={x}
          position={[x, 0.66, 0.75]}
          size={[0.22, 0.65, 1.15]}
          color="#C4D4CF"
        />
      ))}
      {[-2.15, -1.12].map((x) => (
        <Box
          key={x}
          position={[x, 0.77, 0.72]}
          size={[0.9, 0.15, 0.75]}
          color="#F8FAF9"
        />
      ))}
      <Box
        position={[-0.2, 0.04, 0.35]}
        size={[3.3, 0.03, 2.4]}
        color="#AFC7C2"
      />
      <Box
        position={[0.05, 0.4, 0.3]}
        size={[1.3, 0.12, 0.8]}
        color="#D6B891"
      />
      {[-0.48, 0.48].map((x) => (
        <Box
          key={x}
          position={[x, 0.2, 0.3]}
          size={[0.06, 0.4, 0.5]}
          color="#527C6F"
        />
      ))}
      <mesh position={[2.35, 0.32, 1.35]}>
        <cylinderGeometry args={[0.24, 0.18, 0.6, 20]} />
        <meshStandardMaterial color="#D4DAD5" />
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
          <meshStandardMaterial color="#6E9C84" />
        </mesh>
      ))}
      <mesh position={[0, 2.8, 0]}>
        <cylinderGeometry args={[0.45, 0.65, 0.18, 32]} />
        <meshStandardMaterial
          color="#F1E7D3"
          emissive="#ffe3a1"
          emissiveIntensity={s.light ? 1 : 0}
        />
      </mesh>
      <Line
        points={[
          [0, 2.8, 0],
          [0, 3.4, 0],
        ]}
        color="#9CAAB6"
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
      <div
        className={`fallback-tv ${s.tv ? "on" : "off"}`}
        aria-label={`TV 전원 ${s.tv ? "켜짐" : "꺼짐"}`}
      >
        <i aria-hidden="true" />
      </div>
      <div className="sofa">━━━</div>
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
          color={i % 2 ? "#82B5AD" : "#A9CBC4"}
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
        color="#FFFDF7"
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
