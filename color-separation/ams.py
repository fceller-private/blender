import bpy
import bmesh
import math
import random
import colorsys
from collections import Counter

# --- KONFIGURATION (PRÄZISIONS-MODUS) ---
MAX_COLORS = 8          
SMOOTHING_PASSES = 30   
MIN_REGION_SIZE = 150   
MIN_VOLUME_PERCENTAGE = 0.02 
# ----------------------------------------

def show_message_box(message = "", title = "Achtung!", icon = 'ERROR'):
    """Erzeugt ein Info-Fenster in der Blender Oberfläche."""
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)

def get_hsv_distance(rgb1, rgb2):
    h1, s1, v1 = colorsys.rgb_to_hsv(rgb1[0], rgb1[1], rgb1[2])
    h2, s2, v2 = colorsys.rgb_to_hsv(rgb2[0], rgb2[1], rgb2[2])
    dh = min(abs(h1 - h2), 1.0 - abs(h1 - h2))
    ds = abs(s1 - s2)
    dv = abs(v1 - v2)
    return (dh * 20.0) + (ds * 5.0) + (dv * 1.0)

def safe_get_volume(obj_name):
    obj = bpy.data.objects.get(obj_name)
    if not obj: return 0
    return obj.dimensions.x * obj.dimensions.y * obj.dimensions.z

def advanced_repair(obj_name):
    obj = bpy.data.objects.get(obj_name)
    if not obj: return
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    loose_v = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_interior_faces()
    bpy.ops.mesh.delete(type='FACE')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.fill_holes(sides=60) 
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')

