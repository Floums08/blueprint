"""A single-storey 3-bedroom house (86 m2) in Blender, built from a builder's brochure plan.

Everything comes from plan.json (walls, openings, rooms, kitchen, furniture, site), read off the plan with
extract_walls.py and grid_view.py. Exterior walls are cut in two layers along their thickness, so the outer layer
carries the render into the window reveals and the inner layer the paint; the window frames sit at the joint.
Doors stand open at the angle the plan draws them. The roof is a 22 deg hipped roof in Roman tiles over the main
block; the cellier is a lower annex with a flat roof behind a parapet. Materials are procedural (no downloads),
so the scene builds anywhere bpy runs.

Run:
  blender -b --factory-startup -P houses/plainpied/build.py -- top dollhouse exterior living --samples 128 --res 1600x900
  python -c "import bpy" works too: python houses/plainpied/build.py -- top   (bpy from pip)
Shots: top (orthographic, to lay over the plan with compare.py), dollhouse, exterior, living, kitchen, bedroom.
Stills land in blueprint-out/plainpied/render_<shot>.png; --blend also saves the scene there.
"""
import json
import math
import os
import random
import sys
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "kit"))
import bpy  # noqa: E402  (first: with bpy from pip, bmesh only exists once bpy is imported)
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

import bkit as K  # noqa: E402
from bkit import bump_into, math_node, mix_rgb, new_mat, inp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = json.load(open(os.path.join(HERE, "plan.json")))
OPTS, SHOTS = K.args(("top", "dollhouse", "exterior", "living"))
scene = K.setup(OPTS, samples=128, res="1600x900")
OUT = os.path.join(os.environ.get("BLUEPRINT_OUT", "blueprint-out"), "plainpied")
os.makedirs(OUT, exist_ok=True)
random.seed(11)
t0 = time.time()

H = PLAN["ceiling"]
TOP = PLAN["wall_top"]
DOOR = PLAN["door_head"]
WIN = PLAN["window_head"]
CX, CY = 5.9, 4.6  # plan point at the world origin
GROUND = -0.22
OUTLINE = PLAN["outline"]
WALLS = {w["id"]: w for w in PLAN["walls"]}
IN_LAYER = 0.10  # inner (painted) layer of an exterior wall; the window frames sit on its outer face


def P(x, y):
    """Plan (x east, y south) to world (X east, Y north)."""
    return Vector((x - CX, CY - y))


def W3(x, y, z):
    p = P(x, y)
    return Vector((p.x, p.y, z))


# ---------------------------------------------------------------- collections: what each shot shows
ROOT = K.ROOT
COLL = {}
for cname in ("interior", "roof", "site", "labels", "catcher"):
    COLL[cname] = bpy.data.collections.new(cname)
    ROOT.children.link(COLL[cname])


@contextmanager
def into(cname):
    """Objects made inside this block land in that collection (bkit links to K.ROOT)."""
    prev = K.ROOT
    K.ROOT = COLL[cname]
    try:
        yield
    finally:
        K.ROOT = prev


def stage(s):
    K.STAGE[0] = s


# ---------------------------------------------------------------- procedural materials
def principled(name, color, rough=0.5, metal=0.0, emission=None, estr=0.0, sheen=0.0, coat=0.0):
    m = K.principled(name, color, rough, metal, emission, estr)
    b = m.node_tree.nodes["Principled BSDF"]
    if sheen:
        inp(b, ["Sheen Weight", "Sheen"], sheen)
    if coat:
        inp(b, ["Coat Weight", "Clearcoat"], coat)
    return m


def coord(N, L, space="Object"):
    tc = N.new("ShaderNodeTexCoord")
    return tc.outputs[space]


def swizzle(N, L, v, order):
    """Reorder a vector's axes ('yxz' swaps x and y), so one pattern can run along either wall direction."""
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(v, sep.inputs[0])
    cb = N.new("ShaderNodeCombineXYZ")
    for k, ch in enumerate(order):
        L.new(sep.outputs["xyz".index(ch)], cb.inputs[k])
    return cb.outputs[0]


def grain(N, L, v, scale, detail=6.0):
    """Fine noise in 0..1 around 0.5."""
    return K.noise_tex(N, L, v, scale, detail, 0.6)


def plaster(name, color, rough=0.92, bump=0.08, scale=60.0, vary=0.04):
    """Paint or render: a flat colour, a faint cloudy variation and a fine bump."""
    m, N, L, b = new_mat(name)
    v = coord(N, L)
    n1 = grain(N, L, v, 2.0, 3.0)
    c = mix_rgb(N, L, n1, tuple(max(0, k - vary) for k in color), tuple(min(1, k + vary) for k in color))
    L.new(c, b.inputs["Base Color"])
    inp(b, "Roughness", rough)
    bump_into(N, L, b, grain(N, L, v, scale), bump, 0.002)
    return m


def tiles(name, c1, c2, joint, w, h, offset=0.0, rough=0.3, joint_w=0.003, bump=0.35, swap=False, vary=0.5, glaze=0.0):
    """Floor or wall tiles: a brick grid in object coordinates (metres), each tile its own shade, sunk joints."""
    m, N, L, b = new_mat(name)
    v = coord(N, L)
    if swap:
        v = swizzle(N, L, v, "yxz")
    br = N.new("ShaderNodeTexBrick")
    br.offset = offset
    br.offset_frequency = 2
    br.squash_frequency = 1
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = w
    br.inputs["Row Height"].default_value = h
    br.inputs["Mortar Size"].default_value = joint_w
    br.inputs["Mortar Smooth"].default_value = 0.3
    br.inputs["Bias"].default_value = 0.0
    br.inputs["Color1"].default_value = (*c1, 1)
    br.inputs["Color2"].default_value = (*c2, 1)
    br.inputs["Mortar"].default_value = (*joint, 1)
    L.new(v, br.inputs["Vector"])
    cloud = grain(N, L, v, 1.5, 3.0)
    col = mix_rgb(N, L, vary * 0.35, br.outputs["Color"], mix_rgb(N, L, cloud, (0.92, 0.92, 0.92), (1.06, 1.05, 1.03)), "MULTIPLY")
    L.new(col, b.inputs["Base Color"])
    r = math_node(N, L, "MULTIPLY_ADD", br.outputs["Fac"], 0.5, rough)
    L.new(r, b.inputs["Roughness"])
    if glaze:
        inp(b, ["Coat Weight", "Clearcoat"], glaze)
    inv = math_node(N, L, "SUBTRACT", 1.0, br.outputs["Fac"])
    bump_into(N, L, b, inv, bump, 0.002)
    return m


def wood(name, light, dark, scale=1.0, rough=0.45, boards=None, swap=False):
    """Oak: wave-texture rings stretched along x, a noise to break them up; optionally laid in boards."""
    m, N, L, b = new_mat(name)
    v = coord(N, L)
    if swap:
        v = swizzle(N, L, v, "yxz")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.35 * scale, 6.0 * scale, 6.0 * scale)
    L.new(v, mp.inputs["Vector"])
    wv = N.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = "Y"
    wv.inputs["Scale"].default_value = 1.6
    wv.inputs["Distortion"].default_value = 6.0
    wv.inputs["Detail"].default_value = 3.0
    wv.inputs["Detail Scale"].default_value = 1.5
    L.new(mp.outputs[0], wv.inputs["Vector"])
    n = grain(N, L, mp.outputs[0], 3.0, 4.0)
    f = math_node(N, L, "MULTIPLY_ADD", wv.outputs["Fac"], 0.6, math_node(N, L, "MULTIPLY", n, 0.4))
    col = K.ramp(N, L, f, [(0.25, light), (0.75, dark)])
    if boards:
        bw, bl = boards
        br = N.new("ShaderNodeTexBrick")
        br.offset = 0.37
        br.inputs["Scale"].default_value = 1.0
        br.inputs["Brick Width"].default_value = bl
        br.inputs["Row Height"].default_value = bw
        br.inputs["Mortar Size"].default_value = 0.0015
        br.inputs["Color1"].default_value = (1, 1, 1, 1)
        br.inputs["Color2"].default_value = (0.8, 0.78, 0.76, 1)
        br.inputs["Mortar"].default_value = (0.25, 0.2, 0.16, 1)
        L.new(v, br.inputs["Vector"])
        col = mix_rgb(N, L, 1.0, col, br.outputs["Color"], "MULTIPLY")
        bump_into(N, L, b, math_node(N, L, "SUBTRACT", 1.0, br.outputs["Fac"]), 0.25, 0.002)
    L.new(col, b.inputs["Base Color"])
    inp(b, "Roughness", rough)
    return m


def fabric(name, color, rough=0.9, bump=0.25, scale=260.0):
    m, N, L, b = new_mat(name)
    inp(b, "Base Color", (*color, 1))
    inp(b, "Roughness", rough)
    inp(b, ["Sheen Weight", "Sheen"], 0.5)
    v = coord(N, L)
    bump_into(N, L, b, grain(N, L, v, scale, 2.0), bump, 0.001)
    return m


