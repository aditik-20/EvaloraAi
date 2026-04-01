import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import requests
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

# Put your Groq API key in environment variable:
# Windows PowerShell:
# $env:GROQ_API_KEY="your_api_key_here"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# -----------------------------
# DATABASE
# -----------------------------
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


# -----------------------------
# FILE HANDLING
# -----------------------------
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


# -----------------------------
# LAYER A: RULE-BASED PARSING
# -----------------------------
SKILL_DB = [
    "python", "java", "c", "c++", "javascript", "typescript", "html", "css",
    "react", "node.js", "node", "flask", "django", "fastapi",
    "sql", "mysql", "postgresql", "mongodb", "sqlite",
    "git", "github", "docker", "aws", "azure",
    "machine learning", "deep learning", "nlp", "pandas", "numpy",
    "data structures", "algorithms", "oop", "dbms", "operating systems",
    "rest api", "api", "bootstrap"
]

JOB_ROLE_SKILLS = {
    "software developer": ["python", "java", "sql", "oop", "data structures", "git"],
    "backend developer": ["python", "flask", "sql", "api", "postgresql", "git"],
    "frontend developer": ["html", "css", "javascript", "react", "git"],
    "full stack developer": ["html", "css", "javascript", "react", "python", "flask", "sql", "git"],
    "data analyst": ["python", "sql", "pandas", "numpy"],
    "machine learning engineer": ["python", "machine learning", "deep learning", "nlp", "sql"]
}


def detect_candidate_name(resume_text: str) -> str:
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    if not lines:
        return "Candidate"

    for line in lines[:5]:
        words = line.split()
        if 1 <= len(words) <= 4 and len(line) <= 40:
            has_digits = any(ch.isdigit() for ch in line)
            has_email = "@" in line
            if not has_digits and not has_email:
                return line.title()

    return "Candidate"


def extract_email(resume_text: str):
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', resume_text)
    return match.group(0) if match else None


def extract_phone(resume_text: str):
    match = re.search(r'(\+?\d[\d\s\-()]{8,18}\d)', resume_text)
    return match.group(0).strip() if match else None


def detect_sections(resume_text: str) -> dict:
    lines = resume_text.splitlines()
    sections = {
        "skills": "",
        "projects": "",
        "education": "",
        "experience": "",
        "certifications": "",
        "other": ""
    }

    current_section = "other"

    for raw_line in lines:
        line = raw_line.strip()
        low = line.lower()

        if any(key in low for key in ["skills", "technical skills", "core skills"]):
            current_section = "skills"
            continue
        elif any(key in low for key in ["projects", "project"]):
            current_section = "projects"
            continue
        elif any(key in low for key in ["education", "academic", "qualification"]):
            current_section = "education"
            continue
        elif any(key in low for key in ["experience", "work experience", "internship", "internships"]):
            current_section = "experience"
            continue
        elif any(key in low for key in ["certification", "certifications"]):
            current_section = "certifications"
            continue

        sections[current_section] += line + "\n"

    return sections


def extract_skills(resume_text: str):
    text = resume_text.lower()
    found = []

    for skill in SKILL_DB:
        if skill in text:
            found.append(skill)

    return sorted(set(found))


