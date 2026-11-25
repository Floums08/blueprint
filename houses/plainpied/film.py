"""The plain-pied house, the film: it opens on the builder's plan seen straight down, at its real scale, and the
camera spirals down while the house is built on the paper in white clay, each system flashing its colour as it lands:
the slab in 1 m tiles, the walls block by block, the plaster partitions, the windows and doors, the parquet, the
kitchen, the bathroom and the furniture, the ceiling sheets, the rafters and the tiles row by row from the eaves up.
Then a wave runs out from the front door: the paper becomes a garden, the clay becomes render, tiles, oak and glass,
the backdrop opens onto the sky and the sun drops to the afternoon. Last, the camera comes down onto the terrace,
through the open front door, and turns into the living room.

It runs build.py in film mode, lays the plan under it, wraps every material (clay -> real by the wave), keys the
parts, the camera and the light, renders frames and writes timeline.json for the sound (score.py) and the counter
(hud.py). The plan image is BLUEPRINT_PLAN or plan.png next to this file (it stays out of the repo).

Run (bpy from pip works the same with `python houses/plainpied/film.py -- ...`):
  blender -b --factory-startup -P houses/plainpied/film.py -- --res 960x540 --samples 12
      [--from 0 --to 21] [--step 4] [--out blueprint-out/plainpied/film] [--stills 0,6,13] [--no-render] [--blend]
Frames already on disk are skipped, so a stopped render resumes (delete an empty placeholder first).
"""
import json
import math
import os
import random
import sys
import time

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build.py")
if "--" not in sys.argv:
    sys.argv.append("--")
if "--film" not in sys.argv:
    sys.argv.append("--film")
G = {"__file__": BUILD, "__name__": "plainpied_build"}
exec(compile(open(BUILD, encoding="utf-8").read(), BUILD, "exec"), G)
K = G["K"]
scene, OPTS, M, P, W3, H, GROUND = G["scene"], G["OPTS"], G["M"], G["P"], G["W3"], G["H"], G["GROUND"]
t_start = time.time()

FPS = 24
T_END = 21.0
NF = int(round(T_END * FPS))
OUTDIR = os.path.abspath(str(OPTS.get("out", os.path.join(os.environ.get("BLUEPRINT_OUT", "blueprint-out"), "plainpied", "film"))))
os.makedirs(OUTDIR, exist_ok=True)


def F(t):
    return 1 + int(round(t * FPS))


def T(f):
    return (f - 1) / FPS


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smoother(x):
    x = clamp(x)
    return x * x * x * (x * (6 * x - 15) + 10)


def hermite(keys, t):
    """keys: [(t, value)], smooth through every key, zero speed at both ends."""
    ts = [k[0] for k in keys]
    vs = [k[1] for k in keys]
    if t <= ts[0]:
        return vs[0]
    if t >= ts[-1]:
        return vs[-1]
    i = max(j for j in range(len(ts) - 1) if ts[j] <= t)
    m = [0.0 if j in (0, len(ts) - 1) else (vs[j + 1] - vs[j - 1]) / (ts[j + 1] - ts[j - 1]) for j in range(len(ts))]
    h = ts[i + 1] - ts[i]
    s = (t - ts[i]) / h
    h00, h10, h01, h11 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
    return h00 * vs[i] + h10 * h * m[i] + h01 * vs[i + 1] + h11 * h * m[i + 1]


def bez(p0, p1, p2, p3, u):
    v = 1 - u
    return p0 * v ** 3 + p1 * 3 * v * v * u + p2 * 3 * v * u * u + p3 * u ** 3


def look(loc, tgt, roll=0.0):
    f = (tgt - loc).normalized()
    hz = Vector((f.x, f.y, 0))
    up = Vector((0, 0, 1)) + (hz.normalized() * 0.05 if hz.length > 1e-6 else Vector((0, 0.05, 0)))
    r = f.cross(up).normalized()
    u = r.cross(f).normalized()
    q = Matrix((r, u, -f)).transposed().to_quaternion()
    if roll:
        q = q @ Quaternion((0, 0, 1), roll)
    return q


