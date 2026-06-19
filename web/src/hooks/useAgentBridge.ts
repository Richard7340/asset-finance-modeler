import { useEffect } from "react";
import type { OverrideValue } from "../api";

// ---------------------------------------------------------------------------
// Agent bridge (parent → iframe). The webOS Portfolio app embeds this React UI
// in a same-origin iframe (/finance-ui/?embed=1). The agent operates the LIVE
// controls of the platform by posting commands to this iframe; we apply them to
// React state (which re-simulates by construction via useRun) and HIGHLIGHT the
// touched input so the user SEES the agent act.
//
// Protocol (parent → iframe):
//   { type: 'portfolio:cmd', cmd: 'set_input',  path, value }
//   { type: 'portfolio:cmd', cmd: 'run' }
//   { type: 'portfolio:cmd', cmd: 'navigate',   section }
//   { type: 'portfolio:cmd', cmd: 'select_asset', assetId }
//   { type: 'portfolio:cmd', cmd: 'refresh' }
//
// Result (iframe → parent):
//   { type: 'portfolio:cmd-result', cmd, ok, ...extra }
//
// SECURITY: we only accept messages whose source window is our PARENT
// (ev.source === window.parent) and whose origin matches the parent's origin
// (same-origin embed). Messages from any other window/origin are ignored. When
// not embedded (window.parent === window) the hook is a safe no-op: it never
// registers a listener.
// ---------------------------------------------------------------------------

export type AgentCmd =
  | { type: "portfolio:cmd"; cmd: "set_input"; path: string; value: OverrideValue }
  | { type: "portfolio:cmd"; cmd: "run" }
  | { type: "portfolio:cmd"; cmd: "navigate"; section: string }
  | { type: "portfolio:cmd"; cmd: "select_asset"; assetId: string }
  | { type: "portfolio:cmd"; cmd: "refresh" };

export type AgentBridgeHandlers = {
  /** Apply a single override (numeric/string/bool/points) and re-simulate. */
  setInput: (path: string, value: OverrideValue) => void;
  /** Force a re-run of the current scenario. */
  run: () => void;
  /** Navigate to a primary section/page. */
  navigate: (section: string) => void;
  /** Select an asset by id (fetches + opens its detail). Async. */
  selectAsset: (assetId: string) => Promise<void> | void;
  /** Reload the embedded data (re-fetch from backend). */
  refresh: () => void;
};

/** True when this document is embedded in a distinct parent window. */
export function isEmbeddedInParent(): boolean {
  return typeof window !== "undefined" && window.parent !== window;
}

/**
 * Highlight the input bound to `path` with a temporary glow ring. The element
 * must carry `data-agent-id="asset.<path>"`. Safe no-op if not found. Scrolls
 * the element into view so the user sees the agent's action even off-screen.
 */
export function spotlightInput(path: string, durationMs = 2400): void {
  if (typeof document === "undefined") return;
  const sel = `[data-agent-id="asset.${cssEscape(path)}"]`;
  let el: HTMLElement | null = null;
  try {
    el = document.querySelector(sel) as HTMLElement | null;
  } catch {
    el = null;
  }
  if (!el) return;
  try {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch {
    /* older browsers: ignore */
  }
  el.classList.add("agent-spotlight");
  window.setTimeout(() => el?.classList.remove("agent-spotlight"), durationMs);
}

/** Minimal CSS.escape fallback for attribute-selector values. */
function cssEscape(s: string): string {
  const anyCss = (globalThis as { CSS?: { escape?: (v: string) => string } }).CSS;
  if (anyCss?.escape) return anyCss.escape(s);
  return s.replace(/["\\\]]/g, "\\$&");
}

/** Post a command result back to the parent (best-effort). */
function postResult(parentOrigin: string, payload: Record<string, unknown>): void {
  try {
    window.parent.postMessage(
      { type: "portfolio:cmd-result", ...payload },
      parentOrigin || "*",
    );
  } catch {
    /* cross-origin or unavailable parent — ignore */
  }
}

/**
 * Register the parent→iframe command listener. No-op when not embedded.
 * Handlers are read through a ref-like closure so the latest state setters are
 * always used (the hook re-subscribes when handlers identity changes).
 */
export function useAgentBridge(handlers: AgentBridgeHandlers): void {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!isEmbeddedInParent()) return; // not embedded → safe no-op

    function onMessage(ev: MessageEvent) {
      // SECURITY: only accept commands from our parent window…
      if (ev.source !== window.parent) return;
      // …and only from the parent's own origin (same-origin embed). When the
      // parent's origin is unknown ("null", e.g. sandboxed), reject.
      const parentOrigin = ev.origin;
      if (!parentOrigin || parentOrigin === "null") return;
      if (parentOrigin !== window.location.origin) return;

      const data = ev.data as Partial<AgentCmd> | undefined;
      if (!data || data.type !== "portfolio:cmd" || typeof data.cmd !== "string") {
        return;
      }

      const cmd = data.cmd;
      try {
        if (cmd === "set_input") {
          const path = (data as { path?: unknown }).path;
          const value = (data as { value?: unknown }).value;
          if (typeof path !== "string" || !isOverrideValue(value)) {
            postResult(parentOrigin, { cmd, ok: false, error: "invalid_args" });
            return;
          }
          handlers.setInput(path, value);
          // Highlight on the next frame, after React commits the new value.
          window.setTimeout(() => spotlightInput(path), 0);
          postResult(parentOrigin, { cmd, ok: true, path, value });
        } else if (cmd === "run") {
          handlers.run();
          postResult(parentOrigin, { cmd, ok: true });
        } else if (cmd === "navigate") {
          const section = (data as { section?: unknown }).section;
          if (typeof section !== "string") {
            postResult(parentOrigin, { cmd, ok: false, error: "invalid_args" });
            return;
          }
          handlers.navigate(section);
          postResult(parentOrigin, { cmd, ok: true, section });
        } else if (cmd === "select_asset") {
          const assetId = (data as { assetId?: unknown }).assetId;
          if (typeof assetId !== "string") {
            postResult(parentOrigin, { cmd, ok: false, error: "invalid_args" });
            return;
          }
          Promise.resolve(handlers.selectAsset(assetId))
            .then(() => postResult(parentOrigin, { cmd, ok: true, assetId }))
            .catch((e: unknown) =>
              postResult(parentOrigin, { cmd, ok: false, error: String(e) }),
            );
        } else if (cmd === "refresh") {
          handlers.refresh();
          postResult(parentOrigin, { cmd, ok: true });
        } else {
          postResult(parentOrigin, { cmd, ok: false, error: "unknown_cmd" });
        }
      } catch (e) {
        postResult(parentOrigin, { cmd, ok: false, error: String(e) });
      }
    }

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [handlers]);
}

function isOverrideValue(v: unknown): v is OverrideValue {
  if (typeof v === "number" || typeof v === "string" || typeof v === "boolean") {
    return true;
  }
  return Array.isArray(v) && v.every((x) => typeof x === "number");
}
