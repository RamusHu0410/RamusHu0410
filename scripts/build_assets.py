"""Generate the profile README artwork in assets/.

GitHub renders README images as <img>, which cannot load web fonts, so every
piece of text is converted to font outlines here. Each image is written in a
light and a dark version; README.md picks one with <picture> based on the
viewer's GitHub theme.

    pip3 install fonttools uharfbuzz
    python3 scripts/build_assets.py            # animated (what GitHub shows)
    STATIC=1 python3 scripts/build_assets.py   # no animation, for previews

Portrait: assets/portrait.json holds pen strokes traced from the portfolio's
line-art portrait by scripts/trace_portrait.py. The hero redraws them stroke by
stroke, then music notes drift up off the piano.

Signature: sign in scripts/signature-pad.html, save the download as
assets/signature.json, and rebuild. Until that file exists, a script-font
placeholder is used.
"""

import json
import math
import os
import random
import subprocess
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
SIGNATURE = OUT / "signature.json"
PORTRAIT = OUT / "portrait.json"
STATIC = os.environ.get("STATIC") == "1"
# How much of the piano to draw: "full", "simple" (outline only), or "none".
PIANO = os.environ.get("PIANO", "full")
PIANO_MIN_LENGTH = 130  # px in portrait.json; shorter piano strokes are dropped in "simple"

FONT_DIR = Path.home() / ".cache" / "ramus-readme-fonts"
GF = "https://github.com/google/fonts/raw/main/ofl/"
FONTS = {
    "serif": ("SourceSerif4.ttf", GF + "sourceserif4/SourceSerif4%5Bopsz,wght%5D.ttf"),
    "italic": ("SourceSerif4-Italic.ttf", GF + "sourceserif4/SourceSerif4-Italic%5Bopsz,wght%5D.ttf"),
    "mono": ("JetBrainsMono.ttf", GF + "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"),
    "script": ("HerrVonMuellerhoff.ttf", GF + "herrvonmuellerhoff/HerrVonMuellerhoff-Regular.ttf"),
}

# Black, white and a soft butter yellow, kept quiet so nothing shouts.
# Buttons use the same paper as the cards; the yellow appears only as a
# highlighter, the short rule and the icon dot on the main buttons.
# Dark cards use GitHub's own dark surface (#161b22) so they sit flush on
# the page instead of floating as a separate black slab.
#   line   - the portrait, signature and small rules
#   pencil - the piano, drawn lighter so the person stands out
#   mark   - highlighter behind accent words; mark_fg is the text on it
#   note2  - second colour for the floating notes
LIGHT = dict(
    name="light",
    card="#faf7ec", card_edge="#e8e1cd", staff="#ede6d2",
    ink="#1b1b1a", soft="#45433d", muted="#7a766b",
    line="#1b1b1a", pencil="#aaa494", mark="#f8f0c8", mark_fg="#1b1b1a", note2="#9a937f",
    btn="#faf7ec", btn_edge="#e2dac4", btn_fg="#1b1b1a", btn_sub="#7a766b", btn_icon="#1b1b1a",
    dot="#f8f0c8", dot_icon="#1b1b1a",
)
DARK = dict(
    name="dark",
    card="#161b22", card_edge="#30363d", staff="#21262d",
    ink="#ecebe5", soft="#b9b8b0", muted="#8b8d91",
    line="#e9e7df", pencil="#5f646c", mark="#58513a", mark_fg="#f8f0d0", note2="#ebdfb0",
    btn="#161b22", btn_edge="#30363d", btn_fg="#ecebe5", btn_sub="#8b8d91", btn_icon="#ebdfb0",
    dot="#48432f", dot_icon="#f8f0d0",
)


# --------------------------------------------------------------------------- text

_FACES = {}


def _face(key):
    if key not in _FACES:
        FONT_DIR.mkdir(parents=True, exist_ok=True)
        filename, url = FONTS[key]
        path = FONT_DIR / filename
        if not path.exists():
            # curl uses the system trust store; python.org builds often lack one.
            subprocess.run(["curl", "-fsSL", "-o", str(path), url], check=True)
        _FACES[key] = hb.Face(hb.Blob.from_file_path(str(path)))
    return _FACES[key]


