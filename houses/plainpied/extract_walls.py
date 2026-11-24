"""Trace the plan's wall fill, give the scale, and check the walls written in plan.json against the trace.

The plan draws walls as a solid navy fill (exterior ~0.29 m, partitions ~0.09 m); windows are white boxes cut into
that fill and doors are plain gaps, so the walls are the navy pixels that survive an opening wide enough to drop
the dimension lines, the text, the door arcs and the turning circles. The light-blue watermark is not navy and
drops out by colour.

The scale comes from the plan's own overall dimensions, not a guess: the outer wall faces span 11.8 m across and
9.2 m down (the labels on the dimension lines), which also absorbs the slight anisotropy of the scan.
Origin: the outer north-west corner of the house, x right (east), y down (south), metres.

A raw trace is not the model: a scan's 1 px jitter and every arrowhead touching a wall split it into slivers.
The walls are written by hand in plan.json from the numbers this prints (--probe), and this script then draws
them over the plan and reports how much of the trace they cover and how much of them lies off it.

Writes walls.json (scale and the raw traced rectangles) next to this file and walls_dbg.png to
blueprint-out/plainpied/. The plan image is BLUEPRINT_PLAN or plan.png here (the brochure plan stays out of the repo).
Run: python houses/plainpied/extract_walls.py [--probe]
"""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("BLUEPRINT_PLAN", os.path.join(HERE, "plan.png"))
DBG = os.path.join(os.environ.get("BLUEPRINT_OUT", "blueprint-out"), "plainpied")
os.makedirs(DBG, exist_ok=True)
WIDTH_M, DEPTH_M = 11.8, 9.2  # the overall dimension labels

im = cv2.imread(SRC)
b, g, r = (im[..., k].astype(int) for k in range(3))
navy = (((b - r) > 60) & (r < 90) & (b > 90)).astype(np.uint8)
navy = cv2.morphologyEx(navy, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
n, lab, stats, _ = cv2.connectedComponentsWithStats(navy, 8)
mask = np.zeros_like(navy)
for i in range(1, n):
    if stats[i, cv2.CC_STAT_AREA] >= 150:
        mask[lab == i] = 1

ys, xs = np.nonzero(mask)
X0, Y0 = int(xs.min()), int(ys.min())
SX = (xs.max() - xs.min() + 1) / WIDTH_M
SY = (ys.max() - ys.min() + 1) / DEPTH_M
print("outer box px", X0, Y0, xs.max(), ys.max(), "px/m", round(SX, 2), round(SY, 2))


def runs(a):
    xx = np.nonzero(a)[0]
    if not len(xx):
        return []
    br = np.nonzero(np.diff(xx) > 1)[0]
    return list(zip(np.r_[xx[0], xx[br + 1]].tolist(), (np.r_[xx[br], xx[-1]] + 1).tolist()))


def to_rects(m, min_side=3):
    """Exact rectangle cover of a binary mask: runs per row, merged down while the same run repeats."""
    out, live = [], {}
    for y in range(m.shape[0] + 1):
        rs = set(runs(m[y])) if y < m.shape[0] else set()
        for q in list(live):
            if q not in rs:
                out.append((q[0], live.pop(q), q[1], y))
        for q in rs:
            live.setdefault(q, y)
    return [q for q in out if q[2] - q[0] >= min_side and q[3] - q[1] >= min_side]


def to_px(x, y):
    return int(round(x * SX + X0)), int(round(y * SY + Y0))


def rm(q):
    return {"x0": round((q[0] - X0) / SX, 3), "y0": round((q[1] - Y0) / SY, 3), "x1": round((q[2] - X0) / SX, 3), "y1": round((q[3] - Y0) / SY, 3)}


json.dump({"px_per_m": [round(SX, 3), round(SY, 3)], "origin_px": [X0, Y0], "image": "brochure plan, 1754 x 1240 (not in the repo)",
           "traced": [rm(q) for q in to_rects(mask)]}, open(os.path.join(HERE, "walls.json"), "w"), indent=1)

if "--probe" in sys.argv:  # wall bands crossed by a few rows and columns, in metres: the numbers plan.json is written from
    for xm in np.arange(0.5, 11.8, 0.6):
        print(f"col x={xm:5.2f}", " ".join(f"[{(a - Y0) / SY:.3f}-{(e - Y0) / SY:.3f}]" for a, e in runs(mask[:, int(round(X0 + xm * SX))])))
    for ym in np.arange(0.6, 9.2, 0.45):
        print(f"row y={ym:5.2f}", " ".join(f"[{(a - X0) / SX:.3f}-{(e - X0) / SX:.3f}]" for a, e in runs(mask[int(round(Y0 + ym * SY)), :])))

# ---------------------------------------------------------------- check plan.json against the trace
plan = json.load(open(os.path.join(HERE, "plan.json")))
model = np.zeros_like(mask)
holes = np.zeros_like(mask)
for w in plan["walls"]:
    a, c = to_px(w["x0"], w["y0"]), to_px(w["x1"], w["y1"])
    model[a[1]:c[1], a[0]:c[0]] = 1
byid = {w["id"]: w for w in plan["walls"]}
for o in plan["openings"]:
    w = byid[o["wall"]]
    along_x = w["x1"] - w["x0"] >= w["y1"] - w["y0"]
    x0, x1, y0, y1 = (o["a0"], o["a1"], w["y0"], w["y1"]) if along_x else (w["x0"], w["x1"], o["a0"], o["a1"])
    a, c = to_px(x0, y0), to_px(x1, y1)
    holes[a[1]:c[1], a[0]:c[0]] = 1
model[holes == 1] = 0
inter = int((model & mask).sum())
print(f"plan.json walls cover {inter / mask.sum():.1%} of the traced fill; {1 - inter / max(1, model.sum()):.1%} of them lies off it")

ov = im.copy()
ov[(model == 1) & (mask == 1)] = (60, 170, 60)
ov[(model == 1) & (mask == 0)] = (30, 30, 230)
ov[(model == 0) & (mask == 1)] = (230, 120, 20)
ov[holes == 1] = (0, 200, 255)
cv2.imwrite(os.path.join(DBG, "walls_dbg.png"), cv2.addWeighted(ov, 0.75, im, 0.25, 0))
print("green: agrees, red: model only, blue: trace only, yellow: openings ->", os.path.join(DBG, "walls_dbg.png"))