def roof_tiles(name, along_y=False):
    """Roman clay tiles: courses every 0.34 m up the slope, a rounded roll every 0.22 m, each tile its own red."""
    m, N, L, b = new_mat(name)
    v = coord(N, L)
    if along_y:
        v = swizzle(N, L, v, "yxz")
    br = N.new("ShaderNodeTexBrick")
    br.offset = 0.5
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 0.44
    br.inputs["Row Height"].default_value = 0.315
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Mortar Smooth"].default_value = 0.8
    br.inputs["Color1"].default_value = (0.50, 0.2, 0.1, 1)
    br.inputs["Color2"].default_value = (0.62, 0.3, 0.16, 1)
    br.inputs["Mortar"].default_value = (0.2, 0.08, 0.05, 1)
    br.inputs["Bias"].default_value = 0.0
    L.new(v, br.inputs["Vector"])
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(v, sep.inputs[0])
    roll = math_node(N, L, "SINE", math_node(N, L, "MULTIPLY", sep.outputs[0], 2 * math.pi / 0.22))
    roll = math_node(N, L, "ABSOLUTE", roll)
    dirt = grain(N, L, v, 0.8, 3.0)
    col = mix_rgb(N, L, math_node(N, L, "MULTIPLY", dirt, 0.6), br.outputs["Color"], (0.36, 0.27, 0.22))
    col = mix_rgb(N, L, math_node(N, L, "MULTIPLY", math_node(N, L, "SUBTRACT", 1.0, roll), 0.35), col, (0.25, 0.1, 0.06))
    L.new(col, b.inputs["Base Color"])
    inp(b, "Roughness", 0.75)
    h = math_node(N, L, "ADD", math_node(N, L, "MULTIPLY", roll, 0.7), math_node(N, L, "MULTIPLY", math_node(N, L, "SUBTRACT", 1.0, br.outputs["Fac"]), 0.6))
    bump_into(N, L, b, h, 0.9, 0.03)
    return m


def lawn(name):
    m, N, L, b = new_mat(name)
    v = coord(N, L)
    big = grain(N, L, v, 0.25, 4.0)
    fine = grain(N, L, v, 90.0, 2.0)
    c = K.ramp(N, L, big, [(0.35, (0.10, 0.17, 0.05)), (0.65, (0.20, 0.27, 0.08))])
    c = mix_rgb(N, L, math_node(N, L, "MULTIPLY", fine, 0.5), c, (0.32, 0.36, 0.14))
    L.new(c, b.inputs["Base Color"])
    inp(b, "Roughness", 0.95)
    bump_into(N, L, b, fine, 0.6, 0.01)
    return m


def gravel(name, light=(0.62, 0.58, 0.52), dark=(0.38, 0.35, 0.31)):
    m, N, L, b = new_mat(name)
    v = coord(N, L)
    vo = N.new("ShaderNodeTexVoronoi")
    vo.inputs["Scale"].default_value = 45.0
    L.new(v, vo.inputs["Vector"])
    c = K.ramp(N, L, vo.outputs["Color"], [(0.0, dark), (1.0, light)])
    L.new(c, b.inputs["Base Color"])
    inp(b, "Roughness", 0.9)
    bump_into(N, L, b, vo.outputs["Distance"], 0.8, 0.01)
    return m


def leaves(name, color):
    m, N, L, b = new_mat(name)
    v = coord(N, L)
    n = grain(N, L, v, 6.0, 4.0)
    L.new(K.ramp(N, L, n, [(0.3, tuple(k * 0.6 for k in color)), (0.7, tuple(min(1, k * 1.3) for k in color))]), b.inputs["Base Color"])
    inp(b, "Roughness", 0.7)
    try:
        inp(b, ["Subsurface Weight", "Subsurface"], 0.15)
    except KeyError:
        pass
    bump_into(N, L, b, grain(N, L, v, 40.0, 3.0), 0.5, 0.01)
    return m


def frosted(name):
    m = principled(name, (0.95, 0.96, 0.96), 0.35)
    b = m.node_tree.nodes["Principled BSDF"]
    inp(b, ["Transmission Weight", "Transmission"], 1.0)
    inp(b, "IOR", 1.45)
    return m


M = {
    "paint": plaster("paint", (0.86, 0.85, 0.83), 0.9, 0.03),
    "render": plaster("render", (0.80, 0.73, 0.60), 0.95, 0.25, 140.0, 0.035),
    "cap": principled("wall_cap", (0.07, 0.07, 0.075), 0.7),
    "plinth": plaster("plinth", (0.30, 0.30, 0.30), 0.9, 0.2, 140.0, 0.02),
    "stone": plaster("stone", (0.78, 0.76, 0.71), 0.7, 0.1, 30.0, 0.03),
    "sill_int": principled("sill_int", (0.9, 0.9, 0.89), 0.4),
    "tile": tiles("floor_tile", (0.80, 0.77, 0.72), (0.76, 0.73, 0.68), (0.56, 0.54, 0.5), 0.6, 0.6, rough=0.28),
    "bath_tile": tiles("bath_tile", (0.70, 0.70, 0.69), (0.66, 0.66, 0.65), (0.82, 0.82, 0.8), 0.6, 0.3, offset=0.5, rough=0.3),
    "faience": tiles("faience", (0.93, 0.93, 0.92), (0.9, 0.9, 0.89), (0.75, 0.75, 0.73), 0.6, 0.2, offset=0.5, rough=0.08, glaze=0.4),
    "faience_y": tiles("faience_y", (0.93, 0.93, 0.92), (0.9, 0.9, 0.89), (0.75, 0.75, 0.73), 0.6, 0.2, offset=0.5, rough=0.08, swap=True, glaze=0.4),
    "parquet": wood("parquet", (0.62, 0.45, 0.29), (0.47, 0.32, 0.19), 1.0, 0.4, boards=(0.19, 1.25)),
    "slab": principled("slab", (0.42, 0.42, 0.41), 0.9),
    "oak": wood("oak", (0.66, 0.5, 0.34), (0.5, 0.36, 0.23), 1.4, 0.45),
    "walnut": wood("walnut", (0.36, 0.24, 0.15), (0.22, 0.14, 0.09), 1.4, 0.4),
    "boucle": fabric("boucle", (0.76, 0.72, 0.65), bump=0.6, scale=160.0),
    "upholstery": fabric("upholstery", (0.40, 0.42, 0.40)),
    "linen": fabric("linen", (0.88, 0.87, 0.84), bump=0.15),
    "linen_greige": fabric("linen_greige", (0.62, 0.58, 0.52), bump=0.15),
    "throw": fabric("throw", (0.62, 0.32, 0.2), bump=0.35),
    "blue": fabric("blue_fabric", (0.2, 0.28, 0.38)),
    "rug": fabric("rug", (0.62, 0.59, 0.54), bump=0.9, scale=90.0),
    "rug_dark": fabric("rug_dark", (0.33, 0.31, 0.29), bump=0.9, scale=90.0),
    "white": principled("white_matte", (0.85, 0.85, 0.83), 0.5),
    "sage": principled("sage_matte", (0.42, 0.48, 0.42), 0.55),
    "black": principled("black_metal", (0.03, 0.03, 0.032), 0.35, 0.8),
    "steel": principled("steel", (0.78, 0.78, 0.78), 0.2, 1.0),
    "ceramic": principled("ceramic", (0.92, 0.92, 0.91), 0.06, coat=0.3),
    "terracotta": principled("terracotta_pot", (0.55, 0.3, 0.2), 0.8),
    "soil": principled("soil", (0.12, 0.09, 0.07), 1.0),
    "tv": principled("tv_glass", (0.006, 0.006, 0.007), 0.12),
    "hob": principled("hob_glass", (0.01, 0.01, 0.012), 0.08),
    "mirror": principled("mirror", (0.92, 0.92, 0.92), 0.02, 1.0),
    "pvc": principled("pvc_frame", (0.9, 0.9, 0.89), 0.35),
    "door": principled("door_leaf", (0.9, 0.895, 0.88), 0.4),
    "entrance": principled("entrance_door", (0.13, 0.135, 0.14), 0.45, 0.4),
    "glass": K.glass("glass"),
    "frosted": frosted("frosted_glass"),
    "shower_glass": K.glass("shower_glass", (0.9, 0.95, 0.95)),
    "zinc": principled("zinc", (0.55, 0.57, 0.58), 0.4, 0.8),
    "shutter": wood("shutter", (0.5, 0.58, 0.6), (0.44, 0.52, 0.55), 1.2, 0.6, boards=(0.12, 3.0), swap=True),
    "soffit": principled("soffit", (0.9, 0.89, 0.86), 0.7),
    "roof_x": roof_tiles("roof_tiles_x"),
    "roof_y": roof_tiles("roof_tiles_y", along_y=True),
    "ridge": principled("ridge_tile", (0.5, 0.22, 0.12), 0.75),
    "flat_roof": gravel("flat_roof", (0.5, 0.49, 0.47), (0.3, 0.29, 0.28)),
    "lawn": lawn("lawn"),
    "gravel": gravel("gravel"),
    "terrace": tiles("terrace", (0.62, 0.6, 0.56), (0.58, 0.56, 0.52), (0.4, 0.38, 0.35), 0.6, 0.6, rough=0.7, joint_w=0.006),
    "leaf": leaves("leaf", (0.12, 0.25, 0.08)),
    "leaf_dark": leaves("leaf_dark", (0.07, 0.15, 0.06)),
    "bark": principled("bark", (0.2, 0.15, 0.11), 0.9),
    "art": principled("art_print", (0.62, 0.44, 0.33), 0.8),
    "art2": principled("art_print_2", (0.2, 0.25, 0.28), 0.8),
    "shade": principled("lamp_shade", (0.95, 0.92, 0.86), 0.8, emission=(1.0, 0.8, 0.55), estr=0.6),
    "label": K.emissive("label", (0.05, 0.12, 0.3), 1.0),
}


