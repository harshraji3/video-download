import { useState } from "react";

// ─── CONFIG ──────────────────────────────────────────────────────────────────
// Development: Use localhost. Change to your production URL when deploying.
const FUNCTION_BASE_URL = "http://localhost:8000";

const API = {
  process: `${FUNCTION_BASE_URL}/process`,
  videos:  `${FUNCTION_BASE_URL}/videos`,
  health:  `${FUNCTION_BASE_URL}/health`,
  updateCsv: `${FUNCTION_BASE_URL}/update-csv`,
};

// ─── MOCK DATA (fallback if API is blocked) ───────────────────────────────────
const MOCK_RESULT = {
  file_id: "VJOncology_ASCO_Filippos_Koinis_demo",
  title: "ASCO 2025 — Cancer-related cognitive impairment and adjuvant chemotherapy",
  cancer_indications: ["Breast Cancer", "Colorectal Cancer"],
  drug_generic_names: ["Taxane", "Oxaliplatin"],
  drug_brand_names: ["N/A"],
  biomarker_context: ["N/A"],
  trial_names: ["N/A"],
  speakers: [{ name: "Dr. Filippos Koinis, MD, PhD", affiliation: "University of Thessaly" }],
  content_format: "Clinical Trial Results",
  video_summary: "Dr. Filippos Koinis presents findings from a prospective study on early cancer-related cognitive impairment (CRCI) and its impact on adjuvant chemotherapy delivery in early-stage breast and colorectal cancer patients.",
  confidence_score: 0.85,
  confidence_label: "good",
  duration_minutes: 5.3,
  video_language: "en",
  processed_date: new Date().toISOString(),
  metadata_url: "https://aivideosearch.blob.core.windows.net/media-files/metadata/demo.json",
};

// ─── HELPERS ─────────────────────────────────────────────────────────────────
function ConfidenceBadge({ label, score }) {
  const colors = {
    good:     { bg: "#E1F5EE", border: "#5DCAA5", text: "#085041" },
    marginal: { bg: "#FAEEDA", border: "#EF9F27", text: "#633806" },
    poor:     { bg: "#FAECE7", border: "#F0997B", text: "#712B13" },
  };
  const c = colors[label] || colors.poor;
  return (
    <span style={{
      background: c.bg, border: `0.5px solid ${c.border}`, color: c.text,
      borderRadius: 99, padding: "2px 10px", fontSize: 11, fontWeight: 500,
    }}>
      {label} · {Math.round(score * 100)}%
    </span>
  );
}

function Tag({ children, color = "purple" }) {
  const colors = {
    purple: { bg: "#EEEDFE", border: "#AFA9EC", text: "#3C3489" },
    teal:   { bg: "#E1F5EE", border: "#5DCAA5", text: "#085041" },
    blue:   { bg: "#E6F1FB", border: "#85B7EB", text: "#0C447C" },
    gray:   { bg: "#F1EFE8", border: "#C8C6BE", text: "#444441" },
  };
  const c = colors[color];
  return (
    <span style={{
      background: c.bg, border: `0.5px solid ${c.border}`, color: c.text,
      borderRadius: 99, padding: "3px 10px", fontSize: 11, display: "inline-block",
      margin: "2px 3px 2px 0",
    }}>
      {children}
    </span>
  );
}

