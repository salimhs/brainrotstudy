"use client";

import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import { Check, Loader2, FileSearch, Brain, Layout, Image, Mic, Captions, Film, CheckCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ProgressUIProps {
  jobId: string;
  onComplete: (data: any) => void;
  onError: (error: string) => void;
}

interface StageInfo {
  key: string;
  label: string;
  icon: React.ReactNode;
}

const stages: StageInfo[] = [
  { key: "extract", label: "Extracting content", icon: <FileSearch className="w-4 h-4" /> },
  { key: "script", label: "Writing script", icon: <Brain className="w-4 h-4" /> },
  { key: "timeline", label: "Building timeline", icon: <Layout className="w-4 h-4" /> },
  { key: "assets", label: "Finding visuals", icon: <Image className="w-4 h-4" /> },
  { key: "voice", label: "Generating voice", icon: <Mic className="w-4 h-4" /> },
  { key: "captions", label: "Syncing captions", icon: <Captions className="w-4 h-4" /> },
  { key: "render", label: "Rendering video", icon: <Film className="w-4 h-4" /> },
  { key: "finalize", label: "Finalizing", icon: <CheckCircle className="w-4 h-4" /> },
];

export function ProgressUI({ jobId, onComplete, onError }: ProgressUIProps) {
  const [currentStage, setCurrentStage] = useState<string>("extract");
  const [progress, setProgress] = useState(0);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [status, setStatus] = useState<string>("running");
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Start SSE connection
    const connectSSE = () => {
      const eventSource = new EventSource(`/api/jobs/${jobId}/events`);
      eventSourceRef.current = eventSource;

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setCurrentStage(data.stage || "extract");
          setProgress(data.progress_pct || 0);
          if (data.log_tail) {
            setLogLines(data.log_tail);
          }
        } catch (e) {
          console.error("Failed to parse SSE event:", e);
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        // Fallback to polling
        startPolling();
      };
    };

    // Fallback polling
    const startPolling = () => {
      if (pollIntervalRef.current) return;
      
      pollIntervalRef.current = setInterval(async () => {
        try {
          const response = await fetch(`/api/jobs/${jobId}`);
          if (response.ok) {
            const data = await response.json();
            setCurrentStage(data.stage || "extract");
            setProgress(data.progress_pct || 0);
            setStatus(data.status);

            if (data.status === "succeeded") {
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
              }
              onComplete(data);
            } else if (data.status === "failed") {
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
              }
              onError(data.error_message || "Job failed");
            }
          }
        } catch (e) {
          console.error("Polling error:", e);
        }
      }, 2000);
    };

    connectSSE();

    // Also start polling as backup
    setTimeout(startPolling, 5000);

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [jobId, onComplete, onError]);

  const currentStageIndex = stages.findIndex((s) => s.key === currentStage);

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin text-primary" />
          Generating Your Video
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Progress bar */}
        <div className="relative h-3 bg-secondary rounded-full overflow-hidden">
          <motion.div
            className="h-full progress-bar-animated"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">
            {stages[currentStageIndex]?.label || "Processing..."}
          </span>
          <span className="font-medium">{progress}%</span>
        </div>

        {/* Stage checklist */}
        <div className="grid gap-2">
          {stages.map((stage, index) => {
            const isComplete = index < currentStageIndex;
            const isCurrent = index === currentStageIndex;
            const isPending = index > currentStageIndex;

            return (
              <motion.div
                key={stage.key}
                className={`flex items-center gap-3 p-3 rounded-lg transition-colors ${
                  isCurrent
                    ? "bg-primary/10 border border-primary/30"
                    : isComplete
                    ? "bg-green-500/10"
                    : "bg-secondary/50"
                }`}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
              >
                <div
                  className={`flex items-center justify-center w-8 h-8 rounded-full ${
                    isComplete
                      ? "bg-green-500 text-white"
                      : isCurrent
                      ? "bg-primary text-white"
                      : "bg-secondary text-muted-foreground"
                  }`}
                >
                  {isComplete ? (
                    <Check className="w-4 h-4" />
                  ) : isCurrent ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    stage.icon
                  )}
                </div>
                <span
                  className={`font-medium ${
                    isPending ? "text-muted-foreground" : "text-foreground"
                  }`}
                >
                  {stage.label}
                </span>
              </motion.div>
            );
          })}
        </div>

        {/* Log tail */}
        {logLines.length > 0 && (
          <div className="mt-4">
            <h4 className="text-sm font-medium mb-2 text-muted-foreground">
              Processing Log
            </h4>
            <div className="bg-secondary/50 rounded-lg p-3 max-h-32 overflow-y-auto log-tail">
              {logLines.map((line, index) => (
                <div key={index} className="log-line text-xs text-muted-foreground">
                  {line}
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
