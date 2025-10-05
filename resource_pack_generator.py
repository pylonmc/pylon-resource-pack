import os
import json
import copy
import shutil
import zipfile

"""
This script generates a pylon resource pack from supplied assets from the 'input' directory.
It will automatically create item model definitions and block models for pylon items based
on inputted json files & block states.

Pylon Blocks are not real blocks so you cannot use actual block states, you can recreate the
effect of them with complex item model definitions, but those are hard to do by hand, so this
will do it for you.

You can also supply item model definitions manually if there are any cases you need to handle
yourself.

This script automates:
- atlas appending
- item model definition creation
  - this includes making the item model definition files for the vanilla items that back the pylon items provided (which you can provide specific model values for if needed)
  - if you don't specify a model within the items/<id>.json file, it will look for an item model with the same id, then a block model with the same id, if it can't find either but can find a texture under its id, it will use the built-in "item/generated" model with that texture
    - if it defaults to a provided block model, it will create a new item model that inherits from the block model so that the "fixed" display can be changed, as in block context "fixed" is a placed block, but in item context "fixed" is an item frame
- blockstate to item model conversion
  - this includes both creating the item model definitions, and creating specific item model variants based on rotations
- merging item model definitions
"""

# The order that all common properties are listed in the custom model data of an item.
# Any properties not listed here will be checked for (at the index of) the order they are found.
BUILT_IN_PROPERTY_ORDER = [
    "powered",
    "power",
    "open",
    "half",
    "hanging",
    "face",
    "facing",
    "axis",
    "rotation",
    "type",
    "shape",
    "faces"
]

TRIM_TYPES = [
    "helmet",
    "chestplate",
    "leggings",
    "boots"
]

TRIMS = [
    "quartz",
    "iron",
    "netherite",
    "redstone",
    "copper",
    "gold",
    "emerald",
    "diamond",
    "lapis",
    "amethyst",
    "resin"
]

TEMPLATE_DIR = "template"
INPUT_DIR = "input"
OUTPUT_DIR = "output"

developing = False
packName = "test" if developing else input("What is the name of the outputted resource pack? ")
packVersion = 1 if developing else input("What is the version of the resource pack? (e.g. 1.0.0) ")
flatten = False if developing else input("Flatten json files? (y/n) ").lower() == 'y'
logWarnings = True if developing else input("Log warnings? (y/n) ").lower() == 'y'
deleteTemp = False if developing else input("Delete temp files? (only keeps the zip) (y/n) ").lower() == 'y'

tempDir = os.path.join(OUTPUT_DIR, "temp")
if os.path.exists(tempDir):
    for root, dirs, files in os.walk(tempDir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
else:
    os.makedirs(tempDir)
outputPath = os.path.join(OUTPUT_DIR, f"{packName}.zip")

# unpack template/items/items.zip into template/items
if os.path.exists(os.path.join(TEMPLATE_DIR, "items", "items.zip")):
    with zipfile.ZipFile(os.path.join(TEMPLATE_DIR, "items", "items.zip"), 'r') as zf:
        zf.extractall(os.path.join(TEMPLATE_DIR, "items"))
else:
    if logWarnings:
        print(f"Warning: Template items.zip does not exist. (The generator may not work properly without it.)")

indent = None if flatten else 2
blockModelDefinitions = []
itemModelDefinitions = {}

## Generator Methods
def get_template(templatePath):
    file_path = os.path.join(TEMPLATE_DIR, f"{templatePath}.json")
    if not os.path.exists(file_path):
        if logWarnings:
            print(f"Warning: Template {templatePath} ('{file_path}') does not exist, skipping.")
        return None
    with open(file_path, 'r') as f:
        return json.load(f)

def asset_saved(assetPath):
    namespace, path = assetPath.split(':') if ':' in assetPath else ('minecraft', assetPath)
    file_path = os.path.join(tempDir, "assets", namespace, path)
    return os.path.exists(file_path)

def asset_exists(assetPath):
    namespace, path = assetPath.split(':') if ':' in assetPath else ('minecraft', assetPath)
    file_path = os.path.join(INPUT_DIR, "assets", namespace, path)
    if os.path.exists(file_path):
        return True

    file_path = os.path.join(tempDir, "assets", namespace, path)
    return os.path.exists(file_path)

def save_asset(assetPath, data):
    if asset_saved(assetPath):
        return

    namespace, path = assetPath.split(':') if ':' in assetPath else ('minecraft', assetPath)
    file_path = os.path.join(tempDir, "assets", namespace, path)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=indent)

