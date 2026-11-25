"""Action sounds for the plain-pied house film (houses/plainpied/film.py). Every time comes from timeline.json, which
film.py writes off the film's own clock: each part's launch and landing, the wave, the door.

Paper air over the plan; a dull thud per slab tile; concrete blocks knocking into place under a running rattle of the
courses (1,300 blocks: thinned, the rattle carries the rest); plaster tiles a notch higher; a glass tink per pane and
a click per frame; a wooden knock per plank and rafter; cabinet knocks and soft thumps for the fittings and the
furniture; pops for the decor; a soft slap per ceiling sheet; a ceramic clack per row of roof tiles; a riser into the
wave, an impact and a chime as it leaves the door, air as it spreads; a whoosh down to the terrace, the threshold,
and the room's own tone inside. With BED=1 (tools/music.py sets it when there is no music track) a warm e-piano bed
plays under it all.

    python run_sfx.py houses/plainpied/score.py --out <wav>
    python tools/music.py --film <silent.mp4> --score houses/plainpied/score.py --out <final.mp4>
"""

import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

from sfx.score_kit import airy, bed, chords, env_fade, hz, rattle, thud  # noqa: E402
from sfx.synth import SR, blip, chime, click, impact, pop, riser, sample, whoosh  # noqa: E402

TIMELINE = "timeline.json"
TARGET_LUFS = -14.0
SEED = 8612


def knock(f, dur=0.07, tau=0.018, grit=0.35):
    """a hard part seating: a short pitched knock with a noisy front"""
    n = int(dur * SR)
    out = []
    for k in range(n):
        t = k / SR
        s = math.sin(2 * math.pi * f * t) * math.exp(-t / tau)
        s += 0.5 * math.sin(2 * math.pi * f * 2.3 * t) * math.exp(-t / (tau * 0.5))
        s += random.uniform(-1, 1) * math.exp(-t / 0.002) * grit
        out.append(s)
    return out


def slap(dur=0.12):
    """a board laid flat: a short burst of dark noise with a soft body"""
    n = int(dur * SR)
    return [(random.uniform(-1, 1) * math.exp(-k / (0.012 * SR)) + 0.6 * math.sin(2 * math.pi * 140 * k / SR) * math.exp(-k / (0.03 * SR)))
            for k in range(n)]


def span(tl, stage):
    ts = [e["t"] for e in tl["parts"] if e["stage"] == stage]
    return (min(ts), max(ts)) if ts else (0.0, 0.0)