# ---------------------------------------------------------------- geometry in plan coordinates
def bx(name, x0, x1, y0, y1, z0, z1, mat, **kw):
    a, b = P(x0, y0), P(x1, y1)
    return K.box(name, a.x, b.x, a.y, b.y, z0, z1, mat, **kw)


def cy(name, x, y, r, z0, z1, mat, **kw):
    p = P(x, y)
    return K.cyl(name, p.x, p.y, r, z0, z1, mat, **kw)


def inside(x, y, poly=OUTLINE):
    hit = False
    j = len(poly) - 1
    for k in range(len(poly)):
        xi, yi = poly[k]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
        j = k
    return hit


def paint_faces(o, rule):
    """Give each face of a box a material by its normal and position: rule(nx, ny, nz, x, y, z) -> material (plan coords)."""
    mats = []
    for p in o.data.polygons:
        c = o.location + p.center
        n = p.normal
        m = rule(n.x, -n.y, n.z, c.x + CX, CY - c.y, c.z)
        if m.name not in [q.name for q in o.data.materials]:
            o.data.materials.append(m)
        mats.append(m.name)
    names = [q.name for q in o.data.materials]
    for p, mn in zip(o.data.polygons, mats):
        p.material_index = names.index(mn)
    return o


def wall_box(name, x0, x1, y0, y1, z0, z1, role, top=None, bottom=None):
    """A wall piece. role: 'out' (outer layer of an exterior wall: render, also in the reveals), 'in' (its inner
    layer: paint) or 'part' (a partition). A side face that looks out of the house is render whatever the layer."""
    o = bx(name, x0, x1, y0, y1, z0, z1, M["paint"], bevel=0.0)
    o.data.materials.clear()
    side = M["render"] if role == "out" else M["paint"]

    def rule(nx, ny, nz, x, y, z):
        if nz > 0.5:
            return top or M["cap"]
        if nz < -0.5:
            return bottom or side
        if role != "part" and not inside(x + nx * 0.03, y + ny * 0.03):
            return M["render"]
        return side

    return paint_faces(o, rule)


def axis_of(w):
    return "x" if w["x1"] - w["x0"] >= w["y1"] - w["y0"] else "y"


