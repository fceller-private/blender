import bpy

def normalize_with_color_preservation(voxel_size=0.02):
    # 1. Vorbereitung
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    original_obj = bpy.context.active_object
    if not original_obj or original_obj.type != 'MESH':
        print("Kein Mesh ausgewählt!")
        return

    # Namen speichern für später
    orig_name = original_obj.name

    # 2. Kopie erstellen (als Farbreferenz)
    bpy.ops.object.duplicate()
    remeshed_obj = bpy.context.active_object
    remeshed_obj.name = orig_name + "_3D_Print"

    # 3. Geometrie normalisieren (Voxel Remesh)
    # Das zerstört die Topologie, aber macht es wasserdicht
    mod_remesh = remeshed_obj.modifiers.new(name="Remesh", type='REMESH')
    mod_remesh.mode = 'VOXEL'
    mod_remesh.voxel_size = voxel_size
    bpy.ops.object.modifier_apply(modifier="Remesh")

    # 4. Cleanup (Löcher & Normalen)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.mesh.fill_holes(sides=0)
    bpy.ops.object.mode_set(mode='OBJECT')

    # 5. Farbübertragung (Vertex Color Transfer)
    # Wir übertragen die Farben vom Original auf das neue Mesh
    mod_transfer = remeshed_obj.modifiers.new(name="Transfer", type='DATA_TRANSFER')
    mod_transfer.object = original_obj
    mod_transfer.use_loop_data = True
    mod_transfer.data_types_loops = {'VCOL'} # Vertex Colors
    mod_transfer.loop_mapping = 'NEAREST_POLYNOR' # Beste Projektion für organische Formen
    
    # Vertex Color Layer erstellen, falls nicht vorhanden
    if not remeshed_obj.data.color_attributes:
        bpy.ops.geometry.color_attribute_add(name="Color", domain='CORNER', data_type='BYTE_COLOR')
    
    bpy.ops.object.modifier_apply(modifier="Transfer")

    # 6. Original verstecken
    original_obj.hide_viewport = True
    print(f"Fertig! '{remeshed_obj.name}' ist bereit für den Druck inklusive Farben.")

# Ausführung
normalize_with_color_preservation(voxel_size=0.015)
