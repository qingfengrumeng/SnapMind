"""Expose the existing memory plan to the single agent without a second store."""
from ..session_memory import CONTEXT, token_count


def memory_view():
    plan=CONTEXT.get()
    if not plan:return {'shortTermTurns':0,'hasSummary':False,'hasLongTermPreferences':False}
    return {'shortTermTurns':sum(m['role']=='user' for m in plan['history']),
            'hasSummary':bool(plan['summary']),'hasLongTermPreferences':bool(plan['memories'])}


def observation_budget(catalog_text,prompt,images):
    plan=CONTEXT.get()
    if not plan:return 8000
    policy=plan['policy']
    history=sum(token_count(str(m['content'])) for m in plan['history'])+token_count(plan['summary'])+token_count(plan['memories'])
    return max(1000,min(8000,policy['context_window_tokens']-policy['response_reserve_tokens']-history-token_count(catalog_text)-token_count(prompt)-images*policy['image_reserve_tokens']-4096))
