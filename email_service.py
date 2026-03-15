import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import EMAIL_SENDER, EMAIL_APP_PASSWORD, APP_URL


def send_monthly_report(
    to_email: str,
    user_name: str,
    month: str,
    total_spent: float,
    category_breakdown: dict,
    budget_statuses: list,
    ai_summary: str = ""
) -> bool:
    """
    Send a nicely formatted HTML monthly expense report email.
    Returns True on success, False on failure.
    """
    if not EMAIL_SENDER or EMAIL_SENDER == "your_gmail@gmail.com":
        print("[EMAIL] Email not configured. Skipping send.")
        return False

    subject = f"Your Expense Report — {month}"
    html = _build_html(user_name, month, total_spent, category_breakdown, budget_statuses, ai_summary)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Expense Tracker <{EMAIL_SENDER}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        print(f"[EMAIL] Report sent to {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed to send email: {e}")
        return False


def send_custom_message(
    to_email: str,
    user_name: str,
    subject: str,
    message: str
) -> bool:
    """
    Send a custom admin message to a user.
    Returns True on success, False on failure.
    """
    if not EMAIL_SENDER or EMAIL_SENDER == "your_gmail@gmail.com":
        print("[EMAIL] Email not configured. Skipping send.")
        return False

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f5f5f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:600px;margin:32px auto;padding:0 16px;">
    <div style="background:#5b6af0;border-radius:12px 12px 0 0;padding:28px 32px;">
      <h1 style="color:#fff;font-size:20px;font-weight:600;margin:0;">Expense<span style="opacity:0.7;">Tracker</span></h1>
      <p style="color:rgba(255,255,255,0.8);font-size:14px;margin:6px 0 0;">Message from Admin</p>
    </div>
    <div style="background:#fff;border-radius:0 0 12px 12px;padding:32px;border:1px solid #e5e5e0;border-top:none;">
      <p style="font-size:15px;color:#555;margin:0 0 24px;">Hi {user_name},</p>
      <div style="background:#f8f8ff;border-left:3px solid #5b6af0;border-radius:0 8px 8px 0;padding:16px 20px;margin-bottom:24px;">
        <p style="font-size:14px;color:#333;margin:0;line-height:1.7;white-space:pre-wrap;">{message}</p>
      </div>
      <p style="font-size:12px;color:#aaa;text-align:center;margin:24px 0 0;">Expense Tracker &mdash; your personal finance tool</p>
    </div>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Expense Tracker <{EMAIL_SENDER}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        print(f"[EMAIL] Custom message sent to {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed to send custom message: {e}")
        return False


