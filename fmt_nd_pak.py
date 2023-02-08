#fmt_nd_pak.py - Uncharted 4 ".pak" plugin for Rich Whitehouse's Noesis
#Authors: alphaZomega 
#Special Thanks: icemesh 
Version = 'v0.23 (February 8, 2023)'


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
ExportCopyUV3 = False											# Copy UV1 with '1' or UV2 with '2' to UV3+ when exporting, if 'NullUV3' is disabled
NullUV3 = True													# Make all UVs in UV channels 3+ be at tex coordinates [0,0]

# Set the base path from which the plugin will search for pak files and textures:
BaseDirectories = {
	"TLL": "C:\Program Files (x86)\\Steam\steamapps\\common\\Uncharted Legacy of Thieves Collection\\Uncharted4_data\\build\\pc\\thelostlegacy\\",
	"U4": "F:\\ExtractedGameFiles\\Uncharted4\\",
}

from inc_noesis import *
from collections import namedtuple
import noewin
import json
import os
import re
import random

gameName = "U4"

class DialogOptions:
	def __init__(self):
		self.doLoadTex = LoadTextures
		self.doLoadBase = LoadBaseSkeleton
		self.doConvertTex = ConvertTextures
		self.doFlipUVs = FlipUVs
		self.doLODs = LoadAllLODs
		self.loadAllTextures = LoadAllTextures
		self.nullUV3 = NullUV3
		self.exportCopyUV3 = ExportCopyUV3
		self.baseSkeleton = None
		self.width = 600
		self.height = 800
		self.texDicts = None
		self.gameName = gameName

		dialog = None

dialogOptions = DialogOptions()

def registerNoesisTypes():
	handle = noesis.register("Naughty Dog PAK", ".pak")
	noesis.setTypeExportOptions(handle, "-noanims -notex")
	noesis.addOption(handle, "-nodialog", "Do not display dialog window", 0)
	noesis.addOption(handle, "-t", "Textures only; do not inject geometry data", 0)
	noesis.addOption(handle, "-meshfile", "Export using a given source mesh filename", noesis.OPTFLAG_WANTARG)
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

def readFileBytes(filepath, address, size):
	with open(filepath, 'rb') as f:
		f.seek(address)
		return f.read(size)
		

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
	for name, meshList in meshesBySourceName.items():
		newPositions = []
		newUV1 = []
		newUV2 = []
		newTangents = []
		newWeights = []
		newIndices = []
		for mesh in meshList:
			if len(newPositions):
				for i in range(len(mesh.indices)):
					mesh.indices[i] += len(newPositions)
			newPositions.extend(mesh.positions)
			newUV1.extend(mesh.uvs)
			newUV2.extend(mesh.lmUVs)
			newTangents.extend(mesh.tangents)
			newWeights.extend(mesh.weights)
			newIndices.extend(mesh.indices)
			
		combinedMesh = NoeMesh(newIndices, newPositions, meshList[0].sourceName, meshList[0].sourceName, mdl.globalVtx, mdl.globalIdx)
		combinedMesh.setTangents(newTangents)
		combinedMesh.setWeights(newWeights)
		combinedMesh.setUVs(newUV1)
		combinedMesh.setUVs(newUV2, 1)
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
		"asav": "actor77\asav-base.pak",
		"chloe": "actor77\chloe-base.pak",
		"elena": "actor77\elena-base.pak",
		"horse": "actor77\horse-base.pak",
		"light": "actor77\light-base.pak",
		"meenu": "actor77\meenu-base.pak",
		"monkey": "actor77\monkey-base.pak",
		"nadine": "actor77\nadine-base.pak",
		"nadine-dlc": "actor77\nadine-dlc-base.pak",
		"nilay": "actor77\nilay-base.pak",
		"kid": "actor77\npc-kid-base.pak",
		"kid-fem": "actor77\npc-kid-fem-base.pak",
		"medium": "actor77\npc-medium-base.pak",
		"normal": "actor77\npc-normal-base.pak",
		"crowd": "actor77\npc-normal-crowd-base.pak",
		"crowd-fem": "actor77\npc-normal-crowd-fem-base.pak",
		"fem": "actor77\npc-normal-fem-base.pak",
		"orca": "actor77\orca-base.pak",
		"pistol": "actor77\pistol-base.pak",
		"prison": "actor77\prison-drake-base.pak",
		"rifle": "actor77\rifle-base.pak",
		"samuel": "actor77\samuel-base.pak",
		"samuel-dlc": "actor77\samuel-dlc-base.pak",
		"sandy": "actor77\sandy-base.pak",
		"smokey": "actor77\smokey-base.pak",
		"sull": "actor77\sullivan-base.pak",
		"throw": "actor77\throwable-base.pak",
		"vin": "actor77\vin-base.pak",
		"waz": "actor77\waz-base.pak",
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


