# ACIES CDK3 / XMF Reverse-Engineering Notes

Date: 2026-04-29

This document records the current local understanding of the ACIES APK asset
format, how the `.xmf` decrypt/decode path was found, what CDK3 explains, and
what remains game-specific.

## Workspace

All paths below are relative to:

```text
/Users/p997eyc/projects/boot/acies
```

Important local inputs:

```text
acies.apk
acies-apktool/
acies-jadx/
cdk3/
tools/xmf_probe.py
tools/cdk_xmf_parse.py
tools/decode_cdk_mesh.py
tools/decode_cdk_terrain.py
decrypts/
```

The decoded APK came from `apktool d`. The Java navigation tree came from
`jadx --no-res`. Patches to the APK should be made in `acies-apktool`, not in
the JADX output.

## APK Shape

ACIES is not a normal Java-heavy Android app. The Java layer is mostly a shell
around native code:

- Package: `com.creagames.clashoflegions`
- Main activity: `kr.co.brgames.talescraft2.MainActivity`
- `MainActivity` extends `CSActivity`
- `CSActivity` loads `libcdkapp.so`
- `CSView` is a `GLSurfaceView`
- Runtime starts through native methods such as `nativeStart(...)`

The meaningful game behavior is primarily in:

```text
acies-apktool/lib/arm64-v8a/libcdkapp.so
acies-apktool/assets/**/*.xmf
acies-jadx/sources/kr/co/brgames/cdk
```

The native library exports many C++ symbols, including CDK-style classes such as
`CSBuffer`, `CSData`, `CSGraphics`, `CSRootImage`, `CSAnimation`, `CSMesh`, and
ACIES game classes. This strongly suggested a custom/native engine rather than
Unity, Unreal, Cocos, or Godot.

## CDK3 Evidence

The cloned `cdk3/` repository appears to be the same engine family:

- `cdk3/README.md` says it is based on the mobile game engine used in Tales
  Craft and ACIES projects.
- `cdk3/client/src/CDK` contains the C++ engine runtime.
- `cdk3/editor/src` contains a C# asset editor.
- `cdk3/client/src/CDK/Sources/IO/CSBuffer.cpp` defines the primitive binary
  format used by built assets.
- `cdk3/editor/src/CDK.Assets/Version/VersionAsset.cs` defines how version
  manifests are written.
- `cdk3/editor/src/CDK.Assets/Support/Crypto.cs` defines the AES/hash behavior
  used by the asset build tools.

Useful source references:

```text
cdk3/client/src/CDK/Sources/IO/CSBuffer.cpp
cdk3/client/src/CDK/Sources/Core/CSString.cpp
cdk3/client/src/CDK/Sources/Core/CSLocaleString.cpp
cdk3/editor/src/CDK.Assets/Support/Crypto.cs
cdk3/editor/src/CDK.Assets/Version/VersionAsset.cs
cdk3/editor/src/CDK.Assets/Version/VersionEntry.cs
cdk3/editor/src/CDK.Assets/TypeUtil.cs
```

## Can CDK3 Launch On macOS?

Not directly as cloned.

The editor is Windows-specific:

```text
cdk3/editor/src/CDK.AssetEditor/CDK.AssetEditor.csproj
```

Key blockers:

- Targets `.NET Framework 4.8`
- Uses WinForms
- Uses `kernel32.dll` in `Program.cs`
- Depends on Windows UI/control packages

The client side has:

```text
cdk3/client/src/CDKProject.windows/CDKProject.sln
cdk3/client/src/CDKProject.windows/CDK.vcxproj
cdk3/client/src/CDK/android.cmake
cdk3/client/src/CDK/Sources/Platform/android
cdk3/client/src/CDK/Sources/Platform/ios
cdk3/client/src/CDK/Sources/Platform/windows
```

There is no macOS platform directory, no Xcode project, and no CMake target for
Darwin/macOS in this clone. A native macOS launch would require a new platform
layer for window/input/audio/files/network/GL context and a build target. The
practical launch path is a Windows VM/Parallels/Wine setup first.

Local tool check at the time of investigation:

```text
dotnet: not installed
msbuild: not installed
mono: not installed
cmake: /opt/homebrew/bin/cmake
```

## XMF Container Decryption

The first working decrypt/probe helper is:

```text
tools/xmf_probe.py
```

It handles:

- raw gzip `.xmf`
- AES-256-CBC encrypted `.xmf`
- XOR checksum trailer validation
- optional gzip/zlib after decrypt
- string preview
- writing decoded payloads

The key derivation for APK asset paths is:

```python
SHA1("brtc" + asset_relative_path).hexdigest()[:32].encode("ascii")
```

Example:

```text
data/game[071].xmf
```

uses:

