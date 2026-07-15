from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Group, Message

router = APIRouter(tags=["dashboard"])

ROW = "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>"


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    messages = (
        db.query(Message)
        .order_by(desc(Message.timestamp))
        .limit(50)
        .all()
    )
    groups = db.query(Group).all()

    group_rows = "\n".join(
        f"<li>{g.source} / {g.name} ({g.external_id})</li>" for g in groups
    )
    msg_rows = "\n".join(
        ROW.format(
            m.source,
            m.group.name if m.group else "",
            m.sender,
            m.text[:100],
            m.importance_score or "",
            m.timestamp.strftime("%Y-%m-%d %H:%M") if m.timestamp else "",
        )
        for m in messages
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Message Monitor</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <h1>Message Monitor</h1>
  <section>
    <h2>Groups</h2>
    <ul>{group_rows}</ul>
  </section>
  <section>
    <h2>Recent Messages</h2>
    <table>
      <thead><tr><th>Source</th><th>Group</th><th>Sender</th><th>Text</th><th>Score</th><th>Timestamp</th></tr></thead>
      <tbody>{msg_rows}</tbody>
    </table>
  </section>
</body>
</html>"""
    return HTMLResponse(html)
