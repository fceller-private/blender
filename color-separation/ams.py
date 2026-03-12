import bpy
import bmesh
import math
import random
import colorsys
from collections import Counter

# --- KONFIGURATION ---

# 1. MAXIMALE ANZAHL AN FARBEN (Automatische Suche)
MAX_COLORS = 6 

# 2. FILTER-EINSTELLUNGEN
SMOOTHING_PASSES = 35
MIN_REGION_SIZE = 1500  

# 3. MESH UNTERTEILUNG
SUBDIVISIONS = 1 

# 4. GRÖSSEN-FILTER (Neu)
# Löscht Teile, die kleiner als X Prozent des Gesamtvolumens sind.
MIN_VOLUME_PERCENTAGE = 1.0 # 1.0 = 1%
# ---------------------

def get_hsv_distance(rgb1, rgb2):
    h1, s1, v1 = colorsys.rgb_to_hsv(rgb1[0], rgb1[1], rgb1[2])
    h2, s2, v2 = colorsys.rgb_to_hsv(rgb2[0], rgb2[1], rgb2[2])
    dh = min(abs(h1 - h2), 1.0 - abs(h1 - h2))
    ds = abs(s1 - s2)
    dv = abs(v1 - v2)
    return (dh * 10.0) + (ds * 2.0) + (dv * 1.0)

def cleanup_islands(bm, threshold, label=""):
    visited = set()
    total_islands = 0
    removed_count = 0
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        if face.index in visited: continue
        total_islands += 1
        island = []
        stack = [face]; visited.add(face.index); curr_m = face.material_index
        while stack:
            curr = stack.pop(); island.append(curr)
            for e in curr.edges:
                for n in e.link_faces:
                    if n.index not in visited and n.material_index == curr_m:
                        visited.add(n.index); stack.append(n)
        if len(island) < threshold:
            nmats = [n.material_index for f_isl in island for e in f_isl.edges for n in e.link_faces if n.material_index != curr_m]
            if nmats:
                target = Counter(nmats).most_common(1)[0][0]
                for f_isl in island: f_isl.material_index = target
                removed_count += 1
    print(f"   [{label}] Analyse: {total_islands} Gebiete. {removed_count} Inseln < {threshold} Polys entfernt.")
    return removed_count

def get_obj_volume(obj):
    """Berechnet das Volumen der Bounding Box als Proxy für die Größe."""
    return obj.dimensions.x * obj.dimensions.y * obj.dimensions.z

