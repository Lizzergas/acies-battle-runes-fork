# ACIES Local Mock Backend

Date: 2026-04-29

This document records the local backend-capture and mock-login work for ACIES.
The original production hostname used by the APK is no longer reachable, so the
current goal is to run the client against a local preservation/debug server and
map the minimum response shapes expected by the native game code.

All paths below are relative to:

```text
/Users/p997eyc/projects/boot/acies-disassemble
```

## Current Pieces

The mock server is:

```text
tools/acies_mock_server.py
```

The currently patched APK is:

```text
acies_localmock.apk
```

The patch redirects requests for the original live backend host to the Android
emulator host loopback:

```text
http://10.0.2.2:8080
```

Important patched smali locations:

```text
acies-apktool/smali/kr/co/brgames/cdk/CSURLRequest.smali
```

The runtime log line that confirms the redirect is active is:

```text
CSURLRequest I ACIES local mock redirect: http://10.0.2.2:8080/...
```

## Why This Exists

The APK attempts to contact:

```text
live.saintjoy.co.kr
```

The observed DNS failure was:

```text
Unable to resolve host "live.saintjoy.co.kr": No address associated with hostname
```

Returning arbitrary HTTP 200 JSON is not enough. The native client parses the
body into CDK `CSJSONObject` / `CSJSONArray` objects and then constructs a large
set of C++ model objects. Missing keys, wrong types, or too-short arrays can
crash inside `libcdkapp.so`.

The current approach is therefore:

1. Capture each request body and headers.
2. Return controlled JSON.
3. If the app crashes, use the native stack offset to identify the constructor
   and exact key/type that failed.
4. Patch the local mock payload.
5. Repeat until the client advances to the next backend dependency.

This is a local offline compatibility backend. It is not a real account service
and it does not contact the original servers.

## Running The Mock Server

Default capture/error mode:

```sh
cd /Users/p997eyc/projects/boot/acies-disassemble
python3 tools/acies_mock_server.py --port 8080 --status 200
```

Guest-success experiment mode:

```sh
cd /Users/p997eyc/projects/boot/acies-disassemble
python3 tools/acies_mock_server.py --port 8080 --status 200 --guest-success
```

Guest-success mode with staged campaign tutorial progress:

```sh
cd /Users/p997eyc/projects/boot/acies-disassemble
python3 tools/acies_mock_server.py --port 8080 --status 200 --guest-success --tutorial-stages
```

`--tutorial-stages` resets campaign progress on each synthetic login and then
advances it from `/api/client-secure/game/result` or
`/api/client-secure/game/campaign-step`. It defaults to three mandatory stages.
Use `--tutorial-stage-count N` if later captures show a different count.

The important startup line is:

```text
Guest success mode: True
```

If it says `False`, `/api/client/login` intentionally returns a handled app
error:

```text
Local capture backend does not implement guest login.
```

After restarting the mock, force-stop and relaunch the app:

```sh
adb shell am force-stop com.creagames.clashoflegions
adb shell am start -n com.creagames.clashoflegions/kr.co.brgames.talescraft2.MainActivity
```

## Captures

The mock writes request metadata and bodies under:

```text
captures/acies_mock/
```

For every request, it writes:

```text
<timestamp>_<METHOD>_<path>.json
<timestamp>_<METHOD>_<path>.body
```

The `.json` file contains metadata and headers. The `.body` file contains the
raw request body.

For encrypted `/api/client-secure/...` requests, the mock also writes a
decrypted request body when OpenSSL can decode it:

```text
<timestamp>_<METHOD>_<path>.decrypted
```

Observed request bodies:

```json
{
  "secret": "a034fde6-5b14-414d-bdee-eb330a1a0bed",
  "version": "2.5.1.338",
  "language": "en",
  "region": "US",
  "market": 1
}
```

```json
{
  "secret": "bf080f87-6e5f-4aa1-b94e-ba6cd405fac0",
  "version": "2.5.1.338",
  "assetVersion": 0,
  "language": "en",
  "region": "US",
  "market": 1
}
```

## Endpoint Status

Known initial endpoints:

```text
POST /api/client/admission
POST /api/client/login
```

