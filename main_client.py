import socket
import json
import threading
import customtkinter as ctk
from json import JSONDecoder
import ssl
import base64
from tkinter import filedialog, messagebox
from PIL import Image
import os

HOST = "127.0.0.1"
PORT = 5000

# הגדרת צבעים ורודים לשימוש כללי
COLORS = {
    "PINK_MAIN": "#F4B8DA",
    "PINK_HOVER": "#FF1493",
    "PINK_BG": "#FDE4F2",
    "TEXT_COLOR": "#000000",
    "DARK_PINK": "#E37BAE"
}

# הגדרת ערכת הנושא של CustomTkinter
ctk.set_appearance_mode("light")


# ==========================================
# 1. מחלקת הבסיס למשחקים (מודולריות)
# ==========================================
class BaseGameFrame(ctk.CTkFrame):
    def __init__(self, parent, send_json_callback, show_frame_callback):
        super().__init__(parent, fg_color=COLORS["PINK_BG"])
        self.send_json = send_json_callback
        self.show_frame = show_frame_callback

        self.game_id = None
        self.symbol = None
        self.is_my_turn = False
        self.username = None
        self.logo_data = None
        self.logo_label = None

    def start_game(self, game_id, symbol, username):
        """פונקציה שמופעלת כשהשרת שולח התחלת משחק"""
        self.game_id = game_id
        self.symbol = symbol
        self.username = username
        self.is_my_turn = False
        self.build_ui()

    def build_ui(self):
        """כל משחק חייב לממש את בניית הממשק שלו כאן"""
        script_dir = os.path.dirname(os.path.realpath(__file__))
        logo_path = os.path.join(script_dir, "hummusim_n_hammusim_logo.png")

        try:
            # פתיחת התמונה עם Pillow
            pil_image = Image.open(logo_path)

            # יצירת אובייקט ה-Image של CustomTkinter
            self.logo_data = ctk.CTkImage(light_image=pil_image,
                                          dark_image=pil_image,
                                          size=(150, 150))

            # הצגה בתוך Label
            self.logo_label = ctk.CTkLabel(self, text="", image=self.logo_data)
            self.logo_label.pack(pady=10)

        except Exception as e:
            print(f"שגיאה בטעינת הלוגו: {e}")
            self.logo_label = ctk.CTkLabel(self, text="Logo not found")
            self.logo_label.pack(pady=10)
        pass

    def handle_update(self, data):
        """כל משחק חייב לממש איך הוא מטפל בעדכון מהשרת"""
        pass


# ==========================================
# 2. מחלקת איקס עיגול (הלוגיקה של המשחק עצמו)
# ==========================================
class TicTacToeGame(BaseGameFrame):
    def __init__(self, parent, send_json_callback, show_frame_callback):
        super().__init__(parent, send_json_callback, show_frame_callback)
        self.buttons = []
        self.status_label = None
        self.back_btn = None
        self.menu_back_btn = None
        self.inventory_btn = None

    def build_ui(self):
        # ניקוי הממשק במידה ויש שאריות
        for widget in self.winfo_children():
            widget.destroy()

        self.status_label = ctk.CTkLabel(
            self, text="המשחק מתחיל...", font=("Arial", 20, "bold"), text_color=COLORS["DARK_PINK"]
        )
        self.status_label.pack()

        # מסגרת ללוח המשחק
        board_frame = ctk.CTkFrame(self, fg_color=COLORS["DARK_PINK"])
        board_frame.pack(pady=10)

        self.buttons = []
        for i in range(9):
            btn = ctk.CTkButton(
                board_frame, text="", width=100, height=100,
                font=("Arial", 40, "bold"),
                fg_color="white", text_color=COLORS["DARK_PINK"], hover_color=COLORS["PINK_BG"],
                command=lambda pos=i: self.make_move(pos)
            )
            row = i // 3
            col = i % 3
            btn.grid(row=row, column=col, padx=5, pady=5)
            self.buttons.append(btn)

        # כפתורים שיוצגו בסוף המשחק או במהלך המשחק
        self.inventory_btn = ctk.CTkButton(
            self, text="במלאי צפה 🎒", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            command=self.request_inventory
        )
        # self.inventory_btn.pack(pady=10)

        self.back_btn = ctk.CTkButton(
            self, text="חזור למשחק / המתנה", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            command=self.start_a_match
        )

        self.menu_back_btn = ctk.CTkButton(
            self, text="הבית לעמוד בחזרה", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            command=lambda: self.show_frame("main_menu")
        )

    def make_move(self, pos):
        if self.is_my_turn and self.buttons[pos].cget("text") == "":
            self.send_json({
                "action": "move",
                "game_id": self.game_id,
                "position": pos
            })

    def request_inventory(self):
        self.send_json({"action": "inventory", "username": self.username})

    def start_a_match(self):
        self.send_json({"action": "match", "username": self.username})

    def handle_update(self, data):
        board = data["board"]
        self.is_my_turn = data["turn"]
        winner = data.get("winner")

        # עדכון טקסט הכפתורים
        for i, val in enumerate(board):
            text = "" if val == " " else val
            color = COLORS["PINK_MAIN"] if val == "X" else COLORS["DARK_PINK"]
            self.buttons[i].configure(text=text, text_color=color)

        # עדכון סטטוס תור וניצחון
        if winner:
            self.is_my_turn = False
            self.back_btn.pack(pady=10)
            self.menu_back_btn.pack(pady=10)
            self.inventory_btn.pack(pady=10)

            if winner == "tie":
                self.status_label.configure(text="🤝 המשחק הסתיים בתיקו!")
            elif winner == self.symbol:
                self.status_label.configure(text="🎉 ניצחת במשחק! מחכה לפרס...")
            else:
                self.status_label.configure(text="😢 הפסדת. בהצלחה פעם הבאה!")

            # איפוס מזהה משחק
            self.game_id = None
        else:
            if self.is_my_turn:
                self.status_label.configure(text=f"תורך לשחק! ({self.symbol})")
            else:
                self.status_label.configure(text=f"המתן לתור היריב...")


