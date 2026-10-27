bl_info = {
	"name": "Actions To Files Exporter",
	"author": "Rytelier",
	"version": (1, 0, 0),
	"blender": (5, 2, 0),
	"location": "3D View Sidebar > Animation",
	"description": "Exports individual animation actions into .animt files.",
	"category": "Import-Export",
}

import bpy
import mathutils
import math
import bpy_extras
import time
from bpy.props import StringProperty, FloatProperty, BoolProperty
from array import array


## General


def message_box(message = "", title = "Message Box", icon = 'INFO'):
	def draw(self, context):
		self.layout.label(text = message)

	bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


## ACTIONS LIST


class action_item(bpy.types.PropertyGroup):
	name: bpy.props.StringProperty(name = "Action Name")
	enabled: bpy.props.BoolProperty(name = "Enabled", default = False)
	path: bpy.props.StringProperty(name = "Action path")


class AN_UL_action_list_draw(bpy.types.UIList):
	def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
		if self.layout_type in {'DEFAULT', 'COMPACT'}:
			layout.prop(item, "enabled", text = "")
			layout.prop(item, "name", text = "", emboss = False, icon = 'ACTION')


def setup_action_list():
	scene = bpy.context.scene
	list_copy = {}
	if scene.action_list:
		for item in scene.action_list:
			list_copy[item.name] = item.enabled
	scene.action_list.clear()

	existing = []
	
	# Preserve exiting in file
	for item in list_copy.keys():
		for action in bpy.data.actions:
			if item == action.name:
				itemc = scene.action_list.add()
				itemc.name = action.name
				itemc.enabled = list_copy[item]
				itemc.path = action.name

				existing.append(item)

	for action in bpy.data.actions:
		if action.name in existing:
			continue
		item = scene.action_list.add()
		item.name = action.name
		item.enabled = False
		item.path = action.name


class action_list_select(bpy.types.Operator):
	bl_idname = "scene.action_list_select"
	bl_label = "Action list select"
	bl_options = {'INTERNAL'}

	deselect: bpy.props.BoolProperty(name = "Deselect", default = False)

	def execute(self, context):
		for action in context.scene.action_list:
			action.enabled = not (self.deselect == True)
		
		return {'FINISHED'}


class AN_MT_action_options(bpy.types.Menu):
	bl_label = "Options"

	def draw(self, context):
		layout = self.layout

		select = layout.operator("scene.action_list_select", text = "Select all")
		select.deselect = False
		deselect = layout.operator("scene.action_list_select", text = "Select none")
		deselect.deselect = True



## SHAPE KEY TRACKING OBJECTS


def filter_mesh(self, object):
	return object.type == 'MESH'


class shape_object_item(bpy.types.PropertyGroup):
	obj: bpy.props.PointerProperty(type = bpy.types.Object, name = "")


class OBJECT_UL_shape_object_list_draw(bpy.types.UIList):
	def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
		if self.layout_type in {"DEFAULT", "COMPACT"}:
			layout.label(text = item.obj.name, icon = "OUTLINER_OB_MESH")


def add_shape_object(self, context):
	scene = bpy.context.scene
	if not scene.shape_object_picked:
		return

	for item in scene.shape_object_list:
		if item.obj == scene.shape_object_picked:
			scene.shape_object_picked = None
			return

	item = scene.shape_object_list.add()
	item.obj = scene.shape_object_picked
	scene.shape_object_idx = len(scene.shape_object_list) - 1


class OBJECT_OT_shape_object_remove(bpy.types.Operator):
	bl_idname = "object.shape_object_remove"
	bl_label = "Remove object tracked for shape keys"
	bl_options = {'INTERNAL'}

	def execute(self, context):
		scene = context.scene
		idx = scene.shape_object_idx

		if len(scene.shape_object_list) > 0 and 0 <= idx < len(scene.shape_object_list):
			scene.shape_object_list.remove(idx)
			scene.shape_object_idx = max(0, idx - 1)

		return {"FINISHED"}