Current behavior:

- `/api/client/admission` returns a minimal success payload with
  `assetVersion: 177` and `revision: 83`.
- `/api/client/login` returns a handled app-level error unless
  `--guest-success` is enabled.
- With `--guest-success`, `/api/client/login` returns a synthetic `result: 0`
  response with a local account payload.
- `/api/client-secure/push-token` returns encrypted `{"result":0}`.
- `/api/client-secure/game/result` returns an encrypted minimal reward result
  for completed tutorial/offline games.
- `/api/client-secure/game/campaign-step` and
  `/api/client-secure/tutorial/step` return minimal progress responses for
  tutorial skip/progress calls.
- The current post-login lobby burst is now handled with minimal encrypted
  payloads:

```text
/api/client-secure/pvp-server
/api/client-secure/ping
/api/client-secure/quest/status
/api/client-secure/shop/card-info
/api/client-secure/shop/info
/api/client-secure/season-result
/api/client-secure/challenge-reset
/api/client-secure/game/prev-result
/api/client-secure/refresh
/api/client-secure/profile/stat
/api/client-secure/match-record/list
/api/client-secure/match-record/lock
```

More endpoints are expected after login succeeds, probably under:

```text
/api/client-secure/...
```

Those secure endpoint responses must be AES-CBC encrypted at the CDK transport
layer. The mock uses the current session `encryption` key and its first 16 bytes
as the IV.

Relevant extracted endpoint list:

```text
docs/acies-api-endpoints.md
```

Current admission success shape:

```json
{
  "result": 0,
  "assetVersion": 177,
  "iosReview": false,
  "patchHosts": [],
  "downloadUrl": "",
  "host": "http://10.0.2.2:8080",
  "notices": [],
  "inviteUrl": "",
  "revision": 83
}
```

The names are misleading. From native disassembly, `assetVersion` is the patch
manifest revision used by `TitleLayer::doPatchVersion()`, while `revision` is
copied into `LobbyGateway + 52` and later passed to `Asset::loadGame(int)`.
`Asset::loadGame(int)` rejects versions below `71`, and the APK contains
`data/game[071].xmf` through `data/game[083].xmf`. The decoded `version.xmf`
manifest has revision `177`, while the newest packaged game data is
`data/game[083].xmf`, so the local admission response currently advertises
`assetVersion: 177` and `revision: 83`.

Validation note: the client showed `Code : 10006` / "Failed to load data" when
these values were swapped. Setting `assetVersion` to `177` and `revision` to
`83` fixed that path and allowed the client to enter the game.

## Login Response Mapping

The login success path was mapped from `libcdkapp.so` symbols and stack traces.

Important native symbols:

```text
LobbyGateway::receiveLogin(CSJSONObject const*)      0x051adb8
Account::load(CSJSONObject const*)                   0x05fa8e0
Account::Account(CSJSONObject const*)                0x05f8490
Session::Session(CSJSONObject const*)                0x0505428
Profile::Profile(CSJSONObject const*)                0x060146c
Player::Player(CSJSONObject const*)                  0x0600de4
User::User(CSJSONObject const*)                      0x06020b4
UserThumb::UserThumb(CSJSONObject const*)            0x0602748
UserRecord::UserRecord(CSJSONObject const*, type)    0x06023f4
SeasonReward::SeasonReward(CSJSONObject const*)      0x05ea250
```

`LobbyGateway::receiveLogin` expects:

```json
{
  "result": 0,
  "account": {},
  "secret": "...",
  "dayChanged": false
}
```

It passes `account` to `Account::load(...)` and passes the root login object to
`Session::Session(...)`.

`Session::Session` currently requires:

```text
account.userId
secret
```

and optionally reads:

```text
encryption
```

In practice, `encryption` should not be an empty string. The Android bridge
uses it as an AES key via `CSCrypto.encrypt(...)` / `CSCrypto.decrypt(...)`;
CDK accepts 16- or 32-byte ASCII keys. The current synthetic session key is:

```text
localmockkey0001
```

## Current Synthetic Account Shape

The mock currently emits this class of account payload:

