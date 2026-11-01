# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "vyom.html")
CSS_PATH = os.path.join(BASE_DIR, "vyom_style.css")

# ═════════════════════════════════════════════════════════════════════════
# 1. RADICAL ZERO-CARD CONTINUOUS EDITORIAL CSS
# ═════════════════════════════════════════════════════════════════════════
RADICAL_CSS = """
/* ═════════════════════════════════════════════════════════════════════════
   VYOM CONTINUOUS TEACHING OPERATING WORKSPACE — RADICAL ZERO-CARD DESIGN
   Zero Cards · Zero Boxes · Zero Rectangular Panels · Pure Editorial Flow
   ═════════════════════════════════════════════════════════════════════════ */

:root {
  --vyom-hairline: rgba(0, 0, 0, 0.08);
  --vyom-hairline-subtle: rgba(0, 0, 0, 0.04);
  --vyom-canvas-bg: #FAF9F5;
  --vyom-text-title: #111215;
  --vyom-text-body: #2B2D33;
  --vyom-text-muted: #72757E;
  --vyom-accent: #E88918;
  --vyom-emerald: #059669;
  --vyom-blue: #2563EB;
  --vyom-rose: #DC2626;
}

.dark,
body:not(.light) {
  --vyom-hairline: rgba(255, 255, 255, 0.09);
  --vyom-hairline-subtle: rgba(255, 255, 255, 0.04);
  --vyom-canvas-bg: #0B0C0E;
  --vyom-text-title: #F4F4F6;
  --vyom-text-body: #E2E3E7;
  --vyom-text-muted: #8E919C;
}

/* Base continuous page canvas */
.vyom-editorial-workspace {
  background: var(--vyom-canvas-bg);
  min-height: 100vh;
  width: 100% !important;
  max-width: none !important;
  box-sizing: border-box;
  padding: 32px 40px;
  display: flex;
  flex-direction: column;
  gap: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif;
  color: var(--vyom-text-body);
}

@media (max-width: 768px) {
  .vyom-editorial-workspace {
    padding: 20px 16px;
  }
}

/* ── 1. TOP HORIZON: CLASSROOM STATUS LINE (UNBOXED) ── */
.vyom-horizon-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--vyom-hairline);
  margin-bottom: 26px;
  background: transparent !important;
  box-shadow: none !important;
  border-radius: 0 !important;
}

.vyom-horizon-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.vyom-horizon-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.vyom-horizon-status.active { color: var(--vyom-emerald); }
.vyom-horizon-status.paused { color: var(--vyom-accent); }
.vyom-horizon-status.ended { color: var(--vyom-text-muted); }
.vyom-horizon-status.waiting { color: var(--vyom-accent); }

.vyom-horizon-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  position: relative;
}

.vyom-horizon-status.active .vyom-horizon-dot::after {
  content: '';
  position: absolute;
  top: -3px;
  left: -3px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 1.5px solid var(--vyom-emerald);
  animation: vyom-ping 1.6s cubic-bezier(0, 0, 0.2, 1) infinite;
  box-sizing: border-box;
}

@keyframes vyom-ping {
  0% { transform: scale(0.6); opacity: 1; }
  100% { transform: scale(2.2); opacity: 0; }
}

.vyom-horizon-sep {
  color: var(--vyom-hairline);
  font-weight: 300;
  font-size: 0.9rem;
  user-select: none;
}

.vyom-horizon-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--vyom-text-title);
  letter-spacing: -0.015em;
  margin: 0;
}

.vyom-horizon-code-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.vyom-horizon-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-weight: 750;
  font-size: 0.88rem;
  color: var(--vyom-accent);
  letter-spacing: 0.05em;
}

.vyom-horizon-btn-ghost {
  background: transparent;
  border: none;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--vyom-text-muted);
  cursor: pointer;
  padding: 0 4px;
  text-decoration: underline;
  text-underline-offset: 3px;
  transition: color 0.15s ease;
}

.vyom-horizon-btn-ghost:hover {
  color: var(--vyom-text-title);
}

.vyom-horizon-btn-ghost.copied {
  color: var(--vyom-emerald);
}

.vyom-horizon-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 0.82rem;
}

.vyom-horizon-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--vyom-text-muted);
}

.vyom-horizon-meta-num {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--vyom-text-title);
}

.vyom-horizon-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.vyom-action-btn-flat {
  background: transparent;
  border: 1px solid var(--vyom-hairline);
  padding: 6px 14px;
  font-size: 0.78rem;
  font-weight: 650;
  cursor: pointer;
  color: var(--vyom-text-title);
  transition: all 0.15s ease;
  white-space: nowrap;
}

.vyom-action-btn-flat:hover {
  border-color: var(--vyom-text-title);
  background: rgba(0, 0, 0, 0.02);
}

.dark .vyom-action-btn-flat:hover {
  background: rgba(255, 255, 255, 0.05);
}

.vyom-action-btn-flat.primary {
  background: var(--vyom-accent);
  color: #FFFFFF;
  border-color: var(--vyom-accent);
}

.vyom-action-btn-flat.primary:hover {
  background: #D97706;
  border-color: #D97706;
}

.vyom-action-btn-flat.danger {
  color: var(--vyom-rose);
  border-color: rgba(220, 38, 38, 0.3);
}

.vyom-action-btn-flat.danger:hover {
  background: rgba(220, 38, 38, 0.08);
}

.vyom-action-btn-flat.warning {
  color: var(--vyom-accent);
  border-color: rgba(232, 137, 24, 0.3);
}

.vyom-toggle-link {
  background: none;
  border: none;
  font-size: 0.72rem;
  font-weight: 650;
  color: var(--vyom-text-muted);
  cursor: pointer;
  padding: 4px 8px;
  transition: color 0.15s ease;
}

.vyom-toggle-link:hover {
  color: var(--vyom-text-title);
}

.vyom-toggle-link.active {
  color: var(--vyom-accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.vyom-toggle-link.geo-active {
  color: var(--vyom-blue);
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* ── 2. LIVE METRICS HORIZON (TYPOGRAPHY-DRIVEN, CONTINUOUS) ── */
.vyom-metrics-horizon {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border-bottom: 1px solid var(--vyom-hairline);
  padding-bottom: 28px;
  margin-bottom: 34px;
  background: transparent !important;
  box-shadow: none !important;
  border-radius: 0 !important;
}

@media (max-width: 1024px) {
  .vyom-metrics-horizon {
    grid-template-columns: repeat(2, 1fr);
    row-gap: 24px;
  }
}

@media (max-width: 600px) {
  .vyom-metrics-horizon {
    grid-template-columns: 1fr;
    row-gap: 20px;
  }
}

.vyom-metric-column {
  padding: 0 24px;
  border-right: 1px solid var(--vyom-hairline);
  display: flex;
  flex-direction: column;
  gap: 6px;
  box-sizing: border-box;
}

.vyom-metric-column:first-child {
  padding-left: 0;
}

.vyom-metric-column:last-child {
  border-right: none;
  padding-right: 0;
}

@media (max-width: 1024px) {
  .vyom-metric-column:nth-child(2) {
    border-right: none;
    padding-right: 0;
  }
}

.vyom-metric-eyebrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.65rem;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--vyom-text-muted);
}

.vyom-metric-number-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 2px 0;
}

.vyom-metric-giant {
  font-size: 2.4rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.035em;
  line-height: 1;
  color: var(--vyom-text-title);
}

.vyom-metric-giant.emerald { color: var(--vyom-emerald); }
.vyom-metric-giant.amber { color: var(--vyom-accent); }

.vyom-metric-delta {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--vyom-emerald);
}

.vyom-metric-delta.neutral {
  color: var(--vyom-text-muted);
}

.vyom-metric-progress-rule {
  width: 100%;
  height: 2px;
  background: var(--vyom-hairline);
  margin-top: 4px;
  position: relative;
  overflow: hidden;
}

.vyom-metric-progress-fill {
  height: 100%;
  background: var(--vyom-accent);
  transition: width 0.3s ease;
}

.vyom-metric-progress-fill.emerald {
  background: var(--vyom-emerald);
}

.vyom-metric-footnote {
  font-size: 0.72rem;
  color: var(--vyom-text-muted);
  line-height: 1.4;
  margin-top: 2px;
}

.vyom-type-switch-inline {
  display: inline-flex;
  gap: 6px;
}

.vyom-type-btn {
  background: none;
  border: none;
  font-size: 0.62rem;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--vyom-text-muted);
  cursor: pointer;
  padding: 0;
}

.vyom-type-btn.active {
  color: var(--vyom-accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.vyom-editorial-link {
  background: none;
  border: none;
  padding: 0;
  font-size: 0.72rem;
  font-weight: 650;
  color: var(--vyom-accent);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
  align-self: flex-start;
  margin-top: 2px;
}

.vyom-editorial-link:hover {
  color: #D97706;
}

/* ── 3. WORKSPACE SPLIT: CONTINUOUS ASYMMETRIC FLOW ── */
.vyom-editorial-split {
  display: grid;
  grid-template-columns: minmax(0, 68%) minmax(0, 32%);
  gap: 40px;
  align-items: start;
  width: 100%;
  box-sizing: border-box;
}

@media (max-width: 1100px) {
  .vyom-editorial-split {
    grid-template-columns: 1fr;
    gap: 32px;
  }
}

.vyom-flow-main {
  display: flex;
  flex-direction: column;
  gap: 28px;
  min-width: 0;
}

.vyom-flow-sidebar {
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-width: 0;
  border-left: 1px solid var(--vyom-hairline);
  padding-left: 32px;
}

@media (max-width: 1100px) {
  .vyom-flow-sidebar {
    border-left: none;
    padding-left: 0;
    border-top: 1px solid var(--vyom-hairline);
    padding-top: 32px;
  }
}

/* Editorial Section Heading */
.vyom-editorial-heading-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--vyom-hairline);
  margin-bottom: 14px;
}

.vyom-editorial-heading {
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--vyom-text-title);
  margin: 0;
}

.vyom-editorial-subheading {
  font-size: 0.72rem;
  color: var(--vyom-text-muted);
}

/* Waiting Room Admission Strip (Unboxed) */
.vyom-admission-strip {
  border-left: 3px solid var(--vyom-accent);
  padding: 8px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  background: rgba(232, 137, 24, 0.04);
}

.vyom-admission-title {
  font-size: 0.75rem;
  font-weight: 750;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--vyom-accent);
}

.vyom-admission-chips {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.vyom-admission-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 600;
}

.vyom-inline-action-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0 3px;
  font-size: 0.75rem;
  font-weight: 700;
}

.vyom-inline-action-btn.approve { color: var(--vyom-emerald); }
.vyom-inline-action-btn.reject { color: var(--vyom-rose); }

/* Ledger Inline Controls */
.vyom-ledger-controls-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
}

.vyom-search-underline {
  border: none;
  border-bottom: 1px solid var(--vyom-hairline);
  background: transparent;
  padding: 6px 0;
  font-size: 0.82rem;
  color: var(--vyom-text-title);
  outline: none;
  width: 240px;
  transition: border-color 0.15s ease;
}

.vyom-search-underline:focus {
  border-bottom-color: var(--vyom-text-title);
}

.vyom-filter-text-links {
  display: inline-flex;
  gap: 16px;
}

.vyom-filter-text-btn {
  background: none;
  border: none;
  padding: 0;
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--vyom-text-muted);
  cursor: pointer;
  transition: color 0.15s ease;
}

.vyom-filter-text-btn:hover {
  color: var(--vyom-text-title);
}

.vyom-filter-text-btn.active {
  color: var(--vyom-text-title);
  text-decoration: underline;
  text-underline-offset: 4px;
}

/* Native Unboxed Data Table */
.vyom-native-table-wrap {
  width: 100%;
  overflow-x: auto;
}

.vyom-native-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
  text-align: left;
}

.vyom-native-table thead tr {
  border-bottom: 1px solid var(--vyom-hairline);
}

.vyom-native-table th {
  padding: 10px 12px;
  font-size: 0.65rem;
  font-weight: 750;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vyom-text-muted);
}

.vyom-native-table th:first-child { padding-left: 0; }
.vyom-native-table th:last-child { padding-right: 0; }

.vyom-native-table tbody tr {
  border-bottom: 1px solid var(--vyom-hairline-subtle);
  transition: background 0.1s ease;
}

.vyom-native-table tbody tr:hover {
  background: rgba(0, 0, 0, 0.015);
}

.dark .vyom-native-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.vyom-native-table td {
  padding: 14px 12px;
  vertical-align: middle;
}

.vyom-native-table td:first-child { padding-left: 0; }
.vyom-native-table td:last-child { padding-right: 0; }

.vyom-st-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.vyom-st-monogram {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(232, 137, 24, 0.1);
  color: var(--vyom-accent);
  font-weight: 750;
  font-size: 0.76rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.vyom-st-monogram img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}

.vyom-st-identity-stack {
  display: flex;
  flex-direction: column;
}

.vyom-st-fullname {
  font-weight: 650;
  color: var(--vyom-text-title);
}

.vyom-st-subkey {
  font-size: 0.65rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--vyom-text-muted);
}

.vyom-presence-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.74rem;
  color: var(--vyom-text-muted);
}

.vyom-presence-pulse-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--vyom-emerald);
}

.vyom-geo-tag-text {
  font-size: 0.65rem;
  font-weight: 750;
  margin-left: 4px;
}

.vyom-geo-tag-text.in { color: var(--vyom-emerald); }
.vyom-geo-tag-text.out { color: var(--vyom-rose); }

.vyom-score-stack {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100px;
}

.vyom-inline-track {
  width: 100%;
  height: 3px;
  background: var(--vyom-hairline);
  position: relative;
  overflow: hidden;
}

.vyom-inline-track-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.vyom-inline-track-fill.emerald { background: var(--vyom-emerald); }
.vyom-inline-track-fill.blue { background: var(--vyom-blue); }
.vyom-inline-track-fill.rose { background: var(--vyom-rose); }
.vyom-inline-track-fill.muted { background: var(--vyom-text-muted); }

.vyom-tier-text-tag {
  font-size: 0.68rem;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.vyom-tier-text-tag.emerald { color: var(--vyom-emerald); }
.vyom-tier-text-tag.blue { color: var(--vyom-blue); }
.vyom-tier-text-tag.rose { color: var(--vyom-rose); }
.vyom-tier-text-tag.muted { color: var(--vyom-text-muted); }

.vyom-kick-link {
  background: none;
  border: none;
  color: var(--vyom-rose);
  font-size: 0.72rem;
  font-weight: 650;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.vyom-kick-link:hover {
  opacity: 0.8;
}

.vyom-empty-state-editorial {
  padding: 40px 0;
  text-align: left;
}

.vyom-empty-state-editorial h3 {
  font-size: 1rem;
  font-weight: 700;
  margin: 0 0 6px 0;
  color: var(--vyom-text-title);
}

.vyom-empty-state-editorial p {
  font-size: 0.8rem;
  color: var(--vyom-text-muted);
  margin: 0;
  line-height: 1.5;
}

/* ── 4. RIGHT COLUMN: EDITORIAL BRIEFING, TIMELINE & SPATIAL (UNBOXED) ── */
.vyom-briefing-stream {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.vyom-briefing-prose-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.vyom-prose-tag {
  font-size: 0.64rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.vyom-prose-tag.observation { color: var(--vyom-emerald); }
.vyom-prose-tag.pattern { color: var(--vyom-blue); }
.vyom-prose-tag.recommendation { color: var(--vyom-accent); }

.vyom-prose-body {
  font-size: 0.8rem;
  line-height: 1.5;
  color: var(--vyom-text-body);
  margin: 0;
}

/* Timeline unboxed */
.vyom-timeline-stream {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.vyom-tl-stream-item {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.vyom-tl-timestamp {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.68rem;
  color: var(--vyom-text-muted);
  flex-shrink: 0;
}

.vyom-tl-msg {
  font-size: 0.78rem;
  line-height: 1.4;
  color: var(--vyom-text-body);
}

.vyom-tl-msg-sub {
  font-size: 0.68rem;
  color: var(--vyom-text-muted);
  display: block;
}

/* Spatial unboxed */
.vyom-spatial-stream {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.vyom-spatial-prose {
  font-size: 0.76rem;
  color: var(--vyom-text-muted);
  margin: 0;
  line-height: 1.4;
}

.vyom-spatial-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.vyom-minimal-select {
  border: 1px solid var(--vyom-hairline);
  background: transparent;
  padding: 5px 8px;
  font-size: 0.76rem;
  color: var(--vyom-text-title);
  outline: none;
}

.vyom-minimal-range {
  flex: 1;
  min-width: 100px;
}

.vyom-hairline-sep {
  border: none;
  border-top: 1px solid var(--vyom-hairline);
  margin: 20px 0;
  width: 100%;
}
"""

