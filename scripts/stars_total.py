#!/usr/bin/env python3
"""Total-stars-over-time chart for all owned public non-fork repos -> light/dark SVGs."""
import datetime as dt
import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("STARS_USER", "kochetkov-ma")
OUT = Path(__file__).resolve().parent.parent / "assets"
API = "https://api.github.com"
log = logging.getLogger("stars_total")

THEMES = {
    "light": {"text": "#1f2328", "muted": "#59636e", "grid": "#d1d9e0", "line": "#B8860B", "ring": "#ffffff"},
    "dark": {"text": "#f0f6fc", "muted": "#9198a1", "grid": "#3d444d", "line": "#D4A32A", "ring": "#0d1117"},
}
W, H = 800, 320
L, R, T, B = 56, 24, 84, 40
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"


def token():
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    # Local run fallback: reuse the gh CLI session, never echo it.
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def get_all(url, tok, accept="application/vnd.github+json"):
    items = []
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": accept,
                                                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                items.extend(json.load(resp))
                url = next((p.split(";")[0].strip(" <>") for p in resp.headers.get("Link", "").split(",")
                            if 'rel="next"' in p), None)
        except urllib.error.HTTPError as err:
            sys.exit(f"GET {url} -> {err.code}: {err.read()[:300].decode(errors='replace')}")
    return items


def collect(tok):
    repos = [r for r in get_all(f"{API}/users/{USER}/repos?type=owner&per_page=100", tok)
             if not r["fork"] and not r["private"]]
    stamps = []
    for repo in repos:
        if repo["stargazers_count"]:
            stars = get_all(f"{API}/repos/{repo['full_name']}/stargazers?per_page=100", tok,
                            "application/vnd.github.star+json")
            stamps.extend(dt.datetime.fromisoformat(s["starred_at"].replace("Z", "+00:00")).date() for s in stars)
    return len(repos), sum(r["stargazers_count"] for r in repos), sorted(stamps)


def nice_step(top):
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if top / step <= 5:
            return step
    return 10000


def render(theme, repo_count, stamps):
    c = THEMES[theme]
    total = len(stamps)
    start = dt.date(stamps[0].year, 1, 1)
    today = dt.date.today()
    # x-axis ends at the next month start: output only changes on new stars or monthly.
    end = dt.date(today.year + today.month // 12, today.month % 12 + 1, 1)
    step = nice_step(total)
    ymax = -(-total // step) * step
    pw, ph = W - L - R, H - T - B
    span = (end - start).days

    def x(d):
        return L + pw * (d - start).days / span

    def y(v):
        return T + ph * (1 - v / ymax)

    # Stars landing on the same pixel column merge into one step (keeps the SVG small).
    steps = {}
    for i, d in enumerate(stamps, 1):
        steps[round(x(d), 1)] = i
    line = f"M{x(start):.1f},{y(0):.1f}" + "".join(f"H{px:.1f}V{y(v):.1f}" for px, v in steps.items())
    last = (max(steps), y(total))
    line += f"H{x(end):.1f}"
    area = f"{line}V{y(0):.1f}H{x(start):.1f}Z"

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'role="img" aria-label="Total GitHub stars over time: {total}">',
           f"<title>Total GitHub stars across {repo_count} public repositories: {total}</title>",
           f'<g font-family="{FONT}">',
           f'<text x="{L}" y="34" font-size="18" font-weight="600" fill="{c["text"]}">Total GitHub stars</text>',
           f'<text x="{L}" y="56" font-size="13" fill="{c["muted"]}">Cumulative, across {repo_count} public '
           f'repositories owned by {escape(USER)}</text>',
           f'<text x="{W - R}" y="44" font-size="34" font-weight="600" text-anchor="end" fill="{c["text"]}">{total}</text>',
           f'<text x="{W - R}" y="64" font-size="12" text-anchor="end" fill="{c["muted"]}">stars</text>']
    for v in range(0, ymax + 1, step):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{c["grid"]}" stroke-width="1"/>')
        out.append(f'<text x="{L - 10}" y="{y(v) + 4:.1f}" font-size="12" text-anchor="end" fill="{c["muted"]}">{v}</text>')
    years = range(start.year, end.year + 1)
    every = 1 if len(years) <= 9 else 2
    for yr in years[::every]:
        px = x(dt.date(yr, 1, 1))
        out.append(f'<text x="{px:.1f}" y="{H - B + 22}" font-size="12" text-anchor="middle" fill="{c["muted"]}">{yr}</text>')
    out += [f'<path d="{area}" fill="{c["line"]}" fill-opacity=".12" stroke="none"/>',
            f'<path d="{line}" fill="none" stroke="{c["line"]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>',
            f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="5" fill="{c["line"]}" stroke="{c["ring"]}" stroke-width="2"/>',
            "</g></svg>"]
    return "\n".join(out) + "\n"


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    repo_count, api_total, stamps = collect(token())
    if not stamps:
        sys.exit("no stargazers returned")
    if api_total != len(stamps):
        log.warning("stargazers_count sum %d != listed %d", api_total, len(stamps))
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"stars-total-{theme}.svg").write_text(render(theme, repo_count, stamps), encoding="utf-8")
    log.info("repos=%d stars=%d api_sum=%d", repo_count, len(stamps), api_total)


if __name__ == "__main__":
    main()