modelCache = {}
def get_model(modelPath, logWarnings=logWarnings):
    namespace, path = modelPath.split(':') if ':' in modelPath else ('minecraft', modelPath)
    if modelPath in modelCache:
        return copy.deepcopy(modelCache[modelPath])

    file_path = os.path.join(INPUT_DIR, "assets", namespace, "models", f"{path}.json")
    if not os.path.exists(file_path):
        output_file_path = os.path.join(tempDir, "assets", namespace, "models", f"{path}.json")
        if os.path.exists(output_file_path):
            with open(output_file_path, 'r') as f:
                model = json.load(f)
                modelCache[modelPath] = model
                return copy.deepcopy(model)

        if logWarnings:
            print(f"Warning: model {modelPath} ('{file_path}') does not exist, skipping.")
        return None

    with open(file_path, 'r') as f:
        model = json.load(f)
        modelCache[modelPath] = model
        return copy.deepcopy(model)
        

def save_model(modelPath, model):
    namespace, path = modelPath.split(':') if ':' in modelPath else ('minecraft', modelPath)
    asset_path = f"{namespace}:models/{path}"
    save_asset(f"{asset_path}.json", model)

def texture_ever_exists(texturePath):
    namespace, path = texturePath.split(':') if ':' in texturePath else ('minecraft', texturePath)
    name = path.split('/')[-1] if '/' in path else path
    path = path.rsplit('/', 1)[0] if '/' in path else ''
    file_path = os.path.join(INPUT_DIR, "assets", namespace, "textures", path)
    if os.path.exists(os.path.join(file_path, f"{name}.png")):
        return True

    for _, _, files in os.walk(file_path):
        if f"{name}.png" in files:
            return True
    return False

def find_texture(texturePath):
    namespace, path = texturePath.split(':') if ':' in texturePath else ('minecraft', texturePath)
    name = path.split('/')[-1] if '/' in path else path
    path = path.rsplit('/', 1)[0] if '/' in path else ''
    # Check the expected location under textures/<path>
    textures_dir = os.path.join(INPUT_DIR, "assets", namespace, "textures", path)
    if os.path.exists(os.path.join(textures_dir, f"{name}.png")):
        # Return resource path relative to the textures folder (no 'textures/' prefix)
        rel = os.path.join(path, name).replace(os.sep, '/') if path else name
        return f"{namespace}:{rel}"

    # If not found at the expected location, search the whole textures folder for the file
    search_root = os.path.join(INPUT_DIR, "assets", namespace, "textures")
    for root, _, files in os.walk(search_root):
        if f"{name}.png" in files:
            rel_path = os.path.relpath(root, search_root)
            rel = os.path.join(rel_path, name).replace(os.sep, '/') if rel_path != '.' else name
            return f"{namespace}:{rel}"
    return None

def save_item_definition(itemPath, itemDef):
    namespace, itemKey = itemPath.split(':') if ':' in itemPath else ('minecraft', itemPath)
    save_asset(f"{namespace}:items/{itemKey}.json", itemDef)

def create_block_model_variant(name, variant):
    if "uvlock" in variant or "weight" in variant:
        if logWarnings:
            print(f"Warning: Block variant {name} contains uvlock or weight, which are not supported, skipping.")
        return None
    
    modelPath = variant["model"]
    model = get_model(modelPath, False)
    if model is None:
        namespace, path = modelPath.split(':') if ':' in modelPath else ('minecraft', modelPath)
        if texture_ever_exists(f"{namespace}:{path}"):
            texturePath = find_texture(f"{namespace}:{path}")
            modelPath = f"{namespace}:{path}"
            model = {
                "parent": "block/cube_all",
                "textures": {
                    "all": texturePath,
                    "particle": texturePath
                },
                "display": {
                    "fixed": {}
                }
            }
            if "author" in variant:
                model["author"] = variant["author"]
            save_model(modelPath, model)
        else:
            if logWarnings:
                print(f"Warning: Block variant {name} root model {modelPath} could not be found, skipping.")
            return None

    if "x" in variant or "y" in variant:        
        if "x" in variant:
            x_rot = variant["x"] % 360
            modelPath += f"_x{x_rot}"
        if "y" in variant:
            y_rot = variant["y"] % 360
            modelPath += f"_y{y_rot}"

        if not get_model(modelPath, False) is None:
            return modelPath # already exists

        display = model["display"] if "display" in model else {}
        fixed_display = display["fixed"] if "fixed" in display else {}
        fixed_rotation = fixed_display["rotation"] if "rotation" in fixed_display else [0, 0, 0]
        if "x" in variant:
            x_rot = variant["x"] % 360
            fixed_rotation[0] = (fixed_rotation[0] + x_rot) % 360
        if "y" in variant:
            y_rot = variant["y"] % 360
            fixed_rotation[1] = (fixed_rotation[1] + y_rot) % 360
        fixed_display["rotation"] = fixed_rotation
        display["fixed"] = fixed_display
        model["display"] = display
        save_model(modelPath, model)
    else:
        save_model(modelPath, model)
    

    return modelPath
        
