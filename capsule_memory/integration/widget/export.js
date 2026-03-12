/**
 * export.js — Export dialog for the CapsuleMemory Widget.
 *
 * Shows a modal dialog where the user selects an export format,
 * optionally enters an encryption passphrase, and downloads the capsule file.
 */

/**
 * Show the export dialog for a given capsule.
 *
 * @param {HTMLElement} root       The widget root container (for mounting the overlay).
 * @param {string}      api        Base API URL.
 * @param {string}      capsuleId  The capsule ID to export.
 */
export function showExportDialog(root, api, capsuleId) {
  // ── Overlay
  const overlay = document.createElement("div");
  overlay.className = "cm-overlay";

  // ── Dialog
  const dialog = document.createElement("div");
  dialog.className = "cm-dialog";

  // ── Header
  const header = document.createElement("div");
  header.className = "cm-dialog-header";

  const title = document.createElement("h3");
  title.textContent = "Export Capsule";

  const closeBtn = document.createElement("button");
  closeBtn.className = "cm-btn--icon";
  closeBtn.innerHTML = "&times;";
  closeBtn.title = "Close";
  closeBtn.addEventListener("click", () => cleanup());

  header.appendChild(title);
  header.appendChild(closeBtn);

  // ── Body
  const body = document.createElement("div");
  body.className = "cm-dialog-body";

  // Capsule ID display
  const idGroup = document.createElement("div");
  idGroup.className = "cm-form-group";
  const idLabel = document.createElement("label");
  idLabel.className = "cm-label";
  idLabel.textContent = "Capsule ID";
  const idValue = document.createElement("div");
  idValue.style.cssText =
    "font-family: var(--cm-font-mono); font-size: 13px; color: var(--cm-text-secondary); word-break: break-all;";
  idValue.textContent = capsuleId;
  idGroup.appendChild(idLabel);
  idGroup.appendChild(idValue);

  // Format select
  const formatGroup = document.createElement("div");
  formatGroup.className = "cm-form-group";
  const formatLabel = document.createElement("label");
  formatLabel.className = "cm-label";
  formatLabel.textContent = "Export Format";
  formatLabel.setAttribute("for", "cm-export-format");
  const formatSelect = document.createElement("select");
  formatSelect.className = "cm-select";
  formatSelect.id = "cm-export-format";

  const formats = [
    { value: "json", label: "JSON (.json)" },
    { value: "msgpack", label: "Binary Capsule (.capsule)" },
    { value: "universal", label: "Universal JSON (.json)" },
    { value: "prompt", label: "Prompt Snippet (.txt)" },
  ];

  for (const f of formats) {
    const opt = document.createElement("option");
    opt.value = f.value;
    opt.textContent = f.label;
    formatSelect.appendChild(opt);
  }

  formatGroup.appendChild(formatLabel);
  formatGroup.appendChild(formatSelect);

  // Encryption toggle
  const encryptGroup = document.createElement("div");
  encryptGroup.className = "cm-form-group";
  const encryptRow = document.createElement("label");
  encryptRow.style.cssText =
    "display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; font-weight: 500; color: var(--cm-text);";
  const encryptCheck = document.createElement("input");
  encryptCheck.type = "checkbox";
  encryptCheck.id = "cm-export-encrypt";
  const encryptText = document.createTextNode("Encrypt with passphrase");
  encryptRow.appendChild(encryptCheck);
  encryptRow.appendChild(encryptText);
  encryptGroup.appendChild(encryptRow);

  // Passphrase field (hidden by default)
  const passGroup = document.createElement("div");
  passGroup.className = "cm-form-group";
  passGroup.style.display = "none";

  const passLabel = document.createElement("label");
  passLabel.className = "cm-label";
  passLabel.textContent = "Passphrase";
  passLabel.setAttribute("for", "cm-export-passphrase");

  const passInput = document.createElement("input");
  passInput.type = "password";
  passInput.className = "cm-input";
  passInput.id = "cm-export-passphrase";
  passInput.placeholder = "Enter encryption passphrase";

  const passConfirmLabel = document.createElement("label");
  passConfirmLabel.className = "cm-label";
  passConfirmLabel.textContent = "Confirm Passphrase";
  passConfirmLabel.style.marginTop = "12px";
  passConfirmLabel.setAttribute("for", "cm-export-passphrase-confirm");

  const passConfirmInput = document.createElement("input");
  passConfirmInput.type = "password";
  passConfirmInput.className = "cm-input";
  passConfirmInput.id = "cm-export-passphrase-confirm";
  passConfirmInput.placeholder = "Confirm passphrase";

  passGroup.appendChild(passLabel);
  passGroup.appendChild(passInput);
  passGroup.appendChild(passConfirmLabel);
  passGroup.appendChild(passConfirmInput);

  // Toggle passphrase visibility
  encryptCheck.addEventListener("change", () => {
    passGroup.style.display = encryptCheck.checked ? "block" : "none";
    if (!encryptCheck.checked) {
      passInput.value = "";
      passConfirmInput.value = "";
    }
  });

  // Status message area
  const statusEl = document.createElement("div");
  statusEl.style.display = "none";

  body.appendChild(idGroup);
  body.appendChild(formatGroup);
  body.appendChild(encryptGroup);
  body.appendChild(passGroup);
  body.appendChild(statusEl);

  // ── Footer
  const footer = document.createElement("div");
  footer.className = "cm-dialog-footer";

  const cancelBtn = document.createElement("button");
  cancelBtn.className = "cm-btn";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", () => cleanup());

  const downloadBtn = document.createElement("button");
  downloadBtn.className = "cm-btn cm-btn--primary";
  downloadBtn.textContent = "Download";
  downloadBtn.addEventListener("click", () => handleDownload());

  footer.appendChild(cancelBtn);
  footer.appendChild(downloadBtn);

  // ── Assemble
  dialog.appendChild(header);
  dialog.appendChild(body);
  dialog.appendChild(footer);
  overlay.appendChild(dialog);

  // Close on overlay click (outside dialog)
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) cleanup();
  });

  // Close on Escape
  function onKeyDown(e) {
    if (e.key === "Escape") cleanup();
  }
  document.addEventListener("keydown", onKeyDown);

  root.appendChild(overlay);

  /** Remove the dialog and clean up event listeners. */
  function cleanup() {
    document.removeEventListener("keydown", onKeyDown);
    overlay.remove();
  }

  /** Show a status message inside the dialog. */
  function showStatus(message, type) {
    statusEl.style.display = "block";
    statusEl.className = type === "error" ? "cm-error" : "cm-success-msg";
    statusEl.textContent = message;
  }

  /** Handle the download action. */
  async function handleDownload() {
    const format = formatSelect.value;
    const encrypt = encryptCheck.checked;
    const passphrase = passInput.value;
    const passphraseConfirm = passConfirmInput.value;

    // Validate passphrase if encryption is enabled
    if (encrypt) {
      if (!passphrase) {
        showStatus("Please enter a passphrase.", "error");
        return;
      }
      if (passphrase.length < 4) {
        showStatus("Passphrase must be at least 4 characters.", "error");
        return;
      }
      if (passphrase !== passphraseConfirm) {
        showStatus("Passphrases do not match.", "error");
        return;
      }
    }

    // Disable the download button while fetching
    downloadBtn.disabled = true;
    downloadBtn.textContent = "Downloading...";

    try {
      const params = new URLSearchParams({ format });
      if (encrypt) {
        params.set("encrypt", "true");
        params.set("passphrase", passphrase);
      }

      const url = `${api}/api/v1/capsules/${encodeURIComponent(capsuleId)}/export?${params}`;
      const resp = await fetch(url);

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

      // Extract filename from Content-Disposition header, or construct one
      let filename = `${capsuleId}.json`;
      const disposition = resp.headers.get("Content-Disposition");
      if (disposition) {
        const match = disposition.match(/filename=([^\s;]+)/);
        if (match) {
          filename = match[1].replace(/"/g, "");
        }
      }

      // Trigger browser download
      const blob = await resp.blob();
      const downloadUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = filename;
      anchor.style.display = "none";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(downloadUrl);

      showStatus(`Exported successfully as "${filename}".`, "success");

      // Auto-close after a brief delay
      setTimeout(() => cleanup(), 1500);
    } catch (err) {
      showStatus(`Export failed: ${err.message}`, "error");
    } finally {
      downloadBtn.disabled = false;
      downloadBtn.textContent = "Download";
    }
  }
}
