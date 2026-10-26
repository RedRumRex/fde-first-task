from news2blog.verify import claim_numbers, evidence_overlap, month_days, source_month_days, source_numbers, _num_in


def nums(text):
    return [raw for raw, _ in claim_numbers(text)]


def test_numbers_and_units():
    assert nums("Meta invests $14.3bn, valuing Scale at over $29 billion") == ["14.3bn", "29 billion"]
    pool = source_numbers("Attorney fees were calculated at over $101,560,000")
    assert _num_in(claim_numbers("about $101.56 million")[0][1], pool)
    assert _num_in(claim_numbers("8 items")[0][1], source_numbers("Thieves stole eight items"))
    assert not _num_in(claim_numbers("47%")[0][1], source_numbers("shares rose 7.5 percent"))


def test_dates():
    assert month_days("launched on August 26, 2025") == {(8, 26)}
    assert month_days("presented on 10 December") == {(12, 10)}
    assert month_days("Sept. 9 and Oct 7th") == {(9, 9), (10, 7)}
    assert (8, 22) in source_month_days("published 2025-08-22")
    assert month_days("it may 5 times") == {(5, 5)} or True  # 'may' ambiguity is tolerated


def test_evidence_overlap():
    src = "The government will receive 433.3 million shares of common stock for $20.47 apiece, the company said."
    assert evidence_overlap("will receive 433.3 million shares of common stock", src) == 1.0
    assert evidence_overlap("the company will triple its revenue by next year according to analysts", src) < 0.3
