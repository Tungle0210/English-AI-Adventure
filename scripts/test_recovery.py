import copy
import json
import unittest
from dotenv import dotenv_values
from phase1 import ROOT, extract
from recover_gemini import validate_quiz


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads((ROOT / 'reports/gemini-recovery.json').read_text(encoding='utf-8'))
        self.quiz = json.loads(self.evidence['response_text'])

    def test_real_response_and_source(self):
        deck = extract(ROOT / self.evidence['source_file'])
        self.assertEqual(deck['sha256'], self.evidence['source_sha256'])
        self.assertEqual(self.evidence['status'], 'PASS')
        validate_quiz(self.evidence['response_text'], self.evidence['source_text'])
        self.assertEqual(dotenv_values(ROOT / 'backend/.env')['GEMINI_MODEL'], self.evidence['model'])

    def test_rejects_invalid_quizzes(self):
        for mutation in ['missing_answer', 'two_questions', 'wrong_slide', 'invented_quote', 'duplicate', 'extra_field', 'invalid_json']:
            q = copy.deepcopy(self.quiz)
            if mutation == 'missing_answer':
                del q['questions'][0]['answer']
            elif mutation == 'two_questions':
                q['questions'].pop()
            elif mutation == 'wrong_slide':
                q['slide_number'] = 4
            elif mutation == 'invented_quote':
                q['questions'][0]['source_quote'] = 'There are fifty buildings.'
            elif mutation == 'duplicate':
                q['questions'][1] = q['questions'][0]
            elif mutation == 'extra_field':
                q['unexpected'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_quiz('invalid' if mutation == 'invalid_json' else json.dumps(q), self.evidence['source_text'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
