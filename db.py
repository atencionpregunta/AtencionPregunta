import sqlite3
import threading
import os

db_lock = threading.RLock()
DB_PATH = "database.db"

def get_conn():

    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
