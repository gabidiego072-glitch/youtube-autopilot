from app.services.metadata.rules import fit_tags, normalize_tags, tags_length, validate_metadata


def test_normalize_tags():
    assert normalize_tags([" Space ", "#space", "", "black hole", "Black Hole"]) == ["Space", "black hole"]


def test_tags_length_counts_commas_and_quotes():
    assert tags_length([]) == 0
    assert tags_length(["ab"]) == 2
    assert tags_length(["ab", "c d"]) == 2 + 1 + (3 + 2)


def test_fit_tags_respects_limit():
    tags = [f"tag{i:03d}" for i in range(100)]
    fitted = fit_tags(tags)
    assert tags_length(fitted) <= 500
    assert fitted == tags[: len(fitted)]


def test_validate_metadata():
    assert validate_metadata("Good title", "desc", ["a"]) == []
    problems = validate_metadata("x" * 101, "<b>", [])
    assert any("Title exceeds" in p for p in problems)
    assert any("'<' or '>'" in p for p in problems)
    assert validate_metadata("  ", "", []) == ["Title is empty."]
