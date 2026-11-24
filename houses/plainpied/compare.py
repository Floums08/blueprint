"""Lay the top render over the plan at the same scale: the plan's walls in red over the model, and the two side by side.

The top shot is orthographic, north up, 12.8 m across its width and centred on plan (5.9, 4.6); walls.json holds the
plan's pixels per metre and the pixel of the house's north-west corner. Everything is resampled to 80 px per metre.
Run: python houses/plainpied/compare.py [render_top.png] [out.png]
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.environ.get("BLUEPRINT_OUT", "blueprint-out"), "plainpied")
SRC = os.environ.get("BLUEPRINT_PLAN", os.path.join(HERE, "plan.png"))
top_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "render_top.png")
out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(OUT, "compare_top.png")
W = json.load(open(os.path.join(HERE, "walls.json")))
SX, SY = W["px_per_m"]
OX, OY = W["origin_px"]
K = 80  # output px per metre
X0, X1, Y0, Y1 = -0.5, 12.3, -0.5, 9.7  # the window shown, plan metres

plan = Image.open(SRC).convert("RGB")
plan = plan.crop((round(OX + X0 * SX), round(OY + Y0 * SY), round(OX + X1 * SX), round(OY + Y1 * SY)))
size = (round((X1 - X0) * K), round((Y1 - Y0) * K))
plan = plan.resize(size, Image.LANCZOS)

top = Image.open(top_path).convert("RGBA")
w, h = top.size
ppm = w / 12.8  # render px per metre
cx, cy = w / 2, h / 2  # plan (5.9, 4.6)
top = top.crop((round(cx + (X0 - 5.9) * ppm), round(cy + (Y0 - 4.6) * ppm), round(cx + (X1 - 5.9) * ppm), round(cy + (Y1 - 4.6) * ppm)))
top = top.resize(size, Image.LANCZOS)
paper = Image.new("RGBA", size, (255, 255, 255, 255))
model = Image.alpha_composite(paper, top).convert("RGB")

# the plan's navy wall fill, drawn in red over the model
p = np.asarray(plan).astype(int)
navy = ((p[..., 2] - p[..., 0]) > 60) & (p[..., 0] < 90) & (p[..., 2] > 90)
over = np.asarray(model).copy()
over[navy] = (0.35 * over[navy] + 0.65 * np.array([225, 30, 30])).astype(np.uint8)
gap = 24
sheet = Image.new("RGB", (size[0] * 3 + gap * 2, size[1]), (255, 255, 255))
sheet.paste(plan, (0, 0))
sheet.paste(model, (size[0] + gap, 0))
sheet.paste(Image.fromarray(over), (2 * (size[0] + gap), 0))
sheet.save(out_path)
print("plan | model | plan walls over the model ->", out_path)
