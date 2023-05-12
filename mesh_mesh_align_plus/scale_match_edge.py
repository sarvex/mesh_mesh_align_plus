"""Scale Match Edge tool, internals & UI."""


import bmesh
import bpy
import mathutils

import mesh_mesh_align_plus.utils.exceptions as maplus_except
import mesh_mesh_align_plus.utils.geom as maplus_geom
import mesh_mesh_align_plus.utils.gui_tools as maplus_guitools


class MAPLUS_OT_ScaleMatchEdgeBase(bpy.types.Operator):
    bl_idname = "maplus.scalematchedgebase"
    bl_label = "Scale Match Edge Base"
    bl_description = "Scale match edge base class"
    bl_options = {'REGISTER', 'UNDO'}
    target = None

    def execute(self, context):
        addon_data = bpy.context.scene.maplus_data
        prims = addon_data.prim_list
        previous_mode = maplus_geom.get_active_object().mode
        if hasattr(self, "quick_op_target"):
            active_item = addon_data.quick_scale_match_edge_transf
        else:
            active_item = prims[addon_data.active_list_item]
        # Gather selected Blender object(s) to apply the transform to
        multi_edit_targets = [
            item for item in bpy.context.scene.objects if (
                maplus_geom.get_select_state(item)
            )
        ]
        # Check prerequisites for mesh level transforms, need an active/selected object
        if self.target != 'OBJECT' and (
            not maplus_geom.get_active_object()
            or not maplus_geom.get_select_state(maplus_geom.get_active_object())
        ):
            self.report(
                {'ERROR'},
                ('Cannot complete: cannot perform mesh-level transform'
                 ' without an active (and selected) object.')
            )
            return {'CANCELLED'}
        # Check auto grab prerequisites
        if addon_data.quick_scale_match_edge_auto_grab_src or addon_data.quick_sme_numeric_auto:
            if (
                not maplus_geom.get_active_object()
                or not maplus_geom.get_select_state(
                    maplus_geom.get_active_object()
                )
            ):
                self.report(
                    {'ERROR'},
                    ('Cannot complete: cannot auto-grab source verts '
                     ' without an active (and selected) object.')
                )
                return {'CANCELLED'}
            if maplus_geom.get_active_object().type != 'MESH':
                self.report(
                    {'ERROR'},
                    ('Cannot complete: cannot auto-grab source verts '
                     ' from a non-mesh object.')
                )
                return {'CANCELLED'}

        # Proceed only if selected Blender objects are compatible with the transform target
        # (Do not allow mesh-level transforms when there are non-mesh objects selected)
        if self.target not in {
            'MESH_SELECTED',
            'WHOLE_MESH',
            'OBJECT_ORIGIN',
        } or not [item for item in multi_edit_targets if item.type != 'MESH']:

            if not hasattr(self, "quick_op_target") and (
                prims[active_item.sme_edge_one].kind != 'LINE'
                or prims[active_item.sme_edge_two].kind != 'LINE'
            ):
                self.report(
                    {'ERROR'},
                    ('Wrong operands: "Scale Match Edge" can only'
                     ' operate on two lines')
                )
                return {'CANCELLED'}

            if maplus_geom.get_active_object().type == 'MESH':
                # a bmesh can only be initialized in edit mode...
                if previous_mode == 'EDIT':
                    # else we could already be in edit mode with some stale
                    # updates, exiting and reentering forces an update
                    bpy.ops.object.editmode_toggle()
                bpy.ops.object.editmode_toggle()

            # Get global coordinate data for each geometry item, with
            # applicable modifiers applied. Grab either (A) directly from
            # the scene data (for quick ops), (B) from the MAPlus primitives
            # CollectionProperty on the scene data (for advanced tools), or
            # (C) from the selected verts directly for numeric input mode
            if hasattr(self, "quick_op_target"):
                # Numeric mode is part of this op's quick tools
                if addon_data.quick_sme_numeric_mode:
                    if addon_data.quick_sme_numeric_auto:
                        vert_attribs_to_set = ('line_start', 'line_end')
                        try:
                            vert_data = maplus_geom.return_selected_verts(
                                maplus_geom.get_active_object(),
                                len(vert_attribs_to_set),
                                maplus_geom.get_active_object().matrix_world
                            )
                        except maplus_except.InsufficientSelectionError:
                            self.report(
                                {'ERROR'},
                                'Not enough vertices selected.'
                            )
                            return {'CANCELLED'}
                        except maplus_except.NonMeshGrabError:
                            self.report(
                                {'ERROR'},
                                ('Cannot grab coords: non-mesh'
                                 ' or no active object.')
                            )
                            return {'CANCELLED'}

                        maplus_geom.set_item_coords(
                            addon_data.quick_sme_numeric_src,
                            vert_attribs_to_set,
                            vert_data
                        )
                        maplus_geom.set_item_coords(
                            addon_data.quick_sme_numeric_dest,
                            vert_attribs_to_set,
                            vert_data
                        )

                    addon_data.quick_sme_numeric_dest.ln_make_unit_vec = (
                        True
                    )
                    addon_data.quick_sme_numeric_dest.ln_multiplier = (
                        addon_data.quick_sme_numeric_length
                    )

                    src_global_data = maplus_geom.get_modified_global_coords(
                        geometry=addon_data.quick_sme_numeric_src,
                        kind='LINE'
                    )
                    dest_global_data = maplus_geom.get_modified_global_coords(
                        geometry=addon_data.quick_sme_numeric_dest,
                        kind='LINE'
                    )

                # Non-numeric (normal quick op) mode
                else:
                    if addon_data.quick_scale_match_edge_auto_grab_src:
                        vert_attribs_to_set = ('line_start', 'line_end')
                        try:
                            vert_data = maplus_geom.return_selected_verts(
                                maplus_geom.get_active_object(),
                                len(vert_attribs_to_set),
                                maplus_geom.get_active_object().matrix_world
                            )
                        except maplus_except.InsufficientSelectionError:
                            self.report(
                                {'ERROR'},
                                'Not enough vertices selected.'
                            )
                            return {'CANCELLED'}
                        except maplus_except.NonMeshGrabError:
                            self.report(
                                {'ERROR'},
                                ('Cannot grab coords: non-mesh'
                                 ' or no active object.')
                            )
                            return {'CANCELLED'}

                        maplus_geom.set_item_coords(
                            addon_data.quick_scale_match_edge_src,
                            vert_attribs_to_set,
                            vert_data
                        )

                    src_global_data = maplus_geom.get_modified_global_coords(
                        geometry=addon_data.quick_scale_match_edge_src,
                        kind='LINE'
                    )
                    dest_global_data = maplus_geom.get_modified_global_coords(
                        geometry=addon_data.quick_scale_match_edge_dest,
                        kind='LINE'
                    )

            # Else, operate on data from the advanced tools
            else:
                src_global_data = maplus_geom.get_modified_global_coords(
                    geometry=prims[active_item.sme_edge_one],
                    kind='LINE'
                )
                dest_global_data = maplus_geom.get_modified_global_coords(
                    geometry=prims[active_item.sme_edge_two],
                    kind='LINE'
                )

            # These global point coordinate vectors will be used to construct
            # geometry and transformations in both object (global) space
            # and mesh (local) space
            src_start = src_global_data[0]
            src_end = src_global_data[1]

            dest_start = dest_global_data[0]
            dest_end = dest_global_data[1]

            # Construct vectors for each edge from the global point coord data
            src_edge = src_end - src_start
            dest_edge = dest_end - dest_start

            if dest_edge.length == 0 or src_edge.length == 0:
                self.report(
                    {'ERROR'},
                    'Divide by zero error: zero length edge encountered'
                )
                return {'CANCELLED'}
            scale_factor = dest_edge.length/src_edge.length

            if self.target in {'OBJECT', 'OBJECT_ORIGIN'}:
                for item in multi_edit_targets:
                    # Get the object world matrix before we modify it here
                    item_matrix_unaltered = item.matrix_world.copy()
                    unaltered_inverse = item_matrix_unaltered.copy()
                    unaltered_inverse.invert()

                    # (Note that there are no transformation modifiers for this
                    # transformation type, so that section is omitted here)
                    item.scale = [
                        scale_factor * num
                        for num in item.scale
                    ]
                    bpy.context.view_layer.update()

                    # put the original line starting point (before the object
                    # was transformed) into the local object space
                    src_pivot_location_local = unaltered_inverse @ src_start

                    # get final global position of pivot (source line
                    # start coords) after object rotation
                    new_global_src_pivot_coords = (
                        item.matrix_world @
                        src_pivot_location_local
                    )

                    # get translation, new to old (original) pivot location
                    new_to_old_pivot = (
                        src_start - new_global_src_pivot_coords
                    )

                    item.location = (
                       item.location + new_to_old_pivot
                    )
                    bpy.context.view_layer.update()

            if self.target in {'MESH_SELECTED', 'WHOLE_MESH', 'OBJECT_ORIGIN'}:
                for item in multi_edit_targets:
                    # (Note that there are no transformation modifiers for this
                    # transformation type, so that section is omitted here)
                    self.report(
                        {'WARNING'},
                        ('Warning/Experimental: mesh transforms'
                         ' on objects with non-uniform scaling'
                         ' are not currently supported.')
                    )

                    # Init source mesh
                    src_mesh = bmesh.new()
                    src_mesh.from_mesh(item.data)

                    item_matrix_unaltered_loc = item.matrix_world.copy()
                    unaltered_inverse_loc = item_matrix_unaltered_loc.copy()
                    unaltered_inverse_loc.invert()

                    # Stored geom data in local coords
                    src_start_loc = unaltered_inverse_loc @ src_start
                    src_end_loc = unaltered_inverse_loc @ src_end

                    dest_start_loc = unaltered_inverse_loc @ dest_start
                    dest_end_loc = unaltered_inverse_loc @ dest_end

                    # Construct vectors for each line in local space
                    loc_src_line = src_end_loc - src_start_loc
                    loc_dest_line = dest_end_loc - dest_start_loc

                    # Get the scale match matrix
                    scaling_match = mathutils.Matrix.Scale(
                        scale_factor,
                        4
                    )

                    # Get the new pivot location
                    new_pivot_location_loc = scaling_match @ src_start_loc

                    # Get the translation, new to old pivot location
                    new_to_old_pivot_vec = (
                        src_start_loc - new_pivot_location_loc
                    )
                    new_to_old_pivot = mathutils.Matrix.Translation(
                        new_to_old_pivot_vec
                    )

                    # Get combined scale + move
                    match_transf = new_to_old_pivot @ scaling_match

                    if self.target == 'MESH_SELECTED':
                        src_mesh.transform(
                            match_transf,
                            filter={'SELECT'}
                        )
                    elif self.target == 'WHOLE_MESH':
                        src_mesh.transform(match_transf)
                    elif self.target == 'OBJECT_ORIGIN':
                        # Note: a target of 'OBJECT_ORIGIN' is equivalent
                        # to performing an object transf. + an inverse
                        # whole mesh level transf. To the user,
                        # the object appears to stay in the same place,
                        # while only the object's origin moves.
                        src_mesh.transform(match_transf.inverted())

                    # write and then release the mesh data
                    bpy.ops.object.mode_set(mode='OBJECT')
                    src_mesh.to_mesh(item.data)
                    src_mesh.free()

            # Go back to whatever mode we were in before doing this
            bpy.ops.object.mode_set(mode=previous_mode)

        else:
            # The selected Blender objects are not compatible with the
            # requested transformation type (we can't apply a transform
            # to mesh data when there are non-mesh objects selected)
            self.report(
                {'ERROR'},
                ('Cannot complete: Cannot apply mesh-level'
                 ' transformations to selected non-mesh objects.')
            )
            return {'CANCELLED'}

        return {'FINISHED'}


