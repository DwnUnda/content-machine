from app.services.reddit_feedback import normalise_reddit_feedback_payload


def test_reddit_feedback_requires_repeated_independent_evidence():
    payload = {
        "searched": True,
        "qualified_patterns": [
            {
                "product_name": "Example Dehumidifier",
                "issue": "Noisy fan after several months",
                "feedback_type": "reliability",
                "sentiment": "negative",
                "evidence_comment_count": 3,
                "evidence_thread_count": 1,
                "confidence": "moderate",
                "not_trivially_fixed_reason": "Reported after normal setup and cleaning.",
                "publishable_wording": "Owner discussions mention fan noise developing after several months.",
                "source_urls": ["https://www.reddit.com/r/AusRenovation/comments/example/thread/"],
            },
            {
                "product_name": "Example Dehumidifier",
                "issue": "Hard to empty tank",
                "feedback_type": "usability",
                "sentiment": "negative",
                "evidence_comment_count": 1,
                "evidence_thread_count": 1,
                "confidence": "weak",
                "publishable_wording": "One user disliked the tank.",
                "source_urls": ["https://www.reddit.com/r/example/comments/one/"],
            },
        ],
        "research_sources": [
            {"url": "https://www.reddit.com/r/AusRenovation/comments/example/thread/", "used_for": "fan noise"},
            {"url": "https://example.com/not-reddit", "used_for": "ignored"},
        ],
    }

    result = normalise_reddit_feedback_payload(payload)

    assert len(result["qualified_patterns"]) == 1
    assert result["qualified_patterns"][0]["issue"] == "Noisy fan after several months"
    assert len(result["research_sources"]) == 1
    assert result["policy"]["minimum_comments"] == 3
