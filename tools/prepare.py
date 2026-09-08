#!/usr/bin/env python3
"""
Turn the design JPEGs in `Assets/` into web-ready screen plates.

The artwork ships with a *baked-in* countdown ("20 HOURS / 30 MINUTES"). To run
a live timer we have to take those digits back out again and redraw them in the
browser. This script does the taking-out, once, offline:

  1. locate the seven-segment digit blocks and their unit labels,
  2. paint the digits out by interpolating the background down each column
     (the artwork behind them is a smooth vertical gradient, so this is
     invisible),
  3. write a downscaled "plate" JPEG plus small label patches,
  4. crop the reusable artwork pieces (logo lockup, headline, tagline) that the
     landscape/HD layout composes into a 16:9 screen,
  5. record every measurement in public/screens/manifest.json so the browser
     can position live digits exactly where the designed ones were.

Run:  python3 tools/prepare.py        (server.js runs it automatically once)
"""

import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "Assets ")
if not os.path.isdir(SRC_DIR):
    SRC_DIR = os.path.join(ROOT, "Assets")
OUT_DIR = os.path.join(ROOT, "public", "screens")

# Source art is 7087x31890. A quarter of that is plenty of detail and keeps the
# whole pipeline inside a few hundred MB of RAM.
DRAFT = 4
OUT_W = 1440          # plate width delivered to the browser
CROP_W = 900          # artwork pieces the HD layout re-composes
JPEG_Q = 88

# --- the strategic-partner row across the top ------------------------------
# The artwork carries PIF on the left and a Tuwaiq Academy | Digital Saudi
# lockup on the right. More partners joined after the artwork was signed off,
# so the designed lockup is lifted out and the supplied replacement — the full
# strategic-partner row, header and all — is set in its place, scaled to the
# width between the PIF mark and the right-hand margin the design already uses.
PARTNER_BAND = 0.045      # the top strip, as a fraction of the height
PARTNER_GAP = 0.035       # clearance from the PIF lockup, as a fraction of width
PARTNER_ART = "logos2-04.png"

# --- how many rows the countdown gets --------------------------------------
# The artwork was drawn with two (hours, minutes) or one (minutes). Seconds are
# added below, and the whole stack is scaled to fit the space the artwork
# leaves above whatever comes next.
CLOCK_ROWS = {2: ["hours", "minutes", "seconds"], 1: ["minutes", "seconds"]}

# --- where the designed timer lives, as fractions of the image -------------
# Bands are deliberately loose: the exact ink bounds are measured inside them.
HOURS_SLOT = dict(unit="hours", band=(0.450, 0.565), label_band=(0.565, 0.592), xwin=(0.20, 0.76))
MINS_SLOT = dict(unit="minutes", band=(0.605, 0.713), label_band=(0.714, 0.744), xwin=(0.20, 0.76))
TEAM_SLOT = dict(unit="minutes", band=(0.385, 0.545), label_band=(0.548, 0.592), xwin=(0.08, 0.94))

SCREENS = [
    # id            source file                     program        menu label                 slots
    ("hold",       "coloum-screen-01.jpg",          "both",        "Holding screen",          []),
    ("started",    "coloum-screen-02.jpg",          "hacking",     "Challenge started",       [HOURS_SLOT, MINS_SLOT]),
    ("mentoring1", "coloum-screen-03.jpg",          "hacking",     "Mentoring round 1",       [HOURS_SLOT, MINS_SLOT]),
    ("build",      "coloum-screen-04.jpg",          "hacking",     "Build and develop",       [HOURS_SLOT, MINS_SLOT]),
    ("mentoring2", "coloum-screen-05.jpg",          "hacking",     "Mentoring round 2",       [HOURS_SLOT, MINS_SLOT]),
    ("prototype",  "coloum-screen-06.jpg",          "hacking",     "Prototype mode",          [HOURS_SLOT, MINS_SLOT]),
    ("demo",       "coloum-screen(Teams)-01.jpg",   "presentation", "Demo time",              [TEAM_SLOT]),
    ("judges",     "coloum-screen(Teams)-02.jpg",   "presentation", "Judges time",            [TEAM_SLOT]),
    ("teams",      "coloum-screen(Teams)-03.jpg",   "presentation", "Teams branding",         []),
]