# ---------------------------------------------------------------- the timeline
T_HOLD, T_DESC, T_ORBIT = 0.9, 4.2, 12.9
T_WAVE = 13.0  # the wave leaves the front door
T_HERO = 15.4  # the drift round the finished house ends
T_GROUND, T_DOOR, T_IN = 17.6, 18.9, 19.9  # on the terrace facing the door, on the threshold, turned into the room
WINDOWS = {  # stage: (first launch, last launch); walls and partitions go course by course instead
    "slab": (1.15, 2.5), "openings": (6.0, 7.5), "floor": (6.3, 7.3), "rug": (7.1, 7.3), "builtin": (7.0, 8.3),
    "furniture": (7.4, 8.9), "decor": (8.4, 9.5), "ceiling": (9.3, 10.1), "roof_frame": (9.9, 10.8),
}
COLORS = {  # the flash each system lands in (hud.py draws the same)
    "slab": (0.45, 0.55, 0.75), "walls": (1.0, 0.55, 0.12), "partitions": (1.0, 0.82, 0.18), "openings": (1.0, 0.36, 0.55),
    "floor": (0.95, 0.62, 0.32), "builtin": (0.62, 0.42, 1.0), "furniture": (0.62, 0.42, 1.0), "rug": (0.62, 0.42, 1.0),
    "decor": (0.62, 0.42, 1.0), "ceiling": (0.25, 0.85, 0.5), "roof_frame": (0.2, 0.8, 0.95), "roof": (0.2, 0.5, 1.0),
}
ROWS = [  # the counter's rows (hud.py)
    {"label": "Losa", "stages": ["slab"]}, {"label": "Muros", "stages": ["walls"]}, {"label": "Tabiques", "stages": ["partitions"]},
    {"label": "Carpintería", "stages": ["openings"]}, {"label": "Suelos", "stages": ["floor"]},
    {"label": "Equipamiento", "stages": ["builtin", "furniture", "rug", "decor"]}, {"label": "Techos", "stages": ["ceiling"]},
    {"label": "Estructura", "stages": ["roof_frame"]}, {"label": "Cubierta", "stages": ["roof"]},
]
for r in ROWS:
    r["color"] = COLORS[r["stages"][0]]
CLAY = (0.8, 0.79, 0.76)
DOOR_PT = W3(1.7, 4.1, 1.0)  # the wave's source: the front door

# ---------------------------------------------------------------- the plan on the table, at its real scale
WJ = json.load(open(os.path.join(HERE, "walls.json")))
PSX, PSY = WJ["px_per_m"]
POX, POY = WJ["origin_px"]
PLAN_IMG = os.environ.get("BLUEPRINT_PLAN", os.path.join(HERE, "plan.png"))
if os.path.exists(PLAN_IMG):
    img = bpy.data.images.load(PLAN_IMG, check_existing=True)
else:
    print("WARNING: no plan image (BLUEPRINT_PLAN): the film opens on a blank sheet")
    img = bpy.data.images.new("plan_blank", 1754, 1240)
    img.generated_color = (1, 1, 1, 1)
IW, IH = img.size
SX0, SX1, SY0, SY1 = -POX / PSX, (IW - POX) / PSX, -POY / PSY, (IH - POY) / PSY  # the sheet's edges, plan metres
SHEET_C = ((SX0 + SX1) / 2, (SY0 + SY1) / 2)
Z_SHEET = GROUND + 0.004


def sheet_mat():
    m, N, L, b = K.new_mat("sheet")
    tex = N.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Cubic"
    tex.extension = "CLIP"
    L.new(N.new("ShaderNodeTexCoord").outputs["UV"], tex.inputs["Vector"])
    L.new(tex.outputs["Color"], b.inputs["Base Color"])
    K.inp(b, "Roughness", 0.9)
    K.inp(b, ["Specular IOR Level", "Specular"], 0.1)
    return m


def desk_mat():
    m, N, L, b = K.new_mat("desk")
    v = N.new("ShaderNodeTexCoord").outputs["Object"]
    n = K.noise_tex(N, L, v, 3.0, 4.0, 0.6)
    L.new(K.mix_rgb(N, L, n, (0.74, 0.72, 0.68), (0.8, 0.78, 0.74)), b.inputs["Base Color"])
    K.inp(b, "Roughness", 0.6)
    return m


