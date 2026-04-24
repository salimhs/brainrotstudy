/**
 * Thin wrapper around the BrainRotStudy FastAPI server.
 *
 * In dev we rely on the Next rewrite in next.config.js to proxy /api/* → API.
 * In prod you either keep the proxy or set NEXT_PUBLIC_API_BASE.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type JobStage =
  | "extract"
  | "script"
  | "narrate"
  | "visuals"
  | "render"
  | "exports";

export type Pacing = "fast" | "balanced" | "chill";
export type Vibe = "standard" | "unhinged" | "asmr" | "gossip" | "professor";
export type CaptionStyle = "karaoke" | "pop" | "minimal";

export interface JobOptions {
  length_sec: number;
  pacing: Pacing;
  vibe: Vibe;
  caption_style: CaptionStyle;
  export_extras: boolean;
  language: string;
}

export interface Artifacts {
  video_url?: string | null;
  srt_url?: string | null;
  notes_url?: string | null;
  anki_url?: string | null;
}

export interface JobView {
  id: string;
  status: JobStatus;
  stage: JobStage | null;
  progress: number;
  title: string;
  input_kind: "topic" | "file";
  input_filename: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  artifacts: Artifacts | null;
  options: JobOptions;
}

export interface ProgressEvent {
  id: string;
  status: JobStatus;
  stage: JobStage | null;
  progress: number;
  message: string;
  at: string;
}

export interface ServerConfig {
  llm: { gemini: boolean; anthropic: boolean; openai: boolean };
  tts: { elevenlabs: boolean; gtts: boolean };
  images: { pexels: boolean; openverse: boolean };
  ffmpeg: boolean;
  max_upload_mb: number;
}

export const defaultOptions: JobOptions = {
  length_sec: 60,
  pacing: "balanced",
  vibe: "standard",
  caption_style: "karaoke",
  export_extras: true,
  language: "en",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) message = body.detail;
    } catch {
      /* body was not JSON */
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function getConfig() {
  return request<ServerConfig>("/config");
}

export function listJobs() {
  return request<JobView[]>("/jobs");
}

export function getJob(id: string) {
  return request<JobView>(`/jobs/${id}`);
}

export function deleteJob(id: string) {
  return request<{ id: string; deleted: string }>(`/jobs/${id}`, { method: "DELETE" });
}

export function createTopicJob(topic: string, outline: string | null, options: JobOptions) {
  return request<JobView>("/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ topic, outline, options }),
  });
}

export async function createFileJob(file: File, options: JobOptions) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("options", JSON.stringify(options));
  const res = await fetch(`${API_BASE}/jobs`, { method: "POST", body: fd });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) message = body.detail;
    } catch {
      /* no json */
    }
    throw new Error(message);
  }
  return (await res.json()) as JobView;
}

/** Wire an EventSource to the SSE progress stream. Returns a cleanup fn. */
export function subscribeProgress(
  id: string,
  onEvent: (evt: ProgressEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const es = new EventSource(`${API_BASE}/jobs/${id}/events`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data));
    } catch (e) {
      console.warn("bad SSE payload", e, msg.data);
    }
  };
  if (onError) es.onerror = onError;
  return () => es.close();
}

export function downloadUrl(id: string, asset: "video" | "srt" | "notes" | "anki"): string {
  return `${API_BASE}/jobs/${id}/download/${asset}`;
}
