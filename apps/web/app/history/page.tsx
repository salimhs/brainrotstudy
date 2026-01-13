"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { 
  Sparkles, 
  ArrowLeft, 
  Download, 
  Trash2, 
  Clock, 
  Video,
  CheckCircle,
  XCircle,
  Loader2 
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobHistory, HistoryJob } from "@/lib/useJobHistory";

export default function HistoryPage() {
  const { jobs, removeJob, clearHistory } = useJobHistory();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null; // Prevent hydration mismatch
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "succeeded":
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "failed":
        return <XCircle className="w-4 h-4 text-red-500" />;
      case "running":
        return <Loader2 className="w-4 h-4 text-primary animate-spin" />;
      default:
        return <Clock className="w-4 h-4 text-muted-foreground" />;
    }
  };

  const getPresetBadge = (preset: string) => {
    const colors: Record<string, string> = {
      FAST: "bg-orange-500/20 text-orange-400",
      BALANCED: "bg-blue-500/20 text-blue-400",
      EXAM: "bg-green-500/20 text-green-400",
    };
    return (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[preset] || colors.BALANCED}`}>
        {preset}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Navbar */}
      <nav className="border-b border-border">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-primary" />
            <span className="text-xl font-bold">BrainRotStudy</span>
          </Link>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Link href="/">
              <Button variant="ghost" size="icon">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <div>
              <h1 className="text-3xl font-bold">Job History</h1>
              <p className="text-muted-foreground">
                Your previously generated videos
              </p>
            </div>
          </div>
          {jobs.length > 0 && (
            <Button variant="outline" onClick={clearHistory} className="text-destructive">
              Clear All
            </Button>
          )}
        </div>

        {/* Job List */}
        {jobs.length === 0 ? (
          <Card className="bg-card border-border">
            <CardContent className="py-12 text-center">
              <Video className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
              <h3 className="text-lg font-medium mb-2">No videos yet</h3>
              <p className="text-muted-foreground mb-4">
                Create your first study video to see it here
              </p>
              <Button asChild>
                <Link href="/">Create Video</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {jobs.map((job, index) => (
              <motion.div
                key={job.job_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
              >
                <Card className="bg-card border-border hover:border-primary/50 transition-colors">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4 flex-1 min-w-0">
                        {getStatusIcon(job.status)}
                        <div className="flex-1 min-w-0">
                          <h3 className="font-medium truncate">{job.title}</h3>
                          <div className="flex items-center gap-3 text-sm text-muted-foreground">
                            <span>{formatDate(job.created_at)}</span>
                            <span>•</span>
                            <span>{job.length_sec}s</span>
                            {getPresetBadge(job.preset)}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {job.status === "succeeded" && (
                          <Button asChild size="sm" className="gap-1">
                            <a href={`/api/jobs/${job.job_id}/download`} download>
                              <Download className="w-3 h-3" />
                              Download
                            </a>
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => removeJob(job.job_id)}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