me = bpy.data.meshes.new("sheet")
corners = [(SX0, SY1), (SX1, SY1), (SX1, SY0), (SX0, SY0)]  # bottom-left, bottom-right, top-right, top-left of the image
me.from_pydata([tuple(W3(x, y, Z_SHEET)) for x, y in corners], [], [(0, 1, 2, 3)])
uvl = me.uv_layers.new(name="UVMap")
for li, uv in zip(range(4), ((0, 0), (1, 0), (1, 1), (0, 1))):
    uvl.data[li].uv = uv
me.materials.append(sheet_mat())
SHEET = bpy.data.objects.new("sheet", me)
scene.collection.objects.link(SHEET)
sc_ = W3(*SHEET_C, 0)
DESK = K.box("desk", sc_.x - 60, sc_.x + 60, sc_.y - 60, sc_.y + 60, GROUND - 0.004, GROUND + 0.002, desk_mat(), bevel=0.0)
K.PARTS.pop()  # the desk is not a part
print(f"plan sheet {SX1 - SX0:.2f} x {SY1 - SY0:.2f} m, {IW} x {IH} px")

# ---------------------------------------------------------------- the wave: one node group every material reads
WG = bpy.data.node_groups.new("wave", "ShaderNodeTree")
WG.interface.new_socket("alive", in_out="OUTPUT", socket_type="NodeSocketFloat")
WG.interface.new_socket("edge", in_out="OUTPUT", socket_type="NodeSocketFloat")
gn, gl = WG.nodes, WG.links
g_out = gn.new("NodeGroupOutput")
geo = gn.new("ShaderNodeNewGeometry")
dist = gn.new("ShaderNodeVectorMath")
dist.operation = "DISTANCE"
gl.new(geo.outputs["Position"], dist.inputs[0])
dist.inputs[1].default_value = DOOR_PT
R = gn.new("ShaderNodeValue")
R.outputs[0].default_value = -10.0
BAND = gn.new("ShaderNodeValue")
BAND.outputs[0].default_value = 1.2
d_r = K.math_node(gn, gl, "SUBTRACT", R.outputs[0], dist.outputs["Value"])  # > 0 inside the front
alive = gn.new("ShaderNodeMapRange")
alive.interpolation_type = "SMOOTHERSTEP"
gl.new(K.math_node(gn, gl, "DIVIDE", d_r, BAND.outputs[0]), alive.inputs["Value"])
gl.new(alive.outputs[0], g_out.inputs["alive"])
edge = gn.new("ShaderNodeMapRange")
edge.inputs["From Max"].default_value = 0.35
edge.inputs["To Min"].default_value = 1.0
edge.inputs["To Max"].default_value = 0.0
gl.new(K.math_node(gn, gl, "ABSOLUTE", K.math_node(gn, gl, "DIVIDE", d_r, BAND.outputs[0])), edge.inputs["Value"])
gl.new(edge.outputs[0], g_out.inputs["edge"])
# out past the horizon before the sky opens: until then the backdrop beyond the front stays the plain studio grey
WAVE_KEYS = [(T_WAVE, -1.5), (T_WAVE + 0.6, 3.0), (T_WAVE + 1.4, 12.0), (T_WAVE + 2.0, 45.0), (T_WAVE + 2.7, 4000.0)]


def R_at(t):
    """the front's distance from the door: eased out of the doorway, then spreading geometrically to the horizon"""
    ks = WAVE_KEYS
    if t <= ks[0][0]:
        return ks[0][1]
    if t >= ks[-1][0]:
        return ks[-1][1]
    i = max(j for j in range(len(ks) - 1) if ks[j][0] <= t)
    u = (t - ks[i][0]) / (ks[i + 1][0] - ks[i][0])
    a, b = ks[i][1], ks[i + 1][1]
    return a + (b - a) * smoother(u) if i == 0 else a * (b / a) ** u


def reach(d):
    """when the wave front gets to a distance from the door"""
    f = F(T_WAVE)
    while R_at(T(f)) < d and f < NF:
        f += 1
    return T(f)


