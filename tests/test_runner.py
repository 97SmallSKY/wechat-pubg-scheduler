import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))
import pubg
import run


class RunnerTests(unittest.TestCase):
    def test_preview_mentions_only_matched_players_with_stats(self):
        data = [{
            "name": "One", "status": "records", "summary": {
                "matches": 1, "wins": 0, "kills": 1, "eliminated_matches": 1,
                "kd_estimate": 1.0, "average_damage": 275.1, "first_start": None,
                "latest": {"stats": {"kills": 1, "damageDealt": 275.1, "winPlace": 4},
                           "ended_at": None, "stored_at": "2026-06-03T21:35:00+08:00"},
            },
        }, {"name": "Two", "status": "no_records"}]
        players = [{"steam": "One", "wechat": "真实昵称"}, {"steam": "Two", "wechat": "无战绩"}]
        with patch.object(pubg, "collect", return_value=data) as collect:
            report = run.preview({"report_day": "2026-06-03", "config": {"players": players}}, "fixture")
        collect.assert_called_once_with(["One", "Two"], date(2026, 6, 3), "fixture")
        self.assertEqual(report["mentions"], ["真实昵称"])
        self.assertEqual(len(report["messages"]), 1)
        self.assertIn("下把补枪和集火别慢半拍", report["messages"][0])
        self.assertIn("Two：今日未查到已完成对局", report["messages"][0])

    def test_one_authenticated_lookup_and_error_preservation(self):
        requests = []
        error = HTTPError("https://example.test", 429, "", None, None)
        self.addCleanup(error.close)

        def request(path, key=None):
            requests.append((path, key))
            raise error
        with self.assertRaises(HTTPError):
            pubg.collect(["One", "Two"], date(2026, 6, 3), "fixture", request=request)
        self.assertEqual(len(requests), 1)
        self.assertIn("One%2CTwo", requests[0][0])
        self.assertEqual(requests[0][1], "fixture")

    def test_packs_full_paragraphs(self):
        self.assertEqual(pubg.pack_paragraphs(["一二三", "四五", "六"], 6), ["一二三", "四五\n\n六"])


if __name__ == "__main__":
    unittest.main()
