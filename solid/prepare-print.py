import bpy
import time
import sys

# --- CONFIGURATION ---
TARGET_HEIGHT_CM = 15.0
PRECISION_FACTOR = 1.6  
SMOOTH_ITERATIONS = 2
# ---------------------

def log(msg, elapsed=None):
    timestamp = time.strftime("%H:%M:%S")
    time_info = f" (+{elapsed:.2f}s)" if elapsed is not None else ""
    output = f"[{timestamp}] [PROGRESS] {msg}{time_info}"
    print(output)
    # Force the console to update immediately
    sys.stdout.flush()

def show_report(msg):
    blender_ver = bpy.app.version_string
    full_msg = f"{msg} | Blender v{blender_ver}"
    def draw(self, context):
        self.layout.label(text=full_msg)
    bpy.context.window_manager.popup_menu(draw, title="Cleanup Complete", icon='INFO')

def prepare_for_print():
    total_start = time.time()
    log("--- INITIALIZING NOMAD CLEANUP SEQUENCE ---")
    log(f"Blender Version: {bpy.app.version_string}")

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
        
    selection = bpy.context.selected_objects
    if not selection:
        log("CRITICAL ERROR: No objects selected.")
        return

    # 1. Source Preparation
    step_start = time.time()
    log(f"Step 1: Preparing source mesh from {len(selection)} objects...")
    source_ref = bpy.context.active_object
    bpy.ops.object.duplicate()
    source_obj = bpy.context.active_object
    source_obj.name = "SOURCE_MASTER"
    
    # Identify Source Color Name
    src_color_name = "displayColor"
    if source_ref.data.color_attributes:
        for attr in source_ref.data.color_attributes:
            if "Color" in attr.name and "Opac" not in attr.name:
                src_color_name = attr.name
                source_obj.data.color_attributes.active = attr
                break
    log(f"Identified source color layer: '{src_color_name}'", time.time() - step_start)

    # 2. Target Generation & Remeshing
    step_start = time.time()
    log("Step 2: Creating manifold shell (This is the slow part, please wait)...")
    bpy.ops.object.duplicate()
    target_obj = bpy.context.active_object
    target_obj.name = "FINAL_PRINT_BOT"

    v_size = (max(source_obj.dimensions) / 550.0) / PRECISION_FACTOR
    log(f"Calculated Voxel Size: {v_size:.5f}m. Starting Voxel Remesh...")
    
    target_obj.data.remesh_voxel_size = v_size
    bpy.ops.object.voxel_remesh()
    log("Voxel Remesh complete.", time.time() - step_start)

    # 3. Surgical Scrub
    step_start = time.time()
    log("Step 3: Scrubbing junk attributes (metallic, roughness, etc)...")
    junk_count = 0
    while target_obj.data.color_attributes:
        target_obj.data.color_attributes.remove(target_obj.data.color_attributes[0])
        
    for attr in list(target_obj.data.attributes):
        if attr.name not in {'position', 'normal', 'uv_map', 'id'}:
            try:
                target_obj.data.attributes.remove(attr)
                junk_count += 1
            except:
                pass 
    log(f"Scrubbed {junk_count} layers.", time.time() - step_start)

    # 4. Color Attribute Transfer
    step_start = time.time()
    log(f"Step 4: Projecting colors from '{src_color_name}' to new shell...")
    new_attr = target_obj.data.color_attributes.new(name="displayColor", domain='CORNER', type='BYTE_COLOR')
    target_obj.data.color_attributes.active = new_attr

    transfer = target_obj.modifiers.new(name="NomadTransfer", type='DATA_TRANSFER')
    transfer.object = source_obj
    transfer.use_loop_data = True
    transfer.data_types_loops = {'COLOR_CORNER'}
    transfer.loop_mapping = 'NEAREST_POLYNOR'
    
    bpy.ops.object.datalayout_transfer(modifier=transfer.name)
    bpy.ops.object.modifier_apply(modifier=transfer.name)
    log("Color transfer applied.", time.time() - step_start)

    # 5. Final Transforms
    step_start = time.time()
    log(f"Step 5: Rescaling to {TARGET_HEIGHT_CM}cm and centering...")
    target_m = TARGET_HEIGHT_CM / 100.0
    scale_f = target_m / target_obj.dimensions.z
    target_obj.scale = (scale_f, scale_f, scale_f)
    
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    target_obj.location = (0, 0, (target_obj.dimensions.z / 2))
    log("Transforms applied.", time.time() - step_start)

    # 6. Viewport Refresh
    log("Finalizing viewport settings...")
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.light = 'STUDIO'
                    space.shading.color_type = 'VERTEX'
    
    # Housekeeping
    bpy.data.objects.remove(source_obj, do_unlink=True)
    
    total_duration = round(time.time() - total_start, 2)
    log(f"--- SEQUENCE COMPLETE --- Total Time: {total_duration}s")
    
    final_msg = f"Done! {TARGET_HEIGHT_CM}cm | Time: {total_duration}s"
    show_report(final_msg)

# Run it
prepare_for_print()
