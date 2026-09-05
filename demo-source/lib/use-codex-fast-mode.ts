"use client";

import { useSyncExternalStore } from "react";

const KEY = "plp-codex-fast-mode";
const EVENT = "plp-codex-fast-mode-change";
let fallback = false;

function snapshot() {
  try { return localStorage.getItem(KEY) === "true"; } catch { return fallback; }
}

function subscribe(notify: () => void) {
  window.addEventListener("storage", notify);
  window.addEventListener(EVENT, notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener(EVENT, notify);
  };
}

function setFastMode(enabled: boolean) {
  fallback = enabled;
  try { localStorage.setItem(KEY, String(enabled)); } catch { /* Keep the session usable. */ }
  window.dispatchEvent(new Event(EVENT));
}

export function useCodexFastMode() {
  const enabled = useSyncExternalStore(subscribe, snapshot, () => false);
  return [enabled, setFastMode] as const;
}
