import bpy
import os
from bpy.app.handlers import persistent
from time import time
from . utils.application import delay_execution
from . utils.draw import draw_axes_HUD, draw_focus_HUD, draw_surface_slide_HUD, draw_screen_cast_HUD
from . utils.group import select_group_children
from . utils.light import adjust_lights_for_rendering, get_area_light_poll
from . utils.object import get_active_object, get_visible_objects
from . utils.registration import get_prefs, reload_msgbus, get_addon
from . utils.system import get_temp_dir
from . utils.view import sync_light_visibility

global_debug = False
# global_debug = True


# ------------ DEFERRED EXECUTION ---------------

# AXES HUD

axesHUD = None
prev_axes_objects = []

def manage_axes_HUD():
    global global_debug, axesHUD, prev_axes_objects

    debug = global_debug
    debug = False

    scene = getattr(bpy.context, 'scene', None)

    if scene:

        if debug:
            print("  axes HUD")

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

        if axes_objects:
            if debug:
                print("   axes objects present:", [obj if obj == 'CURSOR' else obj.name for obj in axes_objects])

            if axes_objects != prev_axes_objects:
                if debug:
                    print("   axes objects changed")

                prev_axes_objects = axes_objects

                # the objects have changed, remove the previous handler if one exists
                if axesHUD:
                    if debug:
                        print("   removing previous draw handler")

                    bpy.types.SpaceView3D.draw_handler_remove(axesHUD, 'WINDOW')

                # create a new handler

                if debug:
                    print("   adding new draw handler")
                axesHUD = bpy.types.SpaceView3D.draw_handler_add(draw_axes_HUD, (bpy.context, axes_objects), 'WINDOW', 'POST_VIEW')

        # remove the handler when no axes objects are present anymore
        elif axesHUD:
            bpy.types.SpaceView3D.draw_handler_remove(axesHUD, 'WINDOW')

            if debug:
                print("   removing old draw handler")

            axesHUD = None
            prev_axes_objects = []


# FOCUS HUD

focusHUD = None

def manage_focus_HUD():
    global global_debug, focusHUD

    debug = global_debug
    debug = False

    scene = getattr(bpy.context, 'scene', None)

    if scene:

        if debug:
            print("  focus HUD")

        # if you unregister the addon, the handle will somehow stay arround as a capsule object with the following name
        # despite that, the object will return True, and so we need to check for this or no new handler will be created when re-registering
        if focusHUD and "RNA_HANDLE_REMOVED" in str(focusHUD):
            focusHUD = None

        history = scene.M3.focus_history

        if history:
            if not focusHUD:
                if debug:
                    print("   adding new draw handler")

                focusHUD = bpy.types.SpaceView3D.draw_handler_add(draw_focus_HUD, (bpy.context, (1, 1, 1), 1, 2), 'WINDOW', 'POST_PIXEL')

        elif focusHUD:
            if debug:
                print("   removing old draw handler")

            bpy.types.SpaceView3D.draw_handler_remove(focusHUD, 'WINDOW')
            focusHUD = None


# SURFACE SLIDE HUD

surfaceslideHUD = None

def manage_surface_slide_HUD():
    global global_debug, surfaceslideHUD

    debug = global_debug
    debug = False

    if debug:
        print("  surface slide HUD")

    # if you unregister the addon, the handle will somehow stay arround as a capsule object with the following name
    # despite that, the object will return True, and so we need to check for this or no new handler will be created when re-registering
    if surfaceslideHUD and "RNA_HANDLE_REMOVED" in str(surfaceslideHUD):
        surfaceslideHUD = None

    active = get_active_object(bpy.context)

    if active:
        surfaceslide = [mod for mod in active.modifiers if mod.type == 'SHRINKWRAP' and 'SurfaceSlide' in mod.name]

        if surfaceslide and not surfaceslideHUD:
            if debug:
                print("   adding new draw handler")

            surfaceslideHUD = bpy.types.SpaceView3D.draw_handler_add(draw_surface_slide_HUD, (bpy.context, (0, 1, 0), 1, 2), 'WINDOW', 'POST_PIXEL')

        elif surfaceslideHUD and not surfaceslide:
            if debug:
                print("   removing old draw handler")

            bpy.types.SpaceView3D.draw_handler_remove(surfaceslideHUD, 'WINDOW')
            surfaceslideHUD = None


# SCREEN CAST HUD

screencastHUD = None

