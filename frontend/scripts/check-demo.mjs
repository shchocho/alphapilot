// 공개 데모 빌드(dist-demo) 배포 안전 점검. `npm run build:demo` 끝에 돌고, 걸리면 종료 코드 1로 멈춘다.
// 평일 자동 배포(.github/workflows/demo.yml)도 같은 명령을 쓰므로, 걸린 빌드는 사이트에 올라가지 않는다.
// 기준은 저장소 CLAUDE.md의 "배포 안전 기준(피싱 오탐 방지)". 묶인 JS에서는 속성이 type:"password"처럼 적히므로 두 모양을 다 본다.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../dist-demo", import.meta.url));
const TEXT = new Set([".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt", ".webmanifest"]);

// 하나라도 있으면 안 되는 것
const FORBIDDEN = [
  ["비밀번호 입력칸", /type\s*[:=]\s*["'`]password["'`]/gi],
  ["비밀번호 자동완성", /(current|new)-password/gi],
  ["아이디 자동완성", /autocomplete\s*[:=]\s*["'`]username["'`]/gi],
  ["'비밀번호' 문구", /비밀번호/g],
  ["'복구 코드' 문구", /복구 코드/g],
  ["'시크릿키' 문구", /시크릿키/g],
  ["카카오톡·카카오 로그인", /카카오톡|카카오 ?로그인|kakao/gi],
  ["숨긴 코드(eval)", /\beval\(/g],
  ["숨긴 코드(new Function)", /new Function\b/g],
  ["숨긴 코드(atob)", /\batob\(/g],
  ["자동 이동(meta refresh)", /http-equiv\s*=\s*["']refresh["']/gi],
];
// 뜻이 무해한 쓰임이 있어 개수 상한만 두는 것(늘어나면 무엇이 늘었는지 보고 상한을 고친다)
const BUDGET = [
  ["'로그인' 문구", /로그인/g, 1], // 사이드바의 '로그아웃' 옆 안내 한 곳
  ["'인증 코드' 문구", /인증 코드/g, 3], // 설정 안내문("인증 코드를 한 번 더 묻습니다")
  ["secret", /secret/gi, 1], // 설정 응답의 키 이름(값 없음)
  ["api key", /api.?key/gi, 3], // AI 설정 안내문의 환경변수 이름
];
// 실행 파일은 파일 자체가 없어야 한다(시세 데이터 속 '.exe' 글자는 종목·주소 문자열이라 세지 않는다)
const BAD_FILES = /\.(exe|msi|apk|dmg|scr|bat|cmd|ps1)$/i;

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* walk(path);
    else yield path;
  }
}

const hits = new Map();
const count = (label, file, n) => {
  if (!n) return;
  const entry = hits.get(label) ?? { total: 0, files: [] };
  entry.total += n;
  entry.files.push(`${relative(root, file).replaceAll("\\", "/")}(${n})`);
  hits.set(label, entry);
};

let files = 0;
const problems = [];
for (const file of walk(root)) {
  files += 1;
  if (BAD_FILES.test(file)) problems.push(`실행 파일: ${relative(root, file)}`);
  if (!TEXT.has(extname(file).toLowerCase())) continue;
  const text = readFileSync(file, "utf8");
  for (const [label, pattern] of [...FORBIDDEN, ...BUDGET]) count(label, file, (text.match(pattern) ?? []).length);
}

for (const [label] of FORBIDDEN) {
  const entry = hits.get(label);
  if (entry) problems.push(`${label}: ${entry.total}건 — ${entry.files.slice(0, 5).join(", ")}`);
}
for (const [label, , max] of BUDGET) {
  const entry = hits.get(label);
  if (entry && entry.total > max) problems.push(`${label}: ${entry.total}건(상한 ${max}) — ${entry.files.slice(0, 5).join(", ")}`);
}

if (problems.length > 0) {
  console.error(`\n공개 데모 배포 안전 점검 실패 (${problems.length}가지). 이 빌드는 올리지 않는다.`);
  for (const line of problems) console.error(`  - ${line}`);
  console.error("고치는 법: 그 화면 부품을 vite.config.ts의 DEMO_STUBS에 넣어 데모 빌드에서 빠지게 한다(CLAUDE.md 배포 안전 기준).\n");
  process.exit(1);
}
const budget = BUDGET.map(([label, , max]) => `${label} ${hits.get(label)?.total ?? 0}/${max}`).join(" · ");
console.log(`공개 데모 배포 안전 점검 통과: 파일 ${files}개, 금지 항목 0건 (${budget})`);
