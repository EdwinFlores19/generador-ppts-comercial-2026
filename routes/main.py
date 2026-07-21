import os
from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/chatbot')
def chatbot_page():
    provider = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
    if provider == "groq":
        ai_label = f"Groq · {os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')}"
    else:
        ai_label = f"Gemini · {os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')}"
    return render_template('chatbot.html', ai_label=ai_label)
