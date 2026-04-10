import bpy
import time

def remesh_and_bake_texture_safe(precision=200):
    print("\n" + "="*60)
    print(" PIPELINE: CYCLES TEXTURE BAKING (SAFE MODE) ")
    print("="*60)
    
    start_time = time.time()
    
    # 1. Original prüfen
    original_obj = bpy.context.active_object
    if not original_obj or original_obj.type != 'MESH':
        print("[ERROR] Bitte wähle zuerst das Originalmodell aus!")
        return

    # 2. Render-Engine auf Cycles stellen
    print("[PROCESS] Richte Cycles-Renderer ein...")
    bpy.context.scene.render.engine = 'CYCLES'
    
    # 3. Kopie & Remesh
    print("[PROCESS] Erzeuge Voxel-Hülle...")
    bpy.ops.object.duplicate()
    recon_obj = bpy.context.active_object
    recon_obj.name = original_obj.name + "_SOLID_PRINT"
    
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    max_dim = max(recon_obj.dimensions)
    v_size = max_dim / precision
    
    mod_remesh = recon_obj.modifiers.new(name="Solid", type='REMESH')
    mod_remesh.mode = 'VOXEL'
    mod_remesh.voxel_size = v_size
    bpy.ops.object.modifier_apply(modifier="Solid")

    # ---------------------------------------------------------
    # DER BUGFIX FÜR DEN ABSTURZ (MikkTSpace / calc_uv_tangents)
    # ---------------------------------------------------------
    print("[PROCESS] Erzeuge Dummy-UV-Map (Crash-Prävention)...")
    bpy.context.view_layer.objects.active = recon_obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    # Wir machen ein schnelles, grobes Unwrapping
    bpy.ops.uv.smart_project(angle_limit=1.15) 
    bpy.ops.object.mode_set(mode='OBJECT')
    # ---------------------------------------------------------
    
    # 4. Farbattribut auf dem ZIEL erstellen
    print("[PROCESS] Bereite Vertex Colors vor...")
    color_attr = recon_obj.data.color_attributes.new(
        name="BakedColor", 
        type='BYTE_COLOR', 
        domain='CORNER'
    )
    recon_obj.data.attributes.active_color = color_attr
    
    # 5. Baking Setup (Selected to Active)
    bpy.context.scene.cycles.bake_type = 'DIFFUSE'
    bpy.context.scene.render.bake.use_pass_direct = False
    bpy.context.scene.render.bake.use_pass_indirect = False
    bpy.context.scene.render.bake.use_pass_color = True 
    
    bpy.context.scene.render.bake.use_selected_to_active = True
    bpy.context.scene.render.bake.cage_extrusion = 0.05
    bpy.context.scene.render.bake.target = 'VERTEX_COLORS'
    
    # 6. Objekte für den Bake korrekt selektieren
    bpy.ops.object.select_all(action='DESELECT')
    original_obj.select_set(True) # Quelle
    recon_obj.select_set(True)    # Ziel
    bpy.context.view_layer.objects.active = recon_obj # Aktiv = Ziel
    
    # 7. Der Bake-Vorgang
    print("[PROCESS] Starte Bake. ACHTUNG: Blender rechnet jetzt intensiv...")
    try:
        bpy.ops.object.bake(type='DIFFUSE')
        print(" -> Bake erfolgreich!")
    except Exception as e:
        print(f"[ERROR] Bake fehlgeschlagen: {e}")
        return
        
    # 8. Material Setup
    print("[PROCESS] Erstelle Vorschau-Material...")
    mat = bpy.data.materials.new(name="Baked_Material")
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
        
    nodes = mat.node_tree.nodes
    nodes.clear()
    
    node_attr = nodes.new(type='ShaderNodeAttribute')
    node_attr.attribute_name = "BakedColor"
    node_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    node_out = nodes.new(type='ShaderNodeOutputMaterial')
    
    mat.node_tree.links.new(node_attr.outputs['Color'], node_bsdf.inputs['Base Color'])
    mat.node_tree.links.new(node_bsdf.outputs['BSDF'], node_out.inputs['Surface'])
    
    recon_obj.data.materials.clear()
    recon_obj.data.materials.append(mat)
    
    original_obj.hide_viewport = True
    
    print(f"[FINISH] Vorgang in {time.time() - start_time:.2f} Sekunden beendet.")
    print("="*60)

remesh_and_bake_texture_safe(precision=200)