```json
{
  "userId": 1000001,
  "name": "LocalGuest",
  "country": 0,
  "decorations": [0, 0, 0, 0],
  "pictureUrl": "",
  "level": 1,
  "recordPrivate": {
    "score": 0,
    "scoreHigh": 0,
    "ranking": 0,
    "division": 0,
    "divisionHigh": 0
  },
  "recordTeam": {
    "score": 0,
    "scoreHigh": 0,
    "ranking": 0,
    "division": 0,
    "divisionHigh": 0
  },
  "description": "",
  "achievementPoint": 0,
  "cards": [196608, 196609, 196610, 196613, 196617, 196618, 262144, 327682],
  "runes": [[-1, -1, -1, -1], [-1, -1, -1, -1], [-1, -1, -1, -1]],
  "cardCounts": [20, 20, 20, 20, 20, 20, 20, 20],
  "allCards": [
    {
      "cardId": 196608,
      "level": 0,
      "skin": 0,
      "count": 20,
      "masteryLevel": 0,
      "masteryPoint": 0,
      "masteryRewardPoint": 0,
      "isNew": false
    }
  ],
  "deckTheme": 0,
  "deckPage": 0,
  "deckPageCount": 1,
  "decks": [
    {
      "name": "Local Deck",
      "cards": [196608, 196609, 196610, 196613, 196617, 196618, 262144, 327682],
      "runes": [[-1, -1, -1, -1], [-1, -1, -1, -1], [-1, -1, -1, -1]]
    }
  ]
}
```

The full payload is in:

```text
tools/acies_mock_server.py
```

Notable type fixes made so far:

- `material` must be an array with at least 3 numbers.
- `mileage` must be an array with at least 2 numbers.
- `seasonReward.divisionRewards` must be an array with at least 2 arrays.
- `encryption` must be a non-empty 16- or 32-byte AES key.
- `/api/client-secure/*` responses must be AES-CBC encrypted with PKCS padding.
- `cardId` is a packed `AssetIndex2` integer, encoded as `group << 16 | index`.
- `Deck::Deck(CSJSONObject const*)` requires exactly 8 `cards` entries and 3
  `runes` rows with 4 entries each.

Current `seasonReward` shape:

```json
{
  "userRankingRewards": [],
  "clanRankingRewards": [],
  "divisionRewards": [
    [[], [], "... 31 empty arrays total"],
    [[], [], "... 31 empty arrays total"]
  ]
}
```

`SeasonReward::~SeasonReward()` releases 31 division reward pointers for private
ranking and 31 pointers for clan/team ranking unconditionally. The constructor
only initializes as many slots as are present in `divisionRewards[0]` and
`divisionRewards[1]`, so each inner array must contain all 31 empty reward-list
arrays. A shorter shape such as `[[], []]` can parse but later crash in
`CSObject::release()` when a previous `SeasonReward` is destroyed during
`receiveSeasonResult()`.

## Crash-Guided Mapping History

First generic `result: 0` attempt crashed because `account` was missing:

```text
CSJSONObject::numberForKey()
UserThumb::UserThumb()
User::User()
Player::Player()
Profile::Profile()
Account::Account()
Account::load()
LobbyGateway::receiveLogin()
```

That showed login success requires a real `account` object.

The next crash:

```text
CSJSONArray::numberAtIndex() + 0x8
Account::Account() + 0x7a4 (0x5f8c34)
```

Mapped to `material` being read as an array. `material` was changed from `0` to:

```json
[0, 0, 0]
```

The nearby `mileage` field is also indexed as an array and was changed to:

```json
[0, 0]
```

The next crash:

```text
CSJSONArray::jsonArrayAtIndex() + 0x0
SeasonReward::SeasonReward() + 0xd4 (0x5ea324)
Account::Account() + 0x18d4 (0x5f9d64)
```

Mapped to `seasonReward.divisionRewards` being missing or the wrong type.
`divisionRewards` was changed to:

```json
[[], []]
```

After login began succeeding, the client repeatedly called:

```text
POST /api/client-secure/push-token
```

The first mock response was plaintext JSON, which caused:

