"""
============================================
ROOMMATE MANAGEMENT SYSTEM - FLASK APPLICATION
============================================
File: app.py
Purpose: Main Flask app with all API endpoints
Author: Python Backend
============================================
"""

from flask import Flask, request, jsonify, session, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import secrets
import hashlib
from datetime import datetime, timedelta
import os
import logging
from functools import wraps
import json
from werkzeug.utils import secure_filename
import uuid

# Import database classes
from database import (
    RoommateDatabase, UserManager, ExpenseManager, MarketManager,
    InventoryManager, ChatManager, NotificationManager, BalanceManager,
    SettlementManager, ChoreManager, DashboardManager, initialize_database,
    test_database_connection
)

# ============================================
# INITIALIZATION
# ============================================

app = Flask(__name__)

# BUG FIX 1: Fixed the Secret Key issue.
# Previously, `secrets.token_hex(32)` generated a new key on EVERY server restart, 
# logging out all users instantly. Now it uses a static string if .env is missing.
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'roommate_secret_dev_key_12345')

app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True only if using HTTPS in production
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

# Enable CORS - IMPORTANT: supports_credentials=True is required for cookies
CORS(app, supports_credentials=True, origins=["http://localhost:5500", "http://127.0.0.1:5500", "file://"])

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", manage_session=False)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create upload folder if not exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============================================
# AUTHENTICATION DECORATORS
# ============================================

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def room_required(f):
    """Decorator to check if user has room code"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        room_code = session.get('room_code')
        if not room_code:
            return jsonify({'error': 'No room assigned'}), 400
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# HELPER FUNCTIONS
# ============================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_uploaded_file(file):
    """Save uploaded file and return filename"""
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        return unique_filename
    return None

def generate_room_code():
    """Generate unique room code"""
    return secrets.token_hex(4).upper()

def format_response(success=True, data=None, message=None, error=None):
    """Format API response"""
    response = {'success': success}
    if data is not None:
        response['data'] = data
    if message:
        response['message'] = message
    if error:
        response['error'] = error
    return jsonify(response)

# ============================================
# SOCKET.IO EVENTS
# ============================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('join_room')
def handle_join_room(data):
    """User joins their room chat"""
    room_code = data.get('room_code')
    user_id = data.get('user_id')
    
    if room_code and user_id:
        join_room(room_code)
        # Notify others
        emit('user_joined', {
            'user_id': user_id,
            'message': f"User {user_id} joined the room"
        }, room=room_code, include_self=False)
        logger.info(f"User {user_id} joined room {room_code}")

@socketio.on('leave_room')
def handle_leave_room(data):
    """User leaves room chat"""
    room_code = data.get('room_code')
    user_id = data.get('user_id')
    
    if room_code:
        leave_room(room_code)
        logger.info(f"User {user_id} left room {room_code}")

@socketio.on('send_message')
def handle_send_message(data):
    """Handle real-time chat messages"""
    try:
        with RoommateDatabase() as db:
            chat_manager = ChatManager(db)
            
            # Save message to database
            message_id = chat_manager.send_message({
                'room_code': data['room_code'],
                'sender_id': data['sender_id'],
                'message_type': data.get('message_type', 'text'),
                'message_text': data.get('message'),
                'mentions': data.get('mentions', [])
            })
            
            # Get user details
            user_manager = UserManager(db)
            sender = user_manager.get_user_by_id(data['sender_id'])
            
            # Prepare message data
            message_data = {
                'id': message_id,
                'sender_id': data['sender_id'],
                'sender_name': sender['full_name'],
                'sender_pic': sender['profile_pic'],
                'message': data.get('message'),
                'message_type': data.get('message_type', 'text'),
                'mentions': data.get('mentions', []),
                'timestamp': datetime.now().isoformat()
            }
            
            # Broadcast to room
            emit('new_message', message_data, room=data['room_code'])
            
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        emit('error', {'message': 'Failed to send message'})

# ============================================
# AUTHENTICATION ROUTES
# ============================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['full_name', 'email', 'password']
        if not all(field in data for field in required):
            return format_response(success=False, error='Missing required fields'), 400
        
        with RoommateDatabase() as db:
            user_manager = UserManager(db)
            
            # Check if user exists
            existing = user_manager.get_user_by_email(data['email'])
            if existing:
                return format_response(success=False, error='Email already registered'), 400
            
            # Generate room code if not provided
            if 'room_code' not in data or not data['room_code']:
                data['room_code'] = generate_room_code()
            
            # Create user
            user = user_manager.create_user(data)
            
            if user:
                # Set session
                session.permanent = True  # Ensure session persists across browser restarts
                session['user_id'] = user['user_id']
                session['room_code'] = user['room_code']
                
                # Join socket room
                socketio.emit('join_room', {
                    'room_code': user['room_code'],
                    'user_id': user['user_id']
                })
                
                return format_response(
                    success=True,
                    data={'user': user},
                    message='Registration successful'
                ), 201
            else:
                return format_response(success=False, error='Registration failed'), 400
                
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login"""
    try:
        data = request.get_json()
        
        # Validate
        if not data or not data.get('email') or not data.get('password'):
            return format_response(success=False, error='Email and password required'), 400
        
        with RoommateDatabase() as db:
            user_manager = UserManager(db)
            
            # Authenticate
            user = user_manager.authenticate_user(data['email'], data['password'])
            
            if user:
                # Set session
                session.permanent = True  # Ensure session persists across browser restarts
                session['user_id'] = user['user_id']
                session['room_code'] = user['room_code']
                
                # Join socket room
                socketio.emit('join_room', {
                    'room_code': user['room_code'],
                    'user_id': user['user_id']
                })
                
                return format_response(
                    success=True,
                    data={'user': user},
                    message='Login successful'
                )
            else:
                return format_response(success=False, error='Invalid credentials'), 401
                
    except Exception as e:
        logger.error(f"Login error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    """User logout"""
    try:
        user_id = session.get('user_id')
        room_code = session.get('room_code')
        
        # Leave socket room
        if room_code and user_id:
            socketio.emit('leave_room', {
                'room_code': room_code,
                'user_id': user_id
            })
        
        # Clear session
        session.clear()
        
        return format_response(success=True, message='Logout successful')
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/auth/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged in user"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            user_manager = UserManager(db)
            user = user_manager.get_user_by_id(user_id)
            
            if user:
                return format_response(success=True, data={'user': user})
            else:
                return format_response(success=False, error='User not found'), 404
                
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# USER ROUTES
# ============================================

@app.route('/api/users/roommates', methods=['GET'])
@login_required
@room_required
def get_roommates():
    """Get all roommates in current room"""
    try:
        room_code = session.get('room_code')
        
        with RoommateDatabase() as db:
            user_manager = UserManager(db)
            roommates = user_manager.get_roommates(room_code)
            
            return format_response(success=True, data={'roommates': roommates})
            
    except Exception as e:
        logger.error(f"Get roommates error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/users/status', methods=['PUT'])
@login_required
def update_status():
    """Update user out of station status"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        with RoommateDatabase() as db:
            user_manager = UserManager(db)
            success = user_manager.update_user_status(user_id, data)
            
            if success:
                # Notify room via socket
                socketio.emit('status_update', {
                    'user_id': user_id,
                    'status': data
                }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    message='Status updated successfully'
                )
            else:
                return format_response(success=False, error='Update failed'), 400
                
    except Exception as e:
        logger.error(f"Update status error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# EXPENSE ROUTES
# ============================================

@app.route('/api/expenses', methods=['POST'])
@login_required
@room_required
def add_expense():
    """Add new expense"""
    try:
        data = request.get_json()
        data['room_code'] = session.get('room_code')
        data['paid_by'] = session.get('user_id')
        
        with RoommateDatabase() as db:
            expense_manager = ExpenseManager(db)
            chat_manager = ChatManager(db)
            
            expense = expense_manager.add_expense(data)
            
            # Send to chat
            chat_manager.send_expense_message(expense['expense_id'])
            
            # Notify via socket
            socketio.emit('new_expense', expense, room=data['room_code'])
            
            return format_response(
                success=True,
                data={'expense': expense},
                message='Expense added successfully'
            ), 201
            
    except Exception as e:
        logger.error(f"Add expense error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/expenses', methods=['GET'])
@login_required
@room_required
def get_expenses():
    """Get room expenses"""
    try:
        room_code = session.get('room_code')
        days = request.args.get('days', 30, type=int)
        
        with RoommateDatabase() as db:
            expense_manager = ExpenseManager(db)
            expenses = expense_manager.get_room_expenses(room_code, days)
            
            return format_response(success=True, data={'expenses': expenses})
            
    except Exception as e:
        logger.error(f"Get expenses error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/expenses/<int:expense_id>', methods=['GET'])
@login_required
def get_expense(expense_id):
    """Get single expense details"""
    try:
        with RoommateDatabase() as db:
            expense_manager = ExpenseManager(db)
            expense = expense_manager.get_expense_details(expense_id)
            
            if expense:
                return format_response(success=True, data={'expense': expense})
            else:
                return format_response(success=False, error='Expense not found'), 404
                
    except Exception as e:
        logger.error(f"Get expense error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/expenses/split/<int:split_id>/pay', methods=['POST'])
@login_required
def mark_paid(split_id):
    """Mark expense split as paid"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            expense_manager = ExpenseManager(db)
            chat_manager = ChatManager(db)
            
            success = expense_manager.mark_split_paid(split_id, data)
            
            if success:
                # Send to chat
                chat_manager.send_payment_message(split_id)
                
                # Notify via socket
                socketio.emit('payment_made', {
                    'split_id': split_id,
                    'user_id': user_id
                }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    message='Payment recorded successfully'
                )
            else:
                return format_response(success=False, error='Failed to record payment'), 400
                
    except Exception as e:
        logger.error(f"Mark paid error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/expenses/split/<int:split_id>/confirm', methods=['POST'])
@login_required
def confirm_payment(split_id):
    """Confirm payment received"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            expense_manager = ExpenseManager(db)
            success = expense_manager.confirm_payment_received(split_id, user_id)
            
            if success:
                socketio.emit('payment_confirmed', {
                    'split_id': split_id,
                    'user_id': user_id
                }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    message='Payment confirmed'
                )
            else:
                return format_response(success=False, error='Confirmation failed'), 400
                
    except Exception as e:
        logger.error(f"Confirm payment error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# BALANCE ROUTES
# ============================================

@app.route('/api/balances', methods=['GET'])
@login_required
@room_required
def get_balances():
    """Get room balances"""
    try:
        room_code = session.get('room_code')
        
        with RoommateDatabase() as db:
            balance_manager = BalanceManager(db)
            balances = balance_manager.get_room_balances(room_code)
            
            return format_response(success=True, data=balances)
            
    except Exception as e:
        logger.error(f"Get balances error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/balances/me', methods=['GET'])
@login_required
def my_balance():
    """Get current user's balance"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            balance_manager = BalanceManager(db)
            balance = balance_manager.get_user_balance(user_id)
            
            return format_response(success=True, data=balance)
            
    except Exception as e:
        logger.error(f"Get my balance error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/balances/you-owe', methods=['GET'])
@login_required
def you_owe():
    """Get what current user owes"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            balance_manager = BalanceManager(db)
            owe_list = balance_manager.get_you_owe_summary(user_id)
            
            return format_response(success=True, data={'you_owe': owe_list})
            
    except Exception as e:
        logger.error(f"Get you owe error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/balances/owed-to-you', methods=['GET'])
@login_required
def owed_to_you():
    """Get what others owe current user"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            balance_manager = BalanceManager(db)
            owed_list = balance_manager.get_owed_to_you_summary(user_id)
            
            return format_response(success=True, data={'owed_to_you': owed_list})
            
    except Exception as e:
        logger.error(f"Get owed to you error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# MARKET ROUTES
# ============================================

@app.route('/api/market', methods=['POST'])
@login_required
@room_required
def create_market_run():
    """Create new market run"""
    try:
        data = request.get_json()
        data['room_code'] = session.get('room_code')
        data['created_by'] = session.get('user_id')
        
        with RoommateDatabase() as db:
            market_manager = MarketManager(db)
            run_id = market_manager.create_market_run(data)
            
            if run_id:
                socketio.emit('new_market_run', {
                    'run_id': run_id,
                    'created_by': data['created_by']
                }, room=data['room_code'])
                
                return format_response(
                    success=True,
                    data={'market_run_id': run_id},
                    message='Market run created'
                ), 201
            else:
                return format_response(success=False, error='Creation failed'), 400
                
    except Exception as e:
        logger.error(f"Create market run error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/market/<int:run_id>', methods=['GET'])
@login_required
def get_market_run(run_id):
    """Get market run details"""
    try:
        with RoommateDatabase() as db:
            market_manager = MarketManager(db)
            market_run = market_manager.get_market_run(run_id)
            
            if market_run:
                return format_response(success=True, data={'market_run': market_run})
            else:
                return format_response(success=False, error='Market run not found'), 404
                
    except Exception as e:
        logger.error(f"Get market run error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/market/<int:run_id>/items', methods=['POST'])
@login_required
def add_market_item(run_id):
    """Add item to market run"""
    try:
        data = request.get_json()
        data['market_run_id'] = run_id
        data['added_by'] = session.get('user_id')
        
        with RoommateDatabase() as db:
            market_manager = MarketManager(db)
            item_id = market_manager.add_market_item(data)
            
            if item_id:
                # Get updated market run
                market_run = market_manager.get_market_run(run_id)
                
                socketio.emit('market_item_added', {
                    'run_id': run_id,
                    'item_id': item_id,
                    'market_run': market_run
                }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    data={'item_id': item_id, 'market_run': market_run},
                    message='Item added'
                ), 201
            else:
                return format_response(success=False, error='Failed to add item'), 400
                
    except Exception as e:
        logger.error(f"Add market item error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/market/items/<int:item_id>/purchase', methods=['POST'])
@login_required
def mark_item_purchased(item_id):
    """Mark item as purchased"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            market_manager = MarketManager(db)
            success = market_manager.mark_item_purchased(
                item_id, 
                user_id, 
                data.get('price')
            )
            
            if success:
                # Get run_id for socket
                query = "SELECT market_run_id FROM market_items WHERE item_id = %s"
                result = db.execute_query(query, (item_id,))
                run_id = result[0]['market_run_id'] if result else None
                
                if run_id:
                    market_run = market_manager.get_market_run(run_id)
                    socketio.emit('item_purchased', {
                        'item_id': item_id,
                        'run_id': run_id,
                        'purchased_by': user_id,
                        'market_run': market_run
                    }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    message='Item marked as purchased'
                )
            else:
                return format_response(success=False, error='Failed to update item'), 400
                
    except Exception as e:
        logger.error(f"Mark item purchased error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/market/<int:run_id>/complete', methods=['POST'])
@login_required
def complete_market_run(run_id):
    """Complete market run and create expenses"""
    try:
        with RoommateDatabase() as db:
            market_manager = MarketManager(db)
            success = market_manager.complete_market_run(run_id)
            
            if success:
                socketio.emit('market_completed', {
                    'run_id': run_id
                }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    message='Market run completed'
                )
            else:
                return format_response(success=False, error='Failed to complete'), 400
                
    except Exception as e:
        logger.error(f"Complete market run error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# INVENTORY ROUTES
# ============================================

@app.route('/api/inventory', methods=['GET'])
@login_required
@room_required
def get_inventory():
    """Get room inventory"""
    try:
        room_code = session.get('room_code')
        category = request.args.get('category')
        
        with RoommateDatabase() as db:
            inventory_manager = InventoryManager(db)
            inventory = inventory_manager.get_inventory(room_code, category)
            low_stock = inventory_manager.get_low_stock_items(room_code)
            
            return format_response(success=True, data={
                'inventory': inventory,
                'low_stock': low_stock
            })
            
    except Exception as e:
        logger.error(f"Get inventory error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/inventory', methods=['POST'])
@login_required
@room_required
def add_inventory_item():
    """Add item to inventory"""
    try:
        data = request.get_json()
        data['room_code'] = session.get('room_code')
        data['last_updated_by'] = session.get('user_id')
        
        with RoommateDatabase() as db:
            inventory_manager = InventoryManager(db)
            item_id = inventory_manager.add_inventory_item(data)
            
            if item_id:
                socketio.emit('inventory_updated', {
                    'item_id': item_id
                }, room=data['room_code'])
                
                return format_response(
                    success=True,
                    data={'item_id': item_id},
                    message='Item added to inventory'
                ), 201
            else:
                return format_response(success=False, error='Failed to add item'), 400
                
    except Exception as e:
        logger.error(f"Add inventory item error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/inventory/<int:item_id>/consume', methods=['POST'])
@login_required
def consume_item(item_id):
    """Consume inventory item"""
    try:
        data = request.get_json()
        quantity = data.get('quantity', 1)
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            inventory_manager = InventoryManager(db)
            success = inventory_manager.consume_item(item_id, quantity, user_id)
            
            if success:
                socketio.emit('inventory_consumed', {
                    'item_id': item_id,
                    'quantity': quantity
                }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    message=f'Consumed {quantity} units'
                )
            else:
                return format_response(success=False, error='Failed to consume'), 400
                
    except Exception as e:
        logger.error(f"Consume item error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/inventory/low-stock', methods=['GET'])
@login_required
@room_required
def get_low_stock():
    """Get low stock items"""
    try:
        room_code = session.get('room_code')
        
        with RoommateDatabase() as db:
            inventory_manager = InventoryManager(db)
            low_stock = inventory_manager.get_low_stock_items(room_code)
            
            return format_response(success=True, data={'low_stock': low_stock})
            
    except Exception as e:
        logger.error(f"Get low stock error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# CHAT ROUTES
# ============================================

@app.route('/api/chat/messages', methods=['GET'])
@login_required
@room_required
def get_chat_messages():
    """Get recent chat messages"""
    try:
        room_code = session.get('room_code')
        limit = request.args.get('limit', 50, type=int)
        
        with RoommateDatabase() as db:
            chat_manager = ChatManager(db)
            messages = chat_manager.get_room_messages(room_code, limit)
            
            return format_response(success=True, data={'messages': messages})
            
    except Exception as e:
        logger.error(f"Get chat messages error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/chat/messages', methods=['POST'])
@login_required
@room_required
def send_chat_message():
    """Send chat message"""
    try:
        data = request.get_json()
        data['room_code'] = session.get('room_code')
        data['sender_id'] = session.get('user_id')
        
        with RoommateDatabase() as db:
            chat_manager = ChatManager(db)
            message_id = chat_manager.send_message(data)
            
            if message_id:
                # Get user details
                user_manager = UserManager(db)
                sender = user_manager.get_user_by_id(data['sender_id'])
                
                message_data = {
                    'id': message_id,
                    'sender_id': data['sender_id'],
                    'sender_name': sender['full_name'],
                    'message': data.get('message_text'),
                    'message_type': data.get('message_type', 'text'),
                    'mentions': data.get('mentions', []),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Broadcast via socket
                socketio.emit('new_message', message_data, room=data['room_code'])
                
                return format_response(
                    success=True,
                    data={'message_id': message_id, 'message': message_data},
                    message='Message sent'
                ), 201
            else:
                return format_response(success=False, error='Failed to send'), 400
                
    except Exception as e:
        logger.error(f"Send message error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/chat/mentions/unread', methods=['GET'])
@login_required
def get_unread_mentions():
    """Get unread mentions"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            chat_manager = ChatManager(db)
            mentions = chat_manager.get_unread_mentions(user_id)
            
            return format_response(success=True, data={'mentions': mentions})
            
    except Exception as e:
        logger.error(f"Get unread mentions error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/chat/mentions/<int:message_id>/read', methods=['POST'])
@login_required
def mark_mention_read(message_id):
    """Mark mention as read"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            chat_manager = ChatManager(db)
            success = chat_manager.mark_mention_read(message_id, user_id)
            
            if success:
                return format_response(success=True, message='Marked as read')
            else:
                return format_response(success=False, error='Failed to mark'), 400
                
    except Exception as e:
        logger.error(f"Mark mention read error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# NOTIFICATION ROUTES
# ============================================

@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Get user notifications"""
    try:
        user_id = session.get('user_id')
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        
        with RoommateDatabase() as db:
            notification_manager = NotificationManager(db)
            notifications = notification_manager.get_user_notifications(user_id, unread_only)
            
            return format_response(success=True, data={'notifications': notifications})
            
    except Exception as e:
        logger.error(f"Get notifications error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark notification as read"""
    try:
        with RoommateDatabase() as db:
            notification_manager = NotificationManager(db)
            success = notification_manager.mark_notification_read(notification_id)
            
            if success:
                return format_response(success=True, message='Marked as read')
            else:
                return format_response(success=False, error='Failed to mark'), 400
                
    except Exception as e:
        logger.error(f"Mark notification read error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    """Mark all notifications as read"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            notification_manager = NotificationManager(db)
            count = notification_manager.mark_all_read(user_id)
            
            return format_response(
                success=True,
                data={'marked_count': count},
                message=f'Marked {count} notifications as read'
            )
            
    except Exception as e:
        logger.error(f"Mark all read error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# SETTLEMENT ROUTES
# ============================================

@app.route('/api/settlements', methods=['POST'])
@login_required
@room_required
def create_settlement():
    """Create new settlement"""
    try:
        data = request.get_json()
        data['room_code'] = session.get('room_code')
        
        with RoommateDatabase() as db:
            settlement_manager = SettlementManager(db)
            settlement_id = settlement_manager.create_settlement(data)
            
            if settlement_id:
                socketio.emit('new_settlement', {
                    'settlement_id': settlement_id,
                    'from_user': data['from_user'],
                    'to_user': data['to_user'],
                    'amount': data['amount']
                }, room=data['room_code'])
                
                return format_response(
                    success=True,
                    data={'settlement_id': settlement_id},
                    message='Settlement recorded'
                ), 201
            else:
                return format_response(success=False, error='Failed to record'), 400
                
    except Exception as e:
        logger.error(f"Create settlement error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/settlements', methods=['GET'])
@login_required
@room_required
def get_settlements():
    """Get room settlements"""
    try:
        room_code = session.get('room_code')
        days = request.args.get('days', 30, type=int)
        
        with RoommateDatabase() as db:
            settlement_manager = SettlementManager(db)
            settlements = settlement_manager.get_room_settlements(room_code, days)
            
            return format_response(success=True, data={'settlements': settlements})
            
    except Exception as e:
        logger.error(f"Get settlements error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/settlements/<int:settlement_id>/confirm', methods=['POST'])
@login_required
def confirm_settlement(settlement_id):
    """Confirm settlement received"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            settlement_manager = SettlementManager(db)
            success = settlement_manager.confirm_settlement(settlement_id, user_id)
            
            if success:
                socketio.emit('settlement_confirmed', {
                    'settlement_id': settlement_id,
                    'confirmed_by': user_id
                }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    message='Settlement confirmed'
                )
            else:
                return format_response(success=False, error='Confirmation failed'), 400
                
    except Exception as e:
        logger.error(f"Confirm settlement error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# CHORE ROUTES
# ============================================

@app.route('/api/chores', methods=['GET'])
@login_required
@room_required
def get_chores():
    """Get room chores"""
    try:
        room_code = session.get('room_code')
        
        with RoommateDatabase() as db:
            chore_manager = ChoreManager(db)
            pending = chore_manager.get_pending_chores(room_code)
            history = chore_manager.get_chore_history(room_code)
            
            return format_response(success=True, data={
                'pending': pending,
                'history': history
            })
            
    except Exception as e:
        logger.error(f"Get chores error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/chores', methods=['POST'])
@login_required
@room_required
def create_chore():
    """Create new chore"""
    try:
        data = request.get_json()
        data['room_code'] = session.get('room_code')
        
        with RoommateDatabase() as db:
            chore_manager = ChoreManager(db)
            chore_id = chore_manager.create_chore(data)
            
            if chore_id:
                socketio.emit('new_chore', {
                    'chore_id': chore_id
                }, room=data['room_code'])
                
                return format_response(
                    success=True,
                    data={'chore_id': chore_id},
                    message='Chore created'
                ), 201
            else:
                return format_response(success=False, error='Failed to create'), 400
                
    except Exception as e:
        logger.error(f"Create chore error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/api/chores/<int:chore_id>/complete', methods=['POST'])
@login_required
def complete_chore(chore_id):
    """Mark chore as complete"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            chore_manager = ChoreManager(db)
            success = chore_manager.complete_chore(chore_id, user_id)
            
            if success:
                socketio.emit('chore_completed', {
                    'chore_id': chore_id,
                    'completed_by': user_id
                }, room=session.get('room_code'))
                
                return format_response(
                    success=True,
                    message='Chore completed! Points awarded'
                )
            else:
                return format_response(success=False, error='Failed to complete'), 400
                
    except Exception as e:
        logger.error(f"Complete chore error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# DASHBOARD ROUTES
# ============================================

@app.route('/api/dashboard', methods=['GET'])
@login_required
def get_dashboard():
    """Get complete dashboard data"""
    try:
        user_id = session.get('user_id')
        
        with RoommateDatabase() as db:
            dashboard_manager = DashboardManager(db)
            dashboard_data = dashboard_manager.get_dashboard_data(user_id)
            
            return format_response(success=True, data=dashboard_data)
            
    except Exception as e:
        logger.error(f"Get dashboard error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# FILE UPLOAD ROUTES
# ============================================

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """Upload file (receipt, image, etc)"""
    try:
        if 'file' not in request.files:
            return format_response(success=False, error='No file provided'), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return format_response(success=False, error='No file selected'), 400
        
        filename = save_uploaded_file(file)
        
        if filename:
            file_url = f"/uploads/{filename}"
            return format_response(
                success=True,
                data={'filename': filename, 'url': file_url},
                message='File uploaded successfully'
            )
        else:
            return format_response(success=False, error='Invalid file type'), 400
            
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return format_response(success=False, error=str(e)), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

# ============================================
# SEARCH ROUTES
# ============================================

@app.route('/api/search/users', methods=['GET'])
@login_required
def search_users():
    """Search users"""
    try:
        query = request.args.get('q', '')
        room_code = session.get('room_code')
        
        if len(query) < 2:
            return format_response(success=True, data={'users': []})
        
        with RoommateDatabase() as db:
            user_manager = UserManager(db)
            users = user_manager.search_users(query, room_code)
            
            return format_response(success=True, data={'users': users})
            
    except Exception as e:
        logger.error(f"Search users error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# STATS ROUTES
# ============================================

@app.route('/api/stats/room', methods=['GET'])
@login_required
@room_required
def get_room_stats():
    """Get room statistics"""
    try:
        room_code = session.get('room_code')
        
        with RoommateDatabase() as db:
            # Total expenses
            exp_query = """
            SELECT COUNT(*) as count, SUM(amount) as total
            FROM expenses
            WHERE room_code = %s AND expense_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            """
            expense_stats = db.execute_query(exp_query, (room_code,))[0]
            
            # Active members
            member_query = """
            SELECT COUNT(*) as active,
                   SUM(CASE WHEN is_out_of_station THEN 1 ELSE 0 END) as out_of_station
            FROM users
            WHERE room_code = %s AND is_active = TRUE
            """
            member_stats = db.execute_query(member_query, (room_code,))[0]
            
            # Category breakdown
            cat_query = """
            SELECT category, COUNT(*) as count, SUM(amount) as total
            FROM expenses
            WHERE room_code = %s AND expense_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY category
            """
            category_stats = db.execute_query(cat_query, (room_code,))
            
            # Pending payments
            pending_query = """
            SELECT COUNT(*) as pending_count, SUM(amount_owed) as pending_total
            FROM expense_splits es
            JOIN expenses e ON es.expense_id = e.expense_id
            WHERE e.room_code = %s AND es.is_paid = FALSE
            """
            pending_stats = db.execute_query(pending_query, (room_code,))[0]
            
            return format_response(success=True, data={
                'expenses': {
                    'count': expense_stats['count'] or 0,
                    'total': float(expense_stats['total'] or 0)
                },
                'members': {
                    'active': member_stats['active'] or 0,
                    'out_of_station': member_stats['out_of_station'] or 0
                },
                'categories': category_stats,
                'pending': {
                    'count': pending_stats['pending_count'] or 0,
                    'total': float(pending_stats['pending_total'] or 0)
                }
            })
            
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# HEALTH CHECK ROUTES
# ============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database
        db_ok = test_database_connection()
        
        return format_response(success=True, data={
            'status': 'healthy',
            'database': 'connected' if db_ok else 'disconnected',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return format_response(success=False, error=str(e)), 500

@app.route('/api/init', methods=['POST'])
def init_database():
    """Initialize database (admin only - use carefully)"""
    try:
        # Simple auth check - in production, use proper admin auth
        api_key = request.headers.get('X-API-Key')
        if api_key != os.getenv('ADMIN_API_KEY', 'admin-secret-key'):
            return format_response(success=False, error='Unauthorized'), 401
        
        success = initialize_database()
        
        if success:
            return format_response(success=True, message='Database initialized successfully')
        else:
            return format_response(success=False, error='Database initialization failed'), 500
            
    except Exception as e:
        logger.error(f"Init database error: {e}")
        return format_response(success=False, error=str(e)), 500

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(error):
    return format_response(success=False, error='Endpoint not found'), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return format_response(success=False, error='Method not allowed'), 405

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return format_response(success=False, error='Internal server error'), 500

# ============================================
# MAIN ENTRY POINT
# ============================================

if __name__ == '__main__':
    # Test database connection on startup
    if test_database_connection():
        logger.info("Database connection successful")
    else:
        logger.warning("Database connection failed - check configuration")
    
    # Run app
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    )

# ============================================
# END OF app.py
# ============================================