"use client";

import { useState, useCallback, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import {
  uploadFile,
  pollFileUntilDone,
  type FileRecord,
  type CsvAnalysis,
  type ImageAnalysis,
  type Blueprint,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";
import type { Session } from "@supabase/supabase-js";

const DEMO_ORG_ID = process.env.NEXT_PUBLIC_DEMO_ORG_ID || "";

type UploadState = "idle" | "uploading" | "analyzing" | "complete" | "error";

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);

  const [state, setState] = useState<UploadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<FileRecord | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Check for existing session on mount
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s);
      setAuthLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);

    const { error: err } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (err) {
      setAuthError(err.message);
    }
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setSession(null);
    setState("idle");
    setFile(null);
  };

  const token = session?.access_token || "";

  const handleUpload = useCallback(
    async (selectedFile: File) => {
      if (!token || !DEMO_ORG_ID) {
        setError("Not authenticated or org not configured.");
        setState("error");
        return;
      }

      setState("uploading");
      setError(null);
      setFile(null);

      try {
        const uploaded = await uploadFile(DEMO_ORG_ID, selectedFile, token);
        setState("analyzing");

        const result = await pollFileUntilDone(DEMO_ORG_ID, uploaded.id, token);

        setFile(result);
        setState(result.processing_status === "complete" ? "complete" : "error");
        if (result.processing_status === "failed") {
          setError(result.processing_error || "Analysis failed.");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
        setState("error");
      }
    },
    [token]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) handleUpload(droppedFile);
    },
    [handleUpload]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files?.[0];
      if (selected) handleUpload(selected);
    },
    [handleUpload]
  );

  const reset = () => {
    setState("idle");
    setError(null);
    setFile(null);
  };

  // Loading state
  if (authLoading) {
    return (
      <main className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </main>
    );
  }

  // Login screen
  if (!session) {
    return (
      <main className="min-h-screen bg-background">
        <div className="border-b">
          <div className="mx-auto max-w-5xl px-6 py-4">
            <h1 className="text-xl font-bold tracking-tight">Mays Forge OS</h1>
            <p className="text-sm text-muted-foreground">
              Urban sustainability intelligence
            </p>
          </div>
        </div>

        <div className="mx-auto max-w-md px-6 py-16">
          <Card>
            <CardHeader>
              <CardTitle>Sign in</CardTitle>
              <p className="text-sm text-muted-foreground">
                Enter your credentials to access the platform.
              </p>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium" htmlFor="email">
                    Email
                  </label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    placeholder="you@example.com"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium" htmlFor="password">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    placeholder="••••••••"
                  />
                </div>

                {authError && (
                  <div className="p-3 rounded-md bg-destructive/10 text-destructive text-sm">
                    {authError}
                  </div>
                )}

                <Button className="w-full" onClick={handleLogin}>
                  Sign In
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    );
  }

  // Authenticated — main app
  return (
    <main className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b">
        <div className="mx-auto max-w-5xl px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Mays Forge OS</h1>
            <p className="text-sm text-muted-foreground">
              Urban sustainability intelligence
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">
              {session.user.email}
            </span>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              Sign Out
            </Button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-5xl px-6 py-8 space-y-8">
        {/* Upload Zone */}
        {(state === "idle" || state === "error") && (
          <Card>
            <CardHeader>
              <CardTitle>Analyze City Data</CardTitle>
              <p className="text-sm text-muted-foreground">
                Upload a CSV of municipal data or a photo of a site for
                AI-powered analysis.
              </p>
            </CardHeader>
            <CardContent>
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                className={`
                  border-2 border-dashed rounded-lg p-12 text-center
                  transition-colors cursor-pointer
                  ${
                    dragOver
                      ? "border-primary bg-primary/5"
                      : "border-muted-foreground/25 hover:border-primary/50"
                  }
                `}
              >
                <div className="space-y-3">
                  <div className="text-4xl">📊</div>
                  <div>
                    <p className="font-medium">
                      Drop a file here, or click to browse
                    </p>
                    <p className="text-sm text-muted-foreground mt-1">
                      CSV, PDF, JPG, PNG, WebP, or GeoJSON — up to 25 MB
                    </p>
                  </div>
                  <label>
                    <input
                      type="file"
                      className="hidden"
                      accept=".csv,.pdf,.jpg,.jpeg,.png,.webp,.geojson,.json,.txt"
                      onChange={handleFileSelect}
                    />
                    <Button variant="outline" className="mt-2" asChild>
                      <span>Choose File</span>
                    </Button>
                  </label>
                </div>
              </div>

              {error && (
                <div className="mt-4 p-3 rounded-md bg-destructive/10 text-destructive text-sm">
                  {error}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Progress */}
        {(state === "uploading" || state === "analyzing") && (
          <Card>
            <CardContent className="py-16 text-center space-y-4">
              <div className="text-4xl animate-pulse">
                {state === "uploading" ? "📤" : "🔬"}
              </div>
              <div>
                <p className="font-medium text-lg">
                  {state === "uploading"
                    ? "Uploading file..."
                    : "AI is analyzing your data..."}
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  {state === "analyzing"
                    ? "This typically takes 30-60 seconds. Claude is examining your data for insights."
                    : "Sending to Mays Forge OS..."}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Results */}
        {state === "complete" && file?.analysis && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Analysis Complete</h2>
                <p className="text-sm text-muted-foreground">
                  {file.original_filename} —{" "}
                  {file.analysis.metadata.duration_seconds}s •{" "}
                  ${file.analysis.metadata.estimated_cost_usd.toFixed(4)} •{" "}
                  {file.analysis.metadata.model}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="default"
                  onClick={() => {
                    const url = `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/api/v1/organizations/${DEMO_ORG_ID}/files/${file.id}/report`;
                    fetch(url, {
                      headers: { Authorization: `Bearer ${token}` },
                    })
                      .then((res) => res.blob())
                      .then((blob) => {
                        const blobUrl = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = blobUrl;
                        a.download = `${file.original_filename.replace(/\.[^/.]+$/, "")}_report.pdf`;
                        a.click();
                        URL.revokeObjectURL(blobUrl);
                      });
                  }}
                >
                  Download Report
                </Button>
                <Button variant="outline" onClick={reset}>
                  Analyze Another
                </Button>
              </div>
            </div>

            {file.kind === "csv" ? (
              <CsvResults analysis={file.analysis.result as CsvAnalysis} />
            ) : file.kind === "image" ? (
              <>
                <ImageResults analysis={file.analysis.result as ImageAnalysis} />

                {file.analysis.blueprint && (
                  <BlueprintResults blueprint={file.analysis.blueprint} />
                )}
              </>
            ) : (
              <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                  Analysis view not yet available for {file.kind} files.
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

// ============================================================================
// CSV Results Component
// ============================================================================

function CsvResults({ analysis }: { analysis: CsvAnalysis }) {
  return (
    <Tabs defaultValue="findings" className="space-y-4">
      <TabsList>
        <TabsTrigger value="findings">
          Findings ({analysis.findings.length})
        </TabsTrigger>
        <TabsTrigger value="recommendations">
          Recommendations ({analysis.recommendations.length})
        </TabsTrigger>
        <TabsTrigger value="quality">Data Quality</TabsTrigger>
      </TabsList>

      <Card>
        <CardContent className="pt-6">
          <p className="text-sm leading-relaxed">{analysis.summary}</p>
        </CardContent>
      </Card>

      <TabsContent value="findings" className="space-y-3">
        {analysis.findings.map((f, i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <div className="flex gap-2 shrink-0 pt-0.5">
                  <Badge
                    variant={
                      f.confidence === "confirmed" ? "default" : "secondary"
                    }
                    className="text-xs"
                  >
                    {f.confidence}
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {f.category}
                  </Badge>
                </div>
                <div className="space-y-1 min-w-0">
                  <h3 className="font-medium text-sm">{f.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {f.detail}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </TabsContent>

      <TabsContent value="recommendations" className="space-y-3">
        {analysis.recommendations.map((r, i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <Badge
                  className={`text-xs shrink-0 ${priorityColor(r.priority)}`}
                >
                  {r.priority}
                </Badge>
                <div className="space-y-2 min-w-0">
                  <h3 className="font-medium text-sm">{r.action}</h3>
                  <p className="text-sm text-muted-foreground">
                    {r.rationale}
                  </p>
                  <Separator />
                  <p className="text-xs text-muted-foreground">
                    <span className="font-medium">Estimated impact:</span>{" "}
                    {r.estimated_impact}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </TabsContent>

      <TabsContent value="quality">
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Overall Quality:</span>
              <Badge
                variant={
                  analysis.data_quality.overall_quality === "excellent" ||
                  analysis.data_quality.overall_quality === "good"
                    ? "default"
                    : "secondary"
                }
              >
                {analysis.data_quality.overall_quality}
              </Badge>
            </div>
            {analysis.data_quality.issues.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">Issues noted:</p>
                <ul className="space-y-2">
                  {analysis.data_quality.issues.map((issue, i) => (
                    <li
                      key={i}
                      className="text-sm text-muted-foreground pl-4 border-l-2 border-muted"
                    >
                      {issue}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}

// ============================================================================
// Image Results Component
// ============================================================================

function ImageResults({ analysis }: { analysis: ImageAnalysis }) {
  return (
    <Tabs defaultValue="observations" className="space-y-4">
      <TabsList>
        <TabsTrigger value="observations">
          Observations ({analysis.observations.length})
        </TabsTrigger>
        <TabsTrigger value="opportunities">
          Sustainability ({analysis.sustainability_opportunities.length})
        </TabsTrigger>
        <TabsTrigger value="condition">Condition</TabsTrigger>
      </TabsList>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 mb-2">
            <Badge variant="outline">
              {analysis.site_type.replace(/_/g, " ")}
            </Badge>
            <Badge
              className={conditionColor(
                analysis.condition_assessment.overall_condition
              )}
            >
              {analysis.condition_assessment.overall_condition}
            </Badge>
          </div>
          <p className="text-sm leading-relaxed">
            {analysis.scene_description}
          </p>
        </CardContent>
      </Card>

      <TabsContent value="observations" className="space-y-3">
        {analysis.observations.map((obs, i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <Badge variant="outline" className="text-xs shrink-0">
                  {obs.category.replace(/_/g, " ")}
                </Badge>
                <div className="space-y-2 min-w-0">
                  <p className="text-sm">{obs.detail}</p>
                  <p className="text-xs text-muted-foreground">
                    <span className="font-medium">Planning relevance:</span>{" "}
                    {obs.planning_relevance}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </TabsContent>

      <TabsContent value="opportunities" className="space-y-3">
        {analysis.sustainability_opportunities.map((opp, i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <Badge
                  className={`text-xs shrink-0 ${feasibilityColor(opp.feasibility)}`}
                >
                  {opp.feasibility.replace(/_/g, " ")}
                </Badge>
                <div className="space-y-1 min-w-0">
                  <h3 className="font-medium text-sm">{opp.opportunity}</h3>
                  <p className="text-sm text-muted-foreground">
                    {opp.rationale}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </TabsContent>

      <TabsContent value="condition">
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Condition:</span>
              <Badge
                className={conditionColor(
                  analysis.condition_assessment.overall_condition
                )}
              >
                {analysis.condition_assessment.overall_condition}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {analysis.condition_assessment.details}
            </p>

            {analysis.estimated_characteristics && (
              <>
                <Separator />
                <div className="grid grid-cols-3 gap-4">
                  {analysis.estimated_characteristics.estimated_lot_size && (
                    <div>
                      <p className="text-xs text-muted-foreground">Lot Size</p>
                      <p className="text-sm font-medium">
                        {analysis.estimated_characteristics.estimated_lot_size}
                      </p>
                    </div>
                  )}
                  {analysis.estimated_characteristics
                    .vegetation_coverage_pct != null && (
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Vegetation
                      </p>
                      <p className="text-sm font-medium">
                        {
                          analysis.estimated_characteristics
                            .vegetation_coverage_pct
                        }
                        %
                      </p>
                    </div>
                  )}
                  {analysis.estimated_characteristics
                    .impervious_surface_pct != null && (
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Impervious Surface
                      </p>
                      <p className="text-sm font-medium">
                        {
                          analysis.estimated_characteristics
                            .impervious_surface_pct
                        }
                        %
                      </p>
                    </div>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}
// ============================================================================
// Blueprint Results Component
// ============================================================================

function BlueprintResults({ blueprint }: { blueprint: Blueprint }) {
  return (
    <div className="space-y-4">
      <Separator />
      <div>
        <h2 className="text-lg font-semibold">{blueprint.concept_name}</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Redevelopment Blueprint • {blueprint.estimated_total_cost}
        </p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <p className="text-sm leading-relaxed">{blueprint.vision_statement}</p>
        </CardContent>
      </Card>

      <Tabs defaultValue="phases" className="space-y-4">
        <TabsList>
          <TabsTrigger value="phases">
            Phases ({blueprint.phases.length})
          </TabsTrigger>
          <TabsTrigger value="sustainability">
            Sustainability ({blueprint.sustainability_features.length})
          </TabsTrigger>
          <TabsTrigger value="funding">Funding</TabsTrigger>
        </TabsList>

        <TabsContent value="phases" className="space-y-3">
          {blueprint.phases.map((phase) => (
            <Card key={phase.phase_number}>
              <CardContent className="pt-6">
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      Phase {phase.phase_number}
                    </Badge>
                    <span className="font-medium text-sm">{phase.name}</span>
                    <span className="text-xs text-muted-foreground ml-auto">
                      {phase.timeline} • {phase.estimated_cost}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {phase.description}
                  </p>
                  <ul className="space-y-1">
                    {phase.key_elements.map((elem, i) => (
                      <li
                        key={i}
                        className="text-sm text-muted-foreground pl-4 border-l-2 border-muted"
                      >
                        {elem}
                      </li>
                    ))}
                  </ul>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="sustainability" className="space-y-3">
          {blueprint.sustainability_features.map((sf, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <Badge variant="outline" className="text-xs shrink-0">
                    Phase {sf.phase}
                  </Badge>
                  <div className="space-y-1 min-w-0">
                    <h3 className="font-medium text-sm">{sf.feature}</h3>
                    <p className="text-sm text-muted-foreground">{sf.benefit}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="funding">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="space-y-3">
                {blueprint.funding_strategy.sources.map((src, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <Badge
                      className={`text-xs shrink-0 ${
                        src.likelihood === "high"
                          ? "bg-green-600 text-white"
                          : src.likelihood === "medium"
                            ? "bg-blue-500 text-white"
                            : "bg-slate-400 text-white"
                      }`}
                    >
                      {src.likelihood}
                    </Badge>
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{src.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {src.amount}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
              <Separator />
              <div>
                <p className="text-sm font-medium mb-1">Funding Strategy</p>
                <p className="text-sm text-muted-foreground">
                  {blueprint.funding_strategy.approach}
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ============================================================================
// Color helpers
// ============================================================================

function priorityColor(priority: string): string {
  switch (priority) {
    case "critical":
      return "bg-red-600 text-white hover:bg-red-700";
    case "high":
      return "bg-orange-500 text-white hover:bg-orange-600";
    case "medium":
      return "bg-yellow-500 text-black hover:bg-yellow-600";
    case "low":
      return "bg-slate-400 text-white hover:bg-slate-500";
    default:
      return "";
  }
}

function feasibilityColor(feasibility: string): string {
  switch (feasibility) {
    case "high":
      return "bg-green-600 text-white hover:bg-green-700";
    case "medium":
      return "bg-blue-500 text-white hover:bg-blue-600";
    case "low":
      return "bg-slate-400 text-white hover:bg-slate-500";
    case "needs_investigation":
      return "bg-amber-500 text-black hover:bg-amber-600";
    default:
      return "";
  }
}

function conditionColor(condition: string): string {
  switch (condition) {
    case "excellent":
      return "bg-green-600 text-white";
    case "good":
      return "bg-green-500 text-white";
    case "fair":
      return "bg-yellow-500 text-black";
    case "poor":
      return "bg-orange-500 text-white";
    case "critical":
      return "bg-red-600 text-white";
    default:
      return "";
  }
}