## BONE IGNORE


class bone_ignore_item(bpy.types.PropertyGroup):
	bone: bpy.props.StringProperty(name = "")


class ARMATURE_UL_bone_ignore_list_draw(bpy.types.UIList):
	def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
		if self.layout_type in {"DEFAULT", "COMPACT"}:
			layout.prop(item, "bone", emboss = False, text = "")


class ARMATURE_OT_bone_ignore_add(bpy.types.Operator):
	bl_idname = "scene.bone_ignore_add"
	bl_label = "Remove bone ignore"
	bl_options = {'INTERNAL'}
	
	def execute(self, context):
		scene = bpy.context.scene

		item = scene.bone_ignore_list.add()
		item.bone = "bone name"

		return {"FINISHED"}


class ARMATURE_OT_bone_ignore_remove(bpy.types.Operator):
	bl_idname = "scene.bone_ignore_remove"
	bl_label = "Add bone ignore"
	bl_options = {'INTERNAL'}

	def execute(self, context):
		scene = context.scene
		idx = scene.bone_ignore_idx

		if len(scene.bone_ignore_list) > 0 and 0 <= idx < len(scene.bone_ignore_list):
			scene.bone_ignore_list.remove(idx)
			scene.bone_ignore_idx = max(0, idx - 1)

		return {"FINISHED"}


## ACTION EXPORT


# File extension
text_ext = "animt"

# Y up conversion matrix
axis_basis_change = mathutils.Matrix((
	(1.0, 0.0, 0.0, 0.0), 
	(0.0, 0.0, 1.0, 0.0), 
	(0.0, -1.0, 0.0, 0.0), 
	(0.0, 0.0, 0.0, 1.0)))


