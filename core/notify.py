"""
core/notify.py — Telegram + Gmail delivery for The Currents.

Merged from delivery/__init__.py + uploaded notify.py.
Adds: metrics report to Telegram, metrics table in email,
      separate HI PDF attachment, proper captions.
"""
from __future__ import annotations

import contextlib, json, os, smtplib, time
from email.mime.application import MIMEApplication
from email.mime.multipart   import MIMEMultipart
from email.mime.text        import MIMEText
from pathlib                import Path
from typing                 import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from core.metrics import Metrics

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
_SITE        = os.environ.get("SITE_URL", "https://adityakr2024.github.io/aarambh/")


# ── Telegram helpers ──────────────────────────────────────────────────────────
def _tg(method: str, **kwargs) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {}
    url = TELEGRAM_API.format(token=token, method=method)
    try:
        r = requests.post(url, timeout=30, **kwargs)
        return r.json()
    except Exception as e:
        print(f"  Telegram error ({method}): {e}")
        return {}


def _esc(text: str) -> str:
    """Escape for Telegram MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(
    articles:    list[dict],
    date_str:    str,
    pdf_path:    "Path | None",
    pdf_hi_path: "Path | None",
    image_paths: list[Path],
    metrics:     "Metrics | None" = None,
) -> bool:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        print("⚠ TELEGRAM_CHAT_ID not set — skipping Telegram.")
        return False

    # Message 1: Headlines list
    lines = [f"📰 *UPSC Current Affairs — {_esc(date_str)}*\n"]
    for i, art in enumerate(articles, 1):
        fc      = art.get("fact_check", {}).get("status", "")
        fc_icon = {"verified": "✅", "likely_accurate": "🔵",
                   "unverified": "🟡", "suspicious": "🔴"}.get(fc, "⚪")
        topics  = " · ".join(art.get("upsc_topics", [])[:2])
        lines.append(f"{i:02d}\\. {fc_icon} *{_esc(art['title'][:80])}*")
        if topics:
            lines.append(f"   _{_esc(topics)}_")
        lines.append("")
    if _SITE:
        lines.append(f"🌐 [View on website]({_SITE})")

    _tg("sendMessage", data={
        "chat_id":    chat_id,
        "text":       "\n".join(lines),
        "parse_mode": "MarkdownV2",
    })
    print("  ✅ Telegram: headlines sent")
    time.sleep(1)

    # Message 2: Metrics report
    if metrics:
        _tg("sendMessage", data={
            "chat_id":    chat_id,
            "text":       f"<pre>{metrics.telegram_report()}</pre>",
            "parse_mode": "HTML",
        })
        print("  ✅ Telegram: metrics sent")
        time.sleep(1)

    # Message 3: English PDF
    if pdf_path and pdf_path.exists():
        with open(pdf_path, "rb") as f:
            _tg("sendDocument", data={
                "chat_id": chat_id,
                "caption": f"📄 The Currents (English) — {date_str}",
            }, files={"document": (pdf_path.name, f, "application/pdf")})
        print("  ✅ Telegram: EN PDF sent")
        time.sleep(1)

    # Message 4: Hindi PDF
    if pdf_hi_path and pdf_hi_path.exists():
        with open(pdf_hi_path, "rb") as f:
            _tg("sendDocument", data={
                "chat_id": chat_id,
                "caption": f"📄 The Currents (हिन्दी) — {date_str}",
            }, files={"document": (pdf_hi_path.name, f, "application/pdf")})
        print("  ✅ Telegram: HI PDF sent")
        time.sleep(1)

    # Messages 5+: Social post images (batches of 10)
    valid_imgs = [p for p in image_paths if p.exists()]
    for start in range(0, len(valid_imgs), 10):
        batch = valid_imgs[start:start + 10]
        media, files = [], {}
        with contextlib.ExitStack() as stack:
            for j, img in enumerate(batch):
                key = f"img{j}"
                fh  = stack.enter_context(open(img, "rb"))
                media.append({"type": "photo", "media": f"attach://{key}"})
                files[key] = (img.name, fh, "image/jpeg")
            media[0]["caption"] = (
                f"🖼 Posts {start+1}–{start+len(batch)} of {len(valid_imgs)}"
            )
            _tg("sendMediaGroup",
                data={"chat_id": chat_id, "media": json.dumps(media)},
                files=files)
        print(f"  ✅ Telegram: images {start+1}–{start+len(batch)} sent")
        time.sleep(2)

    return True


# ── Gmail ─────────────────────────────────────────────────────────────────────
def send_email(
    articles:    list[dict],
    date_str:    str,
    pdf_path:    "Path | None",
    pdf_hi_path: "Path | None",
    metrics:     "Metrics | None" = None,
) -> bool:
    addr = os.environ.get("GMAIL_SENDER",       "")
    pwd  = os.environ.get("GMAIL_APP_PASSWORD", "")
    to   = os.environ.get("GMAIL_RECIPIENT",    addr)
    if not addr or not pwd:
        print("⚠ Gmail credentials not set — skipping email.")
        return False

    # Metrics block
    metrics_html = ""
    if metrics:
        md = metrics.to_dict()
        provider_rows = "".join(
            f"<tr><td style='padding:3px 14px 3px 0;color:#aaa'>{name}</td>"
            f"<td style='color:#fff'>calls:{p['calls']} err:{p['errors']} "
            f"tokens:{p['total_tokens']:,} avg:{p['avg_latency_s']}s</td></tr>"
            for name, p in md.get("providers", {}).items()
        )
        metrics_html = f"""
        <div style="background:#0D1B2A;color:#ccc;padding:20px 24px;margin-top:16px;
                    border-radius:6px;font-family:monospace;font-size:12px">
          <div style="color:#FF9933;font-weight:bold;margin-bottom:10px">📊 Pipeline Metrics</div>
          <table style="border-collapse:collapse;width:100%">
            <tr><td style="padding:3px 14px 3px 0;color:#aaa">Run time</td>
                <td style="color:#fff">{int(metrics.pipeline_duration//60)}m {int(metrics.pipeline_duration%60)}s</td></tr>
            <tr><td style="padding:3px 14px 3px 0;color:#aaa">Fetched</td>
                <td style="color:#fff">{md['articles_fetched']}</td></tr>
            <tr><td style="padding:3px 14px 3px 0;color:#aaa">Filtered (UPSC)</td>
                <td style="color:#fff">{md['articles_filtered']}</td></tr>
            <tr><td style="padding:3px 14px 3px 0;color:#aaa">Total API calls</td>
                <td style="color:#fff">{md['total_calls']}</td></tr>
            <tr><td style="padding:3px 14px 3px 0;color:#aaa">Errors / Fallbacks</td>
                <td style="color:#fff">{md['total_errors']} / {md['fallbacks_used']}</td></tr>
            <tr><td style="padding:3px 14px 3px 0;color:#aaa">Prompt tokens</td>
                <td style="color:#fff">{md['prompt_tokens']:,}</td></tr>
            <tr><td style="padding:3px 14px 3px 0;color:#aaa">Output tokens</td>
                <td style="color:#fff">{md['completion_tokens']:,}</td></tr>
            <tr><td style="padding:3px 14px 3px 0;color:#aaa">Total tokens</td>
                <td style="color:#fff"><strong style="color:#FF9933">{md['total_tokens']:,}</strong></td></tr>
            {provider_rows}
          </table>
        </div>"""

    # Article rows
    rows = ""
    for i, art in enumerate(articles, 1):
        status = art.get("fact_check", {}).get("status", "unverified")
        colors = {"verified": "#27ae60", "likely_accurate": "#2980b9",
                  "unverified": "#f39c12", "suspicious": "#e74c3c"}
        bc     = colors.get(status, "#888")
        topics = " · ".join(art.get("upsc_topics", [])[:3])
        ctx    = (art.get("context") or art.get("summary", ""))[:350]
        rows  += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:14px 8px;vertical-align:top;width:32px;
                     color:#FF9933;font-weight:bold;font-size:16px">{i:02d}</td>
          <td style="padding:14px 8px">
            <a href="{art.get('url','#')}" style="color:#0D1B2A;text-decoration:none;
               font-weight:bold;font-size:14px">{art['title']}</a>
            <p style="color:#555;font-size:12px;margin:5px 0 4px">{ctx}</p>
            <span style="font-size:10px;color:#888">{art.get('source','')} · {art.get('published','')}</span>&nbsp;
            <span style="background:{bc};color:white;padding:1px 7px;border-radius:3px;
                         font-size:10px">✓ {status}</span>
            <br><span style="color:#FF9933;font-size:10px">{topics}</span>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:800px;margin:auto;background:#f5f5f5">
  <div style="background:#0D1B2A;padding:20px 28px">
    <h1 style="color:#FF9933;margin:0;font-size:20px">📰 The Currents — UPSC Current Affairs</h1>
    <p style="color:#aaa;margin:4px 0 0;font-size:13px">{date_str} · {len(articles)} articles</p>
    {f'<a href="{_SITE}" style="color:#88aaff;font-size:11px">{_SITE}</a>' if _SITE else ''}
  </div>
  <table style="width:100%;background:white;border-collapse:collapse">{rows}</table>
  {metrics_html}
  <p style="text-align:center;color:#aaa;font-size:10px;padding:12px">
    The Currents — auto-generated daily UPSC current affairs
  </p>
</body></html>"""

    msg              = MIMEMultipart("mixed")
    msg["Subject"]   = f"📰 The Currents — UPSC Current Affairs — {date_str}"
    msg["From"]      = addr
    msg["To"]        = to
    msg.attach(MIMEText(html, "html"))

    for pdf, label in [(pdf_path, "EN"), (pdf_hi_path, "HI")]:
        if pdf and pdf.exists():
            with open(pdf, "rb") as f:
                part = MIMEApplication(f.read(), Name=pdf.name)
            part["Content-Disposition"] = f'attachment; filename="{pdf.name}"'
            msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(addr, pwd)
            server.sendmail(addr, to, msg.as_string())
        print("  ✅ Email sent")
        return True
    except Exception as e:
        print(f"  ❌ Email failed: {e}")
        return False


# ── Public entry point ────────────────────────────────────────────────────────
def send_notifications(
    articles:    list[dict],
    date_str:    str,
    pdf_path:    "Path | None",
    pdf_hi_path: "Path | None" = None,
    image_paths: list[Path]    = (),
    metrics:     "Metrics | None" = None,
) -> None:
    print("\n📣 Sending notifications…")
    send_telegram(articles, date_str, pdf_path, pdf_hi_path, list(image_paths), metrics)
    send_email(articles, date_str, pdf_path, pdf_hi_path, metrics)
