from fastapi.testclient import TestClient
from backend.tests.test_capture_processing import module


def test_text_attachment_and_long_prompt_roundtrip(module,monkeypatch):
    content='中文\n' * 1000 + '<script>plain text</script>'
    attachment={'id':'text-synthetic','name':'粘贴内容.txt','content':content}
    body={'id':'imagechat-text-test','title':'文本附件','scenario':'custom','assets':[],
          'messages':[{'id':'turn-user','role':'user','text':content,'textAttachments':[attachment]}],
          'formula':'','rows':[],'createdAt':'2026-10-10T00:00:00Z','updatedAt':'2026-10-10T00:00:00Z',
          'imageConversation':{'version':1,'selectedId':None,'pictures':[],'textAttachments':[attachment]}}
    client=TestClient(module.app)
    assert client.put('/api/sessions/'+body['id'],json=body).status_code==200
    stored=next(s for s in client.get('/api/sessions').json() if s['id']==body['id'])
    assert stored['messages'][0]['textAttachments']==[attachment]
    assert stored['imageConversation']['textAttachments']==[attachment]
    captured=[]
    async def converse(*args,**kwargs):
        captured.append(args[3])
        return {'action':'chat','assetId':None,'answer':'Synthetic','payload':{}}
    monkeypatch.setattr(module,'run_agent',converse)
    before=client.get('/api/sessions').json()
    assert client.post('/api/capture/conversation',json={'prompt':content,'action':'chat'}).status_code==200
    assert captured==[content]
    call={'name':'ocr','arguments':{'prompt':content},'context':{'prompt':content}}
    assert client.post('/api/tools/call',json=call).status_code==200
    assert captured[-1]==content
    assert client.get('/api/sessions').json()==before, 'Calls without a sessionId must remain transient'


def test_text_attachment_size_limit(module):
    attachment={'id':'text-limit','name':'large.txt','content':'x'*100001}
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        module.TextAttachment.model_validate(attachment)
    with pytest.raises(ValidationError):
        module.ImageConversationRequest.model_validate({'prompt':'x'*205001})
