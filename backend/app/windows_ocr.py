"""Windows OCR via Python WinRT projections, without PowerShell or .NET."""
import asyncio
import base64
import json
from pathlib import Path
import sys

vendor=Path(__file__).resolve().parents[1]/'vendor'
if vendor.is_dir():sys.path.insert(0,str(vendor))

async def recognize(request):
    from winrt.windows.storage.streams import InMemoryRandomAccessStream,DataWriter
    from winrt.windows.graphics.imaging import BitmapDecoder,BitmapPixelFormat,SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    engine=OcrEngine.try_create_from_user_profile_languages()
    if engine is None:raise RuntimeError('No installed OCR language')
    text=[];documents=[]
    for encoded in request['images']:
        stream=InMemoryRandomAccessStream();writer=DataWriter(stream);bitmap=None
        try:
            writer.write_bytes(base64.b64decode(encoded,validate=True))
            await writer.store_async();stream.seek(0)
            decoder=await BitmapDecoder.create_async(stream)
            bitmap=await decoder.get_software_bitmap_async()
            if bitmap.bitmap_pixel_format not in (BitmapPixelFormat.BGRA8,BitmapPixelFormat.GRAY8):
                converted=SoftwareBitmap.convert(bitmap,BitmapPixelFormat.BGRA8);bitmap.close();bitmap=converted
            result=await engine.recognize_async(bitmap)
            text.append('\n'.join(line.text for line in result.lines))
            if request.get('locations'):
                documents.append({'lines':[{'text':line.text,'words':[{'text':word.text,'bbox':[word.bounding_rect.x,word.bounding_rect.y,word.bounding_rect.x+word.bounding_rect.width,word.bounding_rect.y+word.bounding_rect.height]} for word in line.words]} for line in result.lines]})
        finally:
            if bitmap is not None:bitmap.close()
            writer.detach_stream();writer.close();stream.close()
    return {'text':'\n'.join(text),'documents':documents,'language':engine.recognizer_language.language_tag}

if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.read(80_000_000));result=asyncio.run(recognize(request))
        sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
    except Exception:
        sys.stderr.write('Windows OCR unavailable or image invalid\n');sys.exit(1)
