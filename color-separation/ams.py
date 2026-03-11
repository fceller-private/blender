import bpy
import bmesh
import math
import random
import colorsys
from collections import Counter

# --- KONFIGURATION ---

# 1. WIE VIELE FILAMENTE HAST DU IM AMS?
# Das Script findet automatisch die X wichtigsten Farben deines Modells.
TARGET_FILAMENT_COUNT = 6 

# 2. GLÄTTUNG & REINIGUNG
SMOOTHING_PASSES = 35
MIN_REGION_SIZE = 1200 

# 3. MESH UNTERTEILUNG
SUBDIVISIONS = 1 
# ---------------------

def get_distance(c1, c2):
    # HSV-basierte Distanz für bessere Farbtrennung
    h1, s1, v1 = colorsys.rgb_to_hsv(c1[0], c1[1], c1[2])
    h2, s2, v2 = colorsys.rgb_to_hsv(c2[0], c2[1], c2[2])
    dh = min(abs(h1 - h2), 1.0 - abs(h1 - h2))
    ds = abs(s1 - s2)
    dv = abs(v1 - v2)
    if v2 < 0.1 or (v2 > 0.8 and s2 < 0.1): 
        return dv * 2.0 + ds * 1.0
    return (dh * 10.0) + (ds * 2.0) + (dv * 0.5)

def run_all_in_one():
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH': return

    print("=== START: AUTOMATISCHE PALETTE & VOLUMEN-ZERLEGUNG ===")

    # 1. Vorbereitung & Baking
    if not obj.data.materials: return
    mat = obj.data.materials[0]
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    img_node = next((n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), None)
    if bsdf and img_node:
        mat.node_tree.links.new(img_node.outputs['Color'], bsdf.inputs['Base Color'])
        mat.node_tree.nodes.active = img_node

    if SUBDIVISIONS > 0:
        print("1. Unterteile Mesh...")
        mod = obj.modifiers.new(name="SubSurf", type='SUBSURF')
        mod.levels = SUBDIVISIONS
        mod.subdivision_type = 'SIMPLE'
        bpy.ops.object.modifier_apply(modifier="SubSurf")

    print("2. Baking (Generiere Farbdaten)...")
    bpy.context.scene.render.engine = 'CYCLES'
    if not obj.data.vertex_colors: obj.data.vertex_colors.new(name="BakeColor")
    vcol = obj.data.vertex_colors.active
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, target='VERTEX_COLORS')

    # 3. AUTOMATISCHE PALETTE FINDEN (K-Means)
    print(f"3. Extrahiere die {TARGET_FILAMENT_COUNT} wichtigsten Farben...")
    mesh = obj.data
    data = vcol.data
    all_colors = []
    for poly in mesh.polygons:
        item = data[poly.loop_indices[0]]
        all_colors.append((item.color[0], item.color[1], item.color[2]))

    # Initialisierung der Zentren (Zufällige Punkte aus dem Modell)
    centers = random.sample(all_colors, TARGET_FILAMENT_COUNT)
    
    # 10 Iterationen um die Palette zu verfeinern
    for _ in range(10):
        clusters = {i: [] for i in range(TARGET_FILAMENT_COUNT)}
        for c in all_colors:
            best_i = min(range(TARGET_FILAMENT_COUNT), key=lambda i: get_distance(c, centers[i]))
            clusters[best_i].append(c)
        
        for i in range(TARGET_FILAMENT_COUNT):
            if clusters[i]:
                centers[i] = tuple(sum(col[j] for col in clusters[i]) / len(clusters[i]) for j in range(3))

    print("   Gefundene Palette (RGB):")
    for i, c in enumerate(centers):
        print(f"   Filament {i+1}: {round(c[0],2)}, {round(c[1],2)}, {round(c[2],2)}")

    # 4. Zuweisung & Materialien
    obj.data.materials.clear()
    for i, color in enumerate(centers):
        new_mat = bpy.data.materials.new(name=f"Filament_{i+1}")
        new_mat.use_nodes = True
        new_mat.node_tree.nodes.get("Principled BSDF").inputs[0].default_value = (color[0], color[1], color[2], 1)
        obj.data.materials.append(new_mat)

    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        poly_color = all_colors[f.index]
        f.material_index = min(range(TARGET_FILAMENT_COUNT), key=lambda i: get_distance(poly_color, centers[i]))

    print("4. Glätte und Reinige Mesh...")
    for _ in range(SMOOTHING_PASSES):
        changes = {}
        for f in bm.faces:
            neighbor_mats = [n.material_index for e in f.edges for n in e.link_faces if n != f]
            if neighbor_mats:
                mc = Counter(neighbor_mats).most_common(1)[0][0]
                if f.material_index != mc and neighbor_mats.count(mc) >= len(neighbor_mats) / 2:
                    changes[f] = mc
        for f, nm in changes.items(): f.material_index = nm

    # Schmutz-Filter
    visited = set()
    for face in bm.faces:
        if face.index in visited: continue
        island = []
        stack = [face]; visited.add(face.index); curr_m = face.material_index
        while stack:
            curr = stack.pop(); island.append(curr)
            for e in curr.edges:
                for n in e.link_faces:
                    if n.index not in visited and n.material_index == curr_m:
                        visited.add(n.index); stack.append(n)
        if len(island) < MIN_REGION_SIZE:
            nmats = [n.material_index for isl_f in island for e in isl_f.edges for n in e.link_faces if n.material_index != curr_m]
            if nmats:
                target = Counter(nmats).most_common(1)[0][0]
                for isl_f in island: isl_f.material_index = target
    bmesh.update_edit_mesh(mesh)

    # 5. Zerschneiden & Schließen
    print("5. Erzeuge solide Bauteile...")
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
        
        # Löcher an den Schnittkanten schließen
        bm_p = bmesh.from_edit_mesh(bpy.context.active_object.data)
        bm_p.edges.ensure_lookup_table()
        boundary = [e for e in bm_p.edges if e.is_boundary]
        if boundary:
            bpy.ops.mesh.select_all(action='DESELECT')
            for e in boundary: e.select = True
            bpy.ops.mesh.edge_face_add()
        
        bmesh.update_edit_mesh(bpy.context.active_object.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')

    print(f"=== FERTIG! {len(bpy.context.selected_objects)} Teile erstellt ===")

run_all_in_one()