```python
SHA1("brtcdata/game[071].xmf").hexdigest()[:32]
```

AES settings:

```text
AES-256-CBC
PKCS5/PKCS7 padding
key = ASCII bytes of the 32-char truncated SHA1 hex string
iv = first 16 ASCII bytes of that key
```

After decrypting, encrypted files have a 4-byte little-endian XOR checksum
trailer. The checksum is the XOR of up to the first 256 little-endian 32-bit
words of the decrypted payload, excluding the trailer.

The CDK3 source confirms the same build-side behavior in:

```text
cdk3/editor/src/CDK.Assets/Support/Crypto.cs
cdk3/editor/src/CDK.Assets/Version/VersionAsset.cs
```

## XMF Classification

Current classification of ACIES APK `.xmf` files:

```text
551 total
484 gzip
34 encrypted + gzip
15 encrypted direct
18 plain/custom binary
```

Encrypted direct examples:

```text
version.xmf
data/menu.xmf
data/game[071].xmf
data/game[072].xmf
...
data/game[083].xmf
```

Plain/custom examples:

```text
strings.xmf
locale.xmf
animations.xmf
mesh/*.xmf
```

## Decoded Test Corpus

The following decoded files were written for easy testing:

```text
decrypts/game[071].xmf.decoded
decrypts/map[000][000][001].xmf.decoded
decrypts/small/locale.xmf.decoded
decrypts/small/images[003][004].xmf.decoded
decrypts/small/images[003][019].xmf.decoded
decrypts/small/mesh[000][004].xmf.decoded
decrypts/small/version.xmf.decoded
decrypts/small/game[071].xmf.decoded
decrypts/small/map[003][005][001].xmf.decoded
```

Useful commands:

```bash
python3 tools/xmf_probe.py \
  'acies-apktool/assets/data/game[071].xmf' \
  'acies-apktool/assets/maps/map[000][000][001].xmf' \
  --write-dir decrypts

python3 tools/xmf_probe.py \
  acies-apktool/assets/version.xmf \
  --write-dir decrypts/small
```

## CDK Binary Primitives

`CSBuffer` is the core binary reader.

Important primitives:

```text
byte:        1 signed byte in C++ readByte()
bool:        byte != 0
short:       little-endian i16
int:         little-endian i32
long:        little-endian i64
half:        little-endian fp16
float:       little-endian fp32
double:      little-endian fp64
fixed:       little-endian i64 fixed-point
length:      custom big-endian 7-bit varint
string:      readLength() bytes of UTF-8
locale str:  array of locale/value string pairs
```

The custom `readLength()` algorithm is:

```text
value = 0
repeat:
  current = read byte
  value = (value << 7) | (current & 0x7f)
until current high bit is clear
```

This is confirmed in:

```text
cdk3/client/src/CDK/Sources/IO/CSBuffer.cpp
cdk3/editor/src/CDK.Assets/TypeUtil.cs
```

## Structured Parser Added

The structured parser foundation is:

```text
tools/cdk_xmf_parse.py
```

It reuses the decode layer from `xmf_probe.py`, then parses selected CDK/game
schemas.

Currently implemented:

- `CSBufferReader`
- full local `version.xmf` parser
- partial `strings.xmf` localized string parser
- JSON output
- CSV output

Commands used:

```bash
python3 -m py_compile tools/xmf_probe.py tools/cdk_xmf_parse.py

python3 tools/cdk_xmf_parse.py \
  acies-apktool/assets/version.xmf \
  --kind version \
  --output decrypts/version.xmf.json \
  --csv decrypts/version.xmf.csv

python3 tools/cdk_xmf_parse.py \
  acies-apktool/assets/strings.xmf \
  --kind strings \
  --output decrypts/strings.xmf.partial.json \
  --csv decrypts/strings.xmf.partial.csv
```

Verified `version.xmf` result:

```text
version-local: parsed=1206/1206 remaining=0 decoded=38561
```

Generated outputs:

```text
decrypts/version.xmf.json
decrypts/version.xmf.csv
decrypts/strings.xmf.partial.json
decrypts/strings.xmf.partial.csv
```

`version.xmf` begins with:

```text
u16 bundle_version
u16 revision
readLength entry_count
repeat entry_count:
  string path
  i16 version
```

This maps directly to `VersionAsset.BuildLocal()` and
`VersionEntry.BuildLocal()` in CDK3.

For this APK:

```text
bundle_version = 2
revision = 177
entries = 1206
```

First parsed entries:

```text
data/game[071].xmf version 28
data/game[072].xmf version 29
data/game[073].xmf version 30
data/game[074].xmf version 31
data/game[075].xmf version 33
```

## strings.xmf Status

`strings.xmf` starts with a little-endian `u16` count:

```text
22562
```

The first records parse as repeated CDK `CSLocaleString` values:

