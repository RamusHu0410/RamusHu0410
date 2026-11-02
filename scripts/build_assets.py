"""Generate the profile README artwork in assets/.

GitHub renders README images as <img>, which cannot load web fonts, so every
piece of text is converted to EB Garamond outlines here.

    pip3 install fonttools uharfbuzz
    python3 scripts/build_assets.py
"""

import random
import subprocess
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
FONT_DIR = Path.home() / ".cache" / "ramus-readme-fonts"
FONT_URLS = {
    "roman": "https://github.com/google/fonts/raw/main/ofl/ebgaramond/EBGaramond%5Bwght%5D.ttf",
    "italic": "https://github.com/google/fonts/raw/main/ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf",
}

# Palette taken from ramushu.vercel.app (default "brass" palette).
PARCHMENT = "#efe9d8"
PARCHMENT_DEEP = "#e5dbc1"
INK = "#33291f"
INK_SOFT = "#5c5145"
INK_FAINT = "#6f6454"
BRASS = "#6a5b35"
BRASS_DEEP = "#594d2c"
BRASS_SOFT = "#b5a785"
RULE = "#ded2b2"
RULE_STRONG = "#cec4a2"
UNDER_PAPER = "#cdc19c"
UNDER_BRASS = "#322b19"
CREAM = "#f6f1e3"


# --------------------------------------------------------------------------- text

def _font_blob(style):
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    path = FONT_DIR / f"EBGaramond-{style}.ttf"
    if not path.exists():
        # curl uses the system trust store; python.org builds often lack one.
        subprocess.run(["curl", "-fsSL", "-o", str(path), FONT_URLS[style]], check=True)
    return hb.Blob.from_file_path(str(path))


_FACES = {}


def _face(style):
    if style not in _FACES:
        _FACES[style] = hb.Face(_font_blob(style))
    return _FACES[style]


