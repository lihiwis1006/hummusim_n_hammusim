"""
קובץ בדיקות יחידה (Unit Tests) ל-"איקס עיגול חומוס".
מריצים מהשורש של הפרויקט (ליד server.py / auth.py / database.py וכו'):

    python -m unittest tests.py -v

הקובץ מבודד את הבדיקות מ-DB האמיתי על ידי שימוש בקובץ DB זמני, ומאפס את המסד לפני כל בדיקה.
"""

import os
import sys
import time
import gc
import unittest
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# ===== הוספת תיקיית הקוד ל-sys.path =====
# אנו תומכים בשתי מבנים:
#   1. הקבצים נמצאים באותה רמה כמו tests.py (השורש של הפרויקט).
#   2. הקבצים נמצאים בתת-תיקייה בשם hummusim_server.
# מאחר ו-auth.py משתמש ב-"from database import get_db" (ייבוא מוחלט),
# חייבים שהתיקייה שמכילה את database.py תהיה ב-sys.path.
HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [HERE, os.path.join(HERE, "hummusim_server")]
for path in CANDIDATES:
    if os.path.isfile(os.path.join(path, "database.py")):
        sys.path.insert(0, path)
        break
else:
    raise RuntimeError(
        "לא מצאתי את database.py לא בשורש ולא ב-hummusim_server. "
        "הריצי את הבדיקות מהשורש של הפרויקט."
    )

# ===== הכנת DB זמני לפני ייבוא המודולים =====
# יוצרים נתיב לקובץ DB ייחודי לבדיקות (ייחודי לתהליך, כדי לא להתנגש בריצות מקבילות),
# בלי לפתוח file descriptor של OS – אחרת SQLite ב-Windows מקבל "database is locked".
TEST_DB_PATH = os.path.join(
    tempfile.gettempdir(),
    f"hummus_test_{os.getpid()}.db"
)
# מנקים שאריות מהרצה קודמת
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except OSError:
        pass

# מייבאים את המודולים שלנו ומחליפים בכל אחד מהם את DB_NAME
import database
import auth
import game_logic

database.DB_NAME = TEST_DB_PATH


def reset_db():
    """
    מנקה את הנתונים בכל הטבלאות לפני כל בדיקה (במקום DROP TABLE שגורם לקריאות סכימה).
    משתמשים ב-DELETE FROM שהוא מהיר יותר, ומריצים init_db רק כדי להבטיח
    שהטבלאות אכן קיימות (CREATE IF NOT EXISTS).
    """
    # מבטיחים שהטבלאות קיימות (init_db בעצמה משתמשת ב-IF NOT EXISTS)
    database.init_db()

    # מאפסים נתונים – מנסים מספר פעמים אם SQLite ב-Windows אוחז זמנית בקובץ
    last_err = None
    for attempt in range(5):
        try:
            conn = sqlite3.connect(TEST_DB_PATH, timeout=10)
            cur = conn.cursor()
            cur.execute("DELETE FROM inventory")
            cur.execute("DELETE FROM hummusim")
            cur.execute("DELETE FROM users")
            conn.commit()
            conn.close()
            break
        except sqlite3.OperationalError as e:
            last_err = e
            gc.collect()
            time.sleep(0.1)
    else:
        raise last_err  # אם נכשלנו 5 פעמים – נזרוק כדי לראות את השגיאה האמיתית

    # יוצרים מחדש את משתמש ה-admin (init_db כבר קוראת לזה, אבל מחקנו את הטבלה)
    database.create_default_admin()


