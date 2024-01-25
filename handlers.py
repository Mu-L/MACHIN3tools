import bpy
import os
from bpy.app.handlers import persistent
from . utils.application import delay_execution
from . utils.draw import draw_axes_HUD, draw_focus_HUD, draw_surface_slide_HUD, draw_screen_cast_HUD
from . utils.group import select_group_children
from . utils.light import adjust_lights_for_rendering, get_area_light_poll
from . utils.object import get_active_object, get_visible_objects
from . utils.registration import get_prefs, reload_msgbus, get_addon
from . utils.system import get_temp_dir
from . utils.view import sync_light_visibility



# ------------ DEFERRED EXECUTION ---------------

# AXES HUD

axesHUD = None
prev_axes_objects = []

def manage_axes_HUD():
    global axesHUD, prev_axes_objects

    scene = getattr(bpy.context, 'scene', None)

    if scene:

        # if you unregister the addon, the handle will somehow stay arround as a capsule object with the following name
        # despite that, the object will return True, and so we need to check for this or no new handler will be created when re-registering
        if axesHUD and "RNA_HANDLE_REMOVED" in str(axesHUD):
            axesHUD = None

        # axes_objects = [obj for obj in getattr(bpy.context, 'visible_objects', []) if obj.M3.draw_axes]
        axes_objects = [obj for obj in get_visible_objects(bpy.context) if obj.M3.draw_axes]
        active = get_active_object(bpy.context)

        if scene.M3.draw_active_axes and active and active not in axes_objects:
            axes_objects.append(active)

        if scene.M3.draw_cursor_axes:
            axes_objects.append('CURSOR')

        # print()

        if axes_objects:
            # print("axes objects present")

            if axes_objects != prev_axes_objects:
                # print(" axes objects changed")
                prev_axes_objects = axes_objects

                # the objects have changed, remove the previous handler if one exists
                if axesHUD:
                    # print("  removing previous draw handler")
                    bpy.types.SpaceView3D.draw_handler_remove(axesHUD, 'WINDOW')

                # create a new handler
                # print("  adding new draw handler")
                axesHUD = bpy.types.SpaceView3D.draw_handler_add(draw_axes_HUD, (bpy.context, axes_objects), 'WINDOW', 'POST_VIEW')

        # remove the handler when no axes objects are present anymore
        elif axesHUD:
            bpy.types.SpaceView3D.draw_handler_remove(axesHUD, 'WINDOW')
            # print("removing old draw handler")
            axesHUD = None
            prev_axes_objects = []


# FOCUS HUD

focusHUD = None

def manage_focus_HUD():
    global focusHUD

    scene = getattr(bpy.context, 'scene', None)

    if scene:

        # if you unregister the addon, the handle will somehow stay arround as a capsule object with the following name
        # despite that, the object will return True, and so we need to check for this or no new handler will be created when re-registering
        if focusHUD and "RNA_HANDLE_REMOVED" in str(focusHUD):
            focusHUD = None

        history = scene.M3.focus_history

        if history:
            if not focusHUD:
                focusHUD = bpy.types.SpaceView3D.draw_handler_add(draw_focus_HUD, (bpy.context, (1, 1, 1), 1, 2), 'WINDOW', 'POST_PIXEL')

        elif focusHUD:
            bpy.types.SpaceView3D.draw_handler_remove(focusHUD, 'WINDOW')
            focusHUD = None


# SURFACE SLIDE HUD

surfaceslideHUD = None

def manage_surface_slide_HUD():
    global surfaceslideHUD

    # if you unregister the addon, the handle will somehow stay arround as a capsule object with the following name
    # despite that, the object will return True, and so we need to check for this or no new handler will be created when re-registering
    if surfaceslideHUD and "RNA_HANDLE_REMOVED" in str(surfaceslideHUD):
        surfaceslideHUD = None

    active = get_active_object(bpy.context)

    if active:
        surfaceslide = [mod for mod in active.modifiers if mod.type == 'SHRINKWRAP' and 'SurfaceSlide' in mod.name]

        if surfaceslide and not surfaceslideHUD:
            surfaceslideHUD = bpy.types.SpaceView3D.draw_handler_add(draw_surface_slide_HUD, (bpy.context, (0, 1, 0), 1, 2), 'WINDOW', 'POST_PIXEL')

        elif surfaceslideHUD and not surfaceslide:
            bpy.types.SpaceView3D.draw_handler_remove(surfaceslideHUD, 'WINDOW')
            surfaceslideHUD = None


# SCREEN CAST HUD

screencastHUD = None

