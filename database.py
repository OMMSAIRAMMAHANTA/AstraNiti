"""
============================================
ROOMMATE MANAGEMENT SYSTEM - DATABASE LAYER
============================================
File: database.py
Purpose: MySQL connection, queries, and utilities
Author: Python Backend
============================================
"""

import mysql.connector
from mysql.connector import Error
from mysql.connector import pooling
import hashlib
import secrets
import logging
from datetime import datetime, date, timedelta
import json
from typing import Optional, Dict, List, Tuple, Any, Union
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================
# CONFIGURATION
# ============================================

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '3306'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'T202414401'),
    'database': os.getenv('DB_NAME', 'roommate_system'),
    'pool_name': 'roommate_pool',
    'pool_size': 10,
    'pool_reset_session': True,
    'autocommit': False,
    'use_pure': True
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('database.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# DATABASE POOL MANAGER
# ============================================

class DatabasePoolManager:
    """
    Manages database connection pool for optimal performance
    Handles connection creation, retrieval, and cleanup
    """
    
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance
    
    def _initialize_pool(self):
        """Initialize the connection pool"""
        try:
            self._pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name=DB_CONFIG['pool_name'],
                pool_size=DB_CONFIG['pool_size'],
                pool_reset_session=DB_CONFIG['pool_reset_session'],
                host=DB_CONFIG['host'],
                port=DB_CONFIG['port'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                database=DB_CONFIG['database'],
                autocommit=DB_CONFIG['autocommit'],
                use_pure=DB_CONFIG['use_pure']
            )
            logger.info(f"Database pool created successfully with size {DB_CONFIG['pool_size']}")
        except Error as e:
            logger.error(f"Failed to create database pool: {e}")
            raise
    
    def get_connection(self):
        """Get a connection from the pool"""
        try:
            connection = self._pool.get_connection()
            logger.debug("Connection retrieved from pool")
            return connection
        except Error as e:
            logger.error(f"Failed to get connection from pool: {e}")
            raise
    
    def close_all_connections(self):
        """Close all connections in the pool"""
        try:
            self._pool = None
            logger.info("All database connections closed")
        except Error as e:
            logger.error(f"Error closing connections: {e}")


# ============================================
# BASE DATABASE CLASS
# ============================================

class RoommateDatabase:
    """
    Main database class with all CRUD operations
    Handles all database interactions for the roommate system
    """
    
    def __init__(self):
        self.pool_manager = DatabasePoolManager()
        self.connection = None
        self.cursor = None
    
    def __enter__(self):
        """Context manager entry - get connection"""
        self.connection = self.pool_manager.get_connection()
        self.cursor = self.connection.cursor(dictionary=True, buffered=True)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close cursor and return connection to pool"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.debug("Database connection returned to pool")
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """
        Execute SELECT query and return results
        """
        try:
            self.cursor.execute(query, params or ())
            results = self.cursor.fetchall()
            logger.debug(f"Query executed: {query[:100]}... | Rows: {len(results)}")
            return results
        except Error as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise
    
    def execute_insert(self, query: str, params: tuple = None) -> int:
        """
        Execute INSERT query and return last insert ID
        """
        try:
            self.cursor.execute(query, params or ())
            self.connection.commit()
            last_id = self.cursor.lastrowid
            logger.debug(f"Insert executed | Last ID: {last_id}")
            return last_id
        except Error as e:
            self.connection.rollback()
            logger.error(f"Insert failed: {e}")
            raise
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """
        Execute UPDATE query and return affected rows
        """
        try:
            self.cursor.execute(query, params or ())
            self.connection.commit()
            affected = self.cursor.rowcount
            logger.debug(f"Update executed | Affected rows: {affected}")
            return affected
        except Error as e:
            self.connection.rollback()
            logger.error(f"Update failed: {e}")
            raise
    
    def execute_delete(self, query: str, params: tuple = None) -> int:
        """
        Execute DELETE query and return affected rows
        """
        try:
            self.cursor.execute(query, params or ())
            self.connection.commit()
            affected = self.cursor.rowcount
            logger.debug(f"Delete executed | Affected rows: {affected}")
            return affected
        except Error as e:
            self.connection.rollback()
            logger.error(f"Delete failed: {e}")
            raise
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """
        Execute batch INSERT/UPDATE
        """
        try:
            self.cursor.executemany(query, params_list)
            self.connection.commit()
            affected = self.cursor.rowcount
            logger.debug(f"Batch execute | Affected rows: {affected}")
            return affected
        except Error as e:
            self.connection.rollback()
            logger.error(f"Batch execute failed: {e}")
            raise
    
    def call_procedure(self, proc_name: str, params: tuple = None) -> List[Dict]:
        """
        Call stored procedure
        """
        try:
            self.cursor.callproc(proc_name, params or ())
            results = []
            for result in self.cursor.stored_results():
                results.extend(result.fetchall())
            self.connection.commit()
            logger.debug(f"Procedure called: {proc_name}")
            return results
        except Error as e:
            self.connection.rollback()
            logger.error(f"Procedure call failed: {e}")
            raise


# ============================================
# USER MANAGEMENT CLASS
# ============================================

class UserManager:
    """
    Handles all user-related database operations
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def create_user(self, user_data: Dict) -> Dict:
        """
        Create a new user
        """
        query = """
        INSERT INTO users (
            full_name, email, phone, password_hash, 
            room_number, room_code, profile_pic
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        # Hash password (simplified - use proper hashing in production)
        password_hash = hashlib.sha256(user_data['password'].encode()).hexdigest()
        
        params = (
            user_data['full_name'],
            user_data['email'],
            user_data.get('phone', ''),
            password_hash,
            user_data.get('room_number', ''),
            user_data['room_code'],
            user_data.get('profile_pic', 'default.jpg')
        )
        
        user_id = self.db.execute_insert(query, params)
        
        # Get created user
        return self.get_user_by_id(user_id)
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """
        Get user by ID
        """
        query = "SELECT * FROM users WHERE user_id = %s"
        results = self.db.execute_query(query, (user_id,))
        return results[0] if results else None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """
        Get user by email
        """
        query = "SELECT * FROM users WHERE email = %s"
        results = self.db.execute_query(query, (email,))
        return results[0] if results else None
    
    def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
        """
        Authenticate user login
        """
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        query = "SELECT * FROM users WHERE email = %s AND password_hash = %s"
        results = self.db.execute_query(query, (email, password_hash))
        
        if results:
            user = results[0]
            # Update last login
            self.update_last_login(user['user_id'])
            return user
        return None
    
    def update_last_login(self, user_id: int):
        """
        Update user's last login timestamp
        """
        query = "UPDATE users SET last_login = NOW() WHERE user_id = %s"
        self.db.execute_update(query, (user_id,))
    
    def get_roommates(self, room_code: str) -> List[Dict]:
        """
        Get all active roommates in a room
        """
        query = """
        SELECT user_id, full_name, email, phone, profile_pic,
               is_out_of_station, out_station_end
        FROM users 
        WHERE room_code = %s AND is_active = TRUE
        ORDER BY full_name
        """
        return self.db.execute_query(query, (room_code,))
    
    def update_user_status(self, user_id: int, status_data: Dict) -> bool:
        """
        Update user's out of station status
        """
        query = """
        UPDATE users 
        SET is_out_of_station = %s,
            out_station_start = %s,
            out_station_end = %s,
            out_station_reason = %s
        WHERE user_id = %s
        """
        params = (
            status_data.get('is_out_of_station', False),
            status_data.get('start_date'),
            status_data.get('end_date'),
            status_data.get('reason', ''),
            user_id
        )
        affected = self.db.execute_update(query, params)
        
        # Create notification for roommates
        if affected and status_data.get('is_out_of_station'):
            self._notify_status_change(user_id, status_data)
        
        return affected > 0
    
    def _notify_status_change(self, user_id: int, status_data: Dict):
        """
        Notify roommates about status change
        """
        # Get user details
        user = self.get_user_by_id(user_id)
        if not user:
            return
        
        # Get all roommates
        roommates = self.get_roommates(user['room_code'])
        
        # Create notification for each roommate
        notification_manager = NotificationManager(self.db)
        for roommate in roommates:
            if roommate['user_id'] != user_id:
                notification_manager.create_notification({
                    'user_id': roommate['user_id'],
                    'type': 'status_change',
                    'title': 'Roommate Status Update',
                    'message': f"{user['full_name']} is out of station until {status_data['end_date']}",
                    'reference_id': user_id,
                    'reference_type': 'user'
                })
    
    def search_users(self, search_term: str, room_code: str = None) -> List[Dict]:
        """
        Search users by name or email
        """
        query = """
        SELECT user_id, full_name, email, phone, profile_pic
        FROM users
        WHERE (full_name LIKE %s OR email LIKE %s)
        """
        params = [f"%{search_term}%", f"%{search_term}%"]
        
        if room_code:
            query += " AND room_code = %s"
            params.append(room_code)
        
        query += " ORDER BY full_name LIMIT 20"
        
        return self.db.execute_query(query, tuple(params))


# ============================================
# EXPENSE MANAGEMENT CLASS
# ============================================

class ExpenseManager:
    """
    Handles all expense-related database operations
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def add_expense(self, expense_data: Dict) -> Dict:
        """
        Add a new expense and create splits
        """
        # Insert expense
        expense_query = """
        INSERT INTO expenses (
            room_code, paid_by, amount, description, category,
            split_type, market_name, location_lat, location_lng,
            receipt_image, expense_date
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        expense_params = (
            expense_data['room_code'],
            expense_data['paid_by'],
            expense_data['amount'],
            expense_data['description'],
            expense_data.get('category', 'other'),
            expense_data.get('split_type', 'equal'),
            expense_data.get('market_name'),
            expense_data.get('location_lat'),
            expense_data.get('location_lng'),
            expense_data.get('receipt_image'),
            expense_data.get('expense_date', date.today())
        )
        
        expense_id = self.db.execute_insert(expense_query, expense_params)
        
        # Create splits
        self._create_expense_splits(expense_id, expense_data)
        
        # Create notification
        self._notify_new_expense(expense_id)
        
        # Get complete expense with splits
        return self.get_expense_details(expense_id)
    
    def _create_expense_splits(self, expense_id: int, expense_data: Dict):
        """
        Create split records for an expense
        """
        splits = expense_data.get('splits', [])
        
        if not splits and expense_data.get('split_type') == 'equal':
            # Equal split - get all roommates
            query = "SELECT user_id FROM users WHERE room_code = %s AND is_active = TRUE"
            roommates = self.db.execute_query(query, (expense_data['room_code'],))
            
            split_amount = expense_data['amount'] / len(roommates)
            splits = [
                {
                    'user_id': rm['user_id'],
                    'amount': split_amount,
                    'percentage': 100 / len(roommates)
                }
                for rm in roommates
            ]
        
        # Insert splits
        split_query = """
        INSERT INTO expense_splits (
            expense_id, user_id, amount_owed, percentage_owed
        ) VALUES (%s, %s, %s, %s)
        """
        
        split_params = [
            (expense_id, split['user_id'], split['amount'], split.get('percentage'))
            for split in splits
        ]
        
        if split_params:
            self.db.execute_many(split_query, split_params)
    
    def _notify_new_expense(self, expense_id: int):
        """
        Notify roommates about new expense
        """
        expense = self.get_expense_details(expense_id)
        if not expense:
            return
        
        # Get payer details
        user_manager = UserManager(self.db)
        payer = user_manager.get_user_by_id(expense['paid_by'])
        
        # Get all involved users
        splits = expense.get('splits', [])
        
        # Create notifications
        notification_manager = NotificationManager(self.db)
        for split in splits:
            if split['user_id'] != expense['paid_by']:
                notification_manager.create_notification({
                    'user_id': split['user_id'],
                    'type': 'new_expense',
                    'title': 'New Expense Added',
                    'message': f"{payer['full_name']} added {expense['description']} - You owe ₹{split['amount_owed']}",
                    'reference_id': expense_id,
                    'reference_type': 'expense',
                    'action_url': f"/expense/{expense_id}"
                })
    
    def get_expense_details(self, expense_id: int) -> Optional[Dict]:
        """
        Get complete expense details with splits
        """
        # Get expense
        expense_query = """
        SELECT e.*, u.full_name as paid_by_name
        FROM expenses e
        JOIN users u ON e.paid_by = u.user_id
        WHERE e.expense_id = %s
        """
        expenses = self.db.execute_query(expense_query, (expense_id,))
        
        if not expenses:
            return None
        
        expense = expenses[0]
        
        # Get splits with user details
        splits_query = """
        SELECT es.*, u.full_name, u.email, u.profile_pic
        FROM expense_splits es
        JOIN users u ON es.user_id = u.user_id
        WHERE es.expense_id = %s
        """
        expense['splits'] = self.db.execute_query(splits_query, (expense_id,))
        
        return expense
    
    def get_room_expenses(self, room_code: str, days: int = 30) -> List[Dict]:
        """
        Get all expenses for a room in last X days
        """
        query = """
        SELECT e.*, u.full_name as paid_by_name
        FROM expenses e
        JOIN users u ON e.paid_by = u.user_id
        WHERE e.room_code = %s 
        AND e.expense_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        ORDER BY e.expense_date DESC, e.created_at DESC
        """
        return self.db.execute_query(query, (room_code, days))
    
    def mark_split_paid(self, split_id: int, payment_data: Dict) -> bool:
        """
        Mark an expense split as paid
        """
        query = """
        UPDATE expense_splits 
        SET is_paid = TRUE,
            paid_date = %s,
            payment_method = %s,
            payment_note = %s,
            confirmed_by_payer = %s,
            confirmed_by_receiver = FALSE
        WHERE split_id = %s
        """
        params = (
            payment_data.get('paid_date', date.today()),
            payment_data.get('payment_method', 'cash'),
            payment_data.get('payment_note', ''),
            True,  # confirmed_by_payer
            split_id
        )
        
        affected = self.db.execute_update(query, params)
        
        if affected:
            # Notify receiver
            self._notify_payment_made(split_id)
        
        return affected > 0
    
    def confirm_payment_received(self, split_id: int, user_id: int) -> bool:
        """
        Receiver confirms payment received
        """
        query = """
        UPDATE expense_splits 
        SET confirmed_by_receiver = TRUE,
            confirmation_date = NOW()
        WHERE split_id = %s
        """
        affected = self.db.execute_update(query, (split_id,))
        
        if affected:
            # Update expense settled status if all paid
            self._update_expense_settlement_status(split_id)
        
        return affected > 0
    
    def _notify_payment_made(self, split_id: int):
        """
        Notify that payment has been made
        """
        # Get split details
        query = """
        SELECT es.*, e.room_code, e.description, 
               u.full_name as payer_name,
               u2.full_name as receiver_name
        FROM expense_splits es
        JOIN expenses e ON es.expense_id = e.expense_id
        JOIN users u ON es.user_id = u.user_id
        JOIN users u2 ON e.paid_by = u2.user_id
        WHERE es.split_id = %s
        """
        results = self.db.execute_query(query, (split_id,))
        
        if not results:
            return
        
        split = results[0]
        
        # Notify receiver
        notification_manager = NotificationManager(self.db)
        notification_manager.create_notification({
            'user_id': split['paid_by'],  # The person who should receive payment
            'type': 'payment_received',
            'title': 'Payment Received',
            'message': f"{split['payer_name']} paid ₹{split['amount_owed']} for {split['description']}",
            'reference_id': split['expense_id'],
            'reference_type': 'expense'
        })
    
    def _update_expense_settlement_status(self, split_id: int):
        """
        Check if all splits are paid and update expense status
        """
        # Get expense_id from split
        query = "SELECT expense_id FROM expense_splits WHERE split_id = %s"
        results = self.db.execute_query(query, (split_id,))
        
        if not results:
            return
        
        expense_id = results[0]['expense_id']
        
        # Check if all splits are paid
        check_query = """
        SELECT COUNT(*) as unpaid_count
        FROM expense_splits
        WHERE expense_id = %s AND is_paid = FALSE
        """
        results = self.db.execute_query(check_query, (expense_id,))
        
        if results and results[0]['unpaid_count'] == 0:
            # All paid - update expense
            update_query = """
            UPDATE expenses 
            SET is_settled = TRUE, settled_date = CURDATE()
            WHERE expense_id = %s
            """
            self.db.execute_update(update_query, (expense_id,))


# ============================================
# MARKET MANAGEMENT CLASS
# ============================================

class MarketManager:
    """
    Handles market runs and item tracking
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def create_market_run(self, run_data: Dict) -> int:
        """
        Create a new market run
        """
        query = """
        INSERT INTO market_runs (
            room_code, created_by, market_name, run_date, run_time, notes
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            run_data['room_code'],
            run_data['created_by'],
            run_data.get('market_name'),
            run_data.get('run_date', date.today()),
            run_data.get('run_time'),
            run_data.get('notes')
        )
        
        run_id = self.db.execute_insert(query, params)
        
        # Notify roommates
        self._notify_new_market_run(run_id)
        
        return run_id
    
    def _notify_new_market_run(self, run_id: int):
        """
        Notify roommates about new market run
        """
        # Get run details
        query = """
        SELECT mr.*, u.full_name as creator_name
        FROM market_runs mr
        JOIN users u ON mr.created_by = u.user_id
        WHERE mr.market_run_id = %s
        """
        results = self.db.execute_query(query, (run_id,))
        
        if not results:
            return
        
        run = results[0]
        
        # Get all roommates
        user_manager = UserManager(self.db)
        roommates = user_manager.get_roommates(run['room_code'])
        
        # Notify everyone except creator
        notification_manager = NotificationManager(self.db)
        for roommate in roommates:
            if roommate['user_id'] != run['created_by']:
                notification_manager.create_notification({
                    'user_id': roommate['user_id'],
                    'type': 'market_run',
                    'title': 'New Market Run',
                    'message': f"{run['creator_name']} created a market run. Add items needed!",
                    'reference_id': run_id,
                    'reference_type': 'market',
                    'action_url': f"/market/{run_id}"
                })
    
    def add_market_item(self, item_data: Dict) -> int:
        """
        Add an item to market run
        """
        # Calculate total price if price_per_unit provided
        if item_data.get('price_per_unit') and item_data.get('quantity'):
            total_price = item_data['price_per_unit'] * item_data['quantity']
        else:
            total_price = item_data.get('total_price', 0)
        
        query = """
        INSERT INTO market_items (
            market_run_id, added_by, item_name, quantity, unit,
            price_per_unit, total_price, is_shared, specific_for
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            item_data['market_run_id'],
            item_data['added_by'],
            item_data['item_name'],
            item_data.get('quantity', 1),
            item_data.get('unit', 'piece'),
            item_data.get('price_per_unit'),
            total_price,
            item_data.get('is_shared', True),
            item_data.get('specific_for')
        )
        
        return self.db.execute_insert(query, params)
    
    def get_market_run(self, run_id: int) -> Optional[Dict]:
        """
        Get complete market run with items
        """
        # Get run details
        run_query = """
        SELECT mr.*, u.full_name as creator_name
        FROM market_runs mr
        JOIN users u ON mr.created_by = u.user_id
        WHERE mr.market_run_id = %s
        """
        runs = self.db.execute_query(run_query, (run_id,))
        
        if not runs:
            return None
        
        run = runs[0]
        
        # Get items
        items_query = """
        SELECT mi.*, 
               u1.full_name as added_by_name,
               u2.full_name as specific_for_name,
               u3.full_name as purchased_by_name
        FROM market_items mi
        LEFT JOIN users u1 ON mi.added_by = u1.user_id
        LEFT JOIN users u2 ON mi.specific_for = u2.user_id
        LEFT JOIN users u3 ON mi.purchased_by = u3.user_id
        WHERE mi.market_run_id = %s
        ORDER BY mi.is_purchased, mi.created_at
        """
        run['items'] = self.db.execute_query(items_query, (run_id,))
        
        # Calculate totals
        total = sum(item.get('total_price', 0) for item in run['items'])
        purchased_total = sum(
            item.get('total_price', 0) 
            for item in run['items'] 
            if item.get('is_purchased')
        )
        
        run['total_amount'] = total
        run['purchased_amount'] = purchased_total
        
        return run
    
    def mark_item_purchased(self, item_id: int, purchased_by: int, price: float = None) -> bool:
        """
        Mark item as purchased
        """
        if price:
            # Update price and mark purchased
            query = """
            UPDATE market_items 
            SET is_purchased = TRUE,
                purchased_by = %s,
                total_price = %s,
                price_per_unit = %s / quantity
            WHERE item_id = %s
            """
            # Get quantity first
            q_query = "SELECT quantity FROM market_items WHERE item_id = %s"
            q_result = self.db.execute_query(q_query, (item_id,))
            quantity = q_result[0]['quantity'] if q_result else 1
            
            params = (purchased_by, price, price, item_id)
        else:
            # Just mark purchased
            query = """
            UPDATE market_items 
            SET is_purchased = TRUE, purchased_by = %s
            WHERE item_id = %s
            """
            params = (purchased_by, item_id)
        
        affected = self.db.execute_update(query, params)
        
        if affected:
            # Update market run total
            self._update_market_run_total(item_id)
        
        return affected > 0
    
    def _update_market_run_total(self, item_id: int):
        """
        Update market run total amount
        """
        # Get market_run_id
        query = "SELECT market_run_id FROM market_items WHERE item_id = %s"
        results = self.db.execute_query(query, (item_id,))
        
        if not results:
            return
        
        run_id = results[0]['market_run_id']
        
        # Calculate new total
        total_query = """
        SELECT SUM(total_price) as total
        FROM market_items
        WHERE market_run_id = %s AND is_purchased = TRUE
        """
        total_result = self.db.execute_query(total_query, (run_id,))
        total = total_result[0]['total'] or 0
        
        # Update market run
        update_query = """
        UPDATE market_runs 
        SET total_amount = %s
        WHERE market_run_id = %s
        """
        self.db.execute_update(update_query, (total, run_id))
    
    def complete_market_run(self, run_id: int) -> bool:
        """
        Mark market run as completed and create expenses
        """
        # Get run details
        run = self.get_market_run(run_id)
        if not run:
            return False
        
        # Create expenses from purchased items
        expense_manager = ExpenseManager(self.db)
        
        # Group items by purchaser
        items_by_purchaser = {}
        for item in run['items']:
            if item['is_purchased'] and item['purchased_by']:
                purchaser = item['purchased_by']
                if purchaser not in items_by_purchaser:
                    items_by_purchaser[purchaser] = []
                items_by_purchaser[purchaser].append(item)
        
        # Create expense for each purchaser
        for purchaser_id, items in items_by_purchaser.items():
            total = sum(item['total_price'] for item in items)
            
            # Determine who should share this expense
            shared_items = [i for i in items if i['is_shared']]
            personal_items = [i for i in items if not i['is_shared']]
            
            if shared_items:
                # Create shared expense
                expense_data = {
                    'room_code': run['room_code'],
                    'paid_by': purchaser_id,
                    'amount': sum(i['total_price'] for i in shared_items),
                    'description': f"Market run: {', '.join(i['item_name'] for i in shared_items[:3])}",
                    'category': 'groceries',
                    'split_type': 'equal',
                    'market_name': run['market_name'],
                    'expense_date': run['run_date']
                }
                expense_manager.add_expense(expense_data)
            
            # Handle personal items - create direct owes
            for item in personal_items:
                if item['specific_for']:
                    # Create direct expense for personal item
                    expense_data = {
                        'room_code': run['room_code'],
                        'paid_by': purchaser_id,
                        'amount': item['total_price'],
                        'description': item['item_name'],
                        'category': 'other',
                        'split_type': 'custom',
                        'splits': [{
                            'user_id': item['specific_for'],
                            'amount': item['total_price']
                        }],
                        'market_name': run['market_name'],
                        'expense_date': run['run_date']
                    }
                    expense_manager.add_expense(expense_data)
        
        # Update market run status
        update_query = """
        UPDATE market_runs 
        SET status = 'completed', completed_at = NOW()
        WHERE market_run_id = %s
        """
        self.db.execute_update(update_query, (run_id,))
        
        return True


# ============================================
# INVENTORY MANAGEMENT CLASS
# ============================================

class InventoryManager:
    """
    Handles inventory tracking
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def add_inventory_item(self, item_data: Dict) -> int:
        """
        Add new item to inventory
        """
        query = """
        INSERT INTO inventory (
            room_code, item_name, category, quantity, unit, 
            min_quantity, expiry_date, last_updated_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            item_data['room_code'],
            item_data['item_name'],
            item_data.get('category'),
            item_data.get('quantity', 0),
            item_data.get('unit', 'piece'),
            item_data.get('min_quantity', 1),
            item_data.get('expiry_date'),
            item_data.get('last_updated_by')
        )
        
        return self.db.execute_insert(query, params)
    
    def update_quantity(self, item_id: int, quantity: float, user_id: int) -> bool:
        """
        Update quantity of inventory item
        """
        # Get current quantity
        query = "SELECT quantity, room_code, item_name FROM inventory WHERE item_id = %s"
        current = self.db.execute_query(query, (item_id,))
        
        if not current:
            return False
        
        old_quantity = current[0]['quantity']
        
        # Update quantity
        update_query = """
        UPDATE inventory 
        SET quantity = %s, last_updated_by = %s, last_updated_date = NOW()
        WHERE item_id = %s
        """
        affected = self.db.execute_update(update_query, (quantity, user_id, item_id))
        
        # Check if low stock and notify
        if affected and quantity < current[0]['min_quantity'] and old_quantity >= current[0]['min_quantity']:
            self._notify_low_stock(current[0]['room_code'], current[0]['item_name'], quantity)
        
        return affected > 0
    
    def _notify_low_stock(self, room_code: str, item_name: str, quantity: float):
        """
        Notify roommates about low stock
        """
        user_manager = UserManager(self.db)
        roommates = user_manager.get_roommates(room_code)
        
        notification_manager = NotificationManager(self.db)
        for roommate in roommates:
            notification_manager.create_notification({
                'user_id': roommate['user_id'],
                'type': 'inventory',
                'title': 'Low Stock Alert',
                'message': f"{item_name} is running low ({quantity} left)",
                'reference_type': 'inventory'
            })
    
    def get_low_stock_items(self, room_code: str) -> List[Dict]:
        """
        Get all items below minimum quantity
        """
        query = """
        SELECT * FROM inventory
        WHERE room_code = %s AND quantity < min_quantity
        ORDER BY (quantity / min_quantity) ASC
        """
        return self.db.execute_query(query, (room_code,))
    
    def get_inventory(self, room_code: str, category: str = None) -> List[Dict]:
        """
        Get all inventory items
        """
        query = "SELECT * FROM inventory WHERE room_code = %s"
        params = [room_code]
        
        if category:
            query += " AND category = %s"
            params.append(category)
        
        query += " ORDER BY category, item_name"
        
        return self.db.execute_query(query, tuple(params))
    
    def consume_item(self, item_id: int, quantity: float, user_id: int) -> bool:
        """
        Reduce quantity (when item is used)
        """
        # Get current quantity
        query = "SELECT quantity FROM inventory WHERE item_id = %s"
        current = self.db.execute_query(query, (item_id,))
        
        if not current:
            return False
        
        new_quantity = max(0, current[0]['quantity'] - quantity)
        return self.update_quantity(item_id, new_quantity, user_id)


# ============================================
# CHAT MANAGEMENT CLASS
# ============================================

class ChatManager:
    """
    Handles all chat functionality
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def send_message(self, message_data: Dict) -> int:
        """
        Send a new chat message
        """
        query = """
        INSERT INTO chat_messages (
            room_code, sender_id, message_type, message_text,
            reference_id, reference_type
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            message_data['room_code'],
            message_data['sender_id'],
            message_data.get('message_type', 'text'),
            message_data.get('message_text', ''),
            message_data.get('reference_id'),
            message_data.get('reference_type')
        )
        
        message_id = self.db.execute_insert(query, params)
        
        # Handle mentions
        if message_data.get('mentions'):
            self._add_mentions(message_id, message_data['mentions'])
        
        return message_id
    
    def _add_mentions(self, message_id: int, mentions: List[int]):
        """
        Add user mentions to message
        """
        query = """
        INSERT INTO message_mentions (message_id, user_id)
        VALUES (%s, %s)
        """
        params = [(message_id, user_id) for user_id in mentions]
        
        if params:
            self.db.execute_many(query, params)
    
    def get_room_messages(self, room_code: str, limit: int = 50) -> List[Dict]:
        """
        Get recent messages for a room
        """
        query = """
        SELECT cm.*, u.full_name as sender_name, u.profile_pic
        FROM chat_messages cm
        JOIN users u ON cm.sender_id = u.user_id
        WHERE cm.room_code = %s
        ORDER BY cm.created_at DESC
        LIMIT %s
        """
        messages = self.db.execute_query(query, (room_code, limit))
        
        # Get mentions for each message
        for msg in messages:
            mention_query = """
            SELECT u.user_id, u.full_name
            FROM message_mentions mm
            JOIN users u ON mm.user_id = u.user_id
            WHERE mm.message_id = %s
            """
            msg['mentions'] = self.db.execute_query(mention_query, (msg['message_id'],))
        
        return messages
    
    def mark_mention_read(self, message_id: int, user_id: int) -> bool:
        """
        Mark a mention as read
        """
        query = """
        UPDATE message_mentions 
        SET is_read = TRUE, read_at = NOW()
        WHERE message_id = %s AND user_id = %s
        """
        affected = self.db.execute_update(query, (message_id, user_id))
        return affected > 0
    
    def get_unread_mentions(self, user_id: int) -> List[Dict]:
        """
        Get all unread mentions for a user
        """
        query = """
        SELECT cm.*, mm.message_id, mm.mention_id,
               u.full_name as sender_name
        FROM message_mentions mm
        JOIN chat_messages cm ON mm.message_id = cm.message_id
        JOIN users u ON cm.sender_id = u.user_id
        WHERE mm.user_id = %s AND mm.is_read = FALSE
        ORDER BY cm.created_at DESC
        """
        return self.db.execute_query(query, (user_id,))
    
    def send_system_message(self, room_code: str, message: str, 
                           reference_type: str = None, reference_id: int = None) -> int:
        """
        Send a system-generated message
        """
        message_data = {
            'room_code': room_code,
            'sender_id': 0,  # System user
            'message_type': 'system',
            'message_text': message,
            'reference_id': reference_id,
            'reference_type': reference_type
        }
        return self.send_message(message_data)
    
    def send_expense_message(self, expense_id: int):
        """
        Auto-send message when expense is added
        """
        expense_manager = ExpenseManager(self.db)
        expense = expense_manager.get_expense_details(expense_id)
        
        if not expense:
            return
        
        message = f"💰 New expense: {expense['description']} - ₹{expense['amount']} (paid by {expense['paid_by_name']})"
        
        self.send_system_message(
            room_code=expense['room_code'],
            message=message,
            reference_type='expense',
            reference_id=expense_id
        )
    
    def send_payment_message(self, split_id: int):
        """
        Auto-send message when payment is made
        """
        query = """
        SELECT es.*, e.description, e.room_code,
               u1.full_name as payer_name,
               u2.full_name as receiver_name
        FROM expense_splits es
        JOIN expenses e ON es.expense_id = e.expense_id
        JOIN users u1 ON es.user_id = u1.user_id
        JOIN users u2 ON e.paid_by = u2.user_id
        WHERE es.split_id = %s
        """
        results = self.db.execute_query(query, (split_id,))
        
        if not results:
            return
        
        split = results[0]
        message = f"💸 {split['payer_name']} paid ₹{split['amount_owed']} to {split['receiver_name']} for {split['description']}"
        
        self.send_system_message(
            room_code=split['room_code'],
            message=message,
            reference_type='expense',
            reference_id=split['expense_id']
        )


# ============================================
# NOTIFICATION MANAGEMENT CLASS
# ============================================

class NotificationManager:
    """
    Handles user notifications
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def create_notification(self, notification_data: Dict) -> int:
        """
        Create a new notification
        """
        query = """
        INSERT INTO notifications (
            user_id, notification_type, title, message,
            action_url, reference_id
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            notification_data['user_id'],
            notification_data.get('type', 'general'),
            notification_data.get('title', 'Notification'),
            notification_data.get('message', ''),
            notification_data.get('action_url'),
            notification_data.get('reference_id')
        )
        
        return self.db.execute_insert(query, params)
    
    def get_user_notifications(self, user_id: int, unread_only: bool = False) -> List[Dict]:
        """
        Get notifications for a user
        """
        query = """
        SELECT * FROM notifications
        WHERE user_id = %s
        """
        params = [user_id]
        
        if unread_only:
            query += " AND is_read = FALSE"
        
        query += " ORDER BY created_at DESC LIMIT 50"
        
        return self.db.execute_query(query, tuple(params))
    
    def mark_notification_read(self, notification_id: int) -> bool:
        """
        Mark notification as read
        """
        query = """
        UPDATE notifications 
        SET is_read = TRUE, read_at = NOW()
        WHERE notification_id = %s
        """
        affected = self.db.execute_update(query, (notification_id,))
        return affected > 0
    
    def mark_all_read(self, user_id: int) -> int:
        """
        Mark all user notifications as read
        """
        query = """
        UPDATE notifications 
        SET is_read = TRUE, read_at = NOW()
        WHERE user_id = %s AND is_read = FALSE
        """
        return self.db.execute_update(query, (user_id,))
    
    def delete_old_notifications(self, days: int = 30):
        """
        Delete notifications older than X days
        """
        query = """
        DELETE FROM notifications
        WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)
        """
        return self.db.execute_delete(query, (days,))


# ============================================
# BALANCE CALCULATION CLASS
# ============================================

class BalanceManager:
    """
    Calculates who owes whom
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def get_room_balances(self, room_code: str) -> Dict:
        """
        Get complete balance sheet for a room
        """
        # Get all roommates
        user_manager = UserManager(self.db)
        roommates = user_manager.get_roommates(room_code)
        
        # Initialize balances
        balances = {}
        for user in roommates:
            balances[user['user_id']] = {
                'user_id': user['user_id'],
                'name': user['full_name'],
                'paid': 0,
                'owed': 0,
                'net': 0,
                'profile_pic': user['profile_pic']
            }
        
        # Get all unpaid expenses
        query = """
        SELECT e.expense_id, e.paid_by, e.amount, e.description,
               es.user_id, es.amount_owed, es.is_paid
        FROM expenses e
        JOIN expense_splits es ON e.expense_id = es.expense_id
        WHERE e.room_code = %s AND es.is_paid = FALSE
        """
        expenses = self.db.execute_query(query, (room_code,))
        
        # Calculate totals
        for exp in expenses:
            if not exp['is_paid']:
                # Who paid
                balances[exp['paid_by']]['paid'] += exp['amount_owed']
                # Who owes
                balances[exp['user_id']]['owed'] += exp['amount_owed']
        
        # Calculate net (positive = others owe you, negative = you owe others)
        for user_id in balances:
            balances[user_id]['net'] = balances[user_id]['paid'] - balances[user_id]['owed']
        
        # Calculate simplified settlements
        settlements = self._calculate_settlements(balances)
        
        return {
            'balances': balances,
            'settlements': settlements
        }
    
    def _calculate_settlements(self, balances: Dict) -> List[Dict]:
        """
        Calculate who should pay whom to settle all debts
        """
        # Separate creditors and debtors
        creditors = []
        debtors = []
        
        for user_id, data in balances.items():
            if data['net'] > 0:
                creditors.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'amount': data['net']
                })
            elif data['net'] < 0:
                debtors.append({
                    'user_id': user_id,
                    'name': data['name'],
                    'amount': -data['net']  # Positive amount they owe
                })
        
        # Sort by amount (largest first)
        creditors.sort(key=lambda x: x['amount'], reverse=True)
        debtors.sort(key=lambda x: x['amount'], reverse=True)
        
        # Calculate settlements
        settlements = []
        i = j = 0
        
        while i < len(debtors) and j < len(creditors):
            debtor = debtors[i]
            creditor = creditors[j]
            
            amount = min(debtor['amount'], creditor['amount'])
            
            settlements.append({
                'from_user': debtor['user_id'],
                'from_name': debtor['name'],
                'to_user': creditor['user_id'],
                'to_name': creditor['name'],
                'amount': amount
            })
            
            debtor['amount'] -= amount
            creditor['amount'] -= amount
            
            if debtor['amount'] == 0:
                i += 1
            if creditor['amount'] == 0:
                j += 1
        
        return settlements
    
    def get_user_balance(self, user_id: int) -> Dict:
        """
        Get balance for a specific user
        """
        # Get user's room
        user_manager = UserManager(self.db)
        user = user_manager.get_user_by_id(user_id)
        
        if not user:
            return {}
        
        # Get room balances
        room_balances = self.get_room_balances(user['room_code'])
        
        # Extract this user's balance
        user_balance = room_balances['balances'].get(user_id, {})
        
        # Filter settlements involving this user
        user_settlements = [
            s for s in room_balances['settlements']
            if s['from_user'] == user_id or s['to_user'] == user_id
        ]
        
        return {
            'user': user,
            'balance': user_balance,
            'settlements': user_settlements,
            'all_balances': room_balances['balances']
        }
    
    def get_you_owe_summary(self, user_id: int) -> List[Dict]:
        """
        Get summary of who this user owes money to
        """
        query = """
        SELECT e.expense_id, e.description, e.amount as total_amount,
               e.paid_by, u.full_name as owed_to_name,
               es.amount_owed, es.split_id, e.expense_date
        FROM expense_splits es
        JOIN expenses e ON es.expense_id = e.expense_id
        JOIN users u ON e.paid_by = u.user_id
        WHERE es.user_id = %s AND es.is_paid = FALSE
        ORDER BY e.expense_date DESC
        """
        return self.db.execute_query(query, (user_id,))
    
    def get_owed_to_you_summary(self, user_id: int) -> List[Dict]:
        """
        Get summary of who owes money to this user
        """
        query = """
        SELECT e.expense_id, e.description, e.amount as total_amount,
               es.user_id, u.full_name as owes_from_name,
               es.amount_owed, es.split_id, e.expense_date
        FROM expenses e
        JOIN expense_splits es ON e.expense_id = es.expense_id
        JOIN users u ON es.user_id = u.user_id
        WHERE e.paid_by = %s AND es.is_paid = FALSE
        ORDER BY e.expense_date DESC
        """
        return self.db.execute_query(query, (user_id,))


