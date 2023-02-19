#fmt_nd_pak.py - Uncharted 4 ".pak" plugin for Rich Whitehouse's Noesis
#Authors: alphaZomega 
#Special Thanks: icemesh 
Version = 'v1.31 (February 19, 2023)'


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


# Set the base path from which the plugin will search for pak files and textures:
BaseDirectories = {
	"TLL": "D:\\ExtractedGameFiles\\Uncharted4_data\\build\\pc\\thelostlegacy\\",
	"U4": "D:\\ExtractedGameFiles\\Uncharted4_data\\build\\pc\\uncharted4\\",
}

from inc_noesis import *
from collections import namedtuple
import noewin
import json
import os
import re
import random



class DialogOptions:
	def __init__(self):
		self.doLoadTex = LoadTextures
		self.doLoadBase = LoadBaseSkeleton
		self.doConvertTex = ConvertTextures
		self.doFlipUVs = FlipUVs
		self.doLODs = LoadAllLODs
		self.loadAllTextures = LoadAllTextures
		self.printMaterialParams = PrintMaterialParams
		self.readColors = ReadColors
		self.baseSkeleton = None
		self.width = 600
		self.height = 800
		self.texDicts = None
		self.gameName = gameName
		self.dialog = None

dialogOptions = DialogOptions()

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
	if magic == 2681 and magic != 68217 and magic != 2147486329:
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
	
def mergeChannelsRGBA(sourceBytes, sourceChannel, sourceWidth, sourceHeight, targetBytes, targetChannel, targetWidth, targetHeight):
	resizedSourceBytes = rapi.imageResample(sourceBytes, sourceWidth, sourceHeight, targetWidth, targetHeight)
	#resizedSourceBytes = rapi.imageEncodeRaw(resizedSourceBytes, targetWidth, targetHeight, "r8g8b8a8")
	#resizedSourceBytes = rapi.imageDecodeRaw(resizedSourceBytes, targetWidth, targetHeight, "r8g8b8a8")
	outputTargetBytes = copy.copy(targetBytes)
	for i in range(int(len(resizedSourceBytes)/16)):
		for b in range(4):
			outputTargetBytes[i*16 + b*4 + targetChannel] = resizedSourceBytes[i*16 + b*4 + sourceChannel]
	
	return outputTargetBytes

def encodeImageData(data, width, height, fmt):
	outputData = NoeBitStream()
	mipWidth = width
	mipHeight = height
	mipCount = 0
	while mipWidth > 2 or mipHeight > 2:
		mipData = rapi.imageResample(data, width, height, mipWidth, mipHeight)
		try:
			dxtData = rapi.imageEncodeDXT(mipData, 4, mipWidth, mipHeight, fmt)
		except:
			dxtData = rapi.imageEncodeRaw(mipData, mipWidth, mipHeight, fmt)
		outputData.writeBytes(dxtData)
		if mipWidth > 2: 
			mipWidth = int(mipWidth / 2)
		if mipHeight > 2: 
			mipHeight = int(mipHeight / 2)
		mipCount += 1
		
	return outputData.getBuffer(), mipCount


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

fullGameNames = ["Uncharted 4", "The Lost Legacy"]
gamesList = [ "U4", "TLL"]

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
	]
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
	"TLL": {
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
	}
}

