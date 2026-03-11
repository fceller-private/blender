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

# 2. GLÄTTUNG & REINIGUNG
SMOOTHING_PASSES = 30
MIN_REGION_SIZE = 1000  # Große Dampfwalze für saubere Flächen

# 3. MESH UNTERTEILUNG
SUBDIVISIONS = 1 
# ---------------------

def get_distance(c1, c2):
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

    print("=== START: GENERIERUNG VON FESTKÖRPERN (SOLID OBJECTS) ===")

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

    print("2. Baking...")
    bpy.context.scene.render.engine = 'CYCLES'
    if not obj.data.vertex_colors: obj.data.vertex_colors.new(name="BakeColor")
    vcol = obj.data.vertex_colors.active
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, target='VERTEX_COLORS')

    # 3. Farbe auslesen (Object Mode!)
    print("3. Analysiere Palette...")
    mesh = obj.data
    data = vcol.data
    face_to_best_i = {}
    for poly in mesh.polygons:
        item = data[poly.loop_indices[0]]
        c = (item.color[0], item.color[1], item.color[2]) if hasattr(item, 'color') else (1,1,1)
        face_to_best_i[poly.index] = min(range(len(AMS_FILAMENTS)), key=lambda i: get_distance(c, AMS_FILAMENTS[i]))

    # 4. Materialien & Reinigung
    obj.data.materials.clear()
    for i, color in enumerate(AMS_FILAMENTS):
        new_mat = bpy.data.materials.new(name=f"AMS_{i+1}")
        new_mat.use_nodes = True
        new_mat.node_tree.nodes.get("Principled BSDF").inputs[0].default_value = (color[0], color[1], color[2], 1)
        obj.data.materials.append(new_mat)

    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    for f in bm.faces: f.material_index = face_to_best_i[f.index]

    print("4. Glätte Kanten...")
    for _ in range(SMOOTHING_PASSES):
        changes = {}
        for f in bm.faces:
            neighbor_mats = [n.material_index for e in f.edges for n in e.link_faces if n != f]
            if neighbor_mats:
                mc = Counter(neighbor_mats).most_common(1)[0][0]
                if f.material_index != mc and neighbor_mats.count(mc) >= len(neighbor_mats) / 2:
                    changes[f] = mc
        for f, nm in changes.items(): f.material_index = nm

    print("5. Schmutz-Filter...")
    for _ in range(2):
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

    # 6. Zerschneiden
    print("6. Zerschneide Modell...")
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

    # 7. NEU: MAKE SOLID (Löcher schließen)
    print("7. Erzeuge Volumen (Schließe Löcher an den Schnittkanten)...")
    final_parts = bpy.context.selected_objects.copy()
    for p in final_parts:
        bpy.context.view_layer.objects.active = p
        bpy.ops.object.mode_set(mode='EDIT')
        bm_p = bmesh.from_edit_mesh(p.data)
        
        # Finde alle offenen Kanten (Non-Manifold)
        bm_p.edges.ensure_lookup_table()
        boundary_edges = [e for e in bm_p.edges if e.is_boundary]
        
        if boundary_edges:
            # Markiere alle offenen Kanten und schließe sie
            bpy.ops.mesh.select_all(action='DESELECT')
            for e in boundary_edges:
                e.select = True
            # Schließt die Löcher mit einem Face (F-Befehl)
            bpy.ops.mesh.edge_face_add()
            
        bmesh.update_edit_mesh(p.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')

    print(f"=== FERTIG! {len(final_parts)} solide Festkörper erstellt. ===")

run_all_in_one()
