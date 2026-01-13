"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Download, FileText, BookOpen, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface VideoPlayerProps {
  jobData: {
    job_id: string;
    title: string;
    artifacts?: {
      video_url?: string;
      srt_url?: string;
      notes_url?: string;
      anki_url?: string;
    };
  };
}

export function VideoPlayer({ jobData }: VideoPlayerProps) {
  const [showAttribution, setShowAttribution] = useState(false);
  const { job_id, title, artifacts } = jobData;

  const videoUrl = artifacts?.video_url ? `/api${artifacts.video_url}` : null;

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>🎉 {title}</span>
          <span className="text-sm font-normal text-muted-foreground">
            Video Ready!
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Video Player */}
        {videoUrl && (
          <div className="relative aspect-[9/16] max-h-[600px] mx-auto bg-black rounded-lg overflow-hidden">
            <video
              src={videoUrl}
              controls
              className="w-full h-full object-contain"
              poster="/video-poster.png"
            >
              Your browser does not support the video tag.
            </video>
          </div>
        )}

        {/* Download Buttons */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {videoUrl && (
            <Button asChild className="gap-2">
              <a href={videoUrl} download={`${title}.mp4`}>
                <Download className="w-4 h-4" />
                Download MP4
              </a>
            </Button>
          )}

          {artifacts?.srt_url && (
            <Button variant="outline" asChild className="gap-2">
              <a href={`/api${artifacts.srt_url}`} download>
                <FileText className="w-4 h-4" />
                Download SRT
              </a>
            </Button>
          )}

          {artifacts?.notes_url && (
            <Button variant="outline" asChild className="gap-2">
              <a href={`/api${artifacts.notes_url}`} download>
                <BookOpen className="w-4 h-4" />
                Notes (MD)
              </a>
            </Button>
          )}

          {artifacts?.anki_url && (
            <Button variant="outline" asChild className="gap-2">
              <a href={`/api${artifacts.anki_url}`} download>
                <BookOpen className="w-4 h-4" />
                Anki Cards
              </a>
            </Button>
          )}
        </div>

        {/* Attribution Accordion */}
        <div className="border-t border-border pt-4">
          <button
            onClick={() => setShowAttribution(!showAttribution)}
            className="flex items-center justify-between w-full text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <span>Visual Attribution & Licenses</span>
            {showAttribution ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>

          {showAttribution && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              className="mt-4 space-y-2"
            >
              <p className="text-sm text-muted-foreground">
                All visuals used in this video are from Creative Commons or public domain sources.
              </p>
              <div className="bg-secondary/50 rounded-lg p-3 text-sm">
                <p className="text-muted-foreground">
                  Attribution details are available in the assets manifest for this job.
                </p>
                <a
                  href="https://openverse.org"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-primary hover:underline mt-2"
                >
                  <ExternalLink className="w-3 h-3" />
                  Learn more about Openverse
                </a>
              </div>
            </motion.div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
