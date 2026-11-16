/**
 * 메인 화면의 실시간 3D 장면(WebGL2, three.js).
 *
 * 보여주는 것: 143종목이 관문 셋(기법 조건 → 위원회 심의 → 리스크 점검)을 지나며 3건의 주문 계획으로 걸러지는 과정.
 * 멈춘 종목은 관문 앞에 납작하게 남는다(엔진이 "안 한 일"도 기록으로 남는다는 뜻).
 *
 * 기준(universal-design-intelligence의 MOTION_DESIGN): 스크롤 진행률 하나 → 감쇠 → 모든 상태가 그 값의 함수,
 * 스플라인 카메라, PBR + 환경광, 인스턴싱(종목 전체가 드로우콜 1), 배경은 토큰과 일치(투명 캔버스 + 같은 색 안개),
 * compileAsync 뒤 첫 프레임, 숨김 시 정지, dispose, reduced-motion 정지 구도.
 * 형상은 코드로 만든 것이고 모델 파일은 없다. 자리·높이·카메라 값은 funnel.ts에 있고 정지 그림(FunnelStill)과 함께 쓴다.
 */

import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { barAt, CAMERA, FIELD, field, INTRO, introScale, labelX, type BarState } from "./funnel";

export interface Anchor {
  x: number;
  y: number;
  /** 카메라에서 떨어진 거리. 이름표가 겹치면 가까운 쪽을 남기는 데 쓴다. */
  distance: number;
  visible: boolean;
}

export interface FunnelHandle {
  /** 스크롤 진행률(0~1). 장면은 감쇠해서 따라간다. */
  setProgress(progress: number): void;
  /** 화면 밖이면 멈춘다(탭이 숨겨지면 스스로 멈춘다). */
  setRunning(running: boolean): void;
  /** 테마가 바뀌면 토큰 색을 다시 읽는다. */
  refreshColors(): void;
  /** 마지막으로 그린 프레임의 드로우콜·삼각형 수(검증 기록용). */
  stats(): { calls: number; triangles: number };
  dispose(): void;
}

interface Options {
  /** true면 스크롤을 따라가지 않고 걸러진 결과 전체가 보이는 정지 구도 한 장만 그린다(모션 줄이기). */
  still: boolean;
  /** 화면을 처음 열 때 기둥이 바닥에서 올라오는 등장을 한 번 보인다(정지 구도에서는 쓰지 않는다). */
  intro: boolean;
  /** 관문 이름표(관문 순서대로)와 주문 계획 이름표(자리 순서대로)가 놓일 화면 좌표. 그릴 때마다 부른다. */
  onAnchors: (gates: Anchor[], plans: Anchor[]) => void;
}

const tokenColor = (name: string): THREE.Color => {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return new THREE.Color(value || "#808080");
};

export function supportsWebGL2(): boolean {
  try {
    return Boolean(document.createElement("canvas").getContext("webgl2"));
  } catch {
    return false;
  }
}

