"""Validation, evidence grounding, bounded retry and observations for one agent."""
import asyncio
import json
import re
from copy import deepcopy
from pydantic import ValidationError
from fastapi import HTTPException
from ..session_memory import record_tool
from ..image_tools import image_from_data, valid_rect
from ..capture_analysis import Tables
from .schemas import Result, AnnotationResultEdit


def validation_message(error):
    if isinstance(error,ValidationError):return [{'path':'.'.join(str(p) for p in item['loc']),'type':item['type'],'message':item['msg']} for item in error.errors(include_input=False,include_context=False)][:20]
    return [{'path':'arguments','type':'invalid','message':str(error)[:500]}]


def text_edit_intent(prompt):
    positive=re.sub(r'(?:不要|不是|别|不需要)\s*(?:打|加|用|做)?(?:马赛克|打码|模糊|遮盖|涂抹掉|消除|擦除|擦掉)','',prompt)
    erase=bool(re.search(r'涂抹掉|涂抹去掉|擦掉|擦除|消除|抹掉',positive))
    cover=bool(re.search(r'马赛克|打码|遮盖',positive))
    blur=bool(re.search(r'模糊',positive))
    if sum((erase,cover,blur))!=1:return None
    return 'heal' if erase else 'mosaic' if cover else 'blur'


def observation(result,limit):
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k not in ('data','layer','apiKey','apiKeyProtected')}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    data=clean(result);raw=json.dumps(data,ensure_ascii=False)
    if len(raw.encode('utf-8'))>limit:
        return {'action':result['action'],'assetId':result['assetId'],'answer':result['answer'][:1500],'excerpt':raw.encode('utf-8')[:limit-2000].decode('utf-8',errors='ignore'),'truncated':True}
    return data


