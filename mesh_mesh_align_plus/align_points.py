"""Align Points tool, internals & UI."""


import bmesh
import bpy
import mathutils

import mesh_mesh_align_plus.utils.exceptions as maplus_except
import mesh_mesh_align_plus.utils.geom as maplus_geom
import mesh_mesh_align_plus.utils.gui_tools as maplus_guitools


class MAPLUS_OT_AlignPointsBase(bpy.types.Operator):
    bl_idname = "maplus.alignpointsbase"
    bl_label = "Align Points Base"
    bl_description = "Align points base class"
    bl_options = {'REGISTER', 'UNDO'}
    target = None

    def execute(self, context):
        addon_data = bpy.context.scene.maplus_data
        prims = addon_data.prim_list
        previous_mode = maplus_geom.get_active_object().mode
        if not hasattr(self, "quick_op_target"):
            active_item = prims[addon_data.active_list_item]
        else:
            active_item = addon_data.quick_align_pts_transf
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
        if addon_data.quick_align_pts_auto_grab_src:
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

            # todo: use a bool check and put on all derived classes
            # instead of hasattr
            if not hasattr(self, 'quick_op_target') and (
                prims[active_item.apt_pt_one].kind != 'POINT'
                or prims[active_item.apt_pt_two].kind != 'POINT'
            ):
                self.report(
                    {'ERROR'},
                    ('Wrong operands: "Align Points" can only operate on '
                     'two points')
                )
                return {'CANCELLED'}

            if maplus_geom.get_active_object().type == 'MESH':
                # a bmesh can only be initialized in edit mode...todo/better way?
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
                if addon_data.quick_align_pts_auto_grab_src:
                    vert_attribs_to_set = ('point',)
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
                        addon_data.quick_align_pts_src,
                        vert_attribs_to_set,
                        vert_data
                    )

                src_global_data = maplus_geom.get_modified_global_coords(
                    geometry=addon_data.quick_align_pts_src,
                    kind='POINT'
                )
                dest_global_data = maplus_geom.get_modified_global_coords(
                    geometry=addon_data.quick_align_pts_dest,
                    kind='POINT'
                )

            else:
                src_global_data = maplus_geom.get_modified_global_coords(
                    geometry=prims[active_item.apt_pt_one],
                    kind='POINT'
                )
                dest_global_data = maplus_geom.get_modified_global_coords(
                    geometry=prims[active_item.apt_pt_two],
                    kind='POINT'
                )

            # These global point coordinate vectors will be used to construct
            # geometry and transformations in both object (global) space
            # and mesh (local) space
            src_pt = src_global_data[0]
            dest_pt = dest_global_data[0]

            if self.target in {'OBJECT', 'OBJECT_ORIGIN'}:
                for item in multi_edit_targets:
                    align_points = dest_pt - src_pt

                    # Take modifiers on the transformation item into account,
                    # in global (object) space
                    if active_item.apt_make_unit_vector:
                        align_points.normalize()
                    if active_item.apt_flip_direction:
                        align_points.negate()
                    align_points *= active_item.apt_multiplier

                    item.location += align_points

            if self.target in {'MESH_SELECTED', 'WHOLE_MESH', 'OBJECT_ORIGIN'}:
                for item in multi_edit_targets:
                    self.report(
                        {'WARNING'},
                        ('Warning/Experimental: mesh transforms'
                         ' on objects with non-uniform scaling'
                         ' are not currently supported.')
                    )
                    # Init source mesh
                    src_mesh = bmesh.new()
                    src_mesh.from_mesh(item.data)

                    active_obj_transf = maplus_geom.get_active_object().matrix_world.copy()
                    inverse_active = active_obj_transf.copy()
                    inverse_active.invert()

                    # Stored geom data in local coords
                    src_pt_loc = inverse_active @ src_pt
                    dest_pt_loc = inverse_active @ dest_pt

                    # Get translation vector (in local space), src to dest
                    align_points_vec = dest_pt_loc - src_pt_loc

                    # Take modifiers on the transformation item into account,
                    # in local (mesh) space
                    if active_item.apt_make_unit_vector:
                        # There are special considerations for this modifier
                        # since we need to achieve a global length of
                        # one, but can only transform it in local space
                        # (NOTE: assumes only uniform scaling on the
                        # active object)
                        scaling_factor = 1.0 / item.scale[0]
                        align_points_vec.normalize()
                        align_points_vec *= scaling_factor
                    if active_item.apt_flip_direction:
                        align_points_vec.negate()
                    align_points_vec *= active_item.apt_multiplier

                    align_points_loc = mathutils.Matrix.Translation(
                        align_points_vec
                    )

                    if self.target == 'MESH_SELECTED':
                        src_mesh.transform(
                            align_points_loc,
                            filter={'SELECT'}
                        )
                    elif self.target == 'WHOLE_MESH':
                        src_mesh.transform(align_points_loc)
                    elif self.target == 'OBJECT_ORIGIN':
                        # Note: a target of 'OBJECT_ORIGIN' is equivalent
                        # to performing an object transf. + an inverse
                        # whole mesh level transf. To the user,
                        # the object appears to stay in the same place,
                        # while only the object's origin moves.
                        src_mesh.transform(align_points_loc.inverted())

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


