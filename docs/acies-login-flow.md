# ACIES Login Flow

Date: 2026-04-29

This is the native login path recovered from `libcdkapp.so` for local
preservation/debugging. It describes what the Android client expects from a
compatible local backend; it is not a production service integration guide.

## Summary

The client has two related paths:

1. A normal startup path: `/api/client/admission` then `/api/client/login`.
2. A first-time account path: the title layer opens the account-sync popup; the
   Guest button confirms through `AccountSyncGuestLayer`, calls
   `/api/client/social-link`, saves the returned local session, then continues
   to `/api/client/login`.

If a local `SessionInfo` file already exists, the Guest button is skipped
entirely. `TitleLayer::doLogin()` immediately calls `LobbyGateway::requestLogin()`.

## Native Evidence

Important symbols:

```text
0x506fb4  LobbyGateway::requestAdmission()
0x50714c  LobbyGateway::receiveAdmission(CSJSONObject const*)
0x51ac34  LobbyGateway::requestLogin()
0x51adb8  LobbyGateway::receiveLogin(CSJSONObject const*)
0x528238  LobbyGateway::requestSocialLink(SocialPlatform, char const*)
0x5283c8  LobbyGateway::receiveSocialLink(CSJSONObject const*)
0x528594  LobbyGateway::requestSocialLinkValidate(SocialPlatform, char const*)
0x528678  LobbyGateway::receiveSocialLinkValidate(CSJSONObject const*)
0x5050fc  SessionInfo::createFromLocal(char const*)
0x505398  SessionInfo::save(char const*)
0x7b8e74  TitleLayer::doLogin()
0x7b8ecc  TitleLayer::popupAccountSyncLayer()
0x7b1798  AccountSyncDelegateLayer::touchesEndedGuestButton()
0x7b1964  guest-confirm delegate lambda
0x7b13a0  AccountSyncDelegateLayer::onLobbySocialLink()
0x7b9be0  TitleLayer::onLobbyLogin(bool)
```

## Startup Admission

`LobbyGateway::requestAdmission()` builds a JSON body.

With no saved session:

```json
{
  "secret": "<CSDevice::uuid()>",
  "version": "2.5.1.338",
  "language": "en",
  "region": "US",
  "market": 1
}
```

With a saved session:

```json
{
  "userId": 1000001,
  "secret": "local-offline-secret",
  "version": "2.5.1.338",
  "language": "en",
  "region": "US",
  "market": 1
}
```

It may also include `signal` when a previous native crash log exists.

The response needs at least:

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

For the local APK, `assetVersion: 177` matches the patch manifest revision and
`revision: 83` matches the newest packaged `data/game[083].xmf`.

## Session File

`SessionInfo::createFromLocal()` checks for a saved user id and secret. The
storage path is derived from the gateway storage key, with `/` and `:` replaced
by `_`, and the final file name uses `.xmf`.

The saved data contains:

```text
long userId
string secret
```

`SessionInfo::save()` writes those two values after `/api/client/social-link`
or `/api/client/login` succeeds. This is why later launches send `userId` and
`secret` immediately and skip the guest popup.

## Normal Login

`LobbyGateway::requestLogin()` sends:

```json
{
  "userId": 1000001,
  "secret": "local-offline-secret",
  "version": "2.5.1.338",
  "assetVersion": 177,
  "language": "en",
  "region": "US",
  "market": 1
}
```

If there is no saved session, `userId` is omitted and `secret` is the device
UUID. A real backend could choose to treat that as a guest lookup, but the
client UI's explicit guest path is the social-link path below.

A successful login response must contain:

```json
{
  "result": 0,
  "secret": "local-offline-secret",
  "encryption": "localmockkey0001",
  "dayChanged": false,
  "account": {}
}
```

`account` is not optional. It is passed to `Account::load(...)`, and missing
nested fields can crash native constructors. The current synthetic account
shape lives in `tools/acies_mock_server.py` in `mock_account()`.

On success, `receiveLogin()` does this:

1. Loads the account model.
2. Constructs a `Session` from the root login response.
3. Saves `userId` and `secret` through `SessionInfo::save()`.
4. Calls `CSAppSafer::setUserId(...)` and `CSFirebase::setUserId(...)`.
5. Sends the `onLobbyLogin(dayChanged)` delegate callback.
6. If `message` exists, sends a separate login-message callback.

After that, the observed next request is:

```text
POST /api/client-secure/push-token
```

The secure endpoints are encrypted with the session `encryption` value. The
current mock uses AES-CBC with key `localmockkey0001` and IV equal to the first
16 bytes of that key.

## Guest Button Flow

The Guest button path only appears when no local `SessionInfo` exists:

```text
TitleLayer::doLogin()
  -> SessionInfo::createFromLocal(...) returns null
  -> TitleLayer::popupAccountSyncLayer()
  -> AccountSyncLayer guest button
  -> AccountSyncDelegateLayer::touchesEndedGuestButton()
  -> AccountSyncGuestLayer confirmation popup
  -> confirm lambda at 0x7b1964
  -> AccountSyncDelegateLayer::requestSocialLink()
  -> LobbyGateway::requestSocialLink(...)
```

`requestSocialLink()` supports enum values `0..6`. Confirmed setters:

```text
Facebook success:    socialPlatform = 0, socialId from CSFacebook::userId()
Google Play success: socialPlatform = 1, socialId from CSGooglePlay::userId()
```