def count_projects(section_text: str) -> int:
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    if not lines:
        return 0

    count = 0
    for line in lines:
        low = line.lower()
        if (
            "project" in low
            or "developed" in low
            or "built" in low
            or "designed" in low
            or "implemented" in low
        ):
            count += 1

    return max(1, count // 2) if count > 0 else 0


def count_education(section_text: str) -> int:
    text = section_text.lower()
    keywords = ["b.tech", "bachelor", "master", "degree", "university", "college", "school"]
    count = sum(1 for k in keywords if k in text)
    return max(1, count) if count > 0 else 0


def count_experience(section_text: str) -> int:
    text = section_text.lower()
    keywords = ["intern", "internship", "experience", "worked", "developer", "engineer"]
    count = sum(1 for k in keywords if k in text)
    return max(1, count) if count > 0 else 0


def get_job_role_requirements(job_role: str):
    role = job_role.strip().lower()
    return JOB_ROLE_SKILLS.get(role, ["python", "sql", "communication"])


def compute_match(extracted_skills: list, required_skills: list) -> dict:
    extracted_set = set(s.lower() for s in extracted_skills)
    required_set = set(s.lower() for s in required_skills)

    matched = sorted(list(extracted_set & required_set))
    missing = sorted(list(required_set - extracted_set))

    if len(required_set) == 0:
        match_score = 0
    else:
        match_score = int((len(matched) / len(required_set)) * 100)

    return {
        "match_score": match_score,
        "matched_skills": matched,
        "missing_skills": missing,
        "keyword_coverage": match_score
    }


def compute_ats_score(resume_text: str, matched_skills: list, missing_skills: list) -> int:
    text = resume_text.lower()
    score = 50

    if len(resume_text) > 300:
        score += 10

    score += min(20, len(matched_skills) * 3)
    score -= min(15, len(missing_skills) * 2)

    if "project" in text:
        score += 5
    if "education" in text:
        score += 5
    if "experience" in text or "internship" in text:
        score += 5

    return max(0, min(100, score))


def compute_formatting_score(resume_text: str) -> int:
    lines = [line for line in resume_text.splitlines() if line.strip()]
    if not lines:
        return 50

    short_lines = sum(1 for line in lines if len(line.strip()) < 80)
    ratio = short_lines / len(lines)
    score = int(60 + (ratio * 30))
    return max(0, min(100, score))


def compute_clarity_score(resume_text: str) -> int:
    words = resume_text.split()
    if not words:
        return 50

    avg_word_len = sum(len(w) for w in words) / len(words)

    if avg_word_len < 4:
        return 70
    if avg_word_len < 6:
        return 82
    return 74


def build_score_breakdown(skills_count, project_count, experience_count, education_count, match_score):
    return [
        {"label": "Skills", "score": min(35, skills_count * 4)},
        {"label": "Projects", "score": min(20, project_count * 6)},
        {"label": "Experience", "score": min(15, experience_count * 8)},
        {"label": "Education", "score": min(10, education_count * 10)},
        {"label": "Job Match", "score": min(12, max(0, match_score // 8))},
        {"label": "Communication", "score": 8}
    ]


# -----------------------------
# LAYER B: LLM / GENAI
# -----------------------------
def build_llm_prompt(job_role: str, resume_text: str, parsed_data: dict, match_data: dict) -> str:
    return f"""
You are an expert recruiter, resume evaluator, and interview panel assistant.

Analyze the following candidate for the role: {job_role}

Resume Text:
{resume_text}

Parsed Resume Data:
{json.dumps(parsed_data, indent=2)}

Job Match Data:
{json.dumps(match_data, indent=2)}

Return ONLY valid JSON with this exact structure:
{{
  "candidate_summary": "string",
  "overall_score": 0,
  "hiring_recommendation": "Hire or Hold or Reject",
  "confidence_score": 0,
  "recommendation_reason": "string",
  "feedback": {{
    "strengths": ["string", "string", "string"],
    "improvements": ["string", "string", "string"]
  }},
  "adaptive_question_difficulty": [
    {{
      "level": "Easy",
      "question": "string",
      "purpose": "string"
    }},
    {{
      "level": "Medium",
      "question": "string",
      "purpose": "string"
    }},
    {{
      "level": "Hard",
      "question": "string",
      "purpose": "string"
    }}
  ],
  "dynamic_questions": [
    {{
      "question": "string",
      "purpose": "string"
    }},
    {{
      "question": "string",
      "purpose": "string"
    }},
    {{
      "question": "string",
      "purpose": "string"
    }},
    {{
      "question": "string",
      "purpose": "string"
    }},
    {{
      "question": "string",
      "purpose": "string"
    }}
  ],
  "recruiter_summary": "string"
}}

Rules:
- Be realistic and professional.
- Base the answer on the resume content and parsed data.
- Keep strengths and improvements practical.
- Make interview questions relevant to the resume.
- Output only JSON. No markdown.
"""


def call_groq_llm(prompt: str) -> dict:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not found")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are an expert recruiter and resume analyst. Always return valid JSON only."},
            {"role": "user", "content": prompt}
        ]
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def fallback_llm_output(job_role: str, parsed_data: dict, match_data: dict) -> dict:
    skills = parsed_data["skills"]
    project_count = parsed_data["project_count"]
    experience_count = parsed_data["experience_count"]
    education_count = parsed_data["education_count"]
    match_score = match_data["match_score"]

    if match_score >= 75:
        recommendation = "Hire"
        reason = "Candidate shows strong alignment with the target role based on skills and project relevance."
        summary = "Candidate demonstrates good technical fundamentals, relevant project exposure, and a strong entry-level fit for the target role."
        recruiter_summary = "Recommended for shortlist and technical interview round."
    elif match_score >= 45:
        recommendation = "Hold"
        reason = "Candidate has a reasonable base but still shows some important skill gaps for the target role."
        summary = "Candidate has fair alignment with the role, with useful technical basics but some missing areas to strengthen."
        recruiter_summary = "Can be considered after stronger matching profiles are screened."
    else:
        recommendation = "Reject"
        reason = "Candidate currently lacks several core requirements expected for the role."
        summary = "Candidate profile is currently weaker compared to the expected role requirements."
        recruiter_summary = "Not recommended for immediate shortlist."

    overall_score = min(
        100,
        40
        + min(20, len(skills) * 3)
        + min(15, project_count * 5)
        + min(10, experience_count * 5)
        + min(10, education_count * 5)
        + min(5, match_score // 20)
    )

    strengths = []
    improvements = []

    if len(skills) >= 5:
        strengths.append("Good breadth of technical skills mentioned in the resume.")
    if project_count > 0:
        strengths.append("Resume shows hands-on project exposure.")
    if education_count > 0:
        strengths.append("Educational background is clearly present.")
    if experience_count > 0:
        strengths.append("Resume includes experience or internship-related signals.")

    if "docker" not in skills:
        improvements.append("Add DevOps or deployment tools like Docker to improve industry readiness.")
    if "aws" not in skills and "azure" not in skills:
        improvements.append("Mention cloud exposure or deployment knowledge if available.")
    improvements.append("Add measurable outcomes in projects, such as performance gains or user impact.")

    while len(strengths) < 3:
        strengths.append("Profile shows potential for further technical growth.")
    while len(improvements) < 3:
        improvements.append("Improve resume structure and role-specific customization.")

    dynamic_questions = [
        {
            "question": f"What motivated you to apply for the role of {job_role}?",
            "purpose": "Check role alignment"
        },
        {
            "question": "Explain one project from your resume in detail.",
            "purpose": "Check project depth"
        },
        {
            "question": "Which technical skill are you most confident in, and why?",
            "purpose": "Check self-awareness and technical strength"
        },
        {
            "question": "What challenge did you face while building your project and how did you solve it?",
            "purpose": "Check problem solving"
        },
        {
            "question": "How would you improve your current resume or project portfolio further?",
            "purpose": "Check growth mindset"
        }
    ]

    if "sql" in skills:
        dynamic_questions[2] = {
            "question": "How did you use SQL in your project or coursework?",
            "purpose": "Check DB understanding"
        }

    if "flask" in skills:
        dynamic_questions[1] = {
            "question": "Why did you choose Flask and how did you structure your backend?",
            "purpose": "Check backend design understanding"
        }

    return {
        "candidate_summary": summary,
        "overall_score": overall_score,
        "hiring_recommendation": recommendation,
        "confidence_score": min(95, max(65, match_score + 10)),
        "recommendation_reason": reason,
        "feedback": {
            "strengths": strengths[:3],
            "improvements": improvements[:3]
        },
        "adaptive_question_difficulty": [
            {
                "level": "Easy",
                "question": "Tell me about yourself and your technical background.",
                "purpose": "Check communication and profile clarity"
            },
            {
                "level": "Medium",
                "question": "How does your resume demonstrate fit for this role?",
                "purpose": "Check role understanding"
            },
            {
                "level": "Hard",
                "question": "How would you improve one of your projects to make it production-ready?",
                "purpose": "Check advanced engineering thinking"
            }
        ],
        "dynamic_questions": dynamic_questions,
        "recruiter_summary": recruiter_summary
    }


# -----------------------------
# MAIN ANALYSIS
# -----------------------------
def analyze_with_groq(job_role: str, resume_text: str) -> dict:
    candidate_name = detect_candidate_name(resume_text)
    email = extract_email(resume_text)
    phone = extract_phone(resume_text)
    sections = detect_sections(resume_text)
    skills = extract_skills(resume_text)

    project_count = count_projects(sections["projects"])
    education_count = count_education(sections["education"])
    experience_count = count_experience(sections["experience"])

    required_skills = get_job_role_requirements(job_role)
    match_data = compute_match(skills, required_skills)

    ats_score = compute_ats_score(
        resume_text,
        match_data["matched_skills"],
        match_data["missing_skills"]
    )
    formatting_score = compute_formatting_score(resume_text)
    clarity_score = compute_clarity_score(resume_text)

    parsed_data = {
        "candidate_name": candidate_name,
        "email": email,
        "phone": phone,
        "skills": skills,
        "required_skills": required_skills,
        "project_count": project_count,
        "education_count": education_count,
        "experience_count": experience_count,
        "sections_detected": {
            "skills": bool(sections["skills"].strip()),
            "projects": bool(sections["projects"].strip()),
            "education": bool(sections["education"].strip()),
            "experience": bool(sections["experience"].strip()),
            "certifications": bool(sections["certifications"].strip())
        }
    }

    try:
        prompt = build_llm_prompt(job_role, resume_text, parsed_data, match_data)
        llm_output = call_groq_llm(prompt)
    except Exception:
        llm_output = fallback_llm_output(job_role, parsed_data, match_data)

    score_breakdown = build_score_breakdown(
        skills_count=len(skills),
        project_count=project_count,
        experience_count=experience_count,
        education_count=education_count,
        match_score=match_data["match_score"]
    )

    return {
        "candidate_name": candidate_name,
        "email": email,
        "phone": phone,
        "candidate_summary": llm_output.get("candidate_summary", "Candidate profile analyzed successfully."),
        "overall_score": llm_output.get("overall_score", match_data["match_score"]),
        "hiring_recommendation": llm_output.get("hiring_recommendation", "Hold"),
        "confidence_score": llm_output.get("confidence_score", 75),
        "recommendation_reason": llm_output.get("recommendation_reason", "Evaluation completed based on resume content and role fit."),

        "job_match_analysis": match_data,

        "section_analysis": {
            "projects": project_count,
            "experience": experience_count,
            "education": education_count
        },

        "resume_quality": {
            "ats_score": ats_score,
            "formatting_score": formatting_score,
            "clarity_score": clarity_score,
            "content_quality": "Good" if ats_score >= 70 else "Average"
        },

        "score_breakdown": score_breakdown,

        "feedback": llm_output.get("feedback", {
            "strengths": ["Good technical foundation"],
            "improvements": ["Add more role-specific details"]
        }),

        "adaptive_question_difficulty": llm_output.get("adaptive_question_difficulty", []),
        "dynamic_questions": llm_output.get("dynamic_questions", []),
        "recruiter_summary": llm_output.get("recruiter_summary", "Analysis completed.")
    }


# -----------------------------
# SAVE REPORT
# -----------------------------
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


# -----------------------------
# ROUTES
# -----------------------------
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