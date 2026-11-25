"""The parts counter over the plain-pied house film: a still card top-left while the house is built on the plan.

It reads timeline.json (every landing with its stage, the counter's rows and colours, the title), draws one RGBA frame
per film frame at the output size and lays them over the rendered frames with ffmpeg, scaling the frames up to that
size first (the film renders at 960x540 on a CPU; the card stays sharp). The card never moves: only the numbers and
the bars change. Leaves on the house plants land with the decor but are not counted as parts.

    python houses/plainpied/hud.py --frames blueprint-out/plainpied/film --out blueprint-out/plainpied/silent.mp4
        [--size 1920x1080] [--test 7.5,frame.png,out.png]
"""
import argparse
import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def font(bold):
    names = (["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf", r"C:\Windows\Fonts\seguisb.ttf", "/System/Library/Fonts/SFNS.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else
             ["/usr/share/fonts/opentype/inter/Inter-Regular.otf", r"C:\Windows\Fonts\segoeui.ttf", "/System/Library/Fonts/SFNS.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    return next((f for f in names if os.path.exists(f)), None)


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def rgb(c, a=255):
    return tuple(int(round(255 * max(0.0, min(1.0, v)) ** (1 / 2.2))) for v in c) + (a,)


def num(n):
    return f"{n:,}".replace(",", ".")  # Spanish thousands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True, help="the rendered film frames f_0001.png ...")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--hud-dir", default=os.path.join(os.environ.get("BLUEPRINT_OUT", "blueprint-out"), "plainpied", "hud"))
    ap.add_argument("--crf", default="17")
    ap.add_argument("--test", help="'seconds,background.png,out.png': draw one frame over an image and stop")
    a = ap.parse_args()
    W, H = map(int, a.size.split("x"))
    S = H / 1080
    tl = json.load(open(os.path.join(HERE, "timeline.json"), encoding="utf-8"))
    fps, dur = tl["fps"], tl["duration"]
    nf = int(round(dur * fps))
    rows = tl["rows"]
    stage_row = {st: i for i, r in enumerate(rows) for st in r["stages"]}
    lands = [(p["t"], stage_row.get(p["stage"])) for p in tl["parts"] if p.get("count", True)]
    lands = [(t, r) for t, r in lands if r is not None]
    totals = [sum(1 for _, r in lands if r == i) for i in range(len(rows))]
    total = sum(totals)
    t_in, t_out = 1.0, tl["T"]["wave"] + 0.3
    os.makedirs(a.hud_dir, exist_ok=True)
    fb, fr = font(True), font(False)
    f_title, f_sub = ImageFont.truetype(fb, int(21 * S)), ImageFont.truetype(fr, int(18 * S))
    f_big, f_row, f_num = ImageFont.truetype(fb, int(72 * S)), ImageFont.truetype(fr, int(19 * S)), ImageFont.truetype(fb, int(18 * S))
    X, Y, CW = int(56 * S), int(52 * S), int(452 * S)
    CH = int((196 + 31 * len(rows) + 18) * S)
    blank = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    only = None
    if a.test:
        ts_, bg_, out_ = a.test.split(",")
        only = int(round(float(ts_) * fps)) + 1
    for f in range(1, nf + 1):
        if only and f != only:
            continue
        t = (f - 1) / fps
        alpha = smooth((t - t_in) / 0.5) * (1 - smooth((t - t_out) / 0.8))
        path = os.path.join(a.hud_dir, f"h_{f:04d}.png")
        if alpha <= 0.002 and not only:
            blank.save(path)
            continue
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        A = lambda v: int(v * alpha)  # noqa: E731
        d.rounded_rectangle((X, Y, X + CW, Y + CH), int(20 * S), fill=(14, 16, 20, A(168)))
        d.text((X + 28 * S, Y + 24 * S), tl.get("title", ""), font=f_title, fill=(255, 255, 255, A(235)))
        d.text((X + 28 * S, Y + 54 * S), tl.get("subtitle", ""), font=f_sub, fill=(255, 255, 255, A(150)))
        done = [sum(1 for tt, r in lands if r == i and tt <= t) for i in range(len(rows))]
        d.text((X + 26 * S, Y + 84 * S), num(sum(done)), font=f_big, fill=(255, 255, 255, A(255)))
        d.text((X + 30 * S, Y + 166 * S), f"de {num(total)} piezas colocadas", font=f_sub, fill=(255, 255, 255, A(150)))
        y = Y + 210 * S
        for i, r in enumerate(rows):
            col = r["color"]
            full = done[i] >= totals[i] > 0
            d.ellipse((X + 30 * S, y + 7 * S, X + 42 * S, y + 19 * S), fill=rgb(col, A(255)))
            d.text((X + 54 * S, y), r["label"], font=f_row, fill=(255, 255, 255, A(230 if done[i] else 120)))
            n_ = num(done[i])
            tw = d.textlength(n_, font=f_num)
            d.text((X + 300 * S - tw, y + 1 * S), n_, font=f_num, fill=(255, 255, 255, A(255 if full else 200)))
            bx0, bx1 = X + 318 * S, X + CW - 28 * S
            d.rounded_rectangle((bx0, y + 10 * S, bx1, y + 15 * S), int(3 * S), fill=(255, 255, 255, A(26)))
            k = done[i] / totals[i] if totals[i] else 0.0
            if k > 0:
                d.rounded_rectangle((bx0, y + 10 * S, bx0 + max(6 * S, (bx1 - bx0) * k), y + 15 * S), int(3 * S), fill=rgb(col, A(255)))
            y += 31 * S
        if only:
            bgim = Image.open(bg_).convert("RGBA").resize((W, H), Image.LANCZOS)
            Image.alpha_composite(bgim, im).convert("RGB").save(out_)
            print("test frame", out_)
            return
        im.save(path)
    print(f"hud: {nf} frames, {total} parts")
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(a.frames, "f_%04d.png"),
           "-framerate", str(fps), "-i", os.path.join(a.hud_dir, "h_%04d.png"),
           "-filter_complex", f"[0]scale={W}:{H}:flags=lanczos[v];[v][1]overlay=0:0:format=auto:shortest=1,format=yuv420p",
           "-c:v", "libx264", "-crf", a.crf, "-preset", "slow", "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
