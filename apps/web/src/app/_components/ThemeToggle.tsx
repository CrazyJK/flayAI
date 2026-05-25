"use client";

import { useEffect, useSyncExternalStore } from "react";

type Theme = "system" | "light" | "dark";
const STORAGE_KEY = "flayai-theme";
// 클릭 순회 순서: 시스템 → 라이트 → 다크 → 시스템 …
const ORDER: Theme[] = ["system", "light", "dark"];

// 선택 테마를 실제 <html>.dark / color-scheme 에 반영
function applyTheme(t: Theme) {
  const dark =
    t === "dark" || (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const el = document.documentElement;
  el.classList.toggle("dark", dark);
  el.style.colorScheme = dark ? "dark" : "light";
}

// localStorage 기반 초소형 외부 스토어 — 탭 간(storage 이벤트) + 같은 탭(수동 통지) 동기화
const listeners = new Set<() => void>();
function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}
function getSnapshot(): Theme {
  const t = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
  return t && ORDER.includes(t) ? t : "system";
}
function getServerSnapshot(): Theme {
  return "system";
}
function setStoredTheme(t: Theme) {
  window.localStorage.setItem(STORAGE_KEY, t);
  applyTheme(t);
  listeners.forEach((l) => l());
}

const LABEL: Record<Theme, string> = { system: "시스템", light: "라이트", dark: "다크" };

function ThemeIcon({ theme }: { theme: Theme }) {
  const common = {
    width: 14,
    height: 14,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  if (theme === "light") {
    // 해
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
      </svg>
    );
  }
  if (theme === "dark") {
    // 달
    return (
      <svg {...common}>
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    );
  }
  // 모니터 (시스템)
  return (
    <svg {...common}>
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}

/** 헤더용 테마 순회 버튼 — 시스템/라이트/다크를 한 번 클릭마다 순환 선택. */
export default function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  // 시스템 모드일 때만 OS 다크/라이트 변경을 실시간 추종 (state 변경 없이 클래스만 재적용)
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const cycle = () => {
    setStoredTheme(ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]);
  };

  return (
    <button
      type="button"
      onClick={cycle}
      title={`테마: ${LABEL[theme]} (클릭하여 전환)`}
      aria-label={`테마: ${LABEL[theme]}`}
      className="flex items-center gap-1 rounded-md border border-neutral-300 dark:border-neutral-700 px-2 py-1 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800"
    >
      <ThemeIcon theme={theme} />
      <span>{LABEL[theme]}</span>
    </button>
  );
}