function MetaRow({ label, children }) {
  return (
    <div style={{ display: "flex", gap: 12, padding: "8px 0", borderBottom: "0.5px solid #ECEAE3", alignItems: "flex-start" }}>
      <span style={{ fontSize: 11, color: "#888780", width: 140, flexShrink: 0, paddingTop: 3, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>
      <div style={{ flex: 1, fontSize: 13, color: "#2C2C2A" }}>{children}</div>
    </div>
  );
}

function ResultCard({ data }) {
  const tags = (arr) => arr?.filter(v => v && v !== "N/A").map((v, i) => <Tag key={i}>{v}</Tag>);
  const speakers = data.speakers?.filter(s => s.name && s.name !== "N/A") || [];

  return (
    <div style={{
      background: "#FAFAF8", border: "0.5px solid #DDDBD3",
      borderRadius: 12, padding: "1.25rem 1.5rem", marginTop: "1rem",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem", gap: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: "#888780", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>
            {data.content_format || "Uncategorized"}
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "#1A1916", lineHeight: 1.4 }}>
            {data.title}
          </div>
        </div>
        <ConfidenceBadge label={data.confidence_label} score={data.confidence_score} />
      </div>

      {/* Summary */}
      {data.video_summary && data.video_summary !== "N/A" && (
        <div style={{
          background: "#EEEDFE", border: "0.5px solid #AFA9EC", borderRadius: 8,
          padding: "0.65rem 0.9rem", fontSize: 12, color: "#26215C",
          lineHeight: 1.6, marginBottom: "0.75rem",
        }}>
          {data.video_summary}
        </div>
      )}

      {/* Fields */}
      <div style={{ borderTop: "0.5px solid #ECEAE3" }}>
        {data.cancer_indications?.filter(v => v !== "N/A").length > 0 && (
          <MetaRow label="Cancer type">
            {tags(data.cancer_indications)}
          </MetaRow>
        )}
        {data.drug_generic_names?.filter(v => v !== "N/A").length > 0 && (
          <MetaRow label="Drugs">
            {tags(data.drug_generic_names?.filter(v => v !== "N/A").concat(
              data.drug_brand_names?.filter(v => v !== "N/A") || []
            ))}
          </MetaRow>
        )}
        {data.biomarker_context?.filter(v => v !== "N/A").length > 0 && (
          <MetaRow label="Biomarkers">
            {tags(data.biomarker_context)}
          </MetaRow>
        )}
        {data.trial_names?.filter(v => v !== "N/A").length > 0 && (
          <MetaRow label="Trials">
            {tags(data.trial_names, "blue")}
          </MetaRow>
        )}
        {speakers.length > 0 && (
          <MetaRow label="Speakers">
            {speakers.map((s, i) => (
              <div key={i} style={{ fontSize: 12 }}>
                <span style={{ fontWeight: 500, color: "#1A1916" }}>{s.name}</span>
                {s.affiliation && s.affiliation !== "N/A" && (
                  <span style={{ color: "#888780" }}> · {s.affiliation}</span>
                )}
              </div>
            ))}
          </MetaRow>
        )}
        <MetaRow label="Duration">
          {data.duration_minutes} min · {data.video_language?.toUpperCase()}
        </MetaRow>
        {data.metadata_url && (
          <MetaRow label="Blob storage">
            <a href={data.metadata_url} target="_blank" rel="noreferrer"
              style={{ color: "#534AB7", fontSize: 11, wordBreak: "break-all" }}>
              {data.metadata_url}
            </a>
          </MetaRow>
        )}
      </div>
    </div>
  );
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────
export default function ClinSearch() {
  const [url, setUrl]           = useState("");
  const [loading, setLoading]   = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState(null);
  const [usedMock, setUsedMock] = useState(false);
  const [tab, setTab]           = useState("process"); // "process" | "library"
  const [library, setLibrary]   = useState([]);
  const [libLoading, setLibLoading] = useState(false);
  const [healthStatus, setHealthStatus] = useState(null);

  // ── Check health ────────────────────────────────────────────────────────────
  const checkHealth = async () => {
    try {
      const res = await fetch(API.health);
      const data = await res.json();
      setHealthStatus(data.status === "ok" ? "online" : "error");
    } catch {
      setHealthStatus("error");
    }
  };

  // ── Process video ───────────────────────────────────────────────────────────
  const handleProcess = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setResult(null);
    setError(null);
    setUsedMock(false);

    try {
      const res = await fetch(API.process, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), metadata_only: false }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`API error ${res.status}: ${errText}`);
      }
      const data = await res.json();
      
      // Update CSV after successful processing
      try {
        await fetch(API.updateCsv, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data.metadata),
        });
      } catch (csvErr) {
        console.warn("CSV update failed (non-blocking):", csvErr);
      }
      
      setResult(data);
    } catch (err) {
      setError(err.message || "Processing failed. Make sure backend is running on http://localhost:8000");
      console.error("Process error:", err);
    } finally {
      setLoading(false);
    }
  };

  // ── Load library ────────────────────────────────────────────────────────────
  const loadLibrary = async () => {
    setLibLoading(true);
    try {
      const res = await fetch(API.videos);
      const data = await res.json();
      setLibrary(Array.isArray(data) ? data : []);
    } catch {
      setLibrary([]);
    } finally {
      setLibLoading(false);
    }
  };

  // ── UI ──────────────────────────────────────────────────────────────────────
  return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", background: "#FAFAF8", minHeight: "100vh" }}>

      {/* Top bar */}
      <div style={{
        background: "#1A1916", padding: "0 1.5rem",
        display: "flex", alignItems: "center", gap: 12, height: 52,
        position: "sticky", top: 0, zIndex: 10,
      }}>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="9" stroke="#AFA9EC" strokeWidth="1.5"/>
          <path d="M7 10h6M10 7v6" stroke="#AFA9EC" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
        <span style={{ fontSize: 13, fontWeight: 600, color: "#FAFAF8", letterSpacing: "0.02em" }}>
          I3DH <span style={{ color: "#534AB7" }}>·</span> ClinSearch
        </span>
        <span style={{ fontSize: 11, color: "#888780", marginLeft: 4 }}>Video Metadata Pipeline</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={checkHealth}
            style={{
              fontSize: 11, padding: "3px 10px", borderRadius: 99,
              border: "0.5px solid #444", background: "transparent",
              color: healthStatus === "online" ? "#5DCAA5" : healthStatus === "error" ? "#F0997B" : "#888780",
              cursor: "pointer",
            }}
          >
            {healthStatus === "online" ? "● API online" : healthStatus === "error" ? "● API error" : "Check API"}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ background: "#F1EFE8", borderBottom: "0.5px solid #DDDBD3", padding: "0 1.5rem", display: "flex", gap: 0 }}>
        {[["process", "Process video"], ["library", "Video library"]].map(([key, label]) => (
          <button key={key} onClick={() => { setTab(key); if (key === "library") loadLibrary(); }}
            style={{
              fontSize: 12, fontWeight: 500, padding: "10px 16px",
              border: "none", background: "transparent", cursor: "pointer",
              color: tab === key ? "#1A1916" : "#888780",
              borderBottom: tab === key ? "2px solid #534AB7" : "2px solid transparent",
            }}>
            {label}
          </button>
        ))}
      </div>

      <div style={{ maxWidth: 720, margin: "0 auto", padding: "1.5rem" }}>

        {/* ── PROCESS TAB ── */}
        {tab === "process" && (
          <>
            {healthStatus === "error" && (
              <div style={{
                background: "#FAECE7", border: "0.5px solid #F0997B", borderRadius: 8,
                padding: "0.6rem 0.9rem", fontSize: 12, color: "#712B13",
                display: "flex", gap: 6, alignItems: "flex-start", marginBottom: "1rem",
              }}>
                <span style={{ fontSize: 14 }}>⚠</span>
                <span><strong>Backend not running!</strong> Start it first: <code style={{background: "#F0997B", color: "white", padding: "2px 5px", borderRadius: 3}}>python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000</code></span>
              </div>
            )}
            <div style={{ marginBottom: "1.25rem" }}>
              <div style={{ fontSize: 11, color: "#888780", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 6 }}>
                Video URL
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleProcess()}
                  placeholder="https://www.youtube.com/watch?v=..."
                  style={{
                    flex: 1, fontSize: 13, padding: "9px 12px",
                    border: "0.5px solid #DDDBD3", borderRadius: 8,
                    background: "#FFFFFF", color: "#1A1916", outline: "none",
                    fontFamily: "inherit",
                  }}
                />
                <button
                  onClick={handleProcess}
                  disabled={loading || !url.trim()}
                  style={{
                    fontSize: 13, fontWeight: 500, padding: "9px 20px",
                    borderRadius: 8, border: "none",
                    background: loading || !url.trim() ? "#DDDBD3" : "#534AB7",
                    color: loading || !url.trim() ? "#888780" : "#FFFFFF",
                    cursor: loading || !url.trim() ? "not-allowed" : "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  {loading ? "Extracting…" : "Extract metadata"}
                </button>
              </div>
              <div style={{ fontSize: 11, color: "#888780", marginTop: 5 }}>
                Calls <code style={{ background: "#ECEAE3", padding: "1px 5px", borderRadius: 3 }}>POST /process</code> on <code style={{ background: "#ECEAE3", padding: "1px 5px", borderRadius: 3 }}>localhost:8000</code> · downloads video, uploads to Azure, updates CSV
              </div>
            </div>

            {/* Error notice */}
            {error && (
              <div style={{
                background: "#FAECE7", border: "0.5px solid #F0997B", borderRadius: 8,
                padding: "0.6rem 0.9rem", fontSize: 12, color: "#712B13",
                display: "flex", gap: 6, alignItems: "flex-start", marginBottom: "0.75rem",
              }}>
                <span style={{ fontSize: 14 }}>✕</span>
                <span>{error}</span>
              </div>
            )}

            {/* Loading */}
            {loading && (
              <div style={{
                background: "#EEEDFE", border: "0.5px solid #AFA9EC", borderRadius: 8,
                padding: "1rem", textAlign: "center", fontSize: 13, color: "#534AB7",
              }}>
                🎬 Downloading video · extracting clinical metadata · uploading to Azure…
              </div>
            )}

            {/* Result */}
            {result && <ResultCard data={result} />}
          </>
        )}

        {/* ── LIBRARY TAB ── */}
        {tab === "library" && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "#1A1916" }}>Video library</div>
                <div style={{ fontSize: 11, color: "#888780", marginTop: 2 }}>
                  Calls <code style={{ background: "#ECEAE3", padding: "1px 5px", borderRadius: 3 }}>GET /videos</code> on <code style={{ background: "#ECEAE3", padding: "1px 5px", borderRadius: 3 }}>localhost:8000</code> · reads from Azure Blob index
                </div>
              </div>
              <button onClick={loadLibrary}
                style={{
                  fontSize: 12, padding: "6px 14px", borderRadius: 8,
                  border: "0.5px solid #DDDBD3", background: "#FFFFFF",
                  color: "#1A1916", cursor: "pointer",
                }}>
                Refresh
              </button>
            </div>

            {libLoading && (
              <div style={{ textAlign: "center", fontSize: 13, color: "#888780", padding: "2rem" }}>
                Loading from Azure Blob…
              </div>
            )}

            {!libLoading && library.length === 0 && (
              <div style={{
                background: "#F1EFE8", border: "0.5px solid #DDDBD3", borderRadius: 8,
                padding: "2rem", textAlign: "center", fontSize: 13, color: "#888780",
              }}>
                No videos processed yet. Go to Process video tab and submit a URL.
              </div>
            )}

            {library.map((v, i) => (
              <div key={i} style={{
                background: "#FFFFFF", border: "0.5px solid #DDDBD3", borderRadius: 8,
                padding: "0.9rem 1rem", marginBottom: 8,
                display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "#1A1916", marginBottom: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {v.title || v.file_id}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {v.category && <Tag color="purple">{v.category}</Tag>}
                    <Tag color="gray">{v.processed_date?.slice(0, 10)}</Tag>
                  </div>
                </div>
                <ConfidenceBadge label={v.confidence_label || "poor"} score={v.confidence_score || 0} />
              </div>
            ))}
          </>
        )}

      </div>
    </div>
  );
}
