from scripts.train_iitk import select_cohort


def test_cohort_is_exact_dedicated_org_and_spans_rating_range():
    users = [
        {"handle": f"user{i}", "rating": i * 100, "organization": "IIT Kanpur"}
        for i in range(10)
    ]
    users.append(
        {"handle": "other", "rating": 5000, "organization": "Other Kanpur College"}
    )
    result = select_cohort(users, 3)
    assert [u["handle"] for u in result] == ["user0", "user4", "user9"]
    assert select_cohort(users, 1)[0]["handle"] == "user5"