def findRootDir(path):
	uncharted4Idx = path.find("\\uncharted4\\")
	if uncharted4Idx != -1:
		return path[:(uncharted4Idx + 12)]
	lostLegacyIdx = path.find("\\thelostlegacy\\")
	if lostLegacyIdx != -1:
		return path[:(lostLegacyIdx + 15)]
	return path

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
		self.noeWnd.closeWindow()
			
	def openOptionsButtonCancel(self, noeWnd, controlId, wParam, lParam):
		self.isCancelled = True
		#self.pak.dumpGlobalVramHashes()
		self.noeWnd.closeWindow()
		
	def selectDirListItem(self, noeWnd, controlId, wParam, lParam):
		if self.dirList.getSelectionIndex() == -1:
			self.dirList.selectString(self.subDirs[0])
		if self.dirIdx != self.dirList.getSelectionIndex() and dialogOptions.currentDir != self.dirList.getStringForIndex(self.dirList.getSelectionIndex()):
			print("changed selection", self.dirList.getSelectionIndex(), self.dirIdx, self.dirList.getStringForIndex(self.dirList.getSelectionIndex()), self.dirList.getStringForIndex(self.dirIdx),	dialogOptions.currentDir)
			self.dirIdx = self.dirList.getSelectionIndex()
			dialogOptions.currentDir = self.dirList.getStringForIndex(self.dirIdx)
			self.setDirList()
			self.setPakList()
	
	def selectBaseListItem(self, noeWnd, controlId, wParam, lParam):
		self.baseIdx = self.baseList.getSelectionIndex()
		dialogOptions.baseSkeleton = self.baseList.getStringForIndex(self.baseIdx)
		
	def selectPakListItem(self, noeWnd, controlId, wParam, lParam):
		print(self.pakIdx, self.pakList.getSelectionIndex(), self.pakList.getStringForIndex(self.pakList.getSelectionIndex()))
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
		for hint, fileName in baseSkeletons[gameName].items():
			if self.name.find(hint) != -1:
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
			self.setLoadList()
			
			if True:
				index = self.noeWnd.createCheckBox("Load Textures", 10, 665, 130, 30, self.checkLoadTexCheckbox)
				self.loadTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.loadTexCheckbox.setChecked(dialogOptions.doLoadTex)
				
				
				index = self.noeWnd.createCheckBox("Load All Textures", 140, 665, 160, 30, self.checkLoadAllTexCheckbox)
				self.loadAllTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.loadAllTexCheckbox.setChecked(dialogOptions.loadAllTextures)
				
				
				index = self.noeWnd.createCheckBox("Convert Normal Maps", 10, 695, 160, 30, self.checkConvTexCheckbox)
				self.convTexCheckbox = self.noeWnd.getControlByIndex(index)
				self.convTexCheckbox.setChecked(dialogOptions.doConvertTex)
				
				
				#index = self.noeWnd.createCheckBox("Flip UVs", 140, 680, 130, 30, self.checkFlipUVsCheckbox)
				#self.flipUVsCheckbox = self.noeWnd.getControlByIndex(index)
				#self.flipUVsCheckbox.setChecked(dialogOptions.doFlipUVs)
				
				
				index = self.noeWnd.createCheckBox("Load Base", 170, 695, 90, 30, self.checkBaseCheckbox)
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
			
			
			self.setBaseList(self.baseList, baseSkeletons[gameName]["chloe" if gameName == "TLL" else "hero"])
			self.setDirList()
			self.setPakList()
			self.setGameBox(self.gameBox)
			self.setLocalBox(self.localBox)
			self.isStarted = True
			
			self.noeWnd.doModal()
			
			
