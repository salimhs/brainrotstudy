"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";
import type { JobStage, JobView, ProgressEvent } from "@/lib/api";

const STAGES: { id: JobStage; label: string; hint: string }[] = [
  { id: "extract", label: "Extract", hint: "Reading the source" },
  { id: "script", label: "Script", hint: "Writing narration" },
  { id: "narrate", label: "Narrate", hint: "Synthesizing voice" },
  { id: "visuals", label: "Visuals", hint: "Hunting images" },
  { id: "render", label: "Render", hint: "Stitching video" },
  { id: "exports", label: "Finish", hint: "Study extras" },
];

export function Progress({
  job,
  event,
}: {
  job: JobView | null;
  event: ProgressEvent | null;
}) {
  const progress = event?.progress ?? job?.progress ?? 0;
  const activeStage = event?.stage ?? job?.stage ?? null;
  const status = event?.status ?? job?.status ?? "queued";
  const message = event?.message ?? "Preparing…";

  return (
    <div className="card p-6 w-full max-w-xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <p className="text-xs uppercase tracking-wider text-muted">Status</p>
          <p className="text-lg font-semibold capitalize">
            {status === "succeeded" ? "Done!" : status}
          </p>
        </div>
        <motion.div
          key={progress}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-2xl font-bold tabular-nums"
        >
          {progress}%
        </motion.div>
      </div>

      <div className="relative h-2 w-full overflow-hidden rounded-full bg-panel border border-border">
        <motion.div
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="h-full bg-gradient-to-r from-accent to-accent2"
        />
        {status === "running" && (
          <div className="absolute inset-0 overflow-hidden rounded-full">
            <div className="h-full w-1/3 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/25 to-transparent" />
          </div>
        )}
      </div>

      <ul className="mt-6 space-y-2">
        {STAGES.map((stage) => {
          const idx = STAGES.findIndex((s) => s.id === stage.id);
          const activeIdx = activeStage ? STAGES.findIndex((s) => s.id === activeStage) : -1;
          const state =
            status === "succeeded" || idx < activeIdx
              ? "done"
              : idx === activeIdx && status === "running"
                ? "active"
                : "pending";
          return (
            <li
              key={stage.id}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
                state === "active" && "bg-white/5",
              )}
            >
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full border",
                  state === "done"
                    ? "border-success bg-success/20 text-success"
                    : state === "active"
                      ? "border-accent bg-accent/20 text-white"
                      : "border-border text-muted",
                )}
              >
                {state === "done" ? (
                  <Check className="h-3.5 w-3.5" />
                ) : state === "active" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
              </span>
              <span
                className={cn(
                  "font-medium",
                  state === "pending" ? "text-muted" : "text-white",
                )}
              >
                {stage.label}
              </span>
              <span className="text-muted">— {stage.hint}</span>
            </li>
          );
        })}
      </ul>

      <AnimatePresence mode="wait">
        <motion.p
          key={message}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          className="mt-5 text-xs text-muted"
        >
          {message}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}