## First copy over all non block/item definitions (as these are only used to generate actual assets, they are not directly assets themselves):
for namespace in os.listdir(os.path.join(INPUT_DIR, "assets")):
    namespacePath = os.path.join(INPUT_DIR, "assets", namespace)
    if not os.path.isdir(namespacePath):
        continue

    for root, dirs, files in os.walk(namespacePath):
        for file in files:
            relDir = os.path.relpath(root, namespacePath)
            relFile = os.path.join(relDir, file) if relDir != '.' else file
            relFile = relFile.replace("\\", "/")
            if relFile.startswith("blocks/") or relFile.startswith("items/"):
                continue

            inputFilePath = os.path.join(root, file)
            outputFilePath = os.path.join(tempDir, "assets", namespace, relFile)
            os.makedirs(os.path.dirname(outputFilePath), exist_ok=True)
            shutil.copyfile(inputFilePath, outputFilePath)

for file in os.listdir(INPUT_DIR):
    inputFilePath = os.path.join(INPUT_DIR, file)
    if os.path.isfile(inputFilePath) and file != "assets":
        outputFilePath = os.path.join(tempDir, file)
        shutil.copyfile(inputFilePath, outputFilePath)


## Generate from blockstate files:
for namespace in os.listdir(os.path.join(INPUT_DIR, "assets")):
    namespacePath = os.path.join(INPUT_DIR, "assets", namespace)
    if not os.path.isdir(namespacePath):
        continue

    blocksPath = os.path.join(namespacePath, "blocks")
    if not os.path.exists(blocksPath):
        continue

    blockStates = []
    for root, dirs, files in os.walk(blocksPath):
        for file in files:
            relDir = os.path.relpath(root, blocksPath)
            relFile = os.path.join(relDir, file) if relDir != '.' else file
            relFile = relFile.replace("\\", "/")
            if os.path.isfile(os.path.join(root, file)):
                blockStates.append(relFile)

    for blockFile in blockStates:
        if not blockFile.endswith(".json"):
            if logWarnings:
                print(f"Warning: Block file {blockFile} is not a json file, skipping.")
            continue

        blockFilePath = os.path.join(blocksPath, blockFile)
        with open(blockFilePath, 'r') as f:
            blockData = json.load(f)

        if "multipart" in blockData:
            if logWarnings:
                print(f"Warning: Block file {blockFilePath} contains multipart definitions, which are not yet supported, skipping.")
            continue

        if "variants" in blockData and (not isinstance(blockData["variants"], dict) or len(blockData["variants"]) == 0):
            if logWarnings:
                print(f"Warning: Block file {blockFilePath} does not contain valid variants, skipping.")
            continue
        variants = blockData["variants"] if "variants" in blockData else {}

        if len(variants) > 1 and ("properties" not in blockData or not isinstance(blockData["properties"], list)):
            if logWarnings:
                print(f"Warning: Block file {blockFilePath} does not contain a list of possible properties, skipping.")
            continue
        allPropertyKeys = blockData["properties"] if "properties" in blockData else []
        allPropertyValues = {}
        for key in allPropertyKeys:
            allPropertyValues[key] = []

        blockPath = blockFile[:-5]
        blockName = blockPath.split('/')[-1] if '/' in blockPath else blockPath
        blockModel = {}
        blockModelDefinition = {
            "when": f"{namespace}:{blockName}"
        }
        cases = []

        if (variants == {}) :
            modelPath = f"{namespace}:block/{blockName}"
            if (get_model(modelPath, False) is not None):
                model = get_model(modelPath, False)
            else:
                modelPath = f"{namespace}:block/{blockPath}"
                model = get_model(modelPath, False)
            
            if model is None:
                if texture_ever_exists(f"{namespace}:block/{blockName}"):
                    texturePath = find_texture(f"{namespace}:block/{blockName}")
                    modelPath = texturePath
                    model = {
                        "parent": "block/cube_all",
                        "textures": {
                            "all": texturePath,
                            "particle": texturePath
                        },
                        "display": {
                            "fixed": {}
                        }
                    }
                    if "author" in blockData:
                        model["author"] = blockData["author"]
                    save_model(modelPath, model)
                else:
                    if logWarnings:
                        print(f"Warning: Block file {blockFilePath} does not contain any variants and no model or texture to generate a model could be found for it, skipping.")
                    continue
            
            variants[""] = {
                "model": modelPath
            }

        for name, variant in variants.items():
            if "model" not in variant:
                if logWarnings:
                    print(f"Warning: Block variant {name} does not contain a model, skipping.")
                continue

            if "author" in blockData:
                variant["author"] = blockData["author"]

            properties = {}
            for prop in name.split(','):
                if '=' not in prop:
                    if name != "" and logWarnings:
                        print(f"Warning: Block variant {name} contains invalid property {prop}, skipping.")
                    continue
                key, value = prop.split('=')
                properties[key] = value
                if key not in allPropertyKeys:
                    allPropertyKeys.append(key)
                if value not in allPropertyValues[key]:
                    allPropertyValues[key].append(value)

            modelPath = create_block_model_variant(name, variant)
            if modelPath is None:
                continue

            cases.append({
                "properties": properties,
                "model": modelPath
            })
        
        allPropertyKeys.sort(key=lambda x: BUILT_IN_PROPERTY_ORDER.index(x) if x in BUILT_IN_PROPERTY_ORDER else len(BUILT_IN_PROPERTY_ORDER) + allPropertyKeys.index(x))

        def build_select_from_cases(cases_list, propertyKeys, index=0):
            if index >= len(propertyKeys):
                return None

            key = propertyKeys[index]
            select = {
                "type": "minecraft:select",
                "property": "custom_model_data",
                "index": index + 1, # plus one because the first index is the block model id itself
                "cases": []
            }

            groups = {}
            for case in cases_list:
                value = case["properties"].get(key, None)
                if value is None:
                    if logWarnings:
                        print(f"Warning: Case {case} does not contain property {key}, skipping.")
                    continue
                groups.setdefault(value, []).append(case)

            for value, group in groups.items():
                if index == len(propertyKeys) - 1:
                    models = {c["model"] for c in group}
                    if len(models) > 1:
                        if logWarnings:
                            print(f"Warning: Multiple models for property {key}={value} at leaf, using first.")
                    model_choice = next(iter(models))
                    case_entry = {
                        "when": f"{key}={value}",
                        "model": {
                            "type": "minecraft:model",
                            "model": model_choice
                        }
                    }
                else:
                    sub_select = build_select_from_cases(group, propertyKeys, index + 1)
                    if sub_select is None:
                        continue
                    case_entry = {
                        "when": f"{key}={value}",
                        "model": sub_select
                    }
                select["cases"].append(case_entry)

            return select if select["cases"] else None

        if len(cases) == 1 and (not cases[0].get("properties")):
            blockModel = {
                "type": "minecraft:model",
                "model": cases[0]["model"]
            }
        else:
            blockModel = build_select_from_cases(cases, allPropertyKeys, 0)
        blockModelDefinition["model"] = blockModel
        blockModelDefinitions.append(blockModelDefinition)

