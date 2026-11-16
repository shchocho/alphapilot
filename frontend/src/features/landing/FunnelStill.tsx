/**
 * 3D 장면과 같은 구도의 정지 그림(SVG). 3D 묶음을 내려받는 동안과 WebGL2를 쓸 수 없을 때 보인다.
 * 자리·높이·카메라는 funnel.ts의 값을 그대로 쓴다. 빛과 재질은 없다(선과 면으로만 그린다).
 */

import { useMemo } from "react";
import { barAt, CAMERA, FIELD, field, GATE_LABELS, labelX, projector, smoothstep } from "./funnel";

interface Props {
  width: number;
  height: number;
  /** "start": 3D가 처음 그리는 장면과 같은 자리. "overview": 걸러진 결과 전체가 보이는 자리 */
  view: "start" | "overview";
}

export function FunnelStill({ width, height, view }: Props) {
  const drawing = useMemo(() => {
    if (width < 2 || height < 2) return null;
    const aspect = width / height;
    const back = CAMERA.pullBack(aspect);
    const [from, to] = [CAMERA.path[0], CAMERA.looks[0]];
    const pose = view === "overview" ? CAMERA.overview(aspect) : { eye: [to[0] + (from[0] - to[0]) * back, to[1] + (from[1] - to[1]) * back, to[2] + (from[2] - to[2]) * back] as const, target: to };
    const project = projector(pose.eye, pose.target, CAMERA.fov(aspect), aspect);
    const [fogNear, fogFar] = view === "overview" ? [30, 92] : [16, 48];
    const toScreen = (x: number, y: number, z: number) => {
      const p = project(x, y, z);
      return { x: (p.x * 0.5 + 0.5) * width, y: (-p.y * 0.5 + 0.5) * height, depth: p.depth };
    };
    const progress = view === "overview" ? 1 : 0;

    // "start"는 3D의 등장이 시작되는 순간과 같은 그림이다: 관문만 있고 기둥은 아직 올라오지 않았다
    const bars = (view === "overview" ? field() : [])
      .map((bar) => {
        const s = barAt(bar, progress);
        const base = toScreen(s.x, 0, s.z);
        const top = toScreen(s.x, s.height, s.z);
        const side = toScreen(s.x + FIELD.barWidth, 0, s.z);
        return { base, top, thickness: Math.max(1, Math.hypot(side.x - base.x, side.y - base.y)), tint: s.tint, clear: 1 - smoothstep(fogNear, fogFar, base.depth) };
      })
      .filter((b) => b.base.depth > 0.5 && b.clear > 0.02)
      .sort((a, b) => b.base.depth - a.base.depth);

    const half = FIELD.gateWidth / 2;
    const gates = FIELD.gateZ.map((z, i) => {
      const corners = [toScreen(-half, 0, z), toScreen(half, 0, z), toScreen(half, FIELD.gateHeight, z), toScreen(-half, FIELD.gateHeight, z)];
      return {
        label: GATE_LABELS[i],
        points: corners.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" "),
        anchor: toScreen(labelX(true), FIELD.gateHeight, z),
        clear: 1 - smoothstep(fogNear, fogFar, corners[0].depth),
        behind: corners.some((c) => c.depth <= 0.5),
      };
    });
    return { bars, gates };
  }, [width, height, view]);

  if (!drawing) return null;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden className="block">
      {drawing.gates.map(
        (gate) =>
          !gate.behind && (
            <g key={gate.label} opacity={gate.clear}>
              <polygon points={gate.points} style={{ fill: "var(--ink-muted)", fillOpacity: 0.07, stroke: "var(--border)" }} strokeWidth={1} />
              {view === "overview" && (
                <text x={gate.anchor.x} y={gate.anchor.y - 8} textAnchor="middle" style={{ fill: "var(--ink-secondary)", font: "500 13px var(--font-sans)" }}>
                  {gate.label}
                </text>
              )}
            </g>
          ),
      )}
      {drawing.bars.map((bar, i) => (
        <line
          key={i}
          x1={bar.base.x}
          y1={bar.base.y}
          x2={bar.top.x}
          y2={Math.min(bar.top.y, bar.base.y - 1)}
          strokeWidth={bar.thickness}
          opacity={bar.clear}
          style={{ stroke: bar.tint > 0.5 ? "var(--accent)" : bar.tint < -0.5 ? "var(--data-3)" : "var(--data-2)" }}
        />
      ))}
    </svg>
  );
}
