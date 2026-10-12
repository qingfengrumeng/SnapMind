"""Use only the explicitly enabled profile; never upload an image without its vision flag."""
from datetime import datetime, timezone
from uuid import uuid4
import sqlite3
import json
import httpx
from fastapi import HTTPException
from .model_profiles import endpoint, unprotect_key, safe_http_error
from .session_memory import apply_context, CONTEXT

def cached_input_tokens(usage, input_tokens):
    """Unknown is distinct from zero; cached input is already in prompt_tokens."""
    if not isinstance(input_tokens,int) or isinstance(input_tokens,bool) or input_tokens<0: return None
    details=usage.get('prompt_tokens_details') or {}
    candidates=[usage.get('prompt_cache_hit_tokens'),details.get('cached_tokens') if isinstance(details,dict) else None]
    return next((value for value in candidates if isinstance(value,int) and not isinstance(value,bool) and 0<=value<=input_tokens),None)

async def complete(profile, session, selected, action, prompt, path, on_chunk=None):
    if action!='chat' and not profile.get('vision'):
        raise HTTPException(400,'当前模型未启用图片输入。请在模型配置中选择支持图片的模型，并勾选允许发送截图。')
    system='你是 SnapMind 截图助手。根据提供的截图和上下文回答。看不清的内容要明确说明，不要编造识别结果。'
    if action=='ocr':
        system='你是纯文字转录工具，只输出截图中真实可见且能够确定的文字。保留原文格式，不描述画面、不解释、不添加识别说明。跳过空白和无法识别的内容，禁止输出占位符，不猜测。没有可识别文字时返回空字符串。'
    if not profile.get('vision'):
        system+=' 当前请求没有提供图片，不要假装看到了截图。'
    tasks={'study':'关联截图原文解释代码、论文或试题','annotate':'在截图上添加简短标注并回答问题','explain':'解释截图内容','ocr':'准确提取截图中的文字','translate':'翻译截图中的文字','formula':'提取公式并输出 LaTeX','table':'提取表格并输出 Markdown 表格','table-json':'提取结构化表格','objects':'识别可见物体并定位','chat':'回答用户问题'}
    messages=[{'role':'system','content':system}]
    for message in ([] if CONTEXT.get() is not None else session.messages):
        if not getattr(message,'demo',False) and message.text.strip():
            messages.append({'role':message.role,'content':message.text})
    text=tasks[action]+'：'+prompt
    messages=apply_context(messages,text,len(selected) if profile.get('vision') else 0)
    if profile['provider']=='ollama':
        user={'role':'user','content':text}
        if profile.get('vision'):user['images']=[a.data.split(',',1)[1] for a in selected]
    elif profile.get('vision'):
        user={'role':'user','content':[{'type':'text','text':text}]+[{'type':'image_url','image_url':{'url':a.data}} for a in selected]}
    else:
        user={'role':'user','content':text}
    # The current prompt may already be the last history message.
    if CONTEXT.get() is None and messages[-1]['role']=='user' and messages[-1]['content']==prompt:messages.pop()
    messages.append(user)
    key=unprotect_key(profile.get('apiKeyProtected'))
    headers={'Authorization':'Bearer '+key} if key else {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=8),follow_redirects=False,trust_env=False) as client:
            url=endpoint(profile,'chat' if profile['provider']=='ollama' else 'chat/completions')
            body={'model':profile['model'],'messages':messages,'stream':bool(on_chunk)}
            if profile.get('_agentDecision'):
                if profile['provider']=='ollama':body['format']='json'
                else:body['response_format']={'type':'json_object'}
            if on_chunk:
                if profile['provider']!='ollama':body['stream_options']={'include_usage':True}
                output='';usage={};finished=False
                async with client.stream('POST',url,headers=headers,json=body) as response:
                    if not response.is_success:raise HTTPException(400,safe_http_error(response.status_code))
                    async for line in response.aiter_lines():
                        if not line.strip() or line.startswith(':'):continue
                        if profile['provider']=='ollama':
                            item=json.loads(line);delta=item.get('message',{}).get('content','');finished=finished or item.get('done',False)
                            if item.get('done'):usage={'prompt_tokens':item.get('prompt_eval_count'),'completion_tokens':item.get('eval_count')}
                        else:
                            if not line.startswith('data:'):continue
                            raw=line[5:].strip()
                            if raw=='[DONE]':finished=True;break
                            item=json.loads(raw)
                            if item.get('error'):raise HTTPException(502,'模型流式回复失败，请检查接口配置')
                            if item.get('usage'):usage=item['usage']
                            choice=(item.get('choices') or [{}])[0];delta=(choice.get('delta') or {}).get('content') or '';finished=finished or bool(choice.get('finish_reason'))
                        if not isinstance(delta,str):raise ValueError()
                        output+=delta
                        if len(output)>200000:raise HTTPException(413,'模型回复过长，请分段提问')
                        if delta:await on_chunk(delta)
                    if not finished:raise HTTPException(502,'模型流式回复中断，请重试')
                input_tokens=usage.get('prompt_tokens');output_tokens=usage.get('completion_tokens');cache_tokens=cached_input_tokens(usage,input_tokens)
                if not output.strip() and action!='ocr':raise ValueError()
            else:
                response=await client.post(url,headers=headers,json=body)
        if not on_chunk:
            if not response.is_success:raise HTTPException(400,safe_http_error(response.status_code))
            data=response.json()
            cache_tokens=None
            if profile['provider']=='ollama':
                output=data['message']['content'];input_tokens=data.get('prompt_eval_count');output_tokens=data.get('eval_count')
            else:
                output=data['choices'][0]['message']['content'];usage=data.get('usage') or {};input_tokens=usage.get('prompt_tokens');output_tokens=usage.get('completion_tokens')
                cache_tokens=cached_input_tokens(usage,input_tokens)
        if not isinstance(output,str) or (not output.strip() and action!='ocr'):raise ValueError()
    except httpx.TimeoutException:
        raise HTTPException(408,'模型回复超时，请稍后重试')
    except httpx.RequestError:
        raise HTTPException(400,'无法连接已启用的模型服务，请检查连接配置')
    except (ValueError,KeyError,IndexError,TypeError):
        raise HTTPException(400,'模型返回了无法读取的回复，请检查接口类型')
    reported=all(isinstance(value,int) and not isinstance(value,bool) and value>=0 for value in (input_tokens,output_tokens))
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO model_usage(id,model,input_tokens,output_tokens,created_at,tokens_reported,cached_input_tokens) VALUES(?,?,?,?,?,?,?)',(str(uuid4()),profile['model'],input_tokens if reported else 0,output_tokens if reported else 0,datetime.now(timezone.utc).isoformat(),int(reported),cache_tokens if reported else None))
    # Preserve complete transcription/translation structure rather than cutting a row or paragraph.
    return {'text':output if action in ('ocr','translate','explain','table-json','objects','annotate','study') else output[:20000],'kind':'text'}
