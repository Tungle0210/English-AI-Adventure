from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Kind = Literal['vocabulary', 'quiz', 'match', 'listen', 'fill']
KINDS = ['vocabulary', 'quiz', 'match', 'listen', 'fill']


class Item(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Kind
    prompt: str = Field(min_length=3, max_length=400)
    answer: str = Field(min_length=1, max_length=200)
    options: list[str] = Field(min_length=0, max_length=4)
    explanation: str = Field(min_length=3, max_length=600)
    source: int = Field(ge=1, le=100)
    quote: str = Field(min_length=3, max_length=600)
    word: str = Field(max_length=120)
    meaning: str = Field(max_length=200)
    speech: str = Field(max_length=300)
    image: Literal['', 'school', 'building', 'town', 'three'] = ''
    question_type: Literal['language','reading','listening','visual'] = 'language'
    requires_visual: bool = False
    image_asset_id: str = Field(default='', max_length=64, pattern=r'^$|^[a-f0-9]{64}$')
    source_slide: int | None = Field(default=None, ge=1, le=100)
    source_evidence: str = Field(default='', max_length=1800)
    visual_description: str = Field(default='', max_length=800)
    validation_status: Literal['valid','needs_review','blocked'] = 'needs_review'
    visual_subject: str = Field(default='', max_length=120)
    visual_attribute: str = Field(default='', max_length=50)
    hidden: bool = False

    @model_validator(mode='after')
    def playable(self):
        if self.source_slide is not None and self.source_slide != self.source:
            raise ValueError('Slide nguồn không khớp.')
        self.source_slide=self.source
        picture_words = {'school':{'school','schools'}, 'building':{'building','buildings'}, 'town':{'town','towns'}, 'three':{'three','3'}}
        if self.image and (self.kind != 'vocabulary' or self.word.casefold() not in picture_words[self.image]):
            raise ValueError('Minh họa phải khớp từ vựng được chọn.')
        if self.kind in ('quiz', 'listen', 'vocabulary'):
            if len(self.options) < 2 or len(set(self.options)) != len(self.options) or self.answer not in self.options:
                raise ValueError('Cần 2–4 lựa chọn khác nhau và đáp án nằm trong lựa chọn.')
        if self.kind in ('vocabulary', 'match') and (not self.word or not self.meaning):
            raise ValueError('Thẻ từ/ghép từ cần từ và nghĩa.')
        if self.kind == 'vocabulary' and self.answer != self.meaning:
            raise ValueError('Đáp án thẻ từ phải là nghĩa của từ.')
        if self.kind == 'match' and self.answer != self.meaning:
            raise ValueError('Đáp án ghép từ phải là nghĩa của từ.')
        if self.kind == 'listen' and not self.speech:
            raise ValueError('Câu nghe cần nội dung tiếng Anh để đọc.')
        if self.kind == 'fill' and '___' not in self.prompt:
            raise ValueError('Câu điền từ cần ký hiệu ___.')
        return self


class Generated(BaseModel):
    model_config = ConfigDict(extra='forbid')
    questions: list[Item] = Field(min_length=1, max_length=20)


class GenerateRequest(BaseModel):
    force_refresh: bool = False
    append: bool = False
    grade: Literal[3, 4, 5] = 3
    count: int = Field(default=5, ge=1, le=20)
    difficulty: Literal['easy', 'medium', 'hard'] = 'easy'
    evidence_mode: Literal['auto','visual'] = 'auto'
    kinds: list[Kind] = Field(default_factory=lambda: KINDS.copy(), min_length=1, max_length=5)

    @model_validator(mode='after')
    def valid_count(self):
        if len(set(self.kinds)) != len(self.kinds) or self.count < len(self.kinds):
            raise ValueError('Số câu phải ít nhất bằng số hoạt động đã chọn.')
        if 'match' in self.kinds and self.count < len(self.kinds) + 1:
            raise ValueError('Ghép từ cần ít nhất 2 cặp; hãy tăng số câu.')
        return self


class Editable(Item):
    id: str = Field(min_length=1, max_length=64)
    approved: bool = False


class LessonUpdate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    grade: Literal[3, 4, 5]
    revision: int
    questions: list[Editable] = Field(max_length=40)

    @model_validator(mode='before')
    @classmethod
    def strip_server_fields(cls,value):
        if isinstance(value,dict) and isinstance(value.get('questions'),list):
            value=dict(value,questions=[{k:v for k,v in q.items() if k not in ('quality_issues','media_url')} if isinstance(q,dict) else q for q in value['questions']])
        return value


def verify_sources(items, document):
    sources = {s['number']: ' '.join(s['text'].split()) for s in document['sections']}
    for asset in document.get('assets',[]):
        if asset.get('reviewed') and asset.get('transcript_confirmed') and asset.get('source') in sources:
            sources[asset['source']]+=' '+' '.join(asset.get('transcript','').split())
    for q in items:
        if q.requires_visual or q.question_type=='visual':
            if q.source not in sources:
                raise ValueError('Không tìm thấy phần nguồn.')
            # Pixel/fact/ownership proof is checked independently by quality.py.
            continue
        if q.source not in sources or ' '.join(q.quote.split()) not in sources[q.source]:
            raise ValueError(f'Nguồn trích dẫn không khớp phần {q.source}.')
    keys = [(q.kind, q.prompt.casefold()) for q in items if not q.hidden]
    if len(set(keys)) != len(keys):
        raise ValueError('Có câu hỏi trùng nội dung trong cùng hoạt động.')
