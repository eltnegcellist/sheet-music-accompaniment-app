"""Merge an optional user-supplied MusicXML with the Audiveris output.

Strategy: when the user uploads an authoritative MusicXML alongside the PDF we
trust it for note data (Audiveris OMR is best-effort) but keep the Audiveris
result for layout. The current MVP simply prefers user XML wholesale; richer
merging (e.g. matching parts by name) can be added later.
"""

from __future__ import annotations


def merge_layout_with_musicxml(
    omr_xml: str,
    user_xml: str | None,
    warnings: list[str],
) -> str:
    if user_xml is None:
        return omr_xml

    if "<score-partwise" not in user_xml and "<score-timewise" not in user_xml:
        warnings.append("Uploaded MusicXML did not look valid; using OMR output.")
        return omr_xml

    # MVP: trust user XML for notes. Layout still comes from Audiveris via the
    # measures list returned separately.
    return user_xml
