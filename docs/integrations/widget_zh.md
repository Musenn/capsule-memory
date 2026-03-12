# Web Widget 集成

> [English](widget.md) | **中文**

## 概述

CapsuleMemory 包含一个可嵌入的 Web Widget，提供：

- 胶囊列表面板，支持搜索和筛选
- 一键导出和导入胶囊
- 通过轮询实时接收技能触发通知

## 快速开始

### 1. 构建 Widget

```bash
cd capsule_memory/integration/widget
npm install
npm run build
# 输出: dist/widget.js
```

### 2. 嵌入到页面

```html
<script src="path/to/widget.js"></script>
<script>
  CapsuleWidget.init({
    apiBase: "http://localhost:8000",
    userId: "user_123",
    position: "bottom-right",  // bottom-right | bottom-left | top-right | top-left
    theme: "light",            // light | dark
    pollInterval: 5000,        // 毫秒，技能触发轮询间隔
  });
</script>
```

### 3. 启动 REST API 服务

Widget 通过 CapsuleMemory REST API 通信：

```bash
capsule-memory serve --port 8000
```

## 功能特性

### 胶囊面板

浮动面板展示当前用户的所有胶囊。每个胶囊卡片显示：

- 标题、类型标签和标签
- 创建日期和轮次数
- 快捷操作：导出、查看详情

### 导出与导入

- **导出**：点击胶囊上的导出按钮下载 JSON 文件
- **导入**：使用导入按钮上传胶囊 JSON 文件

### 技能触发通知

Widget 按配置间隔轮询 `GET /api/v1/capsules/pending-triggers`。检测到技能触发时弹出通知，可选择：

- 提取为技能胶囊
- 合并到记忆
- 忽略触发

## 自定义样式

### CSS 变量

通过设置 CSS 自定义属性覆盖默认主题：

```css
:root {
  --capsule-widget-bg: #ffffff;
  --capsule-widget-text: #1a1a1a;
  --capsule-widget-accent: #6366f1;
  --capsule-widget-border: #e5e7eb;
  --capsule-widget-radius: 8px;
}
```

## API 认证

如果 REST API 启用了 Bearer Token 认证，在初始化时传入 Token：

```javascript
CapsuleWidget.init({
  apiBase: "http://localhost:8000",
  userId: "user_123",
  apiKey: "your-secret-key",
});
```