```text
readLength locale_pair_count
repeat locale_pair_count:
  string locale
  string value
```

The first string record parses to:

```json
{
  "ko": "...",
  "en": "OK",
  "th": "...",
  "zh-Hans": "...",
  "ru": "...",
  "ar": "...",
  "fa": "...",
  "zh-Hant": "...",
  "es": "Aceptar",
  "pt": "OK"
}
```

The current parser stops at record index 88 because a later record contains an
extra game-specific marker/prefix that is not plain `CSLocaleString`. This is
why the output is named `strings.xmf.partial.*`.

Current result:

```text
locale-string-table: parsed=88/22562 remaining=1937491 decoded=1951509
```

Next step for full `strings.xmf`: find the ACIES game-specific reader in
`libcdkapp.so`, likely a string manager / resource manager constructor using
`CSBuffer`.

## Image XMF Decoder

The APK image files under:

```text
acies-apktool/assets/images/images*.xmf
```

are mostly gzip-compressed `.xmf` files. After gzip decompression, they do not
match the newer CDK3 `CSTexture` writer exactly. Instead, `libcdkapp.so`
exports an older image path:

```text
CSRootImage::createWithBuffer(CSBuffer*)
CSRootImage::loadRawData(...)
CSRootImage::loadETC2Data(...)
CSRootImage::loadASTCData(...)
CSSubImage::CSSubImage(CSBuffer*, CSImage const*)
```

The useful disassembly target was:

```text
acies-apktool/lib/arm64-v8a/libcdkapp.so
symbol: CSRootImage::createWithBuffer(CSBuffer*)
address: 0x7f0e9c in the arm64-v8a library used during this pass
```

From that function, the root image block format is:

```text
uint32 block_length
int16  format_prefix
int16  width
int16  height
uint8  encoding_count
repeat encoding_count:
  uint8  encoding_code
  uint32 payload_length
  bytes  payload
tail bytes: subimage/atlas metadata
```

For ETC2 payloads, the payload starts with a mip-level count byte. The texture
data after that is GPU compressed block data. Raw RGBA payloads have no mip
prefix and are exactly `width * height * 4` bytes.

Observed encoding codes:

```text
6 = ETC2 RGB8
7 = ETC2 RGBA8
15 = raw RGBA8888
```

Decoder tool added:

```text
tools/decode_cdk_image.py
```

A local virtual environment was created for dependencies:

```text
.venv-xmf/
```

Installed packages:

```text
pillow
texture2ddecoder
```

Commands:

```bash
python3 -m venv .venv-xmf
.venv-xmf/bin/python -m pip install --upgrade pip
.venv-xmf/bin/python -m pip install pillow texture2ddecoder

.venv-xmf/bin/python tools/decode_cdk_image.py \
  'acies-apktool/assets/images/images[003][019].xmf' \
  --out-dir decrypts/images/png \
  --meta-dir decrypts/images/meta
```

Smallest image findings:

```text
images[003][004].xmf  raw 23 bytes -> decoded 5 bytes, empty image block
images[003][007].xmf  raw 23 bytes -> decoded 5 bytes, empty image block
images[003][018].xmf  raw 23 bytes -> decoded 5 bytes, empty image block
images[003][019].xmf  206x206 ETC2_RGBA8, decoded to PNG
images[003][011].xmf  406x202 ETC2_RGBA8, decoded to PNG
images[002][003].xmf  256x167 ETC2_RGBA8, decoded to PNG
images[007][007].xmf  256x256 ETC2_RGB8 with 9 mips, decoded to PNG
```

Generated output examples:

```text
decrypts/images/png/images[003][019].png
decrypts/images/png/images[003][011].png
decrypts/images/png/images[002][003].png
decrypts/images/png/images[007][007].png
decrypts/images/meta/images[003][019].json
```

Full image batch:

```bash
mkdir -p decrypts/images/all-png decrypts/images/all-meta
: > decrypts/images/decode-all.log
: > decrypts/images/decode-all-failures.txt
find acies-apktool/assets/images -type f -name 'images*.xmf' -print0 | sort -z |
while IFS= read -r -d '' p; do
  if .venv-xmf/bin/python tools/decode_cdk_image.py "$p" \
    --out-dir decrypts/images/all-png \
    --meta-dir decrypts/images/all-meta >> decrypts/images/decode-all.log 2>&1; then
    :
  else
    printf '%s\n' "$p" >> decrypts/images/decode-all-failures.txt
  fi
done
```

Final full-batch result:

```text
source image XMFs: 483
PNG atlases written: 480
metadata JSON files: 483
empty image blocks: 3
failures: 0
PNG output size: about 1.0G
```

The 3 non-PNG files are the tiny empty-image blocks above.

