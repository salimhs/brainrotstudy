"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Download, Trash2, Sparkles } from "lucide-react";
import {
  deleteJob,
  downloadUrl,
  listJobs,
  type JobView,
} from "@/lib/api";
import { Button } from "@/components/ui/Button";

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobView[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setJobs(await listJobs());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  async function remove(id: string) {
    await deleteJob(id);
    refresh();
  }

  return (
    <main className="min-h-screen">
      <nav className="border-b border-border/60">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <Link href="/" className="flex items-center gap-2 text-sm text-muted hover:text-white">
            <ArrowLeft className="h-4 w-4" /> Back
          </Link>
          <Link href="/" className="flex items-center gap-2 text-lg font-bold">
            <Sparkles className="h-5 w-5 text-accent" />
            BrainRotStudy
          </Link>
          <span className="w-10" />
        </div>
      </nav>

      <section className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="text-2xl font-bold mb-5">Your videos</h1>

        {error && <p className="text-danger text-sm mb-4">{error}</p>}

        {jobs === null ? (
          <p className="text-muted">Loading…</p>
        ) : jobs.length === 0 ? (
          <p className="text-muted">No jobs yet. Go make your first video!</p>
        ) : (
          <ul className="grid gap-3">
            {jobs.map((j) => (
              <li key={j.id} className="card p-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-medium truncate">{j.title || j.id}</p>
                  <p className="text-xs text-muted">
                    {new Date(j.created_at).toLocaleString()} · {j.status}
                    {j.stage ? ` · ${j.stage}` : ""}
                  </p>
                  {j.error && <p className="text-xs text-danger mt-1">{j.error}</p>}
                </div>
                <div className="flex gap-2">
                  {j.artifacts?.video_url && (
                    <Button asChild variant="outline" size="sm">
                      <a href={downloadUrl(j.id, "video")} download>
                        <Download className="h-4 w-4" />
                      </a>
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => remove(j.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
