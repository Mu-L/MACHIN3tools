import bpy
from bpy.props import FloatProperty, StringProperty, FloatVectorProperty, BoolProperty
from ... utils.draw import draw_label
from ... utils.ui import init_timer_modal, set_countdown, get_timer_progress


class DrawLabel(bpy.types.Operator):
    bl_idname = "machin3.draw_label"
    bl_label = "MACHIN3: Draw Label"
    bl_description = ""
    bl_options = {'INTERNAL'}

    text: StringProperty(name="Text to draw the HUD", default='Text')
    coords: FloatVectorProperty(name='Screen Coordinates', size=2, default=(100, 100))
    center: BoolProperty(name='Center', default=True)
    color: FloatVectorProperty(name='Screen Coordinates', size=3, default=(1, 1, 1))

    time: FloatProperty(name="", default=1, min=0.1)
    alpha: FloatProperty(name="Alpha", default=0.5, min=0.1, max=1)

    cancel: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'VIEW_3D'

    def draw_HUD(self, context):
        try:
            if context.area == self.area:
                alpha = get_timer_progress(self) * self.alpha
                draw_label(context, title=self.text, coords=self.coords, center=self.center, color=self.color, alpha=alpha)

        # NOTE: when the HUD label is still drawing, and a new file is loaded, the operator references gets lost, causing an exception
        # ####: all my attempts to far to then finish the op, or remove the draw handler have failed, so I just silince the error for now
        except ReferenceError:
            pass

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        # finish early if the area is None, this happens when you draw but switch the workspace (via MACHIN3tools worksapce pie only?)
        else:
            self.finish(context)
            return {'FINISHED'}

        # finish early if cancel condition is passed in
        if self.cancel:
            # TODO: no cancel case in MACHIN3tools yet
            pass


        # FINISH when countdown is 0

        if self.countdown < 0:
            self.finish(context)
            return {'FINISHED'}


        # COUNT DOWN

        if event.type == 'TIMER':
            set_countdown(self)

        return {'PASS_THROUGH'}

    def finish(self, context):
        context.window_manager.event_timer_remove(self.TIMER)
        bpy.types.SpaceView3D.draw_handler_remove(self.HUD, 'WINDOW')

    def execute(self, context):

        # initalize time from prefs
        init_timer_modal(self)

        # handlers
        self.area = context.area
        self.HUD = bpy.types.SpaceView3D.draw_handler_add(self.draw_HUD, (context, ), 'WINDOW', 'POST_PIXEL')
        self.TIMER = context.window_manager.event_timer_add(0.1, window=context.window)

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
