import bpy
import os
import shutil
import json 
from PIL import Image
from PIL.ImageChops import invert
from gltflib import GLTF

#remember to run these from Blender\3.0\python\lib
#..\bin\python.exe ensurepip
#..\bin\python.exe -m pip install numpy gltflib pillow

fileFormat = "smd"
pathPrefix = "deskjob"

def Kv2Json(kv):
    return json.loads(kv.split("\n",1)[1].replace('"	', '":	').replace('"\n','",\n').replace('",\n}','"\n}') )

def GenerateVMT( path, name, root ):
    return('PBR_STANDARD\n'
    '{\n'
    '    \"$baseTexture\" \"' + path + name + '_a"\n'
    '    \"$bumpmap\" \"' + path + name + '_n"\n'
    '    \"$rmamap\" \"' + path + name + '_r"\n'
    '}\n')

def GenerateQC( path, name, root ):
    modelScale = 43 if fileFormat == 'smd' else '0.4'
    return('$modelname	\"' +  path.replace('models\\','') + '\\' + name +'.mdl\"\n'
        '$scale '+ str(modelScale) + '\n'
        '$body mybody	\"' + name + '.' + fileFormat + '\"\n'
        '$staticprop\n'
        '$cdmaterials	\"' +path +'"\n'
        '$sequence idle	\"' + name + '.' + fileFormat + '\"\n'
        '$collisionmodel	\"' + name + '.' + fileFormat + '\" { $concave }\n')

def ConvertComplexToNemesisMap(path,name, root, iColor, iNormal, iAO):
    #try:
    relativePath = path.replace( root, '' ).replace('\\textures','').replace("models\\", 'models\\' + pathPrefix +'\\') + '\\'
    #convert these boys to our format for NemesisMap
    #todo support for special map?
    #hack: clamp metalness
    complex=1
    if(complex):
        #complex shader
        iNemesisMap = Image.new( mode = "RGB", size = iColor.size)
        iNemesisMap.putdata(
            [
                (rough[3], 255 - ( max((metal[3] - 128),0) * 2 ),ao[0]) 
                for (metal, rough, ao) in 
                zip( iColor.getdata(), iNormal.getdata(), iAO.getdata()) 
            ] )
    else:
        #Standard shader
        iNemesisMap = Image.new( mode = "RGB", size = iColor.size)
        iNemesisMap.putdata(
            [
                ( int( pow( float(rough[3]) / 255.0, 2.0 ) * 255 ), 255 - ( max((metal[3] - 128),0) * 2 ),ao[0])  
                for (metal, rough, ao) in 
                zip( iColor.getdata(), iNormal.getdata(), iAO.getdata()) 
            ] )
    #strip the alpha from the other boys
    iColor = iColor.convert("RGB")
    iNormal = iNormal.convert("RGB")
    #Invert normals
    red, green, blue = iNormal.split()
    iNormal = Image.merge('RGB', (red, invert(green), blue))
    #save em
    savePath = root + '..\\converted\\materials\\' + relativePath
    os.makedirs( savePath, exist_ok=True )
    iColor.save( savePath + name + '_a.png', type="PNG" )
    iNormal.save( savePath + name + '_n.png', type="PNG" )
    iNemesisMap.save( savePath + name + '_r.png', type="PNG" )
    open( savePath + name + '.vmt', "w+").write( GenerateVMT(relativePath, name, root) )

def ConvertVMat( path,name, root ):
    try:
        with open( os.path.join(path, name),'r') as file:
            relativePath = path.replace( root, '' ).replace('\\textures','\\')
            data = Kv2Json(file.read())
            name = name.rsplit( ".", 1 )[ 0 ] # No need .vmat anymore
            tColor =    data['g_tColor'].replace('.vtex','').replace("/","\\")
            tNormal =   data['g_tNormal'].replace('.vtex','').replace("/","\\")
            tAO =       data['g_tAmbientOcclusion'].replace('.vtex','').replace("/","\\")
            iColor = Image.open(root + tColor + ".png" )
            iNormal = Image.open(root + tNormal + ".png" ) # check if we need to flip normals
            iAO = Image.open(root + tAO + ".png" )
            outName = name if fileFormat == 'smd' else tColor.rsplit( ".", 1 )[ 0 ]
            # Todo: Needs another path if we are using standard shader
            ConvertComplexToNemesisMap(path, outName , root, iColor, iNormal, iAO)
    except:
        print("Error processing texture " + name)

