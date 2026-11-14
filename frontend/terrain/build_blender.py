"""Relief USGS neschimbat; exagerarea verticala este exclusiv de prezentare."""
import bpy, json, os, math, sys
sys.path.insert(0, os.path.join(os.getcwd(), 'terrain'))
from materials import terrain_material
from mathutils import Vector
root = os.getcwd()
with open(os.path.join(root, 'public/terrain/jezero.json')) as f:
    data = json.load(f)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
rows, cols, cell = data['rows'], data['cols'], data['cell_size_m']
VERTICAL_SCALE = 6.0
BASE_THICKNESS = 850.0
PLINTH_DEPTH = 220.0
step = 1
# Include ultima celula: marginile sunt patrate si corespund exact grilei.
rr = sorted(set(range(0, rows, step)) | {rows-1})
cc = sorted(set(range(0, cols, step)) | {cols-1})
reference = data['referenceElevation']
elevations = [data['elevation'][r*cols+c] for r in rr for c in cc]
vertices = [((c-cols/2)*cell, (rows/2-r)*cell, BASE_THICKNESS+(data['elevation'][r*cols+c]-reference)*VERTICAL_SCALE) for r in rr for c in cc]
w, h = len(cc), len(rr)
faces = []
for r in range(h-1):
    for c in range(w-1):
        a, b, d, e = r*w+c, r*w+c+1, (r+1)*w+c, (r+1)*w+c+1
        # Aceeasi diagonala explicita ca la proiectarea traseelor in Three.js.
        faces.extend(((a,d,b), (e,b,d)))
def object_mesh(name, verts, polys):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], polys)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes['Principled BSDF']
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = .94
    return mat

terrain = object_mesh('Jezero_USGS_surface', vertices, faces)
terrain['verticalScale'] = VERTICAL_SCALE
terrain['baseThickness'] = BASE_THICKNESS
terrain['referenceElevation_m'] = reference
terrain['source'] = data['source']
terrain['transform'] = 'display_z = baseThickness + (USGS_elevation_m - referenceElevation_m) * verticalScale'
terrain['displayOnly'] = True
attribute = terrain.data.attributes.new('USGS_elevation_m', 'FLOAT', 'POINT')
for i, value in enumerate(elevations):
    attribute.data[i].value = value
surface_material = material('Martian ochre - altitude coloration', (.42,.16,.065))
colors = terrain.data.color_attributes.new(name='TerrainColor', type='FLOAT_COLOR', domain='POINT')
relief_range = max(elevations)-min(elevations)
for i, value in enumerate(elevations):
    t = (value-reference)/max(1,relief_range)
    colors.data[i].color = (.29+.22*t, .075+.17*t, .022+.09*t, 1)
node = surface_material.node_tree.nodes.new('ShaderNodeVertexColor')
node.layer_name = 'TerrainColor'
surface_material.node_tree.links.new(node.outputs['Color'], surface_material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
terrain.data.materials.append(surface_material)
terrain.data.materials[0] = terrain_material(root, terrain.data)
for p in terrain.data.polygons:
    p.use_smooth = True
# Pereti de la muchia reala a suprafetei pana la planul bazei, fara schimbarea reliefului.
ring = list(range(w)) + [r*w+w-1 for r in range(1,h)] + list(range((h-1)*w+w-2,(h-1)*w-1,-1)) + [r*w for r in range(h-2,0,-1)]
wall_vertices = [vertices[i] for i in ring] + [(vertices[i][0],vertices[i][1],0) for i in ring]
n = len(ring)
wall_faces = [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
wall_faces.append(tuple(range(n,2*n)))
walls = object_mesh('Square geological cut - presentation base', wall_vertices, wall_faces)
walls.data.materials.append(material('Cut rock', (.20,.065,.025)))
# Soclu patrat, separat de volumul geologic.
low_x, high_x = vertices[0][0], vertices[w-1][0]
low_y, high_y = vertices[-1][1], vertices[0][1]
bpy.ops.mesh.primitive_cube_add(size=1, location=((low_x+high_x)/2,(low_y+high_y)/2,-PLINTH_DEPTH/2))
plinth = bpy.context.object
plinth.name = 'Square dark plinth'
plinth.dimensions = (high_x-low_x,high_y-low_y,PLINTH_DEPTH)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
plinth.data.materials.append(material('Dark basalt plinth',(.032,.024,.019)))
bevel = plinth.modifiers.new('Small edge bevel', 'BEVEL')
bevel.width = 18
bevel.segments = 3
bpy.ops.object.select_all(action='DESELECT')
for obj in (terrain,walls,plinth):
    obj.select_set(True)
bpy.context.view_layer.objects.active = terrain
bpy.ops.export_scene.gltf(filepath=os.path.join(root,'public/terrain/jezero.glb'), export_format='GLB', use_selection=True, export_extras=True)
# Studio de prezentare; podeaua si luminile nu sunt exportate in GLB.
bpy.ops.mesh.primitive_plane_add(size=200000, location=(0,0,-PLINTH_DEPTH-8))
bpy.context.object.name = 'Studio floor - preview only'
bpy.context.object.data.materials.append(material('Studio charcoal',(.025,.022,.020)))
bpy.ops.object.light_add(type='AREA',location=(-7000,-4000,13000))
bpy.context.object.data.energy = 3e9
bpy.context.object.data.shape = 'DISK'
bpy.context.object.data.size = 8000
bpy.ops.object.light_add(type='SUN',location=(0,0,8000))
bpy.context.object.rotation_euler = (.9,-.45,-.7)
bpy.context.object.data.energy = 2.5
bpy.context.scene.world.use_nodes = True
bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .25
bpy.ops.object.camera_add(location=(14500,-17500,14500))
camera = bpy.context.object
camera.rotation_euler = (Vector((0,0,800))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 16600
camera.data.clip_end = 200000
bpy.context.scene.camera = camera
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.samples = 32
bpy.context.scene.render.resolution_x = 1100
bpy.context.scene.render.resolution_y = 1000
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene.render.filepath = os.path.join(root,'public/terrain/jezero-preview.png')
# Verifica matematic ca transformarea de prezentare pastreaza datele sursa.
assert max(abs((vertices[i][2]-BASE_THICKNESS)/VERTICAL_SCALE+reference-z) for i,z in enumerate(elevations)) < 1e-8
assert abs((high_x-low_x)-(high_y-low_y)) < 1e-6
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(root,'terrain/jezero.blend'), compress=True)
bpy.ops.render.render(write_still=True)
print('Verified: original USGS elevations retained; display vertical factor', VERTICAL_SCALE)