class openOptionsDialogWindow:
	
	def __init__(self, width=dialogOptions.width, height=dialogOptions.height, args=[]):
		global dialogOptions
		
		self.width = width
		self.height = height
		self.pak = args.get("pak") or None
		self.path = self.pak.path or rapi.getInputName()
		self.name = rapi.getLocalFileName(self.path)
		self.loadItems = [self.name]
		self.localDir = rapi.getDirForFilePath(self.path)
		self.localRoot = findRootDir(self.path)
		self.baseDir = BaseDirectories[gameName] 
		self.allFiles = []
		self.subDirs = []
		self.pakIdx = 0
		self.baseIdx = -1
		self.loadIdx = 0
		self.dirIdx = 0
		self.gameIdx = 0
		self.localIdx = 0
		self.isOpen = True
		self.isCancelled = False
		self.isStarted = False
		self.firstBaseDir = ""
		if os.path.isdir(self.baseDir):
			for item in os.listdir(self.baseDir):
				if os.path.isdir(os.path.join(self.baseDir, item)):
					self.firstBaseDir = item
					if item == "actor77": break
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
		
	def selectDirListItem(self, noeWnd, controlId, wParam, lParam):
		if self.dirList.getSelectionIndex() == -1:
			self.dirList.selectString(self.subDirs[0])
		if self.dirIdx != self.dirList.getSelectionIndex() and dialogOptions.currentDir != self.dirList.getStringForIndex(self.dirList.getSelectionIndex()):
			self.dirIdx = self.dirList.getSelectionIndex()
			dialogOptions.currentDir = self.dirList.getStringForIndex(self.dirIdx)
			self.setDirList()
			self.setPakList()
	
	def selectBaseListItem(self, noeWnd, controlId, wParam, lParam):
		self.baseIdx = self.baseList.getSelectionIndex()
		dialogOptions.baseSkeleton = self.baseList.getStringForIndex(self.baseIdx)
		
	def selectPakListItem(self, noeWnd, controlId, wParam, lParam):
		if self.pakIdx != self.pakList.getSelectionIndex() and self.pakList.getStringForIndex(self.pakList.getSelectionIndex()) not in self.loadItems: #and self.pakIdx != -1 
			self.pakIdx = self.pakList.getSelectionIndex()
			item = self.pakList.getStringForIndex(self.pakIdx)
			if item:
				self.loadItems.append(item)
				self.loadList.addString(self.pakList.getStringForIndex(self.pakIdx))
				self.loadItems = sorted(self.loadItems)
				#self.loadList.selectString(self.pakList.getStringForIndex(self.pakIdx))
				#self.loadIdx = self.loadList.getSelectionIndex()
		self.pakIdx = self.pakList.getSelectionIndex()
	
	def selectLoadListItem(self, noeWnd, controlId, wParam, lParam):
		self.loadIdx = self.loadList.getSelectionIndex()
		if self.loadIdx != -1 and self.loadIdx < len(self.loadItems) and self.loadItems[self.loadIdx] != self.name:
			self.loadList.removeString(self.loadItems[self.loadIdx])
			del self.loadItems[self.loadIdx]
			self.loadIdx = self.loadIdx if self.loadIdx < len(self.loadItems) else self.loadIdx - 1
			self.loadList.selectString(self.loadItems[self.loadIdx])
	
	def selectGameBoxItem(self, noeWnd, controlId, wParam, lParam):
		global gameName
		if self.gameIdx != self.gameBox.getSelectionIndex():
			self.gameIdx = self.gameBox.getSelectionIndex()
			gameName = gamesList[self.gameIdx]
			if self.localBox.getStringForIndex(self.localIdx) == "Base Directory":
				self.baseDir = BaseDirectories[gameName]
				self.firstBaseDir = ""
				if os.path.isdir(self.baseDir):
					for item in os.listdir(self.baseDir):
						if os.path.isdir(os.path.join(self.baseDir, item)):
							self.firstBaseDir = item
							if item == "actor77": break
				self.setDirList()
				self.setPakList()
				self.setLoadList()
				
	def selectLocalBoxItem(self, noeWnd, controlId, wParam, lParam):
		if self.localIdx != self.localBox.getSelectionIndex():
			self.localIdx = self.localBox.getSelectionIndex()
			self.setDirList()
			self.setPakList()
			
	def setBaseList(self, list_object=None, current_item=None):
		for path in skelFiles[gameName]:
			self.baseList.addString(path)
		lastFoundHint = ""
		for hint, fileName in baseSkeletons[gameName].items():
			if self.name.find(hint) != -1 and len(hint) > len(lastFoundHint):
				lastFoundHint = hint
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
		
	def setLoadList(self):
		for item in self.loadItems:
			self.loadList.removeString(item)
		self.loadItems = [self.name]
		self.loadList.addString(self.loadItems[0])
		self.loadList.selectString(self.pak.path or rapi.getInputName())
		
	def setPakList(self):
		dirName = self.localDir if self.localIdx == 0 else self.baseDir + (dialogOptions.currentDir or self.firstBaseDir)
		if os.path.isdir(dirName):
			for name in self.allFiles:
				self.pakList.removeString(name)
			self.allFiles = []
			for item in os.listdir(dirName):
				if os.path.isfile(os.path.join(dirName, item)) and item.find(".pak") != -1:
					self.allFiles.append(item)
					self.pakList.addString(item)
			self.allFiles = sorted(self.allFiles)	
			if self.name in self.allFiles:
				self.pakIdx = self.allFiles.index(self.name)
				self.pakList.selectString(self.name)
		
	def setDirList(self):
		dirName = self.localRoot if self.localIdx == 0 else self.baseDir
		parentFolder = os.path.dirname(dirName)
		for name in self.subDirs:
			self.dirList.removeString(name)
		self.subDirs = []
		for folderName in os.listdir(parentFolder):
			if os.path.isdir(os.path.join(parentFolder, folderName)):
				self.subDirs.append(folderName)
				self.dirList.addString(folderName)
		#self.subDirs = sorted(self.subDirs) #wtf why does THIS one not need to be sorted?
		for folderName in self.subDirs:
			if not self.isStarted and self.localIdx == 0 and self.localDir.find(folderName) != -1:
				self.dirList.selectString(folderName)
				self.dirIdx = self.dirList.getSelectionIndex()
				dialogOptions.currentDir = folderName	
				break
		if self.localIdx == 1:
			self.dirList.selectString(self.subDirs[self.dirIdx])
			dialogOptions.currentDir = self.subDirs[self.dirIdx]
		else:
			self.dirIdx = self.dirList.getSelectionIndex()
			if self.dirIdx == -1:
				self.dirIdx = 0
				self.dirList.selectString(0)
			dialogOptions.currentDir = self.dirList.getStringForIndex(self.dirIdx)
		
		
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
			
			self.noeWnd.createStatic("Base:", 10, 5, width-20, 20)
			index = self.noeWnd.createComboBox(50, 5, width-65, 20, self.selectBaseListItem, noewin.CBS_DROPDOWNLIST) #CB
			self.baseList = self.noeWnd.getControlByIndex(index)
			
			
			self.noeWnd.createStatic("Files from:", 5, 45, width-20, 20)
			index = self.noeWnd.createComboBox(80, 40, width-95, 20, self.selectDirListItem, noewin.CBS_DROPDOWNLIST) #CB
			self.dirList = self.noeWnd.getControlByIndex(index)
			
			
			index = self.noeWnd.createListBox(5, 70, width-20, 400, self.selectPakListItem, noewin.CBS_DROPDOWNLIST) #LB
			self.pakList = self.noeWnd.getControlByIndex(index)
			
			self.noeWnd.createStatic("Files to load:", 5, 485, width-20, 20)
			index = self.noeWnd.createListBox(5, 505, width-20, 150, self.selectLoadListItem, noewin.CBS_DROPDOWNLIST) #LB
			self.loadList = self.noeWnd.getControlByIndex(index)
			
			
			if True:
				index = self.noeWnd.createCheckBox("Load Textures", 10, 665, 130, 30, self.checkLoadTexCheckbox)
				self.loadTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.loadTexCheckbox.setChecked(dialogOptions.doLoadTex)
				
				
				index = self.noeWnd.createCheckBox("Load All Textures", 140, 665, 160, 30, self.checkLoadAllTexCheckbox)
				self.loadAllTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.loadAllTexCheckbox.setChecked(dialogOptions.loadAllTextures)
				
				
				index = self.noeWnd.createCheckBox("Convert Textures", 10, 695, 130, 30, self.checkConvTexCheckbox)
				self.convTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.convTexCheckbox.setChecked(dialogOptions.doConvertTex)
				
				
				#index = self.noeWnd.createCheckBox("Flip UVs", 140, 680, 130, 30, self.checkFlipUVsCheckbox)
				#self.flipUVsCheckbox = self.noeWnd.getControlByIndex(index)
				#self.flipUVsCheckbox.setChecked(dialogOptions.doFlipUVs)
				
				
				index = self.noeWnd.createCheckBox("Load Base", 140, 695, 90, 30, self.checkBaseCheckbox)
				self.loadBaseCheckbox = self.noeWnd.getControlByIndex(index)
				self.loadBaseCheckbox.setChecked(dialogOptions.doLoadBase)
				
				
				index = self.noeWnd.createCheckBox("Import LODs", 270, 695, 100, 30, self.checkLODsCheckbox)
				self.LODsCheckbox = self.noeWnd.getControlByIndex(index)
				self.LODsCheckbox.setChecked(dialogOptions.doLODs)
				

			self.noeWnd.createStatic("Game:", width-198, 670, 60, 20)
			index = self.noeWnd.createComboBox(width-150, 665, 130, 20, self.selectGameBoxItem, noewin.CBS_DROPDOWNLIST) #CB
			self.gameBox = self.noeWnd.getControlByIndex(index)
			
			
			self.noeWnd.createStatic("View:", width-190, 700, 60, 20)
			index = self.noeWnd.createComboBox(width-150, 695, 130, 20, self.selectLocalBoxItem, noewin.CBS_DROPDOWNLIST) #CB
			self.localBox = self.noeWnd.getControlByIndex(index)
			
			
			self.noeWnd.createButton("Load", 5, height-70, width-160, 30, self.openOptionsButtonLoadEntry)
			self.noeWnd.createButton("Cancel", width-96, height-70, 80, 30, self.openOptionsButtonCancel)
			
			self.setLoadList()
			self.setBaseList(self.baseList, baseSkeletons[gameName]["chloe" if gameName == "TLL" else "hero"])
			self.setDirList()
			self.setPakList()
			self.setGameBox(self.gameBox)
			self.setLocalBox(self.localBox)
			self.isStarted = True
			
			self.noeWnd.doModal()
			
			