For browsing, a thumbnail index was generated:

```text
decrypts/images/index.html
decrypts/images/thumbs/
```

The image decoder currently extracts the full atlas texture. The trailing bytes
after the root image block are almost certainly subimage/atlas rectangle
metadata. That tail still needs a dedicated parser if individual icons/sprites
should be cropped automatically.

## Mesh Decoding

The APK meshes under:

```text
acies-apktool/assets/meshes/mesh[*].xmf
```

are plain CDK binary files, not AES/XOR encrypted and not gzip-compressed. Each
file starts with a little-endian `int32` block length equal to `file_size - 4`.

The first attempt to match them against the cloned CDK3 source showed that the
current open-source `CSMesh.cpp` schema is newer than the APK assets, and the
editor-side writer at:

```text
cdk3/editor/src/CDK.Assets/Meshing/MeshAsset.cs
```

still has `BuildImpl()` as `TODO`. The working schema came from disassembling
the APK runtime symbols:

```text
CSMesh::createWithBuffer(CSBuffer*)
CSMeshNode::createWithBuffer(CSMeshNode const*, CSBuffer*, unsigned int&)
CSVertex::CSVertex(CSBuffer*)
CSMatrix::CSMatrix(CSBuffer*)
```

The mesh file layout is:

```text
int32 block_length
uint7 node_count
repeat node_count:
  int32 parent_node_index
  uint7 triangle_count
  repeat triangle_count * 3:
    float32 x, y, z
    uint8 r, g, b, a
    float32 u, v
    float32 normal_x, normal_y, normal_z
  string node_name
  float32 matrix[16]
  bool has_animation
  if has_animation:
    CSMeshAnimation payload
  bool flag0
  bool flag1
  bool flag2
  uint8 sort
int32 footer0
int32 footer1
int32 footer2
```

For the 15 ACIES mesh files, `has_animation` was false for every parsed node.
All files have footer `[100, 160, 30]`.

The decoder is:

```text
tools/decode_cdk_mesh.py
```

Batch command used:

```bash
python3 tools/decode_cdk_mesh.py acies-apktool/assets/meshes/*.xmf \
  --out-dir decrypts/meshes \
  --full-json
```

Outputs:

```text
decrypts/meshes/index.json
decrypts/meshes/json/       compact metadata, no vertex arrays
decrypts/meshes/json-full/  full parsed JSON with every vertex
decrypts/meshes/obj/        Wavefront OBJ exports
```

Batch result:

```text
source mesh files: 15
parsed meshes:     15
total nodes:       22
total triangles:   7856
total vertices:    23568
```

Smallest mesh:

```text
mesh[000][004].xmf  48 triangles, 144 vertices
```

## Terrain XMF Decoder

The APK file:

```text
acies-apktool/assets/terrain.xmf
```

is gzip-compressed. After decompression it is not a full terrain geometry file
and it is not an AES/XOR asset. The payload is a CDK root-image bank with two
arrays:

```text
uint7 lightmap_image_count
repeat lightmap_image_count:
  CSRootImage block
uint7 terrain_texture_count
repeat terrain_texture_count:
  CSRootImage block
```

This was confirmed by parsing the full decoded payload with zero trailing bytes.
The first byte is `0x3a`, which is `58`, the number of lightmap images. Each of
those 58 records is a `256x256` ETC2_RGB8 root image. The next byte is `0x05`,
the number of terrain texture images.

The decoder is:

```text
tools/decode_cdk_terrain.py
```

Batch command used:

```bash
.venv-xmf/bin/python tools/decode_cdk_terrain.py \
  acies-apktool/assets/terrain.xmf \
  --out-dir decrypts/terrain
```

Outputs:

```text
decrypts/terrain/index.json
decrypts/terrain/index.html
decrypts/terrain/terrain.xmf.decoded
decrypts/terrain/meta/lightmaps/
decrypts/terrain/meta/terrain_textures/
decrypts/terrain/png/lightmaps/
decrypts/terrain/png/terrain_textures/
```

Batch result:

```text
decoded size:      4152512 bytes
groups:            2
total images:      63
lightmaps:         58 images, 256x256, ETC2_RGB8
terrain_textures:   5 images
```

Terrain texture group:

```text
terrain-01-000.png  256x256  ETC2_RGB8
terrain-01-001.png  512x512  ETC2_RGB8
terrain-01-002.png  512x512  ETC2_RGB8
terrain-01-003.png  512x512  ETC2_RGB8
terrain-01-004.png  512x512  RGBA8888
```

Important distinction: CDK3 does have a generic `CSTerrain` reader and the
ACIES APK has game-specific `Terrain::Terrain(CSBuffer*)`, `Terrain::loadSurface`
and `Terrain::loadAltitude` symbols. Those explain related formats, but this
standalone `terrain.xmf` file is only the texture bank described above. Actual
terrain dimensions, altitude, surface placement, water placement, camera, and
trigger data should be expected in map/data assets, not in this file.

