from typing import Union
import bpy
import bmesh
from mathutils import Matrix, Vector
from . math import flatten_matrix


def parent(obj, parentobj):
    if obj.parent:
        unparent(obj)

    obj.parent = parentobj
    obj.matrix_parent_inverse = parentobj.matrix_world.inverted_safe()


def unparent(obj):
    if obj.parent:
        omx = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = omx


def unparent_children(obj):
    children = []

    for c in obj.children:
        unparent(c)
        children.append(c)

    return children


def compensate_children(obj, oldmx, newmx):
    '''
    compensate object's childen, for instance, if obj's world matrix is about to be changed and "affect parents only" is enabled
    '''

    # the delta matrix, aka the old mx expressed in the new one's local space
    deltamx = newmx.inverted_safe() @ oldmx
    children = [c for c in obj.children]

    for c in children:
        pmx = c.matrix_parent_inverse
        c.matrix_parent_inverse = deltamx @ pmx


def flatten(obj, depsgraph=None):
    if not depsgraph:
        depsgraph = bpy.context.evaluated_depsgraph_get()

    oldmesh = obj.data

    obj.data = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    obj.modifiers.clear()

    # remove the old mesh
    bpy.data.meshes.remove(oldmesh, do_unlink=True)


def add_vgroup(obj, name="", ids=[], weight=1, debug=False):
    vgroup = obj.vertex_groups.new(name=name)

    if debug:
        print(" » Created new vertex group: %s" % (name))

    if ids:
        vgroup.add(ids, weight, "ADD")

    # from selection
    else:
        obj.vertex_groups.active_index = vgroup.index
        bpy.ops.object.vertex_group_assign()

    return vgroup


def add_facemap(obj, name="", ids=[]):
    fmap = obj.face_maps.new(name=name)

    if ids:
        fmap.add(ids)

    return fmap


def set_obj_origin(obj, mx, bm=None, decalmachine=False, meshmachine=False):
    '''
    change object origin to supplied matrix, support doing it in edit mode when bmesh is passed in
    also update decal backups and stashes if decalmachine or meshmachine are True
    '''

    # pre-origin adjusted object matrix
    omx = obj.matrix_world.copy()

    # get children and compensate for the parent transform
    children = [c for c in obj.children]
    compensate_children(obj, omx, mx)

    # object mx expressed in new mx's local space, this is the "difference matrix" representing the origin change
    deltamx = mx.inverted_safe() @ obj.matrix_world

    obj.matrix_world = mx

    if bm:
        bmesh.ops.transform(bm, verts=bm.verts, matrix=deltamx)
        bmesh.update_edit_mesh(obj.data)
    else:
        obj.data.transform(deltamx)

    if obj.type == 'MESH':
        obj.data.update()

    # the decal origin needs to be chanegd too and the backupmx needs to be compensated for the change in parent object origin
    if decalmachine and children:

        # decal backup's backup matrices, but only for projected/sliced decals!
        for c in [c for c in children if c.DM.isdecal and c.DM.decalbackup]:
            backup = c.DM.decalbackup
            backup.DM.backupmx = flatten_matrix(deltamx @ backup.DM.backupmx)

    # adjust stashes and stash matrices
    if meshmachine:

        # the following originally immitated stash retrieval and then re-creation, it just chained both events together. this could then be simplifed further and further. setting stash.obj.matrix_world is optional
        for stash in obj.MM.stashes:

            # MEShmachine 0.7 uses a delta and orphan matrix
            if getattr(stash, 'version', False) and float('.'.join([v for v in stash.version.split('.')[:2]])) >= 0.7:
                stashdeltamx = stash.obj.MM.stashdeltamx

                # duplicate "instanced" stash objs, to prevent offsetting stashes on object's whose origin is not changed
                # NOTE: it seems this is only required for self stashes for some reason
                if stash.self_stash:
                    if stash.obj.users > 2:
                        print(f"INFO: Duplicating {stash.name}'s stashobj {stash.obj.name} as it's used by multiple stashes")

                        dup = stash.obj.copy()
                        dup.data = stash.obj.data.copy()
                        stash.obj = dup

                stash.obj.MM.stashdeltamx = flatten_matrix(deltamx @ stashdeltamx)
                stash.obj.MM.stashorphanmx = flatten_matrix(mx)

                # for self stashes, cange the stash obj origin in the same way as it was chaged for the main object
                # NOTE: this seems to work, it properly changes the origin of the stash object in the same way
                # ####: however the stash is drawn in and retrieved in the wrong location, in the pre-origin change location
                # ####: you can then align it properly, but why would it not be drawing and retrieved properly??

                # if stash.self_stash:
                    # stash.obj.matrix_world = mx
                    # stash.obj.data.transform(deltamx)
                    # stash.obj.data.update()

                # just disable self_stashes until you get this sorted
                stash.self_stash = False

            # older versions use the stashmx and targetmx
            else:
                # stashmx in stashtargetmx's local space, aka the stash difference matrix(which is all that's actually needed for stashes, just like for decal backups)
                stashdeltamx = stash.obj.MM.stashtargetmx.inverted_safe() @ stash.obj.MM.stashmx

                stash.obj.MM.stashmx = flatten_matrix(omx @ stashdeltamx)
                stash.obj.MM.stashtargetmx = flatten_matrix(mx)

            stash.obj.data.transform(deltamx)
            stash.obj.matrix_world = mx


