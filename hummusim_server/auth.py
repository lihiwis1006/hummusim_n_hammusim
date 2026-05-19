import bcrypt
import sqlite3
import jwt
import os
from datetime import datetime, timedelta
from database import get_db
from dotenv import load_dotenv

# המפתח הסודי שבעזרתו אנחנו חותמים על הטוקנים.
SECRET_KEY = os.getenv("JWT_SECRET", "super_secret_tls_jwt_key_2024_hummus_is_life")
load_dotenv()
# שליפת ה-Pepper (אם הוא לא קיים ב-env, נשתמש בברירת מחדל ריקה - אבל עדיף שיהיה)
PEPPER = os.getenv("PASSWORD_PEPPER", "")


def create_token(username: str, role: str) -> str:
    """מייצר JWT חתום עם פרטי המשתמש והתפקיד שלו"""
    # המידע שנרצה לשמור בטוקן
    payload = {
        "user_id": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=1),  # תוקף לשעה
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str):
    """מפענח ובודק את תקינות הטוקן"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None  # הטוקן פג תוקף
    except jwt.InvalidTokenError:
        return None  # הטוקן מזויף או לא תקין


def handle_register(data):
    username = data.get("username")
    password = data.get("password")
    q1 = data.get("question1")
    q2 = data.get("question2")

    if not all([username, password, q1, q2]):
        return {"status": "error", "message": "Missing fields"}

    # --- השלב הקריטי: הוספת ה-Pepper לסיסמה לפני ה-Hashing ---
    # אנחנו מחברים את ה-Pepper לסיסמה הגולמית
    password_with_pepper = password + PEPPER

    # bcrypt מייצר Salt פנימי אוטומטית בתוך ה-Hash
    password_hash = bcrypt.hashpw(password_with_pepper.encode(), bcrypt.gensalt())

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, password_hash, question1, question2)
            VALUES (?, ?, ?, ?)
            """,
            (username, password_hash.decode(), q1, q2)
        )
        conn.commit()
        conn.close()
        return {"status": "ok", "message": "User registered"}
    except sqlite3.IntegrityError:
        return {"status": "error", "message": "Username exists"}


def handle_login(data):
    username = data.get("username")
    password = data.get("password")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT password_hash, failed_attempts, lockout_until, role FROM users WHERE username = ?", (username,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"status": "error", "message": "Invalid credentials"}

    # חילוץ 4 העמודות שביקשנו מהמסד
    password_hash, failed_attempts, lockout_until, role = row

    # 1. בדיקת חסימה לפני שמנסים בכלל לבדוק סיסמה
    if lockout_until:
        lockout_time = datetime.fromisoformat(lockout_until)
        now = datetime.now()
        if now < lockout_time:
            minutes_left = int((lockout_time - now).total_seconds() / 60) + 1
            conn.close()
            return {"status": "error", "message": f"החשבון חסום. נסה שוב בעוד {minutes_left} דקות."}
        else:
            # עבר זמן החסימה, מאפסים אותה במסד
            cur.execute("UPDATE users SET lockout_until = NULL, failed_attempts = 0 WHERE username = ?", (username,))
            conn.commit()
            failed_attempts = 0

    # 2. בדיקת סיסמה
    password_with_pepper = password + PEPPER
    if bcrypt.checkpw(password_with_pepper.encode(), password_hash.encode()):
        # התחברות מוצלחת! נאפס את מונה הניסיונות וניצור טוקן
        cur.execute("UPDATE users SET failed_attempts = 0, lockout_until = NULL WHERE username = ?", (username,))
        conn.commit()
        conn.close()

        token = create_token(username, role)
        return {
            "status": "ok",
            "message": "Login successful",
            "token": token,
            "role": role
        }
    else:
        # סיסמה שגויה! מעלים את מספר הניסיונות
        new_attempts = failed_attempts + 1

        if new_attempts >= 3:
            # הגענו ל-3 ניסיונות - מעבירים את הלקוח לשאלות אימות
            cur.execute("UPDATE users SET failed_attempts = ? WHERE username = ?", (new_attempts, username))
            conn.commit()
            conn.close()
            return {"status": "security_questions", "message": "3 ניסיונות שגויים. ענה על שאלות האבטחה לאיפוס סיסמה."}
        else:
            cur.execute("UPDATE users SET failed_attempts = ? WHERE username = ?", (new_attempts, username))
            conn.commit()
            conn.close()
            return {"status": "error", "message": f"סיסמה שגויה. נותרו לך {3 - new_attempts} ניסיונות."}


def handle_verification(data):
    username = data.get("username")
    q1 = data.get("question1")
    q2 = data.get("question2")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT question1, question2 FROM users WHERE username = ?", (username,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"status": "error", "message": "Invalid credentials"}

    db_q1, db_q2 = row

    if db_q1 == q1 and db_q2 == q2:
        conn.close()
        return {"status": "ok", "message": "Verification successful"}
    else:
        # המשתמש טעה בשאלות האימות! חוסמים אותו לחצי שעה
        lockout_time = (datetime.now() + timedelta(minutes=30)).isoformat()
        cur.execute("UPDATE users SET lockout_until = ?, failed_attempts = 0 WHERE username = ?",
                    (lockout_time, username))
        conn.commit()
        conn.close()
        return {"status": "blocked", "message": "תשובות שגויות. החשבון נחסם לחצי שעה!"}


def handle_reset(data):
    username = data.get("username")
    new_password = data.get("new password")
    confirm_password = data.get("confirm password")

    if not all([username, new_password, confirm_password]):
        return {"status": "error", "message": "Missing fields"}

    if new_password != confirm_password:
        return {"status": "error", "message": "Passwords do not match"}

    password_with_pepper = new_password + PEPPER
    password_hash = bcrypt.hashpw(password_with_pepper.encode(), bcrypt.gensalt())

    conn = get_db()
    cur = conn.cursor()
    # איפוס הסיסמה מנקה אוטומטית את היסטוריית החסימות ומונה הניסיונות
    cur.execute(
        """
            UPDATE users 
            SET password_hash = ?, failed_attempts = 0, lockout_until = NULL
            WHERE username = ?
        """,
        (password_hash.decode(), username)
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Password reset successful"}