def manage_screen_cast_HUD():
    global global_debug, screencastHUD

    debug = global_debug
    debug = False

    if debug:
        print("  screen cast HUD")

    wm = bpy.context.window_manager

    # if you unregister the addon, the handle will somehow stay arround as a capsule object with the following name
    # despite that, the object will return True, and so we need to check for this or no new handler will be created when re-registering
    if screencastHUD and "RNA_HANDLE_REMOVED" in str(screencastHUD):
        screencastHUD = None

    # if bpy.context.window_manager.operators and scene.M3.screen_cast:
    if getattr(wm, 'M3_screen_cast', False):
        if not screencastHUD:
            if debug:
                print("   adding new draw handler")

            screencastHUD = bpy.types.SpaceView3D.draw_handler_add(draw_screen_cast_HUD, (bpy.context, ), 'WINDOW', 'POST_PIXEL')

    elif screencastHUD:
        if debug:
            print("   removing old draw handler")

        bpy.types.SpaceView3D.draw_handler_remove(screencastHUD, 'WINDOW')
        screencastHUD = None


# GROUP

def manage_group():
    global global_debug

    debug = global_debug
    debug = False

    if debug:
        print("  group management")

    C = bpy.context
    scene = getattr(C, 'scene', None)
    m3 = scene.M3

    # only actually execute any of the group stuff, if there is a 3d view, since we know that already
    if scene and C.mode == 'OBJECT':
        active = active if (active := get_active_object(C)) and active.M3.is_group_empty and active.select_get() else None


        # AUTO SELECT

        if m3.group_select and active:
            if debug:
                print("   auto-selecting")

            select_group_children(C.view_layer, active, recursive=m3.group_recursive_select)


        # STORE USER-SET EMPTY SIZE

        if active:
            if debug:
                print("   storing user-set empty size")

            # without this you can't actually set a new empty size, because it would be immediately reset to the stored value, if group_hide is enabled
            if round(active.empty_display_size, 4) != 0.0001 and active.empty_display_size != active.M3.group_size:
                active.M3.group_size = active.empty_display_size


        # HIDE / UNHIDE

        if (visible := get_visible_objects(C)) and m3.group_hide:
            if debug:
                print("   hiding/unhiding") 

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
    
    global global_debug, was_asset_drop_cleanup_executed

    debug = global_debug
    debug = False

    if debug:
        print("  M3 asset drop management")

    if was_asset_drop_cleanup_executed:
        if debug:
            print("   skipping second (duplicate) run")

        was_asset_drop_cleanup_executed = False
        return

    if debug:
        print("   checking for asset drop cleanup")

    global meshmachine, decalmachine

    if meshmachine is None:
        meshmachine = get_addon('MESHmachine')[0]

        # check if the installed MESHmachine has the asset droper itself already
        if meshmachine:
            import MESHmachine

            if 'manage_asset_drop_cleanup' in dir(MESHmachine.handlers):
                meshmachine = False

                if debug:
                    print("    the installed MESHmachine already manages the asset drop itself, setting MM to False")

    if decalmachine is None:
        decalmachine = get_addon('DECALmachine')[0]

        # check if the installed DECALmachine has the asset droper itself already
        if decalmachine:
            import DECALmachine

            if 'manage_asset_drop_cleanup' in dir(DECALmachine.handlers):
                decalmachine = False

                if debug:
                    print("    the installed DECALmachine already manages the asset drop itself, setting MM to False")

    if debug:
        print("    meshmachine:", meshmachine)
        print("    decalmachine:", decalmachine)

    C = bpy.context

    if C.mode == 'OBJECT' and (meshmachine or decalmachine):
        operators = C.window_manager.operators
        active = active if (active := get_active_object(C)) and active.type == 'EMPTY' and active.instance_collection and active.instance_type == 'COLLECTION' else None

        if active and operators:
            lastop = operators[-1]

            # unlink MESHmachine stashes and DECALmachine decal backups
            if lastop.bl_idname == 'OBJECT_OT_transform_to_mouse':
                if debug:
                    print()
                    print("    asset drop detected!")

                # start = time.time()

                visible = get_visible_objects(C)

                for obj in visible:
                    if meshmachine and obj.MM.isstashobj:
                        if debug:
                            print("     stash object:", obj.name)

                        for col in obj.users_collection:
                            if debug:
                                print(f"      unlinking from {col.name}")

                            col.objects.unlink(obj)

                    if decalmachine and obj.DM.isbackup:
                        if debug:
                            print("     decal backup object:", obj.name)

                        for col in obj.users_collection:
                            if debug:
                                print(f"      unlinking from {col.name}")

                            col.objects.unlink(obj)

                # print(f" MACHIN3tools asset drop check done, after {time.time() - start:.20f} seconds")

            was_asset_drop_cleanup_executed = True

        # if lastop.bl_idname == 'OBJECT_OT_drop_named_material':
            # print("material dropped")


# MANAGE LIGHTS

