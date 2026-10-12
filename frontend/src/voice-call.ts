import type {AiTurn,ImageConversationResult} from './api'

export const spiritGreeting='嗨，我是 SnapMind 里的 AI 精灵——小洁，截图、识字、翻译、标注都可以交给我～需要我帮你做点什么？'
export interface VoiceCallRequest{prompt:string;history:AiTurn[];sessionId:string;turnId:string}
export type VoiceCallExecutor=(request:VoiceCallRequest,signal:AbortSignal,onChunk?:(text:string)=>void)=>Promise<ImageConversationResult>

// Speech should not read Markdown syntax, source URLs, or long fenced code blocks.
export function speechText(text:string){return text.replace(/```[\s\S]*?```/g,'这段代码已显示在对话中。').replace(/!\[[^\]]*\]\([^)]*\)/g,'').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/https?:\/\/\S+/g,'链接已显示在对话中。').replace(/^[\s]*#{1,6}\s+/gm,'').replace(/[*_`~]/g,'').trim()}