def _shape(s, font_key, size, wght, opsz, tracking):
    face = _face(font_key)
    font = hb.Font(face)
    axes = {"wght": wght}
    if font_key in ("serif", "italic"):
        axes["opsz"] = opsz or max(8, min(60, size))
    if font_key != "script":
        font.set_variations(axes)
    buf = hb.Buffer()
    buf.add_str(s)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True})
    scale = size / face.upem
    glyphs, cursor = [], 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        glyphs.append((info.codepoint, cursor + pos.x_offset * scale, pos.y_offset * scale))
        cursor += pos.x_advance * scale + tracking * size
    width = cursor - tracking * size if glyphs else 0.0
    return font, scale, glyphs, width


def measure(s, size, font="serif", wght=400, opsz=None, tracking=0.0):
    return _shape(s, font, size, wght, opsz, tracking)[3]


def outline(s, x, y, size, font="serif", wght=400, opsz=None, tracking=0.0, anchor="start"):
    """SVG path data for `s` with its baseline at y."""
    hbfont, scale, glyphs, width = _shape(s, font, size, wght, opsz, tracking)
    start = x - {"start": 0, "middle": width / 2, "end": width}[anchor]
    pen = SVGPathPen(None, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    for gid, gx, gy in glyphs:
        rec = RecordingPen()
        hbfont.draw_glyph_with_pen(gid, rec)
        rec.replay(TransformPen(pen, (scale, 0, 0, -scale, start + gx, y - gy)))
    return pen.getCommands()


def text(s, x, y, size, fill, cls="", **kw):
    c = f' class="{cls}"' if cls else ""
    return f'<path{c} fill="{fill}" d="{outline(s, x, y, size, **kw)}"/>'


def runs(parts, x, y, size, anchor="start", cls="", **kw):
    """Several pieces of text on one line: parts = [(str, fill) or (str, fill, mark), ...].
    A mark colour draws a highlighter stroke behind that piece."""
    total = sum(measure(p[0], size, **kw) for p in parts)
    cx = x - {"start": 0, "middle": total / 2, "end": total}[anchor]
    out = []
    for p, fill, *mark in parts:
        w = measure(p, size, **kw)
        if mark:
            # Slightly tilted, uneven ends, like a real marker pass.
            x0, x1 = cx + 0.02 * size, cx + w + 0.08 * size
            top, bot = y - 0.62 * size, y + 0.2 * size
            out.append(f'<path class="mark" fill="{mark[0]}" d="M{x0:.1f},{top + 2:.1f} L{x1:.1f},{top:.1f} '
                       f'L{x1 - 2:.1f},{bot - 1:.1f} L{x0 + 1:.1f},{bot + 1:.1f} Z"/>')
        out.append(f'<path fill="{fill}" d="{outline(p, cx, y, size, **kw)}"/>')
        cx += w
    c = f' class="{cls}"' if cls else ""
    return f"<g{c}>{''.join(out)}</g>"


# ------------------------------------------------------------------ svg wrapper

ANIM_CSS = """
@keyframes up { from { opacity: 0; transform: translateY(7px); } }
@keyframes grow { from { transform: scaleX(0); } }
@keyframes draw { from { stroke-dashoffset: 1; } }
@keyframes ink { from { fill-opacity: 0; } }
@keyframes float {
  0% { opacity: 0; transform: translate(0, 0) rotate(0deg) scale(.7); }
  18% { opacity: .95; }
  70% { opacity: .8; }
  100% { opacity: 0; transform: translate(var(--dx), -78px) rotate(var(--r)) scale(1); }
}
.up { animation: up .8s cubic-bezier(.2,.7,.2,1) both; }
.grow { transform-box: fill-box; transform-origin: left center; animation: grow .9s cubic-bezier(.6,0,.2,1) 1s both; }
.mark { transform-box: fill-box; transform-origin: left center; animation: grow .55s cubic-bezier(.5,0,.3,1) 1.1s both; }
.draw { animation: draw var(--t) cubic-bezier(.45,.05,.4,1) var(--d) both; }
.ink { animation: ink .9s ease var(--d) both; }
.note { opacity: 0; transform-box: fill-box; transform-origin: center; animation: float var(--t) ease-out var(--d) infinite; }
.a1 { animation-delay: .05s; } .a2 { animation-delay: .2s; } .a3 { animation-delay: .35s; }
.a4 { animation-delay: .5s; } .a5 { animation-delay: .65s; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; } .note { opacity: .7; } }
"""


def svg(w, h, body, label, animated=True):
    style = f"<style>{ANIM_CSS}</style>\n" if animated and not STATIC else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{label}">\n<title>{label}</title>\n{style}{body}\n</svg>\n')


def card(W, H, t, staves=(), fade_left=0.35):
    """Rounded warm-white card ruled like manuscript paper: five-line staves at
    the given y positions, fading in from the left so text stays clean."""
    lines = "".join(f'<path d="M0,{y + i * 8} H{W}"/>' for y in staves for i in range(5))
    return f"""
<defs>
  <linearGradient id="staffFade" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">
    <stop offset="0" stop-color="{t['staff']}" stop-opacity="{fade_left}"/>
    <stop offset="0.55" stop-color="{t['staff']}"/>
    <stop offset="1" stop-color="{t['staff']}"/></linearGradient>
  <clipPath id="cardClip"><rect width="{W}" height="{H}" rx="14"/></clipPath>
</defs>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="{t['card']}" stroke="{t['card_edge']}"/>
<g clip-path="url(#cardClip)" stroke="url(#staffFade)" stroke-width="1" fill="none">{lines}</g>"""


# -------------------------------------------------------------------- signature

def _smooth(points):
    """Quadratic curve through the midpoints of a polyline."""
    if len(points) == 1:
        x, y = points[0]
        return f"M{x:.1f},{y:.1f} l0.01,0"
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for (x0, y0), (x1, y1) in zip(points[1:-1], points[2:]):
        d += f" Q{x0:.1f},{y0:.1f} {(x0 + x1) / 2:.1f},{(y0 + y1) / 2:.1f}"
    d += f" L{points[-1][0]:.1f},{points[-1][1]:.1f}"
    return d


def signature(t, box, start=0.9):
    """Signature that writes itself inside box = (x, y, w, h)."""
    bx, by, bw, bh = box
    if SIGNATURE.exists():
        data = json.loads(SIGNATURE.read_text())
        strokes = [s["points"] for s in data["strokes"] if s["points"]]
        xs = [p[0] for s in strokes for p in s]
        ys = [p[1] for s in strokes for p in s]
        sw, sh = max(xs) - min(xs) or 1, max(ys) - min(ys) or 1
        k = min(bw / sw, bh / sh)
        ox = bx + (bw - sw * k) / 2 - min(xs) * k
        oy = by + (bh - sh * k) / 2 - min(ys) * k
        out, clock = [], start
        for s in strokes:
            pts = [(ox + p[0] * k, oy + p[1] * k) for p in s]
            length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            recorded = (s[-1][2] - s[0][2]) / 1000 if len(s[0]) > 2 else 0
            dur = max(0.12, min(1.6, recorded or length / 420))
            out.append(f'<path class="draw" style="--t:{dur:.2f}s;--d:{clock:.2f}s" pathLength="1" '
                       f'stroke-dasharray="1" d="{_smooth(pts)}"/>')
            clock += dur + 0.08
        width = max(1.6, min(8.0, data.get("strokeWidth", 9) * k))
        return (f'<g fill="none" stroke="{t["line"]}" stroke-width="{width:.1f}" '
                f'stroke-linecap="round" stroke-linejoin="round">{"".join(out)}</g>')

    # Placeholder: a script-font "Ramus" that is traced, then inked in.
    size = 150
    w = measure("Ramus", size, font="script")
    size *= min(bw / w, bh / (size * 0.75))
    d = outline("Ramus", bx + bw / 2, by + bh * 0.72, size, font="script", anchor="middle")
    # Dash patterns restart on every subpath, so trace each contour as its own
    # path, left to right, then fill the whole word.
    subpaths = ["M" + p for p in d.split("M") if p.strip()]
    first_x = lambda p: float(p[1:].replace(" ", ",").split(",")[0])
    subpaths.sort(key=first_x)
    x_min, x_max = first_x(subpaths[0]), first_x(subpaths[-1])
    traces = "".join(
        f'<path class="draw" style="--t:1.1s;--d:{start + 1.6 * (first_x(p) - x_min) / ((x_max - x_min) or 1):.2f}s" '
        f'pathLength="1" stroke-dasharray="1" d="{p}"/>' for p in subpaths)
    return (f'<path class="ink" style="--d:{start + 2.4:.2f}s" fill="{t["line"]}" d="{d}"/>'
            f'<g fill="none" stroke="{t["line"]}" stroke-width="0.9">{traces}</g>')


# --------------------------------------------------------------------- portrait

def portrait(t, box, start=0.5):
    """The traced portrait, redrawn one stroke at a time inside box = (x, y, w, h).

    Differences from the site's version: the person is drawn in ink and the
    piano in a lighter pencil tone, the floor and piano leg are cropped away,
    and notes float up off the music desk once the drawing is done.
    Returns (svg, seconds until the drawing finishes, point transform).
    """
    data = json.loads(PORTRAIT.read_text())
    stroke_len = lambda s: sum(math.dist(a, b) for a, b in zip(s["points"], s["points"][1:]))
    keep = lambda s: (s["part"] != "piano" or PIANO == "full"
                      or (PIANO == "simple" and stroke_len(s) >= PIANO_MIN_LENGTH))
    data["strokes"] = [s for s in data["strokes"] if keep(s)]
    # Fit what is left, not the original canvas, so the person stays centered
    # when the piano is trimmed.
    xs = [p[0] for s in data["strokes"] for p in s["points"]]
    ys = [p[1] for s in data["strokes"] for p in s["points"]]
    x0, y0 = min(xs), min(ys)
    sw, sh = max(xs) - x0, max(ys) - y0
    bx, by, bw, bh = box
    k = min(bw / sw, bh / sh)
    ox, oy = bx + (bw - sw * k) / 2 - x0 * k, by + (bh - sh * k) / 2 - y0 * k
    to = lambda x, y: (ox + x * k, oy + y * k)

    budget = {"face": 2.4, "body": 1.7, "piano": 2.5}   # seconds per part
    style = {"face": (t["line"], 2.3), "body": (t["line"], 2.0), "piano": (t["pencil"], 1.6)}
    clock, groups = start, []
    for part in ("face", "body", "piano"):
        strokes = [s for s in data["strokes"] if s["part"] == part]
        if not strokes:
            continue
        lengths = [stroke_len(s) for s in strokes]
        total = sum(lengths) or 1
        done, out = 0.0, []
        for st, ln in zip(strokes, lengths):
            d0 = clock + budget[part] * done / total
            dur = max(0.12, budget[part] * ln / total * 1.8)   # x1.8 so neighbours overlap a little
            pts = [to(x, y) for x, y in st["points"]]
            out.append(f'<path class="draw" style="--t:{dur:.2f}s;--d:{d0:.2f}s" pathLength="1" '
                       f'stroke-dasharray="1" d="{_smooth(pts)}"/>')
            done += ln
        color, width = style[part]
        groups.append(f'<g stroke="{color}" stroke-width="{width}">{"".join(out)}</g>')
        clock += budget[part]
    body = f'<g fill="none" stroke-linecap="round" stroke-linejoin="round">{"".join(groups)}</g>'
    return body, clock, to


NOTE_SHAPES = {
    "eighth": '<ellipse cx="0" cy="0" rx="4.6" ry="3.3" transform="rotate(-22)"/>'
              '<path d="M3.9,-1.2 V-18" stroke-width="1.5" fill="none"/>'
              '<path d="M3.9,-18 q6,3 6.4,10 q-1.4,-5 -6.4,-6.2 Z" stroke="none"/>',
    "quarter": '<ellipse cx="0" cy="0" rx="4.6" ry="3.3" transform="rotate(-22)"/>'
               '<path d="M3.9,-1.2 V-17" stroke-width="1.5" fill="none"/>',
    "pair": '<ellipse cx="0" cy="0" rx="4.4" ry="3.1" transform="rotate(-22)"/>'
            '<ellipse cx="13" cy="-3" rx="4.4" ry="3.1" transform="rotate(-22 13 -3)"/>'
            '<path d="M3.7,-1.2 V-18 M16.7,-4.2 V-21" stroke-width="1.5" fill="none"/>'
            '<path d="M3,-19.6 L17.4,-22.6 V-19.4 L3,-16.4 Z" stroke="none"/>',
}


def notes(t, spots, start):
    """Notes that drift up and fade, on a loop, from the given (x, y) spots."""
    rnd = random.Random(21)
    kinds = ["eighth", "pair", "quarter"]
    out = []
    for i, (x, y) in enumerate(spots):
        kind = kinds[i % len(kinds)]
        color = t["note2"] if i % 3 == 1 else t["line"]
        scale = rnd.uniform(0.85, 1.15)
        if STATIC:  # one frozen mid-flight frame
            out.append(f'<g transform="translate({x:.0f},{y - 22 - (i * 13) % 36:.0f}) scale({scale:.2f})" '
                       f'fill="{color}" stroke="{color}" opacity="0.75">{NOTE_SHAPES[kind]}</g>')
            continue
        st = (f"--t:{rnd.uniform(4.2, 5.6):.1f}s;--d:{start + i * 0.85:.2f}s;"
              f"--dx:{rnd.uniform(-22, 26):.0f}px;--r:{rnd.uniform(-18, 18):.0f}deg")
        out.append(f'<g transform="translate({x:.0f},{y:.0f}) scale({scale:.2f})">'
                   f'<g class="note" style="{st}" fill="{color}" stroke="{color}">{NOTE_SHAPES[kind]}</g></g>')
    return "".join(out)


# ------------------------------------------------------------------------ icons

ICONS = {
    "note": '<path d="M-3.5,5.5 V-6 L6,-8 V3.5"/><circle cx="-5.8" cy="5.6" r="2.3"/><circle cx="3.7" cy="3.6" r="2.3"/><path d="M-3.5,-2.6 L6,-4.6"/>',
    "flask": '<path d="M-3,-8 H3 M-2,-8 V-2.5 L-7,6.5 Q-7.5,8 -6,8 H6 Q7.5,8 7,6.5 L2,-2.5 V-8"/><path d="M-4.6,2.5 H4.6"/>',
    "mail": '<rect x="-8" y="-5.5" width="16" height="11" rx="1.6"/><path d="M-7.5,-4.6 L0,1.2 L7.5,-4.6"/>',
    "linkedin": '<rect x="-7.5" y="-7.5" width="15" height="15" rx="2.4"/><path d="M-4,-1 V4.5 M-4,-4 V-3.6 M-0.8,4.5 V-1 M-0.8,1.4 Q-0.8,-1.2 1.8,-1.2 Q4,-1.2 4,1.4 V4.5"/>',
    "instagram": '<rect x="-7.5" y="-7.5" width="15" height="15" rx="4.2"/><circle cx="0" cy="0" r="3.4"/><circle cx="4.4" cy="-4.4" r="0.4"/>',
}


def icon(name, cx, cy, color):
    return (f'<g transform="translate({cx},{cy})" fill="none" stroke="{color}" stroke-width="1.4" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')


# ----------------------------------------------------------------------- pieces

def hero(t):
    W, H = 1000, 360
    x = 64
    drawing, done, to = portrait(t, (600, 44, 330, 276))
    # Where notes rise from, in portrait.json coordinates: the piano's music
    # desk, or just beside the head when the piano isn't drawn.
    desk = ([(480, 340), (510, 270), (540, 370), (490, 230), (530, 310)] if PIANO == "none"
            else [(720, 360), (840, 346), (950, 350), (780, 355), (900, 348)])
    body = card(W, H, t, staves=(30, 318)) + f"""
{text("PIANIST  ·  FULL-STACK DEVELOPER", x, 112, 12, t["muted"], cls="up a1", font="mono", tracking=0.24)}
{text("Ramus Hu", x - 3, 196, 80, t["ink"], cls="up a2", wght=700, opsz=60, tracking=-0.005)}
{runs([("Exploring where ", t["soft"]), ("music", t["mark_fg"], t["mark"]), (" meets code.", t["soft"])],
      x, 242, 24, cls="up a3", font="italic", wght=420)}
<rect class="grow" x="{x}" y="267" width="44" height="3" rx="1.5" fill="{t["mark"]}"/>
{text("ramushu.vercel.app", x, 304, 12.5, t["muted"], cls="up a5", font="mono")}
{drawing}
{notes(t, [to(*p) for p in desk], start=done - 0.4)}"""
    return svg(W, H, body, "Ramus Hu at the piano, sketching itself. Exploring where music meets code.")


def connect(t):
    W, H = 1000, 220
    cx = W / 2
    body = card(W, H, t, staves=(26,), fade_left=1) + f"""
{text("CONNECT", cx, 96, 12, t["muted"], cls="up a1", font="mono", tracking=0.3, anchor="middle")}
{text("Ramus is looking forward to answering your inquiries", cx, 140, 29, t["ink"], cls="up a2", wght=620, opsz=36, anchor="middle")}
{runs([("There is no ", t["soft"]), ("stupid", t["mark_fg"], t["mark"]), (" question.", t["soft"])],
      cx, 184, 20, anchor="middle", cls="up a4", font="italic", wght=420)}
{signature(t, (856, 162, 112, 44))}"""
    return svg(W, H, body, "Connect. There is no stupid question. Signed, Ramus.")


def divider(t):
    W, H = 1000, 28
    cx, cy = W / 2, 16
    span = cx - 140
    note = (f'<g transform="translate({cx - 2},{cy + 4}) scale(0.7)" fill="{t["line"]}" stroke="{t["line"]}">'
            f'{NOTE_SHAPES["eighth"]}</g>')
    body = f"""
<defs><linearGradient id="fade" x1="0" x2="1">
  <stop offset="0" stop-color="{t['pencil']}" stop-opacity="0"/>
  <stop offset="1" stop-color="{t['pencil']}"/></linearGradient></defs>
<rect x="120" y="{cy}" width="{span}" height="1" fill="url(#fade)"/>
<rect x="{cx + 20}" y="{cy}" width="{span}" height="1" fill="url(#fade)" transform="rotate(180 {cx + 20 + span / 2} {cy + 0.5})"/>
{note}"""
    return svg(W, H, body, "Section break", animated=False)


def button(t, label, sub, ico, *, primary=False, w=300, h=64):
    """Paper button matching the cards. The main buttons get a soft yellow
    icon dot instead of a loud filled background."""
    x0, y0, bw, bh = 1, 1, w - 2, h - 4
    icx, icy = x0 + 30, y0 + bh / 2
    if primary:
        ring = f'<circle cx="{icx}" cy="{icy}" r="17" fill="{t["dot"]}"/>'
        ic = t["dot_icon"]
    else:
        ring = f'<circle cx="{icx}" cy="{icy}" r="17" fill="none" stroke="{t["btn_edge"]}"/>'
        ic = t["btn_icon"]
    body = f"""
<rect x="{x0}" y="{y0 + 2}" width="{bw}" height="{bh}" rx="12" fill="{t["btn_edge"]}" fill-opacity="0.7"/>
<rect x="{x0 + 0.5}" y="{y0 + 0.5}" width="{bw - 1}" height="{bh - 1}" rx="11.5" fill="{t["btn"]}" stroke="{t["btn_edge"]}"/>
{ring}{icon(ico, icx, icy, ic)}
{text(label, x0 + 60, icy - 1, 18, t["btn_fg"], wght=600, opsz=20)}
{text(sub.upper(), x0 + 60, icy + 15.5, 10.5, t["btn_sub"], wght=500, opsz=10, tracking=0.12)}
<path d="M{x0 + bw - 34},{icy} h12 m-4.5,-4.5 l4.5,4.5 l-4.5,4.5" fill="none" stroke="{t["btn_sub"]}"
      stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>"""
    return svg(w, h, body, f"{label} - {sub}", animated=False)


def main():
    OUT.mkdir(exist_ok=True)
    for t in (LIGHT, DARK):
        suffix = "" if t is LIGHT else "-dark"
        files = {
            "hero": hero(t),
            "divider": divider(t),
            "connect": connect(t),
            "btn-stem": button(t, "Hackathon team Leader", "Full-stack developer", "flask", primary=True, w=320),
            "btn-music": button(t, "The Accompanist", "ARCT performer", "note", w=270),
            "btn-email": button(t, "Email", "ramushu0410@gmail.com", "mail", primary=True, w=300),
            "btn-linkedin": button(t, "LinkedIn", "in/ramushu", "linkedin", w=220),
            "btn-instagram": button(t, "Instagram", "@ramushu0410", "instagram", w=230),
        }
        for name, content in files.items():
            (OUT / f"{name}{suffix}.svg").write_text(content)
            print(f"wrote assets/{name}{suffix}.svg  ({len(content) // 1024} KB)")
    print("signature:", "assets/signature.json" if SIGNATURE.exists() else "placeholder (no assets/signature.json)")


if __name__ == "__main__":
    main()
