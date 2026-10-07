"""Combine existing analyzer responses into a provenance-preserving feature vector."""

from typing import Any

from app.ranking.normalization import (
    normalize_count,
    normalize_rating,
    normalize_score,
    normalize_skill_name,
)
from app.ranking.schemas import (
    CandidateAnalysisInputs,
    CandidateFeatureVector,
    FeatureDatum,
    FeatureGroup,
    SkillFeature,
)


def _datum(
    value: Any,
    source: str,
    evidence: list[str] | None = None,
    normalized: float | None = None,
    normalization: str | None = None,
    available: bool | None = None,
) -> FeatureDatum:
    is_available = value is not None if available is None else available
    return FeatureDatum(
        value=value,
        normalized_value=normalized if is_available else None,
        available=is_available,
        source=source if is_available else (source or "not_provided"),
        evidence=evidence or [],
        normalization=normalization if is_available else None,
    )


def _missing_group(source: str, names: list[str]) -> FeatureGroup:
    return FeatureGroup(
        available=False,
        sources=[],
        features={name: _datum(None, "not_provided", available=False) for name in names},
    )


def _score(value: int | None, source: str, evidence: list[str] | None = None) -> FeatureDatum:
    return _datum(
        value,
        source,
        evidence,
        normalize_score(value),
        "Source score on a 0-100 scale divided by 100; missing remains unavailable.",
    )


def _count(value: int | None, source: str, metric_cap: int, evidence: list[str] | None = None) -> FeatureDatum:
    return _datum(
        value,
        source,
        evidence,
        normalize_count(value, metric_cap),
        f"Metric-specific capped log1p scale with ceiling {metric_cap}; not comparable to differently named metrics.",
    )


def _resume_skill_evidence(name: str) -> str:
    return f"Resume skills section lists: {name}"


def _collect_skills(inputs: CandidateAnalysisInputs) -> list[SkillFeature]:
    collected: dict[str, dict[str, Any]] = {}

    def add(raw_name: str, source: str, evidence: str) -> None:
        name = normalize_skill_name(raw_name)
        if not name:
            return
        key = name.casefold()
        item = collected.setdefault(key, {"name": name, "sources": [], "evidence": []})
        if source not in item["sources"]:
            item["sources"].append(source)
        if evidence and evidence not in item["evidence"]:
            item["evidence"].append(evidence)

    if inputs.resume:
        for skill in inputs.resume.skills:
            add(skill.name, "resume_analyzer", _resume_skill_evidence(skill.name))
    if inputs.project:
        for tech in inputs.project.technologies:
            add(tech.name, "project_analyzer", f"Project technology {tech.name}; files: {', '.join(tech.evidence_files) or 'not specified'}")
        for language, count in inputs.project.structure.languages.items():
            add(language, "project_analyzer", f"Project scanner found {count} {language} source file(s).")
    if inputs.github:
        for language in inputs.github.languages:
            add(language.name, "github_analyzer", f"GitHub language: {language.name} ({language.repository_count} repositories).")
        for technology in inputs.github.technologies:
            add(technology.name, "github_analyzer", f"GitHub technology signal: {technology.name} ({technology.repository_count} repositories).")
    if inputs.kaggle:
        for skill in inputs.kaggle.skills:
            add(skill, "kaggle_analyzer", f"Kaggle artifact metadata includes topic/language: {skill}.")

    return [
        SkillFeature(name=data["name"], normalized_key=key, sources=data["sources"], evidence=data["evidence"])
        for key, data in sorted(collected.items(), key=lambda pair: pair[1]["name"].casefold())
    ]


