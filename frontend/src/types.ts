export type Scenario = 'formula' | 'table' | 'error' | 'custom'
export interface Asset { id: string; name: string; data: string; width: number; height: number; scenario: Scenario }
export interface ImageMessageResult {assetId?:string;tables?:import('./api').ExtractedTable[];codes?:import('./api').ImageUtility['codes'];entities?:import('./api').ImageUtility['entities'];note?:import('./api').ImageNote}
export interface TextAttachment {id:string;name:string;content:string}
export interface VoiceMessage {data:string;duration:number;waveform:number[]}
export interface Message { id: string; role: 'user' | 'assistant'; text: string; voice?:VoiceMessage; action?: string; sources?: string[]; kind?: 'formula' | 'table' | 'text'; demo?: boolean;imageResult?:ImageMessageResult;textAttachments?:TextAttachment[];paused?:boolean;failed?:boolean;images?:Asset[];imageOutput?:import('./api').ImageConversationResult;imageRequest?:{action?:import('./api').ImageAction;question:string;toolCall?:import('./api').ImageToolCall;userId:string;context?:Parameters<typeof import('./api').api.callImageTool>[1]} }
export interface DataRow { label: string; value: number }
export interface ImageConversationState {version:1;selectedId:string|null;pictures:{assetId:string;annotations:import('./api').AiExisting[];rendered?:Asset}[];textAttachments?:TextAttachment[];titleGenerated?:boolean}
export interface VoiceCallRecord {startedAt:string;endedAt?:string;startMessageId:string;endMessageId?:string}
export type ImageHistoryItem=Pick<Session,'id'|'title'|'createdAt'|'updatedAt'|'pinned'>&{titleGenerated?:boolean;hasVoiceCall?:boolean}
export interface Session { id: string; title: string; scenario: Scenario; assets: Asset[]; messages: Message[]; formula: string; rows: DataRow[]; createdAt: string; updatedAt: string; pinned: boolean;imageConversation?:ImageConversationState;voiceCall?:VoiceCallRecord }