def run_all_in_one():
    # --- CHECK: IST ETWAS SELEKTIERT? ---
    base_obj = bpy.context.active_object
    
    if not base_obj:
        msg = "Kein Objekt selektiert! Bitte klicke den Hund an."
        print(f"\n[ABBBRUCH] {msg}")
        show_message_box(msg)
        return

    if base_obj.type != 'MESH':
        msg = f"'{base_obj.name}' ist kein Mesh! Bitte ein 3D-Modell wählen."
        print(f"\n[ABBRUCH] {msg}")
        show_message_box(msg)
        return
    # ------------------------------------

    print("\n" + "="*70)
    print(f"START: DIVERSITY-FOCUSED ZERLEGUNG FÜR '{base_obj.name}'")
    print("="*70)

    # 1. Analyse
    print("\n[1/6] Farbanalyse (USDZ-Check)...")
    color_attr = None
    for attr in base_obj.data.color_attributes:
        if "opacity" not in attr.name.lower() and 'COLOR' in attr.data_type:
            color_attr = attr
            break
            
    if color_attr:
        attr_data = color_attr.data
        all_colors = []
        for poly in base_obj.data.polygons:
            idx = poly.vertices[0] if color_attr.domain == 'POINT' else poly.loop_indices[0]
            c = attr_data[idx].color
            all_colors.append((c[0], c[1], c[2]))
    else:
        print("   -> Keine USDZ-Farben gefunden. Abbruch oder Baking nötig.")
        return

    # CLUSTERING (Extreme Diversity Modus)
    unique_colors = list(set([tuple(round(c, 3) for c in col) for col in all_colors]))
    centers = [random.choice(unique_colors)]
    while len(centers) < MAX_COLORS and len(centers) < len(unique_colors):
        next_c = max(unique_colors, key=lambda c: min(get_hsv_distance(c, existing) for existing in centers))
        centers.append(next_c)
    
    for _ in range(25):
        clusters = {idx: [] for idx in range(len(centers))}
        for c in all_colors:
            best_i = min(range(len(centers)), key=lambda idx: get_hsv_distance(c, centers[idx]))
            clusters[best_i].append(c)
        for idx in range(len(centers)):
            if clusters[idx]:
                centers[idx] = tuple(sum(col[j] for col in clusters[idx]) / len(clusters[idx]) for j in range(3))

    print("\n--- OPTIMIERTE FARB-PALETTE ---")
    for i, rgb in enumerate(centers):
        print(f"   Slot {i+1}: R:{int(rgb[0]*255):3} G:{int(rgb[1]*255):3} B:{int(rgb[2]*255):3}")

    base_obj.data.materials.clear()
    for i, color in enumerate(centers):
        mat = bpy.data.materials.new(name=f"Slot_{i+1}")
        mat.use_nodes = True
        mat.node_tree.nodes.get("Principled BSDF").inputs[0].default_value = (color[0], color[1], color[2], 1)
        base_obj.data.materials.append(mat)

    # 2. Glättung
    print("\n[2/6] Glättung & Detailschutz...")
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(base_obj.data)
    for f in bm.faces:
        f.material_index = min(range(len(centers)), key=lambda i: get_hsv_distance(all_colors[f.index], centers[i]))

    for _ in range(SMOOTHING_PASSES):
        changes = {}
        for f in bm.faces:
            nm = [n.material_index for e in f.edges for n in e.link_faces if n != f]
            if nm:
                mc = Counter(nm).most_common(1)[0][0]
                if f.material_index != mc and nm.count(mc) >= len(nm) / 1.5:
                    changes[f] = mc
        for f, val in changes.items(): f.material_index = val

    # Insel-Cleanup
    visited = set(); bm.faces.ensure_lookup_table()
    for face in bm.faces:
        if face.index in visited: continue
        island = []; stack = [face]; visited.add(face.index); curr_m = face.material_index
        while stack:
            curr = stack.pop(); island.append(curr)
            for e in curr.edges:
                for n in e.link_faces:
                    if n.index not in visited and n.material_index == curr_m:
                        visited.add(n.index); stack.append(n)
        if len(island) < MIN_REGION_SIZE:
            nmats = [n.material_index for f_isl in island for e in f_isl.edges for n in e.link_faces if n.material_index != curr_m]
            if nmats:
                target = Counter(nmats).most_common(1)[0][0]
                for f_isl in island: f_isl.material_index = target
    
    bmesh.update_edit_mesh(base_obj.data)

    # 3. Separation
    print("\n[3/6] Zerschneiden...")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    
    group_names = [o.name for o in bpy.context.selected_objects]
    final_names = []

    for idx, g_name in enumerate(group_names):
        group_obj = bpy.data.objects.get(g_name)
        if not group_obj: continue
        bpy.ops.object.select_all(action='DESELECT')
        group_obj.select_set(True)
        bpy.context.view_layer.objects.active = group_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='LOOSE')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        loose_names = [o.name for o in bpy.context.selected_objects]
        vols = {name: safe_get_volume(name) for name in loose_names}
        thresh = sum(vols.values()) * (MIN_VOLUME_PERCENTAGE / 100.0)
        mains = [n for n in loose_names if vols[n] >= thresh]
        tinies = [n for n in loose_names if vols[n] < thresh]
        
        if mains:
            for t in tinies:
                t_obj = bpy.data.objects.get(t)
                if not t_obj: continue
                target = min(mains, key=lambda m: (bpy.data.objects[m].location - t_obj.location).length)
                bpy.ops.object.select_all(action='DESELECT')
                t_obj.select_set(True)
                bpy.data.objects[target].select_set(True)
                bpy.context.view_layer.objects.active = bpy.data.objects[target]
                bpy.ops.object.join()
            
            bpy.ops.object.select_all(action='DESELECT')
            for m in mains:
                if m in bpy.data.objects: bpy.data.objects[m].select_set(True)
            primary = bpy.data.objects.get(mains[0])
            if primary:
                bpy.context.view_layer.objects.active = primary
                bpy.ops.object.join()
                primary.name = f"FINAL_BLOCK_{idx+1}"
                final_names.append(primary.name)

    # 4. Final Repair
    print("\n[4/6] Finale Reparatur...")
    for f_name in final_names:
        advanced_repair(f_name)
        print(f"   -> Block '{f_name}' versiegelt.")

    print("\n" + "="*70)
    print(f"FERTIG! Das Modell besteht nun aus {len(final_names)} farbechten Blöcken.")
    print("="*70)

run_all_in_one()
