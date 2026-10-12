import asyncio
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field, model_validator,FiniteFloat, ConfigDict
from typing import Literal
from .model_settings import ModelConfig, read_settings, public_settings, save_settings
from .model_profiles import ProfileConfig, ActiveSelection, get_profiles, get_configuration, save_profile, set_active, test_profile, query_models, open_key_portal, get_active_profile
from .model_inference import complete
from .capture_processing import recognize_async, clean_transcription
from .ocr_settings import OcrConfig, get_ocr, save_ocr, active_ocr, read_ocr, import_ocr_environment, migrate_ocr_configuration
from .ocr_model_catalog import fetch_ocr_models
from .ocr_locator import locate
from .ocr_usage import model_totals
from .usage_analytics import get_usage_analytics
from .inline_translation import TranslationLine,translate_lines
from .capture_analysis import analyze
from .ai_annotations import ExistingAnnotation,ConversationTurn,annotate
from .annotation_grounding import ControlTarget
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .capture_study import StudyTurn,study
from .paddle_ocr import recognize_paddle, probe_ocr
from .model_profiles import unprotect_key
from .image_tools import repair, decode_codes, screen_entities
from .image_conversation import converse, Action
from .agent import run_agent
from .agent.workflow import context_reserve as agent_context_reserve
from .agent.tools import REGISTRY as AGENT_TOOLS
from .image_tool_registry import catalog, arguments_model, default_prompt, ToolName
from .capture_processing import recognize_positions_async
from .capture_analysis import Table
from contextlib import asynccontextmanager
from .local_storage import initialize_paths, business_path, atomic_write, json_text
from .session_store import SessionStore
from .session_memory import MemoryManager, CONTEXT
from .conversation_runtime import ConversationRuntime
from .image_history import generate_title
from .speech_settings import SpeechProfile, SpeechSelection, get_speech, save_speech, select_speech, active_tts, active_asr, draft_speech, import_speech_environment
from .speech_recognition import relay as relay_asr
from .speech_synthesis import synthesize, synthesize_stream, probe as probe_speech
from .speech_voices import list_voices
from .speech_models import fetch_models as fetch_speech_models

HOME=initialize_paths()
DB=business_path()
DATA=DB.parent
DATA.mkdir(parents=True,exist_ok=True)
with sqlite3.connect(DB) as db:
    db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS model_usage (id TEXT PRIMARY KEY, model TEXT NOT NULL, input_tokens INTEGER NOT NULL CHECK(input_tokens>=0), output_tokens INTEGER NOT NULL CHECK(output_tokens>=0), created_at TEXT NOT NULL)')
    if 'tokens_reported' not in {row[1] for row in db.execute('PRAGMA table_info(model_usage)')}:
        db.execute('ALTER TABLE model_usage ADD COLUMN tokens_reported INTEGER NOT NULL DEFAULT 1')
    if 'cached_input_tokens' not in {row[1] for row in db.execute('PRAGMA table_info(model_usage)')}:
        db.execute('ALTER TABLE model_usage ADD COLUMN cached_input_tokens INTEGER CHECK(cached_input_tokens>=0)')
    db.execute('CREATE INDEX IF NOT EXISTS model_usage_time ON model_usage(created_at)')
    db.execute('CREATE TABLE IF NOT EXISTS app_settings (name TEXT PRIMARY KEY, body TEXT NOT NULL)')
import_ocr_environment(DB)
migrate_ocr_configuration(DB)
import_speech_environment(DB)
STORE=SessionStore(HOME)
STORE.import_sessions(DB)
MEMORY=MemoryManager(STORE)
RUNTIME=ConversationRuntime(STORE,MEMORY)

class Asset(BaseModel):
    id: str = Field(max_length=80)
    name: str = Field(max_length=240)
    data: str = Field(max_length=12_000_000)
    width: int = Field(gt=0, le=20000)
    height: int = Field(gt=0, le=20000)
    scenario: Literal['formula','table','error','custom']
    @model_validator(mode='after')
    def image_only(self):
        if not self.data.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')):
            raise ValueError('仅接受 PNG、JPEG 和 WebP 图片')
        return self

class SavedCode(BaseModel):
    text: str = Field(max_length=20000)
    format: str = Field(max_length=80)
    bbox: list[FiniteFloat] = Field(min_length=4,max_length=4)
    url: str | None = Field(default=None,max_length=20000)

class SavedEntity(BaseModel):
    kind: Literal['url','email','phone']
    text: str = Field(max_length=20000)
    url: str = Field(max_length=20000)
    bbox: list[FiniteFloat] = Field(min_length=4,max_length=4)

class SavedImageNote(BaseModel):
    markdown: str = Field(max_length=300000)
    imageIds: list[str] = Field(max_length=6)

class SavedImageResult(BaseModel):
    assetId: str | None = Field(default=None,max_length=80)
    tables: list[Table] | None = Field(default=None,max_length=10)
    codes: list[SavedCode] | None = Field(default=None,max_length=50)
    entities: list[SavedEntity] | None = Field(default=None,max_length=100)
    note: SavedImageNote | None = None

