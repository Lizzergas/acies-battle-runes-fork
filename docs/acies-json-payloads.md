# ACIES JSON Payload And Data-Class Inventory

Date: 2026-04-29

Static analysis sources:

- `acies-apktool/lib/arm64-v8a/libcdkapp.so`
- `decrypts/libcdkapp/symbols.demangled.txt`
- `decrypts/libcdkapp/rodata-strings-with-offsets.txt`
- `captures/acies_mock/*.body`

This document lists native classes and payload hints recoverable from symbols and string references. It is not a full server contract: field types and nested response objects still need deeper function-level decompilation or live archival responses.

## JSON-Backed Data Classes

Found `80` classes/factories that consume `CSJSONObject`:

### `Account`

Constructors/factories:
- `Account::Account(CSJSONObject const*)`

JSON keys referenced directly:
- `exp`
- `gold`
- `cash`
- `medal`
- `badge`
- `material`
- `mileage`
- `socialCoin`
- `clanToken`
- `cardResetTicket`
- `nameTicket`
- `nameRemainTime`
- `countryTicket`
- `countryChanged`
- `arenaTicket`
- `allCards`
- `allRunes`
- `deckTheme`
- `deckPage`
- `deckPageCount`
- `decks`
- `allSkins`
- `allDecorations`
- `allEmoticons`
- `emoticons`
- `clan`
- `gameRewardLimits`
- `gameModeStatus`
- `arena`
- `scoreRewardObtain`
- `levelQuests`
- `questStatus`
- `achievements`
- `boosters`
- `challenges`
- `challengeRemainTime`
- `subscriptions`
- `themes`
- `season`
- `seasonRemainTime`
- `seasonReward`
- `tutorialSteps`
- `campaignStages`
- `minigame`
- `hotTimeEvents`
- `banners`
- `socialPlatforms`
- `shop`
- `cardShop`
- `ad`
- `isDeveloper`

### `Achievement`

Constructors/factories:
- `Achievement::Achievement(CSJSONObject const*)`

JSON keys referenced directly:
- `achievementId`
- `progress`
- `state`

### `Ad`

Constructors/factories:
- `Ad::Ad(CSJSONObject const*)`

JSON keys referenced directly:
- `dailyRewardStep`
- `gameRewardRemaining`
- `dailyRewards`
- `dailyRewardRemainTime`
- `remainRefreshTime`

### `Arena`

Constructors/factories:
- `Arena::Arena(CSJSONObject const*)`

JSON keys referenced directly:
- `join`
- `win`
- `lose`
- `loseLimit`
- `weeklyTry`
- `weeklyTryLimit`
- `levelLimit`
- `gold`
- `rewardStep`
- `rewards`
- `cards`
- `cardPicks`
- `runes`

### `Banner`

Constructors/factories:
- `Banner::Banner(CSJSONObject const*)`

JSON keys referenced directly:
- `bannerId`
- `moveUrl`
- `remainTime`

### `Booster`

Constructors/factories:
- `Booster::Booster(CSJSONObject const*)`

JSON keys referenced directly:
- `boosterId`
- `remaining`

### `Card`

Constructors/factories:
- `Card::Card(CSJSONObject const*, ForceBase const*)`

JSON keys referenced directly:
- none found

### `CardAccount`

Constructors/factories:
- `CardAccount::CardAccount(CSJSONObject const*)`

JSON keys referenced directly:
- `count`
- `masteryLevel`
- `masteryPoint`
- `masteryRewardPoint`
- `isNew`

### `CardProduct`

Constructors/factories:
- `CardProduct::CardProduct(CSJSONObject const*)`

JSON keys referenced directly:
- `cardId`
- `remaining`
- `free`

### `CardShop`

Constructors/factories:
- `CardShop::CardShop(CSJSONObject const*)`

JSON keys referenced directly:
- `products`
- `nextResetTicket`
- `nextResetCash`
- `remainTime`

### `Challenge`

Constructors/factories:
- `Challenge::Challenge(CSJSONObject const*)`

JSON keys referenced directly:
- `challengeId`
- `passBought`
- `obtainGold`
- `point`
- `limitPoint`
- `rewardIndex`
- `passRewardIndex`
- `rewards`
- `remainTime`

### `ChallengeReward`

Constructors/factories:
- `ChallengeReward::ChallengeReward(CSJSONObject const*)`

JSON keys referenced directly:
- `point`
- `item`
- `passItem`

### `Clan`

Constructors/factories:
- `Clan::Clan(CSJSONObject const*)`

JSON keys referenced directly:
- `point`
- `score`
- `pointRanking`
- `scoreRanking`
- `division`
- `country`
- `memberCount`
- `maxMemberCount`
- `joinScore`
- `openType`

### `ClanAccount`

Constructors/factories:
- `ClanAccount::ClanAccount(CSJSONObject const*)`

JSON keys referenced directly:
- `notice`
- `updateTime`
- `arena`
- `allDecorations`
- `posts`

### `ClanArena`

Constructors/factories:
- `ClanArena::ClanArena(CSJSONObject const*)`

JSON keys referenced directly:
- `week`
- `win`
- `lose`
- `collectionPlay`
- `point`
- `card`
- `mapId`
- `mapVersion`
- `mapLevel`
- `state`
- `rewardPoint`
- `rewards`
- `remainTime`
- `allCards`
- `allRunes`
- `deck`

### `ClanArenaCard`

Constructors/factories:
- `ClanArenaCard::ClanArenaCard(CSJSONObject const*)`

JSON keys referenced directly:
- `cardId`
- `count`

### `ClanArenaRewardItem`

Constructors/factories:
- `ClanArenaRewardItem::ClanArenaRewardItem(CSJSONObject const*)`

JSON keys referenced directly:
- `point`

### `ClanArenaRune`

Constructors/factories:
- `ClanArenaRune::ClanArenaRune(CSJSONObject const*)`

JSON keys referenced directly:
- `runeId`
- `count`

### `ClanDonater`

Constructors/factories:
- `ClanDonater::ClanDonater(CSJSONObject const*)`

JSON keys referenced directly:
- `count`

### `ClanMember`

Constructors/factories:
- `ClanMember::ClanMember(CSJSONObject const*, ClanThumb*)`

JSON keys referenced directly:
- `memberAuth`
- `point`
- `card`
- `weeklyPoint`
- `weeklyCard`
- `weeklyCollectionPlay`
- `lastLoginTime`

### `ClanPost`

Constructors/factories:
- `ClanPost::ClanPost(CSJSONObject const*)`

JSON keys referenced directly:
- `clanPostId`
- `user`
- `postTime`

### `ClanPostArena`

Constructors/factories:
- `ClanPostArena::ClanPostArena(CSJSONObject const*)`

JSON keys referenced directly:
- `win`

### `ClanPostDeckShare`

Constructors/factories:
- `ClanPostDeckShare::ClanPostDeckShare(CSJSONObject const*)`