def outward(w):
    """+1 or -1 along the wall's short axis, pointing out of the house (exterior walls)."""
    ax = axis_of(w)
    mx, my = (w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2
    if ax == "x":
        return -1 if not inside(mx, w["y0"] - 0.05) else 1
    return -1 if not inside(w["x0"] - 0.05, my) else 1


def rect(w, a0, a1, c0=None, c1=None):
    """The part of wall w between a0..a1 along it and c0..c1 across it, as plan (x0, x1, y0, y1)."""
    if axis_of(w) == "x":
        return a0, a1, w["y0"] if c0 is None else c0, w["y1"] if c1 is None else c1
    return w["x0"] if c0 is None else c0, w["x1"] if c1 is None else c1, a0, a1


def layers(w):
    """Across-wall ranges of an exterior wall's (outer, inner) layers, and the plane between them."""
    lo, hi = (w["y0"], w["y1"]) if axis_of(w) == "x" else (w["x0"], w["x1"])
    if outward(w) < 0:  # outside at lo
        return (lo, hi - IN_LAYER), (hi - IN_LAYER, hi), hi - IN_LAYER
    return (lo + IN_LAYER, hi), (lo, lo + IN_LAYER), lo + IN_LAYER


def wall_part(w, a0, a1, z0, z1, name="wall", top=None, top_in=None):
    if not w.get("ext"):
        return [wall_box(name, *rect(w, a0, a1), z0, z1, "part", top=top)]
    (o0, o1), (i0, i1), _ = layers(w)
    return [wall_box(name + "_out", *rect(w, a0, a1, o0, o1), z0, z1, "out", top=top),
            wall_box(name + "_in", *rect(w, a0, a1, i0, i1), z0, z1, "in", top=top_in or top)]


OPEN = {}
for o in PLAN["openings"]:
    OPEN.setdefault(o["wall"], []).append(o)


def spans(w):
    lo, hi = (w["x0"], w["x1"]) if axis_of(w) == "x" else (w["y0"], w["y1"])
    out, cur = [], lo
    for o in sorted(OPEN.get(w["id"], []), key=lambda q: q["a0"]):
        if o["a0"] > cur + 1e-4:
            out.append((cur, o["a0"]))
        cur = max(cur, o["a1"])
    if hi > cur + 1e-4:
        out.append((cur, hi))
    return out


# ---------------------------------------------------------------- slab, floors, ceiling
stage("slab")
slab_poly = [P(x, y) for x, y in OUTLINE]
K.prism("slab", [(p.x, p.y) for p in slab_poly], lambda x, y: 0.0, 0.3, None, mats=[M["tile"], M["plinth"], M["slab"]])
stage("floor")
for rm in PLAN["rooms"]:
    if rm["floor"] == "tile":
        continue
    for x0, x1, y0, y1 in rm["rects"]:
        bx("floor_" + rm["name"], x0 - 0.04, x1 + 0.04, y0 - 0.04, y1 + 0.04, 0.0, 0.008, M[rm["floor"]], bevel=0.0)
with into("interior"):
    stage("ceiling")
    K.prism("ceiling", [(p.x, p.y) for p in slab_poly], lambda x, y: H + 0.2, 0.2, M["paint"])

# ---------------------------------------------------------------- walls
stage("walls")
for w in PLAN["walls"]:
    for a0, a1 in spans(w):
        wall_part(w, a0, a1, 0.0, H, "wall")
    if w.get("ext") and not w.get("annex"):
        with into("roof"):  # the band between the ceiling and the roof: only seen from outside
            wall_box("wall_band", *rect(w, *((w["x0"], w["x1"]) if axis_of(w) == "x" else (w["y0"], w["y1"]))), H, TOP, "out")
with into("roof"):  # the main block's west wall above the annex roof
    wall_box("wall_band", 1.57, 1.84, 0.29, 3.02, H, TOP, "out")


# ---------------------------------------------------------------- openings: lintels, sills, frames, glass, doors
def frame_bar(w, a0, a1, c0, c1, z0, z1, mat=None, name="frame"):
    return bx(name, *rect(w, a0, a1, c0, c1), z0, z1, mat or M["pvc"], bevel=0.003)


def glass_pane(w, a0, a1, c, z0, z1, mat):
    return bx("glass", *rect(w, a0, a1, c - 0.006, c + 0.006), z0, z1, mat, bevel=0.0)


def leaf_box(name, w, hinge_a, toward, side, angle, length, thick, z0, z1, mat, face_c):
    """A door leaf hinged at (hinge_a along the wall, face_c across), closed along 'toward' (+1/-1 along the wall),
    turned 'angle' degrees out to 'side' (+1/-1 across). Plan in, world out."""
    ax = axis_of(w)
    along = Vector((1, 0)) if ax == "x" else Vector((0, 1))
    across = Vector((0, 1)) if ax == "x" else Vector((1, 0))
    hinge = along * hinge_a + across * face_c
    th = math.radians(angle)
    u = along * (toward * math.cos(th)) + across * (side * math.sin(th))
    nrm = Vector((-u.y, u.x))
    if nrm.dot(across * side) > 0:
        nrm = -nrm
    c = hinge + u * (length / 2) + nrm * (thick / 2) * -1
    cw = P(c.x, c.y)
    uw = Vector((u.x, -u.y))
    o = K.obox(name, (cw.x, cw.y, (z0 + z1) / 2), (length, thick, z1 - z0), (0, 0, math.atan2(uw.y, uw.x)), mat, bevel=0.004)
    tip = hinge + u * (length - 0.07)
    for s_ in (-1, 1):  # lever handles on both faces
        hp = tip + nrm * s_ * (thick / 2 + 0.03)
        q = P(hp.x, hp.y)
        K.obox("handle", (q.x, q.y, 1.02), (0.13, 0.018, 0.018), (0, 0, math.atan2(uw.y, uw.x)), M["steel"], bevel=0.004)
    return o


stage("openings")
for wid, ops in OPEN.items():
    w = WALLS[wid]
    ext = bool(w.get("ext"))
    ax = axis_of(w)
    lo, hi = (w["y0"], w["y1"]) if ax == "x" else (w["x0"], w["x1"])
    for o in ops:
        a0, a1, kind = o["a0"], o["a1"], o["kind"]
        head = WIN if kind == "window" else (o.get("h", WIN) if kind == "entrance" else DOOR)
        sill = 0.0 if (kind != "window" or o.get("french")) else round(head - o["h"], 3)
        wall_part(w, a0, a1, head, H, "lintel")
        if ext:
            (o0, o1), (i0, i1), jp = layers(w)
            s = outward(w)
            f0, f1 = (jp - 0.05, jp + 0.02) if s < 0 else (jp - 0.02, jp + 0.05)  # frame depth 7 cm across the joint
            fc = (f0 + f1) / 2
            outer = lo if s < 0 else hi
        else:
            f0, f1, fc = lo - 0.012, hi + 0.012, (lo + hi) / 2
        if sill > 0:
            wall_part(w, a0, a1, 0.0, sill, "sill", top=M["stone"], top_in=M["sill_int"])
            # the projecting stone sill outside
            ps0, ps1 = (outer - 0.05, outer + 0.02) if s < 0 else (outer - 0.02, outer + 0.05)
            bx("appui", *rect(w, a0 - 0.04, a1 + 0.04, min(ps0, ps1), max(ps0, ps1)), sill - 0.05, sill + 0.005, M["stone"], bevel=0.004)
        if kind == "window":
            fw = 0.06
            frame_bar(w, a0, a1, f0, f1, sill, sill + fw)
            frame_bar(w, a0, a1, f0, f1, head - fw, head)
            frame_bar(w, a0, a0 + fw, f0, f1, sill, head)
            frame_bar(w, a1 - fw, a1, f0, f1, sill, head)
            leaves = 2 if a1 - a0 > 0.8 else 1
            if leaves == 2:
                m_ = (a0 + a1) / 2
                frame_bar(w, m_ - 0.05, m_ + 0.05, f0, f1, sill, head)
                for p0, p1 in ((a0 + fw, m_ - 0.05), (m_ + 0.05, a1 - fw)):  # sash frames
                    frame_bar(w, p0, p0 + 0.045, fc - 0.025, fc + 0.025, sill + fw, head - fw, name="sash")
                    frame_bar(w, p1 - 0.045, p1, fc - 0.025, fc + 0.025, sill + fw, head - fw, name="sash")
                    if o.get("french"):
                        frame_bar(w, p0, p1, fc - 0.025, fc + 0.025, sill + fw, sill + 0.2, name="sash")
            glass_pane(w, a0 + fw, a1 - fw, fc, sill + fw, head - fw, M["frosted" if o.get("frosted") else "glass"])
            if not ext:
                continue
            o["_portal"] = (w, a0, a1, sill, head)
            if a1 - a0 > 0.8:  # a pair of ledged shutters folded back flat against the facade
                sw = (a1 - a0) / 2
                c0, c1 = (outer - 0.045, outer - 0.012) if s < 0 else (outer + 0.012, outer + 0.045)
                for p0 in (a0 - sw - 0.02, a1 + 0.02):
                    frame_bar(w, p0, p0 + sw, c0, c1, sill + 0.02, head - 0.01, M["shutter"], "shutter")
                    for zb in (sill + 0.25, (sill + head) / 2, head - 0.25):
                        cb0, cb1 = (c0 - 0.02, c0) if s < 0 else (c1, c1 + 0.02)
                        frame_bar(w, p0 + 0.04, p0 + sw - 0.04, cb0, cb1, zb - 0.05, zb + 0.05, M["shutter"], "shutter_ledge")
        elif kind == "entrance":
            frame_bar(w, a0, a0 + 0.07, f0, f1, 0.0, head, M["entrance"])
            frame_bar(w, a1 - 0.07, a1, f0, f1, 0.0, head, M["entrance"])
            frame_bar(w, a0, a1, f0, f1, head - 0.07, head, M["entrance"])
            leaf_box("entrance_leaf", w, a0 + 0.07 if o["hinge"] == "a0" else a1 - 0.07, 1 if o["hinge"] == "a0" else -1,
                     o.get("side", -s), o.get("swing", 50), (a1 - a0) - 0.14, 0.06, 0.01, head - 0.07, M["entrance"],
                     f1 if s < 0 else f0)  # hinged on the frame's inner edge, swinging into the house
            o["_portal"] = (w, a0, a1, 0.0, head)
        else:  # interior door: a casing round the opening and a leaf open at the plan's angle
            frame_bar(w, a0, a0 + 0.04, f0, f1, 0.0, head, M["door"], "casing")
            frame_bar(w, a1 - 0.04, a1, f0, f1, 0.0, head, M["door"], "casing")
            frame_bar(w, a0, a1, f0, f1, head - 0.04, head, M["door"], "casing")
            side = o.get("side", 1)
            face = hi if side > 0 else lo
            hinge_a = a0 + 0.045 if o["hinge"] == "a0" else a1 - 0.045
            leaf_box("door_leaf", w, hinge_a, 1 if o["hinge"] == "a0" else -1, side, o.get("swing", 25),
                     (a1 - a0) - 0.09, 0.04, 0.01, head - 0.045, M["door"], face)

# ---------------------------------------------------------------- roof: a hipped roof over the main block, the annex flat
stage("roof")
PITCH = math.radians(22)
TP = math.tan(PITCH)
OV = 0.45
RX0, RX1, RY0, RY1 = 1.57 - OV, 11.8 + OV, 0.0 - OV, 9.2 + OV
RTH = 0.18
Z_EAVE = TOP + RTH - OV * TP  # roof surface at the eave edge; at the wall face it is TOP + RTH
HALF = (RY1 - RY0) / 2
RIDGE_Y = (RY0 + RY1) / 2
RA, RB = RX0 + HALF, RX1 - HALF  # ridge ends (plan x)
Z_RIDGE = Z_EAVE + HALF * TP


def roof_z(xw, yw):
    x, y = xw + CX, CY - yw
    return Z_EAVE + TP * max(0.0, min(x - RX0, RX1 - x, y - RY0, RY1 - y))


with into("roof"):
    pans = {
        "north": ([(RX0, RY0), (RX1, RY0), (RB, RIDGE_Y), (RA, RIDGE_Y)], "roof_x"),
        "south": ([(RX1, RY1), (RX0, RY1), (RA, RIDGE_Y), (RB, RIDGE_Y)], "roof_x"),
        "west": ([(RX0, RY1), (RX0, RY0), (RA, RIDGE_Y)], "roof_y"),
        "east": ([(RX1, RY0), (RX1, RY1), (RB, RIDGE_Y)], "roof_y"),
    }
    for pn, (poly, mk) in pans.items():
        K.prism("roof_" + pn, [(P(x, y).x, P(x, y).y) for x, y in poly], roof_z, RTH, None, mats=[M[mk], M["soffit"], M["soffit"]])
    # ridge and hip rolls
    ridge = [((RA, RIDGE_Y), (RB, RIDGE_Y))] + [((RX0, RY0), (RA, RIDGE_Y)), ((RX0, RY1), (RA, RIDGE_Y)), ((RX1, RY0), (RB, RIDGE_Y)), ((RX1, RY1), (RB, RIDGE_Y))]
    for (xa, ya), (xb, yb) in ridge:
        a, b = P(xa, ya), P(xb, yb)
        K.tube("ridge_roll", (a.x, a.y, roof_z(a.x, a.y) + 0.02), (b.x, b.y, roof_z(b.x, b.y) + 0.02), 0.085, M["ridge"])
    # gutters along the four eaves, a downpipe at each corner
    zg = Z_EAVE - 0.11
    for (xa, ya), (xb, yb) in (((RX0, RY0), (RX1, RY0)), ((RX1, RY0), (RX1, RY1)), ((RX1, RY1), (RX0, RY1)), ((RX0, RY1), (RX0, RY0))):
        a, b = P(xa, ya), P(xb, yb)
        K.tube("gutter", (a.x, a.y, zg), (b.x, b.y, zg), 0.065, M["zinc"])
    for (x, y), (gx, gy) in (((11.86, -0.06), (11.86, RY0)), ((11.86, 9.26), (11.86, RY1)), ((1.51, 9.26), (1.51, RY1))):
        p, g_ = P(x, y), P(gx, gy)  # down the wall corner, a swan neck out to the gutter
        K.tube("downpipe", (p.x, p.y, GROUND), (p.x, p.y, zg - 0.35), 0.04, M["zinc"])
        K.tube("swan_neck", (p.x, p.y, zg - 0.37), (g_.x, g_.y, zg - 0.02), 0.04, M["zinc"])
    # the annex: a parapet with a zinc coping round a gravel flat roof
    bx("flat_roof", 0.25, 1.6, 0.25, 3.06, H - 0.12, H - 0.08, M["flat_roof"], bevel=0.0)
    for x0, x1, y0, y1 in ((-0.02, 1.57, -0.02, 0.31), (-0.02, 0.31, 0.29, 3.33), (0.29, 1.59, 3.0, 3.33)):
        bx("coping", x0, x1, y0, y1, H, H + 0.03, M["zinc"], bevel=0.003)


# ---------------------------------------------------------------- kitchen
stage("builtin")
KI = PLAN["kitchen"]
nx0, nx1 = KI["north"]
D = KI["depth"]
Y0 = 0.29
cx0, cx1 = KI["column"]
ey0, ey1 = KI["east"]
bx("tall_column", cx0, cx1, Y0, Y0 + D, 0.0, 2.2, M["white"], bevel=0.004)
for zz in (0.85, 1.45):
    bx("column_seam", cx0 + 0.01, cx1 - 0.01, Y0 + D - 0.002, Y0 + D + 0.001, zz - 0.002, zz + 0.002, M["black"], bevel=0.0)
bx("oven_glass", cx0 + 0.04, cx1 - 0.04, Y0 + D, Y0 + D + 0.004, 0.9, 1.4, M["tv"], bevel=0.0)
bx("column_handle", cx0 + 0.08, cx0 + 0.1, Y0 + D, Y0 + D + 0.03, 1.55, 2.0, M["steel"], bevel=0.004)
bx("column_handle", cx0 + 0.08, cx0 + 0.1, Y0 + D, Y0 + D + 0.03, 0.3, 0.75, M["steel"], bevel=0.004)
runs = [(cx1, nx1, Y0, Y0 + D), (nx1 - D, nx1, Y0 + D, ey1)]
for x0, x1, y0, y1 in runs:
    bx("plinth", x0, x1, y0, y1, 0.0, 0.1, M["black"], bevel=0.002)
    bx("base_units", x0, x1, y0, y1, 0.1, 0.86, M["sage"], bevel=0.004)
    bx("worktop", x0, x1, y0, y1 + (0.02 if y1 > Y0 + D else 0.0), 0.86, 0.9, M["oak"], bevel=0.004)
for k in range(1, 6):  # door seams on the north run
    xx = cx1 + k * (nx1 - D - cx1) / 5
    bx("unit_seam", xx - 0.002, xx + 0.002, Y0 + D - 0.002, Y0 + D + 0.001, 0.12, 0.84, M["black"], bevel=0.0)
bx("unit_seam", nx1 - D - 0.001, nx1 - D + 0.002, Y0 + D + 0.4, Y0 + D + 0.404, 0.12, 0.84, M["black"], bevel=0.0)
sxk = KI["sink"]
bx("sink", sxk - 0.3, sxk + 0.3, Y0 + 0.08, Y0 + 0.52, 0.86, 0.903, M["steel"], bevel=0.01)
bx("sink_bowl", sxk - 0.26, sxk + 0.26, Y0 + 0.11, Y0 + 0.49, 0.72, 0.905, M["black"], bevel=0.0)
cy("tap", sxk, Y0 + 0.05, 0.017, 0.9, 1.2, M["steel"])
bx("tap_spout", sxk - 0.012, sxk + 0.012, Y0 + 0.04, Y0 + 0.26, 1.18, 1.205, M["steel"], bevel=0.005)
hy = KI["hob"]
bx("hob", nx1 - 0.55, nx1 - 0.05, hy - 0.3, hy + 0.3, 0.9, 0.905, M["hob"], bevel=0.002)
bx("hood", nx1 - 0.5, nx1, hy - 0.3, hy + 0.3, 1.6, 1.68, M["steel"], bevel=0.004)
bx("hood_flue", nx1 - 0.3, nx1, hy - 0.14, hy + 0.14, 1.68, H, M["steel"], bevel=0.004)
for a, b in KI["uppers"]:
    bx("wall_units", a, b, Y0, Y0 + 0.35, 1.48, 2.2, M["white"], bevel=0.004)
    n = max(1, round((b - a) / 0.5))
    for k in range(1, n):
        xx = a + (b - a) * k / n
        bx("unit_seam", xx - 0.002, xx + 0.002, Y0 + 0.348, Y0 + 0.352, 1.5, 2.18, M["black"], bevel=0.0)
for x0, x1 in ((cx1, 3.1), (4.3, nx1)):
    bx("splashback", x0, x1, Y0, Y0 + 0.01, 0.9, 1.48, M["faience"], bevel=0.0)
bx("splashback", nx1 - 0.01, nx1, Y0 + D, ey1, 0.9, 1.6, M["faience_y"], bevel=0.0)

# ---------------------------------------------------------------- furniture
DIRS = {"+x": Vector((1, 0)), "-x": Vector((-1, 0)), "+y": Vector((0, 1)), "-y": Vector((0, -1))}


def local_box(name, at, d, lx0, lx1, ly0, ly1, z0, z1, mat, **kw):
    """A box in a frame that faces d (plan vector): lx forward, ly sideways."""
    p = Vector((-d.y, d.x))
    cs = [Vector(at) + d * lx + p * ly for lx in (lx0, lx1) for ly in (ly0, ly1)]
    return bx(name, min(c.x for c in cs), max(c.x for c in cs), min(c.y for c in cs), max(c.y for c in cs), z0, z1, mat, **kw)


def rect_frame(f):
    d = DIRS[f["face"]]
    c = Vector(((f["x0"] + f["x1"]) / 2, (f["y0"] + f["y1"]) / 2))
    w, h = f["x1"] - f["x0"], f["y1"] - f["y0"]
    return c, d, (w if d.x else h), (h if d.x else w)


def chair(f):
    at, d = f["at"], DIRS[f["face"]]
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            local_box("chair_leg", at, d, sx_ * 0.18 - 0.017, sx_ * 0.18 + 0.017, sy_ * 0.19 - 0.017, sy_ * 0.19 + 0.017, 0.0, 0.43, M["oak"], bevel=0.006)
    local_box("chair_seat", at, d, -0.22, 0.22, -0.225, 0.225, 0.42, 0.49, M["linen_greige"], bevel=0.025, seg=4)
    for sy_ in (-1, 1):
        local_box("chair_post", at, d, -0.235, -0.2, sy_ * 0.19 - 0.017, sy_ * 0.19 + 0.017, 0.43, 0.84, M["oak"], bevel=0.006)
    local_box("chair_back", at, d, -0.245, -0.205, -0.21, 0.21, 0.62, 0.84, M["oak"], bevel=0.012, seg=3)


def armchair(f):
    at, d = f["at"], DIRS[f["face"]]
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            local_box("arm_leg", at, d, sx_ * 0.3 - 0.02, sx_ * 0.3 + 0.02, sy_ * 0.3 - 0.02, sy_ * 0.3 + 0.02, 0.0, 0.16, M["walnut"], bevel=0.006)
    local_box("arm_base", at, d, -0.36, 0.36, -0.37, 0.37, 0.16, 0.42, M["blue"], bevel=0.05, seg=4)
    local_box("arm_back", at, d, -0.36, -0.2, -0.37, 0.37, 0.42, 0.82, M["blue"], bevel=0.06, seg=4)
    for s_ in (-1, 1):
        local_box("arm_rest", at, d, -0.36, 0.36, s_ * 0.37 - (0.12 if s_ > 0 else 0), s_ * 0.37 + (0.12 if s_ < 0 else 0), 0.42, 0.6, M["blue"], bevel=0.05, seg=4)
    local_box("arm_cushion", at, d, -0.2, 0.34, -0.25, 0.25, 0.42, 0.52, M["blue"], bevel=0.05, seg=4)


def sofa(f):
    c, d, Dp, Lg = rect_frame(f)
    at = (c.x, c.y)
    fr, bk = Dp / 2, -Dp / 2
    for sx_ in (bk + 0.06, fr - 0.06):
        for sy_ in (-Lg / 2 + 0.08, Lg / 2 - 0.08):
            local_box("sofa_foot", at, d, sx_ - 0.025, sx_ + 0.025, sy_ - 0.025, sy_ + 0.025, 0.0, 0.08, M["black"], bevel=0.004)
    local_box("sofa_base", at, d, bk, fr, -Lg / 2, Lg / 2, 0.08, 0.36, M["boucle"], bevel=0.035, seg=4)
    local_box("sofa_back", at, d, bk, bk + 0.2, -Lg / 2, Lg / 2, 0.36, 0.76, M["boucle"], bevel=0.06, seg=5)
    for s_ in (-1, 1):
        local_box("sofa_arm", at, d, bk, fr, s_ * Lg / 2 - (0.2 if s_ > 0 else 0), s_ * Lg / 2 + (0.2 if s_ < 0 else 0), 0.36, 0.6, M["boucle"], bevel=0.06, seg=5)
    inner0, inner1 = -Lg / 2 + 0.2, Lg / 2 - 0.2
    for k in range(2):
        a0 = inner0 + (inner1 - inner0) * k / 2 + 0.008
        a1 = inner0 + (inner1 - inner0) * (k + 1) / 2 - 0.008
        local_box("sofa_seat", at, d, bk + 0.2, fr - 0.01, a0, a1, 0.36, 0.52, M["boucle"], bevel=0.07, seg=6)
        local_box("sofa_cushion", at, d, bk + 0.18, bk + 0.42, a0, a1, 0.5, 0.88, M["boucle"], bevel=0.09, seg=6)
    for a0, mat in ((inner0 + 0.06, M["throw"]), (inner1 - 0.5, M["linen_greige"])):
        local_box("sofa_pillow", at, d, bk + 0.38, bk + 0.52, a0, a0 + 0.44, 0.52, 0.94, mat, bevel=0.06, seg=5)


def bed(f):
    d = DIRS[f["head"]]
    c = Vector(((f["x0"] + f["x1"]) / 2, (f["y0"] + f["y1"]) / 2))
    Lb = (f["x1"] - f["x0"]) if d.x else (f["y1"] - f["y0"])
    Wb = (f["y1"] - f["y0"]) if d.x else (f["x1"] - f["x0"])
    at = (c.x, c.y)
    hd, ft = Lb / 2, -Lb / 2
    local_box("bed_frame", at, d, ft, hd - 0.08, -Wb / 2, Wb / 2, 0.08, 0.34, M["upholstery"], bevel=0.03, seg=4)
    local_box("bed_plinth", at, d, ft + 0.08, hd - 0.16, -Wb / 2 + 0.08, Wb / 2 - 0.08, 0.0, 0.09, M["black"], bevel=0.004)
    local_box("headboard", at, d, hd - 0.1, hd, -Wb / 2 - 0.04, Wb / 2 + 0.04, 0.08, 1.1, M["upholstery"], bevel=0.05, seg=5)
    local_box("mattress", at, d, ft + 0.03, hd - 0.12, -Wb / 2 + 0.03, Wb / 2 - 0.03, 0.34, 0.58, M["linen"], bevel=0.05, seg=5)
    local_box("duvet", at, d, ft - 0.02, hd - 0.68, -Wb / 2 - 0.02, Wb / 2 + 0.02, 0.3, 0.64, M["linen"], bevel=0.06, seg=6)
    local_box("duvet_fold", at, d, hd - 0.82, hd - 0.62, -Wb / 2 - 0.02, Wb / 2 + 0.02, 0.6, 0.67, M["linen"], bevel=0.035, seg=5)
    local_box("throw", at, d, ft + 0.12, ft + 0.62, -Wb / 2 - 0.035, Wb / 2 + 0.035, 0.62, 0.66, M["throw"], bevel=0.02, seg=4)
    gap = 0.04
    pw = (Wb - 0.16 - gap) / 2
    for s_ in (-1, 1):
        a0 = (gap / 2) if s_ > 0 else -(gap / 2) - pw
        local_box("pillow", at, d, hd - 0.58, hd - 0.14, a0, a0 + pw, 0.58, 0.76, M["linen"], bevel=0.07, seg=6)
    local_box("pillow_front", at, d, hd - 0.66, hd - 0.46, -0.3, 0.3, 0.58, 0.88, M["linen_greige"], bevel=0.07, seg=6)


def nightstand(f):
    x, y = f["at"]
    bx("nightstand", x - 0.21, x + 0.21, y - 0.19, y + 0.19, 0.14, 0.5, M["oak"], bevel=0.006)
    bx("nightstand_seam", x - 0.19, x + 0.19, y - 0.195, y + 0.195, 0.33, 0.333, M["black"], bevel=0.0)
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            bx("ns_leg", x + sx_ * 0.17 - 0.012, x + sx_ * 0.17 + 0.012, y + sy_ * 0.15 - 0.012, y + sy_ * 0.15 + 0.012, 0.0, 0.14, M["black"], bevel=0.002)
    cy("lamp_base", x, y, 0.065, 0.5, 0.68, M["ceramic"], bevel=0.02, seg=4)
    cy("lamp_shade", x, y, 0.14, 0.66, 0.86, M["shade"], bevel=0.004, r2=0.11)


def wardrobe(f):
    bx("wardrobe", f["x0"], f["x1"], f["y0"], f["y1"], 0.0, 2.3, M["white"], bevel=0.004)
    long_x = f["x1"] - f["x0"] >= f["y1"] - f["y0"]
    a0, a1 = (f["x0"], f["x1"]) if long_x else (f["y0"], f["y1"])
    n = max(1, round((a1 - a0) / 0.5))
    for k in range(1, n):
        a = a0 + (a1 - a0) * k / n
        if long_x:
            bx("wardrobe_seam", a - 0.002, a + 0.002, f["y0"] - 0.002, f["y1"] + 0.002, 0.02, 2.28, M["black"], bevel=0.0)
        else:
            bx("wardrobe_seam", f["x0"] - 0.002, f["x1"] + 0.002, a - 0.002, a + 0.002, 0.02, 2.28, M["black"], bevel=0.0)


def tv_console(f):
    c, d, Dp, Lg = rect_frame(f)
    at = (c.x, c.y)
    local_box("tv_console", at, d, -Dp / 2, Dp / 2, -Lg / 2, Lg / 2, 0.16, 0.5, M["oak"], bevel=0.006)
    for k in (-1, 0, 1):
        local_box("console_seam", at, d, Dp / 2 - 0.004, Dp / 2 + 0.002, k * Lg / 3 - 0.002, k * Lg / 3 + 0.002, 0.18, 0.48, M["black"], bevel=0.0)
    for s_ in (-1, 1):
        local_box("console_leg", at, d, -0.03, 0.03, s_ * (Lg / 2 - 0.08) - 0.03, s_ * (Lg / 2 - 0.08) + 0.03, 0.0, 0.16, M["black"], bevel=0.003)
    if f.get("tv"):
        w = min(1.3, Lg - 0.2)
        local_box("tv", at, d, -Dp / 2 + 0.0, -Dp / 2 + 0.035, -w / 2, w / 2, 1.0, 1.0 + w * 0.5625, M["tv"], bevel=0.004)


def rug(f):
    bx("rug", f["x0"], f["x1"], f["y0"], f["y1"], 0.008, 0.02, M[f.get("material", "rug")], bevel=0.006)


def coffee_table(f):
    x, y = f["at"]
    cy("table_top", x, y, f["r"], f["h"] - 0.035, f["h"], M["walnut"], bevel=0.008, seg=3)
    cy("table_base", x, y, f["r"] * 0.55, 0.0, f["h"] - 0.035, M["walnut"], bevel=0.006)
    cy("book_stack", x + 0.12, y - 0.1, 0.12, f["h"], f["h"] + 0.06, M["art2"], bevel=0.004, verts=4)


def dining_table(f):
    bx("dining_top", f["x0"], f["x1"], f["y0"], f["y1"], 0.72, 0.76, M["oak"], bevel=0.008, seg=3)
    for x in (f["x0"] + 0.08, f["x1"] - 0.08):
        for y in (f["y0"] + 0.08, f["y1"] - 0.08):
            bx("dining_leg", x - 0.025, x + 0.025, y - 0.025, y + 0.025, 0.0, 0.72, M["black"], bevel=0.004)


def desk(f):
    bx("desk_top", f["x0"], f["x1"], f["y0"], f["y1"], 0.72, 0.75, M["oak"], bevel=0.005)
    for x in (f["x0"] + 0.04, f["x1"] - 0.04):
        for y in (f["y0"] + 0.04, f["y1"] - 0.04):
            bx("desk_leg", x - 0.015, x + 0.015, y - 0.015, y + 0.015, 0.0, 0.72, M["black"], bevel=0.003)
    cxm, cym = (f["x0"] + f["x1"]) / 2, (f["y0"] + f["y1"]) / 2
    bx("laptop", cxm - 0.17, cxm + 0.17, cym - 0.12, cym + 0.12, 0.75, 0.765, M["steel"], bevel=0.004)


def shower(f):
    x0, x1, y0, y1 = f["x0"], f["x1"], f["y0"], f["y1"]
    bx("shower_tray", x0, x1, y0, y1, 0.0, 0.03, M["ceramic"], bevel=0.006)
    bx("faience", x0, x1 + 0.3, y0, y0 + 0.01, 0.0, 2.1, M["faience"], bevel=0.0)
    bx("faience", x0, x0 + 0.01, y0, y1 + 0.1, 0.0, 2.1, M["faience_y"], bevel=0.0)
    g = f["glass"]
    if g in ("x0", "x1"):
        x = f[g]
        bx("shower_glass", x - 0.005, x + 0.005, y0 + 0.01, y1 - 0.05, 0.03, 2.0, M["shower_glass"], bevel=0.0)
        bx("shower_bar", x - 0.008, x + 0.008, y0, y1 - 0.05, 1.98, 2.0, M["black"], bevel=0.002)
    cy("shower_head", x0 + 0.3, y0 + 0.3, 0.12, 2.12, 2.14, M["black"], bevel=0.003)
    bx("shower_arm", x0 + 0.01, x0 + 0.3, y0 + 0.29, y0 + 0.31, 2.14, 2.16, M["black"], bevel=0.003)
    bx("shower_drain", x0 + 0.1, x1 - 0.1, y1 - 0.12, y1 - 0.08, 0.03, 0.032, M["steel"], bevel=0.0)


def toilet(f):
    at, d = f["at"], DIRS[f["face"]]
    local_box("toilet_pan", at, d, 0.12, 0.62, -0.18, 0.18, 0.28, 0.4, M["ceramic"], bevel=0.07, seg=5)
    local_box("toilet_seat", at, d, 0.14, 0.6, -0.175, 0.175, 0.4, 0.42, M["ceramic"], bevel=0.015, seg=3)
    local_box("wc_frame", at, d, 0.0, 0.14, -0.3, 0.3, 0.0, 1.15, M["paint"], bevel=0.004)
    local_box("flush_plate", at, d, 0.14, 0.15, -0.12, 0.12, 0.98, 1.12, M["steel"], bevel=0.003)


def hand_basin(f):
    at, d = f["at"], DIRS[f["face"]]
    local_box("hand_basin", at, d, 0.0, 0.25, -0.2, 0.2, 0.72, 0.85, M["ceramic"], bevel=0.03, seg=3)
    local_box("hb_tap", at, d, 0.0, 0.08, -0.012, 0.012, 0.85, 0.95, M["steel"], bevel=0.004)
    local_box("hb_mirror", at, d, 0.0, 0.006, -0.25, 0.25, 1.1, 1.6, M["mirror"], bevel=0.002)


def vanity(f):
    c, d, Dp, Lg = rect_frame(f)
    at = (c.x, c.y)
    local_box("vanity", at, d, -Dp / 2, Dp / 2, -Lg / 2, Lg / 2, 0.32, 0.82, M["oak"], bevel=0.005)
    local_box("vanity_top", at, d, -Dp / 2, Dp / 2 + 0.01, -Lg / 2, Lg / 2, 0.82, 0.85, M["ceramic"], bevel=0.003)
    local_box("basin", at, d, -Dp / 2 + 0.15, Dp / 2 - 0.08, -0.22, 0.22, 0.85, 0.97, M["ceramic"], bevel=0.04, seg=4)
    local_box("v_tap", at, d, -Dp / 2 + 0.03, -Dp / 2 + 0.14, -0.012, 0.012, 0.97, 1.0, M["steel"], bevel=0.004)
    local_box("mirror", at, d, -Dp / 2, -Dp / 2 + 0.008, -Lg / 2 + 0.03, Lg / 2 - 0.03, 1.05, 1.85, M["mirror"], bevel=0.002)
    local_box("v_light", at, d, -Dp / 2, -Dp / 2 + 0.05, -Lg / 2 + 0.06, Lg / 2 - 0.06, 1.9, 1.93, M["shade"], bevel=0.004)


def towel_rail(f):
    for k in range(9):
        z = 0.5 + k * 0.13
        bx("towel_bar", f["x0"], f["x1"], f["y0"], f["y1"], z, z + 0.025, M["white"], bevel=0.008)
    for y in (f["y0"], f["y1"] - 0.03):
        bx("towel_post", f["x0"], f["x1"], y, y + 0.03, 0.45, 1.6, M["white"], bevel=0.008)
    bx("towel", f["x0"] - 0.03, f["x0"] - 0.005, f["y0"] + 0.08, f["y1"] - 0.08, 0.9, 1.45, M["linen_greige"], bevel=0.01)


def washer(f):
    at, d = f["at"], DIRS[f["face"]]
    local_box("washer", at, d, -0.3, 0.3, -0.3, 0.3, 0.0, 0.85, M["ceramic"], bevel=0.02, seg=3)
    local_box("washer_door", at, d, 0.3, 0.32, -0.18, 0.18, 0.28, 0.64, M["tv"], bevel=0.05, seg=4)
    local_box("dryer", at, d, -0.3, 0.3, -0.3, 0.3, 0.86, 1.71, M["ceramic"], bevel=0.02, seg=3)
    local_box("dryer_door", at, d, 0.3, 0.32, -0.18, 0.18, 1.12, 1.48, M["tv"], bevel=0.05, seg=4)


def water_heater(f):
    x, y = f["at"]
    cy("water_heater", x, y, f["r"], 0.15, 0.15 + f["h"], M["white"], bevel=0.03, seg=4)
    for a in (0, 2.1, 4.2):
        cy("wh_foot", x + 0.2 * math.cos(a), y + 0.2 * math.sin(a), 0.02, 0.0, 0.15, M["steel"], bevel=0.0)


def shelves(f):
    x0, x1, y0, y1 = f["x0"], f["x1"], f["y0"], f["y1"]
    for y in (y0, y1 - 0.03):
        bx("shelf_post", x0, x1, y, y + 0.03, 0.0, 2.0, M["steel"], bevel=0.003)
    for k in range(5):
        z = 0.1 + k * 0.45
        bx("shelf", x0, x1, y0, y1, z, z + 0.025, M["oak"], bevel=0.003)
        rnd = random.Random(k)
        yy = y0 + 0.05
        while yy < y1 - 0.2 and k < 4:
            w_ = rnd.uniform(0.12, 0.3)
            bx("shelf_box", x0 + 0.04, x1 - 0.06, yy, yy + w_, z + 0.025, z + 0.025 + rnd.uniform(0.12, 0.3), [M["white"], M["art"], M["linen_greige"], M["art2"]][rnd.randrange(4)], bevel=0.004)
            yy += w_ + rnd.uniform(0.03, 0.1)


def coat_rack(f):
    x0, x1, y0, y1 = f["x0"], f["x1"], f["y0"], f["y1"]
    bx("bench", x0, x1, y0, y1, 0.0, 0.45, M["oak"], bevel=0.006)
    bx("coat_board", x0, x0 + 0.02, y0, y1, 1.55, 1.7, M["oak"], bevel=0.004)
    for k in range(4):
        yy = y0 + 0.1 + k * (y1 - y0 - 0.2) / 3
        bx("hook", x0 + 0.02, x0 + 0.1, yy - 0.01, yy + 0.01, 1.6, 1.62, M["black"], bevel=0.003)
    bx("coat", x0 + 0.04, x0 + 0.16, y0 + 0.08, y0 + 0.42, 0.85, 1.6, M["linen_greige"], bevel=0.05, seg=4)
    bx("coat", x0 + 0.04, x0 + 0.15, y1 - 0.4, y1 - 0.12, 0.95, 1.6, M["blue"], bevel=0.05, seg=4)


def leafy(name, cx_, cy_, z0, height, spread, mat, seed, n=28, size=0.09):
    """A potted plant's foliage: stems from the pot, flattened elliptical leaves along them."""
    rnd = random.Random(seed)
    base = W3(cx_, cy_, z0)
    for k in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        t = rnd.uniform(0.35, 1.0)
        r = spread * t * rnd.uniform(0.6, 1.0)
        tip = base + Vector((r * math.cos(a), r * math.sin(a), height * t))
        if k % 3 == 0:
            K.tube("stem", base, tip, 0.006, M["bark"], verts=6)
        o = K.sphere(name, tip.x, tip.y, tip.z, size * rnd.uniform(0.8, 1.3), mat, seg=12)
        o.scale = (1.0, 0.45, 0.08)
        o.rotation_euler = (rnd.uniform(-0.6, 0.6), rnd.uniform(-0.9, 0.9), a + rnd.uniform(-0.5, 0.5))


def plant(f):
    x, y = f["at"]
    h = f["h"]
    pr = 0.11 + 0.08 * h
    cy("pot", x, y, pr, 0.0, 0.28 * h, M["terracotta"] if h < 1 else M["ceramic"], bevel=0.01, r2=pr * 0.8)
    cy("soil", x, y, pr * 0.92, 0.0, 0.28 * h - 0.02, M["soil"], bevel=0.0)
    leafy("leaf", x, y, 0.26 * h, h * 0.75, 0.25 + 0.2 * h, M["leaf"], int(x * 100 + y * 10), n=int(18 + 18 * h), size=0.06 + 0.05 * h)


def pendant(f):
    x, y = f["at"]
    with into("interior"):
        cy("pendant_cord", x, y, 0.004, 1.75, H, M["black"], bevel=0.0)
        cy("pendant_shade", x, y, 0.26, 1.55, 1.75, M["black"], bevel=0.004, r2=0.05)
        K.light("pendant_light", "POINT", W3(x, y, 1.62), 40, (1.0, 0.8, 0.58), size=0.08)


BUILD = {"chair": chair, "sofa": sofa, "bed": bed, "nightstand": nightstand, "wardrobe": wardrobe, "tv_console": tv_console,
         "rug": rug, "coffee_table": coffee_table, "dining_table": dining_table, "desk": desk, "shower": shower,
         "toilet": toilet, "hand_basin": hand_basin, "vanity": vanity, "towel_rail": towel_rail, "washer": washer,
         "water_heater": water_heater, "shelves": shelves, "coat_rack": coat_rack, "plant": plant, "pendant": pendant,
         "armchair": armchair}
STAGE_OF = {"wardrobe": "builtin", "shower": "builtin", "toilet": "builtin", "vanity": "builtin", "hand_basin": "builtin",
            "towel_rail": "builtin", "washer": "builtin", "water_heater": "builtin", "shelves": "builtin", "rug": "rug",
            "plant": "decor", "pendant": "ceiling"}
for f in PLAN["furniture"]:
    stage(STAGE_OF.get(f["type"], "furniture"))
    BUILD[f["type"]](f)

stage("decor")
bx("art_frame", 5.36, 5.4, 6.4, 7.8, 1.15, 1.85, M["black"], bevel=0.004)
bx("art_print", 5.355, 5.36, 6.44, 7.1, 1.19, 1.81, M["art"], bevel=0.0)
bx("art_print_2", 5.355, 5.36, 7.1, 7.76, 1.19, 1.81, M["art2"], bevel=0.0)
cy("fruit_bowl", 3.4, 2.05, 0.15, 0.76, 0.83, M["ceramic"], bevel=0.02, seg=3, r2=0.08)

# ---------------------------------------------------------------- site: lawn, terrace, path, shrubs, two trees
_clouds = bpy.data.textures.new("clouds", "CLOUDS")
_clouds.noise_scale = 0.35


def blob(name, x, y, z, r, mat, squash=0.8, seed=0):
    p = P(x, y)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=r)
    for v in bm.verts:
        v.co.z *= squash
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    o = K.link(bpy.data.objects.new(name, me))
    o.location = (p.x, p.y, z)
    o.rotation_euler = (0, 0, seed)
    dm = o.modifiers.new("lumps", "DISPLACE")
    dm.texture = _clouds
    dm.strength = r * 0.45
    dm.texture_coords = "GLOBAL"
    for pg in me.polygons:
        pg.use_smooth = True
    return o


