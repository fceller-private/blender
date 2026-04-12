import bpy

# --- WICHTIGE EINSTELLUNG ---
TARGET_RESOLUTION = 250 
# ----------------------------

original_obj = bpy.context.active_object

if original_obj and original_obj.type == 'MESH':
    # 0. Sicherheitscheck: Hat das Original überhaupt Farben?
    if not original_obj.data.color_attributes:
        print("Fehler: Das ausgewählte Original-Objekt hat keine Color Attributes!")
    else:
        try:
            # 1. Automatische Voxel-Größe berechnen
            dims = original_obj.dimensions
            max_dim = max(dims.x, dims.y, dims.z)
            
            if max_dim == 0:
                raise ValueError("Das Objekt hat keine Ausdehnung (Größe 0).")
                
            calculated_voxel_size = max_dim / TARGET_RESOLUTION
            print(f"Modellgröße (Max): {max_dim:.2f} -> Berechnete Voxel-Größe: {calculated_voxel_size:.4f}")

            # 2. Original duplizieren
            bpy.ops.object.duplicate()
            new_obj = bpy.context.active_object
            new_obj.name = original_obj.name + "_SolidShell"
            mesh = new_obj.data
            
            # 3. Voxel Remesh
            remesh_mod = new_obj.modifiers.new(name="VoxelRemesh", type='REMESH')
            remesh_mod.mode = 'VOXEL'
            remesh_mod.voxel_size = calculated_voxel_size
            bpy.ops.object.modifier_apply(modifier=remesh_mod.name)
            
            # 4. Data Transfer
            dt_mod = new_obj.modifiers.new(name="ColorTransfer", type='DATA_TRANSFER')
            dt_mod.object = original_obj
            dt_mod.use_loop_data = True
            dt_mod.data_types_loops = {'COLOR_CORNER'}
            dt_mod.loop_mapping = 'POLYINTERP_NEAREST'
            
            # Erzeugt die Daten-Ebenen
            bpy.context.view_layer.objects.active = new_obj
            bpy.ops.object.datalayout_transfer(modifier=dt_mod.name)
            
            # Modifier anwenden
            bpy.ops.object.modifier_apply(modifier=dt_mod.name)
            
            # 5. Attribut-Cleanup für Bambu Studio (Point Domain)
            src_attr = None
            for attr in mesh.color_attributes:
                src_attr = attr
                break
                
            if src_attr:
                new_attr_name = "BambuColor"
                # Neues, reines Point-Attribut erstellen
                new_attr = mesh.color_attributes.new(name=new_attr_name, type='FLOAT_COLOR', domain='POINT')
                
                vertex_colors = {i: [] for i in range(len(mesh.vertices))}
                for poly in mesh.polygons:
                    for loop_index in poly.loop_indices:
                        v_idx = mesh.loops[loop_index].vertex_index
                        vertex_colors[v_idx].append(src_attr.data[loop_index].color)
                
                for v_idx, colors in vertex_colors.items():
                    if colors:
                        r = sum(c[0] for c in colors) / len(colors)
                        g = sum(c[1] for c in colors) / len(colors)
                        b = sum(c[2] for c in colors) / len(colors)
                        a = sum(c[3] for c in colors) / len(colors)
                        new_attr.data[v_idx].color = (r, g, b, a)
                        
                # --- KORREKTUR: Nur alte FARB-Attribute löschen ---
                attrs_to_remove = [attr.name for attr in mesh.color_attributes if attr.name != new_attr_name]
                for name in attrs_to_remove:
                    mesh.attributes.remove(mesh.attributes[name])
                        
                print(f"Erfolg! '{new_obj.name}' wurde erstellt. Du kannst es jetzt als .3mf exportieren!")
            else:
                print("Fehler: Die Farbe konnte trotz Data-Layer-Generierung nicht übertragen werden.")
                
        except Exception as e:
            print(f"Ein Fehler ist aufgetreten: {e}")
else:
    print("Bitte wähle zuerst dein Original-Modell im Viewport aus!")
