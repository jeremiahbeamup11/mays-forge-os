/**
 * API client for the Mays Forge OS backend.
 *
 * Centralizes all fetch calls so every component uses consistent
 * error handling, auth headers, and base URL configuration.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface FileRecord {
  id: string;
  organization_id: string;
  uploaded_by: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  kind: "csv" | "pdf" | "image" | "geojson" | "other";
  processing_status: "pending" | "parsing" | "analyzing" | "complete" | "failed";
  processing_error: string | null;
  analysis: AnalysisPayload | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisPayload {
  result: CsvAnalysis | ImageAnalysis;
  metadata: AnalysisMetadata;
  csv_summary?: Record<string, unknown>;
}

export interface AnalysisMetadata {
  prompt_version: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  duration_seconds: number;
  estimated_cost_usd: number;
}

// CSV analysis types
export interface CsvAnalysis {
  summary: string;
  findings: Finding[];
  recommendations: Recommendation[];
  data_quality: DataQuality;
}

export interface Finding {
  title: string;
  detail: string;
  confidence: "confirmed" | "inferred";
  category: string;
}

export interface Recommendation {
  action: string;
  rationale: string;
  priority: "critical" | "high" | "medium" | "low";
  estimated_impact: string;
}

export interface DataQuality {
  overall_quality: "excellent" | "good" | "fair" | "poor";
  issues: string[];
}

// Image analysis types
export interface ImageAnalysis {
  scene_description: string;
  site_type: string;
  observations: Observation[];
  sustainability_opportunities: Opportunity[];
  condition_assessment: ConditionAssessment;
  estimated_characteristics?: EstimatedCharacteristics;
}

export interface Observation {
  category: string;
  detail: string;
  planning_relevance: string;
}

export interface Opportunity {
  opportunity: string;
  rationale: string;
  feasibility: "high" | "medium" | "low" | "needs_investigation";
}

export interface ConditionAssessment {
  overall_condition: "excellent" | "good" | "fair" | "poor" | "critical";
  details: string;
}

export interface EstimatedCharacteristics {
  estimated_lot_size?: string;
  vegetation_coverage_pct?: number;
  impervious_surface_pct?: number;
}

export interface FileUploadResponse {
  id: string;
  organization_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  kind: string;
  processing_status: string;
  created_at: string;
}

/**
 * Upload a file to an organization and trigger AI analysis.
 */
export async function uploadFile(
  orgId: string,
  file: File,
  token: string
): Promise<FileUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/v1/organizations/${orgId}/files`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: "Upload failed" }));
    throw new Error(err.detail || err.message || `Upload failed (${res.status})`);
  }

  return res.json();
}

/**
 * Fetch a single file's metadata + analysis.
 */
export async function getFile(
  orgId: string,
  fileId: string,
  token: string
): Promise<FileRecord> {
  const res = await fetch(
    `${API_BASE}/api/v1/organizations/${orgId}/files/${fileId}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );

  if (!res.ok) {
    throw new Error(`Failed to fetch file (${res.status})`);
  }

  return res.json();
}

/**
 * Poll a file until analysis is complete or failed.
 * Returns the final file record.
 */
export async function pollFileUntilDone(
  orgId: string,
  fileId: string,
  token: string,
  intervalMs = 2000,
  maxAttempts = 60
): Promise<FileRecord> {
  for (let i = 0; i < maxAttempts; i++) {
    const file = await getFile(orgId, fileId, token);
    if (file.processing_status === "complete" || file.processing_status === "failed") {
      return file;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("Analysis timed out after 2 minutes.");
}
