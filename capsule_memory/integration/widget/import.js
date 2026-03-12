/**
 * import.js — Import dialog for the CapsuleMemory Widget.
 *
 * Provides a drag-and-drop zone plus file selector for importing capsule files.
 * Sends the file as multipart FormData to POST /api/v1/capsules/import.
 */

/**
 * Show the import dialog.
 *
 * @param {HTMLElement}  root       The widget root container.
 * @param {string}       api        Base API URL.
 * @param {string}       userId     Current user ID.
 * @param {Function}     onSuccess  Callback invoked after a successful import (to refresh the list).
 */
export function showImportDialog(root, api, userId, onSuccess) {
  /** @type {File|null} */
  let selectedFile = null;

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
  title.textContent = "Import Capsule";

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

  // Drop zone
  const dropzone = document.createElement("div");
  dropzone.className = "cm-dropzone";

  const dzIcon = document.createElement("span");
  dzIcon.className = "cm-dropzone-icon";
  dzIcon.textContent = "\u{1F4C1}"; // file folder icon

  const dzText = document.createElement("div");
  dzText.className = "cm-dropzone-text";
  dzText.textContent = "Drag and drop a capsule file here";

  const dzHint = document.createElement("div");
  dzHint.className = "cm-dropzone-hint";
  dzHint.textContent = "or click to browse — .json, .capsule, .txt";

  const dzFilename = document.createElement("div");
  dzFilename.className = "cm-dropzone-filename";
  dzFilename.style.display = "none";

  dropzone.appendChild(dzIcon);
  dropzone.appendChild(dzText);
  dropzone.appendChild(dzHint);
  dropzone.appendChild(dzFilename);

  // Hidden file input
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = ".json,.capsule,.txt";
  fileInput.style.display = "none";

  // Click dropzone to open file browser
  dropzone.addEventListener("click", () => fileInput.click());

  // File input change handler
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
      selectFile(fileInput.files[0]);
    }
  });

  // Drag-and-drop handlers
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.add("cm-dropzone--active");
  });

  dropzone.addEventListener("dragleave", (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove("cm-dropzone--active");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove("cm-dropzone--active");

    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      selectFile(e.dataTransfer.files[0]);
    }
  });

  // Passphrase field (for encrypted capsules)
  const passGroup = document.createElement("div");
  passGroup.className = "cm-form-group";
  passGroup.style.marginTop = "16px";

  const passLabel = document.createElement("label");
  passLabel.className = "cm-label";
  passLabel.textContent = "Decryption Passphrase (if encrypted)";
  passLabel.setAttribute("for", "cm-import-passphrase");

  const passInput = document.createElement("input");
  passInput.type = "password";
  passInput.className = "cm-input";
  passInput.id = "cm-import-passphrase";
  passInput.placeholder = "Leave blank if not encrypted";

  passGroup.appendChild(passLabel);
  passGroup.appendChild(passInput);

  // Status message area
  const statusEl = document.createElement("div");
  statusEl.style.display = "none";
  statusEl.style.marginTop = "12px";

  body.appendChild(dropzone);
  body.appendChild(fileInput);
  body.appendChild(passGroup);
  body.appendChild(statusEl);

  // ── Footer
  const footer = document.createElement("div");
  footer.className = "cm-dialog-footer";

  const cancelBtn = document.createElement("button");
  cancelBtn.className = "cm-btn";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", () => cleanup());

  const uploadBtn = document.createElement("button");
  uploadBtn.className = "cm-btn cm-btn--primary";
  uploadBtn.textContent = "Upload";
  uploadBtn.disabled = true;
  uploadBtn.addEventListener("click", () => handleUpload());

  footer.appendChild(cancelBtn);
  footer.appendChild(uploadBtn);

  // ── Assemble
  dialog.appendChild(header);
  dialog.appendChild(body);
  dialog.appendChild(footer);
  overlay.appendChild(dialog);

  // Close on overlay click
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) cleanup();
  });

  // Close on Escape
  function onKeyDown(e) {
    if (e.key === "Escape") cleanup();
  }
  document.addEventListener("keydown", onKeyDown);

  root.appendChild(overlay);

  /**
   * Handle file selection (from either input or drag-and-drop).
   * @param {File} file
   */
  function selectFile(file) {
    selectedFile = file;
    dzFilename.textContent = file.name;
    dzFilename.style.display = "block";
    dzText.textContent = "File selected:";
    dzHint.style.display = "none";
    uploadBtn.disabled = false;
    statusEl.style.display = "none";
  }

  /** Show a status message inside the dialog. */
  function showStatus(message, type) {
    statusEl.style.display = "block";
    statusEl.className = type === "error" ? "cm-error" : "cm-success-msg";
    statusEl.textContent = message;
  }

  /** Remove the dialog and clean up event listeners. */
  function cleanup() {
    document.removeEventListener("keydown", onKeyDown);
    overlay.remove();
  }

  /** Handle the upload action. */
  async function handleUpload() {
    if (!selectedFile) {
      showStatus("Please select a file first.", "error");
      return;
    }

    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("user_id", userId);

      const passphrase = passInput.value.trim();
      if (passphrase) {
        formData.append("passphrase", passphrase);
      }

      const resp = await fetch(`${api}/api/v1/capsules/import`, {
        method: "POST",
        body: formData,
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

      const result = await resp.json();
      showStatus(
        `Imported successfully: "${result.title || result.capsule_id}" (${result.type})`,
        "success"
      );

      // Notify parent to refresh the capsule list
      if (typeof onSuccess === "function") {
        onSuccess();
      }

      // Auto-close after a brief delay
      setTimeout(() => cleanup(), 1500);
    } catch (err) {
      showStatus(`Import failed: ${err.message}`, "error");
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Upload";
    }
  }
}
