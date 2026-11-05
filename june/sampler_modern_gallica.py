#!/usr/bin/env python3
"""
sampler_modern_gallica.py
Random sample of clean alignments — produces a self-contained HTML viewer.
Run on server, scp the HTML back for inspection.
"""

import json
import random
import sys
import os

INPUT   = "/path/to/alignements/modern_gallica/output/alignments_clean.jsonl"
OUTPUT  = "/path/to/alignements/modern_gallica/output/sample_viewer.html"
N       = 200
SEED    = 42

random.seed(SEED)

# Reservoir sampling — single pass, no seeking
reservoir = []
with open(INPUT, "rb") as fh:
    for n, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if len(reservoir) < N:
            reservoir.append(rec)
        else:
            j = random.randint(0, n - 1)
            if j < N:
                reservoir[j] = rec

random.shuffle(reservoir)
print(f"Sampled {len(reservoir)} records from {n:,} total.", flush=True)

# ── Build HTML ────────────────────────────────────────────────────────────────
def esc(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

samples_js = json.dumps([
    {
        "sp": rec.get("source_passage",""),
        "tp": rec.get("target_passage",""),
        "sa": rec.get("source_author",""),
        "ta": rec.get("target_author",""),
        "st": rec.get("source_title",""),
        "tt": rec.get("target_title",""),
        "sy": rec.get("source_year",""),
        "ty": rec.get("target_year",""),
    }
    for rec in reservoir
], ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>modern × Gallica — Sample Spot-Check ({N} records)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Georgia, serif; background: #1a1a2e; color: #e0e0e0; padding: 24px; }}
  h1 {{ color: #c9a96e; margin-bottom: 4px; font-size: 1.25em; }}
  .subtitle {{ color: #888; font-size: .82em; margin-bottom: 20px; }}
  .controls {{ display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }}
  .nav-btn {{ padding: 7px 20px; border-radius: 6px; border: none;
              background: #3a3a5a; color: #ddd; cursor: pointer; font-size: .9em; }}
  .nav-btn:hover {{ background: #4a4a6a; }}
  .counter {{ color: #888; font-size: .88em; }}
  .card {{ background: #22223a; border-radius: 10px; padding: 20px;
           border: 1px solid #3a3a5a; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
  .col-label {{ color: #c9a96e; font-size: .76em; text-transform: uppercase;
                letter-spacing: .07em; margin-bottom: 5px; }}
  .meta {{ color: #7a8a9a; font-size: .78em; margin-bottom: 8px; font-style: italic; }}
  .passage {{ background: #161628; border-radius: 6px; padding: 13px;
              font-size: .87em; line-height: 1.65; white-space: pre-wrap;
              border: 1px solid #2a2a4a; min-height: 80px; }}
  kbd {{ background:#333; border:1px solid #555; border-radius:3px;
         padding:1px 5px; font-size:.78em; color:#aaa; }}
</style>
</head>
<body>
<h1>modern × Gallica — Clean Alignment Spot-Check</h1>
<p class="subtitle">{N} random samples from 680,269 clean alignments &nbsp;|&nbsp;
  <kbd>←</kbd> <kbd>→</kbd> to navigate</p>

<div class="controls">
  <button class="nav-btn" onclick="prev()">← Prev</button>
  <button class="nav-btn" onclick="next()">Next →</button>
  <span class="counter" id="counter"></span>
</div>
<div class="card" id="card"></div>

<script>
const S = {samples_js};
let i = 0;

function render() {{
  const s = S[i];
  document.getElementById('counter').textContent = (i+1) + ' / ' + S.length;
  document.getElementById('card').innerHTML = `
    <div class="cols">
      <div>
        <div class="col-label">Source (modern)</div>
        <div class="meta">${{esc(s.sa)}} · ${{esc(s.st)}} (${{s.sy || '?'}})</div>
        <div class="passage">${{esc(s.sp)}}</div>
      </div>
      <div>
        <div class="col-label">Target (Gallica)</div>
        <div class="meta">${{esc(s.ta)}} · ${{esc(s.tt)}} (${{s.ty || '?'}})</div>
        <div class="passage">${{esc(s.tp)}}</div>
      </div>
    </div>`;
}}

function esc(s) {{
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function next() {{ if (i < S.length-1) {{ i++; render(); }} }}
function prev() {{ if (i > 0) {{ i--; render(); }} }}
document.addEventListener('keydown', e => {{
  if (e.key==='ArrowRight') next();
  if (e.key==='ArrowLeft')  prev();
}});
render();
</script>
</body>
</html>"""

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Viewer saved to {OUTPUT}")
