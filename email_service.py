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