# ============================================
# SETTLEMENT MANAGEMENT CLASS
# ============================================

class SettlementManager:
    """
    Handles payment settlements between users
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def create_settlement(self, settlement_data: Dict) -> int:
        """
        Record a direct settlement payment
        """
        query = """
        INSERT INTO settlements (
            room_code, from_user, to_user, amount,
            payment_method, transaction_id, payment_date, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            settlement_data['room_code'],
            settlement_data['from_user'],
            settlement_data['to_user'],
            settlement_data['amount'],
            settlement_data.get('payment_method', 'cash'),
            settlement_data.get('transaction_id'),
            settlement_data.get('payment_date', date.today()),
            settlement_data.get('notes')
        )
        
        settlement_id = self.db.execute_insert(query, params)
        
        # Notify receiver
        self._notify_settlement(settlement_id)
        
        return settlement_id
    
    def _notify_settlement(self, settlement_id: int):
        """
        Notify about settlement
        """
        query = """
        SELECT s.*, 
               u1.full_name as from_name,
               u2.full_name as to_name
        FROM settlements s
        JOIN users u1 ON s.from_user = u1.user_id
        JOIN users u2 ON s.to_user = u2.user_id
        WHERE s.settlement_id = %s
        """
        results = self.db.execute_query(query, (settlement_id,))
        
        if not results:
            return
        
        settlement = results[0]
        
        # Notify receiver
        notification_manager = NotificationManager(self.db)
        notification_manager.create_notification({
            'user_id': settlement['to_user'],
            'type': 'settlement',
            'title': 'Payment Received',
            'message': f"{settlement['from_name']} paid you ₹{settlement['amount']}",
            'reference_id': settlement_id,
            'reference_type': 'settlement'
        })
        
        # Also notify sender for confirmation
        notification_manager.create_notification({
            'user_id': settlement['from_user'],
            'type': 'settlement',
            'title': 'Payment Sent',
            'message': f"You paid ₹{settlement['amount']} to {settlement['to_name']}",
            'reference_id': settlement_id,
            'reference_type': 'settlement'
        })
    
    def confirm_settlement(self, settlement_id: int, user_id: int) -> bool:
        """
        Receiver confirms settlement
        """
        query = """
        UPDATE settlements 
        SET confirmed_by_receiver = TRUE,
            confirmation_date = NOW()
        WHERE settlement_id = %s AND to_user = %s
        """
        affected = self.db.execute_update(query, (settlement_id, user_id))
        return affected > 0
    
    def get_room_settlements(self, room_code: str, days: int = 30) -> List[Dict]:
        """
        Get settlement history for a room
        """
        query = """
        SELECT s.*, 
               u1.full_name as from_name,
               u2.full_name as to_name
        FROM settlements s
        JOIN users u1 ON s.from_user = u1.user_id
        JOIN users u2 ON s.to_user = u2.user_id
        WHERE s.room_code = %s 
        AND s.payment_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        ORDER BY s.payment_date DESC
        """
        return self.db.execute_query(query, (room_code, days))


