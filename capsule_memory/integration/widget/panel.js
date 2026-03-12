/**
 * panel.js — Capsule list panel for the CapsuleMemory Widget.
 *
 * Renders a slide-out drawer listing all capsules for the current user.
 * Each card shows title, type badge, tags, sealed date, and turn count,
 * with Export and Delete action buttons.
 */

import { showExportDialog } from "./export.js";
import { showImportDialog } from "./import.js";

/** @type {HTMLElement|null} */
let panelEl = null;

/** @type {HTMLElement|null} */
let listEl = null;

/** @type {string} */
let _api = "";

/** @type {string} */
let _userId = "";

/** @type {HTMLElement} */
let _root = null;

/**
 * Build and return the panel DOM element (called once during init).
 *
 * @param {HTMLElement} root  The widget root container.
 * @param {string}      api   Base API URL.
 * @param {string}      userId  Current user ID.
 * @returns {HTMLElement}
 */
export function createPanel(root, api, userId) {
  _api = api;
  _userId = userId;
  _root = root;

  panelEl = document.createElement("div");
  panelEl.className = "cm-panel";

  // ── Header
  const header = document.createElement("div");
  header.className = "cm-panel-header";

  const title = document.createElement("h2");
  title.textContent = "Capsule Memory";

  const actions = document.createElement("div");
  actions.className = "cm-panel-header-actions";

  const importBtn = document.createElement("button");
  importBtn.className = "cm-btn cm-btn--sm";
  importBtn.textContent = "Import";
  importBtn.addEventListener("click", () => {
    showImportDialog(_root, _api, _userId, () => refreshCapsules());
  });

  const refreshBtn = document.createElement("button");
  refreshBtn.className = "cm-btn cm-btn--icon";
  refreshBtn.innerHTML = "&#x21bb;"; // ↻ refresh symbol
  refreshBtn.title = "Refresh";
  refreshBtn.addEventListener("click", () => refreshCapsules());

  const closeBtn = document.createElement("button");
  closeBtn.className = "cm-btn cm-btn--icon";
  closeBtn.innerHTML = "&times;";
  closeBtn.title = "Close";
  closeBtn.addEventListener("click", () => closePanel());

  actions.appendChild(importBtn);
  actions.appendChild(refreshBtn);
  actions.appendChild(closeBtn);
  header.appendChild(title);
  header.appendChild(actions);

  // ── Body
  listEl = document.createElement("div");
  listEl.className = "cm-panel-body";

  panelEl.appendChild(header);
  panelEl.appendChild(listEl);
  root.appendChild(panelEl);

  return panelEl;
}

/** Open (slide in) the panel and load capsules. */
export function openPanel() {
  if (!panelEl) return;
  panelEl.classList.add("cm-panel--open");
  refreshCapsules();
}

/** Close (slide out) the panel. */
export function closePanel() {
  if (!panelEl) return;
  panelEl.classList.remove("cm-panel--open");
}

/** Toggle panel open/close state. */
export function togglePanel() {
  if (!panelEl) return;
  if (panelEl.classList.contains("cm-panel--open")) {
    closePanel();
  } else {
    openPanel();
  }
}

/** Fetch capsules from the API and re-render the list. */
async function refreshCapsules() {
  if (!listEl) return;

  listEl.innerHTML = "";

  // Show loading spinner
  const loadingEl = document.createElement("div");
  loadingEl.className = "cm-loading";
  const spinner = document.createElement("div");
  spinner.className = "cm-spinner";
  loadingEl.appendChild(spinner);
  listEl.appendChild(loadingEl);

  try {
    const url = `${_api}/api/v1/capsules?user_id=${encodeURIComponent(_userId)}`;
    const resp = await fetch(url);

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }

    const capsules = await resp.json();
    listEl.innerHTML = "";

    if (!Array.isArray(capsules) || capsules.length === 0) {
      renderEmpty();
      return;
    }

    for (const capsule of capsules) {
      listEl.appendChild(renderCard(capsule));
    }
  } catch (err) {
    listEl.innerHTML = "";
    const errorEl = document.createElement("div");
    errorEl.className = "cm-error";
    errorEl.textContent = `Failed to load capsules: ${err.message}`;
    listEl.appendChild(errorEl);
  }
}

