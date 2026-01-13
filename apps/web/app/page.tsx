"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, FileText, Sparkles, History, Check, X, Download, Play } from "lucide-react";
import Link from "next/link";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ProgressUI } from "@/components/ProgressUI";
import { VideoPlayer } from "@/components/VideoPlayer";
import { useJobHistory } from "@/lib/useJobHistory";

type JobState = "idle" | "uploading" | "processing" | "completed" | "error";

interface JobOptions {
  length_sec: number;
  preset: string;
  caption_style: string;
  voice_id: string;
  export_extras: boolean;
}

export default function Home() {
  const [jobState, setJobState] = useState<JobState>("idle");
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [topic, setTopic] = useState("");
  const [outline, setOutline] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [options, setOptions] = useState<JobOptions>({
    length_sec: 60,
    preset: "BALANCED",
    caption_style: "BOLD",
    voice_id: "default",
    export_extras: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [jobData, setJobData] = useState<any>(null);
  
  const { addJob, updateJob } = useJobHistory();

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && (droppedFile.name.endsWith(".pdf") || droppedFile.name.endsWith(".pptx"))) {
      setFile(droppedFile);
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  }, []);

  const createJob = async (isFileUpload: boolean) => {
    setJobState("uploading");
    setError(null);

    try {
      let response: Response;

      if (isFileUpload && file) {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("options", JSON.stringify(options));

        response = await fetch("/api/jobs", {
          method: "POST",
          body: formData,
        });
      } else {
        response = await fetch("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            topic,
            outline: outline || null,
            options,
          }),
        });
      }

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to create job");
      }

      const data = await response.json();
      setCurrentJobId(data.job_id);
      setJobState("processing");

      // Add to history
      addJob({
        job_id: data.job_id,
        title: isFileUpload ? file?.name || "Uploaded File" : topic,
        created_at: new Date().toISOString(),
        status: "running",
        preset: options.preset,
        length_sec: options.length_sec,
      });

    } catch (err: any) {
      setError(err.message);
      setJobState("error");
    }
  };

  const handleJobComplete = (data: any) => {
    setJobData(data);
    setJobState("completed");
    if (currentJobId) {
      updateJob(currentJobId, { status: data.status });
    }
  };

  const handleJobError = (errorMsg: string) => {
    setError(errorMsg);
    setJobState("error");
    if (currentJobId) {
      updateJob(currentJobId, { status: "failed" });
    }
  };

  const resetForm = () => {
    setJobState("idle");
    setCurrentJobId(null);
    setFile(null);
    setTopic("");
    setOutline("");
    setError(null);
    setJobData(null);
  };

  const exampleTopics = [
    "Intro to linear regression",
    "Photosynthesis for MCAT",
    "French Revolution summary",
    "Python list comprehensions",
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Navbar */}
      <nav className="border-b border-border">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-primary" />
            <span className="text-xl font-bold">BrainRotStudy</span>
          </Link>
          <Link href="/history">
            <Button variant="ghost" className="gap-2">
              <History className="w-4 h-4" />
              History
            </Button>
          </Link>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto px-4 py-12">
        {/* Hero */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-12"
        >
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            Turn slides into a <span className="text-primary">60s study video</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Upload PDF/PPTX or enter a topic. Get a vertical recap with captions, 
            perfect for TikTok-style studying.
          </p>
        </motion.div>

        {/* Main Card */}
        <AnimatePresence mode="wait">
          {jobState === "idle" && (
            <motion.div
              key="form"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle>Create Your Study Video</CardTitle>
                  <CardDescription>
                    Choose your input method and customize your video
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Tabs defaultValue="upload" className="w-full">
                    <TabsList className="grid w-full grid-cols-2 mb-6">
                      <TabsTrigger value="upload" className="gap-2">
                        <Upload className="w-4 h-4" />
                        Upload File
                      </TabsTrigger>
                      <TabsTrigger value="topic" className="gap-2">
                        <FileText className="w-4 h-4" />
                        Enter Topic
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent value="upload">
                      {/* File Upload Zone */}
                      <div
                        className={`dropzone border-2 border-dashed border-border rounded-lg p-12 text-center cursor-pointer transition-all ${
                          file ? "border-primary bg-primary/5" : "hover:border-primary/50"
                        }`}
                        onDrop={handleFileDrop}
                        onDragOver={(e) => e.preventDefault()}
                        onClick={() => document.getElementById("file-input")?.click()}
                      >
                        <input
                          id="file-input"
                          type="file"
                          accept=".pdf,.pptx"
                          className="hidden"
                          onChange={handleFileSelect}
                        />
                        {file ? (
                          <div className="flex items-center justify-center gap-3">
                            <Check className="w-8 h-8 text-green-500" />
                            <div className="text-left">
                              <p className="font-medium">{file.name}</p>
                              <p className="text-sm text-muted-foreground">
                                {(file.size / 1024 / 1024).toFixed(2)} MB
                              </p>
                            </div>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                setFile(null);
                              }}
                            >
                              <X className="w-4 h-4" />
                            </Button>
                          </div>
                        ) : (
                          <div>
                            <Upload className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                            <p className="text-lg font-medium mb-1">
                              Drop your PDF or PPTX here
                            </p>
                            <p className="text-sm text-muted-foreground">
                              or click to browse
                            </p>
                          </div>
                        )}
                      </div>

                      <Button
                        className="w-full mt-6"
                        size="lg"
                        disabled={!file}
                        onClick={() => createJob(true)}
                      >
                        <Sparkles className="w-4 h-4 mr-2" />
                        Generate Video
                      </Button>
                    </TabsContent>

                    <TabsContent value="topic">
                      <div className="space-y-4">
                        <div>
                          <Label htmlFor="topic">Topic</Label>
                          <Input
                            id="topic"
                            placeholder="e.g., Introduction to Machine Learning"
                            value={topic}
                            onChange={(e) => setTopic(e.target.value)}
                            className="mt-1"
                          />
                        </div>

                        <div>
                          <Label htmlFor="outline">Outline (optional)</Label>
                          <textarea
                            id="outline"
                            placeholder="Paste your notes or outline here..."
                            value={outline}
                            onChange={(e) => setOutline(e.target.value)}
                            className="mt-1 w-full h-32 px-3 py-2 rounded-md bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                          />
                        </div>

                        {/* Example chips */}
                        <div>
                          <Label className="text-sm text-muted-foreground">Try an example:</Label>
                          <div className="flex flex-wrap gap-2 mt-2">
                            {exampleTopics.map((example) => (
                              <button
                                key={example}
                                className="px-3 py-1 text-sm rounded-full bg-secondary hover:bg-secondary/80 transition-colors"
                                onClick={() => setTopic(example)}
                              >
                                {example}
                              </button>
                            ))}
                          </div>
                        </div>

                        <Button
                          className="w-full"
                          size="lg"
                          disabled={!topic.trim()}
                          onClick={() => createJob(false)}
                        >
                          <Sparkles className="w-4 h-4 mr-2" />
                          Generate Video
                        </Button>
                      </div>
                    </TabsContent>
                  </Tabs>

                  {/* Advanced Settings */}
                  <div className="mt-8 pt-6 border-t border-border">
                    <button
                      className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                      onClick={() => setShowAdvanced(!showAdvanced)}
                    >
                      <motion.span
                        animate={{ rotate: showAdvanced ? 90 : 0 }}
                        className="text-lg"
                      >
                        ›
                      </motion.span>
                      Advanced Settings
                    </button>

                    <AnimatePresence>
                      {showAdvanced && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <div className="grid md:grid-cols-2 gap-6 mt-4">
                            {/* Length */}
                            <div>
                              <Label>Video Length</Label>
                              <RadioGroup
                                value={String(options.length_sec)}
                                onValueChange={(v) => setOptions({ ...options, length_sec: parseInt(v) })}
                                className="flex gap-4 mt-2"
                              >
                                <div className="flex items-center space-x-2">
                                  <RadioGroupItem value="60" id="60s" />
                                  <Label htmlFor="60s">60 seconds</Label>
                                </div>
                                <div className="flex items-center space-x-2">
                                  <RadioGroupItem value="90" id="90s" />
                                  <Label htmlFor="90s">90 seconds</Label>
                                </div>
                              </RadioGroup>
                            </div>

                            {/* Preset */}
                            <div>
                              <Label>Style Preset</Label>
                              <Select
                                value={options.preset}
                                onValueChange={(v) => setOptions({ ...options, preset: v })}
                              >
                                <SelectTrigger className="mt-2">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="FAST">Fast - Quick cuts, high energy</SelectItem>
                                  <SelectItem value="BALANCED">Balanced - Medium pacing</SelectItem>
                                  <SelectItem value="EXAM">Exam - Slower, clear explanations</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>

                            {/* Caption Style */}
                            <div>
                              <Label>Caption Style</Label>
                              <Select
                                value={options.caption_style}
                                onValueChange={(v) => setOptions({ ...options, caption_style: v })}
                              >
                                <SelectTrigger className="mt-2">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="BOLD">Bold - Large, impactful text</SelectItem>
                                  <SelectItem value="MINIMAL">Minimal - Subtle captions</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>

                            {/* Export Extras */}
                            <div className="flex items-center justify-between">
                              <div>
                                <Label>Export Extras</Label>
                                <p className="text-sm text-muted-foreground">
                                  Generate notes, SRT, and Anki cards
                                </p>
                              </div>
                              <Switch
                                checked={options.export_extras}
                                onCheckedChange={(v) => setOptions({ ...options, export_extras: v })}
                              />
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {(jobState === "uploading" || jobState === "processing") && currentJobId && (
            <motion.div
              key="progress"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <ProgressUI
                jobId={currentJobId}
                onComplete={handleJobComplete}
                onError={handleJobError}
              />
            </motion.div>
          )}

          {jobState === "completed" && jobData && (
            <motion.div
              key="completed"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <VideoPlayer jobData={jobData} />
              <div className="mt-6 text-center">
                <Button variant="outline" onClick={resetForm}>
                  Create Another Video
                </Button>
              </div>
            </motion.div>
          )}

          {jobState === "error" && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <Card className="bg-destructive/10 border-destructive/50">
                <CardContent className="pt-6">
                  <div className="text-center">
                    <X className="w-12 h-12 mx-auto mb-4 text-destructive" />
                    <h3 className="text-lg font-semibold mb-2">Something went wrong</h3>
                    <p className="text-muted-foreground mb-4">{error}</p>
                    <Button onClick={resetForm}>Try Again</Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
