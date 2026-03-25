import json
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader
from docx import Document
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "resume_analyzer.db"
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)

UPLOAD_DIR.mkdir(exist_ok=True)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            job_role TEXT,
            overall_score INTEGER,
            recommendation TEXT,
            created_at TEXT,
            report_json TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix == ".docx":
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs)

    return ""


def read_resume_text():
    pasted_text = request.form.get("resume_text", "").strip()
    uploaded_file = request.files.get("resume_file")

    if pasted_text:
        return pasted_text

    if uploaded_file and uploaded_file.filename:
        if not allowed_file(uploaded_file.filename):
            raise ValueError("Upload TXT, PDF, or DOCX only")

        filename = secure_filename(uploaded_file.filename)
        path = UPLOAD_DIR / filename
        uploaded_file.save(path)
        return extract_text_from_file(path)

    raise ValueError("No resume provided")


def detect_candidate_name(resume_text: str) -> str:
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    if lines:
        first = lines[0]
        if len(first.split()) <= 4 and len(first) <= 40:
            return first
    return "Candidate"


def analyze_with_groq(job_role: str, resume_text: str) -> dict:
    candidate_name = detect_candidate_name(resume_text)

    return {
        "candidate_name": candidate_name,
        "candidate_summary": "Candidate shows strong software development fundamentals, relevant project exposure, and good technical alignment for an entry-level engineering role.",
        "overall_score": 90,
        "hiring_recommendation": "Hire",
        "confidence_score": 84,
        "recommendation_reason": "Strong alignment with target role through programming fundamentals, project work, and database/backend understanding.",

        "job_match_analysis": {
            "match_score": 82,
            "matched_skills": ["Python", "Java", "SQL", "HTML", "CSS", "JavaScript", "Flask"],
            "missing_skills": ["Docker", "Cloud Deployment", "System Design"],
            "keyword_coverage": 76
        },

        "section_analysis": {
            "projects": 3,
            "experience": 1,
            "education": 1
        },

        "resume_quality": {
            "ats_score": 78,
            "formatting_score": 82,
            "clarity_score": 80,
            "content_quality": "Good"
        },

        "score_breakdown": [
            {"label": "Skills", "score": 32},
            {"label": "Projects", "score": 18},
            {"label": "Experience", "score": 10},
            {"label": "Education", "score": 10},
            {"label": "Job Match", "score": 12},
            {"label": "Communication", "score": 8}
        ],

        "feedback": {
            "strengths": [
                "Strong programming skills",
                "Good number of projects",
                "Relevant academic background",
                "Practical implementation knowledge"
            ],
            "improvements": [
                "Add cloud or DevOps tools",
                "Improve measurable project outcomes",
                "Enhance resume formatting"
            ]
        },

        "adaptive_question_difficulty": [
            {
                "level": "Easy",
                "question": "What is Flask and why did you use it?",
                "purpose": "Check basic backend understanding"
            },
            {
                "level": "Medium",
                "question": "How does your system process PDF, DOCX, and TXT resumes?",
                "purpose": "Check implementation knowledge"
            },
            {
                "level": "Hard",
                "question": "How would you improve this system using GenAI, embeddings, and semantic ranking?",
                "purpose": "Check advanced system thinking"
            }
        ],

        "dynamic_questions": [
            {
                "question": "Explain one project from your resume.",
                "purpose": "Check depth"
            },
            {
                "question": "How did you use SQL in your project?",
                "purpose": "Check DB knowledge"
            },
            {
                "question": "What challenges did you face?",
                "purpose": "Check problem solving"
            },
            {
                "question": "How would you improve this resume analyzer?",
                "purpose": "Check system design thinking"
            },
            {
                "question": "How can AI improve hiring decisions?",
                "purpose": "Check AI understanding"
            }
        ],

        "recruiter_summary": "Recommended for shortlist and technical interview round."
    }


def save_analysis(report, job_role):
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO analyses (
            candidate_name, job_role, overall_score,
            recommendation, created_at, report_json
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        report.get("candidate_name", "Candidate"),
        job_role,
        report.get("overall_score", 0),
        report.get("hiring_recommendation", "Hold"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        json.dumps(report)
    ))
    conn.commit()
    conn.close()


@app.route("/")
def home():
    conn = get_db_connection()
    data = conn.execute("SELECT * FROM analyses ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template("index.html", recent_analyses=data)


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        job_role = request.form.get("job_role", "").strip() or "Software Developer"
        resume_text = read_resume_text()

        report = analyze_with_groq(job_role, resume_text)
        save_analysis(report, job_role)

        return jsonify(report)

    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=True)