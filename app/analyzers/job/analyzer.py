"""Rule-based extraction of job requirements, with an optional semantic domain fallback."""

import re
from dataclasses import dataclass

from app.ranking.normalization import normalize_skill_name
from app.schemas.job import (
    EducationRequirement,
    ExperienceRequirement,
    JobAnalysisRequest,
    JobAnalysisResponse,
    JobRequirementVector,
    SkillEvidence,
)
from app.services.job_semantics import SentenceTransformerDomainMatcher


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    category: str
    patterns: tuple[str, ...]
    case_sensitive: bool = False


SKILLS = (
    SkillDefinition("Python", "programming_languages", (r"python",)),
    SkillDefinition("JavaScript", "programming_languages", (r"javascript", r"js")),
    SkillDefinition("TypeScript", "programming_languages", (r"typescript", r"ts")),
    SkillDefinition("Java", "programming_languages", (r"java",)),
    SkillDefinition("C++", "programming_languages", (r"c\+\+", r"cpp")),
    SkillDefinition("C#", "programming_languages", (r"c#", r"csharp")),
    SkillDefinition("Go", "programming_languages", (r"go", r"golang"), case_sensitive=True),
    SkillDefinition("Rust", "programming_languages", (r"rust",)),
    SkillDefinition("Ruby", "programming_languages", (r"ruby",)),
    SkillDefinition("PHP", "programming_languages", (r"php",)),
    SkillDefinition("Swift", "programming_languages", (r"swift",)),
    SkillDefinition("Kotlin", "programming_languages", (r"kotlin",)),
    SkillDefinition("R", "programming_languages", (r"r",), case_sensitive=True),
    SkillDefinition("SQL", "programming_languages", (r"sql", r"structured query language")),
    SkillDefinition("Django", "frameworks", (r"django",)),
    SkillDefinition("Flask", "frameworks", (r"flask",)),
    SkillDefinition("FastAPI", "frameworks", (r"fastapi", r"fast api")),
    SkillDefinition("Spring", "frameworks", (r"spring(?: boot)?",)),
    SkillDefinition("Express.js", "frameworks", (r"express(?:\.js|js)?",)),
    SkillDefinition("Node.js", "frameworks", (r"node(?:\.js|js)?",)),
    SkillDefinition("React", "frameworks", (r"react(?:\.js|js)?",)),
    SkillDefinition("Angular", "frameworks", (r"angular",)),
    SkillDefinition("Vue.js", "frameworks", (r"vue(?:\.js|js)?",)),
    SkillDefinition("Next.js", "frameworks", (r"next(?:\.js|js)?",)),
    SkillDefinition(".NET", "frameworks", (r"\.net", r"dotnet")),
    SkillDefinition("TensorFlow", "frameworks", (r"tensorflow",)),
    SkillDefinition("PyTorch", "frameworks", (r"pytorch",)),
    SkillDefinition("scikit-learn", "frameworks", (r"scikit[- ]learn", r"sklearn")),
    SkillDefinition("PostgreSQL", "databases", (r"postgres(?:ql)?",)),
    SkillDefinition("MySQL", "databases", (r"mysql",)),
    SkillDefinition("MongoDB", "databases", (r"mongodb",)),
    SkillDefinition("Redis", "databases", (r"redis",)),
    SkillDefinition("SQLite", "databases", (r"sqlite",)),
    SkillDefinition("Oracle", "databases", (r"oracle database",)),
    SkillDefinition("DynamoDB", "databases", (r"dynamodb",)),
    SkillDefinition("Cassandra", "databases", (r"cassandra",)),
    SkillDefinition("Elasticsearch", "databases", (r"elasticsearch",)),
    SkillDefinition("Docker", "tools", (r"docker",)),
    SkillDefinition("Kubernetes", "tools", (r"kubernetes", r"k8s")),
    SkillDefinition("Git", "tools", (r"git",)),
    SkillDefinition("Linux", "tools", (r"linux",)),
    SkillDefinition("Terraform", "tools", (r"terraform",)),
    SkillDefinition("Jenkins", "tools", (r"jenkins",)),
    SkillDefinition("GitHub Actions", "tools", (r"github actions",)),
    SkillDefinition("Jira", "tools", (r"jira",)),
    SkillDefinition("Postman", "tools", (r"postman",)),
    SkillDefinition("Apache Kafka", "tools", (r"kafka",)),
    SkillDefinition("AWS", "cloud_technologies", (r"aws", r"amazon web services")),
    SkillDefinition("Azure", "cloud_technologies", (r"microsoft azure", r"azure")),
    SkillDefinition("Google Cloud", "cloud_technologies", (r"google cloud(?: platform)?", r"gcp")),
    SkillDefinition("REST APIs", "technical_skills", (r"rest(?:ful)?\s+apis?", r"apis?\s+rest")),
    SkillDefinition("API Development", "technical_skills", (r"api development", r"api design")),
    SkillDefinition("Database Concepts", "technical_skills", (r"databases?", r"database concepts")),
    SkillDefinition("Authentication", "technical_skills", (r"authentication", r"authorization")),
    SkillDefinition("Microservices", "technical_skills", (r"microservices?",)),
    SkillDefinition("Machine Learning", "technical_skills", (r"machine learning", r"\bml\b")),
    SkillDefinition("Deep Learning", "technical_skills", (r"deep learning",)),
    SkillDefinition("Natural Language Processing", "technical_skills", (r"natural language processing", r"\bnlp\b")),
    SkillDefinition("Computer Vision", "technical_skills", (r"computer vision",)),
    SkillDefinition("Data Science", "technical_skills", (r"data science",)),
    SkillDefinition("Data Engineering", "technical_skills", (r"data engineering",)),
    SkillDefinition("Data Structures and Algorithms", "technical_skills", (r"data structures? and algorithms?", r"\bdsa\b")),
    SkillDefinition("Algorithms", "technical_skills", (r"algorithms?",)),
    SkillDefinition("Competitive Programming", "technical_skills", (r"competitive programming", r"programming contests?")),
    SkillDefinition("System Design", "technical_skills", (r"system design",)),
    SkillDefinition("CI/CD", "technical_skills", (r"ci\s*/\s*cd", r"continuous integration(?: and delivery)?")),
    SkillDefinition("Cloud Computing", "technical_skills", (r"cloud computing",)),
)

