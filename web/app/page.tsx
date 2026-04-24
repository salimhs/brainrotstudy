"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { History, Sparkles } from "lucide-react";
import { CreateForm } from "@/components/CreateForm";
import { Progress } from "@/components/Progress";
import { Result } from "@/components/Result";
import {
  getConfig,
  getJob,
  subscribeProgress,
  type JobView,
  type ProgressEvent,
  type ServerConfig,
} from "@/lib/api";

type Phase = "idle" | "running" | "done";

export default function Home() {
  const [job, setJob] = useState<JobView | null>(null);
  const [event, setEvent] = useState<ProgressEvent | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [config, setConfig] = useState<ServerConfig | null>(null);

  useEffect(() => {
    getConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  useEffect(() => {
    if (!job || phase !== "running") return;
    const stop = subscribeProgress(job.id, async (evt) => {
      setEvent(evt);
      if (evt.status === "succeeded" || evt.status === "failed") {
        const latest = await getJob(job.id).catch(() => null);
        if (latest) setJob(latest);
        setPhase("done");
      }
    });
    return stop;
  }, [job, phase]);

  function reset() {
    setJob(null);
    setEvent(null);
    setPhase("idle");
  }

  return (
    <main className="min-h-screen">
      <nav className="border-b border-border/60">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <Link href="/" className="flex items-center gap-2 text-lg font-bold">
            <Sparkles className="h-5 w-5 text-accent" />
            BrainRotStudy
          </Link>
          <Link
            href="/jobs"
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-white"
          >
            <History className="h-4 w-4" /> History
          </Link>
        </div>
      </nav>

      <section className="mx-auto flex max-w-5xl flex-col items-center gap-8 px-4 pt-10 pb-20">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center"
        >
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight">
            Turn anything into a
            <span className="mx-2 bg-gradient-to-br from-accent to-accent2 bg-clip-text text-transparent">
              60-second study video
            </span>
          </h1>
          <p className="mt-4 max-w-xl mx-auto text-muted">
            Drop a PDF, upload slides, or type a topic. Get a vertical recap with
            narration, captions, and downloadable notes.
          </p>
          {config && <ProviderBadges config={config} />}
        </motion.div>

        <AnimatePresence mode="wait">
          {phase === "idle" && (
            <motion.div
              key="form"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="w-full flex justify-center"
            >
              <CreateForm
                onCreated={(j) => {
                  setJob(j);
                  setPhase("running");
                }}
              />
            </motion.div>
          )}

          {phase === "running" && (
            <motion.div
              key="progress"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="w-full flex justify-center"
            >
              <Progress job={job} event={event} />
            </motion.div>
          )}

          {phase === "done" && job && (
            <motion.div
              key="done"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="w-full flex justify-center"
            >
              {job.status === "failed" ? (
                <FailureCard job={job} onReset={reset} />
              ) : (
                <Result job={job} onReset={reset} />
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    </main>
  );
}

function ProviderBadges({ config }: { config: ServerConfig }) {
  const badges: { label: string; on: boolean }[] = [
    {
      label: "LLM",
      on: config.llm.gemini || config.llm.anthropic || config.llm.openai,
    },
    { label: "Voice", on: config.tts.elevenlabs || config.tts.gtts },
    { label: "FFmpeg", on: config.ffmpeg },
    { label: "Pexels", on: config.images.pexels },
  ];
  return (
    <div className="mt-4 flex flex-wrap justify-center gap-2">
      {badges.map((b) => (
        <span
          key={b.label}
          className={
            "rounded-full border px-2.5 py-0.5 text-[10px] uppercase tracking-wider " +
            (b.on
              ? "border-success/40 bg-success/10 text-success"
              : "border-border text-muted")
          }
        >
          {b.label}: {b.on ? "ready" : "off"}
        </span>
      ))}
    </div>
  );
}

function FailureCard({ job, onReset }: { job: JobView; onReset: () => void }) {
  return (
    <div className="card p-6 w-full max-w-xl border-danger/40">
      <h2 className="text-lg font-semibold text-danger">Job failed</h2>
      <p className="mt-2 text-sm text-muted">
        {job.error || "Something went wrong."}
      </p>
      <button
        onClick={onReset}
        className="mt-4 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-panel"
      >
        Try again
      </button>
    </div>
  );
}
