"""Explainable, deterministic matching and ranking for a supplied job requirement vector."""

import re
from typing import Any

from app.ranking.normalization import normalize_skill_name
from app.ranking.ranking_schemas import (
    CandidateToRank,
    ComponentScore,
    RankedCandidate,
    RankingEvidence,
    RankCandidatesRequest,
    RankCandidatesResponse,
)
from app.ranking.schemas import CandidateFeatureVector, FeatureDatum, FeatureGroup
from app.ranking.weights import COMPONENTS, select_weight_profile
from app.schemas.job import JobRequirementVector


SCORING_METHOD = (
    "Each available component is scored from 0 to 100 using its analyzer evidence and job requirements. "
    "A deterministic profile selected from the job domain assigns component weights; weights are "
    "renormalized over available, applicable components only. Overall score is the weighted mean of "
    "those components. Job-fit score uses required/preferred skill coverage plus stated experience and "
    "education checks when assessable. Unavailable evidence is excluded rather than scored as zero."
)

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "have", "in", "is", "of",
    "on", "or", "the", "to", "with", "we", "who", "years", "year", "experience", "knowledge",
    "strong", "required", "preferred", "developer", "engineer", "intern", "candidate", "candidates",
}

_RECOGNITION_POINTS = {
    "winner_award": 100.0,
    "finalist": 75.0,
    "ranked": 65.0,
    "participation": 30.0,
    "unspecified": 20.0,
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9+#.]+", value.casefold())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _skill_key(skill: str) -> str:
    return normalize_skill_name(skill).casefold()


def _datum(group: FeatureGroup, key: str) -> FeatureDatum | None:
    return group.features.get(key)


def _value(group: FeatureGroup, key: str) -> Any:
    datum = _datum(group, key)
    return datum.value if datum and datum.available else None


def _numeric_0_100(group: FeatureGroup, key: str) -> float | None:
    datum = _datum(group, key)
    if not datum or not datum.available:
        return None
    if datum.normalized_value is not None:
        return max(0.0, min(100.0, datum.normalized_value * 100.0))
    if isinstance(datum.value, (int, float)) and not isinstance(datum.value, bool):
        return max(0.0, min(100.0, float(datum.value)))
    return None


def _feature_evidence(group: FeatureGroup, *keys: str) -> list[str]:
    result: list[str] = []
    for key in keys:
        item = _datum(group, key)
        if item and item.available:
            for line in item.evidence:
                if line and line not in result:
                    result.append(line)
    return result


def _weighted_mean(values: list[tuple[float, float]]) -> float | None:
    if not values:
        return None
    total = sum(weight for _, weight in values)
    if total <= 0:
        return None
    return round(sum(score * weight for score, weight in values) / total, 2)


def _skill_evaluation(job: JobRequirementVector, candidate: CandidateFeatureVector) -> dict[str, Any]:
    candidate_names = {_skill_key(item.name): item for item in candidate.technical_skills}
    supported_sources = {
        "resume_analyzer", "project_analyzer", "github_analyzer", "kaggle_analyzer",
    }
    skill_data_available = bool(candidate.technical_skills) or any(
        supported_sources.intersection(group.sources)
        for group in (candidate.project_features, candidate.github_features, candidate.kaggle_features)
    )
    required = list(dict.fromkeys(job.required_skills))
    preferred = [item for item in dict.fromkeys(job.preferred_skills) if item not in required]
    matched_required = [skill for skill in required if _skill_key(skill) in candidate_names]
    matched_preferred = [skill for skill in preferred if _skill_key(skill) in candidate_names]
    missing_required = [skill for skill in required if skill not in matched_required] if skill_data_available else []
    evidence = []
    for skill in matched_required + matched_preferred:
        candidate_skill = candidate_names[_skill_key(skill)]
        requirement = "required" if skill in matched_required else "preferred"
        for finding in candidate_skill.evidence:
            evidence.append(RankingEvidence(
                component="skills",
                requirement=skill,
                source=", ".join(candidate_skill.sources) or "candidate_features",
                finding=f"Matched {requirement} skill {skill}: {finding}",
                supports_match=True,
            ))
    if not skill_data_available:
        return {
            "available": False, "score": None, "matched_required": [], "missing_required": [],
            "matched_preferred": [], "evidence": evidence,
            "reason": "No skill-bearing candidate evidence was supplied; skill coverage was not scored.",
        }
    scores = []
    if required:
        denominator = sum(max(0.01, job.skill_priorities.get(skill, 0.9)) for skill in required)
        matched_weight = sum(max(0.01, job.skill_priorities.get(skill, 0.9)) for skill in matched_required)
        scores.append((matched_weight / denominator * 100.0, 0.8 if preferred else 1.0))
    if preferred:
        scores.append((len(matched_preferred) / len(preferred) * 100.0, 0.2 if required else 1.0))
    score = _weighted_mean(scores)
    if score is None:
        return {"available": False, "score": None, "matched_required": [], "missing_required": [], "matched_preferred": [], "evidence": evidence, "reason": "The job vector contains no skills to compare."}
    for skill in missing_required:
        evidence.append(RankingEvidence(
            component="skills", requirement=skill, source="job_requirements",
            finding=f"No matching candidate skill evidence was supplied for required skill {skill}.",
            supports_match=False,
        ))
    return {
        "available": True, "score": score, "matched_required": matched_required,
        "missing_required": missing_required, "matched_preferred": matched_preferred,
        "evidence": evidence,
        "reason": "Required skill coverage is priority-weighted; preferred coverage contributes less and does not count as mandatory.",
    }


def _text_skill_coverage(job: JobRequirementVector, text: str) -> float | None:
    requirements = list(dict.fromkeys(job.technical_skills or (job.required_skills + job.preferred_skills)))
    if not requirements:
        return None
    matches = 0
    lowered = text.casefold()
    for skill in requirements:
        if _skill_key(skill) in {_skill_key(name) for name in re.findall(r"[A-Za-z][A-Za-z0-9+#. -]{1,40}", text)}:
            matches += 1
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(skill.casefold())}(?!\w)")
        if pattern.search(lowered):
            matches += 1
    return matches / len(requirements) * 100.0