class MAPLUS_OT_AlignPointsObject(MAPLUS_OT_AlignPointsBase):
    bl_idname = "maplus.alignpointsobject"
    bl_label = "Align Points Object"
    bl_description = (
        "Match the location of one vertex on a mesh object to another"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT'


class MAPLUS_OT_QuickAlignPointsObject(MAPLUS_OT_AlignPointsBase):
    bl_idname = "maplus.quickalignpointsobject"
    bl_label = "Quick Align Points Object"
    bl_description = (
        "Match the location of one vertex on a mesh object to another"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT'
    quick_op_target = True


class MAPLUS_OT_QuickAlignPointsObjectOrigin(MAPLUS_OT_AlignPointsBase):
    bl_idname = "maplus.quickalignpointsobjectorigin"
    bl_label = "Quick Align Points Object Origin"
    bl_description = (
        "Match the location of one vertex on a mesh object to another"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'OBJECT_ORIGIN'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_AlignPointsMeshSelected(MAPLUS_OT_AlignPointsBase):
    bl_idname = "maplus.alignpointsmeshselected"
    bl_label = "Align Points Mesh Selected"
    bl_description = (
        "Match the location of one vertex on a mesh piece "
        "(the selected verts) to another"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'MESH_SELECTED'

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_QuickAlignPointsMeshSelected(MAPLUS_OT_AlignPointsBase):
    bl_idname = "maplus.quickalignpointsmeshselected"
    bl_label = "Quick Align Points Mesh Selected"
    bl_description = (
        "Match the location of one vertex on a mesh piece "
        "(the selected verts) to another"
    )
    bl_options = {'REGISTER', 'UNDO'}
    target = 'MESH_SELECTED'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_AlignPointsWholeMesh(MAPLUS_OT_AlignPointsBase):
    bl_idname = "maplus.alignpointswholemesh"
    bl_label = "Align Points Whole Mesh"
    bl_description = "Match the location of one vertex on a mesh to another"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'WHOLE_MESH'

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_OT_QuickAlignPointsWholeMesh(MAPLUS_OT_AlignPointsBase):
    bl_idname = "maplus.quickalignpointswholemesh"
    bl_label = "Quick Align Points Whole Mesh"
    bl_description = "Match the location of one vertex on a mesh to another"
    bl_options = {'REGISTER', 'UNDO'}
    target = 'WHOLE_MESH'
    quick_op_target = True

    @classmethod
    def poll(cls, context):
        addon_data = bpy.context.scene.maplus_data
        return bool(addon_data.use_experimental)


class MAPLUS_PT_QuickAlignPointsGUI(bpy.types.Panel):
    bl_idname = "MAPLUS_PT_QuickAlignPointsGUI"
    bl_label = "Quick Align Points"
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

        apg_top = layout.row()
        align_pts_gui = layout.box()
        apg_top.label(
            text="Align Points",
            icon="PIVOT_INDIVIDUAL"
        )
        apt_grab_col = align_pts_gui.column()
        apt_grab_col.prop(
            addon_data,
            'quick_align_pts_auto_grab_src',
            text='Auto Grab Source from Selected Vertices'
        )

        apt_src_geom_top = apt_grab_col.row(align=True)
        if not addon_data.quick_align_pts_auto_grab_src:
            if not addon_data.quick_apt_show_src_geom:
                apt_src_geom_top.operator(
                        "maplus.showhidequickaptsrcgeom",
                        icon='TRIA_RIGHT',
                        text="",
                        emboss=False
                )
                preserve_button_roundedge = apt_src_geom_top.row()
                preserve_button_roundedge.operator(
                        "maplus.quickalignpointsgrabsrc",
                        icon='LAYER_ACTIVE',
                        text="Grab Source"
                )
                preserve_button_roundedge.operator(
                        "maplus.quickaptgrabavgsrc",
                        icon='GROUP_VERTEX',
                        text=""
                )

            else:
                apt_src_geom_top.operator(
                        "maplus.showhidequickaptsrcgeom",
                        icon='TRIA_DOWN',
                        text="",
                        emboss=False
                )
                apt_src_geom_top.label(
                    text="Source Coordinates",
                    icon="LAYER_ACTIVE"
                )

                apt_src_geom_editor = apt_grab_col.box()
                pt_grab_all = apt_src_geom_editor.row(align=True)
                pt_grab_all.operator(
                    "maplus.quickalignpointsgrabsrcloc",
                    icon='VERTEXSEL',
                    text="Grab All Local"
                )
                pt_grab_all.operator(
                    "maplus.quickalignpointsgrabsrc",
                    icon='WORLD',
                    text="Grab All Global"
                )
                special_grabs = apt_src_geom_editor.row(align=True)
                special_grabs.operator(
                    "maplus.copyfromaptsrc",
                    icon='COPYDOWN',
                    text="Copy (To Clipboard)"
                )
                special_grabs.operator(
                    "maplus.pasteintoaptsrc",
                    icon='PASTEDOWN',
                    text="Paste (From Clipboard)"
                )

                modifier_header = apt_src_geom_editor.row()
                modifier_header.label(text="Point Modifiers:")
                apply_mods = modifier_header.row()
                apply_mods.alignment = 'RIGHT'

                item_mods_box = apt_src_geom_editor.box()
                mods_row_1 = item_mods_box.row()
                mods_row_1.prop(
                    bpy.types.AnyType(addon_data.quick_align_pts_src),
                    'pt_make_unit_vec',
                    text="Set Length Equal to One"
                )
                mods_row_1.prop(
                    bpy.types.AnyType(addon_data.quick_align_pts_src),
                    'pt_flip_direction',
                    text="Flip Direction"
                )
                mods_row_2 = item_mods_box.row()
                mods_row_2.prop(
                    bpy.types.AnyType(addon_data.quick_align_pts_src),
                    'pt_multiplier',
                    text="Multiplier"
                )

                maplus_guitools.layout_coordvec(
                    parent_layout=apt_src_geom_editor,
                    coordvec_label="Pt. Origin:",
                    op_id_cursor_grab=(
                        "maplus.quickaptsrcgrabpointfromcursor"
                    ),
                    op_id_avg_grab=(
                        "maplus.quickaptgrabavgsrc"
                    ),
                    op_id_local_grab=(
                        "maplus.quickalignpointsgrabsrcloc"
                    ),
                    op_id_global_grab=(
                        "maplus.quickalignpointsgrabsrc"
                    ),
                    coord_container=addon_data.quick_align_pts_src,
                    coord_attribute="point",
                    op_id_cursor_send=(
                        "maplus.quickaptsrcsendpointtocursor"
                    )
                )

        if addon_data.quick_apt_show_src_geom:
            apt_grab_col.separator()

        apt_dest_geom_top = apt_grab_col.row(align=True)
        if not addon_data.quick_apt_show_dest_geom:
            apt_dest_geom_top.operator(
                    "maplus.showhidequickaptdestgeom",
                    icon='TRIA_RIGHT',
                    text="",
                    emboss=False
            )
            preserve_button_roundedge = apt_dest_geom_top.row()
            preserve_button_roundedge.operator(
                    "maplus.quickalignpointsgrabdest",
                    icon='LAYER_ACTIVE',
                    text="Grab Destination"
            )
            preserve_button_roundedge.operator(
                    "maplus.quickaptgrabavgdest",
                    icon='GROUP_VERTEX',
                    text=""
            )

        else:
            apt_dest_geom_top.operator(
                    "maplus.showhidequickaptdestgeom",
                    icon='TRIA_DOWN',
                    text="",
                    emboss=False
            )
            apt_dest_geom_top.label(
                text="Destination Coordinates",
                icon="LAYER_ACTIVE"
            )

            apt_dest_geom_editor = apt_grab_col.box()
            pt_grab_all = apt_dest_geom_editor.row(align=True)
            pt_grab_all.operator(
                "maplus.quickalignpointsgrabdestloc",
                icon='VERTEXSEL',
                text="Grab All Local"
            )
            pt_grab_all.operator(
                "maplus.quickalignpointsgrabdest",
                icon='WORLD',
                text="Grab All Global"
            )
            special_grabs = apt_dest_geom_editor.row(align=True)
            special_grabs.operator(
                "maplus.copyfromaptdest",
                icon='COPYDOWN',
                text="Copy (To Clipboard)"
            )
            special_grabs.operator(
                "maplus.pasteintoaptdest",
                icon='PASTEDOWN',
                text="Paste (From Clipboard)"
            )

            modifier_header = apt_dest_geom_editor.row()
            modifier_header.label(text="Point Modifiers:")
            apply_mods = modifier_header.row()
            apply_mods.alignment = 'RIGHT'

            item_mods_box = apt_dest_geom_editor.box()
            mods_row_1 = item_mods_box.row()
            mods_row_1.prop(
                bpy.types.AnyType(addon_data.quick_align_pts_dest),
                'pt_make_unit_vec',
                text="Set Length Equal to One"
            )
            mods_row_1.prop(
                bpy.types.AnyType(addon_data.quick_align_pts_dest),
                'pt_flip_direction',
                text="Flip Direction"
            )
            mods_row_2 = item_mods_box.row()
            mods_row_2.prop(
                bpy.types.AnyType(addon_data.quick_align_pts_dest),
                'pt_multiplier',
                text="Multiplier"
            )

            maplus_guitools.layout_coordvec(
                parent_layout=apt_dest_geom_editor,
                coordvec_label="Pt. Origin:",
                op_id_cursor_grab=(
                    "maplus.quickaptdestgrabpointfromcursor"
                ),
                op_id_avg_grab=(
                    "maplus.quickaptgrabavgdest"
                ),
                op_id_local_grab=(
                    "maplus.quickalignpointsgrabdestloc"
                ),
                op_id_global_grab=(
                    "maplus.quickalignpointsgrabdest"
                ),
                coord_container=addon_data.quick_align_pts_dest,
                coord_attribute="point",
                op_id_cursor_send=(
                    "maplus.quickaptdestsendpointtocursor"
                )
            )

        align_pts_gui.label(text="Operator settings:", icon="PREFERENCES")
        apt_mods = align_pts_gui.box()
        apt_box_row1 = apt_mods.row()
        apt_box_row1.prop(
            addon_data.quick_align_pts_transf,
            'apt_make_unit_vector',
            text='Set Length to 1'
        )
        apt_box_row1.prop(
            addon_data.quick_align_pts_transf,
            'apt_flip_direction',
            text='Flip Direction'
        )
        apt_box_row2 = apt_mods.row()
        apt_box_row2.prop(
            addon_data.quick_align_pts_transf,
            'apt_multiplier',
            text='Multiplier'
        )
        apt_apply_header = align_pts_gui.row()
        apt_apply_header.label(text="Apply to:")
        apt_apply_header.prop(
            addon_data,
            'use_experimental',
            text='Enable Experimental Mesh Ops.'
        )
        apt_apply_items = align_pts_gui.row()
        apt_to_object_and_origin = apt_apply_items.column()
        apt_to_object_and_origin.operator(
            "maplus.quickalignpointsobject",
            text="Object"
        )
        apt_to_object_and_origin.operator(
            "maplus.quickalignpointsobjectorigin",
            text="Obj. Origin"
        )
        apt_mesh_apply_items = apt_apply_items.column(align=True)
        apt_mesh_apply_items.operator(
            "maplus.quickalignpointsmeshselected",
            text="Mesh Piece"
        )
        apt_mesh_apply_items.operator(
            "maplus.quickalignpointswholemesh",
            text="Whole Mesh"
        )
