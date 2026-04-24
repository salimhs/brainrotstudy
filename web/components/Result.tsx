"use client";

import Link from "next/link";
import { Download, Play, RotateCcw } from "lucide-react";
import { downloadUrl, type JobView } from "@/lib/api";
import { Button } from "@/components/ui/Button";

export function Result({ job, onReset }: { job: JobView; onReset: () => void }) {
  const video = job.artifacts?.video_url;
  return (
    <div className="card p-6 w-full max-w-xl space-y-5">
      <div className="flex items-center gap-2">
        <Play className="h-5 w-5 text-accent" />
        <h2 className="text-xl font-semibold">{job.title}</h2>
      </div>

      {video && (
        <div className="mx-auto w-full max-w-[360px] overflow-hidden rounded-2xl border border-border">
          <video
            src={video}
            controls
            playsInline
            className="aspect-[9/16] w-full bg-black"
          />
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {job.artifacts?.video_url && (
          <Button asChild variant="primary" size="sm">
            <a href={downloadUrl(job.id, "video")} download>
              <Download className="h-4 w-4" />
              Video (mp4)
            </a>
          </Button>
        )}
        {job.artifacts?.srt_url && (
          <Button asChild variant="outline" size="sm">
            <a href={downloadUrl(job.id, "srt")} download>
              Captions (srt)
            </a>
          </Button>
        )}
        {job.artifacts?.notes_url && (
          <Button asChild variant="outline" size="sm">
            <a href={downloadUrl(job.id, "notes")} download>
              Notes (md)
            </a>
          </Button>
        )}
        {job.artifacts?.anki_url && (
          <Button asChild variant="outline" size="sm">
            <a href={downloadUrl(job.id, "anki")} download>
              Flashcards (csv)
            </a>
          </Button>
        )}
      </div>

      <div className="flex items-center justify-between pt-2">
        <Link href="/jobs" className="text-sm text-muted hover:text-white">
          See history →
        </Link>
        <Button variant="ghost" size="sm" onClick={onReset}>
          <RotateCcw className="h-4 w-4" />
          Make another
        </Button>
      </div>
    </div>
  );
}