def _project_score(job: JobRequirementVector, candidate: CandidateFeatureVector) -> tuple[float | None, list[str], str]:
    group = candidate.project_features
    quality = []
    for key, weight in (("project_score", 0.25), ("technical_complexity", 0.20), ("code_quality", 0.20), ("architecture", 0.20), ("completeness", 0.15)):
        value = _numeric_0_100(group, key)
        if value is not None:
            quality.append((value, weight))
    quality_score = _weighted_mean(quality)
    evidence = _feature_evidence(
        group, "project_score", "technical_complexity", "code_quality", "architecture",
        "completeness", "project_evidence", "technologies", "resume_projects",
    )
    relevance_texts = []
    for key in ("project_evidence", "technologies", "resume_projects"):
        value = _value(group, key)
        if isinstance(value, list):
            relevance_texts.extend(str(item) for item in value)
    relevance = _text_skill_coverage(job, " ".join(relevance_texts)) if relevance_texts else None
    values = []
    if quality_score is not None:
        values.append((quality_score, 0.6 if relevance is not None else 1.0))
    if relevance is not None:
        values.append((relevance, 0.4 if quality_score is not None else 1.0))
    return _weighted_mean(values), evidence, "Combines static project dimensions with explicit overlap between job skills and project evidence; file volume alone is not a quality score."


