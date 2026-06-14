import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "games.db"
RAWG_BASE_URL = "https://api.rawg.io/api"
RAWG_API_KEY = os.environ.get("RAWG_API_KEY", "febff0ca52b14a1ea3cd0f99052172f7")
VALID_STATUSES = ("playing", "wishlist", "completed")
STATUS_LABELS = {
    "playing": "Playing",
    "wishlist": "Wishlist",
    "completed": "Completed",
}


app = Flask(__name__)
# Základní nastavení aplikace a bezpečnostního klíče.
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-secret-key-before-production"
)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


class User(UserMixin):
    def __init__(self, id, username, email, password_hash):
        self.id = str(id)
        self.username = username
        self.email = email
        self.password_hash = password_hash

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(row["id"], row["username"], row["email"], row["password_hash"])


def get_db():
    # Připojení k SQLite databázi pro uživatele a jejich hry.
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DATABASE) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('playing', 'wishlist', 'completed')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                UNIQUE (user_id, game_id)
            );

            CREATE TABLE IF NOT EXISTS favorite_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                UNIQUE (user_id, game_id)
            );
            """
        )


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    row = db.execute(
        "SELECT id, username, email, password_hash FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return User.from_row(row)


def rawg_get(path, params=None):
    params = dict(params or {})
    params["key"] = RAWG_API_KEY

    try:
        response = requests.get(
            f"{RAWG_BASE_URL}{path}", params=params, timeout=12
        )
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException:
        return None, "Game data could not be loaded right now. Please try again later."


def fetch_genres():
    data, error = rawg_get("/genres", {"page_size": 50})
    if error:
        return [], error
    return data.get("results", []), None


def fetch_games(search_query=None, genre_id=None, page=1):
    params = {"page_size": 18, "page": page}
    if search_query:
        params.update({"search": search_query, "ordering": "-rating"})
    elif genre_id:
        params.update({"genres": genre_id, "ordering": "-rating"})
    else:
        params.update({"ordering": "-added"})

    data, error = rawg_get("/games", params)
    if error:
        return [], error
    return data.get("results", []), None


def fetch_game_details(game_id):
    data, error = rawg_get(f"/games/{game_id}")
    return data, error


def get_current_status(game_id):
    if not current_user.is_authenticated:
        return None
    row = get_db().execute(
        "SELECT status FROM user_games WHERE user_id = ? AND game_id = ?",
        (current_user.id, game_id),
    ).fetchone()
    return row["status"] if row else None


def get_is_favorited(game_id):
    if not current_user.is_authenticated:
        return False
    row = get_db().execute(
        "SELECT id FROM favorite_games WHERE user_id = ? AND game_id = ?",
        (current_user.id, game_id),
    ).fetchone()
    return row is not None


def is_safe_next(target):
    if not target:
        return False
    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == "" and target.startswith("/")


@app.context_processor
def inject_status_labels():
    return {"STATUS_LABELS": STATUS_LABELS}


@app.route("/")
def home():
    # Hlavní stránka s vyhledáváním a filtrováním her.
    query = request.args.get("q", "").strip()
    genre_id = request.args.get("genre", "").strip()
    genres, _ = fetch_genres()
    games, error = fetch_games(search_query=query, genre_id=genre_id or None, page=1)
    
    if query:
        page_title = "Search Results"
    elif genre_id:
        genre_name = next((g["name"] for g in genres if str(g["id"]) == genre_id), "Games")
        page_title = f"{genre_name}"
    else:
        page_title = "Popular Games"
    
    return render_template(
        "index.html",
        games=games,
        query=query,
        genre=genre_id,
        genres=genres,
        error=error,
        page_title=page_title,
    )


@app.route("/api/games/more", methods=["GET"])
def load_more_games():
    query = request.args.get("q", "").strip()
    genre_id = request.args.get("genre", "").strip()
    page = request.args.get("page", 1, type=int)
    games, error = fetch_games(search_query=query, genre_id=genre_id or None, page=page)
    
    if error:
        return jsonify({"ok": False, "error": error})
    
    return jsonify({
        "ok": True,
        "games": games,
    })


@app.route("/game/<int:id>")
def game_detail(id):
    game, error = fetch_game_details(id)
    if error:
        return render_template("game.html", game=None, error=error, current_status=None)
    if not game:
        abort(404)
    return render_template(
        "game.html",
        game=game,
        error=None,
        current_status=get_current_status(id),
        is_favorited=get_is_favorited(id),
    )


@app.route("/library")
@login_required
def library():
    # Zobrazení her z uživatelovy osobní knihovny.
    rows = get_db().execute(
        """
        SELECT game_id, status
        FROM user_games
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (current_user.id,),
    ).fetchall()

    library_games = {status: [] for status in VALID_STATUSES}
    errors = []

    for row in rows:
        game, error = fetch_game_details(row["game_id"])
        if error:
            errors.append(error)
            continue
        if game:
            library_games[row["status"]].append(game)

    error = errors[0] if errors else None
    return render_template("library.html", library_games=library_games, error=error)