for f in range(1, NF + 1):
    if f == 1 or F(T_WAVE - 0.2) <= f <= F(T_WAVE + 3.0) or f == NF:
        R.outputs[0].default_value = R_at(T(f))
        R.outputs[0].keyframe_insert("default_value", frame=f)
BAND.outputs[0].keyframe_insert("default_value", frame=F(T_WAVE + 1.6))
BAND.outputs[0].default_value = 20.0
BAND.outputs[0].keyframe_insert("default_value", frame=F(T_WAVE + 3.4))

SITE_MATS = {M[k].name for k in ("lawn", "gravel", "terrace", "leaf_dark", "leaf_tree", "bark_tree")}
PAPER_MATS = {"sheet", "desk"}


def output_src(m):
    out = next((n for n in m.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    if not out or not out.inputs["Surface"].links:
        return None, None
    return out, out.inputs["Surface"].links[0].from_socket


def wrap(m):
    """Clay outside the wave, the real material inside; the site appears inside it, the paper goes."""
    if not m or not m.use_nodes or m.get("wrapped") or m.name == "label":
        return
    out, src = output_src(m)
    if src is None:
        return
    N, L = m.node_tree.nodes, m.node_tree.links
    g = N.new("ShaderNodeGroup")
    g.node_tree = WG
    mix = N.new("ShaderNodeMixShader")
    L.new(g.outputs["alive"], mix.inputs[0])
    tr = N.new("ShaderNodeBsdfTransparent")
    m["wrapped"] = True
    if m.name in PAPER_MATS:
        L.new(src, mix.inputs[1])
        L.new(tr.outputs[0], mix.inputs[2])
        L.new(mix.outputs[0], out.inputs["Surface"])
        return
    if m.name in SITE_MATS:
        L.new(tr.outputs[0], mix.inputs[1])
        L.new(src, mix.inputs[2])
        L.new(mix.outputs[0], out.inputs["Surface"])
        return
    clay = N.new("ShaderNodeBsdfPrincipled")
    K.inp(clay, "Roughness", 0.55)
    fl = N.new("ShaderNodeAttribute")
    fl.attribute_type = "OBJECT"
    fl.attribute_name = "flash"
    tn = N.new("ShaderNodeAttribute")
    tn.attribute_type = "OBJECT"
    tn.attribute_name = "tint"
    L.new(K.mix_rgb(N, L, fl.outputs["Fac"], CLAY, tn.outputs["Vector"]), clay.inputs["Base Color"])
    L.new(tn.outputs["Vector"], clay.inputs["Emission Color"])
    L.new(K.math_node(N, L, "MULTIPLY", fl.outputs["Fac"], 1.6), clay.inputs["Emission Strength"])
    L.new(clay.outputs[0], mix.inputs[1])
    L.new(src, mix.inputs[2])
    ed = N.new("ShaderNodeEmission")  # a warm line where the wave passes
    ed.inputs["Color"].default_value = (1.0, 0.62, 0.32, 1)
    L.new(K.math_node(N, L, "MULTIPLY", g.outputs["edge"], float(OPTS.get("edge", 1.5))), ed.inputs["Strength"])
    add = N.new("ShaderNodeAddShader")
    L.new(mix.outputs[0], add.inputs[0])
    L.new(ed.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs["Surface"])


for m_ in list(bpy.data.materials):
    wrap(m_)
print("materials wrapped")

# ---------------------------------------------------------------- the camera
ORBIT = {  # elevation, azimuth (deg, from east, counter-clockwise), distance, target (plan x, y, height), lens
    "el": [(0, 90.0), (T_HOLD, 90.0), (T_DESC, 54.0), (8.5, 47.0), (11.0, 40.0), (T_ORBIT, 31.0), (T_HERO, 19.0)],
    "az": [(0, 270.0), (T_HOLD, 270.0), (T_DESC, 232.0), (8.5, 219.0), (11.0, 212.0), (T_ORBIT, 215.0), (T_HERO, 229.0)],
    "dist": [(0, 24.5), (T_HOLD, 24.5), (T_DESC, 23.0), (8.5, 22.0), (11.0, 21.5), (T_ORBIT, 20.5), (T_HERO, 18.5)],
    "tx": [(0, SHEET_C[0]), (T_HOLD, SHEET_C[0]), (T_DESC, 5.9), (T_ORBIT, 5.8), (T_HERO, 5.0)],
    "ty": [(0, SHEET_C[1]), (T_HOLD, SHEET_C[1]), (T_DESC, 4.6), (T_ORBIT, 4.7), (T_HERO, 4.9)],
    "tz": [(0, 0.0), (T_HOLD, 0.0), (T_DESC, 0.6), (8.5, 0.8), (11.0, 1.0), (T_ORBIT, 1.4), (T_HERO, 1.5)],
    "lens": [(0, 50.0), (T_HOLD, 50.0), (T_DESC, 34.0), (8.5, 32.0), (T_ORBIT, 30.0), (T_HERO, 28.0)],
}


def orbit(t):
    el = math.radians(min(hermite(ORBIT["el"], t), 89.99))  # never tip over the top
    az = math.radians(hermite(ORBIT["az"], t))
    tgt = W3(hermite(ORBIT["tx"], t), hermite(ORBIT["ty"], t), hermite(ORBIT["tz"], t))
    off = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))) * hermite(ORBIT["dist"], t)
    return tgt + off, tgt, hermite(ORBIT["lens"], t)


