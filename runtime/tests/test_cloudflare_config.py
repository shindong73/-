import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class WorkerConfigurationTests(unittest.TestCase):
    def test_cron_and_caption_kv_binding_survive_wrangler_deploy(self):
        config=tomllib.loads((ROOT / "cloudflare" / "wrangler.toml").read_text(encoding="utf8"))
        self.assertEqual(config["triggers"]["crons"], ["* * * * *"])
        self.assertEqual(config["name"], "shindong-news-minute-trigger")
        kv=config.get("kv_namespaces", [])
        self.assertEqual(len(kv),1)
        self.assertEqual(kv[0]["binding"],"CAPTION_LOGS")
        self.assertEqual(kv[0]["id"],"1be3aac9ee67430885b6ed108b8f87f3")

if __name__ == "__main__":
    unittest.main()