# ============================================
# CHORE MANAGEMENT CLASS
# ============================================

class ChoreManager:
    """
    Handles chore tracking and gamification
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
    
    def create_chore(self, chore_data: Dict) -> int:
        """
        Create a new chore
        """
        query = """
        INSERT INTO chores (
            room_code, chore_name, assigned_to, frequency,
            due_date, points, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            chore_data['room_code'],
            chore_data['chore_name'],
            chore_data.get('assigned_to'),
            chore_data.get('frequency', 'weekly'),
            chore_data.get('due_date'),
            chore_data.get('points', 10),
            chore_data.get('notes')
        )
        
        return self.db.execute_insert(query, params)
    
    def complete_chore(self, chore_id: int, completed_by: int) -> bool:
        """
        Mark chore as completed
        """
        query = """
        UPDATE chores 
        SET status = 'completed',
            completed_date = CURDATE(),
            completed_by = %s
        WHERE chore_id = %s AND status = 'pending'
        """
        affected = self.db.execute_update(query, (completed_by, chore_id))
        
        if affected:
            # Award points
            self._award_points(completed_by, chore_id)
        
        return affected > 0
    
    def _award_points(self, user_id: int, chore_id: int):
        """
        Award points for completing chore
        """
        # Get chore points
        query = "SELECT points FROM chores WHERE chore_id = %s"
        results = self.db.execute_query(query, (chore_id,))
        
        if not results:
            return
        
        points = results[0]['points']
        
        # In a real app, you'd have a points table
        # For now, just notify
        user_manager = UserManager(self.db)
        user = user_manager.get_user_by_id(user_id)
        
        notification_manager = NotificationManager(self.db)
        notification_manager.create_notification({
            'user_id': user_id,
            'type': 'chore',
            'title': 'Chore Completed!',
            'message': f"You earned {points} points for completing chore",
            'reference_id': chore_id,
            'reference_type': 'chore'
        })
    
    def get_pending_chores(self, room_code: str) -> List[Dict]:
        """
        Get all pending chores
        """
        query = """
        SELECT c.*, u.full_name as assigned_to_name
        FROM chores c
        LEFT JOIN users u ON c.assigned_to = u.user_id
        WHERE c.room_code = %s AND c.status = 'pending'
        ORDER BY c.due_date ASC
        """
        return self.db.execute_query(query, (room_code,))
    
    def get_chore_history(self, room_code: str, days: int = 30) -> List[Dict]:
        """
        Get completed chore history
        """
        query = """
        SELECT c.*, 
               u1.full_name as assigned_to_name,
               u2.full_name as completed_by_name
        FROM chores c
        LEFT JOIN users u1 ON c.assigned_to = u1.user_id
        LEFT JOIN users u2 ON c.completed_by = u2.user_id
        WHERE c.room_code = %s 
        AND c.status = 'completed'
        AND c.completed_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        ORDER BY c.completed_date DESC
        """
        return self.db.execute_query(query, (room_code, days))


