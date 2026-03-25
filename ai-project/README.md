# Resume Analyzer

A simple and easy-to-understand resume analyzer built with:

- Frontend: HTML, CSS, JavaScript, Bootstrap
- Backend: Python Flask
- Database: SQLite
- AI: OpenAI API

## Included Novelty Features

This project only highlights these five novelty features:

1. Adaptive Question Difficulty
2. AI Follow-Up Question Generator
3. Explainable AI Feedback
4. Hiring Recommendation Engine
5. Basic Integrity Monitoring

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set your OpenAI API key:

```bash
export OPENAI_API_KEY="your_openai_api_key_here"
export OPENAI_MODEL="gpt-4.1-mini"
```

4. Run the app:

```bash
python app.py
```

5. Open in browser:

```text
http://127.0.0.1:5000
```

## Notes

- You can paste a resume directly or upload a TXT, PDF, or DOCX file.
- Every analysis is stored in SQLite in `resume_analyzer.db`.
- The recent analysis table is shown on the homepage.
