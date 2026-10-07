"""Bounded read-only collection of Kaggle notebooks and datasets."""

import os
import re
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from app.analyzers.kaggle.scoring import SCORE_METHOD, score_kaggle_evidence
from app.schemas.kaggle import (
    KaggleActivity,
    KaggleAnalysisResponse,
    KaggleArtifact,
    KaggleEvidence,
)


BASE_URL = "https://www.kaggle.com/api/v1"
REQUEST_TIMEOUT = 8
MAX_RESULTS = 20


class KaggleError(Exception):
    """Base collector error with safe user-facing text."""


class KaggleProfileNotFound(KaggleError):
    pass


class KaggleRateLimitError(KaggleError):
    pass


class KaggleNetworkError(KaggleError):
    pass


class KaggleAPIError(KaggleError):
    pass


class InvalidKaggleUsername(KaggleError):
    pass


def _auth() -> tuple[str, Any] | None:
    """Read optional Kaggle credentials without returning them to the caller."""
    token = os.getenv("KAGGLE_API_TOKEN")
    if token:
        return "bearer", token
    username, key = os.getenv("KAGGLE_USERNAME"), os.getenv("KAGGLE_KEY")
    if username and key:
        return "basic", HTTPBasicAuth(username, key)
    return None


def _fetch_list(path: str, username: str) -> list[dict[str, Any]]:
    auth = _auth()
    if auth is None:
        raise KaggleAPIError("Kaggle API credentials are not configured.")
    kind, credential = auth
    kwargs: dict[str, Any] = {
        "params": {"user": username, "page": 1, "pageSize": MAX_RESULTS},
        "timeout": REQUEST_TIMEOUT,
    }
    if kind == "bearer":
        kwargs["headers"] = {"Authorization": f"Bearer {credential}"}
    else:
        kwargs["auth"] = credential
    try:
        response = requests.get(f"{BASE_URL}/{path}", **kwargs)
    except requests.RequestException as exc:
        raise KaggleNetworkError("Kaggle could not be reached.") from exc
    if response.status_code == 404:
        raise KaggleProfileNotFound("Kaggle did not find the requested account or resource.")
    if response.status_code == 429:
        raise KaggleRateLimitError("Kaggle API rate limit reached.")
    if response.status_code in (401, 403):
        raise KaggleAPIError("Kaggle API access was denied; check the configured credentials.")
    if response.status_code >= 500:
        raise KaggleNetworkError("Kaggle API is temporarily unavailable.")
    if response.status_code >= 400:
        raise KaggleAPIError("Kaggle API returned an error.")
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise KaggleAPIError("Kaggle API returned invalid data.") from exc
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "kernels", "datasets", "items"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    raise KaggleAPIError("Kaggle API returned an unexpected response.")


def _text(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _artifact(item: dict[str, Any], kind: str, username: str) -> KaggleArtifact:
    title = _text(item, "title", "ref", "slug", "kernelName", "datasetName", "name") or "Untitled"
    slug = _text(item, "ref", "slug")
    if not slug and "/" in title:
        slug = title
    url = _text(item, "url", "htmlUrl", "webUrl")
    if not url and slug:
        url = f"https://www.kaggle.com/{kind}/{slug}"
    tags = item.get("tags") or item.get("topics") or []
    if isinstance(tags, list):
        topics = [str(tag.get("name") or tag.get("label")) if isinstance(tag, dict) else str(tag) for tag in tags]
    else:
        topics = []
    language = _text(item, "language", "languageName")
    description = _text(item, "description", "subtitle", "kernelDescription")
    updated = _text(item, "lastUpdated", "lastUpdatedAt", "updated")
    return KaggleArtifact(
        title=title,
        url=url,
        description=description,
        last_updated=updated,
        topics=topics,
        language=language,
    )


def _skills(notebooks: list[KaggleArtifact], datasets: list[KaggleArtifact]) -> list[str]:
    values = {item.language for item in notebooks if item.language}
    values.update(topic for item in notebooks + datasets for topic in item.topics if topic)
    return sorted(values, key=str.casefold)


def analyze_kaggle_username(username: str) -> KaggleAnalysisResponse:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", username):
        raise InvalidKaggleUsername("Kaggle username contains unsupported characters.")

    if _auth() is None:
        return KaggleAnalysisResponse(
            username=username,
            status="unavailable",
            activity=KaggleActivity(
                competitions=None,
                medals=None,
                notebooks=None,
                datasets=None,
                recent_activity_available=False,
                profile_verified=False,
            ),
            kaggle_score=None,
            score_method=SCORE_METHOD,
            evidence=[KaggleEvidence(
                source="Kaggle API configuration",
                finding="The official Kaggle API requires configured credentials; no profile or activity conclusion was made.",
                fields=["profile", "notebooks", "datasets", "competitions", "medals"],
            )],
            unavailable_fields=["profile details", "competitions", "medals", "notebooks", "datasets", "recent activity"],
        )

    notebooks_raw = _fetch_list("kernels/list", username)
    datasets_raw = _fetch_list("datasets/list", username)
    notebooks = [_artifact(item, "code", username) for item in notebooks_raw]
    datasets = [_artifact(item, "datasets", username) for item in datasets_raw]
    skills = _skills(notebooks, datasets)
    score = score_kaggle_evidence(notebooks, datasets)
    evidence = []
    if notebooks:
        evidence.append(KaggleEvidence(source="Kaggle notebooks API", finding=f"{len(notebooks)} notebook records returned in the bounded sample.", fields=["notebooks"]))
    if datasets:
        evidence.append(KaggleEvidence(source="Kaggle datasets API", finding=f"{len(datasets)} dataset records returned in the bounded sample.", fields=["datasets"]))
    unavailable = ["profile details", "competition participation/results", "medals", "recent activity"]
    return KaggleAnalysisResponse(
        username=username,
        status="available",
        notebooks=notebooks,
        datasets=datasets,
        skills=skills,
        activity=KaggleActivity(
            competitions=None,
            medals=None,
            notebooks=len(notebooks),
            datasets=len(datasets),
            recent_activity_available=False,
            profile_verified=False,
        ),
        kaggle_score=score,
        score_method=SCORE_METHOD,
        strengths=["Returned notebook and dataset metadata provides evidence of Kaggle artifact activity."] if score is not None else [],
        weaknesses=[],
        evidence=evidence,
        unavailable_fields=unavailable,
    )
