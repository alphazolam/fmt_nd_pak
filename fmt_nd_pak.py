#fmt_nd_pak.py - Naughty Dog ".pak" plugin for Rich Whitehouse's Noesis
#Author: alphaZomega 
#Special Thanks: icemesh 
Version = 'v1.5 (March 30, 2023)'


#Options: These are global options that change or enable/disable certain features
#Option															Effect
GlobalScale = 100												# Set the scale of the imported model
NoDialog = False												# Disable the UI dialog window on import
LoadBaseSkeleton = True											# Attempt to load a base skeleton for every rigged model missing bones
LoadAllLODs	= False												# Load lower detail LODs onto the model. Lower detail LODs will be disabled on exported paks with this option enabled
LoadTextures = False											# Load textures onto the model
ConvertTextures = True											# Convert normal maps to put normal X in the red channel and normal Y in the green channel (standard format)
FlipUVs = False													# Flip UVs and flip texture images rightside-up (NOT IMPLEMENTED)
LoadAllTextures = False											# Load all textures onto a model, rather than only color and normal maps
ReadColors = False												# Read vertex colors
PrintMaterialParams = False										# Print out all material parameters in the debug log when importing
texoutExt = ".dds"												# Extension of texture files (change to load textures of a specific type in Blender)
gameName = "U4"													# Default game name
ReparentHelpers = 2												# Parents helper bones based on their names, mostly for TLOU models. Set to '2' for automatic


# Set the base path from which the plugin will search for pak files and textures:
BaseDirectories = {
	"TLL": "D:\\ExtractedGameFiles\\Uncharted4_data\\build\\pc\\thelostlegacy\\",
	"U4": "D:\\ExtractedGameFiles\\Uncharted4_data\\build\\pc\\uncharted4\\",
	"TLOU2": "D:\\ExtractedGameFiles\\root\\build\\ps4\\main\\",
	"TLOUP1": "H:\\ExtractedGameFiles\\TLOUP1\\build\\pc\\main\\",
}

from inc_noesis import *
from collections import namedtuple
import noewin
import json
import os
import re
import time

class DialogOptions:
	def __init__(self):
		self.doLoadTex = LoadTextures
		self.doLoadBase = LoadBaseSkeleton
		self.doConvertTex = ConvertTextures
		self.doFlipUVs = FlipUVs
		self.doLODs = LoadAllLODs
		self.loadAllTextures = LoadAllTextures
		self.printMaterialParams = PrintMaterialParams
		self.reparentHelpers = ReparentHelpers
		self.readColors = ReadColors
		self.baseSkeleton = None
		self.width = 600
		self.height = 850
		self.texDicts = None
		self.gameName = gameName
		self.currentDir = ""
		self.isTLOU2 = False
		self.isTLOUP1 = False
		self.dialog = None

dialogOptions = DialogOptions()
ResItemPaddingSz = 32

def registerNoesisTypes():
	handle = noesis.register("Naughty Dog PAK", ".pak")
	noesis.setTypeExportOptions(handle, "-noanims -notex")
	noesis.addOption(handle, "-nodialog", "Do not display dialog window", 0)
	noesis.addOption(handle, "-t", "Textures only; do not inject geometry data", 0)
	noesis.addOption(handle, "-bones", "Write bone positions", 0)
	noesis.addOption(handle, "-lods", "Import/Export with all LODs", 0)
	noesis.addOption(handle, "-meshfile", "Export using a given source mesh filepath", noesis.OPTFLAG_WANTARG)
	noesis.addOption(handle, "-texfolder", "Export using a given textures folder for embedding", noesis.OPTFLAG_WANTARG)
	noesis.setHandlerTypeCheck(handle, pakCheckType)
	noesis.setHandlerLoadModel(handle, pakLoadModel)
	noesis.setHandlerWriteModel(handle, pakWriteModel)
	noesis.setTypeSharedModelFlags(handle, (noesis.NMSHAREDFL_WANTGLOBALARRAY))
	#noesis.setHandlerLoadRGBA(handle, pakLoadRGBA)
	return 1
	
def pakCheckType(data):
	bs = NoeBitStream(data)
	magic = bs.readUInt()
	if (magic == 2681 or magic == 2685) and magic != 68217 and magic != 2147486329:
		return 1
	else: 
		print("Fatal Error: Unknown file magic: " + str(hex(magic)))
		return 0
		
def getGameName():
	inName = rapi.getInputName().lower()
	outName = rapi.getOutputName().lower()
	if inName.find("\\thelostlegacy\\") != -1 or inName.find("tll") != -1:
		return "TLL"
	if inName.find("\\uncharted4\\") != -1 or inName.find("u4") != -1: 
		return "U4"
	if inName.find("\\ps4\\main\\") != -1 or inName.find("tlou2") != -1: 
		return "TLOU2"
	if inName.find("\\pc\\main\\") != -1 or inName.find("tloup1") != -1: 
		return "TLOUP1"
	return gameName

def findNextOf(bs, integer, is64=False):
	start = bs.tell()
	while not bs.checkEOF() and ((is64 and bs.readInt64()) or bs.readInt()) != integer:
		pass
	output = bs.tell()
	bs.seek(start)
	return output

def readStringAt(bs, offset):
	start = bs.tell()
	bs.seek(offset)
	output = bs.readString()
	bs.seek(start)
	return output
	
def readUIntAt(bs, offset):
	start = bs.tell()
	bs.seek(offset)
	output = bs.readUInt()
	bs.seek(start)
	return output 
	
def writeUIntAt(bs, offset, value):
	start = bs.tell()
	bs.seek(offset)
	bs.writeUInt(value)
	bs.seek(start)
	
def findRootDir(path):
	uncharted4Idx = path.find("\\uncharted4\\")
	if uncharted4Idx != -1:
		return path[:(uncharted4Idx + 12)]
	lostLegacyIdx = path.find("\\thelostlegacy\\")
	if lostLegacyIdx != -1:
		return path[:(lostLegacyIdx + 15)]
	tlou2Idx = path.find("\\ps4\\main\\")
	if lostLegacyIdx != -1:
		return path[:(tlou2Idx + 10)]
	return path

def readFileBytes(filepath, address, size):
	with open(filepath, 'rb') as f:
		f.seek(address)
		return f.read(size)

def generateDummyTexture4px(rgbaColor, name="Dummy"):
	imageByteList = []
	for i in range(16):
		imageByteList.extend(rgbaColor)
	imageData = struct.pack("<" + 'B'*len(imageByteList), *imageByteList)
	imageData = rapi.imageDecodeRaw(imageData, 4, 4, "r8g8b8a8")
	return NoeTexture(name, 4, 4, imageData, noesis.NOESISTEX_RGBA32)	
	
def moveChannelsRGBA(sourceBytes, sourceChannel, sourceWidth, sourceHeight, targetBytes, targetChannel, targetWidth, targetHeight):
	resizedSourceBytes = rapi.imageResample(sourceBytes, sourceWidth, sourceHeight, targetWidth, targetHeight)
	outputTargetBytes = copy.copy(targetBytes)
	for i in range(int(len(resizedSourceBytes)/16)):
		for b in range(4):
			outputTargetBytes[i*16 + b*4 + targetChannel] = resizedSourceBytes[i*16 + b*4 + sourceChannel]
	return outputTargetBytes

def encodeImageData(data, width, height, fmtName):
	outputData = NoeBitStream()
	mipWidth = width
	mipHeight = height
	mipCount = 0
	decodeFmt, encodeFmt, bpp = getDXTFormat(fmtName)
	
	if encodeFmt != None:
		while mipWidth > 2 or mipHeight > 2:
			mipData = rapi.imageResample(data, width, height, mipWidth, mipHeight)
			try:
				dxtData = rapi.imageEncodeDXT(mipData, bpp, mipWidth, mipHeight, encodeFmt)
			except:
				dxtData = rapi.imageEncodeRaw(mipData, mipWidth, mipHeight, encodeFmt)
			outputData.writeBytes(dxtData)
			if mipWidth > 2: 
				mipWidth = int(mipWidth / 2)
			if mipHeight > 2: 
				mipHeight = int(mipHeight / 2)
			mipCount += 1
		
	return outputData.getBuffer(), mipCount
	
def getDXTFormat(fmtName):
	bpp = 8
	decFmt = encFmt = None
	if fmtName.count("Bc1"):
		encFmt = noesis.NOE_ENCODEDXT_BC1
		decFmt = noesis.FOURCC_DXT1
		bpp = 4
	elif fmtName.count("Bc3"):
		encFmt = noesis.NOE_ENCODEDXT_BC3
		decFmt = noesis.FOURCC_BC3
	elif fmtName.count("Bc4"):
		encFmt = noesis.NOE_ENCODEDXT_BC4
		decFmt = noesis.FOURCC_BC4
		bpp = 4
	elif fmtName.count("Bc5"):
		encFmt = noesis.NOE_ENCODEDXT_BC5
		decFmt = noesis.FOURCC_BC5
	elif fmtName.count("Bc6"): 
		encFmt = noesis.NOE_ENCODEDXT_BC6H
		decFmt = noesis.FOURCC_BC6H
	elif fmtName.count("Bc7"): 
		encFmt = noesis.NOE_ENCODEDXT_BC7
		decFmt = noesis.FOURCC_BC7
	elif re.search("[RGBA]\d\d?", fmtName):
		fmtName = fmtName.split("_")[0].lower()
		encFmt = decFmt = fmtName
	return decFmt, encFmt, bpp
	
	
def recombineNoesisMeshes(mdl):
	
	meshesBySourceName = {}
	for mesh in mdl.meshes:
		meshesBySourceName[mesh.sourceName] = meshesBySourceName.get(mesh.sourceName) or []
		meshesBySourceName[mesh.sourceName].append(mesh)
		
	combinedMeshes = []
	for sourceName, meshList in meshesBySourceName.items():
		newPositions = []
		newUV1 = []
		newUV2 = []
		newUV3 = []
		newTangents = []
		newWeights = []
		newIndices = []
		newColors = []
		for mesh in meshList:
			tempIndices = []
			for index in mesh.indices:
				tempIndices.append(index + len(newPositions))
			newPositions.extend(mesh.positions)
			newUV1.extend(mesh.uvs)
			newUV2.extend(mesh.lmUVs)
			newUV3.extend(mesh.uvxList[0] if len(mesh.uvxList) > 0 else [])
			newColors.extend(mesh.colors)
			newTangents.extend(mesh.tangents)
			newWeights.extend(mesh.weights)
			newIndices.extend(tempIndices)
			
		combinedMesh = NoeMesh(newIndices, newPositions, meshList[0].sourceName, meshList[0].sourceName, mdl.globalVtx, mdl.globalIdx)
		combinedMesh.setTangents(newTangents)
		combinedMesh.setWeights(newWeights)
		combinedMesh.setUVs(newUV1)
		combinedMesh.setUVs(newUV2, 1)
		combinedMesh.setUVs(newUV3, 2)
		combinedMesh.setColors(newColors)
		if len(combinedMesh.positions) > 65535:
			print("Warning: Mesh exceeds the maximum of 65535 vertices (has", str(len(combinedMesh.positions)) + "):\n	", combinedMesh.name)
		else:
			combinedMeshes.append(combinedMesh)
		
	return combinedMeshes

fullGameNames = ["Uncharted 4", "The Lost Legacy", "The Last of Us P1", "The Last of Us P2"]
gamesList = [ "U4", "TLL",  "TLOUP1", "TLOU2"]

for gameName, path in BaseDirectories.items():
	if path[(len(path)-1):] != "\\":
		BaseDirectories[gameName] = path + "\\"

