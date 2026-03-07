-- ============================================
-- ROOMMATE MANAGEMENT SYSTEM - DATABASE SCHEMA
-- ============================================

CREATE DATABASE IF NOT EXISTS roommate_system;
USE roommate_system;

-- ============================================
-- TABLE 1: users (Store all roommate information)
-- ============================================
CREATE TABLE users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(15),
    password_hash VARCHAR(255) NOT NULL,
    profile_pic VARCHAR(255) DEFAULT 'default.jpg',
    
    -- Room information
    room_number VARCHAR(20),
    room_code VARCHAR(10), -- Shared code for same room
    
    -- Status tracking
    is_active BOOLEAN DEFAULT TRUE,
    is_out_of_station BOOLEAN DEFAULT FALSE,
    out_station_start DATE,
    out_station_end DATE,
    out_station_reason VARCHAR(255),
    
    -- Preferences
    notification_email BOOLEAN DEFAULT TRUE,
    notification_sms BOOLEAN DEFAULT FALSE,
    dark_mode BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_room_code (room_code),
    INDEX idx_email (email)
);

-- ============================================
-- TABLE 2: expenses (Track all purchases)
-- ============================================
CREATE TABLE expenses (
    expense_id INT PRIMARY KEY AUTO_INCREMENT,
    room_code VARCHAR(10) NOT NULL,
    paid_by INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    description VARCHAR(255) NOT NULL,
    
    -- Categorization
    category ENUM('groceries', 'rent', 'electricity', 'water', 
                  'internet', 'gas', 'dining', 'entertainment', 'other') 
                  DEFAULT 'other',
    
    -- Split type
    split_type ENUM('equal', 'custom', 'percentage') DEFAULT 'equal',
    
    -- Location tracking
    market_name VARCHAR(100),
    location_lat DECIMAL(10, 8),
    location_lng DECIMAL(11, 8),
    
    -- Receipt image
    receipt_image VARCHAR(255),
    
    -- Status
    is_settled BOOLEAN DEFAULT FALSE,
    settled_date DATE,
    
    -- Timestamps
    expense_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (paid_by) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_room (room_code),
    INDEX idx_date (expense_date)
);

