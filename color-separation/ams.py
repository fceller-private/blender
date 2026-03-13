import bpy
import bmesh
import math
import random
import colorsys
from collections import Counter

# --- KONFIGURATION ---
MAX_COLORS = 6 
SMOOTHING_PASSES = 35
MIN_REGION_SIZE = 600   
MIN_VOLUME_PERCENTAGE = 0.05 
# ------------------------------

def get_hsv_distance(rgb1, rgb2):
    h1, s1, v1 = colorsys.rgb_to_hsv(rgb1[0], rgb1[1], rgb1[2])
    h2, s2, v2 = colorsys.rgb_to_hsv(rgb2[0], rgb2[1], rgb2[2])
    dh = min(abs(h1 - h2), 1.0 - abs(h1 - h2))
    ds = abs(s1 - s2)
    dv = abs(v1 - v2)
    return (dh * 10.0) + (ds * 2.0) + (dv * 1.0)

def get_obj_volume(obj):
    # Sicherstellen, dass das Objekt noch existiert
    if not obj or obj.name not in bpy.data.objects: return 0
    return obj.dimensions.x * obj.dimensions.y * obj.dimensions.z

def run_all_in_one():
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        print("FEHLER: Bitte ein Mesh-Objekt auswählen!")
        return

    print("\n" + "="*50)
    print("START: FIX - ERWEITERTE AMS-ZERLEGUNG")
    print("="*50)

    # 1. Mesh-Heilung
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    # 2. Baking & Palette
    print("\n[1/6] Farbanalyse läuft...")
    bpy.context.scene.render.engine = 'CYCLES'
    if not obj.data.vertex_colors:
        obj.data.vertex_colors.new(name="BakeColor")
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, target='VERTEX_COLORS')

    mesh = obj.data
    data = mesh.vertex_colors.active.data
    all_colors = [(data[p.loop_indices[0]].color[0], data[p.loop_indices[0]].color[1], data[p.loop_indices[0]].color[2]) for p in mesh.polygons]
    
    centers = random.sample(all_colors, MAX_COLORS)
    for _ in range(15):
        clusters = {i: [] for i in range(MAX_COLORS)}
        for c in all_colors:
            best_i = min(range(MAX_COLORS), key=lambda i: get_hsv_distance(c, centers[i]))
            clusters[best_i].append(c)
        for i in range(MAX_COLORS):
            if clusters[i]:
                centers[i] = tuple(sum(col[j] for col in clusters[i]) / len(clusters[i]) for j in range(3))

    print("\n--- GEFUNDENE PALETTE ---")
    for i, rgb in enumerate(centers):
        print(f"   Slot {i+1}: R:{int(rgb[0]*255):3} G:{int(rgb[1]*255):3} B:{int(rgb[2]*255):3}")

    obj.data.materials.clear()
    for i, color in enumerate(centers):
        new_mat = bpy.data.materials.new(name=f"AMS_Slot_{i+1}")
        new_mat.use_nodes = True
        new_mat.node_tree.nodes.get("Principled BSDF").inputs[0].default_value = (color[0], color[1], color[2], 1)
        obj.data.materials.append(new_mat)

    # 3. Zuweisung & Glättung
    print("\n[2/6] Glätte Kanten...")
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh)
    for f in bm.faces:
        f.material_index = min(range(MAX_COLORS), key=lambda i: get_hsv_distance(all_colors[f.index], centers[i]))

    for p in range(SMOOTHING_PASSES):
        changes = {}
        for f in bm.faces:
            nm = [n.material_index for e in f.edges for n in e.link_faces if n != f]
            if nm:
                mc = Counter(nm).most_common(1)[0][0]
                if f.material_index != mc and nm.count(mc) >= len(nm) / 2: changes[f] = mc
        for f, val in changes.items(): f.material_index = val
        if (p + 1) % 10 == 0: print(f"   Pass {p+1}/{SMOOTHING_PASSES} stabilisiert.")
    bmesh.update_edit_mesh(mesh)

    # 4. Zerschneiden
    print("\n[3/6] Zerlege nach Materialien...")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    
    color_groups = bpy.context.selected_objects.copy()

    # 5. Physische Trennung & Adoptions-Fix
    print("\n[4/6] Starte Massen-Adoption (Fix)...")
    final_objects = []

    for group_idx, group in enumerate(color_groups):
        bpy.context.view_layer.objects.active = group
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='LOOSE')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        loose_parts = bpy.context.selected_objects.copy()
        
        # Schwellenwert berechnen
        total_vol = sum([get_obj_volume(p) for p in loose_parts])
        threshold = total_vol * (MIN_VOLUME_PERCENTAGE / 100.0)
        
        main_parts = [p for p in loose_parts if get_obj_volume(p) >= threshold]
        tiny_parts = [p for p in loose_parts if get_obj_volume(p) < threshold]
        
        print(f"   Farbe {group_idx+1}: {len(main_parts)} Hauptteile, {len(tiny_parts)} Winzlinge.")

        if main_parts:
            # Ordne jeden Winzling einem Hauptteil zu (Mapping)
            adoption_plan = {mp.name: [] for mp in main_parts}
            for tp in tiny_parts:
                target = min(main_parts, key=lambda mp: (mp.location - tp.location).length)
                adoption_plan[target.name].append(tp)
            
            # Führe die Adoption gesammelt pro Hauptteil aus
            for target_name, kids in adoption_plan.items():
                target_obj = bpy.data.objects.get(target_name)
                if not target_obj or not kids: continue
                
                bpy.ops.object.select_all(action='DESELECT')
                for kid in kids:
                    if kid.name in bpy.data.objects:
                        kid.select_set(True)
                target_obj.select_set(True)
                bpy.context.view_layer.objects.active = target_obj
                bpy.ops.object.join() # Alle Kids auf einmal joinen
                
                if target_obj not in final_objects:
                    final_objects.append(target_obj)
        elif loose_parts:
            keep = max(loose_parts, key=get_obj_volume)
            final_objects.append(keep)

    # 6. Finalisierung
    print("\n[5/6] Versiegele Geometrie...")
    for i, p in enumerate(final_objects):
        if not p or p.name not in bpy.data.objects: continue
        bpy.context.view_layer.objects.active = p
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.fill_holes(sides=0)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
        if (i+1) % 5 == 0: print(f"   Fortschritt: {i+1}/{len(final_objects)} fertig.")

    print("\n" + "="*50)
    print(f"FERTIG! Finale Druckobjekte: {len(final_objects)}")
    print("="*50)

run_all_in_one()
