import bpy
from bpy.types import ThemeDopeSheet
from mathutils import Vector
from . registration import get_addon
from . math import get_sca_matrix
from . mesh import get_bbox


decalmachine = None

def get_last_node(mat):
    if mat.use_nodes:
        tree = mat.node_tree
        output = tree.nodes.get("Material Output")
        if output:
            surf = output.inputs.get("Surface")
            if surf:
                if surf.links:
                    return surf.links[0].from_node


def lighten_color(color, amount):
    def remap(value, new_low):
        old_range = (1 - 0)
        new_range = (1 - new_low)
        return (((value - 0) * new_range) / old_range) + new_low

    return tuple(remap(c, amount) for c in color)


# BEVEL SHADER

def adjust_bevel_shader(context, debug=False):
    '''
    go over all visible objects, to find all materials used by them
    for objects without any material a "white bevel" material is created, if use_bevel_shader is True
    for each of these materiasl try to find a "Bevel" node
        if use_bevel_shader is True, and none can be found check if the last node has a normal input without any links
            if so hook up a new bevel node

    if use_bevel_shader is True
        adjust the sample and radius values according to the m3 props
    if use_bevel_shader is False
        if white bevel material exists
            remove it 
        if it doesn't:
            remove the bevel node in the current mat, if it exists
    '''

    # debug = True

    global decalmachine

    if decalmachine is None:
        decalmachine = get_addon('DECALmachine')[0]

    # import DM dg and tsg fetch functions
    if decalmachine:
        from DECALmachine.utils.material import get_decalgroup_from_decalmat, get_trimsheetgroup_from_trimsheetmat
    else:
        get_decalgroup_from_decalmat = get_trimsheetgroup_from_trimsheetmat = None

    m3 = context.scene.M3

    if debug:
        print("\nadjusting bevel shader")
        print("use bevel:", m3.use_bevel_shader)

    visible_objs = [obj for obj in context.visible_objects if obj.data and getattr(obj.data, 'materials', False) is not False and not any([obj.type == 'GPENCIL', obj.display_type in ['WIRE', 'BOUNDS'], obj.hide_render])]
    # print([obj.name for obj in visible_objs])

    white_bevel = bpy.data.materials.get('white bevel')
    white_bevel_objs = []

    visible_mats = {white_bevel} if white_bevel else set()

    if debug:
        print("white bevel mat:", white_bevel)

    if debug:
        print("\nvisible objects")

    for obj in visible_objs:
        mats = [mat for mat in obj.data.materials if mat]

        # clear material stack if there are only empty slots
        if obj.data.materials and not mats:
            obj.data.materials.clear()

        if debug:
            print(obj.name, [mat.name for mat in mats])

        # create white bevel mat, if it doesnt exist yet, then add it to any object without materials
        if m3.use_bevel_shader and not mats:
            if not white_bevel:
                if debug:
                    print(" creating new white bevel material")

                white_bevel = bpy.data.materials.new('white bevel')
                white_bevel.use_nodes = True

            if debug:
                print(" assigning white bevel material")

            obj.data.materials.append(white_bevel)
            mats.append(white_bevel)

        if obj.data.materials and obj.data.materials[0] == white_bevel:
            white_bevel_objs.append(obj)
        
        # collect all visible materials in a set
        visible_mats.update(mats)
        
        # set dimensions prop
        if m3.use_bevel_shader:

            # for panel decal objects, ensure the radius mod is the same as the parent object's
            if decalmachine and obj.DM.decaltype == 'PANEL' and obj.parent:
                obj.M3.avoid_update = True
                obj.M3.bevel_shader_radius_mod = obj.parent.M3.bevel_shader_radius_mod

            # set dimensions factor based on max dim
            if m3.bevel_shader_use_dimensions:

                # for panel decals use the parent object's dimensions
                if decalmachine and obj.DM.decaltype == 'PANEL' and obj.parent:
                    dimobj = obj.parent

                else:
                    dimobj = obj

                # get dimensions from non-evaluated mesh(as mirror mods massivele change the dims!)
                if dimobj.type == 'MESH':
                    # print(obj.name)
                    
                    # get mesh dimensios as vector
                    dims = Vector(get_bbox(dimobj.data)[2])

                    # get scalemx
                    scalemx = get_sca_matrix(dimobj.matrix_world.to_scale())
                    
                    # get the maxdims by getting the length of the scalemx @ dis vector
                    maxdim = (scalemx @ dims).length
                    # print(maxdim)
                
                # fall back to obj.dims for non-mesh objects
                else:
                    maxdim = max(dimobj.dimensions)

                if debug:
                    print(" setting bevel dimensions to:", maxdim)

                obj.M3.bevel_shader_dimensions_mod = maxdim

            # re-set dimensions factor to 1
            else:
                if debug:
                    print(" re-setting bevel dimensions")

                obj.M3.bevel_shader_dimensions_mod = 1

            # this seems to be required, or toggling m3.bevel_shader_use_dimenions won't update the shader effect, unless you toggle in and out of obect mode
            obj.update_tag()

    # print("\nvisible mats:", [mat.name for mat in visible_mats])

    if debug:
        print("\nvisible materials")

    for mat in visible_mats:
        if debug:
            print()
            print(mat.name)

        tree = mat.node_tree

        bevel = tree.nodes.get('MACHIN3tools Bevel')
        math = tree.nodes.get('MACHIN3tools Bevel Shader Radius Math')
        math2 = tree.nodes.get('MACHIN3tools Bevel Shader Radius Math2')
        global_radius = tree.nodes.get('MACHIN3tools Bevel Shader Global Radius')
        obj_modulation = tree.nodes.get('MACHIN3tools Bevel Shader Object Radius Modulation')
        dim_modulation = tree.nodes.get('MACHIN3tools Bevel Shader Dimensions Radius Modulation')

        if debug:
            print(" bevel:", bevel)
            print(" math:", math)
            print(" math2:", math2)
            print(" global_radius:", global_radius)
            print(" obj_modulation:", obj_modulation)
            print(" dim_modulation:", dim_modulation)

        # try to create bevel node
        if not bevel:
            if debug:
                print()
                print(" no bevel node found")

            last_node = get_last_node(mat)

            if last_node:
                if debug:
                    print("  found last node", last_node.name)

                # BSDF
                if last_node.type == 'BSDF_PRINCIPLED':
                    normal_inputs = [last_node.inputs[name] for name in ['Normal', 'Coat Normal'] if last_node.inputs.get(name) and not last_node.inputs[name].links]

                # decal or trim sheet mats
                elif decalmachine and (mat.DM.isdecalmat or mat.DM.istrimsheetmat):

                    # get decalmat inputs
                    if mat.DM.isdecalmat and mat.DM.decaltype == 'PANEL':
                        normal_inputs = [last_node.inputs[f"{comp} {name}"] for name in ['Normal', 'Coat Normal'] for comp in ['Material', 'Material 2', 'Subset'] if last_node.inputs.get(f"{comp} {name}")]

                    # get trimsheetmat inputs
                    elif mat.DM.istrimsheetmat:
                        normal_inputs = [last_node.inputs[name] for name in ['Normal', 'Coat Normal'] if last_node.inputs.get(name)]

                    # non-panel decals, ignore
                    else:
                        continue

                # fallback to any other node or node group
                else:
                    normal_inputs = [last_node.inputs[name] for name in ['Normal', 'Coat Normal'] if last_node.inputs.get(name) and not last_node.inputs[name].links]

                if normal_inputs:
                    if debug:
                        print("   has a normal input without links, creating bevel node")


                    # CREATE BEVEL NODE SETUP, return bevel and global_radius nodes

                    bevel, global_radius = create_and_connect_bevel_shader_setup(mat, last_node, normal_inputs, math, math2, global_radius, obj_modulation, dim_modulation, decalmachine=decalmachine, debug=debug)

                # couldn't find a normal input, moving on to the next material
                else:
                    continue

            # couldn't find last node, moving on to the next material
            else:
                continue

        # set bevel node props
        if m3.use_bevel_shader:
            samples = bevel.samples
            radius = global_radius.outputs[0].default_value

            if samples != m3.bevel_shader_samples:
                if debug:
                    print(" setting bevel samples to:", m3.bevel_shader_samples)

                bevel.samples = m3.bevel_shader_samples

            if radius != m3.bevel_shader_radius:
                if debug:
                    print(" setting bevel radius to:", m3.bevel_shader_radius)
                
                # set the radius on the bevel node itself, even if it's overwritten by the input from the math node
                bevel.inputs[0].default_value = m3.bevel_shader_radius

                # then set it on the global radius value node
                global_radius.outputs[0].default_value = m3.bevel_shader_radius


        # REMOVE BEVEL NODE and WHITE BEVEL MAT mat

        else:

            # REMOVE WHITE BEVEL MATERIAL

            if mat == white_bevel:
                if debug:
                    print(" removing white bevel material")

                bpy.data.materials.remove(mat, do_unlink=True)
                
                for obj in white_bevel_objs:
                    obj.data.materials.clear()

                    if debug:
                        print("  clearing material slots on", obj.name)


            # REMOVE BEVEL NODE SETUP

            else:
                remove_bevel_shader_setup(mat, bevel, math, math2, global_radius, obj_modulation, dim_modulation, decalmachine, get_decalgroup_from_decalmat, get_trimsheetgroup_from_trimsheetmat, debug)


