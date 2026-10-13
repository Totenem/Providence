"""Literal retrieval evidence, including separator-tolerant class/reference codes."""

from pathlib import Path
import re

_CODE_TOKENS = re.compile(
    r'(?<![a-zA-Z0-9])(?:\d+[-_][a-zA-Z]+(?:[-_]?\d+)?'
    r'|[a-zA-Z]+[-_]\d+|\d+[a-zA-Z]+[-_]\d+|[a-zA-Z0-9]+)(?![a-zA-Z0-9])'
)


def normalize_identifiers(query):
    def normalized(match):
        word = match.group()
        if re.search(r'[a-zA-Z]', word) and re.search(r'\d', word):
            return word.replace('-', '').replace('_', '')
        return word
    return _CODE_TOKENS.sub(normalized, query)


def identifiers(query):
    return list(dict.fromkeys(
        word.casefold() for word in re.findall(r'[a-zA-Z0-9]+', normalize_identifiers(query))
        if re.search(r'[a-zA-Z]', word) and re.search(r'\d', word)
    ))


def identifier_pattern(code):
    parts = re.findall(r'[a-z]+|\d+', code.casefold())
    return re.compile(
        r'(?<![a-z0-9])' + r'[\s._-]*'.join(map(re.escape, parts))
        + r'(?![a-z0-9])', re.IGNORECASE,
    )


def identifier_expression(code):
    """FTS alternatives for 1CS1, 1-CS1, 1CS-1 and 1-CS-1."""
    parts = re.findall(r'[a-z]+|\d+', code.casefold())
    if len(parts) > 6:
        return '"' + code + '"'
    alternatives = []
    for mask in range(1 << (len(parts) - 1)):
        groups = [parts[0]]
        for index, part in enumerate(parts[1:]):
            if mask & (1 << index):
                groups.append(part)
            else:
                groups[-1] += part
        alternatives.append('(' + ' AND '.join('"' + group + '"' for group in groups) + ')')
    return '(' + ' OR '.join(alternatives) + ')'


def word_found(word, text):
    if word in identifiers(word):
        return bool(identifier_pattern(word).search(text))
    return word.casefold() in re.findall(r'\w+', text.casefold().replace('_', ' '))


def explain(path, text, words, query, reason):
    """Describe observed matches, never a generated rationale or confidence score."""
    filename = Path(path).name
    folder = str(Path(path).parent)
    locations = [('Filename', filename), ('Folder', folder), ('Passage', text)]
    details = []
    matched = set()
    for label, value in locations:
        hits = [word for word in words if word_found(word, value)]
        if hits:
            details.append(label + ': ' + ', '.join(hits))
            matched.update(hits)
    codes = set(identifiers(query))
    topics = [word for word in words if word not in codes]
    if topics and not any(word in matched for word in topics):
        reason = 'Meaning'
        details.append('Topic words not found; suggested by local meaning')
    elif words and all(word_found(word, filename) for word in words):
        reason = 'Filename'
    originals = re.findall(r'\w+', normalize_identifiers(query).casefold())
    replacements = [word for word in words if word not in originals]
    used_replacements = [word for word in replacements if word in matched]
    if used_replacements:
        reason = 'Similar words' if reason not in {'Filename', 'Path'} else reason
        details.append('Spelling fallback: ' + ', '.join(used_replacements))
    elif reason == 'Similar words':
        reason = 'Text'
    if not details:
        details.append('Suggested by local meaning; no literal query words found')
    other_codes = [code for code in codes if code not in matched]
    if other_codes:
        details.append('Required code elsewhere in indexed text: ' + ', '.join(sorted(other_codes)))
    missing = [word for word in topics if word not in matched]
    if missing and len(missing) != len(topics):
        details.append('Other query words not found: ' + ', '.join(missing))
    return reason, '. '.join(details) + '.', matched
