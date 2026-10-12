from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ToolDecision(StrictModel):
    kind: Literal['tool']
    name: str = Field(min_length=1, max_length=64)
    arguments: dict
    done: bool = False


class FinalDecision(StrictModel):
    kind: Literal['final']
    # This is a brief instruction for the answer tool, not a fabricated tool result.
    instruction: str = Field(default='', max_length=2000)


Decision = Annotated[ToolDecision | FinalDecision, Field(discriminator='kind')]


class BaseArguments(StrictModel):
    imageId: str | None = Field(default=None, min_length=1, max_length=80)
    prompt: str = Field(default='', max_length=205000)


class CropArguments(BaseArguments):
    bbox: list[FiniteFloat] | None = Field(default=None,min_length=4,max_length=4)
    targetText: str | None = Field(default=None,min_length=1,max_length=300)

    @model_validator(mode='after')
    def one_target(self):
        if (self.bbox is None)==(self.targetText is None):
            raise ValueError('裁剪必须且只能提供 bbox 或 targetText；文字区域可提供截图原文，工具会真实定位')
        if self.bbox and (self.bbox[0]<0 or self.bbox[1]<0 or self.bbox[2]<=self.bbox[0] or self.bbox[3]<=self.bbox[1]):
            raise ValueError('bbox 必须是有效的 [左,上,右,下] 像素矩形')
        if self.targetText is not None and not self.targetText.strip():raise ValueError('裁剪目标原文不能为空')
        return self


class DrawArguments(BaseArguments):
    kind: Literal['circle', 'rectangle', 'arrow', 'highlight', 'text', 'number', 'check', 'cross', 'callout']
    bbox: list[FiniteFloat] = Field(min_length=4, max_length=4)
    text: str = Field(default='', max_length=40)

    @model_validator(mode='after')
    def ordered(self):
        if self.bbox[0] < 0 or self.bbox[1] < 0 or self.bbox[2] <= self.bbox[0] or self.bbox[3] <= self.bbox[1]:
            raise ValueError('bbox 必须是有效的 [左,上,右,下] 像素矩形')
        if self.kind in ('text', 'callout', 'number') and not self.text.strip():
            raise ValueError('文字、气泡和序号工具必须提供 text')
        return self


class BlurArguments(BaseArguments):
    targetText: str = Field(min_length=1, max_length=300)
    radius: FiniteFloat = Field(default=8, ge=1, le=40)


class Result(StrictModel):
    action: str = Field(min_length=1, max_length=64)
    assetId: str | None
    answer: str = Field(max_length=200000)
    payload: dict


class AnnotationResultEdit(StrictModel):
    operation: Literal['add','update','remove']
    id: str | None = Field(default=None,pattern=r'^ai-[0-9]{1,10}$')
    kind: Literal['circle','rectangle','arrow','highlight','text','number','check','cross','callout'] = 'callout'
    text: str = Field(default='',max_length=40)
    bbox: list[FiniteFloat] | None = Field(default=None,min_length=4,max_length=4)
    targetIds: list[str] = Field(default_factory=list,max_length=40)
    targetText: str = Field(default='',max_length=300)
    locationSource: Literal['visual','ocr','uia','object-detection','existing'] | None = None

    @model_validator(mode='after')
    def valid_edit(self):
        if self.operation=='add' and self.id is not None:raise ValueError('新增标注不应指定 ID')
        if self.operation!='add' and self.id is None:raise ValueError('修改或删除标注需要 ID')
        if self.operation!='remove' and self.bbox is None:raise ValueError('标注结果缺少像素位置')
        return self


class Limits(StrictModel):
    max_steps: int = Field(default=8, ge=1, le=16)
    schema_attempts: int = Field(default=3, ge=1, le=5)
    transient_attempts: int = Field(default=2, ge=1, le=3)
    total_seconds: int = Field(default=240, ge=10, le=600)
    tool_seconds: int = Field(default=120, ge=5, le=240)
    observation_bytes: int = Field(default=24000, ge=2000, le=64000)