JSON keys referenced directly:
- `description`
- `cards`
- `runes`

### `ClanPostDonate`

Constructors/factories:
- `ClanPostDonate::ClanPostDonate(CSJSONObject const*)`

JSON keys referenced directly:
- `cardId`
- `donaters`
- `count`
- `limit`
- `remainTime`

### `ClanPostMatch`

Constructors/factories:
- `ClanPostMatch::ClanPostMatch(CSJSONObject const*)`

JSON keys referenced directly:
- `message`
- `matchId`
- `mode`
- `mapId`
- `mapVersion`
- `mapLevel`
- `user`

### `ClanPostMatchResult`

Constructors/factories:
- `ClanPostMatchResult::ClanPostMatchResult(CSJSONObject const*)`

JSON keys referenced directly:
- `message`
- `mapId`
- `mapVersion`
- `mapLevel`
- `playTime`
- `winner`
- `players`

### `ClanPostMember`

Constructors/factories:
- `ClanPostMember::ClanPostMember(CSJSONObject const*)`

JSON keys referenced directly:
- `target`
- `action`
- `auth`

### `ClanPostParty`

Constructors/factories:
- `ClanPostParty::ClanPostParty(CSJSONObject const*)`

JSON keys referenced directly:
- `message`
- `partyId`
- `mode`
- `playerCount`
- `players`

### `ClanPostReplayShare`

Constructors/factories:
- `ClanPostReplayShare::ClanPostReplayShare(CSJSONObject const*)`

JSON keys referenced directly:
- `matchRecord`
- `description`

### `ClanPostTrade`

Constructors/factories:
- `ClanPostTrade::ClanPostTrade(CSJSONObject const*)`

JSON keys referenced directly:
- `takeCard`
- `giveCards`
- `trader`
- `tradeCard`
- `remainTime`

### `ClanProfile`

Constructors/factories:
- `ClanProfile::ClanProfile(CSJSONObject const*)`

JSON keys referenced directly:
- `description`
- `members`

### `ClanRanker`

Constructors/factories:
- `ClanRanker::ClanRanker(CSJSONObject const*)`

JSON keys referenced directly:
- `rankingDiff`

### `ClanThumb`

Constructors/factories:
- `ClanThumb::ClanThumb(CSJSONObject const*)`

JSON keys referenced directly:
- `clanId`
- `name`
- `decorations`

### `ClanTradeCard`

Constructors/factories:
- `ClanTradeCard::ClanTradeCard(CSJSONObject const*)`

JSON keys referenced directly:
- `cardId`
- `count`

### `Deck`

Constructors/factories:
- `Deck::Deck(CSJSONObject const*)`

JSON keys referenced directly:
- `name`
- `cards`
- `runes`

### `Emoticon`

Constructors/factories:
- `Emoticon::Emoticon(CSJSONObject const*)`

JSON keys referenced directly:
- `emoticonId`
- `isNew`

### `GameModeStatus`

Constructors/factories:
- `GameModeStatus::GameModeStatus(CSJSONObject const*)`

JSON keys referenced directly:
- `mode`
- `open`
- `remainTime`

### `GameRewardLimit`

Constructors/factories:
- `GameRewardLimit::GameRewardLimit(CSJSONObject const*)`

JSON keys referenced directly:
- `type`
- `current`
- `limit`
- `remainTime`

### `HotTimeEvent`

Constructors/factories:
- `HotTimeEvent::HotTimeEvent(CSJSONObject const*)`

JSON keys referenced directly:
- `eventId`
- `mode`
- `remainTime`

### `Invitation`

Constructors/factories:
- `Invitation::Invitation(CSJSONObject const*)`

JSON keys referenced directly:
- `count`
- `input`
- `inputReward`
- `rewards`

### `InvitationRewardItem`

Constructors/factories:
- `InvitationRewardItem::InvitationRewardItem(CSJSONObject const*)`

JSON keys referenced directly:
- `count`
- `received`

### `LevelQuest`

Constructors/factories:
- `LevelQuest::LevelQuest(CSJSONObject const*)`

JSON keys referenced directly:
- `questId`
- `progress`
- `state`

### `LobbyGateway`

Constructors/factories:
- `LobbyGateway::receiveAchievementAttain(CSJSONObject const*)`

JSON keys referenced directly:
- `achievementPoint`
- `achievements`
- `progress`
- `state`

### `Mail`

Constructors/factories:
- `Mail::Mail(CSJSONObject const*)`

JSON keys referenced directly:
- `mailId`
- `title`
- `message`
- `isNew`
- `rewards`
- `remainTime`
- `receiveTime`
- `type`

### `MatchLive`

Constructors/factories:
- `MatchLive::MatchLive(CSJSONObject const*)`

JSON keys referenced directly:
- `matchId`
- `mode`
- `maxCardLevel`
- `maxRuneLevel`
- `mapId`
- `mapVersion`
- `mapLevel`
- `observerCount`
- `updateTime`
- `players`

### `MatchRecord`

Constructors/factories:
- `MatchRecord::MatchRecord(CSJSONObject const*)`

JSON keys referenced directly:
- `matchRecordId`
- `mode`
- `mapId`
- `mapVersion`
- `mapLevel`
- `maxCardLevel`
- `maxRuneLevel`
- `winner`
- `playTime`
- `updateTime`
- `players`
- `url`

### `Minigame`

Constructors/factories:
- `Minigame::Minigame(CSJSONObject const*)`

JSON keys referenced directly:
- `board`
- `attendances`
- `quests`
- `roulettes`

### `MinigameAttendance`

Constructors/factories:
- `MinigameAttendance::MinigameAttendance(CSJSONObject const*)`

JSON keys referenced directly:
- `eventId`
- `type`
- `rewardDay`
- `rewardEnabled`
- `continuousRewardEnabled`
- `continuousDay`
- `rewardIndex`
- `remainRefreshTime`
- `rewards`

### `MinigameBoard`

Constructors/factories:
- `MinigameBoard::MinigameBoard(CSJSONObject const*)`

JSON keys referenced directly:
- `remainRefreshTime`
- `remainPlayTime`
- `cash`
- `currentPosition`
- `startTime`
- `endTime`
- `rewards`
- `rewardIndices`

### `MinigameQuest`

Constructors/factories:
- `MinigameQuest::MinigameQuest(CSJSONObject const*)`

JSON keys referenced directly:
- `eventId`
- `point`
- `today`
- `rewardIndex`
- `remainTime`
- `quests`

### `MinigameQuestElement`

Constructors/factories:
- `MinigameQuestElement::MinigameQuestElement(CSJSONObject const*)`

JSON keys referenced directly:
- `questId`
- `state`
- `progress`

### `MinigameRoulette`

Constructors/factories:
- `MinigameRoulette::MinigameRoulette(CSJSONObject const*)`

JSON keys referenced directly:
- `eventId`
- `payment`
- `accum`
- `point`
- `dailyCount`
- `dailyLimit`
- `remainCountRefreshTime`
- `remainNextTime`
- `remainTime`
- `rewards`
- `rewardIndices`