SOFT_SKILLS = (
    "Communication", "Teamwork", "Collaboration", "Leadership", "Problem Solving",
    "Adaptability", "Time Management", "Critical Thinking", "Written Communication",
    "Attention to Detail", "Mentorship",
)

REQUIRED_CUES = (
    (r"must\s+have", "must have"),
    (r"required", "required"),
    (r"strong\s+knowledge\s+of", "strong knowledge of"),
    (r"experience\s+(?:with|in|using)", "experience with"),
    (r"proficient\s+in", "proficient in"),
)
PREFERRED_CUES = (
    (r"nice\s+to\s+have", "nice to have"),
    (r"preferred", "preferred"),
    (r"bonus", "bonus"),
    (r"\bplus\b", "plus"),
    (r"familiarity\s+with", "familiarity with"),
    (r"desirable", "desirable"),
)

DOMAIN_RULES = (
    ("Competitive Programming", (r"competitive programming", r"codeforces", r"leetcode", r"programming contests?", r"algorithmic competitions?")),
    ("Machine Learning", (r"machine learning", r"\bml engineer", r"deep learning", r"artificial intelligence", r"\bai engineer")),
    ("Data Science", (r"data scientist", r"data science", r"statistical modeling")),
    ("Data Engineering", (r"data engineer", r"data engineering", r"data pipeline")),
    ("Frontend Development", (r"front[- ]end", r"frontend", r"user interface", r"\bui developer")),
    ("Backend Development", (r"back[- ]end", r"backend", r"server[- ]side")),
    ("Full-Stack Development", (r"full[- ]stack", r"fullstack")),
    ("Cloud and DevOps", (r"devops", r"site reliability", r"cloud engineer", r"platform engineer")),
    ("Cybersecurity", (r"cyber ?security", r"information security", r"security engineer")),
    ("Mobile Development", (r"mobile developer", r"ios developer", r"android developer")),
    ("Software Engineering", (r"software (?:developer|engineer)", r"application developer")),
)

