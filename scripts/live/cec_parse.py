#!/usr/bin/env python3
"""Parse the CEC count site's pages (計票資訊查詢網站): candidate-vote pages and turnout pages.

  parse_count(html)   -> {"title", "sent", "total", "rows": [{"no", "name", "sex", "votes", "party", "mark"}], "updated",
                          "seats", "women"}   (seats and reserved women's seats: council pages)
  parse_turnout(html) -> {"title", "rows": [{"area", "E", "C", "A", "invalid"}], "updated"}

The pages are HTML fragments. Their markup changed between 2022 (class-based) and 2025 (id-based), so the
parser reads tables by their header labels and the station count by its text ("已送/應送: 137/137" in 2022,
"已送投票所數/總投票所數: 17832/17832" in 2025), not by class names. Fixtures: tests/fixtures/cec/.
"""
import html as H
import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _text(s):
    return _WS.sub(" ", H.unescape(_TAG.sub(" ", s))).replace("\xa0", " ").strip()


def _num(s):
    s = _text(s).replace(",", "").replace("%", "")
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def _tables(page):
    """Every <table>: (header labels, [row cells as raw html])."""
    out = []
    for t in re.finditer(r"<table\b[^>]*>(.*?)</table>", page, re.S | re.I):
        body = t.group(1)
        heads = [_text(h) for h in re.findall(r"<th\b[^>]*>(.*?)</th>", body, re.S | re.I)]
        rows = []
        for tr in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", body, re.S | re.I):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", tr.group(1), re.S | re.I)
            if cells:
                rows.append(cells)
        out.append((heads, rows))
    return out


def _title(page):
    m = re.search(r"<b>(.*?)</b>", page, re.S)
    return _text(m.group(1)) if m else ""


def _updated(page):
    m = re.search(r"資料更新時間[:：]\s*([0-9/]+\s+[0-9:]+)", _text(page))
    return m.group(1) if m else None


def _sent(page):
    t = _text(page)
    m = re.search(r"已送[^0-9]{0,24}?(\d+)\s*/\s*(\d+)", t)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def parse_count(page):
    sent, total = _sent(page)
    rows = []
    for heads, trs in _tables(page):
        if "號次" not in heads or "得票數" not in heads:
            continue
        ix = {h: i for i, h in enumerate(heads)}
        for cells in trs:
            if len(cells) < len(heads):
                continue
            no = _num(cells[ix["號次"]])
            if not isinstance(no, int):
                continue
            rows.append({"no": no, "name": _text(cells[ix["姓名"]]) if "姓名" in ix else "",
                         "sex": {"男": 1, "女": 2}.get(_text(cells[ix["性別"]]), 0) if "性別" in ix else 0,
                         "votes": _num(cells[ix["得票數"]]) or 0,
                         "party": _text(cells[ix["推薦之政黨"]]) if "推薦之政黨" in ix else "",
                         "mark": _text(cells[ix["註記"]]) if "註記" in ix else ""})
    if not rows:
        raise ValueError("no candidate table on the page")
    if sent is None:
        raise ValueError("no station count (已送/應送) on the page")
    t = _text(page)
    seats = re.search(r"應選人數[:：]\s*(\d+)", t)
    women = re.search(r"婦女應當選名額[:：]\s*(\d+)", t)
    return {"title": _title(page), "sent": sent, "total": total, "rows": rows, "updated": _updated(page),
            "seats": int(seats.group(1)) if seats else None, "women": int(women.group(1)) if women else 0}


def parse_turnout(page):
    rows = []
    for heads, trs in _tables(page):
        if "選舉人數" not in heads or "投票數" not in heads:
            continue
        ix = {h: i for i, h in enumerate(heads)}
        area_col = 0
        for cells in trs:
            if len(cells) < len(heads):
                continue
            rows.append({"area": _text(cells[area_col]), "E": _num(cells[ix["選舉人數"]]), "C": _num(cells[ix["投票數"]]),
                         "A": _num(cells[ix["有效票數"]]) if "有效票數" in ix else None,
                         "invalid": _num(cells[ix["無效票數"]]) if "無效票數" in ix else None})
    if not rows:
        raise ValueError("no turnout table on the page")
    return {"title": _title(page), "rows": rows, "updated": _updated(page)}


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    for f in sys.argv[1:]:
        s = Path(f).read_text()
        kind = parse_turnout if Path(f).name.startswith(("SC", "ST")) else parse_count
        print(f, json.dumps(kind(s), ensure_ascii=False)[:400])