### `Notice`

Constructors/factories:
- `Notice::Notice(CSJSONObject const*)`

JSON keys referenced directly:
- `noticeId`
- `title`
- `message`
- `url`
- `moveUrl`
- `startTime`
- `endTime`
- `type`

### `PVPAddress`

Constructors/factories:
- `PVPAddress::PVPAddress(CSJSONObject const*)`

JSON keys referenced directly:
- `host`
- `port`

### `Player`

Constructors/factories:
- `Player::createWithJSON(CSJSONObject const*)`

JSON keys referenced directly:
- none found

### `Product`

Constructors/factories:
- `Product::Product(CSJSONObject const*)`

JSON keys referenced directly:
- `productId`
- `category`
- `priceType`
- `price`
- `originPrice`
- `cash`
- `buyCount`
- `buyLimit`
- `valuation`
- `repeat`
- `remainBuyTime`
- `remainSellStartTime`
- `remainSellEndTime`
- `rewards`

### `Profile`

Constructors/factories:
- `Profile::createWithJSON(CSJSONObject const*)`

JSON keys referenced directly:
- none found

### `ProfileStat`

Constructors/factories:
- `ProfileStat::ProfileStat(CSJSONObject const*)`

JSON keys referenced directly:
- `dailyPlay`
- `normalPlay`
- `normalWin`
- `normalWinStreak`
- `rankPrivatePlay`
- `rankPrivateWin`
- `rankPrivateWinStreak`
- `rankPrivateMaxScore`
- `rankTeamPlay`
- `rankTeamWin`
- `rankTeamWinStreak`
- `rankTeamMaxScore`

### `Quest`

Constructors/factories:
- `Quest::Quest(CSJSONObject const*)`

JSON keys referenced directly:
- `questId`
- `progress`
- `state`

### `QuestPointRewardItem`

Constructors/factories:
- `QuestPointRewardItem::QuestPointRewardItem(CSJSONObject const*)`

JSON keys referenced directly:
- `point`

### `QuestStatus`

Constructors/factories:
- `QuestStatus::QuestStatus(CSJSONObject const*)`

JSON keys referenced directly:
- `dailyRewards`
- `weeklyRewards`
- `dailyRewardStep`
- `weeklyRewardStep`
- `dailyPoint`
- `weeklyPoint`
- `remainTime`
- `quests`

### `Ranker`

Constructors/factories:
- `Ranker::Ranker(CSJSONObject const*)`

JSON keys referenced directly:
- `rankingDiff`
- `clan`

### `RankingReward`

Constructors/factories:
- `RankingReward::RankingReward(CSJSONObject const*)`

JSON keys referenced directly:
- `rankFrom`
- `rankTo`
- `rewards`

### `Reward`

Constructors/factories:
- `Reward::Reward(CSJSONObject const*)`

JSON keys referenced directly:
- `boxId`
- `items`

### `RewardItem`

Constructors/factories:
- `RewardItem::RewardItem(CSJSONObject const*)`

JSON keys referenced directly:
- `type`
- `value0`
- `value1`
- `value2`

### `Rune`

Constructors/factories:
- `Rune::Rune(CSJSONObject const*, ForceBase const*)`

JSON keys referenced directly:
- `runeId`
- `level`

### `RuneAccount`

Constructors/factories:
- `RuneAccount::RuneAccount(CSJSONObject const*)`

JSON keys referenced directly:
- `isNew`

### `SeasonResult`

Constructors/factories:
- `SeasonResult::SeasonResult(CSJSONObject const*)`

JSON keys referenced directly:
- `score`
- `ranking`
- `division`

### `SeasonReward`

Constructors/factories:
- `SeasonReward::SeasonReward(CSJSONObject const*)`

JSON keys referenced directly:
- `userRankingRewards`
- `clanRankingRewards`
- `divisionRewards`

### `Session`

Constructors/factories:
- `Session::Session(CSJSONObject const*)`

JSON keys referenced directly:
- `account`
- `userId`
- `secret`
- `encryption`

### `Shop`

Constructors/factories:
- `Shop::Shop(CSJSONObject const*)`

JSON keys referenced directly:
- `updateTime`
- `remainTime`
- `products`

### `Subscription`

Constructors/factories:
- `Subscription::Subscription(CSJSONObject const*)`

JSON keys referenced directly:
- `subscriptionId`
- `remainTime`

### `UnitBase`

Constructors/factories:
- `UnitBase::UnitBase(CSJSONObject const*)`

JSON keys referenced directly:
- `cardId`
- `level`
- `skin`

### `User`

Constructors/factories:
- `User::createWithJSON(CSJSONObject const*)`

JSON keys referenced directly:
- none found

### `UserMatchRecord`

Constructors/factories:
- `UserMatchRecord::UserMatchRecord(CSJSONObject const*)`

JSON keys referenced directly:
- `result`
- `scoreDiff`
- `locked`
- `shared`

### `UserRecord`

Constructors/factories:
- `UserRecord::UserRecord(CSJSONObject const*, UserRecordType)`

JSON keys referenced directly:
- `score`
- `scoreHigh`
- `ranking`
- `division`
- `divisionHigh`

### `UserThumb`

Constructors/factories:
- `UserThumb::UserThumb(CSJSONObject const*)`

JSON keys referenced directly:
- `userId`
- `name`
- `country`
- `decorations`
- `pictureUrl`

### `_Player`

Constructors/factories:
- `_Player::_Player(CSJSONObject const*)`

JSON keys referenced directly:
- `clan`
- `deckTheme`
- `cards`
- `runes`

### `_Profile`

Constructors/factories:
- `_Profile::_Profile(CSJSONObject const*)`

JSON keys referenced directly:
- `clan`
- `deckTheme`
- `cards`
- `runes`
- `achievementPoint`
- `cardCounts`

### `_User`

Constructors/factories:
- `_User::_User(CSJSONObject const*)`

JSON keys referenced directly:
- `clan`

## Lobby Request Payload Hints

For request functions, `endpoint` comes from the `sendPacket` string, and `body keys` are direct `CSJSONWriter::write*` key strings.

