import type {ImageAction,ImageToolCatalog,ImageToolCall} from './api'

export type ImageToolName=Exclude<ImageAction,'chat'|'note'|'explain'|'code'|'paper'|'exam'|'formula'|'blur'|'restore_image'|'draw'|'undo'|'clear_annotations'|'answer'>
export interface ImageToolCommand{name:ImageToolName;label:string;icon:string;group:string;description:string;summary?:string;example?:string;parameters:Record<string,unknown>;required:string[]}
const examples:Partial<Record<ImageToolName,string>>={
 ocr:'提取这张截图中的全部文字，保留原文的换行和缩进。',
 table:'提取这张截图中的表格，保留表头和数据，整理成可复制到 Excel 的格式。',
 translate:'将这张截图中的文字翻译成简体中文，并在原文位置显示译文。',
}
const summaries:Record<ImageToolName,string>={
 ocr:'提取截图文字，保留原文内容',offline:'使用本地识别提取图片中的文字',
 table:'识别表格，复制到 Excel 或导出数据',
 qr:'读取图片中的二维码和条码',entities:'提取邮箱与链接，直接复制或打开',
 translate:'在原文位置翻译，结合图片对照阅读',
 annotate:'按要求添加圈画、箭头与文字说明',detect:'识别图片中的物体并标出位置',
 region:'从已有截图中增加一个引用区域',crop:'裁剪图片，保留指定区域',
 highlight:'高亮指定文字，让重点更醒目',mosaic:'遮盖指定文字，隐藏敏感内容',
 heal:'移除指定文字，修补图片背景',lift:'提取指定内容，生成透明图层',
}
const labels:Record<ImageToolName,[string,string,string]>={
 ocr:['提取文字','ocr','识别与提取'],offline:['离线文字识别','offline','识别与提取'],
 table:['表格提取','table','识别与提取'],
 qr:['二维码与条码','qr','识别与提取'],entities:['邮箱与链接','entity','识别与提取'],
 translate:['原位翻译','translate','理解与标注'],
 annotate:['AI 标注','annotate','理解与标注'],detect:['物体识别','detect','理解与标注'],
 region:['增加截图区域','images','图片编辑'],crop:['裁剪图片','crop','图片编辑'],
 highlight:['高亮文字','highlight','图片编辑'],mosaic:['文字打码','mosaic','图片编辑'],
 heal:['涂抹消除','heal','图片编辑'],lift:['无痕提取','lift','图片编辑'],
}

export function isImageTool(name:string):name is ImageToolName{return Object.hasOwn(labels,name)}

export function toolCommands(catalog:ImageToolCatalog):ImageToolCommand[]{
 if(!Array.isArray(catalog.tools))throw new Error('功能列表暂不可用，请重试')
 const groups=['识别与提取','理解与标注','图片编辑']
 return catalog.tools.flatMap(({function:tool})=>{
  if(!isImageTool(tool.name))return []
  const name=tool.name as ImageToolName,[label,icon,group]=labels[name]
  return [{name,label,icon,group,description:tool.description,summary:summaries[name],example:examples[name],parameters:tool.parameters,required:Array.isArray(tool.parameters.required)?tool.parameters.required as string[]:[]}]
 }).sort((a,b)=>groups.indexOf(a.group)-groups.indexOf(b.group))
}

export function slashQuery(text:string,caret:number){
 const match=/(?:^|\s)[/／]([^\s/／]*)$/.exec(text.slice(0,caret))
 return match?{query:match[1]!,start:caret-match[1]!.length-1,end:caret}:undefined
}

export function filterToolCommands(tools:ImageToolCommand[],query:string){
 const words=query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean)
 return tools.filter(tool=>words.every(word=>(tool.label+' '+tool.name+' '+tool.description+' '+tool.group).toLocaleLowerCase().includes(word)))
}

export function buildToolCall(tool:ImageToolCommand,prompt:string,targetText:string,bboxText:string,language:string):ImageToolCall{
 const args:ImageToolCall['arguments']={}
 if(prompt.trim())args.prompt=prompt.trim()
 if(tool.name==='translate')args.language=language
 if(tool.required.includes('targetText')){
  if(!targetText.trim())throw new Error('请填写要处理的截图原文')
  args.targetText=targetText.trim()
 }
 if(tool.required.includes('bbox')){
  const normalized=bboxText.trim().replace(/^[\[（(]\s*|\s*[\]）)]$/g,'').replace(/\s*[,，]\s*/g,',')
  const values=normalized.split(/[,\s]+/).map(Number)
  if(!normalized||/(^,|,,|,$)/.test(normalized)||values.length!==4||values.some(n=>!Number.isFinite(n))||values[0]!<0||values[1]!<0||values[2]!<=values[0]!||values[3]!<=values[1]!)throw new Error('请填写有效区域：左、上、右、下，例如 20, 40, 320, 180')
  args.bbox=values
 }
 return {name:tool.name,arguments:args}
}
