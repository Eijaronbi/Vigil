from backend.schemas import MessageIn


class KeywordRule:
    def __init__(self, keywords: list[str], priority: int = 1):
        self.keywords = [k.lower() for k in keywords]
        self.priority = priority

    def evaluate(self, message: MessageIn) -> tuple[float, list[str]]:
        text_lower = message.text.lower()
        matched = [k for k in self.keywords if k in text_lower]
        if matched:
            return (7.0 * self.priority, matched)
        return (0.0, [])


class SenderRule:
    def __init__(self, priority_senders: list[str], priority: int = 1):
        self.priority_senders = [s.lower().removeprefix("@") for s in priority_senders]
        self.priority = priority

    def evaluate(self, message: MessageIn) -> tuple[float, list[str]]:
        sender_lower = message.sender.lower().removeprefix("@")
        matched = [s for s in self.priority_senders if s == sender_lower]
        if matched:
            return (10.0 * self.priority, matched)
        return (0.0, [])


class TopicRule:
    def __init__(self, topic_descriptions: list[str], priority: int = 1):
        self.topics = topic_descriptions
        self.priority = priority

    def evaluate(self, message: MessageIn) -> tuple[float, list[str]]:
        text_lower = message.text.lower()
        matched = []
        for topic in self.topics:
            words = topic.lower().split()
            if not words:
                continue
            count = sum(1 for w in words if w in text_lower)
            if count / len(words) >= 0.5:
                matched.append(topic)
        if matched:
            return (5.0 * self.priority * len(matched), matched)
        return (0.0, [])


class HybridClassifier:
    def __init__(self, rules: list | None = None):
        self.rules = rules or []

    def set_rules(self, rules: list):
        self.rules = rules

    def classify(self, message: MessageIn) -> dict:
        total = 0.0
        matched_rules = []
        for rule in self.rules:
            score, matches = rule.evaluate(message)
            if matches:
                total += score
                matched_rules.append(type(rule).__name__)
        return {"score": min(total, 10.0), "matched_rules": matched_rules}
