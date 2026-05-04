import glob
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _iter_jsonl(paths: List[str]):
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def _parse_iso(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _sanitize_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
        if x != x:
            return None
        return x
    except Exception:
        return None


def _svg_line_chart(title: str, xs: List[str], ys: List[Optional[float]], width: int = 980, height: int = 240) -> str:
    if not xs or not ys:
        return f"<h3>{title}</h3><p>No data.</p>"

    values = [v for v in ys if isinstance(v, (int, float))]
    if not values:
        return f"<h3>{title}</h3><p>No numeric data.</p>"

    y_min = min(values)
    y_max = max(values)
    if y_max == y_min:
        y_max = y_min + 1.0

    pad_l, pad_r, pad_t, pad_b = 50, 20, 20, 40
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b

    def x_pos(i: int) -> float:
        return pad_l + (i / max(len(xs) - 1, 1)) * w

    def y_pos(v: float) -> float:
        return pad_t + (1.0 - (v - y_min) / (y_max - y_min)) * h

    pts = []
    for i, v in enumerate(ys):
        if v is None:
            pts.append(None)
        else:
            pts.append((x_pos(i), y_pos(float(v))))

    d = []
    started = False
    for p in pts:
        if p is None:
            started = False
            continue
        x, y = p
        if not started:
            d.append(f"M {x:.2f} {y:.2f}")
            started = True
        else:
            d.append(f"L {x:.2f} {y:.2f}")

    ticks = 5
    y_grid = []
    for k in range(ticks + 1):
        v = y_min + (k / ticks) * (y_max - y_min)
        y = y_pos(v)
        y_grid.append((v, y))

    x_label_every = max(int(len(xs) / 6), 1)
    x_labels = [(i, xs[i]) for i in range(0, len(xs), x_label_every)]
    if len(xs) > 1 and x_labels[-1][0] != len(xs) - 1:
        x_labels.append((len(xs) - 1, xs[-1]))

    svg = []
    svg.append(f"<h3>{title}</h3>")
    svg.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>')

    for v, y in y_grid:
        svg.append(f'<line x1="{pad_l}" y1="{y:.2f}" x2="{pad_l + w}" y2="{y:.2f}" stroke="#eee" stroke-width="1"/>')
        svg.append(f'<text x="{pad_l - 8}" y="{y + 4:.2f}" font-size="11" text-anchor="end" fill="#666">{v:.3g}</text>')

    svg.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + h}" stroke="#aaa" stroke-width="1"/>')
    svg.append(f'<line x1="{pad_l}" y1="{pad_t + h}" x2="{pad_l + w}" y2="{pad_t + h}" stroke="#aaa" stroke-width="1"/>')

    for i, label in x_labels:
        x = x_pos(i)
        svg.append(f'<line x1="{x:.2f}" y1="{pad_t + h}" x2="{x:.2f}" y2="{pad_t + h + 5}" stroke="#aaa" stroke-width="1"/>')
        svg.append(f'<text x="{x:.2f}" y="{pad_t + h + 18}" font-size="11" text-anchor="middle" fill="#666">{label}</text>')

    path_d = " ".join(d) if d else ""
    svg.append(f'<path d="{path_d}" fill="none" stroke="#2b6cb0" stroke-width="2"/>')

    last_v = next((v for v in reversed(ys) if v is not None), None)
    if last_v is not None:
        svg.append(f'<text x="{pad_l + w}" y="{pad_t + 12}" font-size="12" text-anchor="end" fill="#111">last={float(last_v):.6g}</text>')

    svg.append("</svg>")
    return "\n".join(svg)


def _svg_bar_chart(title: str, items: List[Tuple[str, int]], width: int = 980, height: int = 220) -> str:
    if not items:
        return f"<h3>{title}</h3><p>No data.</p>"

    pad_l, pad_r, pad_t, pad_b = 50, 20, 20, 50
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b

    max_v = max(v for _, v in items) if items else 1
    if max_v <= 0:
        max_v = 1

    bar_w = w / max(len(items), 1)

    svg = []
    svg.append(f"<h3>{title}</h3>")
    svg.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>')
    svg.append(f'<line x1="{pad_l}" y1="{pad_t + h}" x2="{pad_l + w}" y2="{pad_t + h}" stroke="#aaa" stroke-width="1"/>')
    svg.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + h}" stroke="#aaa" stroke-width="1"/>')

    for i, (k, v) in enumerate(items):
        x = pad_l + i * bar_w + bar_w * 0.15
        bw = bar_w * 0.7
        bh = (v / max_v) * h
        y = pad_t + h - bh
        svg.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bw:.2f}" height="{bh:.2f}" fill="#2f855a"/>')
        svg.append(f'<text x="{x + bw/2:.2f}" y="{pad_t + h + 18}" font-size="11" text-anchor="middle" fill="#666">{k}</text>')
        svg.append(f'<text x="{x + bw/2:.2f}" y="{y - 4:.2f}" font-size="11" text-anchor="middle" fill="#111">{v}</text>')

    svg.append("</svg>")
    return "\n".join(svg)


def generate_charts(last_n: int = 50, out_path: Optional[str] = None) -> str:
    metrics_paths = glob.glob(os.path.join("metrics", "metrics.jsonl*"))
    records = list(_iter_jsonl(sorted(metrics_paths)))
    records.sort(key=lambda r: _parse_iso(str(r.get("ts", ""))))

    if last_n > 0:
        records = records[-last_n:]

    xs = []
    llm_sec = []
    total_sec = []
    turnover = []
    status_count: Dict[str, int] = {}

    for r in records:
        ts = str(r.get("ts", ""))
        if len(ts) >= 19:
            xs.append(ts[11:19])
        else:
            xs.append(str(len(xs)))
        llm_sec.append(_sanitize_float(r.get("llm_sec")))
        total_sec.append(_sanitize_float(r.get("total_sec")))
        turnover.append(_sanitize_float(r.get("turnover")))
        st = str(r.get("status", "unknown"))
        status_count[st] = status_count.get(st, 0) + 1

    status_items = sorted(status_count.items(), key=lambda kv: (-kv[1], kv[0]))

    body = []
    body.append("<!doctype html>")
    body.append('<html lang="en">')
    body.append("<head>")
    body.append('<meta charset="utf-8"/>')
    body.append("<meta name='viewport' content='width=device-width, initial-scale=1'/>")
    body.append("<title>Metrics Charts</title>")
    body.append("<style>")
    body.append("body{font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial; margin:24px; color:#111;} h2{margin-top:0;} h3{margin:22px 0 10px;} .grid{max-width:1020px;} .hint{color:#666; font-size:13px;}")
    body.append("</style>")
    body.append("</head>")
    body.append("<body>")
    body.append('<div class="grid">')
    body.append("<h2>Metrics Charts</h2>")
    body.append(f'<div class="hint">source: metrics/metrics.jsonl*, last_n={len(records)}</div>')
    body.append(_svg_bar_chart("Run Status", status_items))
    body.append(_svg_line_chart("LLM Latency (sec)", xs, llm_sec))
    body.append(_svg_line_chart("Total Runtime (sec)", xs, total_sec))
    body.append(_svg_line_chart("Turnover Ratio", xs, turnover))
    body.append("</div>")
    body.append("</body></html>")

    os.makedirs("reports", exist_ok=True)
    if out_path is None:
        out_path = os.path.join("reports", "charts.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    return out_path


if __name__ == "__main__":
    print(generate_charts())

