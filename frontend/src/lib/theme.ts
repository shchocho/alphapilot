/** 밝은·어두운 화면. 기본은 어두운 화면(2026-11-21 다크 트레이딩 콘솔 개편)이고, 고르면 그 브라우저에만 기억한다.
 *  '기기 설정'을 고르면 기기의 밝기 설정을 따른다. <html>에는 항상 data-theme을 직접 적는다. */

import { useEffect, useState } from "react";

export type ThemeChoice = "system" | "light" | "dark";
const KEY = "ap-theme";
const EVENT = "ap-theme-change";
const DEFAULT: ThemeChoice = "dark";

export function getTheme(): ThemeChoice {
  try {
    const saved = window.localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    /* 저장소를 못 쓰는 환경에서는 기본(어두운 화면)을 쓴다 */
  }
  return DEFAULT;
}

/** 지금 실제로 적용되는 테마. */
export function resolvedTheme(choice: ThemeChoice = getTheme()): "light" | "dark" {
  if (choice !== "system") return choice;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function paint(choice: ThemeChoice): void {
  const theme = resolvedTheme(choice);
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
}

export function applyTheme(choice: ThemeChoice): void {
  paint(choice);
  try {
    if (choice === DEFAULT) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, choice);
  } catch {
    /* 기억하지 못해도 이번 화면에는 적용된다 */
  }
  window.dispatchEvent(new Event(EVENT));
}

/** 앱을 켤 때 한 번 부른다. '기기 설정'을 고른 경우에만 기기 설정이 바뀔 때 따라 바뀐다. */
export function watchSystemTheme(): void {
  paint(getTheme());
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (getTheme() === "system") {
      paint("system");
      window.dispatchEvent(new Event(EVENT));
    }
  });
}

/** 테마가 바뀔 때마다 값이 바뀐다. 캔버스 차트처럼 색을 직접 읽는 컴포넌트가 다시 그리는 데 쓴다. */
export function useThemeVersion(): number {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const bump = () => setVersion((v) => v + 1);
    window.addEventListener(EVENT, bump);
    return () => window.removeEventListener(EVENT, bump);
  }, []);
  return version;
}

export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(getTheme);
  return [
    choice,
    (next) => {
      setChoice(next);
      applyTheme(next);
    },
  ];
}

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