## Assemble final "air" item model definition (what block models work off of)
# uses the select model type against the 0 index of custom_model_data
airModelDefinition = {
    "model": {
        "type": "minecraft:select",
        "property": "custom_model_data",
        "index": 0,
        "cases": [],
        "fallback": {
            "type": "minecraft:model",
            "model": "minecraft:item/air"
        }
    }
}
for modelDef in blockModelDefinitions:
    airModelDefinition["model"]["cases"].append(modelDef)
save_item_definition("air", airModelDefinition)

## Now handle item definition files:
# First compile all of the different cases
for namespace in os.listdir(os.path.join(INPUT_DIR, "assets")):
    namespacePath = os.path.join(INPUT_DIR, "assets", namespace)
    if not os.path.isdir(namespacePath):
        continue

    itemsPath = os.path.join(namespacePath, "items")
    if not os.path.exists(itemsPath):
        continue

    itemFiles = []
    for root, dirs, files in os.walk(itemsPath):
        for file in files:
            relDir = os.path.relpath(root, itemsPath)
            relFile = os.path.join(relDir, file) if relDir != '.' else file
            relFile = relFile.replace("\\", "/")
            if os.path.isfile(os.path.join(root, file)):
                itemFiles.append(relFile)

    for itemFile in itemFiles:
        if not itemFile.endswith(".json"):
            if logWarnings:
                print(f"Warning: Item file {itemFile} is not a json file, skipping.")
            continue

        itemFilePath = os.path.join(itemsPath, itemFile)
        with open(itemFilePath, 'r') as f:
            itemData = json.load(f)

        itemPath = itemFile[:-5]
        itemName = itemPath.split('/')[-1] if '/' in itemPath else itemPath
        itemKey = f"{namespace}:{itemName}"
        
        if "vanilla" not in itemData or not isinstance(itemData["vanilla"], str):
            if logWarnings:
                print(f"Warning: Item file {itemFilePath} does not contain a valid vanilla item id, skipping.")
            continue
        vanillaItem = itemData["vanilla"]
        if not ":" in vanillaItem:
            vanillaItem = f"minecraft:{vanillaItem}"

        vanillaDefinition = itemModelDefinitions[vanillaItem] if vanillaItem in itemModelDefinitions else {
            "model": {
                "type": "minecraft:select",
                "property": "custom_model_data",
                "index": 0,
                "cases": []
            }
        }
        vanillaCases = vanillaDefinition["model"]["cases"] if "cases" in vanillaDefinition["model"] else []
        
        if "fallback" in itemData:
            if "fallback" in vanillaDefinition:
                if logWarnings:
                    print(f"Warning: Item file {itemFilePath} contains a fallback but one is already defined for {vanillaItem}, overwriting fallback {vanillaDefinition['fallback']}.")
            vanillaDefinition["fallback"] = itemData["fallback"]

        if "oversized" in itemData:
            if itemData["oversized"] != True:
                if logWarnings:
                    print(f"Warning: Item file {itemFilePath} contains invalid oversized value (should only ever be 'true'), skipping.")
                continue
            vanillaDefinition["oversized_in_gui"] = True
        
        case = None
        if "model" in itemData:
            model = itemData["model"]
            if isinstance(model, dict):
                case = {
                    "when": f"{itemKey}",
                    "model": itemData["model"]
                }
            elif isinstance(model, str):
                case = {
                    "when": f"{itemKey}",
                    "model": {
                        "type": "minecraft:model",
                        "model": model
                    }
                }
            else:
                if logWarnings:
                    print(f"Warning: Item file {itemFilePath} contains invalid model value (should be a full definition or inlined model reference), skipping.")
                continue
        else:
            modelPath = f"{namespace}:item/{itemName}"
            if (get_model(modelPath, False) is not None):
                model = get_model(modelPath, False)
            else:
                modelPath = f"{namespace}:item/{itemPath}"
                model = get_model(modelPath, False)

            if model is None:
                modelPath = f"{namespace}:block/{itemName}"
                if (get_model(modelPath, False) is not None):
                    model = get_model(modelPath, False)
                else:
                    modelPath = f"{namespace}:block/{itemPath}"
                    model = get_model(modelPath, False)

                if model is not None:
                    if "display" in model and "fixed" in model["display"]:
                        model["display"]["fixed"] = {
                            "scale": [0.5, 0.5, 0.5]
                        }
                        modelPath = f"{namespace}:item/{itemPath}"
                        save_model(modelPath, model)
                    case = {
                        "when": f"{itemKey}",
                        "model": {
                            "type": "minecraft:model",
                            "model": modelPath
                        }
                    }
                elif texture_ever_exists(f"{namespace}:item/{itemName}"):
                    texturePath = find_texture(f"{namespace}:item/{itemName}")
                    modelPath = texturePath
                    model = {
                        "parent": "item/generated",
                        "textures": {
                            "layer0": texturePath,
                            "particle": texturePath
                        }
                    }
                    if "author" in itemData:
                        model["author"] = itemData["author"]
                    save_model(modelPath, model)
                    case = {
                        "when": f"{itemKey}",
                        "model": {
                            "type": "minecraft:model",
                            "model": modelPath
                        }
                    }
                else:
                    if logWarnings:
                        print(f"Warning: Item file {itemFilePath} does not contain a model and no model or texture to generate a model could be found for it, skipping.")
                    continue
            else:
                case = {
                    "when": f"{itemKey}",
                    "model": {
                        "type": "minecraft:model",
                        "model": modelPath
                    }
                }
        
        if "create_trims" in itemData:
            trimType = itemData["create_trims"]
            if trimType not in TRIM_TYPES:
                if logWarnings:
                    print(f"Warning: Item file {itemFilePath} contains invalid trimmable type {trimType} (must be one of {TRIM_TYPES}), skipping.")
                continue
            elif case["model"]["type"] != "minecraft:model":
                if logWarnings:
                    print(f"Warning: Item file {itemFilePath} contains trimmable value but its model type is not 'minecraft:model', skipping.")
                continue

            modelPath = case["model"]["model"]
            model = get_model(modelPath)
            if model is None:
                if logWarnings:
                    print(f"Warning: Item file {itemFilePath} trimmable model {modelPath} could not be found, skipping.")
                continue
            elif "parent" not in model or model["parent"] != "item/generated":
                if logWarnings:
                    print(f"For automatic trims, item model {modelPath} must have parent 'item/generated', skipping.")
                continue

            trimCases = []
            case = {
                "when": f"{itemKey}",
                "model": {
                    "type": "minecraft:select",
                    "property": "trim_material",
                    "cases": trimCases,
                    "fallback": case["model"]
                }
            }

            for trim in TRIMS:
                trimModelPath = f"{modelPath}_trim_{trim}"
                trimModel = copy.deepcopy(model)
                
                if "particle" in trimModel["textures"]:
                    particleLayer = trimModel["textures"].pop("particle")
                trimModel["textures"][f"layer{len(trimModel['textures'])}"] = f"trims/items/{trimType}_trim_{trim}"
                if particleLayer is not None:
                    trimModel["textures"]["particle"] = particleLayer
                
                save_model(trimModelPath, trimModel)
                trimCases.append({
                    "when": trim,
                    "model": {
                        "type": "minecraft:model",
                        "model": trimModelPath
                    }
                })
        
        vanillaCases.append(case)
        vanillaDefinition["model"]["cases"] = vanillaCases
        itemModelDefinitions[vanillaItem] = vanillaDefinition
                    
