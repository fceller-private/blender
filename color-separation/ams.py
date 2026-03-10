import bpy
import bmesh
import math
import colorsys
from collections import Counter

# --- KONFIGURATION ---

# 1. DEINE BAMBU AMS FILAMENTE
AMS_FILAMENTS = [
    (0.95, 0.95, 0.95), # 1. Weiß
    (0.02, 0.02, 0.02), # 2. Schwarz
    (0.18, 0.07, 0.03), # 3. Dunkelbraun
    (0.55, 0.40, 0.25), # 4. Hellbraun
    (0.30, 0.10, 0.40), # 5. Lila
    (0.75, 0.55, 0.05), # 6. Gold
]

# 2. MAXIMALE GLÄTTUNG
SMOOTHING_PASSES = 40

# 3. DIE ULTIMATIVE DAMPFWALZE
# 1500 Polygone löscht alle kleinen Reflexionen und Schattenreste.
MIN_REGION_SIZE = 1500

# 4. MESH UNTERTEILUNG
SUBDIVISIONS = 1 
# ---------------------

def get_distance(c1, c2):
    h1, s1, v1 = colorsys.rgb_to_hsv(c1[0], c1[1], c1[2])
    h2, s2, v2 = colorsys.rgb_to_hsv(c2[0], c2[1], c2[2])

    dh = min(abs(h1 - h2), 1.0 - abs(h1 - h2))
    ds = abs(s1 - s2)
    dv = abs(v1 - v2)

    # Spezial-Logik für Schwarz und Weiß
    # Wenn ein Filament fast schwarz ist, ignorieren wir den Farbton fast komplett
    is_dark = v2 < 0.1
    is_bright = v2 > 0.8 and s2 < 0.1
    
    if is_dark or is_bright:
        return dv * 2.0 + ds * 1.0 # Fokus nur auf Helligkeit/Sättigung
    
    # Für bunte Farben: Farbton ist alles!
    return (dh * 10.0) + (ds * 2.0) + (dv * 0.5)

def auto_setup_texture(obj):
    if not obj.data.materials: return False
    mat = obj.data.materials[0]
    if not getattr(mat, "use_nodes", False): mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    img_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.image), None)
    if not bsdf or not img_node: return False
    nodes.active = img_node
    links.new(img_node.outputs['Color'], bsdf.inputs['Base Color'])
    return True

def run_all_in_one():
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH': return

    print("=== START: AMS FILAMENT ULTIMATIVE REINIGUNG ===")

    if not auto_setup_texture(obj): return

    if SUBDIVISIONS > 0:
        print(f"1. Unterteile Mesh...")
        mod = obj.modifiers.new(name="SubSurf", type='SUBSURF')
        mod.levels = SUBDIVISIONS
        mod.subdivision_type = 'SIMPLE'
        bpy.ops.object.modifier_apply(modifier="SubSurf")

    print("2. Baking...")
    bpy.context.scene.render.engine = 'CYCLES'
    if not obj.data.vertex_colors:
        vcol = obj.data.vertex_colors.new(name="BakeColor")
    else:
        vcol = obj.data.vertex_colors.active
    obj.data.vertex_colors.active = vcol
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, target='VERTEX_COLORS')

    print("3. Analysiere Farben...")
    mesh = obj.data
    data = vcol.data
    face_to_best_i = {}
    for poly in mesh.polygons:
        item = data[poly.loop_indices[0]]
        c = (item.color[0], item.color[1], item.color[2]) if hasattr(item, 'color') else (1,1,1)
        best_i = min(range(len(AMS_FILAMENTS)), key=lambda i: get_distance(c, AMS_FILAMENTS[i]))
        face_to_best_i[poly.index] = best_i

    obj.data.materials.clear()
    for i, color in enumerate(AMS_FILAMENTS):
        mat = bpy.data.materials.new(name=f"AMS_Slot_{i+1}")
        mat.use_nodes = True
        mat.node_tree.nodes.get("Principled BSDF").inputs[0].default_value = (color[0], color[1], color[2], 1)
        obj.data.materials.append(mat)

    print("4. Glätte und reinige Mesh radikal...")
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    for f in bm.faces: f.material_index = face_to_best_i[f.index]

    # Aggressives Glätten
    for _ in range(SMOOTHING_PASSES):
        changes = {}
        for f in bm.faces:
            neighbor_mats = [n.material_index for e in f.edges for n in e.link_faces if n != f]
            if neighbor_mats:
                mc = Counter(neighbor_mats).most_common(1)[0][0]
                if f.material_index != mc and neighbor_mats.count(mc) >= len(neighbor_mats) / 2:
                    changes[f] = mc
        for f, nm in changes.items(): f.material_index = nm

    # Aggressiver Schmutzfilter
    for _ in range(4):
        visited = set()
        for face in bm.faces:
            if face.index in visited: continue
            island = []
            stack = [face]
            visited.add(face.index)
            curr_m = face.material_index
            while stack:
                curr = stack.pop()
                island.append(curr)
                for e in curr.edges:
                    for n in e.link_faces:
                        if n.index not in visited and n.material_index == curr_m:
                            visited.add(n.index)
                            stack.append(n)
            if len(island) < MIN_REGION_SIZE:
                nmats = [n.material_index for isl_f in island for e in isl_f.edges for n in e.link_faces if n.material_index != curr_m]
                if nmats:
                    target = Counter(nmats).most_common(1)[0][0]
                    for isl_f in island: isl_f.material_index = target
        bmesh.update_edit_mesh(mesh)

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    
    parts = bpy.context.selected_objects.copy()
    for part in parts:
        bpy.context.view_layer.objects.active = part
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='LOOSE')
        bpy.ops.object.mode_set(mode='OBJECT')

    final = bpy.context.selected_objects
    for p in final:
        bpy.context.view_layer.objects.active = p
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')

    print(f"=== FERTIG! {len(final)} saubere Teile. ===")

run_all_in_one()
