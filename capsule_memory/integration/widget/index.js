/**
 * index.js — Main entry point for the CapsuleMemory Web Widget.
 *
 * Embeddable via a single script tag:
 *   <script src="widget.js"
 *           data-user-id="user123"
 *           data-api="http://localhost:8000"
 *           data-theme="auto">
 *   </script>
 *
 * Reads configuration from data-* attributes on its own <script> tag,
 * initializes the capsule list panel and skill trigger notifier,
 * and starts polling for pending triggers every 5 seconds.
 */

import cssText from "./styles.css";
import { createPanel, togglePanel } from "./panel.js";
import { initNotifier, showNotification } from "./notifier.js";

/** Set of event IDs already shown, prevents duplicate notifications. */
const shownEventIds = new Set();

/** Polling interval handle, for cleanup. */
let pollTimer = null;

/** Polling interval in milliseconds. */
const POLL_INTERVAL_MS = 5000;

/**
 * Boot the widget. Automatically invoked on script load.
 */
function init() {
  // ── Locate our own <script> tag to read data-* attributes
  const scriptEl = document.currentScript || findOwnScript();
  if (!scriptEl) {
    console.error("[CapsuleMemory Widget] Cannot locate own <script> element.");
    return;
  }

  const userId = scriptEl.getAttribute("data-user-id") || "default";
  const api = (scriptEl.getAttribute("data-api") || "http://localhost:8000").replace(
    /\/$/,
    ""
  );
  const theme = scriptEl.getAttribute("data-theme") || "auto";

  // ── Create the widget root container
  const root = document.createElement("div");
  root.className = "cm-widget";
  root.setAttribute("data-theme", theme);
  document.body.appendChild(root);

  // ── Inject styles into a <style> element inside the root
  const styleEl = document.createElement("style");
  styleEl.textContent = cssText;
  root.appendChild(styleEl);

  // ── Create the floating toggle button
  const toggleBtn = document.createElement("button");
  toggleBtn.className = "cm-toggle-btn";
  toggleBtn.title = "Capsule Memory";
  toggleBtn.innerHTML = buildCapsuleIcon();
  toggleBtn.addEventListener("click", () => togglePanel());
  root.appendChild(toggleBtn);

  // ── Initialize panel and notifier
  createPanel(root, api, userId);
  initNotifier(root, api);

  // ── Start polling for pending triggers
  startPolling(api, userId);
}

/**
 * Fallback: find the <script> tag by scanning all scripts for one whose src
 * contains "widget.js" (covers bundled / renamed scenarios).
 *
 * @returns {HTMLScriptElement|null}
 */
function findOwnScript() {
  const scripts = document.querySelectorAll("script[src]");
  for (const s of scripts) {
    if (s.src && s.src.includes("widget")) {
      return s;
    }
  }
  return null;
}

/**
 * Start polling the pending-triggers endpoint.
 *
 * @param {string} api     Base API URL.
 * @param {string} userId  Current user ID.
 */
function startPolling(api, userId) {
  // Run once immediately, then set up the interval
  pollPendingTriggers(api, userId);
  pollTimer = setInterval(() => pollPendingTriggers(api, userId), POLL_INTERVAL_MS);
}

/**
 * Poll GET /api/v1/capsules/pending-triggers?user_id={userId}
 * and show notifications for any new (not-yet-shown) trigger events.
 *
 * Errors are silently swallowed to avoid noisy console spam from
 * transient network issues or when the API server is not running.
 *
 * Response format (Patch #4):
 *   {
 *     "triggers": [
 *       {
 *         "event_id": "...",
 *         "session_id": "...",
 *         "trigger_rule": "...",
 *         "skill_draft": {
 *           "suggested_name": "...",
 *           "confidence": 0.85,
 *           "preview": "...",
 *           "trigger_rule": "..."
 *         }
 *       }
 *     ],
 *     "count": 1
 *   }
 *
 * @param {string} api     Base API URL.
 * @param {string} userId  Current user ID.
 */
async function pollPendingTriggers(api, userId) {
  try {
    const url = `${api}/api/v1/capsules/pending-triggers?user_id=${encodeURIComponent(userId)}`;
    const resp = await fetch(url);

    if (!resp.ok) return; // Silently ignore non-2xx responses

    const data = await resp.json();

    if (!data || !Array.isArray(data.triggers)) return;

    for (const trigger of data.triggers) {
      if (!trigger.event_id) continue;

      // Skip already-shown events to prevent duplicate notifications
      if (shownEventIds.has(trigger.event_id)) continue;

      shownEventIds.add(trigger.event_id);
      showNotification(trigger);
    }
  } catch {
    // Silently swallow errors — the server may not be running,
    // the network may be temporarily unavailable, etc.
  }
}

/**
 * Build an SVG icon for the toggle button (capsule / memory vault motif).
 * Returns an SVG string.
 *
 * @returns {string}
 */
function buildCapsuleIcon() {
  return `<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="4" ry="4"/>
    <line x1="3" y1="12" x2="21" y2="12"/>
    <circle cx="12" cy="7.5" r="1.5" fill="currentColor" stroke="none"/>
    <circle cx="12" cy="16.5" r="1.5" fill="currentColor" stroke="none"/>
  </svg>`;
}

// ── Auto-initialize when the DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// ── Public API (exposed on the global CapsuleMemoryWidget object by esbuild IIFE)
export { togglePanel } from "./panel.js";
export { showNotification } from "./notifier.js";

/**
 * Stop polling and remove the widget from the DOM.
 */
export function destroy() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  shownEventIds.clear();
  const root = document.querySelector(".cm-widget");
  if (root) root.remove();
}