def _build_html(user_name, month, total_spent, category_breakdown, budget_statuses, ai_summary):
    cat_rows = ""
    for cat, amt in category_breakdown.items():
        pct = (amt / total_spent * 100) if total_spent else 0
        cat_rows += f"""
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #f0f0e8;font-size:14px;">{cat}</td>
          <td style="padding:10px 16px;border-bottom:1px solid #f0f0e8;font-size:14px;text-align:right;font-weight:600;">₹{amt:,.0f}</td>
          <td style="padding:10px 16px;border-bottom:1px solid #f0f0e8;font-size:14px;text-align:right;color:#888;">{pct:.1f}%</td>
        </tr>"""

    budget_rows = ""
    if budget_statuses:
        for b in budget_statuses:
            color = "#1D9E75" if b["status"] == "safe" else ("#BA7517" if b["status"] == "warning" else "#E24B4A")
            badge = {"safe": "On track", "warning": "Warning", "exceeded": "Exceeded"}[b["status"]]
            bar_pct = min(b["percent_used"], 100)
            budget_rows += f"""
            <tr>
              <td style="padding:10px 16px;border-bottom:1px solid #f0f0e8;font-size:14px;">{b['category']}</td>
              <td style="padding:10px 16px;border-bottom:1px solid #f0f0e8;font-size:14px;">
                <div style="background:#f0f0e8;border-radius:4px;height:8px;width:100%;max-width:140px;">
                  <div style="background:{color};width:{bar_pct}%;height:8px;border-radius:4px;"></div>
                </div>
              </td>
              <td style="padding:10px 16px;border-bottom:1px solid #f0f0e8;font-size:14px;text-align:right;">₹{b['spent']:,.0f} / ₹{b['limit']:,.0f}</td>
              <td style="padding:10px 16px;border-bottom:1px solid #f0f0e8;font-size:13px;">
                <span style="background:{color}22;color:{color};padding:2px 8px;border-radius:12px;font-weight:500;">{badge}</span>
              </td>
            </tr>"""

    budget_section = ""
    if budget_rows:
        budget_section = f"""
        <h2 style="font-size:16px;font-weight:600;color:#1a1a1a;margin:0 0 12px;">Budget Status</h2>
        <table width="100%" style="border-collapse:collapse;background:#fff;border-radius:10px;border:1px solid #e5e5e0;margin-bottom:28px;">
          <thead>
            <tr style="background:#fafaf8;">
              <th style="text-align:left;padding:10px 16px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Category</th>
              <th style="text-align:left;padding:10px 16px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Progress</th>
              <th style="text-align:right;padding:10px 16px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Spent / Limit</th>
              <th style="padding:10px 16px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Status</th>
            </tr>
          </thead>
          <tbody>{budget_rows}</tbody>
        </table>"""

    ai_section = ""
    if ai_summary:
        ai_section = f"""
        <div style="background:#f0f0ff;border-left:3px solid #5b6af0;border-radius:0 10px 10px 0;padding:16px 20px;margin-bottom:28px;">
          <p style="font-size:13px;font-weight:600;color:#5b6af0;margin:0 0 6px;">AI Insight</p>
          <p style="font-size:14px;color:#333;margin:0;line-height:1.6;">{ai_summary}</p>
        </div>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f5f5f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:600px;margin:32px auto;padding:0 16px;">
    <div style="background:#5b6af0;border-radius:12px 12px 0 0;padding:28px 32px;">
      <h1 style="color:#fff;font-size:20px;font-weight:600;margin:0;">Expense<span style="opacity:0.7;">Tracker</span></h1>
      <p style="color:rgba(255,255,255,0.8);font-size:14px;margin:6px 0 0;">Monthly report for {month}</p>
    </div>
    <div style="background:#fff;border-radius:0 0 12px 12px;padding:32px;border:1px solid #e5e5e0;border-top:none;">
      <p style="font-size:15px;color:#555;margin:0 0 24px;">Hi {user_name}, here's your spending summary for {month}.</p>
      <div style="background:#5b6af0;border-radius:10px;padding:20px 24px;margin-bottom:28px;text-align:center;">
        <p style="color:rgba(255,255,255,0.7);font-size:13px;margin:0 0 4px;">Total spent this month</p>
        <p style="color:#fff;font-size:32px;font-weight:700;margin:0;">₹{total_spent:,.0f}</p>
      </div>
      {ai_section}
      <h2 style="font-size:16px;font-weight:600;color:#1a1a1a;margin:0 0 12px;">Category breakdown</h2>
      <table width="100%" style="border-collapse:collapse;background:#fff;border-radius:10px;border:1px solid #e5e5e0;margin-bottom:28px;">
        <thead>
          <tr style="background:#fafaf8;">
            <th style="text-align:left;padding:10px 16px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Category</th>
            <th style="text-align:right;padding:10px 16px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Amount</th>
            <th style="text-align:right;padding:10px 16px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Share</th>
          </tr>
        </thead>
        <tbody>{cat_rows}</tbody>
      </table>
      {budget_section}
      <div style="text-align:center;margin-top:8px;">
        <a href="{APP_URL}" style="display:inline-block;background:#5b6af0;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:500;">View Full Dashboard</a>
      </div>
      <p style="font-size:12px;color:#aaa;text-align:center;margin:24px 0 0;">Expense Tracker &mdash; your personal finance tool</p>
    </div>
  </div>
</body>
</html>"""