def export_action(action_target: str, folder_path: str):
	scene = bpy.context.scene

	lines: array[str] = []
	map_assigned: bool = False

	armature: bpy.types.Object = scene.armature_target
	children: list[bpy.types.Object] = armature.children_recursive

	for action in bpy.data.actions:
		action: bpy.types.Action
		if action.name != action_target:
			continue

		scene.armature_target.animation_data.action = action

		frame_start: int = round(action.frame_range[0])
		frame_end: int = round(action.frame_range[1])
	
		lines.append(f"[ACTION]")
		lines.append(f'frame_start={frame_start}')
		lines.append(f'frame_end={frame_end}')
		lines.append(f'fps={scene.render.fps}')
		lines.append(f"armature_name=\"{armature.name}\"")

		# Track history for cleanup
		mat_prev: dict[str, mathutils.Matrix] = {}
		mat_difference: dict[str, float] = {}
		mat_first: dict[str, mathutils.Matrix] = {}

		# Code for shape key stuff
		
		tracked_keys: dict[str, array] = {}

		# Gather tracked shape keys
		for item in scene.shape_object_list:
			obj: bpy.types.Object = item.obj
			shape_keys = obj.data.shape_keys
			anim_data = shape_keys.animation_data

			driver_paths = []
			if anim_data and anim_data.drivers:
				driver_paths = [driver.data_path for driver in anim_data.drivers]

			for key in shape_keys.key_blocks:
				target_path = f'key_blocks["{key.name}"].value'

				has_driver = any(target_path in path for path in driver_paths)
				if has_driver:
					if not tracked_keys.get(obj.name, []):
						tracked_keys[obj.name] = [key.name]
					else:
						tracked_keys[obj.name].append(key.name)
		
		# Write frame data

		bone_data: dict = {}  # dict[bone, data[frame, matrix]]
		key_data: dict = {}
		bone_cleanup: dict = {}  #dict[bone, flags]

		# Gather frame data
		for frame in range(frame_start, frame_end + 1):
			scene.frame_set(frame)
			bpy.context.view_layer.update()

			# Gather bone transforms
			for bone in scene.armature_target.pose.bones:
				bone: bpy.types.PoseBone

				ignored = False
				for ignore in scene.bone_ignore_list:
					if bone.name == ignore.bone:
						ignored = True

				if ignored:
					continue

				matrix: mathutils.Matrix = bone.matrix
				if bone.parent:
					matrix = bone.parent.matrix.inverted() @ bone.matrix
				else:
					if scene.yup:
						matrix = axis_basis_change @ bone.matrix  # Apply y up to bone parents
					else:
						matrix = bone.matrix

				values: array[float] = [round(v, 6) for row in matrix for v in row]
				
				if bone_data.get(bone.name) is None:
					bone_data[bone.name] = {}
				bone_data[bone.name][frame] = values
				
				# Track history for cleanup
				if frame == frame_start:
					mat_difference[bone.name] = 0.0
					mat_prev[bone.name] = bone.matrix_basis.copy()
					mat_first[bone.name] = matrix.copy()
				else:
					mat_delta: mathutils.Matrix = bone.matrix_basis - mat_prev[bone.name]
					if not mat_difference[bone.name]:
						mat_difference[bone.name] = [0.0, 0.0, 0.0, 0.0] 
					mat_difference[bone.name][0] += sum(val**2 for row in (mat_delta) for val in row) ** 0.5
					mat_difference[bone.name][1] += (bone.matrix_basis.to_translation() - mat_prev[bone.name].to_translation()).length
					mat_difference[bone.name][2] += bone.matrix_basis.to_quaternion().rotation_difference(mat_prev[bone.name].to_quaternion()).angle
					mat_difference[bone.name][3] += (bone.matrix_basis.to_scale() - mat_prev[bone.name].to_scale()).length
					mat_prev[bone.name] = bone.matrix_basis.copy()

			# Gather shape key values
			for item in scene.shape_object_list:
				obj = item.obj
				for key in tracked_keys.get(obj.name, []):
					shape_key: bpy.types.ShapeKey = obj.data.shape_keys.key_blocks.get(key)
					if shape_key:
						if not key_data.get(obj.name):
							key_data[obj.name] = {}
						if not key_data[obj.name].get(key):
							key_data[obj.name][key] = {}
						key_data[obj.name][key][frame] = shape_key.value


		# Clean up pose unchanged from rest pose
		if scene.cleanup:
			for bone in scene.armature_target.pose.bones:
				if bone.name not in mat_difference.keys():
					continue
				
				rest_matrix = bone.bone.matrix_local
				if bone.bone.parent:
					rest_matrix = bone.bone.parent.matrix_local.inverted() @ rest_matrix
				# Clean up all bone data
				if mat_difference[bone.name][0] <= 0.001 and mat_first[bone.name] == rest_matrix: # Compare to rest pose
						bone_data.pop(bone.name, None)
				else:
					# Clean up individual channels
					if mat_difference[bone.name][1] <= 0.001 and mat_first[bone.name].to_translation() == rest_matrix.to_translation():
						bone_cleanup[bone.name] = bone_cleanup.get(bone.name, 0) | (1 << 0) # Position, flag 0 (1)
					if mat_difference[bone.name][2] <= 0.001 and mat_first[bone.name].to_quaternion() == rest_matrix.to_quaternion():
						bone_cleanup[bone.name] = bone_cleanup.get(bone.name, 0) | (1 << 1) # Rotation, flag 1 (2)
					if mat_difference[bone.name][3] <= 0.001 and mat_first[bone.name].to_scale() == rest_matrix.to_scale():
						bone_cleanup[bone.name] = bone_cleanup.get(bone.name, 0) | (1 << 2) # Scale, flag 2 (4)


		
		line = f"bone_frames={bone_data}"
		if key_data:
			line += f"\nshape_key_frames={key_data}"
		if bone_cleanup:
			line += f"\ncleanup={bone_cleanup}"
		line = line.replace(" ", "")  # Reduce size
		line = line.replace("'", "\"")  # Correct string symbol
		lines.append(line)
		map_assigned = True
	
	if map_assigned:
		full_path = f"{folder_path}{action_target}.{text_ext}"
		try:
			with open(full_path, 'w', encoding='utf-8') as file:
				file.write("\n".join(lines))
			return True
		except Exception as e:
			return False

		return False
	return False


