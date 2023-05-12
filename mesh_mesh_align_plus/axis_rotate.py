"""Axis Rotate tool, internals & UI."""


import math

import bmesh
import bpy
import mathutils

import mesh_mesh_align_plus.utils.exceptions as maplus_except
import mesh_mesh_align_plus.utils.geom as maplus_geom
import mesh_mesh_align_plus.utils.gui_tools as maplus_guitools


class MAPLUS_OT_AxisRotateBase(bpy.types.Operator):
    bl_idname = "maplus.axisrotatebase"
    bl_label = "Axis Rotate Base"
    bl_description = "Axis rotate base class"
    bl_options = {'REGISTER', 'UNDO'}
    target = None

    def execute(self, context):
        addon_data = bpy.context.scene.maplus_data
        prims = addon_data.prim_list
        previous_mode = maplus_geom.get_active_object().mode
        if not hasattr(self, "quick_op_target"):
            active_item = prims[addon_data.active_list_item]
        else:
            active_item = addon_data.quick_axis_rotate_transf
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
        if addon_data.quick_axis_rotate_auto_grab_src:
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

            if (
                not hasattr(self, "quick_op_target")
                and prims[active_item.axr_axis].kind != 'LINE'
            ):
                self.report(
                    {'ERROR'},
                    ('Wrong operands: "Axis Rotate" can only operate on '
                     'a line')
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
            # modifiers applied. Grab either directly from the scene data
            # (for quick ops), or from the MAPlus primitives
            # CollectionProperty on the scene data (for advanced tools)
            if hasattr(self, 'quick_op_target'):
                if addon_data.quick_axis_rotate_auto_grab_src:
                    vert_attribs_to_set = ('line_start', 'line_end')
                    try:
                        vert_data = maplus_geom.return_selected_verts(
                            maplus_geom.get_active_object(),
                            len(vert_attribs_to_set),
                            maplus_geom.get_active_object().matrix_world
                        )
                    except maplus_except.InsufficientSelectionError:
                        self.report({'ERROR'}, 'Not enough vertices selected.')
                        return {'CANCELLED'}
                    except maplus_except.NonMeshGrabError:
                        self.report(
                            {'ERROR'},
                            'Cannot grab coords: non-mesh or no active object.'
                        )
                        return {'CANCELLED'}

                    maplus_geom.set_item_coords(
                        addon_data.quick_axis_rotate_src,
                        vert_attribs_to_set,
                        vert_data
                    )

                src_global_data = maplus_geom.get_modified_global_coords(
                    geometry=addon_data.quick_axis_rotate_src,
                    kind='LINE'
                )

            else:
                src_global_data = maplus_geom.get_modified_global_coords(
                    geometry=prims[active_item.axr_axis],
                    kind='LINE'
                )

            # These global point coordinate vectors will be used to construct
            # geometry and transformations in both object (global) space
            # and mesh (local) space
            axis_start = src_global_data[0]
            axis_end = src_global_data[1]

            # Get rotation in proper units (radians)
            if (bpy.context.scene.unit_settings.system_rotation == 'RADIANS'):
                converted_rot_amount = active_item.axr_amount
            else:
                converted_rot_amount = math.radians(active_item.axr_amount)

            if self.target in {'OBJECT', 'OBJECT_ORIGIN'}:
                for item in multi_edit_targets:
                    # (Note that there are no transformation modifiers for this
                    # transformation type, so that section is omitted here)

                    # Get the object world matrix before we modify it here
                    item_matrix_unaltered = item.matrix_world.copy()
                    unaltered_inverse = item_matrix_unaltered.copy()
                    unaltered_inverse.invert()

                    # Construct the axis vector and corresponding matrix
                    axis = axis_end - axis_start
                    axis_rot = mathutils.Matrix.Rotation(
                        converted_rot_amount,
                        4,
                        axis
                    )

                    # Perform the rotation (axis will be realigned later)
                    item.rotation_euler.rotate(axis_rot)
                    bpy.context.view_layer.update()

                    # put the original line starting point (before the object
                    # was rotated) into the local object space
                    src_pivot_location_local = unaltered_inverse @ axis_start

                    # Calculate the new pivot location (after the
                    # first rotation), so that the axis can be moved
                    # back into place
                    new_pivot_loc_global = (
                        item.matrix_world @
                        src_pivot_location_local
                    )
                    pivot_to_dest = axis_start - new_pivot_loc_global

                    item.location += pivot_to_dest
                    bpy.context.view_layer.update()

            if self.target in {'MESH_SELECTED', 'WHOLE_MESH', 'OBJECT_ORIGIN'}:
                for item in multi_edit_targets:
                    self.report(
                        {'WARNING'},
                        ('Warning/Experimental: mesh transforms'
                         ' on objects with non-uniform scaling'
                         ' are not currently supported.')
                    )
                    # (Note that there are no transformation modifiers for this
                    # transformation type, so that section is omitted here)

                    # Init source mesh
                    src_mesh = bmesh.new()
                    src_mesh.from_mesh(item.data)

                    # Get the object world matrix
                    item_matrix_unaltered_loc = item.matrix_world.copy()
                    unaltered_inverse_loc = item_matrix_unaltered_loc.copy()
                    unaltered_inverse_loc.invert()

                    # Stored geom data in local coords
                    axis_start_loc = unaltered_inverse_loc @ axis_start
                    axis_end_loc = unaltered_inverse_loc @ axis_end

                    # Get axis vector in local space
                    axis_loc = axis_end_loc - axis_start_loc

                    # Get translation, pivot to local origin
                    axis_start_inv = axis_start_loc.copy()
                    axis_start_inv.negate()
                    src_pivot_to_loc_origin = mathutils.Matrix.Translation(
                        axis_start_inv
                    )
                    src_pivot_to_loc_origin.resize_4x4()

                    # Get local axis rotation
                    axis_rot_at_loc_origin = mathutils.Matrix.Rotation(
                        converted_rot_amount,
                        4,
                        axis_loc
                    )

                    # Get translation, pivot to dest
                    pivot_to_dest = mathutils.Matrix.Translation(
                        axis_start_loc
                    )
                    pivot_to_dest.resize_4x4()

                    axis_rotate_loc = (
                        pivot_to_dest @
                        axis_rot_at_loc_origin @
                        src_pivot_to_loc_origin
                    )

                    if self.target == 'MESH_SELECTED':
                        src_mesh.transform(
                            axis_rotate_loc,
                            filter={'SELECT'}
                        )
                    elif self.target == 'WHOLE_MESH':
                        src_mesh.transform(axis_rotate_loc)
                    elif self.target == 'OBJECT_ORIGIN':
                        # Note: a target of 'OBJECT_ORIGIN' is equivalent
                        # to performing an object transf. + an inverse
                        # whole mesh level transf. To the user,
                        # the object appears to stay in the same place,
                        # while only the object's origin moves.
                        src_mesh.transform(axis_rotate_loc.inverted())

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


class MAPLUS_OT_AxisRotateObject(MAPLUS_OT_AxisRotateBase):
    bl_idname = "maplus.axisrotateobject"
    bl_label = "Axis Rotate"
    bl_description = "Rotates around an axis"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT'


class MAPLUS_OT_QuickAxisRotateObject(MAPLUS_OT_AxisRotateBase):
    bl_idname = "maplus.quickaxisrotateobject"
    bl_label = "Axis Rotate"
    bl_description = "Rotates around an axis"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT'
    quick_op_target = True


class MAPLUS_OT_QuickAxisRotateObjectOrigin(MAPLUS_OT_AxisRotateBase):
    bl_idname = "maplus.quickaxisrotateobjectorigin"
    bl_label = "Axis Rotate"
    bl_description = "Rotates around an axis"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT_ORIGIN'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_AxisRotateMeshSelected(MAPLUS_OT_AxisRotateBase):
    bl_idname = "maplus.axisrotatemeshselected"
    bl_label = "Axis Rotate"
    bl_description = "Rotates around an axis"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'MESH_SELECTED'

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_AxisRotateWholeMesh(MAPLUS_OT_AxisRotateBase):
    bl_idname = "maplus.axisrotatewholemesh"
    bl_label = "Axis Rotate"
    bl_description = "Rotates around an axis"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'WHOLE_MESH'

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_QuickAxisRotateMeshSelected(MAPLUS_OT_AxisRotateBase):
    bl_idname = "maplus.quickaxisrotatemeshselected"
    bl_label = "Axis Rotate"
    bl_description = "Rotates around an axis"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'MESH_SELECTED'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_QuickAxisRotateWholeMesh(MAPLUS_OT_AxisRotateBase):
    bl_idname = "maplus.quickaxisrotatewholemesh"
    bl_label = "Axis Rotate"
    bl_description = "Rotates around an axis"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'WHOLE_MESH'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_PT_QuickAxisRotateGUI(bpy.types.Panel):
    bl_idname = "MAPLUS_PT_QuickAxisRotateGUI"
    bl_label = "Quick Axis Rotate"
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

        axr_top = layout.row()
        axr_gui = layout.box()
        axr_top.label(text=
            "Axis Rotate",
            icon="FORCE_MAGNETIC"
        )
        axr_grab_col = axr_gui.column()
        axr_grab_col.prop(
            addon_data,
            'quick_axis_rotate_auto_grab_src',
            text='Auto Grab Axis from Selected Vertices'
        )

        axr_src_geom_top = axr_grab_col.row(align=True)
        if not addon_data.quick_axis_rotate_auto_grab_src:
            if not addon_data.quick_axr_show_src_geom:
                axr_src_geom_top.operator(
                        "maplus.showhidequickaxrsrcgeom",
                        icon='TRIA_RIGHT',
                        text="",
                        emboss=False
                )
                preserve_button_roundedge = axr_src_geom_top.row()
                preserve_button_roundedge.operator(
                        "maplus.quickaxisrotategrabsrc",
                        icon='LIGHT_SUN',
                        text="Grab Axis"
                )
                preserve_button_roundedge.operator(
                    "maplus.quickaxrgrabnormalsrc",
                    icon='LIGHT_HEMI',
                    text=""
                )
            else:
                axr_src_geom_top.operator(
                        "maplus.showhidequickaxrsrcgeom",
                        icon='TRIA_DOWN',
                        text="",
                        emboss=False
                )
                axr_src_geom_top.label(
                    text="Source Coordinates",
                    icon="LIGHT_SUN"
                )

                axr_src_geom_editor = axr_grab_col.box()
                ln_grab_all = axr_src_geom_editor.row(align=True)
                ln_grab_all.operator(
                    "maplus.quickaxisrotategrabsrcloc",
                    icon='VERTEXSEL',
                    text="Grab All Local"
                )
                ln_grab_all.operator(
                    "maplus.quickaxisrotategrabsrc",
                    icon='WORLD',
                    text="Grab All Global"
                )

                special_grabs = axr_src_geom_editor.row(align=True)
                special_grabs.operator(
                    "maplus.quickaxrgrabnormalsrc",
                    icon='LIGHT_HEMI',
                    text="Grab Normal"
                )
                special_grabs_extra = axr_src_geom_editor.row(align=True)
                special_grabs_extra.operator(
                    "maplus.copyfromaxrsrc",
                    icon='COPYDOWN',
                    text="Copy (To Clipboard)"
                )
                special_grabs_extra.operator(
                    "maplus.pasteintoaxrsrc",
                    icon='PASTEDOWN',
                    text="Paste (From Clipboard)"
                )

                modifier_header = axr_src_geom_editor.row()
                modifier_header.label(text="Line Modifiers:")
                apply_mods = modifier_header.row()
                apply_mods.alignment = 'RIGHT'

                item_mods_box = axr_src_geom_editor.box()
                mods_row_1 = item_mods_box.row()
                mods_row_1.prop(
                    bpy.types.AnyType(addon_data.quick_axis_rotate_src),
                    'ln_make_unit_vec',
                    text="Set Length Equal to One"
                )
                mods_row_1.prop(
                    bpy.types.AnyType(addon_data.quick_axis_rotate_src),
                    'ln_flip_direction',
                    text="Flip Direction"
                )
                mods_row_2 = item_mods_box.row()
                mods_row_2.prop(
                    bpy.types.AnyType(addon_data.quick_axis_rotate_src),
                    'ln_multiplier',
                    text="Multiplier"
                )

                maplus_guitools.layout_coordvec(
                    parent_layout=axr_src_geom_editor,
                    coordvec_label="Start:",
                    op_id_cursor_grab=(
                        "maplus.quickaxrsrcgrablinestartfromcursor"
                    ),
                    op_id_avg_grab=(
                        "maplus.quickaxrgrabavgsrclinestart"
                    ),
                    op_id_local_grab=(
                        "maplus.quickaxrsrcgrablinestartfromactivelocal"
                    ),
                    op_id_global_grab=(
                        "maplus.quickaxrsrcgrablinestartfromactiveglobal"
                    ),
                    coord_container=addon_data.quick_axis_rotate_src,
                    coord_attribute="line_start",
                    op_id_cursor_send=(
                        "maplus.quickaxrsrcsendlinestarttocursor"
                    ),
                    op_id_text_tuple_swap_first=(
                        "maplus.quickaxrsrcswaplinepoints",
                        "End"
                    )
                )

                maplus_guitools.layout_coordvec(
                    parent_layout=axr_src_geom_editor,
                    coordvec_label="End:",
                    op_id_cursor_grab=(
                        "maplus.quickaxrsrcgrablineendfromcursor"
                    ),
                    op_id_avg_grab=(
                        "maplus.quickaxrgrabavgsrclineend"
                    ),
                    op_id_local_grab=(
                        "maplus.quickaxrsrcgrablineendfromactivelocal"
                    ),
                    op_id_global_grab=(
                        "maplus.quickaxrsrcgrablineendfromactiveglobal"
                    ),
                    coord_container=addon_data.quick_axis_rotate_src,
                    coord_attribute="line_end",
                    op_id_cursor_send=(
                        "maplus.quickaxrsrcsendlineendtocursor"
                    ),
                    op_id_text_tuple_swap_first=(
                        "maplus.quickaxrsrcswaplinepoints",
                        "Start"
                    )
                )

        if addon_data.quick_axr_show_src_geom:
            axr_grab_col.separator()

        axr_gui.label(text="Operator settings:", icon="PREFERENCES")
        axr_mods = axr_gui.box()
        axr_mods_row1 = axr_mods.row()
        axr_mods_row1.prop(
            addon_data.quick_axis_rotate_transf,
            'axr_amount',
            text='Amount'
        )
        axr_apply_header = axr_gui.row()
        axr_apply_header.label(text="Apply to:")
        axr_apply_header.prop(
            addon_data,
            'use_experimental',
            text='Enable Experimental Mesh Ops.'
        )
        axr_apply_items = axr_gui.row()
        axr_to_object_and_origin = axr_apply_items.column()
        axr_to_object_and_origin.operator(
            "maplus.quickaxisrotateobject",
            text="Object"
        )
        axr_to_object_and_origin.operator(
            "maplus.quickaxisrotateobjectorigin",
            text="Obj. Origin"
        )
        axr_mesh_apply_items = axr_apply_items.column(align=True)
        axr_mesh_apply_items.operator(
            "maplus.quickaxisrotatemeshselected",
            text="Mesh Piece"
        )
        axr_mesh_apply_items.operator(
            "maplus.quickaxisrotatewholemesh",
            text="Whole Mesh"
        )
