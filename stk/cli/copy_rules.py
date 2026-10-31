"""Copy rules for stk smoke: visible text that renders fine but reads badly."""

import re
from collections import Counter

# innerText already leaves out script, style, hidden elements and input values;
# code and pre are shown on purpose, so their text is removed too.
VISIBLE_TEXT_JS = """() => {
  let text = document.body.innerText;
  for (const el of document.body.querySelectorAll('pre, code:not(pre code)')) {
    const shown = el.innerText;
    if (shown) text = text.replace(shown, ' ');
  }
  return text;
}"""

# Visible texts of sibling elements that share a tag and classes: rows of a list.
ROWS_JS = """() => {
  const shown = el => el.getClientRects().length > 0;
  const sig = k => k.tagName + '.' + [...k.classList]
    .filter(c => !/active|selected|hover|focus|open|current/.test(c)).sort().join('.');
  const out = [];
  for (const p of document.querySelectorAll('body *')) {
    const kids = [...p.children].filter(shown);
    if (kids.length < 3) continue;
    const groups = {};
    for (const k of kids) (groups[sig(k)] ||= []).push(k);
    for (const g of Object.values(groups))
      if (g.length >= 3) out.push(g.map(k => k.innerText.trim().replace(/\\s+/g, ' ')));
  }
  return out;
}"""

UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
HEX = re.compile(r"[0-9a-f]{6,}", re.I)
# A hash that is the deliberate content is labelled as one.
HASH_LABEL = re.compile(r"(?:sha-?256|sha|md5|hash|digest|fingerprint)\W{0,3}$", re.I)
SNAKE = re.compile(r"(?<![\w./@-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![\w@-]|\.\w)")
SCORE = re.compile(
    r"\b(?:score|similarity|confidence|distance|cosine)\b\s*[:=]?\s*-?\d*\.\d+", re.I
)
ONE = re.compile(r"(?<![\d.,:/-])\b1[ \t]+([A-Za-z]+s)\b")
# Words ending in s after a 1 that are not plurals: "1 is", "1 status".
NOT_PLURAL = {
    "is",
    "was",
    "has",
    "this",
    "its",
    "news",
    "status",
    "access",
    "address",
    "process",
    "class",
    "basis",
    "plus",
    "minus",
    "always",
    "across",
    "less",
    "yes",
    "ms",
}
LITERALS = re.compile(r"\bundefined\b|\bnull\b|\bNaN\b|\[object Object\]")


def _around(text, match, pad=30):
    """The match with up to `pad` characters either side, within its line."""
    start, end = match.span()
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end < 0 else line_end
    return text[max(line_start, start - pad) : min(line_end, end + pad)].strip()


def uuid(text):
    return [_around(text, m) for m in UUID.finditer(text)]


def hex_id(text):
    """6+ hex characters with at least two digits and a letter, alone or glued to a
    word: 'Request 1fbaac41'. Uuids are their own rule."""
    text = UUID.sub(" ", text)
    out = []
    for m in HEX.finditer(text):
        token = m.group()
        if sum(c.isdigit() for c in token) < 2 or token.isdigit():
            continue
        if HASH_LABEL.search(text[max(0, m.start() - 20) : m.start()]):
            continue
        out.append(_around(text, m))
    return out


def snake_case(text):
    return [_around(text, m) for m in SNAKE.finditer(text)]


def raw_score(text):
    return [_around(text, m) for m in SCORE.finditer(text)]


def one_plural(text):
    return [
        _around(text, m)
        for m in ONE.finditer(text)
        if m.group(1).lower() not in NOT_PLURAL
        and not m.group(1).lower().endswith(("ss", "us", "is"))
    ]


def broken_value(text):
    return [_around(text, m) for m in LITERALS.finditer(text)]


def repeated_rows(lists, at_least=3):
    """The same row 3+ times in one list is a duplicate the reader skims past."""
    out = []
    for rows in lists:
        rows = [r for r in rows if len(r) > 3 and re.search(r"[^\W\d_]", r)]
        out += [f"{r[:80]} (x{n})" for r, n in Counter(rows).items() if n >= at_least]
    return out


TEXT_RULES = {
    "uuid": uuid,
    "hex-id": hex_id,
    "snake-case": snake_case,
    "raw-score": raw_score,
    "one-plural": one_plural,
    "broken-value": broken_value,
}


def copy_findings(text, rows=(), allow=()):
    """Rule findings on a page's visible text and rows, minus snippets matching an
    `allow` regex."""
    found = [(rule, s) for rule, fn in TEXT_RULES.items() for s in fn(text)]
    found += [("repeated-row", s) for s in repeated_rows(rows)]
    return [
        {"rule": rule, "text": snippet}
        for rule, snippet in dict.fromkeys(found)
        if not any(re.search(pattern, snippet) for pattern in allow)
    ]