```text
CSCrypto.decrypt(...)
WRONG_FINAL_BLOCK_LENGTH
```

That showed secure endpoint responses require encrypted bodies. The mock now
returns encrypted `{"result":0}` for `push-token` and logs decrypted secure
request bodies such as:

```json
{
  "token": "...",
  "enabled": true
}
```

The next observed failure was not in the login transport. The app reached the
title/offline path, then crashed while building a force:

```text
UnitBase::data() + 0x14
Force::resetCardsImpl() + 0x1f8
Force::Force()
Map::Map()
Map::loadForOfflinePlay()
GameLayer::layerForOfflinePlay()
TitleLayer::doComplete()
```

That pointed at an empty or invalid deck/card inventory. The mock now includes
a starter deck using real decoded game assets from `game[083].xmf`:

```text
3,0 Hound       -> 196608
3,1 Swordsman  -> 196609
3,2 Archer     -> 196610
3,5 Skull Rogue -> 196613
3,9 Berserker  -> 196617
3,10 Healer    -> 196618
4,0 Watch Tower -> 262144
5,2 Fireball   -> 327682
```

The Google Play sign-in prompt/error is a separate SDK flow. `ApiException: 4`
means the Google Play sign-in result failed before it reaches the local mock
backend. The current backend work should be judged by whether guest login sets
`userId` and whether the native offline path advances past deck construction.

After adding non-empty `allCards`, login crashed earlier:

```text
UnitBase::data() + 0x14
Account::Account() + 0x9d8
```

The mapped block is the `allCards` loop. It constructs `CardAccount` entries and
calls `UnitBase::data()` when the parsed card `level` field is nonzero. The
mock now sets starter `allCards[*].level` to `0` to avoid touching unit metadata
during login while keeping `count` and deck IDs present for the next mapping
step.

After the tutorial intro, the client posted:

```text
POST /api/client-secure/game/result
```

Observed decrypted request:

```json
{
  "transaction": 1777470177880,
  "result": {
    "mode": 32,
    "result": 1,
    "playTime": 37,
    "attain0": 0,
    "attain1": 0,
    "attain2": 0,
    "single": {
      "mapId": 196608,
      "mapVersion": 1,
      "mapLevel": 0,
      "campaignStage": 1
    }
  }
}
```

The generic secure fallback crashed here:

```text
CSJSONObject::jsonArrayForKey()
LobbyGateway::receiveRewardResult() + 0x6c
LobbyGateway::receiveGameResult() + 0xa0
```

Disassembly maps that required array to `rewardResult.rewards`. The mock now
echoes the request transaction in root `result` and returns:

```json
{
  "result": 1777470177880,
  "rewardResult": {
    "rewards": [],
    "campaignStages": [0, 0, 0, 1, 1, 1]
  }
}
```

`receiveRewardResult()` has many optional account-progress keys after this
point, but `rewards` is the first required shape needed to avoid the crash.

The next tutorial-loop issue was caused by campaign progress not being updated.
`Account::isPlayingCampaignTutorial()` compares the length of
`account.campaignStages` against a tutorial campaign count loaded from
`data/menu.xmf`. With an empty `campaignStages` array, the title flow keeps
starting the campaign tutorial after each successful `/game/result`. The mock
normally uses the completed campaign progress array:

```json
"campaignStages": [0, 0, 0, 1, 1, 1]
```

in the synthetic login account and inside `rewardResult` for `/game/result`.
It also returns completed `campaignStages` from
`/api/client-secure/game/campaign-step`. The tutorial step endpoint echoes
`category`, `step`, and `skip`, then returns the same minimal `rewardResult`.

For fresh-account tutorial testing, start the server with `--tutorial-stages`.
In that mode, login returns:

```json
"campaignStages": []
```

The mock then advances stage progress as tutorial campaign results arrive:

```text
after stage 1 -> [0]
after stage 2 -> [0, 0]
after stage 3 -> [0, 0, 0, 1, 1, 1]
```

The third stage intentionally switches to the completed campaign array so the
client can leave the mandatory tutorial path and enter the main lobby instead of
looping back into the first tutorial battle.

