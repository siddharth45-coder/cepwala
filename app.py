import os
import re
import uuid
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "local-text-pagination-secret-key-change-if-needed"

# Configuration
CONTENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content.txt")
SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sessions")
WORDS_PER_PAGE = 1200

# Ensure session storage directory exists
os.makedirs(SESSION_DIR, exist_ok=True)

# Cache dictionary: { file_path: (mtime, words_list) }
_cache_store = {}


def load_and_clean_words(file_path):
    """
    Reads a text file with UTF-8 encoding, cleans whitespace with regex,
    and returns a list of words. Caches results using the file's last modified time.
    """
    global _cache_store

    if not os.path.exists(file_path):
        return [], "missing"

    try:
        current_mtime = os.path.getmtime(file_path)
    except OSError:
        current_mtime = None

    # Check cache
    if file_path in _cache_store:
        cached_mtime, cached_words = _cache_store[file_path]
        if current_mtime is not None and cached_mtime == current_mtime and cached_words:
            return cached_words, "ok"

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_content = f.read()
    except Exception as e:
        return [], f"error: {str(e)}"

    # Text cleaning:
    # 1. Convert multiple spaces, tabs, and newlines into single spaces
    # 2. Strip leading and trailing whitespace
    # 3. Preserve all words, word order, and normal punctuation
    cleaned_content = re.sub(r"\s+", " ", raw_content).strip()

    if not cleaned_content:
        words = []
        status = "empty"
    else:
        words = cleaned_content.split(" ")
        status = "ok"

    _cache_store[file_path] = (current_mtime, words)
    return words, status


def get_active_content_info():
    """
    Determines whether to load session-pasted text or the default content.txt.
    """
    sid = session.get("sid")
    if sid:
        session_file = os.path.join(SESSION_DIR, f"{sid}.txt")
        if os.path.exists(session_file):
            return session_file, "pasted"
    return CONTENT_FILE, "file"


@app.route("/")
def index():
    active_file, source_type = get_active_content_info()
    words, status = load_and_clean_words(active_file)
    total_words = len(words)

    if total_words == 0:
        total_pages = 1
        current_page = 1
        page_text = ""
        start_word_num = 0
        end_word_num = 0
    else:
        total_pages = (total_words + WORDS_PER_PAGE - 1) // WORDS_PER_PAGE

        # Safely parse page query parameter
        raw_page = request.args.get("page", "1")
        try:
            current_page = int(raw_page)
        except (ValueError, TypeError):
            current_page = 1

        # Bound page number within valid range
        if current_page < 1:
            current_page = 1
        elif current_page > total_pages:
            current_page = total_pages

        # Calculate exact 1200-word slice for the requested page
        start_idx = (current_page - 1) * WORDS_PER_PAGE
        end_idx = min(start_idx + WORDS_PER_PAGE, total_words)

        page_words = words[start_idx:end_idx]
        page_text = " ".join(page_words)

        start_word_num = start_idx + 1
        end_word_num = end_idx

    has_prev = current_page > 1
    has_next = current_page < total_pages
    prev_page = current_page - 1 if has_prev else None
    next_page = current_page + 1 if has_next else None

    return render_template(
        "index.html",
        page_text=page_text,
        current_page=current_page,
        total_pages=total_pages,
        total_words=total_words,
        start_word_num=start_word_num,
        end_word_num=end_word_num,
        has_prev=has_prev,
        has_next=has_next,
        prev_page=prev_page,
        next_page=next_page,
        status=status,
        source_type=source_type,
    )


@app.route("/paste", methods=["POST"])
def paste_content():
    """
    Accepts full content pasted directly from the browser,
    saves it to the user's session store, and redirects to page 1.
    """
    raw_content = request.form.get("content", "")

    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())

    session_file = os.path.join(SESSION_DIR, f"{session['sid']}.txt")
    with open(session_file, "w", encoding="utf-8") as f:
        f.write(raw_content)

    # Invalidate cache for this session file so it re-cleans immediately
    _cache_store.pop(session_file, None)

    return redirect(url_for("index", page=1))


@app.route("/reset", methods=["GET", "POST"])
def reset_to_file():
    """
    Clears pasted content for this session and reverts back to reading content.txt.
    """
    sid = session.pop("sid", None)
    if sid:
        session_file = os.path.join(SESSION_DIR, f"{sid}.txt")
        _cache_store.pop(session_file, None)
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
            except OSError:
                pass

    return redirect(url_for("index", page=1))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