skelFiles = {
	"U4": [
		"actor77\\adventurer-base.pak",
		"actor77\\alcazar-base.pak",
		"actor77\\auctioneer-f-base.pak",
		"actor77\\avery-base.pak",
		"actor77\\avery-guard-base.pak",
		"actor77\\cassie-base.pak",
		"actor77\\col-tower-sect-1-base.pak",
		"actor77\\crash-base.pak",
		"actor77\\elena-base.pak",
		"actor77\\gustavo-base.pak",
		"actor77\\jameson-base.pak",
		"actor77\\lemur-base.pak",
		"actor77\\light-base.pak",
		"actor77\\man-false-journals-base.pak",
		"actor77\\man-letters-base.pak",
		"actor77\\man-letters-pictures-base.pak",
		"actor77\\manager-base.pak",
		"actor77\\monica-base.pak",
		"actor77\\nadine-base.pak",
		"actor77\\note-fold-6x9-portrait-base.pak",
		"actor77\\note-fold-standard-portrait-base.pak",
		"actor77\\npc-medium-base.pak",
		"actor77\\npc-normal-base.pak",
		"actor77\\npc-normal-crowd-base.pak",
		"actor77\\npc-normal-crowd-fem-base.pak",
		"actor77\\npc-normal-fem-base.pak",
		"actor77\\pistol-base.pak",
		"actor77\\prison-drake-base.pak",
		"actor77\\proto.pak",
		"actor77\\proto-sp.pak",
		"actor77\\rafe-base.pak",
		"actor77\\rifle-base.pak",
		"actor77\\samuel-base.pak",
		"actor77\\sco-bucket-base.pak",
		"actor77\\sco-map-room-second-corner-pillar-base.pak",
		"actor77\\sco-map-room-start-corner-pillar-base.pak",
		"actor77\\sco-map-room-third-corner-pillar-base.pak",
		"actor77\\smokey-base.pak",
		"actor77\\sullivan-base.pak",
		"actor77\\tew-base.pak",
		"actor77\\throwable-base.pak",
		"actor77\\vargas-base.pak",
		"actor77\\young-drake-base.pak",
		"actor77\\young-samuel-base.pak",
	],
	"TLL": [
		"actor77\\asav-base.pak",
		"actor77\\chloe-base.pak",
		"actor77\\elena-base.pak",
		"actor77\\horse-base.pak",
		"actor77\\light-base.pak",
		"actor77\\meenu-base.pak",
		"actor77\\monkey-base.pak",
		"actor77\\nadine-base.pak",
		"actor77\\nadine-dlc-base.pak",
		"actor77\\nilay-base.pak",
		"actor77\\note-fold-6x9-portrait-base.pak",
		"actor77\\note-fold-standard-portrait-base.pak",
		"actor77\\npc-kid-base.pak",
		"actor77\\npc-kid-fem-base.pak",
		"actor77\\npc-medium-base.pak",
		"actor77\\npc-normal-base.pak",
		"actor77\\npc-normal-crowd-base.pak",
		"actor77\\npc-normal-crowd-fem-base.pak",
		"actor77\\npc-normal-fem-base.pak",
		"actor77\\orca-base.pak",
		"actor77\\pistol-base.pak",
		"actor77\\prison-drake-base.pak",
		"actor77\\proto.pak",
		"actor77\\proto-sp.pak",
		"actor77\\rifle-base.pak",
		"actor77\\rur-combat-column-e-base-a.pak",
		"actor77\\rur-combat-column-f-base-a.pak",
		"actor77\\rur-hub-coin-base.pak",
		"actor77\\rur-hub-forest-rotation-puzzle-base.pak",
		"actor77\\rur-hub-mid-ruins-base-a-broken-corner-a.pak",
		"actor77\\rur-ruling-kings-trinkets-base.pak",
		"actor77\\rur-shiva-puzzle-light-push-stone-base.pak",
		"actor77\\samuel-base.pak",
		"actor77\\samuel-dlc-base.pak",
		"actor77\\sandy-base.pak",
		"actor77\\smokey-base.pak",
		"actor77\\sri-basement-debris-shift-pile-a.pak",
		"actor77\\sullivan-base.pak",
		"actor77\\throwable-base.pak",
		"actor77\\train-car-box-car-base.pak",
		"actor77\\train-locomotive-base.pak",
		"actor77\\vin-base.pak",
		"actor77\\waz-base.pak",
	],
	"TLOUP1": [
		"common\\actor97\\gore-male-shrunk-explosion-lower-skel.pak",
		"common\\actor97\\gore-male-shrunk-explosion-upper-skel.pak",
		"common\\actor97\\light-skel.pak",
		"sp-common\\actor97\\abby-skel.pak",
		"sp-common\\actor97\\alice-skel.pak",
		"sp-common\\actor97\\base-female-skel.pak",
		"sp-common\\actor97\\base-male-skel.pak",
		"sp-common\\actor97\\bird-medium-skel.pak",
		"sp-common\\actor97\\bloater-skel.pak",
		"sp-common\\actor97\\buck-skel.pak",
		"sp-common\\actor97\\cannibal-m-joel-torture-chair-skel.pak",
		"sp-common\\actor97\\craft-backpack-ellie-skel.pak",
		"sp-common\\actor97\\dina-skel.pak",
		"sp-common\\actor97\\dog-skel.pak",
		"sp-common\\actor97\\ellie-skel.pak",
		"sp-common\\actor97\\fire-extinguisher-skel.pak",
		"sp-common\\actor97\\giraffe-skel.pak",
		"sp-common\\actor97\\hare-skel.pak",
		"sp-common\\actor97\\horse-main-rein-cloth-skel.pak",
		"sp-common\\actor97\\horse-main-skel.pak",
		"sp-common\\actor97\\horse-main-stirrups-skel.pak",
		"sp-common\\actor97\\horse-mane-cloth-skel.pak",
		"sp-common\\actor97\\horse-saddle-bag-straps-cloth-skel.pak",
		"sp-common\\actor97\\horse-saddle-strap-cloth-skel.pak",
		"sp-common\\actor97\\horse-skel.pak",
		"sp-common\\actor97\\horse-tail-cloth-skel.pak",
		"sp-common\\actor97\\infected-skel.pak",
		"sp-common\\actor97\\jerry-skel.pak",
		"sp-common\\actor97\\joel-skel.pak",
		"sp-common\\actor97\\npc-normal-skel.pak",
		"sp-common\\actor97\\prop-backpack-ellie-skel.pak",
		"sp-common\\actor97\\prop-backpack-joel-skel.pak",
		"sp-common\\actor97\\runner-f-qz-mal-outro-skel.pak",
		"sp-common\\actor97\\t1x-bill-skel.pak",
		"sp-common\\actor97\\t1x-david-skel.pak",
		"sp-common\\actor97\\t1x-door-l-skel.pak",
		"sp-common\\actor97\\t1x-door-r-skel.pak",
		"sp-common\\actor97\\t1x-drawer-skel.pak",
		"sp-common\\actor97\\t1x-ellie-05-skel.pak",
		"sp-common\\actor97\\t1x-ellie-skel.pak",
		"sp-common\\actor97\\t1x-henry-skel.pak",
		"sp-common\\actor97\\t1x-hunter-m-striker-skel.pak",
		"sp-common\\actor97\\t1x-james-skel.pak",
		"sp-common\\actor97\\t1x-joel-skel.pak",
		"sp-common\\actor97\\t1x-locker-doubledoor-skel.pak",
		"sp-common\\actor97\\t1x-maria-skel.pak",
		"sp-common\\actor97\\t1x-marlene-skel.pak",
		"sp-common\\actor97\\t1x-monkey-skel.pak",
		"sp-common\\actor97\\t1x-riley-skel.pak",
		"sp-common\\actor97\\t1x-robert-skel.pak",
		"sp-common\\actor97\\t1x-sam-skel.pak",
		"sp-common\\actor97\\t1x-sarah-skel.pak",
		"sp-common\\actor97\\t1x-tess-skel.pak",
		"sp-common\\actor97\\t1x-tommy-skel.pak",
		"sp-common\\actor97\\texan-f-news-reporter-skel.pak",
		"sp-common\\pak68\\part-actor-bloater-skel.pak",
		"sp-common\\pak68\\part-actor-fire-extinguisher-skel.pak",
		"world-bills\\actor97\\base-brute-male-skel.pak",
		"world-bills\\actor97\\city-bus-skel.pak",
		"world-bills\\actor97\\infected-bloater-skel.pak",
		"world-bills\\actor97\\infected-fem-skel.pak",
		"world-bills\\actor97\\manny-skel.pak",
		"world-bills\\actor97\\t1x-door-r-skel-realskel.pak",
		"world-bills\\actor97\\t1x-heavy-truck-crewcab-pickup-fma-skel.pak",
		"world-bills\\actor97\\t1x-hunter-ellie-drag-skel.pak",
		"world-bills\\actor97\\t1x-hunter-joel-drag-skel.pak",
		"world-home\\actor97\\base-female-crowd-skel.pak",
		"world-home\\actor97\\base-female-horde-skel.pak",
		"world-home\\actor97\\base-kid-skel.pak",
		"world-home\\actor97\\base-male-crowd-skel.pak",
		"world-home\\actor97\\base-male-horde-skel.pak",
		"world-home\\actor97\\base-teen-skel.pak",
		"world-hunter-city\\actor97\\bird-small-skel.pak",
		"world-hunter-city\\actor97\\fish-large-skel.pak",
		"world-hunter-city\\actor97\\ladder-skel-3o5m-realskel.pak",
		"world-hunter-city\\actor97\\t1x-hunter-m-ellie-drag-skel.pak",
		"world-hunter-city\\actor97\\t1x-hunter-m-joel-drag-skel.pak",
		"world-hunter-city\\actor97\\t1x-ladder-skel-3o5m-realskel.pak",
		"world-hunter-city\\actor97\\t1x-plank-skel-realskel.pak",
		"world-hunter-city\\actor97\\t1x-plank-skel.pak",
		"world-lakeside\\actor97\\t1x-cannibal-m-joel-torture-ground-skel.pak",
		"world-mall\\actor97\\clicker-m-pharmacist-skel.pak",
		"world-mall\\actor97\\t1x-mal-storage-swing-door-skel.pak",
		"world-mall\\actor97\\t1x-mask-skel.pak",
		"world-military-city\\actor97\\bird-large-skel.pak",
		"world-military-city\\actor97\\carry-plank-skel.pak",
		"world-military-city\\actor97\\t1x-door-l-skel-realskel.pak",
		"world-outskirts\\actor97\\bird-xlarge-skel.pak",
		"world-suburbs\\actor97\\seth-skel.pak",
		"world-tommys-dam\\actor97\\door-skel.pak",
	],
	"TLOU2": [
		"common\\actor97\\base-male-skel.pak",
		"common\\actor97\\ellie-skel.pak",
		"common\\actor97\\light-skel.pak",
		"common\\actor97\\manual-upgrade-magazine-righthand-skel.pak",
		"sp-common\\actor97\\ellie-festival-strand-hair-cloth-skel.pak",
		"sp-common\\actor97\\ellie-santa-barbara-hair-cloth-skel.pak",
		"sp-common\\actor97\\ellie-seattle-hoodie-string-skel.pak",
		"sp-common\\actor97\\horse-main-rein-cloth-skel.pak",
		"sp-common\\actor97\\horse-main-stirrups-skel.pak",
		"sp-common\\actor97\\horse-mane-cloth-skel.pak",
		"sp-common\\actor97\\horse-saddle-bag-straps-cloth-skel.pak",
		"sp-common\\actor97\\horse-saddle-strap-cloth-skel.pak",
		"sp-common\\actor97\\horse-tail-cloth-skel.pak",
		"sp-common\\actor97\\lev-jacket-cloth-skel.pak",
		"world-abby-fights-militia\\actor97\\scar-colin-skel.pak",
		"world-abby-flashback-dad\\actor97\\marlene-skel.pak",
		"world-abby-flashback-dad\\actor97\\zebra-baby-skel.pak",
		"world-abby-flashback-dad\\actor97\\zebra-skel.pak",
		"world-ellie-flashback-patrol\\actor97\\base-brute-male-skel.pak",
		"world-ellie-flashback-patrol\\actor97\\bloater-skel.pak",
		"world-ellie-flashback-patrol\\actor97\\infected-bloater-skel.pak",
		"world-farm\\actor97\\base-kid-female-skel.pak",
		"world-farm\\actor97\\festival-partner-skel.pak",
		"world-farm\\actor97\\sheep-lamb-skel.pak",
		"world-find-nora\\actor97\\base-brute-female-skel.pak",
		"world-find-nora\\actor97\\bird-xlarge-skel-t2.pak",
		"world-find-nora\\actor97\\frog-skel.pak",
		"world-find-nora\\actor97\\med-hosp-skeleton-male-a.pak",
		"world-find-nora\\actor97\\militia-whitney-skel.pak",
		"world-find-nora\\actor97\\npc-brute-skel.pak",
		"world-flashback-guitar\\actor97\\base-female-crowd-skel.pak",
		"world-flashback-guitar\\actor97\\base-female-skel.pak",
		"world-flashback-guitar\\actor97\\base-kid-skel.pak",
		"world-flashback-guitar\\actor97\\base-male-crowd-skel.pak",
		"world-flashback-guitar\\actor97\\base-teen-skel.pak",
		"world-flashback-guitar\\actor97\\bird-medium-skel-t2.pak",
		"world-flashback-guitar\\actor97\\dina-skel.pak",
		"world-flashback-guitar\\actor97\\doe-skel.pak",
		"world-flashback-guitar\\actor97\\door-skel.pak",
		"world-flashback-guitar\\actor97\\drawer-skel.pak",
		"world-flashback-guitar\\actor97\\ellie-14-skel.pak",
		"world-flashback-guitar\\actor97\\guitar-skel.pak",
		"world-flashback-guitar\\actor97\\horse-main-skel.pak",
		"world-flashback-guitar\\actor97\\horse-skel.pak",
		"world-flashback-guitar\\actor97\\jerry-skel.pak",
		"world-flashback-guitar\\actor97\\jesse-skel.pak",
		"world-flashback-guitar\\actor97\\joel-skel.pak",
		"world-flashback-guitar\\actor97\\maria-skel.pak",
		"world-flashback-guitar\\actor97\\t1-npc-normal-skel-old.pak",
		"world-flashback-guitar\\actor97\\tommy-skel.pak",
		"world-flooded-city\\actor97\\cab-high-skel-l.pak",
		"world-flooded-city\\actor97\\military-truck-modern-skel.pak",
		"world-flooded-city\\actor97\\young-abby-skel.pak",
		"world-forward-base\\actor97\\bird-small-skel.pak",
		"world-forward-base\\actor97\\bird-tiny-skel.pak",
		"world-forward-base\\actor97\\chicken-skel.pak",
		"world-forward-base\\actor97\\dog-crowd-skel.pak",
		"world-forward-base\\actor97\\fish-skel-sml.pak",
		"world-forward-base\\actor97\\halloween-skeleton-a-hanging.pak",
		"world-forward-base\\actor97\\horse-crowd-skel.pak",
		"world-forward-base\\actor97\\isaac-skel.pak",
		"world-forward-base\\actor97\\militia-mannysdad-skel.pak",
		"world-forward-base\\actor97\\scar-chris-skel.pak",
		"world-forward-base\\actor97\\scar-emily-skel.pak",
		"world-forward-base\\actor97\\sea-lion-skel.pak",
		"world-forward-base\\actor97\\sheep-adult-skel.pak",
		"world-medicine\\actor97\\abby-prisoner-skel.pak",
		"world-medicine\\actor97\\med-hosp-skeleton-female-a.pak",
		"world-medicine\\actor97\\ratking-bloater-skel.pak",
		"world-medicine\\actor97\\ratking-stalker-scaled-skel.pak",
		"world-medicine\\actor97\\ratking-stalker-skel.pak",
		"world-patrol-chalet\\actor97\\jordan-skel.pak",
		"world-patrol-jackson\\actor97\\abby-skel.pak",
		"world-patrol-jackson\\actor97\\alice-skel.pak",
		"world-patrol-jackson\\actor97\\base-baby-skel.pak",
		"world-patrol-jackson\\actor97\\cow-skel.pak",
		"world-patrol-jackson\\actor97\\dog-skel.pak",
		"world-patrol-jackson\\actor97\\gustavo-skel.pak",
		"world-patrol-jackson\\actor97\\leah-skel.pak",
		"world-patrol-jackson\\actor97\\manny-skel.pak",
		"world-patrol-jackson\\actor97\\mel-skel.pak",
		"world-patrol-jackson\\actor97\\nick-skel.pak",
		"world-patrol-jackson\\actor97\\nora-skel.pak",
		"world-patrol-jackson\\actor97\\npc-normal-skel.pak",
		"world-patrol-jackson\\actor97\\owen-skel.pak",
		"world-patrol-jackson\\actor97\\seth-skel.pak",
		"world-patrol\\actor97\\base-female-horde-skel.pak",
		"world-patrol\\actor97\\cab-short-skel-r.pak",
		"world-santa-barbara\\actor97\\prisoner-ian-skel.pak",
		"world-santa-barbara\\actor97\\slaver-matthew-skel.pak",
		"world-santa-barbara\\actor97\\slaver-ryan-skel.pak",
		"world-saving-kids\\actor97\\bird-large-skel-t2.pak",
		"world-saving-kids\\actor97\\carry-plank-skel.pak",
		"world-saving-kids\\actor97\\lev-skel.pak",
		"world-saving-kids\\actor97\\scar-reuben-skel.pak",
		"world-saving-kids\\actor97\\yara-skel.pak",
		"world-seattle-arrival\\actor97\\cab-short-skel-l.pak",
		"world-seattle-arrival\\actor97\\cat-skel.pak",
		"world-seattle-arrival\\actor97\\fish-skel-lrg.pak",
		"world-seattle-arrival\\actor97\\manual-upgrade-skel.pak",
		"world-seattle-arrival\\actor97\\mike-skel.pak",
		"world-seattle-arrival\\actor97\\rifle-strap-inspect-skel.pak",
		"world-theater\\actor97\\backpack-ellie-museum-skel.pak",
		"world-theater\\actor97\\backpack-young-ellie-skel.pak",
		"world-theater\\actor97\\bird-small-skel-t2.pak",
		"world-theater\\actor97\\boar-skel.pak",
		"world-theater\\actor97\\buck-skel.pak",
		"world-theater\\actor97\\fish-skel-tiny.pak",
		"world-tracking-horde\\actor97\\base-male-horde-skel.pak",
		"world-tracking-horde\\actor97\\door-dbl-skel.pak",
		"world-tracking\\actor97\\infected-skel.pak",
		"world-tracking\\actor97\\rope14m-skel.pak",
		"world-watchtower\\actor97\\cab-high-skel-r.pak",
		"world-watchtower\\actor97\\hangmans-noose-2m-body-skel.pak",
		"world-watchtower\\actor97\\shambler-skel.pak",
	],
}

baseSkeletons = {
	"U4": {
		"adventurer": "actor77\\adventurer-base.pak",
		"alcazar": "actor77\\alcazar-base.pak",
		"auctioneer": "actor77\\auctioneer-f-base.pak",
		"avery": "actor77\\avery-base.pak",
		"avery-guard": "actor77\\avery-guard-base.pak",
		"bucket": "actor77\\sco-bucket-base.pak",
		"cassie": "actor77\\cassie-base.pak",
		"crash": "actor77\\crash-base.pak",
		"elena": "actor77\\elena-base.pak",
		"fem": "actor77\\npc-normal-fem-base.pak",
		"-gun": "actor77\\pistol-base.pak",
		"gustavo": "actor77\\gustavo-base.pak",
		"hero": "actor77\\proto.pak",
		"prison-drake": "actor77\\prison-drake-base.pak",
		"jameson": "actor77\\jameson-base.pak",
		"lemur": "actor77\\lemur-base.pak",
		"manager": "actor77\\manager-base.pak",
		"medium": "actor77\\npc-medium-base.pak",
		"monica": "actor77\\monica-base.pak",
		"nadine": "actor77\\nadine-base.pak",
		"pistol": "actor77\\pistol-base.pak",
		"rafe": "actor77\\rafe-base.pak",
		"rifle": "actor77\\rifle-base.pak",
		"samuel": "actor77\\samuel-base.pak",
		"smokey": "actor77\\smokey-base.pak",
		"sull": "actor77\\sullivan-base.pak",
		"tew": "actor77\\tew-base.pak",
		"throw": "actor77\\throwable-base.pak",
		"vargas": "actor77\\vargas-base.pak",
		"young-drake": "actor77\\young-drake-base.pak",
		"young-drake": "actor77\\young-drake-base.pak",
		"young-samuel": "actor77\\young-samuel-base.pak",
	},
	"TLL": {
		"asav": "actor77\\asav-base.pak",
		"chloe": "actor77\\chloe-base.pak",
		"elena": "actor77\\elena-base.pak",
		"hero": "actor77\\proto.pak",
		"horse": "actor77\\horse-base.pak",
		"light": "actor77\\light-base.pak",
		"meenu": "actor77\\meenu-base.pak",
		"monkey": "actor77\\monkey-base.pak",
		"nadine": "actor77\\nadine-base.pak",
		"nadine-dlc": "actor77\\nadine-dlc-base.pak",
		"nilay": "actor77\\nilay-base.pak",
		"kid": "actor77\\npc-kid-base.pak",
		"kid-fem": "actor77\\npc-kid-fem-base.pak",
		"medium": "actor77\\npc-medium-base.pak",
		"normal": "actor77\\npc-normal-base.pak",
		"male-0": "actor77\\npc-normal-crowd-base.pak",
		"female-0": "actor77\\npc-normal-crowd-fem-base.pak",
		"fem": "actor77\\npc-normal-fem-base.pak",
		"orca": "actor77\\orca-base.pak",
		"pistol": "actor77\\pistol-base.pak",
		"prison": "actor77\\prison-drake-base.pak",
		"rifle": "actor77\\rifle-base.pak",
		"samuel": "actor77\\samuel-base.pak",
		"samuel-dlc": "actor77\\samuel-dlc-base.pak",
		"sandy": "actor77\\sandy-base.pak",
		"smokey": "actor77\\smokey-base.pak",
		"sull": "actor77\\sullivan-base.pak",
		"throw": "actor77\\throwable-base.pak",
		"vin": "actor77\\vin-base.pak",
		"waz": "actor77\\waz-base.pak",
	},
	"TLOUP1": {
		"abby": "sp-common\\actor97\\abby-skel.pak",
		"alice": "sp-common\\actor97\\alice-skel.pak",
		"base-female": "sp-common\\actor97\\base-female-skel.pak",
		"base-male": "sp-common\\actor97\\base-male-skel.pak",
		"bill": "sp-common\\actor97\\t1x-bill-skel.pak",
		"bird": "sp-common\\actor97\\bird-medium-skel.pak",
		"bloater": "sp-common\\actor97\\bloater-skel.pak",
		"brute-male": "world-bills\\actor97\\base-brute-male-skel.pak",
		"buck": "sp-common\\actor97\\buck-skel.pak",
		"clicker": "world-mall\\actor97\\clicker-m-pharmacist-skel.pak",
		"david": "sp-common\\actor97\\t1x-david-skel.pak",
		"david": "sp-common\\actor97\\t1x-david-skel.pak",
		"dina": "sp-common\\actor97\\dina-skel.pak",
		"dog": "sp-common\\actor97\\dog-skel.pak",
		"ellie": "sp-common\\actor97\\t1x-ellie-skel.pak",
		"extinguisher": "sp-common\\actor97\\fire-extinguisher-skel.pak",
		"female-crowd": "world-home\\actor97\\base-female-crowd-skel.pak",
		"female-horde": "world-home\\actor97\\base-female-horde-skel.pak",
		"giraffe": "sp-common\\actor97\\giraffe-skel.pak",
		"hare": "sp-common\\actor97\\hare-skel.pak",
		"henry": "sp-common\\actor97\\t1x-henry-skel.pak",
		"hunter": "sp-common\\actor97\\t1x-hunter-m-striker-skel.pak",
		"horse": "sp-common\\actor97\\horse-main-skel.pak",
		"infect": "sp-common\\actor97\\infected-skel.pak",
		"infected-fem": "world-bills\\actor97\\infected-fem-skel.pak",
		"james": "sp-common\\actor97\\t1x-james-skel.pak",
		"jerry": "sp-common\\actor97\\jerry-skel.pak",
		"joel": "sp-common\\actor97\\t1x-joel-skel.pak",
		"male-crowd": "world-home\\actor97\\base-male-crowd-skel.pak",
		"male-horde": "world-home\\actor97\\base-male-horde-skel.pak",
		"manny": "world-bills\\actor97\\manny-skel.pak",
		"maria": "sp-common\\actor97\\t1x-maria-skel.pak",
		"marlene": "sp-common\\actor97\\t1x-marlene-skel.pak",
		"mask": "world-mall\\actor97\\t1x-mask-skel.pak",
		"monkey": "sp-common\\actor97\\t1x-monkey-skel.pak",
		"npc": "sp-common\\actor97\\npc-normal-skel.pak",
		"reporter": "sp-common\\actor97\\texan-f-news-reporter-skel.pak",
		"riley": "sp-common\\actor97\\t1x-riley-skel.pak",
		"robert": "sp-common\\actor97\\t1x-robert-skel.pak",
		"sam": "sp-common\\actor97\\t1x-sam-skel.pak",
		"sarah": "sp-common\\actor97\\t1x-sarah-skel.pak",
		"seth": "world-suburbs\\actor97\\seth-skel.pak",
		"teen": "world-home\\actor97\\base-teen-skel.pak",
		"tess": "sp-common\\actor97\\t1x-tess-skel.pak",
		"tommy": "sp-common\\actor97\\t1x-tommy-skel.pak",
		#"bloater": "world-bills\\actor97\\infected-bloater-skel.pak",
		#"ellie": "sp-common\\actor97\\t1x-ellie-05-skel.pak",
		#"joel": "sp-common\\actor97\\joel-skel.pak",
	},
	"TLOU2": {
		"abby": "world-patrol-jackson\\actor97\\abby-skel.pak",
		"abby-prisoner": "world-medicine\\actor97\\abby-prisoner-skel.pak",
		"alice": "world-patrol-jackson\\actor97\\alice-skel.pak",
		"backpack-ellie-museum": "world-theater\\actor97\\backpack-ellie-museum-skel.pak",
		"backpack-young-ellie": "world-theater\\actor97\\backpack-young-ellie-skel.pak",
		"base-baby": "world-patrol-jackson\\actor97\\base-baby-skel.pak",
		"base-brute-female": "world-find-nora\\actor97\\base-brute-female-skel.pak",
		"base-brute-male": "world-ellie-flashback-patrol\\actor97\\base-brute-male-skel.pak",
		"base-female": "world-flashback-guitar\\actor97\\base-female-skel.pak",
		"base-female-crowd": "world-flashback-guitar\\actor97\\base-female-crowd-skel.pak",
		"base-female-horde": "world-patrol\\actor97\\base-female-horde-skel.pak",
		"base-kid": "world-flashback-guitar\\actor97\\base-kid-skel.pak",
		"base-kid-female": "world-farm\\actor97\\base-kid-female-skel.pak",
		"base-male": "common\\actor97\\base-male-skel.pak",
		"base-male-crowd": "world-flashback-guitar\\actor97\\base-male-crowd-skel.pak",
		"base-male-horde": "world-tracking-horde\\actor97\\base-male-horde-skel.pak",
		"base-teen": "world-flashback-guitar\\actor97\\base-teen-skel.pak",
		"bird-large": "world-saving-kids\\actor97\\bird-large-skel-t2.pak",
		"bird-medium-t2": "world-flashback-guitar\\actor97\\bird-medium-skel-t2.pak",
		"bird-small": "world-forward-base\\actor97\\bird-small-skel.pak",
		"bird-small": "world-theater\\actor97\\bird-small-skel-t2.pak",
		"bird-tiny": "world-forward-base\\actor97\\bird-tiny-skel.pak",
		"bird-xlarge-t2": "world-find-nora\\actor97\\bird-xlarge-skel-t2.pak",
		"bloater": "world-ellie-flashback-patrol\\actor97\\bloater-skel.pak",
		"boar": "world-theater\\actor97\\boar-skel.pak",
		"buck": "world-theater\\actor97\\buck-skel.pak",
		"cab-high": "world-watchtower\\actor97\\cab-high-skel-r.pak",
		"cab-high-l": "world-flooded-city\\actor97\\cab-high-skel-l.pak",
		"cab-short": "world-seattle-arrival\\actor97\\cab-short-skel-l.pak",
		"cab-short-r": "world-patrol\\actor97\\cab-short-skel-r.pak",
		"carry-plank": "world-saving-kids\\actor97\\carry-plank-skel.pak",
		"cat": "world-seattle-arrival\\actor97\\cat-skel.pak",
		"chicken": "world-forward-base\\actor97\\chicken-skel.pak",
		"cow": "world-patrol-jackson\\actor97\\cow-skel.pak",
		"dina": "world-flashback-guitar\\actor97\\dina-skel.pak",
		"doe": "world-flashback-guitar\\actor97\\doe-skel.pak",
		"dog": "world-patrol-jackson\\actor97\\dog-skel.pak",
		"dog-crowd": "world-forward-base\\actor97\\dog-crowd-skel.pak",
		"door": "world-flashback-guitar\\actor97\\door-skel.pak",
		"door-dbl": "world-tracking-horde\\actor97\\door-dbl-skel.pak",
		"drawer": "world-flashback-guitar\\actor97\\drawer-skel.pak",
		"ellie": "common\\actor97\\ellie-skel.pak",
		"ellie-14": "world-flashback-guitar\\actor97\\ellie-14-skel.pak",
		"ellie-festival-strand-hair-cloth": "sp-common\\actor97\\ellie-festival-strand-hair-cloth-skel.pak",
		"ellie-santa-barbara-hair-cloth": "sp-common\\actor97\\ellie-santa-barbara-hair-cloth-skel.pak",
		"ellie-seattle-hoodie-string": "sp-common\\actor97\\ellie-seattle-hoodie-string-skel.pak",
		"festival-partner": "world-farm\\actor97\\festival-partner-skel.pak",
		"fish": "world-seattle-arrival\\actor97\\fish-skel-lrg.pak",
		"fish-sml": "world-forward-base\\actor97\\fish-skel-sml.pak",
		"fish-tiny": "world-theater\\actor97\\fish-skel-tiny.pak",
		"frog": "world-find-nora\\actor97\\frog-skel.pak",
		"guitar": "world-flashback-guitar\\actor97\\guitar-skel.pak",
		"gustavo": "world-patrol-jackson\\actor97\\gustavo-skel.pak",
		"halloween-a-hanging": "world-forward-base\\actor97\\halloween-skeleton-a-hanging.pak",
		"hangmans-noose-2m": "world-watchtower\\actor97\\hangmans-noose-2m-body-skel.pak",
		"horse": "world-flashback-guitar\\actor97\\horse-skel.pak",
		"horse-crowd": "world-forward-base\\actor97\\horse-crowd-skel.pak",
		"horse-main": "world-flashback-guitar\\actor97\\horse-main-skel.pak",
		"horse-main-rein-cloth": "sp-common\\actor97\\horse-main-rein-cloth-skel.pak",
		"horse-main-stirrups": "sp-common\\actor97\\horse-main-stirrups-skel.pak",
		"horse-mane-cloth": "sp-common\\actor97\\horse-mane-cloth-skel.pak",
		"horse-saddle-bag-straps-cloth": "sp-common\\actor97\\horse-saddle-bag-straps-cloth-skel.pak",
		"horse-saddle-strap-cloth": "sp-common\\actor97\\horse-saddle-strap-cloth-skel.pak",
		"horse-tail-cloth": "sp-common\\actor97\\horse-tail-cloth-skel.pak",
		"infected-bloater": "world-ellie-flashback-patrol\\actor97\\infected-bloater-skel.pak",
		"infected-skel": "world-tracking\\actor97\\infected-skel.pak",
		"isaac": "world-forward-base\\actor97\\isaac-skel.pak",
		"jerry": "world-flashback-guitar\\actor97\\jerry-skel.pak",
		"jesse": "world-flashback-guitar\\actor97\\jesse-skel.pak",
		"joel": "world-flashback-guitar\\actor97\\joel-skel.pak",
		"jordan": "world-patrol-chalet\\actor97\\jordan-skel.pak",
		"leah": "world-patrol-jackson\\actor97\\leah-skel.pak",
		"lev": "world-saving-kids\\actor97\\lev-skel.pak",
		"lev-jacket-cloth": "sp-common\\actor97\\lev-jacket-cloth-skel.pak",
		"light": "common\\actor97\\light-skel.pak",
		"manny": "world-patrol-jackson\\actor97\\manny-skel.pak",
		"manual-upgrade": "world-seattle-arrival\\actor97\\manual-upgrade-skel.pak",
		"manual-upgrade-magazine-righthand": "common\\actor97\\manual-upgrade-magazine-righthand-skel.pak",
		"maria": "world-flashback-guitar\\actor97\\maria-skel.pak",
		"marlene": "world-abby-flashback-dad\\actor97\\marlene-skel.pak",
		"med-hosp-female-a": "world-medicine\\actor97\\med-hosp-skeleton-female-a.pak",
		"med-hosp-male-a": "world-find-nora\\actor97\\med-hosp-skeleton-male-a.pak",
		"mel": "world-patrol-jackson\\actor97\\mel-skel.pak",
		"mike": "world-seattle-arrival\\actor97\\mike-skel.pak",
		"military-truck-modern": "world-flooded-city\\actor97\\military-truck-modern-skel.pak",
		"militia-mannysdad": "world-forward-base\\actor97\\militia-mannysdad-skel.pak",
		"militia-whitney": "world-find-nora\\actor97\\militia-whitney-skel.pak",
		"nick": "world-patrol-jackson\\actor97\\nick-skel.pak",
		"nora": "world-patrol-jackson\\actor97\\nora-skel.pak",
		"npc-brute": "world-find-nora\\actor97\\npc-brute-skel.pak",
		"npc-normal": "world-patrol-jackson\\actor97\\npc-normal-skel.pak",
		"owen": "world-patrol-jackson\\actor97\\owen-skel.pak",
		"prisoner-ian": "world-santa-barbara\\actor97\\prisoner-ian-skel.pak",
		"ratking-bloater": "world-medicine\\actor97\\ratking-bloater-skel.pak",
		"ratking-stalker": "world-medicine\\actor97\\ratking-stalker-skel.pak",
		"ratking-stalker-scaled": "world-medicine\\actor97\\ratking-stalker-scaled-skel.pak",
		"rifle-strap-inspect": "world-seattle-arrival\\actor97\\rifle-strap-inspect-skel.pak",
		"rope14m": "world-tracking\\actor97\\rope14m-skel.pak",
		"scar-chris": "world-forward-base\\actor97\\scar-chris-skel.pak",
		"scar-colin": "world-abby-fights-militia\\actor97\\scar-colin-skel.pak",
		"scar-emily": "world-forward-base\\actor97\\scar-emily-skel.pak",
		"scar-reuben": "world-saving-kids\\actor97\\scar-reuben-skel.pak",
		"sea-lion": "world-forward-base\\actor97\\sea-lion-skel.pak",
		"seth": "world-patrol-jackson\\actor97\\seth-skel.pak",
		"shambler": "world-watchtower\\actor97\\shambler-skel.pak",
		"sheep-adult": "world-forward-base\\actor97\\sheep-adult-skel.pak",
		"sheep-lamb": "world-farm\\actor97\\sheep-lamb-skel.pak",
		"slaver-matthew": "world-santa-barbara\\actor97\\slaver-matthew-skel.pak",
		"slaver-ryan": "world-santa-barbara\\actor97\\slaver-ryan-skel.pak",
		"t1-npc-normal-old": "world-flashback-guitar\\actor97\\t1-npc-normal-skel-old.pak",
		"tommy": "world-flashback-guitar\\actor97\\tommy-skel.pak",
		"yara": "world-saving-kids\\actor97\\yara-skel.pak",
		"young-abby": "world-flooded-city\\actor97\\young-abby-skel.pak",
		"zebra": "world-abby-flashback-dad\\actor97\\zebra-skel.pak",
		"zebra-baby": "world-abby-flashback-dad\\actor97\\zebra-baby-skel.pak",
	},
}

