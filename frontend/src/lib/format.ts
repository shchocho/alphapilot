/** 숫자·날짜 표기. 화면의 모든 숫자는 이 파일을 거친다(한국 관례). */

const WON = new Intl.NumberFormat("ko-KR");

/** 12345678 → "12,345,678" */
export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return digits > 0
    ? new Intl.NumberFormat("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)
    : WON.format(Math.round(value));
}

/** 12345678 → "12,345,678원" */
export function won(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return `${WON.format(Math.round(value))}원`;
}

/** 큰 금액을 억·조로 줄인다. 1_234_000_000 → "12.3억 원", 2_500_000_000_000 → "2.5조 원" */
export function wonShort(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1e12) return `${sign}${trim(abs / 1e12)}조 원`;
  if (abs >= 1e8) return `${sign}${trim(abs / 1e8)}억 원`;
  if (abs >= 1e4) return `${sign}${WON.format(Math.round(abs / 1e4))}만 원`;
  return `${sign}${WON.format(Math.round(abs))}원`;
}

/**
 * 축 눈금용 금액: 억·만으로 줄여 쓰되 반올림하지 않는다. 줄여서 정확히 적을 수 없으면 원 단위로 다 적는다.
 * 27_500_000 → "2,750만 원", 120_000_000 → "1.2억 원", 25_000 → "2.5만 원", 12_345 → "12,345원"
 */
export function wonExact(value: number): string {
  const abs = Math.abs(Math.round(value));
  if (abs === 0) return "0";
  const sign = value < 0 ? "−" : "";
  if (abs >= 1e8) {
    if (abs % 1e7 === 0) return `${sign}${abs / 1e8}억 원`;
    if (abs % 1e4 === 0) return `${sign}${Math.floor(abs / 1e8)}억 ${WON.format((abs % 1e8) / 1e4)}만 원`;
  } else if (abs >= 1e4) {
    if (abs % 1e4 === 0) return `${sign}${WON.format(abs / 1e4)}만 원`;
    if (abs % 1e3 === 0) return `${sign}${(abs / 1e4).toFixed(1)}만 원`;
  }
  return `${sign}${WON.format(abs)}원`;
}

/** 약 71만원처럼 어림한 금액(승인 버튼용) */
export function wonAbout(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e8) return `약 ${trim(abs / 1e8)}억 원`;
  if (abs >= 1e4) return `약 ${WON.format(Math.round(abs / 1e4))}만 원`;
  return `약 ${WON.format(Math.round(abs))}원`;
}

function trim(x: number): string {
  return x >= 100 ? WON.format(Math.round(x)) : x.toFixed(1).replace(/\.0$/, "");
}

/** 0.0123 → "+1.23%" (부호 포함, 음수는 − 기호) */
export function pct(value: number | null | undefined, digits = 2, signed = true): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const v = value * 100;
  const body = Math.abs(v).toFixed(digits);
  if (!signed) return `${body}%`;
  if (v > 0) return `+${body}%`;
  if (v < 0) return `−${body}%`;
  return `${body}%`;
}

/** 부호 있는 금액: +12,300원 / −4,500원 */
export function wonSigned(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const body = `${WON.format(Math.abs(Math.round(value)))}원`;
  if (value > 0) return `+${body}`;
  if (value < 0) return `−${body}`;
  return body;
}

export type Direction = "up" | "down" | "flat";

export function direction(value: number | null | undefined): Direction {
  if (!value) return "flat";
  return value > 0 ? "up" : "down";
}

/** ▲ ▼ – : 색을 못 봐도 방향을 읽을 수 있게 한다 */
export function arrow(value: number | null | undefined): string {
  const d = direction(value);
  return d === "up" ? "▲" : d === "down" ? "▼" : "–";
}

/** "2026-11-13" → "11월 13일" */
export function dayLabel(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${Number(m)}월 ${Number(d)}일`;
}

/** "2026-11-13" → "2026.11.13" */
export function dayDots(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10).replaceAll("-", ".") : "–";
}

/** ISO 시각 → "10:31" */
export function clock(iso: string | null | undefined): string {
  if (!iso || iso.length < 16) return "";
  return iso.slice(11, 16);
}

/** 초 → "4시간 48분" / "12분" */
export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "";
  const m = Math.max(0, Math.round(seconds / 60));
  const h = Math.floor(m / 60);
  return h > 0 ? `${h}시간 ${m % 60}분` : `${m}분`;
}

/** 거래번호: 0157 */
export function seqLabel(seq: number): string {
  return String(seq).padStart(4, "0");
}

/** "2026-11-13" → "11.13" (표 안의 짧은 날짜) */
export function dayShort(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${m}.${d}`;
}

/** 확신 등급·기법 상태처럼 서버가 준 영문 키를 화면 말로 바꾼다. 모르는 키는 그대로 보여준다. */
export function labelOf(map: Record<string, string>, key: string | null | undefined, fallback = "–"): string {
  if (!key) return fallback;
  return map[key] ?? key;
}
