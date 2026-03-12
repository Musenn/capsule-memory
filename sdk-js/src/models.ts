/** Capsule type classification. */
export type CapsuleType = "memory" | "skill" | "hybrid" | "context";

/** Capsule lifecycle status. */
export type CapsuleStatus = "draft" | "sealed" | "imported" | "archived";

/** Supported export formats. */
export type ExportFormat = "json" | "msgpack" | "universal" | "prompt";

/** Result returned by the recall endpoint. */
export interface RecallResult {
  facts: Array<{ key: string; value: string }>;
  skills: Array<{
    name: string;
    description: string;
    instructions: string;
    trigger_pattern: string;
  }>;
  summary: string;
  prompt_injection: string;
  sources: string[];
}

/** Options for sealing a session into a capsule. */
export interface SealOptions {
  userId: string;
  title?: string;
  tags?: string[];
}

/** Capsule summary returned by list and detail endpoints. */
export interface Capsule {
  capsule_id: string;
  capsule_type: CapsuleType;
  lifecycle: { status: CapsuleStatus; sealed_at?: string };
  metadata: { title: string; tags: string[]; turn_count: number };
}
