"""The plan with a metre grid over it, to read openings and furniture off in metres (x right, y down, origin at the
house's outer north-west corner; the scale from walls.json). Run:
python houses/plainpied/grid_view.py x0 y0 x1 y1 out.png [zoom]   (all in metres)"""
import json
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("BLUEPRINT_PLAN", os.path.join(HERE, "plan.png"))
W = json.load(open(os.path.join(HERE, "walls.json")))
SX, SY = W["px_per_m"]
OX, OY = W["origin_px"]
x0, y0, x1, y1 = map(float, sys.argv[1:5])
out = sys.argv[5]
k = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0
im = cv2.imread(SRC)[int(OY + y0 * SY):int(OY + y1 * SY), int(OX + x0 * SX):int(OX + x1 * SX)]
im = cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)


def lines(a0, a1, s, horizontal):
    step = 0.1
    v = a0 - (a0 % step) + step
    while v < a1:
        q = int((v - a0) * s * k)
        whole = abs(round(v) - v) < 1e-6
        half = abs(round(v * 2) - v * 2) < 1e-6
        if horizontal:
            c = (255, 0, 0) if whole else ((255, 120, 80) if half else (255, 215, 205))
            cv2.line(im, (0, q), (im.shape[1], q), c, 1)
            if half:
                cv2.putText(im, f"{v:.1f}", (2, q - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 0, 0), 1)
        else:
            c = (0, 0, 255) if whole else ((80, 80, 255) if half else (205, 205, 255))
            cv2.line(im, (q, 0), (q, im.shape[0]), c, 1)
            if half:
                cv2.putText(im, f"{v:.1f}", (q + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 200), 1)
        v += step


lines(x0, x1, SX, False)
lines(y0, y1, SY, True)
cv2.imwrite(out, im)
