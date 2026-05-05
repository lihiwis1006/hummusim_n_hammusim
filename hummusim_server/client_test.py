import socket
import json

HOST = "127.0.0.1"
PORT = 5000


def send_json(sock, message):
    sock.send(json.dumps(message).encode())


def print_board(board):
    symbols = [c if c != " " else " " for c in board]
    print(f"\n {symbols[0]} | {symbols[1]} | {symbols[2]}")
    print("--+---+--")
    print(f" {symbols[3]} | {symbols[4]} | {symbols[5]}")
    print("--+---+--")
    print(f" {symbols[6]} | {symbols[7]} | {symbols[8]}\n")


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    while True:
        choice = input("הקלד 'r' להרשמה או 'l' להתחברות: ").lower()
        if choice in ["r", "l"]:
            break

    username = input("Username: ")
    password = input("Password: ")

    if choice == "r":
        question1 = input("שאלה 1: ")
        question2 = input("שאלה 2: ")

        send_json(sock, {
            "action": "register",
            "username": username,
            "password": password,
            "question1": question1,
            "question2": question2
        })

    else:
        send_json(sock, {
            "action": "login",
            "username": username,
            "password": password
        })

    response = json.loads(sock.recv(4096).decode())
    print("SERVER:", response)

    if response.get("status") != "ok":
        print("התחברות נכשלה")
        return

    print("התחברת בהצלחה! מחכה ליריב...")

    symbol = None
    game_id = None
    board = [" "] * 9
    game_over = False

    while True:
        data = json.loads(sock.recv(4096).decode())

        status = data.get("status")

        # קבלת סימן
        if status == "assign_symbol":
            symbol = data["symbol"]
            game_id = data["game_id"]
            print(f"קיבלת סימן {symbol}, game_id={game_id}")

        # עדכון לוח
        elif status == "update":
            board = data["board"]
            print_board(board)

            winner = data.get("winner")
            your_turn = data.get("turn")

            if winner and not game_over:
                game_over = True

                if winner == "tie":
                    print("תיקו!")
                elif winner == symbol:
                    print("ניצחת! 🎉")
                else:
                    print("הפסדת 😢")

            if your_turn and not game_over:
                while True:
                    try:
                        pos = int(input("בחר מיקום (0-8): "))
                        if board[pos] == " ":
                            break
                        else:
                            print("המקום תפוס")
                    except:
                        print("מספר לא חוקי")

                send_json(sock, {
                    "action": "move",
                    "game_id": game_id,
                    "position": pos
                })

        # קבלת פרס
        elif status == "reward":
            print("🎁 קיבלת מרכיב:", data["item"])

            # מבקשים inventory
            send_json(sock, {"action": "inventory"})

        # קבלת inventory
        elif status == "inventory":
            print("\n🧺 המלאי שלך:")
            for item, amount in data["items"]:
                print(f"{item} x{amount}")

            print("\nהמשחק הסתיים.")
            break


if __name__ == "__main__":
    main()