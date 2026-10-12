import type {ImageConversationResult} from './api'
export function imageSteps(result:ImageConversationResult){return result.steps?.length?result.steps:[result]}
export const agentToolLabels:Record<string,string>={answer:'整理回复',ocr:'提取文字',offline:'定位截图文字',translate:'原位翻译',table:'提取表格',detect:'识别物体',annotate:'添加标注',qr:'识别二维码',entities:'提取链接',crop:'裁剪截图',highlight:'高亮文字',mosaic:'文字打码',heal:'消除文字',lift:'提取透明图层',region:'增加截图区域',draw:'绘制标注',blur:'模糊文字',undo:'撤销操作',clear_annotations:'清空 AI 标注'}