with into("site"):
    stage("site")
    gp = P(5.9, 4.6)
    K.box("lawn", gp.x - 400, gp.x + 400, gp.y - 400, gp.y + 400, GROUND - 0.05, GROUND, M["lawn"], bevel=0.0)
    S_ = PLAN["site"]
    for x0, x1, y0, y1 in S_["terrace"]:
        bx("terrace", x0, x1, y0, y1, GROUND, -0.03, M["terrace"], bevel=0.004)
    for x0, x1, y0, y1 in S_["path"]:
        bx("path", x0, x1, y0, y1, GROUND, GROUND + 0.02, M["gravel"], bevel=0.0)
    bx("step", 1.4, 1.57, 3.55, 4.62, -0.03, 0.0, M["stone"], bevel=0.004)
    for k, (x, y, r) in enumerate(S_["shrubs"]):
        blob("shrub", x, y, GROUND + r * 0.6, r, M["leaf_dark"], 0.85, k)
    for k, (x, y, h) in enumerate(S_["trees"]):
        p = P(x, y)
        K.tube("trunk", (p.x, p.y, GROUND), (p.x, p.y, GROUND + h * 0.65), 0.09, M["bark"], verts=12)
        for j in range(4):
            a = j * 1.7 + k
            blob("crown", x + 0.5 * math.cos(a), y + 0.5 * math.sin(a), GROUND + h * (0.7 + 0.12 * j), h * 0.32, M["leaf"], 0.8, j + k)
    bx("planter_bed", 1.84, 11.8, 9.2, 10.2, GROUND, GROUND + 0.02, M["gravel"], bevel=0.0)

