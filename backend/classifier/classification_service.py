from sqlalchemy.orm import Session
from backend.models import Group, Rule, Message
from backend.schemas import MessageIn
from backend.classifier.rules import KeywordRule, SenderRule, TopicRule, HybridClassifier
from backend.classifier.llm_scorer import LLMScorer
from backend.config import settings


def build_classifier_for_group(db: Session, group_id: int) -> HybridClassifier:
    rules = db.query(Rule).filter(Rule.group_id == group_id).all()
    classifier_rules = []
    for r in rules:
        if r.rule_type == "keyword":
            keywords = [k.strip() for k in r.value.split(",")]
            classifier_rules.append(KeywordRule(keywords=keywords, priority=r.priority))
        elif r.rule_type == "sender":
            senders = [s.strip() for s in r.value.split(",")]
            classifier_rules.append(SenderRule(priority_senders=senders, priority=r.priority))
        elif r.rule_type == "topic":
            topics = [t.strip() for t in r.value.split(",")]
            classifier_rules.append(TopicRule(topic_descriptions=topics, priority=r.priority))
    return HybridClassifier(rules=classifier_rules)


async def classify_message(db: Session, msg: Message, message_in: MessageIn):
    classifier = build_classifier_for_group(db, msg.group_id or 0)
    rule_result = classifier.classify(message_in)
    msg.importance_score = rule_result["score"]

    if rule_result["score"] >= settings.importance_threshold:
        scorer = LLMScorer(api_key=settings.openrouter_api_key, model=settings.openrouter_model)
        llm_result = await scorer.score(
            text=message_in.text,
            sender=message_in.sender,
            group_name=message_in.group_name,
        )
        msg.importance_score = max(msg.importance_score, llm_result.get("score", 0))
        msg.summary = llm_result.get("summary", "")

        if msg.importance_score >= settings.importance_threshold:
            from backend.dispatcher.telegram import TelegramDispatcher
            dispatcher = TelegramDispatcher(
                bot_token=settings.telegram_bot_token,
                chat_id="",
            )
            await dispatcher.send_alert(
                group_name=message_in.group_name,
                sender=message_in.sender,
                text=message_in.text,
                summary=msg.summary,
                score=msg.importance_score,
            )
            msg.notified = True

            from backend.websocket_manager import ws_manager
            await ws_manager.broadcast({
                "type": "alert",
                "group": message_in.group_name,
                "sender": message_in.sender,
                "summary": msg.summary,
                "score": msg.importance_score,
            })

            # On-chain attestation (non-blocking)
            try:
                from backend.onchain import onchain_client
                tx_hash = onchain_client.attest_alert(
                    text=message_in.text,
                    group=message_in.group_name,
                    timestamp=int(msg.timestamp.timestamp()),
                    score=msg.importance_score,
                )
                if tx_hash:
                    print(f"Attested on-chain: {tx_hash}")
            except Exception as e:
                print(f"On-chain attestation failed: {e}")

    db.commit()