def manage_lights_decrease_and_visibility_sync():
    global global_debug

    debug = global_debug
    debug = False

    if debug:
        print("  light descrease and visiblity sync")

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
                    if debug:
                        print("   decreasing lights for cycles when starting render")

                    m3.adjust_lights_on_render_last = 'DECREASE'
                    m3.is_light_decreased_by_handler = True

                    adjust_lights_for_rendering(mode='DECREASE', debug=debug)

        if p.activate_render and p.render_sync_light_visibility:
            if debug:
                print("   light visibility syncing")

            sync_light_visibility(scene)


def manage_lights_increase():
    global global_debug
    
    debug = global_debug
    debug = False

    if debug:
        print("  light increase")

    scene = getattr(bpy.context, 'scene', None)

    if scene:
        m3 = scene.M3
        p = get_prefs()

        if p.activate_render and p.activate_shading_pie and p.render_adjust_lights_on_render and get_area_light_poll() and m3.adjust_lights_on_render:
            if scene.render.engine == 'CYCLES':
                last = m3.adjust_lights_on_render_last

                # increase again when finished
                if last == 'DECREASE' and m3.is_light_decreased_by_handler:
                    if debug:
                        print("   increasing lights for cycles when finshing/aborting render")

                    m3.adjust_lights_on_render_last = 'INCREASE'
                    m3.is_light_decreased_by_handler = False

                    adjust_lights_for_rendering(mode='INCREASE', debug=debug)


# SAVE FILE before UNDO

def pre_undo_save():
    global global_debug

    debug = global_debug
    debug = False

    if debug:
        print("  undo save")

    scene = getattr(bpy.context, 'scene', None)

    # PRE-UNDO SAVING

    if scene:
        m3 = scene.M3

        if m3.use_undo_save:
            global last_active_operator

            C = bpy.context
            bprefs =  bpy.context.preferences
            
            if debug:
                print("   active operator:", C.active_operator)

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
                            print("    saving before first redo")
                        else:
                            print("    saving before undoing")

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
                        print("     to temp folder:", filepath)

                    if debug:
                        start = time()

                    bpy.ops.wm.save_as_mainfile(filepath=filepath, check_existing=True, copy=True, compress=True)

                    if debug:
                        print("     save time:", time() - start)


# ----------------- HANDLERS --------------------

# LOAD POST HANDLER

@persistent
def load_post(none):
    global global_debug

    # MSGBUS

    if global_debug:
        print()
        print("MACHIN3tools load post handler:")
        print(" reloading msgbus")

    reload_msgbus()


# DEPSGRAPH UPDATE POST HANDLER

@persistent
def depsgraph_update_post(scene):
    global global_debug

    if global_debug:
        print()
        print("MACHIN3tools depsgraph update post handler:")

    p = get_prefs()


    # AXES HUD

    if p.activate_shading_pie:
        if global_debug:
            print(" managing axes HUD")

        delay_execution(manage_axes_HUD)


    # FOCUS HUD

    if p.activate_focus:
        if global_debug:
            print(" managing focus HUD")

        delay_execution(manage_focus_HUD)


    # SURFACE SLIDE HUD

    if p.activate_surface_slide:
        if global_debug:
            print(" managing surface slide HUD")

        delay_execution(manage_surface_slide_HUD)


    # SCREEN CAST HUD

    if p.activate_save_pie and p.show_screencast:
        if global_debug:
            print(" managing screen cast HUD")

        delay_execution(manage_screen_cast_HUD)


    # GROUP

    if p.activate_group:
        if global_debug:
            print(" managing group")

        delay_execution(manage_group)


    # ASSET DROP CLEANUP

    if global_debug:
        print(" managing asset drop")

    delay_execution(manage_asset_drop_cleanup)


# RENDER INIT / CANCEL / COMPLETE HANDLERS

@persistent
def render_start(scene):
    global global_debug

    if global_debug:
        print()
        print("MACHIN3tools render start handler:")

    p = get_prefs()

    # LIGHT DESCREASE + VISIBILITY SYNC on RENDER START

    if p.activate_render and (p.render_adjust_lights_on_render or p.render_enforce_hide_render):
        if global_debug:
            print(" managing light decrease and light visibility sync")

        delay_execution(manage_lights_decrease_and_visibility_sync)


@persistent
def render_end(scene):
    global global_debug

    if global_debug:
        print()
        print("MACHIN3tools render cancel or complete handler:")

    p = get_prefs()

    # LIGHT INCREASE on RENDER CANCEL/COMPLETE

    if p.activate_render and p.render_adjust_lights_on_render:
        if global_debug:
            print(" managing light increase")

        delay_execution(manage_lights_increase)


# PRE-UNDO HANDLER

last_active_operator = None

@persistent
def undo_pre(scene):
    global global_debug

    if global_debug:
        print()
        print("MACHIN3tools undo pre handler:")

    p = get_prefs()

    # PRE-UNDO SAVING

    if p.activate_save_pie and p.save_pie_use_undo_save:
        if global_debug:
            print(" managing pre undo save")

        delay_execution(pre_undo_save)
