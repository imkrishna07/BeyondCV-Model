"""Dependency manifest and common framework/library detection."""

from pathlib import PurePosixPath
import re

from app.schemas.project import ProjectTechnology


MANIFESTS: dict[str, tuple[str, str]] = {
    "requirements.txt": ("Python dependencies", "dependency manifest"),
    "pyproject.toml": ("Python dependencies", "dependency manifest"),
    "pipfile": ("Python dependencies", "dependency manifest"),
    "poetry.lock": ("Python dependencies", "dependency lockfile"),
    "package.json": ("Node.js dependencies", "dependency manifest"),
    "package-lock.json": ("Node.js dependencies", "dependency lockfile"),
    "yarn.lock": ("Node.js dependencies", "dependency lockfile"),
    "pnpm-lock.yaml": ("Node.js dependencies", "dependency lockfile"),
    "pom.xml": ("Maven dependencies", "dependency manifest"),
    "build.gradle": ("Gradle dependencies", "dependency manifest"),
    "build.gradle.kts": ("Gradle dependencies", "dependency manifest"),
    "cargo.toml": ("Cargo dependencies", "dependency manifest"),
    "go.mod": ("Go modules", "dependency manifest"),
    "gemfile": ("Ruby dependencies", "dependency manifest"),
    "composer.json": ("Composer dependencies", "dependency manifest"),
}

FRAMEWORKS: dict[str, tuple[str, tuple[str, ...]]] = {
    "FastAPI": ("framework", ("fastapi",)),
    "Django": ("framework", ("django",)),
    "Flask": ("framework", ("flask",)),
    "React": ("frontend framework", ("react",)),
    "Next.js": ("frontend framework", ("next",)),
    "Vue": ("frontend framework", ("vue",)),
    "Angular": ("frontend framework", ("@angular/",)),
    "Express": ("framework", ("express",)),
    "Spring Boot": ("framework", ("spring-boot", "springframework")),
    "Laravel": ("framework", ("laravel/framework",)),
    "Ruby on Rails": ("framework", ("rails",)),
    "Flutter": ("framework", ("flutter",)),
    "Pytest": ("test framework", ("pytest",)),
    "Jest": ("test framework", ("jest",)),
    "Vitest": ("test framework", ("vitest",)),
}


def detect_dependencies(files: dict[str, str]) -> tuple[list[str], list[ProjectTechnology]]:
    dependency_files: list[str] = []
    technologies: dict[tuple[str, str], set[str]] = {}
    searchable: list[tuple[str, str]] = []
    for path, content in files.items():
        basename = PurePosixPath(path).name.lower()
        if basename in MANIFESTS:
            name, category = MANIFESTS[basename]
            dependency_files.append(path)
            technologies.setdefault((name, category), set()).add(path)
        if basename in MANIFESTS or PurePosixPath(path).suffix.lower() in {
            ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".rb", ".php"
        }:
            searchable.append((path, content.lower()))

    for framework, (category, needles) in FRAMEWORKS.items():
        matches = []
        for path, content in searchable:
            if any(
                needle in content if any(char in needle for char in "@/-")
                else re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", content)
                for needle in needles
            ):
                matches.append(path)
        if matches:
            technologies.setdefault((framework, category), set()).update(matches[:8])

    result = [
        ProjectTechnology(name=name, category=category, evidence_files=sorted(paths))
        for (name, category), paths in sorted(technologies.items())
    ]
    return sorted(dependency_files), result