The Guest path does not set a fresh enum in `touchesEndedGuestButton()`. It
uses the default state already on `AccountSyncDelegateLayer`; based on the
constructor and current static trace, that likely means `socialPlatform: 0` and
an empty/null `socialId` unless another initialization path is found. The next
real emulator capture after tapping Guest should confirm the exact body.

Expected `/api/client/social-link` request shape:

```json
{
  "secret": "<device uuid or saved session secret>",
  "socialPlatform": 0,
  "socialId": "",
  "language": "en",
  "region": "US",
  "market": 1
}
```

If a saved session already exists, the body also includes `userId`.

Minimum successful `/api/client/social-link` response:

```json
{
  "result": 0,
  "userId": 1000001,
  "secret": "local-offline-secret",
  "socialPlatform": 0
}
```

`receiveSocialLink()` then:

1. Builds `SessionInfo(userId, secret)`.
2. Saves it locally.
3. If `Account::shared` already exists, marks that social platform as linked.
4. Notifies delegates through `onLobbySocialLink()`.
5. The title popup handler continues back into the login path.

For Google/Facebook only, the client first calls
`/api/client/social-link-validate` with:

```json
{
  "socialPlatform": 1,
  "socialId": "<external platform id>"
}
```

If the response has no `user` object, the client proceeds to
`requestSocialLink()`. If it has a `user` object, it opens an account-change
confirmation popup.

## What Happens After Guest Sign-In

For a clean install, the intended identity sequence is:

```text
POST /api/client/admission
POST /api/client/social-link
POST /api/client/login
POST /api/client-secure/push-token
```

The important point is that Guest is not a separate long-lived auth mode in the
native client. The Guest button asks the backend to create/link an identity
through `/api/client/social-link`; the returned `userId` and `secret` are saved
locally as the normal session. Later launches use that saved session and skip
the Guest UI.

After `/api/client/login` succeeds, `TitleLayer::onLobbyLogin(bool)` does not
enter the lobby immediately. It:

1. Stores `dayChanged`.
2. Sets the title state to `6`.
3. Calls `LobbyGateway::requestIAPConnect()`.
4. Calls `LobbyGateway::requestPushToken()`.
5. Clears and re-adds local notifications.

When IAP connect succeeds, `TitleLayer::onLobbyIAPConnected()` sets state `7`
and calls `LobbyGateway::requestIAPSync(account.userId)`. When IAP sync
succeeds, `TitleLayer::onLobbyIAPSync()` sets state `8`. At that point the
title screen is waiting for a tap.

On tap, `TitleLayer::onTouchesEnded()` checks Google Play:

```text
state 8 + Google Play connected     -> TitleLayer::doComplete()
state 8 + Google Play not connected -> state 9, CSGooglePlay::login()
Google Play callback                -> TitleLayer::doComplete()
```

This explains why a Guest account can still trigger a Google Play prompt after
login. The prompt is a post-login platform-link attempt, not the Guest account
creation itself.

`TitleLayer::doComplete()` decides what screen the new account sees:

```text
if Account::isPlayingCampaignTutorial():
    open GameLayer::layerForOfflinePlay(mode=32, first campaign map)
else if GameRecord::resumeMatch():
    ask whether to resume the previous online match
else:
    TitleLayer::doMoveToLobby()
```

`Account::isPlayingCampaignTutorial()` compares the length of
`account.campaignStages` with the campaign tutorial count loaded from game
assets. A truly fresh account with `campaignStages: []` is therefore treated as
still inside the campaign tutorial. It does not go straight to the lobby; it
starts an offline campaign/tutorial battle through
`GameLayer::layerForOfflinePlay(...)`.

The observed first tutorial battle completion posts:

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

to:

```text
POST /api/client-secure/game/result
```

The response must include a `rewardResult` object with at least a `rewards`
array. Returning completed `campaignStages` there prevents the title flow from
looping back into the same campaign tutorial.

Tutorial overlay progress is separate from campaign battle progress.
`LobbyGateway::requestTutorialStep(TutorialCategory, int, bool)` posts:

```json
{
  "category": 0,
  "step": 1,
  "skip": false
}
```

to:

```text
POST /api/client-secure/tutorial/step
```

`LobbyGateway::receiveTutorialStep()` expects `category`, `step`, `skip`, and
`rewardResult`; it writes `step` into `Account` at the per-category tutorial
step array and then applies the reward result.

If the account is already past the campaign tutorial, `TitleLayer::doMoveToLobby()`
clears the title layers and opens:

```text
LobbyLayer(LobbyTutorialState=1, LobbyPage=0)
```

If `dayChanged` was true in the login response, it then calls
`LobbyGateway::requestLoginAttain()`.

The [tutorial analysis](acies-tutorials.md) lists the campaign entries,
the in-context categories, and the account levels and steps that unlock
features in the shipped client.

## Local Mock Status

`tools/acies_mock_server.py --guest-success` now returns local success payloads
for:

```text
POST /api/client/admission
POST /api/client/social-link-validate
POST /api/client/social-link
POST /api/client/login
POST /api/client-secure/push-token
POST /api/client-secure/game/result
POST /api/client-secure/game/campaign-step
POST /api/client-secure/tutorial/step
```

This lets the next emulator run capture the actual Guest `socialPlatform` and
`socialId` values while still allowing the client to proceed through login and
the first offline tutorial checks.
