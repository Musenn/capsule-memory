# @capsule-memory/sdk

TypeScript SDK for [CapsuleMemory](https://github.com/Musenn/capsule-memory) — user-sovereign AI memory capsule system with skill extraction.

## Installation

```bash
npm install @capsule-memory/sdk
```

## Quick Start

```typescript
import { CapsuleMemoryClient } from "@capsule-memory/sdk";

const client = new CapsuleMemoryClient({
  apiUrl: "http://localhost:8000",
  apiKey: "your-api-key", // optional
});

// Create a session and ingest a conversation turn
const { session_id } = await client.createSession();
await client.ingest(session_id, "How do I optimize PostgreSQL queries?", "Here are several approaches...");

// Seal the session into a capsule (with optional host LLM extraction)
const capsule = await client.sealSession(session_id, {
  title: "PostgreSQL Optimization",
  tags: ["database", "postgresql"],
  facts: [{ key: "db.optimization", value: "Use EXPLAIN ANALYZE for query plans" }],
  summary: "Discussed PostgreSQL query optimization strategies.",
});

// Recall relevant memories
const result = await client.recall("database optimization", 3);
console.log(result.prompt_injection);
```

## API

See the [main project documentation](https://github.com/Musenn/capsule-memory) for full API reference.

## License

Apache-2.0
