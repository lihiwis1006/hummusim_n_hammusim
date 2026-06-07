import socket
import ssl
import threading
import json
from json import JSONDecoder
import random
import base64
import os

from database import init_db, get_db, give_reward, get_leaderboard, get_user_neighborhood
# ייבאנו גם את decode_token מ-auth
from auth import handle_register, handle_login, handle_verification, handle_reset, decode_token
from game_logic import check_winner, handle_making_hummus
from ai_utils import generate_ai_password

HOST = "0.0.0.0"
PORT = 5000

# קבצי ההצפנה שיצרנו
CERT_FILE = "cert.pem"
KEY_FILE = "key.pem"


class GameServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port

        # 1. הגדרת אבטחת TLS
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            self.ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
        except FileNotFoundError:
            print("שגיאה: לא נמצאו קבצי ההצפנה (cert.pem, key.pem).")
            print("אנא צרי אותם בעזרת הפקודת openssl.")
            exit(1)
        # כי גרסאות קודמות נחשבות פרוצות
        self.ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        # יצירת סוקט רגיל
        self.raw_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # שימוש חוזר באותה הכתובת במקרה של קריסת שרת
        self.raw_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.raw_server.bind((self.host, self.port))

        self.games = {}
        self.waiting_x_o_player = None
        self.waiting_number_player = None
        self.usernames = {}
        self.lock = threading.Lock()

        init_db()

    def start(self):
        # השרת מתחיל להאזין לחיבורים
        self.raw_server.listen()
        # 2. עטיפת השרת הרגיל ב-TLS
        self.server = self.ctx.wrap_socket(self.raw_server, server_side=True)
        print(f"[*] שרת מאובטח (TLS+JWT) מאזין על {self.host}:{self.port}")

        while True:
            try:
                conn, addr = self.server.accept()
                thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                thread.start()
            except ssl.SSLError as e:
                print(f"SSL Error: {e}")

    def send_json(self, conn, message):
        try:
            conn.send(json.dumps(message).encode())
        except Exception:
            pass

    def start_x_o_game(self, player1, player2):
        game_id = f"game_{random.randint(1000, 9999)}"
        self.games[game_id] = {
            "players": [player1, player2],
            "symbols": {player1: "X", player2: "O"},
            "board": [" "] * 9,
            "turn": player1
        }
        print(f"[GAME STARTED] {game_id}")
        self.send_json(player1, {"status": "assign_symbol", "symbol": "X", "game_id": game_id})
        self.send_json(player2, {"status": "assign_symbol", "symbol": "O", "game_id": game_id})
        self.send_x_o_board_update(game_id)

    def start_number_game(self, player1, player2):
        game_id = f"numgame_{random.randint(1000, 9999)}"
        self.games[game_id] = {
            "type": "number",
            "players": [player1, player2],
            "secret": random.randint(1, 100),  # השרת מגריל מספר בין 1 ל-100
            "turn": player1
        }
        print(f"[NUMBER GAME STARTED] {game_id} (Secret: {self.games[game_id]['secret']})")

        # מודיע לשחקנים שהמשחק התחיל
        for p in [player1, player2]:
            self.send_json(p, {
                "status": "start_number_game",
                "game_id": game_id,
                "turn": p == player1  # True עבור השחקן הראשון
            })

    def send_x_o_board_update(self, game_id):
        if game_id not in self.games:
            return

        game = self.games[game_id]
        winner = check_winner(game["board"])

        for p in game["players"]:
            self.send_json(p, {
                "status": "update",
                "board": game["board"],
                "turn": game["turn"] == p,
                "winner": winner
            })

        if winner in ["X", "O"]:
            for p in game["players"]:
                if game["symbols"][p] == winner:
                    username = self.usernames.get(p)
                    if username:
                        prize = give_reward(username)
                        self.send_json(p, {"status": "reward", "item": prize})
            del self.games[game_id]
        elif winner == "tie":
            del self.games[game_id]

    def handle_guess_number(self, conn, message):
        """מטפל בניחוש של שחקן במהלך משחק מספרים"""
        game_id = message.get("game_id")

        # נוודא שהמשתמש באמת שלח מספר כדי למנוע קריסה בשרת
        try:
            guess = int(message.get("guess"))
        except (ValueError, TypeError):
            self.send_json(conn, {"status": "error", "message": "קלט לא חוקי, נא לשלוח מספרים בלבד."})
            return

        game = self.games.get(game_id)

        # מוודאים שהמשחק קיים, שהוא מסוג מספרים, ושזה התור של השחקן
        if game and game.get("type") == "number" and conn == game["turn"]:
            secret = game["secret"]
            guesser_name = self.usernames.get(conn, "שחקן")

            # בדיקת הניחוש
            if guess == secret:
                result_msg = f"{guesser_name} ניחש {guess} וצדק! 🎉"
                is_winner = True
            elif guess > secret:
                result_msg = f"{guesser_name} ניחש {guess} - גבוה מדי ⬆️"
                is_winner = False
            else:
                result_msg = f"{guesser_name} ניחש {guess} - נמוך מדי ⬇️"
                is_winner = False

            # העברת תור אם אין ניצחון
            if not is_winner:
                game["turn"] = [p for p in game["players"] if p != conn][0]

            # עדכון שני השחקנים
            for p in game["players"]:
                self.send_json(p, {
                    "status": "number_update",
                    "message": result_msg,
                    "turn": game["turn"] == p,
                    "winner": is_winner,
                    "is_me": p == conn  # עוזר ללקוח לדעת אם הוא המנצח/מפסיד
                })

            # אם יש ניצחון, מחלקים פרס ומוחקים את המשחק
            if is_winner:
                prize = give_reward(guesser_name)
                self.send_json(conn, {"status": "reward", "item": prize})
                del self.games[game_id]

    def handle_client(self, conn, addr):
        print(f"[+] TLS Connected: {addr}")
        buffer = ""
        decoder = JSONDecoder()

        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break

                buffer += data.decode()

                while buffer:
                    buffer = buffer.lstrip()
                    try:
                        message, index = decoder.raw_decode(buffer)
                        buffer = buffer[index:]

                        action = message.get("action")

                        # ==========================================
                        # אזור חופשי (Public Routes) - לא דורש טוקן
                        # ==========================================
                        if action == "register":
                            self.send_json(conn, handle_register(message))
                        elif action == "password":
                            self.send_json(conn, {"status": "password", "password": generate_ai_password()})
                        elif action == "login":
                            req_username = message.get("username")

                            # בדיקה: האם המשתמש כבר מחובר ממקום אחר?
                            if req_username in self.usernames.values():
                                self.send_json(conn, {"status": "error", "message": "משתמש זה כבר מחובר ממכשיר אחר!"})
                            else:
                                response = handle_login(message)
                                if response.get("status") == "ok":
                                    # שומרים את החיבור מיד אחרי התחברות מוצלחת
                                    self.usernames[conn] = req_username
                                self.send_json(conn, response)
                        elif action == "verification":
                            self.send_json(conn, handle_verification(message))
                        elif action == "reset":
                            self.send_json(conn, handle_reset(message))

                        # ==========================================
                        # אזור מאובטח (Protected Routes) - דורש JWT!
                        # ==========================================
                        else:
                            token = message.get("token")
                            if not token:
                                self.send_json(conn, {"status": "error", "message": "חסר טוקן התחברות (JWT)!"})
                                continue

                            # 3. פענוח ובדיקת הטוקן
                            payload = decode_token(token)
                            if not payload:
                                self.send_json(conn, {"status": "error",
                                                        "message": "טוקן לא תקין או פג תוקף. נא להתחבר מחדש."})
                                continue

                            # חילוץ המידע מתוך הטוקן
                            username = payload.get("user_id")
                            role = payload.get("role")

                            # בדיקה: האם מישהו אחר משתמש כרגע בשם הזה מחיבור אחר?
                            active_connections = [c for c, u in self.usernames.items() if
                                                    u == username and c != conn]
                            if active_connections:
                                self.send_json(conn, {"status": "error",
                                                        "message": "החשבון מחובר ממכשיר אחר. אי אפשר לבצע פעולות."})
                                continue

                            # שומרים בשרת מי נמצא על ה-Socket הזה
                            self.usernames[conn] = username

                            if action == "match":
                                with self.lock:
                                    if self.waiting_x_o_player is None:
                                        self.waiting_x_o_player = conn
                                        self.send_json(conn, {"status": "waiting"})
                                    else:
                                        self.start_x_o_game(self.waiting_x_o_player, conn)
                                        self.waiting_x_o_player = None

                            elif action == "match_number":
                                with self.lock:
                                    if self.waiting_number_player is None:
                                        self.waiting_number_player = conn
                                        self.send_json(conn, {"status": "waiting"})
                                    else:
                                        self.start_number_game(self.waiting_number_player, conn)
                                        self.waiting_number_player = None

                            elif action == "guess_number":
                                self.handle_guess_number(conn, message)

                            elif action == "logout":
                                # מוציאים את המשתמש מרשימת המחוברים הפעילים
                                if conn in self.usernames:
                                    disconnected_user = self.usernames.pop(conn)
                                    print(f"[*] המשתמש {disconnected_user} התנתק מהמערכת.")

                                self.send_json(conn, {"status": "ok", "message": "התנתקת בהצלחה"})

                            elif action == "move":
                                game_id, pos = message.get("game_id"), message.get("position")
                                if not isinstance(pos, int) or not (0 <= pos <= 8):
                                    return
                                game = self.games.get(game_id)
                                if game and conn == game["turn"] and game["board"][pos] == " ":
                                    game["board"][pos] = game["symbols"][conn]
                                    game["turn"] = [p for p in game["players"] if p != conn][0]
                                    self.send_x_o_board_update(game_id)

                            elif action == "get_image_file":
                                file_path = r"hummus_recipe.png"

                                if os.path.exists(file_path):
                                    with open(file_path, "rb") as f:
                                        # קריאה והמרה לטקסט
                                        encoded_image = base64.b64encode(f.read()).decode('utf-8')

                                    response = {
                                        "status": "save_recipe_file",
                                        "image_data": encoded_image,
                                        "filename": "hummus_recipe.png",  # שם ברירת המחדל
                                        "extension": ".png"  # הסיומת הנכונה
                                    }
                                    # שליחה עם \n בסוף כדי לעזור ל-raw_decode בלקוח
                                    conn.sendall((json.dumps(response) + "\n").encode())
                                else:
                                    print(f"Error: File {file_path} not found.")

                            elif action == "inventory":
                                conn_db = get_db()
                                cur = conn_db.cursor()
                                cur.execute("SELECT item, amount FROM inventory WHERE username = ?", (username,))
                                self.send_json(conn, {"status": "inventory", "items": cur.fetchall()})
                                conn_db.close()

                            elif action == "hummus":
                                message["username"] = username  # כעת אנחנו סומכים רק על הטוקן, לא על הלקוח!
                                self.send_json(conn, handle_making_hummus(message))

                            elif action == "world_rank":
                                self.send_json(conn, {"status": "rank", "rank": get_leaderboard()})

                            elif action == "personal_rank":
                                print("hello world")
                                self.send_json(conn, {"status": "rank", "rank": get_user_neighborhood(username)})

                            # ==========================================
                            # אזור מנהלים בלבד (RBAC - Admin Route)
                            # ==========================================
                            elif action == "give_free_hummus":
                                if role != "admin":
                                    self.send_json(conn, {"status": "error",
                                                          "message": "Access Denied: פעולה זו שמורה למנהלים בלבד!"})
                                else:
                                    # מנהל יכול לתת לעצמו או למישהו אחר פרס חינם!
                                    target_user = message.get("target_user", username)
                                    prize = give_reward(target_user)
                                    self.send_json(conn, {"status": "reward", "item": prize})
                                    print(f"[ADMIN] המנהל {username} העניק {prize} ל-{target_user}")

                            else:
                                self.send_json(conn, {"status": "error", "message": "פעולה לא חוקית"})

                    except json.JSONDecodeError:
                        break

        except Exception as e:
            print("Client Error:", e)

        finally:
            self.disconnect_client(conn, addr)

    def disconnect_client(self, conn, addr):
        with self.lock:
            if self.waiting_x_o_player == conn:
                self.waiting_x_o_player = None

        for game_id, game in list(self.games.items()):
            if conn in game["players"]:

                other_player = [p for p in game["players"] if p != conn][0]

                try:
                    # משחק ניחוש מספרים
                    if game.get("type") == "number":

                        self.send_json(other_player, {
                            "status": "number_update",
                            "message": "🎉 היריב התנתק! ניצחת טכנית.",
                            "turn": False,
                            "winner": True,
                            "is_me": True
                        })

                        other_username = self.usernames.get(other_player)

                        if other_username:
                            self.send_json(other_player, {
                                "status": "reward",
                                "item": give_reward(other_username)
                            })

                    # איקס עיגול
                    else:
                        self.send_json(other_player, {
                            "status": "update",
                            "board": game["board"],
                            "turn": False,
                            "winner": game["symbols"][other_player]
                        })

                        other_username = self.usernames.get(other_player)

                        if other_username:
                            self.send_json(other_player, {
                                "status": "reward",
                                "item": give_reward(other_username)
                            })

                except Exception as e:
                    print("Disconnect handling error:", e)

                del self.games[game_id]
                break
        self.usernames.pop(conn, None)
        conn.close()
        print(f"[-] Disconnected: {addr}")


if __name__ == "__main__":
    my_server = GameServer(HOST, PORT)
    my_server.start()