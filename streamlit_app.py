from __future__ import annotations

import html as _html
import json
import os
import sys
from collections.abc import Callable
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st
from dotenv import load_dotenv
from streamlit.typing import UploadedFile

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from canonical_model_generator.acord_rag import (  # noqa: E402
    ACORD_ARTIFACTS,
    AcordDocumentIndex,
    build_acord_chunks,
    generate_acord_artifacts,
    parse_acord_document,
)
from canonical_model_generator.acord_rag.history import (  # noqa: E402
    delete_acord_record,
    load_acord_records,
    save_acord_record,
)
from canonical_model_generator.alignment_agent import (  # noqa: E402
    ALIGNMENT_SELECTIONS,
    FULL_MATCH,
    MANUAL,
    MATCH_STATUSES,
    NOT_MATCHED,
    PARTIAL_MATCH,
    USE_ACORD,
    USE_BASELINE,
    USE_GENERATED,
    AlignmentAgentError,
    OpenAICanonicalGapProvider,
    alignment_input_digest,
    approve_acord_alignment,
    attach_generated_gap_proposal,
    build_regional_alignment_source,
    delete_alignment_artifact,
    load_alignment_agent_state,
    load_alignment_artifacts,
    persist_alignment_decisions,
    purge_alignment_agent_run,
    resume_alignment_agent,
    run_alignment_agent,
    save_alignment_artifact,
    validate_alignment_decisions,
)
from canonical_model_generator.api_analyzer import (  # noqa: E402
    OpenAISemanticProvider,
    TokenBudgetConfig,
    inspect_retrieved_code,
    inspect_retrieved_target,
    normalize_regional_entity,
    run_api_analyzer_agent,
)
from canonical_model_generator.api_analyzer.normalization import (  # noqa: E402
    normalize_regional_endpoint,
)
from canonical_model_generator.application_history import (  # noqa: E402
    RUN_ID_PATTERN,
    load_application_records,
    save_application_record,
)
from canonical_model_generator.canonical_registry import (  # noqa: E402
    REVIEW_ACTIONS,
    default_final_review,
    load_canonical_versions,
    submit_canonical_version,
)
from canonical_model_generator.discovery_agent.artifacts import generate_artifacts  # noqa: E402
from canonical_model_generator.discovery_agent.model import DiscoveryModel  # noqa: E402
from canonical_model_generator.discovery_agent.openapi import discover_openapi  # noqa: E402
from canonical_model_generator.discovery_agent.reconcile import reconcile  # noqa: E402
from canonical_model_generator.discovery_agent.roslyn import (  # noqa: E402
    extract_roslyn,
    merge_roslyn_models,
)
from canonical_model_generator.intake import (  # noqa: E402
    IntakeError,
    inspect_repository_zip,
    validate_openapi,
)
from canonical_model_generator.llm_audit import llm_log_directory  # noqa: E402
from canonical_model_generator.openai_config import (  # noqa: E402
    resolve_openai_api_key,
    resolve_openai_model,
)
from canonical_model_generator.regional_catalog import (  # noqa: E402
    regional_catalog_rows,
    regional_domain_tree,
    regional_model_tree,
)
from canonical_model_generator.regional_review import (  # noqa: E402
    build_regional_review,
    render_regional_review_excel,
    render_regional_review_mermaid,
)
from canonical_model_generator.repository_rag.embeddings import (  # noqa: E402
    LOCAL_MODEL,
    OPENAI_MODELS,
    EmbeddingConfig,
    create_embedder,
)
from canonical_model_generator.repository_rag.index import ChromaRepositoryIndex  # noqa: E402
from canonical_model_generator.workflow_progress import reached_stage_count  # noqa: E402

st.set_page_config(
    page_title="Canonical Model Platform",
    page_icon=":material/account_tree:",
    layout="wide",
)

