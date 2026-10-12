import type {UsageMetrics} from './api'

// Missing cache detail follows the user's rule: zero cached, all input uncached.
export function usageTokens(row:UsageMetrics){
 const input=row.inputTokens??0,output=row.outputTokens??0
 const cached=Math.min(input,Math.max(0,row.cachedInputTokens??0))
 return {input,cached,uncached:input-cached,output,total:input+output}
}
