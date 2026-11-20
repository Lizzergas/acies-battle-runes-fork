import argparse
import http.client
import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path

from tools.acies_accounts import AccountError, AccountStore, gateway_token
from tools.acies_mock_server import (
    Community, CommunityGateway, CommunityHandler, CommunityHTTPServer, LobbySocketHandler, MockState,
    decrypt_secure_payload, encrypt_secure_payload, gateway_string, login_success_response,
)


PASSWORD = "a separate test password"


class Peer:
    def __init__(self, address, user_id, secret):
        self.socket = socket.create_connection(address, timeout=3)
        self.stream = self.socket.makefile("rb")
        self.last_sent = 0
        self.last_received = 0
        self.send(b"\x00\x12\x00" + struct.pack("<Q", user_id) + gateway_string(secret) + b"\0\0")

    def send(self, payload):
        self.socket.sendall(LobbySocketHandler.header.pack(b"TC", self.last_sent, len(payload)) + payload)
        self.last_sent += 1

    def receive(self):
        header = self.stream.read(LobbySocketHandler.header.size)
        if not header:
            return None
        magic, seq, size = LobbySocketHandler.header.unpack(header)
        assert (magic, seq) == (b"TC", self.last_received)
        self.last_received += 1
        return self.stream.read(size)

    def receive_until(self, predicate):
        for _ in range(100):
            packet = self.receive()
            if packet is None or predicate(packet):
                return packet
        raise AssertionError("Did not receive the expected gateway response")

    def close(self):
        self.stream.close()
        self.socket.close()


class CommunityTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.path = Path(root.name) / "community.sqlite3"
        self.accounts = AccountStore(self.path)
        self.addCleanup(self.accounts.close)
        args = argparse.Namespace(community_db=self.path, open_registration=False, trusted_proxy=False, enable_chat=False,
                                  admission_url="https://acies.example.test", pvp_port=9090,
                                  tutorial_stages=False, tutorial_stage_count=3)
        community = Community(self.accounts, args)
        self.addCleanup(community.social.db.close)
        self.http = CommunityHTTPServer(("127.0.0.1", 0), CommunityHandler, max_clients=8)
        self.gateway = CommunityGateway(("127.0.0.1", 0), LobbySocketHandler, max_clients=8)
        self.http.community = self.gateway.community = community
        community.listener = self.gateway
        for server in (self.http, self.gateway):
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

    def request(self, method, path, *, token=None, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.http.server_address, timeout=3)
        headers = dict(headers or {})
        if token:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            body = json.dumps(body).encode()
            if path.startswith("/api/client-secure/"):
                body = encrypt_secure_payload(body)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
            if response.headers["Content-Type"] == "application/octet-stream":
                data = decrypt_secure_payload(data)
            return response.status, json.loads(data)
        finally:
            connection.close()

    def register(self, username):
        status, data = self.request("POST", "/community/register", body={
            "username": username, "password": PASSWORD, "invite": self.accounts.invite(1),
        })
        self.assertEqual(status, 201)
        token = data["token"]
        status, data = self.request("POST", "/api/client/login", token=token, body={})
        self.assertEqual(status, 200)
        self.assertEqual(data["account"]["name"], username)
        return token, data["account"]["userId"], data["secret"]

    def test_account_isolation_persistence_and_revoke(self):
        status, admission = self.request("POST", "/api/client/admission", body={})
        self.assertEqual((status, admission["host"]), (200, "https://acies.example.test"))
        token, user_id, secret = self.register("Alice")
        second, other_id, _ = self.register("Bob")
        self.assertNotEqual(user_id, other_id)
        self.assertEqual(self.request("POST", "/api/client/login", body={"userId": user_id, "secret": secret})[0], 401)
        self.assertEqual(self.request("POST", "/api/client-secure/deck/change-name", token=token,
                                      body={"page": 0, "name": "Alice Deck"})[1]["name"], "Alice Deck")
        self.assertEqual(self.accounts.progress(user_id)[0]["deck_name"], "Alice Deck")
        self.assertNotIn("deck_name", self.accounts.progress(other_id)[0])
        self.assertEqual(self.request("POST", "/api/client-secure/pvp-server", token=second,
                                      headers={"X-Acies-Gateway-Port": "42000"}), (200, {"host": "127.0.0.1", "port": 42000}))
        self.assertEqual(self.request("POST", "/community/logout", token=token)[0], 200)
        self.assertEqual(self.request("GET", "/community/session", token=token)[0], 401)
        self.assertEqual(self.request("GET", "/community/session", token=second)[0], 200)
        self.assertEqual(self.request("POST", "/community/login", body={"username": "alice", "password": "incorrect-password"})[0], 401)
        status, data = self.request("POST", "/community/login", body={"username": "alice", "password": PASSWORD})
        self.assertEqual(status, 200)
        reopened = AccountStore(self.path)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.authenticate(data["token"]).user_id, user_id)
        self.assertEqual(reopened.progress(user_id)[0]["deck_name"], "Alice Deck")
        backup = self.path.with_name("backup.sqlite3")
        self.accounts.backup(backup)
        restored = AccountStore(backup)
        self.addCleanup(restored.close)
        self.assertEqual(restored.progress(user_id)[0]["deck_name"], "Alice Deck")

    def test_onboarding_progress_survives_account_switch_and_restart(self):
        first, first_id, _ = self.register("Alice")
        second, second_id, _ = self.register("Bob")

        def account(token):
            return self.request("POST", "/api/client/login", token=token, body={})[1]["account"]

        def battle(stage, transaction, result=1):
            return self.request("POST", "/api/client-secure/game/result", token=first, body={
                "transaction": transaction,
                "result": {"mode": 32, "result": result, "single": {"campaignStage": stage}},
            })[1]["rewardResult"]["campaignStages"]

        def tutorial(token, category, step, skip=False):
            return self.request("POST", "/api/client-secure/tutorial/step", token=token,
                                body={"category": category, "step": step, "skip": skip})

        self.assertEqual(account(first)["campaignStages"], [])
        self.assertEqual(battle(1, 1, result=2), [])
        self.assertEqual(battle(1, 2), [1])
        self.assertEqual(battle(2, 3), [1, 1])
        self.assertEqual(battle(3, 4), [1, 1, 1, 0])
        self.assertEqual(battle(3, 4), [1, 1, 1, 0])
        self.assertEqual(account(first)["tutorialSteps"], [{"category": 0, "step": 255}])
        status, step = tutorial(first, 0, 1)
        self.assertEqual((status, step["step"], step["skip"]), (200, 255, True))
        self.assertEqual(tutorial(second, 1, 3)[1]["step"], 3)
        self.assertEqual(tutorial(second, 1, 2)[1]["step"], 3)
        self.assertEqual(tutorial(second, 13, 1)[0], 400)
        returning = self.request("POST", "/community/login", body={"username": "Alice", "password": PASSWORD})[1]["token"]
        self.assertEqual(account(returning)["tutorialSteps"], [{"category": 0, "step": 255}])
        self.assertEqual(account(second)["campaignStages"], [])
        self.assertEqual(account(second)["tutorialSteps"], [{"category": 1, "step": 3}])

        reopened = AccountStore(self.path)
        self.addCleanup(reopened.close)
        for token, user_id in ((returning, first_id), (second, second_id)):
            restored = MockState(tutorial_stages=True, tutorial_stage_count=3, accounts=reopened, user_id=user_id)
            fresh_login = login_success_response(restored)["account"]
            for key in ("campaignStages", "tutorialSteps"):
                self.assertEqual(fresh_login[key], account(token)[key])

    def test_preexisting_accounts_keep_their_unlocked_lobby(self):
        token = self.accounts.register("Returning", PASSWORD, self.accounts.invite(1), open_registration=False)
        player = self.accounts.authenticate(token)
        with self.accounts.db:
            self.accounts.db.execute("DELETE FROM player_state WHERE user_id = ?", (player.user_id,))
        account = self.request("POST", "/api/client/login", token=token, body={})[1]["account"]
        self.assertEqual(account["campaignStages"], [0, 0, 0, 1, 1, 1])
        self.assertEqual(account["tutorialSteps"], [{"category": 0, "step": 255}])

    def test_invitation_is_single_use_and_casefolded_names_are_unique(self):
        invite = self.accounts.invite(1)
        self.accounts.register("Alice", PASSWORD, invite, open_registration=False)
        with self.assertRaises(AccountError) as used:
            self.accounts.register("Other", PASSWORD, invite, open_registration=False)
        self.assertEqual(used.exception.status, 403)
        retry = self.accounts.invite(1)
        with self.assertRaises(AccountError) as duplicate:
            self.accounts.register("ALICE", PASSWORD, retry, open_registration=False)
        self.assertEqual(duplicate.exception.status, 409)
        self.accounts.register("Other", PASSWORD, retry, open_registration=False)

    def test_gateway_same_ip_players_reconnect_and_persist_results(self):
        first, first_id, first_secret = self.register("Alice")
        second, second_id, second_secret = self.register("Bob")
        peer = Peer(self.gateway.server_address, first_id, second_secret)
        self.assertIsNone(peer.receive())
        peer.close()
        a = Peer(self.gateway.server_address, first_id, first_secret)
        b = Peer(self.gateway.server_address, second_id, second_secret)
        self.addCleanup(a.close)
        for client in (a, b):
            self.assertEqual(client.receive(), bytes(4))
            client.send(bytes([3, 2, 0, 0, 0, 0, 0]))
            self.assertEqual(client.receive()[0], 3)
            client.send(bytes([12, 1]))
            self.assertEqual(client.receive()[0], 12)
        for client in (a, b):
            joined = client.receive()
            self.assertEqual(joined[:2], bytes([18, 0]))
            match_id = struct.unpack_from("<I", joined, 2)[0]
            self.assertEqual(client.receive()[0], 29)
            client.send(bytes([30]))
        self.assertEqual(a.receive(), bytes([30]))
        self.assertEqual(b.receive(), bytes([30]))
        update = b.receive()
        resume_at = struct.unpack_from("<I", update, 2)[0] + update[1]
        b.close()
        a.send(bytes([32, 0, 0]))
        order = a.receive_until(lambda packet: packet[0] == 32 and len(packet) > 10)
        b = Peer(self.gateway.server_address, second_id, second_secret)
        self.addCleanup(b.close)
        self.assertEqual(b.receive(), bytes(4))
        b.send(struct.pack("<BIIB", 18, match_id, resume_at, 1))
        self.assertEqual(b.receive()[:2], bytes([18, 0]))
        self.assertEqual(b.receive(), order)
        self.assertEqual(len(b.receive()), 10)
        a.send(bytes([37, 2]))
        b.send(bytes([37, 1]))
        b.send(bytes([100]))
        self.assertEqual(b.receive_until(lambda packet: packet == bytes([100])), bytes([100]))
        a.send(bytes([100]))
        self.assertEqual(a.receive_until(lambda packet: packet == bytes([100])), bytes([100]))
        self.assertEqual(self.accounts.match_counts(first_id), (1, 0))
        self.assertEqual(self.accounts.match_counts(second_id), (1, 1))
        self.assertEqual(first_secret, gateway_token(first))
        self.assertEqual(self.request("POST", "/community/logout", token=second)[0], 200)
        self.assertIsNone(b.receive_until(lambda packet: packet[0] == 100))


if __name__ == "__main__":
    unittest.main()
