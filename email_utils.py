import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def send_email(smtp_settings, to_email, subject, html_content):
    """
    Sends an email using the provided SMTP settings.
    smtp_settings: dict with 'server', 'port', 'email', 'password'
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_settings['email']
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(html_content, 'html'))

        # Connect to server
        server = smtplib.SMTP(smtp_settings['server'], smtp_settings['port'])
        server.starttls()
        server.login(smtp_settings['email'], smtp_settings['password'])
        
        # Send email
        server.send_message(msg)
        server.quit()
        
        return True, "Sent successfully"
    except Exception as e:
        return False, str(e)

import imaplib
import email
from datetime import datetime, timedelta

def check_replies(imap_settings, campaigns=None):
    """
    Connects to IMAP and fetches emails from the last 30 days.
    Optimized to fetch headers first, then body only if relevant.
    imap_settings: dict with 'server', 'email', 'password'
    campaigns: list of Campaign objects to filter by subject (optional)
    Returns: list of dicts (replies), or (False, error_message)
    """
    try:
        mail = imaplib.IMAP4_SSL(imap_settings['server'])
        mail.login(imap_settings['email'], imap_settings['password'])
        mail.select('inbox')

        # Optimize: Search only emails from the last 30 days
        since_date = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{since_date}")')
        
        if status != 'OK':
            return False, "Failed to search emails"

        all_email_ids = messages[0].split()
        # Process only the last 50 emails from the search result to avoid timeout
        email_ids = all_email_ids[-50:] if all_email_ids else []

        replies = []
        
        if not email_ids:
            return [], None # No new emails

        for e_id in email_ids:
            try:
                # Optimize: Fetch ONLY headers first to check subject
                _, header_data = mail.fetch(e_id, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE CC)])')
                
                msg_header = None
                for response_part in header_data:
                    if isinstance(response_part, tuple):
                        msg_header = email.message_from_bytes(response_part[1])
                        break
                
                if not msg_header:
                    continue

                # Decode subject
                subject = msg_header['Subject']
                if subject:
                    decoded_list = email.header.decode_header(subject)
                    subject = ""
                    for text, encoding in decoded_list:
                        if isinstance(text, bytes):
                            subject += text.decode(encoding or 'utf-8', errors='ignore')
                        else:
                            subject += text
                else:
                    subject = "(No Subject)"

                # Filter logic: Check if subject relates to any campaign
                is_relevant = False
                campaign_id = None
                
                if campaigns:
                    for campaign in campaigns:
                        # Simple check: if campaign subject is in reply subject (ignoring Re:)
                        if campaign.template and campaign.template.subject and campaign.template.subject in subject:
                            is_relevant = True
                            campaign_id = campaign.id
                            break
                else:
                    is_relevant = True

                if is_relevant:
                    # NOW fetch the full content (or at least the body structure)
                    # We use RFC822 to easily parse everything including attachments check
                    _, msg_data = mail.fetch(e_id, '(RFC822)')
                    msg = email.message_from_bytes(msg_data[0][1])

                    sender = msg.get('From')
                    date = msg.get('Date')
                    cc = msg.get('Cc')
                    
                    # Extract content
                    content = ""
                    has_attachments = False
                    
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            
                            if "attachment" in content_disposition:
                                has_attachments = True
                                continue

                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    content += payload.decode(errors='ignore')
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            content = payload.decode(errors='ignore')

                    replies.append({
                        'sender': sender,
                        'subject': subject,
                        'content': content,
                        'campaign_id': campaign_id,
                        'date': date,
                        'cc': cc,
                        'has_attachments': has_attachments
                    })
            except Exception as inner_e:
                print(f"Error processing email {e_id}: {inner_e}")
                continue 

        mail.close()
        mail.logout()
        
        return replies, None
    except Exception as e:
        return False, f"IMAP Error: {str(e)}"
