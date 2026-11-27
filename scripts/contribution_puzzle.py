"""Contribution jigsaw: an animated SVG where the squares of a GitHub
contribution graph fly in from all over and snap into place, column by column,
hold as a finished picture, then scatter and start again.

Usage:
    python scripts/contribution_puzzle.py <github-user> <out-dir>
    python scripts/contribution_puzzle.py <github-user> <out-dir> --html saved.html

Writes contribution-puzzle.svg (light) and contribution-puzzle-dark.svg.
Data comes from the GraphQL API when GITHUB_TOKEN is set (as in GitHub
Actions), otherwise from the public contributions page. Standard library only.
"""
import json
import os
import random
import re
import sys
import urllib.request
from datetime import date

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

THEMES = {
    "light": dict(empty="#ebedf0", slot="#d0d7de", text="#1f2328", muted="#59636e",
                  levels=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"], accent="#0969da"),
    "dark": dict(empty="#161b22", slot="#30363d", text="#f0f6fc", muted="#8b949e",
                 levels=["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"], accent="#4493f8"),
}

CYCLE = 14.0          # seconds for one full assemble / hold / scatter loop
CELL, GAP = 12, 3     # square size and spacing, like GitHub's graph
LEFT, TOP = 36, 52    # board origin inside the SVG


# ------------------------------------------------------------------ data
def fetch_graphql(user, token):
    query = """query($login: String!) { user(login: $login) { contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays {
        date contributionCount contributionLevel weekday } } } } } }"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        cal = json.load(resp)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = []
    for col, week in enumerate(cal["weeks"]):
        for d in week["contributionDays"]:
            days.append((col, d["weekday"], LEVELS[d["contributionLevel"]], d["contributionCount"]))
    return days, cal["totalContributions"]


def parse_html(html):
    """Read the public https://github.com/users/<user>/contributions page."""
    counts = {}
    for cell_id, text in re.findall(r'for="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)</tool-tip>', html):
        m = re.match(r"(\d[\d,]*) contribution", text)
        counts[cell_id] = int(m.group(1).replace(",", "")) if m else 0
    days = []
    for td in re.findall(r"<td[^>]*ContributionCalendar-day[^>]*>", html):
        cid = re.search(r'id="(contribution-day-component-(\d+)-(\d+))"', td)
        level = re.search(r'data-level="(\d)"', td)
        if cid and level:
            days.append((int(cid.group(3)), int(cid.group(2)), int(level.group(1)), counts.get(cid.group(1), 0)))
    return days, sum(d[3] for d in days)


def fetch_html(user):
    req = urllib.request.Request(f"https://github.com/users/{user}/contributions",
                                 headers={"User-Agent": "contribution-puzzle"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


# ---------------------------------------------------------------- render
def render(days, total, theme, seed):
    T = THEMES[theme]
    rng = random.Random(seed)
    cols = max(d[0] for d in days) + 1
    width = LEFT * 2 + cols * (CELL + GAP) - GAP
    height = TOP + 7 * (CELL + GAP) + 40
    active = [d for d in days if d[2] > 0]

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
             f'font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">']

    # Title and a progress bar that fills while the pieces land.
    parts.append(f'<text x="{LEFT}" y="24" font-size="14" font-weight="600" fill="{T["text"]}">🧩 Contribution jigsaw</text>')
    parts.append(f'<text x="{width - LEFT}" y="24" text-anchor="end" font-size="12" fill="{T["muted"]}">'
                 f'{total:,} contributions · {len(active)} pieces</text>')
    bar_w = width - 2 * LEFT
    parts.append(f'<rect x="{LEFT}" y="34" width="{bar_w}" height="3" rx="1.5" fill="{T["slot"]}" opacity="0.6"/>')
    parts.append(f'<rect x="{LEFT}" y="34" width="0" height="3" rx="1.5" fill="{T["accent"]}">'
                 f'<animate attributeName="width" dur="{CYCLE}s" repeatCount="indefinite" '
                 f'values="0;{bar_w};{bar_w};0;0" keyTimes="0;0.66;0.86;0.94;1"/></rect>')

    # The board: every day is an empty slot with a faint outline.
    for col, row, _, _ in days:
        x, y = LEFT + col * (CELL + GAP), TOP + row * (CELL + GAP)
        parts.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{T["empty"]}" '
                     f'stroke="{T["slot"]}" stroke-opacity="0.55" stroke-width="0.8"/>')

    # The pieces: days with contributions fly in left to right, hold, then scatter.
    for col, row, level, count in active:
        x, y = LEFT + col * (CELL + GAP), TOP + row * (CELL + GAP)
        land = 0.04 + 0.60 * (col / max(cols - 1, 1)) + rng.uniform(-0.02, 0.02)
        land = min(max(land, 0.03), 0.66)
        start = max(land - 0.06, 0.0)
        dx, dy = rng.randint(-260, 260), rng.choice([-1, 1]) * rng.randint(70, 160)
        ex, ey = rng.randint(-200, 200), rng.choice([-1, 1]) * rng.randint(80, 170)
        spin, espin = rng.randint(-180, 180), rng.randint(-180, 180)
        leave = 0.86 + rng.uniform(0, 0.04)
        gone = min(leave + 0.05, 0.99)
        kt = f"0;{start:.3f};{land:.3f};{leave:.3f};{gone:.3f};1"
        cx, cy = x + CELL / 2, y + CELL / 2
        parts.append(
            f'<g opacity="0"><title>{count} contribution{"s" if count != 1 else ""}</title>'
            f'<animate attributeName="opacity" dur="{CYCLE}s" repeatCount="indefinite" values="0;0;1;1;0;0" keyTimes="{kt}"/>'
            f'<animateTransform attributeName="transform" type="translate" dur="{CYCLE}s" repeatCount="indefinite" '
            f'values="{dx} {dy};{dx} {dy};0 0;0 0;{ex} {ey};{ex} {ey}" keyTimes="{kt}" '
            f'calcMode="spline" keySplines="0 0 1 1;.2 .8 .3 1;0 0 1 1;.6 0 .9 .4;0 0 1 1"/>'
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{T["levels"][level]}">'
            f'<animateTransform attributeName="transform" type="rotate" dur="{CYCLE}s" repeatCount="indefinite" '
            f'values="{spin} {cx} {cy};{spin} {cx} {cy};0 {cx} {cy};0 {cx} {cy};{espin} {cx} {cy};{espin} {cx} {cy}" keyTimes="{kt}"/>'
            f'</rect></g>'
        )

    # Legend, like GitHub's "Less ... More".
    ly = TOP + 7 * (CELL + GAP) + 22
    lx = width - LEFT - 5 * (CELL + 3) - 34
    parts.append(f'<text x="{lx - 8}" y="{ly + 10}" text-anchor="end" font-size="11" fill="{T["muted"]}">Less</text>')
    for i, c in enumerate(T["levels"]):
        parts.append(f'<rect x="{lx + i * (CELL + 3)}" y="{ly}" width="{CELL}" height="{CELL}" rx="2.5" fill="{c}" '
                     f'stroke="{T["slot"]}" stroke-opacity="0.55" stroke-width="0.8"/>')
    parts.append(f'<text x="{lx + 5 * (CELL + 3) + 4}" y="{ly + 10}" font-size="11" fill="{T["muted"]}">More</text>')
    parts.append(f'<text x="{LEFT}" y="{ly + 10}" font-size="11" fill="{T["muted"]}">Every green square is a piece.</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    user, out = sys.argv[1], sys.argv[2]
    if "--html" in sys.argv:
        with open(sys.argv[sys.argv.index("--html") + 1], encoding="utf-8") as f:
            days, total = parse_html(f.read())
    elif os.environ.get("GITHUB_TOKEN"):
        days, total = fetch_graphql(user, os.environ["GITHUB_TOKEN"])
    else:
        days, total = parse_html(fetch_html(user))
    if not days:
        sys.exit("No contribution data found.")
    os.makedirs(out, exist_ok=True)
    seed = date.today().isoformat()  # a new scramble every day
    for theme, name in [("light", "contribution-puzzle.svg"), ("dark", "contribution-puzzle-dark.svg")]:
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(render(days, total, theme, seed))
    print(f"{len(days)} days, {total} contributions -> {out}")


if __name__ == "__main__":
    main()
