#!/usr/bin/env python3
"""Local ACIES endpoint capture server.

By default this records request shapes and returns handled application errors.
Use --guest-success to try an offline, synthetic guest payload while mapping the
dead backend protocol.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import queue
import socket
import sqlite3
import socketserver
import struct
import subprocess
import threading
import time
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

if __package__:
    from .acies_accounts import AccountError, AccountStore, PlayerIdentity, digest, gateway_token
    from .acies_social import ChatMessage, SocialStore, valid_text
else:
    from acies_accounts import AccountError, AccountStore, PlayerIdentity, digest, gateway_token
    from acies_social import ChatMessage, SocialStore, valid_text


SESSION_ENCRYPTION_KEY = "localmockkey0001"
ASSET_VERSION = 83
ASSET_REVISION = 177
EMPTY_ASSET_ID = -1
COMPLETED_CAMPAIGN_STAGES = [0, 0, 0, 1, 1, 1]
CAMPAIGN_MISSION_COUNT = 7
DEFAULT_TUTORIAL_STAGE_COUNT = 3
LOBBY_TUTORIAL_CATEGORY_COUNT = 13
LOBBY_TUTORIAL_COMPLETE_STEP = 255  # ACIES stores each step in one unsigned byte.
DEFAULT_ADMISSION_URL = "http://10.0.2.2:8080"
DEFAULT_PVP_PORT = 9090
SEASON_REWARD_DIVISION_SLOTS = 31
LOCAL_SEASON_DURATION = 30 * 24 * 3600
LOCAL_SAMPLE_PLAYERS = ("Demo Ember", "Demo Cedar", "Demo Iris", "Demo Quartz", "Demo Vale")
LOCAL_STARTING_GOLD = 100_000
LOCAL_STARTING_CRYSTALS = 100_000
LOCAL_CARD_PRICE = 100
LOCAL_CARD_STOCK = 5
LOCAL_CARD_OFFER_COUNT = 3
STARTER_CARD_IDS = [
    (3 << 16) | 0,   # Hound
    (3 << 16) | 1,   # Swordsman
    (3 << 16) | 2,   # Archer
    (3 << 16) | 5,   # Skull Rogue
    (3 << 16) | 9,   # Berserker
    (3 << 16) | 10,  # Healer
    (4 << 16) | 0,   # Watch Tower
    (5 << 16) | 2,   # Fireball
]
MAX_HTTP_BODY = 64 * 1024


class MockState:
    def __init__(
        self,
        *,
        tutorial_stages: bool,
        tutorial_stage_count: int,
        admission_url: str = DEFAULT_ADMISSION_URL,
        pvp_port: int = DEFAULT_PVP_PORT,
        state_db: Path | None = None,
        user_id: int = 1000001,
        name: str = "LocalGuest",
        accounts: AccountStore | None = None,
    ) -> None:
        self.admission_url = admission_url
        self.pvp_port = pvp_port
        self.tutorial_stages = tutorial_stages
        self.tutorial_stage_count = tutorial_stage_count
        self.user_id = user_id
        self.name = name
        self.accounts = accounts
        self.social: SocialStore | None = None
        self.secret = "local-offline-secret" if name == "LocalGuest" else f"local-guest-{user_id}"
        self._lock = threading.Lock()
        self._completed_tutorial_stages = 0
        self._won_campaign_stages: set[int] = set()
        self._tutorial_steps: dict[str, int] = {}
        self._legacy_completed_campaign = False
        self._deck_name = "Local Deck"
        self._deck_cards = list(STARTER_CARD_IDS)
        self._card_purchases = [0] * LOCAL_CARD_OFFER_COUNT
        self._db = sqlite3.connect(state_db, check_same_thread=False) if state_db else None
        if self._db is not None:
            with self._db:
                self._db.execute("CREATE TABLE IF NOT EXISTS guest_state (key TEXT PRIMARY KEY, value NOT NULL)")
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS battle_results (transaction_id INTEGER PRIMARY KEY, result_json TEXT NOT NULL)"
                )
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS lan_match_results "
                    "(match_id INTEGER PRIMARY KEY, opponent_id INTEGER NOT NULL, outcome INTEGER NOT NULL)"
                )
                saved = dict(self._db.execute("SELECT key, value FROM guest_state"))
                battles = [json.loads(result) for result, in self._db.execute("SELECT result_json FROM battle_results")]
        elif accounts is not None:
            saved, battles = accounts.progress(user_id)
        else:
            return
        for battle in battles:
            stage = won_campaign_stage(battle)
            if stage is not None:
                self._won_campaign_stages.add(stage)
        # Older community accounts started with the campaign tutorial cleared.
        self._legacy_completed_campaign = accounts is not None and "tutorial_stages" not in saved
        self._completed_tutorial_stages = int(saved.get(
            "tutorial_stages", self.tutorial_stage_count if self._legacy_completed_campaign else 0,
        ))
        if "tutorial_steps" in saved:
            self._tutorial_steps = json.loads(saved["tutorial_steps"])
        self._deck_name = str(saved.get("deck_name", self._deck_name))
        if "deck_cards" in saved:
            self._deck_cards = json.loads(saved["deck_cards"])
        if "card_purchases" in saved:
            self._card_purchases = json.loads(saved["card_purchases"])

    def reset_login_progress(self) -> None:
        if not self.tutorial_stages or self._db is not None or self.accounts is not None:
            return
        with self._lock:
            self._completed_tutorial_stages = 0
            self._won_campaign_stages.clear()

    def save_lan_match_result(self, match_id: int, opponent_id: int, outcome: int) -> None:
        if self._db is not None:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT OR IGNORE INTO lan_match_results VALUES (?, ?, ?)",
                    (match_id, opponent_id, outcome),
                )

    def lan_match_counts(self) -> tuple[int, int]:
        if self.accounts is not None:
            return self.accounts.match_counts(self.user_id)
        if self._db is None:
            return (0, 0)
        with self._lock:
            return self._db.execute(
                "SELECT COUNT(*), COUNT(CASE WHEN outcome = 1 THEN 1 END) FROM lan_match_results"
            ).fetchone()

    def campaign_stages(self) -> list[int]:
        with self._lock:
            return self._campaign_stages_locked()

    def campaign_tutorial_complete(self) -> bool:
        if not self.tutorial_stages:
            return True
        with self._lock:
            return self._completed_tutorial_stages >= self.tutorial_stage_count

    def advance_campaign_stage(self, request: dict[str, object], *, record_result: bool = False) -> list[int]:
        requested_stage = campaign_stage_from_request(request)
        with self._lock:
            stages = self._completed_tutorial_stages
            battle = request.get("result") if record_result else None
            won_stage = won_campaign_stage(battle)
            won_or_stepped = not record_result or (isinstance(battle, dict) and battle.get("result") == 1)
            if self.accounts is not None:
                if record_result:
                    requested_stage = won_stage
                if requested_stage != stages + 1:
                    requested_stage = None
            if self.tutorial_stages and requested_stage is not None and won_or_stepped:
                stages = max(stages, min(requested_stage, self.tutorial_stage_count))
            if self.accounts is not None:
                new_stages = stages if stages != self._completed_tutorial_stages else None
                if not self.accounts.save_campaign(self.user_id, new_stages, request.get("transaction"), battle):
                    return self._campaign_stages_locked()
            elif self._db is not None:
                with self._db:
                    transaction = request.get("transaction")
                    if isinstance(battle, dict) and type(transaction) is int and 0 < transaction < 2**63:
                        inserted = self._db.execute(
                            "INSERT OR IGNORE INTO battle_results VALUES (?, ?)",
                            (transaction, json.dumps(battle)),
                        ).rowcount
                        if not inserted:
                            return self._campaign_stages_locked()
                    if stages != self._completed_tutorial_stages:
                        self._db.execute("INSERT OR REPLACE INTO guest_state VALUES ('tutorial_stages', ?)", (stages,))
            self._completed_tutorial_stages = stages
            if won_stage is not None:
                self._won_campaign_stages.add(won_stage)
            return self._campaign_stages_locked()

    def _campaign_stages_locked(self) -> list[int]:
        if self.accounts is not None and not self._legacy_completed_campaign:
            count = self._completed_tutorial_stages
            if count >= self.tutorial_stage_count:
                count = min(max(count, max(self._won_campaign_stages, default=0)) + 1, CAMPAIGN_MISSION_COUNT)
            stages = [0] * count
        elif not self.tutorial_stages or self._completed_tutorial_stages >= self.tutorial_stage_count:
            stages = list(COMPLETED_CAMPAIGN_STAGES)
            if CAMPAIGN_MISSION_COUNT - 1 in self._won_campaign_stages:
                stages.append(0)
        else:
            stages = [0] * self._completed_tutorial_stages
        for stage in self._won_campaign_stages:
            if stage <= len(stages):
                stages[stage - 1] = 1
        return stages

    def _save_locked(self, key: str, value: str | int) -> None:
        if self.accounts is not None:
            self.accounts.save_progress(self.user_id, key, value)
        elif self._db is not None:
            with self._db:
                self._db.execute("INSERT OR REPLACE INTO guest_state VALUES (?, ?)", (key, value))

    def onboarding_progress(self) -> tuple[list[int], list[dict[str, int]]]:
        with self._lock:
            steps = self._tutorial_steps.copy()
            if self.accounts is not None and self._completed_tutorial_stages >= self.tutorial_stage_count:
                # The lobby walkthrough depends on the old shop. Completing its
                # category also restores all five feature unlocks on login.
                steps["0"] = LOBBY_TUTORIAL_COMPLETE_STEP
            return self._campaign_stages_locked(), [
                {"category": int(category), "step": step} for category, step in steps.items()
            ]

    def advance_tutorial_step(self, category: int, step: int, skip: bool) -> int:
        with self._lock:
            key = str(category)
            previous = self._tutorial_steps.get(key, 0)
            # The preserved lobby script reaches an unsupported shop step.
            # Completing category zero also opens its five feature gates.
            if skip or (category == 0 and self._completed_tutorial_stages >= self.tutorial_stage_count):
                step = LOBBY_TUTORIAL_COMPLETE_STEP
            step = max(previous, step)
            if step != previous:
                steps = {**self._tutorial_steps, key: step}
                self._save_locked("tutorial_steps", json.dumps(steps))
                self._tutorial_steps = steps
            return step

    def deck(self) -> dict[str, object]:
        with self._lock:
            return starter_deck(self._deck_name, self._deck_cards)

    def rename_deck(self, name: object) -> str:
        with self._lock:
            if isinstance(name, str) and 1 <= len(name) <= 32 and (self.accounts is None or valid_text(name, 127)):
                self._save_locked("deck_name", name)
                self._deck_name = name
            return self._deck_name

    def equip_cards(self, cards: object) -> list[int]:
        with self._lock:
            if (
                isinstance(cards, list)
                and len(cards) == len(STARTER_CARD_IDS)
                and all(type(card) is int for card in cards)
                and set(cards) == set(STARTER_CARD_IDS)
            ):
                self._set_cards_locked(cards)
            return list(self._deck_cards)

    def equip_card(self, slot: object, card: object) -> tuple[int, int]:
        with self._lock:
            if type(slot) is not int or not 0 <= slot < len(self._deck_cards):
                return 0, self._deck_cards[0]
            if type(card) is int and card in self._deck_cards:
                cards = list(self._deck_cards)
                previous_slot = cards.index(card)
                cards[previous_slot], cards[slot] = cards[slot], cards[previous_slot]
                self._set_cards_locked(cards)
            return slot, self._deck_cards[slot]

    def _set_cards_locked(self, cards: list[int]) -> None:
        self._save_locked("deck_cards", json.dumps(cards))
        self._deck_cards = list(cards)

    def card_purchases(self) -> list[int]:
        with self._lock:
            return list(self._card_purchases)

    def gold(self, purchases: list[int] | None = None) -> int:
        amount = local_gold(self.card_purchases() if purchases is None else purchases)
        if self.social is not None:
            amount -= self.social.gold_spent(self.user_id)
        return amount

    def change_clan(self, action: str, request: dict) -> dict | None:
        if self.social is None:
            return None
        with self._lock:
            change = self.social.change(self.user_id, action, request, gold=self.gold(self._card_purchases))
            if change is not None and action == "create":
                change["gold"] = self.gold(self._card_purchases)
            return change

    def buy_card(self, slot: int, card_id: int, count: int) -> tuple[int, list[int]]:
        with self._lock:
            purchases = list(self._card_purchases)
            if not 0 <= slot < len(purchases) or STARTER_CARD_IDS[slot] != card_id:
                return 0, purchases
            bought = min(count, LOCAL_CARD_STOCK - purchases[slot], self.gold(purchases) // LOCAL_CARD_PRICE)
            if bought <= 0:
                return 0, purchases
            purchases[slot] += bought
            self._save_locked("card_purchases", json.dumps(purchases))
            self._card_purchases = purchases
            return bought, list(purchases)


def campaign_stage_from_request(request: dict[str, object]) -> int | None:
    stage = request.get("stage")
    if type(stage) is int:
        return stage

    result = request.get("result")
    if not isinstance(result, dict):
        return None
    single = result.get("single")
    if not isinstance(single, dict):
        return None
    campaign_stage = single.get("campaignStage")
    return campaign_stage if type(campaign_stage) is int else None


def won_campaign_stage(battle: object) -> int | None:
    if not isinstance(battle, dict) or battle.get("mode") != 32 or battle.get("result") != 1:
        return None
    stage = campaign_stage_from_request({"result": battle})
    if type(stage) is int and 1 <= stage <= CAMPAIGN_MISSION_COUNT:
        return stage
    return None


def starter_card(card_id: int) -> dict[str, object]:
    return {
        "cardId": card_id,
        "level": 0,
        "skin": 0,
        "count": 20,
        "masteryLevel": 0,
        "masteryPoint": 0,
        "masteryRewardPoint": 0,
        "isNew": False,
    }


def starter_deck(name: str = "Local Deck", cards: list[int] = STARTER_CARD_IDS) -> dict[str, object]:
    return {
        "name": name,
        "cards": list(cards),
        "runes": [
            [EMPTY_ASSET_ID, EMPTY_ASSET_ID, EMPTY_ASSET_ID, EMPTY_ASSET_ID],
            [EMPTY_ASSET_ID, EMPTY_ASSET_ID, EMPTY_ASSET_ID, EMPTY_ASSET_ID],
            [EMPTY_ASSET_ID, EMPTY_ASSET_ID, EMPTY_ASSET_ID, EMPTY_ASSET_ID],
        ],
    }


def _aes_cipher(data: bytes, *, decrypt: bool) -> bytes | None:
    key = SESSION_ENCRYPTION_KEY.encode("utf-8")
    if len(key) == 16:
        cipher = "-aes-128-cbc"
    elif len(key) == 32:
        cipher = "-aes-256-cbc"
    else:
        raise ValueError("SESSION_ENCRYPTION_KEY must be 16 or 32 bytes")

    command = ["openssl", "enc", cipher, "-K", key.hex(), "-iv", key[:16].hex()]
    if decrypt:
        command.insert(2, "-d")

    result = subprocess.run(command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return None
    return result.stdout


def encrypt_secure_payload(payload: bytes) -> bytes:
    encrypted = _aes_cipher(payload, decrypt=False)
    if encrypted is None:
        raise RuntimeError("openssl failed to encrypt secure payload")
    return encrypted


def decrypt_secure_payload(payload: bytes) -> bytes | None:
    return _aes_cipher(payload, decrypt=True)


def request_json_for_path(path: str, body: bytes) -> dict[str, object]:
    if not body:
        return {}
    payload = decrypt_secure_payload(body) if path.startswith("/api/client-secure/") else body
    if payload is None:
        return {}
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def user_record(score: int = 0, ranking: int = 0) -> dict[str, int]:
    return {
        "score": score,
        "scoreHigh": score,
        "ranking": ranking,
        "division": 0,
        "divisionHigh": 0,
    }


def profile_stat() -> dict[str, int]:
    return {
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
        "rankTeamMaxScore": 0,
    }


def season_reward() -> dict[str, object]:
    return {
        "userRankingRewards": [],
        "clanRankingRewards": [],
        "divisionRewards": [
            [[] for _ in range(SEASON_REWARD_DIVISION_SLOTS)],
            [[] for _ in range(SEASON_REWARD_DIVISION_SLOTS)],
        ],
    }


def quest_status() -> dict[str, object]:
    return {
        "dailyRewards": [],
        "weeklyRewards": [],
        "dailyRewardStep": 0,
        "weeklyRewardStep": 0,
        "dailyPoint": 0,
        "weeklyPoint": 0,
        "remainTime": 0,
        "quests": [],
    }


def reward_result() -> dict[str, object]:
    return {
        "rewards": [],
    }


def shop_info() -> dict[str, object]:
    return {
        "updateTime": 0,
        "remainTime": 0,
        "products": [rune_workshop_product(0), rune_workshop_product(1)],
    }


def local_gold(purchases: list[int]) -> int:
    return LOCAL_STARTING_GOLD - sum(purchases) * LOCAL_CARD_PRICE


def card_shop_info(purchases: list[int]) -> dict[str, object]:
    return {
        "products": [
            {"cardId": card_id, "remaining": LOCAL_CARD_STOCK - bought, "free": False}
            for card_id, bought in zip(STARTER_CARD_IDS, purchases)
        ],
        "nextResetTicket": 0,
        "nextResetCash": 0,
        "remainTime": 0,
    }


def user_thumb(user_id: int = 1000001, name: str = "LocalGuest") -> dict[str, object]:
    return {
        "userId": user_id,
        "name": name,
        "country": 0,
        "decorations": [0, 0, 0, 0],
        "pictureUrl": "",
    }


def sample_players() -> list[dict[str, object]]:
    return [
        {
            **user_thumb(2000000 + rank, name),
            "level": 15 - rank,
            "recordPrivate": user_record(1500 - 125 * rank, rank),
            "recordTeam": user_record(1200 - 90 * rank, rank),
            "rankingDiff": 0,
            "description": "Sample player on the local server.",
        }
        for rank, name in enumerate(LOCAL_SAMPLE_PLAYERS, 1)
    ]


def ranking_response(request: dict[str, object]) -> dict[str, object]:
    order = request.get("order", 0)
    start = request.get("from", 0)
    return {
        "order": order if type(order) is int and 0 <= order <= 1 else 0,
        "from": start if type(start) is int and start >= 0 else 0,
        "ranking": len(LOCAL_SAMPLE_PLAYERS) + 1,
        "score": 0,
        "users": sample_players() if start == 0 else [],
    }


def public_profile(state: MockState, user_id: object) -> dict[str, object]:
    profile = mock_account(state.campaign_stages(), state.deck(), state.card_purchases())
    profile.update(user_thumb(state.user_id, state.name))
    for player in sample_players() if state.accounts is None else ():
        if user_id == player["userId"]:
            profile = mock_account([])
            profile.update(player)
            break
    inventory = {card["cardId"]: card for card in profile["allCards"]}
    profile["cards"] = [inventory[card_id] for card_id in profile["cards"]]
    profile["runes"] = []
    return {"profile": profile}


def buy_card_response(request: dict[str, object], state: MockState) -> dict[str, object]:
    slot = request.get("slot")
    card_id = request.get("cardId")
    count = request.get("count")
    if type(slot) is not int or not 0 <= slot < LOCAL_CARD_OFFER_COUNT:
        slot = 0
        count = 0
    if type(card_id) is not int:
        card_id = STARTER_CARD_IDS[slot]
        count = 0
    if type(count) is not int:
        count = 0
    bought, purchases = state.buy_card(slot, card_id, count)
    card = starter_card(STARTER_CARD_IDS[slot])
    card["count"] = 20 + purchases[slot]
    return {
        "slot": slot,
        "cardId": STARTER_CARD_IDS[slot],
        "count": bought,
        "remaining": LOCAL_CARD_STOCK - purchases[slot],
        "rewardResult": {"rewards": [], "gold": state.gold(purchases), "cards": [card] if bought else []},
    }


def season_result() -> dict[str, int]:
    return {
        "score": 0,
        "ranking": 0,
        "division": 0,
    }


def rune_workshop_product(product_id: int) -> dict[str, object]:
    return {
        "productId": product_id,
        "category": 9,
        "priceType": 0,
        "price": 100,
        "originPrice": 100,
        "cash": 0,
        "buyCount": 1,
        "buyLimit": 1,
        "repeat": False,
        "rewards": [],
    }


def mock_account(
    campaign_stages: list[int],
    deck: dict[str, object] | None = None,
    purchases: list[int] | None = None,
) -> dict[str, object]:
    if deck is None:
        deck = starter_deck()
    if purchases is None:
        purchases = [0] * LOCAL_CARD_OFFER_COUNT
    all_cards = [starter_card(card_id) for card_id in STARTER_CARD_IDS]
    for card, bought in zip(all_cards, purchases):
        card["count"] = 20 + bought
    card_counts = {card["cardId"]: card["count"] for card in all_cards}
    account: dict[str, object] = {
        "userId": 1000001,
        "name": "LocalGuest",
        "country": 0,
        "decorations": [0, 0, 0, 0],
        "pictureUrl": "",
        "level": 1,
        "recordPrivate": user_record(),
        "recordTeam": user_record(),
        "description": "",
        "achievementPoint": 0,
        "cards": deck["cards"],
        "runes": deck["runes"],
        "cardCounts": [card_counts[card_id] for card_id in deck["cards"]],
        "gold": local_gold(purchases),
        "cash": 0,
        "medal": 0,
        "badge": 0,
        "material": [LOCAL_STARTING_CRYSTALS, 0, 0],
        "mileage": [0, 0],
        "socialCoin": 0,
        "clanToken": 0,
        "cardResetTicket": 0,
        "nameTicket": 0,
        "nameRemainTime": 0,
        "countryTicket": 0,
        "countryChanged": False,
        "arenaTicket": 0,
        "allCards": all_cards,
        "allRunes": [],
        "deckTheme": 0,
        "deckPage": 0,
        "deckPageCount": 1,
        "decks": [deck],
        "allSkins": [],
        "allDecorations": [],
        "allEmoticons": [],
        "emoticons": [0, 0, 0, 0, 0, 0],
        "gameRewardLimits": [],
        "gameModeStatus": [],
        "arena": {"rewards": []},
        "scoreRewardObtain": 0,
        "questStatus": quest_status(),
        "achievements": [],
        "boosters": [],
        "challenges": [],
        "challengeRemainTime": 0,
        "subscriptions": [],
        "season": 1,
        "seasonRemainTime": LOCAL_SEASON_DURATION,
        "seasonReward": season_reward(),
        "tutorialSteps": [],
        "campaignStages": campaign_stages,
        "minigame": {},
        "hotTimeEvents": [],
        "banners": [],
        "socialPlatforms": [],
        "shop": shop_info(),
        "cardShop": card_shop_info(purchases),
        "isDeveloper": False,
    }
    return account


def login_success_response(state: MockState, *, secret: str | None = None) -> dict[str, object]:
    state.reset_login_progress()
    campaign_stages, tutorial_steps = state.onboarding_progress()
    account = mock_account(campaign_stages, state.deck(), state.card_purchases())
    account.update(user_thumb(state.user_id, state.name))
    account["gold"] = state.gold()
    account["tutorialSteps"] = tutorial_steps
    if state.social is not None:
        clan = state.social.profile(state.social.clan_id(state.user_id))
        if clan is not None:
            account["clan"] = clan
    return {
        "result": 0,
        "secret": state.secret if secret is None else secret,
        "encryption": SESSION_ENCRYPTION_KEY,
        "dayChanged": False,
        "account": account,
    }


def social_link_success_response(body: bytes, state: MockState) -> dict[str, object]:
    social_platform = 0
    try:
        request = json.loads(body.decode("utf-8")) if body else {}
        social_platform = int(request.get("socialPlatform", 0))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {
        "result": 0,
        "userId": state.user_id,
        "secret": state.secret,
        "socialPlatform": social_platform,
    }


def admission_success_response(host: str = DEFAULT_ADMISSION_URL) -> dict[str, object]:
    return {
        "result": 0,
        "assetVersion": ASSET_REVISION,
        "iosReview": False,
        "patchHosts": [],
        "downloadUrl": "",
        "host": host,
        "notices": [],
        "inviteUrl": "",
        "revision": ASSET_VERSION,
    }


def game_result_response(request: dict[str, object], state: MockState) -> dict[str, object]:
    transaction = request.get("transaction", 0)
    campaign_stages = state.advance_campaign_stage(request, record_result=True)
    return {
        "result": transaction if isinstance(transaction, int) else 0,
        "rewardResult": {
            "rewards": [],
            "campaignStages": campaign_stages,
        },
    }


def game_prev_result_response() -> dict[str, object]:
    return {
        "result": 0,
        "defeat": False,
        "retry": False,
        "rewardResults": [],
    }


def campaign_step_response(request: dict[str, object], state: MockState) -> dict[str, object]:
    return {
        "result": 0,
        "campaignStages": state.advance_campaign_stage(request),
    }


def tutorial_step_response(request: dict[str, object], state: MockState) -> dict[str, object]:
    step = request.get("step", 0)
    category = request.get("category", 0)
    skip = request.get("skip", False)
    if state.accounts is not None:
        if (type(category) is not int or not 0 <= category < LOBBY_TUTORIAL_CATEGORY_COUNT
                or type(step) is not int or not 0 <= step <= LOBBY_TUTORIAL_COMPLETE_STEP
                or type(skip) is not bool):
            raise AccountError(400, "Invalid tutorial progress.")
        step = state.advance_tutorial_step(category, step, skip)
        skip = step == LOBBY_TUTORIAL_COMPLETE_STEP
    elif state.campaign_tutorial_complete():
        step = 999
        skip = True
    return {
        "result": 0,
        "category": category,
        "step": step,
        "skip": bool(skip),
        "rewardResult": {
            "rewards": [],
            "campaignStages": state.campaign_stages(),
        },
    }


def pvp_server_response(state: MockState) -> dict[str, object]:
    return {
        "host": urlparse(state.admission_url).hostname,
        "port": state.pvp_port,
    }


def ping_response() -> dict[str, object]:
    return {
        "hasNewMail": False,
        "hasNewInvitationReward": False,
        "hotTimeEvents": [],
        "clanRewardResult": reward_result(),
        "clanDonaters": [],
    }


def refresh_response() -> dict[str, object]:
    return {
        "rankingPrivate": 0,
        "rankingTeam": 0,
        "clanRewardResult": reward_result(),
        "clanDonaters": [],
        "clanReset": False,
        "clanId": 0,
    }


def profile_stat_response(request: dict[str, object], guests: tuple[MockState, ...] = (), *, include_samples: bool = True) -> dict[str, object]:
    user_id = request.get("userId", 1000001)
    stat = profile_stat()
    for guest in guests:
        if guest.user_id == user_id:
            stat["normalPlay"], stat["normalWin"] = guest.lan_match_counts()
            break
    if include_samples and type(user_id) is int and 2000001 <= user_id <= 2000000 + len(LOCAL_SAMPLE_PLAYERS):
        rank = user_id - 2000000
        stat.update(
            normalPlay=72 - rank * 4,
            normalWin=49 - rank * 4,
            rankPrivatePlay=40 - rank * 2,
            rankPrivateWin=27 - rank * 2,
            rankPrivateMaxScore=1500 - 125 * rank,
            rankTeamPlay=33 - rank * 2,
            rankTeamWin=22 - rank * 2,
            rankTeamMaxScore=1200 - 90 * rank,
        )
    return {
        "userId": user_id if isinstance(user_id, int) else 1000001,
        "stat": stat,
    }


def match_record_list_response(request: dict[str, object]) -> dict[str, object]:
    user_id = request.get("userId", 1000001)
    return {
        "userId": user_id if isinstance(user_id, int) else 1000001,
        "matchRecords": [],
    }


def match_record_lock_response(request: dict[str, object]) -> dict[str, object]:
    match_record_id = request.get("matchRecordId", 0)
    lock = request.get("lock", False)
    return {
        "matchRecordId": match_record_id if isinstance(match_record_id, int) else 0,
        "lock": bool(lock),
    }


def season_result_response() -> dict[str, object]:
    return {
        "season": 1,
        "seasonRemainTime": LOCAL_SEASON_DURATION,
        "seasonResultPrivate": season_result(),
        "seasonResultTeam": season_result(),
        "seasonResultClan": season_result(),
        "seasonReward": season_reward(),
        "rewardResult": reward_result(),
    }


def route_response(
    method: str,
    path: str,
    body: bytes,
    status: int,
    guest_success: bool,
    state: MockState,
    guests: tuple[MockState, ...] = (),
) -> tuple[int, dict[str, object]]:
    parsed = urlparse(path)

    if method == "POST" and parsed.path == "/api/client/admission":
        return 200, admission_success_response(state.admission_url)

    if method == "POST" and parsed.path == "/api/client/social-link-validate":
        return 200, {
            "result": 0,
            "mock": True,
        }

    if method == "POST" and parsed.path == "/api/client/social-link":
        if guest_success:
            return 200, social_link_success_response(body, state)
        return 200, {
            "result": 2,
            "message": "Local capture backend does not implement social link.",
            "mock": True,
            "path": path,
            "bodyLength": len(body),
        }

    if method == "POST" and parsed.path == "/api/client/login":
        if guest_success:
            return 200, login_success_response(state)
        return 200, {
            "result": 2,
            "message": "Local capture backend does not implement guest login.",
            "mock": True,
            "path": path,
            "bodyLength": len(body),
        }

    if parsed.path == "/api/client-secure/game/result":
        return 200, game_result_response(request_json_for_path(parsed.path, body), state)

    if parsed.path == "/api/client-secure/game/campaign-step":
        return 200, campaign_step_response(request_json_for_path(parsed.path, body), state)

    if parsed.path == "/api/client-secure/tutorial/step":
        return 200, tutorial_step_response(request_json_for_path(parsed.path, body), state)

    if parsed.path == "/api/client-secure/quest/status":
        return 200, {
            "questStatus": quest_status(),
        }

    if parsed.path == "/api/client-secure/pvp-server":
        return 200, pvp_server_response(state)

    if parsed.path == "/api/client-secure/ping":
        return 200, ping_response()

    if parsed.path == "/api/client-secure/refresh":
        return 200, refresh_response()

    if parsed.path == "/api/client-secure/profile/stat":
        return 200, profile_stat_response(request_json_for_path(parsed.path, body), guests, include_samples=state.accounts is None)

    if parsed.path == "/api/client-secure/profile":
        request = request_json_for_path(parsed.path, body)
        user_id = request.get("userId")
        owner = next((guest for guest in guests if guest.user_id == user_id), state)
        return 200, public_profile(owner, user_id)

    if parsed.path == "/api/client-secure/ranking/user-list":
        ranking = ranking_response(request_json_for_path(parsed.path, body))
        if state.accounts is not None:
            ranking.update(ranking=0, users=[])
        return 200, ranking

    if parsed.path == "/api/client-secure/ranking/clan-list":
        request = request_json_for_path(parsed.path, body)
        order = request.get("order", 0)
        start = request.get("from", 0)
        return 200, {
            "order": order if type(order) is int and 0 <= order <= 1 else 0,
            "from": start if type(start) is int and start >= 0 else 0,
            "clans": state.social.search() if state.social and start == 0 else [],
        }

    if parsed.path in {"/api/client-secure/clan/recommend", "/api/client-secure/clan/search"}:
        request = request_json_for_path(parsed.path, body)
        keyword = request.get("keyword", "")
        return 200, {"clans": state.social.search(keyword) if state.social and valid_text(keyword, 48, empty=True) else []}

    if state.social is not None and parsed.path.startswith("/api/client-secure/clan/"):
        request = request_json_for_path(parsed.path, body)
        action = parsed.path.rsplit("/", 1)[1]
        if action == "arena-validate":
            clan = state.social.profile(state.social.clan_id(state.user_id))
            if clan is not None:
                return 200, {"clanArena": clan["arena"]}
        if action == "profile":
            clan_id = request.get("clanId")
            if type(clan_id) is int and 0 < clan_id < 2**63:
                clan = state.social.profile(clan_id)
                if clan is not None:
                    return 200, {"clan": clan}
            return 404, {"message": "Clan not found"}
        if method == "POST" and action in {"create", "join", "leave", "change-notice"}:
            change = state.change_clan(action, request)
            if change is None:
                return 409, {"message": "This clan action is unavailable"}
            return 200, change

    if parsed.path == "/api/client-secure/friend/recommend":
        users = []
        for guest in guests:
            if guest is state:
                continue
            users.append({
                **user_thumb(guest.user_id, guest.name),
                "level": 1,
                "recordPrivate": user_record(),
                "recordTeam": user_record(),
            })
        return 200, {"users": users if state.accounts is not None else users or sample_players()}

    if parsed.path == "/api/client-secure/tv-live/list":
        return 200, {"lives": []}

    if guests and parsed.path == "/api/client-secure/tv-replay/upload-verify":
        request = request_json_for_path(parsed.path, body)
        match_id = request.get("matchRecordId", 0)
        return 200, {"matchRecordId": match_id if type(match_id) is int else 0, "result": False}

    if parsed.path == "/api/client-secure/match-record/list":
        return 200, match_record_list_response(request_json_for_path(parsed.path, body))

    if parsed.path == "/api/client-secure/match-record/lock":
        return 200, match_record_lock_response(request_json_for_path(parsed.path, body))

    if parsed.path == "/api/client-secure/shop/card-info":
        return 200, {
            "cardShop": card_shop_info(state.card_purchases()),
        }

    if method == "POST" and parsed.path == "/api/client-secure/shop/buy-card":
        return 200, buy_card_response(request_json_for_path(parsed.path, body), state)

    if parsed.path == "/api/client-secure/shop/info":
        return 200, {
            "shop": shop_info(),
        }

    if parsed.path == "/api/client-secure/season-result":
        return 200, season_result_response()

    if parsed.path == "/api/client-secure/challenge-reset":
        return 200, {
            "challenges": [],
            "challengeRemainTime": 0,
        }

    if parsed.path == "/api/client-secure/game/prev-result":
        return 200, game_prev_result_response()

    if method == "POST" and parsed.path == "/api/client-secure/deck/change-name":
        request = request_json_for_path(parsed.path, body)
        name = request.get("name") if request.get("page") == 0 else None
        return 200, {"page": 0, "name": state.rename_deck(name)}

    if method == "POST" and parsed.path == "/api/client-secure/deck/card-equip":
        request = request_json_for_path(parsed.path, body)
        card = request.get("cardId") if request.get("page") == 0 else None
        slot, card_id = state.equip_card(request.get("slot"), card)
        return 200, {"page": 0, "slot": slot, "cardId": card_id}

    if method == "POST" and parsed.path == "/api/client-secure/deck/card-equip-all":
        request = request_json_for_path(parsed.path, body)
        cards = request.get("cardIds") if request.get("page") == 0 else None
        return 200, {"page": 0, "cards": state.equip_cards(cards)}

    if parsed.path == "/api/client-secure/push-token":
        return 200, {
            "result": 0,
            "mock": True,
            "path": path,
        }

    return status, {
        "ok": False,
        "mock": True,
        "message": "ACIES local capture server received the request, but no archival backend response is implemented.",
        "method": method,
        "path": path,
        "bodyLength": len(body),
        "status": status,
    }


class CaptureHandler(BaseHTTPRequestHandler):
    server_version = "AciesMock/0.1"

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def _write_capture(self, body: bytes) -> None:
        capture_dir: Path = self.server.capture_dir  # type: ignore[attr-defined]
        capture_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        parsed = urlparse(self.path)
        safe_path = parsed.path.strip("/").replace("/", "_") or "root"
        base = capture_dir / f"{stamp.replace('.', '-')}_{self.command}_{safe_path}"

        meta = {
            "time_utc": stamp,
            "client": self.client_address[0],
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers.items()),
            "body_length": len(body),
        }
        base.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        if body:
            base.with_suffix(".body").write_bytes(body)
            if parsed.path.startswith("/api/client-secure/"):
                decrypted = decrypt_secure_payload(body)
                if decrypted is not None:
                    base.with_suffix(".decrypted").write_bytes(decrypted)

        print(f"{stamp} {self.command} {self.path} body={len(body)}")
        for key, value in self.headers.items():
            print(f"  {key}: {value}")
        if body:
            preview = body[:512]
            try:
                print("  body.preview:", preview.decode("utf-8"))
            except UnicodeDecodeError:
                print("  body.preview.hex:", preview.hex())
            if parsed.path.startswith("/api/client-secure/"):
                decrypted = decrypt_secure_payload(body)
                if decrypted is not None:
                    try:
                        print("  body.decrypted:", decrypted[:512].decode("utf-8"))
                    except UnicodeDecodeError:
                        print("  body.decrypted.hex:", decrypted[:512].hex())

    def _send_placeholder(self, body: bytes, state: MockState) -> None:
        default_status: int = self.server.response_status  # type: ignore[attr-defined]
        guest_success: bool = self.server.guest_success  # type: ignore[attr-defined]
        guests = tuple(self.server.guests.values())  # type: ignore[attr-defined]
        status, response = route_response(self.command, self.path, body, default_status, guest_success, state, guests)
        payload = json.dumps(response, separators=(",", ":")).encode("utf-8")
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/client-secure/"):
            payload = encrypt_secure_payload(payload)
        self.send_response(status)
        content_type = "application/octet-stream" if parsed.path.startswith("/api/client-secure/") else "application/json; charset=utf-8"
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self) -> None:
        guests: dict[str, MockState] = self.server.guests  # type: ignore[attr-defined]
        if guests:
            state = guests.get(self.client_address[0])
            if state is None:
                self.send_error(403)
                return
        else:
            state = self.server.mock_state  # type: ignore[attr-defined]
        body = self._read_body()
        self._write_capture(body)
        self._send_placeholder(body, state)

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def log_message(self, fmt: str, *args: object) -> None:
        return


class Community:
    def __init__(self, accounts: AccountStore, args: argparse.Namespace) -> None:
        self.accounts = accounts
        self.names = accounts.players()
        self.social = SocialStore(args.community_db, self.names, starter_deck())
        self.open_registration = args.open_registration
        self.trusted_proxy = args.trusted_proxy
        self.chat_enabled = args.enable_chat
        self.player_options = {
            "admission_url": args.admission_url,
            "pvp_port": args.pvp_port,
            "tutorial_stages": True,
            "tutorial_stage_count": DEFAULT_TUTORIAL_STAGE_COUNT,
        }
        self.players: dict[int, MockState] = {}
        self.lock = threading.Lock()
        self.attempts: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self.listener: LobbySocketServer | None = None

    def player(self, identity: PlayerIdentity) -> MockState:
        with self.lock:
            state = self.players.get(identity.user_id)
            if state is None:
                state = MockState(user_id=identity.user_id, name=identity.username, accounts=self.accounts, **self.player_options)
                with self.social.lock:
                    self.names[identity.user_id] = identity.username
                state.social = self.social
                self.players[identity.user_id] = state
            return state

    def related_players(self, path: str, request: dict[str, object]) -> tuple[MockState, ...]:
        if path == "/api/client-secure/friend/recommend":
            with self.lock:
                return tuple(self.players.values())[-30:]
        if path in {"/api/client-secure/profile", "/api/client-secure/profile/stat"}:
            user_id = request.get("userId")
            if type(user_id) is int:
                with self.social.lock:
                    name = self.names.get(user_id)
                if name:
                    return (self.player(PlayerIdentity(user_id, name)),)
        return ()

    def allow_attempt(self, source: str) -> bool:
        now = time.monotonic()
        with self.lock:
            since, count = self.attempts.get(source, (now, 0))
            if now - since >= 60:
                since, count = now, 0
            if count >= 12:
                return False
            self.attempts[source] = (since, count + 1)
            self.attempts.move_to_end(source)
            if len(self.attempts) > 4096:
                self.attempts.popitem(last=False)
            return True


class LimitedRequests:
    """Bounds concurrent work before starting a request handler."""

    def __init__(self, *args, max_clients: int, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.slots = threading.BoundedSemaphore(max_clients)
        self.active_clients = 0
        self.active_lock = threading.Lock()

    def process_request(self, request: socket.socket, address: tuple) -> None:
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request: socket.socket, address: tuple) -> None:
        with self.active_lock:
            self.active_clients += 1
        try:
            request.settimeout(10)
            super().process_request_thread(request, address)
        except OSError:
            self.shutdown_request(request)
        finally:
            with self.active_lock:
                self.active_clients -= 1
            self.slots.release()


class CommunityHTTPServer(LimitedRequests, ThreadingHTTPServer):
    request_queue_size = 128
    community: Community


class CommunityHandler(CaptureHandler):
    server: CommunityHTTPServer
    server_version = "AciesCommunity"
    sys_version = ""

    def _read_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding") is not None or len(self.headers.get_all("Content-Length", [])) > 1:
            raise AccountError(400, "Unsupported request body framing.")
        length = self.headers.get("Content-Length", "0")
        if not length.isascii() or not length.isdigit() or len(length) > 10:
            raise AccountError(400, "Invalid content length.")
        if int(length) > MAX_HTTP_BODY:
            raise AccountError(413, "The request body is too large.")
        body = self.rfile.read(int(length))
        if len(body) != int(length):
            raise AccountError(400, "Incomplete request body.")
        return body

    def reply(self, status: int, data: dict, *, secure: bool = False) -> None:
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
        if secure:
            payload = encrypt_secure_payload(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream" if secure else "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self) -> None:
        community = self.server.community
        path = urlparse(self.path).path
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            token = ""
        try:
            if self.command == "GET" and path == "/community/health":
                return self.reply(200, {"status": "ok", "registration": "open" if community.open_registration else "invite"})
            if self.command == "GET" and path == "/community/metrics" and self.client_address[0] == "127.0.0.1" and not self.headers.get("X-Acies-Client-IP"):
                listener = community.listener
                return self.reply(200, {"http_connections": self.server.active_clients,
                                        "gateway_connections": listener.active_clients if listener else 0,
                                        "active_matches": len(listener.matches) if listener else 0})
            if self.command == "POST" and path in {"/community/register", "/community/login"}:
                return self._credentials(path)
            if self.command == "POST" and path == "/api/client/admission":
                self._read_body()
                return self.reply(200, admission_success_response(community.player_options["admission_url"]))
            identity = community.accounts.authenticate(token)
            if identity is None:
                raise AccountError(401, "Please sign in to Acies.")
            if self.command == "GET" and path == "/community/session":
                return self.reply(200, {"username": identity.username, "userId": identity.user_id})
            if self.command == "POST" and path == "/community/logout":
                community.accounts.revoke(token)
                if community.listener is not None:
                    community.listener.revoke(identity.user_id, digest(gateway_token(token)))
                return self.reply(200, {"ok": True})
            if not path.startswith(("/api/client/", "/api/client-secure/")):
                raise AccountError(404, "Unknown endpoint.")
            state = community.player(identity)
            body = self._read_body()
            secure = path.startswith("/api/client-secure/")
            if self.command == "POST" and path == "/api/client/login":
                return self.reply(200, login_success_response(state, secret=gateway_token(token)))
            if path in {"/api/client/social-link", "/api/client/social-link-validate"}:
                return self.reply(200, {"result": 2, "message": "Use the Acies account screen to sign in."})
            if path == "/api/client-secure/pvp-server":
                port = self.headers.get("X-Acies-Gateway-Port", "")
                if not port.isascii() or not port.isdigit() or len(port) > 5 or not 1024 <= int(port) <= 65535:
                    raise AccountError(400, "Install a compatible Acies community client.")
                return self.reply(200, {"host": "127.0.0.1", "port": int(port)}, secure=True)
            request = request_json_for_path(path, body) if path.endswith(("/profile", "/profile/stat")) else {}
            guests = community.related_players(path, request)
            status, result = route_response(self.command, self.path, body, 200, False, state, guests)
            self.reply(status, result, secure=secure)
        except AccountError as error:
            self.reply(error.status, {"error": str(error)})

    def _credentials(self, path: str) -> None:
        community = self.server.community
        source = self.client_address[0]
        if community.trusted_proxy:
            source = self.headers.get("X-Acies-Client-IP", source)
        if not community.allow_attempt(source[:64]):
            raise AccountError(429, "Too many attempts. Try again in a minute.")
        body = self._read_body()
        if len(body) > 2048:
            raise AccountError(413, "The request body is too large.")
        try:
            values = json.loads(body)
            if not isinstance(values, dict):
                raise ValueError
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise AccountError(400, "Send a JSON object.") from None
        if path == "/community/register":
            token = community.accounts.register(values.get("username"), values.get("password"), values.get("invite"),
                                                open_registration=community.open_registration)
        else:
            token = community.accounts.login(values.get("username"), values.get("password"))
        identity = community.accounts.authenticate(token)
        community.player(identity)
        self.reply(201 if path.endswith("register") else 200, {"token": token, "username": identity.username})


def gateway_string(value: str) -> bytes:
    data = value.encode("utf-8")
    if len(data) > 127:
        raise ValueError("Local gateway names must fit in 127 UTF-8 bytes")
    return bytes([len(data)]) + data


def chat_payload(message: ChatMessage) -> bytes:
    return (
        struct.pack("<q", message.user_id)
        + gateway_string(message.name)
        + bytes(19)  # country, decorations, empty picture URL
        + gateway_string(message.text)
        + struct.pack("<I", message.time)
    )


def read_chat_string(data: bytes) -> tuple[str, bytes]:
    if not data or data[0] > 127 or data[0] >= len(data):
        raise ValueError("Invalid chat string length")
    end = data[0] + 1
    return data[1:end].decode("utf-8"), data[end:]


def gateway_block(seat: int, command: bytes) -> bytes:
    length = len(command) + 1
    prefix = bytes([length]) if length < 128 else bytes([0x80 | (length >> 7), length & 0x7F])
    # The client reads another block length after each order block.
    return prefix + bytes([seat]) + command + bytes(1)


def gateway_user(guest: MockState) -> bytes:
    return (
        struct.pack("<q", guest.user_id)
        + gateway_string(guest.name)
        + bytes(18)  # country and four decoration asset IDs
        + bytes(1)  # picture URL
        + struct.pack("<H", 1)  # level
        + bytes(28)  # two unranked user records
        + bytes(1)  # no clan
    )


class LanParty:
    """The local player's party while the client waits in the 1v1 queue."""

    def __init__(self, guest: MockState, mode: int) -> None:
        self.guest = guest
        self.mode = mode
        self.waiting = False

    def created_packet(self) -> bytes:
        guest = self.guest
        return (
            bytes([3])  # party created
            + gateway_string(f"lan-{guest.user_id}")
            + bytes([self.mode, 0, 0])  # mode, no map, no password
            + struct.pack("<q", guest.user_id)  # leader
            + bytes([0, 1, 1])  # idle, one slot, occupied
            + gateway_user(guest)
            + bytes([1, 0, 1])  # occupied slot state, counters
        )


