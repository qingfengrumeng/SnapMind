"""Working pixels for chained tools; the client retains its native final renderer."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fastapi import HTTPException
from ..image_tools import image_from_data, valid_rect


def font(size):
    for file in ('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/segoeui.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if Path(file).exists():return ImageFont.truetype(file,size)
    return ImageFont.load_default(size=size)


def render_result(asset,result):
    image=image_from_data(asset.data).convert('RGBA');draw=ImageDraw.Draw(image);payload=result['payload'];action=result['action']
    if action=='translate':
        for line in payload['lines']:
            l,t,r,b=valid_rect(line['bbox'],image.width,image.height)
            draw.rectangle((l,t,r-1,b-1),fill='white')
            size=max(8,min(32,int((b-t)*.8)));face=font(size)
            while size>8 and draw.textlength(line['text'],font=face)>r-l:size-=1;face=font(size)
            draw.text((l,t),line['text'],font=face,fill='#342747')
    elif action=='detect':
        for item in payload['objects']:draw.rectangle(valid_rect(item['bbox'],image.width,image.height),outline='#843dff',width=2)
    else:
        box=valid_rect(payload['bbox'],image.width,image.height)
        if action=='highlight':
            overlay=Image.new('RGBA',image.size);ImageDraw.Draw(overlay).rectangle(box,fill=(255,211,60,100));image=Image.alpha_composite(image,overlay)
        elif action=='mosaic':
            l,t,r,b=box;part=image.crop(box);part=part.resize((max(1,(r-l)//12),max(1,(b-t)//12))).resize((r-l,b-t),Image.Resampling.NEAREST);image.paste(part,(l,t))
        elif action=='blur':image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(payload['radius'])),box)
        else:raise HTTPException(502,'工具结果不能渲染')
    return image
