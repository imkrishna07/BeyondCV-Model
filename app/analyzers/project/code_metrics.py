"""Lightweight static code signals; project code is only read as text, never run."""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re

from app.analyzers.project.language_detector import is_source_file


@dataclass
class CodeMetrics:
    meaningful_lines: int = 0
    duplicate_line_count: int = 0
    naming_consistent_files: int = 0
    error_handling_files: list[str] = field(default_factory=list)
    api_files: list[str] = field(default_factory=list)
    database_files: list[str] = field(default_factory=list)
    auth_files: list[str] = field(default_factory=list)
    integration_files: list[str] = field(default_factory=list)
    algorithm_files: list[str] = field(default_factory=list)
    env_usage_files: list[str] = field(default_factory=list)
    secret_pattern_files: list[str] = field(default_factory=list)


_SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?(?:key|token)|secret|password|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
)
_IGNORED_SECRET_VALUES = ("example", "changeme", "change-me", "your_", "your-", "placeholder", "dummy")
_DATABASE_TERMS = re.compile(r"(?i)\b(sqlalchemy|psycopg|mongoose|prisma|typeorm|mysql|postgres(?:ql)?|mongodb|redis|sqlite3?)\b")
_AUTH_TERMS = re.compile(r"(?i)\b(authentication|authorization|jwt|oauth2?|passport|bcrypt|argon2|login)\b")
_API_TERMS = re.compile(r"(?i)(@app\.(?:get|post|put|delete|patch)|@router\.|\b(?:FastAPI|APIRouter|express\s*\(|graphql|rest[_ -]?api)\b|/api/)")
_INTEGRATION_TERMS = re.compile(r"(?i)\b(?:requests\.(?:get|post)|httpx\.|axios\.|fetch\s*\(|stripe|twilio|sendgrid|boto3)\b")
_ALGORITHM_TERMS = re.compile(r"(?i)\b(?:breadth.first|depth.first|bfs|dfs|dynamic programming|dijkstra|a\* search|trie|binary search|quicksort|merge sort)\b")
_ENV_TERMS = re.compile(r"\b(?:os\.getenv|os\.environ|process\.env|import\.meta\.env|env\[['\"][A-Z_])")


def _naming_looks_consistent(path: str) -> bool:
    filename = PurePosixPath(path).stem
    if filename in {"__init__", "index", "main", "app"}:
        return True
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in {".py", ".rb"}:
        return bool(re.fullmatch(r"[a-z][a-z0-9_]*", filename))
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return bool(re.fullmatch(r"[a-z][a-zA-Z0-9_-]*", filename))
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", filename))


def inspect_code(files: dict[str, str]) -> CodeMetrics:
    metrics = CodeMetrics()
    line_counts: Counter[str] = Counter()
    for path, content in files.items():
        if not is_source_file(path):
            continue
        metrics.naming_consistent_files += int(_naming_looks_consistent(path))
        lines = [line.strip() for line in content.splitlines()]
        meaningful = [line for line in lines if line and not line.startswith(("#", "//", "/*", "*", "<!--"))]
        metrics.meaningful_lines += len(meaningful)
        line_counts.update(line for line in meaningful if len(line) >= 30)

        if re.search(r"\b(?:try|catch|except|finally)\b|\braise\s+", content):
            metrics.error_handling_files.append(path)
        if _API_TERMS.search(content):
            metrics.api_files.append(path)
        if _DATABASE_TERMS.search(content):
            metrics.database_files.append(path)
        if _AUTH_TERMS.search(content):
            metrics.auth_files.append(path)
        if _INTEGRATION_TERMS.search(content):
            metrics.integration_files.append(path)
        if _ALGORITHM_TERMS.search(content):
            metrics.algorithm_files.append(path)
        if _ENV_TERMS.search(content):
            metrics.env_usage_files.append(path)
        secret_detected = any(pattern.search(content) for pattern in _SECRET_PATTERNS[:2])
        secret_detected = secret_detected or any(
            not any(placeholder in match.group(0).lower() for placeholder in _IGNORED_SECRET_VALUES)
            for match in _SECRET_PATTERNS[2].finditer(content)
        )
        if secret_detected:
            metrics.secret_pattern_files.append(path)

    metrics.duplicate_line_count = sum(count - 1 for count in line_counts.values() if count > 1)
    for attribute in (
        "error_handling_files", "api_files", "database_files", "auth_files",
        "integration_files", "algorithm_files", "env_usage_files", "secret_pattern_files",
    ):
        setattr(metrics, attribute, sorted(set(getattr(metrics, attribute))))
    return metrics