with into("catcher"):
    gp = P(5.9, 4.6)
    K.box("shadow_catcher", gp.x - 30, gp.x + 30, gp.y - 30, gp.y + 30, -0.32, -0.3, M["white"], bevel=0.0)
    bpy.data.objects["shadow_catcher"].is_shadow_catcher = True

# ---------------------------------------------------------------- room labels with their areas (the top view only)
with into("labels"):
    for rm in PLAN["rooms"]:
        area = sum((x1 - x0) * (y1 - y0) for x0, x1, y0, y1 in rm["rects"])
        cu = bpy.data.curves.new("label_" + rm["name"], "FONT")
        cu.body = f"{rm['name']}\n{area:.2f} m²\n(plan {rm['area_plan']:g})".replace(".", ",")  # measured, then the plan's label
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.size = 0.26
        ob = K.link(bpy.data.objects.new("label_" + rm["name"], cu))
        ob.data.materials.append(M["label"])
        lp = P(*rm["label"])
        ob.location = (lp.x, lp.y, H + 0.3)
        for ray in ("diffuse", "glossy", "transmission", "shadow", "volume_scatter"):  # seen by the camera only
            setattr(ob, "visible_" + ray, False)
print(f"built in {time.time() - t0:.1f} s, {len(bpy.data.objects)} objects, {len(K.PARTS)} parts")

