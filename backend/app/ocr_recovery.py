"""Find compact text strips from pixels, without model-generated geometry."""
import cv2
import numpy as np
from PIL import Image


def text_strips(image, max_strips=64):
    gray=np.asarray(image.convert('L'))
    # Recovery is restricted to light documents; photos/dark themes retain OCR.
    if np.mean(gray>220)<.65:return []
    ink=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV|cv2.THRESH_OTSU)[1]
    height,width=ink.shape
    rules=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(80,width//5)),np.uint8))
    rules|=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(80,height//5),1),np.uint8))
    clean=cv2.subtract(ink,rules)
    n,labels,stats,_=cv2.connectedComponentsWithStats(clean)
    heights=[int(s[3]) for s in stats[1:] if 5<=s[3]<=80 and 2<=s[2]<=100 and s[4]>=8]
    if not heights:return []
    char_height=float(np.median(heights))
    grouped=cv2.dilate(clean,np.ones((3,max(3,round(char_height*.65))),np.uint8))
    count,_,boxes,_=cv2.connectedComponentsWithStats(grouped)
    result=[]
    for x,y,w,h,area in boxes[1:]:
        if not (6<=h<=max(100,char_height*2) and w>=8 and area>=20):continue
        if w>width*.95 or h>height*.4:continue
        l,t,r,b=max(0,int(x)-2),max(0,int(y)-2),min(width,int(x+w)+2),min(height,int(y+h)+2)
        crop=Image.fromarray(255-clean[t:b,l:r]).convert('RGB')
        result.append({'bbox':[l,t,r,b],'image':crop})
    result.sort(key=lambda item:(item['bbox'][1]//max(1,round(char_height)),item['bbox'][0]))
    return result if len(result)<=max_strips else []


def strip_atlas(strips):
    """Upscale text with whitespace; OCR one atlas instead of a subprocess per cell."""
    tiles=[];pages=[];current=[];height=20
    for strip in strips:
        crop=strip['image'].resize((strip['image'].width*2,strip['image'].height*2),Image.Resampling.LANCZOS)
        if crop.width>2300:continue
        if height+crop.height+40>2300 and current:
            pages.append(current);current=[];height=20
        current.append((strip,crop,height));height+=crop.height+40
    if current:pages.append(current)
    for page in pages:
        width=max(c.width for _,c,_ in page)+40
        atlas=Image.new('RGB',(width,page[-1][2]+page[-1][1].height+20),'white')
        mapping=[]
        for strip,crop,y in page:
            atlas.paste(crop,(20,y));mapping.append({'bbox':strip['bbox'],'atlasBbox':[20,y,20+crop.width,y+crop.height]})
        tiles.append((atlas,mapping))
    return tiles


def coverage(box, other):
    l,t,r,b=box;x,y,right,bottom=other
    return max(0,min(r,right)-max(l,x))*max(0,min(b,bottom)-max(t,y))/max(1,(r-l)*(b-t))


def merge_atlas(document, mappings, documents):
    regions=list(document['regions'])
    for mapping,recognized in zip(mappings,documents):
        for tile in mapping:
            l,t,r,b=tile['bbox'];x,y,right,bottom=tile['atlasBbox']
            words=[w for line in recognized['lines'] for w in line['words']
                if x<=sum(w['bbox'][::2])/2<=right and y<=sum(w['bbox'][1::2])/2<=bottom]
            if not words:continue
            words.sort(key=lambda word:word['bbox'][0])
            text=' '.join(w['text'] for w in words)
            # Keep original number punctuation; recovery must not change decimals.
            old=[item for item in regions if coverage(item['bbox'],tile['bbox'])>=.75]
            if not old and any(coverage(tile['bbox'],item['bbox'])>=.65 for item in regions):continue
            if old and (all(not any(c.isalpha() for c in item['text']) for item in old)
                        or any(any(token in item['text'] for token in ('@','://')) for item in old)):continue
            regions=[item for item in regions if item not in old]
            regions.append({'text':text,'bbox':tile['bbox'],'label':'text','page':0,'granularity':'line','recovered':True})
    regions.sort(key=lambda item:(round(item['bbox'][1]/12),item['bbox'][0]))
    return document|{'regions':regions,'text':'\n'.join(item['text'] for item in regions)}


def pending_regions(data, document):
    """Uncovered text-shaped pixels can be read by vision using fixed IDs/boxes."""
    import base64
    import io
    image=Image.open(io.BytesIO(base64.b64decode(data.split(',',1)[1],validate=True))).convert('RGB')
    strips=text_strips(image)
    return [{'id':f'text-{len(document["regions"])+i+1}','text':'','bbox':strip['bbox'],
             'recognitionRequired':True}
            for i,strip in enumerate(strips)
            if not any(coverage(strip['bbox'],region['bbox'])>=.5 or coverage(region['bbox'],strip['bbox'])>=.75
                       for region in document['regions'])]
