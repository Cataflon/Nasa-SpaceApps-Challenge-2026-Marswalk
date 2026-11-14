"""Texturi PBR procedurale de prezentare; nu modifica DTM-ul."""
import bpy, numpy as np, os

def terrain_material(root, mesh):
    size = 2048
    rng = np.random.default_rng(2026)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    def noise(cells):
        lattice = rng.random((cells+1,cells+1)).astype(np.float32)
        x, y = xx/size*cells, yy/size*cells
        xi, yi = x.astype(int), y.astype(int)
        fx, fy = x-xi, y-yi
        fx, fy = fx*fx*(3-2*fx), fy*fy*(3-2*fy)
        return (lattice[yi,xi]*(1-fx)+lattice[yi,xi+1]*fx)*(1-fy)+(lattice[yi+1,xi]*(1-fx)+lattice[yi+1,xi+1]*fx)*fy
    macro = noise(12)*.4+noise(45)*.32+noise(160)*.18+noise(500)*.1
    fine = noise(700)
    grains = rng.random((size,size)).astype(np.float32)
    ripples = np.sin(xx*.18+noise(35)*14+yy*.08)*.5+.5
    height = macro*.3+fine*.17+grains*.055+ripples*.028
    variation = np.clip(.6+(macro-.5)*.75+(fine-.5)*.16, .2,1)
    colors = np.stack([variation*.58,variation*.245,variation*.095],axis=-1)
    rocks = grains>.995
    colors[rocks] *= .45
    dust = np.clip((noise(30)-.55)*2,0,.35)
    colors += dust[:,:,None]*np.array([.16,.11,.055],dtype=np.float32)
    gy,gx = np.gradient(height)
    normals = np.stack([-gx*5,-gy*5,np.ones_like(gx)],axis=-1)
    normals /= np.linalg.norm(normals,axis=-1)[:,:,None]
    normals = normals*.5+.5
    rough = np.clip(.76+macro*.2,0,1)
    packed = np.stack([np.ones_like(rough),rough,np.zeros_like(rough)],axis=-1)
    folder = os.path.join(root,'public/terrain/textures')
    os.makedirs(folder,exist_ok=True)
    def image(name, rgb, noncolor=False):
        img = bpy.data.images.new(name,width=size,height=size,alpha=True)
        if noncolor: img.colorspace_settings.name = 'Non-Color'
        rgba = np.concatenate([rgb,np.ones((size,size,1),dtype=np.float32)],axis=-1)
        img.pixels.foreach_set(rgba.astype(np.float32).ravel())
        img.filepath_raw = os.path.join(folder,name+'.png')
        img.file_format = 'PNG'
        img.save()
        img.pack()
        return img
    albedo = image('regolith_albedo',colors)
    normal = image('regolith_normal',normals,True)
    orm = image('regolith_roughness',packed,True)
    uv = mesh.uv_layers.new(name='TerrainUV')
    xs=[v.co.x for v in mesh.vertices]; ys=[v.co.y for v in mesh.vertices]
    xmin,xmax,ymin,ymax=min(xs),max(xs),min(ys),max(ys)
    for loop in mesh.loops:
        v = mesh.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = ((v.x-xmin)/(xmax-xmin),(v.y-ymin)/(ymax-ymin))
    mat = bpy.data.materials.new('Jezero - procedural regolith PBR 2K')
    mat.use_nodes = True
    nodes,links = mat.node_tree.nodes,mat.node_tree.links
    shader = nodes['Principled BSDF']
    tex = nodes.new('ShaderNodeTexImage'); tex.image=albedo
    links.new(tex.outputs['Color'],shader.inputs['Base Color'])
    texn=nodes.new('ShaderNodeTexImage'); texn.image=normal
    nmap=nodes.new('ShaderNodeNormalMap'); nmap.inputs['Strength'].default_value=.65
    links.new(texn.outputs['Color'],nmap.inputs['Color']);links.new(nmap.outputs['Normal'],shader.inputs['Normal'])
    texr=nodes.new('ShaderNodeTexImage');texr.image=orm
    split=nodes.new('ShaderNodeSeparateColor')
    links.new(texr.outputs['Color'],split.inputs['Color']);links.new(split.outputs['Green'],shader.inputs['Roughness']);links.new(split.outputs['Blue'],shader.inputs['Metallic'])
    return mat