LODSubmeshDesc = namedtuple("LODSubmeshDesc", "name address offset index")

JointsInfo = namedtuple("JointsInfo", "transformsStart parentingStart")

StreamDesc = namedtuple("StreamDesc", "type offset stride bufferOffsetAddr")

SkinDesc = namedtuple("SkinDesc", "mapOffset weightsOffset weightCount mapOffsetAddr weightOffsetAddr")

PakEntry = namedtuple("PakEntry", "type offset")

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
		self.lods = args.get("lods") or []
		self.jointsInfo = None
		self.jointOffset = None
		self.basePak = None
		self.geoOffset = None
		self.boneList = None
		self.boneMap = None
		self.boneDict = None
		self.doLODs = False
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
		
	def readPointerFixup(self, bs=None):
		bs = bs or self.bs
		readAddr = bs.tell()
		offset = bs.readInt64()
		if offset > 0:
			pageId = self.getPointerFixupPage(readAddr)
			if pageId != None:
				return offset + self.pakPageEntries[pageId][0]
			print("ReadAddr not found in PointerFixups!", readAddr, pageIdm)
			print("ReadAddr not found in PointerFixups! This file may be broken", crashHere)
		return offset
	
	def loadBaseSkeleton(self, skelPath):
		if skelPath and rapi.checkFileExists(skelPath):
			self.basePak = PakFile(NoeBitStream(rapi.loadIntoByteArray(skelPath)), {'path':skelPath})
			self.basePak.readPak()
			self.boneList = self.basePak.boneList
			self.boneMap = self.basePak.boneMap
			#self.boneNames = basePak.boneNames
		else:
			print("Failed to load base skeleton")
	
	def makeVramHashJson(self, jsons):
		fileName = rapi.getLocalFileName(self.path)
		jsons[fileName] = {}
		for hash, subTuple in self.vrams.items():
			jsons[fileName][hash] = subTuple[0]
			
	def dumpGlobalVramHashes(self):
		file = open(noesis.getPluginsPath() + "python\\TLLTextureHashes.json") or {}
		jsons = json.load(file) if file else {}
		root = os.path.dirname(dialogOptions.dialog.localDir[:-1])+"\\textureDict2\\"
		
		for fileName in os.listdir(root):
			if fileName.find("global-dict")  != -1 and fileName not in jsons:
				dictPak = PakFile(NoeBitStream(rapi.loadIntoByteArray(root + fileName)), {"path": root + fileName})
				pageCt = readUIntAt(dictPak.bs, 16)
				dictPak.bs.seek(readUIntAt(dictPak.bs, 20)+12*(pageCt-1))
				rawDataAddr = dictPak.bs.readUInt() + dictPak.bs.readUInt()
				gdRawDataStarts[gameName][fileName] = rawDataAddr
				print("\"" + fileName, ": " + str(rawDataAddr) + "," )
				dictPak.readPak()
				dictPak.makeVramHashJson(jsons)
				with open(noesis.getPluginsPath() + "python\\TLLTextureHashes.json", "w") as outfile:
					json.dump(jsons, outfile)
	
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
			
			#fetch dds data
			ds = NoeBitStream(rapi.loadIntoByteArray(filepath))
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
				#compressionType = dxFormat.get(compressionType)
				ds.seek(16, 1) #skip DX10 header
				
			imgBytes = ds.readBytes(ds.getSize() - ds.tell())
			
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
		m_width = bs.readUInt()
		m_height = bs.readUInt()
		field_3C = bs.readUInt()
		m_streamFlags = bs.readUInt()
		
		texFileName = self.vrams[m_hash][1]
		texPath = readStringAt(bs, bs.tell()+12)
		bigVramOffset = None
		for fileName, subDict in self.texDict.items():
			if rapi.checkFileExists(BaseDirectories[gameName] + "texturedict2\\" + fileName):
				bigVramOffset = subDict.get(str(m_hash))
				if bigVramOffset: break
				
		if bigVramOffset: 
			vramBytes = readFileBytes(BaseDirectories[gameName] + "texturedict2\\" + fileName, bigVramOffset, 1024)
			vramStream = NoeBitStream(vramBytes)
			offset = readUIntAt(vramStream, 40)
			m_width = readUIntAt(vramStream, 84)
			m_height = readUIntAt(vramStream, 88)
			vramSize = readUIntAt(vramStream, 48)
			imgFormat = readUIntAt(vramStream, 72)
			print("VRAM texture hash found!", fileName, '{:02X}'.format(m_hash), texFileName) #offset + gdRawDataStarts[gameName][fileName], m_width, m_height, vramSize, imgFormat, "\n", texFileName)
			imageData = readFileBytes(BaseDirectories[gameName] + "texturedict2\\" + fileName, offset + gdRawDataStarts[gameName][fileName], vramSize)
		else:
			print("Texture hash not found in json:", m_hash, "\n", texFileName)
			bs.seek(pakOffset + self.pakPageEntries[len(self.pakPageEntries)-1][0] + self.pakPageEntries[len(self.pakPageEntries)-1][1])
			imageData = bs.readBytes(vramSize)
			
		fmtName = dxFormat.get(imgFormat) or ""
		
		if fmtName.find("Bc1") != -1:
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_DXT1)
		elif fmtName.find("Bc3") != -1:
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC3)
		elif fmtName.find("Bc4") != -1:
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC4)
		elif fmtName.find("Bc5") != -1:
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC5)
		elif fmtName.find("Bc6") != -1: 
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC6H)
		elif fmtName.find("Bc7") != -1: 
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC7)
			if dialogOptions.doConvertTex: 
				if exTexName.find("_NoesisAO") != -1:
					texData = rapi.imageEncodeRaw(texData, m_width, m_height, "r8r8r8")
					texData = rapi.imageDecodeRaw(texData, m_width, m_height, "r8g8b8")
					texFileName = exTexName
				elif texFileName.find("-ao") != -1 or texFileName.find("-occlusion") != -1:
					texData = rapi.imageEncodeRaw(texData, m_width, m_height, "g16b16")
					texData = rapi.imageDecodeRaw(texData, m_width, m_height, "r16g16")
		elif re.search("[RGBA]\d\d?", fmtName):
			fmtName = fmtName.split("_")[0].lower()
			print("RGBA: ", fmtName)
			try:
				texData = rapi.imageDecodeRaw(imageData, m_width, m_height, fmtName)
			except:
				print("Failed to decode raw image type", fmtName)
		else:
			print("Error: Unsupported texture type: " + str(imgFormat) + "  " + fmtName)
			return []
			
		return NoeTexture(texFileName, m_width, m_height, texData, noesis.NOESISTEX_RGBA32)
			
		print("Failed to locate texture dict", path)
		return []
	
	def readPakHeader(self):
		
		print ("Reading", self.path or rapi.getInputName())
		readPointerFixup = self.readPointerFixup
		
		bs = self.bs
		bs.seek(0)
		m_magic = bs.readUInt()						#0x0 0x00000A79
		if m_magic != 2681 and m_magic != 68217 and m_magic != 2147486329:
			print("No pak header detected!", m_magic)
			return 0

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
		
		self.vramDicts = None
		self.vrams = {}
		
		file = open(noesis.getPluginsPath() + "python\\UC4TextureHashes.json")
		#try:
		dialogOptions.texDicts = dialogOptions.texDicts or (json.load(file) if file else {})
		self.texDict = dialogOptions.texDicts[gameName]
		#except:
		#	print("Failed to load json", jsonPath)
		
		for p, pageEntry in enumerate(self.pakPageEntries):
			
			start = pageEntry[0]
			bs = self.bs
			bs.seek(start + 12)
			m_pageSize = bs.readUInt()
			bs.seek(2,1)
			m_numPageHeaderEntries = bs.readUShort()
			vramNames = {}
			
			for ph in range(m_numPageHeaderEntries):
				m_name = readStringAt(bs, bs.readUInt64()+start)
				m_resItemOffset = bs.readUInt()
				place = bs.tell() + 4
				bs.seek(m_resItemOffset + start)
				m_itemNameOffset = bs.readUInt64()
				m_itemName = readStringAt(bs, m_itemNameOffset+start)
				m_itemTypeOffset = bs.readUInt64()
				m_itemType = readStringAt(bs, m_itemTypeOffset+start)
				
				self.entriesList.append(PakEntry(type=m_itemType, offset = m_resItemOffset))
				
				if m_itemType == "VRAM_DESC":
					bs.seek(m_resItemOffset + start + 56)
					texHash = bs.readUInt64()
					texPath = readStringAt(bs, m_resItemOffset + start + 112)
					splitted = rapi.getLocalFileName(texPath.replace(".tga/", "+")).split("+", 1)
					texName = splitted[0] + texoutExt
					if len(splitted) > 1:
						if texName in vramNames:
							texName = (splitted[0] + "_" + splitted[1]).replace(".ndb", texoutExt)
						vramNames[texName] = True
						self.vrams[texHash] = [m_resItemOffset + start, texName, [], None]
					
					if getattr(self, "vramDicts") and texHash not in self.vramDicts[key]:
						self.vramDicts[key][texHash] = m_resItemOffset + start + self.startAddr
						bs.seek(m_resItemOffset + start)
				
				if m_itemType == "JOINT_HIERARCHY":
					self.jointOffset = (m_resItemOffset, start)
					
				if m_itemType == "GEOMETRY_1":
					self.geoOffset = (m_resItemOffset, start)
					
				bs.seek(place)
		self.readPakHeader = True
	
	def readPak(self):
		
		global dialogOptions
		bs = self.bs
		readPointerFixup = self.readPointerFixup
		
		if len(self.pakPageEntries) == 0:
			self.readPakHeader()
		start = self.pakPageEntries[0]
		
		if not self.jointOffset and dialogOptions.doLoadBase and dialogOptions.baseSkeleton: # and dialogOptions.baseIdx != -1:
			localRoot = findRootDir(rapi.getOutputName() or rapi.getInputName())
			baseSkelPath = BaseDirectories[gameName] + dialogOptions.baseSkeleton
			if rapi.checkFileExists(localRoot + dialogOptions.baseSkeleton):
				baseSkelPath = localRoot + dialogOptions.baseSkeleton
				if rapi.checkFileExists(baseSkelPath.replace(".pak", ".NEW.pak")): 
					baseSkelPath = baseSkelPath.replace(".pak", ".NEW.pak")
				print("\nFound local base pak: ", baseSkelPath, "\n")
			dialogOptions.baseSkeleton = ""
			self.loadBaseSkeleton(baseSkelPath)
		
		if self.jointOffset:
			start = self.jointOffset[1]
			print("Found Joint Hierarchy") # offset", self.jointOffset[0] + start, ", location:", self.jointOffset[0] + start + 20 + 32)
			bs.seek(self.jointOffset[0] + start + 20 + 32)
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
					matchedName = boneNames[b].replace("_"+splitted[len(splitted)-1], "")
					bFound = False
					mat = identity
					if parentList[b][3] != -1 and parentList[b][3] in self.boneMap: #parentList[b][3] < len(self.boneMap) and self.boneMap[parentList[b][3]] < len(mainBoneMats):
						mat = mainBoneMats[self.boneMap[parentList[b][3]]]
					
					for j, bId in enumerate(self.boneMap):
						if boneNames[bId].find(matchedName) != -1:
							bFound = True
							self.boneList.append(NoeBone(startBoneIdx + b, boneNames[b], mat, None, parentList[b][1]))
							if parentList[b][1] == -1:
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
			
			bs.seek(self.geoOffset[0] + start + 32)
			
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
			#print("self.lods", self.lods)
			
			bs.seek(SubmeshesOffs)
			
			for i in range(m_numSubMeshDesc):
			
				field_0 = bs.readUInt()
				field_4 = bs.readUInt()
				m_nameOffset = readPointerFixup()
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
				submeshName = readStringAt(bs, m_nameOffset).split("|")
				submeshName = submeshName[len(submeshName)-1]
				streamDescs = []
				
				for j in range(m_numStreamSource):
					
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
				self.submeshes[i].streamsAddr = m_compInfoOffs
				
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
					bIndicesOffs = readPointerFixup()
					weightsOffs = readPointerFixup()
					
					self.submeshes[i].skinDesc = SkinDesc(mapOffset=bIndicesOffs, weightsOffset=weightsOffs, weightCount=numWeights, mapOffsetAddr=bs.tell()-16, weightOffsetAddr=bs.tell()-8)
				
				
				bs.seek(m_material)
				shaderAssetNameOffs = readPointerFixup()
				shaderTypeOffs = readPointerFixup()
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
					loadedDiffuse = loadedNormal = loadedTrans = loadedSpec = loadedMetal = loadedRoughness = False
					
					for j in range(texCount):
						bs.seek(texDescsListOffs + 40*j)
						nameAddr = readPointerFixup()
						name = readStringAt(bs, nameAddr)
						bs.seek(8,1) #path = readStringAt(bs, readPointerFixup())
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
							
					params = {}
					setBaseColor = setSpecScale = setRoughness = setMetal = False
					outstring = "\n" + matKey + "material parameters:"
					
					for j in range(paramCount):
						bs.seek(shaderParamsOffs + 24*j)
						name = readStringAt(bs, readPointerFixup())
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
								tex.pixelData = mergeChannelsRGBA(channelTex.pixelData, texNameOrList[1], channelTex.width, channelTex.height, tex.pixelData, texNameOrList[2], tex.width, tex.height)
								
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
					
					#Positions
					if j == 0:
						rapi.rpgBindPositionBufferOfs(bs.readBytes(sd.stride * sm.numVerts), noesis.RPGEODATA_FLOAT if sd.stride==12 else noesis.RPGEODATA_HALFFLOAT, sd.stride, 0)
					
					#UVs
					elif sd.type == 34: 
						foundUVs += 1
						rapi.rpgBindUVXBuffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4, foundUVs-1, sm.numVerts)
						
					#Normals/Tangents
					elif sd.type == 31 and foundNormals != 2:
						foundNormals += 1
						if foundNormals == 1:
							rapi.rpgBindNormalBufferOfs(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_BYTE, 4, 0)
						elif foundNormals == 2:
							rapi.rpgBindTangentBufferOfs(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_BYTE, 4, 0)
							
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
						tupleList = []
						for w in range(8):
							if w >= offsetsCounts[0]:
								weightList.append(0)
								idsList.append(0)
							else:
								weightList.append(bs.readBits(22))
								idsList.append(bs.readBits(10) + startingBonesCt)
								
					rapi.rpgBindBoneIndexBufferOfs(struct.pack("<" + 'H'*len(idsList), *idsList), noesis.RPGEODATA_USHORT, 16, 0, 8)
					rapi.rpgBindBoneWeightBufferOfs(struct.pack("<" + 'I'*len(weightList), *weightList), noesis.RPGEODATA_UINT, 32, 0, 8)
				
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
					print("    " + sortTuple[0].replace(".tga", texoutExt) + "  --  " + dxFormat.get(readUIntAt(bs, sortTuple[1]+72)))
			print("")
			
		else:
			print("Geometry data not found!")
			
		return 1
		