class SavedAnnotation(ExistingAnnotation):
    locationSource: Literal['ocr','uia','object-detection','existing','visual'] | None = None

class SavedImageScene(BaseModel):
    assetId: str = Field(max_length=80)
    annotations: list[SavedAnnotation] = Field(default_factory=list,max_length=100)
    rendered: Asset | None = None

class TextAttachment(BaseModel):
    id: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=160)
    content: str = Field(max_length=100000)

class SavedImageConversation(BaseModel):
    version: Literal[1] = 1
    selectedId: str | None = Field(default=None,max_length=80)
    pictures: list[SavedImageScene] = Field(max_length=6)
    textAttachments: list[TextAttachment] | None = Field(default=None,max_length=6)
    titleGenerated: bool = False

class SavedContextTurn(BaseModel):
    role: Literal['user','assistant']
    text: str = Field(min_length=1,max_length=12000)

class SavedRequestContext(BaseModel):
    assets: list[Asset] = Field(max_length=6)
    selectedId: str | None = Field(default=None,max_length=80)
    prompt: str = Field(default='',max_length=205000)
    history: list[SavedContextTurn] = Field(default_factory=list,max_length=20)
    existing: list[SavedAnnotation] = Field(default_factory=list,max_length=100)
    controls: list[ControlTarget] = Field(default_factory=list,max_length=300)
    language: str = Field(default='zh-CN',max_length=20)

class SavedImageRequest(BaseModel):
    action: Action | None = None
    question: str = Field(max_length=205000)
    toolCall: dict | None = None
    userId: str = Field(max_length=80)
    context: SavedRequestContext | None = None

from .voice_message import VoiceMessage

class Message(BaseModel):
    id: str = Field(max_length=80)
    role: Literal['user','assistant']
    text: str = Field(max_length=300000)
    voice: VoiceMessage | None = None
    action: str | None = None
    sources: list[str] | None = None
    kind: Literal['formula','table','text'] | None = None
    demo: bool | None = None
    imageResult: SavedImageResult | None = None
    textAttachments: list[TextAttachment] | None = Field(default=None,max_length=6)
    paused: bool | None = None
    failed: bool | None = None
    imageRequest: SavedImageRequest | None = None
    images: list[Asset] | None = Field(default=None,max_length=6)
    imageOutput: dict | None = None

class DataRow(BaseModel):
    label: str = Field(max_length=80)
    value: float = Field(allow_inf_nan=False)

class VoiceCallRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    startedAt: str = Field(max_length=40)
    endedAt: str | None = Field(default=None,max_length=40)
    startMessageId: str = Field(min_length=1,max_length=80)
    endMessageId: str | None = Field(default=None,min_length=1,max_length=80)

class Session(BaseModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9-]{1,80}$')
    title: str = Field(min_length=1,max_length=160)
    scenario: Literal['formula','table','error','custom']
    assets: list[Asset] = Field(max_length=20)
    messages: list[Message] = Field(max_length=10000)
    formula: str = Field(max_length=5000)
    rows: list[DataRow] = Field(max_length=100)
    createdAt: str
    updatedAt: str
    pinned: bool = False
    imageConversation: SavedImageConversation | None = None
    voiceCall: VoiceCallRecord | None = None
    @model_validator(mode='after')
    def total_size(self):
        if self.voiceCall:
            call=self.voiceCall
            ids=[m.id for m in self.messages]
            if call.startMessageId not in ids or call.endMessageId is not None and call.endMessageId not in ids:
                raise ValueError('语音通话边界引用的消息不存在')
            start=ids.index(call.startMessageId)
            end=ids.index(call.endMessageId) if call.endMessageId else len(ids)-1
            first=self.messages[start]
            if start>end or first.role!='user' or not first.text.strip() or not first.images or not self.imageConversation:
                raise ValueError('语音通话首条问题必须携带截图')
            if bool(call.endedAt)!=bool(call.endMessageId):
                raise ValueError('语音通话结束时间与结束消息必须同时提供')
            if not any(m.role=='assistant' and m.text.strip() and not m.failed and not m.paused for m in self.messages[start+1:end+1]):
                raise ValueError('语音通话必须收到有效回复后才能保存')
        if sum(len(message.voice.data) for message in self.messages if message.voice)>24_000_000:
            raise ValueError('会话录音总量超过限制，请创建新会话')
        if sum(len(a.data) for a in self.assets)>36_000_000:
            raise ValueError('单个会话图片总量超过限制，请创建新会话')
        if self.imageConversation:
            scene=self.imageConversation
            images={a.id:a for a in self.assets}
            if len(images)!=len(self.assets) or len({p.assetId for p in scene.pictures})!=len(scene.pictures):
                raise ValueError('图片或场景编号不能重复')
            if scene.selectedId is not None and scene.selectedId not in {p.assetId for p in scene.pictures}:
                raise ValueError('选中的图片不存在')
            for picture in scene.pictures:
                asset=images.get(picture.assetId)
                if asset is None:raise ValueError('场景引用的图片不存在')
                if len({a.id for a in picture.annotations})!=len(picture.annotations):raise ValueError('标注编号不能重复')
                if any(a.bbox[2]>asset.width or a.bbox[3]>asset.height for a in picture.annotations):raise ValueError('标注超出图片范围')
        if sum(len(json.dumps(m.imageResult.model_dump(),ensure_ascii=False)) for m in self.messages if m.imageResult)+sum(len(json.dumps(m.imageOutput,ensure_ascii=False)) for m in self.messages if m.imageOutput)>4_000_000:
            raise ValueError('对话结构化结果过多，请创建新对话')
        return self

