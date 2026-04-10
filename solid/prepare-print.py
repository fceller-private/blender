import bpy
import time
import sys

# --- KONFIGURATION ---
TARGET_HEIGHT_CM = 15.0
# Wir starten sicherheitshalber bei 1.0. Wenn das klappt, kannst du es auf 1.5 erhöhen.
PRECISION_FACTOR = 1.0  
SMOOTH_ITERATIONS = 2
# ---------------------

def log(msg, elapsed=None):
    timestamp = time.strftime("%H:%M:%S")
    time_info = f" (+{elapsed:.2f}s)" if elapsed is not None else ""
    print(f"[{timestamp}] [SAFE-MODE] {msg}{time_info}")
    sys.stdout.flush()

def show_report(msg):
    blender_ver = bpy.app.version_string
    def draw(self, context):
        self.layout.label(text=f"{msg} | Blender v{blender_ver}")
    bpy.context.window_manager.popup_menu(draw, title="Cleanup Fertig", icon='INFO')

def prepare_for_print():
    total_start = time.time()
    log("--- STARTE SICHERHEITS-OPTIMIERUNG (SKALIERUNG ZUERST) ---")

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
        
    selection = bpy.context.selected_objects
    if not selection:
        log("FEHLER: Nichts ausgewählt!")
        return

    # 1. SOFORTIGE SKALIERUNG (RAM-Schonung)
    step_start = time.time()
    log(f"Schritt 1: Skaliere Modell auf {TARGET_HEIGHT_CM}cm...")
    
    active_obj = bpy.context.view_layer.objects.active
    current_height = active_obj.dimensions.z
    
    # Skalierungsfaktor berechnen
    target_m = TARGET_HEIGHT_CM / 100.0
    scale_factor = target_m / current_height
    
    # Auf alle ausgewählten Objekte anwenden
    for obj in selection:
        obj.scale *= scale_factor
        
    # Transforms anwenden (Wichtig für korrekte Voxel-Berechnung!)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    log(f"Modell von {current_height:.2f}m auf {target_m:.2f}m geschrumpft.", time.time() - step_start)

    # 2. Source vorbereiten
    step_start = time.time()
    log("Schritt 2: Erstelle Daten-Backup für Farben...")
    bpy.ops.object.duplicate()
    source_obj = bpy.context.active_object
    source_obj.name = "NOMAD_SOURCE_BACKUP"
    if len(selection) > 1:
        bpy.ops.object.join()
    
    # Farblayer suchen
    src_color_name = "displayColor"
    if source_obj.data.color_attributes:
        for attr in source_obj.data.color_attributes:
            if "Color" in attr.name and "Opac" not in attr.name:
                src_color_name = attr.name
                source_obj.data.color_attributes.active = attr
                break
    log(f"Farblayer erkannt: '{src_color_name}'")

    # 3. Voxel Remesh (Jetzt auf kleiner Skala)
    step_start = time.time()
    log("Schritt 3: Erstelle Manifold-Hülle (Voxel Remesh)...")
    bpy.ops.object.duplicate()
    target_obj = bpy.context.active_object
    target_obj.name = "PRINT_READY_LIME"

    # Voxelgröße für ein 15cm Objekt (viel sicherer!)
    # Ergibt ca. 0.0003m bis 0.0005m
    v_size = (max(target_obj.dimensions) / 500.0) / PRECISION_FACTOR
    log(f"Ziel-Voxelgröße: {v_size:.6f}m. Starte Berechnung...")
    
    target_obj.data.remesh_voxel_size = v_size
    bpy.ops.object.voxel_remesh()
    log("Remesh erfolgreich beendet.", time.time() - step_start)

    # 4. Attribute säubern (Black-Bot Fix)
    step_start = time.time()
    log("Schritt 4: Lösche störende Metallic/Roughness Layer...")
    while target_obj.data.color_attributes:
        target_obj.data.color_attributes.remove(target_obj.data.color_attributes[0])
    
    for attr in list(target_obj.data.attributes):
        if attr.name not in {'position', 'normal', 'uv_map', 'id'}:
            try: target_obj.data.attributes.remove(attr)
            except: pass
    
    # 5. Farbübertragung
    log("Schritt 5: Übertrage Farben auf die neue Hülle...")
    new_attr = target_obj.data.color_attributes.new(name="displayColor", domain='CORNER', type='BYTE_COLOR')
    target_obj.data.color_attributes.active = new_attr

    transfer = target_obj.modifiers.new(name="Transfer", type='DATA_TRANSFER')
    transfer.object = source_obj
    transfer.use_loop_data = True
    transfer.data_types_loops = {'COLOR_CORNER'}
    transfer.loop_mapping = 'NEAREST_POLYNOR'
    
    bpy.ops.object.datalayout_transfer(modifier=transfer.name)
    bpy.ops.object.modifier_apply(modifier=transfer.name)

    # 6. Finalisierung
    log("Schritt 6: Zentriere Modell und setze Viewport...")
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    target_obj.location = (0, 0, (target_obj.dimensions.z / 2))

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.light = 'STUDIO'
                    space.shading.color_type = 'VERTEX'
    
    bpy.data.objects.remove(source_obj, do_unlink=True)
    
    total_duration = round(time.time() - total_start, 2)
    log(f"--- FERTIG --- Gesamtzeit: {total_duration}s")
    show_report(f"Bot auf {TARGET_HEIGHT_CM}cm optimiert. Zeit: {total_duration}s")

# Start
prepare_for_print()