# ==========================================
# 2.5 משחק נחש את המספר (יורש מ-BaseGameFrame)
# ==========================================
class NumberGuessGame(BaseGameFrame):
    def __init__(self, parent, send_json_callback, show_frame_callback):
        super().__init__(parent, send_json_callback, show_frame_callback)
        self.turn_lbl = None
        self.history_box = None
        self.guess_entry = None
        self.guess_btn = None
        self.back_btn = None

    def start_game(self, game_id, is_my_turn, username):
        # אנחנו עוקפים את ה-start_game המקורי כי כאן אין "symbol" אלא רק מי מתחיל
        self.game_id = game_id
        self.is_my_turn = is_my_turn
        self.username = username
        self.build_ui()
        self.update_turn_display()

    def build_ui(self):
        # ניקוי הממשק
        for widget in self.winfo_children():
            widget.destroy()

        # אנחנו קוראים ל-build_ui של מחלקת הבסיס כדי לקבל את הלוגו המשותף
        super().build_ui()

        title_lbl = ctk.CTkLabel(self, text="נחש את המספר (1-100)!", font=("Arial", 24, "bold"),
                                 text_color=COLORS["DARK_PINK"])
        title_lbl.pack(pady=10)

        self.turn_lbl = ctk.CTkLabel(self, text="...", font=("Arial", 18))
        self.turn_lbl.pack(pady=5)

        # תיבת טקסט שתציג את ההיסטוריה
        self.history_box = ctk.CTkTextbox(self, width=350, height=180, font=("Arial", 14),
                                          text_color=COLORS["DARK_PINK"], border_color=COLORS["PINK_MAIN"],
                                          border_width=2)
        self.history_box.pack(pady=10)

        self.guess_entry = ctk.CTkEntry(self, placeholder_text="הכנס מספר", justify="center")
        self.guess_entry.pack(pady=5)

        self.guess_btn = ctk.CTkButton(self, text="שלח ניחוש", fg_color=COLORS["PINK_MAIN"],
                                       hover_color=COLORS["PINK_HOVER"], command=self.send_guess)
        self.guess_btn.pack(pady=10)

        self.back_btn = ctk.CTkButton(self, text="חזור לתפריט הראשי", fg_color=COLORS["PINK_MAIN"],
                                      hover_color=COLORS["PINK_HOVER"], command=lambda: self.show_frame("main_menu"))

    def update_turn_display(self):
        if self.is_my_turn:
            self.turn_lbl.configure(text="תורך לנחש!", text_color="green")
            self.guess_btn.configure(state="normal")
        else:
            self.turn_lbl.configure(text="המתן לתור היריב...", text_color="orange")
            self.guess_btn.configure(state="disabled")

    def send_guess(self):
        guess_val = self.guess_entry.get()
        if guess_val.isdigit():
            self.send_json({
                "action": "guess_number",
                "game_id": self.game_id,
                "guess": int(guess_val)
            })
            self.guess_entry.delete(0, 'end')
        else:
            messagebox.showwarning("שגיאה", "נא להכניס מספרים בלבד!")

    def handle_update(self, data):
        # טיפול בעדכון שמתקבל מהשרת
        msg = data.get("message")
        self.history_box.insert("end", msg + "\n")
        self.history_box.see("end")

        winner = data.get("winner")
        if winner:
            self.is_my_turn = False
            self.update_turn_display()
            is_me = data.get("is_me")

            if is_me:
                self.turn_lbl.configure(text="🎉 צדקת! ניצחת במשחק! מחכה לפרס...", text_color="green")
            else:
                self.turn_lbl.configure(text="😢 הפסדת! היריב הקדים אותך.", text_color="red")

            self.guess_entry.pack_forget()
            self.guess_btn.pack_forget()
            self.back_btn.pack(pady=10)
        else:
            self.is_my_turn = data.get("turn")
            self.update_turn_display()