# ============================================================
# 1. בדיקות מודול auth – הרשמה, התחברות, אימות, איפוס סיסמה
# ============================================================
class TestAuth(unittest.TestCase):
    """בודק את הפונקציות handle_register / handle_login / handle_verification / handle_reset"""

    def setUp(self):
        reset_db()

    # -------- הרשמה --------
    def test_register_success(self):
        """הרשמה תקינה של משתמש חדש מחזירה ok ומכניסה אותו ל-DB"""
        result = auth.handle_register({
            "username": "alice", "password": "Pa$$w0rd",
            "question1": "ירוק", "question2": "כלב"
        })
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["message"], "User registered")

        # בדיקה שהמשתמש קיים ב-DB
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT username, role FROM users WHERE username = ?", ("alice",))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "alice")
        self.assertEqual(row[1], "player")  # ברירת מחדל

    def test_register_password_is_hashed(self):
        """הסיסמה לא נשמרת בטקסט נקי – מכילה $2b$ של bcrypt"""
        auth.handle_register({
            "username": "bob", "password": "MySecret123",
            "question1": "א", "question2": "ב"
        })
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", ("bob",))
        h = cur.fetchone()[0]
        conn.close()
        self.assertNotIn("MySecret123", h)
        self.assertTrue(h.startswith("$2b$"), "ה-Hash לא נראה כמו פלט bcrypt")

    def test_register_duplicate_username(self):
        """הרשמה שנייה עם אותו שם משתמש נכשלת"""
        auth.handle_register({"username": "carol", "password": "x",
                              "question1": "1", "question2": "2"})
        result = auth.handle_register({"username": "carol", "password": "y",
                                       "question1": "3", "question2": "4"})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "Username exists")

    def test_register_missing_fields(self):
        """הרשמה ללא שדות חובה נכשלת"""
        result = auth.handle_register({"username": "dan"})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "Missing fields")

    # -------- התחברות --------
    def test_login_success(self):
        """כניסה עם פרטים נכונים מחזירה token ו-role"""
        auth.handle_register({"username": "eve", "password": "abc123",
                              "question1": "א", "question2": "ב"})
        result = auth.handle_login({"username": "eve", "password": "abc123"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["message"], "Login successful")
        self.assertIn("token", result)
        self.assertEqual(result["role"], "player")

    def test_login_wrong_password_increments_attempts(self):
        """סיסמה שגויה מגדילה את failed_attempts ב-1"""
        auth.handle_register({"username": "frank", "password": "right",
                              "question1": "א", "question2": "ב"})
        result = auth.handle_login({"username": "frank", "password": "wrong"})
        self.assertEqual(result["status"], "error")
        self.assertIn("נותרו לך 2", result["message"])

        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT failed_attempts FROM users WHERE username = ?", ("frank",))
        attempts = cur.fetchone()[0]
        conn.close()
        self.assertEqual(attempts, 1)

    def test_login_three_failures_triggers_security_questions(self):
        """אחרי 3 ניסיונות שגויים – status הופך ל-security_questions"""
        auth.handle_register({"username": "gina", "password": "right",
                              "question1": "א", "question2": "ב"})
        for _ in range(2):
            auth.handle_login({"username": "gina", "password": "wrong"})
        result = auth.handle_login({"username": "gina", "password": "wrong"})
        self.assertEqual(result["status"], "security_questions")

    def test_login_unknown_user(self):
        """כניסה למשתמש שלא קיים מחזירה שגיאה גנרית (לא חושפת אם השם קיים או לא)"""
        result = auth.handle_login({"username": "ghost", "password": "x"})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "Invalid credentials")

    def test_login_resets_attempts_on_success(self):
        """אחרי כניסה מוצלחת מאופס מונה הניסיונות"""
        auth.handle_register({"username": "hank", "password": "right",
                              "question1": "א", "question2": "ב"})
        auth.handle_login({"username": "hank", "password": "wrong"})
        auth.handle_login({"username": "hank", "password": "right"})

        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT failed_attempts FROM users WHERE username = ?", ("hank",))
        attempts = cur.fetchone()[0]
        conn.close()
        self.assertEqual(attempts, 0)

    # -------- שאלות אבטחה --------
    def test_verification_correct_answers(self):
        """תשובות נכונות לשאלות מחזירות ok"""
        auth.handle_register({"username": "ivy", "password": "x",
                              "question1": "אדום", "question2": "חתול"})
        result = auth.handle_verification({
            "username": "ivy", "question1": "אדום", "question2": "חתול"
        })
        self.assertEqual(result["status"], "ok")

    def test_verification_wrong_answers_lock_account(self):
        """תשובות שגויות חוסמות את החשבון לחצי שעה"""
        auth.handle_register({"username": "jane", "password": "x",
                              "question1": "אדום", "question2": "חתול"})
        result = auth.handle_verification({
            "username": "jane", "question1": "כחול", "question2": "כלב"
        })
        self.assertEqual(result["status"], "blocked")

        # בודקים שהחסימה אכן נרשמה ב-DB
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT lockout_until FROM users WHERE username = ?", ("jane",))
        lockout = cur.fetchone()[0]
        conn.close()
        self.assertIsNotNone(lockout)
        # החסימה צריכה להיות בעתיד
        self.assertGreater(datetime.fromisoformat(lockout), datetime.now())

    def test_login_during_lockout_is_rejected(self):
        """כניסה בזמן חסימה מוחזרת עם הודעת חסימה"""
        auth.handle_register({"username": "kate", "password": "x",
                              "question1": "א", "question2": "ב"})
        # יוצרים חסימה ידנית
        future = (datetime.now() + timedelta(minutes=10)).isoformat()
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET lockout_until = ? WHERE username = ?",
                    (future, "kate"))
        conn.commit()
        conn.close()

        result = auth.handle_login({"username": "kate", "password": "x"})
        self.assertEqual(result["status"], "error")
        self.assertIn("חסום", result["message"])

    def test_expired_lockout_is_cleared_on_login(self):
        """אם החסימה פגה, היא מתנקה אוטומטית בכניסה הבאה"""
        auth.handle_register({"username": "lily", "password": "right",
                              "question1": "א", "question2": "ב"})
        past = (datetime.now() - timedelta(minutes=1)).isoformat()
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET lockout_until = ? WHERE username = ?",
                    (past, "lily"))
        conn.commit()
        conn.close()

        result = auth.handle_login({"username": "lily", "password": "right"})
        self.assertEqual(result["status"], "ok")

    # -------- איפוס סיסמה --------
    def test_reset_password_success(self):
        """איפוס סיסמה תקין משנה את הסיסמה ב-DB"""
        auth.handle_register({"username": "mia", "password": "old",
                              "question1": "א", "question2": "ב"})
        result = auth.handle_reset({
            "username": "mia", "new password": "newPass1!",
            "confirm password": "newPass1!"
        })
        self.assertEqual(result["status"], "ok")
        # הסיסמה הישנה כבר לא עובדת, החדשה כן
        self.assertEqual(auth.handle_login({"username": "mia", "password": "old"})["status"],
                         "error")
        self.assertEqual(auth.handle_login({"username": "mia", "password": "newPass1!"})["status"],
                         "ok")

    def test_reset_password_mismatch(self):
        """אם הסיסמה והאישור לא זהים – נכשל"""
        auth.handle_register({"username": "noa", "password": "x",
                              "question1": "א", "question2": "ב"})
        result = auth.handle_reset({
            "username": "noa", "new password": "abc",
            "confirm password": "different"
        })
        self.assertEqual(result["status"], "error")
        self.assertIn("not match", result["message"])