## Remaining XMF Format Families

There are 551 `.xmf` files under `acies-apktool/assets`.

```text
483 images        decoded to 480 PNG atlases; 3 are empty image blocks
 68 non-images    18 fully parsed, 1 partially parsed, 49 not yet parsed
```

Non-image inventory:

```text
animations.xmf       1  plain
data/               14  AES + XOR checksum, no compression
locale.xmf           1  plain
maps/               34  AES + XOR checksum + gzip
meshes/             15  plain
strings.xmf          1  plain
terrain.xmf          1  gzip only
version.xmf          1  AES + XOR checksum, parsed
```

The non-image types are:

```text
version.xmf
  Status: parsed completely by tools/cdk_xmf_parse.py.
  Meaning: asset/version manifest. It has bundle_version=2, revision=177, and
  1206 manifest entries. It includes the XMFs plus sound assets.

strings.xmf
  Status: partially parsed.
  Meaning: game string / locale-string table. It starts with locale-string
  records like ko/en values, then diverges into an ACIES-specific extension.
  Native evidence: CSLocaleString and Asset::loadStrings().

locale.xmf
  Status: parsed by tools/cdk_xmf_parse.py.
  Meaning: locale/language metadata table. Small, plain file. Starts with
  records like ko=한국어, en=English.
  Native evidence: LocaleData::LocaleData(CSBuffer*),
  LanguageData::LanguageData(CSBuffer*), Asset::loadLocales(),
  Option::loadLocales().

data/game[071..083].xmf
  Status: container decoded; schema not parsed.
  Meaning: game balance/content database. Repeated game versions with unit,
  resource, ability, rune, card, skin, theme, quest, reward, product, and
  tutorial-style records.
  Native evidence includes ResourceData, UnitData, CommandData, AbilityData,
  AbilityTargetData, AbilityDescriptionData, RuneData, RuneLevelData,
  RuneTierData, CardLevelData, SkinData, ThemeData, QuestData, RewardItem, and
  many readNArrayImpl<T> symbols.

data/menu.xmf
  Status: container decoded; schema not parsed.
  Meaning: lobby/menu/client metadata table. Starts with localized strings such
  as ko=언랭크, en=Unranked.
  Native evidence: Asset::loadMenu().

maps/map[*].xmf
  Status: container decoded; schema not parsed.
  Meaning: battle map data. Each file contains localized map names, map setup,
  forces/resources/units/squads, and mission/trigger bytecode.
  Native evidence: Map::Map(AssetIndex4 const&, CSBuffer*, ...), Map::read(),
  MapThumb::MapThumb(...), Terrain::Terrain(CSBuffer*), and many trigger
  opcode handlers named Map::mt* such as mtUnit, mtResource, mtMission,
  mtAction, mtTimer, mtMessage, mtAnimation, mtControl.

meshes/mesh[*].xmf
  Status: parsed and exported by tools/decode_cdk_mesh.py.
  Meaning: older ACIES/CDK mesh assets. Plain files with a 4-byte length
  wrapper, node records, old packed vertices, node transforms, and footer ints.
  Native evidence: libcdkapp.so CSMesh::createWithBuffer(CSBuffer*) and
  CSMeshNode::createWithBuffer(CSMeshNode const*, CSBuffer*, unsigned int&).
  CDK3 source helped with CSBuffer primitives, but the cloned editor-side
  MeshAsset.BuildImpl writer is TODO and the modern CDK3 CSMeshGeometry reader
  does not directly match these APK files.

animations.xmf
  Status: container decoded; schema not parsed.
  Meaning: animation bank, not a single generic CDK AnimationAsset file.
  Native evidence: Asset::loadAnimations(), CSArray<CSAnimation, 3>,
  CSArray<CSArray<CSAnimation, 2>>, GameAnimation::GameAnimation(...), and
  CSAnimation::CSAnimation(CSBuffer*).

terrain.xmf
  Status: parsed and exported by tools/decode_cdk_terrain.py.
  Meaning: standalone CDK terrain texture bank, not full terrain geometry.
  Contains 58 lightmap images and 5 terrain texture images. All 63 images were
  decoded to PNG.
  Native/CDK evidence: CSRootImage::createWithBuffer(CSBuffer*) and the terrain
  editor's light/surface texture build path. Generic CSTerrain and ACIES
  Terrain::Terrain symbols explain related map terrain records, but they do not
  describe this top-level terrain.xmf payload.
```

## Locale XMF Parser

`locale.xmf` is now parsed completely. The command is:

