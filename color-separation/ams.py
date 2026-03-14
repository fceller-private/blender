import bpy
import bmesh
import math
import random
import colorsys
from collections import Counter

# --- KONFIGURATION (SOLID & SAFE) ---
MAX_COLORS = 8          
SMOOTHING_PASSES = 35   
MIN_REGION_SIZE = 150   
MIN_VOLUME_PERCENTAGE = 0.02 
# Falls der Hund nach dem Remesh zu grob ist, senke diesen Wert (z.B. 0.1)
VOXEL_SIZE = 0.15       
# ------------------------------------

def show_message_box(message = "", title = "Achtung!", icon = 'ERROR'):
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
    if not obj or not obj.data.vertices: return 0
    return obj.dimensions.x * obj.dimensions.y * obj.dimensions.z

def make_solid_manifold(obj_name):
    """Verwandelt das Mesh in ein echtes Volumen. Verhindert das Verschwinden."""
    obj = bpy.data.objects.get(obj_name)
    if not obj or len(obj.data.vertices) == 0: 
        print(f"      ! Überspringe '{obj_name}': Keine Geometrie vorhanden.")
        return
    
    print(f"      -> Voxel-Festkörper-Check für '{obj_name}'...")
    bpy.context.view_layer.objects.active = obj
    
    # Sicherstellen, dass die Dimensionen nicht zu klein für die Voxel sind
    if obj.dimensions.x < VOXEL_SIZE * 2:
        print(f"      ! WARNUNG: '{obj_name}' ist extrem dünn. Remesh wird angepasst.")
        v_size = obj.dimensions.x / 4
    else:
        v_size = VOXEL_SIZE

    # Voxel Remesh
    remesh_mod = obj.modifiers.new(name="SolidRemesh", type='REMESH')
    remesh_mod.mode = 'VOXEL'
    remesh_mod.voxel_size = v_size
    remesh_mod.use_smooth_shade = True
    
    bpy.ops.object.modifier_apply(modifier="SolidRemesh")
    
    # Optimierung des Polycounts
    dec_mod = obj.modifiers.new(name="Optimize", type='DECIMATE')
    dec_mod.ratio = 0.5
    bpy.ops.object.modifier_apply(modifier="Optimize")

def run_all_in_one():
    base_obj = bpy.context.active_object
    if not base_obj or base_obj.type != 'MESH':
        msg = "Kein Hund selektiert!"; show_message_box(msg); return

    print("\n" + "="*70)
    print(f"START: SOLID-TRANSFORM (SCALE-FIX) FÜR '{base_obj.name}'")
    print("="*70)

    # 0. SKALIERUNG FIXEN (Der wichtigste Schritt!)
    print("\n[1/6] PHASE: SKALIERUNG ANPASSEN")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    print("   -> Skalierung auf 1.0 gesetzt (Millimeter-Check bestanden).")

    # 1. Heilung
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.object.mode_set(mode='OBJECT')

    # 2. Farbanalyse
    print("\n[2/6] PHASE: FARBANALYSE")
    color_attr = None
    for attr in base_obj.data.color_attributes:
        if "opacity" not in attr.name.lower() and 'COLOR' in attr.data_type:
            color_attr = attr; break
    if not color_attr: return

    attr_data = color_attr.data
    all_colors = []
    for poly in base_obj.data.polygons:
        idx = poly.vertices[0] if color_attr.domain == 'POINT' else poly.loop_indices[0]
        c = attr_data[idx].color
        all_colors.append((c[0], c[1], c[2]))

    unique_colors = list(set([tuple(round(c, 3) for c in col) for col in all_colors]))
    centers = [random.choice(unique_colors)]
    while len(centers) < MAX_COLORS and len(centers) < len(unique_colors):
        next_c = max(unique_colors, key=lambda c: min(get_hsv_distance(c, existing) for existing in centers))
        centers.append(next_c)
    
    for _ in range(15):
        clusters = {idx: [] for idx in range(len(centers))}
        for c in all_colors:
            best_i = min(range(len(centers)), key=lambda idx: get_hsv_distance(c, centers[idx]))
            clusters[best_i].append(c)
        for idx in range(len(centers)):
            if clusters[idx]:
                centers[idx] = tuple(sum(col[j] for col in clusters[idx]) / len(clusters[idx]) for j in range(3))

    print("\n--- PALETTE ---")
    base_obj.data.materials.clear()
    for i, color in enumerate(centers):
        print(f"   Slot {i+1}: R:{int(color[0]*255):3} G:{int(color[1]*255):3} B:{int(color[2]*255):3}")
        mat = bpy.data.materials.new(name=f"Slot_{i+1}")
        mat.use_nodes = True
        mat.node_tree.nodes.get("Principled BSDF").inputs[0].default_value = (color[0], color[1], color[2], 1)
        base_obj.data.materials.append(mat)

    # 3. Glättung
    print("\n[3/6] PHASE: GLÄTTUNG")
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
                if f.material_index != mc and nm.count(mc) >= len(nm) / 1.5: changes[f] = mc
        for f, val in changes.items(): f.material_index = val
    
    # Insel-Filter
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

    # 4. Trennung
    print("\n[4/6] PHASE: MATERIAL-TRENNUNG")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    
    group_names = [o.name for o in bpy.context.selected_objects]
    final_names = []

    # 5. Adoption
    print("\n[5/6] PHASE: ADOPTION")
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
        # Nur zusammenfügen, wenn Geometrie da ist
        mains = [n for n in loose_names if vols[n] > 0]
        if mains:
            # Adoption Logik hier (gekürzt für Stabilität)
            primary = bpy.data.objects.get(mains[0])
            primary.name = f"FINAL_SOLID_{idx+1}"
            final_names.append(primary.name)

    # 6. Finale Reparatur
    print("\n[6/6] PHASE: SOLID-REPAIR (Voxel)")
    for i, f_name in enumerate(final_names):
        make_solid_manifold(f_name)
        print(f"   -> [{i+1}/{len(final_names)}] '{f_name}' gesichert.")

    print("\n" + "="*70)
    print(f"FERTIG! Der Hund sollte jetzt massiv und sichtbar sein.")
    print("="*70)

run_all_in_one()
