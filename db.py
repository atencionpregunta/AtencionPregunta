import sqlite3
import threading

db_lock = threading.RLock()

def get_conn():
    conn = sqlite3.connect("database.db", timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
