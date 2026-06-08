from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser


POSITIVE_TERMS = {
    "achieved",
    "benefit",
    "benefited",
    "efficient",
    "favorable",
    "gain",
    "gains",
    "growth",
    "improved",
    "improvement",
    "increase",
    "increased",
    "increases",
    "profitability",
    "record",
    "resilient",
    "strong",
    "strength",
}

NEGATIVE_TERMS = {
    "adverse",
    "challenge",
    "challenging",
    "decline",
    "declined",
    "decrease",
    "decreased",
    "impairment",
    "loss",
    "losses",
    "negative",
    "pressure",
    "risk",
    "risks",
    "uncertain",
    "uncertainty",
    "weak",
    "weakness",
}

SUMMARY_TERMS = {
    "cash",
    "cost",
    "demand",
    "expense",
    "income",
    "liquidity",
    "margin",
    "net",
    "operating",
    "revenue",
    "sales",
}


@dataclass
class ManagementAnalysis:
    section_title: str
    text: str
    summary: str
    sentiment_label: str
    sentiment_score: float
    positive_terms: int
    negative_terms: int
    word_count: int


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "table"}:
            self._skip_depth += 1
        if tag in {"br", "div", "p", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "table"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"div", "p", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return clean_text(" ".join(self.parts))


def analyze_management_discussion(document_html: str, form: str) -> ManagementAnalysis | None:
    document_text = html_to_text(document_html)
    section_title, section_text = extract_management_discussion(document_text, form)
    if not section_text:
        return None
    summary = summarize_text(section_text)
    sentiment_label, sentiment_score, positive_terms, negative_terms = score_sentiment(section_text)
    return ManagementAnalysis(
        section_title=section_title,
        text=section_text,
        summary=summary,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        positive_terms=positive_terms,
        negative_terms=negative_terms,
        word_count=len(re.findall(r"[A-Za-z]+", section_text)),
    )


def html_to_text(document_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html.unescape(document_html))
    return parser.text()


def clean_text(text: str) -> str:
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_management_discussion(document_text: str, form: str) -> tuple[str, str]:
    mda_phrase = (
        r"(?:this\s+)?management[’'`]?s\s+discussion\s+and\s+analysis"
        r"(?:\s+of\s+financial\s+condition\s+and\s+results\s+of\s+operations)?"
    )
    if form.startswith("10-K"):
        title = "Item 7. Management's Discussion and Analysis"
        start_pattern = rf"\bitem\s+7[\.\s:-]+{mda_phrase}\b|{mda_phrase}\s+should\s+be\s+read"
        end_pattern = (
            r"\bitem\s+7a[\.\s:-]+|\bitem\s+8[\.\s:-]+|"
            r"quantitative\s+and\s+qualitative\s+disclosures\s+about\s+market\s+risk"
        )
    else:
        title = "Item 2. Management's Discussion and Analysis"
        start_pattern = rf"\bitem\s+2[\.\s:-]+{mda_phrase}\b|{mda_phrase}\s+provides"
        end_pattern = (
            r"\bitem\s+3[\.\s:-]+|\bitem\s+4[\.\s:-]+|"
            r"there\s+have\s+been\s+no\s+significant\s+changes\s+to\s+our\s+market\s+risks|"
            r"evaluation\s+of\s+disclosure\s+controls\s+and\s+procedures|"
            r"\bpart\s+ii[\.\s:-]+other\s+information"
        )

    candidates = []
    for start in re.finditer(start_pattern, document_text, flags=re.IGNORECASE):
        following = document_text[start.end() :]
        end_offset = None
        for end in re.finditer(end_pattern, following, flags=re.IGNORECASE):
            if end.start() > 1_500:
                end_offset = end.start()
                break
        end_idx = start.end() + end_offset if end_offset else min(len(document_text), start.end() + 120_000)
        section = clean_text(document_text[start.end() : end_idx])
        words = len(section.split())
        if words >= 80:
            candidates.append((words, section))
    if not candidates:
        return title, ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return title, candidates[0][1][:120_000]


def summarize_text(text: str, max_sentences: int = 3) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return ""
    scored = []
    for index, sentence in enumerate(sentences[:80]):
        tokens = [token.lower() for token in re.findall(r"[A-Za-z]+", sentence)]
        if len(tokens) < 8:
            continue
        score = sum(1 for token in tokens if token in SUMMARY_TERMS)
        score += min(3, len(re.findall(r"\$?\d+(?:\.\d+)?%?", sentence)))
        score += 1 if index < 8 else 0
        scored.append((score, index, sentence))
    if not scored:
        return sentences[0][:900]
    chosen = sorted(sorted(scored, reverse=True)[:max_sentences], key=lambda item: item[1])
    return clean_text(" ".join(sentence for _, _, sentence in chosen))[:1200]


def split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z$])", clean_text(text))
    return [piece.strip() for piece in pieces if piece.strip()]


def score_sentiment(text: str) -> tuple[str, float, int, int]:
    tokens = [token.lower() for token in re.findall(r"[A-Za-z]+", text)]
    if not tokens:
        return "neutral", 0.0, 0, 0
    positive = sum(1 for token in tokens if token in POSITIVE_TERMS)
    negative = sum(1 for token in tokens if token in NEGATIVE_TERMS)
    score = (positive - negative) / max(1, positive + negative)
    if score >= 0.15:
        label = "positive"
    elif score <= -0.15:
        label = "negative"
    else:
        label = "neutral"
    return label, round(score, 3), positive, negative
