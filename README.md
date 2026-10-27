# Blender Action Export To File

Export individual animation actions into separate files.

No object stored, only keyframe data.

## Usage
### Basics

Access export panel in 3D viewport side bar -> Animation -> Export actions to files (.animt)

Select target armature.

Select actions to be exported.

### Tracking shape key keyframes

Shape keys require to be controlled by bone drivers to be included inside actions, animating keyframes on shape keys directly will global and not included in the action.

To export shape key animation, add animated meshes into `Objects for shape key tracking`.

You can exclude driver bone keyframes by adding their names to `Ignore bone frames` list.

### Export process

Set the `Folder` path, all actions will be exported into individual `.animt` files.

`Y axis is up` will reorient the pose for Y up coordinate space.

`Remove unchanged tracks` will remove tracks identical to the rest pose, or mark individual animation channels for removal.

`Export selected actions` will export all enabled actions from the list.

`Export highlighted action` will export only the action highlighted in the action list.

## Importing in engine

Import plugin for Godot engine is available: (link)

Imported files can also be used in other engines, refer to section below on how file structure works.

## File structure
### General

File is formatted in `ini` style.

`frame_start` and `frame_end` (int) is frame range.

`fps` (int) is reference framerate for the animation.

`armature_name` (string) is used for relative path in animation channels.

### Bone frames

`bone_frames` (dictionary) holds all keyframes for bone animation.

It's formated like this: **[**`bone name` (string) , `frames` (dictionary) **[** `frame` (int) , `values` (float array) **] ]**

Value array needs to be converted 4x4 matrix used for transforms.

### Shape key frames

`shape_key_frames` hold all keyframes for shape key animation.

It's formated like this: **[** `mesh object` (string) , `keys` (dictionary) **[** `shape key` (string) , `frames` (dictionary) **[** `frame` (float) , `value` (float) **] ] ]**

### Cleanup data

When `Remove unchanged tracks` is enabled, file might contain data for removing individual channels if entire transform matrix wasn't removed.

Dictionary for `bone name` (string) and `flags` (int) uses bit flags.

Flag `1 << 0` is for `position`, flag `1 << 1` is for `rotation`, flag `1 << 2` is for `scale`. Check using `&` operator.