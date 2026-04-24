"use client";

import { useCallback, useState } from "react";
import { Upload, Sparkles, FileText, Loader2, X } from "lucide-react";
import {
  createFileJob,
  createTopicJob,
  defaultOptions,
  type CaptionStyle,
  type JobOptions,
  type JobView,
  type Pacing,
  type Vibe,
} from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";

const SAMPLE_TOPICS = [
  "Photosynthesis for MCAT",
  "Linear regression intuition",
  "French Revolution in 60s",
  "Python list comprehensions",
];

export function CreateForm({ onCreated }: { onCreated: (job: JobView) => void }) {
  const [topic, setTopic] = useState("");
  const [outline, setOutline] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<JobOptions>(defaultOptions);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const onFile = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return;
    const f = files[0];
    const lower = f.name.toLowerCase();
    if (![".pdf", ".pptx", ".txt", ".md"].some((ext) => lower.endsWith(ext))) {
      setError("File must be a .pdf, .pptx, .txt or .md");
      return;
    }
    setError(null);
    setFile(f);
  }, []);

  async function submitTopic() {
    if (!topic.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const job = await createTopicJob(topic.trim(), outline.trim() || null, options);
      onCreated(job);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function submitFile() {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      const job = await createFileJob(file, options);
      onCreated(job);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card p-6 w-full max-w-xl">
      <Tabs defaultValue="topic" className="w-full">
        <TabsList className="mb-5 w-full">
          <TabsTrigger value="topic" className="flex-1">
            <FileText className="h-4 w-4" /> Topic
          </TabsTrigger>
          <TabsTrigger value="file" className="flex-1">
            <Upload className="h-4 w-4" /> Upload
          </TabsTrigger>
        </TabsList>

        <TabsContent value="topic" className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="topic">Topic</Label>
            <Input
              id="topic"
              placeholder="e.g. Krebs cycle for biology midterm"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="outline">Outline (optional)</Label>
            <Textarea
              id="outline"
              placeholder="Paste notes, bullet points, or a reading…"
              value={outline}
              onChange={(e) => setOutline(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {SAMPLE_TOPICS.map((sample) => (
              <button
                key={sample}
                type="button"
                onClick={() => setTopic(sample)}
                className="rounded-full border border-border bg-panel px-3 py-1 text-xs text-muted hover:text-white"
                disabled={submitting}
              >
                {sample}
              </button>
            ))}
          </div>
          <Button
            size="lg"
            className="w-full"
            disabled={!topic.trim() || submitting}
            onClick={submitTopic}
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Generate video
          </Button>
        </TabsContent>

        <TabsContent value="file" className="space-y-4">
          <label
            htmlFor="file-input"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              onFile(e.dataTransfer.files);
            }}
            className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border bg-panel px-6 py-10 text-center cursor-pointer hover:border-accent/60 transition-colors"
          >
            <Upload className="h-8 w-8 text-muted" />
            <p className="text-sm font-medium">Drop a .pdf, .pptx, .txt, or .md</p>
            <p className="text-xs text-muted">or click to browse</p>
            <input
              id="file-input"
              type="file"
              accept=".pdf,.pptx,.txt,.md"
              className="hidden"
              onChange={(e) => onFile(e.target.files)}
              disabled={submitting}
            />
          </label>

          {file && (
            <div className="flex items-center justify-between rounded-lg border border-border bg-panel px-3 py-2 text-sm">
              <span className="truncate">
                <FileText className="inline h-4 w-4 text-muted mr-2" />
                {file.name}
                <span className="text-muted"> · {(file.size / 1024 / 1024).toFixed(1)} MB</span>
              </span>
              <button
                type="button"
                onClick={() => setFile(null)}
                className="text-muted hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          <Button
            size="lg"
            className="w-full"
            disabled={!file || submitting}
            onClick={submitFile}
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Generate video
          </Button>
        </TabsContent>
      </Tabs>

      <div className="mt-6 border-t border-border pt-5">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-xs font-medium text-muted hover:text-white"
        >
          {showAdvanced ? "Hide" : "Show"} advanced options
        </button>
        {showAdvanced && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Length</Label>
              <Select
                value={String(options.length_sec)}
                onValueChange={(v) => setOptions({ ...options, length_sec: Number(v) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">30 seconds</SelectItem>
                  <SelectItem value="45">45 seconds</SelectItem>
                  <SelectItem value="60">60 seconds</SelectItem>
                  <SelectItem value="90">90 seconds</SelectItem>
                  <SelectItem value="120">2 minutes</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Pacing</Label>
              <Select
                value={options.pacing}
                onValueChange={(v) => setOptions({ ...options, pacing: v as Pacing })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="fast">Fast — high energy</SelectItem>
                  <SelectItem value="balanced">Balanced</SelectItem>
                  <SelectItem value="chill">Chill — slower, clearer</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Vibe</Label>
              <Select
                value={options.vibe}
                onValueChange={(v) => setOptions({ ...options, vibe: v as Vibe })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="unhinged">Unhinged</SelectItem>
                  <SelectItem value="asmr">ASMR</SelectItem>
                  <SelectItem value="gossip">Gossip</SelectItem>
                  <SelectItem value="professor">Professor</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Captions</Label>
              <Select
                value={options.caption_style}
                onValueChange={(v) =>
                  setOptions({ ...options, caption_style: v as CaptionStyle })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="karaoke">Karaoke (bold)</SelectItem>
                  <SelectItem value="pop">Pop</SelectItem>
                  <SelectItem value="minimal">Minimal</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border bg-panel px-3 py-2 sm:col-span-2">
              <div>
                <Label className="text-sm">Export extras</Label>
                <p className="text-xs text-muted">Notes (md), captions (srt), flashcards (csv)</p>
              </div>
              <Switch
                checked={options.export_extras}
                onCheckedChange={(v) => setOptions({ ...options, export_extras: v })}
              />
            </div>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-4 text-sm text-danger">{error}</p>
      )}
    </div>
  );
}
