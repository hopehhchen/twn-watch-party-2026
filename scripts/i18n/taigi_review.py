#!/usr/bin/env python3
"""Write docs/taigi-review.md: every 華語 → 台語 pair on the two pages, for native-speaker review.

  python3 scripts/i18n/taigi_review.py

Interface strings come from the tx(en, zh, tw) calls in the page templates; long text from the
data-l="zh" / data-l="tw" blocks. Placeholders such as ${...} are page values (numbers, names).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import txparse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


def strip(src):
    src = src.strip()
    if src[:1] in "'`\"" and src[-1:] == src[:1]:
        src = src[1:-1]
    return re.sub(r"\$\{[^{}]*(\{[^{}]*\}[^{}]*)*\}", "…", src)


def blocks(s, lang):
    return [re.sub(r"<[^>]+>", "", m.group(1)).strip() for m in re.finditer(rf'<(?:p|h2|span|li|div|ul)[^>]*data-l="{lang}"[^>]*>(.*?)</(?:p|h2|span|div|ul)>', s, re.S)]


def main():
    out = ["# 台語 translation: review list", "",
           "The 台語 text on the site is a first draft by Claude (MOE 臺灣台語常用詞辭典 recommended characters, 台羅 where needed). "
           "It hasn't been reviewed by a native speaker. Columns: 華語 source, 台語 draft. \"…\" is a value the page fills in.", ""]
    for name in ("live-template.html", "index-template.html"):
        s = (ROOT / "site" / name).read_text()
        out += [f"## {name}: interface", "", "| 華語 | 台語 |", "|---|---|"]
        seen = set()
        for _, _, args in txparse.calls(s):
            if len(args) == 3:
                zh, tw = strip(s[args[1][0]:args[1][1]]), strip(s[args[2][0]:args[2][1]])
                if (zh, tw) not in seen:
                    seen.add((zh, tw))
                    out.append(f"| {zh.replace('|', '¦')} | {tw.replace('|', '¦')} |")
        out += ["", f"## {name}: long text", ""]
        for zh, tw in zip(blocks(s, "zh"), blocks(s, "tw")):
            out += ["**華語**", "", " ".join(zh.split()), "", "**台語**", "", " ".join(tw.split()), "", "---", ""]
    (ROOT / "docs" / "taigi-review.md").write_text("\n".join(out) + "\n")
    print("docs/taigi-review.md", len(out), "lines")


if __name__ == "__main__":
    main()
