# ACIES libcdkapp.so Extraction Pack

Date: 2026-04-29

Generated from `acies-apktool/lib/arm64-v8a/libcdkapp.so` and the already-demangled symbol/string files.

## Generated Artifacts

- `docs/acies-api-endpoints.md`: HTTP endpoint inventory.
- `docs/acies-json-payloads.md`: JSON data classes, request keys, response keys.
- `decrypts/libcdkapp/extracted/pvp-gateway.md`: PVP binary gateway request/receive map.
- `decrypts/libcdkapp/extracted/pvp-buffer-ops.json`: machine-readable PVP buffer op hints.
- `decrypts/libcdkapp/extracted/symbol-groups.md`: grouped native symbols.
- `decrypts/libcdkapp/extracted/asset-file-refs.txt`: asset/path/template strings.
- `decrypts/libcdkapp/extracted/security-anticheat.md`: security, anti-cheat, token/session refs.
- `decrypts/libcdkapp/extracted/replay-match.md`: replay, match, result refs.
- `decrypts/libcdkapp/extracted/enum-type-hints.txt`: enum/type names inferred from signatures.

## Counts

- Total demangled symbols: `22193`
- RODATA string entries: `4697`
- PVPGateway symbols: `130`
- PVPGateway request symbols: `59`
- PVPGateway receive symbols: `55`
- Asset/path string refs: `40`
- Security/anti-cheat symbols: `74`
- Security/anti-cheat strings: `37`
- Replay/match symbols: `745`

## Top Native Class/Namespace Prefixes

| Prefix | Symbol Count |
| --- | --- |
| `std` | 3599 |
| `typeinfo name for std` | 501 |
| `typeinfo for std` | 501 |
| `vtable for std` | 448 |
| `Unit` | 417 |
| `Map` | 411 |
| `LobbyGateway` | 318 |
| `GameLayer` | 204 |
| `CSGraphics` | 189 |
| `typeinfo name for CSDelegate0<void, CSLayer*>` | 172 |
| `typeinfo for CSDelegate0<void, CSLayer*>` | 172 |
| `typeinfo name for CSDelegate0<void, CSLayer*, CSGraphics*>` | 170 |
| `typeinfo for CSDelegate0<void, CSLayer*, CSGraphics*>` | 170 |
| `LobbyGatewayDelegate` | 156 |
| `PVPGateway` | 130 |
| `Tutorial` | 106 |
| `CSString` | 92 |
| `Analysis` | 89 |
| `CSLayer` | 84 |
| `ClanMainLayer` | 81 |
| `PVPGatewayDelegate` | 72 |
| `non-virtual thunk to Tutorial` | 69 |
| `Force` | 64 |
| `ShopLayer` | 62 |
| `LobbyLayer` | 60 |
| `Account` | 59 |
| `MatchLayer` | 57 |
| `typeinfo name for CSLayer` | 55 |
| `ChatLayer` | 54 |
| `CardDeckLayer` | 54 |
| `CSView` | 54 |
| `CSBuffer` | 54 |
| `RuneDeckLayer` | 53 |
| `ClanArenaRuneDeckLayer` | 50 |
| `DecorationCollectionLayer` | 49 |
| `Spell` | 48 |
| `CardInfoLayer` | 48 |
| `HomeLayer` | 47 |
| `Asset` | 45 |
| `UnitBase` | 44 |
| `ClanTradeRegisterLayer` | 43 |
| `ClanArenaCardDeckLayer` | 42 |
| `ClanArenaCollectionBattleLayer` | 42 |
| `ClanArenaBattleLayer` | 41 |
| `UserPopupLayer` | 40 |
| `ClanMemberPopupLayer` | 39 |
| `PartyLayer` | 39 |
| `TitleLayer` | 39 |
| `CSMatrix` | 38 |
| `ClanDonateRegisterLayer` | 38 |
| `CSTextField` | 38 |
| `ChallengeContentsLayer` | 37 |
| `SocialLayer` | 37 |
| `NavMesh` | 36 |
| `BuyProductLayer` | 35 |
| `OptionGameLayoutLayer` | 34 |
| `SocialFriendRecommendLayer` | 34 |
| `CSData` | 34 |
| `MailLayer` | 33 |
| `Animation` | 32 |

## Highest-Value Next Targets

1. PVP packet opcode recovery from `PVPGateway::receivePacket()` and `PVPGateway::request*()`.
2. Deep schema reconstruction for `Account`, `Deck`, `Card`, `Rune`, `Player`, `MatchRecord`, and `GameResultRecord`.
3. Patch/version flow from `LobbyGateway::requestPatch`, `receivePatch`, and asset path templates.
4. Security flow from `CSAppSafer`, `Session`, `cheat-log`, and crash `signal` payloads.