def manage_screen_cast_HUD():
    global screencastHUD

    wm = bpy.context.window_manager

    # if you unregister the addon, the handle will somehow stay arround as a capsule object with the following name
    # despite that, the object will return True, and so we need to check for this or no new handler will be created when re-registering
    if screencastHUD and "RNA_HANDLE_REMOVED" in str(screencastHUD):
        screencastHUD = None

    # if bpy.context.window_manager.operators and scene.M3.screen_cast:
    if getattr(wm, 'M3_screen_cast', False):
        if not screencastHUD:
            screencastHUD = bpy.types.SpaceView3D.draw_handler_add(draw_screen_cast_HUD, (bpy.context, ), 'WINDOW', 'POST_PIXEL')

    elif screencastHUD:
        bpy.types.SpaceView3D.draw_handler_remove(screencastHUD, 'WINDOW')
        screencastHUD = None


# GROUP

def manage_group():
    context = bpy.context

    scene = getattr(bpy.context, 'scene', None)

    # only actually execute any of the group stuff, if there is a 3d view, since we know that already
    if scene and context.mode == 'OBJECT':
        active = active if (active := get_active_object(context)) and active.M3.is_group_empty and active.select_get() else None


        # AUTO SELECT

        if scene.M3.group_select and active:
            # print(" auto-select")
            select_group_children(context.view_layer, active, recursive=scene.M3.group_recursive_select)


        # STORE USER-SET EMPTY SIZE

        if active:
            # print(" storing user-set empty size")
            # without this you can't actually set a new empty size, because it would be immediately reset to the stored value, if group_hide is enabled
            if round(active.empty_display_size, 4) != 0.0001 and active.empty_display_size != active.M3.group_size:
                active.M3.group_size = active.empty_display_size


        # HIDE / UNHIDE

        if (visible := get_visible_objects(context)) and scene.M3.group_hide:
            # print(" hide/unhide") 

            selected = [obj for obj in visible if obj.M3.is_group_empty and obj.select_get()]
            unselected = [obj for obj in visible if obj.M3.is_group_empty and not obj.select_get()]

            # NOTE: not checking if these props are set already, will cause repeated handler calls, even now that things are executed in a timer

            if selected:
                for group in selected:
                    if not group.show_name:
                        group.show_name = True

                    if group.empty_display_size != group.M3.group_size:
                        group.empty_display_size = group.M3.group_size

            if unselected:
                for group in unselected:
                    if group.show_name:
                        group.show_name = False

                    # store existing non-zero size
                    if round(group.empty_display_size, 4) != 0.0001:
                        group.M3.group_size = group.empty_display_size
                        
                        # then hide the empty, but making it tiny
                        group.empty_display_size = 0.0001


# ASSET DROP

meshmachine = None
decalmachine = None
was_asset_drop_cleanup_executed = False

def manage_asset_drop_cleanup():
    '''
    for some reason this particular function is reliably executed twice
    and while it's generally not a problem, it really not necessary
    so we ensure it's only executed every second time via was_asset_drop_cleanup_executed

    NOTE: this may also be related to other handlers (perhaps in HC) causing a second run, so verify that's not the case
    '''
    
    global was_asset_drop_cleanup_executed

    if was_asset_drop_cleanup_executed:
        was_asset_drop_cleanup_executed = False
        return

    # print(" asset drop cleanup")

    global meshmachine, decalmachine

    if meshmachine is None:
        meshmachine = get_addon('MESHmachine')[0]

    if decalmachine is None:
        decalmachine = get_addon('DECALmachine')[0]

    # print("  meshmachine:", meshmachine)
    # print("  decalmachine:", decalmachine)

    context = bpy.context

    if context.mode == 'OBJECT':

        if meshmachine or decalmachine:
            operators = context.window_manager.operators
            active = active if (active := get_active_object(bpy.context)) and active.type == 'EMPTY' and active.instance_collection and active.instance_type == 'COLLECTION' else None

            if active and operators:
                lastop = operators[-1]

                # unlink MESHmachine stashes and DECALmachine decal backups
                if lastop.bl_idname == 'OBJECT_OT_transform_to_mouse':
                    # print()
                    # print("  asset drop detected!")
                    # start = time.time()

                    visible = get_visible_objects(context)

                    for obj in visible:
                        if meshmachine and obj.MM.isstashobj:
                            # print("   STASH!", obj.name)

                            for col in obj.users_collection:
                                # print(f"    unlinking {obj.name} from {col.name}")
                                col.objects.unlink(obj)

                        if decalmachine and obj.DM.isbackup:
                            # print("   DECAL BACKUP!", obj.name)

                            for col in obj.users_collection:
                                # print(f"    unlinking {obj.name} from {col.name}")
                                col.objects.unlink(obj)

                    # print(f" MACHIN3tools asset drop check done, after {time.time() - start:.20f} seconds")

                was_asset_drop_cleanup_executed = True

            # if lastop.bl_idname == 'OBJECT_OT_drop_named_material':
                # print("material dropped")