# ============================================================
# 2. בדיקות JWT – יצירה, פיענוח, חתימה, תפוגה
# ============================================================
class TestJWT(unittest.TestCase):

    def test_create_and_decode_roundtrip(self):
        """JWT שיצרנו יוכל להיפתח עם user_id ו-role נכונים"""
        token = auth.create_token("john", "player")
        payload = auth.decode_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["user_id"], "john")
        self.assertEqual(payload["role"], "player")

    def test_decode_tampered_token_returns_none(self):
        """טוקן עם תו שונה בחתימה נדחה"""
        token = auth.create_token("admin", "admin")
        tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
        self.assertIsNone(auth.decode_token(tampered))

    def test_decode_garbage_token_returns_none(self):
        """מחרוזת שאינה JWT בכלל – מוחזר None ולא Exception"""
        self.assertIsNone(auth.decode_token("not.a.real.jwt"))

    def test_decode_expired_token_returns_none(self):
        """טוקן שפג תוקפו נדחה"""
        import jwt as pyjwt
        payload = {
            "user_id": "x", "role": "player",
            "exp": datetime.utcnow() - timedelta(seconds=1),
            "iat": datetime.utcnow() - timedelta(seconds=10),
        }
        expired = pyjwt.encode(payload, auth.SECRET_KEY, algorithm="HS256")
        self.assertIsNone(auth.decode_token(expired))