def _github_score(job: JobRequirementVector, candidate: CandidateFeatureVector) -> tuple[float | None, list[str], str]:
    group = candidate.github_features
    quality = []
    for key, weight in (("github_score", 0.4), ("documentation", 0.2), ("testing", 0.2), ("ci_cd", 0.1), ("project_structure", 0.1)):
        score = _numeric_0_100(group, key)
        if score is not None:
            quality.append((score, weight))
    quality_score = _weighted_mean(quality)
    evidence = _feature_evidence(
        group, "github_score", "documentation", "testing", "ci_cd", "project_structure",
        "repository_evidence", "repositories", "technologies", "languages",
    )
    names = []
    for key in ("technologies", "languages"):
        values = _value(group, key)
        if isinstance(values, list):
            names.extend(item.get("name", "") if isinstance(item, dict) else str(item) for item in values)
    required = list(dict.fromkeys(job.technical_skills or (job.required_skills + job.preferred_skills)))
    technology_data_available = any(
        _datum(group, key) is not None and _datum(group, key).available
        for key in ("technologies", "languages")
    )
    relevance = (
        sum(_skill_key(skill) in {_skill_key(name) for name in names} for skill in required)
        / len(required) * 100.0
        if required and technology_data_available
        else None
    )
    values = []
    if quality_score is not None:
        values.append((quality_score, 0.6 if relevance is not None else 1.0))
    if relevance is not None:
        values.append((relevance, 0.4 if quality_score is not None else 1.0))
    return _weighted_mean(values), evidence, "Uses repository quality indicators and job-skill technology overlap; commit, star, follower, and repository totals do not contribute."


def _group_source_available(group: FeatureGroup, key: str) -> bool:
    item = _datum(group, key)
    return bool(item and item.available)


def _certification_match(job: JobRequirementVector, candidate: CandidateFeatureVector) -> tuple[float | None, list[str], str]:
    group = candidate.certification_features
    record_datum = _datum(group, "records")
    resume_datum = _datum(group, "resume_certifications")
    if record_datum and record_datum.available:
        records = record_datum.value if isinstance(record_datum.value, list) else []
    elif resume_datum and resume_datum.available:
        records = resume_datum.value if isinstance(resume_datum.value, list) else []
    else:
        return None, [], "No certification details were supplied."
    if not records:
        return 0.0, ["Certification analyzer reports no certification records."] if record_datum else [], "Certification details are known to be empty."
    target = set(_skill_key(item) for item in (job.technical_skills + job.required_skills + job.preferred_skills))
    target.update(_tokens(f"{job.domain or ''} {job.role or ''}"))
    matched = []
    for record in records:
        if isinstance(record, dict):
            text = " ".join(str(record.get(key) or "") for key in ("name", "issuer", "domain", "details"))
        else:
            text = str(record)
        if any(skill in text.casefold() for skill in target) or bool(_tokens(text) & target):
            matched.append(text)
    evidence = [f"Job-related certification evidence: {item}" for item in matched]
    return (100.0 if matched else 0.0), evidence, "Scores whether supplied certification details match job skills/domain; credential count and source completeness do not add points."


def _achievement_match(job: JobRequirementVector, candidate: CandidateFeatureVector) -> tuple[float | None, list[str], str]:
    group = candidate.achievement_features
    record_datum = _datum(group, "records")
    resume_datum = _datum(group, "resume_achievements")
    if record_datum and record_datum.available:
        records = record_datum.value if isinstance(record_datum.value, list) else []
    elif resume_datum and resume_datum.available:
        records = resume_datum.value if isinstance(resume_datum.value, list) else []
    else:
        return None, [], "No achievement details were supplied."
    if not records:
        return 0.0, [], "Achievement records are known to be empty."
    target = set(_skill_key(item) for item in (job.technical_skills + job.required_skills + job.preferred_skills))
    target.update(_tokens(f"{job.domain or ''} {job.role or ''}"))
    relevant_records = []
    score_by_record = []
    for record in records:
        if isinstance(record, dict):
            text = " ".join(str(record.get(key) or "") for key in ("name", "domain", "rank", "recognition_level"))
            level = str(record.get("recognition_level") or "unspecified")
        else:
            text = str(record)
            level = "unspecified"
        if any(skill in text.casefold() for skill in target) or bool(_tokens(text) & target):
            relevant_records.append(text)
            score_by_record.append(_RECOGNITION_POINTS.get(level, 20.0))
    if not relevant_records:
        return 0.0, [], "Achievement records were supplied, but no job-related domain or skill match was found."
    return max(score_by_record), [f"Relevant achievement outcome: {item}" for item in relevant_records], "Uses the strongest relevant stated outcome; participation is distinguished from finalist, ranked, and winner/award claims."