def create_and_connect_bevel_shader_setup(mat, last_node, normal_inputs, math=None, math2=None, global_radius=None, obj_modulation=None, dim_modulation=None, decalmachine=False, debug=False):
    '''
    create the complete MACHIN3tools bevel shader setup
        create any nodes that aren't passed in
        and connect them to each other
    return bevel and global_radius nodes
    '''

    tree = mat.node_tree
    
    bevel = tree.nodes.new('ShaderNodeBevel')
    bevel.name = "MACHIN3tools Bevel"
    bevel.location.x = last_node.location.x - 250

    # for a newly created bevel mat (but also in some other cases?), blender will return dimensions of 0 for the principled shader (or the decal node group) for some reason, so correct for that
    y_dim = last_node.dimensions.y

    if y_dim == 0:
        y_dim = 660

        if 'trimsheet' in last_node.name:
            print("hello", mat.name)

        if decalmachine:
            if mat.DM.isdecalmat:
                if mat.DM.decaltype == 'PANEL':
                    y_dim = 963

    # always push bevel node down a little for trimsheet mats, otherwise they overlap with texture nodes
    if decalmachine and mat.DM.istrimsheetmat:
        y_dim += 200


    bevel.location.y = last_node.location.y - y_dim + bevel.height

    # link it to the normal inputs
    for i in normal_inputs:
        tree.links.new(bevel.outputs[0], i)

    # create first math node
    if not math:
        if debug:
            print("   creating multiply node")

        math = tree.nodes.new('ShaderNodeMath')
        math.name = "MACHIN3tools Bevel Shader Radius Math"
        math.operation = 'MULTIPLY'

        math.location = bevel.location
        math.location.x = bevel.location.x - 200

        tree.links.new(math.outputs[0], bevel.inputs[0])

    # create second math node
    if not math2:
        if debug:
            print("   creating 2nd multiply node")

        math2 = tree.nodes.new('ShaderNodeMath')
        math2.name = "MACHIN3tools Bevel Shader Radius Math2"
        math2.operation = 'MULTIPLY'

        math2.location = math.location
        math2.location.x = math.location.x - 200

        tree.links.new(math2.outputs[0], math.inputs[0])

    # create global radius value node
    if not global_radius:
        if debug:
            print("   creating global radius node")

        global_radius = tree.nodes.new('ShaderNodeValue')
        global_radius.name = "MACHIN3tools Bevel Shader Global Radius"
        global_radius.label = "Global Radius"

        global_radius.location = math2.location
        global_radius.location.x = math2.location.x - 200
        global_radius.location.y = math2.location.y

        tree.links.new(global_radius.outputs[0], math2.inputs[0])
    
    # create per-object radius modulation node
    if not obj_modulation:
        if debug:
            print("   creating obj modulation node")

        obj_modulation = tree.nodes.new('ShaderNodeAttribute')
        obj_modulation.name = "MACHIN3tools Bevel Shader Object Radius Modulation"
        obj_modulation.label = "Obj Radius Modulation"

        obj_modulation.attribute_type = 'OBJECT'
        obj_modulation.attribute_name = 'M3.bevel_shader_radius_mod'

        obj_modulation.location = global_radius.location
        obj_modulation.location.y = global_radius.location.y - 100

        tree.links.new(obj_modulation.outputs[2], math2.inputs[1])

    # create obj-dimensions radius modulation node
    if not dim_modulation:
        if debug:
            print("   creating dimensions modulation node")

        dim_modulation = tree.nodes.new('ShaderNodeAttribute')
        dim_modulation.name = "MACHIN3tools Bevel Shader Dimensions Radius Modulation"
        dim_modulation.label = "Dimensions Radius Modulation"

        dim_modulation.attribute_type = 'OBJECT'
        dim_modulation.attribute_name = 'M3.bevel_shader_dimensions_mod'

        dim_modulation.location = math2.location
        dim_modulation.location.y = math2.location.y - 175

        tree.links.new(dim_modulation.outputs[2], math.inputs[1])

    return bevel, global_radius