/** Render the "no capsules" empty state. */
function renderEmpty() {
  const el = document.createElement("div");
  el.className = "cm-empty";

  const icon = document.createElement("div");
  icon.className = "cm-empty-icon";
  icon.textContent = "\u{1F4E6}"; // package emoji as placeholder icon

  const text = document.createElement("p");
  text.textContent = "No capsules found. Start a session to create your first memory capsule.";

  el.appendChild(icon);
  el.appendChild(text);
  listEl.appendChild(el);
}

/**
 * Render a single capsule card.
 *
 * @param {Object} capsule  Capsule data from the list endpoint.
 * @returns {HTMLElement}
 */
function renderCard(capsule) {
  const card = document.createElement("div");
  card.className = "cm-card";

  // ── Title
  const titleEl = document.createElement("div");
  titleEl.className = "cm-card-title";
  titleEl.textContent = capsule.title || capsule.capsule_id;

  // ── Meta row: type badge + date + turn count
  const metaEl = document.createElement("div");
  metaEl.className = "cm-card-meta";

  const badge = document.createElement("span");
  const typeKey = (capsule.type || "memory").toLowerCase();
  badge.className = `cm-badge cm-badge--${typeKey}`;
  badge.textContent = typeKey;
  metaEl.appendChild(badge);

  if (capsule.sealed_at) {
    const dateSpan = document.createElement("span");
    const d = new Date(capsule.sealed_at);
    dateSpan.textContent = d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
    metaEl.appendChild(dateSpan);
  }

  if (typeof capsule.turn_count === "number") {
    const turnsSpan = document.createElement("span");
    turnsSpan.textContent = `${capsule.turn_count} turn${capsule.turn_count !== 1 ? "s" : ""}`;
    metaEl.appendChild(turnsSpan);
  }

  // ── Tags
  let tagsEl = null;
  if (Array.isArray(capsule.tags) && capsule.tags.length > 0) {
    tagsEl = document.createElement("div");
    tagsEl.className = "cm-card-tags";
    for (const tag of capsule.tags) {
      const t = document.createElement("span");
      t.className = "cm-tag";
      t.textContent = tag;
      tagsEl.appendChild(t);
    }
  }

  // ── Action buttons
  const actionsEl = document.createElement("div");
  actionsEl.className = "cm-card-actions";

  const exportBtn = document.createElement("button");
  exportBtn.className = "cm-btn cm-btn--sm";
  exportBtn.textContent = "Export";
  exportBtn.addEventListener("click", () => {
    showExportDialog(_root, _api, capsule.capsule_id);
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "cm-btn cm-btn--sm cm-btn--danger";
  deleteBtn.textContent = "Delete";
  deleteBtn.addEventListener("click", () => handleDelete(capsule.capsule_id, card));

  actionsEl.appendChild(exportBtn);
  actionsEl.appendChild(deleteBtn);

  // ── Assemble
  card.appendChild(titleEl);
  card.appendChild(metaEl);
  if (tagsEl) card.appendChild(tagsEl);
  card.appendChild(actionsEl);

  return card;
}

/**
 * Handle capsule deletion with confirmation.
 *
 * @param {string}      capsuleId  The capsule ID to delete.
 * @param {HTMLElement}  cardEl     The card DOM element to remove on success.
 */
async function handleDelete(capsuleId, cardEl) {
  const confirmed = window.confirm(
    `Delete capsule "${capsuleId}"?\n\nThis action cannot be undone.`
  );
  if (!confirmed) return;

  try {
    const resp = await fetch(`${_api}/api/v1/capsules/${encodeURIComponent(capsuleId)}`, {
      method: "DELETE",
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }

    // Remove the card with a fade-out effect
    cardEl.style.transition = "opacity 0.25s ease, transform 0.25s ease";
    cardEl.style.opacity = "0";
    cardEl.style.transform = "translateX(20px)";
    setTimeout(() => {
      cardEl.remove();
      // Check if the list is now empty
      if (listEl && listEl.children.length === 0) {
        renderEmpty();
      }
    }, 250);
  } catch (err) {
    window.alert(`Failed to delete capsule: ${err.message}`);
  }
}