After the third campaign tutorial, the client may still start a separate lobby
tutorial overlay and call:

```text
POST /api/client-secure/tutorial/step
```

The observed request was:

```json
{"category":0,"step":1,"skip":false}
```

Returning that step literally allowed the native tutorial script to continue and
hit `Tutorial::ttError()`, showing `Code : 14000` with details like
`(0 / 1 / 0 -> 54)`. In `--tutorial-stages` mode, once the three campaign stages
are complete, the mock now answers tutorial-step calls with `step: 999` and
`skip: true` while preserving the completed `campaignStages`. This marks the
lobby overlay tutorial category complete so the client can stay in the main menu.

After reaching the home/lobby UI, the app issued a burst of secure requests and
then crashed during draw:

```text
QuestStatus::hasNew() + 0x3c
HomeLayer::onDrawEvent() + 0x44
```

The failing instruction dereferenced the `dailyRewards` array pointer inside
`QuestStatus`. `QuestStatus::QuestStatus()` only initializes `dailyRewards` and
`weeklyRewards` if those keys exist, while `QuestStatus::hasNew()` later reads
both arrays without null checks. The login account and
`/api/client-secure/quest/status` now use:

```json
{
  "dailyRewards": [],
  "weeklyRewards": [],
  "dailyRewardStep": 0,
  "weeklyRewardStep": 0,
  "dailyPoint": 0,
  "weeklyPoint": 0,
  "remainTime": 0,
  "quests": []
}
```

The arrays must be present even when empty.

The next lobby draw crash was:

```text
HomeLayer::onDrawRune() + 0xac
```

This path dereferences `account.shop`, then unconditionally reads the first
product in shop category `9`, which is the rune workshop / badge product slot.
An empty `shop.products` array parses successfully but leaves that category
without a product object. The mock now includes one inert category `9` product
in both the login account's `shop` object and `/api/client-secure/shop/info`:

```json
{
  "productId": 0,
  "category": 9,
  "priceType": 0,
  "price": 100,
  "originPrice": 100,
  "cash": 0,
  "buyCount": 1,
  "buyLimit": 1,
  "repeat": false,
  "rewards": []
}
```

`buyCount == buyLimit` makes `Product::isBuyabled()` return before it needs to
walk deeper product asset metadata, while the product still exists for the home
screen rune-workshop draw logic.

Another success-flow crash happened inside:

```text
CSJSONObject::numberForKey()
UserThumb::UserThumb()
LobbyGateway::receivePing()
```

The response had `"clanTradeRecord": {}`. `receivePing()` treats presence of
that object as an actual clan trade record, then requires nested `user`,
`takeCard`, and `giveCard` objects. An empty object sends a null object into
`UserThumb::UserThumb()`, which immediately requires `userId`. The mock now
omits `clanTradeRecord` from `/api/client-secure/ping` and refresh responses
when there is no trade record.

## Profile Stat And Refresh

After tutorial completion, opening the lobby can request:

```text
POST /api/client-secure/refresh
POST /api/client-secure/profile/stat
```

The captured profile-stat request body was:

```json
{"userId":1000001}
```

Returning the generic secure fallback crashed in:

```text
CSJSONObject::numberForKey() + 0x3c
ProfileStat::ProfileStat() + 0x38
LobbyGateway::receiveProfileStat() + 0x58
```

`LobbyGateway::receiveProfileStat()` expects the root object to contain
`userId` and a nested `stat` object. `ProfileStat::ProfileStat()` then reads
twelve numeric counters from that nested object. The mock now returns:

```json
{
  "userId": 1000001,
  "stat": {
    "dailyPlay": 0,
    "normalPlay": 0,
    "normalWin": 0,
    "normalWinStreak": 0,
    "rankPrivatePlay": 0,
    "rankPrivateWin": 0,
    "rankPrivateWinStreak": 0,
    "rankPrivateMaxScore": 0,
    "rankTeamPlay": 0,
    "rankTeamWin": 0,
    "rankTeamWinStreak": 0,
    "rankTeamMaxScore": 0
  }
}
```

`/api/client-secure/refresh` currently returns the minimum keys recovered from
`LobbyGateway::receiveRefresh()` that do not instantiate deeper clan objects:

