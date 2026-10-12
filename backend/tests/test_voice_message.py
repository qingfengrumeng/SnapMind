import base64
import io
import wave
import pytest
from pydantic import ValidationError
from backend.app.voice_message import VoiceMessage

def recording():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as writer:
        writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(16000);writer.writeframes(b'\0\0'*32000)
    return {'data':'data:audio/wav;base64,'+base64.b64encode(stream.getvalue()).decode(),'duration':2,'waveform':[0,.2,.4]}

def test_voice_recording_roundtrip_preserves_original_audio():
    payload=recording();assert VoiceMessage.model_validate(payload).model_dump()==payload

@pytest.mark.parametrize('change',[{'duration':3},{'data':'https://example.com/audio.wav'}, {'data':'data:audio/wav;base64,aGVsbG8='},{'waveform':[float('nan')]},{'waveform':[1.1]}])
def test_invalid_audio_metadata_and_remote_urls_are_rejected(change):
    with pytest.raises(ValidationError):VoiceMessage.model_validate(recording()|change)