class LanMatch:
    """One two-player match on the built-in Windmill Boot Camp map."""

    simulation_rate = 40  # The client initializes online maps at 40 frames per second.
    frames_per_update = 2
    update_interval = frames_per_update / simulation_rate
    # The previous update must never authorize frames past a new order's frame.
    frame_lead = frames_per_update
    reconnect_window = 45
    history_limit = 4096
    command_group_sizes = (3, 2, 6, 56, 36, 142)
    unit_group_sizes = (7, 3, 20, 42, 4, 17, 4, 14)
    target_lengths = (1, 25, 5, 5, 27)

    def __init__(
        self,
        match_id: int,
        guests: tuple[MockState, MockState],
        clients: tuple[LobbySocketHandler, LobbySocketHandler],
        server: LobbySocketServer,
    ) -> None:
        self.match_id = match_id
        self.guests = guests
        self.clients = list(clients)
        self.server = server
        self.deck_cards = tuple(tuple(guest.deck()["cards"]) for guest in guests)
        self.ready: set[LobbySocketHandler] = set()
        self.started = False
        self.stopped = threading.Event()
        self.orders: deque[tuple[int, bytes]] = deque()
        self.order_lock = threading.RLock()
        self.detached: dict[int, float] = {}
        self.frame_limit = 0
        self.history_floor = 0
        self.order_history: deque[tuple[int, bytes]] = deque(maxlen=self.history_limit)
        self.resigned: set[int] = set()
        self.results: dict[int, int] = {}
        self.exited: set[int] = set()
        self.ready_timer: threading.Timer | None = None
        self.finish_deadline = float("inf")

    def expire_unready(self) -> None:
        with self.order_lock:
            if not self.started:
                self.close(disconnected=True)

    def enter_packet(self, *, active: bool = False) -> bytes:
        guest_slots = []
        for seat, guest in enumerate(self.guests):
            cards = self.deck_cards[seat]
            deck = b"".join(struct.pack("<4H", card >> 16, card & 0xFFFF, 0, 0) for card in cards)
            player = gateway_user(guest) + bytes(4) + bytes([len(cards)]) + deck + bytes(1)
            guest_slots.append(bytes([1]) + player + bytes([1, seat]))
        return (
            bytes([18, 0])  # entered match, full state
            + struct.pack("<IBB3H", self.match_id, 2, 0, 0, 0, 0)
            + struct.pack("<4H", 0, 0, 1, 0)
            + bytes(1)  # no password
            + struct.pack("<qqBI", self.match_id if active else 0, self.guests[0].user_id, 2 if active else 0, self.match_id)
            + bytes([0, len(guest_slots)])  # no voice address, player slots
            + b"".join(guest_slots)
            + bytes(8)  # observers and trailer
        )

    def start_packet(self) -> bytes:
        return struct.pack("<BqH", 29, self.match_id, 0)

    def player_ready(self, client: LobbySocketHandler) -> None:
        with self.order_lock:
            if self.started or client.match is not self:
                return
            self.ready.add(client)
            if len(self.ready) != len(self.clients):
                return
            for peer in self.clients:
                try:
                    peer.send(bytes([30]))
                except (socket.timeout, ConnectionError):
                    print(f"Guest {peer.client_address[0]} disconnected during local match sync")
                    self.close(disconnected=True)
                    return
            self.started = True
            if self.ready_timer is not None:
                self.ready_timer.cancel()
        print(f"Both clients ready in local match {self.match_id}")
        threading.Thread(target=self.run_frames, daemon=True).start()

    def run_frames(self) -> None:
        frame = 0
        start = time.monotonic()
        while not self.stopped.wait(max(0, start + frame / self.simulation_rate - time.monotonic())):
            packet = struct.pack("<BBIf", 32, self.frame_lead, frame, self.update_interval)
            with self.order_lock:
                now = time.monotonic()
                if now >= self.finish_deadline or any(deadline <= now for deadline in self.detached.values()):
                    self.close(disconnected=True)
                    return
                order = self.orders.popleft() if self.orders else None
                if order is not None:
                    seat, command = order
                    packet += gateway_block(seat, command)
                    if len(self.order_history) == self.history_limit:
                        self.history_floor = self.order_history[0][0] + self.frames_per_update
                    self.order_history.append((frame, packet))
                self.frame_limit = frame + self.frame_lead
                for peer in self.clients:
                    if peer.match is self:
                        try:
                            peer.send(packet, match=self)
                        except (socket.timeout, ConnectionError):
                            self.disconnect(peer)
            if order is not None:
                print(f"Local match {self.match_id} relayed action {command[0]} for seat {seat} at frame {frame}")
            frame += self.frames_per_update

    def disconnect(self, client: LobbySocketHandler) -> None:
        with self.order_lock:
            if client.match is not self:
                return
            if not self.started or self.results or self.exited:
                self.close(disconnected=True)
                return
            seat = self.clients.index(client)
            self.detached[seat] = time.monotonic() + self.reconnect_window
            self.ready.discard(client)
            client.match = None
            try:
                client.request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            print(f"Local match {self.match_id} waiting for seat {seat} to reconnect")

    def resume(self, guest: MockState, client: LobbySocketHandler, frame: int) -> bool:
        with self.order_lock:
            if self.stopped.is_set() or client.match is not None or guest not in self.guests or self.results:
                return False
            seat = self.guests.index(guest)
            if self.detached.get(seat, 0) <= time.monotonic():
                return False
            if frame % self.frames_per_update or not self.history_floor <= frame <= self.frame_limit:
                return False
            # The requested frame is the exclusive limit from the last received update.
            packets = (self.enter_packet(active=True), *(packet for order_frame, packet in self.order_history if order_frame >= frame))
            client.send_many(packets)
            self.clients[seat] = client
            client.match = self
            self.ready.add(client)
            del self.detached[seat]
            print(f"Local match {self.match_id} restored seat {seat} from frame {frame}")
            return True

    @staticmethod
    def in_bounds(x: int, y: int) -> bool:
        return 0 <= x < (154 << 16) and 0 <= y < (132 << 16)

    def target_end(self, command: bytes, start: int, seat: int) -> int | None:
        if start >= len(command) or command[start] >= len(self.target_lengths):
            return None
        target = command[start]
        end = start + self.target_lengths[target]
        if end > len(command):
            return None
        if target == 1:
            x, y, offset, radius = struct.unpack_from("<qqIf", command, start + 1)
            if not (self.in_bounds(x, y) and offset == 0 and 0 <= radius <= 200):
                return None
        elif target in (2, 3):
            if struct.unpack_from("<I", command, start + 1)[0] == 0:
                return None
        elif target == 4:
            force, group, asset, x, y, offset, kind = struct.unpack_from("<BHHqqIB", command, start + 1)
            if force != seat or group >= len(self.unit_group_sizes) or asset >= self.unit_group_sizes[group]:
                return None
            if not (self.in_bounds(x, y) and offset == 0 and kind == 1):
                return None
        return end

    def valid_order(self, command: bytes, seat: int) -> bool:
        if len(command) < 3:
            return False
        if command[0] == 7:
            return command[1] < len(self.deck_cards[seat]) and self.target_end(command, 2, seat) == len(command)
        if command[0] != 2 or command[1] > 127:
            return False
        unit_count = command[1]
        asset_start = 2 + unit_count * 4
        if len(command) < asset_start + 6:
            return False
        units = struct.unpack_from(f"<{unit_count}I", command, 2)
        if not units or 0 in units or len(set(units)) != unit_count:
            return False
        group, asset = struct.unpack_from("<HH", command, asset_start)
        if (group, asset) != (0xFFFF, 0xFFFF):
            if group >= len(self.command_group_sizes) or asset >= self.command_group_sizes[group]:
                return False
        end = self.target_end(command, asset_start + 4, seat)
        if end is None or end >= len(command):
            return False
        if command[end] == 0:
            return len(command) == end + 1
        if command[end] != 1 or len(command) != end + 21:
            return False
        x, y, offset = struct.unpack_from("<qqI", command, end + 1)
        return self.in_bounds(x, y) and offset == 0

    def queue_order(self, client: LobbySocketHandler, command: bytes) -> None:
        resign = command == bytes(2)
        with self.order_lock:
            if self.stopped.is_set() or client.match is not self or client not in self.ready:
                return
            seat = self.clients.index(client)
            if seat in self.results:
                return
            if not resign and not self.valid_order(command, seat):
                return
            if seat in self.resigned:
                return
            if resign:
                self.resigned.add(seat)
            if resign or len(self.orders) < 8:
                self.orders.append((seat, command))

    def report_result(self, client: LobbySocketHandler, outcome: int) -> None:
        with self.order_lock:
            if client.match is not self or client not in self.ready or not 1 <= outcome <= 3:
                return
            seat = self.clients.index(client)
            if seat in self.results:
                return
            self.results[seat] = outcome
            print(f"Local match {self.match_id} seat {seat} reported result {outcome}")
            results = (self.results.get(0), self.results.get(1))
            if self.server.community is not None and None not in results:
                self.finish_deadline = time.monotonic() + 60
            if results not in ((1, 2), (2, 1), (3, 3)):
                return
            if self.server.community is not None:
                self.server.community.accounts.save_match(self.match_id, (self.guests[0].user_id, self.guests[1].user_id), results)
            else:
                for index, guest in enumerate(self.guests):
                    guest.save_lan_match_result(self.match_id, self.guests[1 - index].user_id, self.results[index])

    def exit(self, client: LobbySocketHandler) -> None:
        with self.order_lock:
            if client.match is not self:
                return
            self.exited.add(self.clients.index(client))
            client.match = None
            if self.server.community is not None:
                self.finish_deadline = min(self.finish_deadline, time.monotonic() + 60)
            if len(self.exited) == len(self.clients):
                self.close()

    def close(self, *, disconnected: bool = False) -> None:
        self.stopped.set()
        if self.ready_timer is not None:
            self.ready_timer.cancel()
        self.server.remove_match(self.match_id)
        for peer in self.clients:
            if peer.match is self:
                peer.match = None
                if disconnected:
                    try:
                        peer.request.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass


class LobbySocketHandler(socketserver.BaseRequestHandler):
    header = struct.Struct("<2sII")

    def setup(self) -> None:
        self.outgoing_sequence = 0
        self.write_lock = threading.Lock()
        self.match: LanMatch | None = None
        self.channel_joined = False
        self.last_chat_at = float("-inf")
        self.auth_hash: bytes | None = None
        self.outbound: queue.Queue | None = None
        self.writer: threading.Thread | None = None
        self.closed = threading.Event()

    def send(self, payload: bytes, *, match: LanMatch | None = None) -> None:
        self.send_many((payload,), match=match)

    def send_many(self, payloads: tuple[bytes, ...], *, match: LanMatch | None = None) -> None:
        if match is not None and self.match is not match:
            return
        if self.outbound is not None:
            if self.closed.is_set():
                raise ConnectionError("Gateway connection closed")
            try:
                self.outbound.put_nowait(payloads)
            except queue.Full:
                self.abort()
                raise ConnectionError("Gateway send queue full") from None
            return
        with self.write_lock:
            if match is None or self.match is match:
                self.write_packets(payloads)

    def write_packets(self, payloads: tuple[bytes, ...]) -> None:
        data = bytearray()
        for payload in payloads:
            data += self.header.pack(b"TC", self.outgoing_sequence, len(payload)) + payload
            self.outgoing_sequence += 1
        self.request.sendall(data)

    def write_loop(self) -> None:
        try:
            while not self.closed.is_set():
                try:
                    payloads = self.outbound.get(timeout=0.5)
                except queue.Empty:
                    continue
                self.write_packets(payloads)
        except OSError:
            self.abort()

    def abort(self) -> None:
        self.closed.set()
        try:
            self.request.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def handle(self) -> None:
        community = self.server.community
        guests = self.server.guests
        guest = guests.get(self.client_address[0])
        if guests and guest is None:
            return
        if guest is not None:
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.request.settimeout(8 if community is not None else 3600)
        logged_in = False
        expected_sequence = 0
        party: LanParty | None = None
        check_session_at = 0.0
        try:
            with self.request.makefile("rb") as stream:
                while header := stream.read(self.header.size):
                    if len(header) != self.header.size:
                        return
                    magic, sequence, length = self.header.unpack(header)
                    if magic != b"TC" or sequence != expected_sequence or not 1 <= length <= 65536:
                        return
                    payload = stream.read(length)
                    if len(payload) != length:
                        return
                    expected_sequence += 1
                    response = None
                    opcode = payload[0]
                    if opcode == 0 and not logged_in:
                        if community is not None:
                            auth = community.accounts.authenticate_gateway(payload)
                            if auth is None:
                                return
                            identity, self.auth_hash = auth
                            guest = community.player(identity)
                            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                            self.request.settimeout(90)
                            self.outbound = queue.Queue(maxsize=128)
                            self.writer = threading.Thread(target=self.write_loop, daemon=True)
                            self.writer.start()
                            self.server.claim_peer(guest, self)
                        # Login opcode, empty session tag, and empty friend lists.
                        response = bytes(4)
                        logged_in = True
                        print(f"Lobby login acknowledged for player {guest.user_id if guest else 'local'}")
                        if guest is not None and guest.social is not None:
                            self.server.register_chat_peer(guest, self)
                    elif guest is not None and logged_in:
                        if community is not None:
                            now = time.monotonic()
                            if self.closed.is_set() or (now >= check_session_at and not community.accounts.gateway_valid(self.auth_hash)):
                                return
                            if now >= check_session_at:
                                check_session_at = now + 15
                        match = self.match
                        if guest.social is not None and opcode in {38, 39, 49, 50, 51}:
                            if community is None or community.chat_enabled or opcode in {38, 49, 50}:
                                self.handle_chat(guest, payload)
                        elif opcode == 3 and len(payload) == 7 and payload[5] == 0:
                            party = LanParty(guest, payload[1])
                            response = party.created_packet()
                            print(f"Created local party for guest {guest.user_id}, mode={party.mode}")
                        elif opcode == 12 and party is not None and len(payload) == 2:
                            party.waiting = bool(payload[1])
                            self.send(bytes([12, int(party.waiting), 0]))
                            print(f"Local party for guest {guest.user_id} waiting={party.waiting}")
                            if party.waiting and party.mode == 2:
                                self.server.queue_for_match(guest, self)
                            elif not party.waiting:
                                self.server.leave_queue(self)
                        elif opcode == 5 and len(payload) == 1:
                            party = None
                            self.server.leave_queue(self)
                            response = bytes([5, 0])
                            print(f"Guest {guest.user_id} left the local party")
                        elif opcode == 100 and len(payload) == 1:
                            response = bytes([100])
                        elif opcode == 30 and len(payload) == 1 and match is not None:
                            match.player_ready(self)
                        elif opcode == 33 and len(payload) == 11 and match is not None:
                            pass
                        elif opcode == 32 and match is not None:
                            match.queue_order(self, payload[1:])
                        elif opcode == 37 and len(payload) == 2 and match is not None:
                            match.report_result(self, payload[1])
                        elif opcode == 18 and len(payload) == 10:
                            match_id, frame, reconnect = struct.unpack_from("<IIB", payload, 1)
                            if reconnect != 1 or not self.server.resume_match(match_id, guest, self, frame):
                                response = bytes([18, 3])
                        elif opcode == 19 and len(payload) == 1:
                            if match is not None:
                                match.exit(self)
                            party = None
                            response = bytes([19, 0])
                        elif community is None:
                            print(f"Lobby client {self.client_address[0]} opcode={opcode} sequence={sequence} length={length}")
                    elif community is not None:
                        return
                    if response is not None:
                        self.send(response)
        except OSError:
            pass
        finally:
            if guest is not None:
                self.server.leave_queue(self)
                self.server.unregister_chat_peer(guest, self)
                if community is not None:
                    self.server.release_peer(guest, self)
            match = self.match
            if match is not None:
                match.disconnect(self)
            self.abort()
            if self.writer is not None:
                self.writer.join(timeout=1)

    def handle_chat(self, guest: MockState, payload: bytes) -> None:
        social = guest.social
        if social is None:
            return
        opcode = payload[0]
        can_chat = self.server.community is None or self.server.community.chat_enabled
        if opcode == 49:
            try:
                language, rest = read_chat_string(payload[1:])
                region, rest = read_chat_string(rest)
            except ValueError:
                return
            if rest:
                return
            with self.server.chat_lock:
                history = social.history(0) if can_chat else []
                self.send(
                    bytes([49, 1, 1]) + gateway_string(language) + gateway_string(region) + bytes([0, len(history)])
                    + b"".join(map(chat_payload, history))
                )
                self.channel_joined = True
        elif opcode == 50 and len(payload) == 1:
            with self.server.chat_lock:
                self.channel_joined = False
                self.send(bytes([50, 1]))
        elif opcode == 38 and len(payload) == 18:
            clan_id = social.clan_id(guest.user_id)
            if clan_id:
                with self.server.chat_lock:
                    history = social.history(clan_id) if can_chat else []
                    self.send(bytes([40, len(history)]) + b"".join(map(chat_payload, history)))
        elif opcode in (39, 51):
            try:
                message, rest = read_chat_string(payload[1:])
            except ValueError:
                return
            now = time.monotonic()
            if rest or now - self.last_chat_at < 0.75 or (opcode == 51 and not self.channel_joined):
                return
            with self.server.chat_lock:
                posted = social.post(guest.user_id, message, clan=opcode == 39)
                if posted is not None:
                    self.last_chat_at = now
                    clan_id, message = posted
                    self.server.broadcast_chat(social, opcode, clan_id, message)