# ============================================================
# 3. בדיקות לוגיקת משחק – check_winner ו-handle_making_hummus
# ============================================================
class TestGameLogic(unittest.TestCase):

    def setUp(self):
        reset_db()

    # -------- check_winner --------
    def test_winner_top_row(self):
        board = ["X", "X", "X", " ", " ", " ", " ", " ", " "]
        self.assertEqual(game_logic.check_winner(board), "X")

    def test_winner_diagonal(self):
        board = ["O", " ", " ", " ", "O", " ", " ", " ", "O"]
        self.assertEqual(game_logic.check_winner(board), "O")

    def test_winner_column(self):
        board = ["X", " ", " ", "X", " ", " ", "X", " ", " "]
        self.assertEqual(game_logic.check_winner(board), "X")

    def test_no_winner_yet(self):
        board = ["X", "O", " ", " ", " ", " ", " ", " ", " "]
        self.assertIsNone(game_logic.check_winner(board))

    def test_tie(self):
        # לוח מלא בלי מנצח
        board = ["X", "O", "X",
                 "X", "O", "O",
                 "O", "X", "X"]
        self.assertEqual(game_logic.check_winner(board), "tie")

    def test_blanks_not_winners(self):
        """שלושה רווחים ברצף לא יוצרים ניצחון מזויף"""
        board = [" "] * 9
        self.assertIsNone(game_logic.check_winner(board))

    # -------- handle_making_hummus --------
    def _grant_all_items(self, username, amount=1):
        """עוזר: נותן למשתמש 1 מכל פריט"""
        conn = database.get_db()
        cur = conn.cursor()
        for item in database.ITEMS:
            cur.execute("""
                INSERT INTO inventory (username, item, amount) VALUES (?, ?, ?)
                ON CONFLICT(username, item) DO UPDATE SET amount = ?
            """, (username, item, amount, amount))
        conn.commit()
        conn.close()

    def test_make_hummus_with_all_items(self):
        """7 פריטים בכמות 1 → חומוס מוכן, כל פריט יורד ל-0"""
        auth.handle_register({"username": "p1", "password": "x",
                              "question1": "א", "question2": "ב"})
        self._grant_all_items("p1", 1)

        result = game_logic.handle_making_hummus({"username": "p1"})
        self.assertEqual(result["status"], "hummus")
        self.assertEqual(result["amount"], "1")

        # מאמתים שהפריטים אכן ירדו
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT MIN(amount), MAX(amount) FROM inventory WHERE username = ?", ("p1",))
        mn, mx = cur.fetchone()
        conn.close()
        self.assertEqual(mn, 0)
        self.assertEqual(mx, 0)

    def test_make_hummus_missing_items(self):
        """משתמש עם 4 פריטים בלבד לא יכול להכין"""
        auth.handle_register({"username": "p2", "password": "x",
                              "question1": "א", "question2": "ב"})
        conn = database.get_db()
        cur = conn.cursor()
        for item in database.ITEMS[:4]:
            cur.execute("INSERT INTO inventory VALUES (?, ?, ?)", ("p2", item, 1))
        conn.commit()
        conn.close()

        result = game_logic.handle_making_hummus({"username": "p2"})
        self.assertEqual(result["status"], "error")

    def test_make_hummus_zero_of_some_item(self):
        """7 פריטים אבל אחד מהם ב-0 – לא ניתן להכין"""
        auth.handle_register({"username": "p3", "password": "x",
                              "question1": "א", "question2": "ב"})
        conn = database.get_db()
        cur = conn.cursor()
        for i, item in enumerate(database.ITEMS):
            amount = 0 if i == 0 else 1
            cur.execute("INSERT INTO inventory VALUES (?, ?, ?)", ("p3", item, amount))
        conn.commit()
        conn.close()

        result = game_logic.handle_making_hummus({"username": "p3"})
        self.assertEqual(result["status"], "error")

    def test_make_hummus_increases_counter(self):
        """הכנת חומוס פעמיים → counter עולה ל-2"""
        auth.handle_register({"username": "p4", "password": "x",
                              "question1": "א", "question2": "ב"})
        self._grant_all_items("p4", 2)

        r1 = game_logic.handle_making_hummus({"username": "p4"})
        r2 = game_logic.handle_making_hummus({"username": "p4"})
        self.assertEqual(r1["amount"], "1")
        self.assertEqual(r2["amount"], "2")