EYE = 1.58
H_P, H_T, _ = orbit(T_HERO)
TERRACE, DOOR_LOOK = W3(-4.6, 4.15, EYE), W3(1.7, 4.1, 1.35)
THRESH = W3(1.6, 4.1, EYE - 0.03)
INSIDE_LOOK0 = W3(4.2, 4.2, 1.25)  # through the door: the open kitchen and the corridor
ROOM, ROOM_LOOK = W3(3.05, 4.5, 1.45), W3(4.15, 8.6, 0.95)  # turned to the living room: sofa, table, the south window


def cam_at(t):
    """location, rotation, lens"""
    if t <= T_HERO:
        loc, tgt, lens = orbit(t)
        return loc, look(loc, tgt), lens
    if t <= T_GROUND:  # down from the hero view onto the terrace, facing the front door
        u = smoother((t - T_HERO) / (T_GROUND - T_HERO))
        loc = bez(H_P, H_P.lerp(TERRACE, 0.35) + Vector((0, 0, 3.0)), TERRACE + Vector((-3.5, 1.2, 1.2)), TERRACE, u)
        tgt = H_T.lerp(DOOR_LOOK, smoother(u * 1.2))
        return loc, look(loc, tgt), 28 + (24 - 28) * u
    if t <= T_DOOR:  # across the terrace and onto the threshold
        u = (t - T_GROUND) / (T_DOOR - T_GROUND)
        u = u * u * (3 - 2 * u) * 0.75 + u * 0.25
        loc = TERRACE.lerp(THRESH, u)
        tgt = DOOR_LOOK.lerp(INSIDE_LOOK0, smoother(u * 1.3 - 0.3))
        return loc, look(loc, tgt), 24 + (21 - 24) * u
    u = smoother((t - T_DOOR) / (T_IN - T_DOOR))  # in, turning right to the room
    loc = bez(THRESH, THRESH + Vector((0.7, 0.0, 0.0)), ROOM + Vector((-0.35, 0.2, 0.0)), ROOM, u)
    k = smoother((t - T_DOOR) / (T_IN + 0.5 - T_DOOR))
    tgt = INSIDE_LOOK0.lerp(ROOM_LOOK, k)
    drift = smoother((t - T_IN) / (T_END - T_IN))  # a slow drift on into the room
    loc = loc + (ROOM_LOOK - ROOM).normalized() * 0.25 * drift
    return loc, look(loc, tgt), 21 + (19 - 21) * u


