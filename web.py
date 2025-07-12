from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO
import json
import os
import datetime
import logging
import secrets
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
socketio = SocketIO(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
CONFIG_FILE = 'bot_config.json'
USER_DB_FILE = 'user_database.json'
TEMPLATE_FILE = 'response_templates.json'
ADMIN_FILE = 'admin_credentials.json'

# Default configuration
DEFAULT_CONFIG = {
    'bot_active': False,
    'away_mode': False,
    'response_delay': 1,
    'respond_to_groups': False,
    'last_status_update': datetime.datetime.now().isoformat()
}

# Default templates
DEFAULT_TEMPLATES = {
    'welcome': "👋 Hello! Thanks for messaging me. I'm currently using an auto-responder. How can I help you?",
    'default': "Thanks for your message! I'll get back to you as soon as possible.",
    'away': "I'm currently away but will respond when I return.",
    'keyword_responses': {
        'help|support|assist': "Need help? Please provide more details about what you need assistance with.",
        'price|cost|pricing': "For pricing information, please visit our website or let me know the specific service you're interested in.",
        'schedule|booking|appointment': "To schedule an appointment, please let me know your preferred date and time.",
        'hours|available|when': "I'm typically available Monday-Friday from 9 AM to 5 PM (UTC+0).",
        'thanks|thank you': "You're welcome! Let me know if you need anything else.",
    }
}

# Default admin credentials
DEFAULT_ADMIN = {
    'username': 'admin',
    'password': 'admin',  # Should be changed immediately
    'setup_complete': False
}

# Ensure files exist
def ensure_files_exist():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    
    if not os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, 'w') as f:
            json.dump(DEFAULT_TEMPLATES, f, indent=2)
    
    if not os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, 'w') as f:
            json.dump({}, f, indent=2)
            
    if not os.path.exists(ADMIN_FILE):
        with open(ADMIN_FILE, 'w') as f:
            json.dump(DEFAULT_ADMIN, f, indent=2)

# Load and save functions
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_CONFIG

