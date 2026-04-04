import bpy

# --- CONFIG ---
# Höherer Wert = schärferer Text, aber längere Rechenzeit (400-600 ist ideal)
DETAIL_LEVEL = 500 
# Bläht Teile vor dem Verschmelzen leicht auf, um Lücken zu schließen
INFLATE_STRENGTH = 0.0005 

def run_ultimate_trophy_pipeline():
    # 0. Initialer Check
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    selected_objs = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
    if len(selected_objs) == 0:
        print("Fehler: Bitte alle Teile der Trophäe auswählen!")
        return

    print("\n" + "="*70)
    print("STARTE ULTIMATIVE SOLID-PIPELINE")
    print("="*70)

    # 1. FARB-BACKUP (Sichert die Originale für den späteren Transfer)
    print("[1/6] Erstelle Farb-Backup...")
    bpy.ops.object.duplicate()
    backup_parts = bpy.context.selected_objects.copy()
    source_obj = backup_parts[0]
    bpy.context.view_layer.objects.active = source_obj
    if len(backup_parts) > 1:
        bpy.ops.object.join()
    source_obj.name = "FARB_BACKUP_TEMP"
    source_obj.hide_viewport = True # Verstecken, damit es nicht stört
    bpy.ops.object.select_all(action='DESELECT')

    # 2. VORBEREITUNG & DILATE (Lücken schließen)
    print("[2/6] Schließe Schnittlinien-Lücken (Dilate)...")
    for o in selected_objs:
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        
        # Jedes Teil minimal aufblasen, damit sie sich sicher überschneiden
        disp = o.modifiers.new(name="GapFill", type='DISPLACE')
        disp.strength = INFLATE_STRENGTH
        bpy.ops.object.modifier_apply(modifier="GapFill")

    # 3. ZUSAMMENFÜHREN (Join)
    print("[3/6] Führe Teile zusammen...")
    main_obj = selected_objs[0]
    bpy.context.view_layer.objects.active = main_obj
    bpy.ops.object.join()

    # 4. VOXEL-SOLID (Innere Elemente entfernen & Löcher schließen)
    print("[4/6] Erzeuge Solid-Hülle (Voxel Remesh)...")
    max_dim = max(main_obj.dimensions)
    v_size = max_dim / DETAIL_LEVEL
    
    remesh = main_obj.modifiers.new(name="Solidify", type='REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = v_size
    remesh.use_remove_disconnected = True # Entfernt lose Fragmente
    bpy.ops.object.modifier_apply(modifier="Solidify")

    # 5. GEOMETRIE-FINALE (Normalen & Triangulierung)
    print("[5/6] Korrigiere Normalen und trianguliere...")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    # Triangulierung für Bambu Studio
    bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
    bpy.ops.object.mode_set(mode='OBJECT')

    # 6. FARB-TRANSFER & MATERIAL
    print("[6/6] Projiziere Farben zurück und erstelle Material...")
    if not main_obj.data.color_attributes:
        main_obj.data.color_attributes.new(name="Color", type='BYTE_COLOR', domain='CORNER')
    
    attr_name = main_obj.data.color_attributes.active.name

    dt = main_obj.modifiers.new(name="ColorTransfer", type='DATA_TRANSFER')
    dt.object = source_obj
    dt.use_loop_data = True
    dt.data_types_loops = {'COLOR_CORNER'}
    dt.loop_mapping = 'POLYINTERP_LNORPROJ' # Bester Modus für Texturen/Vertex-Farben
    
    bpy.ops.object.datalayout_transfer(modifier="ColorTransfer")
    bpy.ops.object.modifier_apply(modifier="ColorTransfer")

    # Automatisches Material für die Sichtbarkeit
    mat_name = "Trophy_Final_Material"
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    node_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    node_out = nodes.new(type='ShaderNodeOutputMaterial')
    node_attr = nodes.new(type='ShaderNodeAttribute')
    node_attr.attribute_name = attr_name
    
    links.new(node_attr.outputs['Color'], node_bsdf.inputs['Base Color'])
    links.new(node_bsdf.outputs['BSDF'], node_out.inputs['Surface'])
    node_bsdf.inputs['Roughness'].default_value = 0.7

    main_obj.data.materials.clear()
    main_obj.data.materials.append(mat)

    # Viewport-Anzeige erzwingen
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'

    # Aufräumen
    bpy.data.objects.remove(source_obj, do_unlink=True)

    print("\n" + "="*70)
    print("FERTIG! Dein Modell ist jetzt ein massives, buntes Solid.")
    print(f"Voxel-Auflösung: {v_size:.5f}")
    print("="*70)

run_ultimate_trophy_pipeline()