class ChatRequest(BaseModel):
    session: Session
    action: Literal['explain','formula','table','translate','ocr','chat']
    prompt: str = Field(min_length=1,max_length=6000)

@asynccontextmanager
async def lifespan(_app):
    task=asyncio.create_task(RUNTIME.maintain(get_active_profile,complete,DB))
    try:yield
    finally:
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass
        await asyncio.to_thread(STORE.flush)

app=FastAPI(title='SnapMind local API',version='0.1.0',lifespan=lifespan)
@app.exception_handler(RequestValidationError)
async def invalid_request(_request,error):
    # Never echo submitted images/secrets or non-finite values into error JSON.
    return JSONResponse(status_code=422,content={'detail':[
        {key:item[key] for key in ('loc','msg','type')} for item in error.errors()]})
app.add_middleware(CORSMiddleware,allow_origins=['http://tauri.localhost','https://tauri.localhost','tauri://localhost'],allow_methods=['GET','PUT','POST','DELETE'],allow_headers=['Content-Type'])

class CaptureProcessRequest(BaseModel):
    asset: Asset
    action: Literal['ocr', 'translate', 'explain']
    language: Literal['zh-CN', 'zh-TW', 'en'] = 'zh-CN'
    engine: Literal['auto', 'multimodal'] = 'auto'

@app.post('/api/capture/process')
async def process_capture(req: CaptureProcessRequest):
    profile = get_active_profile(DB)
    if req.engine == 'multimodal':
        if not profile:
            raise HTTPException(400, '请先在 LLM 配置中启用一个支持图片的模型。')
        if not profile.get('vision'):
            raise HTTPException(400, '当前模型未启用图片输入，请在 LLM 配置中选择支持图片的模型，并启用截图输入。')
        language = {'zh-CN':'简体中文', 'zh-TW':'繁體中文', 'en':'English'}[req.language]
        layout = '按截图阅读顺序保留标题、段落、换行、空行、缩进、列表编号与表格行列结构。使用空格或制表符表达列对齐，不要合并原有换行。直接输出正文，不添加开场白、结尾、Markdown 代码围栏或截图中没有的内容。不猜测看不清的文字。'
        tasks = {
            'ocr': '只逐字输出截图中真实可见且能够确定识别的文字，保留原文语言、大小写、标点和数字。不翻译、不总结，不描述图片、图标、界面、物体、颜色或位置，不添加任何解释或识别说明。空白、遮挡、模糊和无法确定的字符直接跳过，禁止输出“无法辨认”“无法识别”等占位符或推测文字。如果没有任何可识别文字，返回空字符串。',
            'translate': f'直接阅读截图，将可见文字翻译成{language}。保留各段对应关系、原有列表层级和表格结构，保留代码、变量、网址及公式。',
            'explain': f'用{language}解释截图的内容。先说明这是什么，再说明它是干什么用的、用途和作用是什么，以及关键概念或功能如何理解。根据内容类型解释文档、代码、界面、图表或公式的实际意义，必要时给出简短例子或使用场景。合理推断应说明依据，无法确认的信息不要编造。以自然段、清晰的小标题或简洁要点组织说明，可以重新组织内容，不需要按截图的版式、段落顺序或表格行列排版。不要仅仅转录、复述或提取原文。',
        }
        from types import SimpleNamespace
        prompt = tasks[req.action] if req.action=='explain' else tasks[req.action]+'\n'+layout
        positions=None
        if req.action=='translate':
            try: ocr=active_ocr(DB)
            except HTTPException: ocr={'assistLlm':True}
            if ocr and ocr.get('assistLlm'):
                positions=await locate(DB,req.asset.data)
                context={'imageSize':[positions['width'],positions['height']],'coordinateSpace':'image-pixels','regions':positions['regions'][:200]}
                prompt+='\n以下 OCR 结果提供内容位置。以图片校正文字并翻译，保持各区域阅读顺序；坐标来自 OCR，不要自行生成坐标。\n'+json.dumps(context,ensure_ascii=False)
        result = await complete(profile, SimpleNamespace(messages=[]), [req.asset], req.action, prompt, DB)
        text = clean_transcription(result['text']) if req.action=='ocr' else result['text']
        output={'text':text, 'mode':'model', 'model':profile.get('name') or profile.get('model','')}
        if positions is not None: output['location']=positions
        return output
    if req.action != 'ocr' and not profile:
        raise HTTPException(400, '请先在模型配置中启用一个模型，再使用翻译或解释。')
    try: ocr = active_ocr(DB)
    except HTTPException: ocr={'assistLlm':True}
    recognized = None
    if ocr and (req.action=='ocr' or not profile.get('vision') or ocr.get('assistLlm')):
        recognized = await locate(DB,req.asset.data)
    if req.action == 'ocr' or not profile.get('vision'):
        text = recognized['text'] if recognized is not None else await recognize_async(req.asset.data)
        if not text:
            raise HTTPException(400, '未识别到文字，请调整截图范围后重试。')
        if req.action == 'ocr':
            return recognized if recognized is not None else {'text': text, 'mode': 'local-ocr'}
    else:
        text = recognized['text'] if recognized is not None else ''
    language = {'zh-CN': '简体中文', 'zh-TW': '繁體中文', 'en': 'English'}[req.language]
    prompt = f'将以下内容翻译为{language}，直接输出翻译结果。' if req.action == 'translate' else f'用{language}解释以下内容：说明这是什么、用途和作用是什么，再讲清关键概念或功能。用自然段和简洁要点组织说明，不需要沿用原文格式，不要只提取或复述文字，不要编造看不到的信息。'
    prompt += '\n' + text
    if recognized and profile.get('vision'):
        context = {'imageSize':[recognized['width'],recognized['height']],'coordinateSpace':'image-pixels','regions':recognized['regions'][:200]}
        prompt += '\n以下 OCR 结果仅用于辅助文字定位，坐标相对于原图左上角；文字与位置可能有误，以截图为准。\n'+json.dumps(context,ensure_ascii=False)
    from types import SimpleNamespace
    result = await complete(profile, SimpleNamespace(messages=[]), [req.asset] if profile.get('vision') else [], req.action if profile.get('vision') else 'chat', prompt, DB)
    return {'text': result['text'], 'mode': 'model'}