def _research_match(job: JobRequirementVector, candidate: CandidateFeatureVector) -> tuple[float | None, list[str], str]:
    group = candidate.research_features
    base = _numeric_0_100(group, "research_score")
    domains = _value(group, "domains")
    publications = _value(group, "publications")
    target_domains = _tokens(f"{job.domain or ''} {job.role or ''}")
    domain_score = None
    domain_evidence = []
    if isinstance(domains, list):
        if not domains:
            domain_score = 0.0
        else:
            matches = [domain for domain in domains if _tokens(str(domain)) & target_domains]
            domain_score = 100.0 * len(matches) / len(domains)
            domain_evidence = [f"Research domain matches job context: {domain}" for domain in matches]
    values = []
    if base is not None:
        values.append((base, 0.3 if domain_score is not None else 1.0))
    if domain_score is not None:
        values.append((domain_score, 0.7 if base is not None else 1.0))
    evidence = _feature_evidence(group, "publications") + domain_evidence
    if isinstance(publications, list):
        evidence.extend(f"Candidate-supplied publication: {item.get('title', 'untitled')} (not externally verified)." for item in publications if isinstance(item, dict))
    return _weighted_mean(values), evidence, "Combines available research evidence coverage with explicit domain overlap; publication count and venue prestige are not scored."


def _experience_match(job: JobRequirementVector, candidate: CandidateFeatureVector) -> tuple[float | None, list[str], str]:
    requirements = job.experience_requirements
    if not requirements:
        return None, [], "The job vector contains no explicit experience requirement."
    group = candidate.experience_features
    item = _datum(group, "experience_records")
    if not item or not item.available:
        return None, [], "Candidate experience evidence is unavailable."
    records = item.value if isinstance(item.value, list) else []
    if not records:
        return 0.0, [], "Resume evidence was supplied with no experience records."
    context = _tokens(" ".join([job.role or "", job.domain or ""] + job.technical_skills + job.required_skills))
    candidate_text = " ".join(str(record) for record in records)
    record_tokens = _tokens(candidate_text)
    if not context:
        return None, [], "No role or skill terms were available for experience matching."
    matched = context & record_tokens
    fit = len(matched) / len(context) * 100.0
    years_found = [int(value) for value in re.findall(r"\b(\d+)\+?\s+years?\b", candidate_text, re.I)]
    year_requirements = [req.minimum_years for req in requirements if req.minimum_years is not None]
    if year_requirements and years_found:
        year_fit = min(100.0, max(years_found) / max(year_requirements) * 100.0)
        fit = 0.75 * fit + 0.25 * year_fit
    evidence = [f"Resume experience evidence: {record}" for record in records]
    if year_requirements and not years_found:
        evidence.append("Exact candidate experience duration was not stated in the supplied resume records.")
    return round(fit, 2), evidence, "Matches job role/domain/skill terms against resume experience text; explicit years are considered only when present."


def _education_match(job: JobRequirementVector, candidate: CandidateFeatureVector) -> tuple[float | None, list[str], str]:
    requirements = job.education_requirements
    if not requirements:
        return None, [], "The job vector contains no explicit education requirement."
    group = candidate.experience_features
    item = _datum(group, "education_records")
    if not item or not item.available:
        return None, [], "Candidate education evidence is unavailable."
    records = item.value if isinstance(item.value, list) else []
    if not records:
        return 0.0, [], "Resume evidence was supplied with no education records."
    result_scores = []
    for requirement in requirements:
        level_tokens = _tokens(requirement.level or requirement.description)
        matched = any(level_tokens & _tokens(str(record)) for record in records)
        result_scores.append(100.0 if matched else 0.0)
    evidence = [f"Resume education evidence: {record}" for record in records]
    return round(sum(result_scores) / len(result_scores), 2), evidence, "Compares stated education requirements with supplied resume education records."