# ---------------------------------------------------------------- light: a physical sky and a low south-west sun
world = bpy.data.worlds.new("sky")
scene.world = world
world.use_nodes = True
WN, WL = world.node_tree.nodes, world.node_tree.links
bg = WN["Background"]
sky = WN.new("ShaderNodeTexSky")
sky.sky_type = "MULTIPLE_SCATTERING"
sky.sun_disc = False
# Blender's physical sky at strength 1 lights a white floor ~5x brighter than a 3 W/m2 sun, and deep blue: it runs at
# a few hundredths of that, half desaturated, so the sun leads and the shade stays cool without going blue
sky_hs = WN.new("ShaderNodeHueSaturation")
sky_hs.inputs["Saturation"].default_value = 0.55
WL.new(sky.outputs["Color"], sky_hs.inputs["Color"])
WL.new(sky_hs.outputs["Color"], bg.inputs["Color"])
studio = WN.new("ShaderNodeBackground")
studio.inputs["Color"].default_value = (0.9, 0.89, 0.87, 1)
lp_ = WN.new("ShaderNodeLightPath")
cam_mix = WN.new("ShaderNodeMixShader")
WL.new(bg.outputs[0], cam_mix.inputs[1])
WL.new(studio.outputs[0], cam_mix.inputs[2])
WL.new(cam_mix.outputs[0], WN["World Output"].inputs["Surface"])