# ============================================
# DASHBOARD AGGREGATION CLASS
# ============================================

class DashboardManager:
    """
    Aggregates data for the main dashboard
    """
    
    def __init__(self, db: RoommateDatabase):
        self.db = db
        self.user_manager = UserManager(db)
        self.expense_manager = ExpenseManager(db)
        self.balance_manager = BalanceManager(db)
        self.inventory_manager = InventoryManager(db)
        self.chat_manager = ChatManager(db)
        self.notification_manager = NotificationManager(db)
        self.chore_manager = ChoreManager(db)
    
    def get_dashboard_data(self, user_id: int) -> Dict:
        """
        Get all data needed for user dashboard
        """
        # Get user details
        user = self.user_manager.get_user_by_id(user_id)
        if not user:
            return {}
        
        room_code = user['room_code']
        
        # Get roommates
        roommates = self.user_manager.get_roommates(room_code)
        
        # Get balances
        balances = self.balance_manager.get_room_balances(room_code)
        user_balance = balances['balances'].get(user_id, {})
        
        # Get what you owe
        you_owe = self.balance_manager.get_you_owe_summary(user_id)
        
        # Get what's owed to you
        owed_to_you = self.balance_manager.get_owed_to_you_summary(user_id)
        
        # Get recent expenses
        recent_expenses = self.expense_manager.get_room_expenses(room_code, 7)
        
        # Get low stock items
        low_stock = self.inventory_manager.get_low_stock_items(room_code)
        
        # Get recent chat messages
        recent_chats = self.chat_manager.get_room_messages(room_code, 20)
        
        # Get unread notifications
        notifications = self.notification_manager.get_user_notifications(user_id, unread_only=True)
        
        # Get pending chores
        pending_chores = self.chore_manager.get_pending_chores(room_code)
        
        # Get active market runs
        market_query = """
        SELECT * FROM market_runs 
        WHERE room_code = %s AND status IN ('planned', 'in_progress')
        ORDER BY created_at DESC
        """
        active_markets = self.db.execute_query(market_query, (room_code,))
        
        # Get who's out of station
        out_of_station = [
            rm for rm in roommates 
            if rm['is_out_of_station']
        ]
        
        return {
            'user': user,
            'roommates': roommates,
            'room_code': room_code,
            'roommate_count': len(roommates),
            'balances': balances,
            'user_balance': user_balance,
            'you_owe': you_owe,
            'you_owe_total': sum(item['amount_owed'] for item in you_owe),
            'owed_to_you': owed_to_you,
            'owed_to_you_total': sum(item['amount_owed'] for item in owed_to_you),
            'recent_expenses': recent_expenses,
            'low_stock': low_stock,
            'recent_chats': recent_chats,
            'unread_notifications': len(notifications),
            'notifications': notifications[:5],
            'pending_chores': pending_chores,
            'active_markets': active_markets,
            'out_of_station': out_of_station,
            'timestamp': datetime.now().isoformat()
        }