#Recalculate normals etc
def ProcessModel(name):
    print("Fixing normals in scene for" + name)
    obj_objects = bpy.context.selected_objects[:]
    for obj in obj_objects:
        if obj.type == 'MESH':
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            # go edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            # select al faces
            bpy.ops.mesh.select_all(action='SELECT')
            # recalculate outside normals 
            bpy.ops.mesh.normals_make_consistent(inside=False)
            # go object mode again
            bpy.ops.object.editmode_toggle()
    #Fix the name of the mesh we are going to export
    for index, obj in enumerate(obj_objects):
        index = 0;
        if obj.type == 'MESH':
            #Remove lower LODS, fixme, we should rather export all of them
            if index > 0:
                bpy.data.objects.remove(obj)
            else:
                obj.name = name;
            index+=1

def ConvertGLTFTextures(path,name,root):
    gltf = GLTF.load( os.path.join(path, name) )
    if gltf.model.materials:
        for material in gltf.model.materials:
            materialName = material.name;
            colorIndex = material.pbrMetallicRoughness.baseColorTexture.index
            print("Converting material " + materialName)
            tColor = gltf.model.images[gltf.model.textures[colorIndex].source].uri
            iColor = Image.open(path + '\\' + tColor )
            #Some of them don't have normal maps
            normalIndex = material.normalTexture.index if material.normalTexture is not None else -1
            if ( normalIndex != -1 ):
                tNormal = gltf.model.images[gltf.model.textures[normalIndex].source].uri
                iNormal = Image.open(path + '\\' + tNormal )
            else:
                # Make a blank normal map
                iNormal = Image.new( mode = "RGBA", size = iColor.size)
                iNormal.putdata( [ (128,128,255,255) for i in range(iColor.size[0] * iColor.size[1]) ] )
                print("No normal map for " + materialName)
            #Some of them don't have AO
            aoIndex = material.occlusionTexture.index if material.occlusionTexture is not None else -1
            if(aoIndex != -1):
                tAO = gltf.model.images[gltf.model.textures[aoIndex].source].uri
                iAO = Image.open(path + '\\' + tAO )
            else:
                #Make a dummy white AO
                # Generate a blank AO from the aspect ratio of the color map
                iAO = Image.new( mode = "RGB", size = iColor.size)
                iAO.putdata( [ (255,255,255) for i in range(iColor.size[0] * iColor.size[1]) ] )
                print("No AO map for " + materialName)
            outName = materialName if fileFormat == 'smd' else tColor.rsplit( ".", 1 )[ 0 ]
            ConvertComplexToNemesisMap(path, outName , root, iColor, iNormal, iAO)

def ConvertGLTFToSourceFBX( path,name, root ):
    print("Converting " + name + " to FBX")
    ConvertGLTFTextures( path,name, root )
    #convert the model itself
    name = name.rsplit( ".", 1 )[ 0 ] #remove extension
    relativePath = path.replace( root, '' ).replace('\\textures','\\').replace("models\\", 'models\\' + pathPrefix +'\\')
    exportPath = root + '..\\converted\\' + relativePath + '\\'
    print("Converting " + name + " to " + name)
    # delete everything
    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj)
    # import smd
    bpy.ops.import_scene.gltf(filepath=os.path.join(path, name + '.gltf'))
    # Recalculate normals etc
    ProcessModel(name)
    # export the boy
    os.makedirs( exportPath, exist_ok=True )
    if fileFormat == "fbx":
        bpy.ops.export_scene.fbx(filepath= exportPath + name + '.fbx' )
    elif fileFormat == "smd":
        scene = bpy.data.scenes[0]
        scene.vs.export_format = "SMD"
        scene.vs.export_path = exportPath
        bpy.ops.export_scene.smd()
    print(GenerateQC(relativePath, name, root))
    #And generate QC
    open( exportPath + name + '.qc', "w+").write( GenerateQC(relativePath, name, root) )

#Setup plugin

#Convert mesh SMDs to FBX
def convertS2ToSource( dir ):
    for root, dirs, files in os.walk(dir):
        for directory in dirs:
            convertS2ToSource(directory) 
        for name in files:
            if name.lower().endswith('gltf'):
                ConvertGLTFToSourceFBX(root,name,dir)
            elif name.lower().endswith('vmat'):
                ConvertVMat(root,name,dir)

convertS2ToSource("C:\\Dev\\Source2ToSource1\\deskjob\\")