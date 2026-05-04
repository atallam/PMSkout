---
name: Unicode box-drawing chars break Python on this setup
description: Box-drawing chars (U+2500 family, em-dash) in Python source comments cause SyntaxError
type: feedback
---

Do NOT use box-drawing characters (─, ──, ═) or em-dashes (—) in Python source file comments or strings for the Skout project.

**Why:** The Linux Python 3.10 runtime on this VM mount combination treats certain UTF-8 multi-byte sequences inside source files as invalid, producing confusing SyntaxError messages like "'{' was never closed" even though the actual brace is fine.

**How to apply:** Use plain ASCII in all Python comments and docstrings:
- Replace ── with -- or ===
- Replace — with -- or (nothing)
- Replace bullet decorators (─) with plain hyphens
- Emojis in *string literals* (for UI display) are fine; emojis in comments are not