# MANAGE LIGHTS

def manage_lights_decrease_and_visibility_sync():
    scene = getattr(bpy.context, 'scene', None)

    if scene:
        m3 = scene.M3
        p = get_prefs()

        if p.activate_render and p.activate_shading_pie and p.render_adjust_lights_on_render and get_area_light_poll() and m3.adjust_lights_on_render:
            if scene.render.engine == 'CYCLES':
                last = m3.adjust_lights_on_render_last
                divider = m3.adjust_lights_on_render_divider

                # decrease on start of rendering
                if last in ['NONE', 'INCREASE'] and divider > 1:
                    # print()
                    # print("decreasing lights for cycles when starting render")

                    m3.adjust_lights_on_render_last = 'DECREASE'
                    m3.is_light_decreased_by_handler = True

                    adjust_lights_for_rendering(mode='DECREASE')

        if p.activate_render and p.render_sync_light_visibility:
            sync_light_visibility(scene)


def manage_lights_increase():
    scene = getattr(bpy.context, 'scene', None)

    if scene:
        m3 = scene.M3
        p = get_prefs()

        if p.activate_render and p.activate_shading_pie and p.render_adjust_lights_on_render and get_area_light_poll() and m3.adjust_lights_on_render:
            if scene.render.engine == 'CYCLES':
                last = m3.adjust_lights_on_render_last

                # increase again when finished
                if last == 'DECREASE' and m3.is_light_decreased_by_handler:
                    # print()
                    # print("increasing lights for cycles when finshing/aborting render")

                    m3.adjust_lights_on_render_last = 'INCREASE'
                    m3.is_light_decreased_by_handler = False

                    adjust_lights_for_rendering(mode='INCREASE')


# SAVE FILE before UNDO

def pre_undo_save():
    debug = False
    debug = True

    scene = getattr(bpy.context, 'scene', None)

    # PRE-UNDO SAVING

    if scene and get_prefs().save_pie_use_undo_save:
        m3 = scene.M3

        if m3.use_undo_save:
            global last_active_operator

            C = bpy.context
            bprefs =  bpy.context.preferences
            
            if debug:
                print()
                print("active operator:", C.active_operator)

            first_redo = False

            # if the active operator has changed, then this it's the first redo (for that op)
            if m3.use_redo_save and C.active_operator:
                if last_active_operator != C.active_operator:
                    last_active_operator = C.active_operator
                    first_redo = True

            if C.active_operator is None or first_redo:
                temp_dir = get_temp_dir(bpy.context)

                if temp_dir:
                    if debug:
                        if first_redo:
                            print("saving before first redo")
                        else:
                            print("saving before undoing")

                        # print(" to temp folder:", temp_dir)

                    # get save path
                    # path = os.path.join(temp_dir, 'undo_save.blend')

                    filepath = bpy.data.filepath
                    # print("filepath:", filepath)

                    if filepath:
                        filename = os.path.basename(filepath)
                    else:
                        filename = "startup.blend"

                    name, ext = os.path.splitext(filename)
                    filepath = os.path.join(temp_dir, name + '_undosave' + ext)

                    if debug: 
                        print(" to temp folder:", filepath)

                    if debug:
                        from time import time
                        start = time()

                    bpy.ops.wm.save_as_mainfile(filepath=filepath, check_existing=True, copy=True, compress=True)

                    if debug:
                        print("time:", time() - start)


# ----------------- HANDLERS --------------------

# LOAD POST HANDLER

@persistent
def load_post(none):
    reload_msgbus()


# DEPSGRAPH UPDATE POST HANDLER

@persistent
def depsgraph_update_post(scene):
    # print()
    # print("dg update post handler")


    # AXES HUD

    delay_execution(manage_axes_HUD)


    # FOCUS HUD

    delay_execution(manage_focus_HUD)


    # SURFACE SLIDE HUD

    delay_execution(manage_surface_slide_HUD)


    # SCREEN CAST HUD

    delay_execution(manage_screen_cast_HUD)


    # GROUP

    delay_execution(manage_group)


    # ASSET DROP CLEANUP

    delay_execution(manage_asset_drop_cleanup)


# RENDER INIT / CANCEL / COMPLETE HANDLERS

@persistent
def render_start(scene):

    # LIGHT DESCREASE + VISIBILITY SYNC on RENDER START

    delay_execution(manage_lights_decrease_and_visibility_sync)


@persistent
def render_end(scene):

    # LIGHT INCREASE on RENDER CANCEL/COMPLETE

    delay_execution(manage_lights_increase)


# PRE-UNDO HANDLER

last_active_operator = None

@persistent
def undo_pre(scene):

    # PRE-UNDO SAVING

    delay_execution(pre_undo_save)