class EXPORT_OT_action_export_anim(bpy.types.Operator):
	"""Export baked animation action to file (.animt)"""
	bl_idname = "export.action_export_anim"
	bl_label = "Export active action to .animt file"

	action_target: bpy.props.StringProperty(name = "action_target")
	
	folder_path: bpy.props.StringProperty(name = "folder_path")
	
	def execute(self, context):
		if context.scene.armature_target is None:
			message_box("Armature target not set", "Error")
			return {'CANCELLED'}
		
		self.report({'INFO'}, f"Exporting {self.action_target} {self.folder_path}")
		exported = export_action(self.action_target, self.folder_path)
		if exported:
			message_box(f"Exported action", "Export .animt file")
			return {'FINISHED'}
		else:
			message_box(f"Didn't export any action", "Export .animt file")
			return {'CANCELLED'}


class EXPORT_OT_action_export_anim_selected(bpy.types.Operator):
	"""Export baked animation actions to files (.animt)"""
	bl_idname = "export.action_export_anim_selected"
	bl_label = "Export selected actions to .animt files"

	folder_path: bpy.props.StringProperty(name = "folder_path")
	
	def execute(self, context):
		if context.scene.armature_target is None:
			message_box("Armature target not set", "Error")
			return {'CANCELLED'}
		
		exported = None
		amount = 0
		for action in context.scene.action_list:
			if action.enabled:
				self.report({'INFO'}, f"Exporting {action.name} {self.folder_path}")
				exported = export_action(action.name, self.folder_path)
				if exported:
					amount += 1
		if amount > 0:
			message_box(f"Exported {amount} actions", "Export .animt files")
			return {'FINISHED'}
		else:
			message_box(f"Didn't export any action", "Export .animt files")
			return {'CANCELLED'}


## PANEL


bpy.types.Scene.export_path = bpy.props.StringProperty(
	name="Export Path",
	subtype='DIR_PATH',
	description="Directory for exported actions"
)


def list_update_handler(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph):
	scene.shape_object_picked = None  # Just abuse it here for shape object picker stay clean

	if not (depsgraph.id_type_updated('ACTION') or depsgraph.id_type_updated('ARMATURE')):
		return
	
	setup_action_list()


def filter_armature(self, object):
	return object.type == 'ARMATURE'


class ACTION_PT_action_anim_export(bpy.types.Panel):
	"""Actions exporter UI"""
	bl_label = "Export actions to files (.animt)"
	bl_idname = "ACTION_PT_action_anim_export"
	bl_space_type = 'VIEW_3D'
	bl_region_type = 'UI'
	bl_category = "Animation"


	def draw(self, context):
		layout = self.layout
		scene = context.scene

		layout.prop_search(context.scene, "armature_target", context.scene, "objects", text = "Target armature")

		# Action list
		row = layout.row()
		row.label(text = "Actions to export")
		row.menu("AN_MT_action_options", icon='DOWNARROW_HLT', text="")

		layout.template_list(
			"AN_UL_action_list_draw", "", 
			scene, "action_list", 
			scene, "action_index",
		)

		# Shape key tracking
		layout.label(text = "Objects for shape key tracking")
		layout.template_list(
			"OBJECT_UL_shape_object_list_draw", "",
			scene, "shape_object_list",
			scene, "shape_object_idx",
		)
		row = layout.row(align = True)
		row.prop_search(context.scene, "shape_object_picked", context.scene, "objects", text = "", icon = "ADD")
		row.operator("object.shape_object_remove", icon = "REMOVE", text="")

		# Bone ignore
		layout.label(text = "Ignore bone frames")
		layout.template_list(
			"ARMATURE_UL_bone_ignore_list_draw", "", 
			scene, "bone_ignore_list", 
			scene, "bone_ignore_idx",
		)
		row = layout.row(align = True)
		row.operator("scene.bone_ignore_add", icon = "ADD", text="")
		row.operator("scene.bone_ignore_remove", icon = "REMOVE", text="")
		
		# Export
		layout.separator(type = "LINE")
		layout.label(text = "Export", icon = "EXPORT")
		layout.prop(scene, "export_path", text = "Folder")
		layout.prop(scene, "yup", text = "Y axis is up")
		layout.prop(scene, "cleanup", text = "Remove unchanged tracks")

		call = layout.operator("export.action_export_anim_selected", text = "Export selected actions", icon = 'EXPORT')
		call.folder_path = scene.export_path

		call2 = layout.operator("export.action_export_anim", text = "Export highlighted action", icon = 'EXPORT')
		if scene.action_index >= 0 and scene.action_index < len(scene.action_list):
			call2.action_target = scene.action_list.values()[scene.action_index].name
		call2.folder_path = scene.export_path