def _project_group(inputs: CandidateAnalysisInputs) -> FeatureGroup:
    project = inputs.project
    resume = inputs.resume
    if not project and not resume:
        return _missing_group("project_analyzer", [
            "project_score", "technical_complexity", "code_quality", "architecture", "documentation",
            "testing", "deployment", "security", "completeness", "total_files", "source_files",
            "component_count", "technologies", "resume_projects",
        ])
    features: dict[str, FeatureDatum] = {}
    sources: list[str] = []
    if project:
        source = "project_analyzer"
        sources.append(source)
        for field in (
            "project_score", "technical_complexity", "code_quality", "architecture", "documentation",
            "testing", "deployment", "security", "completeness",
        ):
            value = getattr(project, field)
            features[field] = _score(value, source, [f"Project analyzer {field.replace('_', ' ')} score: {value}."] if value is not None else [])
        features["total_files"] = _count(project.structure.total_files, source, 1000, [f"Project scanner counted {project.structure.total_files} files."])
        features["source_files"] = _count(project.structure.source_files, source, 1000, [f"Project scanner counted {project.structure.source_files} source files."])
        features["component_count"] = _count(project.structure.component_count, source, 100, [f"Project scanner detected {project.structure.component_count} components."])
        features["languages"] = _datum(project.structure.languages, source, [f"Detected source languages: {', '.join(project.structure.languages)}"] if project.structure.languages else [])
        features["project_scale"] = _datum(project.project_scale, source, [f"Project scale classification: {project.project_scale}."])
        features["evidence_level"] = _datum(project.evidence_level, source, [f"Project evidence level: {project.evidence_level}."])
        features["technologies"] = _datum(
            [tech.model_dump(mode="json") for tech in project.technologies],
            source,
            [f"{tech.name} ({tech.category}); files: {', '.join(tech.evidence_files) or 'not specified'}" for tech in project.technologies],
        )
        features["project_evidence"] = _datum(
            [item.model_dump(mode="json") for item in project.evidence],
            source,
            [f"{item.area}: {item.finding}" for item in project.evidence],
        )
    else:
        for field in (
            "project_score", "technical_complexity", "code_quality", "architecture", "documentation",
            "testing", "deployment", "security", "completeness", "total_files", "source_files",
            "component_count", "languages", "project_scale", "evidence_level", "technologies", "project_evidence",
        ):
            features[field] = _datum(None, "project_analyzer", available=False)
    if resume:
        sources.append("resume_analyzer")
        features["resume_projects"] = _datum(
            [item.details for item in resume.projects],
            "resume_analyzer",
            [f"Resume project section: {item.details}" for item in resume.projects],
            available=True,
        )
    else:
        features["resume_projects"] = _datum(None, "resume_analyzer", available=False)
    payloads = {}
    if project:
        payloads["project_analyzer"] = project.model_dump(mode="json")
    if resume:
        payloads["resume_analyzer"] = resume.model_dump(mode="json")
    return FeatureGroup(available=True, sources=sources, features=features, source_payloads=payloads)


def _github_group(inputs: CandidateAnalysisInputs) -> FeatureGroup:
    github = inputs.github
    if not github:
        return _missing_group("github_analyzer", [
            "github_score", "documentation", "testing", "ci_cd", "project_structure", "public_repositories",
            "analyzed_repositories", "followers", "following", "commits_observed", "pull_requests_observed",
            "issues_observed", "languages", "technologies", "repository_evidence", "repositories",
        ])
    source = "github_analyzer"
    quality = github.quality_indicators
    observed_evidence = [f"{item.category}: {item.finding}" for item in github.evidence]
    features = {
        "github_score": _score(github.github_score, source, observed_evidence),
        "documentation": _score(quality.documentation, source, observed_evidence),
        "testing": _score(quality.testing, source, observed_evidence),
        "ci_cd": _score(quality.ci_cd, source, observed_evidence),
        "project_structure": _score(quality.project_structure, source, observed_evidence),
        "public_repositories": _count(github.public_repositories, source, 100, [f"Public repositories reported: {github.public_repositories}."]),
        "analyzed_repositories": _count(github.analyzed_repositories, source, 50, [f"Repositories inspected: {github.analyzed_repositories}."]),
        "followers": _datum(github.followers, source, [f"Public profile reports {github.followers} followers; not a quality feature."], normalization="Popularity metric retained raw and excluded from quality normalization."),
        "following": _datum(github.following, source, [f"Public profile reports following {github.following} accounts; not a quality feature."], normalization="Profile count retained raw and excluded from quality normalization."),
        "commits_observed": _count(github.activity.commits, source, 100, [github.activity.source]),
        "pull_requests_observed": _count(github.activity.pull_requests, source, 50, [github.activity.source]),
        "issues_observed": _count(github.activity.issues, source, 50, [github.activity.source]),
        "languages": _datum([item.model_dump(mode="json") for item in github.languages], source, [f"{item.name}: {item.repository_count} repositories ({item.percentage:g}%)." for item in github.languages]),
        "technologies": _datum([item.model_dump(mode="json") for item in github.technologies], source, [f"{item.name}: {item.repository_count} repositories ({item.percentage:g}%)." for item in github.technologies]),
        "repository_evidence": _datum([item.model_dump(mode="json") for item in github.evidence], source, observed_evidence),
        "repositories": _datum([item.model_dump(mode="json") for item in github.repositories], source, [f"Repository {item.full_name}: {item.description or 'no description supplied'}" for item in github.repositories]),
    }
    return FeatureGroup(available=True, sources=[source], features=features, source_payloads={source: github.model_dump(mode="json")})


