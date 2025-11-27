from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from database import db, Contact, Template, Campaign, EmailLog, Reply, Settings, Server, ContactGroup, User
from email_utils import send_email, check_replies
import os
import json
from openpyxl import load_workbook
import glob
import threading
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
import pytz

basedir = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.join(basedir, 'email_templates')

def get_file_templates():
    if not os.path.exists(TEMPLATE_DIR):
        os.makedirs(TEMPLATE_DIR)
    files = glob.glob(os.path.join(TEMPLATE_DIR, '*.html'))
    return [os.path.basename(f) for f in files]

from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = r'sqlite:///email_marketing.db'
app.config['SECRET_KEY'] = 'warzone_secure_key_998877' # Changed to a more "secure" looking key
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# UserMixin for the User model is now directly in database.py

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    # Create default admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='adminpassword')
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created: admin / adminpassword")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        next_url = request.form.get('next')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:
            login_user(user)
            flash('Login successful.', 'success')
            return redirect(next_url or url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
            
    return render_template('login.html', next=request.args.get('next'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    # Fetch stats
    contact_count = Contact.query.filter_by(status='active').count()
    campaign_count = Campaign.query.count()
    
    # Advanced stats
    total_sent = EmailLog.query.filter_by(status='sent').count()
    total_failed = EmailLog.query.filter_by(status='failed').count()
    total_attempts = total_sent + total_failed
    success_rate = round((total_sent / total_attempts * 100), 1) if total_attempts > 0 else 0
    
    # Check replies logic removed to improve performance. 
    # Users can manually check for replies on the Replies page.
    reply_count = Reply.query.count()

    # Today's stats
    try:
        cairo_tz = pytz.timezone("Africa/Cairo")
        today = datetime.now(cairo_tz).date()
    except Exception as e:
        today = datetime.now(timezone.utc).date()
    sent_today = EmailLog.query.filter(db.func.date(EmailLog.sent_at) == today, EmailLog.status == 'sent').count()
    replies_today = Reply.query.filter(db.func.date(Reply.received_at) == today).count()

    # Recent activity
    recent_campaigns = Campaign.query.order_by(Campaign.created_at.desc()).limit(5).all()
    recent_replies = Reply.query.order_by(Reply.received_at.desc()).limit(5).all()

    # Chart Data: Last 7 Days Sent
    daily_stats_labels = []
    daily_stats_values = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        count = EmailLog.query.filter(db.func.date(EmailLog.sent_at) == date, EmailLog.status == 'sent').count()
        daily_stats_labels.append(date.strftime('%d %b'))
        daily_stats_values.append(count)

    # Chart Data: Campaign Status
    campaign_statuses = db.session.query(Campaign.status, db.func.count(Campaign.status)).group_by(Campaign.status).all()
    campaign_stats = {status: count for status, count in campaign_statuses}
    # Ensure all keys exist for the chart
    status_order = ['completed', 'sending', 'failed', 'draft']
    campaign_stats_values = [campaign_stats.get(s, 0) for s in status_order]

    # Follow-ups sent
    followup_count = EmailLog.query.filter_by(status='sent', type='followup').count()

    return render_template('dashboard.html', 
                           contact_count=contact_count, 
                           campaign_count=campaign_count, 
                           reply_count=reply_count,
                           followup_count=followup_count,
                           total_sent=total_sent,
                           success_rate=success_rate,
                           sent_today=sent_today,
                           replies_today=replies_today,
                           recent_campaigns=recent_campaigns,
                           recent_replies=recent_replies,
                           daily_stats_labels=daily_stats_labels,
                           daily_stats_values=daily_stats_values,
                           campaign_stats_values=campaign_stats_values)

@app.route('/replies')
@login_required
def replies():
    # Filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    server_id = request.args.get('server_id')
    
    query = Reply.query
    
    if start_date:
        query = query.filter(Reply.received_at >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        # Add one day to include the end date fully
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        query = query.filter(Reply.received_at < end_dt.replace(day=end_dt.day+1))
        
    # If server_id is provided for filtering (optional, if we want to see replies from specific server)
    if server_id:
        query = query.filter_by(server_id=server_id)

    replies_list = query.order_by(Reply.received_at.desc()).all()
    servers = Server.query.all()
    
    return render_template('replies.html', replies=replies_list, servers=servers, 
                           selected_server_id=int(server_id) if server_id else None,
                           start_date=start_date, end_date=end_date)

@app.route('/check_replies_manual', methods=['POST'])
@login_required
def check_replies_manual():
    server = Server.query.filter_by(is_primary=True).first()
    if not server:
        flash('No primary server configured.', 'error')
        return redirect(url_for('replies'))

    imap_config = {
        'server': server.imap_server,
        'email': server.smtp_email,
        'password': server.smtp_password
    }
    campaigns = Campaign.query.all()
    
    try:
        new_replies, error = check_replies(imap_config, campaigns)
        if error:
            flash(f"Error checking replies: {error}", 'error')
        else:
            count = 0
            if new_replies:
                for r in new_replies:
                    exists = Reply.query.filter_by(sender_email=r['sender'], subject=r['subject'], content=r['content']).first()
                    if not exists:
                        reply = Reply(
                            campaign_id=r['campaign_id'],
                            sender_email=r['sender'],
                            subject=r['subject'],
                            content=r['content'],
                            server_id=server.id,
                            cc=r.get('cc'),
                            has_attachments=r.get('has_attachments', False)
                        )
                        db.session.add(reply)
                        count += 1
                db.session.commit()
            flash(f'Checked for replies. Found {count} new replies.', 'success')
    except Exception as e:
        flash(f"Error checking replies: {str(e)}", 'error')

    return redirect(url_for('replies'))

@app.route('/replies/<int:reply_id>/resend_campaign', methods=['POST'])
@login_required
def resend_campaign_single(reply_id):
    reply = Reply.query.get_or_404(reply_id)
    campaign = Campaign.query.get(reply.campaign_id) if reply.campaign_id else None
    
    if not campaign:
        flash('Associated campaign not found.', 'error')
        return redirect(url_for('replies'))
        
    server = Server.query.filter_by(is_primary=True).first()
    if not server:
        flash('No primary server configured.', 'error')
        return redirect(url_for('replies'))
        
    template = Template.query.get(campaign.template_id)
    if not template:
        flash('Campaign template not found.', 'error')
        return redirect(url_for('replies'))
        
    # Try to find contact for personalization
    _, email_addr = parseaddr(reply.sender_email)
    contact = Contact.query.filter_by(email=email_addr).first()
    name = contact.name if contact else 'Valued Customer'
    
    smtp_config = {
        'server': server.smtp_server,
        'port': server.smtp_port,
        'email': server.smtp_email,
        'password': server.smtp_password
    }
    
    personalized_content = template.content.replace('{{name}}', name)
    
    try:
        success, error = send_email(smtp_config, reply.sender_email, template.subject, personalized_content)
        
        log = EmailLog(
            campaign_id=campaign.id,
            recipient_email=reply.sender_email,
            status='sent' if success else 'failed',
            error_message=None if success else error
        )
        db.session.add(log)
        db.session.commit()
        
        if success:
            flash(f'Campaign resent to {reply.sender_email}.', 'success')
        else:
            flash(f'Failed to resend campaign: {error}', 'error')
            
    except Exception as e:
        flash(f'Error resending campaign: {str(e)}', 'error')
        
    return redirect(url_for('replies'))

@app.route('/replies/<int:reply_id>/followup', methods=['POST'])
@login_required
def send_followup(reply_id):
    reply = Reply.query.get_or_404(reply_id)
    subject = request.form.get('subject')
    content = request.form.get('content')
    
    server = Server.query.filter_by(is_primary=True).first()
    if not server:
        flash('No primary server configured.', 'error')
        return redirect(url_for('replies'))
        
    smtp_config = {
        'server': server.smtp_server,
        'port': server.smtp_port,
        'email': server.smtp_email,
        'password': server.smtp_password
    }
    
    try:
        success, error = send_email(smtp_config, reply.sender_email, subject, content)
        
        log = EmailLog(
            campaign_id=reply.campaign_id,
            recipient_email=reply.sender_email,
            status='sent' if success else 'failed',
            type='followup',
            error_message=None if success else error
        )
        db.session.add(log)
        db.session.commit()
        
        if success:
            flash(f'Follow-up sent to {reply.sender_email}.', 'success')
        else:
            flash(f'Failed to send follow-up: {error}', 'error')
            
    except Exception as e:
        flash(f'Error sending follow-up: {str(e)}', 'error')
        
    return redirect(url_for('replies'))

@app.route('/set_primary_server/<int:server_id>')
@login_required
def set_primary_server(server_id):
    # Unset all
    Server.query.update({Server.is_primary: False})
    # Set new primary
    server = Server.query.get_or_404(server_id)
    server.is_primary = True
    db.session.commit()
    flash(f'Primary server set to {server.name}', 'success')
    return redirect(request.referrer or url_for('replies'))

@app.route('/contacts', methods=['GET', 'POST'])
@login_required
def contacts():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_group':
            group_name = request.form.get('group_name')
            if group_name:
                existing = ContactGroup.query.filter_by(name=group_name).first()
                if not existing:
                    group = ContactGroup(name=group_name)
                    db.session.add(group)
                    db.session.commit()
                    flash(f'Group "{group_name}" created.', 'success')
                else:
                    flash('Group already exists.', 'error')
        
        elif action == 'add_to_group':
            group_id = request.form.get('group_id')
            contact_ids = request.form.getlist('contact_ids') # Assuming checkboxes
            if group_id and contact_ids:
                group = ContactGroup.query.get(group_id)
                count = 0
                for cid in contact_ids:
                    contact = Contact.query.get(cid)
                    if contact and group not in contact.groups:
                        contact.groups.append(group)
                        count += 1
                db.session.commit()
                flash(f'Added {count} contacts to group "{group.name}".', 'success')

        elif action == 'manual_add':
            # Handle manual entry
            manual_entry = request.form.get('manual_entry')
            group_id = request.form.get('group_id') # Optional group assignment on creation
            
            if manual_entry:
                count = 0
                lines = manual_entry.replace(',', '\n').split('\n')
                group = ContactGroup.query.get(group_id) if group_id else None
                
                for line in lines:
                    email = line.strip()
                    if email:
                        existing = Contact.query.filter_by(email=email).first()
                        if not existing:
                            contact = Contact(email=email, name='Unknown')
                            if group:
                                contact.groups.append(group)
                            db.session.add(contact)
                            count += 1
                        elif group and group not in existing.groups:
                            existing.groups.append(group)
                            count += 1 # Count as success if added to group
                db.session.commit()
                flash(f'Successfully processed {count} contacts.', 'success')

        elif action == 'import_file':
            # Handle file upload
            file = request.files.get('file')
            group_id = request.form.get('group_id')
            
            if file:
                try:
                    data = []
                    if file.filename.endswith('.xlsx'):
                        wb = load_workbook(file)
                        sheet = wb.active
                        headers = [cell.value for cell in sheet[1]]
                        for row in sheet.iter_rows(min_row=2, values_only=True):
                            data.append(dict(zip(headers, row)))
                    elif file.filename.endswith('.json'):
                        data = json.load(file)
                    else:
                        flash('Invalid file format. Please upload .xlsx or .json', 'error')
                        return redirect(url_for('contacts'))
                    
                    count = 0
                    group = ContactGroup.query.get(group_id) if group_id else None
                    
                    for row in data:
                        email = row.get('Email') or row.get('email')
                        if email:
                            existing = Contact.query.filter_by(email=email).first()
                            contact = existing
                            if not existing:
                                contact = Contact(
                                    name=row.get('Name') or row.get('name'),
                                    email=email,
                                    company=row.get('Company') or row.get('company')
                                )
                                db.session.add(contact)
                                count += 1
                            
                            if group and group not in contact.groups:
                                contact.groups.append(group)
                                if existing: count += 1 # Count if just added to group
                                
                    db.session.commit()
                    flash(f'Successfully processed {count} contacts.', 'success')
                except Exception as e:
                    flash(f'Error importing contacts: {str(e)}', 'error')
            
    contacts_list = Contact.query.order_by(Contact.created_at.desc()).all()
    groups = ContactGroup.query.all()
    return render_template('contacts.html', contacts=contacts_list, groups=groups)

@app.route('/templates', methods=['GET', 'POST'])
@login_required
def templates():
    if request.method == 'POST':
        name = request.form.get('name')
        subject = request.form.get('subject')
        content = request.form.get('content')
        
        new_template = Template(name=name, subject=subject, content=content)
        db.session.add(new_template)
        db.session.commit()
        flash('Template created successfully.', 'success')
        return redirect(url_for('templates'))

    templates_list = Template.query.order_by(Template.created_at.desc()).all()
    file_templates = get_file_templates()
    return render_template('templates.html', templates=templates_list, file_templates=file_templates)

@app.route('/templates/file/<filename>')
@login_required
def get_template_content(filename):
    try:
        # Security check: ensure filename doesn't contain path separators
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': 'Invalid filename'}), 400
            
        file_path = os.path.join(TEMPLATE_DIR, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/campaigns', methods=['GET', 'POST'])
@login_required
def campaigns():
    if request.method == 'POST':
        name = request.form.get('name')
        template_mode = request.form.get('template_mode')
        target_group_id = request.form.get('target_group_id')
        target_group_id = int(target_group_id) if target_group_id else None
        
        template_id = None
        if template_mode == 'custom':
            custom_subject = request.form.get('custom_subject')
            custom_content = request.form.get('custom_content')
            new_template = Template(name=f"Custom: {name}", subject=custom_subject, content=custom_content)
            db.session.add(new_template)
            db.session.commit()
            template_id = new_template.id
        else:
            file_template = request.form.get('file_template')
            if file_template:
                try:
                    with open(os.path.join(TEMPLATE_DIR, file_template), 'r', encoding='utf-8') as f:
                        content = f.read()
                    new_template = Template(name=f"File: {file_template}", subject=f"Campaign: {name}", content=content)
                    db.session.add(new_template)
                    db.session.commit()
                    template_id = new_template.id
                except Exception as e:
                    flash(f'Error reading template file: {str(e)}', 'error')
                    return redirect(url_for('campaigns'))
            else:
                template_id = request.form.get('template_id')
        
        # Calculate contacts count based on group
        if target_group_id:
            group = ContactGroup.query.get(target_group_id)
            contacts_count = len(group.contacts) if group else 0
        else:
            contacts_count = Contact.query.filter_by(status='active').count()
        
        existing = Campaign.query.filter_by(name=name).first()
        if existing:
            flash(f'A campaign with the name "{name}" already exists. Please use a different name.', 'error')
            return redirect(url_for('campaigns'))
        
        new_campaign = Campaign(name=name, template_id=template_id, status='draft', total_contacts=contacts_count, target_group_id=target_group_id)
        db.session.add(new_campaign)
        db.session.commit()
        
        flash(f'Campaign "{name}" created successfully!', 'success')
        return redirect(url_for('campaigns'))

    campaigns_list = Campaign.query.order_by(Campaign.created_at.desc()).all()
    templates_list = Template.query.all()
    file_templates = get_file_templates()
    groups = ContactGroup.query.all()
    return render_template('campaigns.html', campaigns=campaigns_list, templates=templates_list, file_templates=file_templates, groups=groups)

@app.route('/campaigns/<int:campaign_id>/duplicate', methods=['POST'])
@login_required
def duplicate_campaign(campaign_id):
    original = Campaign.query.get_or_404(campaign_id)
    
    # Create new name
    new_name = f"Copy of {original.name}"
    # Ensure unique name
    counter = 1
    while Campaign.query.filter_by(name=new_name).first():
        new_name = f"Copy of {original.name} ({counter})"
        counter += 1
        
    # Recalculate count
    if original.target_group_id:
        group = ContactGroup.query.get(original.target_group_id)
        contacts_count = len(group.contacts) if group else 0
    else:
        contacts_count = Contact.query.filter_by(status='active').count()
    
    new_campaign = Campaign(
        name=new_name,
        template_id=original.template_id,
        status='draft',
        total_contacts=contacts_count,
        target_group_id=original.target_group_id
    )
    db.session.add(new_campaign)
    db.session.commit()
    
    flash(f'Campaign duplicated as "{new_name}".', 'success')
    return redirect(url_for('campaigns'))

def send_campaign_emails(campaign_id):
    with app.app_context():
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return
        
        server = Server.query.filter_by(is_primary=True).first()
        if not server:
            campaign.status = 'failed'
            db.session.commit()
            print("No primary server configured.")
            return
        
        template = Template.query.get(campaign.template_id)
        if not template:
            campaign.status = 'failed'
            db.session.commit()
            return
        
        template_content = template.content
        template_subject = template.subject
        
        # Filter contacts based on target group
        if campaign.target_group_id:
            # Join with groups to filter
            contacts = Contact.query.join(Contact.groups).filter(ContactGroup.id == campaign.target_group_id, Contact.status == 'active').all()
        else:
            contacts = Contact.query.filter_by(status='active').all()
            
        total_contacts = len(contacts)
        campaign.total_contacts = total_contacts
        campaign.status = 'sending'
        campaign.sent_count = 0
        db.session.commit()
        
        smtp_config = {
            'server': server.smtp_server,
            'port': server.smtp_port,
            'email': server.smtp_email,
            'password': server.smtp_password
        }
        
        sent_count = 0
        failed_count = 0
        
        try:
            for contact in contacts:
                personalized_content = template_content.replace('{{name}}', contact.name or 'Valued Customer')
                
                success, error = send_email(smtp_config, contact.email, template_subject, personalized_content)
                
                log = EmailLog(
                    campaign_id=campaign.id,
                    recipient_email=contact.email,
                    status='sent' if success else 'failed',
                    error_message=None if success else error
                )
                db.session.add(log)
                
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
                
                # Commit progress after every email for real-time updates
                campaign.sent_count = sent_count
                db.session.commit()
            
            campaign.sent_count = sent_count
            campaign.status = 'completed' if sent_count > 0 or total_contacts == 0 else 'failed'
            db.session.commit()
            
        except Exception as e:
            campaign.status = 'failed'
            db.session.commit()
            print(f"Error sending campaign {campaign_id}: {str(e)}")

@app.route('/campaigns/<int:campaign_id>/start', methods=['POST'])
@login_required
def start_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    
    if campaign.status not in ['draft', 'failed']:
        flash('Campaign can only be started if it is in draft or failed status.', 'error')
        return redirect(url_for('campaigns'))
    
    server = Server.query.filter_by(is_primary=True).first()
    if not server:
        flash('Please configure a primary server in Settings before starting a campaign.', 'error')
        return redirect(url_for('settings'))
    
    if campaign.status == 'failed':
        campaign.sent_count = 0
    
    # Set status to sending immediately so UI updates on redirect
    campaign.status = 'sending'
    db.session.commit()
    
    thread = threading.Thread(target=send_campaign_emails, args=(campaign_id,))
    thread.daemon = True
    thread.start()
    
    flash(f'Campaign "{campaign.name}" started.', 'success')
    return redirect(url_for('campaigns'))

@app.route('/campaigns/<int:campaign_id>/progress', methods=['GET'])
@login_required
def get_campaign_progress(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    total = campaign.total_contacts if campaign.total_contacts > 0 else 1
    sent = campaign.sent_count
    progress_percent = round((sent / total * 100), 1) if total > 0 else 0
    return jsonify({
        'status': campaign.status,
        'sent': sent,
        'total': total,
        'progress': progress_percent
    })

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # Add new server
        name = request.form.get('name')
        smtp_server = request.form.get('smtp_server')
        smtp_port = int(request.form.get('smtp_port'))
        smtp_email = request.form.get('smtp_email')
        smtp_password = request.form.get('smtp_password')
        imap_server = request.form.get('imap_server')
        
        # If this is the first server, make it primary
        is_primary = Server.query.count() == 0
        
        new_server = Server(
            name=name,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            smtp_email=smtp_email,
            smtp_password=smtp_password,
            imap_server=imap_server,
            is_primary=is_primary
        )
        db.session.add(new_server)
        db.session.commit()
        flash('Server added successfully.', 'success')
        return redirect(url_for('settings'))
        
    servers = Server.query.all()
    return render_template('settings.html', servers=servers)

@app.route('/contacts/<int:contact_id>/delete', methods=['POST'])
@login_required
def delete_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    db.session.delete(contact)
    db.session.commit()
    flash('Contact deleted successfully.', 'success')
    return redirect(url_for('contacts'))

@app.route('/contacts/<int:contact_id>/edit', methods=['POST'])
@login_required
def edit_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    contact.name = request.form.get('name')
    contact.email = request.form.get('email')
    contact.company = request.form.get('company')
    db.session.commit()
    flash('Contact updated successfully.', 'success')
    return redirect(url_for('contacts'))

@app.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_template(template_id):
    template = Template.query.get_or_404(template_id)
    # Check if used in any campaign
    if Campaign.query.filter_by(template_id=template_id).first():
        flash('Cannot delete template because it is used in a campaign.', 'error')
    else:
        db.session.delete(template)
        db.session.commit()
        flash('Template deleted successfully.', 'success')
    return redirect(url_for('templates'))

@app.route('/templates/<int:template_id>/edit', methods=['POST'])
@login_required
def edit_template(template_id):
    template = Template.query.get_or_404(template_id)
    template.name = request.form.get('name')
    template.subject = request.form.get('subject')
    template.content = request.form.get('content')
    db.session.commit()
    flash('Template updated successfully.', 'success')
    return redirect(url_for('templates'))

@app.route('/campaigns/<int:campaign_id>/delete', methods=['POST'])
@login_required
def delete_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    # Delete associated logs and replies first if needed, or rely on cascade if configured (not configured here)
    # Manually delete logs and replies to be safe
    EmailLog.query.filter_by(campaign_id=campaign_id).delete()
    Reply.query.filter_by(campaign_id=campaign_id).delete()
    db.session.delete(campaign)
    db.session.commit()
    flash('Campaign deleted successfully.', 'success')
    return redirect(url_for('campaigns'))

@app.route('/campaigns/<int:campaign_id>/edit', methods=['POST'])
@login_required
def edit_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    if campaign.status != 'draft':
        flash('Only draft campaigns can be edited.', 'error')
        return redirect(url_for('campaigns'))
    
    campaign.name = request.form.get('name')
    # If we want to allow changing template, we'd need more logic, but for now just name is fine or maybe template_id
    # Let's assume just name for now to keep it simple, or we can add template switching later if requested.
    db.session.commit()
    flash('Campaign updated successfully.', 'success')
    return redirect(url_for('campaigns'))

@app.route('/settings/server/<int:server_id>/delete', methods=['POST'])
@login_required
def delete_server(server_id):
    server = Server.query.get_or_404(server_id)
    if server.is_primary:
        flash('Cannot delete the primary server. Please set another server as primary first.', 'error')
    else:
        # Check if used in replies
        if Reply.query.filter_by(server_id=server_id).first():
             flash('Cannot delete server because it has associated replies. Please clear replies first.', 'error')
        else:
            db.session.delete(server)
            db.session.commit()
            flash('Server deleted successfully.', 'success')
    return redirect(url_for('settings'))

@app.route('/settings/server/<int:server_id>/edit', methods=['POST'])
@login_required
def edit_server(server_id):
    server = Server.query.get_or_404(server_id)
    server.name = request.form.get('name')
    server.smtp_server = request.form.get('smtp_server')
    server.smtp_port = int(request.form.get('smtp_port'))
    server.smtp_email = request.form.get('smtp_email')
    
    # Only update password if provided (not empty)
    new_password = request.form.get('smtp_password')
    if new_password:
        server.smtp_password = new_password
        
    server.imap_server = request.form.get('imap_server')
    db.session.commit()
    flash('Server updated successfully.', 'success')
    return redirect(url_for('settings'))

if __name__ == '__main__':
    app.run(debug=False)
