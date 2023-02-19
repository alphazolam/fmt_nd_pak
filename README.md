# fmt_nd_pak
Naughty Dog ".pak" model plugin for Rich Whitehouse's Noesis

by alphaZomega

![plugin](https://i.imgur.com/oAzAv5A.png)

This plugin previews Uncharted 4 and The Lost Legacy models from their pak files and can fetch textures for them as well.
It can also create modified pak files for use in modding the game.
Support for Naughty Dog games beyond Uncharted 4 is also possible in the future.


## Installation
1. Download and install [Noesis](https://richwhitehouse.com/index.php?content=inc_projects.php&showproject=91)

2. Place 'fmt_nd_pak.py' and 'UC4TextureHashes.json' into your Noesis\Plugins\Python\ folder

3. (Optional) Edit 'fmt_nd_pak.py' to point to the location of your extracted game files (directory containing 'Actor77', 'texturedict2' etc folders). Make sure the path has double slashes ("\\\\"s instead of "\\\"s)

4. (Optional) Place NDP_NOESIS_CMD.ms into your 3dsmax Scripts folder or a place where you keep your Maxscripts

5. (Optional) Associate Noesis with loading .pak files


## Extaction / File Modding
Use [U4.PSARC.Tool](https://github.com/Ekey/U4.PSARC.Tool) by Ekey to extract your PSARC files and get the pak files that make up everything in the game.
Rename your original PSARC so that the game does not see it and it will resort to loading its assets from your extracted folder of that PSARC instead, if it is in the same folder.

You can use [Fluffy Mod Manager](https://www.nexusmods.com/unchartedlegacyofthievescollection/mods/45) to install and uninstall mods quickly without needing to extract everything

## Usage
Load an Uncharted 4 pak file in Noesis and it will appear in the Noesis preview, if it has geometry.
If you have set up your extracted base directory in Installation step 3, many models should load their hi-res textures.
LOW RES EMBEDDED TEXTURES ARE DISPLAYED WITH BLACK LINES ACROSS THEM, this is a bug I will try to fix.

You can export this model as FBX with 'File -> Export from Preview'. Then view or edit it in Blender or 3dsmax.
Using 'Export From Preview' on a model that has had its textures loaded will save the textures to the same folder as TGA files. You can bypass this by checking 'No Textures' in the Noesis export menu.

*MANY MODELS DO NOT HAVE BONES IN THEIR OWN PAK!*

The "Base Skeleton" for most characters and many weapons is in a file that's name ends in '-base.pak'. Noesis will attempt to find these files automatically from inside your specified BaseDirectory. You'll need to skeleton in order to import the rigging properly.
If you get an import error about an out-of-range bone index, it is probably from loading the wrong base skeleton.

You can load multiple files at once using the plugin's GUI window, and select the skeletal base. It will attempt to merge all selected paks together into the same preview scene, which you can then extract as FBX

#### GUI OPTIONS:

- Load Textures: 	  	Load textures onto the model
- Load Base (Skeleton):	Attempt to load a base skeleton for every rigged model missing bones
- Import LODs:		  	Load lower detail LODs onto the model. Lower detail LODs will be disabled on exported paks with this option enabled
- Convert Textures:	  	Convert normal maps to put normal X in the red channel and normal Y in the green channel (standard format). Also separates Occlusion maps from Normal maps and assigns them in Noesis preview.
- Load All Textures:	Allows you to extract every texture in a pak, rather than just diffuse, transparency and normal maps
- Game :				This menu lets you pick between using HD textures/skeletons from Uncharted 4 or The Lost Legacy, along with setting which one's Base Directory is used	
- View: 				This menu lets you pick between viewing files / folders from the directory of the opened file or from the extracted Base Directory of your selected Game

## Injecting
Once you have edited a model in your 3D program, you can inject it back into a copy of the same pak file it came from using Noesis 'File -> Export -> .pak - Naughty Dog PAK'
The resulting file will be injected with the new geometry and should work, but many cases have not been tested yet.

- You can now inject submeshes with up to 60,000 vertices, however it is advisable to keep submeshes at lower vertex counts than that as each "page" in the pak file is only capable of holding 1MB of data, and 60k vertices of complex rigging on one submesh can add up to more than that
- It is best to keep an original copy of the mesh you are injecting and inject that copy every time. *DO NOT inject an already-injected file!*
- The script normally makes LOD0 become the LOD for all distances, but LOD3 is special and needs to be preserved when exporting in order to have working shadows and facial lighting, so it is not modified by this. You can make copies of your LOD0 submeshes renamed for their LOD3 counterparts to preserve this.
- Use the '-lods' advanced option to inject all LODs as LOD0 is normally injected, creating placeholders if they are not there.
- Use the '-bones' advanced option to write new bone positions, creating a new base.pak file if needed

#### SUBMESHES IN YOUR FBX MUST HAVE THE SAME NAMES AS SUBMESHES FROM THE ORIGINAL PAK TO BE INJECTED, otherwise they will be ignored.

![RaqModExample](https://i.imgur.com/ET7C3wm.png)


## Texture Modding
When loading any pak model, its list of used textures will appear in the debug log.
You can create a folder named after the file you are injecting and fill it with properly-encoded DDS files with the same filenames as from this list, and the plugin will grab those textures and embed them into the PAK.

## Material Modding
To edit materials, you will need to use my 010 Editor template, [nd_pak.bt ](https://github.com/alphazolam/nd_pak.bt)
Navigate to PageData[0-3] -> GEOMETRY_1 -> Item -> SubmeshDescs, and edit the Material for your submesh. You can change important material parameters and you can modify which textures are loaded by swapping texStruct offsets in TexHeaders section.
Edit material parameters on the vanilla copy of your pak file that you are repeatedly injecting for best results.

#### Use the '-t' Advanced option to inject only textures, ignoring the mesh

![-t-option](https://i.imgur.com/0CEvcyC.png)

For example, when injecting "nadine-island-body.pak", create a folder called "nadine-island-body" next to it and put "nadine_mad_pants-color.dds" encoded as BC1/DXT1 compression, and it will become the texture for Nadine's pants on the island. You can use Intel Texture Works plugin for Photoshop to encode your textures.
Even if you are not modding the mesh and only want to change textures, you still need to use an FBX to inject them.
Check the Noesis debug log when exporting for the text "Checking for textures in \[path]" to see exactly where you need to put your dds files.
*NORMAL MAPS should have AMBIENT OCCLUSION map in the RED channel, Normal X in the GREEN channel and Normal Y in the BLUE channel*


## NDP_NOESIS_CMD Maxscript
This Maxscript tool lets you quickly mod pak files in 3dsmax through a GUI.

Edit the 'NDP_NOESIS_CMD.ms' file in a text editor to point it to the location of your Noesis.exe
Then you can load it in 3dsmax with 'Scripts -> Run Script'
It should let you import a pak file directly into the scene.

To export a mod from submeshes in your scene, select all of those submeshes and click "Export" in the script window.
It will let you select a pak file to inject, and will make a modified copy of it.

#### Tips
- If you rename your original pak (to be injected) from say 'hero-island.pak' to 'hero-island.orig.pak' and keep it next to hero-island, you can inject 'hero-island.orig' with the Maxscript to create a modified 'hero-island.pak' immediately. This allows you to quickly mod without having to rename things every time.
- You can set up a textures folder for each model you are injecting and quickly switch between them using the Browse button
- It is always helpful for rigging to use the multi-file loading feature of the plugin to import body, head, hair, jacket, holster etc all together on the same big skeleton

## SUPPORT 
Use my [nd_pak.bt](https://github.com/alphazolam/nd_pak.bt) binary template to learn more about pak files and edit things like material parameters


For more support, join our Uncharted Modding discord at 

https://discord.gg/APQr5GgUeC


Here is an example mod I made for Uncharted 4 using this plugin:
[![ChrisModExample](https://i.imgur.com/b4b6Y6K.jpg)](https://youtu.be/iFkjbkle4JU)