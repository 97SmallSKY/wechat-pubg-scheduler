"""Four-character idiom validation and exact-character chaining."""

from collections import defaultdict
from pathlib import Path

WORDS = frozenset(Path(__file__).with_name("idioms.txt").read_text(encoding="utf-8").splitlines())
BY_FIRST = defaultdict(list)
for word in sorted(WORDS):
    BY_FIRST[word[0]].append(word)


def chain(body):
    previous, candidate, used = body.get("previous"), body.get("candidate"), body.get("used", [])
    if not isinstance(previous, str) or previous not in WORDS:
        raise ValueError("previous 需要词库中的四字成语")
    if candidate is not None and (not isinstance(candidate, str) or len(candidate) != 4):
        raise ValueError("candidate 需要四个字")
    if not isinstance(used, list) or len(used) > 500 or any(not isinstance(x, str) or len(x) != 4 for x in used):
        raise ValueError("used 需要四字成语数组，最多 500 项")
    excluded = set(used) | {previous}
    valid = None if candidate is None else candidate in WORDS and candidate[0] == previous[-1] and candidate not in excluded
    options = [word for word in BY_FIRST[previous[-1]] if word not in excluded][:5]
    return {"valid": valid, "next": options}
