"""
Subly — UI Design Canvas  v2
Void Signal philosophy: dark precision instrument aesthetic
Refined: proper sizing, tighter spacing, content fills canvas.
"""

from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont
import os

FONT_DIR = os.path.join(
    os.path.expanduser("~"),
    "Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin"
    "/14851d6c-2ea5-4f56-8cd3-b3bbfb9d05b9/eebd68dd-2782-4d4e-80e6-dd6c73563354"
    "/skills/canvas-design/canvas-fonts",
)

def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except Exception:
        return ImageFont.load_default()

# ── Palette ────────────────────────────────────────────────────────────────
BG       = (13, 15, 22)
SURFACE  = (20, 23, 34)
SURFACE2 = (26, 30, 44)
BORDER   = (40, 46, 66)
BORDER2  = (55, 62, 88)
VIOLET   = (124, 58, 237)
VIOLET_G = (90, 35, 180)
TEAL     = (13, 148, 136)
TEAL_D   = (9, 100, 92)
AMBER    = (217, 119, 6)
AMBER_D  = (140, 76, 4)
CRIMSON  = (185, 28, 28)
CRIMSON_D= (110, 18, 18)
BLUE     = (37, 99, 235)
BLUE_D   = (24, 64, 152)
GREEN    = (22, 163, 74)
GREEN_D  = (14, 104, 48)
TEXT_HI  = (238, 240, 250)
TEXT_MID = (148, 158, 186)
TEXT_DIM = (68, 76, 108)
WHITE    = (255, 255, 255)

# ── Canvas ─────────────────────────────────────────────────────────────────
W, H = 1600, 2080
img = Image.new("RGB", (W, H), BG)
d   = ImageDraw.Draw(img)

MARGIN   = 52
GAP      = 18

# ── Fonts ──────────────────────────────────────────────────────────────────
f_logo    = font("Jura-Medium.ttf",              52)
f_dossier = font("BricolageGrotesque-Bold.ttf",  26)
f_section = font("BricolageGrotesque-Bold.ttf",  21)
f_body    = font("BricolageGrotesque-Regular.ttf",18)
f_small   = font("BricolageGrotesque-Regular.ttf",15)
f_xsmall  = font("BricolageGrotesque-Regular.ttf",13)
f_mono    = font("JetBrainsMono-Regular.ttf",     15)
f_mono_b  = font("JetBrainsMono-Bold.ttf",        16)
f_label   = font("Jura-Medium.ttf",              13)
f_badge   = font("BricolageGrotesque-Bold.ttf",  15)
f_score_n = font("BricolageGrotesque-Bold.ttf",  80)
f_score_s = font("BricolageGrotesque-Regular.ttf",17)
f_btn     = font("BricolageGrotesque-Bold.ttf",  19)
f_tag     = font("JetBrainsMono-Regular.ttf",     13)

# ── Helpers ────────────────────────────────────────────────────────────────
def rect(x0, y0, x1, y1, fill=SURFACE, radius=12, border=None, bw=1):
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                        fill=fill, outline=border, width=bw)

def text_at(txt, x, y, f, col=TEXT_HI, anchor="la"):
    d.text((x, y), txt, font=f, fill=col, anchor=anchor)