class LobbySocketServer(socketserver.ThreadingTCPServer):
    guests: dict[str, MockState] = {}
    community: Community | None = None
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[LobbySocketHandler]) -> None:
        super().__init__(address, handler)
        self.queue_lock = threading.Lock()
        self.waiting: dict[MockState, LobbySocketHandler] = {}
        self.matches: dict[int, LanMatch] = {}
        self.chat_lock = threading.Lock()
        self.chat_peers: dict[int, LobbySocketHandler] = {}
        self.auth_lock = threading.Lock()
        self.auth_peers: dict[int, LobbySocketHandler] = {}
        self.next_match_id = int(dt.datetime.now(dt.timezone.utc).timestamp())

    def claim_peer(self, guest: MockState, client: LobbySocketHandler) -> None:
        with self.auth_lock:
            previous = self.auth_peers.get(guest.user_id)
            self.auth_peers[guest.user_id] = client
        if previous is not None:
            previous.abort()
            self.leave_queue(previous)
            match = previous.match
            if match is not None:
                match.disconnect(previous)

    def release_peer(self, guest: MockState, client: LobbySocketHandler) -> None:
        with self.auth_lock:
            if self.auth_peers.get(guest.user_id) is client:
                del self.auth_peers[guest.user_id]

    def revoke(self, user_id: int, token_hash: bytes) -> None:
        with self.auth_lock:
            peer = self.auth_peers.get(user_id)
            if peer is not None and peer.auth_hash == token_hash:
                peer.abort()

    def register_chat_peer(self, guest: MockState, client: LobbySocketHandler) -> None:
        with self.chat_lock:
            self.chat_peers[guest.user_id] = client

    def unregister_chat_peer(self, guest: MockState, client: LobbySocketHandler) -> None:
        with self.chat_lock:
            if self.chat_peers.get(guest.user_id) is client:
                del self.chat_peers[guest.user_id]

    def broadcast_chat(self, social: SocialStore, opcode: int, clan_id: int, message: ChatMessage) -> None:
        packet = bytes([opcode]) + chat_payload(message)
        for user_id, peer in self.chat_peers.items():
            if clan_id and social.clan_id(user_id) != clan_id:
                continue
            if not clan_id and not peer.channel_joined:
                continue
            try:
                peer.send(packet)
            except (socket.timeout, ConnectionError):
                continue

    def queue_for_match(self, guest: MockState, client: LobbySocketHandler) -> None:
        with self.queue_lock:
            if client.match is not None or any(
                guest in match.guests and match.guests.index(guest) not in match.exited
                for match in self.matches.values()
            ):
                return
            self.waiting[guest] = client
            if len(self.waiting) < 2:
                return
            host, challenger = list(self.waiting)[:2]
            clients = (self.waiting.pop(host), self.waiting.pop(challenger))
            match_id = self.community.accounts.create_match() if self.community is not None else self.next_match_id
            match = LanMatch(match_id, (host, challenger), clients, self)
            self.matches[match.match_id] = match
            self.next_match_id += 1
            for peer in clients:
                peer.match = match
            if self.community is not None:
                match.ready_timer = threading.Timer(30, match.expire_unready)
                match.ready_timer.daemon = True
                match.ready_timer.start()
        join = match.enter_packet()
        start = match.start_packet()
        for peer in clients:
            try:
                peer.send(join)
                peer.send(start)
            except (socket.timeout, ConnectionError):
                print(f"Guest {peer.client_address[0]} disconnected during local match start")
                match.close(disconnected=True)
                return
        print(f"Paired local match {match.match_id}: {host.user_id} vs {challenger.user_id}")

    def resume_match(self, match_id: int, guest: MockState, client: LobbySocketHandler, frame: int) -> bool:
        with self.queue_lock:
            match = self.matches.get(match_id)
        return match is not None and match.resume(guest, client, frame)

    def remove_match(self, match_id: int) -> None:
        with self.queue_lock:
            self.matches.pop(match_id, None)

    def leave_queue(self, client: LobbySocketHandler) -> None:
        with self.queue_lock:
            for guest, peer in self.waiting.items():
                if peer is client:
                    del self.waiting[guest]
                    break


