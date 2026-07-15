from backend.classifier.rules import HybridClassifier, KeywordRule, SenderRule, TopicRule
from backend.schemas import MessageIn


def test_keyword_rule_match():
    rule = KeywordRule(["urgent", "asap"], priority=2)
    msg = MessageIn(source="email", group_name="inbox", sender="alice", text="This is URGENT, reply ASAP")
    score, matches = rule.evaluate(msg)
    assert score == 14.0
    assert set(matches) == {"urgent", "asap"}


def test_keyword_rule_no_match():
    rule = KeywordRule(["urgent", "asap"])
    msg = MessageIn(source="email", group_name="inbox", sender="alice", text="Nothing important here")
    score, matches = rule.evaluate(msg)
    assert score == 0.0
    assert matches == []


def test_sender_rule_match():
    rule = SenderRule(["@boss", "ceo@company.com"], priority=3)
    msg = MessageIn(source="email", group_name="inbox", sender="Boss", text="Let's meet")
    score, matches = rule.evaluate(msg)
    assert score == 30.0
    assert matches == ["boss"]


def test_sender_rule_no_match():
    rule = SenderRule(["boss"])
    msg = MessageIn(source="email", group_name="inbox", sender="spammer", text="Buy now")
    score, matches = rule.evaluate(msg)
    assert score == 0.0
    assert matches == []


def test_topic_rule_match():
    rule = TopicRule(["meeting schedule", "deadline reminder"], priority=1)
    msg = MessageIn(source="email", group_name="inbox", sender="alice", text="Schedule for meeting is set")
    score, matches = rule.evaluate(msg)
    assert score == 5.0
    assert "meeting schedule" in matches


def test_hybrid_classifier():
    kw = KeywordRule(["urgent"], priority=2)
    sr = SenderRule(["boss"], priority=1)
    tr = TopicRule(["project deadline"], priority=1)
    classifier = HybridClassifier(rules=[kw, sr, tr])

    msg = MessageIn(source="email", group_name="inbox", sender="boss", text="URGENT: project deadline moved")
    result = classifier.classify(msg)
    assert result["score"] == 10.0
    assert "SenderRule" in result["matched_rules"]
    assert "KeywordRule" in result["matched_rules"]


def test_hybrid_classifier_score_capped():
    kw = KeywordRule(["urgent", "asap", "critical"], priority=2)
    classifier = HybridClassifier(rules=[kw])
    msg = MessageIn(source="email", group_name="inbox", sender="alice", text="URGENT ASAP CRITICAL")
    result = classifier.classify(msg)
    assert result["score"] == 10.0