dxFormat = {
	0: "Invalid",
	2: "R32G32B32A32_Float",
	3: "R32G32B32A32_Uint",
	4: "R32G32B32A32_Sint",
	6: "R32G32B32_Float",
	7: "R32G32B32_Uint",
	8: "R32G32B32_Sint",
	0xA: "R16G16B16A16_Float",
	0xB: "R16G16B16A16_Unorm",
	0xC: "R16G16B16A16_Uint",
	0xD: "R16G16B16A16_Snorm",
	0xE: "R16G16B16A16_Sint",
	0x10: "R32G32_Float",
	0x11: "R32G32_Uint",
	0x12: "R32G32_Sint",
	0x13: "R32G8X24",
	0x14: "D32S8X24",
	0x15: "R32X8X24",
	0x16: "X32G8X24",
	0x18: "R10G10B10A2_Unorm",
	0x19: "R10G10B10A2_Uint",
	0x1A: "R11G11B10_Float",
	0x1C: "R8G8B8A8_Unorm",
	0x1D: "R8G8B8A8_UnormSrgb",
	0x1E: "R8G8B8A8_Uint",
	0x1F: "R8G8B8A8_Snorm",
	0x20: "R8G8B8A8_Sint",
	0x22: "R16G16_Float",
	0x23: "R16G16_Unorm",
	0x24: "R16G16_Uint",
	0x25: "R16G16_Snorm",
	0x26: "R16G16_Sint",
	0x27: "R32Typeless",
	0x28: "D32_Float",
	0x29: "R32_Float",
	0x2A: "R32_Uint",
	0x2B: "R32_Sint",
	0x2C: "R24G8_Typeless",
	0x2D: "D24S8",
	0x2E: "R24X8_Unorm",
	0x2F: "X24G8",
	0x31: "R8G8_Unorm",
	0x32: "R8G8_Uint",
	0x33: "R8G8_Snorm",
	0x34: "R8G8_Sint",
	0x35: "R16_Typeless",
	0x36: "R16_Float",
	0x37: "D16_Unorm",
	0x38: "R16_Unorm",
	0x39: "R16_Uint",
	0x3A: "R16_Snorm",
	0x3B: "R16_Sint",
	0x3D: "R8_Unorm",
	0x3E: "R8_Uint",
	0x3F: "R8_Snorm",
	0x40: "R8_Sint",
	0x41: "A8_Unorm",
	0x42: "R1_Unorm",
	0x46: "Bc1_Typeless",
	0x47: "Bc1_Unorm",
	0x48: "Bc1_UnormSrgb",
	0x49: "Bc2_Typeless",
	0x4A: "Bc2_Unorm",
	0x4B: "Bc2_UnormSrgb",
	0x4C: "Bc3_Typeless",
	0x4D: "Bc3_Unorm",
	0x4E: "Bc3_UnormSrgb",
	0x4F: "Bc4_Typeless",
	0x50: "Bc4_Unorm",
	0x51: "Bc4_Snorm",
	0x52: "Bc5_Typeless",
	0x53: "Bc5_Unorm",
	0x54: "Bc5_Snorm",
	0x55: "B5G6R5_Unorm",
	0x56: "B5G5R5A1_Unorm",
	0x57: "B8G8R8A8_Unorm",
	0x58: "B8G8R8X8_Unorm",
	0x59: "R10G10B10A2_Unorm_2",
	0x5A: "B8G8R8A8_Unorm_2",
	0x5B: "B8G8R8A8_UnormSrgb",
	0x5C: "B8G8R8X8_Typeless",
	0x5D: "B8G8R8X8_UnormSrgb",
	0x5E: "Bc6Typeless",
	0x5F: "Bc6_Uf16",
	0x60: "Bc6_Sf16",
	0x61: "Bc7_Typeless",
	0x62: "Bc7_Unorm",
	0x63: "Bc7_UnormSrgb",
	0x64: "B16G16R16A16_Float" 
}

gdRawDataStarts = {
	"U4": {
		"All": {
			"global-dict.pak":  940048,
			"global-dict-1.pak":  1083904,
			"global-dict-2.pak":  959456,
			"global-dict-3.pak":  1041088,
			"global-dict-4.pak":  924576,
			"global-dict-5.pak":  1013456,
			"global-dict-6.pak":  781216,
			"global-dict-7.pak":  740640,
			"global-dict-8.pak":  853104,
			"global-dict-9.pak":  551888,
			"global-dict-10.pak":  301056,
			"global-dict-11.pak":  923936,
			"global-dict-12.pak":  850656,
			"global-dict-13.pak":  839584,
			"global-dict-14.pak":  229456,
			"global-dict-15.pak":  227216,
			"global-dict-16.pak":  277968,
			"global-dict-17.pak":  192960,
			"global-dict-18.pak":  448832,
			"global-dict-19.pak":  506752,
			"global-dict-20.pak":  391920,
		},
	},
	"TLL": {
		"All": {
			"global-dict.pak": 1040608,
			"global-dict-1.pak": 949568,
			"global-dict-2.pak": 1081104,
			"global-dict-3.pak": 574688,
			"global-dict-4.pak": 748944,
			"global-dict-5.pak": 546608,
			"global-dict-6.pak": 1074032,
			"global-dict-7.pak": 911984,
			"global-dict-8.pak": 247632,
			"global-dict-9.pak": 131072,
			"global-dict-10.pak": 140048,
			"global-dict-11.pak": 488656,
			"global-dict-12.pak": 79440,
		},
	},
	"TLOUP1": {
		"common": {
			"common-dict.pak": 490768,
		},
		"sp-common": {
			"sp-common-dict-1.pak": 1308752,
			"sp-common-dict-2.pak": 1312512,
			"sp-common-dict-3.pak": 1179152,
			"sp-common-dict.pak": 1568992,
		},
		"world-bills": {
			"world-bills-dict-1.pak": 707792,
			"world-bills-dict.pak": 1335136,
		},
		"world-game-start": {
			"world-game-start-dict.pak": 41680,
		},
		"world-home": {
			"world-home-dict-1.pak": 1099808,
			"world-home-dict-2.pak": 248576,
			"world-home-dict.pak": 1250192,
		},
		"world-hunter-city": {
			"world-hunter-city-dict-1.pak": 1020592,
			"world-hunter-city-dict-2.pak": 316576,
			"world-hunter-city-dict-3.pak": 1371984,
			"world-hunter-city-dict-4.pak": 17552,
			"world-hunter-city-dict.pak": 1406560,
		},
		"world-lab": {
			"world-lab-dict.pak": 329248,
		},
		"world-lakeside": {
			"world-lakeside-dict-1.pak": 481088,
			"world-lakeside-dict.pak": 1212656,
		},
		"world-mall": {
			"world-mall-dict-1.pak": 1084928,
			"world-mall-dict-2.pak": 209008,
			"world-mall-dict.pak": 1378112,
		},
		"world-military-city": {
			"world-military-city-dict-1.pak": 1205728,
			"world-military-city-dict-2.pak": 634832,
			"world-military-city-dict.pak": 1291008,
		},
		"world-outskirts": {
			"world-outskirts-dict-1.pak": 686208,
			"world-outskirts-dict-2.pak": 689200,
			"world-outskirts-dict.pak": 1352992,
		},
		"world-suburbs": {
			"world-suburbs-dict-1.pak": 229472,
			"world-suburbs-dict.pak": 1078272,
		},
		"world-tommys-dam": {
			"world-tommys-dam-dict-1.pak": 422544,
			"world-tommys-dam-dict.pak": 810576,
		},
		"world-university": {
			"world-university-dict.pak": 301072,
		},
		"world-wild": {
			"world-wild-dict.pak": 440240,
		},
	},
	"TLOU2": {
		"common": {
			"common-dict.pak": 617216,
		},
		"sp-common": {
			"sp-common-dict.pak": 1117024,
		},
		"world-abby-ellie-fight": {
			"world-abby-ellie-fight-dict.pak": 328144,
		},
		"world-abby-fights-militia": {
			"world-abby-fights-militia-dict.pak": 535872,
		},
		"world-abby-flashback-dad": {
			"world-abby-flashback-dad-dict.pak": 323760,
		},
		"world-amputation": {
			"world-amputation-dict.pak": 274256,
		},
		"world-ellie-flashback-museum": {
			"world-ellie-flashback-museum-dict.pak": 508400,
		},
		"world-ellie-flashback-patrol": {
			"world-ellie-flashback-patrol-dict.pak": 252752,
		},
		"world-ellie-flashback-ultimatum": {
			"world-ellie-flashback-ultimatum-dict.pak": 198304,
		},
		"world-epilogue": {
			"world-epilogue-dict.pak": 12448,
		},
		"world-farm": {
			"world-farm-dict.pak": 617776,
		},
		"world-find-aquarium": {
			"world-find-aquarium-dict.pak": 205712,
		},
		"world-find-nora": {
			"world-find-nora-dict-1.pak": 548432,
			"world-find-nora-dict.pak": 1065968,
		},
		"world-flashback-guitar": {
			"world-flashback-guitar-dict-1.pak": 1639248,
			"world-flashback-guitar-dict-2.pak": 148448,
			"world-flashback-guitar-dict.pak": 1811392,
		},
		"world-flooded-city": {
			"world-flooded-city-dict.pak": 1540400,
		},
		"world-forward-base": {
			"world-forward-base-dict-1.pak": 858688,
			"world-forward-base-dict.pak": 1570704,
		},
		"world-game-start": {
			"world-game-start-dict.pak": 544,
		},
		"world-jordan-escape": {
			"world-jordan-escape-dict.pak": 1065920,
		},
		"world-medicine": {
			"world-medicine-dict-1.pak": 291872,
			"world-medicine-dict.pak": 1281248,
		},
		"world-patrol": {
			"world-patrol-dict.pak": 1046272,
		},
		"world-patrol-chalet": {
			"world-patrol-chalet-dict.pak": 380128,
		},
		"world-patrol-departure": {
			"world-patrol-departure-dict.pak": 259680,
		},
		"world-patrol-jackson": {
			"world-patrol-jackson-dict.pak": 1737472,
		},
		"world-rescue-jesse": {
			"world-rescue-jesse-dict.pak": 1281008,
		},
		"world-santa-barbara": {
			"world-santa-barbara-dict.pak": 1102624,
		},
		"world-save-lev": {
			"world-save-lev-dict.pak": 909840,
		},
		"world-saving-kids": {
			"world-saving-kids-dict.pak": 655632,
		},
		"world-seattle-arrival": {
			"world-seattle-arrival-dict.pak": 1914512,
		},
		"world-theater": {
			"world-theater-dict.pak": 200752,
		},
		"world-theater-ambush": {
			"world-theater-ambush-dict.pak": 138256,
		},
		"world-tracking": {
			"world-tracking-dict.pak": 656848,
		},
		"world-tracking-horde": {
			"world-tracking-horde-dict.pak": 257840,
		},
		"world-watchtower": {
			"world-watchtower-dict-1.pak": 655024,
			"world-watchtower-dict.pak": 1854112,
		},
	},
}
		
DoubleClickTimer = namedtuple("DoubleClickTimer", "name idx timer")