def _coding_group(inputs: CandidateAnalysisInputs) -> FeatureGroup:
    coding = inputs.coding
    names = [
        "coding_score", "leetcode_status", "leetcode_rating", "leetcode_problem_solving", "leetcode_contest_participation",
        "leetcode_problems_solved", "leetcode_easy", "leetcode_medium", "leetcode_hard", "codeforces_status",
        "codeforces_rating", "codeforces_peak_rating", "codeforces_problem_solving", "codeforces_contest_participation",
        "codeforces_problems_solved", "normalized_platform_features", "platform_evidence", "leetcode_profile", "codeforces_profile",
    ]
    if not coding:
        return _missing_group("coding_analyzer", names)
    source = "coding_analyzer"
    features: dict[str, FeatureDatum] = {
        "coding_score": _score(coding.coding_score, source, [coding.scoring_method]),
        "leetcode_status": _datum(coding.leetcode_status, source, [f"LeetCode profile state: {coding.leetcode_status}."]),
        "codeforces_status": _datum(coding.codeforces_status, source, [f"Codeforces profile state: {coding.codeforces_status}."]),
        "normalized_platform_features": _datum(coding.normalized_features.model_dump(mode="json"), source, [coding.normalized_features.method]),
        "platform_evidence": _datum([item.model_dump(mode="json") for item in coding.evidence], source, [f"{item.platform}: {item.finding}" for item in coding.evidence]),
    }
    lc, lc_norm = coding.leetcode, coding.normalized_features.leetcode
    cf, cf_norm = coding.codeforces, coding.normalized_features.codeforces
    features.update({
        "leetcode_rating": _datum(lc.rating if lc else None, source, [f"LeetCode rating: {lc.rating}."] if lc and lc.rating is not None else [], normalize_score(lc_norm.rating) if lc_norm else None, "LeetCode normalizer value 0-100 divided by 100."),
        "leetcode_problem_solving": _datum(lc_norm.problem_solving if lc_norm else None, source, [f"LeetCode reports {lc.problems_solved} problems solved."] if lc and lc.problems_solved is not None else [], normalize_score(lc_norm.problem_solving) if lc_norm else None, "LeetCode-specific normalized problem-solving feature divided by 100."),
        "leetcode_contest_participation": _datum(lc_norm.contest_participation if lc_norm else None, source, [f"LeetCode contests participated: {lc.contests_participated}."] if lc and lc.contests_participated is not None else [], normalize_score(lc_norm.contest_participation) if lc_norm else None, "LeetCode-specific normalized contest feature divided by 100."),
        "leetcode_problems_solved": _count(lc.problems_solved if lc else None, source, 2000, [f"{lc.problems_solved} total accepted problems reported."] if lc and lc.problems_solved is not None else []),
        "leetcode_easy": _count(lc.easy if lc else None, source, 1000),
        "leetcode_medium": _count(lc.medium if lc else None, source, 1000),
        "leetcode_hard": _count(lc.hard if lc else None, source, 1000),
        "codeforces_rating": _datum(cf.rating if cf else None, source, [f"Codeforces rating: {cf.rating}."] if cf and cf.rating is not None else [], normalize_rating(cf.rating, 4000) if cf else None, "Codeforces rating divided by the fixed 4000 reference ceiling."),
        "codeforces_peak_rating": _datum(cf.max_rating if cf else None, source, [f"Codeforces max rating: {cf.max_rating}."] if cf and cf.max_rating is not None else [], normalize_score(cf_norm.peak_rating) if cf_norm else None, "Codeforces-specific normalized peak rating divided by 100."),
        "codeforces_problem_solving": _datum(cf_norm.problem_solving if cf_norm else None, source, [f"Codeforces sampled unique solved problems: {cf.problems_solved}."] if cf and cf.problems_solved is not None else [], normalize_score(cf_norm.problem_solving) if cf_norm else None, "Codeforces-specific normalized problem-solving feature divided by 100."),
        "codeforces_contest_participation": _datum(cf_norm.contest_participation if cf_norm else None, source, [f"Codeforces contests participated: {cf.contests_participated}."] if cf and cf.contests_participated is not None else [], normalize_score(cf_norm.contest_participation) if cf_norm else None, "Codeforces-specific normalized contest feature divided by 100."),
        "codeforces_problems_solved": _count(cf.problems_solved if cf else None, source, 500, [cf.problem_count_scope] if cf else []),
        "leetcode_profile": _datum(lc.model_dump(mode="json") if lc else None, source, [f"LeetCode profile supplied for {lc.username}."] if lc else []),
        "codeforces_profile": _datum(cf.model_dump(mode="json") if cf else None, source, [f"Codeforces profile supplied for {cf.username}."] if cf else []),
    })
    return FeatureGroup(available=True, sources=[source], features=features, source_payloads={source: coding.model_dump(mode="json")})


