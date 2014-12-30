from logging import getLogger
from numpy import zeros, rollaxis, indices
import traceback
from os.path import join
from collections import defaultdict
from pprint import pformat

import os

NOTEX = (0x1F0, 0x1F0)

import yaml

log = getLogger(__name__)


class Block(object):
    """
    Value object representing an (id, data) pair.
    Provides elements of its parent material's block arrays.
    Blocks will have (name, ID, blockData, aka, color, brightness, opacity, blockTextures)
    """

    def __str__(self):
        return "<Block {name} ({id}:{data})>".format(
            name=self.name, id=self.ID, data=self.blockData)

    def __repr__(self):
        return str(self)

    def __cmp__(self, other):
        if not isinstance(other, Block):
            return -1
        key = lambda a: a and (a.ID, a.blockData)
        return cmp(key(self), key(other))

    def __init__(self, materials, blockID, blockData=0, blockString=""):
        self.materials = materials
        self.ID = blockID
        self.blockData = blockData
        self.stringID = blockString

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return self.__dict__[attr]
        if attr == "name":
            r = self.materials.names[self.ID]
        else:
            r = getattr(self.materials, attr)[self.ID]
        if attr in ("name", "aka", "color", "type"):
            r = r[self.blockData]
        return r


id_limit = 4096


