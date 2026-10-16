"""Conservative common cardinal normalization; no dates, money rounding or homophones."""
import re

PATTERN = re.compile(r'[零〇一二两三四五六七八九十百千万亿点]+')
DIGITS = dict(zip('零一二三四五六七八九', range(10))) | {'〇':0, '两':2}
UNITS = {'十':10,'百':100,'千':1000,'万':10000,'亿':100000000}


def cardinal(value):
    if len(value) < 2:
        return value  # Single characters in prose are ambiguous.
    if '点' in value:
        if value.count('点') != 1:
            return value
        left,right=value.split('点')
        if not left or not right or any(c not in DIGITS for c in right):
            return value
        return cardinal(left) + '.' + ''.join(str(DIGITS[c]) for c in right) if len(left)>1 else str(DIGITS.get(left,left))+'.'+''.join(str(DIGITS[c]) for c in right)
    if all(c in DIGITS for c in value):
        return ''.join(str(DIGITS[c]) for c in value) if len(value) >= 3 else value
    if '万' in value or '亿' in value:
        return value
    total=section=number=0
    for char in value:
        if char in DIGITS:
            number=DIGITS[char]
        elif char in UNITS:
            unit=UNITS[char]
            if unit < 10000:
                section+=(number or 1)*unit
            else:
                total+=(section+number)*unit
                section=0
            number=0
        else:
            return value
    answer = total+section+number
    number = answer
    if number > 9999:
        return value
    # Reject colloquial / malformed readings such as 一百二, 十十 and 万一.
    digits = '零一二三四五六七八九'
    canonical = ''
    zero = False
    for unit, suffix in ((1000,'千'),(100,'百'),(10,'十'),(1,'')):
        digit, number = divmod(number, unit)
        if digit:
            if zero:
                canonical += '零'
            canonical += digits[digit] + suffix
            zero = False
        elif canonical and number:
            zero = True
    if canonical.startswith('一十'):
        canonical = canonical[1:]
    return str(answer) if value.replace('两','二') == canonical else value


def normalize(value):
    return PATTERN.sub(lambda m:cardinal(m[0]), value)


def normalize_timed(words):
    result=[]
    index=0
    while index<len(words):
        end=index
        while end<len(words) and len(words[end]['text'])==1 and words[end]['text'] in '零〇一二两三四五六七八九十百千万亿点':
            end+=1
        if end>index:
            selected=words[index:end]
            text=cardinal(''.join(w['text'] for w in selected))
            if text != ''.join(w['text'] for w in selected):
                result.append(dict(text=text,start=selected[0]['start'],end=selected[-1]['end'],probability=min(w['probability'] for w in selected)))
            else:
                result.extend(selected)
            index=end
        else:
            result.append(words[index]);index+=1
    return result