DOMAIN_CANDIDATES = [name for name, _ in DOMAIN_RULES]
JOB_EVIDENCE_TYPES = (
    "technical_skills", "backend_projects", "frontend_projects", "software_projects",
    "github", "coding_profiles", "research_publications", "cloud_certifications",
    "work_experience", "education",
)


def _chunks(text: str) -> list[str]:
    flattened = re.sub(r"\s+", " ", text).strip()
    return [chunk.strip(" -*•\t") for chunk in re.split(r"(?<=[.!?;])\s+", flattened) if chunk.strip(" -*•\t")]


def _compile(pattern: str, case_sensitive: bool = False) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<![\w+#.])(?:{pattern})(?![\w+#])", flags)


def _title_line(text: str) -> tuple[str | None, str | None]:
    lines = [re.sub(r"^(?:job\s+title|position)\s*:\s*", "", line.strip().lstrip("#*-• ").strip(), flags=re.I) for line in text.splitlines() if line.strip()]
    title_markers = r"\b(developer|engineer|intern|analyst|scientist|programmer|specialist|architect|designer|administrator|manager|consultant|coach)\b"
    for line in lines[:4]:
        if len(line) <= 100 and re.search(title_markers, line, re.I) and not re.search(r"\b(we are looking|responsibilities|qualifications|requirements)\b", line, re.I):
            return line, line
    for pattern in (
        r"looking for\s+(?:an?\s+)?(.+?)(?=\s+(?:with|for|to|who|that)\b|[,.;\n]|$)",
        r"seeking\s+(?:an?\s+)?(.+?)(?=\s+(?:with|for|to|who|that)\b|[,.;\n]|$)",
        r"hiring\s+(?:an?\s+)?(.+?)(?=\s+(?:with|for|to|who|that)\b|[,.;\n]|$)",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            role = match.group(1).strip().title()
            for old, new in (("Ml", "ML"), ("Ai", "AI"), ("Ui", "UI"), ("Devops", "DevOps")):
                role = role.replace(old, new)
            return role[:100], match.group(0)
    return None, None


def _rule_domain(text: str) -> tuple[str | None, str | None]:
    for domain, patterns in DOMAIN_RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                match = re.search(pattern, text, re.I)
                return domain, match.group(0) if match else None
    return None, None


def _nearest_cue(chunk: str, start: int, end: int) -> tuple[str, str | None]:
    cues = []
    for requirement, patterns in (("required", REQUIRED_CUES), ("preferred", PREFERRED_CUES)):
        for pattern, label in patterns:
            for match in re.finditer(pattern, chunk, re.I):
                distance = min(abs(start - match.end()), abs(match.start() - end))
                cues.append((distance, requirement, label))
    if not cues:
        return "required", None
    _, requirement, label = min(cues, key=lambda cue: cue[0])
    return requirement, label


def _extract_skills(text: str) -> tuple[list[SkillEvidence], str]:
    records: dict[str, dict] = {}
    for chunk in _chunks(text):
        for definition in SKILLS:
            for pattern in definition.patterns:
                regex = _compile(pattern, definition.case_sensitive)
                for match in regex.finditer(chunk):
                    # Single-letter language names require strong syntax context to avoid false positives.
                    if definition.name == "R" and not re.search(r"\bR\s+(?:programming|language|developer|statistical)\b", chunk):
                        continue
                    if definition.name == "Go" and match.group(0).casefold() == "go" and not re.search(r"\bGo\s+(?:programming|language|developer|services?)\b", chunk):
                        continue
                    requirement, cue = _nearest_cue(chunk, match.start(), match.end())
                    canonical = normalize_skill_name(definition.name)
                    existing = records.get(canonical)
                    priority = 1.0 if requirement == "required" and cue else (0.9 if requirement == "required" else 0.5)
                    evidence = SkillEvidence(
                        skill=canonical,
                        requirement=requirement,
                        priority=priority,
                        category=definition.category,
                        excerpt=chunk,
                        cue=cue,
                    )
                    if existing is None:
                        records[canonical] = {"evidence": evidence, "position": len(records)}
                    elif requirement == "required" and existing["evidence"].requirement == "preferred":
                        records[canonical] = {"evidence": evidence, "position": existing["position"]}
                    elif priority > existing["evidence"].priority:
                        records[canonical]["evidence"] = evidence
    ordered = sorted(records.values(), key=lambda record: record["position"])
    return [record["evidence"] for record in ordered], ""


def _extract_experience(chunks: list[str]) -> list[ExperienceRequirement]:
    results = []
    year_pattern = re.compile(r"(\d+)\s*(?:-|to)\s*(\d+)\s+years?", re.I)
    single_pattern = re.compile(r"(\d+)\+?\s+years?", re.I)
    for chunk in chunks:
        matches = list(re.finditer(r"\b\d+\s*(?:-|to|\+)?\s*years?\b", chunk, re.I))
        if not matches:
            if not re.search(r"\b(entry[- ]level|junior|senior|intern|internship|graduate role)\b", chunk, re.I):
                continue
        year_range = year_pattern.search(chunk)
        single = single_pattern.search(chunk)
        minimum = int(year_range.group(1)) if year_range else int(single.group(1)) if single else None
        maximum = int(year_range.group(2)) if year_range else None
        requirement, _ = _nearest_cue(chunk, 0, min(len(chunk), 1))
        results.append(ExperienceRequirement(description=chunk, minimum_years=minimum, maximum_years=maximum, requirement=requirement if matches else "unspecified"))
    return results


def _extract_education(chunks: list[str]) -> list[EducationRequirement]:
    results = []
    education_pattern = re.compile(r"\b(bachelor'?s?|master'?s?|b\.?s\.?|b\.?a\.?|m\.?s\.?|m\.?a\.?|bsc|msc|ph\.?d\.?|doctorate|degree|diploma|graduate|undergraduate|education|academic background)\b", re.I)
    for chunk in chunks:
        match = education_pattern.search(chunk)
        if not match:
            continue
        requirement, _ = _nearest_cue(chunk, match.start(), match.end())
        level = match.group(0)
        results.append(EducationRequirement(description=chunk, level=level, requirement=requirement))
    return results


def _role_domain_evidence(text: str, role: str | None) -> tuple[str | None, str | None, str]:
    domain, evidence = _rule_domain(f"{role or ''} {text}")
    if domain:
        return domain, evidence, "rules"
    matcher = SentenceTransformerDomainMatcher()
    if matcher.enabled:
        semantic_domain = matcher.classify_domain(text, DOMAIN_CANDIDATES)
        if semantic_domain:
            return semantic_domain, f"Semantic classification from configured model for role text: {role or text[:180]}", "rules+semantic"
    return None, None, "rules"


def _relevant_evidence(domain: str | None, technical: list[str], experiences: list[ExperienceRequirement], education: list[EducationRequirement]) -> list[str]:
    types = []
    if technical:
        types.append("technical_skills")
        types.append("github")
    if domain == "Backend Development":
        types.append("backend_projects")
    elif domain == "Frontend Development":
        types.append("frontend_projects")
    elif domain in {"Full-Stack Development", "Software Engineering", "Machine Learning", "Data Science", "Data Engineering", "Mobile Development"}:
        types.append("software_projects")
    if domain == "Competitive Programming" or "Competitive Programming" in technical or "Algorithms" in technical:
        types.append("coding_profiles")
    if domain in {"Machine Learning", "Data Science"}:
        types.append("research_publications")
        types.append("kaggle")
    if domain == "Cloud and DevOps" or any(item in technical for item in ("Cloud Computing", "Docker", "Kubernetes")):
        types.append("cloud_certifications")
    if experiences:
        types.append("work_experience")
    if education:
        types.append("education")
    return list(dict.fromkeys(types))


def analyze_job_description(
    request: JobAnalysisRequest | str,
    semantic_matcher: SentenceTransformerDomainMatcher | None = None,
) -> JobAnalysisResponse:
    """Extract a structured role vector using a deterministic taxonomy and optional semantic fallback."""
    job_text = request.job_description if isinstance(request, JobAnalysisRequest) else request
    role, role_evidence = _title_line(job_text)
    domain, domain_evidence, method = _role_domain_evidence(job_text, role)
    if domain is None and semantic_matcher is not None and semantic_matcher.enabled:
        domain = semantic_matcher.classify_domain(job_text, DOMAIN_CANDIDATES)
        if domain:
            domain_evidence = f"Semantic classification from configured model for role text: {role or job_text[:180]}"
            method = "rules+semantic"

    skills, _ = _extract_skills(job_text)
    required = list(dict.fromkeys(item.skill for item in skills if item.requirement == "required"))
    preferred = list(dict.fromkeys(item.skill for item in skills if item.requirement == "preferred" and item.skill not in required))
    technical = [item.skill for item in skills if item.category != "soft_skills"]
    category_lists = {
        "frameworks": [item.skill for item in skills if item.category == "frameworks"],
        "programming_languages": [item.skill for item in skills if item.category == "programming_languages"],
        "databases": [item.skill for item in skills if item.category == "databases"],
        "tools": [item.skill for item in skills if item.category == "tools"],
        "cloud_technologies": [item.skill for item in skills if item.category == "cloud_technologies"],
        "soft_skills": [item.skill for item in skills if item.category == "soft_skills"],
    }
    soft_skills = []
    for skill in SOFT_SKILLS:
        pattern = re.compile(rf"(?<!\w){re.escape(skill)}(?!\w)", re.I)
        match = pattern.search(job_text)
        if match:
            chunk = next((part for part in _chunks(job_text) if pattern.search(part)), job_text)
            local_match = pattern.search(chunk)
            requirement, cue = _nearest_cue(chunk, local_match.start(), local_match.end()) if local_match else ("required", None)
            priority = 1.0 if requirement == "required" and cue else (0.9 if requirement == "required" else 0.5)
            skills.append(SkillEvidence(skill=skill, requirement=requirement, priority=priority, category="soft_skills", excerpt=chunk, cue=cue))
            soft_skills.append(skill)
            if requirement == "required":
                required.append(skill)
            elif skill not in preferred:
                preferred.append(skill)
    category_lists["soft_skills"] = soft_skills
    priorities = {item.skill: item.priority for item in skills}
    chunks = _chunks(job_text)
    experience = _extract_experience(chunks)
    education = _extract_education(chunks)
    relevant = _relevant_evidence(domain, technical, experience, education)
    vector = JobRequirementVector(
        role=role,
        domain=domain,
        required_skills=required,
        preferred_skills=preferred,
        technical_skills=technical,
        frameworks=category_lists["frameworks"],
        programming_languages=category_lists["programming_languages"],
        databases=category_lists["databases"],
        tools=category_lists["tools"],
        cloud_technologies=category_lists["cloud_technologies"],
        soft_skills=category_lists["soft_skills"],
        skill_priorities=priorities,
        skill_evidence=skills,
        experience_requirements=experience,
        education_requirements=education,
        relevant_evidence=relevant,
        extraction_method=method,
        role_evidence=role_evidence,
        domain_evidence=domain_evidence,
    )
    return JobAnalysisResponse(job_requirements=vector)