def _kaggle_group(inputs: CandidateAnalysisInputs) -> FeatureGroup:
    kaggle = inputs.kaggle
    names = ["status", "profile_verified", "kaggle_score", "notebooks_observed", "datasets_observed", "competitions", "competition_records", "medals", "medal_records", "skills", "artifact_evidence"]
    if not kaggle:
        return _missing_group("kaggle_analyzer", names)
    source = "kaggle_analyzer"
    accessible = kaggle.status == "available"
    score = kaggle.kaggle_score if accessible else None
    notebooks_count = len(kaggle.notebooks) if accessible else None
    datasets_count = len(kaggle.datasets) if accessible else None
    artifact_evidence = [f"Notebook: {item.title}" for item in kaggle.notebooks] + [f"Dataset: {item.title}" for item in kaggle.datasets]
    return FeatureGroup(available=True, sources=[source], features={
        "status": _datum(kaggle.status, source, [*kaggle.unavailable_fields]),
        "profile_verified": _datum(kaggle.activity.profile_verified, source),
        "kaggle_score": _score(score, source, [kaggle.score_method]),
        "notebooks_observed": _count(notebooks_count, source, 20, artifact_evidence),
        "datasets_observed": _count(datasets_count, source, 20, artifact_evidence),
        "competitions": _datum(kaggle.activity.competitions if accessible else None, source),
        "competition_records": _datum([item.model_dump(mode="json") for item in kaggle.competitions] if accessible else None, source, [f"Kaggle competition: {item.title}" for item in kaggle.competitions] if accessible else []),
        "medals": _datum(kaggle.activity.medals if accessible else None, source),
        "medal_records": _datum(kaggle.medals if accessible else None, source, [f"Kaggle medal: {item}" for item in kaggle.medals] if accessible else []),
        "skills": _datum(kaggle.skills if accessible else None, source, [f"Kaggle skill/topic observed: {item}" for item in kaggle.skills]),
        "artifact_evidence": _datum(artifact_evidence if accessible else None, source, artifact_evidence),
    }, source_payloads={source: kaggle.model_dump(mode="json")})