| Request function | Endpoint | Body keys |
| --- | --- | --- |
| `LobbyGateway::requestAchievementReward(AssetIndex2 const&)` | `api/client-secure/achievement/reward` | `achievementId` |
| `LobbyGateway::requestAdAnalysis(char const*, AdInflow)` |  |  |
| `LobbyGateway::requestAdDailyReward()` | `api/client-secure/ad/daily-reward` |  |
| `LobbyGateway::requestAdGameReward(long)` | `api/client-secure/game/ad-reward` | `matchId` |
| `LobbyGateway::requestAdRefresh()` | `api/client-secure/ad/refresh` |  |
| `LobbyGateway::requestAdmission()` | `api/client/admission` | `userId`, `secret`, `version`, `language`, `region`, `market`, `signal` |
| `LobbyGateway::requestArenaEnd()` | `api/client-secure/arena/end` |  |
| `LobbyGateway::requestArenaPick(AssetIndex2 const&)` | `api/client-secure/arena/pick` | `cardId` |
| `LobbyGateway::requestArenaReward()` | `api/client-secure/arena/reward` |  |
| `LobbyGateway::requestArenaRunes()` | `api/client-secure/arena/runes` | `runeIds` |
| `LobbyGateway::requestArenaStart(bool)` | `api/client-secure/arena/start` | `byGold` |
| `LobbyGateway::requestAttain(AttainCode, unsigned int, unsigned int, unsigned int, bool)` |  |  |
| `LobbyGateway::requestBanners()` | `api/client-secure/banners` |  |
| `LobbyGateway::requestBuyCard(int, AssetIndex2 const&, int)` | `api/client-secure/shop/buy-card` | `slot`, `cardId`, `count` |
| `LobbyGateway::requestBuyCardOpen(AssetIndex2 const&)` | `api/client-secure/shop/buy-card-open` | `cardId` |
| `LobbyGateway::requestBuyCardReset(bool)` | `api/client-secure/shop/buy-card-reset` | `byCash` |
| `LobbyGateway::requestBuyDeckPage()` | `api/client-secure/shop/buy-deck-page` |  |
| `LobbyGateway::requestBuyProduct(ProductCategory, AssetIndex2 const&, bool)` | `api/client-secure/shop/buy-product-validate`, `api/client-secure/shop/buy-product` | `category`, `productId`, `byCash`, `updateTime` |
| `LobbyGateway::requestBuyProductCharge(long, ProductCategory, AssetIndex2 const&, char const*, char const*, char const*)` | `api/client-secure/shop/buy-product-charge` | `transaction`, `category`, `productId`, `token0`, `token1`, `token2` |
| `LobbyGateway::requestCampaignStep(int)` | `api/client-secure/game/campaign-step` | `stage` |
| `LobbyGateway::requestCardConfirm(AssetIndex2 const&)` | `api/client-secure/deck/card-confirm` | `cardId` |
| `LobbyGateway::requestCardEquip(int, int, AssetIndex2 const&)` | `api/client-secure/deck/card-equip` | `page`, `slot`, `cardId` |
| `LobbyGateway::requestCardEquipAll(int, AssetIndex2 const*)` | `api/client-secure/deck/card-equip-all` | `page`, `cardIds` |
| `LobbyGateway::requestCardMake(AssetIndex2 const&, int)` | `api/client-secure/deck/card-make` | `cardId`, `count` |
| `LobbyGateway::requestCardShop()` | `api/client-secure/shop/card-info` |  |
| `LobbyGateway::requestCardUpgrade(AssetIndex2 const&)` | `api/client-secure/deck/card-upgrade` | `cardId` |
| `LobbyGateway::requestChallengeBonusGold(AssetIndex2 const&)` | `api/client-secure/challenge/bonus` | `challengeId` |
| `LobbyGateway::requestChallengeLimitOpen(AssetIndex2 const&)` | `api/client-secure/challenge-reward/slot-open` | `challengeId` |
| `LobbyGateway::requestChallengeReset()` | `api/client-secure/challenge-reset` |  |
| `LobbyGateway::requestChallengeReward(AssetIndex2 const&, bool, int)` | `api/client-secure/challenge-reward` | `challengeId`, `pass`, `rewardIndex` |
| `LobbyGateway::requestChangeCountry(int)` | `api/client-secure/profile/change-country` | `country` |
| `LobbyGateway::requestChangeDescription(char const*)` | `api/client-secure/profile/change-description` | `description` |
| `LobbyGateway::requestChangeName(char const*)` | `api/client-secure/profile/change-name` | `name` |
| `LobbyGateway::requestChangePicture(char const*)` | `api/client-secure/change-picture` | `pictureUrl` |
| `LobbyGateway::requestCheatLog(CheatAction)` | `api/client-secure/cheat-log` | `action` |
| `LobbyGateway::requestClanAccept(long, long)` | `api/client-secure/clan/accept` | `clanPostId`, `userId`, `updateTime` |
| `LobbyGateway::requestClanAppoint(long, ClanMemberAuth)` | `api/client-secure/clan/appoint` | `userId`, `memberAuth`, `updateTime` |
| `LobbyGateway::requestClanArenaCardEquip(int, AssetIndex2 const&)` | `api/client-secure/clan/arena-card-equip` | `slot`, `cardId` |
| `LobbyGateway::requestClanArenaReward()` | `api/client-secure/clan/arena-reward` |  |
| `LobbyGateway::requestClanArenaRuneEquip(int, int, AssetIndex2 const&)` | `api/client-secure/clan/arena-rune-equip` | `tier`, `slot`, `runeId` |
| `LobbyGateway::requestClanArenaRuneEquipAll(AssetIndex2 const (*) [4])` | `api/client-secure/clan/arena-rune-equip-all` | `runeIds` |
| `LobbyGateway::requestClanArenaValidate()` | `api/client-secure/clan/arena-validate` |  |
| `LobbyGateway::requestClanChangeNotice(char const*)` | `api/client-secure/clan/change-notice` | `notice`, `updateTime` |
| `LobbyGateway::requestClanCreate(AssetIndex2 const*, char const*, char const*, int, unsigned int, ClanOpenType)` | `api/client-secure/clan/create` | `name`, `description`, `decorations`, `country`, `joinScore`, `openType` |
| `LobbyGateway::requestClanDeckShare(int, char const*)` | `api/client-secure/clan/deck-share` | `page`, `description` |
| `LobbyGateway::requestClanDecorationEquip(ClanDecorationType, AssetIndex2 const&)` | `api/client-secure/clan/deco-equip` | `type`, `decoration`, `updateTime` |
| `LobbyGateway::requestClanDeny(long, long)` | `api/client-secure/clan/deny` | `clanPostId`, `userId`, `updateTime` |
| `LobbyGateway::requestClanDenyAll()` | `api/client-secure/clan/deny-all` | `updateTime` |
| `LobbyGateway::requestClanDonate(long, bool)` | `api/client-secure/clan/donate` | `clanPostId`, `byMaterial`, `updateTime` |
| `LobbyGateway::requestClanDonateRegister(AssetIndex2 const&)` | `api/client-secure/clan/donate-register` | `cardId`, `updateTime` |
| `LobbyGateway::requestClanDonateUnregister(long)` | `api/client-secure/clan/donate-unregister` | `clanPostId`, `updateTime` |
| `LobbyGateway::requestClanExpulse(long)` | `api/client-secure/clan/expulse` | `userId`, `updateTime` |
| `LobbyGateway::requestClanJoin(long)` | `api/client-secure/clan/join` | `clanId` |
| `LobbyGateway::requestClanLeave()` | `api/client-secure/clan/leave` |  |
| `LobbyGateway::requestClanModify(char const*, char const*, int, unsigned int, ClanOpenType)` | `api/client-secure/clan/modify` | `name`, `description`, `country`, `joinScore`, `openType`, `updateTime` |
| `LobbyGateway::requestClanProfile(long)` | `api/client-secure/clan/profile` | `clanId` |
| `LobbyGateway::requestClanRankingList(ClanRankingType, bool)` | `api/client-secure/ranking/clan-list` | `order`, `from` |
| `LobbyGateway::requestClanRecommend(bool)` | `api/client-secure/clan/recommend` |  |
| `LobbyGateway::requestClanRefresh()` |  |  |
| `LobbyGateway::requestClanReplayShare(long, char const*)` | `api/client/clan/replay-share` | `userId`, `matchRecordId`, `description`, `file` |
| `LobbyGateway::requestClanSearch(char const*, LobbyGateway::ClanKeywordType, int, int, int, bool)` | `api/client-secure/clan/search` | `keyword`, `keywordType`, `minMemberCount`, `maxMemberCount`, `minJoinScore`, `joinEnabledOnly` |
| `LobbyGateway::requestClanTrade(long, AssetIndex2 const&)` | `api/client-secure/clan/trade` | `clanPostId`, `giveCardId`, `updateTime` |
| `LobbyGateway::requestClanTradeRegister(AssetIndex2 const&, CSArray<AssetIndex2, 1, true> const*)` | `api/client-secure/clan/trade-register` | `takeCardId`, `giveCardIds`, `updateTime` |
| `LobbyGateway::requestClanTradeUnregister(long)` | `api/client-secure/clan/trade-unregister` | `clanPostId`, `updateTime` |
| `LobbyGateway::requestClearSession()` |  |  |
| `LobbyGateway::requestCoupon(char const*)` | `api/client-secure/coupon` | `coupon` |
| `LobbyGateway::requestDeckChangeName(int, char const*)` | `api/client-secure/deck/change-name` | `page`, `name` |
| `LobbyGateway::requestDeckMode(DeckMode)` |  |  |
| `LobbyGateway::requestDeckPage(int)` | `api/client-secure/deck/set-page` | `page` |
| `LobbyGateway::requestDecorationEquip(UserDecorationType, AssetIndex2 const&)` | `api/client-secure/profile/deco-equip` | `type`, `decoration` |
| `LobbyGateway::requestDispose()` | `api/client-secure/social-link-remove` |  |
| `LobbyGateway::requestEmoticonConfirm(AssetIndex2 const&)` | `api/client-secure/emoticon/confirm` | `emoticonId` |
| `LobbyGateway::requestEmoticonEquip(AssetIndex2 const*)` | `api/client-secure/emoticon/equip` | `emoticons` |
| `LobbyGateway::requestFriendConfirm(FriendConfirmOp)` | `api/client-secure/friend/confirm` | `op` |
| `LobbyGateway::requestFriendRecommend()` | `api/client-secure/friend/recommend` |  |
| `LobbyGateway::requestGameModeReset()` | `api/client-secure/game/mode-reset` |  |
| `LobbyGateway::requestGamePrevResult(bool)` | `api/client-secure/game/prev-result` | `retry` |
| `LobbyGateway::requestGameResult()` | `api/client-secure/game/result` | `transaction` |
| `LobbyGateway::requestGameResultAttain(GameResultRecord const*)` |  |  |
| `LobbyGateway::requestGameRewardReset()` | `api/client-secure/game/reward-reset` |  |
| `LobbyGateway::requestIAPConnect()` |  |  |
| `LobbyGateway::requestIAPSync(long)` |  |  |
| `LobbyGateway::requestInvitation()` | `api/client-secure/invitation` |  |
| `LobbyGateway::requestInvitationInput(long)` | `api/client-secure/invitation/input` | `userId` |
| `LobbyGateway::requestInvitationReward(int)` | `api/client-secure/invitation/reward` | `count` |
| `LobbyGateway::requestLanguage()` | `api/client-secure/language` | `language` |
| `LobbyGateway::requestLevelQuestReward(int)` | `api/client-secure/level/reward` | `questId` |
| `LobbyGateway::requestLogin()` | `api/client/login` | `userId`, `secret`, `version`, `assetVersion`, `language`, `region`, `market` |
| `LobbyGateway::requestLoginAttain()` |  |  |
| `LobbyGateway::requestLogout()` |  |  |
| `LobbyGateway::requestMailConfirm(long)` | `api/client-secure/mail/confirm` | `mailId` |
| `LobbyGateway::requestMailList()` | `api/client-secure/mail/list` | `lastMailId` |
| `LobbyGateway::requestMailOpen(long)` | `api/client-secure/mail/open` | `mailId` |
| `LobbyGateway::requestMailOpenAll()` | `api/client-secure/mail/open-all` |  |
| `LobbyGateway::requestMailSend(long, char const*, char const*)` | `api/client-secure/offline-message` | `userId`, `title`, `description` |
| `LobbyGateway::requestMarketAttain(AttainCode, unsigned int, unsigned int, unsigned int, bool)` |  |  |
| `LobbyGateway::requestMasteryReward(AssetIndex2 const&)` | `api/client-secure/deck/mastery-reward` | `cardId` |
| `LobbyGateway::requestMatchRecordList(long)` | `api/client-secure/match-record/list` | `userId`, `lastMatchRecordId` |
| `LobbyGateway::requestMatchRecordLock(long, bool)` | `api/client-secure/match-record/lock` | `matchRecordId`, `lock` |
| `LobbyGateway::requestMinigameAttendance()` | `api/client-secure/minigame/attendance/info` |  |
| `LobbyGateway::requestMinigameAttendanceContinuousReward(int, int)` | `api/client-secure/minigame/attendance/ex-reward` | `eventId`, `rewardIndex` |
| `LobbyGateway::requestMinigameAttendanceReward(int)` | `api/client-secure/minigame/attendance/reward` | `eventId` |
| `LobbyGateway::requestMinigameBoard()` | `api/client-secure/minigame/board/info` |  |
| `LobbyGateway::requestMinigameBoardPlay(bool)` | `api/client-secure/minigame/board/play` | `byCash` |
| `LobbyGateway::requestMinigameQuest()` | `api/client-secure/minigame/quest/info` |  |
| `LobbyGateway::requestMinigameQuestPointReward(int, int)` | `api/client-secure/minigame/quest/point-reward` | `eventId`, `rewardIndex` |
| `LobbyGateway::requestMinigameQuestReward(AssetIndex2 const&)` | `api/client-secure/minigame/quest/reward` | `questId` |
| `LobbyGateway::requestMinigameRoulette()` | `api/client-secure/minigame/roulette/info` |  |
| `LobbyGateway::requestMinigameRoulettePlay(int)` | `api/client-secure/minigame/roulette/play` | `eventId` |
| `LobbyGateway::requestPVPServer()` | `api/client-secure/pvp-server` |  |
| `LobbyGateway::requestPatch(char const*)` |  |  |
| `LobbyGateway::requestPing()` | `api/client-secure/ping` |  |
| `LobbyGateway::requestProfile(long)` | `api/client-secure/profile` | `userId` |
| `LobbyGateway::requestProfileStat(long)` | `api/client-secure/profile/stat` | `userId` |
| `LobbyGateway::requestPushToken()` | `api/client-secure/push-token` | `token`, `enabled` |
| `LobbyGateway::requestQuestPointReward(LobbyGateway::QuestPointRewardType)` | `api/client-secure/quest/point-reward` | `type` |
| `LobbyGateway::requestQuestReward(AssetIndex2 const&)` | `api/client-secure/quest/reward` | `questId` |
| `LobbyGateway::requestQuestStatus()` | `api/client-secure/quest/status` |  |
| `LobbyGateway::requestRefresh(void (LobbyGateway::*)(CSJSONObject const*), LobbyOp)` | `api/client-secure/refresh` | `clanUpdateTime` |
| `LobbyGateway::requestReload()` | `api/client-secure/reload` |  |
| `LobbyGateway::requestReplayDownload(long, char const*)` |  |  |
| `LobbyGateway::requestReplayUpload(long)` | `api/client/replay/upload` | `userId`, `matchRecordId`, `file` |
| `LobbyGateway::requestRuneConfirm(AssetIndex2 const&)` | `api/client-secure/deck/rune-confirm` | `runeId` |
| `LobbyGateway::requestRuneEquip(int, int, int, AssetIndex2 const&)` | `api/client-secure/deck/rune-equip` | `page`, `tier`, `slot`, `runeId` |
| `LobbyGateway::requestRuneEquipAll(int, AssetIndex2 const (*) [4])` | `api/client-secure/deck/rune-equip-all` | `page`, `runeIds` |
| `LobbyGateway::requestRuneUpgrade(AssetIndex2 const&)` | `api/client-secure/deck/rune-upgrade` | `runeId` |
| `LobbyGateway::requestScoreReward()` | `api/client-secure/score/reward` |  |
| `LobbyGateway::requestSeasonResult()` | `api/client-secure/season-result` |  |
| `LobbyGateway::requestShop(bool)` | `api/client-secure/shop/info` | `updateTime` |
| `LobbyGateway::requestSkinEquip(AssetIndex3 const&)` | `api/client-secure/deck/skin-equip` | `cardId`, `skin` |
| `LobbyGateway::requestSocialLink(SocialPlatform, char const*)` | `api/client/social-link` | `userId`, `secret`, `socialPlatform`, `socialId`, `language`, `region`, `market` |
| `LobbyGateway::requestSocialLinkValidate(SocialPlatform, char const*)` | `api/client/social-link-validate` | `socialPlatform`, `socialId` |
| `LobbyGateway::requestSubscriptionReset()` | `api/client-secure/subscription-reset` |  |
| `LobbyGateway::requestTVLiveList(bool)` | `api/client-secure/tv-live/list` |  |
| `LobbyGateway::requestTVReplayList(int)` | `api/client-secure/tv-replay/list` | `divisionGroup`, `lastMatchRecordId` |
| `LobbyGateway::requestTVReplayUploadVerify(long, int)` | `api/client-secure/tv-replay/upload-verify` | `matchRecordId`, `valuation` |
| `LobbyGateway::requestThemeEquip(AssetIndex2 const&)` | `api/client-secure/deck/theme-equip` | `deckTheme` |
| `LobbyGateway::requestTutorialStep(TutorialCategory, int, bool)` | `api/client-secure/tutorial/step` | `category`, `step`, `skip` |
| `LobbyGateway::requestUserRankingList(UserRecordType, bool, int)` | `api/client-secure/ranking/user-list` | `order`, `from`, `mapId` |
| `LobbyGateway::requestValidateAttain()` |  |  |

