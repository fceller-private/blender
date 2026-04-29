import bpy
import bmesh

# =================================================================
# METHODE 1: FROZEN - SOLID MUSTER
# =================================================================
def make_islands_solid_and_clean(obj):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    islands = bpy.context.selected_objects
    for island in islands:
        bpy.context.view_layer.objects.active = island
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.edge_face_add() 
        bm = bmesh.from_edit_mesh(island.data)
        if len(bm.faces) == 0:
            bpy.ops.mesh.fill()
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = islands[0]
    bpy.ops.object.join()

# =================================================================
# METHODE 2: FROZEN - PERFEKTE RÖHRE
# =================================================================
def build_perfect_smooth_tube_logic(n, l, ni):
    try: n_path = n.new('GeometryNodeCurvePrimitiveCircle')
    except: n_path = n.new('GeometryNodeCurveCircle')
    n_path.inputs['Resolution'].default_value = 256
    l.new(ni.outputs[2], n_path.inputs['Radius']) 
    try: n_profile = n.new('GeometryNodeCurvePrimitiveQuadrilateral')
    except: n_profile = n.new('GeometryNodeCurveQuadrilateral')
    l.new(ni.outputs[3], n_profile.inputs['Width']) 
    l.new(ni.outputs[4], n_profile.inputs['Height']) 
    n_trans_prof = n.new('GeometryNodeTransform')
    n_math_half = n.new('ShaderNodeMath'); n_math_half.operation = 'DIVIDE'; n_math_half.inputs[1].default_value = 2.0
    n_comb_offset = n.new('ShaderNodeCombineXYZ')
    l.new(ni.outputs[3], n_math_half.inputs[0])
    l.new(n_math_half.outputs[0], n_comb_offset.inputs[0]) 
    l.new(n_profile.outputs[0], n_trans_prof.inputs[0])
    l.new(n_comb_offset.outputs[0], n_trans_prof.inputs['Translation'])
    n_sweep = n.new('GeometryNodeCurveToMesh')
    l.new(n_path.outputs[0], n_sweep.inputs[0]) 
    l.new(n_trans_prof.outputs[0], n_sweep.inputs[1]) 
    n_smooth = n.new('GeometryNodeSetShadeSmooth')
    for s in n_smooth.inputs:
        if s.type == 'BOOLEAN': s.default_value = True
    l.new(n_sweep.outputs[0], n_smooth.inputs[0])
    n_final_trans = n.new('GeometryNodeTransform')
    n_comb_z = n.new('ShaderNodeCombineXYZ')
    l.new(ni.outputs[5], n_comb_z.inputs[2]) 
    l.new(n_smooth.outputs[0], n_final_trans.inputs[0])
    l.new(n_comb_z.outputs[0], n_final_trans.inputs['Translation'])
    return n_final_trans

# =================================================================
# METHODE 3: FROZEN - FOKUS-STRAHLEN
# =================================================================
def build_focal_cutters_logic(n, l, ni):
    n_realize = n.new('GeometryNodeRealizeInstances')
    l.new(ni.outputs[0], n_realize.inputs[0]) 
    n_ext = n.new('GeometryNodeExtrudeMesh')
    l.new(n_realize.outputs[0], n_ext.inputs['Mesh'])
    l.new(ni.outputs[4], n_ext.inputs['Offset Scale']) 
    n_scale = n.new('GeometryNodeScaleElements')
    l.new(n_ext.outputs['Mesh'], n_scale.inputs['Geometry'])
    l.new(n_ext.outputs['Top'], n_scale.inputs['Selection'])
    n_scale.inputs['Scale'].default_value = 0.0001 
    n_comb_f = n.new('ShaderNodeCombineXYZ')
    l.new(ni.outputs[1], n_comb_f.inputs['Z']) 
    l.new(n_comb_f.outputs['Vector'], n_scale.inputs['Center'])
    n_join = n.new('GeometryNodeJoinGeometry')
    l.new(n_realize.outputs[0], n_join.inputs[0])
    l.new(n_scale.outputs[0], n_join.inputs[0])
    return n_join

