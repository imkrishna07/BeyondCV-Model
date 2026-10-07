"""Normalize reported achievements and classify explicitly stated outcomes."""

import re

from app.analyzers.achievements.scoring import SCORE_METHOD, score_achievements
from app.schemas.achievements import (
    AchievementAnalysisRequest,
    AchievementAnalysisResponse,
    AchievementEvidence,
    AchievementEvidenceItem,
    RecognitionLevel,
)


_WINNER = re.compile(r"\b(winner|won|champion|gold medal|first place|1st place|1st|first|award|scholarship|honoree|laureate)\b", re.I)
_FINALIST = re.compile(r"\b(finalist|final round|top\s*\d+\s*finalists?)\b", re.I)
_PARTICIPATION = re.compile(r"\b(participant|participated|participation|entrant)\b", re.I)
_RANKED = re.compile(r"\b(second place|third place|runner[- ]?up|silver medal|bronze medal|\d+(?:st|nd|rd|th)(?:\s+place)?|rank(?:ed)?\s*#?\s*\d+|top\s*\d+)\b", re.I)


def _recognition(rank: str | None, name: str) -> RecognitionLevel:
    stated_result = rank.strip() if rank else ""
    if _WINNER.search(stated_result) or _WINNER.search(name):
        return "winner_award"
    if _FINALIST.search(stated_result):
        return "finalist"
    if re.fullmatch(r"\s*#?1\s*", stated_result):
        return "winner_award"
    if _RANKED.search(stated_result):
        return "ranked"
    if _PARTICIPATION.search(stated_result):
        return "participation"
    if re.fullmatch(r"\s*#?\d+\s*", stated_result):
        return "ranked"
    return "unspecified"


def _tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9+#.]{2,}", text.casefold()) if word not in {"and", "the", "for", "with", "from"}}


def analyze_achievements(request: AchievementAnalysisRequest) -> AchievementAnalysisResponse:
    results = []
    evidence = []
    job_terms = _tokens(request.job_description) if request.job_description else set()
    for index, entry in enumerate(request.achievements):
        name = entry.name.strip()
        domain = entry.domain.strip() if entry.domain and entry.domain.strip() else None
        matches = sorted(_tokens(f"{name} {domain or ''}") & job_terms)
        relevance = "not_assessed" if not request.job_description else ("relevant" if matches else "not_relevant")
        level = _recognition(entry.rank, name)
        item = AchievementEvidenceItem(
            name=name,
            rank=entry.rank.strip() if entry.rank and entry.rank.strip() else None,
            year=entry.year,
            domain=domain,
            participants=entry.participants,
            recognition_level=level,
            relevance=relevance,
            matched_terms=matches,
        )
        results.append(item)
        fields = ["name"]
        fields.extend(field for field, value in (
            ("rank", item.rank), ("year", item.year), ("domain", domain), ("participants", item.participants),
        ) if value)
        evidence.append(AchievementEvidence(
            finding=f"Candidate-supplied achievement details recorded; stated outcome classified as {level}.",
            achievement_index=index,
            fields=fields,
        ))
    if not results:
        evidence.append(AchievementEvidence(finding="No competition or achievement records were supplied."))
    strengths = []
    winners = sum(item.recognition_level == "winner_award" for item in results)
    finalists = sum(item.recognition_level == "finalist" for item in results)
    ranked = sum(item.recognition_level == "ranked" for item in results)
    if winners:
        strengths.append(f"{winners} supplied record(s) state a winner or award outcome.")
    if finalists:
        strengths.append(f"{finalists} supplied record(s) state finalist status.")
    if ranked:
        strengths.append(f"{ranked} supplied record(s) state a ranked result.")
    return AchievementAnalysisResponse(
        achievements=results,
        achievement_score=score_achievements(results),
        strengths=strengths,
        evidence=evidence,
        score_method=SCORE_METHOD,
        status="available" if results else "no_data",
    )