# ── Global UI theme ──────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* ── Base ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Inter',system-ui,-apple-system,sans-serif}
.stApp{background:#f4f6fb}
.block-container{padding-top:1.25rem!important}

/* ── Main title ── */
h1{color:#1e293b!important;font-weight:800!important;letter-spacing:-.025em}
h2,h3{color:#1e293b!important;font-weight:600!important;letter-spacing:-.015em}
p,li,label{color:#334155}

/* ── Sidebar ── */
section[data-testid="stSidebar"]{
  background:#ffffff!important;
  border-right:1px solid #e2e8f0!important;
  box-shadow:2px 0 12px rgba(0,0,0,.06)!important}
section[data-testid="stSidebarContent"]{background:transparent!important}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span{color:#1e293b!important}
section[data-testid="stSidebar"] .stCaption p{
  color:#64748b!important;text-transform:uppercase;
  font-size:.62rem!important;letter-spacing:.1em;font-weight:700}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3{color:#1e293b!important}

/* Sidebar pill buttons — idle */
section[data-testid="stSidebar"] [data-testid="stPills"] button{
  background:#f8fafc!important;
  color:#334155!important;
  border:1px solid #e2e8f0!important;
  border-radius:7px!important;font-size:.8rem!important;
  transition:background .15s,color .15s,border-color .15s!important}
/* Sidebar pill buttons — hover */
section[data-testid="stSidebar"] [data-testid="stPills"] button:hover{
  background:#eff6ff!important;
  color:#1d4ed8!important;
  border-color:#bfdbfe!important}
/* Sidebar pill buttons — selected */
section[data-testid="stSidebar"] [data-testid="stPills"] button[aria-selected="true"]{
  background:linear-gradient(135deg,#1d4ed8,#2563eb)!important;
  color:#ffffff!important;
  border-color:#2563eb!important;
  box-shadow:0 2px 8px rgba(37,99,235,.3)!important;
  font-weight:700!important}

/* Sidebar hr */
section[data-testid="stSidebar"] hr{
  border-color:#e2e8f0!important}

/* ── Tab bar ── */
.stTabs [data-baseweb="tab-list"]{
  background:transparent!important;
  border:none!important;
  border-bottom:2px solid #e2e8f0!important;
  border-radius:0!important;padding:0!important;gap:0!important}
.stTabs [data-baseweb="tab"]{
  background:transparent!important;
  border:none!important;border-radius:0!important;
  color:#64748b!important;
  font-size:.85rem!important;font-weight:500!important;
  padding:10px 20px!important;
  border-bottom:2px solid transparent!important;
  margin-bottom:-2px!important;
  transition:color .15s,border-color .15s!important}
.stTabs [data-baseweb="tab"]:hover{
  color:#1d4ed8!important;
  border-bottom-color:#93c5fd!important;
  background:transparent!important}
.stTabs [aria-selected="true"]{
  color:#1d4ed8!important;font-weight:700!important;
  border-bottom:2px solid #2563eb!important;
  background:transparent!important;
  box-shadow:none!important}

/* ── Metric tiles ── */
[data-testid="metric-container"]{
  background:#ffffff!important;
  border:1px solid #e2e8f0!important;
  border-radius:10px!important;
  box-shadow:0 1px 4px rgba(0,0,0,.06)!important}
[data-testid="stMetricValue"]{color:#1e293b!important;font-weight:700!important}
[data-testid="stMetricLabel"]{color:#64748b!important}
[data-testid="stMetricDelta"]{font-weight:600!important}

/* ── Bordered containers ── */
[data-testid="stVerticalBlockBorderWrapper"]{
  background:#ffffff!important;
  border-color:#e2e8f0!important;border-radius:12px!important;
  box-shadow:0 1px 6px rgba(0,0,0,.06)!important}

/* ── Buttons ── */
button[kind="primary"]{
  background:linear-gradient(135deg,#1d4ed8,#2563eb)!important;
  border:none!important;border-radius:8px!important;
  font-weight:600!important;letter-spacing:.02em!important;
  box-shadow:0 2px 10px rgba(37,99,235,.3)!important;color:#fff!important}
button[kind="secondary"]{
  border-color:#cbd5e1!important;
  border-radius:8px!important;background:#ffffff!important;
  color:#1e293b!important}

/* ── Expanders ── */
[data-testid="stExpander"] summary{
  background:#ffffff!important;border-radius:8px!important;
  border:1px solid #e2e8f0!important;color:#1e293b!important}

/* ── HR divider ── */
hr{border-color:#e2e8f0!important;margin:18px 0!important}

/* ── Alerts ── */
[data-testid="stAlertContainer"]{border-radius:10px!important}

/* ── Status ── */
[data-testid="stStatus"]{
  border-radius:10px!important;background:#ffffff!important;
  border:1px solid #e2e8f0!important}

/* ── Inputs ── */
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{
  background:#ffffff!important;
  border-color:#cbd5e1!important;border-radius:8px!important;
  color:#1e293b!important}

/* ── Captions ── */
.stCaption p{color:#64748b!important}

/* ── Select / Dropdown ── */
[data-testid="stSelectbox"] div,[data-testid="stMultiSelect"] div{
  color:#1e293b!important}

/* ── Progress bar ── */
[data-testid="stProgressBar"]>div{border-radius:999px!important}

/* ── Dataframes ── */
[data-testid="stDataFrame"]{border-radius:10px!important;overflow:hidden}

/* ── Code blocks ── */
code{background:#f1f5f9!important;color:#1e293b!important;
     border-radius:4px!important;padding:1px 5px!important}
</style>
""",
    unsafe_allow_html=True,
)

APPLICATION_HISTORY_ROOT = Path(__file__).resolve().parent / ".applications"
ACORD_HISTORY_ROOT = Path(__file__).resolve().parent / ".acord"
REGIONAL_REVIEWS_ROOT = Path(__file__).resolve().parent / ".regional-reviews"


def _safe_region_slug(region: str) -> str:
    import re as _re

    return _re.sub(r"[^a-z0-9_-]", "-", region.casefold()).strip("-") or "region"


def _save_norm_draft(root: Path, region: str, data: dict[str, Any]) -> None:
    """Persist normalization proposals and decisions so they survive page reloads."""
    root.mkdir(parents=True, exist_ok=True)
    slug = _safe_region_slug(region)
    tmp = root / f"{slug}-norm.json.tmp"
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(root / f"{slug}-norm.json")


def _load_all_norm_drafts(root: Path) -> dict[str, dict[str, Any]]:
    """Load all saved normalization drafts keyed by region."""
    drafts: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return drafts
    for path in sorted(root.glob("*-norm.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            region = d.get("region")
            if region:
                drafts[region] = d
        except Exception:
            continue
    return drafts


def _save_regional_review(root: Path, region: str, review: dict[str, Any]) -> None:
    """Persist an approved regional review JSON so it survives page reloads."""
    root.mkdir(parents=True, exist_ok=True)
    safe = _safe_region_slug(region)
    tmp = root / f"{safe}.json.tmp"
    tmp.write_text(json.dumps(review, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(root / f"{safe}.json")


def _load_regional_reviews(root: Path) -> dict[str, dict[str, Any]]:
    """Load previously approved regional reviews from disk and rebuild derived artifacts."""
    reviews: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return reviews
    for path in sorted(root.glob("*.json")):
        try:
            review = json.loads(path.read_text(encoding="utf-8"))
            region = review.get("region")
            if not region:
                continue
            reviews[region] = {
                "review": review,
                "excel": render_regional_review_excel(review),
                "mermaid": render_regional_review_mermaid(review),
            }
        except Exception:
            continue
    return reviews


ALIGNMENT_HISTORY_ROOT = Path(
    os.getenv("ALIGNMENT_HISTORY_ROOT", Path(__file__).resolve().parent / ".alignments")
)
ALIGNMENT_AGENT_DATABASE = Path(
    os.getenv("ALIGNMENT_AGENT_DATABASE", ALIGNMENT_HISTORY_ROOT / "alignment-agent.sqlite3")
)
CANONICAL_DATABASE = Path(__file__).resolve().parent / ".canonical" / "canonical-models.sqlite3"

DISCOVERY_ARTIFACTS = {
    "API Catalog": "api-catalog.json",
    "Data Model": "data-model.json",
    "Relationship Graph": "relationship-graph.json",
    "Validation and enums": "validation-enums.json",
    "Lineage": "lineage.json",
}

REGIONS = {
    "EU": "European Union",
    "IN": "India",
    "GB": "United Kingdom",
    "US": "United States",
    "CA": "Canada",
    "AU": "Australia",
    "SG": "Singapore",
}

st.session_state.setdefault("discovery_artifacts", {})
st.session_state.setdefault("discovery_projects", [])
st.session_state.setdefault("discovery_model", None)
st.session_state.setdefault("repository_archive", None)
st.session_state.setdefault("phase_2_unlocked", False)
st.session_state.setdefault("phase_2_artifacts", {})
st.session_state.setdefault("phase_2_error", None)
st.session_state.setdefault("rag_store_path", None)
st.session_state.setdefault("rag_manifest", None)
st.session_state.setdefault("rag_results", [])
st.session_state.setdefault("rag_semantics", None)
st.session_state.setdefault("application_runs", {})
st.session_state.setdefault("active_application_id", None)
st.session_state.setdefault("regional_normalizations", {})
st.session_state.setdefault("regional_endpoint_normalizations", {})
st.session_state.setdefault("regional_decisions", {})
st.session_state.setdefault("approved_regional_reviews", {})
st.session_state.setdefault("acord_runs", {})
st.session_state.setdefault("active_acord_id", None)
st.session_state.setdefault("acord_results", [])
st.session_state.setdefault("alignment_reviews", {})
st.session_state.setdefault("active_alignment_id", None)
st.session_state.setdefault("acord_alignment_drafts", {})
st.session_state.setdefault("canonical_gap_proposals", {})
if not st.session_state["application_runs"]:
    st.session_state["application_runs"] = load_application_records(APPLICATION_HISTORY_ROOT)
if not st.session_state["acord_runs"]:
    st.session_state["acord_runs"] = load_acord_records(ACORD_HISTORY_ROOT)
if (
    st.session_state["acord_runs"]
    and st.session_state["active_acord_id"] not in st.session_state["acord_runs"]
):
    st.session_state["active_acord_id"] = next(iter(st.session_state["acord_runs"]))
if not st.session_state["alignment_reviews"]:
    st.session_state["alignment_reviews"] = load_alignment_artifacts(ALIGNMENT_HISTORY_ROOT)
if (
    st.session_state["alignment_reviews"]
    and st.session_state["active_alignment_id"] not in st.session_state["alignment_reviews"]
):
    st.session_state["active_alignment_id"] = next(reversed(st.session_state["alignment_reviews"]))
if not st.session_state["approved_regional_reviews"]:
    st.session_state["approved_regional_reviews"] = _load_regional_reviews(REGIONAL_REVIEWS_ROOT)
if not st.session_state.get("_norm_drafts_loaded"):
    for _region, _draft in _load_all_norm_drafts(REGIONAL_REVIEWS_ROOT).items():
        for _k, _v in _draft.get("normalizations", {}).items():
            st.session_state["regional_normalizations"].setdefault(_k, _v)
        for _k, _v in _draft.get("endpointNormalizations", {}).items():
            st.session_state["regional_endpoint_normalizations"].setdefault(_k, _v)
        st.session_state["regional_decisions"].setdefault(_region, _draft.get("decisions", {}))
    st.session_state["_norm_drafts_loaded"] = True


def build_artifact_bundle(artifacts: dict[str, bytes]) -> bytes:
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for label, content in artifacts.items():
            archive.writestr(DISCOVERY_ARTIFACTS[label], content)
    return bundle.getvalue()


def build_named_bundle(artifacts: dict[str, bytes]) -> bytes:
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for filename, content in artifacts.items():
            archive.writestr(filename, content)
    return bundle.getvalue()


def build_acord_bundle(artifacts: dict[str, bytes]) -> bytes:
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for label, content in artifacts.items():
            archive.writestr(ACORD_ARTIFACTS[label], content)
    return bundle.getvalue()


def _hero_banner(
    icon: str,
    eyebrow: str,
    title: str,
    body: str,
    accent: str = "#2563eb",
    glow_right: str = "rgba(37,99,235,.08)",
    glow_left: str = "rgba(99,102,241,.06)",
) -> str:
    """Full-width light hero banner with subtle radial glow decorations."""
    return f"""
<div style="background:linear-gradient(135deg,#eff6ff 0%,#f8fafc 60%,#f0f7ff 100%);
            border:1px solid {accent}33;border-radius:16px;padding:28px 28px;
            position:relative;overflow:hidden;margin-bottom:4px">
  <div style="position:absolute;top:-50px;right:-50px;width:320px;height:320px;
              background:radial-gradient(circle,{glow_right},transparent 68%);
              pointer-events:none;z-index:0"></div>
  <div style="position:absolute;bottom:-70px;left:160px;width:220px;height:220px;
              background:radial-gradient(circle,{glow_left},transparent 68%);
              pointer-events:none;z-index:0"></div>
  <div style="display:flex;align-items:center;gap:20px;position:relative;z-index:1">
    <div style="background:linear-gradient(135deg,{accent}22,{accent}11);
                border:1px solid {accent}44;border-radius:14px;padding:14px;
                font-size:28px;line-height:1;flex-shrink:0">{icon}</div>
    <div>
      <div style="color:{accent};font-size:.68rem;font-weight:700;letter-spacing:.13em;
                  text-transform:uppercase;margin-bottom:6px;font-family:system-ui">{eyebrow}</div>
      <h2 style="color:#1e293b;font-size:1.55rem;font-weight:700;margin:0;
                 font-family:system-ui;line-height:1.25">{title}</h2>
      <p style="color:#64748b;font-size:.87rem;margin:8px 0 0;font-family:system-ui;
                max-width:680px;line-height:1.55">{body}</p>
    </div>
  </div>
</div>"""


def _pipeline_steps(steps: list[tuple[str, str, str]]) -> str:
    """Horizontal pipeline strip.  Each tuple: (label, state, icon_char).
    state: 'done' | 'active' | 'pending'
    """
    _colors = {
        "done": ("#f0fdf4", "#166534", "#22c55e"),
        "active": ("#eff6ff", "#1e40af", "#3b82f6"),
        "pending": ("#f8fafc", "#94a3b8", "#cbd5e1"),
    }
    parts: list[str] = []
    for i, (label, state, icon_char) in enumerate(steps):
        bg, fg, border = _colors.get(state, _colors["pending"])
        connector = (
            f'<div style="flex:1;height:2px;background:linear-gradient(90deg,{border},{border}88);'
            f'min-width:20px;max-width:60px"></div>'
            if i < len(steps) - 1
            else ""
        )
        parts.append(
            f'<div style="display:flex;align-items:center;gap:8px;padding:9px 16px;'
            f"background:{bg};border:1px solid {border}55;border-radius:8px;"
            f'white-space:nowrap">'
            f'<span style="background:{border};color:#000;width:18px;height:18px;'
            f"border-radius:50%;display:inline-flex;align-items:center;justify-content:center;"
            f'font-size:.65rem;font-weight:700;flex-shrink:0">{icon_char}</span>'
            f'<span style="color:{fg};font-size:.78rem;font-weight:600;'
            f'font-family:system-ui">{label}</span>'
            f"</div>" + connector
        )
    return (
        '<div style="display:flex;align-items:center;gap:0;'
        'flex-wrap:wrap;row-gap:8px;margin:14px 0">' + "".join(parts) + "</div>"
    )


def _stat_tile(value: str | int, label: str, accent: str = "#2563eb") -> str:
    """Return an HTML string for a single coloured metric tile."""
    return (
        f'<div style="flex:1;min-width:110px;max-width:160px;background:#ffffff;'
        f"border:1px solid {accent}22;border-top:3px solid {accent};border-radius:10px;"
        f"box-shadow:0 1px 4px rgba(0,0,0,.06);"
        f'padding:18px 12px;text-align:center;">'
        f'<div style="color:{accent};font-size:2rem;font-weight:700;line-height:1.1">{value}</div>'
        f'<div style="color:#64748b;font-size:.72rem;margin-top:6px;text-transform:uppercase;'
        f'letter-spacing:.07em">{label}</div>'
        f"</div>"
    )


def _status_pill(text: str, kind: str = "success") -> str:
    """Return an HTML status pill badge."""
    _palettes = {
        "success": ("#dcfce7", "#166534", "✓"),
        "info": ("#dbeafe", "#1e40af", "●"),
        "warning": ("#fef3c7", "#92400e", "⚠"),
        "neutral": ("#f1f5f9", "#475569", "○"),
    }
    bg, fg, icon = _palettes.get(kind, _palettes["info"])
    return (
        f'<span style="background:{bg};color:{fg};padding:4px 12px;border-radius:12px;'
        f"font-size:.7rem;font-weight:700;letter-spacing:.07em;white-space:nowrap;"
        f'font-family:system-ui,sans-serif">{icon} {text}</span>'
    )


def _section_heading(title: str, subtitle: str = "") -> str:
    """Return an HTML section heading with a left accent bar."""
    sub = (
        f'<p style="color:#64748b;font-size:.85rem;margin:4px 0 0;'
        f'font-family:system-ui,sans-serif">{subtitle}</p>'
        if subtitle
        else ""
    )
    return (
        f'<div style="border-left:4px solid #2563eb;padding:4px 0 4px 14px;margin:8px 0 16px">'
        f'<h3 style="color:#1e293b;font-size:1.05rem;font-weight:600;margin:0;'
        f'font-family:system-ui,sans-serif">{title}</h3>{sub}</div>'
    )


def _coverage_ring_html(percent: float, label: str = "MATCHED") -> str:
    """SVG donut ring showing a coverage percentage."""
    r = 46
    circ = 2 * 3.14159 * r
    offset = circ * (1 - max(0.0, min(1.0, percent / 100)))
    color = "#22c55e" if percent >= 75 else "#f59e0b" if percent >= 40 else "#ef4444"
    return f"""
<svg width="130" height="130" viewBox="0 0 130 130"
     style="flex-shrink:0;display:block" xmlns="http://www.w3.org/2000/svg">
  <circle cx="65" cy="65" r="{r}" fill="none" stroke="#e2e8f0" stroke-width="11"/>
  <circle cx="65" cy="65" r="{r}" fill="none" stroke="{color}" stroke-width="11"
          stroke-linecap="round"
          stroke-dasharray="{circ:.1f}" stroke-dashoffset="{offset:.1f}"
          transform="rotate(-90 65 65)"/>
  <text x="65" y="61" text-anchor="middle" fill="#1e293b"
        font-size="21" font-weight="700" font-family="system-ui">{percent:.0f}%</text>
  <text x="65" y="77" text-anchor="middle" fill="#64748b"
        font-size="9" font-weight="600" letter-spacing="1"
        font-family="system-ui">{label}</text>
</svg>"""


def _summary_card_html(
    title: str,
    subtitle: str,
    pill_text: str,
    pill_kind: str,
    stat_tiles_html: str,
    footer: str = "",
) -> str:
    """Return a full-width dark gradient summary card."""
    footer_html = (
        f'<p style="color:#64748b;font-size:.72rem;margin:16px 0 0;'
        f'font-family:system-ui,sans-serif">{footer}</p>'
        if footer
        else ""
    )
    return f"""
<div style="background:linear-gradient(135deg,#ffffff 0%,#f0f7ff 100%);
            border:1px solid #dbeafe;border-radius:12px;padding:24px;margin:10px 0;
            box-shadow:0 2px 10px rgba(37,99,235,.08);">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;
              flex-wrap:wrap;gap:10px;margin-bottom:8px">
    <div>
      <h2 style="color:#1e293b;margin:0;font-size:1.35rem;font-weight:600;
                 font-family:system-ui,sans-serif">{title}</h2>
      <p style="color:#64748b;margin:5px 0 0;font-size:.83rem;
                font-family:system-ui,sans-serif">{subtitle}</p>
    </div>
    {_status_pill(pill_text, pill_kind)}
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:18px">
    {stat_tiles_html}
  </div>
  {footer_html}
</div>"""


def render_artifact_download_gallery(
    *,
    title: str,
    artifacts: dict[str, bytes],
    filenames: dict[str, str],
    key_prefix: str,
    bundle: bytes,
    bundle_filename: str,
    extra_downloads: list[dict[str, Any]] | None = None,
) -> None:
    """Render a compact right-side gallery for generated artifact downloads."""
    with st.container(border=True):
        st.subheader(title, anchor=False)
        st.caption(f"{len(artifacts)} generated artifacts")
        for label, filename in filenames.items():
            with st.container(border=True, gap=None):
                st.markdown(f"**{label}**")
                st.caption(filename)
                st.download_button(
                    "Download JSON",
                    data=artifacts[label],
                    file_name=filename,
                    mime="application/json",
                    icon=":material/download:",
                    key=f"{key_prefix}_{filename}",
                    width="stretch",
                )
        st.download_button(
            "Download all artifacts",
            data=bundle,
            file_name=bundle_filename,
            mime="application/zip",
            type="primary",
            icon=":material/folder_zip:",
            key=f"{key_prefix}_all",
            width="stretch",
        )
        for item in extra_downloads or []:
            st.download_button(
                item["label"],
                data=item["data"],
                file_name=item["filename"],
                mime=item["mime"],
                icon=":material/download:",
                key=f"{key_prefix}_{item['key']}",
                width="stretch",
            )


def dismiss_alignment_deletion() -> None:
    """Forget the pending deletion so a dismissed dialog does not reopen."""
    st.session_state.pop("pending_alignment_deletion", None)


@st.dialog("Delete approved ACORD alignment", on_dismiss=dismiss_alignment_deletion)
def confirm_delete_alignment(alignment_id: str) -> None:
    alignments = st.session_state["alignment_reviews"]
    artifact = alignments.get(alignment_id)
    if artifact is None:
        st.error("This alignment is no longer available.")
        return
    reference = artifact.get("acordReference", {})
    st.warning(
        "This permanently deletes only the selected saved alignment artifact. Submitted "
        "canonical versions, ACORD ingestion, regional evidence, and agent checkpoints remain."
    )
    st.markdown(
        f"**{artifact.get('region', 'Unknown region')} · "
        f"{reference.get('referenceLabel', 'ACORD')} "
        f"{reference.get('referenceVersion', '')} [{alignment_id[:6]}]**"
    )
    confirmed = st.checkbox(
        "I understand this saved alignment artifact will be deleted.",
        key=f"confirm_delete_alignment_{alignment_id}",
    )
    if st.button(
        "Delete alignment",
        type="primary",
        icon=":material/delete:",
        disabled=not confirmed,
        key=f"delete_alignment_{alignment_id}",
    ):
        try:
            if not delete_alignment_artifact(ALIGNMENT_HISTORY_ROOT, alignment_id):
                st.error("The saved alignment file was not found; nothing was deleted.")
                return
            del alignments[alignment_id]
            st.session_state["active_alignment_id"] = next(reversed(alignments), None)
            st.session_state.pop(f"final_canonical_review_{alignment_id}", None)
            st.session_state.pop("pending_alignment_deletion", None)
            st.session_state["alignment_delete_notice"] = (
                f"Deleted saved ACORD alignment [{alignment_id[:6]}]. "
                "Submitted canonical versions were retained."
            )
            st.rerun()
        except (OSError, ValueError) as exc:
            st.error(f"Alignment deletion failed: {exc}")


def dismiss_acord_deletion() -> None:
    """Forget the pending ACORD deletion so a dismissed dialog does not reopen."""
    st.session_state.pop("pending_acord_deletion", None)


@st.dialog("Delete ACORD ingestion", on_dismiss=dismiss_acord_deletion)
def confirm_delete_acord(run_id: str) -> None:
    acord_runs = st.session_state["acord_runs"]
    run = acord_runs.get(run_id)
    if run is None:
        st.error("This ACORD ingestion is no longer available.")
        return
    profile = run["profile"]
    st.warning(
        "This permanently deletes the selected ACORD ingestion and its local index. "
        "Saved alignment artifacts and submitted canonical versions are not affected."
    )
    st.markdown(
        f"**{profile['referenceLabel']} · {profile['referenceVersion']} · "
        f"{profile['sourceFile']} [{run_id[:6]}]**"
    )
    confirmed = st.checkbox(
        "I understand this ACORD ingestion and its index will be deleted.",
        key=f"confirm_delete_acord_{run_id}",
    )
    if st.button(
        "Delete ACORD ingestion",
        type="primary",
        icon=":material/delete:",
        disabled=not confirmed,
        key=f"delete_acord_{run_id}",
    ):
        try:
            delete_acord_record(ACORD_HISTORY_ROOT, run_id)
            del acord_runs[run_id]
            if st.session_state.get("active_acord_id") == run_id:
                st.session_state["active_acord_id"] = next(reversed(acord_runs), None)
            st.session_state.pop("pending_acord_deletion", None)
            st.session_state["acord_delete_notice"] = (
                f"Deleted ACORD ingestion [{run_id[:6]}]. Saved alignment artifacts were retained."
            )
            st.rerun()
        except (OSError, ValueError) as exc:
            st.error(f"ACORD ingestion deletion failed: {exc}")


def _extract_yaml_json_from_zip(content: bytes, zip_name: str) -> list[tuple[str, bytes]]:
    """Return (filename, content) pairs for every YAML/JSON file found inside a ZIP archive."""
    results: list[tuple[str, bytes]] = []
    try:
        with ZipFile(BytesIO(content)) as zf:
            for entry in zf.infolist():
                if entry.is_dir():
                    continue
                raw_name = entry.filename
                suffix = raw_name.lower().rsplit(".", 1)[-1] if "." in raw_name else ""
                if suffix not in {"json", "yaml", "yml"}:
                    continue
                safe_name = Path(raw_name).name
                if not safe_name:
                    continue
                results.append((safe_name, zf.read(entry)))
    except Exception as exc:
        raise ValueError(f"Could not open ZIP archive '{zip_name}': {exc}") from exc
    return results


def ingest_acord_reference(
    *,
    source_content: bytes,
    source_name: str,
    reference_label: str,
    reference_version: str,
    progress: Callable[[str], None] | None = None,
) -> str:
    model = parse_acord_document(
        source_content,
        source_name,
        reference_label=reference_label,
        reference_version=reference_version,
    )
    artifacts = generate_acord_artifacts(model)
    chunks = build_acord_chunks(model)
    run_id = uuid4().hex
    run_path = save_acord_record(
        ACORD_HISTORY_ROOT,
        run_id,
        model=model,
        artifacts=artifacts,
        source_content=source_content,
    )
    index = AcordDocumentIndex(run_path / "index")
    try:
        stats = index.ingest(model, chunks, progress=progress)
        manifest = index.manifest
    finally:
        index.close()
    st.session_state["acord_runs"][run_id] = {
        "profile": {
            "runId": run_id,
            "sourceFile": Path(source_name).name,
            "referenceLabel": reference_label.strip(),
            "referenceVersion": reference_version.strip(),
            "sha256": model["source"]["sha256"],
        },
        "model": model,
        "artifacts": artifacts,
        "manifest": manifest,
        "storagePath": str(run_path / "index"),
        "stats": stats,
    }
    st.session_state["active_acord_id"] = run_id
    st.session_state["acord_results"] = []
    return run_id


def openai_api_key() -> str | None:
    """Return the key loaded from the ignored `.env` file or the process environment."""
    return resolve_openai_api_key()


def workflow_stages() -> list[dict[str, str]]:
    """Describe the four-stage regional application journey."""
    active_id = st.session_state.get("active_application_id")
    run = st.session_state.get("application_runs", {}).get(active_id, {})
    discovery_ready = bool(run.get("discovery_model"))
    rag_path = run.get("rag_store_path")
    rag_ready = bool(rag_path and Path(rag_path, "rag-manifest.json").is_file())
    report_content = run.get("phase_2_artifacts", {}).get("enrichment-report.json")
    report: dict[str, object] = {}
    if report_content:
        try:
            report = json.loads(report_content)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            report = {}
    analyzer_status = str(report.get("status", ""))
    current_workspace = str(st.session_state.get("workflow_tabs", ""))
    regional_selected = "Regional view" in current_workspace
    analyzer_complete = analyzer_status == "complete"
    return [
        {
            "name": "Discovery agent",
            "state": "Complete" if discovery_ready else "Current",
            "detail": "Repository structure and endpoint contracts"
            if discovery_ready
            else "Upload and analyze a trusted repository",
        },
        {
            "name": "Repository RAG",
            "state": "Complete" if rag_ready else "Ready" if discovery_ready else "Locked",
            "detail": "Saved index for the selected repository"
            if rag_ready
            else "Build an index from the same Discovery repository",
        },
        {
            "name": "API analyzer",
            "state": (
                "Complete"
                if analyzer_status == "complete"
                else "Partial"
                if analyzer_status
                else "Ready"
                if rag_ready
                else "Locked"
            ),
            "detail": (
                f"{report.get('endpointsEnriched', 0)}/"
                f"{report.get('endpointsDiscovered', 0)} endpoints, "
                f"{report.get('entitiesEnriched', 0)}/"
                f"{report.get('entitiesDiscovered', 0)} entities enriched"
                if analyzer_status
                else "Requires the selected repository's RAG index"
            ),
        },
        {
            "name": "Regional view",
            "state": "Current"
            if discovery_ready and (analyzer_complete or regional_selected)
            else "Ready"
            if discovery_ready
            else "Locked",
            "detail": "Inspect models, mappings, domains, and regional review",
        },
    ]


def render_workflow_progress() -> None:
    stages = workflow_stages()
    reached = reached_stage_count([item["state"] for item in stages])
    active_id = st.session_state.get("active_application_id")
    active_run = st.session_state.get("application_runs", {}).get(active_id, {})
    profile = active_run.get("profile", {})
    with st.container(border=True):
        st.subheader("Agent workflow", anchor=False)
        if profile:
            st.caption(
                f"Selected pipeline: {profile.get('region')} · "
                f"{profile.get('application')} · {profile.get('repository')} [{active_id[:6]}]"
            )
        else:
            st.caption("Start with Discovery to create a selected application pipeline.")
        partial = next((item for item in stages if item["state"] == "Partial"), None)
        progress_text = f"{reached} of {len(stages)} stages reached"
        if partial:
            progress_text += f" · {partial['name']} partial: {partial['detail']}"
        st.progress(reached / len(stages), text=progress_text)


def activate_application(application_id: str) -> None:
    """Restore one completed Discovery/RAG run without carrying another run's artifacts."""
    run = st.session_state["application_runs"][application_id]
    st.session_state["active_application_id"] = application_id
    for key in (
        "discovery_artifacts",
        "discovery_projects",
        "discovery_model",
        "repository_archive",
        "rag_store_path",
        "rag_manifest",
        "phase_2_artifacts",
    ):
        st.session_state[key] = run[key]
    st.session_state["phase_2_unlocked"] = True
    st.session_state["phase_2_error"] = run.get("phase_2_error")
    st.session_state["rag_results"] = []
    st.session_state["rag_semantics"] = None
    st.session_state["phase_2_source_consent"] = False


def persist_application(application_id: str) -> None:
    # AppTest fixtures may use short readable IDs; production records use UUID hex IDs.
    if not RUN_ID_PATTERN.fullmatch(application_id):
        return
    save_application_record(
        APPLICATION_HISTORY_ROOT,
        application_id,
        st.session_state["application_runs"][application_id],
    )


def save_application(
    *,
    discovery_model: bytes,
    discovery_artifacts: dict[str, bytes],
    projects: list[str],
    repository_archive: bytes | None,
    repository_name: str,
    openapi_name: str,
) -> str:
    model = DiscoveryModel.model_validate_json(discovery_model)
    # A submission is a new analysis run even when its files match a prior upload.
    # It must never inherit another run's RAG index or Phase 2 artifacts.
    application_id = uuid4().hex
    st.session_state["application_runs"][application_id] = {
        "profile": {
            "region": model.region,
            "application": model.system,
            "repository": repository_name,
            "openapi": openapi_name,
        },
        "discovery_artifacts": discovery_artifacts,
        "discovery_projects": projects,
        "discovery_model": discovery_model,
        "repository_archive": repository_archive,
        "rag_store_path": None,
        "rag_manifest": None,
        "phase_2_artifacts": {},
        "phase_2_error": None,
    }
    persist_application(application_id)
    activate_application(application_id)
    return application_id


def run_uploaded_semantic_generation(
    *,
    repository_archive: bytes | None,
    discovery_artifact: bytes,
    provider: OpenAISemanticProvider,
    progress: Callable[[str], None] | None = None,
    rag_store_path: Path | None = None,
    embedder=None,
    resume_artifacts: dict[str, bytes] | None = None,
) -> dict[str, bytes]:
    if repository_archive is None:
        raise ValueError("API Analyzer requires the source repository and its saved RAG index.")
    if rag_store_path is None:
        raise ValueError("API Analyzer requires a saved RAG index for the selected repository.")
    inspect_repository_zip(repository_archive)
    with TemporaryDirectory(prefix="canonical-semantic-openapi-") as temporary:
        repository = Path(temporary) / "repository"
        repository.mkdir()
        with ZipFile(BytesIO(repository_archive)) as zip_file:
            zip_file.extractall(repository)
        return run_api_analyzer_agent(
            discovery_artifact,
            repository,
            provider,
            progress,
            rag_store_path=rag_store_path,
            embedder=embedder,
            resume_artifacts=resume_artifacts,
        )


def has_unfinished_semantic_targets(artifacts: dict[str, bytes]) -> bool:
    report_content = artifacts.get("enrichment-report.json")
    if not report_content:
        return False
    try:
        report = json.loads(report_content)
    except (TypeError, json.JSONDecodeError):
        return False
    return report.get("status") == "partial" and any(
        report.get(key) for key in ("missingEndpointIds", "missingEntityIds", "missingEnumIds")
    )


def select_web_projects(
    projects: tuple[str, ...],
    controllers: tuple[str, ...],
    azure_function_projects: tuple[str, ...] = (),
) -> list[str]:
    ownership = {project: 0 for project in projects}
    project_parents = {project: PurePosixPath(project).parent for project in projects}
    for controller in controllers:
        controller_path = PurePosixPath(controller)
        candidates = [
            project
            for project, parent in project_parents.items()
            if controller_path.is_relative_to(parent)
        ]
        if candidates:
            owner = max(candidates, key=lambda item: len(project_parents[item].parts))
            ownership[owner] += 1

    azure_fn_set = set(azure_function_projects)
    selected = [
        project
        for project, count in ownership.items()
        if (
            count > 0
            or project in azure_fn_set
            or "api" in PurePosixPath(project).stem.lower()
            or PurePosixPath(project).stem.lower() == "web"
        )
        and "test" not in project.lower()
    ]
    return sorted(selected)


def run_uploaded_discovery(
    *,
    region: str,
    system: str,
    repository_file: UploadedFile | None,
    openapi_file: UploadedFile | None,
) -> tuple[dict[str, bytes], list[str], bytes]:
    if repository_file is None:
        raise IntakeError("A trusted .NET repository ZIP is required; OpenAPI is optional.")
    archive = repository_file.getvalue()
    inventory = inspect_repository_zip(archive)
    if not inventory.projects:
        raise IntakeError("The repository ZIP must contain a .csproj file.")
    if not inventory.controllers and not inventory.azure_function_projects:
        raise IntakeError(
            "The repository ZIP must contain at least one controller or Azure Functions project."
        )
    with TemporaryDirectory(prefix="canonical-discovery-") as temporary:
        workspace = Path(temporary)
        repository = workspace / "repository"
        output = workspace / "output"
        repository.mkdir()
        with ZipFile(BytesIO(archive)) as zip_file:
            zip_file.extractall(repository)

        selected_projects = select_web_projects(
            inventory.projects, inventory.controllers, inventory.azure_function_projects
        )
        if not selected_projects:
            raise IntakeError("No non-test project owns the discovered controller or function files.")
        roslyn_models = [
            extract_roslyn(repository / project, repository, region.strip(), system.strip())
            for project in selected_projects
        ]
        model = merge_roslyn_models(roslyn_models)
        openapi = None
        if openapi_file is not None:
            validate_openapi(openapi_file.getvalue(), openapi_file.name)
            openapi = repository / "uploaded-openapi" / Path(openapi_file.name).name
            openapi.parent.mkdir()
            openapi.write_bytes(openapi_file.getvalue())
        elif inventory.openapi_candidates:
            openapi = repository / inventory.openapi_candidates[0]

        if openapi is None:
            if not model.operations and not model.entities:
                raise IntakeError(
                    "No supported controllers or endpoint contract models were discovered in the "
                    "controller projects. "
                    "The current analyzer supports ASP.NET Core MVC controller projects."
                )
            generate_artifacts(model, output)
        else:
            openapi_model = discover_openapi(openapi, region.strip(), system.strip(), repository)
            model = reconcile(model, openapi_model)
            if not model.operations and not model.entities:
                raise IntakeError(
                    "No supported operations or endpoint contract models were discovered in the "
                    "repository."
                )
            generate_artifacts(model, output)

        artifacts = {
            label: (output / filename).read_bytes()
            for label, filename in DISCOVERY_ARTIFACTS.items()
        }
        discovery_model = (output / "discovery-model.json").read_bytes()
        return artifacts, selected_projects, discovery_model


# Persist UUID-backed runs that were already in the live session when history was introduced.
for existing_application_id in st.session_state["application_runs"]:
    if (
        RUN_ID_PATTERN.fullmatch(existing_application_id)
        and not (APPLICATION_HISTORY_ROOT / existing_application_id / "record.json").is_file()
    ):
        persist_application(existing_application_id)


if st.session_state["discovery_model"] is not None and not st.session_state["application_runs"]:
    uploaded_repository = st.session_state.get("repository_zip")
    uploaded_openapi = st.session_state.get("openapi_document")
    save_application(
        discovery_model=st.session_state["discovery_model"],
        discovery_artifacts=st.session_state["discovery_artifacts"],
        projects=st.session_state["discovery_projects"],
        repository_archive=st.session_state["repository_archive"],
        repository_name=(
            uploaded_repository.name if uploaded_repository else "Current repository ZIP"
        ),
        openapi_name=uploaded_openapi.name if uploaded_openapi else "Not uploaded",
    )
elif (
    st.session_state["application_runs"]
    and st.session_state["active_application_id"] not in st.session_state["application_runs"]
):
    activate_application(next(iter(st.session_state["application_runs"])))


st.title("Canonical Model platform")

CRAWLER_TAB_LABELS = [
    ":material/account_tree: 1 Discovery",
    ":material/search: 2 Repository RAG",
    ":material/manage_search: 3 API analyzer",
    ":material/public: 4 Regional view",
]
ACORD_TAB_LABELS = [
    ":material/library_books: ACORD ingestion",
    ":material/compare_arrows: ACORD alignment",
    ":material/hub: Canonical model",
]
WORKFLOW_TAB_LABELS = CRAWLER_TAB_LABELS + ACORD_TAB_LABELS

if st.session_state.get("workflow_tabs") == ":material/hub: Canonical view":
    st.session_state["workflow_tabs"] = ACORD_TAB_LABELS[2]


def open_crawler_workspace() -> None:
    """Open a selected crawler-code workspace."""
    selected = st.session_state.get("crawler_sidebar_menu")
    if selected:
        st.session_state["workflow_tabs"] = selected
        st.session_state["crawler_tabs"] = selected
        st.session_state["acord_sidebar_menu"] = None


def open_acord_workspace() -> None:
    """Open a selected ACORD workspace."""
    selected = st.session_state.get("acord_sidebar_menu")
    if selected:
        st.session_state["workflow_tabs"] = selected
        st.session_state["crawler_sidebar_menu"] = None


def open_crawler_tab() -> None:
    """Synchronize a visible crawler tab with the sidebar workspace state."""
    selected = st.session_state.get("crawler_tabs")
    if selected:
        st.session_state["workflow_tabs"] = selected
        st.session_state["crawler_sidebar_menu"] = selected
        st.session_state["acord_sidebar_menu"] = None


with st.sidebar:
    current_workspace = st.session_state.get("workflow_tabs", CRAWLER_TAB_LABELS[0])

    # ── Branded header ────────────────────────────────────────────────────────
    st.html("""
<div style="padding:22px 4px 0;text-align:center">
  <div style="width:56px;height:56px;
              background:linear-gradient(135deg,#dbeafe,#eff6ff);
              border:1.5px solid #bfdbfe;border-radius:16px;
              display:inline-flex;align-items:center;justify-content:center;
              font-size:26px;margin-bottom:12px;
              box-shadow:0 2px 10px rgba(37,99,235,.12)">🏗️</div>
  <div style="color:#1e293b;font-size:1.0rem;font-weight:700;font-family:system-ui;
              letter-spacing:-.01em;line-height:1.3">Canonical<br>Model Platform</div>
  <div style="color:#64748b;font-size:.63rem;margin-top:5px;
              font-family:system-ui;letter-spacing:.08em;text-transform:uppercase">
    v1.0 &ensp;·&ensp; Phase 1 MVP
  </div>
</div>
<div style="border-top:1px solid #e2e8f0;margin:18px 0 6px"></div>
""")

    # ── Crawler section ───────────────────────────────────────────────────────
    st.html("""
<div style="display:flex;align-items:center;gap:8px;margin:6px 2px 4px">
  <span style="font-size:14px">🔍</span>
  <span style="color:#334155;font-size:.72rem;font-weight:700;
               text-transform:uppercase;letter-spacing:.1em;font-family:system-ui">
    Crawler Workflow
  </span>
  <div style="flex:1;height:1px;background:#e2e8f0"></div>
</div>
""")
    st.pills(
        "Crawler workspace",
        CRAWLER_TAB_LABELS,
        default=current_workspace if current_workspace in CRAWLER_TAB_LABELS else None,
        key="crawler_sidebar_menu",
        on_change=open_crawler_workspace,
        label_visibility="collapsed",
    )

    # ── ACORD section ─────────────────────────────────────────────────────────
    st.html("""
<div style="display:flex;align-items:center;gap:8px;margin:18px 2px 4px">
  <span style="font-size:14px">📋</span>
  <span style="color:#334155;font-size:.72rem;font-weight:700;
               text-transform:uppercase;letter-spacing:.1em;font-family:system-ui">
    ACORD &amp; Canonical
  </span>
  <div style="flex:1;height:1px;background:#e2e8f0"></div>
</div>
""")
    st.pills(
        "ACORD workspace",
        ACORD_TAB_LABELS,
        default=current_workspace if current_workspace in ACORD_TAB_LABELS else None,
        key="acord_sidebar_menu",
        on_change=open_acord_workspace,
        label_visibility="collapsed",
    )

    # ── Footer ────────────────────────────────────────────────────────────────
    st.html("""
<div style="border-top:1px solid #e2e8f0;margin:22px 0 0;
            padding:14px 4px 6px;text-align:center">
  <div style="color:#94a3b8;font-size:.62rem;font-family:system-ui;
              letter-spacing:.04em;line-height:1.6">
    
  </div>
</div>
""")

if current_workspace in CRAWLER_TAB_LABELS:
    render_workflow_progress()

if "crawler_tabs" not in st.session_state:
    st.session_state["crawler_tabs"] = (
        current_workspace if current_workspace in CRAWLER_TAB_LABELS else CRAWLER_TAB_LABELS[0]
    )

discovery_tab, rag_tab, phase_two_tab, regional_tab = st.tabs(
    CRAWLER_TAB_LABELS,
    key="crawler_tabs",
    on_change=open_crawler_tab,
)
acord_ingestion_tab = st.container(key="acord_ingestion_page")
acord_alignment_tab = st.container(key="acord_alignment_page")
canonical_view_tab = st.container(key="canonical_view_page")

visible_page_key = {
    ACORD_TAB_LABELS[0]: "acord_ingestion_page",
    ACORD_TAB_LABELS[1]: "acord_alignment_page",
    ACORD_TAB_LABELS[2]: "canonical_view_page",
}.get(current_workspace)
hidden_page_keys = {
    "acord_ingestion_page",
    "acord_alignment_page",
    "canonical_view_page",
} - ({visible_page_key} if visible_page_key else set())
hidden_selectors = [f".st-key-{key}" for key in sorted(hidden_page_keys)]
if current_workspace not in CRAWLER_TAB_LABELS:
    hidden_selectors.append(".st-key-crawler_tabs")
st.html(f"<style>{', '.join(hidden_selectors)} {{ display: none; }}</style>")

with discovery_tab:
    st.header("Discovery Agent")
    st.caption(
        "Create a regional application profile, then provide the trusted source inputs to "
        "build its discovery artifacts."
    )
    if st.session_state["application_runs"]:
        with st.expander("Open a previous application", expanded=False):
            historical_runs = st.session_state["application_runs"]
            historical_ids = list(historical_runs)
            historical_id = st.selectbox(
                "Saved application",
                historical_ids,
                format_func=lambda item: (
                    f"{historical_runs[item]['profile']['application']} · "
                    f"{historical_runs[item]['profile']['region']} · "
                    f"{historical_runs[item]['profile']['repository']} [{item[:6]}]"
                ),
                key="historical_application",
            )
            if st.button(
                "Open saved application",
                icon=":material/history:",
                key="open_historical_application",
            ):
                activate_application(historical_id)
                st.rerun()
    with st.form("discovery_agent", border=True):
        st.subheader("Application details", anchor=False)
        st.caption(
            "These values identify the source application in every generated artifact. "
            "Use a stable name that your teams will recognize."
        )
        region_column, application_column = st.columns(2, gap="large")
        with region_column:
            region = st.selectbox(
                "Region",
                options=list(REGIONS),
                index=None,
                format_func=lambda code: f"{code} — {REGIONS.get(code, code)}",
                placeholder="Select or enter a region code",
                accept_new_options=True,
                help=(
                    "Choose a common ISO country code or enter the regional code used by your "
                    "organization, such as EU or LATAM."
                ),
                key="region",
            )
        with application_column:
            system = st.text_input(
                "Application name",
                placeholder="regional-quote-api",
                help=(
                    "A stable source-system name used to identify this application in generated "
                    "models and lineage."
                ),
                key="system",
            )

        st.subheader("Source inputs", anchor=False)
        st.caption("Upload a repository ZIP and, optionally, an OpenAPI YAML/JSON document.")
        repository_column, contract_column = st.columns(2, gap="large")
        with repository_column:
            repository_file: UploadedFile | None = st.file_uploader(
                "Trusted .NET repository ZIP",
                type="zip",
                max_upload_size=100,
                help=("Required. Roslyn/MSBuild analyzes the repository as trusted code."),
                key="repository_zip",
            )
            st.caption("Repository input · ZIP · Up to 100 MB")
        with contract_column:
            openapi_file: UploadedFile | None = st.file_uploader(
                "OpenAPI document",
                type=["json", "yaml", "yml"],
                max_upload_size=10,
                help=(
                    "Optional. When supplied, the specification is reconciled with repository "
                    "evidence."
                ),
                key="openapi_document",
            )
            st.caption("Specification input · JSON or YAML · Up to 10 MB")

        submitted = st.form_submit_button(
            "Analyze application", type="primary", icon=":material/play_arrow:"
        )

    if submitted:
        if not region or not region.strip() or not system.strip() or repository_file is None:
            st.error("Region, application name, and a repository ZIP are required.")
        else:
            try:
                with st.status("Running deterministic discovery...", expanded=True) as status:
                    st.write("Inspecting and extracting the trusted repository")
                    st.write("Running Roslyn and optional OpenAPI discovery")
                    artifacts, selected_projects, discovery_model = run_uploaded_discovery(
                        region=region,
                        system=system,
                        repository_file=repository_file,
                        openapi_file=openapi_file,
                    )
                    st.write("Validating and generating five artifacts")
                    save_application(
                        discovery_model=discovery_model,
                        discovery_artifacts=artifacts,
                        projects=selected_projects,
                        repository_archive=repository_file.getvalue(),
                        repository_name=repository_file.name,
                        openapi_name=openapi_file.name if openapi_file else "Not uploaded",
                    )
                    status.update(label="Discovery complete", state="complete", expanded=False)
            except (IntakeError, OSError, RuntimeError, ValueError) as exc:
                st.error(str(exc))

    artifacts: dict[str, bytes] = st.session_state["discovery_artifacts"]
    if artifacts:
        active_run = st.session_state["application_runs"][st.session_state["active_application_id"]]
        profile = active_run["profile"]
        with st.container(border=True):
            st.badge("Discovery complete", color="green", icon=":material/check:")
            profile_columns = st.columns(3)
            profile_columns[0].metric("Region", profile["region"])
            profile_columns[1].metric("Application", profile["application"])
            profile_columns[2].metric(
                "Projects analyzed", len(st.session_state["discovery_projects"])
            )
            st.caption(f"Repository: {profile['repository']}")
            st.caption("Projects: " + ", ".join(st.session_state["discovery_projects"]))
        st.warning(
            "Current entity coverage includes user-authored request, response, DTO, domain, "
            "ViewModel, nested property, collection-element, and inherited models reachable "
            "from API endpoints. Generated types and unrelated models are excluded. "
            "Deep call paths, persistence, mappings, integrations, security, and Razor Pages "
            "remain open gaps. When OpenAPI is supplied, its schemas are reconciled with the "
            "repository evidence.",
            icon=":material/radar:",
        )
        st.subheader("Discovery artifact tree")
        st.markdown(
            "Repository/OpenAPI → Discovery Agent → API Catalog, Data Model, "
            "Relationship Graph, Validation and Enums, and Lineage."
        )

        discovery_content, discovery_gallery = st.columns([2.2, 1], gap="large")
        with discovery_content:
            preview_label = st.selectbox(
                "Preview artifact", list(artifacts), key="artifact_preview"
            )
            st.json(json.loads(artifacts[preview_label]), expanded=2)
        with discovery_gallery:
            render_artifact_download_gallery(
                title="Discovery download gallery",
                artifacts=artifacts,
                filenames=DISCOVERY_ARTIFACTS,
                key_prefix="download_discovery",
                bundle=build_artifact_bundle(artifacts),
                bundle_filename="discovery-artifacts.zip",
            )

with rag_tab:
    st.header("Repository RAG")
    st.caption(
        "Build reusable code context, then inspect what an endpoint, model or field retrieves. "
        "Code is grouped by file, type and member, with parent and relationship links."
    )
    active_id = st.session_state["active_application_id"]
    application_runs = st.session_state["application_runs"]
    if application_runs:
        rag_choices = [
            *([active_id] if active_id in application_runs else []),
            *(item for item in application_runs if item != active_id),
        ]
        rag_selected_id = st.selectbox(
            "Select application index",
            rag_choices,
            index=rag_choices.index(active_id) if active_id in rag_choices else 0,
            format_func=lambda item: (
                f"{application_runs[item]['profile']['region']} · "
                f"{application_runs[item]['profile']['application']} · "
                f"{application_runs[item]['profile']['repository']} [{item[:6]}] · "
                + ("current discovery · " if item == active_id else "")
                + (
                    "RAG ready"
                    if application_runs[item].get("rag_store_path")
                    and Path(
                        application_runs[item]["rag_store_path"], "rag-manifest.json"
                    ).is_file()
                    else "no RAG index"
                )
            ),
            key=f"rag_application_{active_id}",
        )
        if rag_selected_id != active_id:
            activate_application(rag_selected_id)
            st.rerun()
        active_id = rag_selected_id
    if active_id:
        profile = st.session_state["application_runs"][active_id]["profile"]
        st.info(
            f"Selected application: {profile['application']} · {profile['region']} · "
            f"{profile['repository']}"
        )
    embedding_provider = st.selectbox(
        "Embedding provider", ["Sentence Transformer (local)", "OpenAI"], key="rag_provider"
    )
    embedding_name = st.selectbox(
        "Embedding model",
        [LOCAL_MODEL] if embedding_provider.startswith("Sentence") else list(OPENAI_MODELS),
        key="rag_embedding_model",
    )
    cloud_embedding_consent = (
        st.checkbox(
            "Allow redacted repository chunks to be sent to OpenAI for embedding.",
            key="rag_cloud_consent",
        )
        if embedding_provider == "OpenAI"
        else False
    )
    if embedding_provider.startswith("Sentence"):
        st.caption("Runs on this computer. The first run downloads the embedding model.")
    else:
        st.caption("Indexing sends all included redacted chunks to OpenAI and incurs API usage.")
    repository_bytes = st.session_state["repository_archive"]
    if repository_bytes is None:
        st.info("Upload a repository here to build code retrieval independently of discovery.")
        rag_upload = st.file_uploader("Repository for code retrieval", type="zip", key="rag_upload")
        repository_bytes = rag_upload.getvalue() if rag_upload else None
    st.caption(
        "Each build creates a fresh index for the currently selected upload. "
        "The API Analyzer uses only that application's index."
    )
    if st.button("Build repository index", key="build_rag", disabled=repository_bytes is None):
        rag_index = None
        try:
            profile = EmbeddingConfig(
                provider="openai" if embedding_provider == "OpenAI" else "sentence_transformer",
                model=embedding_name,
            )
            adapter = create_embedder(
                profile, api_key=openai_api_key(), allow_source_sharing=cloud_embedding_consent
            )
            inspect_repository_zip(repository_bytes)
            with st.status("Building repository index...", expanded=True) as status:
                with TemporaryDirectory(prefix="canonical-rag-") as temporary:
                    repository_root = Path(temporary)
                    with ZipFile(BytesIO(repository_bytes)) as archive:
                        archive.extractall(repository_root)
                    run_directory = active_id or "standalone"
                    storage = Path(__file__).resolve().parent / ".rag" / run_directory / uuid4().hex
                    rag_index = ChromaRepositoryIndex(storage, adapter)
                    model = (
                        DiscoveryModel.model_validate_json(st.session_state["discovery_model"])
                        if st.session_state["repository_archive"] is not None
                        else None
                    )
                    rag_index.ingest(repository_root, model, st.write)
                    st.session_state["rag_store_path"] = str(storage)
                    st.session_state["rag_manifest"] = rag_index.manifest
                    if st.session_state["repository_archive"] is not None and active_id:
                        run = st.session_state["application_runs"][active_id]
                        run["rag_store_path"] = str(storage)
                        run["rag_manifest"] = rag_index.manifest
                        run["phase_2_artifacts"] = {}
                        run["phase_2_error"] = None
                        st.session_state["phase_2_artifacts"] = {}
                        st.session_state["phase_2_error"] = None
                        persist_application(active_id)
                    st.session_state["rag_results"] = []
                    st.session_state["rag_semantics"] = None
                status.update(label="Repository index ready", state="complete", expanded=False)
        except Exception as exc:
            st.error(f"Repository indexing failed: {exc}")
        finally:
            if rag_index is not None:
                rag_index.close()

    rag_manifest = st.session_state["rag_manifest"]
    if rag_manifest:
        stats = rag_manifest["stats"]
        with st.container(horizontal=True):
            st.metric("Files indexed", stats["filesIndexed"])
            st.metric("Code chunks", stats["chunksIndexed"])
            st.metric("Relationships", stats["relationshipsIndexed"])
        st.caption(f"Saved locally: {st.session_state['rag_store_path']}")
        st.success(
            "Existing repository index reopened for the selected application.",
            icon=":material/database:",
        )
        st.caption(f"Embedding model: {rag_manifest['embedding']['model']}")
        st.download_button(
            "Download RAG manifest",
            json.dumps(rag_manifest, indent=2),
            file_name="rag-manifest.json",
            mime="application/json",
        )
        if stats["gaps"]:
            with st.expander("Index coverage gaps"):
                st.json(stats["gaps"])
        target_kind = st.selectbox(
            "Retrieve by", ["endpoint", "entity", "attribute", "enum", "code query"]
        )
        candidates = [t for t in rag_manifest["targets"] if t["kind"] == target_kind]
        target_map = {t["id"]: t for t in candidates}
        target_id = (
            st.selectbox(
                "Discovered target",
                list(target_map),
                format_func=lambda key: target_map[key]["label"],
                key=f"rag_target_{target_kind}",
            )
            if candidates
            else None
        )
        query_text = st.text_input(
            "Code query", placeholder="QuoteService.Create or QuoteResponse.Premium"
        )
        if st.button("Retrieve code context", key="retrieve_rag"):
            rag_index = None
            try:
                profile = EmbeddingConfig.model_validate(rag_manifest["embedding"])
                adapter = create_embedder(
                    profile, api_key=openai_api_key(), allow_source_sharing=cloud_embedding_consent
                )
                rag_index = ChromaRepositoryIndex(Path(st.session_state["rag_store_path"]), adapter)
                query = query_text.strip() or (target_map[target_id]["label"] if target_id else "")
                st.session_state["rag_results"] = rag_index.query(query, subject_id=target_id)
                st.session_state["rag_semantics"] = None
            except Exception as exc:
                st.error(f"Code retrieval failed: {exc}")
            finally:
                if rag_index is not None:
                    rag_index.close()
        for snippet in st.session_state["rag_results"]:
            with st.expander(f"{snippet['symbol']} — {snippet['path']}:{snippet['startLine']}"):
                st.caption(f"Retrieved via {snippet['retrievalReason']}; {snippet['kind']}")
                st.code(snippet["text"], language="csharp")
                if snippet["truncated"]:
                    st.caption("Bounded preview; additional content is stored in child chunks.")
        if st.session_state["rag_results"]:
            st.subheader("Interpret the retrieved code")
            st.caption(
                "The API Analyzer reads the selected code context and returns inferred meaning "
                "with source locations and uncertainty."
            )
            semantic_consent = st.checkbox(
                "Allow these selected, redacted code snippets to be sent to OpenAI.",
                key="rag_semantic_consent",
            )
            semantic_model = resolve_openai_model()
            st.caption(f"Interpretation model from .env: {semantic_model}")
            if st.button(
                "Explain selected target" if target_id else "Explain retrieved code",
                key="rag_explain_target",
                disabled=not semantic_consent or not openai_api_key(),
            ):
                focused_index = None
                try:
                    profile = EmbeddingConfig.model_validate(rag_manifest["embedding"])
                    adapter = create_embedder(
                        profile,
                        api_key=openai_api_key(),
                        allow_source_sharing=cloud_embedding_consent,
                    )
                    focused_index = ChromaRepositoryIndex(
                        Path(st.session_state["rag_store_path"]), adapter
                    )
                    semantic_provider = OpenAISemanticProvider(
                        api_key=openai_api_key() or "", model=semantic_model
                    )
                    if target_id and st.session_state["discovery_model"]:
                        st.session_state["rag_semantics"] = inspect_retrieved_target(
                            st.session_state["discovery_model"],
                            focused_index,
                            target_id,
                            semantic_provider,
                        )
                    else:
                        st.session_state["rag_semantics"] = inspect_retrieved_code(
                            focused_index, query_text.strip(), semantic_provider
                        )
                except Exception as exc:
                    st.error(
                        f"Code interpretation failed: {type(exc).__name__}. "
                        "Check provider access and target evidence."
                    )
                finally:
                    if focused_index is not None:
                        focused_index.close()
            interpretation = st.session_state["rag_semantics"]
            if (
                interpretation
                and interpretation.get("targetId") == target_id
                and (target_id or interpretation.get("query") == query_text.strip())
            ):
                if interpretation["status"] == "unknown":
                    st.warning(interpretation["reason"])
                else:
                    if "confidence" in interpretation:
                        st.caption(
                            f"{interpretation['status'].capitalize()} interpretation with "
                            f"provider confidence {interpretation['confidence']:.2f} "
                            f"by {interpretation['model']}"
                        )
                    else:
                        st.caption(
                            f"Code interpretation by {interpretation['model']}; "
                            "see confidence on each claim."
                        )
                    st.json(interpretation["semantic"], expanded=2)
                    if interpretation.get("codeAnalysis"):
                        st.caption(
                            "Code observations and inferred meaning (each claim cites chunks)"
                        )
                        st.json(interpretation["codeAnalysis"], expanded=2)
                    st.caption("Source context considered")
                    st.json(interpretation["citations"], expanded=1)
                    if interpretation["gaps"]:
                        st.warning("Open context: " + "; ".join(interpretation["gaps"]))

with phase_two_tab:
    if not st.session_state["phase_2_unlocked"] or not st.session_state["application_runs"]:
        st.info(
            "Run the Discovery Agent to create an application for Phase 2.", icon=":material/lock:"
        )
    else:
        st.header("API Analyzer Agent")
        runs = st.session_state["application_runs"]
        active_id = st.session_state["active_application_id"]
        choices = list(runs)
        selected_id = st.selectbox(
            "Select discovered application",
            choices,
            index=choices.index(active_id),
            format_func=lambda item: (
                f"{runs[item]['profile']['application']} · {runs[item]['profile']['region']} · "
                f"{runs[item]['profile']['repository']} [{item[:6]}] · "
                + (
                    "RAG ready"
                    if runs[item].get("rag_store_path")
                    and Path(runs[item]["rag_store_path"], "rag-manifest.json").is_file()
                    else "no RAG index"
                )
            ),
            key=f"phase2_application_{active_id}",
        )
        if selected_id != active_id:
            activate_application(selected_id)
            st.rerun()
        profile = runs[active_id]["profile"]
        with st.container(border=True):
            st.subheader("Selected application", anchor=False)
            with st.container(horizontal=True):
                st.metric("Region", profile["region"])
                st.metric("Application", profile["application"])
            st.caption(f"Repository ZIP: {profile['repository']}")
            st.caption(f"OpenAPI upload: {profile['openapi']}")
            st.caption(
                "Repository RAG: "
                + (
                    "ready for this application"
                    if st.session_state["rag_store_path"]
                    else "not built for this application"
                )
            )
        st.caption(
            "The agent reuses the saved repository index when available, retrieves "
            "bounded code evidence, classifies domain and capability, and explains endpoints, "
            "endpoint contract models, attributes, and enums before generating a self-contained "
            "enriched OpenAPI 3.0 specification. Structural facts continue to come only from "
            "Phase 1."
        )
        previous_error = st.session_state.get("phase_2_error")
        if previous_error:
            st.error(f"Previous API Analyzer run failed: {previous_error}")
            st.caption("Correct the issue above, then run the selected application again.")
        if st.session_state["repository_archive"] is None:
            st.error(
                "API Analyzer requires repository source; specification-only runs are disabled."
            )
        api_key = openai_api_key()
        if api_key:
            st.badge(
                "API key available; checked when run starts", color="green", icon=":material/key:"
            )
        else:
            st.warning(
                "Set OPENAI_API_KEY in the ignored .env file in the project root and restart "
                "the app. The key is never written to an artifact.",
                icon=":material/key:",
            )
        openai_model = resolve_openai_model()
        st.caption(
            f"OpenAI model from .env: {openai_model}. The model must support Structured "
            "Outputs in the Responses API."
        )
        with st.expander("LLM usage guardrails"):
            max_run_tokens = st.number_input(
                "Maximum tokens for this run",
                min_value=5_000,
                max_value=1_000_000,
                value=120_000,
                step=5_000,
                help=(
                    "The analyzer estimates each request with tiktoken before sending it and "
                    "stops before the projected total exceeds this ceiling."
                ),
            )
            max_llm_requests = st.number_input(
                "Maximum paid LLM requests",
                min_value=1,
                max_value=500,
                value=100,
                step=1,
            )
            max_input_tokens = st.number_input(
                "Maximum input tokens per request",
                min_value=1_000,
                max_value=200_000,
                value=24_000,
                step=1_000,
                key="phase_2_max_input_tokens",
            )
            max_output_tokens = st.number_input(
                "Maximum output tokens per request",
                min_value=500,
                max_value=100_000,
                value=4_000,
                step=500,
                key="phase_2_max_output_tokens",
            )
            st.caption(
                "The provider-reported input and output count for every completed request is "
                "written to the enrichment report and a separate JSON file under the sidebar "
                "log location."
            )
        source_consent = st.checkbox(
            "Allow selected specification details and redacted code (when available) "
            "to be sent to OpenAI.",
            key="phase_2_source_consent",
        )
        missing = []
        if st.session_state["discovery_model"] is None:
            missing.append("Select an application with completed Discovery.")
        if st.session_state["repository_archive"] is None:
            missing.append("Select an application with its trusted repository archive.")
        if not (
            st.session_state["rag_store_path"]
            and (Path(st.session_state["rag_store_path"]) / "rag-manifest.json").is_file()
        ):
            missing.append("Build or reopen this application's repository index in Repository RAG.")
        if not api_key:
            missing.append("Provide an OpenAI API key.")
        if not source_consent:
            missing.append("Acknowledge source sharing above.")
        if missing:
            st.info("Before running: " + " ".join(missing))
        else:
            st.success("Ready to analyze the selected application.")
        previous_artifacts = dict(st.session_state["phase_2_artifacts"])
        can_continue = has_unfinished_semantic_targets(previous_artifacts)
        continue_clicked = False
        if can_continue:
            st.caption(
                "This run is partial. Continue reuses completed semantic results and starts a "
                "fresh token budget only for unfinished targets."
            )
            continue_clicked = st.button(
                "Continue remaining analysis",
                type="primary",
                icon=":material/play_arrow:",
                key="continue_phase_2_semantic_openapi",
                disabled=bool(missing),
                help=(
                    "Reuse completed endpoint, entity, and enum results and call the LLM only "
                    "for unfinished targets with a fresh run budget."
                ),
            )
        rerun = bool(previous_artifacts or previous_error)
        restart_clicked = st.button(
            ("Restart API Analyzer from beginning" if rerun else "Run API Analyzer Agent"),
            type="secondary" if can_continue else "primary",
            icon=":material/auto_awesome:",
            key="run_phase_2_semantic_openapi",
            disabled=bool(missing),
        )
        if continue_clicked or restart_clicked:
            resume_artifacts = previous_artifacts if continue_clicked else None
            if restart_clicked:
                st.session_state["phase_2_artifacts"] = {}
                runs[active_id]["phase_2_artifacts"] = {}
            st.session_state["phase_2_error"] = None
            runs[active_id]["phase_2_error"] = None
            try:
                provider = OpenAISemanticProvider(
                    api_key=api_key or "",
                    model=openai_model,
                    token_budget=TokenBudgetConfig(
                        max_run_tokens=int(max_run_tokens),
                        max_requests=int(max_llm_requests),
                        max_input_tokens_per_request=int(max_input_tokens),
                        max_output_tokens_per_request=int(max_output_tokens),
                    ),
                )
                adapter = None
                if st.session_state["rag_manifest"]:
                    profile = EmbeddingConfig.model_validate(
                        st.session_state["rag_manifest"]["embedding"]
                    )
                    adapter = create_embedder(
                        profile, api_key=api_key, allow_source_sharing=source_consent
                    )
                with st.status("Running API Analyzer Agent...", expanded=True) as status:
                    generated = run_uploaded_semantic_generation(
                        repository_archive=st.session_state["repository_archive"],
                        discovery_artifact=st.session_state["discovery_model"],
                        provider=provider,
                        progress=st.write,
                        rag_store_path=Path(st.session_state["rag_store_path"])
                        if st.session_state["rag_store_path"]
                        else None,
                        embedder=adapter,
                        resume_artifacts=resume_artifacts,
                    )
                    st.session_state["phase_2_artifacts"] = generated
                    runs[active_id]["phase_2_artifacts"] = generated
                    generated_report = json.loads(generated["enrichment-report.json"])
                    if generated_report["providerStatus"] == "failed":
                        failure = (
                            generated_report["validationErrors"][0]
                            if generated_report["validationErrors"]
                            else "Provider validation failed."
                        )
                        st.session_state["phase_2_error"] = failure
                        runs[active_id]["phase_2_error"] = failure
                        status.update(
                            label="API Analyzer stopped during provider validation",
                            state="error",
                            expanded=True,
                        )
                    else:
                        status.update(
                            label="API Analyzer Agent complete",
                            state="complete",
                            expanded=False,
                        )
                    persist_application(active_id)
                st.rerun()
            except Exception as exc:
                failure = str(exc)
                st.session_state["phase_2_error"] = failure
                runs[active_id]["phase_2_error"] = failure
                persist_application(active_id)
                st.error(f"Semantic OpenAPI generation failed: {failure}")
                st.rerun()

        phase_2_artifacts: dict[str, bytes] = {
            filename: content
            for filename, content in st.session_state["phase_2_artifacts"].items()
            if Path(filename).suffix.casefold() in {".json", ".yaml", ".yml"}
        }
        if phase_2_artifacts:
            report = json.loads(phase_2_artifacts["enrichment-report.json"])
            with st.container(horizontal=True):
                st.metric("Endpoints discovered", report["endpointsDiscovered"])
                st.metric("Endpoints enriched", report["endpointsEnriched"])
                st.metric("Domains classified", report["domainsClassified"])
                st.metric("Capabilities", report["capabilitiesClassified"])
            with st.container(horizontal=True):
                st.metric("Contract models discovered", report["entitiesDiscovered"])
                st.metric("Contract models enriched", report["entitiesEnriched"])
                st.metric("Attributes enriched", report["attributesEnriched"])
                st.metric("Enums enriched", report["enumsEnriched"])
            with st.container(horizontal=True):
                st.metric("Needs more context", len(report["needsMoreContextTargets"]))
                st.metric("Open issues", len(report["validationErrors"]))
                st.metric(
                    "Repository files indexed", report.get("retrieval", {}).get("filesIndexed", 0)
                )
                st.metric("Chroma chunks", report.get("retrieval", {}).get("chunksIndexed", 0))
            if report["validationErrors"]:
                st.error(report["validationErrors"][0])
            if report["status"] == "partial":
                st.warning(
                    "The structural discovery result is preserved, but semantic enrichment is "
                    "partial. Review enrichment-report.json for validation and coverage gaps.",
                    icon=":material/warning:",
                )
            with st.container(horizontal=True):
                for filename, content in phase_2_artifacts.items():
                    mime = "application/yaml" if filename.endswith(".yaml") else "application/json"
                    st.download_button(
                        f"Download {filename}",
                        data=content,
                        file_name=filename,
                        mime=mime,
                        icon=":material/download:",
                        key=f"download_phase_2_{filename}",
                    )
            st.download_button(
                "Download all Phase 2 artifacts",
                data=build_named_bundle(phase_2_artifacts),
                file_name="semantic-openapi-artifacts.zip",
                mime="application/zip",
                icon=":material/folder_zip:",
                key="download_all_phase_2_artifacts",
            )
            preview_name = st.selectbox(
                "Preview Phase 2 artifact", list(phase_2_artifacts), key="phase_2_preview"
            )
            if preview_name.endswith(".yaml"):
                st.code(phase_2_artifacts[preview_name].decode("utf-8"), language="yaml")
            else:
                st.json(json.loads(phase_2_artifacts[preview_name]), expanded=2)

with regional_tab:
    st.header("Regional API catalog")
    st.caption(
        "Compare endpoint contract models, domains and capabilities across every completed "
        "application in a region. Select all APIs or focus on one Claim, Quote or other API."
    )
    runs = st.session_state["application_runs"]
    if not runs:
        st.info(
            "Run the Discovery Agent for an EU, US or other regional application to populate "
            "this catalog.",
            icon=":material/info:",
        )
    else:
        available_regions = sorted(
            {run["profile"]["region"] for run in runs.values()},
            key=str.casefold,
        )
        selected_region = st.selectbox(
            "Region",
            available_regions,
            format_func=lambda code: f"{code} — {REGIONS.get(code, code)}",
            key="regional_catalog_region",
        )
        regional_runs = {
            run_id: run
            for run_id, run in runs.items()
            if run["profile"]["region"] == selected_region
        }
        scope_options = [None, *regional_runs]
        selected_scope = st.selectbox(
            "API view",
            scope_options,
            format_func=lambda run_id: (
                "All APIs in region"
                if run_id is None
                else (
                    f"{regional_runs[run_id]['profile']['application']} · "
                    f"{regional_runs[run_id]['profile']['repository']} [{run_id[:6]}]"
                )
            ),
            key="regional_catalog_api",
        )
        model_rows, endpoint_rows = regional_catalog_rows(
            runs, region=selected_region, application_id=selected_scope
        )
        model_tree = regional_model_tree(
            runs, region=selected_region, application_id=selected_scope
        )
        domain_tree = regional_domain_tree(
            runs, region=selected_region, application_id=selected_scope
        )
        selected_run_ids = list(regional_runs) if selected_scope is None else [selected_scope]
        for run_id in selected_run_ids:
            report_content = runs[run_id].get("phase_2_artifacts", {}).get("enrichment-report.json")
            if not report_content:
                continue
            try:
                report = json.loads(report_content)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                continue
            if report.get("status") == "complete":
                continue
            st.warning(
                f"{runs[run_id]['profile']['application']} has partial API Analyzer coverage: "
                f"{report.get('endpointsEnriched', 0)}/{report.get('endpointsDiscovered', 0)} "
                f"endpoints and {report.get('entitiesEnriched', 0)}/"
                f"{report.get('entitiesDiscovered', 0)} models were enriched. "
                f"Stop reason: {report.get('stop_reason', 'not reported')}. "
                "Pending rows remain marked Awaiting API Analyzer.",
                icon=":material/warning:",
            )
        api_count = len(model_tree) if selected_scope is None else 1
        with st.container(horizontal=True):
            st.metric("APIs", api_count)
            st.metric("Endpoints", len(endpoint_rows))
            st.metric("Contract models", len(model_rows))
            st.metric(
                "Analyzed endpoints",
                sum(row["Domain"] != "Awaiting API Analyzer" for row in endpoint_rows),
            )

        models_tab, domains_tab, review_tab = st.tabs(
            [
                ":material/schema: Models and mappings",
                ":material/hub: Domains and capabilities",
                ":material/fact_check: Regional normalization review",
            ]
        )
        with models_tab:
            st.caption(
                "Expand the regional hierarchy to trace each API contract model to its "
                "request or response endpoints and fields."
            )
            if model_tree and model_rows:
                st.markdown(f"#### :material/public: {selected_region}")
                for branch in model_tree:
                    with st.container(border=True):
                        st.markdown(f"##### :material/api: {branch['api']}")
                        st.caption(
                            f"{branch['repository']} · {len(branch['models'])} contract models"
                        )
                        for model_branch in branch["models"]:
                            with st.expander(
                                f":material/schema: {model_branch['name']} · "
                                f"{len(model_branch['fields'])} fields"
                            ):
                                with st.container(horizontal=True):
                                    st.badge(f"Domain: {model_branch['domain']}")
                                    if model_branch["confidence"] is not None:
                                        st.badge(
                                            f"Confidence: {model_branch['confidence']:.2f}",
                                            color="blue",
                                        )
                                st.caption(f"Domain source: {model_branch['domainSource']}")
                                st.markdown(
                                    f"**Business concept:** {model_branch['businessConcept']}"
                                )
                                st.markdown(f"**Summary:** {model_branch['summary']}")
                                st.markdown(f"**Description:** {model_branch['description']}")
                                st.markdown("**Endpoint mappings**")
                                if model_branch["mappings"]:
                                    st.dataframe(
                                        model_branch["mappings"],
                                        hide_index=True,
                                        width="stretch",
                                    )
                                else:
                                    st.caption("No direct endpoint mapping was discovered.")
                                st.markdown("**Fields**")
                                if model_branch["fields"]:
                                    field_rows = [
                                        {key: value for key, value in field.items() if key != "id"}
                                        for field in model_branch["fields"]
                                    ]
                                    st.dataframe(
                                        field_rows,
                                        hide_index=True,
                                        width="stretch",
                                        column_config={
                                            "Confidence": st.column_config.NumberColumn(
                                                "Confidence",
                                                min_value=0,
                                                max_value=1,
                                                format="%.2f",
                                            ),
                                        },
                                    )
                                else:
                                    st.caption("No fields were discovered for this model.")
            else:
                st.info("No endpoint contract models were discovered for this selection.")
        with domains_tab:
            st.caption(
                "Expand the hierarchy to trace domains and capabilities across APIs and "
                "endpoints. Classifications come from completed API Analyzer output."
            )
            if domain_tree and endpoint_rows:
                st.markdown(f"#### :material/public: {selected_region}")
                for domain_branch in domain_tree:
                    endpoint_count = sum(
                        len(api["endpoints"])
                        for capability in domain_branch["capabilities"]
                        for api in capability["apis"]
                    )
                    with st.expander(
                        f":material/domain: {domain_branch['name']} · {endpoint_count} endpoints"
                    ):
                        for capability_branch in domain_branch["capabilities"]:
                            with st.container(border=True):
                                st.markdown(f"##### :material/hub: {capability_branch['name']}")
                                for api_branch in capability_branch["apis"]:
                                    st.markdown(f"**:material/api: {api_branch['name']}**")
                                    st.dataframe(
                                        api_branch["endpoints"],
                                        hide_index=True,
                                        width="stretch",
                                        column_config={
                                            "Confidence": st.column_config.NumberColumn(
                                                "Confidence",
                                                min_value=0,
                                                max_value=1,
                                                format="%.2f",
                                            )
                                        },
                                    )
            else:
                st.info("No endpoints were discovered for this selection.")
        with review_tab:
            st.caption(
                "Review every entity and attribute across the entire selected region. "
                "Approved duplicates are merged only in the downloadable regional view; all "
                "source entities, fields, APIs, and endpoints remain in the truth mapping."
            )
            entire_region_tree = regional_model_tree(runs, region=selected_region)
            entity_count = sum(len(branch["models"]) for branch in entire_region_tree)
            field_count = sum(
                len(model["fields"]) for branch in entire_region_tree for model in branch["models"]
            )
            with st.container(horizontal=True):
                st.metric("Regional APIs", len(regional_runs))
                st.metric("Source entities", entity_count)
                st.metric("Source attributes", field_count)

            if not entity_count:
                st.info("No endpoint contract entities were discovered in this region.")
            else:
                proposals = st.session_state["regional_normalizations"]
                ep_proposals = st.session_state["regional_endpoint_normalizations"]

                # helper: Select-All version tracking forces data_editor re-render
                def _sa_ver(section: str) -> int:
                    key = f"_sa_{section}_{selected_region}"
                    prev_key = f"_sa_{section}_prev_{selected_region}"
                    current = st.session_state.get(f"sa_{section}_{selected_region}", False)
                    if st.session_state.get(prev_key) != current:
                        st.session_state[prev_key] = current
                        st.session_state[key] = st.session_state.get(key, 0) + 1
                    return st.session_state.get(key, 0)

                # Saved decisions for pre-filling Approved/Comment on fresh load
                _saved_dec = st.session_state["regional_decisions"].get(selected_region, {})
                _saved_ent_dec = _saved_dec.get("entities", {})
                _saved_attr_dec = _saved_dec.get("attributes", {})
                _saved_ep_dec = _saved_dec.get("endpoints", {})

                # Build entity and attribute rows
                entity_rows_meta: list[str] = []
                entity_rows_display: list[dict] = []
                attr_rows_meta: list[tuple[str, str]] = []
                attr_rows_display: list[dict] = []
                for branch in entire_region_tree:
                    for model_branch in branch["models"]:
                        review_id = f"{branch['runId']}:{model_branch['id']}"
                        proposal = proposals.get(review_id, {})
                        suggested_attrs = {
                            item["attributeId"]: item for item in proposal.get("attributes", [])
                        }
                        _edec = _saved_ent_dec.get(review_id, {})
                        entity_rows_meta.append(review_id)
                        entity_rows_display.append(
                            {
                                "Select": False,
                                "API": branch["api"],
                                "Entity (original)": model_branch["name"],
                                "Domain": model_branch.get("domain", "Awaiting API Analyzer"),
                                "AI suggestion": proposal.get("normalizedName") or "—",
                                "Approved": _edec.get("selection", "Original"),
                                "Comment": _edec.get("comment", ""),
                            }
                        )
                        for field in model_branch["fields"]:
                            suggested = suggested_attrs.get(field["id"], {})
                            _adec = _saved_attr_dec.get(f"{review_id}:{field['id']}", {})
                            attr_rows_meta.append((review_id, field["id"]))
                            attr_rows_display.append(
                                {
                                    "Select": False,
                                    "API": branch["api"],
                                    "Entity": model_branch["name"],
                                    "Attribute (original)": field["Field"],
                                    "AI suggestion": suggested.get("normalizedName") or "—",
                                    "Type": field["Type"],
                                    "Approved": _adec.get("selection", "Original"),
                                    "Comment": _adec.get("comment", ""),
                                }
                            )

                # Entity table
                st.markdown("##### Entities")
                sa_ent = st.checkbox(
                    "Select all entities",
                    key=f"sa_entities_{selected_region}",
                )
                ent_ver = _sa_ver("entities")
                edited_entities = st.data_editor(
                    [{**r, "Select": sa_ent} for r in entity_rows_display],
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key=f"entity_review_{selected_region}_v{ent_ver}",
                    disabled=["API", "Entity (original)", "Domain", "AI suggestion"],
                    column_config={
                        "Select": st.column_config.CheckboxColumn(
                            "Select",
                            help="Check to include in LLM normalization",
                            default=False,
                        ),
                        "Approved": st.column_config.SelectboxColumn(
                            "Approved",
                            options=["Original", "AI suggestion"],
                            required=True,
                        ),
                        "Comment": st.column_config.TextColumn("Comment"),
                    },
                )
                _n_ent_sel = sum(1 for r in edited_entities if r.get("Select"))
                st.caption(
                    f"{'✓ ' + str(_n_ent_sel) + ' of ' + str(len(entity_rows_display)) + ' entities selected' if _n_ent_sel else '0 of ' + str(len(entity_rows_display)) + ' entities selected'}"
                )

                # Attribute table
                st.markdown("##### Attributes")
                sa_attr = st.checkbox(
                    "Select all attributes",
                    key=f"sa_attributes_{selected_region}",
                )
                attr_ver = _sa_ver("attributes")
                edited_attrs = st.data_editor(
                    [{**r, "Select": sa_attr} for r in attr_rows_display],
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key=f"attribute_review_{selected_region}_v{attr_ver}",
                    disabled=[
                        "API",
                        "Entity",
                        "Attribute (original)",
                        "AI suggestion",
                        "Type",
                    ],
                    column_config={
                        "Select": st.column_config.CheckboxColumn(
                            "Select",
                            help="Check to include in LLM normalization",
                            default=False,
                        ),
                        "Approved": st.column_config.SelectboxColumn(
                            "Approved",
                            options=["Original", "AI suggestion"],
                            required=True,
                        ),
                        "Comment": st.column_config.TextColumn("Comment"),
                    },
                )
                _n_attr_sel = sum(1 for r in edited_attrs if r.get("Select"))
                if _n_attr_sel:
                    _attr_parent_ids = {
                        attr_rows_meta[i][0]
                        for i in range(len(edited_attrs))
                        if edited_attrs[i].get("Select")
                    }
                    _np = len(_attr_parent_ids)
                    st.caption(
                        f"✓ {_n_attr_sel} of {len(attr_rows_display)} attributes selected"
                        f" → {_np} parent {'entity' if _np == 1 else 'entities'} queued for normalization"
                    )
                else:
                    st.caption(f"0 of {len(attr_rows_display)} attributes selected")

                # Endpoint table
                st.markdown("##### Endpoints")
                st.caption("Domain and Capability come from completed API Analyzer output.")
                endpoint_rows_meta: list[tuple[str, str]] = []
                endpoint_rows_display: list[dict] = []
                for branch in entire_region_tree:
                    ep_run = runs[branch["runId"]]
                    ep_discovery = DiscoveryModel.model_validate_json(ep_run["discovery_model"])
                    ep_meta_bytes = ep_run.get("phase_2_artifacts", {}).get(
                        "semantic-metadata.json"
                    )
                    try:
                        ep_meta = json.loads(ep_meta_bytes) if ep_meta_bytes else {}
                    except Exception:
                        ep_meta = {}
                    ep_semantics = {
                        item["operationId"]: item
                        for item in ep_meta.get("endpoints", [])
                        if isinstance(item, dict) and item.get("operationId")
                    }
                    for op in ep_discovery.operations:
                        norm_id = f"{branch['runId']}:{op.id}"
                        ep_proposal = ep_proposals.get(norm_id, {})
                        sem = ep_semantics.get(op.id, {})
                        domain_name = sem.get("domain", {}).get("name", "Awaiting API Analyzer")
                        cap_name = sem.get("capability", {}).get("name", "Awaiting API Analyzer")
                        _epdec = _saved_ep_dec.get(f"{branch['runId']}:{op.id}", {})
                        endpoint_rows_meta.append((branch["runId"], op.id))
                        endpoint_rows_display.append(
                            {
                                "Select": False,
                                "API": branch["api"],
                                "Endpoint (original)": op.name,
                                "Method": op.method.upper(),
                                "Route": op.route,
                                "Domain": domain_name,
                                "Capability": cap_name,
                                "AI suggestion": ep_proposal.get("normalizedName") or "—",
                                "Approved": _epdec.get("selection", "Original"),
                                "Comment": _epdec.get("comment", ""),
                            }
                        )
                if endpoint_rows_display:
                    sa_ep = st.checkbox(
                        "Select all endpoints",
                        key=f"sa_endpoints_{selected_region}",
                    )
                    ep_ver = _sa_ver("endpoints")
                    edited_endpoints = st.data_editor(
                        [{**r, "Select": sa_ep} for r in endpoint_rows_display],
                        hide_index=True,
                        use_container_width=True,
                        num_rows="fixed",
                        key=f"endpoint_review_{selected_region}_v{ep_ver}",
                        disabled=[
                            "API",
                            "Endpoint (original)",
                            "Method",
                            "Route",
                            "Domain",
                            "Capability",
                            "AI suggestion",
                        ],
                        column_config={
                            "Select": st.column_config.CheckboxColumn(
                                "Select",
                                help="Check to include in LLM normalization",
                                default=False,
                            ),
                            "Approved": st.column_config.SelectboxColumn(
                                "Approved",
                                options=["Original", "AI suggestion"],
                                required=True,
                            ),
                            "Comment": st.column_config.TextColumn("Comment"),
                        },
                    )
                    _n_ep_sel = sum(1 for r in edited_endpoints if r.get("Select"))
                    st.caption(
                        f"{'✓ ' + str(_n_ep_sel) if _n_ep_sel else '0'}"
                        f" of {len(endpoint_rows_display)} endpoints selected"
                    )
                else:
                    edited_endpoints = []
                    st.info("No endpoints were discovered in this region.")

                # Single unified normalize button (entities + endpoints)
                # Directly selected entities
                sel_entity_ids: dict[str, dict] = {
                    entity_rows_meta[i]: edited_entities[i]
                    for i in range(len(edited_entities))
                    if edited_entities[i].get("Select")
                }
                # Add parent entities of any selected attribute rows
                for i in range(len(edited_attrs)):
                    if edited_attrs[i].get("Select"):
                        parent_id = attr_rows_meta[i][0]  # review_id = runId:entityId
                        if parent_id not in sel_entity_ids:
                            parent_idx = entity_rows_meta.index(parent_id)
                            sel_entity_ids[parent_id] = edited_entities[parent_idx]
                sel_entities = list(sel_entity_ids.items())
                sel_endpoints = [
                    (endpoint_rows_meta[i], edited_endpoints[i])
                    for i in range(len(edited_endpoints))
                    if edited_endpoints[i].get("Select")
                ]
                n_attr_sel = sum(1 for r in edited_attrs if r.get("Select"))
                n_direct_ent = sum(1 for r in edited_entities if r.get("Select"))
                n_via_attr = len(sel_entities) - n_direct_ent
                total_sel = len(sel_entities) + len(sel_endpoints)

                _btn_ent_label = f"{n_direct_ent} entit{'y' if n_direct_ent == 1 else 'ies'}"
                if n_via_attr:
                    _btn_ent_label += f" + {n_via_attr} via {n_attr_sel} attr{'s' if n_attr_sel != 1 else ''}"
                _btn_ep_label = f"{len(sel_endpoints)} endpoint{'s' if len(sel_endpoints) != 1 else ''}"

                norm_model = resolve_openai_model()
                st.caption(f"Normalization model from .env: {norm_model}")
                norm_consent = st.checkbox(
                    "Allow selected items and their API Analyzer descriptions to be sent "
                    "to OpenAI.",
                    key=f"norm_consent_{selected_region}",
                )
                norm_api_key = openai_api_key()
                _nc1, _nc2 = st.columns([3, 1])
                with _nc1:
                    _do_normalize = st.button(
                        f"Normalize selected ({_btn_ent_label}, {_btn_ep_label})",
                        icon=":material/auto_fix_high:",
                        type="primary",
                        key=f"normalize_selected_{selected_region}",
                        disabled=(total_sel == 0 or not norm_consent or not norm_api_key),
                        use_container_width=True,
                    )
                with _nc2:
                    _do_save = st.button(
                        "Save draft",
                        icon=":material/save:",
                        key=f"save_decisions_{selected_region}",
                        use_container_width=True,
                        help="Save AI suggestions and Approved/Comment selections to disk so they survive page reload.",
                    )
                if _do_save:
                    _dec_snapshot = {
                        "entities": {
                            entity_rows_meta[i]: {
                                "selection": edited_entities[i].get("Approved", "Original"),
                                "comment": edited_entities[i].get("Comment", ""),
                            }
                            for i in range(len(edited_entities))
                        },
                        "attributes": {
                            f"{attr_rows_meta[i][0]}:{attr_rows_meta[i][1]}": {
                                "selection": edited_attrs[i].get("Approved", "Original"),
                                "comment": edited_attrs[i].get("Comment", ""),
                            }
                            for i in range(len(edited_attrs))
                        },
                        "endpoints": {
                            f"{endpoint_rows_meta[i][0]}:{endpoint_rows_meta[i][1]}": {
                                "selection": edited_endpoints[i].get("Approved", "Original"),
                                "comment": edited_endpoints[i].get("Comment", ""),
                            }
                            for i in range(len(edited_endpoints))
                        },
                    }
                    st.session_state["regional_decisions"][selected_region] = _dec_snapshot
                    _save_norm_draft(
                        REGIONAL_REVIEWS_ROOT,
                        selected_region,
                        {
                            "region": selected_region,
                            "normalizations": dict(
                                st.session_state["regional_normalizations"]
                            ),
                            "endpointNormalizations": dict(
                                st.session_state["regional_endpoint_normalizations"]
                            ),
                            "decisions": _dec_snapshot,
                        },
                    )
                    st.success("Draft saved — AI suggestions and decisions will reload on next page open.")
                if _do_normalize:
                    norm_provider = OpenAISemanticProvider(
                        api_key=norm_api_key or "",
                        model=norm_model,
                    )
                    norm_progress = st.progress(0, text="Checking provider access")
                    try:
                        norm_provider.validate_connection()
                        regional_inventory = [
                            {
                                "api": branch["api"],
                                "entity": mb["name"],
                                "attributes": [
                                    {"name": f["Field"], "type": f["Type"]} for f in mb["fields"]
                                ],
                            }
                            for branch in entire_region_tree
                            for mb in branch["models"]
                        ]
                        ep_inventory = [
                            {
                                "api": row["API"],
                                "operation": row["Endpoint (original)"],
                                "method": row["Method"],
                                "route": row["Route"],
                            }
                            for row in (edited_endpoints or [])
                        ]
                        done = 0
                        for review_id, ent_row in sel_entities:
                            norm_progress.progress(
                                done / total_sel,
                                text=(
                                    f"Normalizing entity {ent_row['API']} · "
                                    f"{ent_row['Entity (original)']}"
                                ),
                            )
                            run_id, entity_id = review_id.split(":", 1)
                            sel_run = runs[run_id]
                            st.session_state["regional_normalizations"][review_id] = (
                                normalize_regional_entity(
                                    sel_run["discovery_model"],
                                    entity_id,
                                    sel_run.get("phase_2_artifacts", {}).get(
                                        "semantic-metadata.json"
                                    ),
                                    norm_provider,
                                    regional_inventory,
                                )
                            )
                            done += 1
                        for (run_id, op_id), ep_row in sel_endpoints:
                            norm_progress.progress(
                                done / total_sel,
                                text=(
                                    f"Normalizing endpoint {ep_row['API']} · "
                                    f"{ep_row['Endpoint (original)']}"
                                ),
                            )
                            ep_run_data = runs[run_id]
                            st.session_state["regional_endpoint_normalizations"][
                                f"{run_id}:{op_id}"
                            ] = normalize_regional_endpoint(
                                ep_run_data["discovery_model"],
                                op_id,
                                ep_run_data.get("phase_2_artifacts", {}).get(
                                    "semantic-metadata.json"
                                ),
                                norm_provider,
                                ep_inventory,
                            )
                            done += 1
                        norm_progress.progress(1.0, text="Normalization complete — auto-saving draft")
                        _save_norm_draft(
                            REGIONAL_REVIEWS_ROOT,
                            selected_region,
                            {
                                "region": selected_region,
                                "normalizations": dict(
                                    st.session_state["regional_normalizations"]
                                ),
                                "endpointNormalizations": dict(
                                    st.session_state["regional_endpoint_normalizations"]
                                ),
                                "decisions": st.session_state["regional_decisions"].get(
                                    selected_region, {}
                                ),
                            },
                        )
                        st.rerun()
                    except Exception as exc:
                        norm_progress.empty()
                        st.error(
                            "Normalization stopped. Existing proposals were kept. "
                            f"Error: {type(exc).__name__}."
                        )

                # Rebuild decisions dict from flat table edits
                decisions: dict[str, dict] = {}
                for idx, review_id in enumerate(entity_rows_meta):
                    row = edited_entities[idx]
                    decisions[review_id] = {
                        "selection": row["Approved"],
                        "comment": row["Comment"],
                        "attributes": {},
                    }
                for idx, (review_id, field_id) in enumerate(attr_rows_meta):
                    row = edited_attrs[idx]
                    decisions[review_id]["attributes"][field_id] = {
                        "selection": row["Approved"],
                        "comment": row["Comment"],
                    }

                # ── Mapping & gap analysis ──────────────────────────────────────
                with st.expander("Mapping & gap analysis", expanded=False):
                    ent_no_suggest = sum(
                        1 for r in edited_entities if r.get("AI suggestion", "—") == "—"
                    )
                    attr_no_suggest = sum(
                        1 for r in edited_attrs if r.get("AI suggestion", "—") == "—"
                    )
                    ep_no_suggest = sum(
                        1 for r in (edited_endpoints or [])
                        if r.get("AI suggestion", "—") == "—"
                    )
                    ent_no_domain = sum(
                        1 for r in edited_entities
                        if r.get("Domain") == "Awaiting API Analyzer"
                    )
                    ep_no_domain = sum(
                        1 for r in (edited_endpoints or [])
                        if r.get("Domain") == "Awaiting API Analyzer"
                        or r.get("Capability") == "Awaiting API Analyzer"
                    )

                    st.markdown("##### Coverage gaps")
                    gc1, gc2, gc3 = st.columns(3)
                    with gc1:
                        st.metric("Entities without AI suggestion", ent_no_suggest)
                        st.metric("Entities awaiting analyzer", ent_no_domain)
                    with gc2:
                        st.metric("Attributes without AI suggestion", attr_no_suggest)
                    with gc3:
                        st.metric("Endpoints without AI suggestion", ep_no_suggest)
                        st.metric("Endpoints awaiting analyzer", ep_no_domain)

                    # Entity mapping
                    st.markdown("##### Entity normalization mapping")
                    ent_mapping_rows = []
                    for r in edited_entities:
                        ai_sug = r.get("AI suggestion", "—")
                        approved = r.get("Approved", "Original")
                        effective = (
                            ai_sug
                            if approved == "AI suggestion" and ai_sug != "—"
                            else r["Entity (original)"]
                        )
                        if ai_sug == "—":
                            status = "No suggestion"
                        elif effective != r["Entity (original)"]:
                            status = "Renamed"
                        else:
                            status = "Unchanged"
                        ent_mapping_rows.append(
                            {
                                "API": r["API"],
                                "Original name": r["Entity (original)"],
                                "Domain": r["Domain"],
                                "AI suggestion": ai_sug,
                                "Effective name": effective,
                                "Status": status,
                            }
                        )
                    st.dataframe(ent_mapping_rows, hide_index=True, use_container_width=True)

                    # Attribute mapping
                    st.markdown("##### Attribute normalization mapping")
                    attr_mapping_rows = []
                    for r in edited_attrs:
                        ai_sug = r.get("AI suggestion", "—")
                        approved = r.get("Approved", "Original")
                        effective = (
                            ai_sug
                            if approved == "AI suggestion" and ai_sug != "—"
                            else r["Attribute (original)"]
                        )
                        if ai_sug == "—":
                            status = "No suggestion"
                        elif effective != r["Attribute (original)"]:
                            status = "Renamed"
                        else:
                            status = "Unchanged"
                        attr_mapping_rows.append(
                            {
                                "API": r["API"],
                                "Entity": r["Entity"],
                                "Original name": r["Attribute (original)"],
                                "Type": r["Type"],
                                "AI suggestion": ai_sug,
                                "Effective name": effective,
                                "Status": status,
                            }
                        )
                    st.dataframe(attr_mapping_rows, hide_index=True, use_container_width=True)

                    # Endpoint mapping
                    if edited_endpoints:
                        st.markdown("##### Endpoint normalization mapping")
                        ep_mapping_rows = []
                        for r in edited_endpoints:
                            ai_sug = r.get("AI suggestion", "—")
                            approved = r.get("Approved", "Original")
                            effective = (
                                ai_sug
                                if approved == "AI suggestion" and ai_sug != "—"
                                else r["Endpoint (original)"]
                            )
                            if ai_sug == "—":
                                status = "No suggestion"
                            elif effective != r["Endpoint (original)"]:
                                status = "Renamed"
                            else:
                                status = "Unchanged"
                            ep_mapping_rows.append(
                                {
                                    "API": r["API"],
                                    "Method": r["Method"],
                                    "Route": r["Route"],
                                    "Domain": r["Domain"],
                                    "Capability": r["Capability"],
                                    "Original name": r["Endpoint (original)"],
                                    "AI suggestion": ai_sug,
                                    "Effective name": effective,
                                    "Status": status,
                                }
                            )
                        st.dataframe(ep_mapping_rows, hide_index=True, use_container_width=True)

                    # Conflict detection
                    st.markdown("##### Naming conflicts")
                    # Intra-API: same API + same effective entity name but different originals
                    api_eff: dict[tuple[str, str], list[str]] = {}
                    for r in ent_mapping_rows:
                        key = (r["API"], r["Effective name"])
                        api_eff.setdefault(key, []).append(r["Original name"])
                    intra = [
                        {
                            "API": api,
                            "Effective name": name,
                            "Conflicting originals": " / ".join(sorted(origs)),
                            "Type": "Intra-API conflict",
                        }
                        for (api, name), origs in api_eff.items()
                        if len(origs) > 1
                    ]
                    # Cross-API: same effective name appears in 2+ different APIs (merge)
                    eff_apis: dict[str, list[str]] = {}
                    for r in ent_mapping_rows:
                        eff_apis.setdefault(r["Effective name"], []).append(r["API"])
                    cross = [
                        {
                            "API": ", ".join(sorted(set(apis))),
                            "Effective name": name,
                            "Conflicting originals": "",
                            "Type": "Cross-API merge",
                        }
                        for name, apis in eff_apis.items()
                        if len(set(apis)) > 1
                    ]
                    # Attribute type mismatch: same entity effective + same attr effective, diff types
                    attr_key_types: dict[tuple[str, str], set[str]] = {}
                    for ent_r in ent_mapping_rows:
                        for attr_r in attr_mapping_rows:
                            if attr_r["API"] == ent_r["API"] and attr_r["Entity"] == ent_r["Original name"]:
                                combo = (ent_r["Effective name"], attr_r["Effective name"])
                                attr_key_types.setdefault(combo, set()).add(attr_r["Type"])
                    type_mismatches = [
                        {
                            "API": "multiple",
                            "Effective name": f"{ent}/{attr}",
                            "Conflicting originals": " / ".join(sorted(types)),
                            "Type": "Attribute type mismatch (will not merge)",
                        }
                        for (ent, attr), types in attr_key_types.items()
                        if len(types) > 1
                    ]
                    all_conflicts = intra + cross + type_mismatches
                    if all_conflicts:
                        st.warning(f"{len(all_conflicts)} conflict(s) / merge(s) detected.")
                        st.dataframe(all_conflicts, hide_index=True, use_container_width=True)
                    else:
                        st.success("No naming conflicts detected.")

                st.divider()
                st.markdown("#### Approve and generate regional artifacts")
                st.caption(
                    "Entities merge by approved name. Attributes merge within an approved "
                    "entity only when approved name and source type match. Approval creates a "
                    "regional review artifact and never modifies source Discovery artifacts."
                )
                approval_confirmed = st.checkbox(
                    "I reviewed the selections and approve this regional deduplication view.",
                    key=f"regional_approval_confirmed_{selected_region}",
                )
                if st.button(
                    "Approve regional view",
                    icon=":material/verified:",
                    type="primary",
                    disabled=not approval_confirmed,
                    key=f"approve_regional_view_{selected_region}",
                ):
                    approved_review = build_regional_review(
                        selected_region,
                        entire_region_tree,
                        proposals,
                        decisions,
                    )
                    st.session_state["approved_regional_reviews"][selected_region] = {
                        "review": approved_review,
                        "excel": render_regional_review_excel(approved_review),
                        "mermaid": render_regional_review_mermaid(approved_review),
                    }
                    _save_regional_review(REGIONAL_REVIEWS_ROOT, selected_region, approved_review)
                    st.success("Regional view approved. Both artifacts are ready.")

                approved = st.session_state["approved_regional_reviews"].get(selected_region)
                if approved:
                    review = approved["review"]
                    with st.container(horizontal=True):
                        st.metric(
                            "Approved regional entities",
                            review["summary"]["regionalEntities"],
                        )
                        st.metric(
                            "Duplicate entities merged",
                            review["summary"]["mergedDuplicateEntities"],
                        )
                        st.metric(
                            "Approved regional attributes",
                            review["summary"]["regionalAttributes"],
                        )
                    duplicate_rows = [
                        {
                            "Action": item["action"],
                            "API": item["api"],
                            "Source entity": item["sourceEntity"],
                            "Source attribute": item["sourceAttribute"],
                            "Regional entity": item["regionalEntity"],
                            "Regional attribute": item["regionalAttribute"],
                            "Endpoints involved": "; ".join(item["endpoints"]),
                        }
                        for item in review["removedDuplicates"]
                    ]
                    st.markdown("**Removed duplicate truth map**")
                    if duplicate_rows:
                        st.dataframe(duplicate_rows, hide_index=True, width="stretch")
                    else:
                        st.info("No duplicates matched the approved names and field types.")
                    with st.container(horizontal=True):
                        st.download_button(
                            "Download approved regional Excel",
                            data=approved["excel"],
                            file_name=f"{selected_region.lower()}-regional-model.xlsx",
                            mime=(
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            ),
                            icon=":material/download:",
                            key=f"download_regional_excel_{selected_region}",
                        )
                        st.download_button(
                            "Download Mermaid truth map",
                            data=approved["mermaid"],
                            file_name=f"{selected_region.lower()}-regional-truth-map.mmd",
                            mime="text/plain",
                            icon=":material/download:",
                            key=f"download_regional_mermaid_{selected_region}",
                        )

with acord_ingestion_tab:
    _cur_acord_id = st.session_state.get("active_acord_id")
    _has_index = bool(_cur_acord_id and st.session_state["acord_runs"].get(_cur_acord_id))
    st.html(
        _hero_banner(
            icon="📦",
            eyebrow="ACORD · RAG Pipeline",
            title="ACORD Ingestion",
            body=(
                "Upload an authorized ACORD OpenAPI 3 document. "
                "The pipeline deterministically extracts endpoints, recursively nested entities, "
                "attributes, constraints, and JSON-pointer lineage "
                "into a persistent local retrieval index for downstream alignment."
            ),
            accent="#6366f1",
        )
    )
    st.html(
        _pipeline_steps(
            [
                ("Parse OpenAPI", "done" if _has_index else "active", "1"),
                ("Extract entities", "done" if _has_index else "pending", "2"),
                ("Build RAG chunks", "done" if _has_index else "pending", "3"),
                ("Index ready", "done" if _has_index else "pending", "✓"),
            ]
        )
    )
    st.info(
        "Ingestion is a standalone pipeline — it does not perform alignment or "
        "canonical generation and is not a numbered step in the regional workflow.",
        icon=":material/info:",
    )
    acord_runs = st.session_state["acord_runs"]
    acord_notice = st.session_state.pop("acord_delete_notice", None)
    if acord_notice:
        st.success(acord_notice, icon=":material/check:")
    if acord_runs:
        with st.expander(
            f":material/history: Open a previous ACORD ingestion ({len(acord_runs)} saved)",
            expanded=False,
        ):
            saved_acord_id = st.selectbox(
                "Saved ACORD reference",
                list(acord_runs),
                format_func=lambda item: (
                    f"{acord_runs[item]['profile']['referenceLabel']} · "
                    f"{acord_runs[item]['profile']['referenceVersion']} · "
                    f"{acord_runs[item]['profile']['sourceFile']} [{item[:6]}]"
                ),
                key="saved_acord_reference",
            )
            open_col, delete_col = st.columns(2, gap="small")
            with open_col:
                if st.button(
                    "Open saved ACORD reference",
                    icon=":material/history:",
                    key="open_saved_acord_reference",
                ):
                    st.session_state["active_acord_id"] = saved_acord_id
                    st.session_state["acord_results"] = []
                    st.rerun()
            with delete_col:
                if st.button(
                    "Delete ACORD ingestion",
                    icon=":material/delete:",
                    key="delete_saved_acord_reference",
                    type="secondary",
                ):
                    st.session_state["pending_acord_deletion"] = saved_acord_id
            if st.session_state.get("pending_acord_deletion") == saved_acord_id:
                confirm_delete_acord(saved_acord_id)

    with st.container(border=True):
        st.subheader(":material/library_books: New ACORD reference", anchor=False)
        st.caption("Provide reference metadata and upload the approved ACORD specification.")
        st.divider()
        reference_column, version_column = st.columns(2, gap="large")
        with reference_column:
            acord_label = st.text_input(
                "ACORD reference label",
                placeholder="ACORD policy API",
                help="A stable name for this independently ingested standards reference.",
                key="acord_reference_label",
            )
        with version_column:
            acord_version = st.text_input(
                "Approved reference version",
                placeholder="2026.1",
                help="The approved ACORD release or package version used for this ingestion.",
                key="acord_reference_version",
            )
        acord_files: list[UploadedFile] = st.file_uploader(
            "ACORD OpenAPI documents",
            type=["json", "yaml", "yml", "zip"],
            accept_multiple_files=True,
            help=("One or more OpenAPI 3.x JSON or YAML files, or a ZIP archive containing them."),
            key="acord_document",
        )
        selected_acord_files: list[UploadedFile] = (
            acord_files or st.session_state.get("acord_document") or []
        )
        for _f in selected_acord_files:
            if not hasattr(_f, "name"):
                continue
            _suffix = _f.name.lower().rsplit(".", 1)[-1] if "." in _f.name else ""
            if _suffix == "zip":
                st.success(
                    f"ZIP archive: **{_f.name}** · {len(_f.getvalue()):,} bytes"
                    " — YAML/JSON files will be extracted and ingested",
                    icon=":material/folder_zip:",
                )
            else:
                st.success(
                    f"Specification selected: **{_f.name}** · {len(_f.getvalue()):,} bytes",
                    icon=":material/attach_file:",
                )
        usage_authorized = st.checkbox(
            "I confirm that this ACORD document is approved for local ingestion and indexing.",
            key="acord_usage_authorized",
        )
        ingest_clicked = st.button(
            "Build ACORD RAG index",
            type="primary",
            icon=":material/library_add:",
            key="build_acord_rag_index",
        )

    if ingest_clicked:
        missing_inputs = []
        if not acord_label.strip():
            missing_inputs.append("reference label")
        if not acord_version.strip():
            missing_inputs.append("approved version")
        if not selected_acord_files:
            missing_inputs.append("ACORD YAML/JSON file")
        if missing_inputs:
            st.error("Required input missing: " + ", ".join(missing_inputs) + ".")
        elif not usage_authorized:
            st.error("Confirm that the ACORD document is approved for local ingestion.")
        else:
            # Resolve all YAML/JSON sources — expand any ZIP archives first.
            all_sources: list[tuple[str, bytes]] = []
            expand_errors: list[str] = []
            for _uploaded in selected_acord_files:
                _sfx = _uploaded.name.lower().rsplit(".", 1)[-1] if "." in _uploaded.name else ""
                if _sfx == "zip":
                    try:
                        _extracted = _extract_yaml_json_from_zip(
                            _uploaded.getvalue(), _uploaded.name
                        )
                        if _extracted:
                            all_sources.extend(_extracted)
                        else:
                            expand_errors.append(
                                f"No YAML/JSON files found inside '{_uploaded.name}'."
                            )
                    except ValueError as _exc:
                        expand_errors.append(str(_exc))
                else:
                    all_sources.append((_uploaded.name, _uploaded.getvalue()))
            for _err in expand_errors:
                st.error(_err)
            if not all_sources:
                if not expand_errors:
                    st.error("No YAML or JSON files found to ingest.")
            else:
                for _source_name, _source_content in all_sources:
                    try:
                        with st.status(
                            f"Building ACORD RAG pipeline for **{_source_name}**…",
                            expanded=True,
                        ) as _status:
                            st.write("Parsing OpenAPI endpoints and recursive model structure")
                            st.write(
                                "Preserving descriptions, comments, constraints, "
                                "and JSON-pointer lineage"
                            )
                            st.write("Creating endpoint/entity chunks and the local semantic index")
                            ingest_acord_reference(
                                source_content=_source_content,
                                source_name=_source_name,
                                reference_label=acord_label,
                                reference_version=acord_version,
                                progress=st.write,
                            )
                            _status.update(
                                label=f"ACORD ingestion complete: {_source_name}",
                                state="complete",
                                expanded=False,
                            )
                    except (OSError, RuntimeError, ValueError) as exc:
                        st.error(f"{_source_name}: {exc}")

    active_acord_id = st.session_state.get("active_acord_id")
    active_acord = acord_runs.get(active_acord_id)
    if active_acord:
        model = active_acord["model"]
        summary = model["summary"]
        stats = active_acord["manifest"]["stats"]
        profile = active_acord["profile"]
        tiles = "".join(
            [
                _stat_tile(summary["endpointCount"], "Endpoints", "#3b82f6"),
                _stat_tile(summary["entityCount"], "Entities", "#8b5cf6"),
                _stat_tile(summary["attributeCount"], "Attributes", "#06b6d4"),
                _stat_tile(stats["chunksIndexed"], "RAG Chunks", "#f59e0b"),
            ]
        )
        st.html(
            _summary_card_html(
                title=profile["referenceLabel"],
                subtitle=(
                    f"Version {profile['referenceVersion']}&ensp;&middot;&ensp;"
                    f"{profile['sourceFile']}&ensp;&middot;&ensp;"
                    f"Snapshot <code style='background:#f1f5f9;padding:2px 6px;"
                    f"border-radius:4px;color:#475569;font-size:.78rem'>"
                    f"{active_acord['manifest']['snapshotId'][:12]}</code>"
                ),
                pill_text="ACORD RAG READY",
                pill_kind="success",
                stat_tiles_html=tiles,
                footer=(
                    f"&#128192; Local Chroma index &ensp;&middot;&ensp;"
                    f" Embedding: {stats['embedding']}"
                ),
            )
        )

        st.html(
            _section_heading(
                "ACORD Artifact Tree",
                "ACORD OpenAPI → Ingestion → API Catalog, Data Model, Relationship Graph, "
                "Validation &amp; Enums, and Lineage.",
            )
        )
        acord_artifacts: dict[str, bytes] = active_acord["artifacts"]
        acord_content, acord_gallery = st.columns([2.2, 1], gap="large")
        with acord_content:
            acord_preview = st.selectbox(
                "Preview ACORD artifact",
                list(acord_artifacts),
                key="acord_artifact_preview",
            )
            st.json(json.loads(acord_artifacts[acord_preview]), expanded=2)
        with acord_gallery:
            render_artifact_download_gallery(
                title="ACORD download gallery",
                artifacts=acord_artifacts,
                filenames=ACORD_ARTIFACTS,
                key_prefix=f"download_acord_{active_acord_id}",
                bundle=build_acord_bundle(acord_artifacts),
                bundle_filename="acord-ingestion-artifacts.zip",
                extra_downloads=[
                    {
                        "label": "Download RAG manifest",
                        "data": (
                            json.dumps(active_acord["manifest"], indent=2, sort_keys=True) + "\n"
                        ).encode("utf-8"),
                        "filename": "acord-rag-manifest.json",
                        "mime": "application/json",
                        "key": "rag_manifest",
                    }
                ],
            )

        st.html(
            _section_heading(
                "Inspect ACORD Retrieval",
                "Search the independent index to inspect the exact endpoint/entity chunks "
                "that a later alignment agent would receive.",
            )
        )
        with st.form("acord_retrieval", border=False):
            acord_query = st.text_input(
                "Search endpoints, entities, attributes, descriptions, or constraints",
                placeholder="policy postal code constraint",
                key="acord_query",
            )
            acord_search = st.form_submit_button("Search ACORD index", icon=":material/search:")
        if acord_search:
            try:
                acord_index = AcordDocumentIndex(Path(active_acord["storagePath"]))
                try:
                    st.session_state["acord_results"] = acord_index.query(acord_query)
                finally:
                    acord_index.close()
            except (OSError, RuntimeError, ValueError) as exc:
                st.error(str(exc))
        for rank, result in enumerate(st.session_state["acord_results"], start=1):
            with st.expander(
                f"{rank}. {result['kind']} · {result['aliases'][0]} · {result['retrievalReason']}"
            ):
                st.caption(f"Source: {profile['sourceFile']}{result['sourcePointer']}")
                st.code(result["text"], language="text")


def _alignment_decision_by_id(
    decisions: dict[str, object], regional_id: str
) -> dict[str, object] | None:
    for section, child_key in (("entities", "attributes"), ("domains", "capabilities")):
        parents = decisions.get(section, {})
        if not isinstance(parents, dict):
            continue
        if regional_id in parents and isinstance(parents[regional_id], dict):
            return parents[regional_id]
        for parent in parents.values():
            if not isinstance(parent, dict):
                continue
            children = parent.get(child_key, {})
            if isinstance(children, dict) and isinstance(children.get(regional_id), dict):
                return children[regional_id]
    return None


def _canonical_baseline_label(version: dict[str, object]) -> str:
    artifact = version["artifact"]
    if not isinstance(artifact, dict):
        return f"v{version['version']}"
    regions = artifact.get("regions") or [artifact.get("region", "Unknown")]
    return f"v{version['version']} · {', '.join(str(item) for item in regions)}"


def _decision_description(match: dict[str, object], decision: dict[str, object]) -> str:
    candidate_by_selection = {
        USE_BASELINE: match.get("baselineCandidate"),
        USE_ACORD: match.get("acordCandidate"),
        USE_GENERATED: match.get("generatedProposal"),
    }
    candidate = candidate_by_selection.get(decision.get("selection")) or {}
    return str(
        decision.get("reviewDescription")
        or (candidate.get("description") if isinstance(candidate, dict) else "")
        or match.get("regionalDescription")
        or ""
    )


def _render_match_decision_controls(
    *,
    match: dict[str, object],
    decision: dict[str, object],
    label: str,
    key_prefix: str,
) -> None:
    decision.setdefault("reviewStatus", match["status"])
    decision.setdefault("reviewDescription", _decision_description(match, decision))
    status_key = f"{key_prefix}_status"
    description_key = f"{key_prefix}_description"
    selection_key = f"{key_prefix}_selection"
    reason_key = f"{key_prefix}_reason"
    st.session_state.setdefault(status_key, decision["reviewStatus"])
    st.session_state.setdefault(description_key, decision["reviewDescription"])
    st.session_state.setdefault(selection_key, decision["selection"])
    st.session_state.setdefault(reason_key, decision.get("reason", ""))

    ctrl_col, res_col, reason_col = st.columns(3, gap="medium")
    with ctrl_col:
        review_status = st.radio(
            "Review status",
            MATCH_STATUSES,
            key=status_key,
            persist_state="session",
        )
    with res_col:
        selection = st.selectbox(
            "Canonical resolution",
            ALIGNMENT_SELECTIONS,
            key=selection_key,
            persist_state="session",
        )
        review_description = st.text_area(
            "Description",
            key=description_key,
            placeholder="Describe the match and the meaning retained in the canonical model.",
            height=80,
            persist_state="session",
        )
    with reason_col:
        reason = st.text_area(
            "Reviewer reason",
            key=reason_key,
            placeholder="Explain partial, unmatched, generated, or manual decisions.",
            height=130,
            persist_state="session",
        )

    decision.update(
        {
            "reviewStatus": review_status,
            "reviewDescription": review_description,
            "selection": selection,
            "reason": reason,
        }
    )
    if selection == MANUAL:
        manual_name_key = f"{key_prefix}_manual_name"
        manual_type_key = f"{key_prefix}_manual_type"
        manual_constraints_key = f"{key_prefix}_manual_constraints"
        st.session_state.setdefault(manual_name_key, decision.get("manualName", ""))
        st.session_state.setdefault(manual_type_key, decision.get("manualType", ""))
        st.session_state.setdefault(manual_constraints_key, decision.get("manualConstraints", "{}"))
        manual_columns = st.columns(2, gap="large")
        with manual_columns[0]:
            manual_name = st.text_input(
                f"{label} manual canonical name",
                key=manual_name_key,
                persist_state="session",
            )
            manual_type = st.text_input(
                f"{label} manual type",
                key=manual_type_key,
                persist_state="session",
            )
        with manual_columns[1]:
            manual_constraints = st.text_area(
                f"{label} manual constraints (JSON object)",
                key=manual_constraints_key,
                persist_state="session",
            )
        decision.update(
            {
                "manualName": manual_name,
                "manualDescription": review_description,
                "manualType": manual_type,
                "manualConstraints": manual_constraints,
            }
        )

    approval_key = f"{key_prefix}_approved"
    review_signature = sha256(
        json.dumps(
            {
                "reviewStatus": decision["reviewStatus"],
                "reviewDescription": decision["reviewDescription"],
                "selection": decision["selection"],
                "reason": decision["reason"],
                "manualName": decision.get("manualName", ""),
                "manualType": decision.get("manualType", ""),
                "manualConstraints": decision.get("manualConstraints", "{}"),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    previous_signature = decision.get("reviewSignature")
    if previous_signature is not None and previous_signature != review_signature:
        st.session_state[approval_key] = False
    else:
        st.session_state.setdefault(approval_key, bool(decision.get("approved", False)))
    with st.container(border=True):
        approved = st.checkbox(
            f"Approve this {label.lower()} match",
            key=approval_key,
            help=(
                "Changing the status, description, resolution, reason, or manual details "
                "resets approval."
            ),
            persist_state="session",
        )
    decision.update(
        {
            "approved": approved,
            "reviewSignature": review_signature,
        }
    )
    if approved and _auto_fill_canonical_name(match, decision, key_prefix):
        # Clear the signature so the signature-change guard doesn't reset this approval.
        decision["reviewSignature"] = None


def _render_match_evidence(match: dict[str, object], *, label: str) -> None:
    baseline = match.get("baselineCandidate") or {}
    acord = match.get("acordCandidate") or {}

    regional_name = _html.escape(str(match.get("regionalName", "")))
    regional_type = _html.escape(str(match.get("regionalType") or ""))
    regional_desc = _html.escape(str(match.get("regionalDescription") or ""))

    baseline_name = (
        _html.escape(str(baseline.get("name", ""))) if isinstance(baseline, dict) else ""
    )
    baseline_pct = float(match.get("baselineMatchPercent") or 0)
    baseline_desc = _html.escape(
        str(baseline.get("description", "") if isinstance(baseline, dict) else "")
    )

    acord_name = _html.escape(str(acord.get("name", ""))) if isinstance(acord, dict) else ""
    acord_type = _html.escape(str(acord.get("type", "") if isinstance(acord, dict) else ""))
    acord_pct = float(match.get("matchPercent") or 0)
    acord_desc = _html.escape(str(acord.get("description", "") if isinstance(acord, dict) else ""))

    status = str(match.get("status", ""))
    status_color, status_bg = {
        FULL_MATCH: ("#166534", "#dcfce7"),
        PARTIAL_MATCH: ("#92400e", "#fef3c7"),
        NOT_MATCHED: ("#991b1b", "#fee2e2"),
    }.get(status, ("#374151", "#f3f4f6"))

    def _pct_bar(pct: float) -> str:
        bar_color = "#22c55e" if pct >= 85 else "#f59e0b" if pct >= 55 else "#ef4444"
        w = min(100, max(0, pct))
        return (
            f'<div style="display:flex;align-items:center;gap:7px;margin:5px 0 3px">'
            f'<div style="flex:1;background:#e5e7eb;border-radius:4px;height:5px;overflow:hidden">'
            f'<div style="width:{w}%;background:{bar_color};height:100%;border-radius:4px"></div>'
            f"</div>"
            f'<span style="font-size:11px;font-weight:700;color:{bar_color};white-space:nowrap">'
            f"{pct:.1f}%</span></div>"
        )

    def _candidate_block(name: str, pct: float, desc: str, type_str: str = "") -> str:
        if not name:
            return (
                '<div style="font-size:12px;color:#9ca3af;font-style:italic;padding:6px 0">'
                "No candidate found</div>"
            )
        type_pill = (
            f'<span style="font-size:10px;background:#dbeafe;color:#1d4ed8;'
            f'padding:1px 6px;border-radius:3px;margin-left:5px">{type_str}</span>'
            if type_str
            else ""
        )
        short_desc = (desc[:130] + "…") if len(desc) > 130 else desc
        desc_html = (
            f'<div style="font-size:11px;color:#6b7280;line-height:1.45;margin-top:3px">'
            f"{short_desc}</div>"
            if short_desc
            else ""
        )
        return (
            f'<div style="font-size:14px;font-weight:700;color:#1e3a5f">'
            f"{name}{type_pill}</div>"
            f"{_pct_bar(pct)}"
            f"{desc_html}"
        )

    type_pill_regional = (
        f'<span style="font-size:10px;background:#f3f4f6;color:#374151;'
        f'padding:1px 7px;border-radius:4px;margin-left:7px;font-weight:500">'
        f"{regional_type}</span>"
        if regional_type
        else ""
    )
    desc_regional = (
        f'<div style="font-size:12px;color:#6b7280;margin-top:4px;line-height:1.45">'
        f"{(regional_desc[:160] + '…') if len(regional_desc) > 160 else regional_desc}</div>"
        if regional_desc
        else ""
    )

    no_candidates_msg = (
        ""
        if (baseline_name or acord_name)
        else '<div style="font-size:12px;color:#9ca3af;font-style:italic;padding:4px 0">No canonical baseline or ACORD candidate found.</div>'
    )

    card = f"""
    <div style="border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;margin-bottom:10px;font-family:system-ui,sans-serif">
      <div style="background:#f8fafc;padding:11px 15px;border-bottom:1px solid #e5e7eb">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af;margin-bottom:3px">Regional {_html.escape(label)}</div>
        <div style="font-size:16px;font-weight:800;color:#111827">{regional_name}{type_pill_regional}</div>
        {desc_regional}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid #e5e7eb">
        <div style="padding:11px 15px;border-right:1px solid #e5e7eb">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af;margin-bottom:6px">Canonical Baseline</div>
          {_candidate_block(baseline_name, baseline_pct, baseline_desc)}
        </div>
        <div style="padding:11px 15px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af;margin-bottom:6px">ACORD Candidate</div>
          {_candidate_block(acord_name, acord_pct, acord_desc, acord_type)}
        </div>
      </div>
      {no_candidates_msg}
      <div style="padding:8px 15px;display:flex;align-items:center;gap:8px;background:#fafafa">
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af">Proposed</span>
        <span style="font-size:11px;font-weight:700;padding:2px 10px;border-radius:20px;color:{status_color};background:{status_bg}">{_html.escape(status)}</span>
      </div>
    </div>
    """
    st.html(card)


def _alignment_tree_review_nodes(
    *,
    matches: list[dict[str, object]],
    decisions: dict[str, dict[str, object]],
    child_key: str,
    statuses: set[str],
    context: str,
) -> list[tuple[dict[str, object], dict[str, object], str]]:
    nodes: list[tuple[dict[str, object], dict[str, object], str]] = []
    for parent in matches:
        parent_id = str(parent["regionalId"])
        decision = decisions[parent_id]
        if parent["status"] in statuses:
            nodes.append((parent, decision, f"{context}_{parent_id}"))
        for child in parent.get(child_key, []):
            if child["status"] not in statuses:
                continue
            child_id = str(child["regionalId"])
            nodes.append(
                (
                    child,
                    decision[child_key][child_id],
                    f"{context}_{parent_id}_{child_id}",
                )
            )
    return nodes


def _decision_needs_reviewer_reason(match: dict[str, object], decision: dict[str, object]) -> bool:
    review_status = decision.get("reviewStatus", match["status"])
    return (
        review_status != FULL_MATCH
        or review_status != match["status"]
        or decision.get("selection") in {MANUAL, USE_GENERATED}
    )


def _auto_fill_canonical_name(
    match: dict[str, object], decision: dict[str, object], key_prefix: str
) -> bool:
    """When approving a node with no available standard candidate, default the canonical name to the
    regional name so the approval is self-contained without requiring manual text entry."""
    regional_name = str(match.get("regionalName", "")).strip()
    if not regional_name:
        return False
    if decision.get("selection") == USE_ACORD and not match.get("acordCandidate"):
        decision["selection"] = MANUAL
        # Pop instead of assign: safe whether the widget is already rendered or not.
        # On the next rerun the setdefault in _render_match_decision_controls re-syncs from decision.
        st.session_state.pop(f"{key_prefix}_selection", None)
        if not str(decision.get("manualName", "")).strip():
            decision["manualName"] = regional_name
            st.session_state[f"{key_prefix}_manual_name"] = regional_name
        return True
    if decision.get("selection") == MANUAL and not str(decision.get("manualName", "")).strip():
        decision["manualName"] = regional_name
        # manual_name widget is rendered when selection == MANUAL, so pop rather than assign.
        st.session_state.pop(f"{key_prefix}_manual_name", None)
        return True
    return False


def _approve_filtered_alignment_tree(
    matches: list[dict[str, object]],
    decisions: dict[str, dict[str, object]],
    child_key: str,
    statuses: set[str],
    context: str,
    reason_key: str,
    result_key: str,
) -> None:
    reason = str(st.session_state.get(reason_key, "")).strip()
    nodes = _alignment_tree_review_nodes(
        matches=matches,
        decisions=decisions,
        child_key=child_key,
        statuses=statuses,
        context=context,
    )
    for match, decision, key_prefix in nodes:
        # Auto-fill before reason check so a selection change to MANUAL also gets a reason applied.
        _auto_fill_canonical_name(match, decision, key_prefix)
        if (
            _decision_needs_reviewer_reason(match, decision)
            and not str(decision.get("reason", "")).strip()
        ):
            decision["reason"] = reason
            st.session_state[f"{key_prefix}_reason"] = reason
        decision["approved"] = True
        # Preserve this batch action on the next render. Later field edits still invalidate it.
        decision["reviewSignature"] = None
        st.session_state[f"{key_prefix}_approved"] = True
    st.session_state[result_key] = len(nodes)


def _render_alignment_gap_llm_button(
    *,
    match: dict[str, object],
    decision: dict[str, object],
    kind_and_path: str,
    gap_context: str,
    key_prefix: str,
) -> None:
    """Inline LLM proposal button for a single NOT_MATCHED item."""
    item_id = str(match["regionalId"])
    st.divider()
    st.caption(":material/auto_awesome: Generate a standard name and description with LLM")
    gap_model = resolve_openai_model()
    st.caption(f"Model from .env: {gap_model}")
    instructions = st.text_area(
        "Description or constraint instructions (optional)",
        placeholder="Describe required terminology or evidence-backed constraints.",
        key=f"{key_prefix}_gap_instructions",
    )
    consent_col, btn_col = st.columns([3, 2], vertical_alignment="bottom")
    with consent_col:
        gap_consent = st.checkbox(
            "Allow this gap and instructions to be sent to OpenAI.",
            key=f"{key_prefix}_gap_consent",
        )
    with btn_col:
        if st.button(
            "Generate standard with LLM",
            icon=":material/auto_awesome:",
            disabled=not gap_consent or not openai_api_key(),
            key=f"{key_prefix}_gap_generate",
        ):
            try:
                provider = OpenAICanonicalGapProvider(
                    api_key=openai_api_key() or "",
                    model=gap_model,
                )
                generated = provider.generate(
                    {
                        "promptVersion": "canonical-gap-v1",
                        "kindAndPath": kind_and_path,
                        "regionalItem": {
                            key: value
                            for key, value in match.items()
                            if key
                            in {
                                "regionalId",
                                "regionalName",
                                "regionalDescription",
                                "regionalType",
                                "required",
                            }
                        },
                        "baselineCandidate": match.get("baselineCandidate"),
                        "acordCandidate": match.get("acordCandidate"),
                        "reviewerInstructions": instructions.strip(),
                    }
                )
                st.session_state["canonical_gap_proposals"].setdefault(gap_context, {})[item_id] = (
                    generated
                )
                decision["selection"] = USE_GENERATED
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _render_alignment_tree(
    *,
    title: str,
    matches: list[dict[str, object]],
    decisions: dict[str, dict[str, object]],
    parent_label: str,
    child_label: str,
    child_key: str,
    context: str,
    gap_context: str,
) -> None:
    selected_statuses = st.pills(
        f"Filter {parent_label.lower()} tree nodes by proposed status",
        MATCH_STATUSES,
        default=list(MATCH_STATUSES),
        selection_mode="multi",
        key=f"{context}_status_filter",
    )
    visible_statuses = set(selected_statuses or MATCH_STATUSES)
    visible_matches = [
        item
        for item in matches
        if item["status"] in visible_statuses
        or any(child["status"] in visible_statuses for child in item.get(child_key, []))
    ]
    st.markdown(f"#### {title}")
    st.caption(
        f"Expand a {parent_label.lower()} node to see its filtered {child_label.lower()} children. "
        "Open Review only for the node you want to inspect, so the full tree stays compact."
    )
    if not visible_matches:
        st.info("No results match the selected status filter.")
        return

    for index, parent in enumerate(visible_matches):
        parent_id = str(parent["regionalId"])
        decision = decisions[parent_id]
        children = parent.get(child_key, [])
        visible_children = [child for child in children if child["status"] in visible_statuses]
        parent_is_visible = parent["status"] in visible_statuses
        approval_label = "Approved" if decision.get("approved") is True else "Pending approval"
        with st.expander(
            (
                f"{parent['regionalName']} · proposed {parent['status']} · "
                f"{len(visible_children)} shown · {approval_label}"
            ),
            expanded=index == 0,
            icon=":material/account_tree:" if parent_label == "Entity" else ":material/category:",
        ):
            if parent_is_visible:
                parent_summary, parent_action = st.columns([5, 1.2], vertical_alignment="center")
                with parent_summary:
                    st.markdown(
                        f"**{parent_label} node** · reviewed "
                        f"`{decision.get('reviewStatus', parent['status'])}` · {approval_label}"
                    )
                with parent_action:
                    with st.popover(
                        f"Review {parent_label.lower()}",
                        icon=":material/rate_review:",
                        width="stretch",
                        key=f"{context}_{parent_id}_review",
                    ):
                        _render_match_evidence(parent, label=parent_label)
                        _render_match_decision_controls(
                            match=parent,
                            decision=decision,
                            label=parent_label,
                            key_prefix=f"{context}_{parent_id}",
                        )
                        if parent["status"] == NOT_MATCHED:
                            _render_alignment_gap_llm_button(
                                match=parent,
                                decision=decision,
                                kind_and_path=f"{parent_label} · {parent['regionalName']}",
                                gap_context=gap_context,
                                key_prefix=f"{context}_{parent_id}",
                            )
            else:
                st.caption(
                    "Parent shown for context; its proposed status is outside the active filter."
                )

            st.markdown(f"##### {child_label} children")
            if not visible_children:
                st.info(f"No {child_label.lower()} children match the active filter.")
                continue
            for child in visible_children:
                child_id = str(child["regionalId"])
                child_decision = decision[child_key][child_id]
                child_approval = (
                    "Approved" if child_decision.get("approved") is True else "Pending approval"
                )
                with st.container(border=True, gap="small"):
                    child_summary, child_action = st.columns([5, 1.2], vertical_alignment="center")
                    with child_summary:
                        child_type = str(child.get("regionalType") or "")
                        type_label = f" · `{child_type}`" if child_type else ""
                        st.markdown(
                            ":material/subdirectory_arrow_right: "
                            f"**{child['regionalName']}**{type_label} · proposed "
                            f"`{child['status']}` · {child_approval}"
                        )
                    with child_action:
                        with st.popover(
                            "Review",
                            icon=":material/edit_note:",
                            width="stretch",
                            key=f"{context}_{parent_id}_{child_id}_review",
                        ):
                            _render_match_evidence(child, label=child_label)
                            _render_match_decision_controls(
                                match=child,
                                decision=child_decision,
                                label=child_label,
                                key_prefix=f"{context}_{parent_id}_{child_id}",
                            )
                            if child["status"] == NOT_MATCHED:
                                _render_alignment_gap_llm_button(
                                    match=child,
                                    decision=child_decision,
                                    kind_and_path=(
                                        f"{child_label} · "
                                        f"{parent['regionalName']}.{child['regionalName']}"
                                    ),
                                    gap_context=gap_context,
                                    key_prefix=f"{context}_{parent_id}_{child_id}",
                                )


def _render_alignment_bulk_approval(
    *,
    matches: list[dict[str, object]],
    decisions: dict[str, dict[str, object]],
    parent_label: str,
    child_key: str,
    child_label: str,
    context: str,
) -> None:
    selected_statuses = set(st.session_state.get(f"{context}_status_filter") or MATCH_STATUSES)
    review_nodes = _alignment_tree_review_nodes(
        matches=matches,
        decisions=decisions,
        child_key=child_key,
        statuses=selected_statuses,
        context=context,
    )
    approved = sum(decision.get("approved") is True for _, decision, _ in review_nodes)
    reason_key = f"bulk_{parent_label.lower()}_approval_reason_{context}"
    result_key = f"bulk_{parent_label.lower()}_approval_result_{context}"
    reason_required = any(
        _decision_needs_reviewer_reason(match, decision)
        and not str(decision.get("reason", "")).strip()
        for match, decision, _ in review_nodes
    )
    with st.expander(
        f"Approve filtered {parent_label} → {child_label} tree · {approved} of "
        f"{len(review_nodes)} approved",
        icon=":material/done_all:",
    ):
        st.caption(
            f"The proposed-status filter in {parent_label} match results controls this batch "
            "action. Existing per-node reasons are preserved."
        )
        bulk_reason = st.text_area(
            f"Bulk {parent_label.lower()} reviewer reason"
            + (" (required)" if reason_required else " (optional)"),
            key=reason_key,
            placeholder=(
                f"Explain why these filtered {parent_label.lower()} and "
                f"{child_label.lower()} matches are acceptable."
            ),
        )
        confirmed = st.checkbox(
            f"I reviewed the filter and want to approve all {len(review_nodes)} shown "
            f"{parent_label.lower()}/{child_label.lower()} nodes.",
            key=f"bulk_{parent_label.lower()}_approval_confirmed_{context}",
        )
        st.button(
            f"Approve all filtered {parent_label.lower()} nodes",
            icon=":material/done_all:",
            disabled=(
                not review_nodes or not confirmed or (reason_required and not bulk_reason.strip())
            ),
            key=f"bulk_{parent_label.lower()}_approval_{context}",
            on_click=_approve_filtered_alignment_tree,
            args=(
                matches,
                decisions,
                child_key,
                selected_statuses,
                context,
                reason_key,
                result_key,
            ),
        )
        approved_in_batch = st.session_state.pop(result_key, None)
        if approved_in_batch is not None:
            st.success(
                f"Approved {approved_in_batch} filtered {parent_label.lower()}/"
                f"{child_label.lower()} nodes."
            )


def render_acord_alignment() -> None:
    st.html(
        _hero_banner(
            icon="⚖️",
            eyebrow="ACORD · Canonical Workflow",
            title="ACORD Alignment",
            body=(
                "Compare a regional catalog with an accepted ACORD reference, "
                "resolve each entity, attribute, domain, and capability mapping, "
                "then approve a separate canonical artifact — "
                "neither source catalog is modified."
            ),
            accent="#0ea5e9",
            glow_right="rgba(14,165,233,.14)",
            glow_left="rgba(99,102,241,.07)",
        )
    )
    regions = sorted(
        {
            run.get("profile", {}).get("region")
            for run in st.session_state["application_runs"].values()
            if run.get("discovery_model") and run.get("profile", {}).get("region")
        }
    )
    acord_runs = st.session_state["acord_runs"]
    if not regions or not acord_runs:
        st.info(
            "Alignment requires at least one regional Discovery catalog and one completed "
            "ACORD ingestion.",
            icon=":material/info:",
        )
        return

    canonical_versions = load_canonical_versions(CANONICAL_DATABASE)
    versions_by_number = {item["version"]: item for item in canonical_versions}
    with st.container(border=True):
        st.html(
            _section_heading(
                "Alignment Configuration",
                "Select the regional catalog, ACORD reference, and optional canonical baseline.",
            )
        )
        selection_columns = st.columns(3, gap="large")
        with selection_columns[0]:
            region = st.selectbox(
                "Regional catalog",
                regions,
                format_func=lambda item: f"{item} · {REGIONS.get(item, item)}",
                key="alignment_region",
            )
        with selection_columns[1]:
            acord_run_id = st.selectbox(
                "ACORD reference",
                list(acord_runs),
                format_func=lambda item: (
                    f"{acord_runs[item]['profile']['referenceLabel']} · "
                    f"{acord_runs[item]['profile']['referenceVersion']} [{item[:6]}]"
                ),
                key="alignment_acord_reference",
            )
        with selection_columns[2]:
            baseline_version = st.selectbox(
                "Approved canonical baseline",
                [*versions_by_number, None],
                format_func=lambda item: (
                    "No baseline · compare with ACORD only"
                    if item is None
                    else _canonical_baseline_label(versions_by_number[item])
                ),
                key="alignment_canonical_baseline",
            )
        if canonical_versions:
            available_versions = ", ".join(f"v{item['version']}" for item in canonical_versions)
            st.caption(
                f":material/layers: Available immutable baselines: {available_versions}. "
                "Newest listed first; every earlier version remains selectable."
            )
    canonical_baseline = (
        versions_by_number[baseline_version]["artifact"] if baseline_version is not None else None
    )
    if canonical_baseline:
        st.info(
            f"v{baseline_version} is compared first. Only incomplete baseline matches "
            "fall back to the selected ACORD reference; remaining gaps require reviewer input.",
            icon=":material/account_tree:",
        )

    model_tree = regional_model_tree(st.session_state["application_runs"], region=region)
    domain_tree = regional_domain_tree(st.session_state["application_runs"], region=region)
    _, endpoint_rows = regional_catalog_rows(st.session_state["application_runs"], region=region)
    approved_region = st.session_state["approved_regional_reviews"].get(region)
    regional_source = build_regional_alignment_source(
        region,
        model_tree,
        approved_region["review"] if approved_region else None,
    )
    if not approved_region:
        st.warning(
            "Regional View is not approved. This review uses a deterministic projection of "
            "the current catalog; approve Regional View first for governed regional names."
        )
    if any(item["name"] == "Awaiting API Analyzer" for item in domain_tree):
        st.warning(
            "Some domain/capability values still await API Analyzer and will require a manual "
            "alignment decision."
        )
    agent_inputs = {
        "region": region,
        "regional_source": regional_source,
        "regional_domain_tree": domain_tree,
        "regional_endpoints": endpoint_rows,
        "acord_model": acord_runs[acord_run_id]["model"],
        "acord_run_id": acord_run_id,
        "canonical_baseline": canonical_baseline,
        "baseline_version": baseline_version,
    }
    digest = alignment_input_digest(**agent_inputs)
    run_id = f"alignment-{digest}"
    agent_state = load_alignment_agent_state(ALIGNMENT_AGENT_DATABASE, run_id)
    if agent_state is None:
        try:
            with st.status("Running Alignment Agent", expanded=True) as status:
                agent_state = run_alignment_agent(
                    ALIGNMENT_AGENT_DATABASE,
                    run_id=run_id,
                    progress=st.write,
                    **agent_inputs,
                )
                status.update(
                    label="Alignment Agent is ready for review",
                    state="complete",
                    expanded=False,
                )
        except AlignmentAgentError as exc:
            st.error(f"Alignment Agent stopped at a recoverable checkpoint: {exc}")
            st.info(
                "The regional and ACORD inputs are saved in SQLite. Resume retries only the "
                "failed graph node; completed nodes are not repeated.",
                icon=":material/database:",
            )
            return
    elif agent_state.get("status") != "awaiting_review":
        st.warning(
            "This Alignment Agent run stopped before review. Its input and completed node "
            "state are available in SQLite.",
            icon=":material/pause_circle:",
        )
        resume_col, reset_col = st.columns(2, gap="small")
        with resume_col:
            if st.button(
                "Resume Alignment Agent",
                icon=":material/play_arrow:",
                key=f"resume_{run_id}",
            ):
                try:
                    with st.status("Resuming Alignment Agent", expanded=True) as status:
                        resume_alignment_agent(
                            ALIGNMENT_AGENT_DATABASE,
                            run_id,
                            progress=st.write,
                        )
                        status.update(label="Alignment Agent resumed", state="complete")
                    st.rerun()
                except AlignmentAgentError as exc:
                    st.error(f"Alignment Agent resume failed: {exc}")
                    st.info(
                        "If the run cannot be recovered, use **Reset alignment** to clear "
                        "the checkpoint and re-run from the beginning with the same inputs.",
                        icon=":material/info:",
                    )
        with reset_col:
            if st.button(
                "Reset alignment",
                icon=":material/restart_alt:",
                key=f"reset_{run_id}",
                help="Clears the stuck checkpoint so the alignment runs from scratch.",
            ):
                purge_alignment_agent_run(ALIGNMENT_AGENT_DATABASE, run_id)
                st.success("Alignment checkpoint cleared. Run the alignment again.")
                st.rerun()
        return

    proposal = agent_state["proposal"]
    context = run_id
    for item_id, generated in st.session_state["canonical_gap_proposals"].get(context, {}).items():
        proposal = attach_generated_gap_proposal(proposal, item_id, generated)
    decisions = st.session_state["acord_alignment_drafts"].setdefault(
        context, agent_state["decisions"]
    )
    summary = proposal["matchSummary"]
    _matched_pct = summary["matchedPercent"]
    _acord_label = acord_runs[acord_run_id]["profile"]["referenceLabel"]
    _ring_color = (
        "#22c55e" if _matched_pct >= 75 else "#f59e0b" if _matched_pct >= 40 else "#ef4444"
    )
    _align_tiles = "".join(
        [
            _stat_tile(f"{summary['unmatchedPercent']:.1f}%", "Unmatched", "#ef4444"),
            _stat_tile(summary["fullMatch"], "Full Matches", "#3b82f6"),
            _stat_tile(summary["partialMatch"], "Partial Matches", "#f59e0b"),
            _stat_tile(summary["notMatched"], "Not Matched", "#8b5cf6"),
        ]
    )
    _ring_html = _coverage_ring_html(_matched_pct)
    st.html(f"""
<div style="background:linear-gradient(135deg,#ffffff 0%,#f0f7ff 100%);
            border:1px solid {_ring_color}44;border-radius:12px;padding:24px;margin:10px 0;
            box-shadow:0 2px 12px rgba(37,99,235,.08)">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;
              flex-wrap:wrap;gap:8px;margin-bottom:18px">
    <div>
      <h2 style="color:#1e293b;margin:0;font-size:1.25rem;font-weight:600;
                 font-family:system-ui">Coverage Summary</h2>
      <p style="color:#64748b;margin:5px 0 0;font-size:.83rem;font-family:system-ui">
        Region: <strong style="color:#1e293b">{region}</strong>
        &ensp;&middot;&ensp;ACORD: <strong style="color:#1e293b">{_acord_label}</strong>
      </p>
    </div>
    {
        _status_pill(
            f"{_matched_pct:.1f}% MATCHED",
            "success" if _matched_pct >= 75 else "warning" if _matched_pct >= 40 else "neutral",
        )
    }
  </div>
  <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap">
    {_ring_html}
    <div style="display:flex;gap:12px;flex-wrap:wrap;flex:1">
      {_align_tiles}
    </div>
  </div>
  <p style="color:#64748b;font-size:.72rem;margin:16px 0 0;font-family:system-ui">
    Coverage formula: full&nbsp;match&nbsp;=&nbsp;1.0
    &ensp;&middot;&ensp;partial&nbsp;match&nbsp;=&nbsp;0.5
    &ensp;&middot;&ensp;Approval requires an explicit decision for every item.
  </p>
</div>""")
    st.divider()

    entity_tab, domain_tab = st.tabs(
        ["Regional entities and attributes", "Domains and capabilities"],
        key="alignment_review_tabs",
        on_change="rerun",
    )
    with entity_tab:
        _render_alignment_tree(
            title="Entity match results",
            matches=proposal["entities"],
            decisions=decisions["entities"],
            parent_label="Entity",
            child_label="Attribute",
            child_key="attributes",
            context=f"entity_{context}",
            gap_context=context,
        )
    with domain_tab:
        _render_alignment_tree(
            title="Domain match results",
            matches=proposal["domains"],
            decisions=decisions["domains"],
            parent_label="Domain",
            child_label="Capability",
            child_key="capabilities",
            context=f"domain_{context}",
            gap_context=context,
        )

    entity_review_decisions = list(decisions["entities"].values())
    attribute_review_decisions = [
        attribute
        for entity in entity_review_decisions
        for attribute in entity.get("attributes", {}).values()
    ]
    domain_review_decisions = list(decisions["domains"].values())
    capability_review_decisions = [
        capability
        for domain in domain_review_decisions
        for capability in domain.get("capabilities", {}).values()
    ]
    entity_reviews = [*entity_review_decisions, *attribute_review_decisions]
    domain_reviews = [*domain_review_decisions, *capability_review_decisions]
    approved_entity_reviews = sum(item.get("approved") is True for item in entity_reviews)
    approved_domain_reviews = sum(item.get("approved") is True for item in domain_reviews)

    st.divider()
    st.markdown("#### Approve canonical alignment")
    st.progress(
        approved_entity_reviews / len(entity_reviews) if entity_reviews else 1.0,
        text=f"Entity and attribute approvals: {approved_entity_reviews} of {len(entity_reviews)}",
    )
    st.progress(
        approved_domain_reviews / len(domain_reviews) if domain_reviews else 1.0,
        text=f"Domain and capability approvals: {approved_domain_reviews} of {len(domain_reviews)}",
    )
    _render_alignment_bulk_approval(
        matches=proposal["entities"],
        decisions=decisions["entities"],
        parent_label="Entity",
        child_label="Attribute",
        child_key="attributes",
        context=f"entity_{context}",
    )
    _render_alignment_bulk_approval(
        matches=proposal["domains"],
        decisions=decisions["domains"],
        parent_label="Domain",
        child_label="Capability",
        child_key="capabilities",
        context=f"domain_{context}",
    )

    persist_alignment_decisions(ALIGNMENT_AGENT_DATABASE, run_id, decisions)
    errors = validate_alignment_decisions(proposal, decisions)
    if errors:
        st.error(f"{len(errors)} review decision(s) remain unresolved.")
        approval_errors = [error for error in errors if error.endswith("needs explicit approval")]
        detail_errors = [error for error in errors if error not in approval_errors]
        entity_detail_errors = [
            e for e in detail_errors if e.startswith("Entity ") or e.startswith("Attribute ")
        ]
        domain_detail_errors = [
            e for e in detail_errors if e.startswith("Domain ") or e.startswith("Capability ")
        ]
        other_detail_errors = [
            e
            for e in detail_errors
            if e not in entity_detail_errors and e not in domain_detail_errors
        ]
        st.caption(
            f"{len(approval_errors)} await explicit approval; {len(detail_errors)} need a "
            "missing or invalid decision detail."
        )
        if any("needs a manual canonical name" in e for e in detail_errors):
            st.caption(
                "To fix a **manual canonical name** error: open the **Review** popover for "
                "that item in the tree above, then either type a name into the "
                "'manual canonical name' field or change the canonical resolution to a "
                "different selection (e.g. Use ACORD or Use baseline)."
            )
        st.caption(f"Showing all {len(errors)} unresolved decisions below.")
        with st.container(border=True, height=360):
            if approval_errors:
                st.markdown(f"**Awaiting explicit approval ({len(approval_errors)})**")
                st.markdown("\n".join(f"- {error}" for error in approval_errors))
            if entity_detail_errors:
                st.markdown(
                    f"**In the 'Regional entities and attributes' tab"
                    f" — {len(entity_detail_errors)} item(s) to fix:**"
                )
                st.markdown("\n".join(f"- {error}" for error in entity_detail_errors))
            if domain_detail_errors:
                st.markdown(
                    f"**In the 'Domains and capabilities' tab"
                    f" — {len(domain_detail_errors)} item(s) to fix:**"
                )
                st.markdown("\n".join(f"- {error}" for error in domain_detail_errors))
            if other_detail_errors:
                st.markdown(f"**Other missing or invalid details ({len(other_detail_errors)})**")
                st.markdown("\n".join(f"- {error}" for error in other_detail_errors))
    confirmed = st.checkbox(
        "I reviewed all entity, attribute, domain, and capability decisions and approve this "
        "canonical alignment.",
        key=f"alignment_confirmed_{context}",
    )
    next_version = max((item["version"] for item in canonical_versions), default=0) + 1
    if errors:
        st.info(
            "Submission is locked until every unresolved decision shown above is corrected.",
            icon=":material/lock:",
        )
    elif not confirmed:
        st.info(
            f"All decisions are valid. Confirm the complete alignment to submit canonical "
            f"v{next_version}.",
            icon=":material/check_circle:",
        )
    else:
        st.success(
            f"Ready to save this approved alignment and append canonical v{next_version} to SQLite."
        )
    if st.button(
        f"Submit and save canonical v{next_version}",
        type="primary",
        icon=":material/publish:",
        disabled=bool(errors) or not confirmed,
        key=f"approve_alignment_{context}",
    ):
        try:
            artifact = approve_acord_alignment(proposal, decisions)
            alignment_id = uuid4().hex
            save_alignment_artifact(ALIGNMENT_HISTORY_ROOT, alignment_id, artifact)
            submitted = submit_canonical_version(
                CANONICAL_DATABASE,
                alignment_id=alignment_id,
                artifact=artifact,
                review=default_final_review(artifact),
            )
            st.session_state["alignment_reviews"][alignment_id] = artifact
            st.session_state["active_alignment_id"] = alignment_id
            st.session_state["submitted_canonical_version"] = submitted["version"]
            st.success(
                f"Canonical v{submitted['version']} was submitted and saved in SQLite. "
                "It is now available in Version history and as an Approved canonical baseline."
            )
        except Exception as exc:  # Local persistence failures must remain operator-visible.
            st.error(f"Canonical submission failed: {exc}")


def render_canonical_view() -> None:
    st.html(
        _hero_banner(
            icon="🏛️",
            eyebrow="Canonical Platform · Final Artifact",
            title="Canonical Model",
            body=(
                "Inspect reviewer-approved regional alignment decisions. "
                "Submit the reviewed model as an immutable versioned snapshot — "
                "later regions can extend a submitted baseline through "
                "baseline-first comparison before falling back to ACORD."
            ),
            accent="#22c55e",
            glow_right="rgba(34,197,94,.12)",
            glow_left="rgba(16,185,129,.06)",
        )
    )
    delete_notice = st.session_state.pop("alignment_delete_notice", None)
    if delete_notice:
        st.success(delete_notice)
    alignments = st.session_state["alignment_reviews"]
    if not alignments:
        st.info(
            "No canonical model is approved yet. Resolve and approve an ACORD alignment first.",
            icon=":material/info:",
        )
        return
    alignment_ids = list(reversed(alignments))
    selected_id = st.selectbox(
        "Approved canonical alignment",
        alignment_ids,
        index=(
            alignment_ids.index(st.session_state["active_alignment_id"])
            if st.session_state["active_alignment_id"] in alignments
            else 0
        ),
        format_func=lambda item: (
            f"{alignments[item]['region']} · "
            f"{alignments[item]['acordReference'].get('referenceLabel', 'ACORD')} "
            f"{alignments[item]['acordReference'].get('referenceVersion', '')} [{item[:6]}]"
        ),
        key="approved_canonical_alignment",
    )
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "Delete selected alignment",
            icon=":material/delete:",
            key=f"request_delete_alignment_{selected_id}",
        ):
            st.session_state["pending_alignment_deletion"] = selected_id
    if st.session_state.get("pending_alignment_deletion") == selected_id:
        confirm_delete_alignment(selected_id)
    st.session_state["active_alignment_id"] = selected_id
    artifact = alignments[selected_id]
    summary = artifact["summary"]
    _cv_ref = artifact.get("acordReference", {})
    _cv_tiles = "".join(
        [
            _stat_tile(summary["canonicalEntities"], "Entities", "#3b82f6"),
            _stat_tile(summary["canonicalAttributes"], "Attributes", "#8b5cf6"),
            _stat_tile(summary["canonicalDomains"], "Domains", "#06b6d4"),
            _stat_tile(summary["canonicalCapabilities"], "Capabilities", "#f59e0b"),
            _stat_tile(summary["canonicalEndpoints"], "Endpoints", "#22c55e"),
        ]
    )
    st.html(
        _summary_card_html(
            title=(
                f"{artifact.get('region', '—')} &ensp;&middot;&ensp; "
                f"{_cv_ref.get('referenceLabel', 'ACORD')} {_cv_ref.get('referenceVersion', '')}"
            ),
            subtitle=(
                f"Alignment ID: <code style='background:#f1f5f9;padding:2px 6px;"
                f"border-radius:4px;color:#475569;font-size:.78rem'>{selected_id[:12]}</code>"
            ),
            pill_text="APPROVED",
            pill_kind="success",
            stat_tiles_html=_cv_tiles,
        )
    )
    st.divider()
    entity_tab, endpoint_tab, review_tab, history_tab = st.tabs(
        [
            "Canonical entities",
            "Canonical endpoints",
            "Final review and submit",
            "Version history",
        ],
        key="canonical_result_tabs",
        on_change="rerun",
    )
    with entity_tab:
        for entity in artifact["canonicalModel"]["entities"]:
            with st.expander(
                f"{entity['name']} · {len(entity['attributes'])} attributes · "
                f"{entity['matchStatus']}"
            ):
                st.write(entity.get("description") or "No description available.")
                st.dataframe(
                    [
                        {
                            "Attribute": field["name"],
                            "Type": field["type"],
                            "Required": field["required"],
                            "Description": field.get("description"),
                            "Constraints": json.dumps(field.get("constraints", {}), sort_keys=True),
                            "Standard": field["standard"],
                            "Match": field["matchStatus"],
                            "Reason": field["reviewerReason"],
                        }
                        for field in entity["attributes"]
                    ],
                    hide_index=True,
                    width="stretch",
                )
    with endpoint_tab:
        endpoint_rows = [
            {
                "API": endpoint["api"],
                "Operation": endpoint["operation"],
                "Method": endpoint["method"],
                "Route": endpoint["route"],
                "Domain": endpoint["domain"],
                "Capability": endpoint["capability"],
                "Approved entities": ", ".join(
                    f"{item['entity']} ({item['usage']})" for item in endpoint["entities"]
                )
                or "No mapped entity",
                "Description": endpoint.get("description"),
            }
            for endpoint in artifact["canonicalEndpoints"]
        ]
        st.dataframe(endpoint_rows, hide_index=True, width="stretch")
    with review_tab:
        st.subheader("Review the entire canonical model", anchor=False)
        st.caption(
            "For every item, use the approved canonical value, keep the regional original, or "
            "reject it from this submitted version. Submission always creates a new version."
        )
        review_key = f"final_canonical_review_{selected_id}"
        review = st.session_state.setdefault(review_key, default_final_review(artifact))
        mappings = {
            (item["kind"], item["canonical"]): item
            for item in artifact.get("alignmentMappings", [])
        }

        entity_rows = []
        attribute_rows = []
        for entity in artifact["canonicalModel"]["entities"]:
            entity_mapping = mappings.get(("Entity", entity["name"]), {})
            entity_rows.append(
                {
                    "ID": entity["id"],
                    "Canonical entity": entity["name"],
                    "Regional original": entity_mapping.get("regional", entity["name"]),
                    "Description": entity.get("description"),
                    "Action": review["entities"][entity["id"]],
                }
            )
            for attribute in entity["attributes"]:
                attribute_mapping = mappings.get(
                    ("Attribute", f"{entity['name']}.{attribute['name']}"), {}
                )
                attribute_rows.append(
                    {
                        "ID": attribute["id"],
                        "Entity": entity["name"],
                        "Canonical attribute": attribute["name"],
                        "Regional original": str(
                            attribute_mapping.get("regional", attribute["name"])
                        ).rsplit(".", 1)[-1],
                        "Type": attribute["type"],
                        "Required": attribute["required"],
                        "Description": attribute.get("description"),
                        "Constraints": json.dumps(attribute.get("constraints", {}), sort_keys=True),
                        "Action": review["attributes"][attribute["id"]],
                    }
                )
        edited_entities = st.data_editor(
            entity_rows,
            hide_index=True,
            width="stretch",
            disabled=["ID", "Canonical entity", "Regional original", "Description"],
            column_config={
                "Action": st.column_config.SelectboxColumn(options=list(REVIEW_ACTIONS))
            },
            key=f"final_entities_{selected_id}",
        )
        for row in edited_entities:
            review["entities"][row["ID"]] = row["Action"]
        with st.expander("Review attributes", expanded=True):
            edited_attributes = st.data_editor(
                attribute_rows,
                hide_index=True,
                width="stretch",
                disabled=[
                    "ID",
                    "Entity",
                    "Canonical attribute",
                    "Regional original",
                    "Type",
                    "Required",
                    "Description",
                    "Constraints",
                ],
                column_config={
                    "Action": st.column_config.SelectboxColumn(options=list(REVIEW_ACTIONS))
                },
                key=f"final_attributes_{selected_id}",
            )
            for row in edited_attributes:
                review["attributes"][row["ID"]] = row["Action"]

        domain_rows = []
        capability_rows = []
        for mapping in artifact.get("alignmentMappings", []):
            if mapping["kind"] == "Domain":
                domain_rows.append(
                    {
                        "Canonical domain": mapping["canonical"],
                        "Regional original": mapping["regional"],
                        "Action": review["domains"][mapping["canonical"]],
                    }
                )
            elif mapping["kind"] == "Capability":
                capability_rows.append(
                    {
                        "Canonical capability": mapping["canonical"],
                        "Regional original": mapping["regional"],
                        "Action": review["capabilities"][mapping["canonical"]],
                    }
                )
        st.subheader("Domain and capability review", anchor=False)
        edited_domains = st.data_editor(
            domain_rows,
            hide_index=True,
            width="stretch",
            disabled=["Canonical domain", "Regional original"],
            column_config={
                "Action": st.column_config.SelectboxColumn(options=list(REVIEW_ACTIONS))
            },
            key=f"final_domains_{selected_id}",
        )
        for row in edited_domains:
            review["domains"][row["Canonical domain"]] = row["Action"]
        edited_capabilities = st.data_editor(
            capability_rows,
            hide_index=True,
            width="stretch",
            disabled=["Canonical capability", "Regional original"],
            column_config={
                "Action": st.column_config.SelectboxColumn(options=list(REVIEW_ACTIONS))
            },
            key=f"final_capabilities_{selected_id}",
        )
        for row in edited_capabilities:
            review["capabilities"][row["Canonical capability"]] = row["Action"]

        st.markdown("#### Submit the complete model")
        confirmed = st.checkbox(
            "I reviewed the complete entity, attribute, domain, and capability model.",
            key=f"final_review_confirmed_{selected_id}",
        )
        if st.button(
            "Submit new canonical model version",
            type="primary",
            icon=":material/publish:",
            disabled=not confirmed,
            key=f"submit_canonical_version_{selected_id}",
        ):
            submitted = submit_canonical_version(
                CANONICAL_DATABASE,
                alignment_id=selected_id,
                artifact=artifact,
                review=review,
            )
            st.session_state["submitted_canonical_version"] = submitted["version"]
            st.success(f"Canonical v{submitted['version']} was stored in SQLite.")

    with history_tab:
        versions = load_canonical_versions(CANONICAL_DATABASE)
        if not versions:
            st.info("No final canonical model version has been submitted yet.")
        else:
            version_number = st.selectbox(
                "Submitted version",
                [item["version"] for item in versions],
                format_func=lambda item: f"v{item}",
                key="submitted_canonical_version_selector",
            )
            version = next(item for item in versions if item["version"] == version_number)
            submitted_summary = version["artifact"]["summary"]
            version_metrics = st.columns(5)
            version_metrics[0].metric("Entities", submitted_summary["canonicalEntities"])
            version_metrics[1].metric("Attributes", submitted_summary["canonicalAttributes"])
            version_metrics[2].metric("Domains", submitted_summary["canonicalDomains"])
            version_metrics[3].metric("Capabilities", submitted_summary["canonicalCapabilities"])
            version_metrics[4].metric("Endpoints", submitted_summary["canonicalEndpoints"])
            st.caption(f"Submitted {version['createdAt']} · SQLite v{version_number}")
            st.json(version["artifact"], expanded=2)
            with st.container(horizontal=True):
                st.download_button(
                    "Download canonical JSON",
                    data=(
                        json.dumps(version["artifact"], indent=2, sort_keys=True) + "\n"
                    ).encode(),
                    file_name=f"canonical-model-v{version_number}.json",
                    mime="application/json",
                    icon=":material/download:",
                    key=f"download_canonical_model_{version_number}",
                )
                st.download_button(
                    "Download OpenAPI JSON",
                    data=version["openapiJson"],
                    file_name=f"canonical-openapi-v{version_number}.json",
                    mime="application/json",
                    icon=":material/download:",
                    key=f"download_canonical_openapi_json_{version_number}",
                )
                st.download_button(
                    "Download OpenAPI YAML",
                    data=version["openapiYaml"],
                    file_name=f"canonical-openapi-v{version_number}.yaml",
                    mime="application/yaml",
                    icon=":material/download:",
                    key=f"download_canonical_openapi_yaml_{version_number}",
                )


with acord_alignment_tab:
    render_acord_alignment()

with canonical_view_tab:
    render_canonical_view()

if False:  # Retained temporarily to keep the former placeholder outside the live UI.
    st.header("Canonical view")
    st.badge("Planned", color="gray", icon=":material/schedule:")
    st.caption(
        "Review the future ACORD-to-regional alignment without changing either source catalog."
    )
    entity_column, domain_column, gap_column = st.columns(3)
    with entity_column.container(border=True, height="stretch"):
        st.subheader("Entity alignment", anchor=False)
        st.markdown(
            "Compare ACORD entities and attributes with the approved regional entity catalog."
        )
        st.badge("Awaiting alignment", color="gray", icon=":material/hourglass_empty:")
    with domain_column.container(border=True, height="stretch"):
        st.subheader("Domain and capability alignment", anchor=False)
        st.markdown("Compare ACORD concepts with regional domains and API Analyzer capabilities.")
        st.badge("Awaiting alignment", color="gray", icon=":material/hourglass_empty:")
    with gap_column.container(border=True, height="stretch"):
        st.subheader("ACORD gap identification", anchor=False)
        st.markdown("Report aligned and unaligned regional coverage as counts and percentages.")
        st.metric("Aligned", "—")
        st.metric("Unaligned", "—")
    st.info(
        "Canonical alignment metrics will become available only after ACORD alignment is "
        "implemented and a reviewer accepts its mappings.",
        icon=":material/info:",
    )
