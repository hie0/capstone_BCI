import { useId } from "react";

type Kind =
  | "covariance"
  | "shrinkage"
  | "tangent"
  | "centering"
  | "oas-detail"
  | "features"
  | "alignment";

const titles: Record<Kind, string> = {
  covariance: "Cross-session covariance 분포 개념도",
  shrinkage: "OAS shrinkage로 covariance 추정을 안정화하는 개념도",
  tangent: "SPD manifold에서 tangent space로 투영하는 개념도",
  centering: "Logit centering으로 분류 출력의 기준점을 정렬하는 개념도",
  "oas-detail": "OAS shrinkage 적용 전후 covariance 개념도",
  features: "CSP 공간 필터와 tangent-space features 개념도",
  alignment:
    "누적 covariance reference를 사용하는 causal input alignment 개념도",
};

// All graphics are explanatory schematics, not measured EEG or fitted model results.
export function StabilityDiagram({ kind }: { kind: Kind }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const sage = `sage${id}`,
    blue = `blue${id}`,
    arrow = `arrow${id}`;
  const arrowLine = (x1: number, y1: number, x2: number, y2: number) => (
    <path
      d={`M${x1},${y1} L${x2},${y2}`}
      fill="none"
      stroke="#39776F"
      strokeWidth="1.7"
      markerEnd={`url(#${arrow})`}
    />
  );
  const ellipse = (
    x: number,
    y: number,
    rx: number,
    ry: number,
    angle: number,
    color = "sage",
    scatter = false,
  ) => (
    <g transform={`translate(${x} ${y}) rotate(${angle})`}>
      <ellipse
        rx={rx}
        ry={ry}
        fill={`url(#${color === "sage" ? sage : blue})`}
        stroke={color === "sage" ? "#739F97" : "#7797B1"}
        strokeWidth="1.1"
      />
      <ellipse
        rx={rx * 0.68}
        ry={ry * 0.68}
        fill="none"
        stroke={color === "sage" ? "#84B0A6" : "#9DB7CB"}
        strokeWidth=".8"
      />
      <ellipse
        rx={rx * 0.35}
        ry={ry * 0.35}
        fill="none"
        stroke={color === "sage" ? "#A3C5BA" : "#B6CBDA"}
        strokeWidth=".7"
      />
      {scatter &&
        Array.from({ length: 13 }, (_, i) => {
          const a = i * 2.4,
            r = 0.48 + (i % 3) * 0.14;
          return (
            <circle
              key={i}
              cx={Math.cos(a) * rx * r}
              cy={Math.sin(a) * ry * r}
              r="1.7"
              fill={color === "sage" ? "#6A9F92" : "#7394AE"}
              opacity={0.4 + (i % 4) * 0.13}
            />
          );
        })}
      <circle r="3.4" fill="#39776F" />
    </g>
  );
  const plane = (x: number, y: number, scale = 1) => (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <path
        d="M0 72 L30 0 H139 L109 72 Z"
        fill={`url(#${sage})`}
        fillOpacity=".55"
        stroke="#7EA7A1"
      />
      {[1, 2, 3].map((i) => (
        <path
          key={i}
          d={`M${i * 27} 72 l30 -72 M${30 - i * 7.5} ${i * 18} h109`}
          stroke="#B6D0C9"
          strokeWidth=".8"
          fill="none"
        />
      ))}
      {[
        [47, 20],
        [92, 20],
        [61, 48],
        [94, 47],
      ].map(([cx, cy], i) => (
        <g key={i}>
          <circle cx={cx} cy={cy} r="7" fill="#B8D8CE" opacity=".7" />
          <circle cx={cx} cy={cy} r="3.4" fill="#39776F" />
        </g>
      ))}
    </g>
  );
  const gaussian = (mean: number, sigma: number) => {
    const points = Array.from({ length: 81 }, (_, i) => {
      const x = 18 + i * 3.25;
      const y = 119 - 76 * Math.exp(-0.5 * ((x - mean) / sigma) ** 2);
      return `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    return { line: points, area: `${points} L278,120 L18,120 Z` };
  };
  const left = gaussian(105, 31),
    right = gaussian(193, 33);
  const scalp = (x: number, fill: string, gradient: string) => (
    <g transform={`translate(${x} 68)`}>
      <ellipse rx="29" ry="34" fill="#F8FBFA" stroke="#526574" />
      <path
        d="M-7 -33 L0 -40 L7 -33 M-29 -9 Q-38 -12 -32 10 M29 -9 Q38 -12 32 10"
        fill="none"
        stroke="#526574"
      />
      <ellipse cx="-5" cy="5" rx="27" ry="28" fill={`url(#${gradient})`} />
      {[10, 16, 22].map((r) => (
        <ellipse
          key={r}
          cx="-5"
          cy="5"
          rx={r * 0.83}
          ry={r}
          fill="none"
          stroke={fill}
          opacity=".48"
          strokeWidth=".65"
        />
      ))}
      <circle cx="-5" cy="5" r="4" fill={fill} opacity=".75" />
    </g>
  );
  return (
    <svg
      className={`stability-diagram stability-diagram-${kind}`}
      viewBox="0 0 300 150"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={titles[kind]}
    >
      <defs>
        <radialGradient id={sage}>
          <stop stopColor="#91BEB0" stopOpacity=".8" />
          <stop offset="1" stopColor="#E2EFEB" stopOpacity=".55" />
        </radialGradient>
        <radialGradient id={blue}>
          <stop stopColor="#588DB7" stopOpacity=".8" />
          <stop offset="1" stopColor="#E0ECF4" stopOpacity=".5" />
        </radialGradient>
        <marker
          id={arrow}
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path
            d="M1 1 L8 5 L1 9"
            fill="none"
            stroke="#39776F"
            strokeWidth="1.3"
          />
        </marker>
      </defs>
      {kind === "covariance" && (
        <>
          {ellipse(78, 48, 63, 26, -24, "sage", true)}
          {ellipse(221, 53, 55, 24, 28, "blue", true)}
          {ellipse(156, 111, 62, 28, 6, "sage", true)}
        </>
      )}
      {kind === "shrinkage" && (
        <>
          <ellipse
            cx="150"
            cy="76"
            rx="101"
            ry="60"
            fill="none"
            stroke="#90B4AC"
            strokeDasharray="4 3"
          />
          {ellipse(150, 76, 66, 37, 0)}
          {arrowLine(150, 23, 150, 37)}
          {arrowLine(150, 130, 150, 115)}
          {arrowLine(63, 76, 79, 76)}
          {arrowLine(237, 76, 222, 76)}
        </>
      )}
      {kind === "tangent" && (
        <>
          <path
            d="M7 121 Q39 -24 107 44 Q139 63 160 122 Q73 72 7 121Z"
            fill={`url(#${sage})`}
            stroke="#90B4AD"
            strokeWidth=".8"
          />
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <g key={i} stroke="#A9C8C0" strokeWidth=".7" fill="none">
              <path
                d={`M${7 + i * 23} ${121 - i * 5} Q${43 + i * 10} ${-10 + i * 9} ${89 + i * 13} ${99 + i * 4}`}
              />
              <path
                d={`M${15 + i * 5} ${103 - i * 12} Q79 ${45 - i * 8} ${151 - i * 9} ${108 - i * 12}`}
              />
            </g>
          ))}
          <circle cx="100" cy="67" r="3.7" fill="#39776F" />
          <path
            d="M100 67 Q152 7 195 55"
            fill="none"
            stroke="#39776F"
            strokeWidth="1.8"
            markerEnd={`url(#${arrow})`}
          />
          {plane(157, 58, 0.97)}
          <text x="39" y="29" className="diagram-math">
            ℳ
          </text>
          <text x="218" y="42" className="diagram-math">
            <tspan fontStyle="italic">T</tspan>
            <tspan baselineShift="sub" fontSize="12">
              Σ
            </tspan>
            <tspan>ℳ</tspan>
          </text>
        </>
      )}
      {kind === "centering" && (
        <>
          <path d={left.area} fill={`url(#${blue})`} />
          <path d={right.area} fill={`url(#${sage})`} />
          <path d={left.line} fill="none" stroke="#527C98" strokeWidth="1.6" />
          <path d={right.line} fill="none" stroke="#72A97C" strokeWidth="1.6" />
          <path
            d="M14 123 H285 M150 24 V126"
            stroke="#526574"
            strokeWidth="1"
            fill="none"
          />
          <path
            d="M150 24 V126"
            stroke="#39776F"
            strokeWidth="1.8"
            strokeDasharray="4 3"
          />
          <path d="M281 120 L286 123 L281 126" stroke="#526574" fill="none" />
          <text x="34" y="20" className="diagram-math diagram-posterior">
            p(y = −1 | z)
          </text>
          <text x="199" y="20" className="diagram-math diagram-posterior">
            p(y = +1 | z)
          </text>
          <text x="146" y="142" className="diagram-math">
            0
          </text>
          <text x="291" y="128" className="diagram-math">
            z
          </text>
        </>
      )}
      {kind === "oas-detail" && (
        <>
          {ellipse(75, 70, 67, 31, -22)}
          {arrowLine(151, 70, 175, 70)}
          {ellipse(235, 70, 48, 25, -22)}
          <text x="69" y="132" className="diagram-math">
            Σ
          </text>
          <text x="220" y="132" className="diagram-math">
            <tspan>Σ</tspan>
            <tspan baselineShift="sub" fontSize="12">
              OAS
            </tspan>
          </text>
        </>
      )}
      {kind === "features" && (
        <>
          {scalp(37, "#527C98", blue)}
          {scalp(111, "#659E78", sage)}
          {arrowLine(151, 70, 171, 70)}
          {plane(178, 43, 0.8)}
          <path
            d="M176 105 H293 M176 105 L216 30"
            fill="none"
            stroke="#526574"
            strokeWidth="1"
          />
          <text x="280" y="123" className="diagram-math">
            <tspan fontStyle="italic">x</tspan>
            <tspan baselineShift="sub" fontSize="12">
              1
            </tspan>
          </text>
          <text x="217" y="32" className="diagram-math">
            <tspan fontStyle="italic">x</tspan>
            <tspan baselineShift="sub" fontSize="12">
              2
            </tspan>
          </text>
        </>
      )}
      {kind === "alignment" && (
        <>
          {arrowLine(42, 104, 110, 104)}
          {arrowLine(164, 104, 238, 104)}
          <path
            d="M132 41 Q92 43 43 79 M165 41 Q211 44 246 79"
            fill="none"
            stroke="#527C98"
            strokeWidth="1.3"
            markerEnd={`url(#${arrow})`}
          />
          {[
            [25, 104, "z", blue],
            [138, 104, "x", sage],
            [267, 104, "y", sage],
            [150, 31, "C", sage],
          ].map(([x, y, text, gradient]) => (
            <g key={text}>
              <circle
                cx={Number(x)}
                cy={Number(y)}
                r="23"
                fill={`url(#${gradient})`}
                stroke="#91ADA7"
              />
              <text
                x={Number(x)}
                y={Number(y) + 6}
                textAnchor="middle"
                className="diagram-math"
              >
                <tspan fontStyle="italic">{text}</tspan>
                <tspan baselineShift="sub" fontSize="12">
                  t
                </tspan>
              </text>
            </g>
          ))}
        </>
      )}
    </svg>
  );
}