with open(CSS_PATH, "r", encoding="utf-8") as f:
    css_content = f.read()

# Replace any previous .vyom-os-dashboard or .vyom-editorial-workspace block
start_pos = css_content.find("/* ═════════════════════════════════════════════════════════════════════════\n   VYOM CONTINUOUS TEACHING OPERATING WORKSPACE")
if start_pos == -1:
    start_pos = css_content.find("/* ═════════════════════════════════════════════════════════════════\n   VYOM TEACHER OPERATING SYSTEM")

if start_pos != -1:
    css_content = css_content[:start_pos] + RADICAL_CSS
else:
    css_content += "\n\n" + RADICAL_CSS

with open(CSS_PATH, "w", encoding="utf-8") as f:
    f.write(css_content)

print("vyom_style.css updated with Radical Zero-Card CSS successfully.")


# ═════════════════════════════════════════════════════════════════════════
# 2. RADICAL ZERO-CARD TeacherDashboard COMPONENT
# ═════════════════════════════════════════════════════════════════════════
RADICAL_JS = '''// ═════════════════════════════════════════════════════════════════════════
//  VYOM TEACHER OPERATING SYSTEM — RADICAL ZERO-CARD CONTINUOUS WORKSPACE
//  Zero Cards · Zero Boxes · Pure Typographic Editorial Instrument
// ═════════════════════════════════════════════════════════════════════════

function TeacherDashboard({
  teacherName,
  sessionCode,
  tasks,
  groups,
  roster,
  analytics,
  sessionStatus,
  sessionDurationMins,
  sessionEndTimestamp,
  sessionControl,
  loadTasks,
  wsSend,
  teacherProfileEmail,
  accessMode,
  setAccessMode,
  closeAccessRadius,
  setCloseAccessRadius,
  teacherLocation,
  geoMessage,
  accessSaving,
  saveAccessSettings,
  captureTeacherLocation,
  setGeoMessage,
  setPage,
  autoJoinEnabled,
  toggleAutoJoin
}) {
  const { add } = useContext(AppCtx);

  // Profile photo cached
  const profilePhoto = (() => {
    try {
      const u = JSON.parse(localStorage.getItem('cm_user') || '{}');
      return localStorage.getItem('cm_avatar_' + (u.email || u.id || 'teacher')) || null;
    } catch { return null; }
  })();

  // Core task dispatch handlers
  async function sendTask(taskId, targetType, targetId = null) {
    if (!taskId) return;
    try {
      const resolvedType = (targetType || 'all').toLowerCase().trim();
      const resolvedId = resolvedType === 'all' ? 'all' : String(targetId || '').trim() || 'all';
      const res = await sendTaskRequest(sessionCode, taskId, resolvedType, resolvedId);
      const label = res.target?.label || (resolvedType === 'student' ? 'student' : resolvedType === 'group' ? 'group' : 'entire class');
      add(`✅ Task sent to ${label}`, 'success');
    } catch (err) {
      add(err.message || 'Error sending task', 'error');
    }
  }

  async function sendNextTask() {
    if (sessionStatus !== 'active') {
      add('▶ Start the session first to enable actions', 'error');
      return;
    }
    try {
      const r = await apiFetch(`/api/session/${sessionCode}/tasks/send_current`, { method: 'POST' });
      add('Task sent to students', 'success');
    } catch (e) {
      add(e.message, 'error');
    }
  }

  // Student moderation handlers
  async function approveStudent(id, e) {
    if (e) {
      if (typeof e.preventDefault === 'function') e.preventDefault();
      if (typeof e.stopPropagation === 'function') e.stopPropagation();
    }
    try {
      await apiFetch(`/api/session/${sessionCode}/approve/${id}`, { method: 'POST' });
      add('Student approved', 'success');
    } catch (e) {
      add(e.message, 'error');
    }
  }

  async function rejectStudent(id) {
    try {
      await apiFetch(`/api/session/${sessionCode}/reject/${id}`, { method: 'POST' });
    } catch {}
  }

  async function kickStudent(id) {
    try {
      await apiFetch(`/api/session/${sessionCode}/kick/${id}`, { method: 'POST' });
      add('Student removed', 'info');
    } catch {}
  }

  const approveAllWaiting = async () => {
    const list = roster?.waiting || [];
    if (list.length === 0) return;
    for (const st of list) {
      try {
        await apiFetch(`/api/session/${sessionCode}/approve/${st.id}`, { method: 'POST' });
      } catch (_) {}
    }
    add(`Approved all ${list.length} waiting students`, 'success');
  };

  // End session modal state & logic
  const [showEndModal, setShowEndModal] = useState(false);
  const [emailInput, setEmailInput] = useState(teacherProfileEmail || '');
  const [topicInput, setTopicInput] = useState('');
  const [emailSent, setEmailSent] = useState(false);
  const [emailSending, setEmailSending] = useState(false);
  const [gdriveSaving, setGdriveSaving] = useState(false);
  const [gdriveConnected, setGdriveConnected] = useState(false);

  async function handleEndSession() {
    setShowEndModal(true);
    try {
      const res = await apiFetch('/api/teacher/settings/google-drive');
      setGdriveConnected(res.connected);
    } catch (_) {
      setGdriveConnected(false);
    }
  }

  async function downloadAndEnd() {
    try {
      const res = await fetch(`${API}/api/session/${sessionCode}/report/download`);
      const data = await res.json();
      const blob = new Blob([data.csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${sessionCode}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {}
    setShowEndModal(false);
    sessionControl('end');
  }

  async function sendEmailAndEnd() {
    if (!emailInput.trim()) return;
    setEmailSending(true);
    setShowEndModal(false);
    sessionControl('end');
    try {
      const res = await apiFetch(`/api/session/${sessionCode}/send-report`, {
        method: 'POST',
        body: { email: emailInput.trim(), session_id: sessionCode }
      });
      if (res.success || res.status === 'success') {
        add('📧 Email queued! It will arrive in your inbox shortly.', 'success');
        setEmailSent(true);
      } else {
        add('⚠️ ' + (res.message || 'Email failed') + '. You can resend it later from history.', 'warning');
      }
    } catch (e) {
      add('❌ Error: ' + e.message, 'error');
    } finally {
      setEmailSending(false);
    }
  }

  async function saveToDriveAndEnd() {
    setGdriveSaving(true);
    setShowEndModal(false);
    sessionControl('end');
    try {
      const res = await apiFetch(`/api/session/${sessionCode}/save-report-gdrive`, { method: 'POST' });
      if (res.success || res.status === 'success') {
        add('💾 Report successfully saved to Google Drive!', 'success');
      } else {
        add('⚠️ ' + (res.message || 'Drive save failed') + '. You can save it later from history.', 'warning');
      }
    } catch (e) {
      add('❌ Google Drive Error: ' + e.message, 'error');
    } finally {
      setGdriveSaving(false);
    }
  }

  async function connectGoogleDrive() {
    try {
      const user = JSON.parse(localStorage.getItem('cm_user') || '{}');
      const email = user.email || '';
      if (!email) {
        add('Teacher email not found in profile', 'error');
        return;
      }
      const res = await apiFetch(`/api/auth/google/url?email=${encodeURIComponent(email)}`);
      if (res.url) {
        const width = 600, height = 650;
        const left = (window.innerWidth - width) / 2;
        const top = (window.innerHeight - height) / 2;
        const popup = window.open(res.url, 'Connect Google Drive', `width=${width},height=${height},top=${top},left=${left}`);
        const timer = setInterval(async () => {
          if (popup.closed) {
            clearInterval(timer);
            try {
              const status = await apiFetch('/api/teacher/settings/google-drive');
              if (status.connected) {
                setGdriveConnected(true);
                add('🎉 Google Drive connected successfully!', 'success');
              }
            } catch (_) {}
          }
        }, 2000);
      } else {
        add('Failed to get connection URL', 'error');
      }
    } catch (e) {
      add('❌ Error connecting Google Drive: ' + e.message, 'error');
    }
  }

  // Session countdown timer
  const [countdownSecs, setCountdownSecs] = useState(0);
  const sessionStartRef = useRef(null);
  useEffect(() => {
    if (sessionStatus === 'active') {
      if (!sessionStartRef.current) sessionStartRef.current = Date.now();
      const id = setInterval(() => {
        if (sessionEndTimestamp) {
          const remaining = Math.max(0, Math.floor((sessionEndTimestamp - Date.now()) / 1000));
          setCountdownSecs(remaining);
          if (remaining === 0) {
            clearInterval(id);
            handleEndSession();
          }
        } else if (sessionDurationMins > 0 && sessionStartRef.current) {
          const elapsed = Math.floor((Date.now() - sessionStartRef.current) / 1000);
          const totalSecs = sessionDurationMins * 60;
          const remaining = Math.max(0, totalSecs - elapsed);
          setCountdownSecs(remaining);
          if (remaining === 0) {
            clearInterval(id);
            handleEndSession();
          }
        }
      }, 1000);
      return () => clearInterval(id);
    } else if (sessionStatus !== 'paused') {
      sessionStartRef.current = null;
      setCountdownSecs(sessionDurationMins ? sessionDurationMins * 60 : 0);
    }
  }, [sessionStatus, sessionEndTimestamp, sessionDurationMins]);

  const fmtCountdown = (secs) => {
    if (secs <= 0) return '0m 0s';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m ${s}s`;
  };

  const getCountdownColor = (secs) => {
    if (secs <= 0 || sessionStatus !== 'active') return 'var(--vyom-text-muted)';
    if (secs < 5 * 60) return '#DC2626';
    if (secs < 15 * 60) return '#E88918';
    return '#059669';
  };
  const countdownColor = getCountdownColor(countdownSecs);
  const countdownBlink = sessionStatus === 'active' && countdownSecs > 0 && countdownSecs < 5 * 60;

  // Real data rolling window for sparklines
  const understandingHistory = useRef([]);
  const participationHistory = useRef([]);
  const activeStudentsHistory = useRef([]);
  const tasksHistory = useRef([]);

  useEffect(() => {
    const MAX_POINTS = 12;
    const u = analytics?.understanding || 0;
    const p = analytics?.participation || 0;
    const a = roster?.active?.length || 0;
    const t = tasks?.length || 0;
    if (sessionStatus === 'active' || u > 0 || p > 0 || a > 0) {
      const push = (arr, val) => { arr.push(val); if (arr.length > MAX_POINTS) arr.shift(); };
      push(understandingHistory.current, u);
      push(participationHistory.current, p);
      push(activeStudentsHistory.current, a);
      push(tasksHistory.current, t);
    }
  }, [analytics?.understanding, analytics?.participation, roster?.active?.length, tasks?.length, sessionStatus]);

  const understanding = analytics?.understanding || 0;

  // AI Insights Generation from real classroom telemetry
  function buildInsights(opts) {
    const _sessionStatus = opts.sessionStatus;
    const _roster        = opts.roster        || { active: [], waiting: [] };
    const _analytics     = opts.analytics     || {};
    const _tasks         = Array.isArray(opts.tasks) ? opts.tasks : [];
    const _phist         = opts.participationHistory || [];
    const _uhist         = opts.understandingHistory || [];

    const isActive = _sessionStatus === 'active';
    const aCount  = (_roster.active  || []).length;
    const wCount  = (_roster.waiting || []).length;
    const part    = _analytics.participation  || 0;
    const undstd  = _analytics.understanding  || 0;
    const atRisk  = (_analytics.at_risk || []).length;

    const pending   = _tasks.filter(t => t.status === 'pending' || !t.status).length;
    const completed = _tasks.filter(t => t.status === 'completed' || t.status === 'reviewed').length;
    const total     = _tasks.length;

    const msgs = [];
    if (isActive && aCount === 0) msgs.push('Session is active. Share the class code with students to begin streaming live classroom responses.');
    if (wCount > 0) msgs.push(`${wCount} student${wCount > 1 ? 's are' : ' is'} in the waiting room ready for entry approval.`);
    if (atRisk > 0) msgs.push(`${atRisk} student${atRisk > 1 ? 's' : ''} flagging comprehension difficulty on recent tasks.`);
    if (undstd > 0 && undstd < 40) msgs.push(`Cohort understanding is currently at ${undstd}%. Consider presenting an engagement recap.`);
    if (pending > 0 && total > 0) msgs.push(`${pending} assignment${pending > 1 ? 's' : ''} currently awaiting student submission.`);
    if (part >= 75 && isActive) msgs.push(`Outstanding participation at ${part}%. The classroom is demonstrating strong responsiveness.`);
    if (undstd >= 70) msgs.push(`Solid grasp across students (${undstd}% average). Ready for next curriculum exercise.`);
    if (msgs.length === 0) msgs.push('Telemetry engine ready. Classroom activity updates will stream continuously.');
    return msgs;
  }

  const AI_MESSAGES = buildInsights({
    sessionStatus,
    roster,
    analytics,
    tasks,
    participationHistory: participationHistory.current,
    understandingHistory: understandingHistory.current
  });

  const [aiMsgIdx, setAiMsgIdx] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => {
      setAiMsgIdx(prev => (prev + 1) % AI_MESSAGES.length);
    }, 7000);
    return () => clearInterval(interval);
  }, [AI_MESSAGES.length]);

  // Search & Filter state
  const [studentSearch, setStudentSearch] = useState('');
  const [understandingType, setUnderstandingType] = useState('mcq');
  const [studentFilter, setStudentFilter] = useState('all');
  const [codeCopied, setCodeCopied] = useState(false);

  const copySessionCode = () => {
    if (navigator.clipboard && sessionCode) {
      navigator.clipboard.writeText(sessionCode).then(() => {
        setCodeCopied(true);
        add('Classroom code copied', 'success');
        setTimeout(() => setCodeCopied(false), 2000);
      }).catch(() => {});
    }
  };

  // Activity Timeline
  const [timelineEvents, setTimelineEvents] = useState([
    { id: '1', type: 'system', icon: '●', title: 'Workspace Initialized', detail: `Classroom session: ${sessionCode}`, time: 'Live' }
  ]);

  const prevActiveLen = useRef((roster?.active || []).length);
  useEffect(() => {
    const active = roster?.active || [];
    if (active.length > prevActiveLen.current) {
      const newest = active[active.length - 1];
      const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      setTimelineEvents(prev => [
        { id: 'st-' + Date.now(), type: 'student', icon: '●', title: `${newest?.name || 'New Student'} connected`, detail: 'Enrolled in workspace', time: nowStr },
        ...prev.slice(0, 15)
      ]);
    }
    prevActiveLen.current = active.length;
  }, [roster?.active]);

  const prevStatusRef = useRef(sessionStatus);
  useEffect(() => {
    if (prevStatusRef.current !== sessionStatus) {
      const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const statusLabel = sessionStatus === 'active' ? 'Session started' : sessionStatus === 'paused' ? 'Session paused' : sessionStatus === 'ended' ? 'Session ended' : 'Session ready';
      setTimelineEvents(prev => [
        { id: 'status-' + Date.now(), type: 'session', icon: '●', title: statusLabel, detail: `Status changed to ${sessionStatus}`, time: nowStr },
        ...prev.slice(0, 15)
      ]);
      prevStatusRef.current = sessionStatus;
    }
  }, [sessionStatus]);

  // Derived metrics
  const activeCount   = roster?.active?.length || 0;
  const waitingCount  = roster?.waiting?.length || 0;
  const participation = analytics?.participation || 0;
  const atRiskCount   = analytics?.at_risk?.length || 0;
  const completedTasks = tasks.filter(t => t.status === 'completed' || t.status === 'reviewed').length;
  const pendingTasks   = tasks.filter(t => t.status === 'pending' || !t.status).length;
  const taskTotal      = tasks.length;
  const completionRate = taskTotal > 0 ? Math.round((completedTasks / taskTotal) * 100) : 0;
  const prevUnderstanding = understandingHistory.current.length >= 2 ? understandingHistory.current[understandingHistory.current.length - 2] : null;

  // Filtered Students for the ledger
  const displayedStudents = (roster.active || []).filter(st => {
    if (studentSearch && !(st.name || '').toLowerCase().includes(studentSearch.toLowerCase())) {
      return false;
    }
    if (studentFilter === 'in_radius') {
      return st.in_radius === true || st.geo_status === 'in_range';
    }
    if (studentFilter === 'needs_support') {
      const pct = st.total_answered > 0 ? (st.correct / st.total_answered) * 100 : 0;
      return pct < 50 || (analytics?.at_risk || []).includes(st.id);
    }
    if (studentFilter === 'top_performers') {
      const pct = st.total_answered > 0 ? (st.correct / st.total_answered) * 100 : 0;
      return pct >= 75;
    }
    return true;
  });

  return React.createElement("div", { className: "vyom-editorial-workspace" },

    /* ── END SESSION MODAL (Preserved functionality) ── */
    showEndModal && React.createElement("div", {
      style: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 500, padding: 16 }
    }, React.createElement("div", {
      className: "card", style: { width: '100%', maxWidth: 420 }
    },
      React.createElement("div", { style: { fontSize: '1.35rem', fontWeight: 700, marginBottom: 6, textAlign: 'center' } }, "🏁 Conclude Classroom Session"),
      React.createElement("div", { className: "text-muted text-sm text-center", style: { marginBottom: 18 } }, "Save institutional records and summaries before closing."),
      React.createElement("div", { style: { display: 'flex', flexDirection: 'column', gap: 10 } },
        React.createElement("div", { style: { display: 'flex', flexDirection: 'column', gap: 4 } },
          React.createElement("label", { style: { fontSize: '0.82rem', color: 'var(--text2, #71717A)', paddingLeft: 2 } }, "Curriculum Topic Taught Today (Required)"),
          React.createElement("input", {
            value: topicInput,
            onChange: e => setTopicInput(e.target.value),
            placeholder: "e.g., Recursion & Dynamic Programming, Photosynthesis...",
            style: { padding: '10px 12px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg2)', color: 'var(--text1)' }
          })
        ),
        React.createElement(ToggleDownloadBtn, { label: 'Download CSV Summary', doneLabel: 'Saved!', onClick: downloadAndEnd, disabled: !topicInput.trim(), style: { justifyContent: 'center', width: '100%' } }),
        React.createElement("div", { style: { display: 'flex', gap: 8 } },
          React.createElement("input", {
            value: emailInput,
            onChange: e => setEmailInput(e.target.value),
            placeholder: "Teacher email address...",
            style: { flex: 1, padding: '10px 12px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg2)', color: 'var(--text1)' }
          }),
          React.createElement("button", {
            className: "btn btn-ghost",
            onClick: sendEmailAndEnd,
            disabled: !topicInput.trim() || !emailInput.trim() || emailSending
          }, emailSending ? "⏳ Sending..." : "📧 Dispatch")
        ),
        gdriveConnected ?
          React.createElement("button", { className: "btn btn-ghost", style: { justifyContent: 'center', gap: 8 }, onClick: saveToDriveAndEnd, disabled: !topicInput.trim() || gdriveSaving }, gdriveSaving ? '⏳ Saving...' : '💾 Export to Google Drive') :
          React.createElement("button", { className: "btn btn-ghost", style: { justifyContent: 'center', gap: 8, color: '#D4AF37', borderColor: 'rgba(212,175,55,0.3)' }, onClick: connectGoogleDrive, disabled: !topicInput.trim() }, '🔗 Connect Google Drive'),
        React.createElement("button", {
          className: "btn btn-ghost",
          style: { justifyContent: 'center', background: 'rgba(239,68,68,0.1)', color: '#EF4444' },
          onClick: () => { setShowEndModal(false); sessionControl('end'); },
          disabled: !topicInput.trim()
        }, "End Session Immediately"),
        React.createElement("button", {
          className: "btn btn-ghost btn-sm",
          style: { justifyContent: 'center', color: 'var(--text3)' },
          onClick: () => setShowEndModal(false)
        }, "✕ Cancel")
      )
    )),

    /* ── 1. TOP HORIZON: CONTINUOUS CLASSROOM STATUS LINE (UNBOXED) ── */
    React.createElement("div", { className: "vyom-horizon-line" },
      /* Left Instrument Metadata */
      React.createElement("div", { className: "vyom-horizon-left" },
        React.createElement("div", { className: `vyom-horizon-status ${sessionStatus}` },
          React.createElement("span", { className: "vyom-horizon-dot" }),
          sessionStatus === 'active' ? 'LIVE SESSION' : sessionStatus === 'paused' ? 'PAUSED' : sessionStatus === 'ended' ? 'COMPLETED' : 'READY'
        ),
        React.createElement("span", { className: "vyom-horizon-sep" }, "/"),
        React.createElement("h1", { className: "vyom-horizon-title" },
          teacherName ? `${teacherName}` : "Classroom Workspace"
        ),
        React.createElement("span", { className: "vyom-horizon-sep" }, "/"),
        React.createElement("div", { className: "vyom-horizon-code-wrap" },
          React.createElement("span", { style: { fontSize: '0.68rem', color: 'var(--vyom-text-muted)', fontWeight: 700 } }, "CODE:"),
          React.createElement("span", { className: "vyom-horizon-code" }, sessionCode),
          React.createElement("button", {
            className: `vyom-horizon-btn-ghost ${codeCopied ? 'copied' : ''}`,
            onClick: copySessionCode,
            title: "Copy class access code"
          }, codeCopied ? "✓ Copied" : "[Copy]"),
          React.createElement("button", {
            className: "vyom-horizon-btn-ghost",
            onClick: () => {
              if (navigator.share) {
                navigator.share({ title: 'Join VYOM Class', text: `Join class code: ${sessionCode}`, url: `${window.location.origin}/?code=${sessionCode}` }).catch(() => {});
              } else {
                navigator.clipboard.writeText(`${window.location.origin}/?code=${sessionCode}`).then(() => add('Class link copied', 'success')).catch(() => {});
              }
            },
            title: "Share class link"
          }, "[Share]")
        ),
        React.createElement("span", { className: "vyom-horizon-sep" }, "/"),
        React.createElement("div", { className: "vyom-horizon-meta" },
          React.createElement("div", { className: "vyom-horizon-meta-item" },
            "Enrolled:",
            React.createElement("span", { className: "vyom-horizon-meta-num" }, `${roster.active?.length || 0} students`)
          ),
          React.createElement("div", { className: "vyom-horizon-meta-item" },
            "Ends in:",
            React.createElement("span", {
              className: "vyom-horizon-meta-num",
              style: {
                color: countdownColor,
                animation: countdownBlink ? 'blink 1s step-start infinite' : 'none'
              }
            },
              sessionStatus === 'active' ? fmtCountdown(countdownSecs) :
              sessionStatus === 'paused' ? fmtCountdown(countdownSecs) :
              sessionDurationMins > 0 ? `${sessionDurationMins}m` : "--"
            )
          )
        )
      ),

      /* Right Operational Controls */
      React.createElement("div", { className: "vyom-horizon-right" },
        sessionStatus === 'waiting' && React.createElement("button", {
          id: "start-session-btn",
          className: "vyom-action-btn-flat primary",
          onClick: () => sessionControl('start')
        }, "▶ Start Session"),
        sessionStatus === 'active' && React.createElement("button", {
          className: "vyom-action-btn-flat warning",
          onClick: () => sessionControl('pause')
        }, "⏸ Pause"),
        sessionStatus === 'paused' && React.createElement("button", {
          className: "vyom-action-btn-flat primary",
          onClick: () => sessionControl('resume')
        }, "▶ Resume"),
        (sessionStatus === 'active' || sessionStatus === 'paused') && React.createElement("button", {
          className: "vyom-action-btn-flat danger",
          onClick: handleEndSession
        }, "⏹ Conclude Session"),
        React.createElement("button", {
          className: `vyom-toggle-link ${autoJoinEnabled ? 'active' : ''}`,
          onClick: () => toggleAutoJoin(!autoJoinEnabled),
          title: "Toggle auto-join"
        }, autoJoinEnabled ? "⚡ Auto-Join: Active" : "🔒 Waiting Room"),
        React.createElement("button", {
          className: `vyom-toggle-link ${accessMode === 'close' ? 'geo-active' : ''}`,
          onClick: () => {
            const next = accessMode === 'close' ? 'open' : 'close';
            setAccessMode(next);
            saveAccessSettings(next, teacherLocation).catch(() => {});
          },
          title: "Toggle geo-fence"
        }, accessMode === 'close' ? `📍 Fence: ${closeAccessRadius}m` : "🌐 Open Access")
      )
    ),

    /* ── 2. LIVE METRICS HORIZON (UNBOXED, PURE TYPOGRAPHY) ── */
    React.createElement("div", { className: "vyom-metrics-horizon" },
      /* Column 1: Comprehension */
      React.createElement("div", { className: "vyom-metric-column" },
        React.createElement("div", { className: "vyom-metric-eyebrow" },
          React.createElement("span", null, "01 / COMPREHENSION"),
          React.createElement("div", { className: "vyom-type-switch-inline" },
            [['mcq', 'MCQ'], ['short', 'SHORT'], ['long', 'LONG']].map(([id, label]) =>
              React.createElement("button", {
                key: id,
                className: `vyom-type-btn ${understandingType === id ? 'active' : ''}`,
                onClick: () => setUnderstandingType(id)
              }, label)
            )
          )
        ),
        React.createElement("div", { className: "vyom-metric-number-row" },
          React.createElement("span", { className: "vyom-metric-giant emerald" },
            understandingType === 'mcq'
              ? (understanding || 0) + '%'
              : understandingType === 'short'
                ? (analytics?.understanding_short ?? '—') + (analytics?.understanding_short !== undefined ? '%' : '')
                : (analytics?.understanding_long ?? '—') + (analytics?.understanding_long !== undefined ? '%' : '')
          ),
          React.createElement("span", { className: "vyom-metric-delta" },
            prevUnderstanding !== null && understanding > prevUnderstanding
              ? `↑ +${understanding - prevUnderstanding}%`
              : "● Real-time"
          )
        ),
        React.createElement("div", { className: "vyom-metric-progress-rule" },
          React.createElement("div", {
            className: "vyom-metric-progress-fill emerald",
            style: { width: `${Math.min(100, understanding)}%` }
          })
        ),
        React.createElement("div", { className: "vyom-metric-footnote" },
          understanding >= 70 ? "Cohort retention strong across recent questions." : "Review recommended on difficult concepts."
        )
      ),

      /* Column 2: Engagement */
      React.createElement("div", { className: "vyom-metric-column" },
        React.createElement("div", { className: "vyom-metric-eyebrow" },
          React.createElement("span", null, "02 / ENGAGEMENT & VELOCITY"),
          React.createElement("span", { style: { color: 'var(--vyom-emerald)' } }, "● ACTIVE")
        ),
        React.createElement("div", { className: "vyom-metric-number-row" },
          React.createElement("span", { className: "vyom-metric-giant" }, `${participation}%`),
          React.createElement("span", { className: "vyom-metric-delta neutral" }, `${activeCount} in class`)
        ),
        React.createElement("div", { className: "vyom-metric-progress-rule" },
          React.createElement("div", {
            className: "vyom-metric-progress-fill",
            style: { width: `${Math.min(100, participation)}%` }
          })
        ),
        React.createElement("div", { className: "vyom-metric-footnote" },
          participation >= 75 ? "High active participation across enrolled students." : "Pacing steady · questions underway."
        )
      ),

      /* Column 3: Curriculum */
      React.createElement("div", { className: "vyom-metric-column" },
        React.createElement("div", { className: "vyom-metric-eyebrow" },
          React.createElement("span", null, "03 / CURRICULUM PIPELINE"),
          React.createElement("button", {
            className: "vyom-editorial-link",
            style: { margin: 0 },
            onClick: () => setPage && setPage('tasks')
          }, "Manage →")
        ),
        React.createElement("div", { className: "vyom-metric-number-row" },
          React.createElement("span", { className: "vyom-metric-giant" }, `${completedTasks} / ${taskTotal}`),
          React.createElement("span", { className: "vyom-metric-delta neutral" },
            taskTotal > 0 ? `${completionRate}% Done` : "Ready"
          )
        ),
        React.createElement("div", { className: "vyom-metric-progress-rule" },
          React.createElement("div", {
            className: "vyom-metric-progress-fill",
            style: { width: `${completionRate}%` }
          })
        ),
        React.createElement("div", { className: "vyom-metric-footnote" },
          pendingTasks > 0 ? `${pendingTasks} pending submissions.` : "All assigned tasks evaluated."
        )
      ),

      /* Column 4: Health */
      React.createElement("div", { className: "vyom-metric-column" },
        React.createElement("div", { className: "vyom-metric-eyebrow" },
          React.createElement("span", null, "04 / COHORT HEALTH"),
          React.createElement("span", { style: { color: atRiskCount > 0 ? 'var(--vyom-rose)' : 'var(--vyom-emerald)' } },
            atRiskCount > 0 ? "⚠️ ATTENTION" : "✓ STABLE"
          )
        ),
        React.createElement("div", { className: "vyom-metric-number-row" },
          React.createElement("span", { className: `vyom-metric-giant ${atRiskCount > 0 ? 'amber' : 'emerald'}` },
            atRiskCount > 0 ? `${atRiskCount} Flagged` : "100% OK"
          )
        ),
        React.createElement("div", { className: "vyom-metric-progress-rule" },
          React.createElement("div", {
            className: "vyom-metric-progress-fill",
            style: { width: atRiskCount > 0 ? '40%' : '100%', background: atRiskCount > 0 ? 'var(--vyom-rose)' : 'var(--vyom-emerald)' }
          })
        ),
        React.createElement("div", { className: "vyom-metric-footnote" },
          atRiskCount > 0
            ? React.createElement("button", {
                className: "vyom-editorial-link",
                onClick: () => setStudentFilter('needs_support')
              }, "Filter struggling students in ledger ↓")
            : "Zero comprehension regressions detected."
        )
      )
    ),

    /* ── 3. WORKSPACE SPLIT: CONTINUOUS ASYMMETRIC CONTENT FLOW ── */
    React.createElement("div", { className: "vyom-editorial-split" },

      /* LEFT FLOW: Student Roster & Activity Ledger */
      React.createElement("div", { className: "vyom-flow-main" },

        /* Waiting Room Admissions Strip (Unboxed) */
        roster.waiting?.length > 0 && React.createElement("div", { className: "vyom-admission-strip" },
          React.createElement("span", { className: "vyom-admission-title" },
            `Waiting for Admission (${roster.waiting.length})`
          ),
          React.createElement("div", { className: "vyom-admission-chips" },
            roster.waiting.map(st =>
              React.createElement("div", { key: st.id || Math.random(), className: "vyom-admission-item" },
                React.createElement("span", null, st.name || st.id || 'Student'),
                React.createElement("button", {
                  className: "vyom-inline-action-btn approve",
                  onClick: (e) => approveStudent(st.id, e),
                  title: "Approve entry"
                }, "[✓]"),
                React.createElement("button", {
                  className: "vyom-inline-action-btn reject",
                  onClick: (e) => { e.preventDefault(); e.stopPropagation(); rejectStudent(st.id); },
                  title: "Reject entry"
                }, "[✕]")
              )
            )
          ),
          React.createElement("button", {
            className: "vyom-editorial-link",
            style: { margin: 0, fontWeight: 750 },
            onClick: approveAllWaiting
          }, "Approve All Admissions →")
        ),

        /* Ledger Section Header */
        React.createElement("div", { className: "vyom-editorial-heading-row" },
          React.createElement("h2", { className: "vyom-editorial-heading" }, "Student Activity & Directory Ledger"),
          React.createElement("span", { className: "vyom-editorial-subheading" },
            `Showing ${displayedStudents.length} of ${roster.active?.length || 0} active students`
          )
        ),

        /* Inline Filter & Search Row (No Card) */
        React.createElement("div", { className: "vyom-ledger-controls-row" },
          React.createElement("input", {
            className: "vyom-search-underline",
            placeholder: "Type to search by student name...",
            value: studentSearch,
            onChange: e => setStudentSearch(e.target.value)
          }),
          React.createElement("div", { className: "vyom-filter-text-links" },
            [
              ['all', `All (${roster.active?.length || 0})`],
              ['in_radius', 'In-Radius'],
              ['needs_support', `Support (${atRiskCount})`],
              ['top_performers', 'Mastery']
            ].map(([id, label]) =>
              React.createElement("button", {
                key: id,
                className: `vyom-filter-text-btn ${studentFilter === id ? 'active' : ''}`,
                onClick: () => setStudentFilter(id)
              }, label)
            )
          )
        ),

        /* Native Data Table (Completely Unboxed) */
        React.createElement("div", { className: "vyom-native-table-wrap" },
          displayedStudents.length > 0
            ? React.createElement("table", { className: "vyom-native-table" },
                React.createElement("thead", null,
                  React.createElement("tr", null,
                    React.createElement("th", null, "STUDENT"),
                    React.createElement("th", null, "STATUS & GEO"),
                    React.createElement("th", null, "SUBMISSIONS"),
                    React.createElement("th", null, "ACCURACY"),
                    React.createElement("th", null, "TIER"),
                    React.createElement("th", { style: { textAlign: 'right' } }, "ACTION")
                  )
                ),
                React.createElement("tbody", null,
                  displayedStudents.map(st => {
                    const ansCount = st.total_answered || 0;
                    const correctCount = st.correct || 0;
                    const pct = ansCount > 0 ? Math.round((correctCount / ansCount) * 100) : 0;
                    const tier = pct >= 80 ? 'Mastery' : pct >= 50 ? 'Steady' : ansCount > 0 ? 'Intervention' : 'Initial';
                    const tierClass = pct >= 80 ? 'emerald' : pct >= 50 ? 'blue' : ansCount > 0 ? 'rose' : 'muted';

                    return React.createElement("tr", { key: st.id || Math.random() },
                      /* Student Identity */
                      React.createElement("td", null,
                        React.createElement("div", { className: "vyom-st-cell" },
                          React.createElement("div", {
                            className: "vyom-st-monogram",
                            style: st.profile_photo ? { background: 'transparent' } : {}
                          },
                            st.profile_photo
                              ? React.createElement("img", { src: st.profile_photo, alt: st.name || '?' })
                              : (st.name || '?')[0].toUpperCase()
                          ),
                          React.createElement("div", { className: "vyom-st-identity-stack" },
                            React.createElement("span", { className: "vyom-st-fullname" }, st.name || 'Student'),
                            React.createElement("span", { className: "vyom-st-subkey" }, `ID: ${String(st.id).slice(-6)}`)
                          )
                        )
                      ),
                      /* Presence & Geo */
                      React.createElement("td", null,
                        React.createElement("div", { className: "vyom-presence-indicator" },
                          React.createElement("span", { className: "vyom-presence-pulse-dot" }),
                          "Online",
                          accessMode === 'close' && (
                            st.in_radius === false
                              ? React.createElement("span", { className: "vyom-geo-tag-text out" }, "[Out-Fence]")
                              : React.createElement("span", { className: "vyom-geo-tag-text in" }, "[In-Fence]")
                          )
                        )
                      ),
                      /* Questions */
                      React.createElement("td", null,
                        React.createElement("span", { style: { fontFamily: 'ui-monospace, monospace', fontVariantNumeric: 'tabular-nums' } },
                          `${ansCount} answered`
                        )
                      ),
                      /* Accuracy */
                      React.createElement("td", null,
                        React.createElement("div", { className: "vyom-score-stack" },
                          React.createElement("span", { style: { fontFamily: 'ui-monospace, monospace', fontWeight: 700 } },
                            `${pct}%`,
                            React.createElement("span", { style: { fontSize: '0.68rem', color: 'var(--vyom-text-muted)', fontWeight: 400, marginLeft: 4 } },
                              `(${correctCount}/${ansCount})`
                            )
                          ),
                          React.createElement("div", { className: "vyom-inline-track" },
                            React.createElement("div", {
                              className: `vyom-inline-track-fill ${tierClass}`,
                              style: { width: `${pct}%` }
                            })
                          )
                        )
                      ),
                      /* Tier */
                      React.createElement("td", null,
                        React.createElement("span", { className: `vyom-tier-text-tag ${tierClass}` }, tier)
                      ),
                      /* Action */
                      React.createElement("td", { style: { textAlign: 'right' } },
                        React.createElement("button", {
                          className: "vyom-kick-link",
                          onClick: () => kickStudent(st.id),
                          title: "Remove student from session"
                        }, "Remove")
                      )
                    );
                  })
                )
              )
            : React.createElement("div", { className: "vyom-empty-state-editorial" },
                React.createElement("h3", null,
                  studentSearch ? "No students match the current filter query" : "No active students connected yet"
                ),
                React.createElement("p", null,
                  studentSearch
                    ? "Adjust search keyword or clear filters to view all enrolled students."
                    : `Provide class access code ${sessionCode} to students to begin streaming live classroom responses.`
                )
              )
        ),

        /* Preserved At-Risk Panel */
        React.createElement(AtRiskPanel, { analytics: analytics, roster: roster })
      ),

      /* RIGHT FLOW: AI Teaching Intelligence, Activity Timeline & Spatial */
      React.createElement("div", { className: "vyom-flow-sidebar" },

        /* AI TEACHING INTELLIGENCE (EDITORIAL BRIEFING) */
        React.createElement("div", null,
          React.createElement("div", { className: "vyom-editorial-heading-row" },
            React.createElement("h3", { className: "vyom-editorial-heading" }, "AI Teaching Intelligence"),
            React.createElement("span", { className: "vyom-editorial-subheading" }, "Continuous Briefing")
          ),
          React.createElement("div", { className: "vyom-briefing-stream" },
            React.createElement("div", { className: "vyom-briefing-prose-block" },
              React.createElement("span", { className: "vyom-prose-tag observation" }, "● LIVE OBSERVATION"),
              React.createElement("p", { className: "vyom-prose-body" },
                AI_MESSAGES[aiMsgIdx] || "Monitoring student response stream and submission velocity in real time."
              )
            ),
            React.createElement("div", { className: "vyom-briefing-prose-block" },
              React.createElement("span", { className: "vyom-prose-tag pattern" }, "● LEARNING PATTERN"),
              React.createElement("p", { className: "vyom-prose-body" },
                understanding >= 75
                  ? "High comprehension velocity across questions. Cohort demonstrates readiness for next level."
                  : understanding >= 45
                    ? "Average retention detected. Key multi-step topics may benefit from class recap."
                    : "Comprehension regression detected. Interactive discussion or review activity recommended."
              )
            ),
            React.createElement("div", { className: "vyom-briefing-prose-block" },
              React.createElement("span", { className: "vyom-prose-tag recommendation" }, "● ACTIONABLE RECOMMENDATION"),
              React.createElement("p", { className: "vyom-prose-body" },
                pendingTasks > 0
                  ? `${pendingTasks} tasks currently in queue. Remind students to finalize answers.`
                  : activeCount === 0
                    ? "Classroom session ready. Invite students using the access code."
                    : "Pacing optimal. Ready to dispatch the next curriculum activity."
              )
            ),
            React.createElement("button", {
              className: "vyom-editorial-link",
              onClick: () => setPage && setPage('reports')
            }, "Open Deep Analytics & Institutional Reports →")
          )
        ),

        React.createElement("hr", { className: "vyom-hairline-sep" }),

        /* CLASSROOM ACTIVITY TIMELINE (UNBOXED CHRONOLOGICAL STREAM) */
        React.createElement("div", null,
          React.createElement("div", { className: "vyom-editorial-heading-row" },
            React.createElement("h3", { className: "vyom-editorial-heading" }, "Classroom Activity Timeline"),
            React.createElement("span", { className: "vyom-editorial-subheading" }, "Real-Time Stream")
          ),
          React.createElement("div", { className: "vyom-timeline-stream" },
            timelineEvents.map(ev =>
              React.createElement("div", { key: ev.id, className: "vyom-tl-stream-item" },
                React.createElement("span", { className: "vyom-tl-timestamp" }, ev.time),
                React.createElement("div", { className: "vyom-tl-msg" },
                  React.createElement("strong", null, ev.title),
                  React.createElement("span", { className: "vyom-tl-msg-sub" }, ev.detail)
                )
              )
            )
          )
        ),

        React.createElement("hr", { className: "vyom-hairline-sep" }),

        /* SPATIAL SECURITY & GEO-FENCE (UNBOXED CONTROLS) */
        React.createElement("div", null,
          React.createElement("div", { className: "vyom-editorial-heading-row" },
            React.createElement("h3", { className: "vyom-editorial-heading" }, "Spatial Geo-Fence Security"),
            React.createElement("span", { className: "vyom-editorial-subheading" }, "GPS Verification")
          ),
          React.createElement("div", { className: "vyom-spatial-stream" },
            React.createElement("p", { className: "vyom-spatial-prose" },
              "Enforce in-classroom attendance boundary verification using high-precision GPS positioning."
            ),
            React.createElement("div", { className: "vyom-spatial-row" },
              React.createElement("select", {
                className: "vyom-minimal-select",
                value: accessMode,
                onChange: async e => {
                  const mode = e.target.value;
                  setAccessMode(mode);
                  if (mode === 'close' && !teacherLocation) {
                    setGeoMessage('Close Access selected. Capture teacher location to enable geo-fence.');
                    return;
                  }
                  await saveAccessSettings(mode, teacherLocation);
                }
              },
                React.createElement("option", { value: "open" }, "Open Access (Everywhere)"),
                React.createElement("option", { value: "close" }, "Close Access (GPS Fence)")
              ),
              React.createElement("input", {
                type: "range",
                min: 10,
                max: 1000,
                step: 10,
                value: closeAccessRadius,
                onChange: e => setCloseAccessRadius(Number(e.target.value)),
                className: "vyom-minimal-range",
                title: `Radius: ${closeAccessRadius}m`
              }),
              React.createElement("span", { style: { fontSize: '0.74rem', fontFamily: 'ui-monospace, monospace' } },
                `${closeAccessRadius}m`
              )
            ),
            React.createElement("button", {
              className: "vyom-action-btn-flat",
              onClick: captureTeacherLocation,
              disabled: accessSaving
            }, accessSaving ? "Capturing GPS..." : "📍 Capture Teacher Location"),
            geoMessage && React.createElement("div", { style: { fontSize: '0.72rem', color: 'var(--vyom-text-muted)' } }, geoMessage)
          )
        ),

        React.createElement("hr", { className: "vyom-hairline-sep" }),

        /* Preserved Modules */
        React.createElement(ShareCodePanel, { sessionCode: sessionCode, add: add }),
        React.createElement(CodingPerformanceBar, { sessionCode: sessionCode }),
        React.createElement(SelfContainedAIInsights, null),
        analytics?.topic_confusion && Object.keys(analytics.topic_confusion).length > 0 &&
          React.createElement("div", null,
            React.createElement("div", { className: "vyom-editorial-heading-row" },
              React.createElement("h3", { className: "vyom-editorial-heading" }, "Topic Confusion Diagnostics")
            ),
            Object.entries(analytics.topic_confusion || {}).map(([topic, data]) => {
              const pct = data.total > 0 ? Math.round(data.wrong / data.total * 100) : 0;
              return React.createElement("div", { key: topic, style: { marginBottom: 12 } },
                React.createElement("div", { style: { display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: 4 } },
                  React.createElement("span", null, topic),
                  React.createElement("span", { style: { color: 'var(--vyom-text-muted)' } }, `${pct}% wrong`)
                ),
                React.createElement("div", { className: "vyom-metric-progress-rule" },
                  React.createElement("div", {
                    className: "vyom-metric-progress-fill",
                    style: { width: `${pct}%`, background: pct > 60 ? 'var(--vyom-rose)' : pct > 30 ? 'var(--vyom-accent)' : 'var(--vyom-emerald)' }
                  })
                )
              );
            })
          )
      )
    )
  );
}
'''

# ═════════════════════════════════════════════════════════════════════════
# 3. REPLACE IN vyom.html
# ═════════════════════════════════════════════════════════════════════════
with open(HTML_PATH, "r", encoding="utf-8") as f:
    html_lines = f.readlines()

start_td = None
for i in range(10350, 10400):
    if "function TeacherDashboard(" in html_lines[i]:
        start_td = i
        break

end_td = None
for i in range(11400, 11450):
    if html_lines[i].strip() == "}" and "TASK MANAGEMENT PAGE" in "".join(html_lines[i:i+10]):
        end_td = i
        break

assert start_td is not None and end_td is not None, f"Could not find TeacherDashboard boundaries: start={start_td}, end={end_td}"

print(f"Replacing lines {start_td} to {end_td} in vyom.html with Radical Zero-Card TeacherDashboard...")
new_html_lines = html_lines[:start_td] + [RADICAL_JS + "\n\n"] + html_lines[end_td+1:]

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.writelines(new_html_lines)

print("vyom.html updated with Radical Zero-Card TeacherDashboard successfully!")