# ==========================================
# 3. הלקוח הראשי (מנהל חיבורים, מסכים כלליים)
# ==========================================
class MainClient(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("איקס עיגול חומוס - מהדורה ורודה 🌸")
        self.geometry("700x700")
        self.configure(fg_color=COLORS["PINK_BG"])
        script_dir = os.path.dirname(os.path.realpath(__file__))
        logo_path = os.path.join(script_dir, "hummusim_n_hammusim_logo.png")

        try:
            # פתיחת התמונה עם Pillow
            pil_image = Image.open(logo_path)

            # יצירת אובייקט ה-Image של CustomTkinter
            self.logo_data = ctk.CTkImage(light_image=pil_image,
                                          dark_image=pil_image,
                                          size=(150, 150))

            # הצגה בתוך Label
            self.logo_label = ctk.CTkLabel(self, text="", image=self.logo_data)

        except Exception as e:
            print(f"שגיאה בטעינת הלוגו: {e}")
            self.logo_label = ctk.CTkLabel(self, text="Logo not found")

        # משתנים חדשים לאבטחה!
        self.sock = None
        self.token = None
        self.role = None

        self.connect_to_server()

        self.username = None
        self.rank = None

        # המשתנה שיחזיק את תצוגת המשחק הפעיל
        self.active_game_frame = None

        # משתני חלונות קיימים שלך
        self.username_entry = None
        self.password_entry = None
        self.show_password_var = None
        self.show_password_check = None
        self.show_password_label = None
        self.generate_btn = None
        self.q1_entry = None
        self.q2_entry = None
        self.login_btn = None
        self.mode_var = None
        self.switch = None
        self.error_label = None
        self.status_label = None
        self.inventory_text = None
        self.admin_btn = None
        self.ans1_entry = None
        self.ans2_entry = None
        self.new_pass_entry = None
        self.confirm_pass_entry = None

        # בניית חלונות הממשק
        self.frames = {}
        self.create_auth_frame()
        self.create_main_menu_frame()
        self.create_waiting_frame()
        self.create_inventory_frame()
        self.create_rank_frame()
        self.create_verification_frame()
        self.create_reset_frame()

        # הצגת מסך ההתחברות בהתחלה
        self.show_frame("auth")

        # התחלת תהליך האזנה לשרת ברקע
        self.listen_thread = threading.Thread(target=self.listen_to_server, daemon=True)
        self.listen_thread.start()

    def connect_to_server(self):
        try:
            # הגדרות TLS מקלות לצורכי פיתוח מקומי
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # עוטפים את הסוקט בהצפנה!
            self.sock = context.wrap_socket(raw_socket, server_hostname=HOST)
            self.sock.connect((HOST, PORT))
        except Exception as e:
            print(f"Connection error: {e}")

    def send_json(self, message):
        try:
            # הזרקת ה-JWT לכל הפעולות שדורשות הרשאה
            public_actions = ["login", "register", "password", "verification", "reset"]
            if self.token and message.get("action") not in public_actions:
                message["token"] = self.token

            self.sock.send(json.dumps(message).encode())
        except Exception as e:
            print(f"Send error: {e}")

    # ==================== תצוגת חלונות ====================

    def show_frame(self, frame_name):
        # הסתרת כל המסכים הרגילים
        for frame in self.frames.values():
            frame.pack_forget()

        # הסתרת מסך המשחק אם הוא קיים ואינו המסך המבוקש
        if self.active_game_frame and frame_name != "game":
            self.active_game_frame.pack_forget()

        # הצגת המסך המבוקש
        if frame_name == "game" and self.active_game_frame:
            self.active_game_frame.pack(fill="both", expand=True)
        elif frame_name in self.frames:
            self.frames[frame_name].pack(fill="both", expand=True)

    # ==================== יצירת מסכים ====================

    def create_auth_frame(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["PINK_BG"])
        self.frames["auth"] = frame

        self.logo_label.pack(pady=10)

        title = ctk.CTkLabel(frame, text="🌸 ברוכים הבאים 🌸", font=("Arial", 28, "bold"), text_color=COLORS["DARK_PINK"])
        title.pack()

        self.username_entry = ctk.CTkEntry(frame, placeholder_text="שם משתמש", justify="center", width=200,
                                           border_color=COLORS["PINK_MAIN"])
        self.username_entry.pack(pady=10)

        self.password_entry = ctk.CTkEntry(frame, placeholder_text="סיסמה", show="*", justify="center", width=200,
                                           border_color=COLORS["PINK_MAIN"])
        self.password_entry.pack(pady=10)

        self.show_password_var = ctk.BooleanVar(value=False)

        checkbox_line = ctk.CTkFrame(frame, fg_color="transparent", width=350)
        checkbox_line.pack(pady=0)
        checkbox_line.pack_propagate(False)
        checkbox_line.configure(height=20)

        self.show_password_check = ctk.CTkCheckBox(
            checkbox_line,
            text="",
            variable=self.show_password_var,
            command=self.toggle_password_visibility,
            text_color=COLORS["DARK_PINK"],
            fg_color=COLORS["PINK_MAIN"],
            hover_color=COLORS["PINK_HOVER"],
            border_color=COLORS["PINK_MAIN"],
            checkbox_width=18,
            checkbox_height=18,
        )
        self.show_password_check.pack(side="right", padx=(5, 0))

        self.show_password_label = ctk.CTkLabel(
            checkbox_line, text="הצג סיסמה", font=("Arial", 12), text_color=COLORS["DARK_PINK"]
        )
        self.show_password_label.pack(side="right")

        self.generate_btn = ctk.CTkButton(
            frame, text="generate password with AI", fg_color=COLORS["PINK_MAIN"],
            hover_color=COLORS["PINK_HOVER"], command=self.generate_password
        )

        self.q1_entry = ctk.CTkEntry(frame, placeholder_text="שאלה 1 (להרשמה בלבד)", justify="center", width=200,
                                     border_color=COLORS["PINK_MAIN"])
        self.q2_entry = ctk.CTkEntry(frame, placeholder_text="שאלה 2 (להרשמה בלבד)", justify="center", width=200,
                                     border_color=COLORS["PINK_MAIN"])

        self.login_btn = ctk.CTkButton(
            frame, text="התחברות", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            command=self.do_login
        )
        self.login_btn.pack(pady=10)

        self.mode_var = ctk.StringVar(value="login")
        self.switch = ctk.CTkSwitch(
            frame, text="החלף להרשמה", variable=self.mode_var, onvalue="register", offvalue="login",
            command=self.toggle_auth_mode, progress_color=COLORS["PINK_MAIN"]
        )
        self.switch.pack(pady=10, before=self.username_entry)

        self.error_label = ctk.CTkLabel(frame, text="", text_color="red", font=("Arial", 14))
        self.error_label.pack(pady=10)

    def create_waiting_frame(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["PINK_BG"])
        self.frames["waiting"] = frame

        label = ctk.CTkLabel(frame, text="⏳ מחפש יריב שווה כוחות...", font=("Arial", 24, "bold"),
                             text_color=COLORS["DARK_PINK"])
        label.pack(expand=True)

    def create_verification_frame(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["PINK_BG"])
        self.frames["verification_frame"] = frame

        title = ctk.CTkLabel(frame, text="אימות זהות", font=("Arial", 24, "bold"), text_color=COLORS["DARK_PINK"])
        title.pack(pady=20)

        # שדות לתשובות
        self.ans1_entry = ctk.CTkEntry(frame, placeholder_text="תשובה לשאלה 1", width=200)
        self.ans1_entry.pack(pady=10)

        self.ans2_entry = ctk.CTkEntry(frame, placeholder_text="תשובה לשאלה 2", width=200)
        self.ans2_entry.pack(pady=10)

        verify_btn = ctk.CTkButton(
            frame, text="אמת תשובות",
            fg_color=COLORS["PINK_MAIN"],
            command=self.submit_verification
        )
        verify_btn.pack(pady=20)

    def create_reset_frame(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["PINK_BG"])
        self.frames["reset_password"] = frame

        ctk.CTkLabel(frame, text="בחירת סיסמה חדשה", font=("Arial", 20)).pack(pady=20)

        self.new_pass_entry = ctk.CTkEntry(frame, placeholder_text="סיסמה חדשה", show="*", width=200)
        self.new_pass_entry.pack(pady=10)

        self.confirm_pass_entry = ctk.CTkEntry(frame, placeholder_text="אימות סיסמה", show="*", width=200)
        self.confirm_pass_entry.pack(pady=10)

        reset_btn = ctk.CTkButton(
            frame, text="עדכן סיסמה",
            command=self.submit_reset
        )
        reset_btn.pack(pady=20)

    def create_main_menu_frame(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["PINK_BG"])
        self.frames["main_menu"] = frame

        self.logo_label.pack(pady=10)

        title = ctk.CTkLabel(frame, text="🌸 תפריט ראשי 🌸", font=("Arial", 32, "bold"), text_color=COLORS["DARK_PINK"])
        title.pack()

        # כפתור איקס עיגול
        x_o_btn = ctk.CTkButton(
            frame, text="שחק איקס-עיגול 🎮", font=("Arial", 20, "bold"),
            fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            height=60, width=250, command=self.start_a_match
        )
        x_o_btn.pack(pady=(20, 10))

        # --- הכפתור החדש ---
        number_game_btn = ctk.CTkButton(
            frame, text="שחק נחש את המספר 🔢", font=("Arial", 20, "bold"),
            fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            height=60, width=250, command=lambda: self.send_json({"action": "match_number"})
        )
        number_game_btn.pack(pady=10)

        inv_btn = ctk.CTkButton(
            frame, text="המלאי שלי 🎒", font=("Arial", 18),
            fg_color=COLORS["DARK_PINK"], hover_color=COLORS["PINK_HOVER"],
            height=50, width=200, command=self.request_inventory
        )
        inv_btn.pack(pady=10)

        hummus_btn = ctk.CTkButton(
            frame, text="הכן חומוס", font=("Arial", 18),
            fg_color=COLORS["DARK_PINK"], hover_color=COLORS["PINK_HOVER"],
            height=50, width=200, command=self.make_hummus
        )
        hummus_btn.pack(pady=10)

        rank_btn = ctk.CTkButton(
            frame, text="טבלת שיאים עולמית", font=("Arial", 18),
            fg_color=COLORS["DARK_PINK"], hover_color=COLORS["PINK_HOVER"],
            height=50, width=200, command=self.get_world_rank
        )
        rank_btn.pack(pady=10)

        # כפתור מנהלים (יוסתר כברירת מחדל)
        self.admin_btn = ctk.CTkButton(
            frame, text="👑 פאנל מנהלים (פרס חינם)", font=("Arial", 18, "bold"),
            fg_color="gold", text_color="black", hover_color="#FFD700",
            height=50, width=200, command=self.give_free_hummus
        )
        # לא עושים לו pack עדיין!

        logout_btn = ctk.CTkButton(frame, text="התנתק", fg_color="gray",
                                   command=self.do_logout)  # שינינו את הפקודה ל-do_logout
        logout_btn.pack(side="bottom", pady=30)

    def create_inventory_frame(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["PINK_BG"])
        self.frames["inventory"] = frame

        # self.logo_label.pack(pady=10)

        title = ctk.CTkLabel(frame, text="🎒 המלאי שלי 🎒", font=("Arial", 28, "bold"), text_color=COLORS["DARK_PINK"])
        title.pack()

        self.inventory_text = ctk.CTkTextbox(
            frame, width=300, height=300, font=("Arial", 16), fg_color="white",
            text_color=COLORS["DARK_PINK"], border_width=2, border_color=COLORS["PINK_MAIN"]
        )
        self.inventory_text.pack(pady=10)

        inventory_back_btn = ctk.CTkButton(
            frame, text="חוזר משחק / המתנה", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            command=self.start_a_match
        )
        inventory_back_btn.pack(pady=10)

        menu_back_btn = ctk.CTkButton(
            frame, text="הבית לעמוד בחזרה", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            command=lambda: self.show_frame("main_menu")
        )
        menu_back_btn.pack(pady=10)

    def create_rank_frame(self):
        frame = ctk.CTkFrame(self, fg_color=COLORS["PINK_BG"])
        self.frames["rank"] = frame

        self.status_label = ctk.CTkLabel(frame, text="דירוג שחקנים עולמי", font=("Arial", 20, "bold"),
                                         text_color=COLORS["DARK_PINK"])
        self.status_label.pack(pady=(10, 0))

        self.switch = ctk.CTkSwitch(
            frame, text="החלף לצפייה בדירוג שלך", variable=self.mode_var, onvalue="self_rank", offvalue="world_rank",
            command=self.toggle_rank_mode, progress_color=COLORS["PINK_MAIN"]
        )
        self.switch.pack(pady=10)

        menu_back_btn = ctk.CTkButton(
            frame, text="הבית לעמוד בחזרה", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
            command=lambda: self.show_frame("main_menu")
        )
        menu_back_btn.pack(pady=10)

    # ==================== פעולות ושליחת נתונים (המקורי שלך) ====================

    def toggle_auth_mode(self):
        if self.mode_var.get() == "register":
            self.q1_entry.pack(pady=10, before=self.login_btn)
            self.q2_entry.pack(pady=10, before=self.login_btn)
            self.generate_btn.pack(pady=(10,), before=self.q1_entry)
            self.login_btn.configure(text="הרשמה")
            self.switch.configure(text="החלף להתחברות")
        else:
            self.generate_btn.pack_forget()
            self.q1_entry.pack_forget()
            self.q2_entry.pack_forget()
            self.login_btn.configure(text="התחברות")
            self.switch.configure(text="החלף להרשמה")

    def toggle_rank_mode(self):
        if self.mode_var.get() == "self_rank":
            self.switch.configure(text="החלף לצפייה בדירוג העולמי")
            self.status_label.configure(text="דירוג שחקנים ביחד אליך")
            self.get_self_rank()
        else:
            self.switch.configure(text="החלף לצפייה בדירוג שלך")
            self.status_label.configure(text="דירוג שחקנים עולמי")
            self.get_world_rank()
        self.update_rank()

    def toggle_password_visibility(self):
        if self.show_password_var.get():
            self.password_entry.configure(show="")
        else:
            self.password_entry.configure(show="*")

    def submit_verification(self):
        # שליחת התשובות לשרת
        data = {
            "action": "verification",
            "username": self.username_entry.get(),
            "question1": self.ans1_entry.get(),
            "question2": self.ans2_entry.get()
        }
        self.send_json(data)

    def submit_reset(self):
        data = {
            "action": "reset",
            "username": self.username_entry.get(),
            "new password": self.new_pass_entry.get(),
            "confirm password": self.confirm_pass_entry.get()
        }
        self.send_json(data)

    def get_world_rank(self):
        self.send_json({"action": "world_rank"})

    def get_self_rank(self):
        self.send_json({"action": "personal_rank"})

    def update_rank(self):
        frame = self.frames["rank"]

        for widget in frame.winfo_children():
            if isinstance(widget, ctk.CTkFrame):
                widget.destroy()

        board_frame = ctk.CTkFrame(frame, fg_color=COLORS["DARK_PINK"])
        board_frame.pack(pady=10)

        headers = ["דירוג", "שם משתמש", "כמות חומוסים"]
        for col, text in enumerate(headers):
            box = ctk.CTkTextbox(board_frame, width=50 if col == 0 else (200 if col == 1 else 100), height=40,
                                 fg_color=COLORS["PINK_BG"], text_color=COLORS["DARK_PINK"], font=("Arial", 15, "bold"))
            box.tag_config("center", justify="center")
            box.insert("0.0", text)
            box.grid(row=0, column=col, padx=5, pady=5)

        if self.rank:
            for i in range(len(self.rank)):
                username = self.rank[i].get("username")
                box_color = "white" if username == self.username else COLORS["PINK_BG"]
                rank = self.rank[i].get("rank")
                hummusim = self.rank[i].get("amount")

                row_data = [(rank, 50), (username, 200), (hummusim, 100)]
                for col, (data, width) in enumerate(row_data):
                    box = ctk.CTkTextbox(board_frame, width=width, height=40, fg_color=box_color,
                                         text_color=COLORS["DARK_PINK"], font=("Arial", 15, "bold"))
                    box.tag_config("center", justify="center")
                    box.insert("0.0", str(data))
                    box.grid(row=i + 1, column=col, padx=5, pady=5)

    def start_a_match(self):
        self.send_json({"action": "match", "username": self.username})

    def generate_password(self):
        self.send_json({"action": "password"})

    def do_login(self):
        self.username = self.username_entry.get()
        password = self.password_entry.get()

        if not self.username or not password:
            self.error_label.configure(text="נא למלא את כל השדות")
            return

        if self.mode_var.get() == "register":
            q1 = self.q1_entry.get()
            q2 = self.q2_entry.get()
            msg = {"action": "register", "username": self.username, "password": password, "question1": q1,
                   "question2": q2}
        else:
            msg = {"action": "login", "username": self.username, "password": password}

        self.send_json(msg)

    def request_inventory(self):
        self.send_json({"action": "inventory", "username": self.username})

    def request_image(self):
        # שליחת בקשה לשרת לקבלת התמונה
        request = {"action": "get_image_file"}
        self.send_json(request)

    def make_hummus(self):
        self.send_json({"action": "hummus", "username": self.username})

    def give_free_hummus(self):
        """פעולה ייחודית שרק מנהל יכול לעשות"""
        self.send_json({"action": "give_free_hummus", "target_user": self.username})

    def do_logout(self):
        """איפוס הנתונים ביציאה ועדכון השרת"""
        # 1. שולחים לשרת הודעה כדי שישחרר את שם המשתמש שלנו מהרשימה
        if self.token:
            self.send_json({"action": "logout"})

        # 2. מאפסים את המשתנים המקומיים
        self.token = None
        self.role = None
        self.username = None

        # 3. מסתירים את כפתור המנהל (למקרה שהוא פתוח)
        if hasattr(self, 'admin_btn') and self.admin_btn:
            self.admin_btn.pack_forget()

        # מחיקת הטקסט מתיבות הקלט במסך ההתחברות
        if self.username_entry:
            self.username_entry.delete(0, "end")
        if self.password_entry:
            self.password_entry.delete(0, "end")
        if self.error_label:
            self.error_label.configure(text="")

        # 4. מעבירים למסך ההתחברות
        self.show_frame("auth")

    # ==================== קבלת נתונים מהשרת ====================

    def listen_to_server(self):
        buffer = ""
        decoder = JSONDecoder()

        while True:
            try:
                data = self.sock.recv(16384).decode()
                print(data)
                print(f"Received {len(data)} bytes...")
                if not data:
                    break

                buffer += data

                # מנגנון חכם לחילוץ מספר הודעות JSON שמגיעות מחוברות
                while buffer:
                    buffer = buffer.lstrip()
                    try:
                        obj, index = decoder.raw_decode(buffer)
                        # שימוש ב-after כדי לעדכן את הממשק (חובה ב-Tkinter כשעובדים עם Thread)
                        self.after(0, self.handle_server_message, obj)
                        buffer = buffer[index:]
                    except json.JSONDecodeError:
                        # אין JSON שלם בבאפר, מחכים לעוד מידע מהסוקט
                        break
            except Exception as e:
                print(f"Disconnected from server: {e}")
                break

    def handle_server_message(self, data):
        status = data.get("status")

        # --- ניתוב הודעות ספציפיות למשחק הפעיל ---
        if (status == "update" or status == "number_update") and self.active_game_frame:
            self.active_game_frame.handle_update(data)
            return

        if status == "assign_symbol":
            # הריסת המשחק הקודם אם קיים ויצירת אחד חדש (איקס עיגול)
            if self.active_game_frame:
                self.active_game_frame.destroy()

            self.active_game_frame = TicTacToeGame(
                self,
                send_json_callback=self.send_json,
                show_frame_callback=self.show_frame
            )
            self.active_game_frame.start_game(
                game_id=data["game_id"],
                symbol=data["symbol"],
                username=self.username
            )
            self.show_frame("game")
            return

        if status == "start_number_game":
            if self.active_game_frame:
                self.active_game_frame.destroy()

            # יצירת המופע החדש של המשחק והכנסתו למערכת
            self.active_game_frame = NumberGuessGame(self, send_json_callback=self.send_json,
                                                     show_frame_callback=self.show_frame)
            # מעבירים is_my_turn במקום symbol
            self.active_game_frame.start_game(game_id=data["game_id"], is_my_turn=data["turn"], username=self.username)
            self.show_frame("game")
            return

        # --- טיפול בשאר ההודעות של המערכת הכללית ---
        if status == "ok" and "message" in data:
            message = data["message"]
            if message == "Login successful":
                # שומרים את הטוקן והתפקיד שקיבלנו מהשרת!
                self.token = data.get("token")
                self.role = data.get("role")
                self.error_label.configure(text=data["message"], text_color="green")
                self.show_frame("main_menu")
                # מציגים את כפתור המנהל רק אם התפקיד מתאים
                if self.role == "admin":
                    self.admin_btn.pack(pady=10, before=self.frames["main_menu"].winfo_children()[-1])
                # else:
                    # self.admin_btn.pack_forget()
            elif message == "User registered":
                # הרשמה הצליחה - נחזיר אותו למסך התחברות כדי שיתחבר ויקבל טוקן
                self.error_label.configure(text="הרשמה בוצעה בהצלחה! אנא התחבר.", text_color="green")
                self.mode_var.set("login")
                self.toggle_auth_mode()
                self.show_frame("auth")
            elif message == "Verification successful":
                self.error_label.configure(text=data["message"], text_color="green")
                popup = ctk.CTkToplevel(self)
                popup.title("אימות מוצלח")
                popup.geometry("300x250")
                popup.configure(fg_color=COLORS["PINK_BG"])
                ctk.CTkLabel(popup, text="האימות הוצלח. בחר סיסמה חדשה!", font=("Arial", 14, "bold"),
                             text_color=COLORS["DARK_PINK"]).pack(pady=20)
                ctk.CTkButton(popup, text="סגור", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
                              command=popup.destroy).pack()
                self.show_frame("reset_password")
            elif message == "Password reset successful":
                self.error_label.configure(text=data["message"], text_color="green")
                self.show_frame("main_menu")
                popup = ctk.CTkToplevel(self)
                popup.title("סיסמה אופסה")
                popup.geometry("300x250")
                popup.configure(fg_color=COLORS["PINK_BG"])
                ctk.CTkLabel(popup, text="סיסמה אופסה בהצלחה!", font=("Arial", 14, "bold"),
                             text_color=COLORS["DARK_PINK"]).pack(pady=20)
                ctk.CTkButton(popup, text="סגור", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
                              command=popup.destroy).pack()

        elif status == "error":
            if "amount" in data:
                amount = data["amount"]
                dialog = ctk.CTkToplevel(self)
                dialog.title("חומוס לא הוכן בהצלחה")
                dialog.geometry("300x250")
                dialog.configure(fg_color=COLORS["PINK_BG"])
                ctk.CTkLabel(dialog, text="❌ אין לך מספיק מרכיבים להכנת החומוס ❌", font=("Arial", 20, "bold"),
                             text_color=COLORS["DARK_PINK"]).pack(pady=10)
                ctk.CTkLabel(dialog, text=f"מספר החומוסים שברשותך: {amount}", font=("Arial", 16)).pack(pady=10)
                ctk.CTkButton(dialog, text="סגור", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
                              command=dialog.destroy).pack()

            self.error_label.configure(text=data.get("message", "שגיאה לא ידועה"), text_color="red")
            self.error_label.pack()

        elif status == "password":
            password = data.get("password")
            self.password_entry.delete(0, "end")
            self.password_entry.insert(0, password)

        elif status == "security_questions":
            # הגעה ל-3 טעויות - מעבר למסך אימות
            self.error_label.configure(text=data["message"], text_color="red")
            popup = ctk.CTkToplevel(self)
            popup.title("שגיאה חוזרת בהתחברות")
            popup.geometry("300x250")
            popup.configure(fg_color=COLORS["PINK_BG"])
            ctk.CTkLabel(popup, text="הגעת למכסת השגיאות. ענה על שאלות האימות כדי לאפס סיסמה.", font=("Arial", 14, "bold"),
                         text_color=COLORS["DARK_PINK"]).pack(pady=20)
            ctk.CTkButton(popup, text="סגור", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
                          command=popup.destroy).pack()
            self.show_frame("verification_frame")

        elif status == "blocked":
            # טעות בשאלות האימות - חסימה לחצי שעה
            self.error_label.configure(text=data["message"], text_color="red")
            self.show_frame("auth")

        elif status == "rank":
            self.rank = data.get("rank")
            self.show_frame("rank")
            self.update_rank()

        elif status == "waiting":
            self.show_frame("waiting")

        elif status == "reward":
            item = data["item"]
            dialog = ctk.CTkToplevel(self)
            dialog.title("פרס!")
            dialog.geometry("300x250")
            dialog.configure(fg_color=COLORS["PINK_BG"])
            ctk.CTkLabel(dialog, text="🎁 קיבלת פרס! 🎁", font=("Arial", 20, "bold"),
                         text_color=COLORS["DARK_PINK"]).pack(pady=10)
            ctk.CTkLabel(dialog, text=f"נוסף למלאי שלך: {item}", font=("Arial", 16)).pack(pady=10)
            ctk.CTkButton(dialog, text="סגור", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
                          command=dialog.destroy).pack()

        elif status == "inventory":
            items = data.get("items", [])
            self.inventory_text.delete("1.0", "end")
            if not items:
                self.inventory_text.insert("end", "המלאי שלך ריק כרגע.\nשחק ונצח כדי להרוויח מצרכים לחומוס!")
            else:
                for item, amount in items:
                    self.inventory_text.insert("end", f"🍲 {item}: {amount} יחידות\n\n")
            self.show_frame("inventory")

        elif status == "hummus":
            amount = data["amount"]
            dialog = ctk.CTkToplevel(self)
            dialog.title("חומוס הוכן בהצלחה")
            dialog.geometry("300x250")
            dialog.configure(fg_color=COLORS["PINK_BG"])
            ctk.CTkLabel(dialog, text="🪄 ברכות! הכנת חומוס! 🪄", font=("Arial", 20, "bold"),
                         text_color=COLORS["DARK_PINK"]).pack(pady=10)
            ctk.CTkLabel(dialog, text=f"מספר החומוסים שברשותך: {amount}", font=("Arial", 16)).pack(pady=10)
            ctk.CTkButton(dialog, text="לחומוס מתכון הורד", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"], command=self.request_image).pack(pady=10)
            ctk.CTkButton(dialog, text="סגור", fg_color=COLORS["PINK_MAIN"], hover_color=COLORS["PINK_HOVER"],
                          command=dialog.destroy).pack()

        elif status == "save_recipe_file":
            encoded_data = data.get("image_data")
            default_name = data.get("filename", "recipe.png")
            ext = data.get("extension", ".png")

            # 1. פתיחת חלונית "שמור בשם" מותאמת ל-PNG
            file_path = filedialog.asksaveasfilename(
                defaultextension=ext,
                initialfile=default_name,
                # הגדרת סוגי קבצים כך שהמשתמש יראה רק PNG
                filetypes=[("Image files", f"*{ext}"), ("All files", "*.*")],
                title="בחר מיקום לשמירת המתכון"
            )

            if file_path:
                try:
                    # 2. הפיכה מ-Base64 חזרה לביטים של תמונה
                    image_bytes = base64.b64decode(encoded_data)

                    # 3. כתיבה לקובץ בפורמט בינארי (wb)
                    with open(file_path, "wb") as f:
                        f.write(image_bytes)

                    messagebox.showinfo("הצלחה", "המתכון נשמר במחשב שלך!")
                except Exception as e:
                    messagebox.showerror("שגיאה", f"השמירה נכשלה: {e}")


if __name__ == "__main__":
    app = MainClient()
    app.mainloop()