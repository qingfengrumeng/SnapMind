export type FollowupExample={label:string;query:string;icon:string;detail:string;requiresUndo?:boolean}

/** Prepare examples from the user's question immediately, without a model round trip. */
export function followupExamples(question:string):FollowupExample[]{
 const undo={label:'撤销这次操作',query:'请撤销刚才对这张截图的操作。',icon:'undo',detail:'恢复到上一步',requiresUndo:true}
 const extract={label:'提取截图文字',query:'请提取当前截图中的全部文字，保留原有换行。',icon:'ocr',detail:'保留文字与换行'}
 const explain={label:'解释截图内容',query:'请解释当前截图的内容，并整理成简洁要点。',icon:'chat',detail:'整理内容与重点'}
 const translate={label:'原位翻译成英文',query:'请把当前截图中的文字原位翻译成英文。',icon:'translate',detail:'在原位置展示译文'}
 if(/翻译|translate/i.test(question))return [undo,{...extract,label:'提取翻译后的文字'},explain]
 if(/涂抹|消除|擦除|擦掉|抹掉|马赛克|打码|遮盖|模糊|裁剪|高亮|圈出|标注|画.*(?:圈|框|箭头)/i.test(question))return [undo,extract,explain]
 if(/代码|code|程序|报错|bug/i.test(question))return [{label:'逐行解释代码',query:'请逐行解释刚才截图中的代码，说明关键逻辑。',icon:'code',detail:'理解关键逻辑'},{label:'检查潜在问题',query:'请检查刚才代码中可能的问题，只根据截图可见内容分析。',icon:'search',detail:'检查可见代码'},{label:'整理修改建议',query:'请根据刚才的问题整理具体的修改建议。',icon:'file',detail:'整理后续步骤'}]
 if(/(?:提取|识别|转录).*(?:文字|文本)|\bocr\b/i.test(question))return [translate,{label:'整理文字要点',query:'请根据刚才提取的文字整理简洁要点。',icon:'file',detail:'快速归纳关键信息'},{label:'提取截图表格',query:'请提取当前截图中的表格，方便复制到 Excel。',icon:'table',detail:'转成可复制的表格'}]
 return [extract,translate,explain]
}
