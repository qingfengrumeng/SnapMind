"""Model-specific system voices from the provider's published catalogue.

DashScope's list_voice customization API lists account-created cloned voices,
not its system voices. Never misrepresent that response as a system catalogue.
No API key is sent to the public documentation host.
"""
import json
import re
from html.parser import HTMLParser

import httpx
from fastapi import HTTPException

CATALOG_URL = 'https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list'
SUPPORTED_MODELS = {'qwen-audio-3.1-tts-flash', 'qwen-audio-3.0-tts-flash', 'qwen-audio-3.0-tts-plus'}


class VoiceCatalog(HTMLParser):
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.section = ''
        self.heading = None
        self.heading_text = ''
        self.group = ''
        self.cells = None
        self.cell = None
        self.codes = []
        self.in_code = False
        self.voices = {}

    def handle_starttag(self, tag, attrs):
        if tag in ('h2', 'h3', 'h4'):
            self.heading = tag
            self.heading_text = ''
        if tag == 'tr' and self.section == self.model:
            self.cells = []
            self.codes = []
        if tag == 'td' and self.cells is not None:
            self.cell = ''
        if tag == 'code' and self.cell is not None:
            self.in_code = True
            self.codes.append('')
        if tag == 'br' and self.cell is not None:
            self.cell += ' '

    def handle_data(self, text):
        if self.heading:
            self.heading_text += text
        if self.cell is not None:
            self.cell += text
            if self.in_code:
                self.codes[-1] += text

    def handle_endtag(self, tag):
        if tag == self.heading:
            if tag in ('h2', 'h3'):
                self.section = self.heading_text.strip()
                self.group = ''
            else:
                self.group = self.heading_text.strip()
            self.heading = None
        if tag == 'code':
            self.in_code = False
        if tag == 'td' and self.cell is not None:
            self.cells.append(self.cell.strip())
            self.cell = None
        if tag == 'tr' and self.cells is not None:
            self.add_row()
            self.cells = None

    def add_row(self):
        cells = self.cells
        if len(cells) < 2:
            return
        voice = next((c.strip() for c in self.codes if re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', c.strip())), '')
        name = cells[0]
        description = ' · '.join(cells[2:-1])
        language = 'en' if '英文' in self.group else 'zh'
        if not voice:
            # Older 3.0 tables use labelled text rather than code elements.
            text = ' '.join(cells)
            match = re.search(r'voice\s*参数\s*[：:]\s*([A-Za-z0-9_.-]+)', text)
            if not match:
                return
            voice = match.group(1)
            match = re.search(r'名称\s*[：:]\s*(.*?)\s*voice', text)
            name = match.group(1).strip() if match else voice
            description = self.group
            language = 'en' if '精品英文' in text else 'zh'
        self.voices[voice] = {'id': voice, 'name': name, 'description': description, 'language': language}


def parse_catalog(document, model):
    marker = 'window.__ICE_PAGE_PROPS__='
    if marker in document:
        data, _ = json.JSONDecoder().raw_decode(document.split(marker, 1)[1].lstrip())
        document = data['docDetailData']['storeData']['data']['content']
    parser = VoiceCatalog(model)
    parser.feed(document)
    if not parser.voices:
        raise ValueError('No model-specific voices in catalogue')
    return list(parser.voices.values())


async def list_voices(config):
    model = config.model.strip()
    if config.kind != 'tts':
        raise HTTPException(400, '只有 TTS 配置支持获取音色列表')
    if config.provider != 'dashscope' or model not in SUPPORTED_MODELS:
        raise HTTPException(400, '此模型暂无系统音色目录，请在音色下拉框中输入音色 ID')
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            async with client.stream('GET', CATALOG_URL) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        raise ValueError('Catalogue too large')
        voices = parse_catalog(content.decode('utf-8'), model)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, '获取官方音色列表失败，请稍后重试；也可输入音色 ID') from None
    return {'model': model, 'voices': voices, 'source': CATALOG_URL}