class openOptionsDialogWindow:
	
	def __init__(self, width=dialogOptions.width, height=dialogOptions.height, args=[]):
		global dialogOptions
		
		self.width = width
		self.height = height
		self.pak = args.get("pak") or None
		self.path = self.pak.path or rapi.getInputName()
		self.name = rapi.getLocalFileName(self.path)
		self.loadItems = [self.name]
		self.fullLoadItems = [self.path]
		self.localDir = rapi.getDirForFilePath(self.path)
		self.localRoot = findRootDir(self.path)
		self.baseDir = BaseDirectories[gameName] 
		self.allFiles = []
		self.pakFiles = []
		self.subDirs = []
		self.pakIdx = 0
		self.baseIdx = -1
		self.loadIdx = 0
		self.dirIdx = 0
		self.gameIdx = 0
		self.localIdx = 0
		self.isOpen = True
		self.isCancelled = False
		dialogOptions.currentDir = self.localDir
		self.currentDirTxt = dialogOptions.currentDir
		self.clicker = DoubleClickTimer(name="", idx=0, timer=0)
		dialogOptions.dialog = self
		
	def setWidthAndHeight(self, width=dialogOptions.width, height=dialogOptions.width):
		self.width = width or self.width
		self.height = height or self.height
		
	def openOptionsButtonLoadEntry(self, noeWnd, controlId, wParam, lParam):
		self.isOpen = False
		self.noeWnd.closeWindow()
			
	def openOptionsButtonCancel(self, noeWnd, controlId, wParam, lParam):
		self.isCancelled = True
		self.isOpen = False
		#self.pak.dumpGlobalVramHashes()
		self.noeWnd.closeWindow()
		
	def openOptionsButtonParentDir(self, noeWnd, controlId, wParam, lParam):
		if self.localIdx == 0: 
			self.localRoot = os.path.dirname(self.localRoot)
		else:
			self.baseDir = os.path.dirname(self.baseDir)
		self.setDirList()
		self.setPakList()
		if self.subDirs:
			self.dirList.selectString(self.subDirs[0])
	
	def selectBaseListItem(self, noeWnd, controlId, wParam, lParam):
		self.baseIdx = self.baseList.getSelectionIndex()
		dialogOptions.baseSkeleton = self.baseList.getStringForIndex(self.baseIdx)
		
	def selectPakListItem(self, noeWnd, controlId, wParam, lParam):
		self.pakIdx = self.pakList.getSelectionIndex()
		if self.clicker.name == "pakList" and self.pakIdx == self.clicker.idx and time.time() - self.clicker.timer < 0.25:
			if self.pakIdx == 0: #parent directory
				if dialogOptions.currentDir[-1:] == "\\":
					dialogOptions.currentDir = os.path.dirname(dialogOptions.currentDir)
				dialogOptions.currentDir = os.path.dirname(dialogOptions.currentDir)
				self.setPakList()
			elif self.pakIdx <= len(self.subDirs):
				dialogOptions.currentDir += "\\" + self.pakList.getStringForIndex(self.pakIdx)
				self.setPakList()
			elif self.pakList.getStringForIndex(self.pakIdx) not in self.loadItems:
				self.loadItems.append(self.pakList.getStringForIndex(self.pakIdx))
				self.fullLoadItems.append(dialogOptions.currentDir + self.pakList.getStringForIndex(self.pakIdx))
				self.loadList.addString(self.pakList.getStringForIndex(self.pakIdx))
				self.fullLoadItems = [x for _, x in sorted(zip(self.loadItems, self.fullLoadItems))]
				self.loadItems = sorted(self.loadItems)
		self.clicker = DoubleClickTimer(name="pakList", idx=self.pakIdx, timer=time.time())
	
	def selectLoadListItem(self, noeWnd, controlId, wParam, lParam):
		self.loadIdx = self.loadList.getSelectionIndex()
		if self.clicker.name == "loadList" and self.loadIdx == self.clicker.idx and time.time() - self.clicker.timer < 0.25 and self.loadItems[self.loadIdx] != self.name:
			self.loadList.removeString(self.loadItems[self.loadIdx])
			del self.loadItems[self.loadIdx]
			del self.fullLoadItems[self.loadIdx]
			self.loadIdx = self.loadIdx if self.loadIdx < len(self.loadItems) else self.loadIdx - 1
			self.loadList.selectString(self.loadItems[self.loadIdx])
			self.fullLoadItems = [x for _, x in sorted(zip(self.loadItems, self.fullLoadItems))]
			self.loadItems = sorted(self.loadItems)
		self.clicker = DoubleClickTimer(name="loadList", idx=self.loadIdx, timer=time.time())
	
	def selectGameBoxItem(self, noeWnd, controlId, wParam, lParam):
		global gameName
		if self.gameIdx != self.gameBox.getSelectionIndex():
			self.gameIdx = self.gameBox.getSelectionIndex()
			gameName = gamesList[self.gameIdx]
			restOfPath = dialogOptions.currentDir.replace(self.baseDir, "")
			self.baseDir = BaseDirectories[gameName]
			if self.localBox.getStringForIndex(self.localIdx) == "Base Directory":
				dialogOptions.currentDir = self.baseDir
				if restOfPath and os.path.isdir(self.baseDir + restOfPath):
					dialogOptions.currentDir = self.baseDir + restOfPath
				self.setPakList()
				
	def selectLocalBoxItem(self, noeWnd, controlId, wParam, lParam):
		if self.localIdx != self.localBox.getSelectionIndex():
			self.localIdx = self.localBox.getSelectionIndex()
			restOfPath = dialogOptions.currentDir.replace(self.localRoot, "").replace(self.baseDir, "")
			if self.localBox.getStringForIndex(self.localIdx) == "Base Directory":
				dialogOptions.currentDir = self.baseDir
				if restOfPath and os.path.isdir(self.baseDir + restOfPath):
					dialogOptions.currentDir = self.baseDir + restOfPath
			else:
				dialogOptions.currentDir = os.path.dirname(self.path)
				if restOfPath and os.path.isdir(self.localRoot + restOfPath):
					dialogOptions.currentDir = self.localRoot + restOfPath
			self.setPakList()
			
	def setBaseList(self, list_object=None, current_item=None):
		#current_item = current_item or baseSkeletons[gameName]["chloe" if gameName == "TLL" else "ellie" if gameName=="TLOU2" else "hero"]
		for path in skelFiles[gameName]:
			self.baseList.addString(path)
		lastFoundHint = ""
		for hint, fileName in baseSkeletons[gameName].items():
			if self.name.find(hint) != -1 and len(hint) > len(lastFoundHint):
				lastFoundHint = hint
				#print(fileName)
				#print(baseSkeletons[gameName])
				self.baseList.selectString(fileName)
				self.baseIdx = self.baseList.getSelectionIndex()
				dialogOptions.baseSkeleton = fileName
		
	def setGameBox(self, list_object=None, current_item=None):
		for i, name in enumerate(fullGameNames):
			self.gameBox.addString(name)
		self.gameBox.selectString(fullGameNames[gamesList.index(gameName)])
		self.gameIdx = self.gameBox.getSelectionIndex()
		
	def setLocalBox(self, list_object=None, current_item=None):
		for name in ["Local Folder", "Base Directory"]:
			self.localBox.addString(name)
		self.localBox.selectString("Local Folder")
		self.localIdx = self.localBox.getSelectionIndex()
	
	def checkLoadTexCheckbox(self, noeWnd, controlId, wParam, lParam):
		dialogOptions.doLoadTex = not dialogOptions.doLoadTex
		self.loadTexCheckbox.setChecked(dialogOptions.doLoadTex)
		
	def checkBaseCheckbox(self, noeWnd, controlId, wParam, lParam):
		dialogOptions.doLoadBase = not dialogOptions.doLoadBase
		self.loadBaseCheckbox.setChecked(dialogOptions.doLoadBase)
		
	def checkLODsCheckbox(self, noeWnd, controlId, wParam, lParam):
		dialogOptions.doLODs = not dialogOptions.doLODs
		self.LODsCheckbox.setChecked(dialogOptions.doLODs)
		
	def checkConvTexCheckbox(self, noeWnd, controlId, wParam, lParam):
		dialogOptions.doConvertTex = not dialogOptions.doConvertTex
		self.convTexCheckbox.setChecked(dialogOptions.doConvertTex)
		
	def checkFlipUVsCheckbox(self, noeWnd, controlId, wParam, lParam):
		dialogOptions.doFlipUVs = not dialogOptions.doFlipUVs
		self.flipUVsCheckbox.setChecked(dialogOptions.doFlipUVs)
		
	def checkLoadAllTexCheckbox(self, noeWnd, controlId, wParam, lParam):
		dialogOptions.loadAllTextures = not dialogOptions.loadAllTextures
		self.loadAllTexCheckbox.setChecked(dialogOptions.loadAllTextures)
		
	def checkReparentCheckbox(self, noeWnd, controlId, wParam, lParam):
		dialogOptions.reparentHelpers = not dialogOptions.reparentHelpers
		self.reparentCheckbox.setChecked(dialogOptions.reparentHelpers)
		
	def setLoadList(self):
		for item in self.loadItems:
			self.loadList.removeString(item)
		self.loadItems = [self.name]
		self.loadList.addString(self.loadItems[0])
		self.loadList.selectString(self.pak.path or rapi.getInputName())
		
	def setPakList(self):
		for name in self.allFiles:
			self.pakList.removeString(name)
		self.allFiles = [".."]
		self.pakFiles = []
		self.subDirs = []
		for item in os.listdir(dialogOptions.currentDir):
			if os.path.isdir(os.path.join(dialogOptions.currentDir, item)):
				self.subDirs.append(item)
			if os.path.isfile(os.path.join(dialogOptions.currentDir, item)) and item.find(".pak") != -1:
				self.pakFiles.append(item)
		self.subDirs = sorted(self.subDirs)
		self.pakFiles = sorted(self.pakFiles)
		self.allFiles.extend(self.subDirs)
		self.allFiles.extend(self.pakFiles)
		for item in self.allFiles:
			self.pakList.addString(item)
		if self.name in self.allFiles:
			self.pakIdx = self.allFiles.index(self.name)
			self.pakList.selectString(self.name)
		elif self.pakIdx < len(self.allFiles):
			self.pakList.selectString(self.pakList.getStringForIndex(self.pakIdx))
		else:
			self.pakIdx = 0
			self.pakList.selectString(self.pakList.getStringForIndex(0))
		self.currentDirEditBox.setText(dialogOptions.currentDir)
		
	def inputCurrentDirEditBox(self, noeWnd, controlId, wParam, lParam):
		if self.currentDirEditBox.getText() != dialogOptions.currentDir and os.path.isdir(self.currentDirEditBox.getText()):
			dialogOptions.currentDir = self.currentDirEditBox.getText()
			self.setPakList()
			
	def inputGlobalScaleEditBox(self, noeWnd, controlId, wParam, lParam):
		global GlobalScale
		try:
			if self.globalScaleEditBox.getText():
				newScale = float(self.globalScaleEditBox.getText())
				if newScale:
					GlobalScale = newScale
		except ValueError:
			print("Non-numeric scale input, resetting to ", GlobalScale)
			self.globalScaleEditBox.setText(str(GlobalScale))
			
	def create(self, width=dialogOptions.width, height=dialogOptions.height):
		self.noeWnd = noewin.NoeUserWindow("Naughty Dog .pak Tool:        " + rapi.getLocalFileName(self.name), "HTRAWWindowClass", width, height) 
		noeWindowRect = noewin.getNoesisWindowRect()
		if noeWindowRect:
			windowMargin = 100
			self.noeWnd.x = noeWindowRect[0] + windowMargin
			self.noeWnd.y = noeWindowRect[1] + windowMargin  
		return self.noeWnd.createWindow()
	
	def createPakWindow(self, width=dialogOptions.width, height=dialogOptions.height):
		
		if self.create(width, height):
			self.noeWnd.setFont("Futura", 14)
			
			self.noeWnd.createStatic("Base:", 10, 7, width-20, 20)
			index = self.noeWnd.createComboBox(50, 5, width-65, 20, self.selectBaseListItem, noewin.CBS_DROPDOWNLIST) #CB
			self.baseList = self.noeWnd.getControlByIndex(index)
			
			self.noeWnd.createStatic("Files from:", 5, 45, width-20, 20)
			index = self.noeWnd.createEditBox(5, 65, width-20, 45, dialogOptions.currentDir, self.inputCurrentDirEditBox, False) #EB
			self.currentDirEditBox = self.noeWnd.getControlByIndex(index)
			
			#LBS_NOTIFY | WS_VSCROLL | WS_BORDER
			index = self.noeWnd.createListBox(5, 120, width-20, 380, self.selectPakListItem, noewin.LBS_NOTIFY | noewin.WS_VSCROLL | noewin.WS_BORDER) #LB
			self.pakList = self.noeWnd.getControlByIndex(index)
			
			self.noeWnd.createStatic("Files to load:", 5, 505, width-20, 20)
			index = self.noeWnd.createListBox(5, 525, width-20, 150, self.selectLoadListItem, noewin.CBS_DROPDOWNLIST) #LB
			self.loadList = self.noeWnd.getControlByIndex(index)
			
			
			if True:
				index = self.noeWnd.createCheckBox("Load Textures", 10, 685, 130, 30, self.checkLoadTexCheckbox)
				self.loadTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.loadTexCheckbox.setChecked(dialogOptions.doLoadTex)
				
				
				index = self.noeWnd.createCheckBox("Load All Textures", 150, 685, 160, 30, self.checkLoadAllTexCheckbox)
				self.loadAllTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.loadAllTexCheckbox.setChecked(dialogOptions.loadAllTextures)
				
				
				index = self.noeWnd.createCheckBox("Convert Textures", 10, 715, 130, 30, self.checkConvTexCheckbox)
				self.convTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.convTexCheckbox.setChecked(dialogOptions.doConvertTex)
				
				
				#index = self.noeWnd.createCheckBox("Flip UVs", 140, 680, 130, 30, self.checkFlipUVsCheckbox)
				#self.flipUVsCheckbox = self.noeWnd.getControlByIndex(index)
				#self.flipUVsCheckbox.setChecked(dialogOptions.doFlipUVs)
				
				
				index = self.noeWnd.createCheckBox("Load Base", 150, 715, 90, 30, self.checkBaseCheckbox)
				self.loadBaseCheckbox = self.noeWnd.getControlByIndex(index)
				self.loadBaseCheckbox.setChecked(dialogOptions.doLoadBase)
				
				if ReparentHelpers == 2:
					dialogOptions.reparentHelpers = (dialogOptions.isTLOU2 or dialogOptions.isTLOUP1)
				index = self.noeWnd.createCheckBox("Reparent Helpers", 10, 750, 130, 20, self.checkReparentCheckbox)
				self.reparentCheckbox = self.noeWnd.getControlByIndex(index)
				self.reparentCheckbox.setChecked(dialogOptions.reparentHelpers)
				
				index = self.noeWnd.createCheckBox("Import LODs", 150, 745, 100, 30, self.checkLODsCheckbox)
				self.LODsCheckbox = self.noeWnd.getControlByIndex(index)
				self.LODsCheckbox.setChecked(dialogOptions.doLODs)
				

			self.noeWnd.createStatic("Game:", width-218, 690, 60, 20)
			index = self.noeWnd.createComboBox(width-170, 685, 150, 20, self.selectGameBoxItem, noewin.CBS_DROPDOWNLIST) #CB
			self.gameBox = self.noeWnd.getControlByIndex(index)
			
			self.noeWnd.createStatic("View:", width-210, 720, 60, 20)
			index = self.noeWnd.createComboBox(width-170, 715, 150, 20, self.selectLocalBoxItem, noewin.CBS_DROPDOWNLIST) #CB
			self.localBox = self.noeWnd.getControlByIndex(index)
			
			self.noeWnd.createStatic("Scale:", width-215, 750, 60, 20)
			index = self.noeWnd.createEditBox(width-170, 750, 80, 20, str(GlobalScale), self.inputGlobalScaleEditBox, False) #EB
			self.globalScaleEditBox = self.noeWnd.getControlByIndex(index)
			
			self.noeWnd.createButton("Load", 5, height-70, width-160, 30, self.openOptionsButtonLoadEntry)
			self.noeWnd.createButton("Cancel", width-96, height-70, 80, 30, self.openOptionsButtonCancel)
			
			self.setLoadList()
			self.setBaseList(self.baseList)
			self.setPakList()
			self.setGameBox(self.gameBox)
			self.setLocalBox(self.localBox)
			
			self.noeWnd.doModal()
			
TP1_pakStringIDs = {
	0x50CAF5257D6A140B: "JOINT_HIERARCHY",
	0x349D779A792F45C1: "GEOMETRY_1",
	0xCE3ADE693131B309: "VRAM_DESC",
	0xE7254422A7A8F476: "VRAM_DESC_TABLE",
	0xA2481DA1A5D2CE2B: "TEXTURE_TABLE",
	0x36125D3CFB7F3991: "TEXTURE_DICTIONARY",
	0x4903731234F1BEA6: "PAK_LOGIN_TABLE",
	0x61DE7E6141BC6F2B: "EFFECT_TABLE",
	0x460F497540A29F73: "SPAWNER_GROUP",
	0x596A72779C4C87D: "TAG_INT",
	0x53DE1E1977F9CBA4: "ANIM_GROUP",
	0x791137002DB17EBB: "MATERIAL_TABLE_1",
	0x384ADF724B123839: "FOREGROUND_SECTION_2",
	0x5ADB4A2D2E2A6EB: "COLLISION_DATA_CLOTH",
	0x3A3BB43D817C93DE: "TAG_VEC4",
	0x35EB8812D3A2D576: "TAG_FLOAT",
	0x6A98005088A56C5: "LEVEL_BOUNDING_BOX_DATA",
	0x438E1B0DBFFAA93: "AMBSHADOWS_OCCLUDER_INFO",
	0x7D9BFD5CEC879080: "COLLISION_DATA_FOREGROUND",
	0xEC3AFEDF7EF282F0: "SOUND_BANK_TABLE",
}

LODSubmeshDesc = namedtuple("LODSubmeshDesc", "name address offset index")

JointsInfo = namedtuple("JointsInfo", "transformsStart parentingStart")

StreamDesc = namedtuple("StreamDesc", "type offset stride bufferOffsetAddr")

T2StreamDesc = namedtuple("T2StreamDesc", "type offset stride bufferOffsetAddr sizes qScale qOffs numVerts")

SkinDesc = namedtuple("SkinDesc", "mapOffset weightsOffset weightCount mapOffsetAddr weightOffsetAddr uncompressed")

PakEntry = namedtuple("PakEntry", "type offset")

PakLoginTableEntry = namedtuple("PakLoginTableEntry", "page offset")

class PakSubmesh:
	def __init__(self, name=None, numVerts=None, numIndices=None, facesOffset=None, streamDescs=None, skinDesc=None, nrmRecalcDesc=None, streamsAddr=None, facesOffsetAddr=None):
		self.name = name
		self.numVerts = numVerts
		self.numIndices = numIndices
		self.streamDescs = streamDescs
		self.skinDesc = skinDesc
		self.nrmRecalcDesc = nrmRecalcDesc
		self.facesOffset = facesOffset
		self.facesOffsetAddr = facesOffsetAddr
		self.bbox = []

