"""LeetCode's public GraphQL profile queries, kept isolated from other platforms."""

from datetime import datetime, timezone
import re

import requests

from app.analyzers.coding.errors import (
    CodingAPIError,
    CodingNetworkError,
    CodingProfileNotFound,
    CodingRateLimitError,
    InvalidCodingUsername,
)
from app.schemas.coding import CodingActivityItem, LeetCodeProfile


LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"
TIMEOUT_SECONDS = 12
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,30}$")
PROFILE_QUERY = """
query userCompetitiveProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile { ranking }
    submitStats: submitStatsGlobal {
      acSubmissionNum { difficulty count submissions }
    }
  }
  userContestRanking(username: $username) {
    attendedContestsCount
    rating
    globalRanking
    topPercentage
  }
}
"""
RECENT_ACTIVITY_QUERY = """
query recentAcSubmissions($username: String!) {
  recentAcSubmissionList(username: $username, limit: 20) {
    id
    title
    titleSlug
    timestamp
  }
}
"""
HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com",
    "User-Agent": "BeyondCV public profile analyzer",
}


def _post(query: str, username: str) -> dict:
    try:
        response = requests.post(
            LEETCODE_GRAPHQL_URL,
            json={"query": query, "variables": {"username": username}},
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
        )
    except (requests.Timeout, requests.ConnectionError, requests.RequestException) as exc:
        raise CodingNetworkError("leetcode", "Could not connect to LeetCode.") from exc
    if response.status_code in {403, 429}:
        raise CodingRateLimitError("leetcode", "LeetCode temporarily rate-limited the request.")
    if response.status_code in {404}:
        raise CodingProfileNotFound("leetcode", "LeetCode profile was not found or is unavailable.")
    if response.status_code >= 400:
        raise CodingAPIError("leetcode", f"LeetCode returned HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise CodingAPIError("leetcode", "LeetCode returned an unreadable response.") from exc
    if not isinstance(payload, dict):
        raise CodingAPIError("leetcode", "LeetCode returned an unexpected response.")
    return payload


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_leetcode_profile(username: str) -> LeetCodeProfile:
    """Fetch public LeetCode profile and contest summary; one optional activity query."""
    clean_username = username.strip()
    if not USERNAME_PATTERN.fullmatch(clean_username):
        raise InvalidCodingUsername("leetcode", "LeetCode username has an invalid format.")

    payload = _post(PROFILE_QUERY, clean_username)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    matched = data.get("matchedUser")
    if not isinstance(matched, dict):
        # A null matchedUser is LeetCode's normal response for an unknown handle.
        errors = payload.get("errors") or []
        if isinstance(errors, dict):
            errors = [errors]
        error_messages = " ".join(
            str(error.get("message", "")) for error in errors if isinstance(error, dict)
        ).lower() if isinstance(errors, list) else str(errors).lower()
        if "rate" in error_messages or "too many requests" in error_messages or "throttl" in error_messages:
            raise CodingRateLimitError("leetcode", "LeetCode temporarily rate-limited the request.")
        if "not found" in error_messages or "user does not exist" in error_messages:
            raise CodingProfileNotFound("leetcode", "LeetCode profile was not found or is unavailable.")
        if "matchedUser" in data and matched is None and not errors:
            raise CodingProfileNotFound("leetcode", "LeetCode profile was not found or is unavailable.")
        raise CodingAPIError("leetcode", "LeetCode did not return profile data.")

    stats = matched.get("submitStats") or {}
    accepted = stats.get("acSubmissionNum") or []
    counts = {
        str(item.get("difficulty", "")).lower(): _as_int(item.get("count"))
        for item in accepted if isinstance(item, dict)
    }
    easy, medium, hard = counts.get("easy"), counts.get("medium"), counts.get("hard")
    total = counts.get("all")
    if total is None and any(value is not None for value in (easy, medium, hard)):
        total = sum(value or 0 for value in (easy, medium, hard))

    contest = data.get("userContestRanking") if isinstance(data.get("userContestRanking"), dict) else {}
    profile = matched.get("profile") if isinstance(matched.get("profile"), dict) else {}
    rating = contest.get("rating")
    try:
        rating = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating = None
    percentile = contest.get("topPercentage")
    try:
        percentile = float(percentile) if percentile is not None else None
    except (TypeError, ValueError):
        percentile = None

    recent: list[CodingActivityItem] = []
    recent_available = False
    try:
        recent_payload = _post(RECENT_ACTIVITY_QUERY, clean_username)
        recent_data = recent_payload.get("data") if isinstance(recent_payload.get("data"), dict) else {}
        entries = recent_data.get("recentAcSubmissionList")
        if isinstance(entries, list):
            recent_available = True
            for item in entries:
                if not isinstance(item, dict):
                    continue
                timestamp = _as_int(item.get("timestamp"))
                recent.append(CodingActivityItem(
                    kind="accepted_submission",
                    name=item.get("title") or item.get("titleSlug"),
                    timestamp=datetime.fromtimestamp(timestamp, timezone.utc) if timestamp is not None else None,
                ))
    except CodingRateLimitError:
        # Core profile data is useful even if the optional activity query is throttled.
        recent_available = False
    except (CodingAPIError, CodingNetworkError):
        recent_available = False

    return LeetCodeProfile(
        username=matched.get("username") or clean_username,
        rating=rating,
        profile_rank=_as_int(profile.get("ranking")),
        contest_rank=_as_int(contest.get("globalRanking")),
        contest_top_percentile=percentile,
        contests_participated=_as_int(contest.get("attendedContestsCount")),
        problems_solved=total,
        easy=easy,
        medium=medium,
        hard=hard,
        recent_activity=recent,
        recent_activity_available=recent_available,
    )