def score(mix, tl):
    random.seed(SEED)
    T, dur = tl["T"], tl["duration"]

    if os.environ.get("BED"):  # no music track: a warm e-piano bed, bass and soft drums from the second bar
        left, right, low, drums = bed(dur + 0.5, 100, chords("Cmaj9:C3 E3 G3 B3 D4/C2", "Am9:A2 C3 E3 G3 B3/A1",
                                                              "Fmaj9:F2 A2 C3 E3 G3/F1", "G6:G2 B2 D3 E3/G1"),
                                      motif=((0, hz("E5")), (0.75, hz("G5")), (1.5, hz("B5")), (2.5, hz("A5"))), drums_from=2, keys_vel=0.8)
        mix.put_stereo(0.0, left, right, 0.32)
        mix.put(0.0, low, 0.3)
        mix.put(0.0, drums, 0.18)

    # ---------------------------------------------------------------- the plan, the spiral down
    mix.put(0.0, env_fade(airy(2.4, 1800, 4200, 0.4), 0.4, 0.8), 0.006)
    mix.put(0.5, riser(1.0, 300, 2400), 0.008)

    # ---------------------------------------------------------------- the courses rattling up, then each part in its own material
    w0, w1 = span(tl, "walls")
    if w1 > w0:
        mix.put(w0, env_fade(rattle(w1 - w0 + 0.3, rate=34, f=700, seed=3), 0.3, 0.4), 0.05, pan=-0.1)
        mix.put(w0, env_fade(rattle(w1 - w0 + 0.3, rate=22, f=1100, seed=4), 0.4, 0.4), 0.035, pan=0.15)
    n_ = {}
    for e in tl["parts"]:
        t, st, name, launch = e["t"], e["stage"], e["name"], e["launch"]
        n_[st] = n_.get(st, 0) + 1
        k = n_[st]
        p = random.uniform(-0.6, 0.6)
        if st == "slab":
            if k % 3 == 0:
                mix.put(t, thud(random.uniform(70, 95), 0.08, 0.3), 0.03, pan=p)
        elif st == "walls":
            if k % 9 == 0:
                mix.put(t, knock(random.uniform(190, 250), 0.09, 0.025, 0.55), 0.012, pan=p)
        elif st == "partitions":
            if k % 3 == 0:
                mix.put(t, knock(random.uniform(300, 380), 0.08, 0.02, 0.45), 0.012, pan=p)
        elif st == "openings":
            if name == "glass":
                mix.put(t, blip(random.uniform(2600, 3400), 0.2, 0.06), 0.008, pan=p)
            elif k % 3 == 0:
                mix.put(t, click(random.uniform(1700, 2400), 0.03), 0.012, pan=p)
        elif st == "floor":
            if k % 2 == 0:
                mix.put(t, knock(random.uniform(420, 540), 0.08, 0.02, 0.3), 0.012, pan=p)
        elif st in ("builtin", "furniture", "rug"):
            if e["size"] > 0.9:
                mix.put(t - 0.02, thud(random.uniform(60, 80), 0.1, 0.35), 0.02, pan=p * 0.5)
            elif k % 3 == 0:
                mix.put(t, knock(random.uniform(460, 640), 0.08, 0.02, 0.3), 0.01, pan=p)
        elif st == "decor":
            if name != "leaf" or k % 6 == 0:
                mix.put(t, pop(random.uniform(500, 700), random.uniform(900, 1300), 0.1), 0.008, pan=p)
        elif st == "ceiling":
            mix.put(t, slap(), 0.012, pan=p)
        elif st == "roof_frame":
            if k % 2 == 0:
                mix.put(t, knock(random.uniform(240, 320), 0.1, 0.03, 0.4), 0.012, pan=p)
        elif st == "roof":
            if name == "tile_row":
                mix.put(t, knock(random.uniform(850, 1100), 0.06, 0.012, 0.5), 0.012, pan=p)
                mix.put(t + 0.03, knock(random.uniform(700, 900), 0.05, 0.01, 0.4), 0.008, pan=-p)
            elif name in ("gutter", "downpipe", "swan_neck", "coping"):
                mix.put(t, blip(random.uniform(1500, 1900), 0.25, 0.08), 0.006, pan=p)
            else:
                mix.put(t, knock(random.uniform(600, 760), 0.08, 0.02, 0.35), 0.012, pan=p)
        if e["size"] > 2.0 and random.random() < 0.3:
            mix.put(launch, whoosh(max(0.3, t - launch), 500, 2400, 0.3), 0.005, pan=p)

    # ---------------------------------------------------------------- the wave: out of the front door to the horizon
    wv = T["wave"]
    mix.put(wv - 1.2, riser(1.2, 240, 3600), 0.014)
    mix.put(wv, impact(1.2), 0.01)
    mix.put(wv + 0.05, chime([hz("C5"), hz("E5"), hz("G5"), hz("B5")], 2.4, 0.9), 0.012)
    mix.put(wv, whoosh(2.6, 400, 3000, 0.35), 0.02)
    mix.put(wv + 0.6, env_fade(airy(T["door"] - wv - 0.6, 500, 1600, 0.6), 1.2, 0.6), 0.012)  # open air outside

    # ---------------------------------------------------------------- down to the terrace, over the threshold, the room
    mix.put(T["hero"], whoosh(T["ground"] - T["hero"], 1800, 400, 0.4), 0.02, pan=-0.15)
    mix.put(T["door"] - 0.05, thud(90, 0.06, 0.25), 0.02)
    try:
        tone = sample("fs-329533-room-tone-in-an-apartment-livi.ogg", 2.0, dur - T["door"] + 0.2)
        mix.put(T["door"] - 0.2, env_fade(tone, 0.6, 0.4), 0.25)
    except Exception as ex:  # no decoder for the sample: the room is quiet
        print("room tone skipped:", ex)
