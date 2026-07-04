#!/usr/bin/env python3
"""Local ACIES endpoint capture server.

By default this records request shapes and returns handled application errors.
Use --guest-success to try an offline, synthetic guest payload while mapping the
dead backend protocol.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


SESSION_ENCRYPTION_KEY = "localmockkey0001"
ASSET_VERSION = 83
ASSET_REVISION = 177
EMPTY_ASSET_ID = -1
COMPLETED_CAMPAIGN_STAGES = [0, 0, 0, 1, 1, 1]
DEFAULT_TUTORIAL_STAGE_COUNT = 3
SEASON_REWARD_DIVISION_SLOTS = 31
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


class MockState:
    def __init__(self, *, tutorial_stages: bool, tutorial_stage_count: int) -> None:
        self.tutorial_stages = tutorial_stages
        self.tutorial_stage_count = tutorial_stage_count
        self._lock = threading.Lock()
        self._completed_tutorial_stages = 0

    def reset_login_progress(self) -> None:
        if not self.tutorial_stages:
            return
        with self._lock:
            self._completed_tutorial_stages = 0

    def campaign_stages(self) -> list[int]:
        if not self.tutorial_stages:
            return list(COMPLETED_CAMPAIGN_STAGES)
        with self._lock:
            return self._campaign_stages_locked()

    def campaign_tutorial_complete(self) -> bool:
        if not self.tutorial_stages:
            return True
        with self._lock:
            return self._completed_tutorial_stages >= self.tutorial_stage_count

    def advance_campaign_stage(self, request: dict[str, object]) -> list[int]:
        if not self.tutorial_stages:
            return list(COMPLETED_CAMPAIGN_STAGES)

        requested_stage = campaign_stage_from_request(request)
        with self._lock:
            if requested_stage is not None:
                self._completed_tutorial_stages = max(
                    self._completed_tutorial_stages,
                    min(requested_stage, self.tutorial_stage_count),
                )
            elif self._completed_tutorial_stages < self.tutorial_stage_count:
                self._completed_tutorial_stages += 1
            return self._campaign_stages_locked()

    def _campaign_stages_locked(self) -> list[int]:
        if self._completed_tutorial_stages >= self.tutorial_stage_count:
            return list(COMPLETED_CAMPAIGN_STAGES)
        return list(COMPLETED_CAMPAIGN_STAGES[: self._completed_tutorial_stages])


def campaign_stage_from_request(request: dict[str, object]) -> int | None:
    stage = request.get("stage")
    if isinstance(stage, int):
        return stage

    result = request.get("result")
    if not isinstance(result, dict):
        return None
    single = result.get("single")
    if not isinstance(single, dict):
        return None
    campaign_stage = single.get("campaignStage")
    return campaign_stage if isinstance(campaign_stage, int) else None


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


def starter_deck() -> dict[str, object]:
    return {
        "name": "Local Deck",
        "cards": STARTER_CARD_IDS,
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
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def user_record() -> dict[str, int]:
    return {
        "score": 0,
        "scoreHigh": 0,
        "ranking": 0,
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
        "products": [rune_workshop_product()],
    }


def card_shop_info() -> dict[str, object]:
    return {
        "products": [],
        "nextResetTicket": 0,
        "nextResetCash": 0,
        "remainTime": 0,
    }


def user_thumb() -> dict[str, object]:
    return {
        "userId": 1000001,
        "name": "LocalGuest",
        "country": 0,
        "decorations": [0, 0, 0, 0],
        "pictureUrl": "",
    }


def season_result() -> dict[str, int]:
    return {
        "score": 0,
        "ranking": 0,
        "division": 0,
    }


def rune_workshop_product() -> dict[str, object]:
    return {
        "productId": 0,
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


def mock_account(campaign_stages: list[int]) -> dict[str, object]:
    deck = starter_deck()
    all_cards = [starter_card(card_id) for card_id in STARTER_CARD_IDS]
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
        "cards": STARTER_CARD_IDS,
        "runes": deck["runes"],
        "cardCounts": [20 for _ in STARTER_CARD_IDS],
        "gold": 0,
        "cash": 0,
        "medal": 0,
        "badge": 0,
        "material": [0, 0, 0],
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
        "arena": {},
        "scoreRewardObtain": 0,
        "questStatus": quest_status(),
        "achievements": [],
        "boosters": [],
        "challenges": [],
        "challengeRemainTime": 0,
        "subscriptions": [],
        "season": 0,
        "seasonRemainTime": 0,
        "seasonReward": season_reward(),
        "tutorialSteps": [],
        "campaignStages": campaign_stages,
        "minigame": {},
        "hotTimeEvents": [],
        "banners": [],
        "socialPlatforms": [],
        "shop": shop_info(),
        "cardShop": card_shop_info(),
        "isDeveloper": False,
    }
    return account


def login_success_response(state: MockState) -> dict[str, object]:
    state.reset_login_progress()
    return {
        "result": 0,
        "secret": "local-offline-secret",
        "encryption": SESSION_ENCRYPTION_KEY,
        "dayChanged": False,
        "account": mock_account(state.campaign_stages()),
    }


def social_link_success_response(body: bytes) -> dict[str, object]:
    social_platform = 0
    try:
        request = json.loads(body.decode("utf-8")) if body else {}
        social_platform = int(request.get("socialPlatform", 0))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {
        "result": 0,
        "userId": 1000001,
        "secret": "local-offline-secret",
        "socialPlatform": social_platform,
    }


def admission_success_response() -> dict[str, object]:
    return {
        "result": 0,
        "assetVersion": ASSET_REVISION,
        "iosReview": False,
        "patchHosts": [],
        "downloadUrl": "",
        "host": "http://10.0.2.2:8080",
        "notices": [],
        "inviteUrl": "",
        "revision": ASSET_VERSION,
    }


def game_result_response(request: dict[str, object], state: MockState) -> dict[str, object]:
    transaction = request.get("transaction", 0)
    campaign_stages = state.advance_campaign_stage(request)
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
    skip = bool(request.get("skip", False))
    if state.tutorial_stages and state.campaign_tutorial_complete():
        step = 999
        skip = True
    return {
        "result": 0,
        "category": request.get("category", 0),
        "step": step,
        "skip": skip,
        "rewardResult": {
            "rewards": [],
            "campaignStages": state.campaign_stages(),
        },
    }


def pvp_server_response() -> dict[str, object]:
    return {
        "host": "10.0.2.2",
        "port": 9090,
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


def profile_stat_response(request: dict[str, object]) -> dict[str, object]:
    user_id = request.get("userId", 1000001)
    return {
        "userId": user_id if isinstance(user_id, int) else 1000001,
        "stat": profile_stat(),
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
        "season": 0,
        "seasonRemainTime": 0,
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
) -> tuple[int, dict[str, object]]:
    parsed = urlparse(path)

    if method == "POST" and parsed.path == "/api/client/admission":
        return 200, admission_success_response()

    if method == "POST" and parsed.path == "/api/client/social-link-validate":
        return 200, {
            "result": 0,
            "mock": True,
        }

    if method == "POST" and parsed.path == "/api/client/social-link":
        if guest_success:
            return 200, social_link_success_response(body)
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
        return 200, pvp_server_response()

    if parsed.path == "/api/client-secure/ping":
        return 200, ping_response()

    if parsed.path == "/api/client-secure/refresh":
        return 200, refresh_response()

    if parsed.path == "/api/client-secure/profile/stat":
        return 200, profile_stat_response(request_json_for_path(parsed.path, body))

    if parsed.path == "/api/client-secure/match-record/list":
        return 200, match_record_list_response(request_json_for_path(parsed.path, body))

    if parsed.path == "/api/client-secure/match-record/lock":
        return 200, match_record_lock_response(request_json_for_path(parsed.path, body))

    if parsed.path == "/api/client-secure/shop/card-info":
        return 200, {
            "cardShop": card_shop_info(),
        }

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
        base = capture_dir / f"{stamp}_{self.command}_{safe_path}"

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

    def _send_placeholder(self, body: bytes) -> None:
        default_status: int = self.server.response_status  # type: ignore[attr-defined]
        guest_success: bool = self.server.guest_success  # type: ignore[attr-defined]
        state: MockState = self.server.mock_state  # type: ignore[attr-defined]
        status, response = route_response(self.command, self.path, body, default_status, guest_success, state)
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
        body = self._read_body()
        self._write_capture(body)
        self._send_placeholder(body)

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture ACIES backend requests locally.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
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
        help="Number of mandatory campaign tutorial stages before returning completed campaign progress.",
    )
    args = parser.parse_args()
    if args.tutorial_stage_count < 1:
        parser.error("--tutorial-stage-count must be at least 1")

    server = ThreadingHTTPServer((args.host, args.port), CaptureHandler)
    server.capture_dir = Path(args.captures)  # type: ignore[attr-defined]
    server.response_status = args.status  # type: ignore[attr-defined]
    server.guest_success = args.guest_success  # type: ignore[attr-defined]
    server.mock_state = MockState(  # type: ignore[attr-defined]
        tutorial_stages=args.tutorial_stages,
        tutorial_stage_count=args.tutorial_stage_count,
    )
    print(f"Listening on http://{args.host}:{args.port}")
    print(f"Writing captures to {server.capture_dir}")
    print(f"Returning HTTP {server.response_status}")
    print(f"Guest success mode: {server.guest_success}")
    print(f"Tutorial stages mode: {args.tutorial_stages} ({args.tutorial_stage_count} stages)")
    server.serve_forever()


if __name__ == "__main__":
    main()
