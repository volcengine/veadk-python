"""Bounded original paragraph context for verified retrieval spans.

This function supplies offsets only. It neither searches another source nor
parses citations in untrusted text. The caller validates current source access
and measures the final serialized payload before including the excerpt.
"""

MAX_CONTEXT_BYTES = 512


def context_window(text: str, start: int, end: int) -> tuple[int, int]:
    """Complete the touched source lines if at most 512 UTF-8 bytes are added.

    Search at most 512 characters per side; UTF-8 byte validation can only
    shrink that allowance. A long line without nearby boundaries stays intact
    as a ranked span instead of allocating an unbounded enclosing paragraph.
    No text is synthesized, and all positions are Unicode character offsets.
    """
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(text)
    ):
        raise ValueError("invalid_context_range")
    left, right = start, end
    if start and text[start - 1] != "\n":
        boundary = text.rfind("\n", max(0, start - MAX_CONTEXT_BYTES - 1), start)
        if boundary >= 0:
            left = boundary + 1
        elif start <= MAX_CONTEXT_BYTES:
            left = 0
    if end < len(text) and text[end - 1] != "\n":
        boundary = text.find("\n", end, min(len(text), end + MAX_CONTEXT_BYTES + 1))
        if boundary >= 0:
            right = boundary
        elif len(text) - end <= MAX_CONTEXT_BYTES:
            right = len(text)
    if len((text[left:start] + text[end:right]).encode("utf-8")) > MAX_CONTEXT_BYTES:
        return start, end
    return left, right