def _base_components(job: JobRequirementVector, candidate: CandidateFeatureVector) -> dict[str, tuple[float | None, list[str], str]]:
    coding_group = candidate.coding_features
    kaggle_group = candidate.kaggle_features
    coding = _numeric_0_100(coding_group, "coding_score")
    kaggle = _numeric_0_100(kaggle_group, "kaggle_score")
    skill_result = _skill_evaluation(job, candidate)
    return {
        "skills": (skill_result["score"], [item.finding for item in skill_result["evidence"]], skill_result["reason"]),
        "projects": _project_score(job, candidate),
        "github": _github_score(job, candidate),
        "coding": (coding, _feature_evidence(coding_group, "platform_evidence", "coding_score"), "Uses the coding analyzer's platform-specific normalized evidence score; raw solve counts are not treated as engineering quality."),
        "kaggle": (kaggle, _feature_evidence(kaggle_group, "artifact_evidence", "kaggle_score"), "Uses Kaggle evidence coverage score, not notebook or competition counts."),
        "research": _research_match(job, candidate),
        "certifications": _certification_match(job, candidate),
        "achievements": _achievement_match(job, candidate),
        "experience": _experience_match(job, candidate),
        "education": _education_match(job, candidate),
    }


def _skill_fit_score(job: JobRequirementVector, skill_result: dict[str, Any]) -> tuple[float | None, list[str]]:
    if not skill_result["available"]:
        return None, []
    req = list(dict.fromkeys(job.required_skills))
    preferred = [skill for skill in dict.fromkeys(job.preferred_skills) if skill not in req]
    candidates = []
    if req:
        weights = [max(0.01, job.skill_priorities.get(skill, 0.9)) for skill in req]
        numerator = sum(weight for skill, weight in zip(req, weights) if skill in skill_result["matched_required"])
        candidates.append((numerator / sum(weights) * 100.0, 0.8 if preferred else 1.0))
    if preferred:
        candidates.append((len(skill_result["matched_preferred"]) / len(preferred) * 100.0, 0.2 if req else 1.0))
    return _weighted_mean(candidates), list(skill_result["matched_required"])


def _ranking_evidence(skill_result: dict[str, Any], components: dict[str, tuple[float | None, list[str], str]]) -> list[RankingEvidence]:
    evidence = list(skill_result["evidence"])
    for component, (score, findings, _) in components.items():
        if component == "skills" or score is None:
            continue
        seen = set()
        for finding in findings:
            if not finding or finding in seen:
                continue
            seen.add(finding)
            evidence.append(RankingEvidence(component=component, source=component, finding=finding))
    return evidence


def _strengths_and_gaps(
    components: dict[str, ComponentScore],
    skill_result: dict[str, Any],
) -> tuple[list[str], list[str]]:
    strengths = []
    weaknesses = []
    if skill_result["matched_required"]:
        strengths.append("Matched required skills: " + ", ".join(skill_result["matched_required"]) + ".")
    if skill_result["matched_preferred"]:
        strengths.append("Matched preferred skills: " + ", ".join(skill_result["matched_preferred"]) + ".")
    if skill_result["missing_required"]:
        weaknesses.append("No matching supplied skill evidence for required skills: " + ", ".join(skill_result["missing_required"]) + ".")
    for name, component in components.items():
        if not component.available:
            continue
        if component.score is not None and component.score >= 70 and component.evidence:
            strengths.append(f"{name.title()} evidence aligned with the job: {component.evidence[0]}")
        elif component.score is not None and component.score < 35 and name not in {"skills", "experience", "education"}:
            weaknesses.append(f"Limited matching {name} evidence was found in the supplied candidate data.")
    if not strengths:
        strengths.append("No strong job-specific match was established from the available evidence.")
    return list(dict.fromkeys(strengths)), list(dict.fromkeys(weaknesses))