class LocateRequest(BaseModel):
    asset: Asset
    granularity: Literal['auto','line'] = 'auto'

@app.post('/api/capture/locate')
async def locate_capture(req: LocateRequest):
    return await locate(DB,req.asset.data,require_lines=req.granularity=='line')

class InlineTranslationRequest(BaseModel):
    asset: Asset
    lines: list[TranslationLine] = Field(max_length=600)
    language: Literal['zh-CN','zh-TW','en'] = 'zh-CN'

@app.post('/api/capture/translate-inline')
async def translate_inline(req: InlineTranslationRequest):
    profile=get_active_profile(DB)
    if not profile: raise HTTPException(400,'请先在 LLM 配置中启用翻译模型')
    if req.lines:
        from .ocr_recovery import pending_regions
        regions=await asyncio.to_thread(pending_regions,req.asset.data,{'regions':[line.model_dump() for line in req.lines]})
        next_id=max(int(line.id.split('-')[1]) for line in req.lines)+1
        req.lines.extend(TranslationLine.model_validate(region|{'id':f'text-{next_id+i}'}) for i,region in enumerate(regions))
    return await translate_lines(profile,req.asset,req.lines,req.language,DB,complete)

@app.get('/api/settings/ocr')
def ocr_configuration():
    return get_ocr(DB)

@app.get('/api/settings/speech')
def speech_configuration():return get_speech()

@app.post('/api/settings/microphone/open')
def open_microphone_settings():
    if os.name!='nt':raise HTTPException(400,'请在系统隐私设置中开启麦克风访问权限')
    try:os.startfile('ms-settings:privacy-microphone')
    except OSError:raise HTTPException(400,'无法打开系统设置，请手动打开“隐私和安全性 → 麦克风”') from None
    return {'opened':True}

@app.put('/api/settings/speech/active')
def activate_speech(selection:SpeechSelection):return select_speech(DB,selection)

@app.put('/api/settings/speech/{profile_id}')
def speech_save(profile_id:str,config:SpeechProfile):return save_speech(DB,profile_id,config)

@app.post('/api/settings/speech/{profile_id}/test')
async def speech_test(profile_id:str,config:SpeechProfile):return await probe_speech(draft_speech(profile_id,config))

@app.post('/api/settings/speech/{profile_id}/voices')
async def speech_voices(profile_id:str,config:SpeechProfile):return await list_voices(config)

@app.post('/api/settings/speech/{profile_id}/models')
async def speech_models(profile_id:str,config:SpeechProfile):return await fetch_speech_models(profile_id,config)

class SynthesisRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str=Field(min_length=1,max_length=200000)

