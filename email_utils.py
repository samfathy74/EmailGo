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
        if int(smtp_settings['port']) == 465:
            server = smtplib.SMTP_SSL(smtp_settings['server'], smtp_settings['port'])
        else:
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

def check_replies(imap_settings, campaigns=None, start_date=None, limit=200):
    """
    Connects to IMAP and fetches emails from the specified start date.
    Optimized to fetch headers first, then body only if relevant.
    imap_settings: dict with 'server', 'email', 'password'
    campaigns: list of Campaign objects to filter by subject (optional)
    start_date: datetime object (default: 30 days ago)
    limit: int (default: 200)
    Returns: list of dicts (replies), scanned_count, error_message
    """
    try:
        mail = imaplib.IMAP4_SSL(imap_settings['server'])
        mail.login(imap_settings['email'], imap_settings['password'])
        mail.select('inbox')

        # Use provided start_date or default to 30 days ago
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
            
        since_date_str = start_date.strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{since_date_str}")')
        
        if status != 'OK':
            return [], 0, "Failed to search emails"

        all_email_ids = messages[0].split()
        
        # Apply limit
        limit = int(limit) if limit else 200
        email_ids = all_email_ids[-limit:] if all_email_ids else []
        
        scanned_count = len(email_ids)
        replies = []
        
        if not email_ids:
            return [], 0, None # No new emails

        # Batch fetch headers for all email IDs at once
        # IMAP fetch supports comma-separated IDs or ranges
        # To avoid command line length limits, we can batch in chunks of 50 or 100
        
        batch_size = 50
        # Ensure IDs are bytes for IMAP commands if needed, but usually strings work for library
        # The library returns bytes in split(), so we decode to string for joining
        email_ids_str = [eid.decode() if isinstance(eid, bytes) else str(eid) for eid in email_ids]
        
        for i in range(0, len(email_ids_str), batch_size):
            batch = email_ids_str[i:i + batch_size]
            batch_ids_str = ",".join(batch)
            
            try:
                # Fetch headers for the batch
                # Note: fetch returns a list. Each email part is a tuple (response_header, data)
                # But for multiple emails, it returns a list where items are either tuples (for found parts) or bytes (closing parens)
                status, data = mail.fetch(batch_ids_str, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE CC)])')
                
                if status != 'OK':
                    print(f"Error fetching batch {batch_ids_str}")
                    continue

                for response_part in data:
                    if isinstance(response_part, tuple):
                        # Parse header
                        # response_part[0] is the header line like: b'123 (BODY[HEADER.FIELDS (FROM SUBJECT DATE CC)] {123}'
                        # response_part[1] is the actual content
                        
                        header_info = response_part[0]
                        if isinstance(header_info, bytes):
                            header_info = header_info.decode()
                            
                        # Extract ID from the header info string "123 (BODY..."
                        current_id = header_info.split()[0]
                        
                        msg_header = email.message_from_bytes(response_part[1])
                        
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

                        # Filter logic
                        is_relevant = False
                        campaign_id = None
                        
                        if campaigns:
                            for campaign in campaigns:
                                if campaign.template and campaign.template.subject:
                                    campaign_subject = campaign.template.subject.lower()
                                    reply_subject = subject.lower()
                                    
                                    if campaign_subject in reply_subject:
                                        is_relevant = True
                                        campaign_id = campaign.id
                                        break
                        else:
                            is_relevant = True

                        if is_relevant:
                            # Fetch full content for this specific email
                            # We still do this one by one because it's heavy and only for relevant emails
                            try:
                                _, msg_data = mail.fetch(current_id, '(RFC822)')
                                msg = email.message_from_bytes(msg_data[0][1])

                                sender = msg.get('From')
                                date = msg.get('Date')
                                cc = msg.get('Cc')
                                
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
                            except Exception as fetch_e:
                                print(f"Error fetching body for {current_id}: {fetch_e}")
            except Exception as batch_e:
                print(f"Error fetching batch: {batch_e}")
                continue 

        mail.close()
        mail.logout()
        
        return replies, scanned_count, None
    except Exception as e:
        return False, 0, f"IMAP Error: {str(e)}"
