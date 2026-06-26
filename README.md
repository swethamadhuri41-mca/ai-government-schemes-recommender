# AI Personalized Government Schemes and Jobs Eligibility Recommender

A Flask web app that opens directly to an eligibility form, checks the user's
profile against local JSON rule data for government schemes and jobs, and
uses Gemini AI only to explain the results in plain English (never to decide
eligibility).

## Folder structure
```
project/
├── app.py                 # Flask app + rule-based eligibility engine
├── requirements.txt
├── .env                    # Gemini API key (fill this in)
├── schemes.json            # 5 sample government schemes
├── jobs.json                # 5 sample government jobs
├── templates/
│   ├── index.html           # The eligibility form (opens by default)
│   └── result.html          # Results page
└── static/
    ├── style.css
    └── script.js
```

## Setup

1. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Add your Gemini API key**
   Open `.env` and replace `your_gemini_api_key_here` with a real key from
   https://aistudio.google.com/app/apikey

   > The app still works without a key — it will fall back to simple
   > template-based summaries/reasons instead of Gemini-generated text.

4. **Run the app**
   ```bash
   python app.py
   ```
   Then open http://127.0.0.1:5000/ in your browser. You'll land directly on
   the eligibility form — no home page, login, or dashboard.

## How eligibility works

- All eligibility decisions come from `evaluate_item()` in `app.py`, which
  compares the submitted form data against the `eligibility` rules inside
  `schemes.json` / `jobs.json` (age range, income ceiling, category, state,
  gender, education, occupation, disability).
- Gemini is called **once per submission** (not once per item, to keep things
  fast) purely to write a friendly profile summary and a short "why
  recommended" sentence for each item that the rule engine already approved.
- If Gemini is unavailable for any reason, the app automatically falls back
  to clear template-generated text so results are never blocked.

## Customizing data

To add more schemes or jobs, add another object to `schemes.json` or
`jobs.json` following the existing structure — `min_age`/`max_age` (or
`null` for no limit), `max_income` (or `null`), `categories`, `states`,
`gender`, `education`, `occupation` (use `["All"]` / `["Any"]` for "open to
everyone"), and `disability` (`"Yes"`, `"No"`, or `"Any"`).
