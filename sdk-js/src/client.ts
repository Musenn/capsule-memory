import type { Capsule, CapsuleStatus, CapsuleType, ExportFormat, RecallResult, SealOptions } from "./models";

/** Configuration options for CapsuleMemoryClient. */
export interface ClientOptions {
  /** Base URL of the CapsuleMemory REST API. Defaults to "http://localhost:8000". */
  apiUrl?: string;
  /** Default user ID sent with requests. Defaults to "default". */
  userId?: string;
  /** Bearer API key for authenticated requests. */
  apiKey?: string;
}

/** Error thrown when the CapsuleMemory API returns a non-OK response. */
export class CapsuleMemoryError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`CapsuleMemory API error ${status}: ${detail}`);
    this.name = "CapsuleMemoryError";
  }
}

/**
 * TypeScript client for the CapsuleMemory REST API.
 *
 * Uses the browser-native `fetch` API (also available in Node 18+).
 *
 * @example
 * ```ts
 * const client = new CapsuleMemoryClient({ apiUrl: "http://localhost:8000" });
 * const result = await client.recall("How do I deploy?");
 * console.log(result.prompt_injection);
 * ```
 */
export class CapsuleMemoryClient {
  private readonly apiUrl: string;
  private readonly userId: string;
  private readonly apiKey: string | undefined;

  constructor(options: ClientOptions = {}) {
    this.apiUrl = (options.apiUrl ?? "http://localhost:8000").replace(/\/+$/, "");
    this.userId = options.userId ?? "default";
    this.apiKey = options.apiKey;
  }

  // ─── Internal helpers ──────────────────────────────────────────────────

  /** Build common request headers. */
  private headers(contentType?: string): Record<string, string> {
    const h: Record<string, string> = {};
    if (contentType) {
      h["Content-Type"] = contentType;
    }
    if (this.apiKey) {
      h["Authorization"] = `Bearer ${this.apiKey}`;
    }
    return h;
  }

  /** Execute a fetch request and handle errors uniformly. */
  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const url = `${this.apiUrl}${path}`;
    const response = await fetch(url, init);

    if (!response.ok) {
      let detail: string;
      try {
        const body = await response.json();
        detail = body.detail ?? JSON.stringify(body);
      } catch {
        detail = await response.text();
      }
      throw new CapsuleMemoryError(response.status, detail);
    }