sun = bpy.data.lights.new("sun", "SUN")
sun.angle = math.radians(1.0)
sun.color = (1.0, 0.92, 0.8)
so = K.link(bpy.data.objects.new("sun", sun))


def aim_sun(az_deg, el_deg, energy):
    """az: compass bearing of the sun (0 north, 90 east, 180 south, 225 south-west)."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    to_sun = Vector((math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)))
    so.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    sun.energy = energy
    sky.sun_elevation = el
    sky.sun_rotation = math.radians(90 - az_deg + 90)


def backdrop(studio_bg, strength):
    for lk in list(cam_mix.inputs[0].links):
        WL.remove(lk)
    if studio_bg:  # the camera sees a plain backdrop, the scene is still lit by the sky
        WL.new(lp_.outputs["Is Camera Ray"], cam_mix.inputs[0])
    else:
        cam_mix.inputs[0].default_value = 0.0
    bg.inputs["Strength"].default_value = strength


def show(**vis):
    for k, c in COLL.items():
        c.hide_render = not vis.get(k, False)


PORTALS = []


def portals(on):
    """Light portals in every exterior opening: Cycles samples the sky through the windows (interiors only)."""
    if on and not PORTALS:
        for o in PLAN["openings"]:
            if "_portal" not in o:
                continue
            w, a0, a1, z0, z1 = o["_portal"]
            s = outward(w)
            lo, hi = (w["y0"], w["y1"]) if axis_of(w) == "x" else (w["x0"], w["x1"])
            c = (lo - 0.02) if s < 0 else (hi + 0.02)
            mid = (a0 + a1) / 2
            x, y = (mid, c) if axis_of(w) == "x" else (c, mid)
            ld = bpy.data.lights.new("portal", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = a1 - a0, z1 - z0
            for holder in (ld, getattr(ld, "cycles", None)):
                if holder is not None and hasattr(holder, "is_portal"):
                    holder.is_portal = True
            lo_ = bpy.data.objects.new("portal", ld)
            ROOT.objects.link(lo_)
            lo_.location = W3(x, y, (z0 + z1) / 2)
            inward = Vector((0, -s, 0)) if axis_of(w) == "x" else Vector((-s, 0, 0))
            inward_w = Vector((inward.x, -inward.y, 0))
            lo_.rotation_euler = inward_w.to_track_quat("-Z", "Y").to_euler()
            PORTALS.append(lo_)
    for p in PORTALS:
        p.hide_render = not on


# ---------------------------------------------------------------- cameras and shots
def cam_at(name, p0, p1, z0, z1, lens, shift_y=0.0):
    return K.camera(name, W3(p0[0], p0[1], z0), W3(p1[0], p1[1], z1), lens, shift_y=shift_y)


def res(rx, ry):
    scene.render.resolution_x, scene.render.resolution_y = rx, ry


RES = tuple(map(int, str(OPTS.get("res", "1600x900")).split("x")))


def top():
    """Straight down, orthographic, north up, 100 px per metre at 1280 wide: lays over the plan (compare.py)."""
    show(labels=True, catcher=False)
    scene.render.film_transparent = True
    backdrop(True, 0.07)
    aim_sun(190, 74, 3.2)
    scene.view_settings.exposure = 0.2
    k = RES[0] / 1600
    res(int(1280 * k), int(1020 * k))
    c = K.camera("cam_top", (0, 0, 30), (0, 0, 0), 50)
    c.data.type = "ORTHO"
    c.data.ortho_scale = 12.8
    c.rotation_euler = (0, 0, 0)
    return c


def dollhouse():
    show(catcher=True)
    scene.render.film_transparent = True
    backdrop(True, 0.07)
    aim_sun(235, 42, 3.6)
    scene.view_settings.exposure = 0.0
    res(*RES)
    tgt = Vector((0.0, 0.1, 1.0))
    az_, el_, dist = math.radians(222), math.radians(50), 27.5
    loc = tgt + dist * Vector((math.cos(el_) * math.sin(az_), math.cos(el_) * math.cos(az_), math.sin(el_)))
    return K.camera("cam_dollhouse", loc, tgt, 42)


def exterior():
    show(roof=True, site=True)
    scene.render.film_transparent = False
    backdrop(False, 0.08)
    aim_sun(240, 30, 4.0)
    scene.view_settings.exposure = 0.0
    res(*RES)
    return cam_at("cam_exterior", (-4.3, 12.9), (4.9, 4.3), 1.6, 1.75, 22, shift_y=0.05)


def interior(p0, p1, lens, z=1.35, z1=None, shift_y=0.0, exposure=1.4):
    show(interior=True, roof=True, site=True)
    scene.render.film_transparent = False
    backdrop(False, 0.12)
    portals(True)
    aim_sun(235, 24, 4.0)
    scene.view_settings.exposure = float(OPTS.get("exposure", exposure))
    res(*RES)
    return cam_at("cam_interior", p0, p1, z, z if z1 is None else z1, lens, shift_y)


def living():
    return interior((2.35, 8.62), (4.9, 1.6), 17, z1=1.15)


def kitchen():
    return interior((4.85, 6.0), (2.7, 0.5), 18, z1=1.15, exposure=1.9)


def bedroom():
    return interior((6.35, 5.0), (8.1, 8.7), 16, z1=0.9, exposure=1.8)


SHOT = {"top": top, "dollhouse": dollhouse, "exterior": exterior, "living": living, "kitchen": kitchen, "bedroom": bedroom}
if OPTS.get("blend"):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(OUT, "plainpied.blend")))
for s in ([] if K.FILM else SHOTS):
    portals(False)
    cam = SHOT[s]()
    scene.camera = cam
    scene.render.filepath = os.path.abspath(os.path.join(OUT, f"render_{s}.png"))
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"rendered {s} in {time.time() - t1:.1f} s -> {scene.render.filepath}")
