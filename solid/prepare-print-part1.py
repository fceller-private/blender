import bpy
import time

def remesh_and_bake_scale_independent(precision=350):
    print("\n" + "="*60)
    print(" PIPELINE: SCALE-INDEPENDENT CYCLES BAKE ")
    print("="*60)
    
    start_time = time.time()
    
    original_obj = bpy.context.active_object
    if not original_obj or original_obj.type != 'MESH':
        print("[ERROR] Bitte wähle zuerst das Originalmodell aus!")
        return

    bpy.context.scene.render.engine = 'CYCLES'
    
    print("[PROCESS] Erzeuge Hülle...")
    bpy.ops.object.duplicate()
    recon_obj = bpy.context.active_object
    recon_obj.name = original_obj.name + "_FINAL_PRINT"
    
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    # Maßstab messen
    max_dim = max(recon_obj.dimensions)
    v_size = max_dim / precision
    
    mod_remesh = recon_obj.modifiers.new(name="Solid", type='REMESH')
    mod_remesh.mode = 'VOXEL'
    mod_remesh.voxel_size = v_size
    bpy.ops.object.modifier_apply(modifier="Solid")

    mod_smooth = recon_obj.modifiers.new(name="Smooth", type='CORRECTIVE_SMOOTH')
    mod_smooth.iterations = 10
    bpy.ops.object.modifier_apply(modifier="Smooth")

    # Dummy UV
    bpy.context.view_layer.objects.active = recon_obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15) 
    bpy.ops.object.mode_set(mode='OBJECT')
    
    color_attr = recon_obj.data.color_attributes.new(
        name="BakedColor", 
        type='BYTE_COLOR', 
        domain='CORNER'
    )
    recon_obj.data.attributes.active_color = color_attr
    
    # --- DIE DYNAMISCHEN BAKE SETTINGS ---
    bpy.context.scene.cycles.bake_type = 'DIFFUSE'
    bpy.context.scene.render.bake.use_pass_direct = False
    bpy.context.scene.render.bake.use_pass_indirect = False
    bpy.context.scene.render.bake.use_pass_color = True 
    bpy.context.scene.render.bake.use_selected_to_active = True
    
    # DER FIX: Die Kamera ("Cage") ist exakt 5% größer als das Modell.
    # Egal ob das Modell 1cm oder 100m groß ist, der Raycast startet immer sauber von außen!
    calculated_extrusion = max_dim * 0.05
    
    bpy.context.scene.render.bake.cage_extrusion = calculated_extrusion
    # 0.0 bedeutet: Der Strahl wandert so lange nach innen, bis er auf jeden Fall etwas trifft.
    bpy.context.scene.render.bake.max_ray_distance = 0.0 
    
    bpy.context.scene.render.bake.target = 'VERTEX_COLORS'
    # -------------------------------------

    bpy.ops.object.select_all(action='DESELECT')
    original_obj.select_set(True) 
    recon_obj.select_set(True)    
    bpy.context.view_layer.objects.active = recon_obj 
    
    print(f"[PROCESS] Starte Bake (Modellgröße: {max_dim:.2f}, Extrusion: {calculated_extrusion:.4f})...")
    try:
        bpy.ops.object.bake(type='DIFFUSE')
        print(" -> Bake erfolgreich!")
    except Exception as e:
        print(f"[ERROR] Bake fehlgeschlagen: {e}")
        return
        
    # Material
    mat = bpy.data.materials.new(name="Baked_Material_Final")
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
    
    print(f"[FINISH] Dauer: {time.time() - start_time:.2f}s")
    print("="*60)

remesh_and_bake_scale_independent(precision=350)
