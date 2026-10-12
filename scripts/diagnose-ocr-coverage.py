"""Inspect actual Windows/cloud OCR on a generated Chinese order table."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from backend.app.capture_processing import recognize_positions_async
from backend.app.image_tools import png_data
from backend.app.ocr_locator import locate
from backend.app import main
from backend.app.ocr_recovery import text_strips, strip_atlas

async def run():
    image=Image.new('RGB',(760,430),'white');g=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',28)
    for text,x,y in [('订单汇总',30,55),('商品',30,120),('数量',330,120),('单价',520,120),('键盘',30,176),('2',330,176),('100.00',520,176),('鼠标',30,232),('1',330,232),('50.00',520,232),('邮箱 support@example.com',30,315)]:
        g.text((x,y),text,font=font,fill='black',anchor='ls')
    for y in [80,136,192,248]:g.line((20,y,720,y),fill='#999')
    out=Path('artifacts/ocr-quality');out.mkdir(parents=True,exist_ok=True);image.save(out/'input.png')
    for name,data in [('original',png_data(image)),('scaled',png_data(image.resize((1520,860))))]:
        result=await recognize_positions_async(data)
        (out/f'{name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'case':name,'text':result['text'],'regions':result['regions'],'language':result.get('language')},ensure_ascii=True),flush=True)
    result=await locate(main.DB,png_data(image),require_lines=True,cloud_timeout=15)
    (out/'located.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'case':'located','text':result['text'],'regions':result['regions'],'mode':result.get('mode'),'fallbackReason':result.get('fallbackReason')},ensure_ascii=True),flush=True)
    for index,(atlas,mapping) in enumerate(strip_atlas(text_strips(image))):
        atlas.save(out/f'atlas-{index}.png')
        result=await recognize_positions_async(png_data(atlas))
        print(json.dumps({'case':'atlas','mapping':mapping,'text':result['text'],'regions':result['regions']},ensure_ascii=True),flush=True)

asyncio.run(run())
