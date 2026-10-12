"""Reject empty/filler-only automatic call turns, without altering dictation."""
import re


def is_filler_transcript(value):
    text=''.join(character for character in value if character.isalnum()).lower()
    return not text or bool(re.fullmatch(r'[嗯呃啊哦唔]+|(?:u+h+|u+m+|h+m+)+',text))