async def speech_audio(profile,text,request,stream=False):
    if not text.strip():raise HTTPException(400,'请输入要朗读的文字')
    if stream:
        source=synthesize_stream(profile,text)
        queue=asyncio.Queue(maxsize=8)
        async def produce():
            try:
                async for chunk in source:await queue.put(('audio',chunk))
                await queue.put(('done',None))
            except HTTPException as e:await queue.put(('error',e))
            except Exception:await queue.put(('error',HTTPException(502,'语音流连接中断，请重试')))
            finally:await source.aclose()
        producer=asyncio.create_task(produce())
        # Validate the provider before sending headers; after that forward every chunk.
        job=asyncio.create_task(queue.get())
        try:
            while not job.done():
                if await request.is_disconnected():raise HTTPException(499,'朗读已取消')
                await asyncio.wait({job},timeout=.05)
            kind,first=await job
            if kind=='error':raise first
            if kind!='audio':raise HTTPException(502,'语音服务未返回音频')
        except BaseException:
            job.cancel();producer.cancel()
            await asyncio.gather(job,producer,return_exceptions=True)
            raise
        async def chunks():
            try:
                yield first
                while True:
                    kind,chunk=await queue.get()
                    if kind=='done':break
                    if kind=='error':raise chunk
                    yield chunk
            finally:
                producer.cancel();await asyncio.gather(producer,return_exceptions=True)
        return StreamingResponse(chunks(),media_type='audio/mpeg',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no','X-SnapMind-Audio':'stream'})
    job=asyncio.create_task(synthesize(profile,text))
    try:
        while not job.done():
            if await request.is_disconnected():raise HTTPException(499,'朗读已取消')
            await asyncio.wait({job},timeout=.1)
        return Response(await job,media_type='audio/mpeg',headers={'Cache-Control':'no-store'})
    finally:
        if not job.done():
            job.cancel()
            try:await job
            except asyncio.CancelledError:pass

@app.post('/api/speech/synthesize')
async def speech_synthesize(body:SynthesisRequest,request:Request,stream:bool=False):return await speech_audio(active_tts(),body.text,request,stream)

@app.websocket('/api/speech/recognize')
async def speech_recognize(client:WebSocket):
    origin=client.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:5174','http://localhost:5174','http://127.0.0.1:5173','http://localhost:5173','http://tauri.localhost','https://tauri.localhost','tauri://localhost'):
        await client.close(code=1008);return
    await client.accept()
    try:
        await relay_asr(client,active_asr(),continuous=client.query_params.get('continuous')=='true')
    except HTTPException as e:await client.send_json({'type':'error','message':e.detail})
    except (WebSocketDisconnect,RuntimeError):pass
    finally:
        try:await client.close()
        except RuntimeError:pass

class SpeechPreview(SpeechProfile):
    text:str=Field(default='你好，我是 SnapMind，很高兴为你朗读。',min_length=1,max_length=200)

@app.post('/api/settings/speech/{profile_id}/preview')
async def speech_preview(profile_id:str,body:SpeechPreview,request:Request,stream:bool=False):
    profile=draft_speech(profile_id,SpeechProfile(**body.model_dump(exclude={'text'})))
    if profile['kind']!='tts':raise HTTPException(400,'只有 TTS 配置支持音色试听')
    return await speech_audio(profile,body.text,request,stream)

class CaptureAnalysisRequest(BaseModel):
    asset: Asset
    action: Literal['table','detect']
    target: Literal['vehicles','all'] = 'all'

@app.post('/api/capture/analyze')
async def analyze_capture(req: CaptureAnalysisRequest):
    return await analyze(get_active_profile(DB),req.asset,req.action,req.target,DB,complete)

class AiAnnotationRequest(BaseModel):
    asset: Asset
    prompt: str = Field(min_length=1,max_length=2000)
    controls: list[ControlTarget] = Field(default_factory=list,max_length=300)
    history: list[ConversationTurn] = Field(default_factory=list,max_length=12)
    existing: list[ExistingAnnotation] = Field(default_factory=list,max_length=100)

@app.post('/api/capture/annotate')
async def annotate_capture(req: AiAnnotationRequest):
    return await annotate(get_active_profile(DB),req.asset,req.prompt,req.history,req.existing,DB,complete,locate,req.controls)

class CaptureStudyRequest(BaseModel):
    assets: list[Asset] = Field(min_length=1,max_length=6)
    mode: Literal['code','paper']
    prompt: str = Field(min_length=1,max_length=3000)
    history: list[StudyTurn] = Field(default_factory=list,max_length=10)
    @model_validator(mode='after')
    def bounded_context(self):
        if sum(len(a.data) for a in self.assets)>36_000_000:raise ValueError('引用页面图片总量超过限制')
        if sum(len(t.text) for t in self.history)>24000:raise ValueError('对话历史过长')
        return self

@app.post('/api/capture/study')
async def study_capture(req: CaptureStudyRequest):
    return await study(get_active_profile(DB),req.assets,req.mode,req.prompt,req.history,DB,complete,locate)

class ImageUtilityRequest(BaseModel):
    asset: Asset
    action: Literal['offline','qr','entities']

@app.post('/api/capture/utility')
async def image_utility(req: ImageUtilityRequest):
    if req.action=='qr': return await asyncio.to_thread(decode_codes,req.asset.data)
    result=await recognize_positions_async(req.asset.data)
    for i,region in enumerate(result['regions']): region.setdefault('id',f'local-{i}')
    return screen_entities(result) if req.action=='entities' else result

class ImageRepairRequest(BaseModel):
    asset: Asset
    mask: str = Field(max_length=12_000_000,pattern=r'^data:image/png;base64,')
    extract: bool = False

@app.post('/api/capture/repair')
async def repair_image(req: ImageRepairRequest):
    return await asyncio.to_thread(repair,req.asset.data,req.mask,req.extract)

class ImageConversationTurn(BaseModel):
    role: Literal['user','assistant']
    text: str = Field(min_length=1,max_length=12000)

class ImageUndoSnapshot(BaseModel):
    model_config=ConfigDict(extra='forbid')
    asset: Asset
    annotations: list[ExistingAnnotation] = Field(default_factory=list,max_length=100)

class ImageConversationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sessionId: str | None = Field(default=None,pattern=r'^[a-zA-Z0-9-]{1,80}$')
    turnId: str | None = Field(default=None,pattern=r'^[a-zA-Z0-9-]{1,64}$')
    userMessageId: str | None = Field(default=None,pattern=r'^[a-zA-Z0-9-]{1,80}$')
    assets: list[Asset] = Field(default_factory=list,max_length=6)
    selectedId: str | None = Field(default=None,max_length=80)
    prompt: str = Field(min_length=1,max_length=205000)
    history: list[ImageConversationTurn] = Field(default_factory=list,max_length=20)
    existing: list[ExistingAnnotation] = Field(default_factory=list,max_length=100)
    undoSnapshot: ImageUndoSnapshot | None = None
    controls: list[ControlTarget] = Field(default_factory=list,max_length=300)
    action: Action | None = None
    language: Literal['zh-CN','zh-TW','en'] = 'zh-CN'
    @model_validator(mode='after')
    def context_bounds(self):
        if len({a.id for a in self.assets})!=len(self.assets): raise ValueError('图片编号不能重复')
        if sum(len(a.data) for a in self.assets)+(len(self.undoSnapshot.asset.data) if self.undoSnapshot else 0)>36_000_000: raise ValueError('引用图片总量过大')
        if self.undoSnapshot and self.undoSnapshot.asset.id not in {a.id for a in self.assets}:raise ValueError('撤销快照引用未知图片')
        if sum(len(t.text) for t in self.history)>60000: raise ValueError('对话历史过长')
        return self

@app.post('/api/capture/conversation')
async def image_conversation(req: ImageConversationRequest,stream:bool=False):
    profile=get_active_profile(DB)
    if stream:
        async def events():
            queue=asyncio.Queue(maxsize=16)
            async def publish(event):await queue.put(event)
            async def invoke_stream(history):
                return await run_agent(profile,req.assets,req.selectedId,req.prompt,history,[a.model_dump() for a in req.existing],[a.model_dump() for a in req.controls],DB,complete,locate,req.action,req.language,on_chunk=publish,undo_snapshot={'asset':req.undoSnapshot.asset,'annotations':[a.model_dump() for a in req.undoSnapshot.annotations]} if req.undoSnapshot else None)
            async def run():
                try:
                    result=await RUNTIME.image_run(req,req.prompt,req.action,{},profile,complete,DB,invoke_stream,context_reserve=agent_context_reserve() if not req.action else 0)
                    await publish({'type':'result','result':result})
                except HTTPException as e:await publish({'type':'error','message':e.detail})
                except Exception:await publish({'type':'error','message':'截图处理失败，请重试'})
            task=asyncio.create_task(run())
            try:
                while True:
                    try:event=await asyncio.wait_for(queue.get(),10)
                    except TimeoutError:
                        yield ': keepalive\n\n';continue
                    yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
                    if event['type'] in ('result','error'):break
            finally:
                task.cancel();await asyncio.gather(task,return_exceptions=True)
        return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
    async def invoke(history):
        return await run_agent(profile,req.assets,req.selectedId,req.prompt,history,[a.model_dump() for a in req.existing],[a.model_dump() for a in req.controls],DB,complete,locate,req.action,req.language,undo_snapshot={'asset':req.undoSnapshot.asset,'annotations':[a.model_dump() for a in req.undoSnapshot.annotations]} if req.undoSnapshot else None)
    return await RUNTIME.image_run(req,req.prompt,req.action,{},profile,complete,DB,invoke,context_reserve=agent_context_reserve() if not req.action else 0)

class ImageToolContext(ImageConversationRequest):
    prompt: str = Field(default='', max_length=205000)

class ImageToolCall(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=64)
    arguments: dict = Field(default_factory=dict)
    context: ImageToolContext

    @model_validator(mode='after')
    def validate_arguments(self):
        AGENT_TOOLS.get(self.name).schema.model_validate(self.arguments,strict=True)
        if self.context.action is not None:
            raise ValueError('工具调用只能通过 name 指定工具')
        return self

@app.get('/api/tools')
def image_tool_catalog():
    return AGENT_TOOLS.catalog()

@app.post('/api/tools/call')
async def call_image_tool(req: ImageToolCall):
    args = AGENT_TOOLS.get(req.name).schema.model_validate(req.arguments,strict=True).model_dump(exclude_none=True)
    context = req.context
    image_id = args.get('imageId', context.selectedId)
    prompt = args.get('prompt') or context.prompt or AGENT_TOOLS.get(req.name).description
    profile=get_active_profile(DB)
    async def invoke(history):
        return await run_agent(profile,context.assets,image_id,prompt,history,[a.model_dump() for a in context.existing],[a.model_dump() for a in context.controls],DB,complete,locate,req.name,args.get('language',context.language),arguments=args,undo_snapshot={'asset':context.undoSnapshot.asset,'annotations':[a.model_dump() for a in context.undoSnapshot.annotations]} if context.undoSnapshot else None)
    return await RUNTIME.image_run(context,prompt,req.name,args,profile,complete,DB,invoke)

@app.put('/api/settings/ocr')
def put_ocr_configuration(config: OcrConfig):
    return save_ocr(DB,config)

@app.post('/api/settings/ocr/test')
async def test_ocr_configuration(config: OcrConfig):
    with sqlite3.connect(DB) as db: stored=read_ocr(db)
    key = '' if config.clearApiKey else (config.apiKey or '').strip() or unprotect_key(stored.get('apiKeyProtected'))
    if not key: raise HTTPException(400,'请填写 PaddleOCR API Key')
    return await probe_ocr(config,key)

@app.post('/api/settings/ocr/models')
async def get_ocr_model_list(config: OcrConfig):
    with sqlite3.connect(DB) as db: stored=read_ocr(db)
    key = '' if config.clearApiKey else (config.apiKey or '').strip() or unprotect_key(stored.get('apiKeyProtected'))
    if not key: raise HTTPException(400,'请先填写 PaddleOCR API Key，再获取模型列表')
    return await fetch_ocr_models(config,key)

def save(session: Session):
    STORE.save(session.model_dump(exclude_none=True))
    MEMORY.publish()

@app.get('/api/health')
def health():
    profile=get_active_profile(DB)
    ocr=active_ocr(DB)
    return {'mode':'model' if profile else 'unconfigured','storage':'sqlite','agent':'single-agent-react','remote_upload':bool(ocr or profile and profile.get('vision')),'ocrMode':'paddleocr' if ocr else 'local'}

@app.get('/api/sessions')
def sessions():
    return STORE.list()

@app.get('/api/image-history')
def image_history():
    return STORE.image_history()

@app.get('/api/sessions/{session_id}')
def get_session(session_id: str):
    session=STORE.get(session_id)
    if session is None:raise HTTPException(404,'会话不存在或已删除')
    return session

class SessionMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = Field(default=None,min_length=1,max_length=40)
    pinned: bool | None = None

@app.patch('/api/sessions/{session_id}/metadata')
def update_session_metadata(session_id: str, change: SessionMetadata):
    title=None
    if change.title is not None:
        title=change.title.strip()
        if not title:raise HTTPException(400,'会话名称不能为空')
    result=STORE.patch_image_metadata(session_id,title,change.pinned)
    if result is None:raise HTTPException(404,'截图会话不存在或已删除')
    MEMORY.publish()
    return result

@app.post('/api/sessions/{session_id}/image-title')
async def image_session_title(session_id: str):
    session=STORE.get(session_id)
    if not session or not session.get('imageConversation'):raise HTTPException(404,'截图会话不存在或已删除')
    referenced=next((m.get('sources') for m in session['messages'] if m['role']=='user' and m.get('sources')),[])
    original=next((m.get('images') for m in session['messages'] if m['role']=='user' and m.get('images')),[])
    asset=next(iter(original),None) or next((a for a in session['assets'] if a['id'] in referenced),None) or next(iter(session['assets']),None)
    if not asset:return {'title':'文本内容讨论','source':'fallback'}
    return await generate_title(get_active_profile(DB),Asset.model_validate(asset),recognize_positions_async,complete,DB)

@app.get('/api/storage')
def storage_info():
    return {'root':str(HOME),'state':'state_1.sqlite','business':'data/snapmind.sqlite3','format_version':1}

@app.get('/api/memories')
def memory_status():
    return MEMORY.status()

class MemoryGenerate(BaseModel):
    sessionId: str | None = Field(default=None,pattern=r'^[a-zA-Z0-9-]{1,80}$')

@app.post('/api/memories/generate')
async def generate_memories(req: MemoryGenerate):
    profile=get_active_profile(DB)
    if not profile:raise HTTPException(400,'请先启用模型，再整理长期记忆')
    return await MEMORY.generate(RUNTIME.extractor(profile,complete,DB),manual=True,session_id=req.sessionId)

@app.get('/api/settings/preferences')
def get_preferences():
    path=HOME/'ui-preferences.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

@app.put('/api/settings/preferences')
def put_preferences(values: dict):
    if len(json_text(values))>20000 or any(not key.startswith('snapmind-') for key in values):raise HTTPException(422,'无效的界面设置')
    from .local_storage import file_lock
    with file_lock(HOME/'thread-writer-locks/preferences.lock'):
        merged=get_preferences()
        for key,value in values.items():
            if value is None:merged.pop(key,None)
            elif isinstance(value,str):merged[key]=value
            else:raise HTTPException(422,'无效的界面设置值')
        atomic_write(HOME/'ui-preferences.json',json_text(merged)+'\n')
    return merged

@app.get('/api/settings/model')
def get_model_settings():
    return public_settings(read_settings(DB))

@app.get('/api/usage')
def get_usage():
    with sqlite3.connect(DB) as db:
        rows=db.execute('SELECT model,SUM(input_tokens),SUM(output_tokens),COUNT(*) FROM model_usage GROUP BY model ORDER BY SUM(input_tokens)+SUM(output_tokens) DESC').fetchall()
        unreported=db.execute('SELECT COUNT(*) FROM model_usage WHERE tokens_reported=0').fetchone()[0]
        ocr_rows=model_totals(db)
    models=[{'model':r[0],'inputTokens':r[1],'outputTokens':r[2],'requests':r[3]} for r in rows]
    result={'inputTokens':sum(r['inputTokens'] for r in models),'outputTokens':sum(r['outputTokens'] for r in models),'requests':sum(r['requests'] for r in models),'models':models}
    if ocr_rows:
        result['llmRequests']=result['requests']
        result['ocrRequests']=sum(r[1] for r in ocr_rows)
        result['requests']+=result['ocrRequests']
        unreported+=result['ocrRequests']
        models.extend({'model':r[0],'kind':'ocr','inputTokens':None,'outputTokens':None,'requests':r[1],'historical':bool(r[2])} for r in ocr_rows)
    if unreported:result['unreportedRequests']=unreported
    return result

@app.get('/api/usage/analytics')
def usage_analytics(kind: Literal['llm','ocr']='llm', start: str | None=None, end: str | None=None):
    return get_usage_analytics(DB,kind,start,end)

@app.put('/api/settings/model')
def put_model_settings(config: ModelConfig):
    return save_settings(DB, config)

@app.get('/api/settings/models')
def model_profiles():
    return get_profiles(DB)

@app.get('/api/settings/config')
def configuration_preview(reveal_keys: bool=False):
    return get_configuration(DB, reveal_keys)

@app.put('/api/settings/models/active')
def activate_model(selection: ActiveSelection):
    return set_active(DB, selection)

@app.put('/api/settings/models/{profile_id}')
def put_model_profile(profile_id: str, config: ProfileConfig):
    if not profile_id.replace('-','').isalnum() or len(profile_id)>80:
        raise HTTPException(400,'配置 ID 无效')
    return save_profile(DB, profile_id, config)

@app.put('/api/settings/models/{profile_id}/draft')
def put_model_draft(profile_id: str, config: ProfileConfig):
    if not profile_id.replace('-','').isalnum() or len(profile_id)>80:
        raise HTTPException(400,'配置 ID 无效')
    return save_profile(DB, profile_id, config, draft=True)

@app.post('/api/settings/models/{profile_id}/test')
async def test_model_profile(profile_id: str, config: ProfileConfig):
    return await test_profile(DB, profile_id, config)

@app.post('/api/settings/models/{profile_id}/models')
async def fetch_profile_models(profile_id: str, config: ProfileConfig):
    return await query_models(DB, profile_id, config)

@app.post('/api/settings/key-portals/{vendor}/open')
def launch_key_portal(vendor: str):
    return open_key_portal(vendor)

@app.put('/api/sessions/{session_id}')
def put_session(session_id: str, session: Session):
    if session_id != session.id:
        raise HTTPException(400,'会话 ID 不匹配')
    if RUNTIME.locks.get(session_id) and RUNTIME.locks[session_id].locked():raise HTTPException(409,'此会话正在处理，暂时不能修改历史')
    save(session)
    return session.model_dump(exclude_none=True)

@app.delete('/api/sessions/{session_id}')
def delete_session(session_id: str):
    if RUNTIME.locks.get(session_id) and RUNTIME.locks[session_id].locked():raise HTTPException(409,'此会话正在处理，暂时不能删除')
    STORE.delete(session_id)
    MEMORY.publish()
    return {'deleted':True}

@app.post('/api/chat')
async def chat(req: ChatRequest):
    if not req.session.assets:
        raise HTTPException(400,'请先添加一张截图')
    referenced=req.session.messages[-1].sources if req.session.messages and req.session.messages[-1].role=='user' else None
    selected=[a for a in req.session.assets if a.id in (referenced or [])] or req.session.assets[-1:]
    scenario='custom' if any(a.scenario=='custom' for a in selected) else selected[-1].scenario
    profile=get_active_profile(DB)
    if not profile:raise HTTPException(400,'请先配置并启用一个 LLM 模型')
    async def invoke():
        return await complete(profile,req.session,selected,req.action,req.prompt,DB)
    message=await RUNTIME.workspace_run(req.session,selected,req.action,req.prompt,profile,complete,DB,invoke)
    async def events():
        step=(len(message['text']) or 1) if profile else 6
        for start in range(0,len(message['text']),step):
            yield 'data: '+json.dumps({'type':'chunk','text':message['text'][start:start+step]},ensure_ascii=False)+'\n\n'
            if not profile:await asyncio.sleep(0.028)
        yield 'data: '+json.dumps({'type':'result','message':message},ensure_ascii=False)+'\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})
