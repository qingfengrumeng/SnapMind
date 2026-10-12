"""Read a service's documented model catalog; never substitute a built-in list."""
from urllib.parse import urlsplit, urljoin
import httpx
from fastapi import HTTPException
from .model_profiles import normalize_url, safe_http_error

UNSUPPORTED = '该 OCR 服务未提供模型列表接口，请手动输入模型名称'

async def fetch_ocr_models(config, key):
    url = normalize_url(config.baseUrl)
    origin = urlsplit(url)
    # The official job API documents no model-list operation. In particular,
    # the SDK's model enum is not an account's authenticated model catalog.
    if origin.hostname == 'paddleocr.aistudio-app.com':
        raise HTTPException(400, UNSUPPORTED)
    headers = {'Authorization':('Bearer ' if config.apiMode=='async' else 'token ')+key}
    root = f'{origin.scheme}://{origin.netloc}'
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False,trust_env=False) as client:
            # Custom OCR services may publish a catalog via their OpenAPI spec.
            # Only call the model-list route actually declared by that service.
            spec_response = await client.get(root+'/openapi.json',headers=headers)
            if spec_response.status_code in (404,405): raise HTTPException(400,UNSUPPORTED)
            if not spec_response.is_success: raise HTTPException(400,safe_http_error(spec_response.status_code))
            spec = spec_response.json()
            paths = spec.get('paths',{})
            routes = [path for path,operations in paths.items()
                      if isinstance(operations,dict) and 'get' in operations
                      and path.rstrip('/').endswith('/models') and '{' not in path]
            if len(routes)!=1: raise HTTPException(400,UNSUPPORTED)
            servers = spec.get('servers') or [{'url':'/'}]
            server = urljoin(root+'/',servers[0]['url'])
            if urlsplit(server)[:2]!=origin[:2]: raise HTTPException(400,UNSUPPORTED)
            endpoint = server.rstrip('/')+'/'+routes[0].lstrip('/')
            models, cursors = [], set()
            cursor = None
            for page in range(100):
                response = await client.get(endpoint,headers=headers,params={'after':cursor} if cursor else None)
                if response.status_code in (404,405): raise HTTPException(400,UNSUPPORTED)
                if not response.is_success: raise HTTPException(400,safe_http_error(response.status_code))
                payload = response.json()
                records = payload if isinstance(payload,list) else payload.get('data',payload.get('models'))
                if isinstance(records,dict): records=records.get('models')
                if not isinstance(records,list): raise ValueError()
                names = [item if isinstance(item,str) else item.get('id',item.get('name')) for item in records if isinstance(item,(str,dict))]
                models.extend(name.strip() for name in names if isinstance(name,str) and name.strip())
                if not isinstance(payload,dict) or not payload.get('has_more'): break
                cursor = payload.get('last_id') or (names[-1] if names else None)
                if not isinstance(cursor,str) or cursor in cursors or page==99:
                    raise HTTPException(400,'模型列表分页异常，请手动输入模型名称')
                cursors.add(cursor)
            return {'models':list(dict.fromkeys(models))}
    except httpx.TimeoutException:
        raise HTTPException(408,'获取模型列表超时，请检查网络后重试')
    except httpx.RequestError:
        raise HTTPException(400,'无法连接 OCR 服务，请检查接口地址与网络')
    except (ValueError,AttributeError,TypeError,KeyError,IndexError):
        raise HTTPException(400,'服务未返回有效的模型列表，请手动输入模型名称')
