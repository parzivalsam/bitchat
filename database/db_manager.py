import sqlite3
import os
from datetime import datetime

class DBManager:
    def __init__(self, db_path="chat_history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                device_name TEXT NOT NULL,
                last_seen TIMESTAMP
            )
        ''')

        # Create Chats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                chat_name TEXT,
                chat_type TEXT DEFAULT 'single', -- 'single' or 'group'
                shared_secret TEXT
            )
        ''')
        
        # Migration for chats table
        try:
            cursor.execute('ALTER TABLE chats ADD COLUMN shared_secret TEXT')
        except sqlite3.OperationalError:
            pass # Column already exists

        # Create Messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                chat_id TEXT,
                sender_id TEXT,
                message_text TEXT,
                timestamp TIMESTAMP,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY(chat_id) REFERENCES chats(chat_id),
                FOREIGN KEY(sender_id) REFERENCES users(user_id)
            )
        ''')

        # Run migration for existing DBs to add 'status' column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE messages ADD COLUMN status TEXT DEFAULT "pending"')
        except sqlite3.OperationalError:
            pass # Column already exists

        # Create Group Members table for group chats
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_members (
                chat_id TEXT,
                user_id TEXT,
                PRIMARY KEY (chat_id, user_id),
                FOREIGN KEY(chat_id) REFERENCES chats(chat_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')

        conn.commit()
        conn.close()

    def add_or_update_user(self, user_id, device_name):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO users (user_id, device_name, last_seen)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                device_name=excluded.device_name,
                last_seen=excluded.last_seen
        ''', (user_id, device_name, now))
        conn.commit()
        conn.close()

    def get_user(self, user_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
        
    def get_all_users(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users ORDER BY last_seen DESC')
        users = cursor.fetchall()
        conn.close()
        return users

    def create_chat(self, chat_id, chat_name, chat_type='single'):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO chats (chat_id, chat_name, chat_type)
            VALUES (?, ?, ?)
        ''', (chat_id, chat_name, chat_type))
        conn.commit()
        conn.close()

    def update_chat_secret(self, chat_id, secret):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE chats SET shared_secret = ? WHERE chat_id = ?', (secret, chat_id))
        conn.commit()
        conn.close()

    def get_chat_secret(self, chat_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT shared_secret FROM chats WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def get_chats(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Get chats along with their latest message
        cursor.execute('''
            SELECT c.chat_id, c.chat_name, c.chat_type, 
                   (SELECT message_text FROM messages m WHERE m.chat_id = c.chat_id ORDER BY timestamp DESC LIMIT 1) as last_msg,
                   (SELECT timestamp FROM messages m WHERE m.chat_id = c.chat_id ORDER BY timestamp DESC LIMIT 1) as last_time
            FROM chats c
            ORDER BY last_time DESC
        ''')
        chats = cursor.fetchall()
        conn.close()
        return chats

    def save_message(self, message_id, chat_id, sender_id, message_text, timestamp=None, status="pending"):
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO messages (message_id, chat_id, sender_id, message_text, timestamp, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (message_id, chat_id, sender_id, message_text, timestamp, status))
        conn.commit()
        conn.close()

    def update_message_status(self, message_id, status):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE messages SET status = ? WHERE message_id = ?', (status, message_id))
        conn.commit()
        conn.close()

    def get_messages(self, chat_id, limit=50):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT message_id, chat_id, sender_id, message_text, timestamp, status 
            FROM messages 
            WHERE chat_id = ? 
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (chat_id, limit))
        messages = cursor.fetchall()
        conn.close()
        return messages

    def get_pending_messages(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Find all messages we sent that are still pending
        cursor.execute("SELECT message_id, chat_id, message_text FROM messages WHERE status = 'pending' AND sender_id != chat_id")
        messages = cursor.fetchall()
        conn.close()
        return messages

    def add_group_member(self, chat_id, user_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO group_members (chat_id, user_id)
            VALUES (?, ?)
        ''', (chat_id, user_id))
        conn.commit()
        conn.close()
        
    def get_group_members(self, chat_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM group_members WHERE chat_id = ?', (chat_id,))
        members = [row[0] for row in cursor.fetchall()]
        conn.close()
        return members
