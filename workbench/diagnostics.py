"""Diagnostic PNGs an assistant can read instead of watching playback.

Called by analyze.run(); can also be run directly:  python workbench/diagnostics.py guard walk
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BLUE, ORANGE, AQUA, RED = (42, 120, 214), (235, 104, 52), (27, 175, 122), (200, 30, 40)
INK, MUTED, GRID, BG = (30, 30, 30), (110, 110, 110), (225, 225, 225), (255, 255, 255)


def font(size=14):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def time_colour(t: float) -> tuple[int, int, int]:
    """Early frames blue, late frames orange."""
    return tuple(int(BLUE[k] + (ORANGE[k] - BLUE[k]) * t) for k in range(3))


def union_bbox(frames, pad=12, ground_y=None):
    xs0, ys0, xs1, ys1 = [], [], [], []
    for f in frames:
        ys, xs = np.nonzero(f[..., 3] > 128)
        if len(xs):
            xs0.append(xs.min()); xs1.append(xs.max()); ys0.append(ys.min()); ys1.append(ys.max())
    h, w = frames[0].shape[:2]
    y1 = max(ys1) + pad
    if ground_y is not None:
        y1 = max(y1, int(ground_y) + pad)
    return max(0, min(xs0) - pad), max(0, min(ys0) - pad), min(w, max(xs1) + pad), min(h, y1)


def to_pil(frame):
    return Image.fromarray(frame, "RGBA")


def outline(frame, colour, width=2):
    m = (frame[..., 3] > 128).astype(np.uint8)
    edge = m - cv2.erode(m, np.ones((3, 3), np.uint8))
    if width > 1:
        edge = cv2.dilate(edge, np.ones((width, width), np.uint8))
    out = np.zeros_like(frame)
    out[edge > 0, :3] = colour
    out[edge > 0, 3] = 255
    return Image.fromarray(out, "RGBA")


def frame_flags(report):
    per = {}
    for f in report["flags"]:
        for k in f["frames"]:
            per.setdefault(k - 1, []).append(f["code"])
    return per


def wrap(text, width_px, fnt):
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    out, cur = [], ""
    for word in text.split(" "):
        trial = (cur + " " + word).strip()
        if probe.textlength(trial, font=fnt) <= width_px or not cur:
            cur = trial
        else:
            out.append(cur); cur = word
    out.append(cur)
    return out


def header(img_w, lines, size=15):
    img_w = max(img_w, 640)
    fnt = font(size)
    rows = [(k, part) for k, line in enumerate(lines) for part in wrap(line, img_w - 20, fnt)]
    im = Image.new("RGB", (img_w, 8 + len(rows) * (size + 6)), BG)
    d = ImageDraw.Draw(im)
    for r, (k, part) in enumerate(rows):
        d.text((10, 6 + r * (size + 6)), part, fill=INK if k == 0 else MUTED, font=fnt)
    return im


def stack(images, bg=BG):
    w = max(i.width for i in images)
    out = Image.new("RGB", (w, sum(i.height for i in images)), bg)
    y = 0
    for i in images:
        out.paste(i, (0, y)); y += i.height
    return out


def title_line(report):
    return f"{report['character']}/{report['action']}  ({report['frame_count']} frames, owner status: {report['status_in_manifest'] or '-'})"


# ------------------------------------------------------------------ contact sheet

def contact_sheet(act, report, scale=0.5, cols=8):
    n = len(act.frames)
    x0, y0, x1, y1 = union_bbox(act.frames, ground_y=act.ground_y)
    tw, th = int((x1 - x0) * scale), int((y1 - y0) * scale)
    cols = min(cols, n)
    rows = (n + cols - 1) // cols
    lab_h = 50
    sheet = Image.new("RGB", (cols * tw, rows * (th + lab_h)), BG)
    d = ImageDraw.Draw(sheet)
    walk = report["metrics"]["walk"]
    flags = frame_flags(report)
    gy = (act.ground_y - y0) * scale
    for i, f in enumerate(act.frames):
        cx, cy = (i % cols) * tw, (i // cols) * (th + lab_h)
        tile = to_pil(f).crop((x0, y0, x1, y1)).resize((tw, th), Image.LANCZOS)
        sheet.paste(tile, (cx, cy + lab_h), tile)
        d.line([(cx, cy + lab_h + gy), (cx + tw, cy + lab_h + gy)], fill=(150, 150, 150), width=1)
        for c in report["metrics"]["feet"][i]["clusters"]:
            px, py = cx + (c["x"] - x0) * scale, cy + lab_h + (c["y"] - y0) * scale
            r = 5
            if c["planted"]:
                d.ellipse([px - r, py - r, px + r, py + r], fill=AQUA, outline=INK)
            else:
                d.ellipse([px - r, py - r, px + r, py + r], outline=ORANGE, width=2)
        kind = f"  {walk['pose_kind'][i]}" if walk else ""
        d.text((cx + 6, cy + 4), f"{i + 1}{kind}", fill=INK, font=font(16))
        if i in flags:
            for r, part in enumerate(wrap(" ".join(sorted(set(flags[i]))), tw - 10, font(10))[:3]):
                d.text((cx + 6, cy + 22 + r * 11), part, fill=RED, font=font(10))
        d.rectangle([cx, cy, cx + tw - 1, cy + th + lab_h - 1], outline=GRID)
    hd = header(sheet.width, [title_line(report),
                              "Numbers = playback order. Grey line = ground y. Filled green dot = planted foot estimate, orange ring = lifted foot. Red = suspect flags on that frame."])
    return stack([hd, sheet])


# ------------------------------------------------------------------ onion skin

def onion(act, report, scale=0.75):
    n = len(act.frames)
    x0, y0, x1, y1 = union_bbox(act.frames, ground_y=act.ground_y)
    base = Image.new("RGBA", (x1 - x0, y1 - y0), BG + (255,))
    ghost = to_pil(act.frames[0]).crop((x0, y0, x1, y1))
    ghost.putalpha(ghost.getchannel("A").point(lambda a: a * 0.18))
    base.alpha_composite(ghost)
    for i, f in enumerate(act.frames):
        base.alpha_composite(outline(f, time_colour(i / max(n - 1, 1))).crop((x0, y0, x1, y1)))
    d = ImageDraw.Draw(base)
    gy = act.ground_y - y0
    d.line([(0, gy), (base.width, gy)], fill=(150, 150, 150), width=1)
    img = base.convert("RGB").resize((int(base.width * scale), int(base.height * scale)), Image.LANCZOS)
    # legend: gradient bar
    leg = Image.new("RGB", (max(img.width, 640), 30), BG)
    ld = ImageDraw.Draw(leg)
    for k in range(200):
        ld.line([(60 + k, 8), (60 + k, 20)], fill=time_colour(k / 199))
    ld.text((10, 7), "frame 1", fill=INK, font=font(12))
    ld.text((266, 7), f"frame {n}", fill=INK, font=font(12))
    hd = header(img.width, [title_line(report), "Outline of every frame, coloured by time. Faint fill = frame 1.",
                            "Tight bundles = little motion; outlines that jump = uneven motion."], 13)
    return stack([hd, img, leg])


# ------------------------------------------------------------------ world-space strip

def matched_steps(contacts, steps, sign, travel_list):
    """For each step, the planted pair that slides least at the given travel."""
    out = []
    for (i, j), v in zip(steps, travel_list):
        best = None
        pa = [c for c in contacts[i] if c["planted"]]
        pb = [c for c in contacts[j] if c["planted"]]
        for a in pa:
            for b in pb:
                if contacts_named(contacts) and a["name"] != b["name"]:
                    continue
                s = abs(sign * (a["x"] - b["x"]) - v)
                if best is None or s < best[0]:
                    best = (s, a, b)
        out.append(best)
    return out


def contacts_named(contacts):
    return any(not c["name"].startswith("cluster") for cs in contacts for c in cs)


def world_strip(act, report, travel=None, label="", loops=2):
    walk = report["metrics"]["walk"]
    n = len(act.frames)
    loop = act.loop_mode == "loop"
    loops = loops if loop else 1
    sign = 1.0 if act.facing == "right" else -1.0
    if travel is None:
        travel = walk["travel_used_px"]
    per_frame = travel if isinstance(travel, list) else [travel] * len(walk["steps"])
    seq = [k % n for k in range(n * loops)] + ([0] if loop else [])
    step_index = {tuple(s): k for k, s in enumerate(walk["steps"])}
    offsets = [0.0]
    for a, b in zip(seq, seq[1:]):
        offsets.append(offsets[-1] + sign * per_frame[step_index[(a, b)]])
    x0, y0, x1, y1 = union_bbox(act.frames, ground_y=act.ground_y)
    span = int(max(offsets) - min(offsets))
    minoff = min(offsets)
    W = x1 - x0 + span
    canvas = Image.new("RGBA", (W, y1 - y0), BG + (255,))
    feet_layer = Image.new("RGBA", (W, y1 - y0), (0, 0, 0, 0))
    # draw the full figure only every `every` frames so small travel doesn't turn into a blur
    mean_tr = abs(float(np.mean(per_frame))) if per_frame else 0
    every = max(1, int(np.ceil(0.3 * (x1 - x0) / max(mean_tr, 1e-6))))
    shown = []
    for k, (fi, off) in enumerate(zip(seq, offsets)):
        col = time_colour(fi / max(n - 1, 1))
        pos = (int(off - minoff), 0)
        feet_layer.alpha_composite(outline(act.frames[fi], col, 1).crop((x0, y0, x1, y1)), pos)
        if k % every:
            continue
        shown.append((k, fi, pos))
        col = time_colour(fi / max(n - 1, 1))
        fr = to_pil(act.frames[fi]).crop((x0, y0, x1, y1))
        fr.putalpha(fr.getchannel("A").point(lambda a: a * 0.10))
        canvas.alpha_composite(fr, pos)
        canvas.alpha_composite(outline(act.frames[fi], col, 1).crop((x0, y0, x1, y1)), pos)
    d = ImageDraw.Draw(canvas)
    for k, fi, pos in shown:
        d.text((pos[0] + (x1 - x0) // 2, 2), str(fi + 1), fill=time_colour(fi / max(n - 1, 1)), font=font(13))
    gy = act.ground_y - y0
    d.line([(0, gy), (W, gy)], fill=INK, width=2)
    contacts = walk["contacts"]
    matches = matched_steps(contacts, walk["steps"], sign, per_frame)
    lim = max(4.0, 0.15 * (np.mean(per_frame) if per_frame else 0))
    # slide rows below the ground
    rows_h = 16 * (len(seq) - 1) + 30
    track = Image.new("RGB", (W, rows_h), BG)
    td = ImageDraw.Draw(track)
    total = 0.0
    for k, (a_i, b_i) in enumerate(zip(seq, seq[1:])):
        m = matches[step_index[(a_i, b_i)]]
        if m is None:
            td.text((4, 6 + 16 * k), f"{a_i+1}->{b_i+1}: no shared planted contact", fill=MUTED, font=font(11))
            continue
        s, a, b = m
        xa = a["x"] - x0 + offsets[k] - minoff
        xb = b["x"] - x0 + offsets[k + 1] - minoff
        total += s
        y = 8 + 16 * k
        col = RED if s > lim else AQUA
        d.ellipse([xa - 4, gy - 4, xa + 4, gy + 4], fill=col)
        td.line([(xa, y), (xb, y)], fill=col, width=3)
        td.line([(xa, y - 5), (xa, y + 5)], fill=INK, width=1)
        td.line([(xb, y - 5), (xb, y + 5)], fill=INK, width=1)
        td.text((max(xa, xb) + 8, y - 7), f"{a_i+1}->{b_i+1}  {s:.1f}px", fill=col if s > lim else MUTED, font=font(11))
    scale_note = f" = {total * act.game_scale:.0f} game px" if act.game_scale else ""
    v_desc = f"{np.mean(per_frame):.1f} px/frame" + (" (per-frame list)" if isinstance(travel, list) else "")
    hd = header(W, [title_line(report) + f"  -  world-space strip {label}",
                    f"Travel {v_desc}; {loops} loop(s) left to right" + (f"; full figure drawn every {every} frames (numbers on top), feet zoom shows all" if every > 1 else "") + ". Each step: the planted foot pair that slides least. "
                    f"Total slide >= {total:.0f} cell px{scale_note} over {len(seq) - 1} steps.",
                    f"Bars below = how far the planted foot moves on the ground in that step (red > {lim:.1f}px). Zero-length = foot stays put."], 13)
    # feet zoom panel at 2x
    band_top = max(0, int(gy - 90))
    zc = Image.new("RGBA", canvas.size, BG + (255,))
    zc.alpha_composite(feet_layer)
    zd = ImageDraw.Draw(zc)
    zd.line([(0, gy), (W, gy)], fill=INK, width=2)
    for k, (a_i, b_i) in enumerate(zip(seq, seq[1:])):
        m = matches[step_index[(a_i, b_i)]]
        if m:
            s_, a, b = m
            xa = a["x"] - x0 + offsets[k] - minoff
            zd.ellipse([xa - 3, gy - 3, xa + 3, gy + 3], fill=RED if s_ > lim else AQUA)
    zoom = zc.crop((0, band_top, W, min(canvas.height, int(gy + 10)))).convert("RGB")
    zoom = zoom.resize((zoom.width * 2, zoom.height * 2), Image.LANCZOS)
    zlab = header(zoom.width, ["Feet region, 2x zoom, every frame's outline (dots = planted foot used for each step; red = sliding)"], 12)
    return stack([hd, canvas.convert("RGB"), track, zlab, zoom])


# ------------------------------------------------------------------ charts

class Chart:
    def __init__(self, w=560, h=250, title="", ylabel="", xs=None, ymin=0.0, ymax=1.0, xlabels=None):
        self.w, self.h, self.ml, self.mr, self.mt, self.mb = w, h, 56, 16, 46, 34
        self.im = Image.new("RGB", (w, h), BG)
        self.d = ImageDraw.Draw(self.im)
        self.xs = list(xs) if xs is not None else []
        self.ymin, self.ymax = ymin, (ymax if ymax > ymin else ymin + 1)
        self.d.text((self.ml, 6), title, fill=INK, font=font(14))
        pw, ph = w - self.ml - self.mr, h - self.mt - self.mb
        for k in range(5):
            v = self.ymin + (self.ymax - self.ymin) * k / 4
            y = self.Y(v)
            self.d.line([(self.ml, y), (self.ml + pw, y)], fill=GRID)
            self.d.text((4, y - 7), f"{v:.3g}", fill=MUTED, font=font(11))
        self.d.text((4, self.mt - 18), ylabel, fill=MUTED, font=font(11))
        self.d.line([(self.ml, self.mt + ph), (self.ml + pw, self.mt + ph)], fill=MUTED)
        labels = xlabels or [str(x) for x in self.xs]
        every = max(1, len(labels) // 16)
        for k, lab in enumerate(labels):
            if k % every == 0:
                self.d.text((self.X(k) - 6, self.mt + ph + 6), lab, fill=MUTED, font=font(10))

    def X(self, k):
        n = max(len(self.xs) - 1, 1)
        return self.ml + (self.w - self.ml - self.mr) * (k / n if len(self.xs) > 1 else 0.5)

    def Y(self, v):
        ph = self.h - self.mt - self.mb
        return self.mt + ph * (1 - (v - self.ymin) / (self.ymax - self.ymin))

    def line(self, ys, colour, marker=True):
        pts = [(self.X(k), self.Y(v)) for k, v in enumerate(ys) if v is not None]
        if len(pts) > 1:
            self.d.line(pts, fill=colour, width=2)
        if marker:
            for x, y in pts:
                self.d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=colour, outline=BG)

    def bars(self, ys, colour, offset=0.0, width=0.35):
        step = (self.w - self.ml - self.mr) / max(len(self.xs), 1)
        for k, v in enumerate(ys):
            if v is None:
                continue
            x = self.X(k) + offset * step
            self.d.rectangle([x - width * step / 2, self.Y(v), x + width * step / 2, self.Y(self.ymin)], fill=colour)

    def legend(self, items):
        x = self.w - self.mr
        for name, col in reversed(items):
            tw = self.d.textlength(name, font=font(11))
            x -= tw + 26
            self.d.rectangle([x, 27, x + 12, 37], fill=col)
            self.d.text((x + 16, 25), name, fill=INK, font=font(11))

    def hline(self, v, colour, text=""):
        y = self.Y(v)
        self.d.line([(self.ml, y), (self.w - self.mr, y)], fill=colour, width=1)
        if text:
            self.d.text((self.ml + 4, y - 14), text, fill=colour, font=font(10))

    def vline_at(self, xval, colour, text, row=0):
        """Vertical marker at a data x value (xs must be numeric)."""
        lo, hi = self.xs[0], self.xs[-1]
        x = self.ml + (self.w - self.ml - self.mr) * (xval - lo) / (hi - lo if hi > lo else 1)
        self.d.line([(x, self.mt), (x, self.h - self.mb)], fill=colour, width=2)
        self.d.text((x + 4, self.mt + 2 + 14 * row), text, fill=colour, font=font(11))


def heatmap(mat, title, size=250):
    n = len(mat)
    m = np.array(mat)
    cell = max(8, (size - 40) // n)
    im = Image.new("RGB", (max(560, 40 + cell * n + 10), 30 + cell * n + 24), BG)
    d = ImageDraw.Draw(im)
    d.text((40, 6), title, fill=INK, font=font(13))
    vmax = m.max() if m.max() > 0 else 1
    lo, hi = np.array([235, 242, 252]), np.array([13, 54, 107])  # sequential blue
    for i in range(n):
        for j in range(n):
            t = m[i, j] / vmax
            col = tuple(int(c) for c in lo + (hi - lo) * t)
            d.rectangle([40 + j * cell, 30 + i * cell, 40 + (j + 1) * cell - 1, 30 + (i + 1) * cell - 1], fill=col)
        d.text((22, 30 + i * cell + cell / 2 - 6), str(i + 1), fill=MUTED, font=font(10))
        d.text((40 + i * cell + 2, 30 + n * cell + 1), str(i + 1), fill=MUTED, font=font(9))
    return im


def charts(act, report):
    met = report["metrics"]
    ch, geo, walk = met["change"], met["geometry"], met["walk"]
    n = len(act.frames)
    step_labels = [f"{i+1}>{j+1}" for i, j, _ in ch["steps"]]
    pose = [v for *_, v in ch["steps"]]
    detail = [v for *_, v in ch["detail_steps"]]
    panels = []
    if pose:
        c = Chart(title="Change per step (seam = last>first)", ylabel="fraction", xs=range(len(pose)),
                  ymax=max(max(pose + detail), 0.1) * 1.1, xlabels=step_labels)
        c.hline(ch["step_median"], MUTED, f"pose median {ch['step_median']:.2f}")
        c.line(pose, BLUE); c.line(detail, ORANGE)
        c.legend([("pose (silhouette)", BLUE), ("detail redrawn", ORANGE)])
        panels.append(c.im)
    hs = [g["height"] for g in geo]
    c = Chart(title="Figure height per frame", ylabel="px", xs=range(n), ymin=min(hs) * 0.97, ymax=max(hs) * 1.03,
              xlabels=[str(i + 1) for i in range(n)])
    ref = met["identity"].get("reference_geometry") if met["identity"].get("same_cell_size") else None
    if ref:
        c.hline(ref["height"], AQUA, f"identity reference {ref['height']}px")
        c.ymin, c.ymax = min(c.ymin, ref["height"] * 0.97), max(c.ymax, ref["height"] * 1.03)
        c = Chart(title="Figure height per frame", ylabel="px", xs=range(n), ymin=min(hs + [ref["height"]]) * 0.97,
                  ymax=max(hs + [ref["height"]]) * 1.03, xlabels=[str(i + 1) for i in range(n)])
        c.hline(ref["height"], AQUA, f"identity reference {ref['height']}px")
    c.line(hs, BLUE)
    panels.append(c.im)
    bs = [g["baseline"] for g in geo]
    c = Chart(title=f"Lowest pixel y per frame (ground = {act.ground_y:.0f})", ylabel="y px", xs=range(n),
              ymin=min(bs + [act.ground_y]) - 4, ymax=max(bs + [act.ground_y]) + 4, xlabels=[str(i + 1) for i in range(n)])
    c.hline(act.ground_y, AQUA, "ground"); c.line(bs, BLUE)
    panels.append(c.im)
    idn = met["identity"]
    if idn.get("head_width_ratio_rel"):
        vals = idn["head_width_ratio_rel"] + idn["bulk_rel"]
        c = Chart(title="Proportions vs identity reference (1 = same)", ylabel="ratio", xs=range(n),
                  ymin=min(vals + [0.9]) - 0.05, ymax=max(vals + [1.1]) + 0.05, xlabels=[str(i + 1) for i in range(n)])
        c.hline(1.0, MUTED, "reference")
        c.line(idn["head_width_ratio_rel"], BLUE); c.line(idn["bulk_rel"], ORANGE)
        c.legend([("head width / height", BLUE), ("area / height^2", ORANGE)])
        panels.append(c.im)
    if walk:
        st = walk["stride_px"]
        c = Chart(title="Stride (foot spread); C = contact, P = passing", ylabel="px", xs=range(n), ymax=max(st + [1]) * 1.15,
                  xlabels=[str(i + 1) for i in range(n)])
        c.line(st, BLUE)
        for i, k in enumerate(walk["pose_kind"]):
            if k != "between":
                c.d.text((c.X(i) - 4, c.Y(st[i]) - 20), k[0].upper(), fill=INK, font=font(12))
        panels.append(c.im)
        used, rec = walk["slide_per_step_px"], walk["slide_at_recommended_px"]
        vals = [v for v in used + rec if v is not None]
        c = Chart(title="Planted-foot slide per step (lower bound)", ylabel="cell px", xs=range(len(used)),
                  ymax=max(vals + [5]) * 1.1, xlabels=[f"{i+1}>{j+1}" for i, j in walk["steps"]])
        c.bars(used, BLUE, -0.2); c.bars(rec, ORANGE, 0.2)
        c.legend([(f"at {walk['travel_used_px']:.1f}px/frame", BLUE), (f"at best {walk['recommended_travel_px']:.1f}", ORANGE)])
        panels.append(c.im)
        curve = walk["slide_curve"]
        xs = [v for v, _ in curve]
        c = Chart(title="Total slide per loop vs constant travel", ylabel="cell px", xs=xs,
                  ymax=max(s for _, s in curve) * 1.1, xlabels=[f"{v:.0f}" for v in xs])
        c.line([s for _, s in curve], BLUE, marker=False)
        c.vline_at(walk["travel_used_px"], RED, "used")
        c.vline_at(walk["recommended_travel_px"], AQUA, "best", 1)
        c.vline_at(walk["stride_based_travel_px"], MUTED, "stride est.", 2)
        c.d.text((c.ml, c.h - 14), "travel px/frame", fill=MUTED, font=font(10))
        panels.append(c.im)
    panels.append(heatmap(met["pose_distance_matrix"], "Pose distance between all frames (dark = different)"))
    # grid 2 columns
    cols = 2
    cw = max(p.width for p in panels)
    rows = [panels[k:k + cols] for k in range(0, len(panels), cols)]
    out = Image.new("RGB", (cw * cols, sum(max(p.height for p in r) for r in rows)), BG)
    y = 0
    for r in rows:
        for k, p in enumerate(r):
            out.paste(p, (k * cw, y))
        y += max(p.height for p in r)
    return stack([header(out.width, [title_line(report) + "  -  metrics", report["summary"]], 13), out])


# ------------------------------------------------------------------ identity side-by-side

def identity_sheet(act, report, max_frames=8, scale=0.5):
    if act.reference is None:
        return None
    n = len(act.frames)
    pick = sorted(set(np.linspace(0, n - 1, min(n, max_frames)).round().astype(int).tolist()))
    x0, y0, x1, y1 = union_bbox(act.frames, ground_y=act.ground_y)
    ref = act.reference
    same = ref.shape[:2] == act.frames[0].shape[:2]
    rx0, ry0, rx1, ry1 = union_bbox([ref])
    note = "same cell scale"
    if same:
        y0, y1 = min(y0, ry0), max(y1, ry1)
        ref_img = to_pil(ref).crop((rx0, y0, rx1, y1))
    else:
        # different drawing size: scale the reference so its height matches the median frame height
        hmed = np.median([g["height"] for g in report["metrics"]["geometry"]])
        k = float(hmed / (ry1 - ry0 - 24))
        ref_img = to_pil(ref).crop((rx0, ry0, rx1, ry1))
        ref_img = ref_img.resize((int(ref_img.width * k), int(ref_img.height * k)), Image.LANCZOS)
        pad = Image.new("RGBA", (ref_img.width, y1 - y0), (0, 0, 0, 0))
        pad.alpha_composite(ref_img, (0, int(max(0, (y1 - y0) - ref_img.height - (y1 - act.ground_y) + 12))))
        ref_img = pad
        note = "reference RESCALED to median frame height (different source size); size comparison not meaningful"
    tiles = [("reference", ref_img)] + [(f"frame {i + 1}", to_pil(act.frames[i]).crop((x0, y0, x1, y1))) for i in pick]
    th = int((y1 - y0) * scale)
    widths = [int(t.width * scale) for _, t in tiles]
    im = Image.new("RGB", (sum(widths) + 10 * len(tiles), th + 26), BG)
    d = ImageDraw.Draw(im)
    x = 0
    for (name, t), w in zip(tiles, widths):
        t = t.resize((w, th), Image.LANCZOS)
        im.paste(t, (x, 26), t)
        d.text((x + 4, 4), name, fill=INK, font=font(13))
        x += w + 10
    if same:
        rg = report["metrics"]["identity"]["reference_geometry"]
        for yv, lab in ((rg["bbox"][1], "ref top"), (rg["bbox"][1] + 0.25 * rg["height"], "ref head 25%"), (rg["baseline"], "ref baseline")):
            yy = 26 + (yv - y0) * scale
            d.line([(0, yy), (im.width, yy)], fill=AQUA, width=1)
            d.text((im.width - 90, yy - 13), lab, fill=AQUA, font=font(10))
    # palette swatches: reference palette with share in reference vs mean share in action
    idn = report["metrics"]["identity"]
    pal, rh = idn["reference_palette"], idn["reference_palette_hist"]
    ah = np.mean(np.array(idn["palette_hist"]), axis=0)
    sw = Image.new("RGB", (im.width, 96), BG)
    sd = ImageDraw.Draw(sw)
    sd.text((6, 4), "Reference palette (k-means, 8): share of pixels in reference (left bar) vs mean of action frames (right bar)", fill=MUTED, font=font(11))
    for k, (hx, a, b) in enumerate(zip(pal, rh, ah)):
        cx = 10 + k * 70
        sd.rectangle([cx, 24, cx + 26, 50], fill=hx, outline=INK)
        sd.rectangle([cx + 32, 90 - a * 150, cx + 42, 90], fill=BLUE)
        sd.rectangle([cx + 44, 90 - b * 150, cx + 54, 90], fill=ORANGE)
        sd.text((cx, 54), f"{a:.0%}/{b:.0%}", fill=INK, font=font(10))
    hd = header(im.width, [title_line(report) + "  -  identity vs " + (idn["reference"] or ""), note], 13)
    return stack([hd, im, sw])


# ------------------------------------------------------------------ entry

def write_all(act, report, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    written = {}

    def save(name, img):
        if img is not None:
            p = out_dir / name
            img.save(p, optimize=True)
            written[name.removesuffix(".png")] = name

    save("contact_sheet.png", contact_sheet(act, report))
    save("onion.png", onion(act, report))
    save("charts.png", charts(act, report))
    save("identity.png", identity_sheet(act, report))
    walk = report["metrics"]["walk"]
    if walk:
        save("world_strip.png", world_strip(act, report, label=f"at {walk['travel_used_px']:.1f} px/frame ({walk['travel_used_source']})"))
        save("world_strip_best_constant.png", world_strip(act, report, walk["recommended_travel_px"], "at slide-minimising constant travel"))
        per = [v if v is not None else walk["recommended_travel_px"] for v in walk["recommended_per_frame_travel_px"]]
        save("world_strip_per_frame.png", world_strip(act, report, per, "with per-frame travel matched to the planted foot"))
    return written


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import analyze
    analyze.main(sys.argv[1:])
