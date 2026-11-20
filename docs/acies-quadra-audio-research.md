# QUADRA in ACIES 2.5.1 audio

**QUADRA’s identity is unresolved.** The name appears in engineer fields on 40 of 654 Ogg Vorbis assets. The tags support an audio-engineering association with those files. The person or studio behind the label, its relationship to the developer, and the composers of the two tagged music tracks remain unverified. [Audio manifest](../decrypts/audio/manifest.json) · [Audio provenance notes](acies-audio-provenance.md)

## APK evidence

The manifest’s APK SHA-256 matches the local `acies.apk`. Android SDK `aapt` identifies version `2.5.1`, package `com.creagames.clashoflegions`, and activity `kr.co.brgames.talescraft2.MainActivity`. All 654 audio entries were checked directly against the APK using SHA-256 and `ffprobe` for codec and stream tags. `QUADRA` appears as `ENGINEER` on 27 files and as `IENG` on 13 other files. The 40 files comprise two music assets and 38 shorter sounds. Their metadata dates span June 18, 2020 through January 6, 2023. [Audio manifest](../decrypts/audio/manifest.json)

| APK asset | File metadata |
|---|---|
| `sound[000][000][000].ogg` | Title theme (`SoundBgmTitle`), 98.924 s. `ENGINEER=QUADRA` and `DATE=2023-01-06`. |
| `sound[002][000][005].ogg` | Battle music 6, 95.989 s. `ENGINEER=QUADRA` and `DATE=2020-06-18`. |
| `sound[001][002][022].ogg` and `sound[001][002][030].ogg` | Short sounds with `IENG=QUADRA`, SOUND FORGE Pro 13.0 coding history and `Lavc58.91.100 libvorbis`. Their `encoded_by` values are `Pro Tools` and `Logic Pro X`, respectively. |

Both music files contain only `DATE` and `ENGINEER` metadata. The earlier local provenance investigation also found no additional QUADRA credit string in its scan of APK strings and decoded menu data. [Audio provenance notes](acies-audio-provenance.md)

## First-party credit and portfolio leads