    return response.json() as Promise<T>;
  }

  /** Execute a fetch request and return the raw Response (for binary/blob downloads). */
  private async requestRaw(path: string, init?: RequestInit): Promise<Response> {
    const url = `${this.apiUrl}${path}`;
    const response = await fetch(url, init);

    if (!response.ok) {
      let detail: string;
      try {
        const body = await response.json();
        detail = body.detail ?? JSON.stringify(body);
      } catch {
        detail = await response.text();
      }
      throw new CapsuleMemoryError(response.status, detail);
    }

    return response;
  }

  // ─── Recall ────────────────────────────────────────────────────────────

  /**
   * Recall relevant memories matching a query.
   *
   * @param query - Natural-language search query.
   * @param topK  - Maximum number of capsules to consider (1-10, default 3).
   * @returns Aggregated recall result with facts, skills, summary, and prompt injection.
   */
  async recall(query: string, topK: number = 3): Promise<RecallResult> {
    const params = new URLSearchParams({
      q: query,
      user_id: this.userId,
      top_k: String(topK),
    });
    return this.request<RecallResult>(`/api/v1/recall?${params}`, {
      method: "GET",
      headers: this.headers(),
    });
  }

  // ─── Capsule CRUD ──────────────────────────────────────────────────────

  /**
   * List capsules with optional filtering.
   *
   * @param options - Filter and pagination options.
   * @returns Array of capsule summaries.
   */
  async listCapsules(
    options: { type?: CapsuleType; tags?: string[]; limit?: number } = {},
  ): Promise<Capsule[]> {
    const params = new URLSearchParams();
    params.set("user_id", this.userId);
    if (options.type) params.set("type", options.type);
    if (options.tags && options.tags.length > 0) params.set("tags", options.tags.join(","));
    if (options.limit !== undefined) params.set("limit", String(options.limit));

    // The REST API returns a flat list; we normalize to the Capsule interface.
    const raw = await this.request<Array<Record<string, unknown>>>(
      `/api/v1/capsules?${params}`,
      { method: "GET", headers: this.headers() },
    );

    return raw.map((item) => this.toCapsule(item));
  }

  /**
   * Get full capsule details by ID.
   *
   * @param id - Capsule unique identifier.
   * @returns Capsule details.
   */
  async getCapsule(id: string): Promise<Capsule> {
    const raw = await this.request<Record<string, unknown>>(`/api/v1/capsules/${encodeURIComponent(id)}`, {
      method: "GET",
      headers: this.headers(),
    });
    return this.toCapsule(raw);
  }

  /**
   * Delete a capsule by ID.
   *
   * @param id - Capsule unique identifier.
   */
  async deleteCapsule(id: string): Promise<void> {
    await this.request<{ deleted: boolean; capsule_id: string }>(
      `/api/v1/capsules/${encodeURIComponent(id)}`,
      { method: "DELETE", headers: this.headers() },
    );
  }

  /**
   * Export a capsule as a downloadable Blob.
   *
   * @param id     - Capsule unique identifier.
   * @param format - Export format (json, msgpack, universal, prompt). Defaults to "json".
   * @returns Blob containing the exported capsule data.
   */
  async exportCapsule(id: string, format: ExportFormat = "json"): Promise<Blob> {
    const params = new URLSearchParams({ format });
    const response = await this.requestRaw(
      `/api/v1/capsules/${encodeURIComponent(id)}/export?${params}`,
      { method: "GET", headers: this.headers() },
    );
    return response.blob();
  }

  /**
   * Import a capsule from a File upload.
   *
   * @param file   - File object to upload (browser File or compatible).
   * @param userId - Target user ID for the imported capsule. Falls back to client default.
   * @returns The newly created capsule.
   */
  async importCapsule(file: File, userId?: string): Promise<Capsule> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("user_id", userId ?? this.userId);

    // Do NOT set Content-Type manually; the browser sets multipart boundary automatically.
    const authHeaders: Record<string, string> = {};
    if (this.apiKey) {
      authHeaders["Authorization"] = `Bearer ${this.apiKey}`;
    }

    const raw = await this.request<Record<string, unknown>>("/api/v1/capsules/import", {
      method: "POST",
      headers: authHeaders,
      body: formData,
    });

    return this.toCapsule(raw);
  }

  // ─── Prompt injection shortcut ─────────────────────────────────────────

  /**
   * Convenience method: recall memories and return only the prompt_injection string.
   *
   * Ideal for injecting recalled context directly into an LLM system prompt.
   *
   * @param query - Natural-language search query.
   * @returns The prompt injection text.
   */
  async getPromptInjection(query: string): Promise<string> {
    const result = await this.recall(query);
    return result.prompt_injection;
  }

  // ─── Session management ────────────────────────────────────────────────

  /**
   * Create a new conversation session.
   *
   * @param userId - User identifier. Falls back to client default.
   * @returns Object containing the new session_id.
   */
  async createSession(userId?: string): Promise<{ session_id: string }> {
    const params = new URLSearchParams({ user_id: userId ?? this.userId });
    return this.request<{ session_id: string }>(`/api/v1/sessions?${params}`, {
      method: "POST",
      headers: this.headers(),
    });
  }

  /**
   * Ingest a user-assistant conversation turn into an active session.
   *
   * @param sessionId         - Target session ID.
   * @param userMessage       - The user's message text.
   * @param assistantResponse - The assistant's response text.
   * @returns Ingest result with turn_id, session_id, total_turns, pending_triggers.
   */
  async ingest(
    sessionId: string,
    userMessage: string,
    assistantResponse: string,
  ): Promise<{
    turn_id: string;
    session_id: string;
    total_turns: number;
    pending_triggers: number;
  }> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/ingest`, {
      method: "POST",
      headers: this.headers("application/json"),
      body: JSON.stringify({
        user_id: this.userId,
        user_message: userMessage,
        assistant_response: assistantResponse,
      }),
    });
  }

  /**
   * Seal a session, creating a persistent capsule.
   *
   * @param sessionId - The session to seal.
   * @param options   - Optional seal configuration (userId, title, tags).
   * @returns The newly created capsule.
   */
  async sealSession(sessionId: string, options?: SealOptions): Promise<Capsule> {
    const raw = await this.request<Record<string, unknown>>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/seal`,
      {
        method: "POST",
        headers: this.headers("application/json"),
        body: JSON.stringify({
          user_id: options?.userId ?? this.userId,
          title: options?.title ?? "",
          tags: options?.tags ?? [],
        }),
      },
    );

    return this.toCapsule(raw);
  }

  // ─── Normalization ─────────────────────────────────────────────────────

  /**
   * Normalize a raw API response object into the Capsule interface.
   *
   * The REST API returns capsule data in varying shapes depending on the
   * endpoint (list vs detail vs seal). This method handles all known shapes
   * and produces a consistent Capsule object.
   */
  private toCapsule(raw: Record<string, unknown>): Capsule {
    // The detail endpoint returns the full nested structure.
    // The list endpoint returns a flattened shape.
    // The seal endpoint returns { capsule_id, title, turn_count, type }.

    const capsuleId = (raw["capsule_id"] as string) ?? "";

    // Resolve capsule_type from nested or flat field
    const rawType = raw["capsule_type"] ?? raw["type"] ?? "memory";
    const capsuleType = (typeof rawType === "string" ? rawType : "memory") as CapsuleType;

    // Resolve lifecycle
    let lifecycle: { status: CapsuleStatus; sealed_at?: string };
    if (raw["lifecycle"] && typeof raw["lifecycle"] === "object") {
      const lc = raw["lifecycle"] as Record<string, unknown>;
      lifecycle = {
        status: ((lc["status"] as string) ?? "sealed") as CapsuleStatus,
        sealed_at: lc["sealed_at"] as string | undefined,
      };
    } else {
      lifecycle = {
        status: ((raw["status"] as string) ?? "sealed") as CapsuleStatus,
        sealed_at: raw["sealed_at"] as string | undefined,
      };
    }

    // Resolve metadata
    let metadata: { title: string; tags: string[]; turn_count: number };
    if (raw["metadata"] && typeof raw["metadata"] === "object") {
      const md = raw["metadata"] as Record<string, unknown>;
      metadata = {
        title: (md["title"] as string) ?? "",
        tags: (md["tags"] as string[]) ?? [],
        turn_count: (md["turn_count"] as number) ?? 0,
      };
    } else {
      metadata = {
        title: (raw["title"] as string) ?? "",
        tags: (raw["tags"] as string[]) ?? [],
        turn_count: (raw["turn_count"] as number) ?? 0,
      };
    }

    return { capsule_id: capsuleId, capsule_type: capsuleType, lifecycle, metadata };
  }
}