# ============================================================
# 4. בדיקות מסד הנתונים – פרסים, leaderboard, neighborhood
# ============================================================
class TestDatabase(unittest.TestCase):

    def setUp(self):
        reset_db()

    def test_give_reward_returns_valid_item(self):
        """give_reward מחזיר פריט אמיתי מתוך 7 ושומר אותו ב-DB"""
        auth.handle_register({"username": "u1", "password": "x",
                              "question1": "א", "question2": "ב"})
        item = database.give_reward("u1")
        self.assertIn(item, database.ITEMS)

        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT amount FROM inventory WHERE username=? AND item=?",
                    ("u1", item))
        amount = cur.fetchone()[0]
        conn.close()
        self.assertEqual(amount, 1)

    def test_give_reward_upserts(self):
        """אם מקבלים פעמיים את אותו פריט – הכמות עולה ל-2"""
        # נשתמש ב-give_every_reward כדי לקבל בוודאות אותו פריט פעמיים
        auth.handle_register({"username": "u2", "password": "x",
                              "question1": "א", "question2": "ב"})
        database.give_every_reward("u2")
        database.give_every_reward("u2")

        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT amount FROM inventory WHERE username = ?", ("u2",))
        amounts = [row[0] for row in cur.fetchall()]
        conn.close()
        self.assertTrue(all(a == 2 for a in amounts))

    def test_leaderboard_sorted_descending(self):
        """leaderboard ממוין לפי כמות חומוסים בסדר יורד"""
        for name, hummusim in [("a", 5), ("b", 10), ("c", 2)]:
            auth.handle_register({"username": name, "password": "x",
                                  "question1": "1", "question2": "2"})
            conn = database.get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO hummusim VALUES (?, ?)", (name, hummusim))
            conn.commit()
            conn.close()

        board = database.get_leaderboard()
        self.assertEqual([row["username"] for row in board], ["b", "a", "c"])
        self.assertEqual([row["rank"] for row in board], [1, 2, 3])

    def test_user_neighborhood(self):
        """neighborhood מחזיר window=2 שכנים מעל ומתחת"""
        users = [("a", 50), ("b", 40), ("c", 30), ("d", 20), ("e", 10)]
        for name, h in users:
            auth.handle_register({"username": name, "password": "x",
                                  "question1": "1", "question2": "2"})
            conn = database.get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO hummusim VALUES (?, ?)", (name, h))
            conn.commit()
            conn.close()

        # c (במקום 3) צריך לראות את a, b, c, d, e (עם window=2)
        neighborhood = database.get_user_neighborhood("c", window=2)
        names = [row["username"] for row in neighborhood]
        self.assertEqual(set(names), {"a", "b", "c", "d", "e"})

    def test_user_neighborhood_for_unknown_user(self):
        """משתמש שאין לו חומוסים – מחזיר רשימה ריקה"""
        result = database.get_user_neighborhood("nobody")
        self.assertEqual(result, [])


# ============================================================
# 5. בדיקות אבטחה – SQL injection, התחזות, hashing
# ============================================================
class TestSecurity(unittest.TestCase):

    def setUp(self):
        reset_db()

    def test_sql_injection_in_username_register(self):
        """ניסיון להזריק SQL בשם משתמש – נשמר כמחרוזת ליטרלית, לא רץ"""
        evil = "evil'; DROP TABLE users; --"
        result = auth.handle_register({
            "username": evil, "password": "x",
            "question1": "א", "question2": "ב"
        })
        self.assertEqual(result["status"], "ok")
        # טבלת users עדיין קיימת ושלמה
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        cur.execute("SELECT username FROM users WHERE username = ?", (evil,))
        row = cur.fetchone()
        conn.close()
        self.assertGreaterEqual(count, 1)
        self.assertIsNotNone(row)
        self.assertEqual(row[0], evil)

    def test_sql_injection_in_login(self):
        """' OR 1=1 -- בלוגין לא מבצע bypass"""
        auth.handle_register({"username": "real", "password": "secret",
                              "question1": "א", "question2": "ב"})
        result = auth.handle_login({
            "username": "' OR 1=1 --", "password": "anything"
        })
        self.assertEqual(result["status"], "error")

    def test_password_hashing_uses_unique_salt(self):
        """אותה סיסמה לשני משתמשים יוצרת hash שונה (Salt ייחודי)"""
        auth.handle_register({"username": "twin1", "password": "samepass",
                              "question1": "א", "question2": "ב"})
        auth.handle_register({"username": "twin2", "password": "samepass",
                              "question1": "א", "question2": "ב"})
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT username, password_hash FROM users WHERE username IN (?, ?)",
                    ("twin1", "twin2"))
        hashes = {row[0]: row[1] for row in cur.fetchall()}
        conn.close()
        self.assertNotEqual(hashes["twin1"], hashes["twin2"])

    def test_jwt_tampered_role_rejected(self):
        """אי אפשר לקחת JWT, להחליף role ל-admin ולהשתמש בו"""
        import jwt as pyjwt

        # יוצרים טוקן רגיל של player
        original = auth.create_token("user", "player")

        # מנסים לזייף עם מפתח חתימה אחר אבל role=admin
        forged = pyjwt.encode(
            {"user_id": "user", "role": "admin",
             "exp": datetime.utcnow() + timedelta(hours=1),
             "iat": datetime.utcnow()},
            "WRONG_SECRET", algorithm="HS256"
        )
        self.assertIsNone(auth.decode_token(forged))

    def test_default_admin_created(self):
        """ב-init_db נוצר משתמש admin עם role=admin"""
        conn = database.get_db()
        cur = conn.cursor()
        cur.execute("SELECT role FROM users WHERE username = 'admin'")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "admin")