class MAPLUS_OT_ScaleMatchEdgeObject(MAPLUS_OT_ScaleMatchEdgeBase):
    bl_idname = "maplus.scalematchedgeobject"
    bl_label = "Scale Match Edge Object"
    bl_description = (
        "Scale source object so that source edge matches length of dest edge"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT'


class MAPLUS_OT_QuickScaleMatchEdgeObject(MAPLUS_OT_ScaleMatchEdgeBase):
    bl_idname = "maplus.quickscalematchedgeobject"
    bl_label = "Scale Match Edge Object"
    bl_description = (
        "Scale source object so that source edge matches length of dest edge"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT'
    quick_op_target = True


class MAPLUS_OT_QuickScaleMatchEdgeObjectOrigin(MAPLUS_OT_ScaleMatchEdgeBase):
    bl_idname = "maplus.quickscalematchedgeobjectorigin"
    bl_label = "Scale Match Edge Object Origin"
    bl_description = (
        "Scale source object so that source edge matches length of dest edge"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT_ORIGIN'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_ScaleMatchEdgeMeshSelected(MAPLUS_OT_ScaleMatchEdgeBase):
    bl_idname = "maplus.scalematchedgemeshselected"
    bl_label = "Scale Match Edge Mesh Selected"
    bl_description = (
        "Scale source mesh piece so that source edge matches length "
        "of dest edge"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'MESH_SELECTED'

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_QuickScaleMatchEdgeMeshSelected(MAPLUS_OT_ScaleMatchEdgeBase):
    bl_idname = "maplus.quickscalematchedgemeshselected"
    bl_label = "Scale Match Edge Whole Mesh"
    bl_description = (
        "Scale source (whole) mesh so that source edge matches length "
        "of dest edge"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'MESH_SELECTED'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_ScaleMatchEdgeWholeMesh(MAPLUS_OT_ScaleMatchEdgeBase):
    bl_idname = "maplus.scalematchedgewholemesh"
    bl_label = "Scale Match Edge Whole Mesh"
    bl_description = (
        "Scale source (whole) mesh so that source edge matches length "
        "of dest edge"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'WHOLE_MESH'

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_QuickScaleMatchEdgeWholeMesh(MAPLUS_OT_ScaleMatchEdgeBase):
    bl_idname = "maplus.quickscalematchedgewholemesh"
    bl_label = "Scale Match Edge Whole Mesh"
    bl_description = (
        "Scale source (whole) mesh so that source edge matches length "
        "of dest edge"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'WHOLE_MESH'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_PT_QuickSMEGUI(bpy.types.Panel):
    bl_idname = "MAPLUS_PT_QuickSMEGUI"
    bl_label = "Quick Scale Match Edge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mesh Align Plus"
    bl_category = "Mesh Align Plus"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        maplus_data_ptr = bpy.types.AnyType(bpy.context.scene.maplus_data)
        addon_data = bpy.context.scene.maplus_data
        prims = addon_data.prim_list

        sme_top = layout.row()
        sme_gui = layout.box()
        sme_top.label(text=
            "Match Edge Scale",
            icon="FULLSCREEN_ENTER"
        )
        sme_grab_col = sme_gui.column()
        sme_grab_col.prop(
            addon_data,
            'quick_scale_match_edge_auto_grab_src',
            text='Auto Grab Source from Selected Vertices'
        )

        sme_src_geom_top = sme_grab_col.row(align=True)
        if not addon_data.quick_scale_match_edge_auto_grab_src:
            if not addon_data.quick_sme_show_src_geom:
                sme_src_geom_top.operator(
                        "maplus.showhidequicksmesrcgeom",
                        icon='TRIA_RIGHT',
                        text="",
                        emboss=False
                )
                preserve_button_roundedge = sme_src_geom_top.row()
                preserve_button_roundedge.operator(
                        "maplus.quickscalematchedgegrabsrc",
                        icon='LIGHT_SUN',
                        text="Grab Source"
                )
            else:
                sme_src_geom_top.operator(
                        "maplus.showhidequicksmesrcgeom",
                        icon='TRIA_DOWN',
                        text="",
                        emboss=False
                )
                sme_src_geom_top.label(
                    text="Source Coordinates",
                    icon="LIGHT_SUN"
                )

                sme_src_geom_editor = sme_grab_col.box()
                ln_grab_all = sme_src_geom_editor.row(align=True)
                ln_grab_all.operator(
                    "maplus.quickscalematchedgegrabsrcloc",
                    icon='VERTEXSEL',
                    text="Grab All Local"
                )
                ln_grab_all.operator(
                    "maplus.quickscalematchedgegrabsrc",
                    icon='WORLD',
                    text="Grab All Global"
                )

                special_grabs = sme_src_geom_editor.row(align=True)
                special_grabs.operator(
                    "maplus.quicksmegrabnormalsrc",
                    icon='LIGHT_HEMI',
                    text="Grab Normal"
                )
                special_grabs_extra = sme_src_geom_editor.row(align=True)
                special_grabs_extra.operator(
                    "maplus.copyfromsmesrc",
                    icon='COPYDOWN',
                    text="Copy (To Clipboard)"
                )
                special_grabs_extra.operator(
                    "maplus.pasteintosmesrc",
                    icon='PASTEDOWN',
                    text="Paste (From Clipboard)"
                )

                modifier_header = sme_src_geom_editor.row()
                modifier_header.label(text="Line Modifiers:")
                apply_mods = modifier_header.row()
                apply_mods.alignment = 'RIGHT'

                item_mods_box = sme_src_geom_editor.box()
                mods_row_1 = item_mods_box.row()
                mods_row_1.prop(
                    bpy.types.AnyType(addon_data.quick_scale_match_edge_src),
                    'ln_make_unit_vec',
                    text="Set Length Equal to One"
                )
                mods_row_1.prop(
                    bpy.types.AnyType(addon_data.quick_scale_match_edge_src),
                    'ln_flip_direction',
                    text="Flip Direction"
                )
                mods_row_2 = item_mods_box.row()
                mods_row_2.prop(
                    bpy.types.AnyType(addon_data.quick_scale_match_edge_src),
                    'ln_multiplier',
                    text="Multiplier"
                )

                maplus_guitools.layout_coordvec(
                    parent_layout=sme_src_geom_editor,
                    coordvec_label="Start:",
                    op_id_cursor_grab=(
                        "maplus.quicksmesrcgrablinestartfromcursor"
                    ),
                    op_id_avg_grab=(
                        "maplus.quicksmegrabavgsrclinestart"
                    ),
                    op_id_local_grab=(
                        "maplus.quicksmesrcgrablinestartfromactivelocal"
                    ),
                    op_id_global_grab=(
                        "maplus.quicksmesrcgrablinestartfromactiveglobal"
                    ),
                    coord_container=addon_data.quick_scale_match_edge_src,
                    coord_attribute="line_start",
                    op_id_cursor_send=(
                        "maplus.quicksmesrcsendlinestarttocursor"
                    ),
                    op_id_text_tuple_swap_first=(
                        "maplus.quicksmesrcswaplinepoints",
                        "End"
                    )
                )

                maplus_guitools.layout_coordvec(
                    parent_layout=sme_src_geom_editor,
                    coordvec_label="End:",
                    op_id_cursor_grab=(
                        "maplus.quicksmesrcgrablineendfromcursor"
                    ),
                    op_id_avg_grab=(
                        "maplus.quicksmegrabavgsrclineend"
                    ),
                    op_id_local_grab=(
                        "maplus.quicksmesrcgrablineendfromactivelocal"
                    ),
                    op_id_global_grab=(
                        "maplus.quicksmesrcgrablineendfromactiveglobal"
                    ),
                    coord_container=addon_data.quick_scale_match_edge_src,
                    coord_attribute="line_end",
                    op_id_cursor_send=(
                        "maplus.quicksmesrcsendlineendtocursor"
                    ),
                    op_id_text_tuple_swap_first=(
                        "maplus.quicksmesrcswaplinepoints",
                        "Start"
                    )
                )

        if addon_data.quick_sme_show_src_geom:
            sme_grab_col.separator()

        sme_dest_geom_top = sme_grab_col.row(align=True)
        if not addon_data.quick_sme_show_dest_geom:
            sme_dest_geom_top.operator(
                    "maplus.showhidequicksmedestgeom",
                    icon='TRIA_RIGHT',
                    text="",
                    emboss=False
            )
            preserve_button_roundedge = sme_dest_geom_top.row()
            preserve_button_roundedge.operator(
                    "maplus.quickscalematchedgegrabdest",
                    icon='LIGHT_SUN',
                    text="Grab Destination"
            )
        else:
            sme_dest_geom_top.operator(
                    "maplus.showhidequicksmedestgeom",
                    icon='TRIA_DOWN',
                    text="",
                    emboss=False
            )
            sme_dest_geom_top.label(
                text="Destination Coordinates",
                icon="LIGHT_SUN"
            )

            sme_dest_geom_editor = sme_grab_col.box()
            ln_grab_all = sme_dest_geom_editor.row(align=True)
            ln_grab_all.operator(
                "maplus.quickscalematchedgegrabdestloc",
                icon='VERTEXSEL',
                text="Grab All Local"
            )
            ln_grab_all.operator(
                "maplus.quickscalematchedgegrabdest",
                icon='WORLD',
                text="Grab All Global"
            )
            special_grabs = sme_dest_geom_editor.row(align=True)
            special_grabs.operator(
                "maplus.quicksmegrabnormaldest",
                icon='LIGHT_HEMI',
                text="Grab Normal"
            )
            special_grabs_extra = sme_dest_geom_editor.row(align=True)
            special_grabs_extra.operator(
                "maplus.copyfromsmedest",
                icon='COPYDOWN',
                text="Copy (To Clipboard)"
            )
            special_grabs_extra.operator(
                "maplus.pasteintosmedest",
                icon='PASTEDOWN',
                text="Paste (From Clipboard)"
            )

            modifier_header = sme_dest_geom_editor.row()
            modifier_header.label(text="Line Modifiers:")
            apply_mods = modifier_header.row()
            apply_mods.alignment = 'RIGHT'

            item_mods_box = sme_dest_geom_editor.box()
            mods_row_1 = item_mods_box.row()
            mods_row_1.prop(
                bpy.types.AnyType(addon_data.quick_scale_match_edge_dest),
                'ln_make_unit_vec',
                text="Set Length Equal to One"
            )
            mods_row_1.prop(
                bpy.types.AnyType(addon_data.quick_scale_match_edge_dest),
                'ln_flip_direction',
                text="Flip Direction"
            )
            mods_row_2 = item_mods_box.row()
            mods_row_2.prop(
                bpy.types.AnyType(addon_data.quick_scale_match_edge_dest),
                'ln_multiplier',
                text="Multiplier"
            )

            maplus_guitools.layout_coordvec(
                parent_layout=sme_dest_geom_editor,
                coordvec_label="Start:",
                op_id_cursor_grab=(
                    "maplus.quicksmedestgrablinestartfromcursor"
                ),
                op_id_avg_grab=(
                    "maplus.quicksmegrabavgdestlinestart"
                ),
                op_id_local_grab=(
                    "maplus.quicksmedestgrablinestartfromactivelocal"
                ),
                op_id_global_grab=(
                    "maplus.quicksmedestgrablinestartfromactiveglobal"
                ),
                coord_container=addon_data.quick_scale_match_edge_dest,
                coord_attribute="line_start",
                op_id_cursor_send=(
                    "maplus.quicksmedestsendlinestarttocursor"
                ),
                op_id_text_tuple_swap_first=(
                    "maplus.quicksmedestswaplinepoints",
                    "End"
                )
            )

            maplus_guitools.layout_coordvec(
                parent_layout=sme_dest_geom_editor,
                coordvec_label="End:",
                op_id_cursor_grab=(
                    "maplus.quicksmedestgrablineendfromcursor"
                ),
                op_id_avg_grab=(
                    "maplus.quicksmegrabavgdestlineend"
                ),
                op_id_local_grab=(
                    "maplus.quicksmedestgrablineendfromactivelocal"
                ),
                op_id_global_grab=(
                    "maplus.quicksmedestgrablineendfromactiveglobal"
                ),
                coord_container=addon_data.quick_scale_match_edge_dest,
                coord_attribute="line_end",
                op_id_cursor_send=(
                    "maplus.quicksmedestsendlineendtocursor"
                ),
                op_id_text_tuple_swap_first=(
                    "maplus.quicksmedestswaplinepoints",
                    "Start"
                )
            )

        numeric_gui = sme_gui.column()
        numeric_gui.prop(
            addon_data,
            'quick_sme_numeric_mode',
            text='Numeric Input Mode'
        )
        numeric_settings = numeric_gui.box()
        numeric_grabs = numeric_settings.row()
        numeric_grabs.prop(
            addon_data,
            'quick_sme_numeric_auto',
            text='Auto Grab Target'
        )
        if not addon_data.quick_sme_numeric_auto:
            numeric_grabs.operator(
                "maplus.grabsmenumeric"
            )
        numeric_settings.prop(
            addon_data,
            'quick_sme_numeric_length',
            text='Target Length'
        )

        # Disable relevant items depending on whether numeric mode
        # is enabled or not
        if addon_data.quick_sme_numeric_mode:
            sme_grab_col.enabled = False
        else:
            numeric_settings.enabled = False

        sme_apply_header = sme_gui.row()
        sme_apply_header.label(text="Apply to:")
        sme_apply_header.prop(
            addon_data,
            'use_experimental',
            text='Enable Experimental Mesh Ops.'
        )
        sme_apply_items = sme_gui.row()
        sme_to_object_and_origin = sme_apply_items.column()
        sme_to_object_and_origin.operator(
            "maplus.quickscalematchedgeobject",
            text="Object"
        )
        sme_to_object_and_origin.operator(
            "maplus.quickscalematchedgeobjectorigin",
            text="Obj. Origin"
        )
        sme_mesh_apply_items = sme_apply_items.column(align=True)
        sme_mesh_apply_items.operator(
            "maplus.quickscalematchedgemeshselected",
            text="Mesh Piece"
        )
        sme_mesh_apply_items.operator(
            "maplus.quickscalematchedgewholemesh",
            text="Whole Mesh"
        )