def _research_group(inputs: CandidateAnalysisInputs) -> FeatureGroup:
    research = inputs.research
    resume = inputs.resume
    if not research and not resume:
        return _missing_group("research_analyzer", ["publication_count", "research_score", "domains", "publications", "resume_research"])
    features: dict[str, FeatureDatum] = {}
    sources = []
    if research:
        source = "research_analyzer"
        sources.append(source)
        features["publication_count"] = _count(research.publication_count, source, 50, [f"Candidate-supplied publication records: {research.publication_count}."])
        features["research_score"] = _score(research.research_score, source, [research.score_method])
        features["domains"] = _datum(research.research_domains, source, [f"Detected research domain: {domain}" for domain in research.research_domains], available=True)
        features["publications"] = _datum([item.model_dump(mode="json") for item in research.publications], source, [f"Publication record supplied: {item.title}; authorship: {item.candidate_authorship}; not externally verified." for item in research.publications], available=True)
    else:
        for field in ("publication_count", "research_score", "domains", "publications"):
            features[field] = _datum(None, "research_analyzer", available=False)
    if resume:
        sources.append("resume_analyzer")
        features["resume_research"] = _datum([item.details for item in resume.research], "resume_analyzer", [f"Resume research section: {item.details}" for item in resume.research], available=True)
    else:
        features["resume_research"] = _datum(None, "resume_analyzer", available=False)
    payloads = {}
    if research:
        payloads["research_analyzer"] = research.model_dump(mode="json")
    if resume:
        payloads["resume_analyzer"] = resume.model_dump(mode="json")
    return FeatureGroup(available=True, sources=sources, features=features, source_payloads=payloads)


def _certification_group(inputs: CandidateAnalysisInputs) -> FeatureGroup:
    certs = inputs.certifications
    resume = inputs.resume
    if not certs and not resume:
        return _missing_group("certifications_analyzer", ["certification_count", "certification_score", "records", "relevant_certifications", "resume_certifications"])
    features: dict[str, FeatureDatum] = {}
    sources = []
    if certs:
        source = "certifications_analyzer"
        sources.append(source)
        features["certification_count"] = _count(len(certs.certifications), source, 50)
        features["certification_score"] = _score(certs.certification_score, source, [certs.score_method])
        features["records"] = _datum([item.model_dump(mode="json") for item in certs.certifications], source, [f"{item.name}; issuer: {item.issuer or 'not supplied'}; date: {item.date or 'not supplied'}" for item in certs.certifications], available=True)
        features["relevant_certifications"] = _datum([item.model_dump(mode="json") for item in certs.relevant_certifications], source, [f"Matched job text terms for {item.name}: {', '.join(item.matched_terms)}" for item in certs.relevant_certifications], available=True)
    else:
        features["certification_count"] = _count(len(resume.certifications), "resume_analyzer", 50)
        features["certification_score"] = _datum(None, "certifications_analyzer", available=False)
        features["records"] = _datum(None, "certifications_analyzer", available=False)
        features["relevant_certifications"] = _datum(None, "certifications_analyzer", available=False)
    if resume:
        sources.append("resume_analyzer")
        features["resume_certifications"] = _datum([item.details for item in resume.certifications], "resume_analyzer", [f"Resume certification section: {item.details}" for item in resume.certifications], available=True)
    else:
        features["resume_certifications"] = _datum(None, "resume_analyzer", available=False)
    payloads = {}
    if certs:
        payloads["certifications_analyzer"] = certs.model_dump(mode="json")
    if resume:
        payloads["resume_analyzer"] = resume.model_dump(mode="json")
    return FeatureGroup(available=True, sources=sources, features=features, source_payloads=payloads)


