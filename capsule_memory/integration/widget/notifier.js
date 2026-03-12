/**
 * notifier.js — Skill trigger notification panel for the CapsuleMemory Widget.
 *
 * Renders a bottom-right floating notification panel for each pending skill trigger.
 * Each notification shows the suggested skill name, confidence score, preview,
 * and action buttons (confirm / dismiss).
 */

/** @type {HTMLElement|null} */
let containerEl = null;

/** @type {string} */
let _api = "";

/**
 * Initialize the notifier — creates the fixed-position notification container.
 *
 * @param {HTMLElement} root  The widget root container.
 * @param {string}      api   Base API URL.
 */
export function initNotifier(root, api) {
  _api = api;

  containerEl = document.createElement("div");
  containerEl.className = "cm-notify-container";
  root.appendChild(containerEl);
}

/**
 * Show a notification for a skill trigger event.
 * If a notification for the same event_id already exists, it is skipped.
 *
 * @param {Object} trigger  Trigger data from the pending-triggers endpoint.
 *   Expected shape:
 *   {
 *     event_id: string,
 *     session_id: string,
 *     trigger_rule: string,
 *     skill_draft: {
 *       suggested_name: string,
 *       confidence: number,
 *       preview: string,
 *       trigger_rule: string,
 *     }
 *   }
 */
export function showNotification(trigger) {
  if (!containerEl) return;

  const { event_id, session_id, trigger_rule, skill_draft } = trigger;
  const { suggested_name, confidence, preview } = skill_draft;

  // ── Notification card
  const notifyEl = document.createElement("div");
  notifyEl.className = "cm-notify";
  notifyEl.dataset.eventId = event_id;

  // ── Header row
  const headerEl = document.createElement("div");
  headerEl.className = "cm-notify-header";

  const titleEl = document.createElement("div");
  titleEl.className = "cm-notify-title";
  titleEl.textContent = "Skill Detected";

  const closeBtnEl = document.createElement("button");
  closeBtnEl.className = "cm-notify-close";
  closeBtnEl.innerHTML = "&times;";
  closeBtnEl.title = "Dismiss";
  closeBtnEl.addEventListener("click", () => dismissNotification(notifyEl));

  headerEl.appendChild(titleEl);
  headerEl.appendChild(closeBtnEl);

  // ── Body
  const bodyEl = document.createElement("div");
  bodyEl.className = "cm-notify-body";

  // Skill name + confidence badge
  const nameSpan = document.createElement("span");
  nameSpan.className = "cm-notify-skill-name";
  nameSpan.textContent = suggested_name;

  const confBadge = document.createElement("span");
  const confLevel =
    confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low";
  confBadge.className = `cm-notify-confidence cm-notify-confidence--${confLevel}`;
  confBadge.textContent = `${Math.round(confidence * 100)}%`;

  bodyEl.appendChild(nameSpan);
  bodyEl.appendChild(confBadge);

  // Trigger rule display
  const ruleEl = document.createElement("div");
  ruleEl.style.cssText =
    "font-size: 11px; margin-top: 4px; opacity: 0.7;";
  ruleEl.textContent = `Trigger: ${trigger_rule}`;
  bodyEl.appendChild(ruleEl);

  // Preview block
  let previewEl = null;
  if (preview) {
    previewEl = document.createElement("div");
    previewEl.className = "cm-notify-preview";
    previewEl.textContent =
      preview.length > 300 ? preview.substring(0, 300) + "..." : preview;
  }

  // ── Action buttons
  const actionsEl = document.createElement("div");
  actionsEl.className = "cm-notify-actions";

  const ignoreBtn = document.createElement("button");
  ignoreBtn.className = "cm-btn cm-btn--sm";
  ignoreBtn.textContent = "Ignore";
  ignoreBtn.addEventListener("click", () =>
    handleConfirm(session_id, event_id, "ignore", notifyEl)
  );

  const extractBtn = document.createElement("button");
  extractBtn.className = "cm-btn cm-btn--sm cm-btn--primary";
  extractBtn.textContent = "Extract Skill";
  extractBtn.addEventListener("click", () =>
    handleConfirm(session_id, event_id, "extract_skill", notifyEl)
  );

  actionsEl.appendChild(ignoreBtn);
  actionsEl.appendChild(extractBtn);

  // ── Assemble
  notifyEl.appendChild(headerEl);
  notifyEl.appendChild(bodyEl);
  if (previewEl) notifyEl.appendChild(previewEl);
  notifyEl.appendChild(actionsEl);

  containerEl.appendChild(notifyEl);
}

/**
 * Dismiss a notification with animation.
 *
 * @param {HTMLElement} notifyEl  The notification element to dismiss.
 */
function dismissNotification(notifyEl) {
  notifyEl.classList.add("cm-notify--dismissed");
  notifyEl.addEventListener("animationend", () => notifyEl.remove(), {
    once: true,
  });
}

/**
 * Send confirmation to the API and remove the notification.
 *
 * @param {string}      sessionId   Session ID.
 * @param {string}      eventId     Trigger event ID.
 * @param {string}      resolution  Resolution type (extract_skill, ignore, etc.).
 * @param {HTMLElement}  notifyEl    The notification element.
 */
async function handleConfirm(sessionId, eventId, resolution, notifyEl) {
  // Disable buttons during the request
  const buttons = notifyEl.querySelectorAll("button");
  buttons.forEach((btn) => {
    btn.disabled = true;
  });

  try {
    const url = `${_api}/api/v1/sessions/${encodeURIComponent(sessionId)}/triggers/${encodeURIComponent(eventId)}/confirm`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolution }),
    });

    if (!resp.ok) {
      const errBody = await resp.text();
      let detail;
      try {
        detail = JSON.parse(errBody).detail;
      } catch {
        detail = errBody;
      }
      throw new Error(detail || `HTTP ${resp.status}`);
    }

    // Successfully confirmed — dismiss the notification
    dismissNotification(notifyEl);
  } catch (err) {
    // Re-enable buttons on error
    buttons.forEach((btn) => {
      btn.disabled = false;
    });

    // Show inline error
    let existingError = notifyEl.querySelector(".cm-error");
    if (!existingError) {
      existingError = document.createElement("div");
      existingError.className = "cm-error";
      existingError.style.marginTop = "8px";
      notifyEl.appendChild(existingError);
    }
    existingError.textContent = `Confirm failed: ${err.message}`;
  }
}