@app.route("/favorites")
@login_required
def favorites():
    # Seznam oblíbených her pro přihlášeného uživatele.
    rows = get_db().execute(
        """
        SELECT game_id
        FROM favorite_games
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (current_user.id,),
    ).fetchall()

    favorite_games = []
    errors = []

    for row in rows:
        game, error = fetch_game_details(row["game_id"])
        if error:
            errors.append(error)
            continue
        if game:
            favorite_games.append(game)

    error = errors[0] if errors else None
    return render_template("favorites.html", favorite_games=favorite_games, error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("library"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()

        if existing:
            flash("Username or email is already in use.", "error")
            return render_template("register.html")

        db.execute(
            """
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (username, email, generate_password_hash(password)),
        )
        db.commit()
        flash("Account created successfully. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("library"))

    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user_row = get_db().execute(
            """
            SELECT id, username, email, password_hash
            FROM users
            WHERE username = ? OR email = ?
            """,
            (identity, identity.lower()),
        ).fetchone()
        user = User.from_row(user_row)

        if user is None or not check_password_hash(user.password_hash, password):
            flash("Invalid username, email, or password.", "error")
            return render_template("login.html")

        login_user(user, remember=remember)
        next_url = request.args.get("next")
        return redirect(next_url if is_safe_next(next_url) else url_for("library"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/update_status/<int:game_id>/<status>", methods=["GET", "POST"])
@login_required
def update_status(game_id, status):
    status = status.lower()
    if status not in VALID_STATUSES:
        abort(404)

    db = get_db()
    db.execute(
        """
        INSERT INTO user_games (user_id, game_id, status)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, game_id)
        DO UPDATE SET status = excluded.status
        """,
        (current_user.id, game_id, status),
    )
    db.commit()

    message = f"Game added to {STATUS_LABELS[status]}."
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if wants_json:
        return jsonify(
            {
                "ok": True,
                "status": status,
                "label": STATUS_LABELS[status],
                "message": message,
            }
        )

    flash(message, "success")
    next_url = request.form.get("next") or request.args.get("next") or request.referrer
    return redirect(next_url if is_safe_next(next_url) else url_for("game_detail", id=game_id))


@app.route("/remove_game/<int:id>", methods=["POST"])
@login_required
def remove_game(id):
    db = get_db()
    db.execute(
        "DELETE FROM user_games WHERE user_id = ? AND game_id = ?",
        (current_user.id, id),
    )
    db.commit()

    message = "Game removed from your library."
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if wants_json:
        return jsonify(
            {
                "ok": True,
                "message": message,
            }
        )

    flash(message, "success")
    next_url = request.form.get("next") or request.args.get("next") or request.referrer
    return redirect(next_url if is_safe_next(next_url) else url_for("library"))


@app.route("/toggle_favorite/<int:game_id>", methods=["POST"])
@login_required
def toggle_favorite(game_id):
    db = get_db()

    existing = db.execute(
        "SELECT id FROM favorite_games WHERE user_id = ? AND game_id = ?",
        (current_user.id, game_id),
    ).fetchone()

    if existing:
        db.execute(
            "DELETE FROM favorite_games WHERE user_id = ? AND game_id = ?",
            (current_user.id, game_id),
        )
        is_favorited = False
        message = "Removed from favorites."
    else:
        db.execute(
            """
            INSERT INTO favorite_games (user_id, game_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, game_id)
            DO NOTHING
            """,
            (current_user.id, game_id),
        )
        is_favorited = True
        message = "Added to favorites."

    db.commit()
    label = "Remove from favorites" if is_favorited else "Add to favorites"

    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if wants_json:
        return jsonify(
            {
                "ok": True,
                "message": message,
                "is_favorited": is_favorited,
                "label": label,
            }
        )

    flash(message, "success")
    next_url = request.form.get("next") or request.args.get("next") or request.referrer
    return redirect(next_url if is_safe_next(next_url) else url_for("game_detail", id=game_id))


init_db()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