def save_config(config):
    config['last_status_update'] = datetime.datetime.now().isoformat()
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_templates():
    try:
        with open(TEMPLATE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_TEMPLATES

def save_templates(templates):
    with open(TEMPLATE_FILE, 'w') as f:
        json.dump(templates, f, indent=2)

def load_user_database():
    try:
        with open(USER_DB_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def load_admin_credentials():
    try:
        with open(ADMIN_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_ADMIN

def save_admin_credentials(credentials):
    with open(ADMIN_FILE, 'w') as f:
        json.dump(credentials, f, indent=2)

# Authentication
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    admin = load_admin_credentials()
    error = None
    
    # Check if setup is needed
    if not admin['setup_complete'] and request.method == 'GET':
        return redirect(url_for('setup'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == admin['username'] and password == admin['password']:
            session['logged_in'] = True
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            error = 'Invalid credentials'
    
    return render_template('login.html', error=error)

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    admin = load_admin_credentials()
    
    # If setup is already complete, redirect to login
    if admin['setup_complete']:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            return render_template('setup.html', error='Passwords do not match')
            
        admin['username'] = username
        admin['password'] = password  # In production, this should be hashed
        admin['setup_complete'] = True
        save_admin_credentials(admin)
        
        return redirect(url_for('login'))
        
    return render_template('setup.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    config = load_config()
    templates = load_templates()
    users = load_user_database()
    
    # Count total number of users
    user_count = len(users)
    
    # Count total messages
    message_count = sum(user.get('message_count', 0) for user in users.values())
    
    # Calculate response statistics
    keyword_matches = {}
    for keyword_pattern in templates['keyword_responses'].keys():
        keywords = keyword_pattern.split('|')
        keyword_matches[keywords[0]] = {
            'response': templates['keyword_responses'][keyword_pattern],
            'count': 0  # In a real implementation, you'd track this
        }
    
    return render_template('dashboard.html', 
                          config=config, 
                          templates=templates, 
                          user_count=user_count,
                          message_count=message_count,
                          keyword_matches=keyword_matches)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    config = load_config()
    
    if request.method == 'POST':
        config['bot_active'] = 'bot_active' in request.form
        config['away_mode'] = 'away_mode' in request.form
        config['respond_to_groups'] = 'respond_to_groups' in request.form
        config['response_delay'] = float(request.form['response_delay'])
        
        save_config(config)
        socketio.emit('config_update', config)
        return redirect(url_for('settings'))
    
    return render_template('settings.html', config=config)

@app.route('/templates', methods=['GET', 'POST'])
@login_required
def manage_templates():
    templates = load_templates()
    
    if request.method == 'POST':
        templates['welcome'] = request.form['welcome']
        templates['default'] = request.form['default']
        templates['away'] = request.form['away']
        
        # Handle keyword responses (more complex)
        new_keyword_responses = {}
        for i in range(10):  # Assuming max 10 keyword patterns
            key = f'keyword_pattern_{i}'
            value = f'keyword_response_{i}'
            
            if key in request.form and value in request.form:
                pattern = request.form[key].strip()
                response = request.form[value].strip()
                
                if pattern and response:
                    new_keyword_responses[pattern] = response
        
        templates['keyword_responses'] = new_keyword_responses
        save_templates(templates)
        return redirect(url_for('manage_templates'))
    
    return render_template('templates.html', templates=templates)

@app.route('/users')
@login_required
def user_list():
    users = load_user_database()
    formatted_users = []
    
    for user_id, user_data in users.items():
        # Convert timestamps to more readable format if they exist
        first_contact = user_data.get('first_contact', '')
        last_contact = user_data.get('last_contact', '')
        
        try:
            if first_contact:
                dt = datetime.datetime.fromisoformat(first_contact)
                user_data['first_contact_formatted'] = dt.strftime('%Y-%m-%d %H:%M')
            
            if last_contact:
                dt = datetime.datetime.fromisoformat(last_contact)
                user_data['last_contact_formatted'] = dt.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            # Handle case where timestamp is invalid
            user_data['first_contact_formatted'] = first_contact
            user_data['last_contact_formatted'] = last_contact
        
        # Add user ID to the data
        user_data['id'] = user_id
        formatted_users.append(user_data)
    
    # Sort by last contact time (newest first)
    formatted_users.sort(key=lambda x: x.get('last_contact', ''), reverse=True)
    
    return render_template('users.html', users=formatted_users)

@app.route('/api/toggle-bot', methods=['POST'])
@login_required
def toggle_bot():
    config = load_config()
    data = request.json
    
    if 'active' in data:
        config['bot_active'] = data['active']
        save_config(config)
        socketio.emit('bot_status_update', {'active': config['bot_active']})
        return jsonify({'success': True, 'active': config['bot_active']})
    
    return jsonify({'success': False, 'error': 'Invalid request'})

@app.route('/api/toggle-away', methods=['POST'])
@login_required
def toggle_away():
    config = load_config()
    data = request.json
    
    if 'away' in data:
        config['away_mode'] = data['away']
        save_config(config)
        socketio.emit('away_status_update', {'away': config['away_mode']})
        return jsonify({'success': True, 'away': config['away_mode']})
    
    return jsonify({'success': False, 'error': 'Invalid request'})

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        admin = load_admin_credentials()
        
        if admin['password'] != current_password:
            return render_template('change_password.html', error='Current password is incorrect')
            
        if new_password != confirm_password:
            return render_template('change_password.html', error='New passwords do not match')
            
        admin['password'] = new_password  # In production, this should be hashed
        save_admin_credentials(admin)
        
        return render_template('change_password.html', success=True)
        
    return render_template('change_password.html')

@app.route('/api/bot-status')
def bot_status():
    config = load_config()
    return jsonify({
        'active': config['bot_active'],
        'away': config['away_mode'],
        'last_update': config['last_status_update']
    })

# Initialize
ensure_files_exist()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