def text(s, x, y, size, *, fill=INK, wght=400, italic=False, tracking=0.0,
         anchor="start", opacity=None, cls=None):
    """Return an SVG <path> drawing `s` with its baseline at y.

    tracking is in em, like CSS letter-spacing.
    """
    face = _face("italic" if italic else "roman")
    font = hb.Font(face)
    font.set_variations({"wght": wght})
    buf = hb.Buffer()
    buf.add_str(s)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True})

    scale = size / face.upem
    track = tracking * size
    glyphs, cursor = [], 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        glyphs.append((info.codepoint, cursor + pos.x_offset * scale, pos.y_offset * scale))
        cursor += pos.x_advance * scale + track
    width = cursor - track if glyphs else 0.0

    start = x - {"start": 0, "middle": width / 2, "end": width}[anchor]
    svg_pen = SVGPathPen(None, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    for gid, gx, gy in glyphs:
        rec = RecordingPen()
        font.draw_glyph_with_pen(gid, rec)
        rec.replay(TransformPen(svg_pen, (scale, 0, 0, -scale, start + gx, y - gy)))

    attrs = f'fill="{fill}"'
    if opacity is not None:
        attrs += f' fill-opacity="{opacity}"'
    if cls:
        attrs += f' class="{cls}"'
    return f'<path {attrs} d="{svg_pen.getCommands()}"/>'


# ----------------------------------------------------------------------- shared

def defs_common():
    return f"""
  <filter id="grain" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7"/>
    <feColorMatrix values="0 0 0 0 0.36  0 0 0 0 0.29  0 0 0 0 0.18  0 0 0 0.10 0"/>
  </filter>
  <filter id="lift" x="-10%" y="-10%" width="120%" height="135%">
    <feDropShadow dx="0" dy="7" stdDeviation="9" flood-color="{INK}" flood-opacity="0.20"/>
    <feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="{INK}" flood-opacity="0.18"/>
  </filter>
  <linearGradient id="sheet" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#f8f5ec"/>
    <stop offset="1" stop-color="#efe9da"/>
  </linearGradient>"""


def deckle(x0, x1, y, depth, seed, step=(1.5, 7)):
    """Points for a torn/deckled horizontal edge, left to right."""
    rnd = random.Random(seed)
    pts, x, up, drift = [], x0, True, 0.0
    while x < x1:
        drift = max(-depth * 0.3, min(depth * 0.3, drift + rnd.uniform(-0.8, 0.8)))
        jag = rnd.uniform(0, depth * 0.3) if up else rnd.uniform(depth * 0.4, depth)
        pts.append((x, y + depth * 0.15 + jag + drift))
        up = not up if rnd.random() < 0.8 else up
        x += rnd.uniform(*step)
    pts.append((x1, y + depth * 0.4))
    return pts


def torn_sheet(x0, y0, x1, y1, seed=3):
    top = deckle(x0, x1, y0, 3, seed)
    bottom = deckle(x0, x1, y1 - 7, 9, seed + 1)
    d = f"M{x0},{y0 + 2} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in top)
    d += f" L{x1},{y1 - 6} "
    d += " ".join(f"L{x:.1f},{y:.1f}" for x, y in reversed(bottom))
    return d + " Z"


def ornament(cx, cy, color=BRASS_SOFT):
    """The little filigree that sits above the name on the site."""
    lens = lambda dx: (f'<path d="M{cx + dx - 17},{cy} Q{cx + dx},{cy - 9} {cx + dx + 17},{cy} '
                       f'Q{cx + dx},{cy + 9} {cx + dx - 17},{cy} Z"/>'
                       f'<path d="M{cx + dx - 10},{cy} Q{cx + dx},{cy - 4.5} {cx + dx + 10},{cy}"/>')
    return f"""<g fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round">
    {lens(-24)}{lens(24)}
    <path d="M{cx},{cy - 7} L{cx + 7},{cy} L{cx},{cy + 7} L{cx - 7},{cy} Z" fill="{CREAM}"/>
    <path d="M{cx},{cy - 2.5} L{cx + 2.5},{cy} L{cx},{cy + 2.5} L{cx - 2.5},{cy} Z" fill="{color}"/>
    <circle cx="{cx - 49}" cy="{cy}" r="1.8" fill="{color}" stroke="none"/>
    <circle cx="{cx + 49}" cy="{cy}" r="1.8" fill="{color}" stroke="none"/>
  </g>"""


def svg(w, h, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{label}">\n<title>{label}</title>\n'
            f"<defs>{defs_common()}</defs>\n{body}\n</svg>\n")


# ------------------------------------------------------------------------ icons

ICONS = {
    "note": '<path d="M-3.5,5.5 V-6 L6,-8 V3.5" /><circle cx="-5.8" cy="5.6" r="2.3"/><circle cx="3.7" cy="3.6" r="2.3"/><path d="M-3.5,-2.6 L6,-4.6"/>',
    "flask": '<path d="M-3,-8 H3 M-2,-8 V-2.5 L-7,6.5 Q-7.5,8 -6,8 H6 Q7.5,8 7,6.5 L2,-2.5 V-8"/><path d="M-4.6,2.5 H4.6"/>',
    "mail": '<rect x="-8" y="-5.5" width="16" height="11" rx="1.6"/><path d="M-7.5,-4.6 L0,1.2 L7.5,-4.6"/>',
    "linkedin": '<rect x="-7.5" y="-7.5" width="15" height="15" rx="2.4"/><path d="M-4,-1 V4.5 M-4,-4 V-3.6 M-0.8,4.5 V-1 M-0.8,1.4 Q-0.8,-1.2 1.8,-1.2 Q4,-1.2 4,1.4 V4.5"/>',
    "instagram": '<rect x="-7.5" y="-7.5" width="15" height="15" rx="4.2"/><circle cx="0" cy="0" r="3.4"/><circle cx="4.4" cy="-4.4" r="0.4"/>',
    "globe": '<circle cx="0" cy="0" r="7.5"/><ellipse cx="0" cy="0" rx="3.2" ry="7.5"/><path d="M-7.5,0 H7.5 M-6.4,-3.8 H6.4 M-6.4,3.8 H6.4"/>',
}


def icon(name, cx, cy, color, s=1.0):
    return (f'<g transform="translate({cx},{cy}) scale({s})" fill="none" stroke="{color}" '
            f'stroke-width="{1.35 / s:.2f}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')


def arrow(x, y, color):
    return (f'<path d="M{x - 6},{y} H{x + 6} M{x + 1.5},{y - 4.5} L{x + 6},{y} L{x + 1.5},{y + 4.5}" '
            f'fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>')


# ----------------------------------------------------------------------- pieces

def paper(shape, W, H, clip_id):
    """A paper sheet floating on the page itself (no backdrop box), so it
    blends into GitHub's light or dark background like the buttons do."""
    return f"""
  <clipPath id="{clip_id}">{shape}</clipPath>
  <g filter="url(#lift)">{shape.replace("/>", ' fill="url(#sheet)"/>')}</g>
  <g clip-path="url(#{clip_id})"><rect width="{W}" height="{H}" filter="url(#grain)" opacity="0.5"/></g>
  {shape.replace("/>", f' fill="none" stroke="{RULE_STRONG}" stroke-opacity="0.55"/>')}"""


def hero():
    W, H = 1000, 424
    sx0, sy0, sx1, sy1 = 14, 10, 986, 396
    cx, dy = W / 2, -24  # dy shifts the original layout up to the new sheet top
    body = paper(f'<path d="{torn_sheet(sx0, sy0, sx1, sy1)}"/>', W, H, "sheetClip") + f"""
  {ornament(cx, 92 + dy)}
  {text("Ramus Hu", cx, 205 + dy, 92, fill=INK, wght=450, anchor="middle", tracking=-0.01)}
  {text("ARCT musician, experienced full-stack developer", cx, 258 + dy, 27, fill=BRASS_DEEP, anchor="middle")}
  <path d="M{cx - 150},{292 + dy} H{cx - 14} M{cx + 14},{292 + dy} H{cx + 150}" stroke="{RULE_STRONG}" stroke-width="1"/>
  <path d="M{cx},{288 + dy} l4,4 l-4,4 l-4,-4 Z" fill="{BRASS_SOFT}"/>
  {text("A high school junior excelling in music and computer science,", cx, 333 + dy, 20.5, fill=INK_SOFT, anchor="middle")}
  {text("exploring the intersections between the two fields.", cx, 362 + dy, 20.5, fill=INK_SOFT, anchor="middle")}"""
    return svg(W, H, body, "Ramus Hu, ARCT musician, experienced full-stack developer")


def pill(label, sub, ico, *, gold, w=330, h=74):
    """A raised pill button like the site's gold / ghost buttons."""
    face_top, face_bot, under = ("#665936", BRASS_DEEP, UNDER_BRASS) if gold else ("#fffffb", "#f4efdf", UNDER_PAPER)
    fg, fg_sub = (CREAM, "#cbbd93") if gold else (INK, INK_FAINT)
    ring_fill, ring_stroke = ("#5f5232", "#8a7a4f") if gold else ("#fbf8ee", RULE_STRONG)
    edge = "#7f724e" if gold else "#fff"
    r = (h - 14) / 2
    x0, y0, bw, bh = 6, 4, w - 12, h - 14
    icx, icy = x0 + r + 2, y0 + bh / 2
    tx = icx + r - 2 + 14
    lines = text(label, tx, icy - (1 if sub else -7), 20, fill=fg, wght=430)
    if sub:
        lines += text(sub.upper(), tx, icy + 17, 11.5, fill=fg_sub, wght=500, tracking=0.16)
    gid = "g" + label.replace(" ", "").lower()
    body = f"""
  <defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{face_top}"/><stop offset="1" stop-color="{face_bot}"/></linearGradient></defs>
  <rect x="{x0}" y="{y0 + 8}" width="{bw}" height="{bh}" rx="{r}" fill="{INK}" opacity="0.16" filter="url(#lift)"/>
  <rect x="{x0}" y="{y0 + 4}" width="{bw}" height="{bh}" rx="{r}" fill="{under}"/>
  <rect x="{x0}" y="{y0}" width="{bw}" height="{bh}" rx="{r}" fill="url(#{gid})"/>
  <rect x="{x0 + 0.75}" y="{y0 + 0.75}" width="{bw - 1.5}" height="{bh - 1.5}" rx="{r - 0.75}" fill="none" stroke="{edge}" stroke-opacity="0.55"/>
  <circle cx="{icx}" cy="{icy}" r="{r - 9}" fill="{ring_fill}" stroke="{ring_stroke}"/>
  {icon(ico, icx, icy, fg, 1.05)}
  {lines}
  {arrow(x0 + bw - 30, icy, fg_sub)}"""
    return svg(w, h, body, f"{label}{' - ' + sub if sub else ''}")


def divider():
    W, H = 1000, 24
    body = f"""
  <defs><linearGradient id="fade" x1="0" x2="1">
    <stop offset="0" stop-color="{BRASS_SOFT}" stop-opacity="0"/>
    <stop offset="0.5" stop-color="{BRASS_SOFT}" stop-opacity="0.9"/>
    <stop offset="1" stop-color="{BRASS_SOFT}" stop-opacity="0"/></linearGradient></defs>
  <rect x="80" y="{H / 2}" width="{W - 160}" height="1" fill="url(#fade)"/>"""
    return svg(W, H, body, "Section break")


def tape(cx, cy, w, angle):
    return (f'<g transform="translate({cx},{cy}) rotate({angle})">'
            f'<rect x="{-w / 2}" y="-13" width="{w}" height="26" fill="#d9ceb0" fill-opacity="0.78"/>'
            f'<path d="M{-w / 2},-13 l-3,5 l3,4 l-3,5 l3,4 l-3,5 l3,3 M{w / 2},-13 l3,5 l-3,4 l3,5 l-3,4 l3,5 l-3,3" '
            f'fill="none" stroke="#cfc3a2" stroke-opacity="0.8"/></g>')


def connect():
    W, H = 1000, 290
    nx0, ny0, nx1, ny1 = 60, 40, 940, 262
    cx = W / 2
    note = f'<rect x="{nx0}" y="{ny0}" width="{nx1 - nx0}" height="{ny1 - ny0}"/>'
    body = f"""
  <g transform="rotate(-0.5 {cx} {H / 2})">{paper(note, W, H, "noteClip")}</g>
  {tape(nx0 + 14, ny0 + 6, 104, -32)}
  {tape(nx1 - 14, ny0 + 6, 104, 32)}
  <g>{text("CONNECT RAMUS", cx, 104, 14, fill=BRASS, wght=500, tracking=0.24, anchor="middle")}</g>
  <g>{text("Ramus is looking forward to answering your inquiries", cx, 158, 33, fill=INK, wght=420, anchor="middle")}</g>
  <g>
    <path d="M{cx - 200},186 H{cx + 200}" stroke="{RULE}" stroke-width="1"/>
    {text("There is no stupid question.", cx, 224, 21, fill=INK_SOFT, italic=True, anchor="middle")}
  </g>"""
    return svg(W, H, body, "Connect Ramus. There is no stupid question.")


def main():
    OUT.mkdir(exist_ok=True)
    files = {
        "hero.svg": hero(),
        "divider.svg": divider(),
        "connect.svg": connect(),
        "btn-music.svg": pill("Music and piano", "Ramus the accompanist", "note", gold=True),
        "btn-stem.svg": pill("STEM side", "That super nerd", "flask", gold=False, w=300),
        "btn-email.svg": pill("Email", "ramushu0410@gmail.com", "mail", gold=True, w=300),
        "btn-linkedin.svg": pill("LinkedIn", "in/ramushu", "linkedin", gold=False, w=230),
        "btn-instagram.svg": pill("Instagram", "@ramushu0410", "instagram", gold=False, w=240),
    }
    for name, content in files.items():
        (OUT / name).write_text(content)
        print(f"wrote assets/{name}  ({len(content) // 1024} KB)")


if __name__ == "__main__":
    main()
