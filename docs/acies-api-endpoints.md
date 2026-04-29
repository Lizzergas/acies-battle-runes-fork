# ACIES API Endpoint Notes

Date: 2026-04-29

This is a static endpoint inventory from the local ACIES APK workspace. The
main source is the native game library string table:

```text
decrypts/libcdkapp/api-endpoints.txt
decrypts/libcdkapp/domains.txt
decrypts/libcdkapp/rodata-strings-with-offsets.txt
decrypts/libcdkapp/strings.txt
```

Observed local mock captures in `captures/acies_mock/` confirm that the app
starts with `POST /api/client/admission` and then `POST /api/client/login`.

## Hosts And URL Shape

Native strings expose these host/domain values:

```text
live.saintjoy.co.kr
col-glob-lb01.srv.creagames.com
```

The native game library also contains:

```text
http://%s/android/%s
```

The patched local mock APK redirects `live.saintjoy.co.kr` requests to
`http://10.0.2.2:8080`, and the captured request paths are `/api/client/...`.
So `live.saintjoy.co.kr` is confirmed as an HTTP API host for the captured
client flow. `col-glob-lb01.srv.creagames.com` is present in native strings but
was not reached in the current captures.

## Confirmed Runtime Requests

Captured from `captures/acies_mock/*.json` and `*.body`:

```text
POST /api/client/admission
POST /api/client/login
```

The admission body shape observed locally:

```json
{
  "secret": "<uuid>",
  "version": "2.5.1.338",
  "language": "en",
  "region": "US",
  "market": 1
}
```

Some admission attempts also include a `signal` crash-report field.

The login body shape observed locally:

```json
{
  "secret": "<uuid>",
  "version": "2.5.1.338",
  "assetVersion": 0,
  "language": "en",
  "region": "US",
  "market": 1
}
```

## Rune-Related Endpoints

These are the endpoints most directly related to runes:

```text
api/client-secure/arena/runes
api/client-secure/deck/rune-confirm
api/client-secure/deck/rune-equip
api/client-secure/deck/rune-equip-all
api/client-secure/deck/rune-upgrade
api/client-secure/clan/arena-rune-equip
api/client-secure/clan/arena-rune-equip-all
```

Native symbols tie these to `LobbyGateway` request/receive handlers:

```text
LobbyGateway::requestArenaRunes()
LobbyGateway::receiveArenaRunes(CSJSONObject const*)
LobbyGateway::requestRuneConfirm(AssetIndex2 const&)
LobbyGateway::receiveRuneConfirm(CSJSONObject const*)
LobbyGateway::requestRuneEquip(int, int, int, AssetIndex2 const&)
LobbyGateway::receiveRuneEquip(CSJSONObject const*)
LobbyGateway::requestRuneEquipAll(int, AssetIndex2 const (*)[4])
LobbyGateway::receiveRuneEquipAll(CSJSONObject const*)
LobbyGateway::requestRuneUpgrade(AssetIndex2 const&)
LobbyGateway::receiveRuneUpgrade(CSJSONObject const*)
LobbyGateway::requestClanArenaRuneEquip(int, int, AssetIndex2 const&)
LobbyGateway::receiveClanArenaRuneEquip(CSJSONObject const*)
LobbyGateway::requestClanArenaRuneEquipAll(AssetIndex2 const (*)[4])
LobbyGateway::receiveClanArenaRuneEquipAll(CSJSONObject const*)
```

## All Game API Paths Found

### Public Client

```text
api/client/admission
api/client/clan/replay-share
api/client/login
api/client/replay/upload
api/client/social-link
api/client/social-link-validate
```

### Secure Achievement

```text
api/client-secure/achievement/attain
api/client-secure/achievement/reward
```

### Secure Ads

```text
api/client-secure/ad/daily-reward
api/client-secure/ad/refresh
```

### Secure Arena

```text
api/client-secure/arena/end
api/client-secure/arena/pick
api/client-secure/arena/reward
api/client-secure/arena/runes
api/client-secure/arena/start
```

### Secure Clan

