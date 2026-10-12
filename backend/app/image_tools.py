"""Local image-only utilities. Pixels never leave this machine for these tools."""
import base64
import io
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import cv2
import numpy as np
from PIL import Image
from fastapi import HTTPException


def image_from_data(data):
    try:
        if not data.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
            raise ValueError()
        image = Image.open(io.BytesIO(base64.b64decode(data.split(',', 1)[1], validate=True)))
        if image.width * image.height > 40_000_000 or max(image.size) > 20000:
            raise ValueError()
        image.load()
        return image.convert('RGB')
    except (ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(400, '图片无法读取或尺寸过大')


def png_data(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def valid_rect(bbox, width, height):
    if len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
        raise HTTPException(400, '选区坐标无效')
    left, top, right, bottom = [round(v) for v in bbox]
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise HTTPException(400, '选区超出图片')
    return left, top, right, bottom


def repair(data, mask_data, extract=False):
    image = image_from_data(data)
    try:
        mask_image = Image.open(io.BytesIO(base64.b64decode(mask_data.split(',', 1)[1], validate=True)))
        if mask_image.size != image.size:
            raise ValueError()
        # The client mask is opaque black with opaque white painted pixels.
        mask = np.where(np.asarray(mask_image.convert('L')) > 127, 255, 0).astype('uint8')
    except (ValueError, OSError, IndexError):
        raise HTTPException(400, '修补区域与图片尺寸不一致')
    if not np.any(mask):
        raise HTTPException(400, '请先涂抹或框选需要处理的区域')
    if np.count_nonzero(mask) > mask.size * .7:
        raise HTTPException(400, '修补区域过大，请缩小范围以保留周围背景')
    # Telea extends nearby colours/gradients; no invented generative content.
    fixed = cv2.inpaint(np.asarray(image), mask, 3, cv2.INPAINT_TELEA)
    output = {'data': png_data(Image.fromarray(fixed)), 'width': image.width, 'height': image.height}
    if extract:
        # Remove the locally estimated background, retaining text/simple pattern opacity.
        rgb = np.asarray(image).astype('float32')
        difference = np.max(np.abs(rgb - fixed.astype('float32')), axis=2)
        alpha = np.where(mask > 0, np.clip((difference - 8) * 5, 0, 255), 0).astype('uint8')
        ys, xs = np.where(alpha > 0)
        if not len(xs):
            raise HTTPException(400, '选区没有可分离的文字或图案，请调整范围')
        left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        rgba = np.dstack((np.asarray(image), alpha))[top:bottom, left:right]
        output['layer'] = {'data': png_data(Image.fromarray(rgba)), 'bbox': [left, top, right, bottom]}
    return output


def decode_codes(data):
    image = image_from_data(data)
    try:
        import zxingcpp
    except ImportError:
        vendor = str(Path(__file__).resolve().parents[1] / 'vendor')
        if vendor not in sys.path:
            sys.path.append(vendor)
        try:
            import zxingcpp
        except ImportError:
            raise HTTPException(503, '二维码组件未安装，请安装后端依赖 zxing-cpp')
    results = []
    for code in zxingcpp.read_barcodes(image):
        if not code.valid or not code.text:
            continue
        points = [code.position.top_left, code.position.top_right, code.position.bottom_right, code.position.bottom_left]
        bbox = [min(p.x for p in points), min(p.y for p in points), max(p.x for p in points), max(p.y for p in points)]
        url = safe_entity_url(code.text)
        results.append({'text': code.text[:20000], 'format': str(code.format), 'bbox': bbox, 'url': url})
    return {'codes': results[:50], 'width': image.width, 'height': image.height}


def safe_entity_url(text):
    candidate = text.strip()
    if candidate.startswith('www.'):
        candidate = 'https://' + candidate
    try:
        parts = urlsplit(candidate)
        if parts.scheme in ('http', 'https') and parts.hostname and not parts.username and not parts.password:
            return candidate
    except ValueError:
        pass
    return None


def screen_entities(location):
    results, seen = [], set()
    patterns = [('url', r'(?:https?://|www\.)[^\s<>"\u3000]+'),
                ('email', r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+'),
                ('phone', r'(?<!\w)(?:\+\d{1,3}[ -]?)?(?:1[3-9]\d{9}|\d{3,4}[ -]\d{6,8})(?!\w)')]
    for region in location['regions']:
        for kind, pattern in patterns:
            for match in re.finditer(pattern, region['text']):
                text = match.group().rstrip('.,;，。；)）]】')
                key = (kind, text)
                if key in seen:
                    continue
                url = safe_entity_url(text) if kind == 'url' else ('mailto:' if kind == 'email' else 'tel:') + text
                if not url:
                    continue
                seen.add(key)
                results.append({'kind': kind, 'text': text, 'url': url, 'bbox': region['bbox']})
    return {'entities': results[:100], 'width': location['width'], 'height': location['height']}
