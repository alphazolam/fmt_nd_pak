--Naughty Dog PAK Noesis CMD tool
--Version: v0.23
--Last Release: February 8 2023
--Created by: alphaZomega 

global noesis_path = "C:\\Program Files\\Noesis\\Noesis.exe"

global python_plugin = "fmt_nd_pak.py"
global reimport_path = "F:\\"
global formNPDNoesisCMD

fn collectSkinBones node = (
	fn findNodesByName list name = (
		for node in list where stricmp node.name name == 0 collect node
	)
	max modify mode
	local bones = #()
	for sk in node.modifiers where iskindof sk Skin do (
		modpanel.setcurrentobject sk
		nodes = for n in (refs.dependson sk) where isvalidnode n collect n
		
		for k=1 to skinops.getnumberbones sk do (
			name = skinops.getbonename sk k 0
			join bones (findNodesByName nodes name)
		)
	)
	bones
)	

fn selectSkeleton node = (
	local originalSelection = selection as array
	local bones = collectSkinBones node
	while bones[1].parent != undefined do
		bones[1] = bones[1].parent
	bones = #(bones[1])
	for p in bones where p.children != undefined do join bones p.children
	join originalSelection bones
	select originalSelection
)

try(destroydialog formNPDNoesisCMD; clearlistener())catch()
rollout formNPDNoesisCMD "Noesis PAK v0.23" (
	group "Import" (
		button btn_import "Import To Scene" align:#center
		checkbox chk_legacyFBX "Use Legacy FBX" checked:false align:#left tooltip:"Import as FBX 2014"
		checkbox chk_rpgOptimize "Optimize" checked:true align:#left tooltip:"Have Noesis automatically remove duplicate vertices on import"
		checkbox chk_folder "Import Folder" checked:false align:#left
		checkbox chk_populateBones "Populate Bones Lists" checked:false align:#left tooltip:"Populate the bones list of every Skin modifier to have all bones"
	)
	group "Export" (
		button btn_export "Export To Game" align:#center
		checkbox chk_writeBones "Write Bone Positions" checked:false align:#left
		checkbox chk_texOnly "Inject Textures Only" checked:false align:#left
	)
	group "Utilities" (
		--button BtnSkinOnTop "Move Skin to Top of Stack" align:#center 
		button BtnSetScale "Set Scale" offset:[-30,0] toolTip:"Multiply mesh scale by this value.\nRight click to change preset scales"
		edittext FldScale "" text:"1.0" fieldWidth:60 labelOnTop:false offset:[70,-25]
		button btn_reimport "Reimport Noesis FBX" align:#center
	)
	group "Config" (
		checkbox chk_showPlugOpt  "Show FBX Options" checked:false align:#left
		checkbox chk_delFBX  "Delete FBX Files" checked:true align:#left
		checkbox chk_showCMD  "Show Console" checked:false align:#left enabled:true
		label lbl_noesis "Noesis Path:" align:#left
		edittext edt_noesis "" align:#left 
		button btn_noesis "Browse" align:#center tooltip:"Edit NDP_Noesis_CMD.ms (this script) in a text editor to save your Noesis path"
	)
	label lbl_author "By alphaZomega" align:#right
	
	local ScaleValue = 1.0
	local vFactory = 0
	local cmd = ""
	local fbx_path = ""
	
	fn checkDialog = (
		local hwnd = dialogMonitorOps.getWindowHandle()
		if (uiAccessor.getWindowText hwnd == "Import Name Conflict") then (
			uiAccessor.PressButtonByName hwnd "OK"
		)
		true
	)
	fn waitForFileUnlock file file_open_limit:30 = (
		local i = 0
		while i < file_open_limit do (
			if (try(renameFile file (file + ".tmp"))catch(false)) do (
				renameFile (file + ".tmp") file
				exit
			)
			sleep 1
			i += 1
		)
	)
	fn noesisComponentsFound = (
		local state = false
		if doesFileExist noesis_path and doesFileExist ((getFilenamePath noesis_path) + "plugins\\python\\" + python_plugin) do (
			state = true
		)
		state
	)
	on formNPDNoesisCMD open do (
		if doesFileExist (try(noesis_path)catch("")) do (
			edt_noesis.text = noesis_path
			)
		)
	on btn_noesis pressed do (
		cmd = getOpenFileName types:"Noesis.exe|noesis.exe|All|*.*|"
		if cmd != undefined and cmd != "" do (
			edt_noesis.text = noesis_path = cmd
		)
	)
	on edt_noesis changed cmd do (
		edt_noesis.text = noesis_path = cmd
	)
	on btn_import pressed do (
		if noesisComponentsFound() then (
			local cmd = getOpenFileName types:"Naughty Dog PAK Model|*.pak|All|*.*|"
			if cmd != undefined and doesFileExist cmd do (
			
				local showFbxOptions = chk_showPlugOpt.checked
				local files = #(cmd)
				
				if chk_folder.checked then 
					files = getFiles (getFilenamePath cmd + "\\*.mesh")
				
				for f = 1 to files.count do (
					cmd = files[f]
					local fbx_path = (getFilenamePath cmd) + (getFilenameFile (getFilenameFile cmd)) + ".fbx"
					local outtxt_path = fbx_path + ".txt"
					
					cmd = (
						"\"" + noesis_path + "\" ?cmode \"" + cmd + "\" \"" + fbx_path + "\"" \
						 + (if chk_legacyFBX.checked then " -fbxoldexport -fbxexportver FBX201400" else "") \
						 + (if not chk_rpgOptimize.checked then " -fbxnooptimize" else "") \
						 + (" -noprompt -notex -fbxmeshmerge") --always
					) -- -
					if chk_showCMD.checked then (
						DOSCommand ("\"" + cmd + " -logfile \"" + outtxt_path + "\"") 
					)
					else (
						HiddenDOSCommand ("\"" + cmd + " -logfile \"" + outtxt_path + "\"") startpath:(getFilenamePath noesis_path) donotwait:false
					)
					
					waitForFileUnlock(fbx_path)
					if showFbxOptions then (--chk_impPrompt
						success = importFile fbx_path using:FBXIMP
					)
					else (
						success = importFile fbx_path #noPrompt using:FBXIMP
					)
					
					actionMan.executeAction 0 "40472" --open listener
					
					format "Import Command:\n%\n" cmd	
						
					if doesFileExist outtxt_path then (
						local fs = openFile outtxt_path
						if fs != undefined then (
							local noesisOutput = "\n"
							while not eof fs do
							   noesisOutput = noesisOutput + (readline fs) + "\n"
							print noesisOutput
							close fs
							deletefile outtxt_path
						)
					)
					
					if chk_delFBX.checked do (
						deleteFile fbx_path
						format "Deleted FBX file %\n" fbx_path
					)
					
					format "\nImport Command: %\n" cmd --print the command for reference
					
					if success then (
						with redraw off (
							local objSelected = selection as array
							local meshes = for obj in objSelected where (classof obj == Editable_mesh) collect obj 
							local bones = for obj in objSelected where (superclassof obj == Helper or classof obj == BoneGeometry) collect obj 
							for bone in bones do hide bone
							container = Point size:1.0
							local uniqueNames = #(); local mainmeshes = #()
							container.name = getFilenameFile (getFilenameFile cmd)
							
							for mesh in meshes do (
								mesh.parent = container
								mesh.material = undefined
								mesh.wirecolor = color (random 0 255) (random 0 255) (random 0 255)
								if getNumVerts mesh == 3 or mesh.modifiers[#Skin] == undefined then continue
								select mesh
								max modify mode
								sk = mesh.modifiers[#Skin]
								sk.bone_Limit = 8 
								skinOps.RemoveZeroWeights sk
								--local boneNames = for i=1 to (skinOps.GetNumberBones mesh.modifiers[#Skin]) collect (skinOps.GetBoneName mesh.modifiers[#Skin] i 0)
								for bone in bones do (
									bone.showLinks = true
									bone.showLinksOnly = true
									bone.wirecolor = orange
									if chk_populateBones.checked do (
										skinOps.selectBoneByNode sk bone
										local bnName = skinOps.GetBoneName sk (skinOps.GetSelectedBone sk) 0
										if bnName != bone.name then 
											skinops.addBone sk bone 0
									)
								)
							)
						)
					)
					if chk_folder.checked then
						showFbxOptions = false
				)
			)
		) else (messagebox "Failed to Locate Noesis!")
	)
	on btn_export pressed do (
		if noesisComponentsFound() then (
			local cmd = getOpenFileName types:"Naughty Dog PAK Model|*.pak|All|*.*|"
			if cmd != undefined and cmd != "" do (
				local fbx_path = (getFilenamePath cmd) + ((getFilenameFile cmd)) + ".fbx"
				local out_path = (getFilenamePath cmd) + ((getFilenameFile cmd)) + ".NEW" + (getFilenameType  cmd)
				local outtxt_path = fbx_path + ".txt"
				
				if findString (toLower fbx_path) ".orig.fbx" != undefined then (
					meshPath = (replace fbx_path (findString (toLower fbx_path) ".orig.fbx") 9 (".pak"))
					format "Changing file output from %.pak to %.pak\n" (getFilenameFile out_path) (getFilenameFile meshPath)
					out_path = meshPath
				)
				
				local originalSelection = selection as array
				for obj in originalSelection where superclassof obj == GeometryClass and obj.modifiers[#Skin] != undefined do ( 
					selectSkeleton obj 
					exit
				)
				
				local copyNodes = #()
				for obj in originalSelection where obj.modifiers[#Skin] != undefined do ( 
					selectSkeleton obj
					--Create dummy mesh with all bones in skin modifier so that FBX will save all bones
					maxOps.cloneNodes obj cloneType:#copy newNodes:&copyNodes #nodialog
					local lastSelection = (selection as array); select copyNodes[1]; copyNodes[1].name = "FBXBoneStorage"
					for bn in lastSelection do 
						if superclassof bn == Helper or classof bn == BoneGeometry then 
							skinops.addBone copyNodes[1].modifiers[#Skin] bn 0
					selectmore lastSelection
					exit
				)
				
				if chk_showPlugOpt.checked then (--chk_expPrompt
					exportFile fbx_path selectedOnly:true using:FBXEXP
				)
				else (
					exportFile fbx_path #noPrompt selectedOnly:true using:FBXEXP
				)
				if doesFileExist fbx_path do (
					waitForFileUnlock(fbx_path)
					cmd = (
						"\"" + noesis_path + "\" ?cmode \"" + fbx_path + "\" \"" + out_path + "\"" \
						+ (if chk_writeBones.checked then " -bones" else "") \
						+ (if chk_texOnly.checked then " -t" else "") \
						+ (" -meshfile \"" + cmd + "\"") \
					)
					if chk_showCMD.checked then (
						DOSCommand ("\"" + cmd + " -logfile \"" + outtxt_path + "\"")
					)
					else (
						HiddenDOSCommand ("\"" + cmd + " -logfile \"" + outtxt_path + "\"") startpath:(getFilenamePath noesis_path) donotwait:false
					)
					waitForFileUnlock(fbx_path)
					if chk_delFBX.checked do (
						deleteFile fbx_path
						format "Deleted FBX file %" fbx_path
					)
				)
				if copyNodes[1] != undefined then delete copyNodes[1]
					
				actionMan.executeAction 0 "40472" --open listener
				
				format "Export Command:\n%\n" cmd	
					
				if doesFileExist outtxt_path then (
					local fs = openFile outtxt_path
					if fs != undefined then (
						local noesisOutput = "\n"
						while not eof fs do
						   noesisOutput = noesisOutput + (readline fs) + "\n"
						print noesisOutput
						close fs
						deletefile outtxt_path
					)
				)
			)
		) else (messagebox "Failed to Locate Noesis!")
	)
	on btn_reimport pressed do (
		if true then ( --with redraw off (
			if noesisComponentsFound() then (
				if superclassof $ != GeometryClass then return false
				cmd = reimport_path + "ReImportedMeshout.fbx"
				newFile = cmd; origNode = $
				fbx_path = reimport_path + "ReImportedMesh.fbx"
				copyNodes = #(); maxOps.cloneNodes selection cloneType:#copy newNodes:&copyNodes #nodialog
				select copyNodes[1]; collapsestack $; $.name = origNode.name
				if chk_showPlugOpt.checked then (--chk_expPrompt
					if not (exportFile fbx_path selectedOnly:true using:FBXEXP) then format ("Failed to write to %\n" fbx_path)
				)
				else (
					if not (exportFile fbx_path #noPrompt selectedOnly:true using:FBXEXP) then format ("Failed to write to %\n" fbx_path)
				)
				if doesFileExist fbx_path do (
					waitForFileUnlock(fbx_path)
					cmd = (
						"\"" + noesis_path + "\" ?cmode \"" + fbx_path + "\" \"" + cmd + "\"" + " -fbxmeshmerge -noanims -notex"  -- + (if chk_noesisOpt.checked then " -RPGOptimize" else "")
					)
					if chk_showCMD.checked then (
						DOSCommand ("\"" + cmd + "\"")
					)
					else (
						HiddenDOSCommand ("\"" + cmd + "\"") startpath:(getFilenamePath noesis_path) donotwait:false
					)
					
					format "%\n" cmd
					waitForFileUnlock(fbx_path)
					waitForFileUnlock(newFile)
					oldObj = objects as array
					
					if chk_showPlugOpt.checked then (
						if not (importFile newFile using:FBXIMP) then ( format "Failed to read %\n" newFile)
					) else ( if not (importFile newFile #noPrompt using:FBXIMP) then ( format "Failed to read %\n" newFile) )
					
					if chk_delFBX.checked do (
						deleteFile fbx_path
						deleteFile newFile
					)
					
					newObj = for o in objects where findItem oldObj o == 0 collect o
					for obj in newObj do (
						if superclassof obj == GeometryClass then 
							selectmore obj
						else delete obj
					)
					
					if $ != undefined then (
						collapsestack $
						addModifier $ (Skin_Wrap())
						skinWrap = $.modifiers["Skin_Wrap"]
						skinWrap.weightAllVerts = true
						skinWrap.falloff = 1.0
						skinWrap.Distance = 0.05
						skinWrap.meshList = #(origNode)
						skinWrap.convertToSkin false
						$.modifiers[#Skin].bone_Limit = 8
						deleteModifier $ $.modifiers["Skin_Wrap"]
					)
				)	
				delete copyNodes[1]
			) else (messagebox "Failed to Locate Noesis!")
		)
	)
	
	on FldScale entered num do (
		ScaleValue = try (num as float) catch (1.0)
		FldScale.text = ScaleValue as string
	)
	
	on BtnSetScale pressed do (
		local object = $
		if superclassof object == GeometryClass and object.modifiers[#skin] != undefined then (
			local bones = collectSkinBones object
			while bones[1].parent != undefined do
				bones[1] = bones[1].parent
			object = bones[1]
		)
		if (superclassof object == Helper or classof object == BoneGeometry) then (
			with undo on (
				local bone = object
				while bone.parent != undefined do bone = bone.parent
				local delta = (matrix3 [1,0,0][0,0,-1][0,1,0][0,0,0])--inverse bone.transform
				if ScaleValue == 1 then (
					bone.transform = (matrix3 [1,0,0] [0,0,1] [0,-1,0] bone.pos)
				) else bone.transform *= delta * (matrix3 [ScaleValue,0,0] [0,0,ScaleValue] [0,-ScaleValue,0] [0,0,0]) -- 
			)
		) else 
			messagebox "Select the root bone"
	)
	
	on BtnSetScale rightclick do (
		if ScaleValue == 1.0 then ScaleValue = 0.393701
		else if ScaleValue == 0.393701 then ScaleValue = 2.54
		else if ScaleValue == 2.54 then ScaleValue = 1.0
		FldScale.text = ScaleValue as string
	)
)
createdialog formNPDNoesisCMD