def _score_one(
    job: JobRequirementVector,
    candidate_id: str,
    candidate: CandidateFeatureVector,
    weights: dict[str, float],
) -> RankedCandidate:
    skill_result = _skill_evaluation(job, candidate)
    raw = _base_components(job, candidate)
    applicable = {name for name, score_data in raw.items() if score_data[0] is not None}
    available_weight_sum = sum(weights[name] for name in applicable)
    component_scores = {}
    weighted_components = []
    for name in COMPONENTS:
        score, evidence, reason = raw[name]
        is_available = score is not None
        effective_weight = weights[name] / available_weight_sum if is_available and available_weight_sum else None
        component_scores[name] = ComponentScore(
            score=round(score, 2) if score is not None else None,
            available=is_available,
            weight=weights[name],
            effective_weight=round(effective_weight, 4) if effective_weight is not None else None,
            evidence=evidence,
            reason=reason,
        )
        if is_available:
            weighted_components.append((float(score), weights[name]))
    overall = _weighted_mean(weighted_components)
    all_available_weight = sum(weights.values())
    coverage = available_weight_sum / all_available_weight if all_available_weight else 0.0
    skill_fit, _ = _skill_fit_score(job, skill_result)
    job_fit_inputs: list[tuple[float, float]] = []
    if skill_fit is not None:
        job_fit_inputs.append((skill_fit, 0.75 if job.experience_requirements or job.education_requirements else 1.0))
    if raw["experience"][0] is not None:
        job_fit_inputs.append((float(raw["experience"][0]), 0.2 if job.education_requirements else 0.25))
    if raw["education"][0] is not None:
        job_fit_inputs.append((float(raw["education"][0]), 0.05 if job.experience_requirements else 0.1))
    job_fit = _weighted_mean(job_fit_inputs)
    evidence = _ranking_evidence(skill_result, raw)
    strengths, weaknesses = _strengths_and_gaps(component_scores, skill_result)
    available_names = [name for name in COMPONENTS if component_scores[name].available]
    unavailable_names = [name for name in COMPONENTS if not component_scores[name].available]
    explanation_parts = [
        f"Job domain: {job.domain or 'unspecified'}.",
        f"The selected dynamic profile is weighted toward {', '.join(sorted(weights, key=weights.get, reverse=True)[:3])}.",
        f"Scored available components: {', '.join(available_names) if available_names else 'none'}.",
    ]
    if skill_result["matched_required"]:
        explanation_parts.append("Matched required skills: " + ", ".join(skill_result["matched_required"]) + ".")
    if skill_result["missing_required"]:
        explanation_parts.append("Required skills without a matching supplied skill entry: " + ", ".join(skill_result["missing_required"]) + ".")
    if unavailable_names:
        explanation_parts.append("Unavailable or inapplicable evidence was excluded from the weighted score: " + ", ".join(unavailable_names) + ".")
    explanation_parts.append(f"Available component weight coverage: {coverage * 100:.1f}%.")
    return RankedCandidate(
        rank=1,
        candidate_id=candidate_id,
        overall_score=overall,
        job_fit_score=job_fit,
        data_coverage=round(coverage, 4),
        job_fit_coverage=round(sum(weight for _, weight in job_fit_inputs), 4),
        component_scores=component_scores,
        matched_required_skills=skill_result["matched_required"],
        missing_required_skills=skill_result["missing_required"],
        matched_preferred_skills=skill_result["matched_preferred"],
        skill_evidence_available=skill_result["available"],
        strengths=strengths,
        weaknesses=weaknesses,
        evidence=evidence,
        explanation=" ".join(explanation_parts),
    )


def rank_candidates(request: RankCandidatesRequest | dict[str, Any]) -> RankCandidatesResponse:
    """Rank multiple candidate vectors for one job with explainable domain-specific weights."""
    parsed = request if isinstance(request, RankCandidatesRequest) else RankCandidatesRequest.model_validate(request)
    profile_name, weights = select_weight_profile(parsed.job_requirements)
    results = [
        _score_one(parsed.job_requirements, candidate.candidate_id, candidate.candidate_features, weights)
        for candidate in parsed.candidates
    ]
    results.sort(key=lambda result: (
        result.overall_score is None,
        -(result.overall_score if result.overall_score is not None else -1),
        -(result.job_fit_score if result.job_fit_score is not None else -1),
        result.candidate_id.casefold(),
    ))
    for index, result in enumerate(results, start=1):
        result.rank = index
    return RankCandidatesResponse(
        ranked_candidates=results,
        job_domain=parsed.job_requirements.domain,
        weight_profile=profile_name,
        scoring_method=SCORING_METHOD,
        limitations=[
            "This is a deterministic evidence-matching baseline, not a trained model or hiring decision.",
            "Scores are conditional on supplied analyzer coverage; data_coverage reports available weighted components.",
            "Job requirement extraction and skill matching use explicit labels and normalized names; nuanced semantic equivalence may be missed.",
        ],
    )
