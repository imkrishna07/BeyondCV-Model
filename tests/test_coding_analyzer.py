"""Mocked LeetCode and Codeforces API tests; no external network calls are made."""

from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import requests

from app.analyzers.coding.analyzer import analyze_coding_profiles
from app.analyzers.coding.codeforces import fetch_codeforces_profile
from app.analyzers.coding.errors import CodingNetworkError, CodingProfileNotFound, InvalidCodingUsername
from app.analyzers.coding.leetcode import fetch_leetcode_profile
from app.analyzers.coding.normalizer import normalize_codeforces, normalize_leetcode
from app.analyzers.coding.scoring import combine_platform_scores, score_codeforces, score_leetcode
from app.main import app
from app.schemas.coding import CodeforcesProfile, LeetCodeProfile


class LeetCodeCollectorTests(TestCase):
    def test_leetcode_profile_with_data(self) -> None:
        profile_payload = {
            "data": {
                "matchedUser": {
                    "username": "sample_user",
                    "profile": {"ranking": 12345},
                    "submitStats": {"acSubmissionNum": [
                        {"difficulty": "All", "count": 120, "submissions": 300},
                        {"difficulty": "Easy", "count": 40, "submissions": 100},
                        {"difficulty": "Medium", "count": 60, "submissions": 150},
                        {"difficulty": "Hard", "count": 20, "submissions": 50},
                    ]},
                },
                "userContestRanking": {
                    "attendedContestsCount": 12,
                    "rating": 1785.5,
                    "globalRanking": 2345,
                    "topPercentage": 4.2,
                },
            }
        }
        recent_payload = {"data": {"recentAcSubmissionList": [
            {"id": "1", "title": "Two Sum", "titleSlug": "two-sum", "timestamp": "1700000000"}
        ]}}
        responses = [Mock(status_code=200), Mock(status_code=200)]
        responses[0].json.return_value = profile_payload
        responses[1].json.return_value = recent_payload

        with patch("app.analyzers.coding.leetcode.requests.post", side_effect=responses) as post:
            result = fetch_leetcode_profile("sample_user")

        self.assertEqual(result.username, "sample_user")
        self.assertEqual(result.rating, 1785.5)
        self.assertEqual(result.problems_solved, 120)
        self.assertEqual((result.easy, result.medium, result.hard), (40, 60, 20))
        self.assertEqual(result.contests_participated, 12)
        self.assertEqual(len(result.recent_activity), 1)
        self.assertEqual(post.call_count, 2)

    def test_invalid_leetcode_username(self) -> None:
        with self.assertRaises(InvalidCodingUsername):
            fetch_leetcode_profile("has spaces")

    def test_leetcode_network_failure(self) -> None:
        with patch("app.analyzers.coding.leetcode.requests.post", side_effect=requests.ConnectionError("offline")):
            with self.assertRaises(CodingNetworkError):
                fetch_leetcode_profile("sample_user")


class CodeforcesCollectorTests(TestCase):
    def test_codeforces_profile_with_data(self) -> None:
        user_info = [{"handle": "sample_cf", "rating": 1510, "maxRating": 1650, "rank": "specialist", "maxRank": "expert"}]
        rating_history = [
            {"contestName": "Round A", "rank": 500, "oldRating": 1400, "newRating": 1450, "ratingUpdateTimeSeconds": 1700000000},
            {"contestName": "Round B", "rank": 300, "oldRating": 1450, "newRating": 1510, "ratingUpdateTimeSeconds": 1701000000},
        ]
        submissions = [
            {"verdict": "OK", "creationTimeSeconds": 1702000000, "problem": {"contestId": 1, "index": "A", "name": "Easy", "rating": 800}},
            {"verdict": "OK", "creationTimeSeconds": 1702000001, "problem": {"contestId": 1, "index": "A", "name": "Easy", "rating": 800}},
            {"verdict": "OK", "creationTimeSeconds": 1702000002, "problem": {"contestId": 2, "index": "B", "name": "Mid", "rating": 1400}},
            {"verdict": "WRONG_ANSWER", "creationTimeSeconds": 1702000003, "problem": {"contestId": 3, "index": "C", "name": "Unsolved", "rating": 2000}},
            {"verdict": "OK", "creationTimeSeconds": 1702000004, "problem": {"contestId": 4, "index": "A", "name": "Unrated"}},
        ]
        with patch("app.analyzers.coding.codeforces._request", side_effect=[user_info, rating_history, submissions]):
            result = fetch_codeforces_profile("sample_cf")

        self.assertEqual(result.rating, 1510)
        self.assertEqual(result.max_rating, 1650)
        self.assertEqual(result.rank, "specialist")
        self.assertEqual(result.contests_participated, 2)
        self.assertEqual(result.problems_solved, 3)
        distribution = {entry.band: entry.count for entry in result.problem_difficulty_distribution}
        self.assertEqual(distribution["below_1200"], 1)
        self.assertEqual(distribution["1200_1599"], 1)
        self.assertEqual(distribution["unrated"], 1)
        self.assertEqual(result.submissions_sampled, 5)
        self.assertEqual(len(result.recent_contests), 2)

    def test_invalid_codeforces_username(self) -> None:
        with self.assertRaises(InvalidCodingUsername):
            fetch_codeforces_profile("invalid handle")


