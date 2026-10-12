from dataclasses import dataclass, field
from copy import deepcopy
from uuid import uuid4
from fastapi import HTTPException
from ..image_tools import image_from_data, png_data
from ..annotation_grounding import match_text


@dataclass
class AgentState:
    assets: list
    selected_id: str | None
    prompt: str
    history: list
    existing: list
    controls: list
    language: str
    steps: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    undo: list = field(default_factory=list)
    last_answer: str = ''
    image_contexts: dict = field(default_factory=dict)
    locations: dict = field(default_factory=dict)

    def activate(self,image_id):
        if image_id==self.selected_id:return
        self.selected(image_id)
        self.image_contexts[self.selected_id]=(deepcopy(self.existing),deepcopy(self.controls))
        self.selected_id=image_id
        self.existing,self.controls=deepcopy(self.image_contexts.get(image_id,([],[])))

    def selected(self, image_id=None):
        selected = next((a for a in self.assets if a.id == (image_id or self.selected_id)), None)
        if selected is None:raise HTTPException(400, '工具引用的图片不存在，请先提供截图')
        return selected

    def checkpoint(self):
        return (list(self.assets), self.selected_id, deepcopy(self.existing), deepcopy(self.controls),deepcopy(self.image_contexts))

    def restore(self, value):
        self.assets, self.selected_id, self.existing, self.controls,self.image_contexts = deepcopy(value)

    def replace(self, old, data, width=None, height=None):
        from types import SimpleNamespace
        values={**vars(old)} if not hasattr(old,'model_dump') else old.model_dump()
        values.update(data=data,width=width or old.width,height=height or old.height)
        item=old.model_copy(update=values) if hasattr(old,'model_copy') else SimpleNamespace(**values)
        self.assets=[item if a.id==old.id else a for a in self.assets]

    def commit(self, result):
        payload=result['payload'];action=result['action'];id=result['assetId']
        if action in ('crop','heal','lift','restore_image'):
            old=self.selected(id);self.replace(old,payload['data'],payload['width'],payload['height']);self.existing=deepcopy(payload.get('annotations',[]));self.controls=[]
        elif action=='region':
            from types import SimpleNamespace
            old=self.selected(id)
            values=old.model_dump() if hasattr(old,'model_dump') else vars(old).copy()
            values.update(id=payload.setdefault('imageId','region-'+uuid4().hex),name='截图区域',data=payload['data'],width=payload['width'],height=payload['height'])
            self.assets.append(old.model_copy(update=values) if hasattr(old,'model_copy') else SimpleNamespace(**values));self.activate(values['id'])
        elif action=='annotate':
            next_id=max([int(a['id'][3:]) for a in self.existing]+[0])
            for edit in payload['annotations']:
                if edit['operation']=='remove':self.existing=[a for a in self.existing if a['id']!=edit['id']];continue
                if edit['operation']=='add':next_id+=1;item={k:v for k,v in edit.items() if k!='operation'}|{'id':'ai-'+str(next_id)};self.existing.append(item)
                else:self.existing=[({k:v for k,v in edit.items() if k!='operation'} if a['id']==edit['id'] else a) for a in self.existing]
        elif action in ('translate','highlight','mosaic','blur','detect'):
            from .rendering import render_result
            old=self.selected(id);rendered=render_result(old,result)
            self.replace(old,png_data(rendered));self.existing=[];self.controls=[]
        self.steps.append(deepcopy(result));self.last_answer=result['answer']