def run_all_in_one():
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH': return

    print("\n=== START: AMS-ZERLEGUNG MIT 1%-FILTER-REINIGUNG ===")

    # 0. Mesh heilen
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles()
    bpy.ops.object.mode_set(mode='OBJECT')

    # 1. Subdivision
    if not obj.data.materials: return
    if SUBDIVISIONS > 0:
        print("1. Unterteile Mesh...")
        mod = obj.modifiers.new(name="SubSurf", type='SUBSURF')
        mod.levels = SUBDIVISIONS
        mod.subdivision_type = 'SIMPLE'
        bpy.ops.object.modifier_apply(modifier="SubSurf")

    # 2. Baking
    print("2. Baking Farbdaten...")
    bpy.context.scene.render.engine = 'CYCLES'
    if not obj.data.vertex_colors: obj.data.vertex_colors.new(name="BakeColor")
    vcol = obj.data.vertex_colors.active
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, target='VERTEX_COLORS')

    # 3. Palette finden
    print(f"3. Extrahiere {MAX_COLORS} Hauptfarben...")
    mesh = obj.data
    data = vcol.data
    all_colors = [(data[p.loop_indices[0]].color[0], data[p.loop_indices[0]].color[1], data[p.loop_indices[0]].color[2]) for p in mesh.polygons]
    centers = random.sample(all_colors, MAX_COLORS)
    for _ in range(15):
        clusters = {i: [] for i in range(MAX_COLORS)}
        for c in all_colors:
            best_i = min(range(MAX_COLORS), key=lambda i: get_hsv_distance(c, centers[i]))
            clusters[best_i].append(c)
        for i in range(MAX_COLORS):
            if clusters[i]: centers[i] = tuple(sum(col[j] for col in clusters[i]) / len(clusters[i]) for j in range(3))

    print("\n--- GEFUNDENE FARB-PALETTE (RGB) ---")
    for i, rgb in enumerate(centers):
        print(f"Farbe {i+1}: R:{int(rgb[0]*255)} G:{int(rgb[1]*255)} B:{int(rgb[2]*255)}")
    print("------------------------------------\n")

    # 4. Materialien & Zuweisung
    obj.data.materials.clear()
    for i, color in enumerate(centers):
        new_mat = bpy.data.materials.new(name=f"Filament_{i+1}")
        new_mat.use_nodes = True
        new_mat.node_tree.nodes.get("Principled BSDF").inputs[0].default_value = (color[0], color[1], color[2], 1)
        obj.data.materials.append(new_mat)

    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    for f in bm.faces: f.material_index = min(range(MAX_COLORS), key=lambda i: get_hsv_distance(all_colors[f.index], centers[i]))

    # 5. Reinigung (Smoothing mit Output)
    print(f"4. Glätte Kanten ({SMOOTHING_PASSES} Durchläufe)...")
    for pass_idx in range(SMOOTHING_PASSES):
        changes = {}
        for f in bm.faces:
            nm = [n.material_index for e in f.edges for n in e.link_faces if n != f]
            if nm:
                mc = Counter(nm).most_common(1)[0][0]
                if f.material_index != mc and nm.count(mc) >= len(nm) / 2: changes[f] = mc
        for f, val in changes.items(): f.material_index = val
        if (pass_idx + 1) % 10 == 0 or pass_idx == 0:
            print(f"   Pass {pass_idx + 1}: {len(changes)} Flächen angepasst.")

    cleanup_islands(bm, MIN_REGION_SIZE, label="PASS 1")
    cleanup_islands(bm, MIN_REGION_SIZE, label="PASS 2")
    bmesh.update_edit_mesh(mesh)

    # 6. Zerschneiden
    print("5. Zerschneide Modell nach Farben...")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    
    parts_initial = bpy.context.selected_objects.copy()
    for part in parts_initial:
        bpy.context.view_layer.objects.active = part
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='LOOSE')
        bpy.ops.object.mode_set(mode='OBJECT')

    # 7. VERSIEGELN & GRÖSSEN-CHECK
    print("6. Mache Teile wasserdicht & entferne Winzlinge...")
    all_loose_parts = bpy.context.selected_objects.copy()
    
    # Berechne Figurengröße
    total_volume = sum([get_obj_volume(p) for p in all_loose_parts])
    min_volume_threshold = total_volume * (MIN_VOLUME_PERCENTAGE / 100.0)
    
    final_count = 0
    deleted_count = 0

    for i, p in enumerate(all_loose_parts):
        # 1. Größen-Check vorab
        if get_obj_volume(p) < min_volume_threshold:
            name_tmp = p.name
            bpy.data.objects.remove(p, do_unlink=True)
            deleted_count += 1
            continue
        
        # 2. Wenn groß genug: Versiegeln
        bpy.context.view_layer.objects.active = p
        bpy.ops.object.mode_set(mode='EDIT')
        bm_p = bmesh.from_edit_mesh(p.data)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.fill_holes(sides=0) 
        bmesh.update_edit_mesh(p.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
        
        final_count += 1
        print(f"      [{i+1}/{len(all_loose_parts)}] '{p.name}' verarbeitet.")

    print(f"\n--- ZUSAMMENFASSUNG ---")
    print(f"   Erhaltene Teile: {final_count}")
    print(f"   Entfernte Winzlinge (< {MIN_VOLUME_PERCENTAGE}%): {deleted_count}")
    print(f"=== FERTIG! Bereit für den Export. ===")

run_all_in_one()
