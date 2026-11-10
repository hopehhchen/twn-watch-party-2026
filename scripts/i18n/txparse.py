import re, json, sys
def parse_args(s, i):
    """s[i] is just after 'tx('; return (list of (start,end) arg spans, index after ')')."""
    args, depth, start, j = [], 0, i, i
    stack = []  # quote / template contexts
    while j < len(s):
        c = s[j]
        if stack:
            top = stack[-1]
            if top in ("'", '"'):
                if c == '\\': j += 2; continue
                if c == top: stack.pop()
            elif top == '`':
                if c == '\\': j += 2; continue
                if c == '`': stack.pop()
                elif c == '$' and s[j+1] == '{': stack.append('{'); j += 2; continue
            elif top == '{':
                if c in "'\"`": stack.append(c)
                elif c == '{': stack.append('{{')
                elif c == '}': stack.pop()
            elif top == '{{':
                if c in "'\"`": stack.append(c)
                elif c == '{': stack.append('{{')
                elif c == '}': stack.pop()
            j += 1; continue
        if c in "'\"`": stack.append(c)
        elif c in '([{': depth += 1
        elif c in ')]}':
            if depth == 0:
                args.append((start, j)); return args, j + 1
            depth -= 1
        elif c == ',' and depth == 0:
            args.append((start, j)); start = j + 1
        j += 1
    raise ValueError('unterminated')
def calls(s):
    out = []
    for m in re.finditer(r'(?<![A-Za-z0-9_$.])tx\(', s):
        if s[m.start()-9:m.start()] == 'function ' or s[m.start()-6:m.start()] == 'const ': continue
        try: args, end = parse_args(s, m.end())
        except Exception: continue
        out.append((m.start(), end, args))
    return out
if __name__ == '__main__':
    s = open(sys.argv[1]).read(); cs = calls(s); zh = []
    for st, en, args in cs:
        if len(args) >= 2: zh.append(s[args[1][0]:args[1][1]].strip())
    u = list(dict.fromkeys(zh)); print(len(cs), len(u))
    json.dump(u, open(sys.argv[2], 'w'), ensure_ascii=False, indent=0)
