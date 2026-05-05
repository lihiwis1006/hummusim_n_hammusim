import sqlite3
import random
import bcrypt  # הוספנו בשביל ליצור את המנהל

DB_NAME = "users.db"

ITEMS = ["גרגירי חומוס", "טחינה", "שום", "לימון", "שמן זית", "פפריקה", "מלח"]


def get_db():
    return sqlite3.connect(DB_NAME, timeout=10)


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # הוספנו את עמודת role! הבררת מחדל היא שחקן רגיל
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        question1 TEXT NOT NULL,
        question2 TEXT NOT NULL,
        role TEXT DEFAULT 'player', 
        failed_attempts INTEGER DEFAULT 0,
        lockout_until TEXT DEFAULT NULL
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        username TEXT NOT NULL,
        item TEXT NOT NULL,
        amount INTEGER DEFAULT 0,
        PRIMARY KEY(username, item),
        FOREIGN KEY(username) REFERENCES users(username)
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hummusim (
        username TEXT NOT NULL,
        amount INTEGER DEFAULT 0,
        PRIMARY KEY(username),
        FOREIGN KEY(username) REFERENCES users(username)
    );""")

    # עדכון הטבלה בלי למחוק את המשתמשים שכבר יצרתי
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN failed_attempts INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN lockout_until TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

    # קריאה לפונקציה שיוצרת מנהל
    create_default_admin()


def create_default_admin():
    """יוצר משתמש מנהל אוטומטית אם הוא לא קיים"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        password_hash = bcrypt.hashpw("Admin123!".encode(), bcrypt.gensalt()).decode()
        cur.execute("""
            INSERT INTO users (username, password_hash, question1, question2, role)
            VALUES (?, ?, ?, ?, ?)
        """, ("admin", password_hash, "admin", "admin", "admin"))
        conn.commit()
    conn.close()

def create_test_users():
    """יוצר משתמשים כדי שנוכל לבצע בדיקות על טבלת החומוסים"""
    conn = get_db()
    cur = conn.cursor()
    for i in range(11,15):
        user = "lihi" + str(i)
        password_hash = bcrypt.hashpw(user.encode(), bcrypt.gensalt()).decode()
        cur.execute("""
            INSERT INTO users (username, password_hash, question1, question2)
            VALUES (?, ?, ?, ?)
        """, (user, password_hash, user, user))
    conn.commit()
    conn.close()

# create_test_users()
# print("created")



def give_reward(username):
    item = random.choice(ITEMS)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO inventory (username, item, amount)
        VALUES (?, ?, 1)
        ON CONFLICT(username, item)
        DO UPDATE SET amount = amount + 1
    """, (username, item))
    conn.commit()
    conn.close()
    return item

def give_every_reward(username):
    """
    פונקציה לצורך בדיקה של הכנת החומוסים וטבלת דירוג
    :param username:
    :return:
    """
    conn = get_db()
    cur = conn.cursor()
    for item in ITEMS:
        cur.execute("""
            INSERT INTO inventory (username, item, amount)
            VALUES (?, ?, 1)
            ON CONFLICT(username, item)
            DO UPDATE SET amount = amount + 1
        """, (username, item))
    conn.commit()
    conn.close()

#give_every_reward("lihi2000")
# print("done")

def add_hummusim_to_test_users():
    for i in range(11,15):
        user = "lihi" + str(i)
        for j in range(i):
            give_every_reward(user)

# add_hummusim_to_test_users()
# print("added")

def get_leaderboard(limit=10):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username, amount FROM hummusim ORDER BY amount DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"rank": rank, "username": row[0], "amount": row[1]} for rank, row in enumerate(rows, start=1)]


def get_user_rank(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT rank FROM (
            SELECT username, RANK() OVER (ORDER BY amount DESC) as rank FROM hummusim
        ) WHERE username = ?
    """, (username,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else None


def get_user_neighborhood(username, window=2):
    user_rank = get_user_rank(username)
    if not user_rank:
        return []

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT rank, username, amount FROM (
            SELECT username, amount, RANK() OVER (ORDER BY amount DESC) as rank FROM hummusim
        ) WHERE rank BETWEEN ? AND ? ORDER BY rank ASC
    """, (user_rank - window, user_rank + window))
    rows = cur.fetchall()
    conn.close()
    return [{"rank": row[0], "username": row[1], "amount": row[2]} for row in rows]