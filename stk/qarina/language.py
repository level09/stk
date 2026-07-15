"""Output-language selection for research reports."""

import re

_ARABIC_SCRIPT = re.compile(
    r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]"
)
_LANGUAGES = {"auto", "arabic", "english"}


def resolve_output_language(query: str, preference: str | None = "auto") -> str:
    """Resolve a user preference to the report language."""
    preference = (preference or "auto").lower()
    if preference not in _LANGUAGES:
        raise ValueError("Output language must be auto, arabic, or english")
    if preference != "auto":
        return preference
    return "arabic" if _ARABIC_SCRIPT.search(query) else "english"


def output_language_instruction(language: str) -> str:
    """Return the final-report language requirement for the research prompt."""
    if language == "arabic":
        return (
            "Write the entire final report in Arabic, including headings and prose. "
            "Keep source titles, direct quotations, and URLs in their original language."
        )
    if language == "english":
        return (
            "Write the entire final report in English, including headings and prose. "
            "Keep source titles, direct quotations, and URLs in their original language."
        )
    raise ValueError("Language must be arabic or english")