cd = bpy.data.cameras.new("film_cam")
cd.sensor_width = 36
cd.clip_start = 0.04
cd.clip_end = 2000
cam = bpy.data.objects.new("film_cam", cd)
scene.collection.objects.link(cam)
cam.rotation_mode = "QUATERNION"
scene.camera = cam
CAM = [cam_at(T(f)) for f in range(1, NF + 1)]
prev = None
for f, (loc, q, lens) in zip(range(1, NF + 1), CAM):
    if prev is not None and prev.dot(q) < 0:
        q = -q
    prev = q
    cam.location = loc
    cam.rotation_quaternion = q
    cd.lens = lens
    # while the counter card is up (top-left), the house sits right of centre
    t = T(f)
    cd.shift_x = -0.1 * smoother((t - T_HOLD) / (T_DESC - T_HOLD)) * (1 - smoother((t - (T_WAVE + 0.4)) / 1.4))
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_quaternion", frame=f)
    cd.keyframe_insert("lens", frame=f)
    cd.keyframe_insert("shift_x", frame=f)
CAM_X = [c[0].x + G["CX"] for c in CAM]  # the camera's plan x: inside the house past the west wall

# ---------------------------------------------------------------- the build: every part lands in clay with its system's flash
rng = random.Random(86)
SKIP_COLL = {G["COLL"]["labels"].name, G["COLL"]["catcher"].name}
parts = [(o, st) for o, st in K.PARTS if o.type == "MESH" and not any(c.name in SKIP_COLL for c in o.users_collection)]
for o, st in parts:
    o["rest"] = tuple(o.location)  # materials read it: a part keeps its pattern in flight and lines up when it lands
    o["tint"] = COLORS.get(st, (0.8, 0.8, 0.8))
    o["flash"] = 0.0


def perim(o):
    """0..1 round the house, from the front door clockwise: walls rise as a running course, not all at once"""
    x, y = o.location.x + G["CX"], G["CY"] - o.location.y
    a = math.atan2(y - 4.6, x - 5.9)
    return ((a - math.atan2(4.1 - 4.6, 1.7 - 5.9)) % (2 * math.pi)) / (2 * math.pi)


sched = []  # (object, stage, launch, duration, style)
by = {}
for o, st in parts:
    by.setdefault(st, []).append(o)
for o in by.get("walls", []):
    c = o.get("course", 0)
    sched.append((o, "walls", 2.25 + c * 0.29 + perim(o) * 0.28 + rng.uniform(0, 0.12), 0.5 + rng.uniform(0, 0.1), "drop"))
for o in by.get("partitions", []):
    c = o.get("course", 0)
    sched.append((o, "partitions", 3.1 + c * 0.62 + perim(o) * 0.3 + rng.uniform(0, 0.15), 0.55 + rng.uniform(0, 0.1), "drop"))
for o in by.get("roof", []):
    nm = o.name.split(".")[0]
    if nm == "tile_row":
        ts = 10.7 + (o.get("row", 1) - 1) * 0.2 + rng.uniform(0, 0.15)
    elif nm in ("flat_roof", "coping"):
        ts = 10.6 + rng.uniform(0, 0.3)
    elif nm in ("gutter", "swan_neck", "downpipe"):
        ts = 11.3 + rng.uniform(0, 0.4)
    else:  # ridge rolls on top
        ts = 12.35 + rng.uniform(0, 0.2)
    sched.append((o, "roof", ts, 0.55 + rng.uniform(0, 0.1), "drop" if nm == "tile_row" else "fly"))
for st, (a, b) in WINDOWS.items():
    objs = by.get(st, [])
    if st == "slab":
        objs = sorted(objs, key=lambda o: o.location.x + rng.uniform(-0.6, 0.6))
    elif st in ("floor", "ceiling", "roof_frame"):
        objs = sorted(objs, key=lambda o: o.location.x - o.location.y * 0.3 + rng.uniform(-0.5, 0.5))
    else:
        objs = sorted(objs, key=lambda o: perim(o) + rng.uniform(-0.15, 0.15))
    style = "drop" if st in ("slab", "floor", "ceiling", "roof_frame") else "fly"
    for i, o in enumerate(objs):
        ts = a + (b - a) * (i / max(1, len(objs) - 1)) + rng.uniform(-0.08, 0.08)
        sched.append((o, st, max(0.9, ts), (0.5 if style == "drop" else 0.85) + rng.uniform(0, 0.25), style))