INK = 150       # luminance above which a pixel counts as artwork ink
GLOW = 70       # softer threshold, used to catch the halo around the digits


def runs(flags):
    """Contiguous True stretches of a 1-D boolean array, as (start, end)."""
    out, start = [], None
    for i, v in enumerate(flags):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(flags)))
    return out


def ink_box(lum, y0, y1, x0, x1, thr=INK, min_px=2):
    """Tight bounding box of ink inside a window, or None."""
    sub = lum[y0:y1, x0:x1] > thr
    rows = np.where(sub.sum(axis=1) > min_px)[0]
    cols = np.where(sub.sum(axis=0) > min_px)[0]
    if not len(rows) or not len(cols):
        return None
    return (x0 + cols.min(), y0 + rows.min(), x0 + cols.max() + 1, y0 + rows.max() + 1)


def measure_slot(lum, W, H, slot):
    """
    Work out the geometry of one designed digit block.

    The right-hand glyph is always a '0', which in this seven-segment face fills
    its cell edge to edge — so it gives us the true cell width. The left glyph
    ('2' or '3') may be inset, so the block's left edge is derived from the cell
    width and the inter-digit gap rather than measured directly.
    """
    y0, y1 = int(slot["band"][0] * H), int(slot["band"][1] * H)
    xw0, xw1 = int(slot["xwin"][0] * W), int(slot["xwin"][1] * W)

    box = ink_box(lum, y0, y1, xw0, xw1)
    if box is None:
        return None
    _, by0, _, by1 = box

    band = lum[by0:by1, xw0:xw1] > INK
    cols = runs(band.sum(axis=0) > 2)

    # Glow blooms in the artwork also register as ink. A digit is distinguished
    # by spanning the full height of the block in at least one column (its
    # vertical segments do), which no bloom does.
    rows_ix = np.arange(band.shape[0])[:, None]
    first = np.where(band.any(axis=0), np.argmax(band, axis=0), 0)
    last = band.shape[0] - 1 - np.where(band.any(axis=0), np.argmax(band[::-1], axis=0), 0)
    extent = np.where(band.any(axis=0), last - first, 0)
    tall = 0.85 * extent.max()
    cols = [r for r in cols if extent[r[0]:r[1]].max() >= tall]
    if len(cols) < 2:
        return None
    left, right = cols[0], cols[-1]

    cell = right[1] - right[0]                 # '0' fills its cell
    gap = (xw0 + right[0]) - (xw0 + left[1])   # measured dark gap
    # Left glyph's ink may start inside its cell; place the cell by arithmetic.
    bx1 = xw0 + right[1]
    bx0 = bx1 - (2 * cell + gap)

    colour = None
    reg = lum[by0:by1, bx0:bx1]
    mask = reg > 200
    if mask.sum():
        colour = mask

    # Unit label directly beneath.
    ly0, ly1 = int(slot["label_band"][0] * H), int(slot["label_band"][1] * H)
    lbox = ink_box(lum, ly0, ly1, xw0, xw1, thr=110)

    return dict(
        unit=slot["unit"],
        digits=(bx0, by0, bx1, by1),
        gap=gap,
        cell=cell,
        label=lbox,
    )


