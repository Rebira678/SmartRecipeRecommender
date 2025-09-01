from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_login import (
    LoginManager, UserMixin, login_user,
    logout_user, login_required, current_user
)
import sqlite3, hashlib, requests, random, os, json
from urllib.parse import quote_plus  # ✅ added for safe image query encoding

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_KEY_CHANGE_ME"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

DB_PATH = "db.sqlite"
# Put your real keys here (optional). If left blank, app uses free fallbacks.
SPOONACULAR_API_KEY = ""            # e.g. "your_spoonacular_key"
UNSPLASH_ACCESS_KEY = ""            # e.g. "your_unsplash_key"

# ---------------- Database Setup ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS pantry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        ingredient TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        link TEXT,
        image TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# ---------------- User Class ----------------
class User(UserMixin):
    def __init__(self, id_, username):
        self.id = id_
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return User(row[0], row[1])
    return None

# ---------------- Routes ----------------
@app.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    return render_template("index.html", username=current_user.username)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = hashlib.sha256(request.form["password"].encode()).hexdigest()
        if not username:
            return "Username cannot be empty", 400
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO users(username,password) VALUES(?,?)", (username, password))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except Exception:
            return "⚠️ Username already exists!", 400
    return render_template("register.html")
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password_input = request.form["password"]

        if not username or not password_input:
            error = "Please enter both username and password"
        else:
            password_hash = hashlib.sha256(password_input.encode()).hexdigest()
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id, password FROM users WHERE username=?", (username,))
            row = c.fetchone()
            conn.close()

            if row:
                user_id, stored_hash = row
                if stored_hash == password_hash:
                    login_user(User(user_id, username))
                    return redirect(url_for("index"))
                else:
                    error = "Wrong password. Please try again."
            else:
                error = "Username not found. Please register first."

    return render_template("login.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

#  ---------------------------------
# ---------------- Pantry ----------------
# ---------------- Pantry ----------------
@app.route("/pantry", methods=["GET","POST"])
@login_required
def pantry():
    if request.method == "POST":
        ingredient = request.form.get("ingredient","").strip()
        if ingredient:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO pantry(user_id,ingredient) VALUES(?,?)", (int(current_user.id), ingredient))
            conn.commit()
            conn.close()
            # After adding, redirect to pantry GET so the list is refreshed
            return redirect(url_for("pantry"))

    # Return (id, ingredient) pairs so frontend can use IDs for deletion
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, ingredient FROM pantry WHERE user_id=?", (int(current_user.id),))
    rows = c.fetchall()
    conn.close()
    # rows is list of tuples (id, ingredient)
    pantry_items = [{"id": r[0], "ingredient": r[1]} for r in rows]
    return render_template("pantry.html", pantry=pantry_items)

@app.route("/pantry/delete/<int:item_id>", methods=["POST"])
@login_required
def pantry_delete(item_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # make sure the item belongs to current user before deleting
        c.execute("SELECT user_id FROM pantry WHERE id=?", (item_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"error":"Item not found"}), 404
        owner_id = row[0]
        if int(owner_id) != int(current_user.id):
            conn.close()
            return jsonify({"error":"Forbidden"}), 403
        c.execute("DELETE FROM pantry WHERE id=?", (item_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        print("Delete pantry error:", e)
        return jsonify({"error": str(e)}), 500

# ---------------- Generate Recipes ----------------
@app.route("/generate", methods=["POST"])
@login_required
def generate():
    data = request.get_json()
    pantry_items = data.get("pantry", "")
    diet = data.get("diet", "")

    try:
        # Normalize pantry items
        if isinstance(pantry_items, list):
            raw_query = ",".join([str(x) for x in pantry_items if x])
        else:
            raw_query = str(pantry_items or "")
        cleaned = ",".join([part.strip() for part in raw_query.split(",") if part and part.strip()])
        if not cleaned:
            cleaned = "food"
        q = quote_plus(cleaned)

        # Helper for images
        def img(tag):
            return f"https://source.unsplash.com/800x600/?{q},{quote_plus(tag)}"

        # Create recipes with unique instructions
        sample = [
            {
                "title": f"Creative Dish with {cleaned}",
                "image": img("food"),
                "link": "#",
                "instructions": f"Use {cleaned} in a creative way. Mix, cook, and enjoy a delicious {cleaned} dish!"
            },
            {
                "title": f"Fusion {cleaned} Curry",
                "image": img("curry"),
                "link": "#",
                "instructions": f"Cook {cleaned} with spices and herbs to make a flavorful curry."
            },
            {
                "title": f"Healthy {cleaned} Salad",
                "image": img("salad"),
                "link": "#",
                "instructions": f"Combine {cleaned} with fresh veggies and dressing for a healthy salad."
            }
        ]
        return jsonify(sample)
    except Exception as e:
        return jsonify({"error": str(e)})

# ---------------- TTS Audio ----------------
@app.route("/tts", methods=["POST"])
@login_required
def tts():
    data = request.get_json() or {}
    text = data.get("text","")
    return jsonify({"text": text})

# ---------------- Food News ----------------
@app.route("/news")
@login_required
def news():
    headlines = [
        "Mediterranean diet proven to boost focus.",
        "Dark chocolate linked to heart health.",
        "Green tea trend skyrockets worldwide.",
        "Lab-grown meat gains regulatory momentum.",
        "AI predicts food waste can be cut by 40%."
    ]
    return jsonify({"headlines": random.sample(headlines, 3)})

# ---------------- Local Background Images ----------------
@app.route("/background")
@login_required
def background():
    """
    Serve random local images from static/backgrounds/.
    Example images: home.jpg, login.jpg, register.jpg...
    """
    try:
        folder = os.path.join(app.static_folder, "backgrounds")
        files = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if not files:
            return jsonify({"url": url_for("static", filename="backgrounds/default.jpg")})
        chosen = random.choice(files)
        return jsonify({"url": url_for("static", filename=f"backgrounds/{chosen}")})
    except Exception as e:
        print("Background error:", e)
        return jsonify({"url": "https://source.unsplash.com/1600x900/?food,meal,cooking"})

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response

# ---------------- Run App ----------------
if __name__ == "__main__":
    app.run(debug=True)
