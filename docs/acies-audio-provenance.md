# ACIES audio provenance investigation

Investigated 2026-10-14. Source: local ACIES 2.5.1 APK and its 654 extracted Ogg Vorbis assets.

## What the files actually establish

Four music assets contain `ARTIST=GWriterStudio`, `ENGINEER=GWriterStudio`, and `ALBUM=https://soundcloud.com/gwriterstudio`. None contains an original song-title tag. These are embedded attribution evidence, not a receipt or proof of the specific purchase/license.

| APK asset | Duration | Embedded attribution | Original title |
|---|---:|---|---|
| `sound[000][000][000].ogg` | 98.924s | QUADRA (engineer only) | Unresolved |
| `sound[001][000][007].ogg` | 137.143s | GWriterStudio (artist and engineer) | Unresolved |
| `sound[001][000][008].ogg` | 84.480s | GWriterStudio (artist and engineer) | Unresolved |
| `sound[002][000][005].ogg` | 95.989s | QUADRA (engineer only) | Unresolved |
| `sound[002][000][010].ogg` | 125.217s | GWriterStudio (artist and engineer) | Unresolved |
| `sound[002][000][012].ogg` | 79.399s | GWriterStudio (artist and engineer) | Unresolved |

The other 19 music/cue candidates have no artist, album, engineer, or title tags. QUADRA appears in 40 total audio assets (27 ENGINEER fields and 13 IENG fields), of which two are music. That prevalence is consistent with a shared audio-editing/export workflow; it does not identify a composer or establish that the music was commissioned or purchased.

Scanning the APK strings and decoded menu data found no additional GWriterStudio/QUADRA credit strings.

One short sound effect (`sound[002][002][013].ogg`) carries the title `Rise of Nations Lumber Mill Sound`. This is a metadata clue about an effect, not a music identification or proof of where it came from.

## Official catalog entry points

- [GWriterStudio public MP3 collection](https://drive.google.com/drive/folders/14Xkqqw83FQNW8AYFgwge9U_jUuru3fMu): named album folders and artist-provided samples, linked by the artist’s [YouTube page](https://www.youtube.com/watch?v=pFlQ3EK_hIU).
- [GWriterStudio YouTube channel](https://www.youtube.com/channel/UCATvWzS7U7C-mb9FVPY5Enw): full album previews and chaptered track names.
- [GWriterStudio Unity catalog](https://assetstore.unity.com/publishers/27610): original WAV packs and product track lists.
- [GWriterStudio Bandcamp](https://gwriterstudio.bandcamp.com/music): early 2018 albums with named track previews.
- [Artist’s portfolio and contact](https://gwriterstudio.artstation.com/projects/q9EAK2): composer profile, catalog links and gwriterstudio@gmail.com. No message was sent.

Some packs are available free in the artist’s own storefront. For example, [Battle Music Album - 060418](https://marketplace.unity.com/packages/audio/music/battle-music-album-060418-120345) is listed free. Therefore, the presence of GWriterStudio credit cannot establish that ACIES paid for that song. This pack has not been confirmed as the source of an ACIES music track.

## Audio matching outcome

No original song title or additional music-provider attribution was verified in this investigation. This is an unresolved result, not proof that an original recording is absent from the catalogue.

The comparison covered:

- 100 early Bandcamp previews screened against all 25 game music/cue assets, with direct waveform checks of close-duration candidates.
- 190 artist-provided MP3 samples from the public Drive folders, screened against the 24 longer game tracks regardless of total duration. Thirty-second multiband spectral screening nominated 72 candidates; their PCM correlations were all below 0.062. References with large embedded artwork were refreshed to ensure at least 20 seconds of actual audio were compared. The seven-second box cue was excluded from this broad spectral pass and remains present in the other direct comparisons.
- Eight older full album previews, checked at arbitrary offsets with aligned-window energy normalization, plus 45 additional early SoundCloud references.
- Additional close-duration references and their individual full-waveform checks.

An extracted Ogg transcoded to MP3 as a positive control produced 0.99847 waveform correlation. Similar durations alone were not accepted as identification; the almost equal-length Fallen Knights, Blakkrheimr and Yinyao Ground recordings did not match.

The research source indexes, reference samples and intermediate results remain in the chat workspace under `work/gwriter/`, `work/gwriter-comparison/` and `work/gwriter-drive-spectral/`. They are not committed or redistributed. Detailed catalog source citations and the older-preview comparisons are in `docs/acies-gwriterstudio-research.md`.

Exact source names still need a matching original pack revision, a developer build/credits manifest, or creator confirmation. No artist contact or purchase was performed.