-- ============================================
-- TABLE 3: expense_splits (Who owes what for each expense)
-- ============================================
CREATE TABLE expense_splits (
    split_id INT PRIMARY KEY AUTO_INCREMENT,
    expense_id INT NOT NULL,
    user_id INT NOT NULL,
    amount_owed DECIMAL(10, 2) NOT NULL,
    percentage_owed DECIMAL(5, 2),
    
    -- Payment tracking
    is_paid BOOLEAN DEFAULT FALSE,
    paid_date DATE,
    payment_method ENUM('cash', 'upi', 'bank', 'card', 'other') DEFAULT 'cash',
    payment_note VARCHAR(255),
    
    -- Confirmation
    confirmed_by_payer BOOLEAN DEFAULT FALSE,
    confirmed_by_receiver BOOLEAN DEFAULT FALSE,
    confirmation_date TIMESTAMP,
    
    FOREIGN KEY (expense_id) REFERENCES expenses(expense_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE KEY unique_expense_user (expense_id, user_id),
    INDEX idx_user_paid (user_id, is_paid)
);

-- ============================================
-- TABLE 4: market_runs (Group shopping trips)
-- ============================================
CREATE TABLE market_runs (
    market_run_id INT PRIMARY KEY AUTO_INCREMENT,
    room_code VARCHAR(10) NOT NULL,
    created_by INT NOT NULL,
    market_name VARCHAR(100),
    run_date DATE NOT NULL,
    run_time TIME,
    total_amount DECIMAL(10, 2) DEFAULT 0,
    
    -- Status
    status ENUM('planned', 'in_progress', 'completed', 'cancelled') 
           DEFAULT 'planned',
    
    -- Notes
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    
    FOREIGN KEY (created_by) REFERENCES users(user_id),
    INDEX idx_room_status (room_code, status)
);

-- ============================================
-- TABLE 5: market_items (Individual items in market run)
-- ============================================
CREATE TABLE market_items (
    item_id INT PRIMARY KEY AUTO_INCREMENT,
    market_run_id INT NOT NULL,
    added_by INT NOT NULL,
    item_name VARCHAR(100) NOT NULL,
    quantity DECIMAL(10, 2) DEFAULT 1,
    unit VARCHAR(20) DEFAULT 'piece',
    price_per_unit DECIMAL(10, 2),
    total_price DECIMAL(10, 2),
    
    -- Who is this for?
    is_shared BOOLEAN DEFAULT TRUE,
    specific_for INT, -- user_id if not shared
    
    -- Track who bought
    purchased_by INT,
    is_purchased BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (market_run_id) REFERENCES market_runs(market_run_id) ON DELETE CASCADE,
    FOREIGN KEY (added_by) REFERENCES users(user_id),
    FOREIGN KEY (specific_for) REFERENCES users(user_id),
    FOREIGN KEY (purchased_by) REFERENCES users(user_id)
);

-- ============================================
-- TABLE 6: inventory (Track house supplies)
-- ============================================
CREATE TABLE inventory (
    item_id INT PRIMARY KEY AUTO_INCREMENT,
    room_code VARCHAR(10) NOT NULL,
    item_name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    quantity DECIMAL(10, 2) DEFAULT 0,
    unit VARCHAR(20),
    min_quantity DECIMAL(10, 2) DEFAULT 0, -- Alert when below this
    
    -- Tracking
    last_updated_by INT,
    last_updated_date TIMESTAMP,
    expiry_date DATE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (last_updated_by) REFERENCES users(user_id),
    INDEX idx_room_item (room_code, item_name),
    INDEX idx_low_stock (room_code, quantity, min_quantity)
);

-- ============================================
-- TABLE 7: chat_messages (Group chat functionality)
-- ============================================
CREATE TABLE chat_messages (
    message_id INT PRIMARY KEY AUTO_INCREMENT,
    room_code VARCHAR(10) NOT NULL,
    sender_id INT NOT NULL,
    message_type ENUM('text', 'expense', 'payment', 'market', 
                      'inventory', 'system', 'image') DEFAULT 'text',
    message_text TEXT,
    
    -- Reference to other tables
    reference_id INT, -- expense_id, market_run_id, etc.
    reference_type VARCHAR(50),
    
    -- Metadata
    is_pinned BOOLEAN DEFAULT FALSE,
    is_edited BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (sender_id) REFERENCES users(user_id),
    INDEX idx_room_chat (room_code, created_at)
);

-- ============================================
-- TABLE 8: message_mentions (Tag users in chat)
-- ============================================
CREATE TABLE message_mentions (
    mention_id INT PRIMARY KEY AUTO_INCREMENT,
    message_id INT NOT NULL,
    user_id INT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP,
    
    FOREIGN KEY (message_id) REFERENCES chat_messages(message_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE KEY unique_mention (message_id, user_id)
);

-- ============================================
-- TABLE 9: notifications (Push/email notifications)
-- ============================================
CREATE TABLE notifications (
    notification_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    notification_type VARCHAR(50),
    title VARCHAR(255),
    message TEXT,
    
    -- Action links
    action_url VARCHAR(255),
    reference_id INT,
    
    -- Status
    is_read BOOLEAN DEFAULT FALSE,
    is_emailed BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_unread (user_id, is_read)
);

-- ============================================
-- TABLE 10: settlements (Record of payments)
-- ============================================
CREATE TABLE settlements (
    settlement_id INT PRIMARY KEY AUTO_INCREMENT,
    room_code VARCHAR(10) NOT NULL,
    from_user INT NOT NULL,
    to_user INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    
    -- Payment details
    payment_method ENUM('cash', 'upi', 'bank', 'card', 'adjustment') DEFAULT 'cash',
    transaction_id VARCHAR(100),
    payment_date DATE NOT NULL,
    
    -- Confirmation
    confirmed_by_sender BOOLEAN DEFAULT TRUE,
    confirmed_by_receiver BOOLEAN DEFAULT FALSE,
    confirmation_date TIMESTAMP,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (from_user) REFERENCES users(user_id),
    FOREIGN KEY (to_user) REFERENCES users(user_id),
    INDEX idx_room_settlement (room_code, payment_date)
);

-- ============================================
-- TABLE 11: chores (Task management)
-- ============================================
CREATE TABLE chores (
    chore_id INT PRIMARY KEY AUTO_INCREMENT,
    room_code VARCHAR(10) NOT NULL,
    chore_name VARCHAR(100) NOT NULL,
    assigned_to INT,
    frequency ENUM('daily', 'weekly', 'biweekly', 'monthly', 'once') DEFAULT 'weekly',
    
    -- Due date
    due_date DATE,
    completed_date DATE,
    
    -- Points/gamification
    points INT DEFAULT 10,
    
    -- Status
    status ENUM('pending', 'in_progress', 'completed', 'skipped') DEFAULT 'pending',
    completed_by INT,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (assigned_to) REFERENCES users(user_id),
    FOREIGN KEY (completed_by) REFERENCES users(user_id),
    INDEX idx_pending (room_code, status, due_date)
);

-- ============================================
-- TABLE 12: user_sessions (Track logins)
-- ============================================
CREATE TABLE user_sessions (
    session_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP,
    logout_time TIMESTAMP,
    
    is_active BOOLEAN DEFAULT TRUE,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_token (session_token)
);

-- ============================================
-- INSERT SAMPLE DATA
-- ============================================

-- Create a sample room
INSERT INTO users (full_name, email, phone, password_hash, room_number, room_code) VALUES
('John Doe', 'john@email.com', '9876543210', 'hashed_password_here', '101', 'ROOM123'),
('Jane Smith', 'jane@email.com', '9876543211', 'hashed_password_here', '101', 'ROOM123'),
('Bob Wilson', 'bob@email.com', '9876543212', 'hashed_password_here', '101', 'ROOM123'),
('Alice Brown', 'alice@email.com', '9876543213', 'hashed_password_here', '101', 'ROOM123');

-- Sample inventory
INSERT INTO inventory (room_code, item_name, quantity, unit, min_quantity) VALUES
('ROOM123', 'Milk', 0.5, 'liter', 1),
('ROOM123', 'Rice', 2, 'kg', 1),
('ROOM123', 'Onions', 0.2, 'kg', 0.5),
('ROOM123', 'Bread', 1, 'loaf', 1);

-- ============================================
-- CREATE TRIGGERS
-- ============================================

-- Trigger for low inventory alerts
DELIMITER $$
CREATE TRIGGER after_inventory_update
AFTER UPDATE ON inventory
FOR EACH ROW
BEGIN
    IF NEW.quantity < NEW.min_quantity AND OLD.quantity >= OLD.min_quantity THEN
        INSERT INTO notifications (user_id, notification_type, title, message)
        SELECT user_id, 'inventory', 'Low Stock Alert', 
               CONCAT(NEW.item_name, ' is running low (', NEW.quantity, ' ', NEW.unit, ' left)')
        FROM users 
        WHERE room_code = NEW.room_code;
    END IF;
END$$
DELIMITER ;

-- ============================================
-- CREATE VIEWS
-- ============================================

-- View for current balances
CREATE VIEW vw_current_balances AS
SELECT 
    u.room_code,
    u.user_id,
    u.full_name,
    COALESCE(SUM(CASE WHEN e.paid_by = u.user_id THEN es.amount_owed ELSE 0 END), 0) as total_owed_to_you,
    COALESCE(SUM(CASE WHEN es.user_id = u.user_id AND es.is_paid = FALSE THEN es.amount_owed ELSE 0 END), 0) as you_owe_total,
    COALESCE(SUM(CASE WHEN e.paid_by = u.user_id AND es.is_paid = FALSE THEN es.amount_owed ELSE 0 END), 0) as owed_to_you_total
FROM users u
LEFT JOIN expense_splits es ON u.user_id = es.user_id
LEFT JOIN expenses e ON es.expense_id = e.expense_id
WHERE u.is_active = TRUE
GROUP BY u.user_id;

-- View for active chat conversations
CREATE VIEW vw_active_chats AS
SELECT 
    cm.room_code,
    cm.message_id,
    cm.sender_id,
    u.full_name as sender_name,
    cm.message_text,
    cm.message_type,
    cm.created_at,
    COUNT(mm.mention_id) as mention_count
FROM chat_messages cm
JOIN users u ON cm.sender_id = u.user_id
LEFT JOIN message_mentions mm ON cm.message_id = mm.message_id
GROUP BY cm.message_id
ORDER BY cm.created_at DESC;

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

CREATE INDEX idx_expenses_paid ON expense_splits(is_paid);
CREATE INDEX idx_notifications_read ON notifications(is_read);
CREATE INDEX idx_chat_recent ON chat_messages(created_at DESC);
CREATE INDEX idx_market_status ON market_runs(status);

-- ============================================
-- DATABASE COMPLETE
-- ============================================