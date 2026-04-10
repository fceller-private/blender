import bpy
import time

def normalize_with_debug(voxel_size=0.01):
    print("\n" + "="*50)
    print("START: 3D-Druck Normalisierung (Blender 5.x)")
    print("="*50)
    
    start_time = time.time()

    # 1. Objekt-Check
    original_obj = bpy.context.active_object
    if not original_obj or original_obj.type != 'MESH':
        print("[ERROR] Kein gültiges Mesh-Objekt ausgewählt!")
        return

    print(f"[INFO] Verarbeite Objekt: '{original_obj.name}'")
    print(f"[INFO] Ausgangs-Polygone: {len(original_obj.data.polygons)}")

    # 2. Vorbereitung
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    
    # Scale anwenden (wichtig für Voxel-Berechnung)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    print("[DEBUG] Transformationen angewendet (Scale auf 1.0).")

    # 3. Kopie erstellen
    bpy.ops.object.duplicate()
    remeshed_obj = bpy.context.active_object
    remeshed_obj.name = original_obj.name + "_SOLID_PRINT"
    print(f"[DEBUG] Kopie erstellt: '{remeshed_obj.name}'")

    # 4. Voxel Remesh (Solid Hull)
    print(f"[PROCESS] Starte Voxel Remesh (Voxel Size: {voxel_size})...")
    remesh_start = time.time()
    
    mod_remesh = remeshed_obj.modifiers.new(name="Remesh", type='REMESH')
    mod_remesh.mode = 'VOXEL'
    mod_remesh.voxel_size = voxel_size
    mod_remesh.adaptivity = 0.0
    
    bpy.ops.object.modifier_apply(modifier="Remesh")
    print(f"[DEBUG] Remesh abgeschlossen (Dauer: {time.time() - remesh_start:.2f}s)")

    # 5. Geometrie-Cleanup
    print("[PROCESS] Bereinige Non-Manifolds und schließe Löcher...")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    
    # Normalen fixen
    bpy.ops.mesh.normals_make_consistent(inside=False)
    # Löcher stopfen
    bpy.ops.mesh.fill_holes(sides=0)
    # Lose Teile löschen
    bpy.ops.mesh.delete_loose()
    
    bpy.ops.object.mode_set(mode='OBJECT')
    print("[DEBUG] Mesh-Cleanup beendet.")

    # 6. Farberhalt (Data Transfer)
    print("[PROCESS] Übertrage Farbattribute (Blender 5 COLOR_CORNER)...")
    
    # Attribut Layer erstellen
    if not remeshed_obj.data.color_attributes:
        remeshed_obj.data.color_attributes.new(
            name="Attribute", 
            type='BYTE_COLOR', 
            domain='CORNER'
        )

    mod_transfer = remeshed_obj.modifiers.new(name="Transfer", type='DATA_TRANSFER')
    mod_transfer.object = original_obj
    mod_transfer.use_loop_data = True
    mod_transfer.data_types_loops = {'COLOR_CORNER'} 
    mod_transfer.loop_mapping = 'NEAREST_POLYNOR'
    
    bpy.ops.object.modifier_apply(modifier="Transfer")
    print("[DEBUG] Farbübertragung abgeschlossen.")

    # 7. Abschluss-Statistik
    total_time = time.time() - start_time
    original_obj.hide_viewport = True # Original ausblenden zur Kontrolle
    
    print("-" * 50)
    print(f"FINISH: Objekt ist bereit für den Slicer.")
    print(f"Endgültige Polygone: {len(remeshed_obj.data.polygons)}")
    print(f"Gesamtdauer: {total_time:.2f} Sekunden")
    print("=" * 50 + "\n")

# Ausführung
normalize_with_debug(voxel_size=0.01)
