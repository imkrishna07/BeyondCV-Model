"""Static project analyzer; it inspects text and never executes project code."""

from app.analyzers.project.analyzer import analyze_project_directory, analyze_project_zip

__all__ = ["analyze_project_directory", "analyze_project_zip"]