```text
api/client-secure/clan/accept
api/client-secure/clan/appoint
api/client-secure/clan/arena-card-equip
api/client-secure/clan/arena-reward
api/client-secure/clan/arena-rune-equip
api/client-secure/clan/arena-rune-equip-all
api/client-secure/clan/arena-validate
api/client-secure/clan/change-notice
api/client-secure/clan/create
api/client-secure/clan/deck-share
api/client-secure/clan/deco-equip
api/client-secure/clan/deny
api/client-secure/clan/deny-all
api/client-secure/clan/donate
api/client-secure/clan/donate-register
api/client-secure/clan/donate-unregister
api/client-secure/clan/expulse
api/client-secure/clan/join
api/client-secure/clan/leave
api/client-secure/clan/modify
api/client-secure/clan/profile
api/client-secure/clan/recommend
api/client-secure/clan/search
api/client-secure/clan/trade
api/client-secure/clan/trade-register
api/client-secure/clan/trade-unregister
```

### Secure Deck

```text
api/client-secure/deck/card-confirm
api/client-secure/deck/card-equip
api/client-secure/deck/card-equip-all
api/client-secure/deck/card-make
api/client-secure/deck/card-upgrade
api/client-secure/deck/change-name
api/client-secure/deck/mastery-reward
api/client-secure/deck/rune-confirm
api/client-secure/deck/rune-equip
api/client-secure/deck/rune-equip-all
api/client-secure/deck/rune-upgrade
api/client-secure/deck/set-page
api/client-secure/deck/skin-equip
api/client-secure/deck/theme-equip
```

### Secure Game

```text
api/client-secure/game/ad-reward
api/client-secure/game/campaign-step
api/client-secure/game/mode-reset
api/client-secure/game/prev-result
api/client-secure/game/result
api/client-secure/game/reward-reset
```

### Secure Mail, Profile, Quest, Shop

```text
api/client-secure/mail/confirm
api/client-secure/mail/list
api/client-secure/mail/open
api/client-secure/mail/open-all
api/client-secure/profile
api/client-secure/profile/change-country
api/client-secure/profile/change-description
api/client-secure/profile/change-name
api/client-secure/profile/deco-equip
api/client-secure/profile/stat
api/client-secure/quest/attain
api/client-secure/quest/point-reward
api/client-secure/quest/reward
api/client-secure/quest/status
api/client-secure/shop/buy-card
api/client-secure/shop/buy-card-open
api/client-secure/shop/buy-card-reset
api/client-secure/shop/buy-deck-page
api/client-secure/shop/buy-product
api/client-secure/shop/buy-product-charge
api/client-secure/shop/buy-product-validate
api/client-secure/shop/card-info
api/client-secure/shop/info
```

### Secure Other

```text
api/client-secure/banners
api/client-secure/challenge-reset
api/client-secure/challenge-reward
api/client-secure/challenge-reward/slot-open
api/client-secure/challenge/bonus
api/client-secure/change-picture
api/client-secure/cheat-log
api/client-secure/coupon
api/client-secure/emoticon/confirm
api/client-secure/emoticon/equip
api/client-secure/friend/confirm
api/client-secure/friend/recommend
api/client-secure/invitation
api/client-secure/invitation/input
api/client-secure/invitation/reward
api/client-secure/language
api/client-secure/level/attain
api/client-secure/level/reward
api/client-secure/match-record/list
api/client-secure/match-record/lock
api/client-secure/minigame/attendance/ex-reward
api/client-secure/minigame/attendance/info
api/client-secure/minigame/attendance/reward
api/client-secure/minigame/board/info
api/client-secure/minigame/board/play
api/client-secure/minigame/quest/attain
api/client-secure/minigame/quest/info
api/client-secure/minigame/quest/point-reward
api/client-secure/minigame/quest/reward
api/client-secure/minigame/roulette/info
api/client-secure/minigame/roulette/play
api/client-secure/offline-message
api/client-secure/ping
api/client-secure/push-token
api/client-secure/pvp-server
api/client-secure/ranking/clan-list
api/client-secure/ranking/user-list
api/client-secure/refresh
api/client-secure/reload
api/client-secure/score/reward
api/client-secure/season-result
api/client-secure/social-link-remove
api/client-secure/subscription-reset
api/client-secure/tutorial/step
api/client-secure/tv-live/list
api/client-secure/tv-replay/list
api/client-secure/tv-replay/upload-verify
```

## Notes

- The HTTP API appears to be owned by the native `LobbyGateway` layer.
- `api/client-secure/pvp-server` likely returns a PVP server address; native
  symbols show a separate `PVPGateway` and `PVPAddress` layer for online match
  traffic. That layer is probably not HTTP endpoint-based.
- Third-party SDK endpoints from AppsFlyer, Firebase, Facebook, AdMob, and
  Google Play are present in Java/smali, but they are not included in the game
  API list above.