def background_floor(sub, win):
    """
    Estimate the artwork behind the ink.

    An absolute brightness threshold cannot separate ink from background here:
    screen 05's brown wash is brighter than screen 02's near-black. So take the
    darkest value in each neighbourhood wider than a segment stroke — that can
    only be background — and smooth it back up to full size. `win` is that
    neighbourhood in pixels; it has to exceed the stroke width of whatever is
    being removed, so callers scale it to the block they are erasing.
    """
    h, w = sub.shape
    b = 16
    ph, pw = -(-h // b), -(-w // b)
    pad = np.full((ph * b, pw * b), sub.max(), np.float32)
    pad[:h, :w] = sub
    coarse = pad.reshape(ph, b, pw, b).min(axis=(1, 3))
    k = max(3, int(round(win / b)) | 1)
    ce = np.pad(coarse, k // 2, mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(ce, (k, k))
    coarse = win.min(axis=(2, 3))
    floor = Image.fromarray(coarse).resize((w, h), Image.BILINEAR)
    return np.asarray(floor, dtype=np.float32)


def _down(img, w):
    """Weighted 2x box reduction; zero-weight (unknown) pixels contribute nothing."""
    h, wd = w.shape
    h2, w2 = (h + 1) // 2 * 2, (wd + 1) // 2 * 2
    pi = np.zeros((h2, w2, img.shape[2]), np.float32)
    pw = np.zeros((h2, w2), np.float32)
    pi[:h, :wd] = img * w[..., None]
    pw[:h, :wd] = w
    si = pi.reshape(h2 // 2, 2, w2 // 2, 2, -1).sum(axis=(1, 3))
    sw = pw.reshape(h2 // 2, 2, w2 // 2, 2).sum(axis=(1, 3))
    out = np.zeros_like(si)
    nz = sw > 0
    out[nz] = si[nz] / sw[nz][:, None]
    return out, np.minimum(sw, 1.0)


def _up(img, shape):
    """Smooth 2x expansion back to `shape`."""
    big = np.repeat(np.repeat(img, 2, axis=0), 2, axis=1)[: shape[0], : shape[1]]
    k = np.array([0.25, 0.5, 0.25], np.float32)
    for ax in (0, 1):
        pad = np.pad(big, [(1, 1) if a == ax else (0, 0) for a in range(3)], mode="edge")
        big = sum(k[i] * np.take(pad, range(i, i + big.shape[ax]), axis=ax) for i in range(3))
    return big


def inpaint(region, known):
    """
    Fill the unknown pixels of `region` with a smooth continuation of what
    surrounds them (a pull-push pyramid, then a few Jacobi passes to polish).

    The artwork behind the digits is soft gradient and glow, so a harmonic fill
    reproduces it convincingly — including where a bloom crosses the block, which
    a straight vertical interpolation cannot follow.
    """
    img = region.astype(np.float32)
    w = known.astype(np.float32)

    pyr = [(img, w)]
    while min(pyr[-1][1].shape) > 2:
        pyr.append(_down(*pyr[-1]))

    filled = pyr[-1][0]
    for lvl in range(len(pyr) - 2, -1, -1):
        li, lw = pyr[lvl]
        up = _up(filled, li.shape)
        filled = li * lw[..., None] + up * (1 - lw)[..., None]

    # A short relaxation removes any residual pyramid structure.
    unknown = ~known
    if unknown.any():
        for _ in range(90):
            p = np.pad(filled, ((1, 1), (1, 1), (0, 0)), mode="edge")
            avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) * 0.25
            filled[unknown] = avg[unknown]
    return filled


def erase(arr, lum, boxes, pad=None):
    """
    Remove the designed ink inside `boxes` and grow the surrounding artwork over
    the hole. A feathered mask blends the repair back so no seam is visible.
    """
    h, w = lum.shape
    out = arr.astype(np.float32).copy()
    for (bx0, by0, bx1, by1) in boxes:
        bh = by1 - by0
        p = pad if pad is not None else max(52, int(0.10 * bh))
        ry0, ry1 = max(0, by0 - p), min(h, by1 + p)
        rx0, rx1 = max(0, bx0 - p), min(w, bx1 + p)
        region = arr[ry0:ry1, rx0:rx1]
        sub_lum = lum[ry0:ry1, rx0:rx1]

        win = min(400, max(48, 0.32 * bh))
        ink = (sub_lum > background_floor(sub_lum, win) + 10).astype(np.uint8) * 255
        ink = np.asarray(
            Image.fromarray(ink).filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(6)),
            dtype=np.float32,
        ) / 255.0
        soft = np.clip(ink * 2.6, 0, 1)
        # Never touch the feathered border itself, or the fill has nothing to
        # anchor against.
        soft[:6, :] = soft[-6:, :] = 0
        soft[:, :6] = soft[:, -6:] = 0
        if soft.max() <= 0.02:
            continue

        filled = inpaint(region, soft < 0.02)
        a = soft[..., None]
        out[ry0:ry1, rx0:rx1] = region.astype(np.float32) * (1 - a) + filled * a
    return np.clip(out, 0, 255).astype(np.uint8)


def load_partner(name):
    """The supplied partner lockup, trimmed to its ink."""
    path = os.path.join(SRC_DIR, name)
    if not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGBA")
    return im.crop(im.getbbox())


def paste_rgba(arr, rgba, x, y):
    """Alpha-composite an RGBA image onto the uint8 RGB plate, in place."""
    h, w = rgba.height, rgba.width
    H, W = arr.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    src = np.asarray(rgba, np.float32)[y0 - y:y1 - y, x0 - x:x1 - x]
    a = src[..., 3:4] / 255.0
    dst = arr[y0:y1, x0:x1].astype(np.float32)
    arr[y0:y1, x0:x1] = np.clip(dst * (1 - a) + src[..., :3] * a, 0, 255).astype(np.uint8)


def add_partners(arr, W, H):
    """
    Swap the designed partner lockup for the current one.

    The replacement keeps the design's own right-hand margin and grows left as
    far as the PIF mark allows, which is what sets its size — it carries a
    header line the designed lockup did not, so it is a wider piece of artwork
    for the same row.
    """
    logo = load_partner(PARTNER_ART)
    if logo is None:
        return arr

    lum = arr.max(axis=2).astype(np.float32)
    band = int(PARTNER_BAND * H)
    old = ink_box(lum, 0, band, int(0.40 * W), W, thr=110, min_px=3)
    pif = ink_box(lum, 0, band, 0, int(0.38 * W), thr=110, min_px=3)
    if old is None:
        return arr
    bx0, by0, bx1, by1 = old
    left = (pif[2] if pif else 0) + PARTNER_GAP * W

    avail_w = bx1 - left
    avail_h = band * 0.86
    scale = min(avail_w / logo.width, avail_h / logo.height)
    w = max(1, round(logo.width * scale))
    h = max(1, round(logo.height * scale))

    out = erase(arr, lum, [old], pad=int(0.006 * H))
    paste_rgba(out, logo.resize((w, h), Image.LANCZOS), bx1 - w, (by0 + by1) / 2 - h / 2)
    return out


def first_ink_below(lum, W, H, y):
    """Where the artwork next has something to say, below row `y`."""
    rows = (lum[int(y):] > 150).sum(axis=1) > W * 0.004
    hit = np.where(rows)[0]
    return int(y) + int(hit[0]) if len(hit) else H


def clock_rows(measured, lum, W, H, units):
    """
    Place one row of digits per unit, in the space the artwork leaves.

    The designed rows give the proportions — block height, the drop to the unit
    word, the pitch from one row to the next. Adding a row needs more height
    than the design left, so the whole stack is scaled about its top until the
    last unit word clears whatever the artwork draws underneath.
    """
    m0 = measured[0]
    dx0, dy0, dx1, dy1 = m0["digits"]
    lab = m0["label"]
    row_h = (lab[3] - dy0) if lab else (dy1 - dy0) * 1.44
    pitch = (measured[1]["digits"][1] - dy0) if len(measured) > 1 else row_h * 1.40

    last = measured[-1]
    below = last["label"][3] if last["label"] else last["digits"][3]
    # Clear of whatever comes next by a comfortable margin — a unit word that
    # only just misses the tagline underneath it reads as a collision.
    limit = first_ink_below(lum, W, H, below + 0.004 * H) - 0.024 * H

    n = len(units)
    total = (n - 1) * pitch + row_h
    k = min(1.0, (limit - dy0) / total) if total > 0 else 1.0

    cx = (dx0 + dx1) / 2
    dw, dh = (dx1 - dx0) * k, (dy1 - dy0) * k
    lab_dy = (lab[1] - dy0) * k if lab else dh * 1.20
    lab_h = (lab[3] - lab[1]) * k if lab else dh * 0.15
    lab_w = (lab[2] - lab[0]) * k if lab else dw * 0.6

    rows = []
    for i, unit in enumerate(units):
        top = dy0 + i * pitch * k
        rows.append(dict(
            unit=unit,
            digits=(cx - dw / 2, top, cx + dw / 2, top + dh),
            label=(cx - lab_w / 2, top + lab_dy, cx + lab_w / 2, top + lab_dy + lab_h),
            gap=m0["gap"] / (dx1 - dx0),
        ))
    return rows


def content_bands(lum, H, W, lo, hi, min_h=8):
    """Row runs that contain ink between two fractional heights."""
    y0, y1 = int(lo * H), int(hi * H)
    flags = (lum[y0:y1] > 90).sum(axis=1) > W * 0.004
    return [(y0 + a, y0 + b) for a, b in runs(flags) if b - a >= min_h]


def crop_region(arr, lum, W, H, lo, hi, pad_frac=0.013, raw=False):
    """
    Cut a piece of artwork out of its background.

    The HD layout re-composes these pieces on its own backdrop, so they cannot
    bring the column's dark ground along with them. Everything in this artwork
    is bright ink glowing over a near-black wash, i.e. essentially additive — so
    subtracting an estimate of the ground and taking what is left as alpha
    recovers the ink with a clean edge.
    """
    bands = content_bands(lum, H, W, lo, hi)
    if not bands:
        return None
    top, bottom = bands[0][0], bands[-1][1]
    pad = int(pad_frac * H)
    top, bottom = max(0, top - pad), min(H, bottom + pad)
    sub = lum[top:bottom] > 90
    cols = np.where(sub.sum(axis=0) > 2)[0]
    if not len(cols):
        return None
    xpad = int(0.03 * W)
    left, right = max(0, cols.min() - xpad), min(W, cols.max() + 1 + xpad)

    reg = arr[top:bottom, left:right].astype(np.float32)
    if raw:
        # Pictorial artwork has no ink/ground distinction to exploit; it is
        # framed and edge-faded by the page instead.
        return Image.fromarray(arr[top:bottom, left:right])
    # Just wider than a letter stroke: big enough to find the ground between
    # glyphs, small enough to follow a glow gradient rather than keep it.
    floor = background_floor(lum[top:bottom, left:right], 96)
    ink = np.clip(reg - floor[..., None], 0, 255)
    alpha = ink.max(axis=2) / 255.0
    # Drop the faint ambient haze that surrounds everything in this artwork,
    # so a cut-out carries only its own ink.
    alpha = np.clip((alpha - 0.07) / 0.93, 0, 1)
    safe = np.maximum(alpha, 1 / 255.0)[..., None]
    # A trace of the column's ambient glow always survives. Fading the alpha
    # across the padding leaves it with no edge to read as a rectangle.
    def ramp(n, k):
        i = np.arange(n, dtype=np.float32)
        return np.clip(np.minimum(i, n - 1 - i) / max(1, k), 0, 1)
    alpha = alpha * ramp(ink.shape[0], pad)[:, None] * ramp(ink.shape[1], xpad)[None, :]

    rgba = np.zeros(ink.shape[:2] + (4,), np.uint8)
    rgba[..., :3] = np.clip(ink / safe, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def hexes(v):
    return "#%02x%02x%02x" % tuple(int(x) for x in v)


def still_bands(lum, W, H):
    """
    Split a screen that carries no countdown into wordmark, picture and copy.

    The picture is simply the tallest block of ink; the wordmark is whatever sits
    above it, and the copy is the run of text lines below — skipping the wide
    ambient glows, which are tall but are not content.
    """
    found = content_bands(lum, H, W, 0.0, 1.0)
    if not found:
        return ()
    hero = max(found, key=lambda b: b[1] - b[0])
    above = [b for b in found if b[1] <= hero[0]]
    below = [b for b in found if b[0] >= hero[1] and (b[1] - b[0]) <= 0.05 * H]
    out = [("lockup", 0.010, 0.180)]
    out.append(("hero", max(0.185, hero[0] / H - 0.004), hero[1] / H + 0.004))
    if below and max(b[1] - b[0] for b in below) >= 0.008 * H:
        out.append(("headline", below[0][0] / H - 0.008, below[-1][1] / H + 0.008))
    return tuple(out)


def main():
    if not os.path.isdir(SRC_DIR):
        sys.exit("Assets folder not found next to this script (looked for %r)" % SRC_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    manifest = []
    for sid, fname, program, name, slots in SCREENS:
        path = os.path.join(SRC_DIR, fname)
        if not os.path.exists(path):
            print("  ! missing %s — skipped" % fname)
            continue
        print("  · %s" % fname, flush=True)

        im = Image.open(path)
        im.draft("RGB", (im.width // DRAFT, im.height // DRAFT))
        im = im.convert("RGB")
        W, H = im.size
        arr = np.asarray(im)
        # Re-set the partner row first, so the plate, the HD crops and the
        # blurred backdrop all carry it.
        arr = add_partners(arr, W, H)
        lum = arr.max(axis=2).astype(np.float32)

        measured = [m for m in (measure_slot(lum, W, H, s) for s in slots) if m]

        # --- accent colour of the designed digits (per-screen: white/orange/pink)
        accent = "#ffffff"
        if measured:
            x0, y0, x1, y1 = measured[0]["digits"]
            reg = arr[y0:y1, x0:x1].astype(np.float32)
            m = lum[y0:y1, x0:x1] > 200
            if m.sum():
                accent = hexes(reg[m].mean(axis=0))

        # --- plate: digits removed, unit labels left intact -------------------
        plate_arr = erase(arr, lum, [m["digits"] for m in measured]) if measured else arr
        plate = Image.fromarray(plate_arr)

        out_h = round(OUT_W * H / W)
        plate_small = plate.resize((OUT_W, out_h), Image.LANCZOS)
        plate_name = "%s.jpg" % sid
        plate_small.save(os.path.join(OUT_DIR, plate_name), quality=JPEG_Q, optimize=True, progressive=True)

        # --- the clock, re-laid with a row per unit ---------------------------
        # Adding seconds moves every row, so the designed unit words can no
        # longer be left in place: each is covered with a patch of its own
        # background and all of them are re-drawn where the new rows put them.
        slot_meta, patch_meta = [], []
        if measured:
            units = CLOCK_ROWS.get(len(measured), [m["unit"] for m in measured])
            label_colour = accent
            for i, m in enumerate(measured):
                if not m["label"]:
                    continue
                lx0, ly0, lx1, ly1 = m["label"]
                # The unit words are dimmer than the digits; match them exactly
                # so a re-drawn label reads as the designed one.
                lreg = arr[ly0:ly1, lx0:lx1].astype(np.float32)
                lmask = lum[ly0:ly1, lx0:lx1]
                bright = lmask >= np.percentile(lmask, 96)
                if bright.sum():
                    label_colour = hexes(lreg[bright].mean(axis=0))
                px, py = int(0.030 * W), int(0.006 * H)
                bx0, by0 = max(0, lx0 - px), max(0, ly0 - py)
                bx1, by1 = min(W, lx1 + px), min(H, ly1 + py)
                patched = erase(arr, lum, [m["label"]], pad=int(0.005 * H))
                patch = Image.fromarray(patched).crop((bx0, by0, bx1, by1))
                pw = max(1, round(OUT_W * (bx1 - bx0) / W))
                patch = patch.resize((pw, max(1, round(pw * (by1 - by0) / (bx1 - bx0)))), Image.LANCZOS)
                pname = "%s-label%d.jpg" % (sid, i)
                patch.save(os.path.join(OUT_DIR, pname), quality=JPEG_Q, optimize=True)
                patch_meta.append(dict(
                    src="screens/" + pname,
                    x=bx0 / W, y=by0 / H, w=(bx1 - bx0) / W, h=(by1 - by0) / H,
                ))

            for row in clock_rows(measured, lum, W, H, units):
                dx0, dy0, dx1, dy1 = row["digits"]
                lx0, ly0, lx1, ly1 = row["label"]
                slot_meta.append(dict(
                    unit=row["unit"],
                    x=dx0 / W, y=dy0 / H, w=(dx1 - dx0) / W, h=(dy1 - dy0) / H,
                    gap=row["gap"],
                    label=dict(
                        x=lx0 / W, y=ly0 / H, w=(lx1 - lx0) / W, h=(ly1 - ly0) / H,
                        colour=label_colour,
                    ),
                ))

        # --- artwork pieces the HD layout reuses ------------------------------
        top_of_timer = min((s["y"] * H for s in slot_meta), default=int(0.62 * H))
        bottom_of_timer = max(
            (((s["label"]["y"] + s["label"]["h"]) if s.get("label") else s["y"] + s["h"]) * H
             for s in slot_meta),
            default=int(0.66 * H),
        )
        # Pieces the landscape layout re-composes. A screen with a countdown
        # splits into headline / clock / tagline; one without splits into its
        # wordmark, its picture and its line of copy.
        if measured:
            bands = (
                ("lockup", 0.010, 0.180),
                ("headline", 0.195, top_of_timer / H - 0.012),
                ("tagline", bottom_of_timer / H + 0.020, 0.960),
            )
        else:
            bands = still_bands(lum, W, H)

        crops = {}
        for key, lo, hi in bands:
            if hi <= lo:
                continue
            c = crop_region(arr, lum, W, H, lo, hi, raw=(key == "hero"))
            if c is None:
                continue
            cw = min(CROP_W, c.width)
            c = c.resize((cw, max(1, round(cw * c.height / c.width))), Image.LANCZOS)
            cname = "%s-%s.%s" % (sid, key, "jpg" if key == "hero" else "png")
            if key == "hero":
                c.save(os.path.join(OUT_DIR, cname), quality=JPEG_Q, optimize=True)
            else:
                c.save(os.path.join(OUT_DIR, cname), optimize=True)
            crops[key] = dict(src="screens/" + cname, ratio=c.width / c.height)

        # --- tiny blurred copy, used as the HD backdrop -----------------------
        bg = im.resize((90, max(1, round(90 * H / W))), Image.LANCZOS).filter(ImageFilter.GaussianBlur(6))
        bg_name = "%s-bg.jpg" % sid
        bg.save(os.path.join(OUT_DIR, bg_name), quality=80)

        manifest.append(dict(
            id=sid, source=fname, program=program, name=name,
            src="screens/" + plate_name, bg="screens/" + bg_name,
            w=OUT_W, h=out_h, accent=accent,
            slots=slot_meta, patches=patch_meta, crops=crops,
        ))

    # A build stamp for the artwork. The plates are served with a long cache —
    # they never change *within* a build — so every URL carries this, and a
    # re-run reaches screens that would otherwise sit on yesterday's copy for a
    # day. Media-server browsers in particular never look again on their own.
    rev = str(int(time.time()))
    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
        json.dump(dict(version=1, rev=rev, screens=manifest), f, indent=1)
    print("  → %d screens written to public/screens/" % len(manifest))


if __name__ == "__main__":
    main()
