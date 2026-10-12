"""Validate persisted microphone PCM/WAV; never accept arbitrary media URLs."""
import base64
import io
import wave
from pydantic import BaseModel,ConfigDict,Field,model_validator

class VoiceMessage(BaseModel):
    model_config=ConfigDict(extra='forbid')
    data:str=Field(max_length=5_130_000)
    duration:float=Field(gt=0,le=120,allow_inf_nan=False)
    waveform:list[float]=Field(min_length=1,max_length=64)

    @model_validator(mode='after')
    def valid_audio(self):
        if any(not 0<=level<=1 for level in self.waveform):raise ValueError('语音波形无效')
        if not self.data.startswith('data:audio/wav;base64,'):raise ValueError('语音必须是本地 WAV 录音')
        try:
            raw=base64.b64decode(self.data.split(',',1)[1],validate=True)
            with wave.open(io.BytesIO(raw)) as audio:
                rate=audio.getframerate();frames=audio.getnframes()
                if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or rate not in (8000,16000) or frames<=0 or frames>rate*120:raise ValueError()
                if abs(frames/rate-self.duration)>.01 or len(audio.readframes(frames))!=frames*2:raise ValueError()
        except (ValueError,wave.Error,EOFError):raise ValueError('语音数据与时长不一致') from None
        return self