def back(u, s=1.15):
    return 1 + (s + 1) * (u - 1) ** 3 + s * (u - 1) ** 2


events = []
t_key = time.time()
for o, st, ts, dur, style in sched:
    rest_l, rest_r, rest_s = o.location.copy(), o.rotation_euler.copy(), o.scale.copy()
    land = ts + dur
    if style == "drop":  # straight down from a few metres up, a little turn
        off = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(2.5, 4.5)))
        lift = Vector((0, 0, 0))
        spin = Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), rng.uniform(-0.6, 0.6)))
    else:  # in from somewhere around, over an arc
        az = rng.uniform(0, 2 * math.pi)
        el = rng.uniform(0.15, 1.0)
        off = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))) * rng.uniform(7, 15)
        lift = Vector((0, 0, rng.uniform(1.0, 2.5)))
        spin = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized() * rng.uniform(0.6, 1.3)
    f0, f1 = F(ts), F(land)
    o.scale = (0, 0, 0)
    o.location = rest_l + off
    o.keyframe_insert("scale", frame=max(1, f0 - 1))
    o.keyframe_insert("location", frame=max(1, f0 - 1))
    for f in range(f0, f1 + 1):
        u = clamp((T(f) - ts) / dur)
        w = 1 - back(u)
        o.location = rest_l + off * (w * w) + lift * (2 * w * (1 - w))
        o.rotation_euler = (rest_r.x + spin.x * w, rest_r.y + spin.y * w, rest_r.z + spin.z * w)
        k = 0.6 + 0.4 * (1 - w)
        o.scale = (rest_s.x * k, rest_s.y * k, rest_s.z * k)
        o.keyframe_insert("location", frame=f)
        o.keyframe_insert("rotation_euler", frame=f)
        o.keyframe_insert("scale", frame=f)
    o.location, o.rotation_euler, o.scale = rest_l, rest_r, rest_s
    o["flash"] = 0.0
    o.keyframe_insert('["flash"]', frame=1)
    o["flash"] = 1.0
    o.keyframe_insert('["flash"]', frame=max(2, F(land - 0.2)))
    o.keyframe_insert('["flash"]', frame=F(land + 0.05))
    o["flash"] = 0.0
    o.keyframe_insert('["flash"]', frame=F(land + 0.7))
    nm = o.name.split(".")[0]
    events.append({"t": round(land, 3), "launch": round(ts, 3), "stage": st, "name": nm,
                   "size": round(max(o.dimensions), 3), "count": nm not in ("leaf", "stem")})
print(f"keyed {len(sched)} parts in {time.time() - t_key:.1f} s")

# the garden grows where the wave reaches it; the lawn, the terrace and the paths are the site materials
n_site = 0
for o in by.get("site", []):
    nm = o.name.split(".")[0]
    if nm in ("lawn", "terrace", "path", "planter_bed"):
        continue
    t0_ = reach((o.location - DOOR_PT).length * 0.9)
    s0 = o.scale.copy()
    o.scale = (0, 0, 0)
    o.keyframe_insert("scale", frame=1)
    o.keyframe_insert("scale", frame=F(t0_))
    for j, kk in ((1, 1.08), (2, 1.0)):
        o.scale = s0 * kk
        o.keyframe_insert("scale", frame=F(t0_ + 0.35 * j))
    n_site += 1
print(f"site pieces timed to the wave: {n_site}")

# ---------------------------------------------------------------- light: a plain backdrop while it is built, then the sky and the afternoon sun
G["show"](interior=True, roof=True, site=True)
G["portals"](True)
WN, WL = G["WN"], G["WL"]
cam_mix, lp_ = G["cam_mix"], G["lp_"]
for lk in list(cam_mix.inputs[0].links):
    WL.remove(lk)