# Then create each item definition
for itemKey, itemDef in itemModelDefinitions.items():
    namespace, itemName = itemKey.split(':') if ':' in itemKey else ('minecraft', itemKey)
    if "fallback" not in itemDef["model"]:
        template = get_template(f"items/{itemName}")
        if template is None:
            template = {"model": {"type": "minecraft:model", "model": f"minecraft:item/{itemName}"} }
        itemDef["model"]["fallback"] = template["model"]
    save_item_definition(itemKey, itemDef)

# Add the atlas appends
atlasSources = []
# find all textures under assets/<namespace>/textures/item and assets/<namespace>/textures/block
for namespace in os.listdir(os.path.join(INPUT_DIR, "assets")):
    namespacePath = os.path.join(INPUT_DIR, "assets", namespace)
    if not os.path.isdir(namespacePath):
        continue

    texturesPath = os.path.join(namespacePath, "textures")
    if not os.path.exists(texturesPath):
        continue

    for root, dirs, files in os.walk(texturesPath):
        for file in files:
            relDir = os.path.relpath(root, texturesPath)
            relFile = os.path.join(relDir, file) if relDir != '.' else file
            relFile = relFile.replace("\\", "/")
            if not file.endswith(".png"):
                continue
            if relFile.startswith("item/") or relFile.startswith("block/"):
                atlasSources.append({
                    "type": "single",
                    "resource": f"{namespace}:{relFile[:-4]}"
                })

save_asset("minecraft:atlases/blocks.json", {
    "sources": atlasSources
})

# output logic:
if os.path.exists(outputPath):
    if logWarnings:
        print(f"Warning: Output file {outputPath} already exists, overwriting.")
    os.remove(outputPath)

with zipfile.ZipFile(outputPath, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(tempDir):
        for file in files:
            filePath = os.path.join(root, file)
            arcname = os.path.relpath(filePath, tempDir)
            zf.write(filePath, arcname)

print(f"Resource pack '{packName}' version {packVersion} generated at '{outputPath}'.")

# clean up temp files
if os.path.exists(tempDir) and deleteTemp:
    for root, dirs, files in os.walk(tempDir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(tempDir)

# clean up template/items files (leave items.zip)
if os.path.exists(os.path.join(TEMPLATE_DIR, "items")):
    for root, dirs, files in os.walk(os.path.join(TEMPLATE_DIR, "items"), topdown=False):
        for name in files:
            if name != "items.zip":
                os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))