## REGISTER


classes = (
	EXPORT_OT_action_export_anim,
	ACTION_PT_action_anim_export,
	EXPORT_OT_action_export_anim_selected,

	action_item,
	AN_UL_action_list_draw,
	AN_MT_action_options,
	action_list_select,

	shape_object_item,
	OBJECT_OT_shape_object_remove,
	OBJECT_UL_shape_object_list_draw,

	bone_ignore_item,
	ARMATURE_OT_bone_ignore_remove,
	ARMATURE_OT_bone_ignore_add,
	ARMATURE_UL_bone_ignore_list_draw,
)


def register():
	for c in classes:
		bpy.utils.register_class(c)
	
	bpy.types.Scene.action_list = bpy.props.CollectionProperty(type = action_item)
	bpy.types.Scene.action_index = bpy.props.IntProperty(name = "Action Index", default = 0)
	bpy.types.Scene.armature_target = bpy.props.PointerProperty(
		type = bpy.types.Object,
		poll = filter_armature)
	
	bpy.types.Scene.yup = bpy.props.BoolProperty(
		name = "Y up", 
		description = "Y is up coordinate system, necessary for some game engines.",
		default = True)
	bpy.types.Scene.cleanup = bpy.props.BoolProperty(
		name = "Clean up tracks", 
		description = "Remove tracks that are identical with rest pose.", 
		default = True)
	
	bpy.types.Scene.shape_object_picked = bpy.props.PointerProperty(
		type = bpy.types.Object,
		update = add_shape_object,
		poll = filter_mesh,)
	bpy.types.Scene.shape_object_list = bpy.props.CollectionProperty(type = shape_object_item)
	bpy.types.Scene.shape_object_idx = bpy.props.IntProperty(
		name = "Shape key list idx", default = 0)

	bpy.types.Scene.bone_ignore_list = bpy.props.CollectionProperty(type = bone_ignore_item)
	bpy.types.Scene.bone_ignore_idx = bpy.props.IntProperty(
		name = "Bone ignore list idx", default = 0)

	if list_update_handler not in bpy.app.handlers.depsgraph_update_post:
		bpy.app.handlers.depsgraph_update_post.append(list_update_handler)


def unregister():
	for c in classes:
		bpy.utils.unregister_class(c)
	del bpy.types.Scene.action_list
	del bpy.types.Scene.action_index

	del bpy.types.Scene.armature_target

	del bpy.types.Scene.yup
	del bpy.types.Scene.cleanup

	del bpy.types.Scene.shape_object_list
	del bpy.types.Scene.shape_object_idx
	del bpy.types.Scene.shape_object_picked

	del bpy.types.Scene.bone_ignore_list
	del bpy.types.Scene.bone_ignore_idx

	if list_update_handler in bpy.app.handlers.depsgraph_update_post:
		bpy.app.handlers.depsgraph_update_post.remove(list_update_handler)

if __name__ == "__main__":
	register()