StreamDesc = namedtuple("StreamDesc", "type offset stride bufferOffsetAddr")

SkinDesc = namedtuple("SkinDesc", "mapOffset weightsOffset mapOffsetAddr weightOffsetAddr")

PakEntry = namedtuple("PakEntry", "type offset")

class PakSubmesh:
	def __init__(self, name=None, numVerts=None, numIndices=None, facesOffset=None, streamDescs=None, skinDesc=None, nrmRecalcDesc=None, facesOffsetAddr=None):
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
		self.jointOffset = None
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
			print("ReadAddr not" + asdf + " found in PointerFixups!", readAddr, pageId)
		return offset
	
	def loadBaseSkeleton(self, skelPath):
		if skelPath and rapi.checkFileExists(skelPath):
			skelPak = PakFile(NoeBitStream(rapi.loadIntoByteArray(skelPath)), {'path':skelPath})
			skelPak.readPak()
			self.boneList = skelPak.boneList
			self.boneMap = skelPak.boneMap
			#self.boneNames = skelPak.boneNames
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
	
	def loadVRAM(self, vramOffset=0):
		
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
			#print("BC1")
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_DXT1)
		elif fmtName.find("Bc3") != -1:
			#print("BC3")
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC3)
		elif fmtName.find("Bc4") != -1:
			#print("BC4")
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC4)
		elif fmtName.find("Bc5") != -1:
			#print("BC5")
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC5)
		elif fmtName.find("Bc6") != -1: 
			#print("BC6")
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC6H)
		elif fmtName.find("Bc7") != -1: 
			#print("BC7")
			texData = rapi.imageDecodeDXT(imageData, m_width, m_height, noesis.FOURCC_BC7)
			if dialogOptions.doConvertTex and (texFileName.find("-ao") != -1 or texFileName.find("-occlusion") != -1):
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
					texName = rapi.getLocalFileName(texPath[:texPath.find(".tga")+4]).replace(".ndb", "").replace(".tga", ".dds")
					self.vrams[texHash] = (m_resItemOffset + start, texName)
					
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
			baseSkelPath = dialogOptions.baseSkeleton = BaseDirectories[gameName] + dialogOptions.baseSkeleton
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
			
			bs.seek(xformsOffset + headerSize)
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
			for b in range(boneCount):
				parentList.append((bs.readInt(), bs.readInt(), bs.readInt(), bs.readInt()))
			
			mainBones = []
			mainBoneMats = []
			boneNames = []
			self.boneDict = []
			self.boneMap = []
			
			bs.seek(namesOffset)
			for b in range(boneCount):
				bs.seek(8,1)
				boneNames.append(readStringAt(bs, bs.readUInt64()+start))
				
			def getRootParent(parentTbl):
				while parentTbl[1] != -1:
					parentTbl = parentList[parentTbl[1]]
				return parentList.index(parentTbl)
			
			for b in range(boneCount):	
				self.boneMap.append(b)
				if getRootParent(parentList[b]) == 0:
					mainBones.append(b)
				
			identity = NoeMat43((NoeVec3((1.0, 0.0, 0.0)), NoeVec3((0.0, 1.0, 0.0)), NoeVec3((0.0, 0.0, 1.0)), NoeVec3((0.0, 0.0, 0.0))))
			startBoneIdx = len(self.boneList)
			for b, bID in enumerate(mainBones):
				mat = matrixList[b] if b < len(matrixList) else identity
				mainBoneMats.append(mat)
			
			for b in range(boneCount):
				if b in mainBones:
					self.boneList.append(NoeBone(startBoneIdx + b, boneNames[b], mainBoneMats[mainBones.index(b)], None, parentList[b][1]))
				else:
					splitted = boneNames[b].split("_")
					matchedName = boneNames[b].replace("_"+splitted[len(splitted)-1], "")
					bFound = False
					for j, bId in enumerate(mainBones):
						if boneNames[bId].find(matchedName) != -1:
							bFound = True
							self.boneList.append(NoeBone(startBoneIdx + b, boneNames[b], identity, None, parentList[b][1]))
							if parentList[b][1] == -1:
								self.boneList[len(self.boneList)-1].parentIndex = bId
							break
					if not bFound:
						self.boneList.append(NoeBone(startBoneIdx + b, boneNames[b], identity, None, parentList[b][1]))
				lastBone = self.boneList[len(self.boneList)-1]
				if lastBone.parentIndex != -1:
					lastBone.parentIndex += startBoneIdx
				elif b not in mainBones:
					lastBone.parentIndex = 0 #parent stragglers to root
				#print(lastBone.index, lastBone.name, lastBone.parentIndex, lastBone.parentName)
				
				
			#rapi.rpgSetBoneMap(self.boneMap)
			
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
			MatHdrsOffs = bs.readUInt64()
			ukn0 = bs.readUInt64()
			ukn1 = bs.readUInt64()
			ukn2 = bs.readUInt64()
			ukn3 = bs.readUInt64()
			uknFloatsOffs = bs.readUInt64()
			ukn4 = bs.readUInt64()
			
			bs.seek(SubmeshesOffs)
			
			usedMaterials = {}
			usedTextures = []
			
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
				
				if nrmRecalcDescOffs:
					bs.seek(nrmRecalcDescOffs)
					indexCount = bs.readInt()
					uknInt2 = bs.readInt()
					ptr1 = readPointerFixup()
					ptr2 = readPointerFixup()
					ptr3 = readPointerFixup()
					ptr4 = readPointerFixup()
					
					self.submeshes[i].nrmRecalcDesc = [ptr1, ptr2, ptr3, ptr4, indexCount, nrmRecalcDescOffsOffset]
				
				if skindataOffset:
					bs.seek(skindataOffset)
					uknSD0 = bs.readUInt()
					uknSD1 = bs.readUInt()
					uknSD2 = bs.readUInt()
					uknSD3 = bs.readUInt()
					bIndicesOffs = readPointerFixup()
					weightsOffs = readPointerFixup()
					
					self.submeshes[i].skinDesc = SkinDesc(mapOffset=bIndicesOffs, weightsOffset=weightsOffs, mapOffsetAddr=bs.tell()-16, weightOffsetAddr=bs.tell()-8)
				
				
				bs.seek(m_material)
				shaderAssetNameOffs = readPointerFixup()
				shaderTypeOffs = readPointerFixup()
				shaderOptions0Offs = readPointerFixup()
				hashCodeOffs = readPointerFixup()
				shaderOptions1Offs = readPointerFixup()
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
					material = NoeMaterial(matKey, "")
					materialFlags = 0
					loadedDiffuse = loadedNormal = loadedTrans = False
					
					for j in range(texCount):
						bs.seek(texDescsListOffs + 40*j)
						nameAddr = readPointerFixup()
						name = readStringAt(bs, nameAddr)
						bs.seek(8,1) #path = readStringAt(bs, readPointerFixup())
						bs.seek(readPointerFixup())
						path = readStringAt(bs, readPointerFixup())
						vramHash = bs.readUInt64()
						
						texFileName = rapi.getLocalFileName(path[:path.find(".tga")+4]).replace(".tga", ".dds")
						tex = doSet = None
						
						if not loadedDiffuse and name.find("BaseColor") != -1:
							doSet = loadedDiffuse =  True 
							material.setTexture(texFileName)
							#material.setSpecularTexture(texFileName)
							#materialFlags |=   noesis.NMATFLAG_PBR_SPEC
							
						elif not loadedNormal and name.find("NR") != -1:
							doSet = loadedNormal = True
							material.setNormalTexture(texFileName)
							if dialogOptions.doConvertTex:
								materialFlags |= noesis.NMATFLAG_NORMALMAP_FLIPY #| noesis.NMATFLAG_NORMALMAP_NODERZ
							
						elif not loadedTrans and name.find("Transp") != -1:
							doSet = loadedTrans = True
							material.setOpacityTexture(texFileName)
							material.setAlphaTest(0.05)
							
							if not loadedDiffuse:
								material.setTexture(texFileName)
							if not loadedNormal:
								material.setNormalTexture(material.texName) #alpha wont work without a diffuse and normal map
								
						doSet = doSet or dialogOptions.loadAllTextures
						
						if doSet and texFileName and texFileName not in usedTextures:
							self.vramHashes.append(vramHash)
							usedTextures.append(texFileName)
								
					#material.setMetal(1.0, 1.0)
					#material.setRoughness(1.0, 1.0)
					material.setFlags(materialFlags)
					usedMaterials[m_material] = material
					self.matList.append(material)
					
				self.matNames.append(material.name)
				
				bs.seek(place)

			
	def loadGeometry(self):
		
		bs = self.bs
		rapi.rpgSetTransform((NoeVec3((GlobalScale,0,0)), NoeVec3((0,GlobalScale,0)), NoeVec3((0,0,GlobalScale)), NoeVec3((0,0,0)))) 
		
		if self.submeshes:
			
			lastLOD = 0
			
			if dialogOptions.doLoadTex:
				for vramHash in self.vramHashes:
					tex = self.loadVRAM(self.vrams[vramHash][0])
					if tex:  
						self.texList.append(tex)
				alreadyLoadedList = [tex.name for tex in self.texList]
				if dialogOptions.loadAllTextures:
					for hash, subTuple in self.vrams.items():
						if subTuple[1] and subTuple[1] not in alreadyLoadedList:
							tex = self.loadVRAM(subTuple[0])
							if tex:  
								self.texList.append(tex)
								
			for i, sm in enumerate(self.submeshes):
				lodFind = sm.name.find("Shape")
				LODidx = int(sm.name[lodFind+5]) if lodFind != -1 and sm.name[lodFind+5].isnumeric() else 0
				if LODidx > lastLOD:
					lastLOD = LODidx
				if not dialogOptions.doLODs and LODidx > 0:
					continue
				
				rapi.rpgSetName(sm.name)
				rapi.rpgSetMaterial(self.matNames[i])
				foundPositions = foundUVs = foundNormals = 0
				
				for j, sd in enumerate(sm.streamDescs):
				
					bs.seek(sd.offset)
					
					#Positions
					if j == 0:
						foundPositions = True
						rapi.rpgBindPositionBufferOfs(bs.readBytes(sd.stride * sm.numVerts), noesis.RPGEODATA_FLOAT if sd.stride==12 else noesis.RPGEODATA_HALFFLOAT, sd.stride, 0)
					
					#UVs
					elif sd.type == 34: 
						
						if not foundUVs:
							foundUVs = 1
							rapi.rpgBindUV1Buffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4)
						elif foundUVs == 1:
							foundUVs = 2
							rapi.rpgBindUV2Buffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4)
						else:
							foundUVs += 1
							print("Would read UV", foundUVs, "from", bs.tell(), "to", bs.tell()+4 * sm.numVerts)
							#rapi.rpgBindUVXBuffer(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4, 0, foundUVs, sm.numVerts)
							

					#Normals/Tangents
					elif sd.type == 31 and foundNormals != 2:
						if not foundNormals:
							foundNormals = 1
							rapi.rpgBindNormalBufferOfs(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_BYTE, 4, 0)
						else:
							foundNormals = 2
							rapi.rpgBindTangentBufferOfs(bs.readBytes(4 * sm.numVerts), noesis.RPGEODATA_BYTE, 4, 0)
							
					#elif sd.type == 10:
					#	rapi.rpgBindColorBufferOfs(bs.readBytes(8 * sm.numVerts), noesis.RPGEODATA_HALFFLOAT, 4, 0, 4)
					
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
								idsList.append(bs.readBits(10))
					rapi.rpgBindBoneIndexBufferOfs(struct.pack("<" + 'H'*len(idsList), *idsList), noesis.RPGEODATA_USHORT, 16, 0, 8)
					rapi.rpgBindBoneWeightBufferOfs(struct.pack("<" + 'I'*len(weightList), *weightList), noesis.RPGEODATA_UINT, 32, 0, 8)
				
				try:
					if foundPositions:
						bs.seek(sm.facesOffset)
						rapi.rpgCommitTriangles(bs.readBytes(2 * sm.numIndices), noesis.RPGEODATA_USHORT, sm.numIndices, noesis.RPGEO_TRIANGLE, 0x1)
					else:
						print("No positions found for submesh", i)
				except:
					print("Failed to bind submesh", i)
				
				rapi.rpgClearBufferBinds()
				
			print("\n====================================\n\"" + rapi.getLocalFileName(self.path or rapi.getInputName()) + "\" Textures list:")
			sortedTupleList = sorted([ (subTuple[1], subTuple[0]) for hash, subTuple in self.vrams.items() ])
			for sortTuple in sortedTupleList:
				if sortTuple[0]:
					print("    " + sortTuple[0].replace(".tga", ".dds") + "  --  " + dxFormat.get(readUIntAt(bs, sortTuple[1]+72)))
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
					skelPak = PakFile(NoeBitStream(rapi.loadIntoByteArray(skelPath)), {'path':skelPath})
					skelself.readPak()
					pak.boneList = skelself.boneList
					pak.boneMap = skelself.boneMap
					pak.boneDict = skelself.boneDict
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
						otherPak.readPak()
						otherPak.loadGeometry()
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
			for mdl in mdlList:
				mdl.setBones(pak.boneList)
		
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
	for i, bone in enumerate(source.boneList):# or mdl.bones):
		boneDict[bone.name] = i
	
	if source.submeshes:
		
		doWrite = didAppend = False
		lastLOD = 0
		isNoesisSplit = (mdl.meshes[0].name[:5] == "0000_")
		fbxMeshList = mdl.meshes if not isNoesisSplit else recombineNoesisMeshes(mdl)
		
		f.seek(source.geoOffset[0] + source.geoOffset[1] + 72)
		submeshesAddr = source.readPointerFixup()
		
		newPak = PakFile(bs)
		newPak.readPak()
		wb = NoeBitStream()
		
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
				
				for i, meshTuple in enumerate(meshesToInject):
					
					writeMesh = meshTuple[0]
					sm = meshTuple[1]
					lodFind = sm.name.find("Shape")
					LODidx = int(sm.name[lodFind+5]) if lodFind != -1 and sm.name[lodFind+5].isnumeric() else 0
					if LODidx > lastLOD:
						lastLOD = LODidx
					if not dialogOptions.doLODs and LODidx > 0:
						continue
					
					appendedPositions = appendedWeights = appendedIndices = False
					print("Injecting ", writeMesh.name)
					
					pageCt = readUIntAt(f, 16)
					pointerFixupPageCt = readUIntAt(bs, 24)
					pointerFixupTblOffs = readUIntAt(bs, 28)
					isModded = (readUIntAt(f, pointerFixupTblOffs + 12*8) == 4294967295)
					newPageDataAddr = source.pakPageEntries[len(source.pakPageEntries)-1][0] + source.pakPageEntries[len(source.pakPageEntries)-1][1]
					newPage = pageCt if not isModded else pageCt-1
					owningIndex = source.pakPageEntries[len(source.pakPageEntries)-1][2]
					
					vertOffs = submeshesAddr + 176*i + 36
					foundPositions = foundUVs = foundNormals = 0
					appendedPositions = (len(writeMesh.positions) > sm.numVerts)
					tempbs = wb if appendedPositions else bs
					
					for j, sd in enumerate(sm.streamDescs):
						bs.seek(sd.offset)
						
						if ((j == 0 and sd.stride == 12 or sd.stride == 8)) and not foundPositions:
							bFoundPositions = True
							if appendedPositions:
								newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)
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
						elif sd.type == 34 and (foundUVs < 2 or (dialogOptions.exportCopyUV3 or dialogOptions.nullUV3)):
							foundUVs += 1
							UVs = writeMesh.lmUVs if dialogOptions.exportCopyUV3 == 2 or foundUVs == 2 else writeMesh.uvs
							if appendedPositions:
								newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)
							if foundUVs > 2 and dialogOptions.nullUV3:
								print(i, "Nulling UV" + str(foundUVs) + " for", sm.name)
								for v, vert in enumerate(UVs):
									tempbs.writeHalfFloat(0)
									tempbs.writeHalfFloat(0)
							else:
								for v, vert in enumerate(UVs):
									tempbs.writeHalfFloat(vert[0])
									tempbs.writeHalfFloat(vert[1])
									
						elif sd.type == 31:
							foundNormals += 1
							if appendedPositions:
								newPak.changePointerFixup(sd.bufferOffsetAddr, wb.tell(), newPage)
							if foundNormals == 1:
								for v, vert in enumerate(writeMesh.tangents): 
									tempbs.writeByte(int(vert[0][0] * 127 + 0.5000000001)) #normal
									tempbs.writeByte(int(vert[0][1] * 127 + 0.5000000001))
									tempbs.writeByte(int(vert[0][2] * 127 + 0.5000000001))
									tempbs.writeByte(0)
							elif foundNormals == 2: 
								foundNormals = 2
								for v, vert in enumerate(writeMesh.tangents):
									tempbs.writeByte(int(vert[2][0] * 127 + 0.5000000001)) #bitangent
									tempbs.writeByte(int(vert[2][1] * 127 + 0.5000000001))
									tempbs.writeByte(int(vert[2][2] * 127 + 0.5000000001))
									TNW = vert[0].cross(vert[1]).dot(vert[2])
									if (TNW < 0.0):
										tempbs.writeByte(129)
									else:
										tempbs.writeByte(127)
						else:
							print("Unknown component", sd.type, "!!")
						'''elif sd.type == 10:
							print("Writing unknown vector3 component")
							for v, vert in enumerate(writeMesh.positions):
								wb.writeHalfFloat(1)
								wb.writeHalfFloat(1)
								wb.writeHalfFloat(1)
								wb.writeHalfFloat(0)'''

						'''else:
							if sd.type==10:
								print(i, "Skipped extra positions buffer", sd.type, "found at", bs.tell())
							elif sd.type==31:
								print(i, "Skipped extra normals/tangents buffer", sd.type, "found at", bs.tell())
							else:
								print(i, "Skipped extra component type", sd.type, "found at", bs.tell())'''
					
					if sm.skinDesc:
					
						srcWeightCount = fbxWeightCount = 0
						f.seek(sm.skinDesc.mapOffset)
						for v in range(sm.numVerts):
							srcWeightCount += f.readUInt()
							f.seek(4,1)
						for vertWeight in writeMesh.weights:
							for w, weight in enumerate(vertWeight.weights):
								if weight > 0: 
									fbxWeightCount += 1
						appendedWeights = (fbxWeightCount > srcWeightCount)
						
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
							tempbs.writeUInt(len(vertWeight.weights))
							tempbs.writeUInt(runningOffset)
							tempbs.seek(wtStart + runningOffset)
							for w, weight in enumerate(vertWeight.weights):
								try:
									boneID = boneDict[mdl.bones[vertWeight.indices[w]].name]
								except:
									print(mdl.bones[vertWeight.indices[w]].name, "not found")
									pass
								tempbs.writeUInt((boneID << 22) | int(weight * 4194303))
								runningOffset += 4
								
					
					if len(writeMesh.indices) > sm.numIndices:
						print(len(writeMesh.indices), "vs", sm.numIndices)
						appendedIndices = True
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
						'''bs.seek(sm.nrmRecalcDesc[0])
						for k in range(sm.nrmRecalcDesc[4]):
							bs.writeShort(0)
						bs.seek(sm.nrmRecalcDesc[2])
						for k in range(sm.nrmRecalcDesc[4]):
							bs.writeShort(0)'''
						bs.seek(sm.nrmRecalcDesc[1])
						for k in range(sm.nrmRecalcDesc[4]):
							bs.writeShort(0)
						bs.seek(sm.nrmRecalcDesc[3])
						for k in range(sm.nrmRecalcDesc[4]):
							bs.writeShort(0)
					
					#set vertex/index counts:
					bs.seek(vertOffs)
					bs.writeUInt(len(writeMesh.positions))
					bs.writeUInt(len(writeMesh.indices))
					
					didAppend = (didAppend or appendedPositions or appendedWeights or appendedIndices)
					if appendedPositions or appendedWeights or appendedIndices:
						print("Mesh must be appended to a new page: ", sm.name)
						if appendedPositions:
							print("	-exceeds the maximum vertex count of", sm.numVerts, "(has", str(len(writeMesh.positions)) + ")!")
						if appendedWeights:
							print("	-exceeds the maximum weight count of", srcWeightCount, "(has", str(fbxWeightCount) + ")!")
						if appendedIndices:
							print("	-exceeds the maximum poly count of", int(sm.numIndices/3), "(has", str(int(len(writeMesh.indices)/3)) + ")!")
			if isNoesisSplit:
				print("\nWARNING:	Duplicate mesh names detected! Check your FBX for naming or geometry issues. This pak may crash the game!\n")

		#Set all LODs to read as LOD0:
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
			for a in range(1, LODCount):
				bs.seek(lodDescs[a] + 24)
				bs.writeUInt64(firstLODSubmeshOffs)
				writeUIntAt(bs, lodDescs[a] + 4, firstLODSubmeshCount)
				
		#Embed image data
		path = rapi.getDirForFilePath(injectMeshName)+rapi.getLocalFileName(injectMeshName).split(".", 1)[0]
		print("\nChecking for textures to embed in", path)
		if os.path.isdir(path):
			source.bs = bs
			vramPathDict = {}
			for hash, vramTuple in source.vrams.items():
				vramPathDict[vramTuple[1]] = (vramTuple[0], hash)
				
			for fileName in os.listdir(path):
				if os.path.isfile(os.path.join(path, fileName)):
					if fileName.find(".dds") != -1:
						vramTuple = vramPathDict.get(fileName)
						if vramTuple:
							print("\nEmbedding texture", fileName, "at", vramTuple[0])
							source.writeVRAMImage(vramTuple[0], os.path.join(path, fileName))
							vramPathDict[fileName] = 0
						elif vramTuple != 0:
							print("Texture was found, but is not in the pak file!\n	", fileName)
							
							
		if doWrite:# and didAppend:
			if not isModded:
				print("\nFile was not previously injected")
				writeUIntAt(bs, 28, pointerFixupTblOffs+12)
				writeUIntAt(bs, 16, pageCt+1) # add new page
				bs.seek(pointerFixupTblOffs)
				oldBytes = bs.readBytes(12) #copy old pointerFixup
				bs.seek(-12, 1)
				bs.writeUInt(newPageDataAddr + 16) # new page offset
				bs.writeUInt(wb.getSize()+20) # new page size
				bs.writeUInt(owningIndex) # new package owning index
				bs.writeBytes(oldBytes)
				padBytes = bs.readBytes(16) #blank padding bytes
				writeUIntAt(bs, 4, readUIntAt(bs, 4)+16) #add to headerSz
				writeUIntAt(bs, pointerFixupTblOffs+12+4, readUIntAt(bs, pointerFixupTblOffs+12+4)+16) #add to PointerFixupEntries dataOffset
				bs.seek(readUIntAt(bs, 20))
				for i in range(pageCt):
					bs.writeUInt(readUIntAt(bs, bs.tell())+16) #add to each pageEntryOffset
					bs.seek(8, 1)
					
			else:
				print("\nFile was previously injected")
			
			#pointerFixupPageCt = readUIntAt(bs, 24)
			ns = NoeBitStream()
			bs.seek(0)
			if not isModded:
				ns.writeBytes(bs.readBytes(pointerFixupTblOffs+12*8))
				ns.writeBytes(padBytes) #move old PointerFixupTables here
				writeUIntAt(ns, ns.tell()-4, 4294967295) #unique ID for modding identification
			ns.writeBytes(bs.readBytes(newPageDataAddr - bs.tell()))
				
			ns.writeUInt64(16045690984833335023) #DEADBEEF
			ns.writeUInt(0) #74565) #unknown
			ns.writeUInt(wb.getSize()+20) #new size
			ns.writeUShort(owningIndex)
			ns.writeUShort(0)
			ns.writeBytes(wb.getBuffer())
			if isModded:
				bs.seek(newPageDataAddr) #skip (delete) contents of page from previous injection
			ns.writeBytes(bs.readBytes(bs.getSize()-bs.tell()))
			
			bs.seek(0)
			bs.writeBytes(ns.getBuffer())
			
	return 1
	