export async function mountFunnel(canvas: HTMLCanvasElement, options: Options): Promise<FunnelHandle> {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  const dpr = () => Math.min(window.devicePixelRatio || 1, coarse ? 1.5 : 2);
  renderer.setPixelRatio(dpr());
  renderer.setClearAlpha(0); // 배경은 CSS의 canvas 토큰이 그대로 보인다(픽셀 단위로 일치)
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = environment;
  const fog = options.still ? new THREE.Fog(0xffffff, 30, 92) : new THREE.Fog(0xffffff, 16, 48);
  scene.fog = fog;

  // 위쪽 한 방향에서 드는 빛: 막대의 윗면과 옆면이 갈려 입체로 읽힌다(그림자 맵은 쓰지 않는다)
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(-6, 12, 8);
  // 맨 끝에서 뒤돌아볼 때 카메라 쪽 면이 어둡지 않게 뒤에서 드는 빛
  const back = new THREE.DirectionalLight(0xffffff, 1.1);
  back.position.set(7, 9, -52);
  scene.add(key, back);

  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 140);
  const path = new THREE.CatmullRomCurve3(CAMERA.path.map((p) => new THREE.Vector3(...p)));
  const lookPath = new THREE.CatmullRomCurve3(CAMERA.looks.map((p) => new THREE.Vector3(...p)));

  // ── 종목 143개: 인스턴스 메시 하나 ─────────────────────────────────
  const items = field();
  const count = items.length;
  // 모서리를 둥글린 사각 기둥. 세로 모서리만 둥글려서 높이를 늘려도 모양이 변하지 않는다.
  const half = FIELD.barWidth / 2;
  const round = 0.08;
  const outline = new THREE.Shape();
  outline.moveTo(-half + round, -half);
  outline.lineTo(half - round, -half);
  outline.absarc(half - round, -half + round, round, -Math.PI / 2, 0, false);
  outline.lineTo(half, half - round);
  outline.absarc(half - round, half - round, round, 0, Math.PI / 2, false);
  outline.lineTo(-half + round, half);
  outline.absarc(-half + round, half - round, round, Math.PI / 2, Math.PI, false);
  outline.lineTo(-half, -half + round);
  outline.absarc(-half + round, -half + round, round, Math.PI, Math.PI * 1.5, false);
  const geometry = new THREE.ExtrudeGeometry(outline, { depth: 1, bevelEnabled: false, curveSegments: 5 });
  geometry.rotateX(-Math.PI / 2); // 뽑아 올린 방향을 위(y)로: 바닥에 붙여 높이만 늘린다
  geometry.clearGroups();
  const material = new THREE.MeshStandardMaterial({ roughness: 0.34, metalness: 0.3, envMapIntensity: 1.1 });
  const bars = new THREE.InstancedMesh(geometry, material, count);
  bars.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  bars.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(count * 3), 3);
  bars.instanceColor.setUsage(THREE.DynamicDrawUsage);
  bars.frustumCulled = false;
  scene.add(bars);

  // 바닥에 비친 상: 같은 기둥을 아래로 뒤집어, 바닥에서 멀어질수록 옅어지게 그린다(인스턴스 값은 위의 것을 함께 쓴다).
  const mirrorGeometry = geometry.clone();
  mirrorGeometry.scale(1, -1, 1);
  for (const name of ["position", "normal", "uv"]) {
    // 뒤집으면 면의 앞뒤가 바뀌므로 삼각형마다 꼭짓점 둘의 순서를 바꿔 되돌린다
    const attribute = mirrorGeometry.getAttribute(name) as THREE.BufferAttribute;
    const size = attribute.itemSize;
    const values = attribute.array;
    for (let v = 0; v < attribute.count; v += 3) {
      for (let k = 0; k < size; k += 1) {
        const a = (v + 1) * size + k;
        const b = (v + 2) * size + k;
        const kept = values[a];
        values[a] = values[b];
        values[b] = kept;
      }
    }
  }
  const mirrorMaterial = new THREE.MeshStandardMaterial({ roughness: 0.34, metalness: 0.3, envMapIntensity: 1.1, transparent: true, opacity: 0.3, depthWrite: false });
  mirrorMaterial.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying float vBelow;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\n#ifdef USE_INSTANCING\n  vBelow = -(instanceMatrix * vec4(position, 1.0)).y;\n#else\n  vBelow = -position.y;\n#endif");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying float vBelow;")
      .replace("#include <dithering_fragment>", "#include <dithering_fragment>\n  gl_FragColor.a *= 1.0 - smoothstep(0.0, 1.5, vBelow);");
  };
  const mirror = new THREE.InstancedMesh(mirrorGeometry, mirrorMaterial, count);
  mirror.instanceMatrix = bars.instanceMatrix;
  mirror.instanceColor = bars.instanceColor;
  mirror.frustumCulled = false;
  mirror.renderOrder = 1;
  scene.add(mirror);

  // ── 관문 셋: 얇은 판(인스턴스 메시 하나)과 테두리(선 묶음 하나) ─────────
  const gateGeometry = new THREE.PlaneGeometry(FIELD.gateWidth, FIELD.gateHeight);
  const gateMaterial = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.045, side: THREE.DoubleSide, depthWrite: false });
  const gates = new THREE.InstancedMesh(gateGeometry, gateMaterial, FIELD.gateZ.length);
  const edgePoints: number[] = [];
  const halfW = FIELD.gateWidth / 2;
  FIELD.gateZ.forEach((z, i) => {
    gates.setMatrixAt(i, new THREE.Matrix4().makeTranslation(0, FIELD.gateHeight / 2, z));
    const corners = [-halfW, 0, halfW, 0, halfW, FIELD.gateHeight, -halfW, FIELD.gateHeight];
    for (let c = 0; c < 4; c += 1) {
      const n = (c + 1) % 4;
      edgePoints.push(corners[c * 2], corners[c * 2 + 1], z, corners[n * 2], corners[n * 2 + 1], z);
    }
  });
  gates.frustumCulled = false;
  gates.renderOrder = 2;
  const edgeGeometry = new THREE.BufferGeometry();
  edgeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(edgePoints, 3));
  const edgeMaterial = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.9 });
  const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);
  edges.frustumCulled = false;
  scene.add(gates, edges);

  // 바닥의 줄: 종목이 지나가는 길의 양쪽 가장자리와, 장부처럼 일정한 간격으로 그은 가로줄
  const lanePoints = [-halfW, 0, 9, -halfW, 0, FIELD.endZ - 4, halfW, 0, 9, halfW, 0, FIELD.endZ - 4];
  for (let z = 8; z >= FIELD.endZ - 4; z -= 2) lanePoints.push(-halfW, 0, z, halfW, 0, z);
  const laneGeometry = new THREE.BufferGeometry();
  laneGeometry.setAttribute("position", new THREE.Float32BufferAttribute(lanePoints, 3));
  const laneMaterial = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.8 });
  const lanes = new THREE.LineSegments(laneGeometry, laneMaterial);
  lanes.frustumCulled = false;
  scene.add(lanes);

  const palette = { ink: new THREE.Color(), dropped: new THREE.Color(), accent: new THREE.Color() };
  let dirty = true;
  const refreshColors = () => {
    palette.ink.copy(tokenColor("--ink-secondary"));
    palette.dropped.copy(tokenColor("--data-3"));
    palette.accent.copy(tokenColor("--accent"));
    fog.color.copy(tokenColor("--canvas"));
    gateMaterial.color.copy(tokenColor("--ink-muted"));
    edgeMaterial.color.copy(tokenColor("--border"));
    laneMaterial.color.copy(tokenColor("--divider"));
    dirty = true;
  };

  const dummy = new THREE.Object3D();
  const color = new THREE.Color();
  const eye = new THREE.Vector3();
  const target = new THREE.Vector3();
  const projected = new THREE.Vector3();
  const anchor = new THREE.Vector3();
  const bar: BarState = { x: 0, z: 0, height: 0, tint: 0 };
  const state = { p: options.still ? 1 : 0, goal: options.still ? 1 : 0, pointerX: 0, pointerY: 0, lookX: 0, lookY: 0 };
  let running = true;
  let disposed = false;
  let last = { calls: 0, triangles: 0 };
  /** 등장이 시작된 시각(ms). null이면 등장이 없거나 끝났다. */
  let introStart: number | null = null;
  const finals = items.filter((item) => item.slot >= 0).sort((a, b) => a.slot - b.slot);
  const planState: BarState = { x: 0, z: 0, height: 0, tint: 0 };

  const layout = (p: number) => {
    const elapsed = introStart === null ? null : performance.now() - introStart;
    if (elapsed !== null && elapsed >= INTRO.duration + INTRO.spread) introStart = null;
    for (let i = 0; i < count; i += 1) {
      barAt(items[i], p, bar);
      const rise = elapsed === null ? 1 : introScale(items[i], elapsed);
      dummy.position.set(bar.x, 0, bar.z);
      dummy.scale.set(1, Math.max(0.001, bar.height * rise), 1);
      dummy.updateMatrix();
      bars.setMatrixAt(i, dummy.matrix);
      color.copy(palette.ink);
      if (bar.tint < 0) color.lerp(palette.dropped, -bar.tint);
      else if (bar.tint > 0) color.lerp(palette.accent, bar.tint);
      bars.setColorAt(i, color);
    }
    bars.instanceMatrix.needsUpdate = true;
    if (bars.instanceColor) bars.instanceColor.needsUpdate = true;
  };

  const draw = () => {
    const p = state.p;
    layout(p);
    if (options.still) {
      const view = CAMERA.overview(camera.aspect);
      camera.position.set(...view.eye);
      target.set(...view.target);
    } else {
      path.getPoint(p, eye);
      lookPath.getPoint(p, target);
      camera.position.lerpVectors(target, eye, CAMERA.pullBack(camera.aspect));
      camera.position.x += state.lookX * 0.9;
      camera.position.y += state.lookY * 0.5;
    }
    camera.lookAt(target);
    renderer.render(scene, camera);
    last = { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles };
    if (canvas.dataset.calls !== String(last.calls)) {
      // 검증 기록용: 한 프레임의 드로우콜·삼각형 수를 요소에 적어 둔다
      canvas.dataset.calls = String(last.calls);
      canvas.dataset.triangles = String(last.triangles);
    }

    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const place = (shown: boolean): Anchor => {
      const distance = camera.position.distanceTo(anchor);
      projected.copy(anchor).project(camera);
      const inFrame = projected.z > -1 && projected.z < 1 && Math.abs(projected.x) < 0.86 && projected.y < 0.86 && projected.y > -0.7;
      return { x: (projected.x * 0.5 + 0.5) * width, y: (-projected.y * 0.5 + 0.5) * height, distance, visible: shown && inFrame && distance > 6 };
    };
    options.onAnchors(
      FIELD.gateZ.map((z) => {
        anchor.set(labelX(options.still), FIELD.gateHeight, z);
        return place(options.still || camera.position.distanceTo(anchor) < 36);
      }),
      // 주문 계획 이름표: 기둥이 제자리에 서서 계획 색이 된 뒤에만, 기둥 꼭대기에 붙인다
      finals.map((item) => {
        barAt(item, p, planState);
        anchor.set(planState.x, planState.height, planState.z);
        return place(!options.still && planState.tint > 0.95);
      }),
    );
  };

  const resize = () => {
    const width = canvas.clientWidth || 1;
    const height = canvas.clientHeight || 1;
    renderer.setPixelRatio(dpr());
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.fov = CAMERA.fov(camera.aspect);
    camera.updateProjectionMatrix();
    dirty = true;
  };

  const clock = new THREE.Clock();
  const frame = () => {
    const dt = Math.min(clock.getDelta(), 0.1);
    const follow = 1 - Math.pow(0.0015, dt); // 스크롤을 감쇠해서 따라간다
    state.p += (state.goal - state.p) * follow;
    state.lookX += (state.pointerX - state.lookX) * follow;
    state.lookY += (state.pointerY - state.lookY) * follow;
    const moving = Math.abs(state.goal - state.p) > 0.0002 || Math.abs(state.pointerX - state.lookX) > 0.0005 || Math.abs(state.pointerY - state.lookY) > 0.0005;
    if (moving || dirty || introStart !== null) {
      dirty = false;
      draw();
    }
  };

  const start = () => {
    if (disposed) return;
    if (options.still) {
      // 모션 줄이기: 루프 없이 한 장만. 크기·테마가 바뀔 때만 다시 그린다.
      draw();
      return;
    }
    clock.getDelta();
    renderer.setAnimationLoop(running && !document.hidden ? frame : null);
  };

  const onPointer = (event: PointerEvent) => {
    if (options.still || event.pointerType === "touch") return;
    state.pointerX = (event.clientX / window.innerWidth - 0.5) * 0.35;
    state.pointerY = (0.5 - event.clientY / window.innerHeight) * 0.35;
  };
  const onVisibility = () => start();
  const observer = new ResizeObserver(() => {
    resize();
    if (options.still && !disposed) draw();
  });

  refreshColors();
  resize();
  observer.observe(canvas);
  window.addEventListener("pointermove", onPointer, { passive: true });
  document.addEventListener("visibilitychange", onVisibility);

  layout(state.p);
  await renderer.compileAsync(scene, camera);
  if (!disposed) {
    if (options.intro && !options.still) introStart = performance.now();
    draw();
    start();
  }

  return {
    setProgress(progress) {
      if (options.still) return;
      state.goal = Math.min(1, Math.max(0, progress));
    },
    setRunning(next) {
      running = next;
      start();
    },
    refreshColors() {
      refreshColors();
      if (options.still) draw();
    },
    stats: () => last,
    dispose() {
      disposed = true;
      renderer.setAnimationLoop(null);
      observer.disconnect();
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("visibilitychange", onVisibility);
      geometry.dispose();
      material.dispose();
      mirrorGeometry.dispose();
      mirrorMaterial.dispose();
      gateGeometry.dispose();
      gateMaterial.dispose();
      edgeGeometry.dispose();
      edgeMaterial.dispose();
      laneGeometry.dispose();
      laneMaterial.dispose();
      environment.dispose();
      pmrem.dispose();
      renderer.dispose();
    },
  };
}
