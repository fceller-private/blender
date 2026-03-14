import bpy
import bmesh
import math
import random
import colorsys
from collections import Counter

# --- KONFIGURATION (PRO-FIX EDITION) ---
MAX_COLORS = 12         
SMOOTHING_PASSES = 15   
MIN_REGION_SIZE = 40    
WALL_THICKNESS = 2.0    

# MANUELLE KORREKTUR: 
# Slot 11 (Fast-Weiß) -> Slot 8 (Reinweiß)
MERGE_REMAP = {11: 8} 
# ---------------------------------------

def show_message_box(message = "", title = "Status", icon = 'INFO'):
    def draw(self, context): self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)

def get_hsv_dist(c1, c2):
    h1, s1, v1 = colorsys.rgb_to_hsv(c1[0], c1[1], c1[2])
    h2, s2, v2 = colorsys.rgb_to_hsv(c2[0], c2[1], c2[2])
    dh = min(abs(h1 - h2), 1.0 - abs(h1 - h2))
    return (dh * 100) + (abs(s1 - s2) * 25) + (abs(v1 - v2) * 15)

def safe_get_volume(obj_name):
    obj = bpy.data.objects.get(obj_name)
    if not obj or not obj.data or not obj.data.vertices: return 0
    return obj.dimensions.x * obj.dimensions.y * obj.dimensions.z

def run_all_in_one():
    base_obj = bpy.context.active_object
    if not base_obj or base_obj.type != 'MESH':
        show_message_box("Fehler: Kein Hund ausgewählt!"); return

    print("\n" + "="*80)
    print(f"REMAP-LOG: ZERLEGUNG FÜR '{base_obj.name}' (11 -> 8)")
    print("="*80)

    # 1. Vorbereitung
    print("\n[1/6] PHASE: INITIALE REINIGUNG")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(base_obj.data)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    bmesh.update_edit_mesh(base_obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')

    # 2. Farbanalyse
    print("\n[2/6] PHASE: DIVERSITY-FARBANALYSE")
    color_attr = None
    for attr in base_obj.data.color_attributes:
        if "color" in attr.name.lower() and "opacity" not in attr.name.lower():
            color_attr = attr; break
    if not color_attr: return

    attr_data = color_attr.data
    poly_colors = [tuple(attr_data[p.vertices[0] if color_attr.domain == 'POINT' else p.loop_indices[0]].color)[:3] for p in base_obj.data.polygons]
    unique_colors = list(set([tuple(round(c, 3) for c in col) for col in poly_colors]))
    
    centers = [random.choice(unique_colors)]
    while len(centers) < MAX_COLORS and len(centers) < len(unique_colors):
        next_c = max(unique_colors, key=lambda c: min(get_hsv_dist(c, ex) for ex in centers))
        centers.append(next_c)

    print("\n--- FILAMENT-PALETTE (VOR REMAP) ---")
    base_obj.data.materials.clear()
    for i, color in enumerate(centers):
        rgb = tuple(int(c * 255) for c in color)
        print(f"   Slot {i+1:2}: RGB({rgb[0]:3}, {rgb[1]:3}, {rgb[2]:3})")
        mat = bpy.data.materials.new(name=f"Slot_{i+1}_RGB_{rgb[0]}_{rgb[1]}_{rgb[2]}")
        mat.use_nodes = True
        mat.node_tree.nodes.get("Principled BSDF").inputs[0].default_value = (color[0], color[1], color[2], 1)
        base_obj.data.materials.append(mat)

    # 3. Zuweisung & Remap
    print("\n[3/6] PHASE: ZUWEISUNG & REMAP-LOGIK")
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(base_obj.data)
    
    for f in bm.faces:
        raw_idx = min(range(len(centers)), key=lambda i: get_hsv_dist(poly_colors[f.index], centers[i]))
        slot_nr = raw_idx + 1
        
        if slot_nr in MERGE_REMAP:
            target_slot = MERGE_REMAP[slot_nr]
            f.material_index = target_slot - 1
        else:
            f.material_index = raw_idx

    bmesh.update_edit_mesh(base_obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')

    # 4. Silo-Trennung
    print("\n[4/6] PHASE: MATERIAL-TRENNUNG")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    
    silo_names = [o.name for o in bpy.context.selected_objects]

    # 5. Volumen-Chirurgie
    print("\n[5/6] PHASE: VOLUMEN-CHIRURGIE")
    final_names = []
    for s_name in silo_names:
        s_obj = bpy.data.objects.get(s_name)
        if not s_obj or len(s_obj.data.polygons) == 0:
            if s_obj: bpy.data.objects.remove(s_obj, do_unlink=True)
            continue
        
        print(f"   -> Bearbeite Silo: {s_obj.active_material.name}...")
        bpy.context.view_layer.objects.active = s_obj
        bpy.ops.object.select_all(action='DESELECT')
        s_obj.select_set(True)
        
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='LOOSE')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        loose_names = [o.name for o in bpy.context.selected_objects]
        mains = [n for n in loose_names if safe_get_volume(n) > 0.0001]
        
        if mains:
            bpy.ops.object.select_all(action='DESELECT')
            for m in mains:
                obj = bpy.data.objects.get(m)
                if obj: obj.select_set(True)
            
            target_obj = bpy.data.objects.get(mains[0])
            bpy.context.view_layer.objects.active = target_obj
            bpy.ops.object.join()
            
            res_obj = bpy.context.active_object
            res_obj.name = f"SOLID_{s_obj.active_material.name}"
            
            sol = res_obj.modifiers.new(name="SiloSolid", type='SOLIDIFY')
            sol.thickness = WALL_THICKNESS
            sol.offset = -1
            bpy.ops.object.modifier_apply(modifier="SiloSolid")
            
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.normals_make_consistent(inside=False)
            bpy.ops.object.mode_set(mode='OBJECT')
            final_names.append(res_obj.name)
            print(f"      - {len(mains)} Teile zu massivem Block vereint.")
        else:
            for n in loose_names:
                o_del = bpy.data.objects.get(n)
                if o_del: bpy.data.objects.remove(o_del, do_unlink=True)

    print("\n" + "="*80)
    print(f"FERTIG! {len(final_names)} massive Farb-Blöcke erstellt.")
    print("="*80)

run_all_in_one()
