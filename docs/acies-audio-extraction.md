# ACIES 2.5.1 audio extraction

The local source is `acies.apk`, copied from Downloads' `acies-battle-runes-2-5-1.apk`.
Extraction reads the APK as a ZIP; audio does not require XMF decryption.

```bash
python3 tools/extract_acies_audio.py acies.apk
```

Requires Python 3 and `ffprobe` (provided by `brew install ffmpeg`). Use a new,
empty `--out-dir` when repeating the extraction.

Generated files, ignored by Git:

- `decrypts/audio/all/`: all 654 original Ogg Vorbis assets, unchanged.
- `decrypts/audio/music/`: 24 long music candidates and one short BGM cue.
- `decrypts/audio/music/acies-music.m3u`: relative playlist.
- `decrypts/audio/catalog.csv`: durations, formats, source paths and SHA-256 hashes.
- `decrypts/audio/manifest.json`: full catalog including embedded credits and APK hash.

The other 629 assets are short sounds. The selection includes every audio file
lasting at least 20 seconds plus the seven-second box background cue. Most
assets have numeric IDs rather than song titles; retain them instead of
inventing track names. Apart from the two native mappings below, music
classification is inferred from duration and asset grouping. All audio is
preserved in `all/` so this inference cannot discard a song.

## Native evidence

In the APK's `lib/arm64-v8a/libcdkapp.so`, dynamic relocations map GOT addresses
`0x8dd5e8` and `0x8dd5f0` to `SoundBgmTitle` and `SoundBgmBoxBackground`.
Initializer instructions at `0x5441f0`–`0x54421c` construct these `AssetIndex3`
values as `(0, 0, 0)` and `(1, 0, 5)` respectively:

- `sound[000][000][000].ogg`: title theme, 98.924 seconds.
- `sound[001][000][005].ogg`: box background cue, 7.040 seconds.

The music-group files are `(0,0,0)`, `(1,0,0..10)`, and `(2,0,0..12)`.
Four tracks retain GWriterStudio credits and two retain QUADRA engineer tags.
The tags are recorded verbatim in the manifest.

## In-game labels in Acies Atlas

The client identifies usage for 20 music entries. These labels describe where
the clips play. Original composition titles remain unverified.

- `Asset::loadMenu()` stores its final `AssetIndex3[]` at Asset offset `0x220`
  (`0x52fbb0`–`0x52fbc8`). `LobbyLayer::playBgm()` reads that field and
  chooses a track at random. The decoded array starts at menu offset
  `0x1911f9` and contains `(1,0,0)` through `(1,0,4)`.
- `Map::mtSound()` at `0x57f50c` handles map opcode 41. Mode 0
  chooses from a length-prefixed `AssetIndex3[]` and reads a float volume.
  This links all 13 `(2,0,n)` tracks to their in-game maps. Mode 2 uses
  the same operand shape for one-shot sound effects.
- AArch64 relocations for `SoundFx*` at `0x8dd5f8`–`0x8dd678` and the
  corresponding initializer at `0x544220`–`0x5443b4` identify 17
  interface effects, including Button click, Tab switch and Match start.
- The game database's `SkinData` voice tables map 393 clips to units and
  skins. The four voice arrays are indexed in order by the native calls
  for arrival or creation (slot 0), selection (slot 1), commands (slot 2),
  and exit or interruption (slot 3). For example, see
  `Unit::updateProducing()` at `0x5c24b0`, `Map::select()` at `0x587544`,
  `Map::click()` at `0x58d240`, and `Unit::destroy()` at `0x5ba740`.
  A clip may be used in multiple slots or by multiple skins.
- `AnnounceData::voice()` appends the announcement index to the
  locale-specific two-part asset index at `0x548014`. The packaged data
  contains two Korean banks with 15 clips each. Individual event names are
  unresolved.

Verification: ZIP CRC checks during extraction, ffprobe validation of all 654
files, SHA-256 comparison against their APK entries, and full ffmpeg decoding
of the 25 selected music/cue files. Keep the APK and extracted assets local.
