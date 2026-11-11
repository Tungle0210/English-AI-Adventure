"""One model-list operation and one bounded generation; no automatic fallback."""
import argparse
from datetime import datetime, timezone
import json
import re
import sys
from dotenv import dotenv_values
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field
from phase1 import ROOT, extract, save


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=5)
    answer: str = Field(min_length=1)
    source_quote: str = Field(min_length=3)


class Quiz(BaseModel):
    model_config = ConfigDict(extra='forbid')
    slide_number: int
    questions: list[Question] = Field(min_length=3, max_length=3)


def validate_quiz(text, source):
    quiz = Quiz.model_validate_json(text)
    if quiz.slide_number != 5:
        raise ValueError('Wrong source slide')
    if len({q.question.casefold().strip() for q in quiz.questions}) != 3:
        raise ValueError('Duplicate questions')
    for q in quiz.questions:
        if ' '.join(q.source_quote.split()) not in ' '.join(source.split()):
            raise ValueError('Evidence quote absent from slide')
        if not q.question.endswith('?'):
            raise ValueError('Expected English question punctuation')
    return quiz


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='gemini-3.5-flash-lite', choices=['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.8-flash'])
    parser.add_argument('--free-plan-confirmed', action='store_true', required=True)
    parser.add_argument('--validate-saved', action='store_true', help='No network: validate saved response and update model')
    args = parser.parse_args()
    cfg = dotenv_values(ROOT / 'backend/.env', interpolate=False)
    key = cfg.get('GEMINI_API_KEY')
    if not key:
        print('FAIL: missing API key')
        return 1
    deck = extract(ROOT / 'input/Unit 6 Lesson 2 Period 3.pptx')
    source = '\n'.join(t.strip() for t in deck['slides'][4]['text'] if t.strip())
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'model': args.model,
              'free_plan': 'confirmed_by_HARRY_in_chat', 'status': 'FAIL',
              'source_file': deck['file'], 'source_sha256': deck['sha256'], 'slide_number': 5,
              'source_text': source, 'generate_requests': 0, 'sdk_retries': 0,
              'max_output_tokens': 1024, 'key_unchanged': True}
    if args.validate_saved:
        result = json.loads((ROOT / 'reports/gemini-recovery.json').read_text(encoding='utf-8'))
        if result['model'] != args.model or result['source_sha256'] != deck['sha256'] or result['source_text'] != source:
            raise ValueError('Saved source/model mismatch')
        quiz = validate_quiz(result['response_text'], source)
        result.update(status='PASS', quiz=quiz.model_dump(), validation={'schema': 'PASS', 'exactly_three': 'PASS', 'source_quotes_whitespace_normalized': 'PASS', 'semantic_review': 'PENDING'})
        for field in ['error_type', 'message', 'http_code']:
            result.pop(field, None)
        result['offline_revalidation'] = True
    try:
        if args.validate_saved:
            raise StopIteration
        with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
            models = [{'name': m.name, 'supported_actions': m.supported_actions} for m in client.models.list()]
            save('models-recovery.json', models)
            result['visible_model_count'] = len(models)
            result['listed_generate_content'] = any(m['name'] == f'models/{args.model}' and 'generateContent' in (m['supported_actions'] or []) for m in models)
            if not result['listed_generate_content']:
                raise ValueError('Requested model not listed with generateContent')
            prompt = ('Create exactly 3 distinct simple English reading-comprehension questions based ONLY on the slide text below. '
                      'The slide is short: question variations are acceptable; invent no additional facts. '
                      'Each item must contain an English question, its correct short answer, and an exact source_quote from the slide supporting it. '
                      'Use slide_number 5. Return JSON only.\nSLIDE TEXT:\n' + source)
            result['generate_requests'] = 1
            response = client.models.generate_content(model=args.model, contents=prompt,
                config=types.GenerateContentConfig(temperature=0, max_output_tokens=1024,
                    response_mime_type='application/json', response_json_schema=Quiz.model_json_schema()))
        text = (response.text or '').replace(key, '[REDACTED]')
        result['response_text'] = text
        result['usage'] = response.usage_metadata.model_dump(mode='json') if response.usage_metadata else None
        quiz = validate_quiz(text, source)
        result.update(status='PASS', quiz=quiz.model_dump(), validation={'schema': 'PASS', 'exactly_three': 'PASS', 'source_quotes': 'PASS', 'semantic_review': 'PENDING'})
    except StopIteration:
        pass
    except Exception as error:
        result['error_type'] = type(error).__name__
        code = getattr(error, 'code', None)
        if isinstance(code, int):
            result['http_code'] = code
        message = getattr(error, 'message', '')
        if isinstance(message, str):
            result['message'] = re.sub(r'https?://\S+', '[URL omitted]', message.replace(key, '[REDACTED]'))[:1500]
    # Update only the model assignment after a successful real generation + schema check.
    if result['status'] == 'PASS':
        env_path = ROOT / 'backend/.env'
        original = env_path.read_bytes()
        replacement = ('GEMINI_MODEL=' + args.model).encode()
        updated, count = re.subn(rb'(?m)^[ \t]*(?:export[ \t]+)?GEMINI_MODEL[ \t]*=[^\r\n]*', replacement, original)
        if count != 1:
            result.update(status='FAIL', config_update='Ambiguous model assignment; .env unchanged')
        else:
            env_path.write_bytes(updated)
            after = dotenv_values(env_path, interpolate=False)
            if after.get('GEMINI_API_KEY') != key or after.get('GEMINI_MODEL') != args.model:
                env_path.write_bytes(original)
                result.update(status='FAIL', config_update='Validation failed; rolled back')
            else:
                result['config_update'] = 'PASS; only GEMINI_MODEL assignment replaced'
    save('gemini-recovery.json', result)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