def text_c(txt, cx, cy, f, col=TEXT_HI):
    bb = d.textbbox((0,0), txt, font=f)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    d.text((cx - tw//2, cy - th//2), txt, font=f, fill=col)

def tw(txt, f):
    bb = d.textbbox((0,0), txt, font=f)
    return bb[2] - bb[0]

def th(txt, f):
    bb = d.textbbox((0,0), txt, font=f)
    return bb[3] - bb[1]

def hline(y, col=BORDER, w=1):
    d.line([(MARGIN, y), (W-MARGIN, y)], fill=col, width=w)

def vline(x, y0, y1, col=BORDER, w=1):
    d.line([(x, y0), (x, y1)], fill=col, width=w)

def badge(txt, x, y, fg, bg):
    pad_x, pad_y = 12, 5
    _tw = tw(txt, f_badge)
    d.rounded_rectangle([x, y, x+_tw+2*pad_x, y+th(txt,f_badge)+2*pad_y],
                        radius=6, fill=bg, outline=fg, width=1)
    d.text((x+pad_x, y+pad_y), txt, font=f_badge, fill=fg)
    return _tw + 2*pad_x + 6   # returns advance width

def gauge_arc(cx, cy, r, pct, col_fg, ring_w=16):
    col_bg = tuple(max(0, c-170) for c in col_fg)
    # background ring
    d.arc([cx-r, cy-r, cx+r, cy+r], -90, 270, fill=BORDER, width=ring_w)
    # value arc
    end = -90 + int(360 * pct / 100)
    d.arc([cx-r, cy-r, cx+r, cy+r], -90, end, fill=col_fg, width=ring_w)
    # inner fill
    ir = r - ring_w - 4
    d.ellipse([cx-ir, cy-ir, cx+ir, cy+ir], fill=SURFACE)

def dot(x, y, r, col):
    d.ellipse([x-r, y-r, x+r, y+r], fill=col)

def wrap_text(text, max_w, f):
    words, line, lines = text.split(), [], []
    for word in words:
        test = " ".join(line + [word])
        if tw(test, f) > max_w and line:
            lines.append(" ".join(line)); line = [word]
        else:
            line.append(word)
    if line: lines.append(" ".join(line))
    return lines

# ════════════════════════════════════════════════════════════════════════════
# TOP ACCENT BAR
# ════════════════════════════════════════════════════════════════════════════
# gradient-ish: violet → teal via segments
seg = (W - 2*MARGIN) // 2
d.rectangle([MARGIN, 0, MARGIN+seg, 3], fill=VIOLET)
d.rectangle([MARGIN+seg, 0, W-MARGIN, 3], fill=TEAL)

# ════════════════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════════════════
y = 28

# Logo mark (two rectangles + wordmark)
d.rounded_rectangle([MARGIN, y, MARGIN+9, y+36], radius=3, fill=VIOLET)
d.rounded_rectangle([MARGIN+13, y, MARGIN+22, y+36], radius=3, fill=TEAL)
text_at("subly", MARGIN+32, y, f_logo, TEXT_HI)

# Right: mode tag
mode_txt = "PROTOTYPE  ·  v0.1"
text_at(mode_txt, W-MARGIN, y+10, f_tag, TEXT_DIM, anchor="ra")

hline(y + 50, BORDER, 1)

# Dossier name
y += 62
text_at("FOM Présence Digitale 2025  —  CNM", MARGIN, y, f_dossier, TEXT_HI)
y += 38

# Status badge + confidence note
bw = badge("À CONFIRMER", MARGIN, y, AMBER, AMBER_D)
badge("SCORE MOYEN", MARGIN + bw + 8, y, TEXT_DIM, (28, 32, 44))
text_at("Analysé le 24 avril 2026  ·  heuristique locale active",
        W-MARGIN, y+4, f_tag, TEXT_DIM, anchor="ra")

y += 42
hline(y, BORDER, 1)
y += 20

# ════════════════════════════════════════════════════════════════════════════
# SCORE ZONE
# ════════════════════════════════════════════════════════════════════════════
zone_h = 210
rect(MARGIN, y, W-MARGIN, y+zone_h, fill=SURFACE, radius=16, border=BORDER, bw=1)

# Gauge
gcx, gcy = MARGIN + 140, y + zone_h//2
gauge_arc(gcx, gcy, 80, 68, AMBER)
text_c("68", gcx, gcy - 12, f_score_n, TEXT_HI)
text_c("/100", gcx, gcy + 46, f_score_s, TEXT_MID)

vline(gcx+110, y+24, y+zone_h-24, BORDER, 1)

# Sub-scores (bars)
sub_x = gcx + 136
sub_y = y + 26
sub_data = [
    ("Bloc client",      55, TEAL),
    ("Bloc projet",      72, TEAL),
    ("Bloc mixte",       68, AMBER),
    ("Fiabilité doc.",   55, TEXT_DIM),
]
bar_max = W - MARGIN - 240 - sub_x - 80
for lbl, val, col in sub_data:
    text_at(lbl, sub_x, sub_y, f_small, TEXT_DIM)
    bar_len = int(bar_max * val / 100)
    d.rounded_rectangle([sub_x+148, sub_y+4, sub_x+148+bar_len, sub_y+18],
                        radius=4, fill=col)
    # track (dim)
    d.rounded_rectangle([sub_x+148+bar_len, sub_y+4, sub_x+148+bar_max, sub_y+18],
                        radius=4, fill=BORDER)
    text_at(f"{val}", sub_x+156+bar_max, sub_y+2, f_mono, TEXT_MID)
    sub_y += 44

# Right panel: counts
sep2_x = W - MARGIN - 280
vline(sep2_x, y+24, y+zone_h-24, BORDER, 1)
rp_x = sep2_x + 28

text_at("NIVEAU DE CONFIANCE", rp_x, y+22, f_label, TEXT_DIM)
text_at("Moyen", rp_x, y+42, f_dossier, AMBER)
text_at("Extraction heuristique locale", rp_x, y+82, f_small, TEXT_DIM)
text_at("→ Claude API non activée", rp_x, y+102, f_xsmall, VIOLET)

text_at("RÉSULTAT  CRITÈRES", rp_x, y+136, f_label, TEXT_DIM)
counts = [("Valides","4",GREEN), ("À conf.","2",AMBER), ("Manquants","3",CRIMSON)]
cx_off = rp_x
for lbl, n, c in counts:
    text_at(n, cx_off, y+156, f_dossier, c)
    text_at(lbl, cx_off, y+188, f_xsmall, TEXT_DIM)
    cx_off += 86

y += zone_h + GAP

# ════════════════════════════════════════════════════════════════════════════
# 4 ANALYSIS COLUMNS
# ════════════════════════════════════════════════════════════════════════════
col_w = (W - 2*MARGIN - 3*GAP) // 4
col_h = 340

cols = [
    ("Points Valides",   GREEN,   [
        "Date de référence détectée",
        "Élément de planning présent",
        "Élément de calendrier OK",
    ]),
    ("À Confirmer",      AMBER,   [
        "Pièce demandée à vérifier",
        "Élément de candidature partiel",
    ]),
    ("Points Bloquants", CRIMSON, [
        "Élément budgétaire absent",
        "Montant dossier non détecté",
    ]),
    ("Recommandations",  BLUE,    [
        "Ajouter un budget / plan de financement",
        "Compléter les documents client",
        "Vérifier les pièces attendues",
    ]),
]

for i, (title, accent, items) in enumerate(cols):
    cx0 = MARGIN + i * (col_w + GAP)
    cx1 = cx0 + col_w
    dim = tuple(max(0, c-160) for c in accent)

    rect(cx0, y, cx1, y+col_h, fill=SURFACE, radius=14, border=BORDER, bw=1)
    # top accent line
    d.rounded_rectangle([cx0, y, cx1, y+4], radius=2, fill=accent)

    # title + count badge
    text_at(title, cx0+18, y+18, f_section, accent)
    cnt = str(len(items))
    cnt_w = tw(cnt, f_badge)
    d.rounded_rectangle([cx1-cnt_w-24, y+14, cx1-10, y+40],
                        radius=6, fill=dim, outline=accent, width=1)
    text_at(cnt, cx1-cnt_w-16, y+17, f_badge, accent)

    # separator
    d.line([(cx0+18, y+52), (cx1-18, y+52)], fill=BORDER, width=1)

    # items
    iy = y + 66
    for item in items:
        dot(cx0+26, iy+9, 4, accent)
        lines = wrap_text(item, col_w-60, f_body)
        for ln in lines:
            text_at(ln, cx0+40, iy, f_body, TEXT_HI)
            iy += 26
        iy += 10

y += col_h + GAP

# ════════════════════════════════════════════════════════════════════════════
# BOTTOM: PRÉ-REMPLISSAGE  +  SUGGESTIONS
# ════════════════════════════════════════════════════════════════════════════
bottom_h = 400
half_w   = (W - 2*MARGIN - GAP) // 2

# ── Pre-fill card ──────────────────────────────────────────────────────────
px0, px1 = MARGIN, MARGIN + half_w
rect(px0, y, px1, y+bottom_h, fill=SURFACE, radius=14, border=BORDER, bw=1)
d.rounded_rectangle([px0, y, px1, y+4], radius=2, fill=VIOLET)

text_at("Pré-remplissage", px0+18, y+16, f_section, VIOLET)
text_at("champs extraits automatiquement", px0+18, y+44, f_xsmall, TEXT_DIM)

# column headers
hdr_y = y + 70
rect(px0+14, hdr_y-2, px1-14, hdr_y+22, fill=SURFACE2, radius=5)
text_at("CHAMP",     px0+22, hdr_y+2, f_label, TEXT_DIM)
text_at("VALEUR",    px0+210, hdr_y+2, f_label, TEXT_DIM)
text_at("CONF",      px1-60,  hdr_y+2, f_label, TEXT_DIM)

conf_col = {
    "haut":  (GREEN, "●"),
    "moyen": (AMBER, "●"),
    "bas":   (CRIMSON, "●"),
}

pre_fields = [
    ("Nom structure",   "FORMATION AUDIO PROFESSIONNELLE",    "moyen"),
    ("Forme juridique", "EI — à confirmer",                   "moyen"),
    ("SIRET",           "Non détecté",                        "bas"),
    ("Email",           "contact@labelackboxstudio.re",        "haut"),
    ("Téléphone",       "Non détecté",                        "bas"),
    ("Titre projet",    "Formulaire de demande d'aide",        "moyen"),
    ("Montant projet",  "Non détecté",                        "bas"),
    ("Dates projet",    "2020-12-01 · 2021-12-31",            "moyen"),
    ("Éléments projet", "public · budget · financement",       "moyen"),
]

row_y = hdr_y + 30
for i, (field, val, conf) in enumerate(pre_fields):
    row_bg = (17, 20, 30) if i % 2 == 0 else SURFACE
    rect(px0+14, row_y, px1-14, row_y+28, fill=row_bg, radius=4)
    text_at(field, px0+22, row_y+5, f_small, TEXT_MID)
    val_disp = val[:32]+"…" if len(val) > 32 else val
    vc = TEXT_HI if conf != "bas" else TEXT_DIM
    text_at(val_disp, px0+210, row_y+5, f_mono, vc)
    col_c, sym = conf_col[conf]
    text_at(sym, px1-46, row_y+5, f_body, col_c)
    row_y += 30

# ── Suggestions card ───────────────────────────────────────────────────────
sx0 = MARGIN + half_w + GAP
sx1 = W - MARGIN
rect(sx0, y, sx1, y+bottom_h, fill=SURFACE, radius=14, border=BORDER, bw=1)
d.rounded_rectangle([sx0, y, sx1, y+4], radius=2, fill=TEAL)

text_at("Suggestions alternatives", sx0+18, y+16, f_section, TEAL)
text_at("financements complémentaires recommandés", sx0+18, y+44, f_xsmall, TEXT_DIM)

suggestions = [
    ("Aides culture, musique & spectacle", 90, TEAL,    "Structures culturelles et production sonore."),
    ("Aides formation et insertion",        75, AMBER,   "Actions de formation, accompagnement."),
    ("Aides territoriales associatives",    60, BLUE,    "Projets associatifs à ancrage local."),
]

card_y = y + 76
card_h_s = (bottom_h - 90) // 3 - GAP//2
sw = sx1 - sx0

for nom, score, col, justif in suggestions:
    rect(sx0+14, card_y, sx1-14, card_y+card_h_s,
         fill=SURFACE2, radius=10, border=BORDER, bw=1)

    # mini gauge
    gcx2, gcy2 = sx0+54, card_y+card_h_s//2
    gauge_arc(gcx2, gcy2, 32, score, col, ring_w=8)
    text_c(str(score), gcx2, gcy2-4, f_mono_b, col)

    # text block
    tx = sx0 + 104
    text_at(nom, tx, card_y+10, f_section, TEXT_HI)
    lines = wrap_text(justif, sw-130, f_small)
    jy = card_y + 38
    for ln in lines:
        text_at(ln, tx, jy, f_small, TEXT_MID)
        jy += 22

    card_y += card_h_s + GAP//2 + 6

y += bottom_h + GAP

# ════════════════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════════════════
foot_h = 66
rect(MARGIN, y, W-MARGIN, y+foot_h, fill=SURFACE, radius=14, border=BORDER, bw=1)

# Left: extraction badge
badge("HEURISTIQUE LOCALE", MARGIN+18, y+(foot_h-28)//2, TEXT_DIM, (26,30,44))

# Center: info
center_txt = "Subly  ·  24 avril 2026  ·  prototype local"
text_c(center_txt, W//2, y+foot_h//2, f_xsmall, TEXT_DIM)

# Right: export button
btn_w, btn_h = 210, 40
bx = W - MARGIN - btn_w - 16
by = y + (foot_h - btn_h)//2
rect(bx, by, bx+btn_w, by+btn_h, fill=VIOLET, radius=10)
text_c("↓  Exporter le rapport", bx+btn_w//2, by+btn_h//2, f_btn, WHITE)

y += foot_h

# ════════════════════════════════════════════════════════════════════════════
# SUBTLE GRID OVERLAY (precision instrument feel) — very faint
# ════════════════════════════════════════════════════════════════════════════
# Only draw grid lines in the area we've filled
for gx in range(MARGIN, W-MARGIN, 40):
    d.line([(gx, 4), (gx, min(y+8, H))], fill=(255,255,255,3), width=1)
for gy in range(4, min(y+8, H), 40):
    d.line([(MARGIN, gy), (W-MARGIN, gy)], fill=(255,255,255,3), width=1)

# Crop to actual content height
final_h = min(y + 16, H)
img_cropped = img.crop((0, 0, W, final_h))

out = os.path.join(os.path.dirname(__file__), "subly_ui_design.png")
img_cropped.save(out, "PNG")
print(f"Saved → {out}  ({W}×{final_h}px)")