```json
{
  "rankingPrivate": 0,
  "rankingTeam": 0,
  "clanRewardResult": {"rewards": []},
  "clanDonaters": [],
  "clanTradeRecord": {},
  "user": {
    "userId": 1000001,
    "name": "LocalGuest",
    "country": 0,
    "decorations": [0, 0, 0, 0],
    "pictureUrl": ""
  },
  "takeCard": -1,
  "giveCard": -1,
  "clanReset": false,
  "clanId": 0
}
```

`receiveRefresh()` also references `clan`. The mock intentionally does not send
a placeholder clan object yet: if the client treats `clan` as present, an empty
object can cascade into `Clan`/`ClanThumb` constructor crashes. Add a real clan
shape only if a later crash proves this response path requires it.

## Match Record List

Opening the profile match-record menu sends:

```json
{"userId":1000001,"lastMatchRecordId":0}
```

to:

```text
POST /api/client-secure/match-record/list
```

The generic fallback response crashed in:

```text
ProfileMatchRecordLayer::resetContents() + 0xcc
LobbyGateway::receiveMatchRecordList() + 0x320
```

`LobbyGateway::receiveMatchRecordList()` requires root `userId` and
`matchRecords`. If `matchRecords` is missing, the UI receives a null array and
`ProfileMatchRecordLayer::resetContents()` dereferences it at offset `+592`.
The mock now echoes the requested user and returns an explicit empty list:

```json
{
  "userId": 1000001,
  "matchRecords": []
}
```

The full `UserMatchRecord` shape is only needed once we want to show real replay
history. Its constructors reference `matchRecordId`, `mode`, map fields,
`winner`, `playTime`, `updateTime`, `players`, `url`, `result`, `scoreDiff`,
`locked`, and `shared`.

## Useful Disassembly Commands

Use GNU binutils objdump, not macOS system `objdump`, for the Android ELF:

```sh
/opt/homebrew/opt/binutils/bin/objdump -d --demangle \
  --start-address=0x5ea250 \
  --stop-address=0x5ea620 \
  acies-apktool/lib/arm64-v8a/libcdkapp.so
```

Resolve string offsets from `rodata`:

```sh
python3 - <<'PY'
from pathlib import Path
wanted = [0x3a9e4a, 0x3a7a13, 0x3a9e5d]
rows = []
for line in Path("decrypts/libcdkapp/rodata-strings-with-offsets.txt").read_text(errors="ignore").splitlines():
    parts = line.strip().split(maxsplit=1)
    if len(parts) == 2:
        try:
            rows.append((int(parts[0], 16), parts[1]))
        except ValueError:
            pass
for addr in wanted:
    print(hex(addr), [s for off, s in rows if off == addr])
PY
```

Find relevant symbols:

```sh
/opt/homebrew/opt/binutils/bin/nm -D --demangle \
  acies-apktool/lib/arm64-v8a/libcdkapp.so | rg 'Account::Account|SeasonReward'
```

## Validation

After editing the mock:

```sh
python3 -m py_compile tools/acies_mock_server.py
```

Quick payload check:

```sh
python3 - <<'PY'
from tools.acies_mock_server import login_success_response
print(login_success_response()["account"]["seasonReward"])
PY
```

## Next Work

Continue the crash-guided loop:

1. Run the server with `--guest-success`.
2. Launch the app and tap guest login.
3. If the app crashes, copy the native stack.
4. Map the top failing constructor and offset.
5. Update the synthetic JSON shape.
6. Repeat until the app reaches the next endpoint.

Expected future blockers:

```text
Arena::Arena(CSJSONObject const*)
QuestStatus::QuestStatus(CSJSONObject const*)
Minigame::Minigame(CSJSONObject const*)
Shop::Shop(CSJSONObject const*)
CardShop::CardShop(CSJSONObject const*)
client-secure/reload or profile endpoints
pvp-server endpoints
shop/deck/card data endpoints
```

Keep all generated login/account state clearly synthetic. The purpose is local
offline preservation and protocol mapping, not reconnecting to or impersonating
the original service.
