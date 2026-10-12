"""Explicit tool allowlist. Existing screenshot services are implementation adapters."""
from dataclasses import dataclass
from typing import get_args
from copy import deepcopy
from fastapi import HTTPException
from PIL import ImageFilter
from ..image_tool_registry import ToolName, arguments_model, catalog as legacy_catalog, default_prompt
from ..image_conversation import converse
from ..image_tools import image_from_data, png_data, valid_rect
from ..annotation_grounding import match_text
from .schemas import BaseArguments, DrawArguments, BlurArguments, CropArguments
from ..ai_annotations import ExistingAnnotation


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: type
    mutates: bool = False


class ToolRegistry:
    def __init__(self):
        descriptions={t['function']['name']:t['function']['description'] for t in legacy_catalog()['tools']}
        descriptions['highlight']='直接高亮用户引用的截图原文，内部完成 OCR 定位与错字复核；只传 targetText，无需先调用 offline 或 draw'
        self.tools={name:Tool(name,descriptions[name],arguments_model(name),name in ('translate','detect','annotate','crop','highlight','mosaic','heal','lift','region')) for name in get_args(ToolName)}
        self.tools['crop']=Tool('crop','裁剪图片：用户明确坐标用 bbox；标题或指定文字区域先 offline 读取原文，再用 targetText 自动真实定位，不能猜测或扩大行框',CropArguments,True)
        for tool in (
            Tool('answer','根据截图、会话记忆和真实工具观测回答，解释代码/论文/公式、整理笔记；不修改截图',BaseArguments),
            Tool('draw','在有来源的像素范围绘制矩形、圆、箭头、文字、序号、勾或气泡',DrawArguments,True),
            Tool('blur','通过 OCR 唯一定位指定原文并模糊遮罩',BlurArguments,True),
            Tool('undo','撤销最近一次图像操作，支持当前窗口上一轮用户操作的快照；没有可撤销快照时提示用户',BaseArguments,True),
            Tool('clear_annotations','清空已有 AI 标注，保留原图与非 AI 手工标注',BaseArguments,True),
        ):self.tools[tool.name]=tool

    def get(self,name):
        if name not in self.tools:raise ValueError('工具不在允许列表：'+name)
        return self.tools[name]

    def catalog(self):
        return {'version':3,'coordinateSpace':'image-pixels','tools':[
            {'type':'function','function':{'name':t.name,'description':t.description,'parameters':(arguments_model('crop') if t.name=='crop' else t.schema).model_json_schema()},'mutatesImage':t.mutates}
            for t in self.tools.values()]}

    async def execute(self,name,args,state,profile,complete,locate,path,on_event=None):
        image_id=args.imageId or state.selected_id
        prompt=args.prompt.strip() or (state.prompt if name=='answer' else default_prompt(name) if name in get_args(ToolName) else state.prompt)
        original_locate=locate
        async def cached_locate(path,data,**options):
            import hashlib
            key=(str(path),hashlib.sha256(data.encode()).hexdigest(),bool(options.get('require_lines')))
            if key not in state.locations:state.locations[key]=await original_locate(path,data,**options)
            return deepcopy(state.locations[key])
        locate=cached_locate
        if name=='crop' and args.targetText is not None:
            from ..text_target import resolve_text_target
            asset=state.selected(image_id)
            location=await locate(path,asset.data,require_lines=True,cloud_timeout=15)
            target=await resolve_text_target(profile,asset,args.targetText,location,path,complete)
            if not target:raise HTTPException(400,'无法唯一定位裁剪原文，请引用截图中的具体文字')
            box=valid_rect(target['bbox'],asset.width,asset.height)
            image=image_from_data(asset.data).crop(box)
            return {'action':'crop','assetId':asset.id,'answer':'已完成图片裁剪，可撤销。','payload':{'bbox':list(box),'data':png_data(image),'width':image.width,'height':image.height}}
        async def chunks(event):
            if on_event:await on_event(event)
        if name in get_args(ToolName) or name=='answer':
            history=state.history
            if name=='answer' and state.observations:
                from types import SimpleNamespace
                from .memory import observation_budget
                budget=observation_budget('',prompt,len(state.assets))
                observations=__import__('json').dumps(state.observations,ensure_ascii=False).encode('utf-8')[-budget:].decode('utf-8',errors='ignore')
                prompt+='\n只根据本轮真实工具观测回答，未执行成功的操作不得声称完成。观测摘要（可能截断）：\n'+observations
            existing=[ExistingAnnotation.model_validate(a) for a in state.existing]
            result=await converse(profile,state.assets,image_id,prompt,history,existing,state.controls,path,complete,locate,'chat' if name=='answer' else name,getattr(args,'language',state.language),arguments=args.model_dump(exclude_none=True),on_chunk=chunks if on_event and name in ('answer','ocr') else None)
            if name in ('region','crop'):result['payload']['bbox']=args.bbox
            return result
        asset=state.selected(image_id)
        if name=='draw':
            valid_rect(args.bbox,asset.width,asset.height)
            label={'highlight':'高亮','rectangle':'矩形','circle':'圈选','arrow':'箭头','text':'文字','number':'序号','check':'勾选','bubble':'气泡'}.get(args.kind,'')
            answer='已完成'+label+'标注，可撤销。'
            return {'action':'annotate','assetId':asset.id,'answer':answer,'payload':{'answer':answer,'annotations':[{'operation':'add','kind':args.kind,'text':args.text,'bbox':args.bbox,'locationSource':'visual'}],'width':asset.width,'height':asset.height,'coordinateSpace':'image-pixels','approximate':False}}
        if name=='clear_annotations':
            return {'action':'annotate','assetId':asset.id,'answer':'已清空标注，可撤销。','payload':{'answer':'已清空标注，可撤销。','annotations':[{'operation':'remove','id':a['id']} for a in state.existing],'width':asset.width,'height':asset.height,'coordinateSpace':'image-pixels','approximate':False}}
        if name=='undo':
            if not state.undo:raise HTTPException(400,'当前没有可撤销的截图快照，请使用截图工具栏撤销此前操作')
            snapshot=state.undo[-1];previous=next((a for a in snapshot[0] if a.id==image_id),next(a for a in snapshot[0] if a.id==snapshot[1]))
            annotations=snapshot[2] if previous.id==snapshot[1] else snapshot[4].get(previous.id,([],[]))[0]
            removed=[a.id for a in state.assets if not any(old.id==a.id for old in snapshot[0])]
            return {'action':'restore_image','assetId':previous.id,'answer':'已撤销最近一次截图操作。','payload':{'data':previous.data,'width':previous.width,'height':previous.height,'annotations':annotations,'removedImageIds':removed}}
        if name=='blur':
            location=await locate(path,asset.data,require_lines=True,cloud_timeout=15)
            from ..text_target import resolve_text_target
            target=await resolve_text_target(profile,asset,args.targetText,location,path,complete)
            if not target:raise HTTPException(400,'无法唯一定位原文，请引用截图中的具体文字')
            box=valid_rect(target['bbox'],asset.width,asset.height);image=image_from_data(asset.data);image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(args.radius)),box)
            return {'action':'blur','assetId':asset.id,'answer':'已完成文字模糊处理，可撤销。','payload':{'bbox':list(box),'radius':args.radius,'data':png_data(image),'width':asset.width,'height':asset.height}}
        raise ValueError('工具缺少实现')


REGISTRY=ToolRegistry()