class MCMaterials(object):
    defaultColor = (0xc9, 0x77, 0xf0, 0xff)
    defaultBrightness = 0
    defaultOpacity = 15
    defaultTexture = NOTEX
    defaultTex = [t // 16 for t in defaultTexture]

    def __init__(self, defaultName="Unused Block"):
        object.__init__(self)
        self.yamlDatas = []

        self.defaultName = defaultName

        self.blockTextures = zeros((id_limit, 16, 6, 2), dtype='uint16')
        # Sets the array size for terrain.png
        self.blockTextures[:] = self.defaultTexture
        self.names = [[defaultName] * 16 for i in range(id_limit)]
        self.aka = [[""] * 16 for i in range(id_limit)]

        self.type = [["NORMAL"] * 16] * id_limit
        self.blocksByType = defaultdict(list)
        self.allBlocks = []
        self.blocksByID = {}

        self.lightEmission = zeros(id_limit, dtype='uint8')
        self.lightEmission[:] = self.defaultBrightness
        self.lightAbsorption = zeros(id_limit, dtype='uint8')
        self.lightAbsorption[:] = self.defaultOpacity
        self.flatColors = zeros((id_limit, 16, 4), dtype='uint8')
        self.flatColors[:] = self.defaultColor

        self.idStr = [""] * id_limit

        self.color = self.flatColors
        self.brightness = self.lightEmission
        self.opacity = self.lightAbsorption

        self.Air = self.addBlock(0,
                                 name="Air",
                                 texture=(0x0, 0x150),
                                 opacity=0,
        )

    def __repr__(self):
        return "<MCMaterials ({0})>".format(self.name)

    @property
    def AllStairs(self):
        return [b for b in self.allBlocks if "Stairs" in b.name]

    @property
    def AllSlabs(self):
        return [b for b in self.allBlocks if "Slab" in b.name]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __len__(self):
        return len(self.allBlocks)

    def __iter__(self):
        return iter(self.allBlocks)

    def __getitem__(self, key):
        """ Let's be magic. If we get a string, return the first block whose
            name matches exactly. If we get a (id, data) pair or an id, return
            that block. for example:

                level.materials[0]  # returns Air
                level.materials["Air"]  # also returns Air
                level.materials["Powered Rail"]  # returns Powered Rail
                level.materials["Lapis Lazuli Block"]  # in Classic

           """
        if isinstance(key, basestring):
            for b in self.allBlocks:
                if b.name == key:
                    return b
            raise KeyError("No blocks named: " + key)
        if isinstance(key, (tuple, list)):
            id, blockData = key
            return self.blockWithID(id, blockData)
        return self.blockWithID(key)

    def blocksMatching(self, name):
        toReturn = []
        name = name.lower()
        spiltNames = name.split(" ")
        amount = len(spiltNames)
        for v in self.allBlocks:
            nameParts = v.name.lower().split(" ")
            for anotherName in v.aka.lower().split(" "):
                nameParts.append(anotherName)
            i = 0
            spiltNamesUsed = []
            for v2 in nameParts:
                Start = True
                j = 0
                while j < len(spiltNames) and Start == True:
                    if spiltNames[j] in v2 and not j in spiltNamesUsed:
                        i += 1
                        spiltNamesUsed.append(j)
                        Start = False
                    j += 1
            if i == amount:
                toReturn.append(v)
        return toReturn

    def blockWithID(self, id, data=0):
        if (id, data) in self.blocksByID:
            return self.blocksByID[id, data]
        else:
            bl = Block(self, id, blockData=data)
            return bl

    def addYamlBlocksFromFile(self, filename):
        try:
            import pkg_resources

            f = pkg_resources.resource_stream(__name__, filename)
        except (ImportError, IOError), e:
            print "Cannot get resource_stream for ", filename, e
            root = os.environ.get("PYMCLEVEL_YAML_ROOT", "pymclevel")  # fall back to cwd as last resort
            path = join(root, filename)

            log.exception("Failed to read %s using pkg_resources. Trying %s instead." % (filename, path))

            f = file(path)
        try:
            log.info(u"Loading block info from %s", f)
            try:
                log.debug("Trying YAML CLoader")
                blockyaml = yaml.load(f, Loader=yaml.CLoader)
            except:
                log.debug("CLoader not preset, falling back to Python YAML")
                blockyaml = yaml.load(f)
            self.addYamlBlocks(blockyaml)

        except Exception, e:
            log.warn(u"Exception while loading block info from %s: %s", f, e)
            traceback.print_exc()

    def addYamlBlocks(self, blockyaml):
        self.yamlDatas.append(blockyaml)
        for block in blockyaml['blocks']:
            try:
                self.addYamlBlock(block)
            except Exception, e:
                log.warn(u"Exception while parsing block: %s", e)
                traceback.print_exc()
                log.warn(u"Block definition: \n%s", pformat(block))

    def addYamlBlock(self, kw):
        blockID = kw['id']

        # xxx unused_yaml_properties variable unused; needed for
        # documentation purpose of some sort?  -zothar
        #unused_yaml_properties = \
        #['explored',
        # # 'id',
        # # 'idStr',
        # # 'mapcolor',
        # # 'name',
        # # 'tex',
        # ### 'tex_data',
        # # 'tex_direction',
        # ### 'tex_direction_data',
        # 'tex_extra',
        # # 'type'
        # ]

        for val, data in kw.get('data', {0: {}}).items():
            datakw = dict(kw)
            datakw.update(data)
            idStr = datakw.get('idStr', "")
            tex = [t * 16 for t in datakw.get('tex', self.defaultTex)]
            texture = [tex] * 6
            texDirs = {
                "FORWARD": 5,
                "BACKWARD": 4,
                "LEFT": 1,
                "RIGHT": 0,
                "TOP": 2,
                "BOTTOM": 3,
            }
            for dirname, dirtex in datakw.get('tex_direction', {}).items():
                if dirname == "SIDES":
                    for dirname in ("LEFT", "RIGHT"):
                        texture[texDirs[dirname]] = [t * 16 for t in dirtex]
                if dirname in texDirs:
                    texture[texDirs[dirname]] = [t * 16 for t in dirtex]
            datakw['texture'] = texture
            # print datakw
            block = self.addBlock(blockID, val, **datakw)
            block.yaml = datakw
            self.idStr[blockID] = idStr

        tex_direction_data = kw.get('tex_direction_data')
        if tex_direction_data:
            texture = datakw['texture']
            # X+0, X-1, Y+, Y-, Z+b, Z-f
            texDirMap = {
                "NORTH": 0,
                "EAST": 1,
                "SOUTH": 2,
                "WEST": 3,
            }

            def rot90cw():
                rot = (5, 0, 2, 3, 4, 1)
                texture[:] = [texture[r] for r in rot]

            for data, dir in tex_direction_data.items():
                for _i in range(texDirMap.get(dir, 0)):
                    rot90cw()
                self.blockTextures[blockID][data] = texture

    def addBlock(self, blockID, blockData=0, **kw):
        name = kw.pop('name', self.names[blockID][blockData])
        stringName = kw.pop('idStr', "")

        self.lightEmission[blockID] = kw.pop('brightness', self.defaultBrightness)
        self.lightAbsorption[blockID] = kw.pop('opacity', self.defaultOpacity)
        self.aka[blockID][blockData] = kw.pop('aka', "")
        type = kw.pop('type', 'NORMAL')

        color = kw.pop('mapcolor', self.flatColors[blockID, blockData])
        self.flatColors[blockID, (blockData or slice(None))] = (tuple(color) + (255,))[:4]

        texture = kw.pop('texture', None)

        if texture:
            self.blockTextures[blockID, (blockData or slice(None))] = texture

        if blockData is 0:
            self.names[blockID] = [name] * 16
            self.type[blockID] = [type] * 16
        else:
            self.names[blockID][blockData] = name
            self.type[blockID][blockData] = type

        block = Block(self, blockID, blockData, blockString=stringName)

        self.allBlocks.append(block)
        self.blocksByType[type].append(block)

        self.blocksByID[blockID, blockData] = block

        return block


PCMaterials = MCMaterials(defaultName="Future Block!")
PCMaterials.name = "Alpha"
PCMaterials.addYamlBlocksFromFile("minecraft.yaml")

# --- Special treatment for some blocks ---

HugeMushroomTypes = {
    "Northwest": 1,
    "North": 2,
    "Northeast": 3,
    "East": 6,
    "Southeast": 9,
    "South": 8,
    "Southwest": 7,
    "West": 4,
    "Stem": 10,
    "Top": 5,
}
from faces import FaceXDecreasing, FaceXIncreasing, FaceYIncreasing, FaceZDecreasing, FaceZIncreasing

Red = (0xD0, 0x70)
Brown = (0xE0, 0x70)
Pore = (0xE0, 0x80)
Stem = (0xD0, 0x80)


def defineShroomFaces(Shroom, id, name):
    for way, data in sorted(HugeMushroomTypes.items(), key=lambda a: a[1]):
        loway = way.lower()
        if way is "Stem":
            tex = [Stem, Stem, Pore, Pore, Stem, Stem]
        elif way is "Pore":
            tex = Pore
        else:
            tex = [Pore] * 6
            tex[FaceYIncreasing] = Shroom
            if "north" in loway:
                tex[FaceZDecreasing] = Shroom
            if "south" in loway:
                tex[FaceZIncreasing] = Shroom
            if "west" in loway:
                tex[FaceXDecreasing] = Shroom
            if "east" in loway:
                tex[FaceXIncreasing] = Shroom

        PCMaterials.addBlock(id, blockData=data,
                                name="Huge " + name + " Mushroom (" + way + ")",
                                texture=tex,
        )


defineShroomFaces(Brown, 99, "Brown")
defineShroomFaces(Red, 100, "Red")

classicMaterials = MCMaterials(defaultName="Not present in Classic")
classicMaterials.name = "Classic"
classicMaterials.addYamlBlocksFromFile("classic.yaml")

indevMaterials = MCMaterials(defaultName="Not present in Indev")
indevMaterials.name = "Indev"
indevMaterials.addYamlBlocksFromFile("indev.yaml")

pocketMaterials = MCMaterials()
pocketMaterials.name = "Pocket"
pocketMaterials.addYamlBlocksFromFile("pocket.yaml")

# --- Static block defs ---

PCMaterials.Stone = PCMaterials[1, 0]
PCMaterials.Grass = PCMaterials[2, 0]
PCMaterials.Dirt = PCMaterials[3, 0]
PCMaterials.Cobblestone = PCMaterials[4, 0]
PCMaterials.WoodPlanks = PCMaterials[5, 0]
PCMaterials.Sapling = PCMaterials[6, 0]
PCMaterials.SpruceSapling = PCMaterials[6, 1]
PCMaterials.BirchSapling = PCMaterials[6, 2]
PCMaterials.Bedrock = PCMaterials[7, 0]
PCMaterials.WaterActive = PCMaterials[8, 0]
PCMaterials.Water = PCMaterials[9, 0]
PCMaterials.LavaActive = PCMaterials[10, 0]
PCMaterials.Lava = PCMaterials[11, 0]
PCMaterials.Sand = PCMaterials[12, 0]
PCMaterials.Gravel = PCMaterials[13, 0]
PCMaterials.GoldOre = PCMaterials[14, 0]
PCMaterials.IronOre = PCMaterials[15, 0]
PCMaterials.CoalOre = PCMaterials[16, 0]
PCMaterials.Wood = PCMaterials[17, 0]
PCMaterials.PineWood = PCMaterials[17, 1]
PCMaterials.BirchWood = PCMaterials[17, 2]
PCMaterials.JungleWood = PCMaterials[17, 3]
PCMaterials.Leaves = PCMaterials[18, 0]
PCMaterials.PineLeaves = PCMaterials[18, 1]
PCMaterials.BirchLeaves = PCMaterials[18, 2]
PCMaterials.JungleLeaves = PCMaterials[18, 3]
PCMaterials.LeavesPermanent = PCMaterials[18, 4]
PCMaterials.PineLeavesPermanent = PCMaterials[18, 5]
PCMaterials.BirchLeavesPermanent = PCMaterials[18, 6]
PCMaterials.JungleLeavesPermanent = PCMaterials[18, 7]
PCMaterials.LeavesDecaying = PCMaterials[18, 8]
PCMaterials.PineLeavesDecaying = PCMaterials[18, 9]
PCMaterials.BirchLeavesDecaying = PCMaterials[18, 10]
PCMaterials.JungleLeavesDecaying = PCMaterials[18, 11]
PCMaterials.Sponge = PCMaterials[19, 0]
PCMaterials.Glass = PCMaterials[20, 0]
PCMaterials.LapisLazuliOre = PCMaterials[21, 0]
PCMaterials.LapisLazuliBlock = PCMaterials[22, 0]
PCMaterials.Dispenser = PCMaterials[23, 0]
PCMaterials.Sandstone = PCMaterials[24, 0]
PCMaterials.NoteBlock = PCMaterials[25, 0]
PCMaterials.Bed = PCMaterials[26, 0]
PCMaterials.PoweredRail = PCMaterials[27, 0]
PCMaterials.DetectorRail = PCMaterials[28, 0]
PCMaterials.StickyPiston = PCMaterials[29, 0]
PCMaterials.Web = PCMaterials[30, 0]
PCMaterials.UnusedShrub = PCMaterials[31, 0]
PCMaterials.TallGrass = PCMaterials[31, 1]
PCMaterials.Shrub = PCMaterials[31, 2]
PCMaterials.DesertShrub2 = PCMaterials[32, 0]
PCMaterials.Piston = PCMaterials[33, 0]
PCMaterials.PistonHead = PCMaterials[34, 0]
PCMaterials.WhiteWool = PCMaterials[35, 0]
PCMaterials.OrangeWool = PCMaterials[35, 1]
PCMaterials.MagentaWool = PCMaterials[35, 2]
PCMaterials.LightBlueWool = PCMaterials[35, 3]
PCMaterials.YellowWool = PCMaterials[35, 4]
PCMaterials.LightGreenWool = PCMaterials[35, 5]
PCMaterials.PinkWool = PCMaterials[35, 6]
PCMaterials.GrayWool = PCMaterials[35, 7]
PCMaterials.LightGrayWool = PCMaterials[35, 8]
PCMaterials.CyanWool = PCMaterials[35, 9]
PCMaterials.PurpleWool = PCMaterials[35, 10]
PCMaterials.BlueWool = PCMaterials[35, 11]
PCMaterials.BrownWool = PCMaterials[35, 12]
PCMaterials.DarkGreenWool = PCMaterials[35, 13]
PCMaterials.RedWool = PCMaterials[35, 14]
PCMaterials.BlackWool = PCMaterials[35, 15]
PCMaterials.Block36 = PCMaterials[36, 0]
PCMaterials.Flower = PCMaterials[37, 0]
PCMaterials.Rose = PCMaterials[38, 0]
PCMaterials.BrownMushroom = PCMaterials[39, 0]
PCMaterials.RedMushroom = PCMaterials[40, 0]
PCMaterials.BlockofGold = PCMaterials[41, 0]
PCMaterials.BlockofIron = PCMaterials[42, 0]
PCMaterials.DoubleStoneSlab = PCMaterials[43, 0]
PCMaterials.DoubleSandstoneSlab = PCMaterials[43, 1]
PCMaterials.DoubleWoodenSlab = PCMaterials[43, 2]
PCMaterials.DoubleCobblestoneSlab = PCMaterials[43, 3]
PCMaterials.DoubleBrickSlab = PCMaterials[43, 4]
PCMaterials.DoubleStoneBrickSlab = PCMaterials[43, 5]
PCMaterials.StoneSlab = PCMaterials[44, 0]
PCMaterials.SandstoneSlab = PCMaterials[44, 1]
PCMaterials.WoodenSlab = PCMaterials[44, 2]
PCMaterials.CobblestoneSlab = PCMaterials[44, 3]
PCMaterials.BrickSlab = PCMaterials[44, 4]
PCMaterials.StoneBrickSlab = PCMaterials[44, 5]
PCMaterials.Brick = PCMaterials[45, 0]
PCMaterials.TNT = PCMaterials[46, 0]
PCMaterials.Bookshelf = PCMaterials[47, 0]
PCMaterials.MossStone = PCMaterials[48, 0]
PCMaterials.Obsidian = PCMaterials[49, 0]
PCMaterials.Torch = PCMaterials[50, 0]
PCMaterials.Fire = PCMaterials[51, 0]
PCMaterials.MonsterSpawner = PCMaterials[52, 0]
PCMaterials.WoodenStairs = PCMaterials[53, 0]
PCMaterials.Chest = PCMaterials[54, 0]
PCMaterials.RedstoneWire = PCMaterials[55, 0]
PCMaterials.DiamondOre = PCMaterials[56, 0]
PCMaterials.BlockofDiamond = PCMaterials[57, 0]
PCMaterials.CraftingTable = PCMaterials[58, 0]
PCMaterials.Crops = PCMaterials[59, 0]
PCMaterials.Farmland = PCMaterials[60, 0]
PCMaterials.Furnace = PCMaterials[61, 0]
PCMaterials.LitFurnace = PCMaterials[62, 0]
PCMaterials.Sign = PCMaterials[63, 0]
PCMaterials.WoodenDoor = PCMaterials[64, 0]
PCMaterials.Ladder = PCMaterials[65, 0]
PCMaterials.Rail = PCMaterials[66, 0]
PCMaterials.StoneStairs = PCMaterials[67, 0]
PCMaterials.WallSign = PCMaterials[68, 0]
PCMaterials.Lever = PCMaterials[69, 0]
PCMaterials.StoneFloorPlate = PCMaterials[70, 0]
PCMaterials.IronDoor = PCMaterials[71, 0]
PCMaterials.WoodFloorPlate = PCMaterials[72, 0]
PCMaterials.RedstoneOre = PCMaterials[73, 0]
PCMaterials.RedstoneOreGlowing = PCMaterials[74, 0]
PCMaterials.RedstoneTorchOff = PCMaterials[75, 0]
PCMaterials.RedstoneTorchOn = PCMaterials[76, 0]
PCMaterials.Button = PCMaterials[77, 0]
PCMaterials.SnowLayer = PCMaterials[78, 0]
PCMaterials.Ice = PCMaterials[79, 0]
PCMaterials.Snow = PCMaterials[80, 0]
PCMaterials.Cactus = PCMaterials[81, 0]
PCMaterials.Clay = PCMaterials[82, 0]
PCMaterials.SugarCane = PCMaterials[83, 0]
PCMaterials.Jukebox = PCMaterials[84, 0]
PCMaterials.Fence = PCMaterials[85, 0]
PCMaterials.Pumpkin = PCMaterials[86, 0]
PCMaterials.Netherrack = PCMaterials[87, 0]
PCMaterials.SoulSand = PCMaterials[88, 0]
PCMaterials.Glowstone = PCMaterials[89, 0]
PCMaterials.NetherPortal = PCMaterials[90, 0]
PCMaterials.JackOLantern = PCMaterials[91, 0]
PCMaterials.Cake = PCMaterials[92, 0]
PCMaterials.RedstoneRepeaterOff = PCMaterials[93, 0]
PCMaterials.RedstoneRepeaterOn = PCMaterials[94, 0]
PCMaterials.StainedGlass = PCMaterials[95, 0]
PCMaterials.Trapdoor = PCMaterials[96, 0]
PCMaterials.HiddenSilverfishStone = PCMaterials[97, 0]
PCMaterials.HiddenSilverfishCobblestone = PCMaterials[97, 1]
PCMaterials.HiddenSilverfishStoneBrick = PCMaterials[97, 2]
PCMaterials.StoneBricks = PCMaterials[98, 0]
PCMaterials.MossyStoneBricks = PCMaterials[98, 1]
PCMaterials.CrackedStoneBricks = PCMaterials[98, 2]
PCMaterials.HugeBrownMushroom = PCMaterials[99, 0]
PCMaterials.HugeRedMushroom = PCMaterials[100, 0]
PCMaterials.IronBars = PCMaterials[101, 0]
PCMaterials.GlassPane = PCMaterials[102, 0]
PCMaterials.Watermelon = PCMaterials[103, 0]
PCMaterials.PumpkinStem = PCMaterials[104, 0]
PCMaterials.MelonStem = PCMaterials[105, 0]
PCMaterials.Vines = PCMaterials[106, 0]
PCMaterials.FenceGate = PCMaterials[107, 0]
PCMaterials.BrickStairs = PCMaterials[108, 0]
PCMaterials.StoneBrickStairs = PCMaterials[109, 0]
PCMaterials.Mycelium = PCMaterials[110, 0]
PCMaterials.Lilypad = PCMaterials[111, 0]
PCMaterials.NetherBrick = PCMaterials[112, 0]
PCMaterials.NetherBrickFence = PCMaterials[113, 0]
PCMaterials.NetherBrickStairs = PCMaterials[114, 0]
PCMaterials.NetherWart = PCMaterials[115, 0]
PCMaterials.EnchantmentTable = PCMaterials[116, 0]
PCMaterials.BrewingStand = PCMaterials[117, 0]
PCMaterials.Cauldron = PCMaterials[118, 0]
PCMaterials.EnderPortal = PCMaterials[119, 0]
PCMaterials.PortalFrame = PCMaterials[120, 0]
PCMaterials.EndStone = PCMaterials[121, 0]
PCMaterials.DragonEgg = PCMaterials[122, 0]
PCMaterials.RedstoneLampoff = PCMaterials[123, 0]
PCMaterials.RedstoneLampon = PCMaterials[124, 0]
PCMaterials.OakWoodDoubleSlab = PCMaterials[125, 0]
PCMaterials.SpruceWoodDoubleSlab = PCMaterials[125, 1]
PCMaterials.BirchWoodDoubleSlab = PCMaterials[125, 2]
PCMaterials.JungleWoodDoubleSlab = PCMaterials[125, 3]
PCMaterials.OakWoodSlab = PCMaterials[126, 0]
PCMaterials.SpruceWoodSlab = PCMaterials[126, 1]
PCMaterials.BirchWoodSlab = PCMaterials[126, 2]
PCMaterials.JungleWoodSlab = PCMaterials[126, 3]
PCMaterials.CocoaPlant = PCMaterials[127, 0]
PCMaterials.SandstoneStairs = PCMaterials[128, 0]
PCMaterials.EmeraldOre = PCMaterials[129, 0]
PCMaterials.EnderChest = PCMaterials[130, 0]
PCMaterials.TripwireHook = PCMaterials[131, 0]
PCMaterials.Tripwire = PCMaterials[132, 0]
PCMaterials.BlockofEmerald = PCMaterials[133, 0]
PCMaterials.SpruceWoodStairs = PCMaterials[134, 0]
PCMaterials.BirchWoodStairs = PCMaterials[135, 0]
PCMaterials.JungleWoodStairs = PCMaterials[136, 0]
PCMaterials.CommandBlock = PCMaterials[137, 0]
PCMaterials.BeaconBlock = PCMaterials[138, 0]
PCMaterials.CobblestoneWall = PCMaterials[139, 0]
PCMaterials.MossyCobblestoneWall = PCMaterials[139, 1]
PCMaterials.FlowerPot = PCMaterials[140, 0]
PCMaterials.Carrots = PCMaterials[141, 0]
PCMaterials.Potatoes = PCMaterials[142, 0]
PCMaterials.WoodenButton = PCMaterials[143, 0]
PCMaterials.MobHead = PCMaterials[144, 0]
PCMaterials.Anvil = PCMaterials[145, 0]
PCMaterials.TrappedChest = PCMaterials[146, 0]
PCMaterials.WeightedPressurePlateLight = PCMaterials[147, 0]
PCMaterials.WeightedPressurePlateHeavy = PCMaterials[148, 0]
PCMaterials.RedstoneComparatorInactive = PCMaterials[149, 0]
PCMaterials.RedstoneComparatorActive = PCMaterials[150, 0]
PCMaterials.DaylightSensor = PCMaterials[151, 0]
PCMaterials.BlockofRedstone = PCMaterials[152, 0]
PCMaterials.NetherQuartzOre = PCMaterials[153, 0]
PCMaterials.Hopper = PCMaterials[154, 0]
PCMaterials.BlockofQuartz = PCMaterials[155, 0]
PCMaterials.QuartzStairs = PCMaterials[156, 0]
PCMaterials.ActivatorRail = PCMaterials[157, 0]
PCMaterials.Dropper = PCMaterials[158, 0]
PCMaterials.StainedClay = PCMaterials[159, 0]
PCMaterials.StainedGlassPane = PCMaterials[160, 0]
PCMaterials.AcaciaLeaves = PCMaterials[161, 0]
PCMaterials.DarkOakLeaves = PCMaterials[161, 1]
PCMaterials.AcaciaLeavesPermanent = PCMaterials[161, 4]
PCMaterials.DarkOakLeavesPermanent = PCMaterials[161, 5]
PCMaterials.AcaciaLeavesDecaying = PCMaterials[161, 8]
PCMaterials.DarkOakLeavesDecaying = PCMaterials[161, 9]
PCMaterials.Wood2 = PCMaterials[162, 0]
PCMaterials.AcaciaStairs = PCMaterials[163, 0]
PCMaterials.DarkOakStairs = PCMaterials[164, 0]
PCMaterials.SlimeBlock = PCMaterials[165, 0]
PCMaterials.Barrier = PCMaterials[166, 0]
PCMaterials.IronTrapdoor = PCMaterials[167, 0]
PCMaterials.Prismarine = PCMaterials[168, 0]
PCMaterials.SeaLantern = PCMaterials[169, 0]
PCMaterials.HayBlock = PCMaterials[170, 0]
PCMaterials.Carpet = PCMaterials[171, 0]
PCMaterials.HardenedClay = PCMaterials[172, 0]
PCMaterials.CoalBlock = PCMaterials[173, 0]
PCMaterials.PackedIce = PCMaterials[174, 0]
PCMaterials.TallFlowers = PCMaterials[175, 0]
PCMaterials.StandingBanner = PCMaterials[176, 0]
PCMaterials.WallBanner = PCMaterials[177, 0]
PCMaterials.DaylightSensorOn = PCMaterials[178, 0]
PCMaterials.RedSandstone = PCMaterials[179, 0]
PCMaterials.SmooothRedSandstone = PCMaterials[179, 1]
PCMaterials.RedSandstoneSairs = PCMaterials[180, 0]
PCMaterials.DoubleRedSandstoneSlab = PCMaterials[181, 0]
PCMaterials.RedSandstoneSlab = PCMaterials[182, 0]
PCMaterials.SpruceFenceGate = PCMaterials[183, 0]
PCMaterials.BirchFenceGate = PCMaterials[184, 0]
PCMaterials.JungleFenceGate = PCMaterials[185, 0]
PCMaterials.DarkOakFenceGate = PCMaterials[186, 0]
PCMaterials.AcaciaFenceGate = PCMaterials[187, 0]
PCMaterials.SpruceFence = PCMaterials[188, 0]
PCMaterials.BirchFence = PCMaterials[189, 0]
PCMaterials.JungleFence = PCMaterials[190, 0]
PCMaterials.DarkOakFence = PCMaterials[191, 0]
PCMaterials.AcaciaFence = PCMaterials[192, 0]
PCMaterials.SpruceDoor = PCMaterials[193, 0]
PCMaterials.BirchDoor = PCMaterials[194, 0]
PCMaterials.JungleDoor = PCMaterials[195, 0]
PCMaterials.AcaciaDoor = PCMaterials[196, 0]
PCMaterials.DarkOakDoor = PCMaterials[197, 0]

# --- Classic static block defs ---
classicMaterials.Stone = classicMaterials[1]
classicMaterials.Grass = classicMaterials[2]
classicMaterials.Dirt = classicMaterials[3]
classicMaterials.Cobblestone = classicMaterials[4]
classicMaterials.WoodPlanks = classicMaterials[5]
classicMaterials.Sapling = classicMaterials[6]
classicMaterials.Bedrock = classicMaterials[7]
classicMaterials.WaterActive = classicMaterials[8]
classicMaterials.Water = classicMaterials[9]
classicMaterials.LavaActive = classicMaterials[10]
classicMaterials.Lava = classicMaterials[11]
classicMaterials.Sand = classicMaterials[12]
classicMaterials.Gravel = classicMaterials[13]
classicMaterials.GoldOre = classicMaterials[14]
classicMaterials.IronOre = classicMaterials[15]
classicMaterials.CoalOre = classicMaterials[16]
classicMaterials.Wood = classicMaterials[17]
classicMaterials.Leaves = classicMaterials[18]
classicMaterials.Sponge = classicMaterials[19]
classicMaterials.Glass = classicMaterials[20]

classicMaterials.RedWool = classicMaterials[21]
classicMaterials.OrangeWool = classicMaterials[22]
classicMaterials.YellowWool = classicMaterials[23]
classicMaterials.LimeWool = classicMaterials[24]
classicMaterials.GreenWool = classicMaterials[25]
classicMaterials.AquaWool = classicMaterials[26]
classicMaterials.CyanWool = classicMaterials[27]
classicMaterials.BlueWool = classicMaterials[28]
classicMaterials.PurpleWool = classicMaterials[29]
classicMaterials.IndigoWool = classicMaterials[30]
classicMaterials.VioletWool = classicMaterials[31]
classicMaterials.MagentaWool = classicMaterials[32]
classicMaterials.PinkWool = classicMaterials[33]
classicMaterials.BlackWool = classicMaterials[34]
classicMaterials.GrayWool = classicMaterials[35]
classicMaterials.WhiteWool = classicMaterials[36]

classicMaterials.Flower = classicMaterials[37]
classicMaterials.Rose = classicMaterials[38]
classicMaterials.BrownMushroom = classicMaterials[39]
classicMaterials.RedMushroom = classicMaterials[40]
classicMaterials.BlockofGold = classicMaterials[41]
classicMaterials.BlockofIron = classicMaterials[42]
classicMaterials.DoubleStoneSlab = classicMaterials[43]
classicMaterials.StoneSlab = classicMaterials[44]
classicMaterials.Brick = classicMaterials[45]
classicMaterials.TNT = classicMaterials[46]
classicMaterials.Bookshelf = classicMaterials[47]
classicMaterials.MossStone = classicMaterials[48]
classicMaterials.Obsidian = classicMaterials[49]

# --- Indev static block defs ---
indevMaterials.Stone = indevMaterials[1]
indevMaterials.Grass = indevMaterials[2]
indevMaterials.Dirt = indevMaterials[3]
indevMaterials.Cobblestone = indevMaterials[4]
indevMaterials.WoodPlanks = indevMaterials[5]
indevMaterials.Sapling = indevMaterials[6]
indevMaterials.Bedrock = indevMaterials[7]
indevMaterials.WaterActive = indevMaterials[8]
indevMaterials.Water = indevMaterials[9]
indevMaterials.LavaActive = indevMaterials[10]
indevMaterials.Lava = indevMaterials[11]
indevMaterials.Sand = indevMaterials[12]
indevMaterials.Gravel = indevMaterials[13]
indevMaterials.GoldOre = indevMaterials[14]
indevMaterials.IronOre = indevMaterials[15]
indevMaterials.CoalOre = indevMaterials[16]
indevMaterials.Wood = indevMaterials[17]
indevMaterials.Leaves = indevMaterials[18]
indevMaterials.Sponge = indevMaterials[19]
indevMaterials.Glass = indevMaterials[20]

indevMaterials.RedWool = indevMaterials[21]
indevMaterials.OrangeWool = indevMaterials[22]
indevMaterials.YellowWool = indevMaterials[23]
indevMaterials.LimeWool = indevMaterials[24]
indevMaterials.GreenWool = indevMaterials[25]
indevMaterials.AquaWool = indevMaterials[26]
indevMaterials.CyanWool = indevMaterials[27]
indevMaterials.BlueWool = indevMaterials[28]
indevMaterials.PurpleWool = indevMaterials[29]
indevMaterials.IndigoWool = indevMaterials[30]
indevMaterials.VioletWool = indevMaterials[31]
indevMaterials.MagentaWool = indevMaterials[32]
indevMaterials.PinkWool = indevMaterials[33]
indevMaterials.BlackWool = indevMaterials[34]
indevMaterials.GrayWool = indevMaterials[35]
indevMaterials.WhiteWool = indevMaterials[36]

indevMaterials.Flower = indevMaterials[37]
indevMaterials.Rose = indevMaterials[38]
indevMaterials.BrownMushroom = indevMaterials[39]
indevMaterials.RedMushroom = indevMaterials[40]
indevMaterials.BlockofGold = indevMaterials[41]
indevMaterials.BlockofIron = indevMaterials[42]
indevMaterials.DoubleStoneSlab = indevMaterials[43]
indevMaterials.StoneSlab = indevMaterials[44]
indevMaterials.Brick = indevMaterials[45]
indevMaterials.TNT = indevMaterials[46]
indevMaterials.Bookshelf = indevMaterials[47]
indevMaterials.MossStone = indevMaterials[48]
indevMaterials.Obsidian = indevMaterials[49]

indevMaterials.Torch = indevMaterials[50, 0]
indevMaterials.Fire = indevMaterials[51, 0]
indevMaterials.InfiniteWater = indevMaterials[52, 0]
indevMaterials.InfiniteLava = indevMaterials[53, 0]
indevMaterials.Chest = indevMaterials[54, 0]
indevMaterials.Cog = indevMaterials[55, 0]
indevMaterials.DiamondOre = indevMaterials[56, 0]
indevMaterials.BlockofDiamond = indevMaterials[57, 0]
indevMaterials.CraftingTable = indevMaterials[58, 0]
indevMaterials.Crops = indevMaterials[59, 0]
indevMaterials.Farmland = indevMaterials[60, 0]
indevMaterials.Furnace = indevMaterials[61, 0]
indevMaterials.LitFurnace = indevMaterials[62, 0]

# --- Pocket static block defs ---

pocketMaterials.Air = pocketMaterials[0, 0]
pocketMaterials.Stone = pocketMaterials[1, 0]
pocketMaterials.Grass = pocketMaterials[2, 0]
pocketMaterials.Dirt = pocketMaterials[3, 0]
pocketMaterials.Cobblestone = pocketMaterials[4, 0]
pocketMaterials.WoodPlanks = pocketMaterials[5, 0]
pocketMaterials.Sapling = pocketMaterials[6, 0]
pocketMaterials.SpruceSapling = pocketMaterials[6, 1]
pocketMaterials.BirchSapling = pocketMaterials[6, 2]
pocketMaterials.Bedrock = pocketMaterials[7, 0]
pocketMaterials.Wateractive = pocketMaterials[8, 0]
pocketMaterials.Water = pocketMaterials[9, 0]
pocketMaterials.Lavaactive = pocketMaterials[10, 0]
pocketMaterials.Lava = pocketMaterials[11, 0]
pocketMaterials.Sand = pocketMaterials[12, 0]
pocketMaterials.Gravel = pocketMaterials[13, 0]
pocketMaterials.GoldOre = pocketMaterials[14, 0]
pocketMaterials.IronOre = pocketMaterials[15, 0]
pocketMaterials.CoalOre = pocketMaterials[16, 0]
pocketMaterials.Wood = pocketMaterials[17, 0]
pocketMaterials.PineWood = pocketMaterials[17, 1]
pocketMaterials.BirchWood = pocketMaterials[17, 2]
pocketMaterials.Leaves = pocketMaterials[18, 0]
pocketMaterials.Glass = pocketMaterials[20, 0]

pocketMaterials.LapisLazuliOre = pocketMaterials[21, 0]
pocketMaterials.LapisLazuliBlock = pocketMaterials[22, 0]
pocketMaterials.Sandstone = pocketMaterials[24, 0]
pocketMaterials.Bed = pocketMaterials[26, 0]
pocketMaterials.Web = pocketMaterials[30, 0]
pocketMaterials.UnusedShrub = pocketMaterials[31, 0]
pocketMaterials.TallGrass = pocketMaterials[31, 1]
pocketMaterials.Shrub = pocketMaterials[31, 2]
pocketMaterials.WhiteWool = pocketMaterials[35, 0]
pocketMaterials.OrangeWool = pocketMaterials[35, 1]
pocketMaterials.MagentaWool = pocketMaterials[35, 2]
pocketMaterials.LightBlueWool = pocketMaterials[35, 3]
pocketMaterials.YellowWool = pocketMaterials[35, 4]
pocketMaterials.LightGreenWool = pocketMaterials[35, 5]
pocketMaterials.PinkWool = pocketMaterials[35, 6]
pocketMaterials.GrayWool = pocketMaterials[35, 7]
pocketMaterials.LightGrayWool = pocketMaterials[35, 8]
pocketMaterials.CyanWool = pocketMaterials[35, 9]
pocketMaterials.PurpleWool = pocketMaterials[35, 10]
pocketMaterials.BlueWool = pocketMaterials[35, 11]
pocketMaterials.BrownWool = pocketMaterials[35, 12]
pocketMaterials.DarkGreenWool = pocketMaterials[35, 13]
pocketMaterials.RedWool = pocketMaterials[35, 14]
pocketMaterials.BlackWool = pocketMaterials[35, 15]
pocketMaterials.Flower = pocketMaterials[37, 0]
pocketMaterials.Rose = pocketMaterials[38, 0]
pocketMaterials.BrownMushroom = pocketMaterials[39, 0]
pocketMaterials.RedMushroom = pocketMaterials[40, 0]
pocketMaterials.BlockofGold = pocketMaterials[41, 0]
pocketMaterials.BlockofIron = pocketMaterials[42, 0]
pocketMaterials.DoubleStoneSlab = pocketMaterials[43, 0]
pocketMaterials.DoubleSandstoneSlab = pocketMaterials[43, 1]
pocketMaterials.DoubleWoodenSlab = pocketMaterials[43, 2]
pocketMaterials.DoubleCobblestoneSlab = pocketMaterials[43, 3]
pocketMaterials.DoubleBrickSlab = pocketMaterials[43, 4]
pocketMaterials.StoneSlab = pocketMaterials[44, 0]
pocketMaterials.SandstoneSlab = pocketMaterials[44, 1]
pocketMaterials.WoodenSlab = pocketMaterials[44, 2]
pocketMaterials.CobblestoneSlab = pocketMaterials[44, 3]
pocketMaterials.BrickSlab = pocketMaterials[44, 4]
pocketMaterials.Brick = pocketMaterials[45, 0]
pocketMaterials.TNT = pocketMaterials[46, 0]
pocketMaterials.Bookshelf = pocketMaterials[47, 0]
pocketMaterials.MossStone = pocketMaterials[48, 0]
pocketMaterials.Obsidian = pocketMaterials[49, 0]

pocketMaterials.Torch = pocketMaterials[50, 0]
pocketMaterials.Fire = pocketMaterials[51, 0]
pocketMaterials.WoodenStairs = pocketMaterials[53, 0]
pocketMaterials.Chest = pocketMaterials[54, 0]
pocketMaterials.DiamondOre = pocketMaterials[56, 0]
pocketMaterials.BlockofDiamond = pocketMaterials[57, 0]
pocketMaterials.CraftingTable = pocketMaterials[58, 0]
pocketMaterials.Crops = pocketMaterials[59, 0]
pocketMaterials.Farmland = pocketMaterials[60, 0]
pocketMaterials.Furnace = pocketMaterials[61, 0]
pocketMaterials.LitFurnace = pocketMaterials[62, 0]
pocketMaterials.WoodenDoor = pocketMaterials[64, 0]
pocketMaterials.Ladder = pocketMaterials[65, 0]
pocketMaterials.StoneStairs = pocketMaterials[67, 0]
pocketMaterials.IronDoor = pocketMaterials[71, 0]
pocketMaterials.RedstoneOre = pocketMaterials[73, 0]
pocketMaterials.RedstoneOreGlowing = pocketMaterials[74, 0]
pocketMaterials.SnowLayer = pocketMaterials[78, 0]
pocketMaterials.Ice = pocketMaterials[79, 0]

pocketMaterials.Snow = pocketMaterials[80, 0]
pocketMaterials.Cactus = pocketMaterials[81, 0]
pocketMaterials.Clay = pocketMaterials[82, 0]
pocketMaterials.SugarCane = pocketMaterials[83, 0]
pocketMaterials.Fence = pocketMaterials[85, 0]
pocketMaterials.Glowstone = pocketMaterials[89, 0]
pocketMaterials.InvisibleBedrock = pocketMaterials[95, 0]
pocketMaterials.Trapdoor = pocketMaterials[96, 0]

pocketMaterials.StoneBricks = pocketMaterials[98, 0]
pocketMaterials.GlassPane = pocketMaterials[102, 0]
pocketMaterials.Watermelon = pocketMaterials[103, 0]
pocketMaterials.MelonStem = pocketMaterials[105, 0]
pocketMaterials.FenceGate = pocketMaterials[107, 0]
pocketMaterials.BrickStairs = pocketMaterials[108, 0]

pocketMaterials.GlowingObsidian = pocketMaterials[246, 0]
pocketMaterials.NetherReactor = pocketMaterials[247, 0]
pocketMaterials.NetherReactorUsed = pocketMaterials[247, 1]


def printStaticDefs(name):
    # printStaticDefs('PCMaterials')
    mats = eval(name)
    for b in sorted(mats.allBlocks):
        print "{name}.{0} = {name}[{1},{2}]".format(
            b.name.replace(" ", "").replace("(", "").replace(")", ""),
            b.ID, b.blockData,
            name=name,
        )


_indices = rollaxis(indices((id_limit, 16)), 0, 3)


def _filterTable(filters, unavailable, default=(0, 0)):
    # a filter table is a id_limit table of (ID, data) pairs.
    table = zeros((id_limit, 16, 2), dtype='uint8')
    table[:] = _indices
    for u in unavailable:
        try:
            if u[1] == 0:
                u = u[0]
        except TypeError:
            pass
        table[u] = default
    for f, t in filters:
        try:
            if f[1] == 0:
                f = f[0]
        except TypeError:
            pass
        table[f] = t
    return table


nullConversion = lambda b, d: (b, d)


def filterConversion(table):
    def convert(blocks, data):
        if data is None:
            data = 0
        t = table[blocks, data]
        return t[..., 0], t[..., 1]

    return convert


def guessFilterTable(matsFrom, matsTo):
    """ Returns a pair (filters, unavailable)
    filters is a list of (from, to) pairs;  from and to are (ID, data) pairs
    unavailable is a list of (ID, data) pairs in matsFrom not found in matsTo.

    Searches the 'name' and 'aka' fields to find matches.
    """
    filters = []
    unavailable = []
    toByName = dict(((b.name, b) for b in sorted(matsTo.allBlocks, reverse=True)))
    for fromBlock in matsFrom.allBlocks:
        block = toByName.get(fromBlock.name)
        if block is None:
            for b in matsTo.allBlocks:
                if b.name.startswith(fromBlock.name):
                    block = b
                    break
        if block is None:
            for b in matsTo.allBlocks:
                if fromBlock.name in b.name:
                    block = b
                    break
        if block is None:
            for b in matsTo.allBlocks:
                if fromBlock.name in b.aka:
                    block = b
                    break
        if block is None:
            if "Indigo Wool" == fromBlock.name:
                block = toByName.get("Purple Wool")
            elif "Violet Wool" == fromBlock.name:
                block = toByName.get("Purple Wool")

        if block:
            if block != fromBlock:
                filters.append(((fromBlock.ID, fromBlock.blockData), (block.ID, block.blockData)))
        else:
            unavailable.append((fromBlock.ID, fromBlock.blockData))

    return filters, unavailable


allMaterials = (PCMaterials, classicMaterials, pocketMaterials, indevMaterials)

_conversionFuncs = {}


def conversionFunc(destMats, sourceMats):
    if destMats is sourceMats:
        return nullConversion
    func = _conversionFuncs.get((destMats, sourceMats))
    if func:
        return func

    filters, unavailable = guessFilterTable(sourceMats, destMats)
    log.debug("")
    log.debug("%s %s %s", sourceMats.name, "=>", destMats.name)
    for a, b in [(sourceMats.blockWithID(*a), destMats.blockWithID(*b)) for a, b in filters]:
        log.debug("{0:20}: \"{1}\"".format('"' + a.name + '"', b.name))

    log.debug("")
    log.debug("Missing blocks: %s", [sourceMats.blockWithID(*a).name for a in unavailable])

    table = _filterTable(filters, unavailable, (35, 0))
    func = filterConversion(table)
    _conversionFuncs[(destMats, sourceMats)] = func
    return func


def convertBlocks(destMats, sourceMats, blocks, blockData):
    if sourceMats == destMats:
        return blocks, blockData

    return conversionFunc(destMats, sourceMats)(blocks, blockData)


namedMaterials = dict((i.name, i) for i in allMaterials)
alphaMaterials = PCMaterials

block_map = {
    0:"minecraft:air",1:"minecraft:stone",2:"minecraft:grass",3:"minecraft:dirt",4:"minecraft:cobblestone",5:"minecraft:planks",6:"minecraft:sapling",
    7:"minecraft:bedrock",8:"minecraft:flowing_water",9:"minecraft:water",10:"minecraft:flowing_lava",11:"minecraft:lava",12:"minecraft:sand",13:"minecraft:gravel",
    14:"minecraft:gold_ore",15:"minecraft:iron_ore",16:"minecraft:coal_ore",17:"minecraft:log",18:"minecraft:leaves",19:"minecraft:sponge",20:"minecraft:glass",
    21:"minecraft:lapis_ore",22:"minecraft:lapis_block",23:"minecraft:dispenser",24:"minecraft:sandstone",25:"minecraft:noteblock",26:"minecraft:bed",
    27:"minecraft:golden_rail",28:"minecraft:detector_rail",29:"minecraft:sticky_piston",30:"minecraft:web",31:"minecraft:tallgrass",32:"minecraft:deadbush",
    33:"minecraft:piston",34:"minecraft:piston_head",35:"minecraft:wool",36:"minecraft:piston_extension",37:"minecraft:yellow_flower",38:"minecraft:red_flower",
    39:"minecraft:brown_mushroom",40:"minecraft:red_mushroom",41:"minecraft:gold_block",42:"minecraft:iron_block",43:"minecraft:double_stone_slab",
    44:"minecraft:stone_slab",45:"minecraft:brick_block",46:"minecraft:tnt",47:"minecraft:bookshelf",48:"minecraft:mossy_cobblestone",49:"minecraft:obsidian",
    50:"minecraft:torch",51:"minecraft:fire",52:"minecraft:mob_spawner",53:"minecraft:oak_stairs",54:"minecraft:chest",55:"minecraft:redstone_wire",
    56:"minecraft:diamond_ore",57:"minecraft:diamond_block",58:"minecraft:crafting_table",59:"minecraft:wheat",60:"minecraft:farmland",61:"minecraft:furnace",
    62:"minecraft:lit_furnace",63:"minecraft:standing_sign",64:"minecraft:wooden_door",65:"minecraft:ladder",66:"minecraft:rail",67:"minecraft:stone_stairs",
    68:"minecraft:wall_sign",69:"minecraft:lever",70:"minecraft:stone_pressure_plate",71:"minecraft:iron_door",72:"minecraft:wooden_pressure_plate",
    73:"minecraft:redstone_ore",74:"minecraft:lit_redstone_ore",75:"minecraft:unlit_redstone_torch",76:"minecraft:redstone_torch",77:"minecraft:stone_button",
    78:"minecraft:snow_layer",79:"minecraft:ice",80:"minecraft:snow",81:"minecraft:cactus",82:"minecraft:clay",83:"minecraft:reeds",84:"minecraft:jukebox",
    85:"minecraft:fence",86:"minecraft:pumpkin",87:"minecraft:netherrack",88:"minecraft:soul_sand",89:"minecraft:glowstone",90:"minecraft:portal",
    91:"minecraft:lit_pumpkin",92:"minecraft:cake",93:"minecraft:unpowered_repeater",94:"minecraft:powered_repeater",
    95:"minecraft:stained_glass",96:"minecraft:trapdoor",97:"minecraft:monster_egg",98:"minecraft:stonebrick",
    99:"minecraft:brown_mushroom_block",100:"minecraft:red_mushroom_block",101:"minecraft:iron_bars",102:"minecraft:glass_pane",103:"minecraft:melon_block",
    104:"minecraft:pumpkin_stem",105:"minecraft:melon_stem",106:"minecraft:vine",107:"minecraft:fence_gate",108:"minecraft:brick_stairs",109:"minecraft:stone_brick_stairs",
    110:"minecraft:mycelium",111:"minecraft:waterlily",112:"minecraft:nether_brick",113:"minecraft:nether_brick_fence",114:"minecraft:nether_brick_stairs",
    115:"minecraft:nether_wart",116:"minecraft:enchanting_table",117:"minecraft:brewing_stand",118:"minecraft:cauldron",119:"minecraft:end_portal",
    120:"minecraft:end_portal_frame",121:"minecraft:end_stone",122:"minecraft:dragon_egg",123:"minecraft:redstone_lamp",124:"minecraft:lit_redstone_lamp",
    125:"minecraft:double_wooden_slab",126:"minecraft:wooden_slab",127:"minecraft:cocoa",128:"minecraft:sandstone_stairs",129:"minecraft:emerald_ore",
    130:"minecraft:ender_chest",131:"minecraft:tripwire_hook",132:"minecraft:tripwire",133:"minecraft:emerald_block",134:"minecraft:spruce_stairs",
    135:"minecraft:birch_stairs",136:"minecraft:jungle_stairs",137:"minecraft:command_block",138:"minecraft:beacon",139:"minecraft:cobblestone_wall",
    140:"minecraft:flower_pot",141:"minecraft:carrots",142:"minecraft:potatoes",143:"minecraft:wooden_button",144:"minecraft:skull",145:"minecraft:anvil",
    146:"minecraft:trapped_chest",147:"minecraft:light_weighted_pressure_plate",148:"minecraft:heavy_weighted_pressure_plate",149:"minecraft:unpowered_comparator",
    150:"minecraft:powered_comparator",151:"minecraft:daylight_detector",152:"minecraft:redstone_block",153:"minecraft:quartz_ore",154:"minecraft:hopper",
    155:"minecraft:quartz_block",156:"minecraft:quartz_stairs",157:"minecraft:activator_rail",158:"minecraft:dropper",159:"minecraft:stained_hardened_clay",
    160:"minecraft:stained_glass_pane",162:"minecraft:log2",163:"minecraft:acacia_stairs",164:"minecraft:dark_oak_stairs",165:"minecraft:slime",166:"minecraft:barrier",
    167:"minecraft:iron_trapdoor",168:"minecraft:prismarine",169:"minecraft:sea_lantern",
    170:"minecraft:hay_block",171:"minecraft:carpet",172:"minecraft:hardened_clay",173:"minecraft:coal_block",174:"minecraft:packed_ice",175:"minecraft:double_plant",
    176:"minecraft:standing_banner",177:"minecraft:wall_banner",178:"minecraft:daylight_detector_inverted",179:"minecraft:red_sandstone",180:"minecraft:red_sandstone_stairs",
    181:"minecraft:double_stone_slab2",182:"minecraft:stone_slab2",183:"minecraft:spruce_fence_gate",184:"minecraft:birch_fence_gate",185:"minecraft:jungle_fence_gate",
    161:"minecraft:leaves2",186:"minecraft:dark_oak_fence_gate",187:"minecraft:acacia_fence_gate",188:"minecraft:spruce_fence",189:"minecraft:birch_fence",190:"minecraft:jungle_fence",
    191:"minecraft:dark_oak_fence",192:"minecraft:acacia_fence",193:"minecraft:spruce_door",194:"minecraft:birch_door",195:"minecraft:jungle_door",196:"minecraft:acacia_door",
    197:"minecraft:dark_oak_door"
}

__all__ = "indevMaterials, pocketMaterials, PCMaterials, classicMaterials, namedMaterials, MCMaterials".split(", ")
