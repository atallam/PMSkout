---
name: File write truncation on Windows NTFS mount
description: Edit/Write tools truncate large content when writing to Windows paths via the VM mount
type: feedback
---

Never use the Edit or Write tools for large file sections (>60 lines of new content) when the target is on the Windows NTFS mount (/sessions/.../mnt/skout/).

**Why:** The Windows NTFS filesystem accessed through the VM mount silently truncates large writes. Files over ~300 lines of new content get cut off mid-line with no error.

**How to apply:** When adding large blocks of new code to an existing file:
1. Use `python3 - << 'PYEOF' ... PYEOF` (heredoc) to write complete files from bash
2. Use `cat >> file << 'EOF'` to safely append tails
3. After any large Edit, always verify with `tail -5 file` and `wc -l file`
4. If a file is truncated, trim the broken last line with python3 and re-append the missing content
