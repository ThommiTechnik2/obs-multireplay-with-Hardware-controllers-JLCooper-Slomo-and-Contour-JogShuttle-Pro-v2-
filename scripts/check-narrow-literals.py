#!/usr/bin/env python3
"""obs-multireplay - no non-ASCII byte may travel through a narrow literal that
Qt reads as Latin-1.

Why this is a script and not a habit: QString::asprintf() copies the literal
text of its format string one byte per character, as Latin-1. The UTF-8 bytes
of the multiplication sign (0xC3 0x97) arrived on the speed label as U+00C3
plus a control character (U+0097) - in four places at once, because the first
one was copied. QStringLiteral() and QString(const char *) are fine (they
decode UTF-8); only the printf family and the Latin-1 constructors are not.
Nothing about the bug is visible in the source and the compiler cannot tell:
it is a valid string either way.

Flagged, in src/: the argument list of QString::asprintf / vasprintf / sprintf
and of QString::fromLatin1 / QLatin1String / QLatin1Char when it holds a byte
>= 0x80, written raw or as a hex or octal escape. The fix is to format the
number and append QChar(0x00D7), or to use QStringLiteral / QString::fromUtf8.

    python3 scripts/check-narrow-literals.py            check src/
    python3 scripts/check-narrow-literals.py --self-test

Exit status 1 on any hit, so this sits in CI.
"""
import re
import sys
from pathlib import Path

BS = chr(92)  # a backslash, spelled so no layer of quoting can eat it

CALL = re.compile(
    r"(?:QString::(?:v?asprintf|sprintf)|fromLatin1|QLatin1(?:String|Char))\s*\("
)
# hex escape >= 0x80, or a 3-digit octal escape >= 0200
ESCAPE = re.compile(
    re.escape(BS) + "x[89a-fA-F][0-9a-fA-F]|" + re.escape(BS) + "[23][0-7][0-7]"
)


def argument_list(text: str, open_paren: int) -> str:
    """The text between the parenthesis at open_paren and its match."""
    depth, i, quote = 0, open_paren, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == BS:
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1 : i]
        i += 1
    return text[open_paren + 1 :]


def scan(text: str):
    """Yield (line, snippet) for every offending call in text."""
    for m in CALL.finditer(text):
        args = argument_list(text, m.end() - 1)
        if ESCAPE.search(args) or any(ord(ch) > 0x7F for ch in args):
            line = text.count("\n", 0, m.start()) + 1
            call = text[m.start() : m.end() + len(args) + 1]
            yield line, " ".join(call.split())[:110]


def self_test() -> int:
    mul = chr(0xD7)
    bad = [
        'QString::asprintf("%.2f' + BS + "xc3" + BS + 'x97", v)',
        'QString::asprintf(\n\t"%.2f' + BS + "xc3" + BS + 'x97",\n v)',
        'QString::asprintf("%.2f' + mul + '", v)',
        'QString::fromLatin1("' + BS + "303" + BS + '227")',
        "QLatin1Char('" + mul + "')",
    ]
    good = [
        "QString::number(v, 'f', 2) + QChar(0x00D7)",
        'QStringLiteral("1.00' + BS + "xc3" + BS + 'x97")',
        'QString("%1' + BS + "xc3" + BS + 'x97").arg(v)',
        'QString::asprintf("%02d:%02d", m, s)',
        # a Latin-1 call that merely sits next to a non-ASCII literal
        "a(QLatin1Char('0')); b(\"" + mul + '");',
        "QString::fromLatin1(role)",
    ]
    failures = [s for s in bad if not list(scan(s))]
    failures += [s for s in good if list(scan(s))]
    for s in failures:
        print("self-test failed on:", repr(s), file=sys.stderr)
    return 1 if failures else 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    root = Path(__file__).resolve().parent.parent
    hits = []
    for path in sorted((root / "src").rglob("*")):
        if path.suffix not in {".cpp", ".hpp", ".c", ".h"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line, snippet in scan(text):
            hits.append(f"{path.relative_to(root).as_posix()}:{line}: {snippet}")
    if hits:
        print(
            "Non-ASCII bytes in a narrow literal that Qt reads as Latin-1:",
            file=sys.stderr,
        )
        print("\n".join(hits), file=sys.stderr)
        print(
            "\nFormat the number and append QChar(0x00D7), or use QStringLiteral /\n"
            "QString::fromUtf8 for the text, instead of putting UTF-8 bytes here.",
            file=sys.stderr,
        )
        return 1
    print("No non-ASCII bytes in Latin-1 narrow literals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