```bash
python3 tools/cdk_xmf_parse.py acies-apktool/assets/locale.xmf \
  --output decrypts/locale.json \
  --csv decrypts/locale.csv
```

Output:

```text
locale-metadata: parsed=10/10 remaining=0 decoded=310
decrypts/locale.json
decrypts/locale.csv
```

Observed schema:

```text
uint7/count locale_count
repeat locale_count:
  int32 unknown_i32
  int32 payload_length
  bytes payload:
    uint7/count alias_count
    repeat alias_count:
      string locale_alias
    string display_name
    uint8 digit_group_separator
```

Parsed locale records:

```text
ko       display=한국어       aliases=ko
en       display=English      aliases=en
th       display=ภาษาไทย      aliases=th
zh-Hans  display=简体         aliases=zh-Hans, zh-CN
zh-Hant  display=繁体         aliases=zh-Hant, zh-MO, zh-HK, zh-TW
ru       display=Русский      aliases=ru, uk, be, hy, az, tt, kk, ky, uz, ka, tg, tk, ro
ar       display=عربى         aliases=ar
fa       display=فارسی        aliases=fa
es       display=Español      aliases=es
pt       display=Português    aliases=pt
```

The `digit_group_separator` field matches the native
`CSLocaleString::_digitGroupSeperator` symbol. The leading `unknown_i32` field
is preserved as `unknown_i32`; do not rename it until we confirm its meaning in
`LocaleData::LocaleData(CSBuffer*)`.

## ACIES game database parser

The ACIES-specific game database files are now decoded by:

```text
tools/decode_acies_game_data.py
```

It reuses the `xmf_probe.py` AES/checksum/decompress layer, then applies the
schema recovered from `Asset::loadGame(int)` and the exported record
constructors in `libcdkapp.so`.

Command used for the validated batch:

```bash
python3 tools/decode_acies_game_data.py \
  acies-apktool/assets/data/game\[*\].xmf \
  --out-dir decrypts/game
```

Generated outputs:

```text
decrypts/game/index.json
decrypts/game/game[071].xmf.json
decrypts/game/game[071].xmf.summary.json
decrypts/game/game[071].xmf.sections.csv
decrypts/game/game[071].xmf.abilities.csv
decrypts/game/game[071].xmf.units.csv
decrypts/game/game[071].xmf.runes.csv
decrypts/game/decoded/game[071].xmf.decoded
...
decrypts/game/game[083].xmf.json
```

Validation result:

```text
game[071].xmf decoded=599422 remaining=0 abilities=45 targets=14 units_outer=8 runes_outer=2
game[072].xmf decoded=600561 remaining=0 abilities=45 targets=14 units_outer=8 runes_outer=2
game[073].xmf decoded=608164 remaining=0 abilities=45 targets=14 units_outer=8 runes_outer=2
game[074].xmf decoded=749905 remaining=0 abilities=47 targets=14 units_outer=8 runes_outer=2
game[075].xmf decoded=750975 remaining=0 abilities=47 targets=14 units_outer=8 runes_outer=2
game[076].xmf decoded=757034 remaining=0 abilities=48 targets=14 units_outer=8 runes_outer=2
game[077].xmf decoded=758466 remaining=0 abilities=48 targets=14 units_outer=8 runes_outer=2
game[078].xmf decoded=877038 remaining=0 abilities=48 targets=14 units_outer=8 runes_outer=2
game[079].xmf decoded=877038 remaining=0 abilities=48 targets=14 units_outer=8 runes_outer=2
game[080].xmf decoded=877271 remaining=0 abilities=48 targets=14 units_outer=8 runes_outer=2
game[081].xmf decoded=877280 remaining=0 abilities=48 targets=14 units_outer=8 runes_outer=2
game[082].xmf decoded=881015 remaining=0 abilities=48 targets=14 units_outer=8 runes_outer=2
game[083].xmf decoded=881015 remaining=0 abilities=48 targets=14 units_outer=8 runes_outer=2
```

The parser writes full JSON with `_type`, `_offset`, `_end`, and `_size` on
major records so schema mistakes can be traced back to the binary. Repeated byte
arrays, including ability bytecode-like fields, are stored as compact hex plus
small value lists where short enough.

Top-level `Asset::loadGame(int)` order:

```text
header: short, short, float, float
AbilityData[]
AbilityTargetData[]
short table
CommandData[][]
DamageTypeData[]
DamageTypeData[]
fixed damage matrix
UnitData[][]
ResourceData
ResourceData
BuffData[][]
RuneData[][]
uint8[][][]
PingData[]
AnnounceData[]
enabled AssetIndex2/int table
enabled AssetIndex2/int table
```

Important implementation corrections found while validating:

- `AbilityUnitData::Entry` reads `uint8[][]`, then target short refs, then two
  fixed values.
