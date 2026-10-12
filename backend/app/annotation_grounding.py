"""Conservative text matching and UI control alignment in screenshot pixels."""
import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi import HTTPException


class ControlTarget(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    id: str = Field(pattern=r'^control-[0-9]{1,4}$')
    text: str = Field(default='', max_length=160)
    controlType: Literal['Button','Edit','ComboBox','CheckBox','RadioButton','Hyperlink','MenuItem','TabItem','ListItem','TreeItem','Slider','Spinner']
    bbox: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode='after')
    def valid_box(self):
        l,t,r,b=self.bbox
        if not all(math.isfinite(v) and v>=0 for v in self.bbox) or r-l<4 or b-t<4:
            raise ValueError('控件边界无效')
        return self


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum() or c in '=<>!+-*/%&|^_')


def similarity(query,text):
    a,b=normalized(query),normalized(text)
    if not a or not b:return 0
    if a==b:return 1
    if a in b:return .96
    # OCR punctuation noise is tolerable; changed code/math operators are not.
    operators=lambda s:''.join(c for c in s if c in '=<>!+-*/%&|^_')
    if operators(a)!=operators(b):return 0
    if len(a)>=4 and len(b)>=4:
        ratio=SequenceMatcher(None,a,b).ratio()
        return ratio if ratio>=.84 else 0
    return 0


def near(box,other):
    l,t,r,b=box; x,y,right,bottom=other
    cx,cy=(l+r)/2,(t+b)/2
    dx=max(x-cx,cx-right,0);dy=max(y-cy,cy-bottom,0)
    return dx<=max(12,(r-l)*.35) and dy<=max(8,(b-t)*.5)


def match_text(query,targets,coarse=None):
    """A repeated label needs a local geometric discriminator; never guess."""
    candidates=[t for t in targets if t['type']=='text' and similarity(query,t['text'])]
    if coarse:candidates=[t for t in candidates if near(coarse,t['bbox'])]
    ranked=sorted(((similarity(query,t['text']),t) for t in candidates),key=lambda item:item[0],reverse=True)
    if not ranked:return None
    if len(ranked)>1 and ranked[0][0]-ranked[1][0]<.12:return None
    if len(normalized(query))<2 and coarse is None:return None
    return ranked[0][1]


def control_intent(prompt):
    # Asking to mark the word itself must keep its text bounds, not its button.
    if re.search(r'文字|文本|标题|段落|这[行句段]|\b(text|paragraph|title)\b',prompt,re.I):return False
    return bool(re.search(r'按钮|输入框|控件|菜单|选项|图标|复选|下拉|开关|标签页|\b(button|input|control|menu|checkbox|dropdown|icon|tab)\b',prompt,re.I))


def refine_control(selected,controls,prompt):
    if not control_intent(prompt) or len(selected)!=1 or selected[0]['type']!='text':return None
    line=selected[0]
    candidates=[]
    for control in controls:
        if not near(line['bbox'],control['bbox']):continue
        score=similarity(line['text'],control['text'])
        if score<.84:continue
        l,t,r,b=line['bbox'];x,y,right,bottom=control['bbox']
        # Text must mostly lie inside the control; adjacent controls cannot win.
        intersection=max(0,min(r,right)-max(l,x))*max(0,min(b,bottom)-max(t,y))
        if intersection/((r-l)*(b-t))<.75:continue
        if (right-x)/(r-l)>8 or (bottom-y)/(b-t)>6:continue
        candidates.append((score,control))
    candidates.sort(key=lambda item:item[0],reverse=True)
    if not candidates or len(candidates)>1 and candidates[0][0]-candidates[1][0]<.12:return None
    return candidates[0][1]


def validate_controls(controls,width,height):
    if len({c.id for c in controls})!=len(controls):raise HTTPException(400,'控件定位编号重复')
    if any(c.bbox[2]>width or c.bbox[3]>height for c in controls):raise HTTPException(400,'控件边界超出截图')
    return [c.model_dump()|{'type':'control'} for c in controls
            if (c.bbox[2]-c.bbox[0])*(c.bbox[3]-c.bbox[1])<width*height*.88]
