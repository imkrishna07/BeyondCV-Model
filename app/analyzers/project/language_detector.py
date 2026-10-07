"""Programming language and framework-neutral source file detection."""

from collections import Counter
from pathlib import PurePosixPath


LANGUAGE_BY_EXTENSION = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".c": "C",
    ".h": "C/C++", ".hpp": "C++", ".swift": "Swift", ".scala": "Scala",
    ".r": "R", ".R": "R", ".sql": "SQL", ".dart": "Dart", ".vue": "Vue",
    ".svelte": "Svelte", ".sh": "Shell", ".html": "HTML", ".css": "CSS",
}


def detect_languages(files: dict[str, str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in files:
        language = LANGUAGE_BY_EXTENSION.get(PurePosixPath(path).suffix)
        if language:
            counts[language] += 1
    return dict(sorted(counts.items()))


def is_source_file(path: str) -> bool:
    return PurePosixPath(path).suffix in LANGUAGE_BY_EXTENSION
