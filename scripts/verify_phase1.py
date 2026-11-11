"""Offline evidence verification. Never prints secrets or makes API calls."""
import json
from pathlib import Path
import unittest
from dotenv import dotenv_values
from phase1 import ROOT, extract


class Phase1Tests(unittest.TestCase):
    def test_environment_evidence(self):
        evidence = json.loads((ROOT / 'reports/environment.json').read_text(encoding='utf-8'))
        self.assertTrue(evidence['pass'])
        self.assertTrue(all(x['pass'] for x in evidence['gitignore'].values()))

    def test_powerpoint_readback(self):
        evidence = json.loads((ROOT / 'reports/powerpoint.json').read_text(encoding='utf-8'))
        self.assertTrue(evidence)
        for deck in evidence:
            self.assertEqual(extract(ROOT / deck['file']), deck)

    def test_no_secret_in_deliverables(self):
        key = dotenv_values(ROOT / 'backend/.env', interpolate=False).get('GEMINI_API_KEY')
        self.assertTrue(key)
        targets = [ROOT / name for name in ['README.md', 'PLAN.md', 'STATUS.md', '.gitignore']]
        targets += [p for folder in ['scripts', 'reports', 'backend'] for p in (ROOT / folder).rglob('*') if p.is_file() and '.venv' not in p.parts and '__pycache__' not in p.parts and p.name != '.env']
        for path in targets:
            self.assertFalse(key.encode() in path.read_bytes(), 'Secret detected in deliverable')

    def test_api_evidence_is_not_false_pass(self):
        evidence = json.loads((ROOT / 'reports/gemini.json').read_text(encoding='utf-8'))
        if evidence['status'] == 'PASS':
            self.assertEqual(evidence['response'].strip(), 'ENGLISH_AI_ADVENTURE_OK')
        else:
            self.assertIn('error_type', evidence)


if __name__ == '__main__':
    unittest.main(verbosity=2)
