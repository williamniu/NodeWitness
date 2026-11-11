"""Real Docker acceptance, separate from model trials."""

import json
import unittest

from finance_runtime.runner import Environment, command
from finance_runtime.sources import ROOT, load_case


class Isolation(unittest.TestCase):
    def test_readonly_selected_case_no_oracle_no_network(self):
        env = Environment(load_case("F00"))
        try:
            env.start()
            info = env.inspection
            self.assertEqual(info["user"], "10001:10001")
            self.assertEqual(info["host_config"]["NetworkMode"], "none")
            self.assertTrue(info["host_config"]["ReadonlyRootfs"])
            self.assertFalse(info["host_config"]["Binds"])
            self.assertEqual(info["host_config"]["CapDrop"], ["ALL"])
            self.assertIn("no-new-privileges", info["host_config"]["SecurityOpt"])
            code = """import json,os,socket,importlib.util
from pathlib import Path
checks={'nonroot':os.getuid()==10001,'only_selected_case':list(Path('/task/pack/cases').iterdir())==[Path('/task/pack/cases/F00')],
'oracle_excluded':not Path('/evaluation').exists() and importlib.util.find_spec('scripts') is None,
'no_socket':not Path('/var/run/docker.sock').exists(),'no_credentials':not os.path.exists('/root/.aws')}
try:
 Path('/task/pack/cases/F00/positions.csv').write_text('forged');checks['source_readonly']=False
except PermissionError:checks['source_readonly']=True
try:
 socket.create_connection(('1.1.1.1',443),timeout=1);checks['network_denied']=False
except OSError:checks['network_denied']=True
print(json.dumps(checks))"""
            checks = json.loads(command(["docker", "exec", env.container, "python", "-c", code]))
            self.assertTrue(all(checks.values()), checks)
            calculated = env.call("compute_review", {})
            self.assertEqual(calculated["findings"][1]["observed"]["pct"], "10.00")
            catalog = env.call("read_source", {"file": "source-catalog.json", "record_ids": ["SRC-PX"], "page": 1})
            self.assertEqual(catalog["records"][0]["file"], "prices.csv")
            schema = env.call("read_source", {"file": "schema.json", "record_ids": [], "page": 1})
            self.assertLessEqual(len(schema["json_text_chunk"]), 4096)
            for name, args in (("approve", {}), ("read_source", {"file": "../../evaluation/reference-results.json", "record_ids": [], "page": 0})):
                with self.assertRaises(RuntimeError):
                    env.call(name, args)
            (ROOT / "outputs/nw003/isolation.json").write_text(json.dumps({"inspection": info, "checks": checks, "deny_tests": 2}, indent=2) + "\n")
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