def remove_bevel_shader_setup(mat, bevel=None, math=None, math2=None, global_radius=None, obj_modulation=None, dim_modulation=None, decalmachine=False, get_decalgroup_from_decalmat=None, get_trimsheetgroup_from_trimsheetmat=None, debug=False):
    '''
    remove all the passed in bevel shader nodes
    for decals also re-connect the detail and tiling normal nodes
    '''

    tree = mat.node_tree

    if bevel:
        if debug:
            print(" removing bevel node")

        tree.nodes.remove(bevel)

    if math:
        if debug:
            print(" removing math node")

        tree.nodes.remove(math)

    if math2:
        if debug:
            print(" removing math2 node")

        tree.nodes.remove(math2)

    if global_radius:
        if debug:
            print(" removing global radius node")

        tree.nodes.remove(global_radius)

    if obj_modulation:
        if debug:
            print(" removing obj modulation node")

        tree.nodes.remove(obj_modulation)

    if dim_modulation:
        if debug:
            print(" removing dim modulation node")

        tree.nodes.remove(dim_modulation)

    # for decals re-connect the detail or tiling normal nodes 
    if decalmachine and (mat.DM.isdecalmat or mat.DM.istrimsheetmat):

        # get decal group (for panel decals)
        if mat.DM.isdecalmat and mat.DM.decaltype == 'PANEL':
            detail_normal = tree.nodes.get('Detail Normal')
            dg = get_decalgroup_from_decalmat(mat)

            if detail_normal and dg:
                normal_inputs = [dg.inputs[f"{comp} Normal"] for comp in ['Material', 'Material 2', 'Subset']]

                for i in normal_inputs:
                    tree.links.new(detail_normal.outputs[0], i)

        # get trimsheet group for sheet mats
        elif mat.DM.istrimsheetmat:
            tiling_normal = tree.nodes.get('Tiling Normal')
            tsg = get_trimsheetgroup_from_trimsheetmat(mat)

            if tiling_normal and tsg:
                normal_inputs = [tsg.inputs[name] for name in ['Normal']]

                for i in normal_inputs:
                    tree.links.new(tiling_normal.outputs[0], i)

        # ignore non-panel decals (for now)
        else:
            pass