def get_eval_bbox(obj):
    return [Vector(co) for co in obj.bound_box]


def get_active_object(context) -> Union[bpy.types.Object, None]:
    '''
    is this a safer way to fetch the active object, especially for use in handlers?

    see https://blenderartists.org/t/hard-crash-with-archipack/1501772
    but also avoid AttributeError: 'Context' object has no attribute 'active_object'
    '''
    
    objects = getattr(context.view_layer, 'objects', None)

    if objects:
        return getattr(objects, 'active', None)


def get_selected_objects(context) -> list[bpy.types.Object]:
    '''
    is this a safer way to fetch the selected objects, especially for use in handlers?
    '''

    objects = getattr(context.view_layer, 'objects', None)

    if objects:
        return getattr(objects, 'selected', [])

    return []


def get_visible_objects(context, local_view=False) -> list[bpy.types.Object]:
    '''
    is this a safer way to fetch the visible objects, especially for use in handlers?

    NOTE: the "if obj" check in the return statement is done to avoid this weird issue, which happens in an empty scene
        return [obj for obj in objects if obj.visible_get(view_layer=view_layer)]
        AttributeError: 'NoneType' object has no attribute 'visible_get'
    interesting printing objects before that reveals an empty list/generator and no None objects in it

    TODO: local_view support, but note that it wont work in a handler, as context.space_data won't exist
    '''

    view_layer = context.view_layer
    objects = getattr(view_layer, 'objects', None)
    
    if objects:
        return [obj for obj in objects if obj and obj.visible_get(view_layer=view_layer)]
    return []


def get_object_hierarchy_layers(context, debug=False):
    '''
    go through all objects of the view_layer, and sort them into hierarchicaly layers, creating a list of lists
    '''

    def add_layer(layers, depth, debug=False):
        '''
        for each object in the last object layer, fetch the children, and create a new layer from them
        do it recursively
        '''
        
        if debug:
            print()
            print("layer", depth)

        children = []

        for obj in layers[-1]:
            if debug:
                print("", obj.name)

            for obj in obj.children:
                children.append(obj)

        if children:
            depth += 1

            layers.append(children)

            add_layer(layers, depth=depth, debug=debug)

    depth = 0

    # start by fetching the objects at the very top, which are those without any parent
    top_level_objects = [obj for obj in context.view_layer.objects if not obj.parent]

    # initiate the list of lists, with the first top level layer
    layers = [top_level_objects]

    # add addiational layers, recursively for as long as there are children
    add_layer(layers, depth, debug=debug)

    return layers


def get_parent(obj, recursive=False, debug=False):
    '''
    get parent of the pasted in object
    optionally recusrively, in which case we return a list instead of a single object
    '''

    if recursive:
        parents = []

        while obj.parent:
            parents.append(obj.parent)
            obj = obj.parent

        return parents

    else:
        return obj.parent
