# Web Widget Integration

> **English** | [中文](widget_zh.md)

## Overview

CapsuleMemory includes an embeddable web widget that provides:

- Capsule list panel with search and filtering
- One-click capsule export and import
- Real-time skill trigger notifications via polling

## Quick Start

### 1. Build the Widget

```bash
cd capsule_memory/integration/widget
npm install
npm run build
# Output: dist/widget.js
```

### 2. Embed in Your Page

```html
<script src="path/to/widget.js"></script>
<script>
  CapsuleWidget.init({
    apiBase: "http://localhost:8000",
    userId: "user_123",
    position: "bottom-right",  // bottom-right | bottom-left | top-right | top-left
    theme: "light",            // light | dark
    pollInterval: 5000,        // ms, for skill trigger polling
  });
</script>
```

### 3. Start the REST API Server

The widget communicates with the CapsuleMemory REST API:

```bash
capsule-memory serve --port 8000
```

## Features

### Capsule Panel

The floating panel displays all capsules for the configured user. Each capsule card shows:

- Title, type badge, and tags
- Creation date and turn count
- Quick actions: export, view details

### Export & Import

- **Export**: Click the export button on any capsule to download it as JSON
- **Import**: Use the import button to upload a capsule JSON file

### Skill Trigger Notifications

The widget polls `GET /api/v1/capsules/pending-triggers` at the configured interval. When a skill trigger is detected, a notification toast appears with options to:

- Extract as skill capsule
- Merge into memory
- Ignore the trigger

## Customization

### CSS Variables

Override the default theme by setting CSS custom properties:

```css
:root {
  --capsule-widget-bg: #ffffff;
  --capsule-widget-text: #1a1a1a;
  --capsule-widget-accent: #6366f1;
  --capsule-widget-border: #e5e7eb;
  --capsule-widget-radius: 8px;
}
```

## API Authentication

If the REST API uses Bearer token auth, pass the token during init:

```javascript
CapsuleWidget.init({
  apiBase: "http://localhost:8000",
  userId: "user_123",
  apiKey: "your-secret-key",
});
```
