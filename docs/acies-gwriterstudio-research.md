# ACIES audio: GWriterStudio catalogue investigation

Investigated 2026-10-14. This is a source-identification report, not evidence of a purchase or licence transaction.

## Finding

Four game music files carry `GWriterStudio` in their embedded artist metadata, according to the local APK audio inventory. Their original song titles remain unresolved. None of the public recordings compared below produced a verified waveform match. Duration coincidences were tested and rejected; they should not be presented as identified songs.

| APK asset | Duration (seconds) | Attribution evidence |
| --- | ---: | --- |
| `sound[001][000][007].ogg` | 137.142857 | Embedded artist tag |
| `sound[001][000][008].ogg` | 84.480000 | Embedded artist tag |
| `sound[002][000][010].ogg` | 125.217392 | Embedded artist tag |
| `sound[002][000][012].ogg` | 79.398503 | Embedded artist tag |

The files are stereo, 44.1 kHz. They are in `decrypts/audio/music/`. Tags support an attribution, but do not establish how the developer obtained the music. For example, the artist's [Battle Music Album - 060418](https://marketplace.unity.com/packages/audio/music/battle-music-album-060418-120345) is offered free, so “bought” is not a safe conclusion simply from the author's name.

## Official places to find the original music

- [Artist YouTube channel](https://www.youtube.com/channel/UCATvWzS7U7C-mb9FVPY5Enw): album previews, some individual songs, and download/store links in video descriptions.
- [Artist's public MP3 folder](https://drive.google.com/drive/folders/14Xkqqw83FQNW8AYFgwge9U_jUuru3fMu): linked in the description of the artist's [Music for Videos/Games introduction](https://www.youtube.com/watch?v=pFlQ3EK_hIU). Contains public album folders from approximately late 2019 onward. The description offers these MP3s for noncommercial use and directs commercial users to purchase/support the artist.
- [Artist Bandcamp](https://gwriterstudio.bandcamp.com/music): early albums, individual track names, durations, streaming previews, and download offerings.
- [Artist SoundCloud](https://soundcloud.com/gwriterstudio): 80 public earlier tracks were returned by the site's public catalogue. The profile itself says to follow YouTube instead because SoundCloud is out of space.
- [Unity publisher catalogue](https://assetstore.unity.com/publishers/27610): downloadable asset packs, including original WAV products.
- [Fab publisher catalogue](https://www.fab.com/sellers/GWriterStudio): Unreal versions of the music packs, with lists of songs and official preview links.
- [Artist Patreon](https://www.patreon.com/gwriterstudio): the artist says support gives access to all their music in the [official introduction](https://www.youtube.com/watch?v=pFlQ3EK_hIU).

The public MP3 folder is a particularly useful source for comparing exact recordings, whereas store listings help establish names and packs. A store album may have a different revision/total duration than an older preview, so a pack title or matching duration alone is insufficient.

## Comparisons performed in this research branch

The comparison sources were public previews/downloads served by the artist's own accounts. No purchases, account authentication, or contact with the artist were performed. Reference audio remained in the chat's `work/gwriter/` scratch directory; it was not added to the repository or redistributed.

1. Indexed 100 Bandcamp tracks from 10 early albums with exact public catalogue duration metadata. The main research agent tested close-duration candidates and performed broader audio screening.
2. Indexed 40 album descriptions from the official YouTube channel, including chapters and public Google Drive download links.
3. Indexed 25 linked Google Drive folders containing 250 files. Some are free WAV albums; others are the artist's offered MP3 references. The main research agent performed the broader cross-catalogue scan.
4. Compared 26 additional close-duration Google Drive references against all 25 extracted game music/cue files. No exact recording matched.
5. Compared all 25 game files against the full official album preview for [RPG Music Album - 010719](https://www.youtube.com/watch?v=PKcFdmwZ-_c), allowing arbitrary starting offsets. No exact match. The attractive chapter-duration candidates `Ytris Village` (~84 seconds) and `Outside` (~125 seconds) were not confirmed. Their names are listed on the [official Fab product](https://www.fab.com/listings/d9b256c5-b671-4d06-88aa-84cdedc16b9d).
6. Compared all 25 game files against seven further full artist album previews, allowing arbitrary starting offsets:
   - [Battle Music Album - 091018](https://www.youtube.com/watch?v=gBRdxwx6Dac)
   - [Dark RPG Music Album - 102918](https://www.youtube.com/watch?v=lRnaKd9jBRQ)
   - [Fantasy Music Album - 111218](https://www.youtube.com/watch?v=aFuLPuGeFos)
   - [Magical Music Album - 090418](https://www.youtube.com/watch?v=jJ7hMHOhVFk)
   - [Boss Music Album - 121018](https://www.youtube.com/watch?v=OmakbKDrVtM)
   - [Magical Music Album - 011219](https://www.youtube.com/watch?v=a0mMxRRDb5I) (the [store product](https://assetstore.unity.com/packages/audio/music/magical-music-album-012119-137919) uses `012119`)
   - [Fantasy Music Album - 050619](https://www.youtube.com/watch?v=FNLICTFMvms)
7. Indexed the 80-track public SoundCloud catalogue and screened 43 references whose exact titles were not present in the Bandcamp index, including RPG Music Album - 011518 tracks and earlier 2017 material. The two remaining HLS-only references were checked separately.

Full-album and SoundCloud comparisons used 20–30 seconds of the game recording against arbitrary valid positions in each public reference, with mono PCM at 2 or 4 kHz. Peak selection was normalized by the energy of each aligned reference window and the game segment, rather than total album energy. The highest full-album Pearson correlation was approximately 0.207; the 43-track SoundCloud scan reached approximately 0.170. These are not strong evidence of the same exported recording. The main agent's positive control—an extracted game Ogg transcoded to MP3—reached approximately 0.998.

## Rejected duration-only leads

- [Fallen Knights](https://gwriterstudio.bandcamp.com/track/6-fallen-knights) is 137.152 seconds, nearly the same length as `sound[001][000][007].ogg`. Direct waveform comparison rejected this candidate.
- `Yinyao Ground`, from [Epic Asian Music - 061421](https://www.youtube.com/watch?v=1nxBnQmuFHo), is approximately 137.146 seconds. Direct comparison rejected it.
- `Mossy Rainforest`, from [Tropical Music - 072522](https://www.youtube.com/watch?v=4QLcW5c8YGg), and `Black Blossom`, from [Dark Asian Music - 011722](https://www.youtube.com/watch?v=E7Q0os9rHis), also have almost identical lengths to the 137.143-second game asset. Both failed direct comparison.
- `Hill Wind`, from [Horror Ambient Album - 060319](https://www.youtube.com/watch?v=JLHGiYmqedA), is approximately 84.471 seconds, near the 84.480-second game track. It failed direct comparison.

This illustrates why a common tempo/bar count can create close duration coincidences without identifying a song.

## Remaining uncertainty

The artist credit in four game assets is the strongest direct attribution evidence. The public catalogue investigation has not recovered their exact titles or source packs. Remaining possibilities include catalogue revisions, retired/unlisted material, or edited exports; these are hypotheses, not findings. None of these comparisons establishes that the remaining uncredited ACIES music was or was not sourced from GWriterStudio.

The next decisive evidence would be the original licensed asset-package revision used by the developer, a credits/build manifest naming song filenames, or confirmation from the creator after hearing these four assets. Contact would require a separate explicit user request.