def pakLoadRGBA(data, texList):
	
	pak = PakFile(NoeBitStream(data), {'path':rapi.getInputName(), 'texList':texList})
	pak.readPak()
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
	
	if not noDialog:
		gameName = getGameName()
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
					print("Failed to load Skeleton")
		else:
			for otherPath in dialog.loadItems:
				fullOtherPath = dialog.localDir + "\\" + otherPath
				if rapi.getLocalFileName(fullOtherPath) != dialog.name: 
					if not rapi.checkFileExists(fullOtherPath):
						fullOtherPath = dialog.baseDir + dialogOptions.currentDir + "\\" + otherPath
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
		
	return 1

def pakWriteModel(mdl, bs):
	
	global pointerPageIds, pakPageEntries, gameName
	
	noesis.logPopup()
	print("\n\n	Naughty Dog PAK model export", Version, "by alphaZomega\n")
	texOnly = noesis.optWasInvoked("-t")
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
		injectMeshName = getExportName(fileName)	
		fileName = injectMeshName
		if injectMeshName == None:
			return 0
			
	srcMesh = rapi.loadIntoByteArray(injectMeshName)
	
	if noesis.optWasInvoked("-lods"):
		dialogOptions.doLODs = True
	
	f = NoeBitStream(srcMesh)
	magic = readUIntAt(f, 0) 
	if magic != 2681 and magic != 68217 and magic != 2147486329:
		print("Not a .pak file.\nAborting...")
		return 0
	
	#copy file:
	bs.writeBytes(f.readBytes(f.getSize()))
	
	source = PakFile(f)
	for hint, fileName in baseSkeletons[gameName].items():
		if rapi.getOutputName().find(hint) != -1:
			dialogOptions.baseSkeleton = fileName
	source.readPak()
	
	boneDict = {}
	if not texOnly or (noesis.optWasInvoked("-bones") and (source.basePak or newPak).jointOffset):
		try:
			for i, bone in enumerate(source.boneList):# or mdl.bones):
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
						if len(writeMesh.positions) == 3:
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
					
					#'''
					
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
							#if appendedPositions:
							#	newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)
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
							#if appendedPositions:
							#	newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)
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
							#if appendedPositions:
							#	newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)

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
							#if appendedPositions:
							#	newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)

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
							#if appendedPositions:
							#	newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)
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
									
						appendedWeights = (fbxWeightCount > sm.skinDesc.weightCount) or appendedPositions #or appendedWeights
						if appendedWeights and wb.tell() > 0 and wb.tell() + 4*fbxWeightCount + 8*len(writeMesh.positions) > 1048032:
							newPageStreams.append(wb)
							newPage += 1
							wb = NoeBitStream()
							
						runningOffset = boneID = 0
						idxStart = wb.tell() if appendedWeights else sm.skinDesc.mapOffset
						if appendedWeights:
							newPak.changePointerFixup(sm.skinDesc.mapOffsetAddr, idxStart, newPage)
							for vertWeight in writeMesh.weights:
								wb.writeUInt64(0)
							newPak.changePointerFixup(sm.skinDesc.weightOffsetAddr, wb.tell(), newPage)
						wtStart = wb.tell() if appendedWeights else sm.skinDesc.weightsOffset
						tempbs = wb if appendedWeights else bs
						for v, vertWeight in enumerate(writeMesh.weights):
							tempbs.seek(idxStart + 8*v)
							tempbs.writeUInt(trueWeightCounts[v])
							tempbs.writeUInt(runningOffset)
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
						
						for n in range(4):
							bs.seek(sm.nrmRecalcDesc[n])
							appendedPositions = appendedPositions or (len(writeMesh.positions) > readUIntAt(bs, sm.nrmRecalcDesc[6]-8))
							tempbs = wb if appendedPositions else bs
							if appendedPositions: 
								if wb.tell() + 2 * len(writeMesh.positions) > 1048032:
									newPageStreams.append(wb)
									newPage += 1
									wb = NoeBitStream()
									tempbs = wb
								newPak.changePointerFixup(sm.nrmRecalcDesc[6] + 8*n, wb.tell(), newPage)
							for k in range(len(writeMesh.positions)+1):
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
		if doWrite and not dialogOptions.doLODs:
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
		if os.path.isdir(path):
			source.bs = bs
			vramPathDict = {}
			for hash, vramTuple in source.vrams.items():
				vramPathDict[vramTuple[1]] = (vramTuple[0], hash)
				
			for fileName in os.listdir(path):
				if os.path.isfile(os.path.join(path, fileName)) and fileName.find(texoutExt) != -1:
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
	
