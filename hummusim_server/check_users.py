# קוד להצגה של המשתמשים והסיסמאות שלהם
import sqlite3
from database import init_db

init_db()

conn = sqlite3.connect("users.db")
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", cur.fetchall())

cur.execute("SELECT username FROM users")
print("Users:", cur.fetchall())

conn.close()
