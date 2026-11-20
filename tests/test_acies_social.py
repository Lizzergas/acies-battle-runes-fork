import tempfile
import unittest
from pathlib import Path

from tools.acies_mock_server import MockState, chat_payload, gateway_string, login_success_response, read_chat_string, starter_deck
from tools.acies_social import HISTORY_LIMIT, SocialStore


class SocialTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "social.sqlite3"
        self.names = {1: "Alice", 2: "Bob", 3: "Carol"}
        self.social = SocialStore(self.path, self.names, starter_deck())
        self.addCleanup(self.social.db.close)
        self.players = [MockState(tutorial_stages=False, tutorial_stage_count=3, user_id=user_id, name=name)
                        for user_id, name in self.names.items()]
        for player in self.players:
            player.social = self.social

    def test_clan_wallet_and_membership_persist(self):
        owner, member, outsider = self.players
        account = login_success_response(owner)["account"]
        self.assertEqual(account["gold"], 100_000)
        self.assertEqual(account["material"][0], 100_000)
        created = owner.change_clan("create", {"name": "Orbit"})
        clan = created["clanId"]
        self.assertEqual(created["gold"], 95_000)
        self.assertIsNone(owner.change_clan("create", {"name": "Other"}))
        self.assertIsNone(outsider.change_clan("create", {"name": "orbit"}))
        self.assertEqual(outsider.gold(), 100_000)
        self.assertEqual(self.social.search("orb")[0]["clanId"], clan)
        self.assertEqual(member.change_clan("join", {"clanId": clan})["clan"]["memberCount"], 2)
        self.assertIsNone(member.change_clan("change-notice", {"notice": "Unauthorized"}))
        self.assertEqual(owner.change_clan("change-notice", {"notice": "Welcome"})["clan"]["notice"], "Welcome")
        reopened = SocialStore(self.path, self.names, starter_deck())
        self.addCleanup(reopened.db.close)
        self.assertEqual(reopened.gold_spent(owner.user_id), 5000)
        self.assertEqual(reopened.clan_id(member.user_id), clan)
        self.assertEqual(login_success_response(member)["account"]["clan"]["clanId"], clan)
        owner.change_clan("leave", {})
        self.assertEqual(member.change_clan("change-notice", {"notice": "New leader"})["clan"]["notice"], "New leader")

    def test_chat_history_is_scoped_and_bounded(self):
        owner, member, outsider = self.players
        clan = owner.change_clan("create", {"name": "Orbit"})["clanId"]
        member.change_clan("join", {"clanId": clan})
        self.assertIsNone(self.social.post(outsider.user_id, "Private", clan=True))
        for count in range(HISTORY_LIMIT + 2):
            self.social.post(member.user_id, f"Clan message {count}", clan=True)
        self.assertEqual(len(self.social.history(clan)), HISTORY_LIMIT)
        self.assertEqual(self.social.history(clan)[0].text, "Clan message 2")
        self.assertEqual(self.social.history(0), [])
        member.change_clan("leave", {})
        self.assertIsNone(self.social.post(member.user_id, "Left", clan=True))
        owner.change_clan("leave", {})
        self.assertEqual(self.social.history(clan), [])

    def test_gateway_string_bounds(self):
        self.assertEqual(read_chat_string(gateway_string("Café") + b"tail"), ("Café", b"tail"))
        with self.assertRaises(ValueError):
            read_chat_string(b"\x0fshort")
        message = self.social.post(self.players[0].user_id, "Hello", clan=False)[1]
        self.assertIn(gateway_string("Hello"), chat_payload(message))


if __name__ == "__main__":
    unittest.main()