# =================================================================
# HAUPTPROZESS (V116 - STABLE RESTORE)
# =================================================================
def process_stencil_v116_stable():
    target_objs = [obj for obj in bpy.context.selected_objects if obj.type in {'CURVE', 'MESH'}]
    if not target_objs: return
    obj = target_objs[0]
    bpy.ops.object.convert(target='MESH')
    make_islands_solid_and_clean(obj)

    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
    obj.location = (0, 0, 0)

    mod = obj.modifiers.get("SVG_Cylinder_Cutter") or obj.modifiers.new(name="SVG_Cylinder_Cutter", type='NODES')
    if mod.node_group: bpy.data.node_groups.remove(mod.node_group)
    node_tree = bpy.data.node_groups.new(name="GeoNodes_V116", type='GeometryNodeTree')
    mod.node_group = node_tree
    
    itf = node_tree.interface
    itf.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry') # 0
    itf.new_socket(name="Fokus Hoehe", in_out='INPUT', socket_type='NodeSocketFloat') # 1
    itf.new_socket(name="Zylinder Radius", in_out='INPUT', socket_type='NodeSocketFloat') # 2
    itf.new_socket(name="Wandstaerke", in_out='INPUT', socket_type='NodeSocketFloat') # 3
    itf.new_socket(name="Zylinder Hoehe", in_out='INPUT', socket_type='NodeSocketFloat') # 4
    itf.new_socket(name="Boden Offset", in_out='INPUT', socket_type='NodeSocketFloat') # 5
    itf.new_socket(name="Strahlen anzeigen", in_out='INPUT', socket_type='NodeSocketBool') # 6
    itf.new_socket(name="Schneiden", in_out='INPUT', socket_type='NodeSocketBool') # 7
    itf.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    n, l = node_tree.nodes, node_tree.links
    ni, no = n.new('NodeGroupInput'), n.new('NodeGroupOutput')

    # 1. GENERIERUNG
    n_tube = build_perfect_smooth_tube_logic(n, l, ni)
    n_cutters = build_focal_cutters_logic(n, l, ni)

    # 2. DER SCHNITT (Direkt, ohne fehlerhaften Union)
    n_bool = n.new('GeometryNodeMeshBoolean')
    try: n_bool.operation = 'DIFFERENCE'; n_bool.solver = 'EXACT'
    except: pass
    l.new(n_tube.outputs[0], n_bool.inputs[0])
    l.new(n_cutters.outputs[0], n_bool.inputs[1])

    # 3. REPAIR & TRIANGULATE (Für Slicer-Stabilität)
    n_merge = n.new('GeometryNodeMergeByDistance')
    n_merge.inputs['Distance'].default_value = 0.001
    l.new(n_bool.outputs[0], n_merge.inputs[0])

    n_tri = n.new('GeometryNodeTriangulate')
    l.new(n_merge.outputs[0], n_tri.inputs[0])

    # 4. NORMALEN TRANSFER (Heiler für das Shading)
    n_sample = n.new('GeometryNodeSampleNearestSurface')
    n_sample.data_type = 'FLOAT_VECTOR'
    l.new(n_tube.outputs[0], n_sample.inputs['Mesh'])
    n_norm_in = n.new('GeometryNodeInputNormal')
    l.new(n_norm_in.outputs[0], n_sample.inputs['Value'])
    
    n_store = n.new('GeometryNodeStoreNamedAttribute')
    n_store.data_type = 'FLOAT_VECTOR'; n_store.domain = 'CORNER'
    n_store.inputs['Name'].default_value = "normal"
    l.new(n_tri.outputs[0], n_store.inputs['Geometry'])
    l.new(n_sample.outputs['Value'], n_store.inputs['Value'])

    # 5. WEICHEN (Strikte Index-Verkabelung)
    n_sw_cut = n.new('GeometryNodeSwitch'); n_sw_cut.input_type = 'GEOMETRY'
    l.new(ni.outputs[7], n_sw_cut.inputs[0]) # Schneiden
    l.new(n_tube.outputs[0], n_sw_cut.inputs[1]) 
    l.new(n_store.outputs[0], n_sw_cut.inputs[2])

    n_sw_rays = n.new('GeometryNodeSwitch'); n_sw_rays.input_type = 'GEOMETRY'
    n_join_debug = n.new('GeometryNodeJoinGeometry')
    l.new(n_tube.outputs[0], n_join_debug.inputs[0])
    l.new(n_cutters.outputs[0], n_join_debug.inputs[0])
    
    l.new(ni.outputs[6], n_sw_rays.inputs[0]) # Strahlen anzeigen
    l.new(n_sw_cut.outputs[0], n_sw_rays.inputs[1]) 
    l.new(n_join_debug.outputs[0], n_sw_rays.inputs[2])

    l.new(n_sw_rays.outputs[0], no.inputs[0])

process_stencil_v116_stable()