## Lobby Response Payload Hints

For receive functions, keys are direct `CSJSONObject::*ForKey` or `containsKey` string references in that handler. Many handlers delegate nested parsing to data classes listed above.

| Receive function | Keys read/checked directly |
| --- | --- |
| `LobbyGateway::receiveAchievementAttain(CSJSONObject const*)` | `achievementPoint`, `achievements`, `progress`, `state` |
| `LobbyGateway::receiveAchievementReward(CSJSONObject const*)` | `achievementId`, `achievementPoint`, `rewardResult` |
| `LobbyGateway::receiveAdDailyReward(CSJSONObject const*)` | `dailyRewardStep`, `dailyRewardRemainTime`, `rewardResult` |
| `LobbyGateway::receiveAdGameReward(CSJSONObject const*)` | `gameRewardRemaining`, `rewardResult` |
| `LobbyGateway::receiveAdRefresh(CSJSONObject const*)` | `ad` |
| `LobbyGateway::receiveAdmission(CSJSONObject const*)` | `result`, `assetVersion`, `iosReview`, `patchHosts`, `downloadUrl`, `host`, `notices`, `inviteUrl`, `revision` |
| `LobbyGateway::receiveArenaEnd(CSJSONObject const*)` | `arena` |
| `LobbyGateway::receiveArenaPick(CSJSONObject const*)` | `card`, `cardPicks` |
| `LobbyGateway::receiveArenaReward(CSJSONObject const*)` | `rewardStep`, `rewardResult` |
| `LobbyGateway::receiveArenaRunes(CSJSONObject const*)` | `runes` |
| `LobbyGateway::receiveArenaStart(CSJSONObject const*)` | `gold`, `arenaTicket`, `weeklyTry`, `cardPicks` |
| `LobbyGateway::receiveBanners(CSJSONObject const*)` | `banners` |
| `LobbyGateway::receiveBuyCard(CSJSONObject const*)` | `slot`, `cardId`, `count`, `remaining`, `rewardResult` |
| `LobbyGateway::receiveBuyCardOpen(CSJSONObject const*)` | `cardId`, `rewardResult` |
| `LobbyGateway::receiveBuyCardReset(CSJSONObject const*)` | `cardShop`, `cardResetTicket`, `cash` |
| `LobbyGateway::receiveBuyDeckPage(CSJSONObject const*)` | `rewardResult` |
| `LobbyGateway::receiveBuyProduct(CSJSONObject const*)` | `result`, `productId`, `rewardResult` |
| `LobbyGateway::receiveBuyProductCharge(CSJSONObject const*)` | `transaction`, `productId`, `result`, `rewardResult` |
| `LobbyGateway::receiveBuyProductValidate(CSJSONObject const*)` | `result`, `category`, `productId` |
| `LobbyGateway::receiveCampaignStep(CSJSONObject const*)` | `campaignStages` |
| `LobbyGateway::receiveCardConfirm(CSJSONObject const*)` | `cardId` |
| `LobbyGateway::receiveCardEquip(CSJSONObject const*)` | `page`, `slot`, `cardId` |
| `LobbyGateway::receiveCardEquipAll(CSJSONObject const*)` | `page`, `cards` |
| `LobbyGateway::receiveCardMake(CSJSONObject const*)` | `cardId`, `count`, `rewardResult` |
| `LobbyGateway::receiveCardShop(CSJSONObject const*)` | `cardShop` |
| `LobbyGateway::receiveCardUpgrade(CSJSONObject const*)` | `cardId`, `rewardResult` |
| `LobbyGateway::receiveChallengeBonusGold(CSJSONObject const*)` | `challengeId`, `rewardResult` |
| `LobbyGateway::receiveChallengeLimitOpen(CSJSONObject const*)` | `cash`, `challengeId`, `point`, `limitPoint` |
| `LobbyGateway::receiveChallengeReset(CSJSONObject const*)` | `challenges`, `challengeRemainTime` |
| `LobbyGateway::receiveChallengeReward(CSJSONObject const*)` | `challengeId`, `pass`, `rewardIndex`, `rewardResult` |
| `LobbyGateway::receiveChangeCountry(CSJSONObject const*)` | `country`, `countryTicket` |
| `LobbyGateway::receiveChangeDescription(CSJSONObject const*)` | `description` |
| `LobbyGateway::receiveChangeName(CSJSONObject const*)` | `result`, `name`, `nameTicket`, `nameRemainTime` |
| `LobbyGateway::receiveChangePicture(CSJSONObject const*)` | `pictureUrl` |
| `LobbyGateway::receiveCheatLog(CSJSONObject const*)` | `action` |
| `LobbyGateway::receiveClanAccept(CSJSONObject const*)` | `userId`, `clan` |
| `LobbyGateway::receiveClanAppoint(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanArenaCardEquip(CSJSONObject const*)` | `slot`, `cardId` |
| `LobbyGateway::receiveClanArenaReward(CSJSONObject const*)` | `rewardPoint`, `rewardResult` |
| `LobbyGateway::receiveClanArenaRuneEquip(CSJSONObject const*)` | `tier`, `slot`, `runeId` |
| `LobbyGateway::receiveClanArenaRuneEquipAll(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanArenaValidate(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanChangeNotice(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanCreate(CSJSONObject const*)` | `gold`, `clan` |
| `LobbyGateway::receiveClanDeckShare(CSJSONObject const*)` | `result` |
| `LobbyGateway::receiveClanDecorationEquip(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanDeny(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanDenyAll(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanDonate(CSJSONObject const*)` | `clan`, `result`, `rewardResult` |
| `LobbyGateway::receiveClanDonateRegister(CSJSONObject const*)` | `clan`, `clanToken` |
| `LobbyGateway::receiveClanDonateUnregister(CSJSONObject const*)` | `clan`, `clanToken` |
| `LobbyGateway::receiveClanExpulse(CSJSONObject const*)` | `userId`, `clan` |
| `LobbyGateway::receiveClanJoin(CSJSONObject const*)` | `clanId`, `clan` |
| `LobbyGateway::receiveClanLeave(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanModify(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanProfile(CSJSONObject const*)` | `clan` |
| `LobbyGateway::receiveClanRankingList(CSJSONObject const*)` | `order`, `from`, `clans` |
| `LobbyGateway::receiveClanRecommend(CSJSONObject const*)` | `clans` |
| `LobbyGateway::receiveClanRefresh(CSJSONObject const*)` |  |
| `LobbyGateway::receiveClanReplayShare(CSJSONObject const*)` | `result` |
| `LobbyGateway::receiveClanSearch(CSJSONObject const*)` | `clans` |
| `LobbyGateway::receiveClanTrade(CSJSONObject const*)` | `clan`, `result`, `rewardResult` |
| `LobbyGateway::receiveClanTradeRegister(CSJSONObject const*)` | `clan`, `clanToken`, `giveCards` |
| `LobbyGateway::receiveClanTradeUnregister(CSJSONObject const*)` | `clan`, `clanToken`, `giveCards` |
| `LobbyGateway::receiveCoupon(CSJSONObject const*)` | `result` |
| `LobbyGateway::receiveDeckChangeName(CSJSONObject const*)` | `page`, `name` |
| `LobbyGateway::receiveDeckPage(CSJSONObject const*)` | `page` |
| `LobbyGateway::receiveDecorationEquip(CSJSONObject const*)` | `type`, `decoration` |
| `LobbyGateway::receiveDispose(CSJSONObject const*)` | `result` |
| `LobbyGateway::receiveEmoticonConfirm(CSJSONObject const*)` | `emoticonId` |
| `LobbyGateway::receiveEmoticonEquip(CSJSONObject const*)` | `emoticons` |
| `LobbyGateway::receiveFriendConfirm(CSJSONObject const*)` | `op` |
| `LobbyGateway::receiveFriendRecommend(CSJSONObject const*)` | `users` |
| `LobbyGateway::receiveGameModeReset(CSJSONObject const*)` | `gameModeStatus` |
| `LobbyGateway::receiveGamePrevResult(CSJSONObject const*)` | `result`, `defeat`, `retry`, `rewardResults` |
| `LobbyGateway::receiveGameResult(CSJSONObject const*)` | `transaction`, `rewardResult` |
| `LobbyGateway::receiveGameRewardReset(CSJSONObject const*)` | `gameRewardLimits` |
| `LobbyGateway::receiveInvitation(CSJSONObject const*)` | `invitation` |
| `LobbyGateway::receiveInvitationInput(CSJSONObject const*)` | `rewardResult` |
| `LobbyGateway::receiveInvitationReward(CSJSONObject const*)` | `count`, `rewardResult` |
| `LobbyGateway::receiveLanguage(CSJSONObject const*)` | `notices` |
| `LobbyGateway::receiveLevelQuestAttain(CSJSONObject const*)` | `quests`, `progress`, `state` |
| `LobbyGateway::receiveLevelQuestReward(CSJSONObject const*)` | `questId`, `rewardResult` |
| `LobbyGateway::receiveLogin(CSJSONObject const*)` | `result`, `account`, `dayChanged`, `message` |
| `LobbyGateway::receiveMailConfirm(CSJSONObject const*)` | `mailId` |
| `LobbyGateway::receiveMailList(CSJSONObject const*)` | `mails` |
| `LobbyGateway::receiveMailOpen(CSJSONObject const*)` | `mailId`, `rewardResult` |
| `LobbyGateway::receiveMailOpenAll(CSJSONObject const*)` | `rewardResult` |
| `LobbyGateway::receiveMailSend(CSJSONObject const*)` | `success` |
| `LobbyGateway::receiveMasteryReward(CSJSONObject const*)` | `cardId`, `masteryRewardPoint`, `rewardResult` |
| `LobbyGateway::receiveMatchRecordList(CSJSONObject const*)` | `userId`, `matchRecords` |
| `LobbyGateway::receiveMatchRecordLock(CSJSONObject const*)` | `matchRecordId`, `lock` |
| `LobbyGateway::receiveMinigameAttendance(CSJSONObject const*)` | `attendances` |
| `LobbyGateway::receiveMinigameAttendanceContinuousReward(CSJSONObject const*)` | `eventId`, `rewardIndex`, `remainRefreshTime`, `rewardResult` |
| `LobbyGateway::receiveMinigameAttendanceReward(CSJSONObject const*)` | `eventId`, `rewardDay`, `remainRefreshTime`, `rewardResult` |
| `LobbyGateway::receiveMinigameBoard(CSJSONObject const*)` | `board` |
| `LobbyGateway::receiveMinigameBoardPlay(CSJSONObject const*)` | `remainPlayTime`, `currentPosition`, `rewardIndex`, `diceNumber`, `rewardResult` |
| `LobbyGateway::receiveMinigameQuest(CSJSONObject const*)` | `quests` |
| `LobbyGateway::receiveMinigameQuestAttain(CSJSONObject const*)` | `quests`, `questId`, `progress` |
| `LobbyGateway::receiveMinigameQuestPointReward(CSJSONObject const*)` | `eventId`, `rewardIndex`, `rewardResult` |
| `LobbyGateway::receiveMinigameQuestReward(CSJSONObject const*)` | `questId`, `point`, `rewardResult` |
| `LobbyGateway::receiveMinigameRoulette(CSJSONObject const*)` | `roulettes` |
| `LobbyGateway::receiveMinigameRoulettePlay(CSJSONObject const*)` | `eventId`, `roulette`, `rewardResult`, `payment`, `accum`, `point`, `dailyCount`, `dailyLimit`, `remainCountRefreshTime`, `remainNextTime`, `remainTime`, `rewards` |
| `LobbyGateway::receiveMyClanProfile(CSJSONObject const*)` |  |
| `LobbyGateway::receiveMyProfile(CSJSONObject const*)` |  |
| `LobbyGateway::receivePVPServer(CSJSONObject const*)` | `host` |
| `LobbyGateway::receivePing(CSJSONObject const*)` | `hasNewMail`, `hasNewInvitationReward`, `hotTimeEvents`, `clanRewardResult`, `clanDonaters`, `clanTradeRecord`, `user`, `takeCard`, `giveCard` |
| `LobbyGateway::receiveProfile(CSJSONObject const*)` | `profile` |
| `LobbyGateway::receiveProfileStat(CSJSONObject const*)` | `userId`, `stat` |
| `LobbyGateway::receiveQuestAttain(CSJSONObject const*)` | `quests`, `progress`, `state` |
| `LobbyGateway::receiveQuestPointReward(CSJSONObject const*)` | `dailyRewardStep`, `weeklyRewardStep`, `rewardResult` |
| `LobbyGateway::receiveQuestReward(CSJSONObject const*)` | `questId`, `rewardResult` |
| `LobbyGateway::receiveQuestStatus(CSJSONObject const*)` | `questStatus` |
| `LobbyGateway::receiveRefresh(CSJSONObject const*, LobbyOp)` | `rankingPrivate`, `rankingTeam`, `clanRewardResult`, `clanDonaters`, `clanTradeRecord`, `user`, `takeCard`, `giveCard`, `clanReset`, `clan`, `clanId` |
| `LobbyGateway::receiveReload(CSJSONObject const*)` | `account` |
| `LobbyGateway::receiveReplayUpload(CSJSONObject const*)` | `matchRecordId` |
| `LobbyGateway::receiveRewardResult(CSJSONObject const*, char const*)` | `rewards`, `level`, `exp`, `recordPrivate`, `recordTeam`, `cash`, `gold`, `medal`, `badge`, `socialCoin`, `clanToken`, `cardResetTicket`, `nameTicket`, `countryTicket`, `arenaTicket`, `cards`, `cardId`, `skin`, `count`, `masteryLevel`, `masteryPoint`, `runes`, `deckPageCount`, `skins`, `decorations`, `boosters`, `challenges`, `subscriptions`, `remainTime`, `themes`, `emoticons`, `questDailyPoint`, `questWeeklyPoint`, `campaignStages`, `gameRewardLimits`, `minigamePoints`, `clanDivision`, `clanPoint`, `clanScore`, `clanPointRanking`, `clanScoreRanking`, `clanArena`, `arenaWin`, `arenaLose`, `shop`, `adGameRewardGold` |
| `LobbyGateway::receiveRuneConfirm(CSJSONObject const*)` | `runeId` |
| `LobbyGateway::receiveRuneEquip(CSJSONObject const*)` | `page`, `tier`, `slot`, `runeId` |
| `LobbyGateway::receiveRuneEquipAll(CSJSONObject const*)` | `page`, `runes` |
| `LobbyGateway::receiveRuneUpgrade(CSJSONObject const*)` | `runeId`, `rewardResult` |
| `LobbyGateway::receiveScoreReward(CSJSONObject const*)` | `scoreRewardObtain`, `rewardResult` |
| `LobbyGateway::receiveSeasonResult(CSJSONObject const*)` | `season`, `seasonRemainTime`, `seasonResultPrivate`, `seasonResultTeam`, `seasonResultClan`, `seasonReward`, `rewardResult` |
| `LobbyGateway::receiveShop(CSJSONObject const*)` | `shop` |
| `LobbyGateway::receiveSkinEquip(CSJSONObject const*)` | `cardId`, `skin` |
| `LobbyGateway::receiveSocialLink(CSJSONObject const*)` | `userId`, `secret`, `socialPlatform` |
| `LobbyGateway::receiveSocialLinkValidate(CSJSONObject const*)` | `user` |
| `LobbyGateway::receiveSubscriptionReset(CSJSONObject const*)` | `deckTheme`, `themes`, `decorations`, `allDecorations`, `subscriptions` |
| `LobbyGateway::receiveTVLiveList(CSJSONObject const*)` | `lives` |
| `LobbyGateway::receiveTVReplayList(CSJSONObject const*)` | `divisionGroup`, `firstMatchRecordId`, `replays` |
| `LobbyGateway::receiveTVReplayUploadVerify(CSJSONObject const*)` | `matchRecordId`, `result` |
| `LobbyGateway::receiveThemeEquip(CSJSONObject const*)` | `deckTheme` |
| `LobbyGateway::receiveTutorialStep(CSJSONObject const*)` | `category`, `step`, `skip`, `rewardResult` |
| `LobbyGateway::receiveUserRankingList(CSJSONObject const*)` | `order`, `from`, `ranking`, `score`, `users` |

## Observed Startup Payloads

Captured request bodies against the local mock backend:

`POST /api/client/admission`

```json
{"secret":"<uuid>","version":"2.5.1.338","language":"en","region":"US","market":1}
```

Some admission requests also include a `signal` crash-report string.

`POST /api/client/login`

```json
{"secret":"<uuid>","version":"2.5.1.338","assetVersion":0,"language":"en","region":"US","market":1}
```

