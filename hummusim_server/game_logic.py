from database import get_db


def check_winner(board):
    """בודק אם יש מנצח בלוח האיקס-עיגול"""
    win_conditions = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],  # שורות
        [0, 3, 6], [1, 4, 7], [2, 5, 8],  # עמודות
        [0, 4, 8], [2, 4, 6]  # אלכסונים
    ]
    for a, b, c in win_conditions:
        if board[a] == board[b] == board[c] and board[a] in ["X", "O"]:
            return board[a]
    if all(pos in ["X", "O"] for pos in board):
        return "tie"
    return None


def handle_making_hummus(data):
    """בודק אם אפשר להכין חומוס ומעדכן את מסד הנתונים"""
    username = data.get("username")
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT MIN(amount), COUNT(*) FROM inventory WHERE username = ?", (username,))
    row = cur.fetchone()
    min_amount = row[0] if row[0] is not None else 0
    total_items = row[1]

    if total_items == 7 and min_amount > 0:
        cur.execute("""
            UPDATE inventory SET amount = amount - 1 
            WHERE username = ? AND amount > 0
        """, (username,))

        cur.execute("""
            INSERT INTO hummusim (username, amount) VALUES (?, 1)
            ON CONFLICT(username) DO UPDATE SET amount = amount + 1
            RETURNING amount
        """, (username,))

        new_amount = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return {"status": "hummus", "amount": str(new_amount)}

    cur.execute("SELECT amount FROM hummusim WHERE username = ?", (username,))
    h_row = cur.fetchone()
    h_amount = h_row[0] if h_row else 0
    conn.close()

    return {
        "status": "error",
        "amount": str(h_amount),
        "message": "User does not have all the ingredients"
    }

def make_test_hummusim():
    """מכין חומוסים לשחקני הבדיקה כדי שנוכל לבדוק שטבלת הדירוג עובדת נכון"""
    for i in range(11,15):
        user = "lihi" + str(i)
        for j in range(i):
            handle_making_hummus({"username": user})

# make_test_hummusim()
# print("made hummusim")