- `SkinData` reads optional indices, name, byte, description, and
  `AbilityUnitData` before slot/replacement/voice tables.
- `VoiceData` is four `AssetIndex3[]` arrays, not strings.
- `AnnounceData` maps each string in a group to the group's `AssetIndex2`; there
  is not a separate `AssetIndex2` after every string.

## What CDK3 Solves vs What It Does Not

CDK3 solves:

- encryption/hash/checksum behavior
- `CSBuffer` primitive reads
- CDK string and locale-string encoding
- version manifest schema
- engine asset schemas where CDK3 source has concrete readers/writers
- image and mesh schemas when combined with the matching APK runtime symbols
- likely animation, terrain, material, trigger, and scene formats

CDK3 does not fully solve:

- ACIES map gameplay schema
- semantic naming of many ACIES unit/building/ability/balance fields
- game-specific string table extensions
- runtime protection / AppSafer behavior

Those game-specific formats live in `libcdkapp.so`, not in generic CDK3.

## Recommended Parser Roadmap

Keep the parser layered:

1. Container layer
   - decrypt
   - checksum
   - decompress
   - already implemented in `xmf_probe.py`

2. CDK primitive layer
   - `CSBufferReader`
   - implemented in `cdk_xmf_parse.py`

3. Generic CDK asset schemas
   - version manifest
   - locale strings
   - images / subimages
   - mesh
   - animation
   - terrain
   - triggers

4. ACIES game schemas from `libcdkapp.so`
   - game data files
   - maps
   - string table extensions
   - unit/ability/economy tables

High-value next targets:

```text
version.xmf        fully parsed, use as manifest/index
locale.xmf         small and readable, likely locale metadata
strings.xmf        needs game-specific marker handling
data/game[071].xmf small enough for schema discovery
maps/map[003][005][001].xmf smallest encrypted+gzip map sample
```

## Map Decoder

`maps/map[003][005][001].xmf` is now structurally decoded by:

```bash
.venv-xmf/bin/python tools/decode_acies_map.py \
  'acies-apktool/assets/maps/map[003][005][001].xmf' \
  --out-dir decrypts/maps
```

Outputs:

```text
decrypts/maps/map[003][005][001].decoded
decrypts/maps/map[003][005][001].json
```

Validation result:

```text
decoded=3270095
remaining=0
terrain=100x80
tiles=8000
trigger groups=7
```

The map decoder follows `Map::Map(AssetIndex4 const&, CSBuffer*, ...)` in
`libcdkapp.so`, not the generic CDK3 `CSTerrain` reader. The useful top-level
order is:

```text
map metadata block table
Terrain::Terrain(CSBuffer*)
Tile[terrain.width * terrain.height]
resource tables, two passes
prop tables, two passes
Squad[][] 
unit placement settings
FPoint[]
Area[]
Camera
uint8[][][] trigger bytecode
```

Important map parser corrections:

- The initial metadata block contains locale-string name/description, three
  optional `AssetIndex3` icon refs, force-slot records, and player-slot records.
- Embedded ACIES `Terrain::Terrain` starts with byte width/height, a
  `CSRootImage`, four bytes, normalized color, `CSLight`, compact altitude data,
  surface slices, and water entries.
- `Terrain::loadSurface` uses a surface image table, two shorts, one int,
  then per-slice records: image ref, material id, `CSMaterial`, two floats,
  cell count, and byte x/y cell pairs.
- Water entries use optional asset references, float tuning fields, two
  normalized colors, flags, and byte/float water-cell instances.
- Prop placement is a two-pass structure like resource placement. Treating it as
  a single nested table shifts the subsequent `Squad[][]` parse and hides the
  trigger bytecode.

The trigger section is currently decoded only structurally as `uint8[][][]`.
That is enough to preserve the bytecode and offsets in readable JSON, but not
enough to name opcodes. Opcode semantics are in ACIES-specific native functions
such as `Map::mtMission`, `Map::mtEvent`, `Map::mtPlayer`, `Map::mtReadUnits`,
`Map::mtReadSquads`, and the other `Map::mt*` helpers.

## Notes For Future Sessions

## 2026-04-29 Continuation Status

Completed:

- All 34 `maps/map*.xmf` files batch-parse with `remaining=0`.
  Output directory: `decrypts/maps-all/`.
- `strings.xmf` is now fully parsed as `CSArray<CSLocaleString, 2>`, not the
  old partial `u16` table guess.
  Outputs:
  - `decrypts/strings.xmf.json`
  - `decrypts/strings.xmf.csv`
- `animations.xmf` has a dedicated old-CDK structural decoder:
  `tools/decode_cdk_animation.py`.
  Outputs:
  - `decrypts/animations.xmf.json`
  - `decrypts/animations.xmf.summary.json`

