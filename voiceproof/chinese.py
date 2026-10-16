"""Normalize written variants locally; retain the original transcript in the report."""
from functools import lru_cache

@lru_cache(maxsize=1)
def converter():
    from opencc import OpenCC
    return OpenCC('t2s')


def simplify(value):
    return converter().convert(value)


def simplify_timed(words):
    source=''.join(w['text'] for w in words)
    target=simplify(source)
    if len(source)!=len(target):
        raise ValueError('Cannot preserve timestamp mapping for this written variant')
    offset=0
    for word in words:
        length=len(word['text'])
        word['text']=target[offset:offset+length]
        offset+=length
    return words
