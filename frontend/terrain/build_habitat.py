"""Habitat conceptuel inspire de NASA/ICON/BIG Mars Dune Alpha, unites en metres."""
import bpy, math, os
from mathutils import Vector
root=os.getcwd()
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
parts=[]
def mat(name,color,metal=0,rough=.7,emission=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    s=m.node_tree.nodes['Principled BSDF'];s.inputs['Base Color'].default_value=(*color,1);s.inputs['Metallic'].default_value=metal;s.inputs['Roughness'].default_value=rough
    if emission: s.inputs['Emission Color'].default_value=(*color,1);s.inputs['Emission Strength'].default_value=emission
    return m
wall=mat('Printed sand concrete',(.52,.30,.15));rib=mat('Printed layer edges',(.62,.39,.21));roof=mat('Sand membrane roof',(.67,.53,.36));dark=mat('Graphite frame',(.045,.04,.032),.5,.4);glass=mat('Recessed glazing',(.065,.12,.14),.65,.2);light=mat('Warm airlock lighting',(1,.58,.18),0,.4,2)
def box(name,loc,size,material,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(material)
    if bevel: m=o.modifiers.new('Rounded construction edges','BEVEL');m.width=bevel;m.segments=3
    parts.append(o);return o
def cylinder(name,loc,radius,depth,material):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=radius,depth=depth,location=loc);o=bpy.context.object;o.name=name;o.data.materials.append(material);parts.append(o);return o
box('160 m2 footprint - conceptual', (0,0,.1),(20,8,.2),dark,.15)
box('Printed main envelope',(0,0,1.7),(20,8,3.2),wall,.6)
# Contour rectangulaire arrondi, strates de fabrication visibles.
outline=[]
for cx,cy,start in [(9.4,3.4,0),(-9.4,3.4,90),(-9.4,-3.4,180),(9.4,-3.4,270)]:
    for j in range(9):
        a=math.radians(start+j/8*90);outline.append((cx+.6*math.cos(a),cy+.6*math.sin(a)))
curve=bpy.data.curves.new('Horizontal printing courses','CURVE');curve.dimensions='3D';curve.bevel_depth=.022;curve.bevel_resolution=1
for k in range(57):
    line=curve.splines.new('POLY');line.points.add(len(outline)-1)
    for p,(x,y) in zip(line.points,outline):p.co=(x*1.001,y*1.001,.25+k*.052,1)
    line.use_cyclic_u=True
obj=bpy.data.objects.new('57 additive manufacturing layers',curve);bpy.context.collection.objects.link(obj);obj.data.materials.append(rib);parts.append(obj)
# Cinq voûtes basses forment le toit ondulant caractéristique.
for k in range(5):
    verts=[];faces=[]
    for xi in [0,1]:
        for j in range(33):
            t=j/32;verts.append((-10+k*4+xi*4,-4.05+8.1*t,3.15+.95*math.sin(math.pi*t)))
    for j in range(32):faces.append((j,j+1,j+34,j+33))
    mesh=bpy.data.meshes.new('Vault');mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new('Low vaulted roof '+str(k+1),mesh);bpy.context.collection.objects.link(o);o.data.materials.append(roof);parts.append(o)
    mod=o.modifiers.new('Roof membrane thickness','SOLIDIFY');mod.thickness=.12
    for p in mesh.polygons:p.use_smooth=True
    box('Roof seam '+str(k),(-10+k*4,0,3.35),(.065,8.05,.08),dark)
for side in [-1,1]:
    for x in [-7,-3,1,5]:
        box('Window frame',(x,side*4.02,1.8),(1.55,.15,1.05),dark,.09)
        box('Dark observation window',(x,side*4.12,1.8),(1.31,.035,.81),glass,.05)
        box('Window mullion',(x,side*4.15,1.8),(.035,.04,.82),roof)
box('Airlock pressure module',(11.25,0,1.6),(3,3.2,3.2),roof,.3)
box('Airlock frame',(12.8,0,1.4),(.16,1.65,2.55),dark,.12)
box('Airlock hatch',(12.91,0,1.4),(.08,1.3,2.2),rib,.1)
box('Airlock vision panel',(12.97,0,1.75),(.04,.7,.55),glass,.04)
box('Airlock status light',(12.99,0,2.55),(.06,.8,.07),light)
for k in range(3):box('Entrance stair',(13.3+k*.4,0,.3-k*.08),(.45,2,.15),dark,.02)
box('Exterior EVA area - 110 m2 conceptual',(-5,-9.5,-.02),(10,11,.16),rib,.08)
for x in [-9.8,-.2]:
    for y in [-14.8,-4.3]:cylinder('EVA enclosure post',(x,y,1.25),.045,2.5,dark)
for x in [-9.8,-.2]:box('EVA boundary rail',(x,-9.5,2.2),(.065,10.5,.065),dark)
for k in range(2):
    cylinder('Life support tank',(-6+k*1.5,5.5,1.1),.5,2.2,roof)
box('Life support cabinet',(5,4.8,.8),(2.6,1.2,1.6),dark,.12)
for k in range(10):box('Heat exchanger fin',(4+k*.22,5.43,.9),(.045,.08,1.1),roof)
cylinder('Communications mast',(-9,3,4.1),.035,2,dark)
box('Antenna',(-9,3,5.15),(.6,.08,.35),roof,.04)
for obj in parts:
    if obj.type=='CURVE':
        bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.convert(target='MESH');obj.select_set(False)
bpy.ops.object.select_all(action='DESELECT')
for obj in parts:obj.select_set(True)
# Metadonnees: maquette inspiree, pas une reconstitution architecturale certifiee.
parts[0]['reference']='NASA CHAPEA / ICON / BIG Mars Dune Alpha'
parts[0]['conceptual']=True
parts[0]['interior_reference_m2']=160
parts[0]['exterior_reference_m2']=110
bpy.ops.export_scene.gltf(filepath=os.path.join(root,'public/terrain/habitat.glb'),export_format='GLB',use_selection=True,export_extras=True)
bpy.ops.object.light_add(type='AREA',location=(6,-10,18));bpy.context.object.data.energy=2500;bpy.context.object.data.size=12
bpy.context.scene.world.use_nodes=True;bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.3
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.15));bpy.context.object.data.materials.append(mat('Studio sand',(.14,.09,.05)))
bpy.ops.object.camera_add(location=(26,-32,22));camera=bpy.context.object;camera.rotation_euler=(Vector((0,-3,1))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=40;bpy.context.scene.camera=camera
bpy.context.scene.render.engine='CYCLES';bpy.context.scene.cycles.samples=32;bpy.context.scene.render.resolution_x=1200;bpy.context.scene.render.resolution_y=900;bpy.context.scene.render.resolution_percentage=100
bpy.context.scene.render.filepath=os.path.join(root,'public/terrain/habitat-preview.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(root,'terrain/habitat.blend'));bpy.ops.render.render(write_still=True)