class CommunityGateway(LimitedRequests, LobbySocketServer):
    request_queue_size = 128


def serve_community(args: argparse.Namespace) -> None:
    accounts = AccountStore(args.community_db)
    community = Community(accounts, args)
    with CommunityHTTPServer((args.host, args.port), CommunityHandler, max_clients=args.max_http_clients) as http:
        with CommunityGateway((args.host, args.pvp_port), LobbySocketHandler, max_clients=args.max_gateway_clients) as gateway:
            gateway.community = http.community = community
            community.listener = gateway
            threading.Thread(target=gateway.serve_forever, daemon=True).start()
            print(f"Acies community API on {http.server_address}; gateway on {gateway.server_address}", flush=True)
            try:
                http.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                gateway.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture ACIES backend requests locally.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--admission-url",
        default=DEFAULT_ADMISSION_URL,
        help="HTTP origin advertised to the Android client after admission.",
    )
    parser.add_argument(
        "--lobby-listener",
        action="store_true",
        help="Accept the local lobby login handshake.",
    )
    parser.add_argument("--pvp-port", type=int, default=DEFAULT_PVP_PORT)
    parser.add_argument("--state-db", type=Path, help="SQLite file for the local guest's saved state and battle history.")
    parser.add_argument("--community-db", type=Path, help="Enable authenticated community mode with this SQLite database.")
    parser.add_argument("--open-registration", action="store_true", help="Allow account creation without an invitation.")
    parser.add_argument("--trusted-proxy", action="store_true", help="Use the client IP set by the local HTTPS proxy for login limits.")
    parser.add_argument("--enable-chat", action="store_true", help="Enable community chat for a moderated beta.")
    parser.add_argument("--max-http-clients", type=int, default=64)
    parser.add_argument("--max-gateway-clients", type=int, default=128)
    parser.add_argument(
        "--guest-device",
        action="append",
        nargs=2,
        metavar=("LAN_IP", "NAME"),
        default=[],
        help="Enroll a test phone. Guests are assigned in argument order and saved separately under --captures.",
    )
    parser.add_argument("--captures", default="captures/acies_mock")
    parser.add_argument("--status", type=int, default=200, help="HTTP status returned to the APK.")
    parser.add_argument(
        "--guest-success",
        action="store_true",
        help="Return a synthetic login success payload for /api/client/login.",
    )
    parser.add_argument(
        "--tutorial-stages",
        action="store_true",
        help="Start guest login before campaign tutorial and advance campaign progress from game result calls.",
    )
    parser.add_argument(
        "--tutorial-stage-count",
        type=int,
        default=DEFAULT_TUTORIAL_STAGE_COUNT,
        help="Number of mandatory campaign tutorial stages in legacy guest tutorial mode.",
    )
    args = parser.parse_args()
    if args.tutorial_stage_count < 1:
        parser.error("--tutorial-stage-count must be at least 1")
    if not urlparse(args.admission_url).hostname:
        parser.error("--admission-url must contain a hostname")
    if not 1 <= args.pvp_port <= 65535:
        parser.error("--pvp-port must be between 1 and 65535")
    try:
        devices = [(str(ipaddress.IPv4Address(host)), name) for host, name in args.guest_device]
    except ipaddress.AddressValueError as error:
        parser.error(str(error))
    if len({host for host, _ in devices}) != len(devices):
        parser.error("--guest-device LAN addresses must be distinct")
    if any(not 1 <= len(name.encode("utf-8")) <= 127 for _, name in devices):
        parser.error("--guest-device NAME must be between 1 and 127 UTF-8 bytes")
    if args.community_db is not None:
        if args.host != "127.0.0.1":
            parser.error("Community listeners must bind to 127.0.0.1 behind the TLS proxy.")
        if urlparse(args.admission_url).scheme != "https":
            parser.error("Community admission requires an HTTPS origin.")
        if devices or args.state_db or args.guest_success:
            parser.error("Community mode uses its own accounts and database.")
        if min(args.max_http_clients, args.max_gateway_clients) < 2:
            parser.error("Community connection limits must each be at least 2.")
        return serve_community(args)

    server = ThreadingHTTPServer((args.host, args.port), CaptureHandler)
    server.capture_dir = Path(args.captures)  # type: ignore[attr-defined]
    server.response_status = args.status  # type: ignore[attr-defined]
    server.guest_success = args.guest_success  # type: ignore[attr-defined]
    server.mock_state = MockState(  # type: ignore[attr-defined]
        tutorial_stages=args.tutorial_stages,
        tutorial_stage_count=args.tutorial_stage_count,
        admission_url=args.admission_url,
        pvp_port=args.pvp_port,
        state_db=args.state_db,
    )
    server.guests = {}  # type: ignore[attr-defined]
    if devices:
        server.capture_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
        server.guests = {  # type: ignore[attr-defined]
            host: MockState(
                tutorial_stages=args.tutorial_stages,
                tutorial_stage_count=args.tutorial_stage_count,
                admission_url=args.admission_url,
                pvp_port=args.pvp_port,
                state_db=Path(args.captures) / f"guest-{index}.sqlite3",
                user_id=1000000 + index,
                name=name,
            )
            for index, (host, name) in enumerate(devices, 1)
        }
        social = SocialStore(server.capture_dir / "social.sqlite3", {
            guest.user_id: guest.name for guest in server.guests.values()
        }, starter_deck())
        for guest in server.guests.values():
            guest.social = social
    if args.lobby_listener:
        listener = LobbySocketServer((args.host, args.pvp_port), LobbySocketHandler)
        listener.guests = server.guests  # type: ignore[attr-defined]
        threading.Thread(target=listener.serve_forever, daemon=True).start()
        print(f"Lobby TCP listener on {args.host}:{args.pvp_port}")
    print(f"Listening on http://{args.host}:{args.port}")
    print(f"Writing captures to {server.capture_dir}")
    print(f"Returning HTTP {server.response_status}")
    print(f"Guest success mode: {server.guest_success}")
    print(f"Tutorial stages mode: {args.tutorial_stages} ({args.tutorial_stage_count} stages)")
    server.serve_forever()


if __name__ == "__main__":
    main()
