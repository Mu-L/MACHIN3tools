from os import tcgetpgrp
import bpy
from bpy.props import EnumProperty, BoolProperty, StringProperty
from mathutils import Vector
from .. utils.draw import draw_fading_label, get_text_dimensions
from .. utils.modifier import get_mod_obj
from .. utils.object import get_object_hierarchy_layers, get_parent
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

last_ret = ''

class SelectHierarchy(bpy.types.Operator):
    bl_idname = "machin3.select_hierarchy"
    bl_label = "MACHIN3: Select Hierarchy"
    bl_description = "Select Hierarchy Down"
    bl_options = {'REGISTER', 'UNDO'}

    direction: StringProperty(name="Hierarchy Direction", default='DOWN')

    include_selection: BoolProperty(name="Include Selection", description="Include Current Selection", default=False)
    include_mod_objects: BoolProperty(name="Include Mod Objects", description="Include Mod Objects, even if they aren't parented", default=False)

    unhide: BoolProperty(name="Unhide + Select", description="Unhide and Select hidden Children/Parents, if you encounter them", default=False)

    # note: for down selection we default to recursive, while for up selections we don't
    recursive_down: BoolProperty(name="Select Recursive Children", description="Select Children Recursively", default=True)
    recursive_up: BoolProperty(name="Select Recursive Parents", description="Select Parents Recursively", default=False)

    @classmethod
    def poll(cls, context):

        if context.mode == 'OBJECT':
            return context.selected_objects

    def draw(self, context):
        layout = self.layout

        column = layout.column(align=True)

        row = column.row(align=True)
        row.prop(self, 'include_selection', toggle=True)

        if self.direction == 'DOWN':
            row.prop(self, 'include_mod_objects', toggle=True)

        row = column.row(align=True)
        row.prop(self, 'recursive_down' if self.direction == 'DOWN' else 'recursive_up', text="Recursive", toggle=True)
        row.prop(self, 'unhide', text="Unhide", toggle=True)

    def invoke(self, context, event):
        self.coords = Vector((event.mouse_region_x, event.mouse_region_y)) + Vector((30, -15))
        return self.execute(context)

    def execute(self, context):
        global last_ret

        time = get_prefs().HUD_fade_select_hierarchy
        scale = context.preferences.system.ui_scale

        # sort view_layer objects into hierarchical list of lists of layers based on their parent child relationships
        layers = get_object_hierarchy_layers(context, debug=False)


        # SELECT UP

        if self.direction == 'UP':
            ret = self.select_up(context, context.selected_objects, layers)

            # REACHED TOP

            if type(ret) == str:
                if ret == 'TOP':
                    text = ["Reached Top of Hierarchy",
                            "with Hidden Parents"]

                    y_offset = 18 * scale

                    draw_fading_label(context, text=text, x=self.coords[0], y=self.coords[1] + y_offset, center=False, size=12, color=[yellow, white], time=time, alpha=0.5)

                # note we offset this one up a litte to ensure it's not drawing on top of the previously drawn, and still fading TOP label, after it was encountered first, and then the op was re-invoked with the unhide option
                elif ret == 'ABSOLUTE_TOP':
                    y_offset = 54 * scale if last_ret == 'TOP' else 18 * scale

                    draw_fading_label(context, text="Reached ABSOLUTE Top of Hierarchy", x=self.coords[0], y=self.coords[1] + y_offset, center=False, size=12, color=green, time=time, alpha=1)

                last_ret = ret


            # UP SELECTION

            else:
                draw_fading_label(context, text="Selecting Up ", x=self.coords[0], y=self.coords[1], center=False, size=12, color=white, time=time, alpha=0.5)
                x_offset = get_text_dimensions(context, "Selecting Up ", size=12)[0]

                if self.unhide:
                    draw_fading_label(context, text="+ Unhiding ", x=self.coords[0] + x_offset, y=self.coords[1] + 5 * scale, center=False, size=10, color=white, time=time, alpha=0.3)

                if self.recursive_up:
                    draw_fading_label(context, text="+ Recursive ", x=self.coords[0] + x_offset, y=self.coords[1] - 5 * scale, center=False, size=10, color=white, time=time, alpha=0.3)

                if self.include_selection:
                    if self.unhide:
                        x_offset += get_text_dimensions(context, "+ Unhiding ", size=10)[0]

                    draw_fading_label(context, text="+ Inclusive", x=self.coords[0] + x_offset, y=self.coords[1] + 5 * scale, center=False, size=10, color=white, time=time, alpha=0.3)



            # ARROW

            draw_fading_label(context, text="🔼", x=self.coords[0] - 70, y=self.coords[1] + 9 * scale, center=False, size=12, color=white, time=time, alpha=0.25)


        # SELECT DOWN

        elif self.direction == 'DOWN':
            ret = self.select_down(context, context.selected_objects, layers)

            # REACHED BOTTOM

            if type(ret) == str:
                if ret == 'BOTTOM':
                    text = ["Reached Bottom of Hierarchy",
                            "with Hidden Children"]

                    y_offset = 36 * scale

                    draw_fading_label(context, text=text, x=self.coords[0], y=self.coords[1] -  y_offset, center=False, size=12, color=[yellow, white], time=time, alpha=0.5)

                # note we offset this one down a litte to ensure it's not drawing on top of the previously drawn, and still fading BOTTOM label, after it was encountered first, and then the op was re-invoked with the unhide option
                elif ret == 'ABSOLUTE_BOTTOM':
                    y_offset = 54 * scale if last_ret == 'BOTTOM' else 18 * scale

                    draw_fading_label(context, text="Reached ABSOLUTE Bottom of Hierarchy", x=self.coords[0], y=self.coords[1] - y_offset, center=False, size=12, color=red, time=time, alpha=1)

                last_ret = ret


            # DOWN SELECTION

            else:
                y_offset = 0 * scale

                draw_fading_label(context, text="Selecting Down", x=self.coords[0], y=self.coords[1], center=False, size=12, color=white, time=time, alpha=0.5)
                x_offset = get_text_dimensions(context, "Selecting Down ", size=12)[0]

                if self.unhide:
                    draw_fading_label(context, text="+ Unhiding ", x=self.coords[0] + x_offset, y=self.coords[1] + 5 * scale, center=False, size=10, color=white, time=time, alpha=0.3)

                if self.recursive_down:
                    draw_fading_label(context, text="+ Recursive ", x=self.coords[0] + x_offset, y=self.coords[1] - 5 * scale, center=False, size=10, color=white, time=time, alpha=0.3)

                if self.include_selection:
                    if self.unhide:
                        x_offset += get_text_dimensions(context, "+ Unhiding ", size=10)[0]

                    draw_fading_label(context, text="+ Inclusive", x=self.coords[0] + x_offset, y=self.coords[1] + 5 * scale, center=False, size=10, color=white, time=time, alpha=0.3)


            # ARROW 

            draw_fading_label(context, text="🔽", x=self.coords[0] - 70, y=self.coords[1] - 9 * scale, center=False, size=12, color=white, time=time, alpha=0.25)


        return {'FINISHED'}


    # UTILS

    def select_up(self, context, objects, layers, debug=False): 
        '''
        based on the current selection select down
        '''

        # debug = True

        parents = set()
        init_selection = set(objects)

        if debug:
            print()
            print("-----")
            print("selected:")

            for obj in init_selection:
                print("", obj.name)

        # get all parent, optionally (by default) recursively
        for obj in init_selection:

            # then collect the parent's  or recursive parentst for actual selection use
            if self.recursive_up:
                parents.update({p for p in get_parent(obj, recursive=True) if p.name in context.view_layer.objects})

            elif obj.parent:
                parents.add(obj.parent)

        # unhide (and ensure objects are in local view)
        if self.unhide:
            ensure_visibility(context, parents, unhide=True)

        # from the set of all parents, get the visible(selectable) ones, then the hidden ones
        visible_parents = set(p for p in parents if p.visible_get())
        hidden_parents = set(parents) - visible_parents

        if debug:
            print()
            print("parents (visible):")

            for obj in visible_parents:
                print("", obj.name)

            print()
            print("parents (hiddden)")

            for obj in hidden_parents:
                print("", obj.name)

        # optionally (by default) deselect the parents (original selection)
        # NOTE: this has to come first, you may reselect some of them as children in the next step, if objects from multiple levels were selected initially
        if not self.include_selection:

            # but only if there actually are visible (selectable) children, otherwise you can end up with nothing seleected, which we want to avoid at all costs
            if visible_parents:
                
                # except when the active is a group empty, and and auto-select is chosen
                # NOTE: if you were to deselect the initial selection now, then you wouldn't be able to detect if you are at the top of the hierarchy
                if (active := context.active_object) and active.M3.is_group_empty and context.scene.M3.group_select:
                    if debug:
                        print("NOTE: Avoiding de-selecting parents, as active is group empty and auto-select is enabled")

                else:
                    for obj in init_selection:
                        obj.select_set(False)

        # then select the visible parents
        for obj in visible_parents:
            obj.select_set(True)

        # get the now selected objects
        new_selection = set(obj for obj in context.selected_objects)

        if debug:
            print()
            print("new selected:")

            for obj in new_selection:
                print("", obj.name)

        # nothing changed, which means we reached the bottom of the hierarchy
        if init_selection == new_selection:
            if hidden_parents:
                return 'TOP'

            else:
                return 'ABSOLUTE_TOP'

        # selection did change, ensure the active object - if there is one initially - that it is now among the top level children
        elif active := context.active_object:

            # find first layer in the view_layer's object hierarchy, where now selected visible children are present, this is out top layer
            for layer in layers:
                if (top_lvl_parents := set(layer) & visible_parents):

                    # NOTE: has to be a separate line, because we alwas want the break once we find top_lvl_parents
                    # while we only want to change the active, if it's not among those already, whic his a separate action
                    if active not in top_lvl_parents:
                        
                        # check if there are group empties, and if so prefer to make a group empty active, instead of a regular object
                        group_empties = [obj for obj in top_lvl_parents if obj.M3.is_group_empty]

                        if group_empties:
                            context.view_layer.objects.active = group_empties[0]
                        else:
                            context.view_layer.objects.active = top_lvl_parents.pop()

                    break

        return True

    def select_down(self, context, objects, layers, debug=False): 
        '''
        based on the current selection select down
        '''
        
        # debug = True

        children = set()
        init_selection = set(objects)

        if debug:
            print()
            print("-----")
            print("selected:")

            for obj in init_selection:
                print("", obj.name)

        # get all children, optionally (by default) recursively, and optionally mod objects too
        for obj in init_selection:

            # then collect the children or recursive children for actual selection use
            if self.recursive_down:
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

        # unhide (and ensure objects are in local view)
        if self.unhide:
            ensure_visibility(context, children, unhide=True)

        # from the set of all children, get the visible(selectable) ones, then the hidden ones, and the top_children, which are just the first level visible children
        visible_children = set(c for c in children if c.visible_get())
        hidden_children = set(children) - visible_children

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
        if not self.include_selection:

            # but only if there actually are visible (selectable) children, otherwise you can end up with nothing seleected, which we want to avoid at all costs
            if visible_children:
                for obj in init_selection:
                    obj.select_set(False)

        # then select the visible children
        for obj in visible_children:
            obj.select_set(True)

        # compare the new selection to the old one
        new_selection = set(obj for obj in context.selected_objects)

        if debug:
            print()
            print("new selected:")

            for obj in new_selection:
                print("", obj.name)

        # nothing changed, which means we reached the bottom of the hierarchy
        if init_selection == new_selection:
            if hidden_children:
                return 'BOTTOM'

            else:
                return 'ABSOLUTE_BOTTOM'

        # selection did change, ensure the active object - if there is one initially - that it is now among the top level children
        elif active := context.active_object:

            # find first layer in the view_layer's object hierarchy, where now selected visible children are present, this is out top layer
            for layer in layers:
                if (top_lvl_children := set(layer) & visible_children):

                    # NOTE: has to be a separate line, because we alwas want the break once we find top_lvl_children
                    # while we only want to change the active, if it's not among those already, which his a separate action
                    if active not in top_lvl_children:
                    
                        # check if there are group empties, and if so prefer to make a group empty active, instead of a regular object
                        group_empties = [obj for obj in top_lvl_children if obj.M3.is_group_empty]

                        if group_empties:
                            context.view_layer.objects.active = group_empties[0]
                        else:
                            context.view_layer.objects.active = top_lvl_children.pop()

                    break

        return True