Map correction:

- `UserThumb` in the map parser must read `int64 id` before the name. The native
  constructor order is `readLong()`, then locale/string name, then short and
  asset refs. Fixing this made the previously failing
  `maps/map[003][000][001].xmf` parse cleanly.

`strings.xmf` evidence:

```text
Asset::loadStrings()
  CSBuffer::readLength()                  outer count
  repeat outer:
    CSBuffer::readLength()                group count
    repeat group:
      CSLocaleString::CSLocaleString(...)
```

Current parsed result:

```text
outer groups: 34 / 34
localized strings: 1203 / 1203
remaining: 0
locales: ar, en, es, fa, ko, pt, ru, th, zh-Hans, zh-Hant
```

`animations.xmf` evidence:

`Asset::loadAnimations()` reads `CSArray<CSAnimation, 3, true>`. The APK binary
does not match the newer open-source CDK3 `CSAnimationFragment` layout. It uses
an older flat `CSAnimation::CSAnimation(CSBuffer*)` with `CSMovement`,
`CSAnimationLoop`, `CSAnimationSubstance`, and `CSAnimationDerivation`.

Important old-layout differences:

- `CSMovementLinear(CSBuffer*)` is `type byte + 4 floats`; there is no trailing
  smooth bool in this APK build.
- `CSAnimationDerivation(CSBuffer*)` reads only a child animation count and
  inline `CSAnimation` children. There is no base `finish` bool.
- `CSAnimationDerivationLinked` reads an `int32` loop count.
- `CSAnimationDerivationEmission` reads `float delay`, `int32 capacity`,
  `bool prewarm`.

Current animation parse result:

```text
recursive animations parsed: 15740
remaining after first isolated failure: 1598490
substance counts: sprite=8053, particle=4453, trail=205, none=3029
derivation counts: multi=5298, linked=170, random=16, emission=44, none=10212
first failure path: 3/8/0
first failure offset: 8472454
reason: unknown CSMovement type 34
```

So `animations.xmf` is no longer opaque, but it is not a complete parse yet.
The next fix should focus on the branch around offset `0x8148c6` / decimal
`8472454`, probably a remaining old animation/substance field mismatch.

`data/menu.xmf` status:

`data/menu.xmf` decrypts correctly:

```text
decoded: 1643032 bytes
layers: aes256-cbc key=f622bb1d3858d55c18e2198fd3643d60, xor32=ok 71d5f246
```

`Asset::loadMenu()` gives the section order. This is a large ACIES-specific
database, not a generic CDK table. The major load order starts:

```text
DivisionData[]
UserLevelData[]
CardLevelData[]
RuneLevelData[]
RuneTierData[]
ThemeData[][]
AssetIndex3
AssetIndex2[]
UserDecorationData[][]
ClanDecorationData[][]
PriceData
ProductData[][]
BoxData[][]
RandomData[][]
BoosterData[][]
EmoticonData[][]
CountryData[]
AssetIndex4[][]
CampaignData[]
byte
ChallengeData[][]
SubscriptionData[][]
QuestData[][]
AchievementData[][]
MarketAchievementData[]
conditional score reward block
LevelQuestData[]
MinigameQuestData[]
MinigameAttendanceData[]
MinigameRouletteData[]
RewardGradeData
ClanData
short, byte, byte, int
TutorialData
AssetIndex3[]
NotificationData[][]
HotTimeEventData[]
GuideTipData[]
AssetIndex3[]
ClanArenaInfoData[]
GameTipData[]
MasteryReward[]
CommunityLinkData[]
AssetIndex3
AssetIndex3[]
```

Trigger bytecode:

The map trigger bytecode is still only structurally preserved as `uint8[][][]`.
The next semantic pass should start from `Map::mtEvent`, `Map::mtMission`, and
`Map::mtPlayer`, then name opcodes by following their calls into helpers like
`Map::mtReadUnits`, `Map::mtReadSquads`, `Map::mtReadResources`,
`Map::mtReadAssetIndex2`, and `Map::mtReadLocaleString`.

Do not restart from raw APK analysis. The important established facts are:

- CDK3 is the matching engine family.
- The decrypt key is `SHA1("brtc" + asset_relative_path)[:32]`.
- AES key and IV are ASCII bytes, not binary SHA1 bytes.
- Encrypted payloads have a trailing XOR checksum.
- Many `.xmf` files are gzip-only and do not need AES.
- `version.xmf` is now parsed completely.
- `strings.xmf` is fully parsed.
- `animations.xmf` has a large best-effort old-CDK parse, with one known
  remaining alignment failure.
- `data/menu.xmf` has a known native section order but no record-level decoder
  yet.
- Full game/map parsing requires following `CSBuffer` constructor/read functions
  in `libcdkapp.so`.
