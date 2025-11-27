from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# Association table for Contact <-> ContactGroup
contact_group_association = db.Table('contact_group_association',
    db.Column('contact_id', db.Integer, db.ForeignKey('contact.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('contact_group.id'), primary_key=True)
)

class ContactGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    company = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, unsubscribed, bounced
    tags = db.Column(db.String(200), nullable=True) # Comma separated tags
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    groups = db.relationship('ContactGroup', secondary=contact_group_association, lazy='subquery',
        backref=db.backref('contacts', lazy=True))

class Template(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False) # HTML content
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('template.id'), nullable=False)
    target_group_id = db.Column(db.Integer, db.ForeignKey('contact_group.id'), nullable=True) # Null = All Contacts
    status = db.Column(db.String(20), default='draft') # draft, sending, completed, failed
    sent_count = db.Column(db.Integer, default=0)
    total_contacts = db.Column(db.Integer, default=0)  # Total contacts to send to (for progress tracking)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    template = db.relationship('Template', backref=db.backref('campaigns', lazy=True))
    target_group = db.relationship('ContactGroup', backref=db.backref('campaigns', lazy=True))

class EmailLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=True)
    recipient_email = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default='sent') # sent, failed, replied
    type = db.Column(db.String(20), default='campaign') # campaign, followup, resend
    error_message = db.Column(db.String(500), nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    campaign = db.relationship('Campaign', backref=db.backref('logs', lazy=True))

class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'), nullable=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=True)
    sender_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=True)
    content = db.Column(db.Text, nullable=True)
    cc = db.Column(db.String(200), nullable=True)
    has_attachments = db.Column(db.Boolean, default=False)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    campaign = db.relationship('Campaign', backref=db.backref('replies', lazy=True))

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    smtp_server = db.Column(db.String(100), default='smtp.gmail.com')
    smtp_port = db.Column(db.Integer, default=587)
    replies_port = db.Column(db.Integer, default=5000)  # Port for replies server
    smtp_email = db.Column(db.String(120), nullable=True)
    smtp_password = db.Column(db.String(120), nullable=True)
    imap_server = db.Column(db.String(100), default='imap.gmail.com')

class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # e.g. "Main Server"
    smtp_server = db.Column(db.String(100), nullable=False)
    smtp_port = db.Column(db.Integer, default=587)
    smtp_email = db.Column(db.String(120), nullable=False)
    smtp_password = db.Column(db.String(120), nullable=False)
    imap_server = db.Column(db.String(100), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

from flask_login import UserMixin

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) # Plain text for now as requested

