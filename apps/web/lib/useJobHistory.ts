"use client";

import { useState, useEffect, useCallback } from "react";

export interface HistoryJob {
  job_id: string;
  title: string;
  created_at: string;
  status: string;
  preset: string;
  length_sec: number;
}

const STORAGE_KEY = "brainrotstudy_history";

export function useJobHistory() {
  const [jobs, setJobs] = useState<HistoryJob[]>([]);

  // Load from localStorage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        try {
          setJobs(JSON.parse(stored));
        } catch (e) {
          console.error("Failed to parse job history:", e);
        }
      }
    }
  }, []);

  // Save to localStorage when jobs change
  useEffect(() => {
    if (typeof window !== "undefined" && jobs.length > 0) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
    }
  }, [jobs]);

  const addJob = useCallback((job: HistoryJob) => {
    setJobs((prev) => [job, ...prev.slice(0, 49)]); // Keep max 50 jobs
  }, []);

  const updateJob = useCallback((jobId: string, updates: Partial<HistoryJob>) => {
    setJobs((prev) =>
      prev.map((job) =>
        job.job_id === jobId ? { ...job, ...updates } : job
      )
    );
  }, []);

  const removeJob = useCallback((jobId: string) => {
    setJobs((prev) => prev.filter((job) => job.job_id !== jobId));
    // Also try to delete from server
    fetch(`/api/jobs/${jobId}`, { method: "DELETE" }).catch(() => {});
  }, []);

  const clearHistory = useCallback(() => {
    setJobs([]);
    if (typeof window !== "undefined") {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  return {
    jobs,
    addJob,
    updateJob,
    removeJob,
    clearHistory,
  };
}
