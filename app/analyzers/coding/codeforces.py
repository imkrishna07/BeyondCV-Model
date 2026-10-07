"""Codeforces public API collection with in-process request pacing."""

from datetime import datetime, timezone
import re
import threading
import time
from typing import Any

import requests

from app.analyzers.coding.errors import (
    CodingAPIError,
    CodingNetworkError,
    CodingProfileNotFound,
    CodingRateLimitError,
    InvalidCodingUsername,
)
from app.schemas.coding import (
    CodeforcesContest,
    CodeforcesProfile,
    CodingActivityItem,
    ProblemDifficultyCount,
)


CODEFORCES_API = "https://codeforces.com/api"
TIMEOUT_SECONDS = 12
MAX_SUBMISSIONS = 1000
MIN_REQUEST_INTERVAL_SECONDS = 2.1
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_request_lock = threading.Lock()
_last_request_time = 0.0


def _request(method: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    global _last_request_time
    with _request_lock:
        wait = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_time)
        if wait > 0:
            time.sleep(wait)
        try:
            response = requests.get(
                f"{CODEFORCES_API}/{method}", params=params,
                timeout=TIMEOUT_SECONDS, headers={"User-Agent": "BeyondCV coding profile analyzer"},
            )
        except (requests.Timeout, requests.ConnectionError, requests.RequestException) as exc:
            raise CodingNetworkError("codeforces", "Could not connect to Codeforces.") from exc
        finally:
            _last_request_time = time.monotonic()

    if response.status_code == 429:
        raise CodingRateLimitError("codeforces", "Codeforces temporarily rate-limited the request.")
    if response.status_code >= 400:
        if response.status_code in {404}:
            raise CodingProfileNotFound("codeforces", "Codeforces profile was not found or is unavailable.")
        if response.status_code == 403:
            raise CodingRateLimitError("codeforces", "Codeforces denied the request; it may be rate-limited.")
        raise CodingAPIError("codeforces", f"Codeforces returned HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise CodingAPIError("codeforces", "Codeforces returned an unreadable response.") from exc
    if not isinstance(payload, dict):
        raise CodingAPIError("codeforces", "Codeforces returned an unexpected response.")
    if payload.get("status") != "OK":
        comment = str(payload.get("comment", ""))
        lowered = comment.lower()
        if "limit" in lowered or "too many" in lowered:
            raise CodingRateLimitError("codeforces", "Codeforces API rate limit reached. Try again later.")
        if "not found" in lowered or "handle" in lowered and "found" in lowered:
            raise CodingProfileNotFound("codeforces", "Codeforces profile was not found or is unavailable.")
        raise CodingAPIError("codeforces", "Codeforces API could not provide the requested data.")
    result = payload.get("result")
    if not isinstance(result, list):
        raise CodingAPIError("codeforces", "Codeforces returned an unexpected result format.")
    return result


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _date(seconds: object) -> datetime | None:
    timestamp = _as_int(seconds)
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _problem_key(problem: dict[str, Any]) -> str | None:
    contest = problem.get("contestId")
    index = problem.get("index")
    if contest is None or index is None:
        return None
    return f"{contest}:{index}"


def _difficulty_band(rating: int | None) -> str:
    if rating is None:
        return "unrated"
    if rating < 1200:
        return "below_1200"
    if rating < 1600:
        return "1200_1599"
    if rating < 2000:
        return "1600_1999"
    if rating < 2400:
        return "2000_2399"
    return "2400_plus"


def fetch_codeforces_profile(username: str) -> CodeforcesProfile:
    """Read public user details, rating history, and a bounded recent submission sample."""
    clean_username = username.strip()
    if not USERNAME_PATTERN.fullmatch(clean_username):
        raise InvalidCodingUsername("codeforces", "Codeforces handle has an invalid format.")

    user_rows = _request("user.info", {"handles": clean_username})
    if not user_rows:
        raise CodingProfileNotFound("codeforces", "Codeforces profile was not found or is unavailable.")
    user = user_rows[0]
    returned_handle = str(user.get("handle", ""))
    if returned_handle.casefold() != clean_username.casefold():
        raise CodingProfileNotFound("codeforces", "Codeforces profile was not found or is unavailable.")

    contests = _request("user.rating", {"handle": returned_handle})
    submissions = _request("user.status", {"handle": returned_handle, "from": 1, "count": MAX_SUBMISSIONS})

    solved: dict[str, dict[str, Any]] = {}
    recent_activity: list[CodingActivityItem] = []
    for submission in submissions:
        if not isinstance(submission, dict):
            continue
        problem = submission.get("problem")
        if not isinstance(problem, dict):
            continue
        if submission.get("verdict") == "OK":
            key = _problem_key(problem)
            if key:
                solved[key] = problem
        if len(recent_activity) < 10:
            recent_activity.append(CodingActivityItem(
                kind="submission",
                name=problem.get("name"),
                timestamp=_date(submission.get("creationTimeSeconds")),
                verdict=submission.get("verdict"),
            ))

    bands = {name: 0 for name in ("below_1200", "1200_1599", "1600_1999", "2000_2399", "2400_plus", "unrated")}
    for problem in solved.values():
        bands[_difficulty_band(_as_int(problem.get("rating")))] += 1

    parsed_contests = [
        CodeforcesContest(
            name=str(contest.get("contestName", "")),
            rank=_as_int(contest.get("rank")),
            old_rating=_as_int(contest.get("oldRating")),
            new_rating=_as_int(contest.get("newRating")),
            date=_date(contest.get("ratingUpdateTimeSeconds")),
        )
        for contest in contests if isinstance(contest, dict)
    ]
    parsed_contests.reverse()
    rating = _as_int(user.get("rating"))
    max_rating = _as_int(user.get("maxRating"))
    return CodeforcesProfile(
        username=returned_handle,
        rating=rating,
        max_rating=max_rating,
        rank=user.get("rank"),
        max_rank=user.get("maxRank"),
        contests_participated=len(contests),
        problems_solved=len(solved),
        problem_difficulty_distribution=[
            ProblemDifficultyCount(band=band, count=count) for band, count in bands.items()
        ],
        recent_contests=parsed_contests[:5],
        recent_activity=recent_activity,
        submissions_sampled=len(submissions),
    )
