import bpy
from bpy.props import EnumProperty, BoolProperty, StringProperty
from mathutils import Vector
from .. utils.draw import draw_fading_label
from .. utils.modifier import get_mod_obj
from .. utils.registration import get_prefs
from .. utils.view import ensure_visibility
from .. colors import yellow, red, green, white


axis_items = [("0", "X", ""),
              ("1", "Y", ""),
              ("2", "Z", "")]

# TODO: use the axis_items in items.py?


class SelectCenterObjects(bpy.types.Operator):
    bl_idname = "machin3.select_center_objects"
    bl_label = "MACHIN3: Select Center Objects"
    bl_description = "Selects Objects in the Center, objects, that have verts on both sides of the X, Y or Z axis."
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(name="Axis", items=axis_items, default="0")

    def draw(self, context):
        layout = self.layout

        column = layout.column()

        row = column.row()
        row.prop(self, "axis", expand=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        visible = [obj for obj in context.visible_objects if obj.type == "MESH"]

        if visible:

            bpy.ops.object.select_all(action='DESELECT')

            for obj in visible:
                mx = obj.matrix_world

                coords = [(mx @ Vector(co))[int(self.axis)] for co in obj.bound_box]

                if min(coords) < 0 and max(coords) > 0:
                    obj.select_set(True)

        return {'FINISHED'}


class SelectWireObjects(bpy.types.Operator):
    bl_idname = "machin3.select_wire_objects"
    bl_label = "MACHIN3: Select Wire Objects"
    bl_description = "Select Objects set to WIRE display type\nALT: Hide Objects\nCLTR: Include Empties"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if context.mode == 'OBJECT':
            return [obj for obj in context.visible_objects if obj.display_type in ['WIRE', 'BOUNDS'] or obj.type == 'EMPTY']

    def invoke(self, context, event):
        bpy.ops.object.select_all(action='DESELECT')

        # fix objects without proper display_type
        for obj in context.visible_objects:
            if obj.display_type == '':
                obj.display_type = 'WIRE'


        # get all wire objects, optionally including empties
        if event.ctrl:
            objects = [obj for obj in context.visible_objects if obj.display_type in ['WIRE', 'BOUNDS'] or obj.type == 'EMPTY']
        else:
            objects = [obj for obj in context.visible_objects if obj.display_type in ['WIRE', 'BOUNDS']]

        for obj in objects:
            if event.alt:
                obj.hide_set(True)
            else:
                obj.select_set(True)

        return {'FINISHED'}


# SELECT HIERARCHY

class SelectHierarchy(bpy.types.Operator):
    bl_idname = "machin3.select_hierarchy"
    bl_label = "MACHIN3: Select Hierarchy"
    bl_description = "Select Hierarchy Down"
    bl_options = {'REGISTER', 'UNDO'}

    direction: StringProperty(name="Hierarchy Direction", default='DOWN')

    include_parent: BoolProperty(name="Include Parent", description="Include the Parent in the Selection", default=False)

    recursive: BoolProperty(name="Select Recursive Children", description="Select Children Recursively", default=False)
    unhide: BoolProperty(name="Select Hidden Children", description="Unhide and Select Hidden Children", default=False)
    include_mod_objects: BoolProperty(name="Include Mod Objects", description="Include Mod Objects, even if they aren't parented", default=False)

    def draw(self, context):
        layout = self.layout

        column = layout.column(align=True)

        row = column.row(align=True)
        row.prop(self, 'include_parent', toggle=True)
        row.prop(self, 'include_mod_objects', toggle=True)

        row = column.row(align=True)
        row.prop(self, 'recursive', text="Recursive", toggle=True)
        row.prop(self, 'unhide', text="Unhide", toggle=True)

    @classmethod
    def poll(cls, context):
        if context.mode == 'OBJECT':
            return context.selected_objects

    def invoke(self, context, event):
        self.coords = Vector((event.mouse_region_x, event.mouse_region_y)) + Vector((20, 20))
        return self.execute(context)

    def execute(self, context):
        sel = context.selected_objects

        # select down
        if self.direction == 'DOWN':
            ret = self.select_down(context, sel)

            if type(ret) == str:
                time = get_prefs().HUD_fade_select_hierarchy

                if ret == 'BOTTOM':
                    text = ["Reached Bottom of Hierarchy",
                            "with Hidden Children"]

                    draw_fading_label(context, text=text, x=self.coords[0], y=self.coords[1], center=False, size=12, color=[yellow, white], time=time, alpha=0.5)

                # note we offset this eon down a litte to ensue it's not drawing on top of the previously drawn, and still fading BOTTOM label, after it was encountered first, and then the op was re-invoked with the unhide option
                elif ret == 'ABSOLUTE_BOTTOM':
                    scale = context.preferences.system.ui_scale
                    draw_fading_label(context, text="Reached ABSOLUTE Bottom of Hierarchy", x=self.coords[0], y=self.coords[1] - 20 * scale, center=False, size=12, color=red, time=time, alpha=1)

        return {'FINISHED'}


    # UTILS

    def select_down(self, context, objects, debug=False):
        '''
        based on the current selection select down
        '''

        # debug = True

        children = set()
        first_lvl_children = set()
        init_selection = set(objects)

        if debug:
            print()
            print("selected:")

            for obj in init_selection:
                print("", obj.name)

        # get all children, optionally (by default) recursively, and optionally mod objects too
        for obj in init_selection:

            # always get the first level children (for later top level active object setting)
            first_lvl_children.update({c for c in obj.children if c.name in context.view_layer.objects})

            # then collect the children or recursive children for actual selection use
            if self.recursive:
                children.update({c for c in obj.children_recursive if c.name in context.view_layer.objects})
            else:
                children.update({c for c in obj.children if c.name in context.view_layer.objects})

            # optionally collect mod objects too
            if self.include_mod_objects:
                for mod in obj.modifiers:
                    if mod.show_viewport:
                        modobj = get_mod_obj(mod)

                        if modobj and modobj.name in context.view_layer.objects:
                            children.add(modobj)
       
        # ensure visibility (local view) of all children, and optionally unhide if that option is chosen, so they can be selected
        ensure_visibility(context, children, unhide=self.unhide)

        # from the set of all children, get the visible(selectable) ones, then the hidden ones, and the top_children, which are just the first level visible children
        visible_children = set(c for c in children if c.visible_get())
        hidden_children = set(children) - visible_children
        top_children = first_lvl_children & visible_children

        if debug:
            print()
            print("children (visible):")

            for obj in visible_children:
                print("", obj.name)

            print()
            print("children (hiddden)")

            for obj in hidden_children:
                print("", obj.name)

        # optionally (by default) deselect the parents (original selection)
        # NOTE: this has to come first, you may reselect some of them as children in the next step, if objects from multiple levels were selected initially
        if not self.include_parent:

            # but only if there actually are visible (selectable) children, otherwise you can end up with nothing seleected, which we want to avoid at all costs
            if visible_children:
                for obj in init_selection:
                    obj.select_set(False)

        # then select the visible children
        for obj in visible_children:
            obj.select_set(True)

        # compare the new selection to the old one
        new_selection = set(obj for obj in context.selected_objects)

        # nothing changed, which means we reached the bottom of the hierarchy
        if init_selection == new_selection:
            if hidden_children:
                return 'BOTTOM'

            else:
                return 'ABSOLUTE_BOTTOM'

        # selection did change, ensure the active object - if there is one - is among the top_children
        else:
            active = context.active_object

            if active and active not in top_children:

                # but prefer making group empties active, if present
                group_empties = [obj for obj in top_children if obj.M3.is_group_empty]

                # TODO: this is too primitive for muilti level selections, where the group empties of various levels are counted as first level
                # in fact, this doesn't only apply to groups but for objects too

                if group_empties:
                    context.view_layer.objects.active = group_empties[0]
                else:
                    context.view_layer.objects.active = top_children.pop()

        return True
