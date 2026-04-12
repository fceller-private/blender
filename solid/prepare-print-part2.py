import bpy

# --- EINSTELLUNGEN ---
# Wie dick soll die mehrfarbige Außenwand sein? 
# Da dein Modell ca. 1770 Einheiten groß ist, schrumpfen wir den Kern 
# hier testweise um 15 Einheiten nach innen. Passe diesen Wert an, 
# wenn der Kern zu klein oder zu groß wird.
WALL_THICKNESS = 15.0

# Die Farbe des Kerns (R, G, B, Alpha) - Hier: Reines Weiß
CORE_COLOR = (1.0, 1.0, 1.0, 1.0) 
# ---------------------

original_obj = bpy.context.active_object

if original_obj and original_obj.type == 'MESH':
    try:
        # 1. Original duplizieren
        bpy.ops.object.duplicate()
        core_obj = bpy.context.active_object
        core_obj.name = original_obj.name + "_InnerCore"
        
        # 2. Schrumpfen über Displace Modifier (entlang der Normalen nach innen)
        disp_mod = core_obj.modifiers.new(name="Shrink", type='DISPLACE')
        disp_mod.mid_level = 0.0
        disp_mod.strength = -WALL_THICKNESS
        bpy.context.view_layer.objects.active = core_obj
        bpy.ops.object.modifier_apply(modifier=disp_mod.name)
        
        # 3. Geometrie reparieren (Voxel Remesh), falls Finger/dünne Teile sich nach innen überlappen
        remesh_mod = core_obj.modifiers.new(name="CoreRemesh", type='REMESH')
        remesh_mod.mode = 'VOXEL'
        max_dim = max(core_obj.dimensions)
        if max_dim > 0:
            # Ein grobes Netz (Auflösung 100) reicht für den inneren Kern völlig
            remesh_mod.voxel_size = max_dim / 100.0 
            bpy.ops.object.modifier_apply(modifier=remesh_mod.name)
        
        # 4. Alle alten Farbattribut-Reste vom Kern löschen
        mesh = core_obj.data
        for attr in list(mesh.color_attributes):
            mesh.color_attributes.remove(attr)
            
        # 5. Eine einzige, saubere Farbe für den Kern anlegen
        new_attr = mesh.color_attributes.new(name="BambuColor", type='FLOAT_COLOR', domain='POINT')
        
        # Kompletten Kern mit der neuen Farbe füllen
        for v in mesh.vertices:
            new_attr.data[v.index].color = CORE_COLOR
            
        print(f"Erfolg! '{core_obj.name}' wurde erzeugt und eingefärbt.")
        
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
else:
    print("Bitte wähle zuerst deine Außenhülle im Viewport aus!")