# ============================================================
# 6. בדיקת AI – יצירת סיסמה (עם mocking, לא תלוי באינטרנט)
# ============================================================
class TestAIPassword(unittest.TestCase):

    def setUp(self):
        # מייבאים בתוך setUp כדי שלא ייכשל אם ai_utils לא קיים
        # (אחרי שה-path הוסף בראש הקובץ, הייבוא הרגיל יעבוד)
        try:
            import ai_utils
            self.ai_utils = ai_utils
        except Exception as e:
            self.skipTest(f"ai_utils לא נטען: {e}")

    def test_ai_password_returns_string(self):
        """generate_ai_password מחזיר string – או מ-Groq או מ-fallback"""
        # ה-mock מבטיח שהבדיקה תעבוד גם בלי אינטרנט / API key
        fake_completion = MagicMock()
        fake_completion.choices = [MagicMock(message=MagicMock(content=" Aa1!Bb2@ "))]

        with patch.object(self.ai_utils.client.chat.completions, "create",
                          return_value=fake_completion):
            password = self.ai_utils.generate_ai_password()
            self.assertIsInstance(password, str)
            self.assertEqual(password, "Aa1!Bb2@")  # עם strip()

    def test_ai_password_fallback_on_error(self):
        """אם ה-API קורס – חוזר ערך הגיבוי TempP@ssw0rd!"""
        with patch.object(self.ai_utils.client.chat.completions, "create",
                          side_effect=Exception("API down")):
            password = self.ai_utils.generate_ai_password()
            self.assertEqual(password, "TempP@ssw0rd!")


# ============================================================
# 7. בדיקות אינטגרציה לשרת (חלקי – דורש שרת חי)
# ============================================================
@unittest.skipUnless(os.getenv("RUN_INTEGRATION") == "1",
                     "מוגדר רק כשה-env var RUN_INTEGRATION=1, ושרת רץ ברקע על 127.0.0.1:5000")
class TestServerIntegration(unittest.TestCase):
    """
    בדיקות המקצה לקצה. דורשות:
        1. ש-server.py רץ ברקע (python server.py)
        2. שערך RUN_INTEGRATION=1 בסביבה
    הבדיקות מדמות לקוח ב-Sockets+TLS וכותבות JSON ישירות.
    """

    HOST = "127.0.0.1"
    PORT = 5000

    def _connect(self):
        import socket, ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock = ctx.wrap_socket(raw, server_hostname=self.HOST)
        sock.connect((self.HOST, self.PORT))
        return sock

    def _send_recv(self, sock, message):
        import json
        sock.send(json.dumps(message).encode())
        data = sock.recv(8192).decode()
        return json.loads(data)

    def test_unknown_action_without_token_rejected(self):
        sock = self._connect()
        try:
            resp = self._send_recv(sock, {"action": "world_rank"})
            self.assertEqual(resp["status"], "error")
            self.assertIn("טוקן", resp["message"])
        finally:
            sock.close()

    def test_register_and_login_via_socket(self):
        sock = self._connect()
        try:
            uname = f"int_{int(time.time())}"
            r1 = self._send_recv(sock, {
                "action": "register", "username": uname, "password": "x",
                "question1": "א", "question2": "ב"
            })
            self.assertEqual(r1["status"], "ok")
            r2 = self._send_recv(sock, {
                "action": "login", "username": uname, "password": "x"
            })
            self.assertEqual(r2["status"], "ok")
            self.assertIn("token", r2)
        finally:
            sock.close()


# ============================================================
# ניקוי בסיום הריצה
# ============================================================
def tearDownModule():
    """ניקוי קובץ ה-DB הזמני בסוף הריצה (אם Windows מאפשר)"""
    import gc
    gc.collect()  # מוודא שאין connections פתוחים בזיכרון
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            # ב-Windows הקובץ עלול להישאר נעול – לא קריטי, נמחק אוטומטית
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)