def _achievement_group(inputs: CandidateAnalysisInputs) -> FeatureGroup:
    achievements = inputs.achievements
    resume = inputs.resume
    if not achievements and not resume:
        return _missing_group("achievements_analyzer", ["achievement_count", "achievement_score", "records", "resume_achievements"])
    features: dict[str, FeatureDatum] = {}
    sources = []
    if achievements:
        source = "achievements_analyzer"
        sources.append(source)
        features["achievement_count"] = _count(len(achievements.achievements), source, 50)
        features["achievement_score"] = _score(achievements.achievement_score, source, [achievements.score_method])
        features["records"] = _datum([item.model_dump(mode="json") for item in achievements.achievements], source, [f"{item.name}; stated result: {item.rank or 'not supplied'}; classified {item.recognition_level}." for item in achievements.achievements], available=True)
    else:
        features["achievement_count"] = _count(len(resume.achievements), "resume_analyzer", 50)
        features["achievement_score"] = _datum(None, "achievements_analyzer", available=False)
        features["records"] = _datum(None, "achievements_analyzer", available=False)
    if resume:
        sources.append("resume_analyzer")
        features["resume_achievements"] = _datum([item.details for item in resume.achievements], "resume_analyzer", [f"Resume achievement section: {item.details}" for item in resume.achievements], available=True)
    else:
        features["resume_achievements"] = _datum(None, "resume_analyzer", available=False)
    payloads = {}
    if achievements:
        payloads["achievements_analyzer"] = achievements.model_dump(mode="json")
    if resume:
        payloads["resume_analyzer"] = resume.model_dump(mode="json")
    return FeatureGroup(available=True, sources=sources, features=features, source_payloads=payloads)


def _experience_group(inputs: CandidateAnalysisInputs) -> FeatureGroup:
    resume = inputs.resume
    if not resume:
        return _missing_group("resume_analyzer", ["experience_count", "experience_records", "education_count", "education_records"])
    return FeatureGroup(available=True, sources=["resume_analyzer"], source_payloads={"resume_analyzer": resume.model_dump(mode="json")}, features={
        "experience_count": _count(len(resume.experience), "resume_analyzer", 50),
        "experience_records": _datum([item.details for item in resume.experience], "resume_analyzer", [f"Resume experience section: {item.details}" for item in resume.experience], available=True),
        "education_count": _count(len(resume.education), "resume_analyzer", 20),
        "education_records": _datum([item.details for item in resume.education], "resume_analyzer", [f"Resume education section: {item.details}" for item in resume.education], available=True),
    })


def _vector_evidence(groups: dict[str, FeatureGroup], skills: list[SkillFeature]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for group_name, group in groups.items():
        for feature_name, datum in group.features.items():
            flattened.append({
                "feature": f"{group_name}.{feature_name}",
                **datum.model_dump(mode="json"),
            })
    for skill in skills:
        for source in skill.sources:
            flattened.append({
                "feature": f"technical_skills.{skill.normalized_key}",
                "value": skill.name,
                "normalized_value": None,
                "available": True,
                "source": source,
                "evidence": skill.evidence,
                "normalization": "Case and common alias normalization; source labels and supporting text retained.",
            })
    return flattened


def aggregate_candidate(inputs: CandidateAnalysisInputs | dict[str, Any]) -> CandidateFeatureVector:
    """Aggregate analyzer outputs into normalized features without producing a candidate score.

    Missing analyzer sections are unavailable. An explicitly supplied empty analyzer result is
    represented as known empty evidence (for example, a count of zero) where applicable.
    """
    parsed = inputs if isinstance(inputs, CandidateAnalysisInputs) else CandidateAnalysisInputs.model_validate(inputs)
    groups = {
        "project_features": _project_group(parsed),
        "github_features": _github_group(parsed),
        "coding_features": _coding_group(parsed),
        "kaggle_features": _kaggle_group(parsed),
        "research_features": _research_group(parsed),
        "certification_features": _certification_group(parsed),
        "achievement_features": _achievement_group(parsed),
        "experience_features": _experience_group(parsed),
    }
    skills = _collect_skills(parsed)
    return CandidateFeatureVector(
        technical_skills=skills,
        evidence_vector=_vector_evidence(groups, skills),
        **groups,
    )