class PakFile:
	def __init__(self, bs, args={}):
		self.bs = bs
		self.pakPageEntries = []
		self.pointerPageIds = {}
		self.entriesList = []
		self.submeshes = []
		self.args = args
		self.path = args.get("path")
		self.texList = args.get("texList") or []
		self.matList = args.get("matList") or []
		self.matNames = args.get("matNames") or []
		self.vramHashes = args.get("vramHashes") or []
		self.userStreams = args.get("userStreams") or {}
		self.pakLoginTable = []
		self.lods = args.get("lods") or []
		self.jointsInfo = None
		self.jointOffset = None
		self.basePak = None
		self.geoOffset = None
		self.boneList = None
		self.boneMap = None
		self.boneDict = None
		self.doLODs = False
		self.needsBasePak = False
		if args.get("doRead"):
			self.readPak()
		
	def getPointerFixupPage(self, readAddr):
		try:
			return self.pointerPageIds[readAddr][0]
		except:
			return None
		
	def changePointerFixup(self, address, newOffset, newPage):
		if address in self.pointerPageIds:
			returnAddr = self.bs.tell()
			writeUIntAt(self.bs, address, newOffset+20)
			self.bs.seek(self.pointerPageIds[address][1])
			self.bs.writeUShort(newPage)
			self.bs.seek(returnAddr)
		
	def readPointerFixup(self, TP1ZeroCondition=False):
		bs = self.bs
		readAddr = bs.tell()
		offset = bs.readInt64()
		if offset > 0 or TP1ZeroCondition:
			pageId = self.getPointerFixupPage(readAddr)
			if pageId != None:
				return offset + self.pakPageEntries[pageId][0]
			print("ReadAddr not found in PointerFixups!", readAddr)
			print("ReadAddr not found in PointerFixups! This file may be broken", crashHere)
			
		return offset
	
	def loadBaseSkeleton(self, skelPath):
		if skelPath and rapi.checkFileExists(skelPath):
			self.basePak = PakFile(NoeBitStream(rapi.loadIntoByteArray(skelPath)), {'path':skelPath})
			self.basePak.readPak()
			self.boneList = self.basePak.boneList
			self.boneMap = self.basePak.boneMap
			#self.boneNames = basePak.boneNames
			return 1
		else:
			print("Failed to load base skeleton from", skelPath)
			print(asdf + asd)
			return 0
	
	def makeVramHashJson(self, jsons):
		fileName = rapi.getLocalFileName(self.path)
		jsons[fileName] = {}
		for hash, subTuple in self.vrams.items():
			jsons[fileName][hash] = subTuple[0]
			
	def dumpGlobalVramHashes(self):
		output = ""
		try:
			jsons = json.load(open(noesis.getPluginsPath() + "python\\NDTextureHashes.json"))
		except:
			jsons = {}
		jsons[gameName] = jsons.get(gameName) or {}
		if gameName == "TLOU2" or gameName == "TLOUP1":
			gameDir = BaseDirectories[gameName]
			for folderName in os.listdir(gameDir+"\\"):
				if os.path.isdir(os.path.join(gameDir, folderName)) and os.path.isdir(os.path.join(gameDir, folderName + "\\texturedict3")):
					root = os.path.join(gameDir, folderName + "\\texturedict3\\")
					jsons[gameName][folderName] = jsons[gameName].get(folderName) or {} 
					suboutput = ""
					for fileName in os.listdir(root):
						if fileName.find("-dict")  != -1 and fileName not in jsons[gameName][folderName]:
							print("Found file", root + fileName)
							dictPak = PakFile(NoeBitStream(rapi.loadIntoByteArray(root + fileName)), {"path": root + fileName})
							pageCt = readUIntAt(dictPak.bs, 16)
							dictPak.bs.seek(readUIntAt(dictPak.bs, 20)+12*(pageCt-1))
							rawDataAddr = dictPak.bs.readUInt() + dictPak.bs.readUInt()
							gdRawDataStarts[gameName][folderName] = gdRawDataStarts[gameName].get(folderName) or {}
							gdRawDataStarts[gameName][folderName][fileName] = rawDataAddr
							suboutput += "\n    \"" + fileName + "\": " + str(rawDataAddr) + "," 
							dictPak.readPakHeader()
							dictPak.makeVramHashJson(jsons[gameName][folderName])
							with open(noesis.getPluginsPath() + "python\\NDTextureHashes.json", "w") as outfile:
								json.dump(jsons, outfile)
					
					output += "\n\"" + folderName + "\": {" + suboutput + "\n},"
			print("\nGlobal dict start offsets:\n", output)
		else:
			root = os.path.dirname(dialogOptions.dialog.localDir[:-1])+"\\textureDict2\\"
			print("Dumping textures json...")
			for fileName in os.listdir(root):
				if fileName.find("global-dict")  != -1 and fileName not in jsons:
					dictPak = PakFile(NoeBitStream(rapi.loadIntoByteArray(root + fileName)), {"path": root + fileName})
					pageCt = readUIntAt(dictPak.bs, 16)
					dictPak.bs.seek(readUIntAt(dictPak.bs, 20)+12*(pageCt-1))
					rawDataAddr = dictPak.bs.readUInt() + dictPak.bs.readUInt()
					gdRawDataStarts[gameName][fileName] = rawDataAddr
					output = output + "\n\"" + fileName, ": " + str(rawDataAddr) + "," 
					dictPak.readPakHeader()
					dictPak.makeVramHashJson(jsons)
					with open(noesis.getPluginsPath() + "python\\NDTextureHashes.json", "w") as outfile:
						json.dump(jsons, outfile)
			print("Texture Dict Start Offsets:\n", output, "\n")
	
	def writeVRAMImage(self, vramOffset, filepath):
		
		if rapi.checkFileExists(filepath):
			bs = self.bs
			vramOffset = vramOffset or bs.tell()
			offset = readUIntAt(bs, vramOffset+40)
			vramSize = readUIntAt(bs, vramOffset+48)
			imgFormat = readUIntAt(bs, vramOffset+72)
			fmtName = dxFormat.get(imgFormat) or ""
			rawDataStart = self.pakPageEntries[len(self.pakPageEntries)-1][0] + self.pakPageEntries[len(self.pakPageEntries)-1][1]
			newDataOffset = offset + rawDataStart
			
			ds = NoeBitStream(rapi.loadIntoByteArray(filepath))
			if filepath.count(".tga"):
				#fetch tga data
				ds.seek(12)
				width = ds.readUShort()
				height = ds.readUShort()
				depth = ds.readUByte()
				ds.seek(18)
				imgBytes = ds.readBytes(ds.getSize() - 18)
				imgBytes, numMips = encodeImageData(imgBytes, width, height, fmtName)
			elif filepath.count(".dds"):
				#fetch dds data
				magic = ds.readUInt()
				hdrSize = ds.readUInt()
				flags = ds.readUInt()
				height = ds.readUInt()
				width = ds.readUInt()
				pitchOrLinearSize = ds.readUInt()
				depth = ds.readUInt()
				numMips = ds.readUInt()
				isDX10 = (readUIntAt(ds, 84) == 808540228)
				ds.seek(hdrSize+4)
				if isDX10:
					compressionType = ds.readUInt() 
					ds.seek(16, 1) #skip DX10 header
				imgBytes = ds.readBytes(ds.getSize() - ds.tell())
				
			if dialogOptions.isTLOU2:
				imgBytes = rapi.callExtensionMethod("tile_1dthin", imgBytes, width, height, 4 if (fmtName.count("Bc1") or fmtName.count("Bc4")) else 8, 1)
				if noesis.optWasInvoked("-t"):
					numMips = 1
			
			if True: #len(imgBytes) > vramSize: #NEEDS FIXING
				newDataOffset = bs.getSize()
				bs.seek(32)
				bs.writeUInt(readUIntAt(bs, bs.tell())+len(imgBytes)) #added size to raw_data
			
			bs.seek(vramOffset+40)
			bs.writeUInt(newDataOffset - rawDataStart) #new offset
			bs.seek(vramOffset+48)
			bs.writeUInt(len(imgBytes)) #new size
			bs.seek(vramOffset+84)
			bs.writeUInt(width) #new width
			bs.seek(vramOffset+88)
			bs.writeUInt(height) #new height
			bs.seek(vramOffset+80)
			bs.writeUInt(numMips) #new mips
			
			#replace hashes
			bs.seek(vramOffset+56)
			hashOld = bs.readBytes(8)
			bs.seek(-8, 1)
			hashNew = struct.pack('<Q', bs.readUInt64() + 1)
			
			bs.seek(0)
			searchBytes = bs.readBytes(rawDataStart)
			bs.seek(0)
			bs.writeBytes(searchBytes.replace(hashOld, hashNew))
			
			#write image data
			bs.seek(newDataOffset)
			bs.writeBytes(imgBytes)
			
			return 1
			
		else:
			print("Texture not found:", filepath)
	
	def loadVRAM(self, vramOffset=0, exTexName=""):
		
		if dialogOptions.doConvertTex and exTexName.find("NoesisBrown") != -1: 
			return generateDummyTexture4px([32, 26, 18, 255], exTexName)
		elif dialogOptions.doConvertTex and exTexName.find("NoesisGray") != -1: 
			return generateDummyTexture4px([127, 127, 127, 255], exTexName)
		elif dialogOptions.doConvertTex and exTexName.find("NoesisWhite") != -1: 
			return generateDummyTexture4px([255, 255, 255, 255], exTexName)
		elif dialogOptions.doConvertTex and exTexName.find("NoesisNRM") != -1: 
			return generateDummyTexture4px([127, 127, 254, 255], exTexName)

		
		bs = self.bs
		vramOffset = vramOffset or bs.tell()
		bs.seek(vramOffset + 40)
		pakOffset = bs.readUInt()
		unknown0 = bs.readUInt()
		vramSize = bs.readUInt()
		textureDictId = bs.readUInt()
		m_hash = bs.readUInt64()
		unknown1 = bs.readUInt()
		m_type = bs.readUInt()
		imgFormat = bs.readUInt()
		field_2C = bs.readUInt()
		m_mipCount = bs.readUInt()
		width = bs.readUInt()
		height = bs.readUInt()
		field_3C = bs.readUInt()
		m_streamFlags = bs.readUInt()
		texFileName = self.vrams[m_hash][1]
		texPath = readStringAt(bs, bs.tell()+12)
		
		bigVramOffset = None
		bigVramDictFile = ""
		worldName = "All"
		
		if gameName == "TLOU2" or gameName == "TLOUP1":
			for worldFolderName, worldDict in self.texDict.items():
				for fileName, subDict in worldDict.items(): 
					bigVramOffset = subDict.get(str(m_hash))
					if bigVramOffset: 
						if rapi.checkFileExists(BaseDirectories[gameName] + worldFolderName + "\\texturedict3\\" + fileName):
							bigVramDictFile = BaseDirectories[gameName] + worldFolderName + "\\texturedict3\\" + fileName
							worldName = worldFolderName
							break
						else:
							bigVramOffset = None
							print("Texture hash was found, but Texture Dict does not exist!\n	", BaseDirectories[gameName] + worldFolderName + "\\texturedict3\\" + fileName)
				if bigVramOffset: break
		else:
			for fileName, subDict in self.texDict.items():
				bigVramOffset = subDict.get(str(m_hash))
				if bigVramOffset: 
					if rapi.checkFileExists(BaseDirectories[gameName] + "texturedict2\\" + fileName):
						bigVramDictFile = BaseDirectories[gameName] + "texturedict2\\" + fileName
						break
					else:
						bigVramOffset = None
						print("Texture hash was found, but Texture Dict does not exist!", texFileName, "\n	", BaseDirectories[gameName] + "texturedict2\\" + fileName)
		
		if bigVramOffset: 
			vramBytes = readFileBytes(bigVramDictFile, bigVramOffset, 1024)
			vramStream = NoeBitStream(vramBytes)
			offset = readUIntAt(vramStream, 40)
			width = readUIntAt(vramStream, 84)
			height = readUIntAt(vramStream, 88)
			vramSize = readUIntAt(vramStream, 48)
			imgFormat = readUIntAt(vramStream, 72)
			print("VRAM texture hash found!", fileName, '{:02X}'.format(m_hash), texFileName) #offset + gdRawDataStarts[gameName][worldName][fileName], width, height, vramSize, imgFormat, "\n", texFileName)
			imageData = readFileBytes(bigVramDictFile, offset + gdRawDataStarts[gameName][worldName][fileName], vramSize)
		else:
			print("Loading local texture", texFileName)
			bs.seek(pakOffset + self.pakPageEntries[len(self.pakPageEntries)-1][0] + self.pakPageEntries[len(self.pakPageEntries)-1][1])
			imageData = bs.readBytes(vramSize)
			
		fmtName = dxFormat.get(imgFormat) or ""
		bpp = 4 if (fmtName.count("Bc1") or fmtName.count("Bc4")) else 8
		
		if dialogOptions.isTLOU2:
			imageData = rapi.callExtensionMethod("untile_1dthin", imageData, width, height, bpp, 1)
		
		decodeFmt, encodeFmt, bpp = getDXTFormat(fmtName)
		
		if isinstance(decodeFmt, str):
			print("RGBA: ", fmtName)
			try:
				texData = rapi.imageDecodeRaw(imageData, width, height, decodeFmt)
			except:
				print("Failed to decode raw image type", fmtName)
		elif decodeFmt != None:
			texData = rapi.imageDecodeDXT(imageData, width, height, decodeFmt)
			if dialogOptions.doConvertTex and decodeFmt == noesis.FOURCC_BC7: 
				if exTexName.count("_NoesisAO"):
					texData = rapi.imageEncodeRaw(texData, width, height, "r8r8r8")
					texData = rapi.imageDecodeRaw(texData, width, height, "r8g8b8")
					texFileName = exTexName
				elif texFileName.count("-ao") or texFileName.count("-occlusion"):
					texData = rapi.imageEncodeRaw(texData, width, height, "g16b16")
					texData = rapi.imageDecodeRaw(texData, width, height, "r16g16")
		else:
			print("Error: Unsupported texture type: " + str(imgFormat) + "  " + fmtName)
			
		return NoeTexture(texFileName, width, height, texData, noesis.NOESISTEX_RGBA32)
	
	def checkResItem(self, start, m_resItemOffset, m_itemType):
		bs = self.bs
		self.entriesList.append(PakEntry(type=m_itemType, offset = m_resItemOffset))
		
		if m_itemType == "VRAM_DESC":
			bs.seek(m_resItemOffset + start + 56)
			texHash = bs.readUInt64()
			texPath = readStringAt(bs, m_resItemOffset + start + 112)
			splitted = rapi.getLocalFileName(texPath.replace(".tga/", "+")).split("+", 1)
			texName = splitted[0] + texoutExt
			if len(splitted) > 1:
				if texName in self.vramNames:
					texName = (splitted[0] + "_" + splitted[1]).replace(".ndb", texoutExt) #add hash to duplicate texture names
				self.vramNames[texName] = True
				self.vrams[texHash] = [m_resItemOffset + start, texName, [], None]
		
		if m_itemType == "JOINT_HIERARCHY":
			self.jointOffset = (m_resItemOffset, start)
			
		if m_itemType == "GEOMETRY_1":
			self.geoOffset = (m_resItemOffset, start)
			m_numSubMeshDesc = readUIntAt(bs, self.geoOffset[0] + self.geoOffset[1] + ResItemPaddingSz + 8)
			bs.seek(self.geoOffset[0] + self.geoOffset[1] + ResItemPaddingSz + 40)
			#print(bs.tell(), ResItemPaddingSz)
			SubmeshesOffs = self.readPointerFixup()
			for i in range(m_numSubMeshDesc):
				bs.seek(SubmeshesOffs + 176*i + 104)
				self.needsBasePak = self.needsBasePak or not not bs.readUInt64()
	
	def readPakHeader(self):
	
		global dialogOptions, ResItemPaddingSz
		
		print ("Reading", self.path or rapi.getInputName())
		readPointerFixup = self.readPointerFixup
		
		bs = self.bs
		bs.seek(0)
		m_magic = bs.readUInt()						#0x0 0x00000A79
		if m_magic != 2681 and m_magic != 68217 and m_magic != 2147486329 and m_magic != 2685 and m_magic != 68221:
			print("No pak header detected!", m_magic)
			return 0
		dialogOptions.isTLOUP1 = (m_magic == 2685 or m_magic == 68221)
		
		m_hdrSize = bs.readUInt()					#0x4 header size
		m_pakLoginTableIdx = bs.readUInt()			#0x8 idx of the page storing the PakLoginTable
		m_pakLoginTableOffset = bs.readUInt()		#0xC relative offset PakLoginTable = PakPageHeader + m_pakLoginTableOffset; //its a ResItem
		m_pageCt = bs.readUInt()					#0x10 page count. Total number of pages in the package
		m_pPakPageEntryTable = bs.readUInt()		#0x14 ptr to the PakPageEntry array/table
		m_numPointerFixUpPages = bs.readUInt()		#0x18 always 0x8
		m_pointerFixUpTableOffset = bs.readUInt()	#0x1C ptr to the PointerFixUpTable table
		m_unk5 = bs.readUInt()						#0x20 no idea
		m_unk6 = bs.readUInt()						#0x20 no idea
		m_unk7 = bs.readUInt()						#0x20 no idea
		if dialogOptions.isTLOUP1:
			m_unk8 = bs.readUInt()
			m_unk9 = bs.readUInt()
			m_unk10 = bs.readUInt()
			
		bs.seek(m_pPakPageEntryTable)
		self.pakPageEntries = []
		for i in range(m_pageCt):
			self.pakPageEntries.append((bs.readUInt(), bs.readUInt(), bs.readUInt()))
		
		bs.seek(m_pointerFixUpTableOffset)
		m_pageEntryNumber = bs.readUInt()
		m_dataOffset = bs.readUInt()
		m_numLoginPageEntries = bs.readUInt()
		bs.seek(m_dataOffset)
		
		self.pointerPageIds = {}
		for i in range(m_numLoginPageEntries):
			m_page1Idx = bs.readUShort()
			m_page2Idx = bs.readUShort()
			pointerOffs = bs.readUInt()
			self.pointerPageIds[pointerOffs + self.pakPageEntries[m_page1Idx][0]] = (m_page2Idx, bs.tell()-6)
			
		self.jointOffset = self.geoOffset = None
		self.vrams = {}
		
		if rapi.checkFileExists(noesis.getPluginsPath() + "python\\NDTextureHashes.json"):
			file = open(noesis.getPluginsPath() + "python\\NDTextureHashes.json")
			dialogOptions.texDicts = dialogOptions.texDicts or json.load(file)
		else:
			dialogOptions.texDicts = {}
		
		for name in gamesList:
			dialogOptions.texDicts[name] = dialogOptions.texDicts.get(name) or {}
		self.texDict = dialogOptions.texDicts[gameName]

		self.pakLoginTable = []
		self.vramNames = {}
		
		pakLoginTableItemStart = self.pakPageEntries[m_pakLoginTableIdx][0] + m_pakLoginTableOffset
		dialogOptions.isTLOU2 = (readUIntAt(bs, pakLoginTableItemStart+32) == 74565)
		ResItemPaddingSz = 48 if (dialogOptions.isTLOU2 or dialogOptions.isTLOUP1) else 32
		bs.seek(pakLoginTableItemStart + ResItemPaddingSz)
		loginCount = bs.readUInt()
		bs.seek(4, 1)
		
		for i in range(loginCount):
			self.pakLoginTable.append(PakLoginTableEntry(page=bs.readUInt(), offset=bs.readUInt()))
		
		if dialogOptions.isTLOUP1: #the outer pak format was changed a lot for TLOU Part I. ResPage and ResPageEntry are gone, now all ResItems are accessed from the pak login table and have StringIDs for names
			for loginResItem in self.pakLoginTable:
				start = self.pakPageEntries[loginResItem.page][0]
				bs.seek(start + loginResItem.offset + 32)
				typeStringID = bs.readUInt64()
				m_itemType = TP1_pakStringIDs.get(typeStringID)
				if m_itemType:
					self.checkResItem(start, loginResItem.offset, m_itemType)
					if m_itemType == "TEXTURE_TABLE" or m_itemType == "TEXTURE_DICTIONARY":
						numTex = readUIntAt(bs, start + loginResItem.offset + ResItemPaddingSz)
						bs.seek(start + loginResItem.offset + ResItemPaddingSz + 24)
						listStart = readPointerFixup()
						for i in range(numTex):
							bs.seek(listStart+i*8)
							pageID = self.getPointerFixupPage(bs.tell())
							pointer = bs.readUInt64()
							self.checkResItem(self.pakPageEntries[pageID][0], pointer-32, "VRAM_DESC")
		else:
			for p, pageEntry in enumerate(self.pakPageEntries):
				start = pageEntry[0]
				bs.seek(start + 12)
				m_pageSize = bs.readUInt()
				bs.seek(2,1)
				m_numPageHeaderEntries = bs.readUShort()
				
				for ph in range(m_numPageHeaderEntries):
					m_name = readStringAt(bs, bs.readUInt64()+start)
					m_resItemOffset = bs.readUInt()
					place = bs.tell() + 4
					bs.seek(m_resItemOffset + start)
					m_itemNameOffset = bs.readUInt64()
					m_itemName = readStringAt(bs, m_itemNameOffset+start)
					m_itemTypeOffset = bs.readUInt64()
					m_itemType = readStringAt(bs, m_itemTypeOffset+start)
					
					self.checkResItem(start, m_resItemOffset, m_itemType)
					bs.seek(place)
	
	def readPak(self):
		
		global dialogOptions
		bs = self.bs
		readPointerFixup = self.readPointerFixup
		
		if len(self.pakPageEntries) == 0:
			self.readPakHeader()
		start = self.pakPageEntries[0]
		
		if not self.jointOffset and dialogOptions.doLoadBase and dialogOptions.baseSkeleton: # and dialogOptions.baseIdx != -1:
			localRoot = findRootDir(rapi.getOutputName() or rapi.getInputName())
			baseSkelPath = BaseDirectories[gameName] + dialogOptions.baseSkeleton if dialogOptions.baseSkeleton[1] != ":" else dialogOptions.baseSkeleton
			if rapi.checkFileExists(localRoot + dialogOptions.baseSkeleton):
				baseSkelPath = localRoot + dialogOptions.baseSkeleton
				if rapi.checkFileExists(baseSkelPath.replace(".pak", ".NEW.pak")): 
					baseSkelPath = baseSkelPath.replace(".pak", ".NEW.pak")
				print("\nFound local base pak: ", baseSkelPath, "\n")
			dialogOptions.baseSkeleton = ""
			if not self.loadBaseSkeleton(baseSkelPath) and not noesis.optWasInvoked("-t"):
				return 0
		
		if self.jointOffset:
			start = self.jointOffset[1]
			print("Found Joint Hierarchy") # offset", self.jointOffset[0] + start, ", location:", self.jointOffset[0] + start + 20 + 32)
			bs.seek(self.jointOffset[0] + start + 20 + ResItemPaddingSz)
			boneCount = bs.readUInt()
			bs.seek(8,1)
			xformsOffset = readPointerFixup()
			flagsOffset = bs.readUInt64()
			uknOffset = bs.readUInt64()
			namesOffset = readPointerFixup()
			
			bs.seek(xformsOffset + 16)
			nodeCount = bs.readUShort()
			xformCount = bs.readUShort()
			uknCount = bs.readUShort()
			uknShort = bs.readUShort()
			uknHash0 = bs.readUInt()
			uknHash1 = bs.readUInt()
			headerSize = bs.readUInt()
			uknInt0 = bs.readUInt()
			uknInt1 = bs.readUInt()
			aOffs = bs.readUInt()
			bOffs = bs.readUInt()
			cOffs = bs.readUInt()
			uknInt2 = bs.readUInt()
			hierarchyOffset = bs.readUInt()
			
			self.boneList = self.boneList or []
			parentList = []
			matrixList = []
			
			transformsStart = xformsOffset + headerSize
			bs.seek(transformsStart)
			for b in range(xformCount):
				scale = NoeVec3((bs.readFloat(), bs.readFloat(), bs.readFloat()))
				bs.seek(4,1)
				rotation = NoeQuat((bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat())).transpose()
				position = NoeVec3((bs.readFloat(), bs.readFloat(), bs.readFloat()))
				bs.seek(4,1)
				mat = rotation.toMat43()
				mat[3] = position * GlobalScale
				matrixList.append(mat)
				
			bs.seek(xformsOffset + hierarchyOffset + 20)
			hashesSize = bs.readUInt()
			bs.seek(hashesSize - 24, 1)
			parentingStart = bs.tell()
			for b in range(boneCount):
				parentList.append((bs.readInt(), bs.readInt(), bs.readInt(), bs.readInt())) #GroupID, ParentID, ChildID, ChainID
			
			self.jointsInfo = JointsInfo(transformsStart=transformsStart, parentingStart=parentingStart)
			
			
			mainBoneMats = []
			boneNames = []
			self.boneDict = []
			self.boneMap = []
			oldBoneNames = [bone.name for bone in self.boneList]
			
			bs.seek(namesOffset)
			for b in range(boneCount):
				bs.seek(8,1)
				boneNames.append(readStringAt(bs, bs.readUInt64()+start))
				
			def getRootParent(parentTbl):
				while parentTbl[1] != -1:
					parentTbl = parentList[parentTbl[1]]
				return parentList.index(parentTbl)
			
			for b in range(boneCount):	
				if getRootParent(parentList[b]) == 0:
					self.boneMap.append(b)
				
			identity = NoeMat43((NoeVec3((1.0, 0.0, 0.0)), NoeVec3((0.0, 1.0, 0.0)), NoeVec3((0.0, 0.0, 1.0)), NoeVec3((0.0, 0.0, 0.0))))
			startBoneIdx = len(self.boneList)
			for b, bID in enumerate(self.boneMap):
				mat = matrixList[b] if b < len(matrixList) else identity
				mainBoneMats.append(mat)
			
			for b in range(boneCount):
				
				if b in self.boneMap:
					self.boneList.append(NoeBone(startBoneIdx + b, boneNames[b], mainBoneMats[self.boneMap.index(b)], None, parentList[b][1]))
				else:
					splitted = boneNames[b].split("_")
					endName = splitted[len(splitted)-1]
					matchedName = boneNames[b].replace("_" + endName, "")#.replace("_runtime", "")
					bFound = False
					mat = identity
					if parentList[b][3] != -1 and parentList[b][3] in self.boneMap: #parentList[b][3] < len(self.boneMap) and self.boneMap[parentList[b][3]] < len(mainBoneMats):
						mat = mainBoneMats[self.boneMap[parentList[b][3]]]
					for j, bId in enumerate(self.boneMap):
						if boneNames[bId].find(matchedName) != -1:
							bFound = True
							self.boneList.append(NoeBone(startBoneIdx + b, boneNames[b], mat, None, parentList[b][1]))
							if parentList[b][1] == -1 or (dialogOptions.reparentHelpers and (endName == "helper" or endName == "grp")): # or endName == "mover"
								self.boneList[len(self.boneList)-1].parentIndex = bId
							break
					if not bFound:
						self.boneList.append(NoeBone(startBoneIdx + b, boneNames[b], mat, None, parentList[b][1]))
				lastBone = self.boneList[len(self.boneList)-1]
				if lastBone.parentIndex != -1:
					lastBone.parentIndex += startBoneIdx
				elif b not in self.boneMap:
					if lastBone.name == "eyelash_grp" and "headb" in boneNames:
						lastBone.parentIndex = boneNames.index("headb") + startBoneIdx
					else:	
						lastBone.parentIndex = 0 #parent stragglers to root
						
		if self.geoOffset:
			start = self.geoOffset[1]
			print("Found Geometry") # offset", self.geoOffset[0] + start)
			
			lastLOD = 0
			self.submeshes = []
			
			bs.seek(self.geoOffset[0] + start + ResItemPaddingSz)
			
			m_version = bs.readUInt()
			m_isForeground = bs.readUInt()
			m_numSubMeshDesc = bs.readUInt()
			m_numLODs = bs.readUInt()
			m_numMaterials = bs.readUInt()
			m_unk4 = bs.readUInt()
			m_numShaders = bs.readUInt()
			m_unk6 = bs.readUInt()
			m_unk7 = bs.readUInt()
			m_unk8 = bs.readUInt()
			SubmeshesOffs = readPointerFixup()
			LODDescsOffs = readPointerFixup()
			ukn0 = bs.readUInt64()
			textureDescsOffs = readPointerFixup()
			shaderDescsOffs = readPointerFixup()
			ukn3 = bs.readUInt64()
			uknFloatsOffs = readPointerFixup()
			materialDescsOffs = readPointerFixup()
			
			usedMaterials = {}
			usedTextures = []
			'''
			for i in range(m_numLODs):
				bs.seek(LODDescsOffs + 8*i)
				bs.seek(readPointerFixup())
				unknown = bs.readUInt()
				submeshCount = bs.readUInt()
				unknown64 = bs.readUInt64()
				collectionName = readStringAt(bs, readPointerFixup())
				firstSubmeshDescOffs = readPointerFixup()
				uknBytesOffs = readPointerFixup()
				submeshDescs = []
				for s in range(submeshCount):
					bs.seek(firstSubmeshDescOffs + 16*s)
					submeshOffs = readPointerFixup()
					submeshIdx = bs.readUInt()
					submeshUkn = bs.readUInt()
					bs.seek(submeshOffs + 8)
					submeshName = readStringAt(bs, readPointerFixup()).split("|")
					submeshName = submeshName[len(submeshName)-1]
					submeshDescs.append(LODSubmeshDesc(name=submeshName,  address=firstSubmeshDescOffs + 16*s, offset=submeshOffs, index=submeshIdx))
				self.lods.append(submeshDescs)
			'''
			for i in range(m_numSubMeshDesc):
				bs.seek(SubmeshesOffs + 176*i)
				if dialogOptions.isTLOU2 or dialogOptions.isTLOUP1:
					bbox = [[bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat()], [bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat()]]
					submeshName = readStringAt(bs, readPointerFixup() or start).split("|")
					submeshName = submeshName[len(submeshName)-1]
					ukn64_0 = bs.readUInt64()
					m_pStreamDesc = readPointerFixup()
					ukn64_1 = bs.readUInt64()
					facesOffsetAddr = bs.tell()
					m_pIndexes = readPointerFixup(True)
					m_material = readPointerFixup()
					ukn64_2 = bs.readUInt64()
					skindataOffset = readPointerFixup()
					ukn64_3 = bs.readUInt64()
					ukn64_4 = bs.readUInt64()
					nrmRecalcDescOffsOffset = bs.tell()
					nrmRecalcDescOffs = readPointerFixup()
					uknStringOffs = bs.readUInt64()
					m_numVertexes = bs.readUInt()
					m_numIndexes = bs.readUInt()
					m_numStreamSource = bs.readUInt()
					m_numDefaultStreams = bs.readUInt()
					ukn32_0 = bs.readUInt()
					ukn32_1 = bs.readUInt()
					ukn64_5 = bs.readUInt64()
					ukn32_2 = bs.readUInt()
					ukn32_3 = bs.readUInt()
					ukn32_4 = bs.readUInt()
					ukn32_5 = bs.readUInt()
				else:
					field_0 = bs.readUInt()
					field_4 = bs.readUInt()
					submeshName = readStringAt(bs, readPointerFixup()).split("|")
					submeshName = submeshName[len(submeshName)-1]
					field_10 = bs.readUInt()
					field_14 = bs.readUInt()
					field_18 = bs.readUInt()
					field_1C = bs.readUInt()
					field_20 = bs.readUInt()
					m_numVertexes = bs.readUInt()
					m_numIndexes = bs.readUInt()
					m_numStreamSource = bs.readUInt()
					m_numDefaultStreams = bs.readInt()
					field_34 = bs.readUInt()
					m_pStreamDesc = readPointerFixup()
					field_40 = bs.readUInt()
					field_44 = bs.readUInt()
					facesOffsetAddr = bs.tell()
					m_pIndexes = readPointerFixup()
					m_material = readPointerFixup()
					m_numMaterialInstances = bs.readUInt()
					field_5C = bs.readUInt()
					field_60 = bs.readUInt()
					field_64 = bs.readUInt()
					skindataOffset = readPointerFixup()
					field_70 = bs.readUInt()
					field_74 = bs.readUInt()
					field_78 = bs.readUInt()
					field_7C = bs.readUInt()
					field_80 = bs.readUInt()
					field_84 = bs.readUInt()
					nrmRecalcDescOffsOffset = bs.tell()
					nrmRecalcDescOffs = readPointerFixup()
					field_90 = bs.readUInt()
					field_94 = bs.readUInt()
					field_98 = bs.readUInt()
					field_9C = bs.readUInt()
					field_A0 = bs.readUInt()
					field_A4 = bs.readUInt()
					field_A8 = bs.readUInt()
					field_AC = bs.readUInt()
				
				place = bs.tell()
				streamDescs = []
				
				for j in range(m_numStreamSource):
					
					if dialogOptions.isTLOU2 or dialogOptions.isTLOUP1:
						bs.seek(m_pStreamDesc + 64*j)
						buffOffsAddr = bs.tell()
						m_bufferOffset = readPointerFixup(True)
						numVerts = bs.readUInt()
						uknInt = bs.readUInt()
						bufferSize = bs.readUInt()
						
						m_compType = bs.readUByte()
						m_unk2 = bs.readUByte()
						m_unk3 = bs.readBits(4)
						m_stride = bs.readBits(4)
						m_unk4 = bs.readUByte()
						sizes = [bs.readUByte(), bs.readUByte(), bs.readUByte(), bs.readUByte()]
						
						uknInt0 = bs.readUInt()
						qScale = NoeVec4((bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat()))# * 10000
						
						qOffs = NoeVec4((bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat()))
						bs.readFloat()
						desc = T2StreamDesc(type=m_compType, offset=m_bufferOffset, stride=m_stride, bufferOffsetAddr=buffOffsAddr, sizes=sizes, qScale=qScale, qOffs=qOffs, numVerts=numVerts)
						streamDescs.append(desc)
					else:
						bs.seek(m_pStreamDesc + 24*j)
						m_numAttributes = bs.readUByte()
						m_unk  = bs.readUByte()
						m_stride  = bs.readUShort()
						m_unk2 = bs.readUByte()
						m_unk3 = bs.readUByte()
						m_unk4 = bs.readUShort()
						m_compInfoOffs = readPointerFixup()
						buffOffsAddr = bs.tell()
						m_bufferOffset = readPointerFixup()
						
						bs.seek(m_compInfoOffs)
						
						m_unkC0 = bs.readUByte()
						m_unkC1 = bs.readUByte()
						m_unkC2 = bs.readUByte()
						m_compType = bs.readUByte()
						
						streamDescs.append(StreamDesc(type=m_compType, offset=m_bufferOffset, stride=m_stride, bufferOffsetAddr=buffOffsAddr))
				
				self.submeshes.append(PakSubmesh(submeshName, m_numVertexes, m_numIndexes, m_pIndexes, streamDescs))
				self.submeshes[i].facesOffsetAddr = facesOffsetAddr
				if dialogOptions.isTLOU2 or dialogOptions.isTLOUP1:
					self.submeshes[i].bbox = bbox
				
				self.submeshes[i].streamsAddr = m_compInfoOffs if not dialogOptions.isTLOU2 and not dialogOptions.isTLOUP1 else None
				
				if nrmRecalcDescOffs:
					bs.seek(nrmRecalcDescOffs)
					indexCount = bs.readInt()
					uknInt2 = bs.readInt()
					ptrOffsetsStart = bs.tell()
					ptr1 = readPointerFixup()
					ptr2 = readPointerFixup()
					ptr3 = readPointerFixup()
					ptr4 = readPointerFixup()
					
					self.submeshes[i].nrmRecalcDesc = [ptr1, ptr2, ptr3, ptr4, indexCount, nrmRecalcDescOffsOffset, ptrOffsetsStart]
				
				if skindataOffset:
					bs.seek(skindataOffset)
					uknSD0 = bs.readUInt()
					numWeights = bs.readUInt()
					uknSD2 = bs.readUInt()
					uknSD3 = bs.readUInt()
					bIndicesOffs = readPointerFixup(dialogOptions.isTLOUP1)
					weightsOffs = readPointerFixup(dialogOptions.isTLOUP1)
					
					self.submeshes[i].skinDesc = SkinDesc(mapOffset=bIndicesOffs, weightsOffset=weightsOffs, weightCount=numWeights, mapOffsetAddr=bs.tell()-16, weightOffsetAddr=bs.tell()-8, uncompressed=(dialogOptions.isTLOUP1 and uknSD2 > 0))
					
				bs.seek(m_material)
				shaderAssetNameOffs = readPointerFixup()
				shaderTypeOffs = readPointerFixup()
				
				
				if dialogOptions.isTLOU2 or dialogOptions.isTLOUP1:
					UUID = bs.readUInt64()
					shaderParamsOffs = readPointerFixup(True)
					texDescsListOffs = readPointerFixup()
					shaderNamesOffs = readPointerFixup()
					uknOffs = readPointerFixup()
					fetchMapDescsOffs = readPointerFixup()
					bs.seek(52*4, 1)
					paramCount = bs.readUInt()
					texCount = bs.readUInt()
					nameCount = bs.readUInt()
					fetchMapCount = bs.readUInt()
				else:
					shaderOptions0Offs = readPointerFixup()
					hashCodeOffs = readPointerFixup()
					shaderParamsOffs = readPointerFixup()
					texDescsListOffs = readPointerFixup()
					shaderOptions3Offs = readPointerFixup()
					nameCount = bs.readUInt()
					paramCount = bs.readUInt()
					texCount = bs.readUInt()
					unkCount = bs.readUInt()
				
				matName = readStringAt(bs, shaderAssetNameOffs)
				matType = readStringAt(bs, shaderTypeOffs)
				matKey = rapi.getLocalFileName(matName[:matName.find(":")])
				material = usedMaterials.get(m_material) 
				
				if not material:
					rapi.setPreviewOption("autoLoadNonDiffuse", "1")
					material = NoeMaterial(matKey, "")
					#materialFlags = 0
					material.setDefaultBlend(0)
					material.setSpecularColor(NoeVec4([0.5, 0.5, 0.5, 32.0])) 
					secondaryDiffuse = []
					loadedDiffuse = loadedNormal = loadedTrans = loadedSpec = loadedMetal = loadedRoughness = loadedOcc = False
					
					for j in range(texCount):
						bs.seek(texDescsListOffs + (40+8*(dialogOptions.isTLOU2 or dialogOptions.isTLOUP1))*j )
						nameAddr = readPointerFixup()
						name = readStringAt(bs, nameAddr)
						bs.seek(8+8*(dialogOptions.isTLOU2 or dialogOptions.isTLOUP1),1) #path = readStringAt(bs, readPointerFixup())
						bs.seek(readPointerFixup())
						path = readStringAt(bs, readPointerFixup())
						vramHash = bs.readUInt64()
						texFileName = self.vrams[vramHash][1] if vramHash in self.vrams else ""
						doSet = False
						
						if texFileName and name.find("01") != -1:
							if not loadedDiffuse and name.find("BaseColor01") != -1:
								doSet = loadedDiffuse = vramHash 
								material.setTexture(texFileName)
							elif not loadedNormal and (name.find("Normal01") != -1 or name.find("NR") != -1):
								doSet = loadedNormal = vramHash
								material.setNormalTexture(texFileName)
								if dialogOptions.doConvertTex:
									#if gameName != "TLOUP1":
									material.flags |= noesis.NMATFLAG_NORMALMAP_FLIPY #| noesis.NMATFLAG_NORMALMAP_NODERZ
									if name.find("NR") != -1 and texFileName.find("-ao") != -1: # Ambient Occlusion
										self.vrams[vramHash][2].append(texFileName.replace(texoutExt, "_NoesisAO" + texoutExt))
										material.setOcclTexture(self.vrams[vramHash][2][len(self.vrams[vramHash][2])-1])
								
							elif not loadedTrans and name.find("Transparency01") != -1:
								doSet = loadedTrans = vramHash
								material.setOpacityTexture(texFileName)
								material.setAlphaTest(0.05)
								material.flags |= noesis.NMATFLAG_TWOSIDED
								
								if dialogOptions.doConvertTex:
									if not loadedNormal:
										self.vrams[vramHash][2].append("NoesisNRM" + texoutExt)
										material.setNormalTexture(self.vrams[vramHash][2][len(self.vrams[vramHash][2])-1])
									if not loadedDiffuse:
										self.vrams[vramHash][2].append("NoesisBrown" + texoutExt)
										material.setTexture(self.vrams[vramHash][2][len(self.vrams[vramHash][2])-1])
									
							elif not loadedSpec and name.find("pecular") != -1:
								doSet = loadedSpec = vramHash
								material.setSpecularTexture(texFileName)
								#material.flags |= noesis.NMATFLAG_PBR_SPEC
							elif not loadedOcc and name.find("Ao01") != -1:
								doSet = loadedOcc = vramHash
								material.setOcclTexture(texFileName)
								
						if not loadedDiffuse and not secondaryDiffuse and name.find("Color0") != -1:
							secondaryDiffuse = [texFileName, vramHash]
								
						'''if dialogOptions.doConvertTex and not loadedSpec :
							if  (name.find("LinearBlend0") != -1 or name.find("ME") != -1): #not loadedMetal and
								if not loadedRoughness:
									doSet = loadedMetal = vramHash
									material.setSpecularTexture(texFileName)
									material.setSpecularSwizzle( NoeMat44([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]]) )
								elif loadedRoughness != vramHash:
									self.vrams[loadedRoughness][2].append([vramHash, 0, 0]) #copy red channel of this texture to red channel of roughness texture (which has been set as specular)
								else:
									material.setRoughness(0.75, 0.0)
								material.flags |= noesis.NMATFLAG_PBR_SPEC_IR_RG | noesis.NMATFLAG_PBR_METAL
								material.setMetal(0.5, 0.0)
								
							if not loadedRoughness and (name.find("Curvature0") != -1 or name.find("RO") != -1):
								if not loadedMetal:
									doSet = loadedRoughness = vramHash
									material.setSpecularTexture(texFileName)
								elif loadedMetal != vramHash:
									self.vrams[loadedMetal][2].append([vramHash, 0, 1])  #copy red channel of this texture to green channel of metal texture (which has been set as specular)
								else:
									material.setMetal(0.0, 0.0)
								material.flags |= noesis.NMATFLAG_PBR_SPEC_IR_RG | noesis.NMATFLAG_PBR_METAL
								material.setRoughness(0.75, 0.5)'''
								
						doSet = doSet or dialogOptions.loadAllTextures
						
						if doSet and texFileName and texFileName not in usedTextures:
							self.vramHashes.append(vramHash)
							usedTextures.append(texFileName)
					
					if not loadedDiffuse and secondaryDiffuse:
						material.setTexture(secondaryDiffuse[0])
						if secondaryDiffuse[0] not in usedTextures:
							self.vramHashes.append(secondaryDiffuse[1])
							usedTextures.append(secondaryDiffuse[0])
					
					params = {}
					setBaseColor = setSpecScale = setRoughness = setMetal = False
					outstring = "\n" + matKey + "material parameters:"
					print("shaderParamsOffs", shaderParamsOffs)
					
					for j in range(paramCount):
						bs.seek(shaderParamsOffs + 24*j)
						name = readStringAt(bs, readPointerFixup(True))
						valueOffset = readPointerFixup()
						numFloats = bs.readUInt()
						bs.seek(valueOffset)
						params[name] = [0.0, 0.0, 0.0, 1.0]
						for p in range(numFloats):
							params[name][p] = bs.readFloat()
						if numFloats == 1:
							outstring = outstring + "\n	" + name + ":  " + str(params[name][0])
						else:
							outstring = outstring + "\n	" +  name + ":  " + str(params[name])
						lowerName = name.lower()
						if True: #lowerName.find("01") != -1:
							if numFloats==3 and not setBaseColor and not material.texName and lowerName.find("basecolor") != -1:
								setBaseColor = True
								material.setDiffuseColor(params[name])
							elif numFloats==1 and not setSpecScale and not loadedMetal and not loadedRoughness and lowerName.find("spec") != -1 :
								setSpecScale = True
								material.setSpecularColor(NoeVec4([0.5*params[name][0], 0.5*params[name][0], 0.5*params[name][0], 32.0]))
							elif numFloats==1 and not setRoughness and lowerName.find("roughness") != -1:
								setRoughness = True
								material.setRoughness(params[name][0], 0.5)
							elif numFloats==1 and not setMetal and lowerName.find("metal") != -1:
								setMetal = True
								material.setMetal(params[name][0], 0.0)
					
					if dialogOptions.printMaterialParams:
						print(outstring, "\n")
						
					if dialogOptions.doConvertTex and not material.texName and ((not loadedNormal and not loadedTrans and not loadedSpec and not setBaseColor) or matKey.find("lens") != -1):
						material.setSkipRender(True)
					
					usedMaterials[m_material] = material
					self.matList.append(material)
					
				self.matNames.append(material.name)
				
				bs.seek(place)
			
			
	def loadGeometry(self, startingBonesCt=0):
		
		bs = self.bs
		rapi.rpgSetTransform((NoeVec3((GlobalScale,0,0)), NoeVec3((0,GlobalScale,0)), NoeVec3((0,0,GlobalScale)), NoeVec3((0,0,0)))) 
		
		if self.submeshes:
			
			lastLOD = 0
			
			if dialogOptions.doLoadTex:
				alreadyLoadedList = [tex.name for tex in self.texList]
				for vramHash in self.vramHashes:
					tex = self.loadVRAM(self.vrams[vramHash][0])
					if tex and tex.name not in alreadyLoadedList:  
						self.texList.append(tex)
						alreadyLoadedList.append(tex.name)
					
					# Load separated channel textures and dummy textures, or merge metal+roughness into specular:
					if self.vrams[vramHash][2]: 
						for texNameOrList in self.vrams[vramHash][2]:
							if isinstance(texNameOrList, list):
								print("Found merge hash", texNameOrList[0], "for", tex.name)
								channelTex = self.loadVRAM(self.vrams[texNameOrList[0]][0])
								tex.pixelData = moveChannelsRGBA(channelTex.pixelData, texNameOrList[1], channelTex.width, channelTex.height, tex.pixelData, texNameOrList[2], tex.width, tex.height)
								
							elif texNameOrList not in alreadyLoadedList:
								dummyTex = self.loadVRAM(self.vrams[vramHash][0], texNameOrList)
								if dummyTex:
									self.texList.append(dummyTex)
									alreadyLoadedList.append(dummyTex.name)
				
				if dialogOptions.loadAllTextures:
					for vramHash, subTuple in self.vrams.items():
						if subTuple[1] and subTuple[1] not in alreadyLoadedList:
							tex = self.loadVRAM(subTuple[0])
							if tex:  
								self.texList.append(tex)
								alreadyLoadedList.append(tex.name)
								
			for i, sm in enumerate(self.submeshes):
				lodFind = sm.name.find("Shape")
				LODidx = int(sm.name[lodFind+5]) if lodFind != -1 and sm.name[lodFind+5].isnumeric() else 0
				if LODidx > lastLOD:
					lastLOD = LODidx
				if not dialogOptions.doLODs and LODidx > 0:
					continue
				
				rapi.rpgSetName(sm.name)
				rapi.rpgSetMaterial(self.matNames[i])
				foundUVs = foundNormals = foundColors = 0
				
				for j, sd in enumerate(sm.streamDescs):
				
					bs.seek(sd.offset)
					if dialogOptions.isTLOU2 or dialogOptions.isTLOUP1:
						if j == 0 and sd.stride==12:
							rapi.rpgBindPositionBuffer(bs.readBytes(12 * sm.numVerts), noesis.RPGEODATA_FLOAT, 12)
						elif sd.type == 1:
							rapi.rpgBindUV1Buffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4)
						elif sd.type == 2:
							rapi.rpgBindNormalBuffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_BYTE, 4)
						elif sd.type == 3:
							rapi.rpgBindTangentBuffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_BYTE, 4)
						elif sd.type == 11:
							rapi.rpgBindUV2Buffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4)
						else:
							floatsList = []
							for v in range(sd.numVerts):
								for c in range(4):
									if sd.sizes[c]:
										floatsList.append(bs.readBits(sd.sizes[c]) * sd.qScale[c] + sd.qOffs[c])
							floatsBuffer = struct.pack("<" + 'f'*len(floatsList), *floatsList)
							try:
								if sd.type == 64: 
									rapi.rpgBindPositionBuffer(floatsBuffer, noesis.RPGEODATA_FLOAT, 12)
								elif sd.type == 65: 
									rapi.rpgBindUV1Buffer(floatsBuffer, noesis.RPGEODATA_FLOAT, 8)
								elif sd.type == 75: 
									rapi.rpgBindUV2Buffer(floatsBuffer, noesis.RPGEODATA_FLOAT, 8)
								elif sd.type == 76: 
									rapi.rpgBindUVXBuffer(floatsBuffer, noesis.RPGEODATA_FLOAT, 8, 2, sd.numVerts)
							except:
								print("Failed to bind buffer type", sd.type)
					else:
						#Positions
						if j == 0:
							rapi.rpgBindPositionBuffer(bs.readBytes(sd.stride * sm.numVerts), noesis.RPGEODATA_FLOAT if sd.stride==12 else noesis.RPGEODATA_HALFFLOAT, sd.stride)
						#UVs
						elif sd.type == 34: 
							foundUVs += 1
							rapi.rpgBindUVXBuffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4, foundUVs-1, sm.numVerts)
						#Normals/Tangents
						elif sd.type == 31 and foundNormals != 2:
							foundNormals += 1
							if foundNormals == 1:
								rapi.rpgBindNormalBuffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_BYTE, 4)
							elif foundNormals == 2:
								rapi.rpgBindTangentBuffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_BYTE, 4)
						#Extra vec4 halfs
						elif sd.type == 10:
							foundColors += 1
							if dialogOptions.readColors  and foundColors == 1:
								rapi.rpgBindColorBufferOfs(bs.readBytes(8 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4, 0, 4)
							else:
								self.userStreams[i] = self.userStreams.get(i) or []
								self.userStreams[i].append(NoeUserStream("Vec4Halfs_" + str(foundColors-1), bs.readBytes(8 * sm.numVerts), 8, 0))
						else:
							print("Omitting vertex component type", sd.type, "found at", bs.tell())
				
				if self.boneList and sm.skinDesc:
					bs.seek(sm.skinDesc.mapOffset)
					vertWeightOffsets = []
					for b in range(sm.numVerts):
						vertWeightOffsets.append((bs.readUInt(), bs.readUInt()))
					idsList = []
					weightList = []
					for v, offsetsCounts in enumerate(vertWeightOffsets):
						bs.seek(sm.skinDesc.weightsOffset + offsetsCounts[1])
						for w in range(12):
							if w >= offsetsCounts[0]:
								weightList.append(0)
								idsList.append(0)
							elif sm.skinDesc.uncompressed:
								weightList.append(bs.readFloat())
								idsList.append(bs.readUInt())
							else:
								weightList.append(bs.readBits(22))
								idsList.append(bs.readBits(10) + startingBonesCt)
					if sm.skinDesc.uncompressed:
						rapi.rpgBindBoneIndexBufferOfs(struct.pack("<" + 'I'*len(idsList), *idsList), noesis.RPGEODATA_UINT, 48, 0, 12)
						rapi.rpgBindBoneWeightBufferOfs(struct.pack("<" + 'f'*len(weightList), *weightList), noesis.RPGEODATA_FLOAT, 48, 0, 12)
					else:
						rapi.rpgBindBoneIndexBufferOfs(struct.pack("<" + 'H'*len(idsList), *idsList), noesis.RPGEODATA_USHORT, 24, 0, 12)
						rapi.rpgBindBoneWeightBufferOfs(struct.pack("<" + 'I'*len(weightList), *weightList), noesis.RPGEODATA_UINT, 48, 0, 12)
				try:
					bs.seek(sm.facesOffset)
					rapi.rpgCommitTriangles(bs.readBytes(2 * sm.numIndices), noesis.RPGEODATA_USHORT, sm.numIndices, noesis.RPGEO_TRIANGLE, 0x1)
				except:
					print("Failed to bind submesh", i)
				
				rapi.rpgClearBufferBinds()
				
			print("\n====================================\n\"" + rapi.getLocalFileName(self.path or rapi.getInputName()) + "\" Textures list:")
			sortedTupleList = sorted([ (subTuple[1], subTuple[0]) for hash, subTuple in self.vrams.items() ])
			for sortTuple in sortedTupleList:
				if sortTuple[0]:
					print("    " + sortTuple[0].replace(".tga", texoutExt) + "  --  " + str(dxFormat.get(readUIntAt(bs, sortTuple[1]+72))))
			print("")
			
		else:
			print("Geometry data not found!")
			
		return 1

def pakLoadModel(data, mdlList):
	
	global dialogOptions, gameName
	
	noesis.logPopup()
	print("\n\n	Naughty Dog PAK model import", Version, "by alphaZomega\n")
	
	if noesis.optWasInvoked("-lods"):
		dialogOptions.doLODs = True
	
	#Close existing dialog (if open)
	if dialogOptions.dialog and dialogOptions.dialog.isOpen:
		dialogOptions.dialog.isOpen = False
		dialogOptions.dialog.isCancelled = True
		dialogOptions.dialog.noeWnd.closeWindow()
	
	noDialog = noesis.optWasInvoked("-nodialog") or NoDialog
	pak = PakFile(NoeBitStream(data), {'path':rapi.getInputName()})
	ctx = rapi.rpgCreateContext()
	gameName = getGameName()
	
	if not noDialog:
		pak.readPakHeader()
		dialog = openOptionsDialogWindow(None, None, {"pak":pak})
		dialog.createPakWindow()
		pak.readPak()
	
	if not noDialog and dialog.isCancelled:
		mdlList.append(NoeModel())
	else:
		pak.loadGeometry()
		
		if noDialog:
			if pak.submeshes[0].skinDesc and not pak.boneList and dialogOptions.doLoadBase:
				guessedName = pak.path.replace(".pak", ".skel.pak")
				for key, value in baseSkeletons[gameName].items():
					if pak.path.find(key) != -1:
						guessedName = BaseDirectories[gameName] + value
						break
				skelPath = guessedName
				
				while skelPath and not rapi.checkFileExists(skelPath):
					skelPath = noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Skeleton Not Found", "Input the path to the .pak containing this model's skeleton", guessedName, None) 
				if skelPath and rapi.checkFileExists(skelPath):
					pak.basePak = PakFile(NoeBitStream(rapi.loadIntoByteArray(skelPath)), {'path':skelPath})
					pak.basePak.readPak()
					pak.boneList = pak.basePak.boneList
					pak.boneMap = pak.basePak.boneMap
					pak.boneDict = pak.basePak.boneDict
				else:
					print("Failed to load Skeleton", skelPath or "[No path found]")
		else:
			for fullOtherPath in dialog.fullLoadItems:
				if rapi.getLocalFileName(fullOtherPath) != dialog.name: 
					if rapi.checkFileExists(fullOtherPath):
						otherPak = PakFile(NoeBitStream(rapi.loadIntoByteArray(fullOtherPath)), {'path':fullOtherPath})
						otherPak.texList = pak.texList
						otherPak.matList = pak.matList
						otherPak.boneList = pak.boneList
						otherPak.doLODs = pak.doLODs
						startingBonesCt = len(pak.boneList) if pak.boneList else 0
						otherPak.readPak()
						otherPak.loadGeometry(startingBonesCt if otherPak.jointOffset != None else 0)
		try:
			mdl = rapi.rpgConstructModelAndSort()
		except:
			print ("Failed to construct model")
			mdl = NoeModel()
			
		if pak.texList:
			mdl.setModelMaterials(NoeModelMaterials(pak.texList, pak.matList))
		
		mdlList.append(mdl)
		
		if pak.boneList:
			pak.boneList = rapi.multiplyBones(pak.boneList)
			if dialog and len(dialog.loadItems) > 1:
				for bone in pak.boneList:
					if bone.name.find("root_hair") != -1:
						bone.parentName = "headb" 
						break
			for mdl in mdlList:
				mdl.setBones(pak.boneList)
				
		if pak.userStreams:
			for meshIdx, userStreamList in pak.userStreams.items():
				if userStreamList and meshIdx < len(mdl.meshes):
					mdl.meshes[meshIdx].setUserStreams(userStreamList)
		#for mesh in mdl.meshes:
		#	print (mesh.name, mesh.positions)
		
	return 1

def pakWriteModel(mdl, bs):
	
	global pointerPageIds, pakPageEntries, gameName
	
	noesis.logPopup()
	print("\n\n	Naughty Dog PAK model export", Version, "by alphaZomega\n")
	gameName = getGameName()
	
	def getExportName(fileName):		
		if fileName == None:
			injectMeshName = re.sub(r'out\w+\.', '.', rapi.getOutputName().lower()).replace("fbx",".").replace("out.pak",".pak")
			splittedTarget = injectMeshName.split("ncharted4_data", 1)
			splittedSource = BaseDirectories[gameName].split("ncharted4_data", 1)
			if len(splittedTarget) > 1 and len(splittedSource) > 1 and rapi.checkFileExists(splittedSource[0] + "ncharted4_data" + splittedTarget[1].replace(".orig", "")): 
				injectMeshName = splittedSource[0] + "ncharted4_data" + splittedTarget[1].replace(".orig", "")
			if rapi.checkFileExists(injectMeshName.replace(".pak", ".orig.pak")):
				injectMeshName = injectMeshName.replace(".pak", ".orig.pak")
		else:
			injectMeshName = fileName
		injectMeshName = noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Export .pak", "Choose a .pak file to inject", injectMeshName, None)
		
		if injectMeshName == None:
			print("Aborting...")
			return
		return injectMeshName
		
	fileName = None
	if noesis.optWasInvoked("-meshfile"):
		injectMeshName = noesis.optGetArg("-meshfile")
	else:
		injectMeshName = getExportName(fileName)
	
	if injectMeshName == None:
		return 0
	while not (rapi.checkFileExists(injectMeshName)):
		print ("File not found!")
		if noesis.optGetArg("-meshfile"):
			print(injectMeshName, "\n", getExportName(fileName))
		injectMeshName = getExportName(fileName)	
		fileName = injectMeshName
		if injectMeshName == None or noesis.optGetArg("-meshfile"):
			return 0
			
	srcMesh = rapi.loadIntoByteArray(injectMeshName)
	
	if noesis.optWasInvoked("-lods"):
		dialogOptions.doLODs = True
	
	f = NoeBitStream(srcMesh)
	magic = readUIntAt(f, 0) 
	if magic != 2681 and magic != 68217 and magic != 2147486329 and magic != 2685:
		print("Not a known .pak file.\nAborting...")
		return 0
	
	#copy file:
	bs.writeBytes(f.readBytes(f.getSize()))
	
	source = PakFile(f)
	for hint, fileName in baseSkeletons[gameName].items():
		if rapi.getOutputName().find(hint) != -1:
			dialogOptions.baseSkeleton = fileName
			
	source.readPakHeader()
	texOnly = noesis.optWasInvoked("-t") or dialogOptions.isTLOU2
	if texOnly:
		print("Embedding textures only")
	
	if source.needsBasePak and not rapi.checkFileExists(BaseDirectories[gameName] + (dialogOptions.baseSkeleton or "")):
		dialogOptions.baseSkeleton = injectMeshName.replace(".pak", "-base.pak")
		while dialogOptions.baseSkeleton != None and not rapi.checkFileExists(dialogOptions.baseSkeleton):
			dialogOptions.baseSkeleton = noesis.userPrompt(noesis.NOEUSERVAL_FILEPATH, "Skeleton Not Found", "Input the path to the .pak containing this model's skeleton", dialogOptions.baseSkeleton, None) 
		if not dialogOptions.baseSkeleton:
			print("No base skeleton was found for skinned mesh, aborting...")
			return 0
			
	source.readPak()
	
	boneDict = {}
	if not texOnly or (noesis.optWasInvoked("-bones") and source.basePak.jointOffset):
		try:
			for i, bone in enumerate(source.boneList):
				boneDict[bone.name] = i
		except:
			print("ERROR: Could not load base skeleton")
	
	if source.submeshes:
		
		doWrite = didAppend = False
		lastLOD = 0
		isNoesisSplit = (mdl.meshes[0].name[:5] == "0000_")
		fbxMeshList = mdl.meshes if not isNoesisSplit else recombineNoesisMeshes(mdl)
		
		f.seek(source.geoOffset[0] + source.geoOffset[1] + 72)
		submeshesAddr = source.readPointerFixup()
		
		newPak = PakFile(bs)
		newPak.readPak()
		
		#write new bone positions:
		newBaseFile = ""
		if noesis.optWasInvoked("-bones") and (source.basePak or newPak).jointOffset:
			bonePak = source.basePak or newPak
			bonestream = bonePak.bs
			ji = bonePak.jointsInfo
			for i, bone in enumerate(mdl.bones):
				boneID = boneDict.get(bone.name)
				if boneID != None and boneID in bonePak.boneMap:
					xformBoneID = bonePak.boneMap.index(boneID)
					boneMat = bone.getMatrix()
					if bone.parentIndex != -1:
						boneMat = boneMat * mdl.bones[bone.parentIndex].getMatrix().inverse()
					boneMat = boneMat.transpose()
					bonestream.seek(ji.transformsStart + xformBoneID*48 + 16)
					bonestream.writeBytes(boneMat.toQuat().toBytes())
					bonestream.writeBytes((boneMat[3] * (1/GlobalScale)).toBytes())
					bonestream.seek(ji.parentingStart + boneID*16 + 4)
					if bone.parentIndex == -1:
						bonestream.writeInt(-1)
					elif boneDict.get(bone.parentName):
						bonestream.writeInt(boneDict.get(bone.parentName))
			if source.basePak:
				newBaseFile = rapi.getOutputName().replace(rapi.getLocalFileName(rapi.getOutputName()), rapi.getLocalFileName(bonePak.path)).replace(".NEW", "").replace(".pak", ".NEW.pak")
				open(newBaseFile, "wb").write(bonestream.getBuffer())
		
		if not texOnly:
			
			meshesToInject = []
			submeshesFound = []
			
			for i, sm in enumerate(source.submeshes):
				writeMesh = None
				for mesh in fbxMeshList:
					fixMeshName = rapi.getExtensionlessName(mesh.name)
					if fixMeshName == sm.name:
						writeMesh = mesh
						submeshesFound.append(fixMeshName)
						break
				if not writeMesh:
					blankMeshName = sm.name
					blankTangent = NoeMat43((NoeVec3((0,0,0)), NoeVec3((0,0,0)), NoeVec3((0,0,0)), NoeVec3((0,0,0)))) 
					blankWeight = NoeVertWeight([0], [1])
					writeMesh = NoeMesh([0, 1, 2], [NoeVec3((0.00000000001,0,0)), NoeVec3((0,0.00000000001,0)), NoeVec3((0,0,0.00000000001))], blankMeshName, blankMeshName, -1, -1) #positions and faces
					writeMesh.setUVs([NoeVec3((0,0,0)), NoeVec3((0,0,0)), NoeVec3((0,0,0))]) #UV1
					writeMesh.setUVs([NoeVec3((0,0,0)), NoeVec3((0,0,0)), NoeVec3((0,0,0))], 1) #UV2
					writeMesh.setTangents([blankTangent, blankTangent, blankTangent]) #Normals + Tangents
					writeMesh.setWeights([blankWeight,blankWeight,blankWeight]) #Weights + Indices
				meshesToInject.append((writeMesh, sm))
			
			if len(submeshesFound) > 0:
				doWrite = True
				print("Found the following submeshes to inject from FBX:")
				for meshName in submeshesFound: 
					print("    " + meshName)
				print("\nAll other submeshes in this pak will be turned into invisible placeholders.\n")
			else:
				print("Found no submeshes to inject from FBX, copying original file...")
			
			if doWrite:
				
				wb = NoeBitStream()
				newPageStreams = []
				pageCt = readUIntAt(f, 16)
				pointerFixupPageCt = readUIntAt(bs, 24)
				pointerFixupTblOffs = readUIntAt(bs, 28)
				isModded = (readUIntAt(f, pointerFixupTblOffs + 12*8) == 4294967295)
				newPage = pageCt if not isModded else pageCt-1
				
				for i, meshTuple in enumerate(meshesToInject):
					
					writeMesh = meshTuple[0]
					sm = meshTuple[1]
					lodFind = sm.name.find("Shape")
					LODidx = int(sm.name[lodFind+5]) if lodFind != -1 and sm.name[lodFind+5].isnumeric() else 0
					if LODidx > lastLOD:
						lastLOD = LODidx
					if not dialogOptions.doLODs and LODidx > 0:
						if len(writeMesh.positions) == 3:# and LODidx  and lodIdx < :
							continue
					
					print("Injecting ", writeMesh.name)
					appendedPositions = appendedWeights = appendedIndices = isModded #False
					newPageDataAddr = source.pakPageEntries[len(source.pakPageEntries)-1][0] + source.pakPageEntries[len(source.pakPageEntries)-1][1]
					owningIndex = source.pakPageEntries[len(source.pakPageEntries)-1][2]
					vertOffs = submeshesAddr + 176*i + 36
					foundPositions = foundUVs = foundNormals = 0
					appendedPositions = (len(writeMesh.positions) > sm.numVerts) or appendedPositions #and (not isModded or (source.getPointerFixupPage(sm.streamDescs[0].bufferOffsetAddr) < pageCt-1))
					tempbs = wb if appendedPositions else bs
					wroteColors = False
					
					bs.seek(sm.streamsAddr)
					#sdBytesList = []
					#finalSdBytesList = []
					#for j, sd in enumerate(sm.streamDescs):
					#	sdBytesList.append(bs.readBytes(24))
					
					for j, sd in enumerate(sm.streamDescs):
						bs.seek(sd.offset)
						
						
						if appendedPositions and wb.tell() + sd.stride * len(writeMesh.positions) > 1048032: #pages have a maximum size
							newPageStreams.append(wb)
							newPage += 1
							wb = NoeBitStream()
							tempbs = wb
							
						if appendedPositions: 
							newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)
						
						bufferStart = tempbs.tell()
						for b in range(sd.stride * len(writeMesh.positions)):
							tempbs.writeByte(0)
						bufferEnd = tempbs.tell()
						tempbs.seek(bufferStart)
						
						if ((j == 0 and sd.stride == 12 or sd.stride == 8)) and not foundPositions:
							bFoundPositions = True
							#finalSdBytesList.append(sdBytesList[j])
							if sd.stride == 12:
								for v, vert in enumerate(writeMesh.positions):
									tempbs.writeFloat(vert[0] * (1/GlobalScale))
									tempbs.writeFloat(vert[1] * (1/GlobalScale))
									tempbs.writeFloat(vert[2] * (1/GlobalScale))
							elif sd.stride == 8:
								for v, vert in enumerate(writeMesh.positions):
									tempbs.writeHalfFloat(vert[0] * (1/GlobalScale))
									tempbs.writeHalfFloat(vert[1] * (1/GlobalScale))
									tempbs.writeHalfFloat(vert[2] * (1/GlobalScale))
									tempbs.writeHalfFloat(0)
									
						elif sd.type == 34:
							foundUVs += 1
							UVs = []
							if foundUVs == 1 and writeMesh.uvs:
								UVs = writeMesh.uvs
							elif foundUVs == 2 and writeMesh.lmUVs:
								UVs = writeMesh.lmUVs
							elif foundUVs > 2 and writeMesh.uvxList and len(writeMesh.uvxList) > foundUVs-3:
								UVs = writeMesh.uvxList[foundUVs-3]
							
							if len(UVs) == len(writeMesh.positions):
								for v, vert in enumerate(UVs):
									tempbs.writeHalfFloat(vert[0])
									tempbs.writeHalfFloat(vert[1])
							else:
								for v, vert in enumerate(writeMesh.positions):
									tempbs.writeHalfFloat(0)
									tempbs.writeHalfFloat(0)
									
						elif sd.type == 31 and foundNormals < 2:
							foundNormals += 1
							#finalSdBytesList.append(sdBytesList[j])
							if foundNormals == 1:
								for v, vert in enumerate(writeMesh.tangents): 
									tempbs.writeByte(int(vert[0][0] * 127 + 0.5000000001)) #normal
									tempbs.writeByte(int(vert[0][1] * 127 + 0.5000000001))
									tempbs.writeByte(int(vert[0][2] * 127 + 0.5000000001))
									tempbs.writeByte(0)
							elif foundNormals == 2: 
								for v, vert in enumerate(writeMesh.tangents):
									tempbs.writeByte(int(vert[2][0] * 127 + 0.5000000001)) #bitangent
									tempbs.writeByte(int(vert[2][1] * 127 + 0.5000000001))
									tempbs.writeByte(int(vert[2][2] * 127 + 0.5000000001))
									TNW = vert[0].cross(vert[1]).dot(vert[2])
									if (TNW < 0.0):
										tempbs.writeByte(129)
									else:
										tempbs.writeByte(127)
						
						elif sd.type == 10:
							if writeMesh.colors and not wroteColors:
								wroteColors = True
								#finalSdBytesList.append(sdBytesList[j])
								for v, vert in enumerate(writeMesh.colors):
									tempbs.writeHalfFloat(vert[0])
									tempbs.writeHalfFloat(vert[1])
									tempbs.writeHalfFloat(vert[2])
									tempbs.writeHalfFloat(0)
							else:
								for v in range(len(writeMesh.positions)):
									tempbs.writeHalfFloat(0)
									tempbs.writeHalfFloat(0)
									tempbs.writeHalfFloat(0)
									tempbs.writeHalfFloat(0)
									
						else:
							print("Nulling unknown component type", sd.type)

						
						#bs.seek(sm.streamsAddr)
						#for rawBytes in finalSdBytesList:
						#	bs.writeBytes(rawBytes)
						
						tempbs.seek(bufferEnd)
						if bufferEnd - bufferStart > 0:
							writeUIntAt(bs, sd.bufferOffsetAddr - 12, bufferEnd-bufferStart) #buffer size
					
					
					if sm.skinDesc:
					
						fbxWeightCount = 0
						trueWeightCounts = []
						for v, vertWeight in enumerate(writeMesh.weights):
							trueWeightCounts.append(0)
							for w, weight in enumerate(vertWeight.weights):
								if weight > 0: 
									fbxWeightCount += 1
									trueWeightCounts[v] += 1
									
						if appendedPositions and wb.tell() > 0 and wb.tell() + 8*len(writeMesh.positions) > 1048032:
							newPageStreams.append(wb)
							newPage += 1
							wb = NoeBitStream()
							
						runningOffset = boneID = 0
						idxStart = wb.tell() if appendedPositions else sm.skinDesc.mapOffset
						idxbs = wb if appendedPositions else bs
						
						if appendedPositions:
							newPak.changePointerFixup(sm.skinDesc.mapOffsetAddr, idxStart, newPage)
							for vertWeight in writeMesh.weights:
								wb.writeUInt64(0)
						
						appendedWeights = (fbxWeightCount > sm.skinDesc.weightCount)
						if appendedWeights:
							if 4*fbxWeightCount > 1048032:
								print("\nWARNING: Weights buffer exceeds the maximum page size of 262008 weights (has " + str(fbxWeightCount) + ")!\n")
							if wb.tell() > 0 and wb.tell() + 4*fbxWeightCount > 1048032:
								newPageStreams.append(wb)
								newPage += 1
								wb = NoeBitStream()
							newPak.changePointerFixup(sm.skinDesc.weightOffsetAddr, wb.tell(), newPage)
							
						wtStart = wb.tell() if appendedWeights else sm.skinDesc.weightsOffset
						tempbs = wb if appendedWeights else bs
						
						for v, vertWeight in enumerate(writeMesh.weights):
							idxbs.seek(idxStart + 8*v)
							idxbs.writeUInt(trueWeightCounts[v])
							idxbs.writeUInt(runningOffset)
							tempbs.seek(wtStart + runningOffset)
							for w, weight in enumerate(vertWeight.weights):
								if weight > 0:
									try:
										boneID = boneDict[mdl.bones[vertWeight.indices[w]].name]
									except:
										print("Bone weight ID", w, mdl.bones[vertWeight.indices[w]].name, "not found in pak skeleton")
									tempbs.writeUInt((boneID << 22) | int(weight * 4194303))
									runningOffset += 4
						
						writeUIntAt(bs, sm.skinDesc.mapOffsetAddr-12, int(runningOffset/4))
					
					if len(writeMesh.indices) > sm.numIndices:
						appendedIndices = True
						if appendedIndices and wb.tell() + 6*len(writeMesh.positions) > 1048032:
							newPageStreams.append(wb)
							newPage += 1
							wb = NoeBitStream()
							
						newPak.changePointerFixup(sm.facesOffsetAddr, wb.tell(), newPage)
						for k, idx in enumerate(writeMesh.indices):
							wb.writeUShort(idx)
					else:
						bs.seek(sm.facesOffset)
						for k, idx in enumerate(writeMesh.indices):
							bs.writeUShort(idx)
					
					while (wb.tell() % 16 != 0): 
						wb.writeByte(0)
					wb.writeUInt64(0)
					wb.writeUInt(0)
						
					#Null out normals recalculation values:
					if sm.nrmRecalcDesc:
						#bs.seek(sm.nrmRecalcDesc[5])
						#bs.writeUInt64(0)
						
						'''bs.seek(sm.nrmRecalcDesc[1])
						for k in range(sm.nrmRecalcDesc[4]):
							bs.writeShort(0)
						bs.seek(sm.nrmRecalcDesc[3])
						for k in range(sm.nrmRecalcDesc[4]):
							bs.writeShort(0)'''
						nrmStart = wb.tell()
						for n in range(4):
							bs.seek(sm.nrmRecalcDesc[n])
							appendedPositions = appendedPositions or (len(writeMesh.positions) > readUIntAt(bs, sm.nrmRecalcDesc[6]-8))
							tempbs = wb if appendedPositions else bs
							if appendedPositions: 
								if n == 0 and wb.tell() + 2 * len(writeMesh.positions) > 1048032:
									newPageStreams.append(wb)
									newPage += 1
									wb = NoeBitStream()
									tempbs = wb
								newPak.changePointerFixup(sm.nrmRecalcDesc[6] + 8*n, nrmStart, newPage)
							if not appendedPositions or n == 0:
								for k in range(len(writeMesh.positions)):
									tempbs.writeShort(0)
							writeUIntAt(bs, sm.nrmRecalcDesc[6]-8, len(writeMesh.positions))
							writeUIntAt(bs, sm.nrmRecalcDesc[6]-4, len(writeMesh.indices))
					
					#set vertex/index counts:
					bs.seek(vertOffs)
					bs.writeUInt(len(writeMesh.positions))
					bs.writeUInt(len(writeMesh.indices))
					#bs.writeUInt(len(finalSdBytesList))
					
					didAppend = (didAppend or appendedPositions or appendedWeights or appendedIndices)
					if not isModded and (appendedPositions or appendedWeights or appendedIndices):
						print("Mesh will be appended to a new page: ", sm.name)
						if appendedPositions:
							print("	-exceeds the maximum vertex count of", sm.numVerts, "(has", str(len(writeMesh.positions)) + ")!")
						if appendedWeights:
							print("	-exceeds the maximum weight count of", sm.skinDesc.weightCount, "(has", str(fbxWeightCount) + ")!")
						if appendedIndices:
							print("	-exceeds the maximum poly count of", int(sm.numIndices/3), "(has", str(int(len(writeMesh.indices)/3)) + ")!")
							
				newPageStreams.append(wb)
					
			if isNoesisSplit:
				print("\nWARNING:	Duplicate mesh names detected! Check your FBX for naming or geometry issues. This pak may crash the game!\n")

		#Set all LODs except the last one to read as LOD0:
		if doWrite:# and not dialogOptions.doLODs:
			f.seek(source.geoOffset[0] + source.geoOffset[1] + 44)
			LODCount = f.readUInt()
			f.seek(32, 1)
			lodDescsOffset = source.readPointerFixup()
			f.seek(lodDescsOffset)
			lodDescs = []
			for a in range(LODCount):
				lodDescs.append(source.readPointerFixup())
			firstLODSubmeshOffs = readUIntAt(f, lodDescs[0] + 24)
			firstLODSubmeshCount = readUIntAt(f, lodDescs[0] + 4)
			for a in range(1, LODCount-1):
				bs.seek(lodDescs[a] + 24)
				bs.writeUInt64(firstLODSubmeshOffs)
				writeUIntAt(bs, lodDescs[a] + 4, firstLODSubmeshCount)
			'''
			#Selectively set submeshes in the last LOD to point to their equivalents in the first one (for shadows / rendering):
			subNamesDict = {}
			for lodSubmeshDesc in newPak.lods[0]:
				name = lodSubmeshDesc.name.split("_lod", 1)[0]
				subNamesDict[name] = subNamesDict.get(name) or [] #these names arent consistent...
				subNamesDict[name].append(lodSubmeshDesc)
			
			print("Dict", subNamesDict)
			for lowLODSubmeshDesc in newPak.lods[len(newPak.lods)-1]:
				name = lowLODSubmeshDesc.name.split("_lod0", 1)[0]
				if subNamesDict.get(name):
					lod0SubDesc = subNamesDict[name][0]
					print("Changing low LOD submesh", lowLODSubmeshDesc.name, "into", lod0SubDesc.name)
					newPak.changePointerFixup(lowLODSubmeshDesc.address, lod0SubDesc.offset, newPak.getPointerFixupPage(lowLODSubmeshDesc.address))
					writeUIntAt(bs, lowLODSubmeshDesc.address+8, lod0SubDesc.index)
					del subNamesDict[name][0]'''
			
				
		#Embed image data
		path = rapi.getDirForFilePath(rapi.getOutputName())+rapi.getLocalFileName(rapi.getOutputName()).split(".", 1)[0]
		path2 = rapi.getDirForFilePath(injectMeshName)+rapi.getLocalFileName(injectMeshName).split(".", 1)[0]
		if noesis.optWasInvoked("-texfolder") and os.path.isdir(noesis.optGetArg("-texfolder")):
			path = noesis.optGetArg("-texfolder")
		print("\nChecking for textures to embed in:\n -", path, "\n -", path2)
		path = path2 if not os.path.isdir(path) else path
		#texInjectExt = ".tga" if dialogOptions.isTLOU2 else texoutExt
		
		if os.path.isdir(path):
			source.bs = bs
			vramPathDict = {}
			for hash, vramTuple in source.vrams.items():
				vramPathDict[vramTuple[1]] = (vramTuple[0], hash)
				
			for fileName in os.listdir(path):
				if os.path.isfile(os.path.join(path, fileName)) and fileName.count(texoutExt):
					vramTuple = vramPathDict.get(fileName)
					if vramTuple:
						print("\nEmbedding texture", fileName)
						source.writeVRAMImage(vramTuple[0], os.path.join(path, fileName))
						vramPathDict[fileName] = 0
					elif vramTuple != 0:
						print("Texture was found, but is not in the pak file\n	", fileName)
							
							
		if doWrite and didAppend:
			
			newPageDataAddrs = []
			numPages = len(newPageStreams)
			newPakPageHeaders = NoeBitStream()
			addAmt = 12*numPages
			orgPFixupPadAmt = 16 - ((pointerFixupTblOffs+8*12) % 16)
			pFixupPadAmt = 16 - ((pointerFixupTblOffs+8*12+addAmt+orgPFixupPadAmt) % 16) + 16 #pad to 16-bytes aligned, then add +16 bytes of new padding for 4294967295 modded marker / extra info
			writeUIntAt(bs, 28, pointerFixupTblOffs+12*numPages) #write pointerFixupTableOffset
			writeUIntAt(bs, 16, pageCt+numPages) # add new pages
			writeUIntAt(bs, pointerFixupTblOffs+4, readUIntAt(bs, pointerFixupTblOffs+4)+addAmt+pFixupPadAmt) #new dataOffset

			bs.seek(pointerFixupTblOffs)
			oldBytes = bs.readBytes(12) #copy old pointerFixup
			bs.seek(-12, 1)
			for i, wb in enumerate(newPageStreams):
				newPageDataAddrs.append(newPageDataAddr)
				while (newPageDataAddr+addAmt+pFixupPadAmt+wb.getSize()) % 16 != 12: #pad it out
					wb.writeByte(0)
				newPakPageHeaders.writeUInt(newPageDataAddr+addAmt+pFixupPadAmt) # new page offset
				newPakPageHeaders.writeUInt(wb.getSize()+20) # new page size
				newPakPageHeaders.writeUInt(owningIndex) # new package owning index
				newPageDataAddr = newPageDataAddr + wb.getSize()+20
				
			writeUIntAt(bs, 4, readUIntAt(bs, 4)+addAmt+pFixupPadAmt) #add to headerSz
			
			bs.seek(readUIntAt(bs, 20))
			for i in range(pageCt):
				bs.writeUInt(readUIntAt(bs, bs.tell())+addAmt+pFixupPadAmt) #add to each pageEntryOffset
				bs.seek(8, 1)
					
			if isModded:
				print("\nWARNING: File was previously injected. It is recommended to inject an unedited pak file\n")
			
			bs.seek(0)
			ns = NoeBitStream()
			ns.writeBytes(bs.readBytes(pointerFixupTblOffs))
			ns.writeBytes(newPakPageHeaders.getBuffer())
			ns.writeBytes(oldBytes)
			
			for i in range(7):
				ns.writeUInt64(0)
				ns.writeUInt(0)
			for i in range(pFixupPadAmt):
				ns.writeByte(0)
			if not isModded:
				writeUIntAt(ns, ns.tell()-pFixupPadAmt, 4294967295) #modded file marker
				writeUIntAt(ns, ns.tell()-pFixupPadAmt+4, pageCt) #original unmodded page count
			
			bs.seek(pointerFixupTblOffs+12*8)
			
			ns.writeBytes(bs.readBytes(newPageDataAddrs[0] - bs.tell()))
			
			for i, wb in enumerate(newPageStreams):
				ns.writeUInt64(16045690984833335023) #0xDEADBEEF
				ns.writeUInt(0) #74565) #unknown
				ns.writeUInt(wb.getSize()+20) #new size
				ns.writeUShort(owningIndex)
				ns.writeUShort(0)
				ns.writeBytes(wb.getBuffer())
				#if isModded:
				#	bs.seek(newPageDataAddrs[i]) #skip (delete) contents of page from previous injection
			ns.writeBytes(bs.readBytes(bs.getSize()-bs.tell()))
			
			bs.seek(0)
			bs.writeBytes(ns.getBuffer())
			
			print("Added", numPages, "new pages")
		
		if newBaseFile:
			print("Wrote new skeleton to", newBaseFile)
		
	return 1
	