class CodingNormalizationAndOrchestrationTests(TestCase):
    def test_normalization_and_weighted_score(self) -> None:
        leetcode = LeetCodeProfile(username="lc", rating=1500, problems_solved=100, contests_participated=10)
        codeforces = CodeforcesProfile(username="cf", rating=2000, max_rating=3000, problems_solved=100, contests_participated=10)
        lc_features = score_leetcode(normalize_leetcode(leetcode))
        cf_features = score_codeforces(normalize_codeforces(codeforces))

        self.assertEqual(lc_features.rating, 50)
        self.assertEqual(cf_features.rating, 50)
        self.assertEqual(cf_features.peak_rating, 75)
        self.assertEqual(combine_platform_scores(lc_features, cf_features), round((lc_features.platform_score + cf_features.platform_score) / 2))
        self.assertIsNone(combine_platform_scores(None, None))

    def test_both_profiles_available(self) -> None:
        leetcode = LeetCodeProfile(username="lc", rating=1600, problems_solved=100, contests_participated=5)
        codeforces = CodeforcesProfile(username="cf", rating=1400, max_rating=1500, problems_solved=80, contests_participated=8)
        with (
            patch("app.analyzers.coding.analyzer.fetch_leetcode_profile", return_value=leetcode),
            patch("app.analyzers.coding.analyzer.fetch_codeforces_profile", return_value=codeforces),
        ):
            result = analyze_coding_profiles("lc", "cf")
        self.assertEqual(result.leetcode_status, "available")
        self.assertEqual(result.codeforces_status, "available")
        self.assertIsNotNone(result.coding_score)
        self.assertIsNotNone(result.normalized_features.leetcode)
        self.assertIsNotNone(result.normalized_features.codeforces)

    def test_only_leetcode_available(self) -> None:
        leetcode = LeetCodeProfile(username="lc", rating=1600, problems_solved=100)
        with patch("app.analyzers.coding.analyzer.fetch_leetcode_profile", return_value=leetcode):
            result = analyze_coding_profiles(leetcode_username="lc")
        self.assertEqual(result.leetcode_status, "available")
        self.assertEqual(result.codeforces_status, "not_provided")
        self.assertIsNone(result.normalized_features.codeforces)
        self.assertIsNotNone(result.coding_score)

    def test_only_codeforces_available(self) -> None:
        codeforces = CodeforcesProfile(username="cf", rating=1400, max_rating=1500, problems_solved=80, contests_participated=8)
        with patch("app.analyzers.coding.analyzer.fetch_codeforces_profile", return_value=codeforces):
            result = analyze_coding_profiles(codeforces_username="cf")
        self.assertEqual(result.leetcode_status, "not_provided")
        self.assertEqual(result.codeforces_status, "available")
        self.assertIsNone(result.normalized_features.leetcode)
        self.assertIsNotNone(result.coding_score)

    def test_neither_profile_available_is_not_scored_as_zero(self) -> None:
        result = analyze_coding_profiles()
        self.assertEqual(result.leetcode_status, "not_provided")
        self.assertEqual(result.codeforces_status, "not_provided")
        self.assertIsNone(result.coding_score)
        self.assertEqual(result.strengths, [])

    def test_unavailable_profile_is_distinct_from_zero_rating(self) -> None:
        with patch(
            "app.analyzers.coding.analyzer.fetch_leetcode_profile",
            side_effect=CodingProfileNotFound("leetcode", "profile missing"),
        ):
            result = analyze_coding_profiles(leetcode_username="deleted_user")
        self.assertEqual(result.leetcode_status, "not_found")
        self.assertIsNone(result.leetcode)
        self.assertIsNone(result.coding_score)

    def test_endpoint_request_accepts_single_platform(self) -> None:
        leetcode = LeetCodeProfile(username="lc", rating=1500, problems_solved=30)
        with patch("app.analyzers.coding.analyzer.fetch_leetcode_profile", return_value=leetcode):
            with TestClient(app) as client:
                response = client.post("/analyze-coding", json={"leetcode_username": "lc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["codeforces_status"], "not_provided")
        self.assertEqual(response.json()["leetcode"]["username"], "lc")


if __name__ == "__main__":
    unittest.main()
