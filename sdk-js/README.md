# @capsule-memory/sdk

TypeScript SDK for [CapsuleMemory](https://github.com/Musenn/capsule-memory) — user-sovereign AI memory capsule system with skill extraction.

## Installation

```bash
npm install @capsule-memory/sdk
```

## Quick Start

```typescript
import { CapsuleClient } from "@capsule-memory/sdk";

const client = new CapsuleClient({
  baseUrl: "http://localhost:8000",
  apiKey: "your-api-key", // optional
});

// Ingest a conversation turn
await client.ingest({
  userId: "user_1",
  userMessage: "How do I optimize PostgreSQL queries?",
  assistantResponse: "Here are several approaches...",
});

// Seal the session into a capsule
const capsule = await client.seal({ userId: "user_1" });

// Recall relevant memories
const memories = await client.recall({
  query: "database optimization",
  userId: "user_1",
  topK: 3,
});
```

## API

See the [main project documentation](https://github.com/Musenn/capsule-memory) for full API reference.

## License

Apache-2.0
