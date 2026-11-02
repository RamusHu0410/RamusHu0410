"""Turn the portfolio's line-art portrait into pen strokes the README can animate.

The portrait PNG (made by portfo/scripts/sketch.py) is thick black line art.
This thins it to one-pixel centerlines, walks those into polylines, simplifies
them, and saves them in drawing order to assets/portrait.json. build_assets.py
then draws them one after another, so the picture sketches itself.

    pip3 install scikit-image pillow
    python3 scripts/trace_portrait.py ~/dev/portfo/public/portrait.png
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_closing, binary_opening
from skimage.morphology import remove_small_objects, skeletonize

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "portrait.json"

# The whole source drawing, uncropped, so nothing of the original is lost.
CROP = (0, 0, 1100, 957)
MIN_LENGTH = 4        # px; only single-pixel specks are dropped, so short hair strokes survive
RDP_EPSILON = 1.4     # px; simplification tolerance

NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def load_mask(path):
    im = Image.open(path).convert("LA")
    alpha = np.asarray(im)[..., 1] > 110
    x0, y0, x1, y1 = CROP
    mask = alpha[y0:y1, x0:x1]
    mask = binary_closing(mask, iterations=1)
    mask = binary_opening(mask, iterations=1)
    return remove_small_objects(mask, max_size=8)


def walk(skel):
    """Split a skeleton into polylines that end at line ends or junctions."""
    h, w = skel.shape
    pix = set(zip(*np.nonzero(skel)))
    nbrs = lambda p: [(p[0] + dy, p[1] + dx) for dy, dx in NEIGHBORS if (p[0] + dy, p[1] + dx) in pix]
    degree = {p: len(nbrs(p)) for p in pix}
    nodes = {p for p, d in degree.items() if d != 2}
    seen_edges, lines = set(), []

    def trace(start, nxt):
        line, prev, cur = [start], start, nxt
        while True:
            edge = frozenset((prev, cur))
            if edge in seen_edges:
                return line if len(line) > 1 else None
            seen_edges.add(edge)
            line.append(cur)
            if cur in nodes:
                return line
            options = [n for n in nbrs(cur) if n != prev and frozenset((cur, n)) not in seen_edges]
            if not options:
                return line
            # Prefer orthogonal steps so diagonal shortcuts don't fork the line.
            options.sort(key=lambda n: abs(n[0] - cur[0]) + abs(n[1] - cur[1]))
            prev, cur = cur, options[0]

    for node in nodes:
        for n in nbrs(node):
            if frozenset((node, n)) not in seen_edges:
                line = trace(node, n)
                if line:
                    lines.append(line)
    # Closed loops have no nodes at all.
    for p in pix:
        for n in nbrs(p):
            if frozenset((p, n)) not in seen_edges:
                line = trace(p, n)
                if line:
                    lines.append(line)
    return [[(x, y) for y, x in line] for line in lines]


def rdp(points, eps):
    if len(points) < 3:
        return points
    (x0, y0), (x1, y1) = points[0], points[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = math.hypot(dx, dy) or 1.0
    dists = [abs(dy * (x - x0) - dx * (y - y0)) / norm for x, y in points[1:-1]]
    i = max(range(len(dists)), key=dists.__getitem__)
    if dists[i] <= eps:
        return [points[0], points[-1]]
    return rdp(points[: i + 2], eps)[:-1] + rdp(points[i + 1:], eps)


def length(line):
    return sum(math.dist(a, b) for a, b in zip(line, line[1:]))


def join(lines, gap=3.5):
    """Glue lines whose ends touch, so the pen draws longer, calmer strokes."""
    lines = [list(l) for l in lines]
    merged = True
    while merged:
        merged = False
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                a, b = lines[i], lines[j]
                for ra, rb in ((False, False), (False, True), (True, False), (True, True)):
                    aa = a[::-1] if ra else a
                    bb = b[::-1] if rb else b
                    if math.dist(aa[-1], bb[0]) <= gap:
                        lines[i] = aa + bb[1:]
                        del lines[j]
                        merged = True
                        break
                if merged:
                    break
            if merged:
                break
    return lines


def part_of(line):
    """'face' for the person, 'piano' for the instrument."""
    xs = [p[0] for p in line]
    ys = [p[1] for p in line]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    if cy < 360 and cx < 380:
        return "face"
    if cx < 440 and cy < 710:
        return "body"
    return "piano"


# The piano's long front bar that crosses in front of the arm. Its two edges
# sit inside the "body" area, so part_of() alone would draw them as the person.
PIANO_BAR = [(270, 546), (490, 597), (490, 620), (270, 600)]


def _in_bar(p):
    """Point-in-polygon test (ray casting) against PIANO_BAR."""
    x, y, inside = p[0], p[1], False
    poly = PIANO_BAR
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def split_bar(line):
    """Return [(part, points), ...]: a body stroke that runs along the bar is
    cut there, so the bar piece is piano and the rest stays the arm."""
    part = part_of(line)
    if part != "body":
        return [(part, line)]
    flags = [_in_bar(p) for p in line]
    if sum(flags) >= 0.6 * len(line):
        return [("piano", line)]
    pieces, start = [], 0
    for i in range(1, len(line) + 1):
        if i == len(line) or flags[i] != flags[start]:
            seg = line[start:i]
            if flags[start] and len(seg) >= 3 and length(seg) >= 30:
                pieces.append(("piano", seg))
            else:
                pieces.append(("body", seg))
            start = i
    # Re-share the joint point so the cut leaves no gap.
    out = []
    for k, (prt, seg) in enumerate(pieces):
        if k and out and out[-1][0] == prt:
            out[-1] = (prt, out[-1][1] + seg)
        else:
            if k:
                seg = [pieces[k - 1][1][-1]] + seg
            out.append((prt, seg))
    return [(prt, seg) for prt, seg in out if len(seg) >= 2]


# Lines the source drawing never had: the back of the head between the crown
# and the ear, and the small gap at the crown. They are added on top; no traced
# stroke is changed. Control points are in source-PNG pixels and are smoothed
# into a curve that starts and ends on the existing line ends.
ADDED_STROKES = [
    [(141, 227), (139, 206), (144, 184), (156, 162), (174, 143), (198, 130), (222, 124), (232, 124)],
    [(236, 124), (244, 124.5), (251, 126)],
]


def curve(ctrl, step=4.0):
    """Dense points along a Catmull-Rom spline through ctrl."""
    pts = [ctrl[0]] + list(ctrl) + [ctrl[-1]]
    out = [ctrl[0]]
    for p0, p1, p2, p3 in zip(pts, pts[1:], pts[2:], pts[3:]):
        n = max(2, int(math.dist(p1, p2) / step))
        for k in range(1, n + 1):
            u = k / n
            out.append(tuple(0.5 * ((2 * p1[i]) + (-p0[i] + p2[i]) * u
                                    + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * u * u
                                    + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * u ** 3) for i in (0, 1)))
    return out


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "dev/portfo/public/portrait.png")
    mask = load_mask(src)
    lines = walk(skeletonize(mask))
    lines = [l for l in join(lines) if length(l) >= MIN_LENGTH]
    lines = [rdp(l, RDP_EPSILON) for l in lines]
    items = [piece for l in lines for piece in split_bar(l)]
    # Source-PNG pixels -> cropped coordinates, then add the new head lines.
    cx0, cy0 = CROP[0], CROP[1]
    items += [("face", [(x - cx0, y - cy0) for x, y in curve(c)]) for c in ADDED_STROKES]

    # Draw order: face top-down, then body, then piano left to right.
    order = {"face": 0, "body": 1, "piano": 2}

    def key(item):
        part, line = item
        x, y = min(line, key=lambda p: (p[1], p[0]))
        return (order[part], y if part != "piano" else x)

    items.sort(key=key)
    # Start each stroke from its upper/left end, like a hand would.
    items = [(p, l if (l[0][1], l[0][0]) <= (l[-1][1], l[-1][0]) else l[::-1]) for p, l in items]

    h, w = mask.shape
    data = {
        "size": [int(w), int(h)],
        "strokes": [{"part": p, "points": [[round(float(x), 1), round(float(y), 1)] for x, y in l]} for p, l in items],
    }
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    counts = {p: sum(s["part"] == p for s in data["strokes"]) for p in order}
    print(f"wrote {OUT.relative_to(ROOT)}: {len(items)} strokes {counts}, "
          f"{sum(length(l) for _, l in items):.0f}px of line, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