- **ACIES / 아키에스: 배틀룬스.** Saint Joy Korea’s company profile lists the game, and the Korean launch notice records its October 2021 storefront dates. The profile and the launch, global update and shutdown notices name no audio contributors. [Saint Joy Korea profile](https://www.gamejob.co.kr/Company/Detail?M=35298423) · [Launch notice](https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/30555050/articles/110) · [Global update notice](https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/30555050/articles/111) · [Shutdown notice](https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/30555050/articles/5293)
- **Tales Arena / 테일즈 아레나 and Tales Craft / 테일즈크래프트.** BR Games’ company profile lists both titles and dates the Tales Arena Play Store launch to June 2018. Hot Head’s indexed portfolio entry names BR Games as the Tales Arena licensor. An indexed excerpt of BR Games’ Tales Craft launch announcement names Oh Hyun-min (오현민) among SBS participants who helped develop the game. SBS published an episode about the project. These sources leave his specific role and any relationship to the QUADRA tags unverified. [BR Games profile](https://www.gamejob.co.kr/Company/Detail?M=12930410) · [Hot Head portfolio](https://hothead.co.th/) · [BR Games announcement via Inven](https://www.inven.co.kr/webzine/news/?news=177989&site=mobilegame) · [SBS episode](https://programs.sbs.co.kr/programTemplate/amp/vod/gameshow/22000225147)
- **Clash of Legions (mobile).** The official mobile RTS YouTube channel yielded no audio attribution in its indexed material. The Steam listing for the same title describes a GX company card game. [Official mobile channel](https://www.youtube.com/channel/UC-_RkhZEUrNkJ4Wm6GQkm1w) · [GX company’s Steam listing](https://store.steampowered.com/app/1694290/Clash_of_Legions/)
- **Audio vendors.** Searches combined the title variants and studio names with `QUADRA`, `쿼드라`, `콰드라`, `사운드 제작`, `효과음`, `작곡`, `BGM`, and English credit and portfolio terms. The public portfolio text checked for Studio EIM, AO Music, RAMMSOUND, and Hexany Audio yielded no matching credit. The sources reviewed establish no ACIES relationship for any QUADRA namesake. [Studio EIM](https://www.eim.kr/) · [AO Music](https://www.aomusic.co.kr/portfolio_game.php) · [RAMMSOUND](https://www.rammsound.kr/en/portfolio/) · [Hexany Audio](https://hexanyaudio.com/portfolio/)
- **Hiroshi Watanabe.** The musician’s own album credits identify QUADRA as his recording alias. Searches under both names and the game’s title variants did not surface an ACIES credit. [Artist’s Bandcamp release](https://hiroshiwatanabe.bandcamp.com/album/quadra-complete-selection-95-07-single-collection-2016-remaster)

## Software named in the tags

Counts are for the entire manifest, with QUADRA overlap in parentheses. The co-occurring fields are consistent with metadata carried across audio production and encoding stages. The sequence of tools, operator and exact build remain unknown. [Audio manifest](../decrypts/audio/manifest.json)

| Software | APK metadata | Official reference |
|---|---|---|
| Avid Pro Tools | `encoded_by=Pro Tools` on 4 files (2). | Avid’s recording, editing and mixing software for audio post-production. [Avid](https://www.avid.com/pro-tools/features/audio-post) |
| Apple Logic Pro X | `encoded_by=Logic Pro X` on 14 files (3). | Apple’s music production software under the exact name used in the files. [Apple launch announcement](https://www.apple.com/newsroom/2013/07/16Apple-Unveils-Logic-Pro-X/) |
| MAGIX SOUND FORGE Pro 13 | `coding_history` names `SOUND FORGE Pro 13.0` on 31 files (5). Two of the 31 also mention `Sound Forge Pro 11.0`. | MAGIX announced version 13 of its recording, editing and mastering software in April 2019. [MAGIX release announcement](https://www.magix.com/au/press/detail/news/magix-releases-sound-forge-pro-13-more-stable-more-efficient-more-speed-1/) |
| Cockos REAPER | `encoded_by=REAPER` on 73 files (0). | Cockos’s digital audio workstation. [REAPER product information](https://www.reaper.fm/about.php) · [User guide](https://www.reaper.fm/userguide.php) |
| FFmpeg `libvorbis` | `encoder=Lavc58.91.100 libvorbis` on 182 files (12), and `Lavc57.64.101 libvorbis` on 1 file (1). | FFmpeg documents `libvorbis` as an encoder wrapper. The `Lavc` numbers match libavcodec identifiers in the FFmpeg 4.3 and 3.2.1 source tags, respectively. [FFmpeg codec documentation](https://ffmpeg.org/ffmpeg-codecs.html#libvorbis) · [4.3 source](https://github.com/FFmpeg/FFmpeg/blob/n4.3/libavcodec/version.h#L28-L38) · [3.2.1 source](https://github.com/FFmpeg/FFmpeg/blob/n3.2.1/libavcodec/version.h#L28-L38) |

The same five QUADRA-tagged effects that name Pro Tools or Logic Pro X also name SOUND FORGE Pro 13.0 in their coding history and carry the newer `Lavc58.91.100 libvorbis` encoder tag. FFmpeg’s WAV reader maps the Broadcast Wave Format’s `Originator` field to `encoded_by`. In a local test with synthetic silence, FFmpeg copied both a test `IENG` value and the WAV’s `Originator` value into the resulting Ogg’s tags. This behavior explains how editing and export metadata can survive a later encoding step. [Audio manifest](../decrypts/audio/manifest.json) · [EBU Broadcast Wave specification](https://tech.ebu.ch/docs/tech/tech3285.pdf) · [FFmpeg WAV reader](https://ffmpeg.org/doxygen/4.3/wavdec_8c_source.html#l00320)