class Harness:
    def __init__(self,registry,limits):self.registry=registry;self.limits=limits

    def validate(self,name,arguments,state,explicit=False):
        tool=self.registry.get(name);args=tool.schema.model_validate(arguments,strict=True)
        intent=text_edit_intent(state.prompt)
        if not explicit and name in ('heal','mosaic','blur') and intent and name!=intent:
            raise ValueError(f'工具与用户编辑要求不符：当前要求使用 {intent}，不可用 {name} 替代；修正决策后重试')
        if name!='answer' or args.imageId is not None:
            asset=state.selected(args.imageId)
        else:asset=next((a for a in state.assets if a.id==state.selected_id),None)
        if getattr(args,'bbox',None) is not None:
            valid_rect(args.bbox,asset.width,asset.height)
            if not explicit:
                sources=[state.prompt]
                # Follow-up authorization may explicitly reuse the user's last
                # coordinates. Assistant prose and long-term preferences are not
                # coordinate evidence and cannot grant new editing permission.
                if re.search(r'上一条|上条|刚才|前面|之前|上次|previous|last message|earlier|same coordinates',state.prompt,re.I):
                    previous=next((turn for turn in reversed(state.history) if turn.role=='user'),None)
                    if previous:sources.append(previous.text)
                choices=[list(map(float,m)) for source in sources for m in re.findall(r'[\[(（]\s*(\d+(?:\.\d+)?)\s*[,，]\s*(\d+(?:\.\d+)?)\s*[,，]\s*(\d+(?:\.\d+)?)\s*[,，]\s*(\d+(?:\.\d+)?)\s*[\])）]',source)]
                def boxes(value):
                    if isinstance(value,dict):
                        if isinstance(value.get('bbox'),list):choices.append(value['bbox'])
                        for item in value.values():boxes(item)
                    elif isinstance(value,list):
                        for item in value:boxes(item)
                for item in state.observations:
                    p=item.get('payload',{})
                    if item.get('assetId')==asset.id and p.get('width',asset.width)==asset.width and p.get('height',asset.height)==asset.height:boxes(item)
                if asset.id==state.selected_id:choices.extend(c['bbox'] for c in state.controls)
                if not any(len(b)==4 and all(abs(a-v)<1 for a,v in zip(args.bbox,b)) for b in choices):raise ValueError('坐标没有来源：先调用 offline 取得行框，或请用户提供像素坐标，禁止猜测 bbox')
        if name=='region' and len(state.assets)>=6:raise ValueError('最多引用六张图片')
        return tool,args

    def validate_result(self,result,state):
        value=Result.model_validate(result,strict=True).model_dump()
        if value['assetId'] is not None and not any(a.id==value['assetId'] for a in state.assets):raise ValueError('工具结果引用未知图片')
        asset=next((a for a in state.assets if a.id==value['assetId']),None);payload=value['payload'];action=value['action']
        if action in ('translate','detect','annotate'):
            if payload.get('width',asset.width)!=asset.width or payload.get('height',asset.height)!=asset.height:raise ValueError('工具结果图片尺寸不匹配')
            if payload.get('coordinateSpace')!='image-pixels':raise ValueError('工具结果必须使用 image-pixels 坐标')
        if action=='annotate':
            if not isinstance(payload.get('annotations'),list) or len(payload['annotations'])>30:raise ValueError('标注结果列表无效')
            ids={a['id'] for a in state.existing}
            for edit in payload['annotations']:
                AnnotationResultEdit.model_validate(edit,strict=True)
                if edit['operation']!='add' and edit['id'] not in ids:raise ValueError('标注 ID 不存在')
                if edit['operation']!='remove':valid_rect(edit['bbox'],asset.width,asset.height)
        if action=='translate':
            if not isinstance(payload.get('lines'),list):raise ValueError('译文缺少行列表')
            for line in payload['lines']:
                valid_rect(line['bbox'],asset.width,asset.height)
                if not isinstance(line.get('text'),str):raise ValueError('译文不是字符串')
        if action=='detect':
            for item in payload['objects']:valid_rect(item['bbox'],asset.width,asset.height)
        if action=='table':Tables.model_validate(payload,strict=True)
        if action in ('crop','heal','lift','region','restore_image','blur'):
            image=image_from_data(payload['data'])
            if image.size!=(payload['width'],payload['height']):raise ValueError('工具返回图片尺寸与像素不一致')
        return value

    async def call(self,name,args,state,profile,complete,locate,path,on_event=None):
        tool=self.registry.get(name);snapshot=state.checkpoint()
        record_tool('tool_call',{'name':name,'arguments':args.model_dump(exclude_none=True)})
        for attempt in range(self.limits.transient_attempts):
            try:
                if args.imageId:state.activate(args.imageId)
                async with asyncio.timeout(self.limits.tool_seconds):
                    result=await self.registry.execute(name,args,state,profile,complete,locate,path,on_event)
                value=self.validate_result(result,state)
                if name=='undo':
                    previous=state.undo.pop();state.restore(previous)
                    state.steps.append(value);state.last_answer=value['answer']
                else:
                    state.commit(value)
                    if tool.mutates:state.undo.append(snapshot)
                item=observation(value,self.limits.observation_bytes);state.observations.append(item)
                record_tool('tool_result',{'name':name,'result':item,'attempt':attempt+1})
                if on_event:await on_event({'type':'tool_result','name':name,'step':len(state.steps),'result':item})
                return value
            except HTTPException as error:
                state.restore(snapshot)
                if error.status_code not in (408,429,502,503,504) or attempt+1==self.limits.transient_attempts:raise
            except TimeoutError:
                state.restore(snapshot)
                if attempt+1==self.limits.transient_attempts:raise HTTPException(504,'工具执行超时，请重试') from None
            except (ValidationError,ValueError,KeyError,TypeError) as error:
                state.restore(snapshot);raise ValueError('工具结果校验失败：'+str(error)[:400]) from None
            if on_event:await on_event({'type':'agent_status','phase':'retrying','tool':name,'attempt':attempt+2})
            await asyncio.sleep(.2*(attempt+1))