open_sky = WN.new("ShaderNodeValue")
WL.new(K.math_node(WN, WL, "MULTIPLY", lp_.outputs["Is Camera Ray"], open_sky.outputs[0]), cam_mix.inputs[0])
bg, sun, so, aim_sun = G["bg"], G["sun"], G["so"], G["aim_sun"]
bg.inputs["Strength"].default_value = 0.07
for f in sorted({1, F(T_WAVE + 1.6), F(T_WAVE + 2.0), F(T_WAVE + 2.4), F(T_WAVE + 2.8), NF}):
    t = T(f)
    k = smoother((t - (T_WAVE + 1.6)) / 1.2)
    open_sky.outputs[0].default_value = 1 - k
    open_sky.outputs[0].keyframe_insert("default_value", frame=f)
for f in range(1, NF + 1, 2):
    t = T(f)
    k = smoother((t - (T_WAVE + 0.4)) / 3.2)  # the sun swings round and down to the afternoon
    aim_sun(222 + 18 * k, 52 - 20 * k, 3.4 + 0.6 * k)
    so.keyframe_insert("rotation_euler", frame=f)
    sun.keyframe_insert("energy", frame=f)
    k_in = smoother((CAM_X[f - 1] - 1.0) / 1.4) if t > T_GROUND else 0.0  # the eye opens up indoors
    k_w = smoother((t - (T_WAVE + 0.3)) / 2.3)  # white clay on a pale backdrop needs less light than the finished house
    scene.view_settings.exposure = float(OPTS.get("build_ev", -0.7)) * (1 - k_w) + 1.35 * k_in
    scene.view_settings.keyframe_insert("exposure", frame=f)
M["shade"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 2.0

# ---------------------------------------------------------------- timeline for the sound and the counter
TL = {"duration": T_END, "fps": FPS, "T": {"hold": T_HOLD, "descent": T_DESC, "orbit_end": T_ORBIT, "wave": T_WAVE,
                                          "hero": T_HERO, "ground": T_GROUND, "door": T_DOOR, "inside": T_IN},
      "rows": ROWS, "parts": sorted(events, key=lambda e: e["t"]),
      "title": "CASA DE UNA PLANTA", "subtitle": "86 m²  ·  3 dormitorios  ·  desde el plano"}
json.dump(TL, open(os.path.join(HERE, "timeline.json"), "w"), indent=0, ensure_ascii=False)
print(f"timeline: {len(events)} landings, {sum(1 for e in events if e['count'])} counted")

# ---------------------------------------------------------------- render: tuned for a CPU (no motion blur, few bounces, denoised)
rx, ry = map(int, str(OPTS.get("res", "960x540")).split("x"))
scene.render.resolution_x, scene.render.resolution_y = rx, ry
cy_ = scene.cycles
cy_.samples = int(OPTS.get("samples", 12))
cy_.adaptive_threshold = float(OPTS.get("noise", 0.04))
cy_.max_bounces, cy_.diffuse_bounces, cy_.glossy_bounces, cy_.transmission_bounces, cy_.transparent_max_bounces = 6, 3, 2, 4, 8
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, NF
if "from" in OPTS:
    scene.frame_start = F(float(OPTS["from"]))
if "to" in OPTS:
    scene.frame_end = min(NF, F(float(OPTS["to"])))
scene.frame_step = int(OPTS.get("step", 1))
scene.render.use_motion_blur = False
scene.render.use_persistent_data = False  # with it on, parts that were scaled to 0 can render black once they appear
scene.render.film_transparent = False
scene.render.use_overwrite = False  # resume: frames on disk are skipped
scene.render.use_placeholder = True
scene.render.filepath = os.path.join(OUTDIR, "f_")
scene.render.image_settings.file_format = "PNG"
print(f"set up in {time.time() - t_start:.1f} s; frames {scene.frame_start}-{scene.frame_end} step {scene.frame_step}, {rx}x{ry}, {cy_.samples} samples")
if OPTS.get("blend"):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.dirname(OUTDIR), "film.blend"))
if OPTS.get("stills"):
    for tt in str(OPTS["stills"]).split(","):
        scene.frame_set(F(float(tt)))
        scene.render.filepath = os.path.join(OUTDIR, f"still_{float(tt):05.2f}.png")
        t1 = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"still {tt} s in {time.time() - t1:.1f} s")
elif not OPTS.get("no-render"):
    bpy.ops.render.render(animation=True)
    print(f"rendered in {time.time() - t_start:.1f} s")
