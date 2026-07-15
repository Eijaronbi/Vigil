import asyncio
import json
from datetime import datetime, timedelta, timezone

from celery import shared_task

from backend.config import settings
from backend.database import SessionLocal
from backend.dispatcher.email import EmailDispatcher
from backend.models import DailyReport, DigestQueue, Group, Message, User
from backend.watchers.gmail_watcher import GmailWatcher
from backend.watchers.twitter_watcher import TwitterWatcher


def _get_session():
    return SessionLocal()


@shared_task
def poll_gmail():
    watcher = GmailWatcher(
        client_id=settings.gmail_oauth_client_id,
        client_secret=settings.gmail_oauth_client_secret,
        refresh_token=settings.gmail_oauth_refresh_token,
    )
    raw_messages = asyncio.run(watcher.poll())
    if not raw_messages:
        return 0

    db = _get_session()
    try:
        count = 0
        for msg in raw_messages:
            group = db.query(Group).filter(
                Group.source == "gmail",
                Group.name == msg["group_name"],
            ).first()
            if group is None:
                continue
            db.add(Message(
                group_id=group.id,
                source=msg["source"],
                sender=msg["sender"],
                text=msg["text"],
                timestamp=msg["timestamp"],
            ))
            count += 1
        db.commit()
        return count
    finally:
        db.close()


@shared_task
def poll_twitter():
    db = _get_session()
    try:
        groups = db.query(Group).filter(
            Group.source == "twitter",
            Group.enabled == True,
        ).all()
    finally:
        db.close()

    if not groups:
        return 0

    watcher = TwitterWatcher()
    total = 0
    for group in groups:
        posts = asyncio.run(watcher.poll(group.external_id))
        if not posts:
            continue

        db = _get_session()
        try:
            for post in posts:
                db.add(Message(
                    group_id=group.id,
                    source=post["source"],
                    sender=post["sender"],
                    text=post["text"],
                    timestamp=post["timestamp"],
                ))
                total += 1
            db.commit()
        finally:
            db.close()

    return total


@shared_task
def send_digest():
    db = _get_session()
    try:
        messages = db.query(Message).filter(
            Message.notified == False,
        ).limit(20).all()
        if not messages:
            return 0

        msg_dicts = [
            {
                "group_name": m.group.name if m.group else "?",
                "sender": m.sender,
                "text": m.text,
                "score": m.importance_score,
            }
            for m in messages
        ]

        user = db.query(User).first()
        to_email = user.email if user else "admin@localhost"

        dispatcher = EmailDispatcher(
            client_id=settings.gmail_oauth_client_id,
            client_secret=settings.gmail_oauth_client_secret,
            refresh_token=settings.gmail_oauth_refresh_token,
            to_email=to_email,
        )
        asyncio.run(dispatcher.send_digest(msg_dicts, digest_type="digest"))

        for m in messages:
            m.notified = True
            db.add(DigestQueue(
                message_id=m.id,
                channel="email",
            ))
        db.commit()
        return len(messages)
    finally:
        db.close()


@shared_task
def generate_daily_report():
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    db = _get_session()
    try:
        messages = db.query(Message).filter(
            Message.timestamp >= since,
            Message.importance_score >= settings.importance_threshold,
        ).all()
        if not messages:
            return 0

        user = db.query(User).first()
        to_email = user.email if user else "admin@localhost"

        msg_dicts = [
            {
                "group_name": m.group.name if m.group else "?",
                "sender": m.sender,
                "text": m.text,
                "score": m.importance_score,
            }
            for m in messages
        ]

        dispatcher = EmailDispatcher(
            client_id=settings.gmail_oauth_client_id,
            client_secret=settings.gmail_oauth_client_secret,
            refresh_token=settings.gmail_oauth_refresh_token,
            to_email=to_email,
        )
        asyncio.run(dispatcher.send_digest(msg_dicts, digest_type="daily"))

        by_user: dict[int, list[Message]] = {}
        for m in messages:
            uid = m.group.user_id if m.group else None
            if uid is not None:
                by_user.setdefault(uid, []).append(m)

        for user_id, msgs in by_user.items():
            db.add(DailyReport(
                user_id=user_id,
                date=datetime.now(timezone.utc).date(),
                summary_json=json.dumps([
                    {"sender": m.sender, "text": m.text, "score": m.importance_score}
                    for m in msgs
                ]),
            ))
        db.commit()
        return len(messages)
    finally:
        db.close()
