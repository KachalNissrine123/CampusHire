# CampusHire

A hiring portal for on-campus student jobs at Al Akhawayn University. Departments
(the SAO, the RA Program, the CLE, ...) post positions with the GPA, credits, level,
school and skills they need. Students apply with their CV. Before a department
sees an application, it is screened against the posting and given a score, so
departments get a ranked shortlist instead of a stack of PDFs.

**Stack:** Flask · SQLAlchemy · PostgreSQL · OpenAI API · pypdf / python-docx

## How an application moves through the system

```
student uploads CV ──▶ applies to a position
                            │
                            ▼
                 screen_application()
           ┌────────────────┴────────────────┐
   OPENAI_API_KEY set and             no key, unreadable CV,
   CV text extracted                  or the API call fails
           │                                 │
   model reads CV + posting,         profile_match_score():
   returns pass/fail, score, reason  weighted GPA/credits/level/school
           └────────────────┬────────────────┘
                            ▼
        score ≥ 0.6 → under_review     score < 0.6 → rejected
                            │
                            ▼
       department sees applicants sorted by score, opens CVs,
       accepts/rejects → student gets a notification
```

The fallback scorer means the app works without an API key: each requirement a
position sets has a weight (GPA 0.3, school 0.3, credits 0.2, level 0.2), and the
score is the share of those weights the student earns. A student below the GPA or
credit minimum gets partial credit in proportion; a level mismatch gets half credit.

## Access rules

- Students see only their own applications and notifications.
- Departments can view and update only applicants to their own positions.
- A CV can be downloaded only by the student who uploaded it and by departments
  that student applied to. Department logos are public.
- Uploaded files are restricted to PDF/DOCX (CVs) and PNG/JPG/WEBP (logos), 16 MB max.

## Running it locally

Requires Python 3.10+ and PostgreSQL.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

createdb campushire               # or create it in pgAdmin
cp .env.example .env              # then set DATABASE_URL (and OPENAI_API_KEY if you have one)

python app.py
```

Open http://127.0.0.1:5001. Tables are created on first start.

To try it out, register a department, post a position, then register a student in
another browser (or a private window), upload a CV and apply.

## Project layout

```
app.py          routes, screening logic, upload handling
models.py       Student, Department, Position, Application, Notification
config.py       settings read from .env
templates/      Jinja pages (student and department views)
static/         CSS and the small bit of JS for flash messages and score bars
uploads/        CVs and logos at runtime (git-ignored)
```