# ============================================
# DATABASE INITIALIZATION FUNCTION
# ============================================

def initialize_database():
    """
    Initialize database with schema.sql
    """
    try:
        # Connect without database selected
        connection = mysql.connector.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            autocommit=True
        )
        
        cursor = connection.cursor()
        
        # Read schema file
        schema_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')
        
        with open(schema_path, 'r') as f:
            sql_script = f.read()
        
        # Split and execute statements
        statements = sql_script.split(';')
        for statement in statements:
            if statement.strip():
                cursor.execute(statement)
        
        cursor.close()
        connection.close()
        
        logger.info("Database initialized successfully")
        return True
        
    except Error as e:
        logger.error(f"Database initialization failed: {e}")
        return False
    except FileNotFoundError:
        logger.error("schema.sql file not found")
        return False


# ============================================
# TEST FUNCTION
# ============================================

def test_database_connection():
    """
    Test database connection
    """
    try:
        with RoommateDatabase() as db:
            result = db.execute_query("SELECT 1 as test")
            if result and result[0]['test'] == 1:
                logger.info("Database connection test successful")
                return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


# ============================================
# EXPORT ALL CLASSES
# ============================================

__all__ = [
    'RoommateDatabase',
    'UserManager',
    'ExpenseManager',
    'MarketManager',
    'InventoryManager',
    'ChatManager',
    'NotificationManager',
    'BalanceManager',
    'SettlementManager',
    'ChoreManager',
    'DashboardManager',
    'initialize_database',
    'test_database_connection'
]

# ============================================
# END OF database.py
# ============================================