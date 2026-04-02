import bpy

def ultimate_voxel_rescue_with_colors():
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        print("Bitte die eiförmige Figur auswählen!")
        return

    print("\n" + "="*70)
    print("STARTE VOXEL-RETTUNG INKLUSIVE FARB-PROJEKTION")
    print("="*70)

    # 1. Skalierung normalisieren
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # 2. Prüfen, ob Farben vorhanden sind
    source_color = obj.data.color_attributes.active
    if not source_color:
        print("Fehler: Das Originalmodell hat keine Farben!")
        return
        
    attr_domain = source_color.domain
    attr_name = source_color.name

    # 3. Auflösung berechnen
    max_dim = max(obj.dimensions)
    voxel_size = max_dim / 250.0  

    # 4. Backup des Originals für den "Farb-Beamer"
    bpy.ops.object.duplicate()
    source_obj = bpy.context.active_object
    source_obj.name = "COLOR_BACKUP"

    # Zurück zum Original-Objekt
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    source_obj.select_set(False)

    # 5. Zerstören & Neu aufbauen (Voxel Remesh)
    remesh = obj.modifiers.new(name="VoxelFix", type='REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = voxel_size
    bpy.ops.object.modifier_apply(modifier="VoxelFix")
    print("   -> Geometrie wurde als sauberer, massiver Block neu aufgebaut.")

    # 6. Farben projizieren (Data Transfer)
    dt = obj.modifiers.new(name="ColorTransfer", type='DATA_TRANSFER')
    dt.object = source_obj
    
    # Automatische Anpassung an die Blender-Version und den Attribut-Typ
    try:
        if attr_domain == 'CORNER':
            dt.use_loop_data = True
            dt.data_types_loops = {'COLOR_CORNER'}
            dt.loop_mapping = 'NEAREST_POLYNOR'
        else:
            dt.use_vert_data = True
            dt.data_types_verts = {'COLOR_VERTEX'}
            dt.vert_mapping = 'NEAREST'
    except:
        # Fallback für andere Versionen
        if attr_domain == 'CORNER':
            dt.data_types_loops = {'VCOL'}
        else:
            dt.data_types_verts = {'VCOL'}
            
    # Das ist der magische Knopf: "Generate Data Layers"
    bpy.ops.object.datalayout_transfer(modifier="ColorTransfer")
    bpy.ops.object.modifier_apply(modifier="ColorTransfer")
    print("   -> Farben wurden erfolgreich auf den neuen Block projiziert.")

    # 7. Material erstellen, um die Farbe sichtbar zu machen
    mat = bpy.data.materials.get("VoxelColorMat")
    if not mat:
        mat = bpy.data.materials.new(name="VoxelColorMat")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        bsdf = nodes.get("Principled BSDF")
        ca_node = nodes.new(type="ShaderNodeVertexColor")
        ca_node.layer_name = attr_name
        
        links.new(ca_node.outputs["Color"], bsdf.inputs["Base Color"])
    
    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat

    # 8. Backup löschen
    bpy.data.objects.remove(source_obj, do_unlink=True)

    print("\n" + "="*70)
    print("FERTIG! Der Roboter ist massiv UND bunt. Exportiere ihn jetzt als .3mf!")
    print("="*70)

ultimate_voxel_rescue_with_colors()
