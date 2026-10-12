const dayFormat=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'})
const clockFormat=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'})
export function historyDay(value:string|number){return dayFormat.format(new Date(value))}
export function historyTime(value:string,now=Date.now()){
 const date=new Date(value);if(!Number.isFinite(date.getTime()))return ''
 const dateDay=historyDay(value),today=historyDay(now),age=Math.round((Date.parse(today+'T00:00:00Z')-Date.parse(dateDay+'T00:00:00Z'))/86400000)
 if(age===0)return clockFormat.format(date)
 if(age===1)return '昨天'
 if(age===2)return '前天'
 if(age>=3&&age<=7)return '7天内'
 return dateDay.slice(5)
}
