"""
AI Personalized Government Schemes and Jobs Eligibility Recommender
---------------------------------------------------------------------
Flask backend.

IMPORTANT DESIGN RULE:
  Eligibility is decided ONLY by the rule engine below (evaluate_item),
  which compares the user's form data against schemes.json / jobs.json.
  Gemini AI is used ONLY to:
    - write a personalized profile summary,
    - explain why each ALREADY-eligible scheme/job suits the user, and
    - attach a High/Medium/Low "AI relevance" label for display purposes.
  The AI is never asked to decide who qualifies, and its output (reasons,
  relevance labels) is never used to add/remove/re-rank results - that
  stays fully controlled by the Python rule engine and JSON data.
  If Gemini is unreachable or returns something unusable, the app logs
  the failure and transparently switches to template-based fallback text
  so the page always renders correctly.
"""

import os
import json
import re


from flask import Flask, render_template, request
from dotenv import load_dotenv

# google-genai is optional at runtime: if it is not installed or no
# API key is configured, the app still works and uses template-based text.
try:
    from google import genai
except ImportError:  # pragma: no cover - handled gracefully at runtime
    genai = None

load_dotenv()

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

GEMINI_ENABLED = bool(GEMINI_API_KEY) and genai is not None
gemini_client = None

# ---------------------------------------------------------------------------
# Gemini connection check (terminal logging only - does not affect routing)
# ---------------------------------------------------------------------------
# if GEMINI_ENABLED:
#     try:
#         gemini_client = genai.Client(api_key=GEMINI_API_KEY)
#         print("✅ Gemini Connected")
#         print(f"   Model: {GEMINI_MODEL}")
#     except Exception as exc:  # noqa: BLE001 - any client creation failure should disable Gemini, not crash the app
#         GEMINI_ENABLED = False
#         gemini_client = None
#         print("❌ Gemini Not Connected")
#         print(f"   Reason: {exc}")
# else:
#     print("❌ Gemini Not Connected")
#     if genai is None:
#         print("   Reason: 'google-genai' package is not installed")
#     elif not GEMINI_API_KEY:
#         print("   Reason: GEMINI_API_KEY is missing/empty in .env")

if GEMINI_ENABLED:

    try:

        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )
        print("✅ Gemini Fully Connected")

    except Exception as exc:

        GEMINI_ENABLED = False

        gemini_client = None

        print("❌ Gemini Connection Failed")

        print(exc)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_json_file(filename):
    """Load a JSON data file from the project root."""
    path = os.path.join(BASE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


SCHEMES = load_json_file("schemes.json")
JOBS = load_json_file("jobs.json")

# Dropdown options shown on the form. Keeping these as constants (instead of
# free-text input) keeps the values consistent with what schemes.json /
# jobs.json expect, which makes the rule engine reliable.
INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
    "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

EDUCATION_OPTIONS = [
    "Below 10th", "10th Pass", "12th Pass", "Diploma",
    "Undergraduate", "Postgraduate", "Doctorate",
]

OCCUPATION_OPTIONS = [
    "Student", "Farmer", "Self-Employed/Business", "Government Job",
    "Private Job", "Daily Wage Worker", "Unemployed", "Other",
]

GENDER_OPTIONS = ["Male", "Female", "Other"]
CATEGORY_OPTIONS = ["OC", "BC", "SC", "ST"]
DISABILITY_OPTIONS = ["Yes", "No"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
def validate_and_parse(form):
    """
    Validate the submitted form and convert it into a clean dict.
    Returns (user_dict, list_of_error_strings).
    If there are errors, user_dict still contains whatever was parsed so the
    form can be re-rendered with the user's previous entries.
    """
    errors = []

    full_name = (form.get("full_name") or "").strip()
    age_raw = (form.get("age") or "").strip()
    gender = (form.get("gender") or "").strip()
    state = (form.get("state") or "").strip()
    education = (form.get("education") or "").strip()
    occupation = (form.get("occupation") or "").strip()
    income_raw = (form.get("annual_income") or "").strip()
    category = (form.get("category") or "").strip()
    disability = (form.get("disability") or "").strip()

    # Full name
    if not full_name:
        errors.append("Full name is required.")
    elif not re.match(r"^[A-Za-z\s.'-]{2,60}$", full_name):
        errors.append("Full name should only contain letters and spaces (2-60 characters).")

    # Age
    age = None
    if not age_raw:
        errors.append("Age is required.")
    else:
        try:
            age = int(age_raw)
            if age < 1 or age > 100:
                errors.append("Age must be between 1 and 100.")
        except ValueError:
            errors.append("Age must be a valid whole number.")

    # Gender
    if gender not in GENDER_OPTIONS:
        errors.append("Please select a valid gender.")

    # State
    if state not in INDIAN_STATES:
        errors.append("Please select a valid state.")

    # Education
    if education not in EDUCATION_OPTIONS:
        errors.append("Please select a valid education level.")

    # Occupation
    if occupation not in OCCUPATION_OPTIONS:
        errors.append("Please select a valid occupation.")

    # Annual income
    income = None
    if not income_raw:
        errors.append("Annual income is required.")
    else:
        try:
            income = float(income_raw)
            if income < 0:
                errors.append("Annual income cannot be negative.")
            if income > 100000000:
                errors.append("Please enter a realistic annual income.")
        except ValueError:
            errors.append("Annual income must be a valid number.")

    # Category
    if category not in CATEGORY_OPTIONS:
        errors.append("Please select a valid category.")

    # Disability
    if disability not in DISABILITY_OPTIONS:
        errors.append("Please specify your disability status.")

    user = {
        "full_name": full_name,
        "age": age,
        "gender": gender,
        "state": state,
        "education": education,
        "occupation": occupation,
        "income": income,
        "category": category,
        "disability": disability,
    }
    return user, errors


# ---------------------------------------------------------------------------
# Rule-based eligibility engine
# (No AI is involved anywhere in this section.)
# ---------------------------------------------------------------------------
def _normalize(value):
    return str(value).strip().lower()


def matches_list(user_value, allowed_list):
    """
    True if user_value is present in allowed_list, OR if allowed_list is a
    wildcard ("All" / "Any") meaning the field does not restrict eligibility.
    """
    if not allowed_list:
        return True
    normalized_allowed = [_normalize(v) for v in allowed_list]
    if "all" in normalized_allowed or "any" in normalized_allowed:
        return True
    return _normalize(user_value) in normalized_allowed


def evaluate_item(user, item):
    """
    Compares the user's profile against a single scheme/job's "eligibility"
    block from schemes.json / jobs.json.

    Returns:
        None              -> user does NOT qualify (hard rule failed)
        "High"/"Medium"/"Low" -> user qualifies, with an eligibility strength
                                 score based on how specifically this
                                 scheme/job targets their profile.
    """
    elig = item.get("eligibility", {})

    # ---- Hard rules: ALL must pass, otherwise the user is not eligible ----
    if elig.get("min_age") is not None and user["age"] < elig["min_age"]:
        return None
    if elig.get("max_age") is not None and user["age"] > elig["max_age"]:
        return None
    if elig.get("max_income") is not None and user["income"] > elig["max_income"]:
        return None
    if not matches_list(user["category"], elig.get("categories", ["All"])):
        return None
    if not matches_list(user["state"], elig.get("states", ["All"])):
        return None
    if not matches_list(user["gender"], elig.get("gender", ["All"])):
        return None
    if not matches_list(user["occupation"], elig.get("occupation", ["Any"])):
        return None
    if not matches_list(user["education"], elig.get("education", ["Any"])):
        return None

    disability_required = elig.get("disability", "Any")
    if disability_required not in ("Any", None):
        if _normalize(user["disability"]) != _normalize(disability_required):
            return None

    # ---- Soft scoring: how specifically targeted is this scheme/job? -----
    # Wildcard fields ("All"/"Any") are open to everyone, so they contribute
    # a neutral amount. Fields that name specific values (e.g. categories
    # restricted to SC/ST/BC, or a state-specific job) reward a stronger
    # match because the user fits a more targeted requirement.
    score_points = 0.0
    max_points = 0.0

    # Category specificity
    max_points += 1
    if not matches_list("__wildcard_probe__", elig.get("categories", ["All"])):
        score_points += 1
    else:
        score_points += 0.5

    # Income margin (only relevant if a max_income rule exists)
    if elig.get("max_income") is not None and elig["max_income"] > 0:
        max_points += 1
        ratio = user["income"] / elig["max_income"]
        if ratio <= 0.5:
            score_points += 1
        elif ratio <= 0.85:
            score_points += 0.6
        else:
            score_points += 0.3

    # Disability-targeted scheme/job
    if disability_required not in ("Any", None):
        max_points += 1
        score_points += 1

    # State-specific scheme/job
    if not matches_list("__wildcard_probe__", elig.get("states", ["All"])):
        max_points += 1
        score_points += 1

    # Occupation-specific scheme/job
    if not matches_list("__wildcard_probe__", elig.get("occupation", ["Any"])):
        max_points += 1
        score_points += 1

    ratio = (score_points / max_points) if max_points > 0 else 1.0

    if ratio >= 0.75:
        return "High"
    elif ratio >= 0.45:
        return "Medium"
    else:
        return "Low"


SCORE_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def find_eligible(user, items):
    """Run the rule engine over a list of schemes/jobs and return matches."""
    results = []
    for item in items:
        score = evaluate_item(user, item)
        if score is not None:
            result = dict(item)
            result["score"] = score
            results.append(result)
    results.sort(key=lambda r: SCORE_ORDER[r["score"]])
    return results


# ---------------------------------------------------------------------------
# AI explanation layer (Gemini) - text + relevance ranking ONLY.
# Eligibility (who shows up at all, and the rule-based "score" on each item)
# is decided exclusively by evaluate_item()/find_eligible() above and is
# NEVER touched by anything in this section. Gemini is only allowed to:
#   1) write a personalized profile summary,
#   2) explain why each ALREADY-eligible scheme/job suits the user,
#   3) attach a High/Medium/Low "AI relevance" label for display purposes.
# That relevance label never adds, removes, or re-sorts results.
# ---------------------------------------------------------------------------
VALID_RELEVANCE_LEVELS = {"High", "Medium", "Low"}


def _clean_relevance(value, fallback):
    """
    Make sure a relevance value coming from Gemini is one of
    High/Medium/Low. If it's missing, malformed, or anything unexpected,
    fall back to the item's own rule-based eligibility score instead -
    this guarantees the UI never shows a broken/invalid value.
    """
    if isinstance(value, str) and value.strip().title() in VALID_RELEVANCE_LEVELS:
        return value.strip().title()
    return fallback


def build_fallback_ai_content(user, schemes, jobs):
    """
    Template-based text used when Gemini is unavailable (no API key,
    network error, quota error, parsing error, etc.) so the app always
    works end-to-end without depending on the AI service.
    """
    income_display = f"₹{user['income']:,.0f}" if user["income"] is not None else "N/A"
    summary = (
        f"{user['full_name']} is a {user['age']}-year-old {user['gender']} from "
        f"{user['state']}, educated up to {user['education']}, currently working "
        f"as {user['occupation']}, with an annual income of {income_display} "
        f"and belonging to the {user['category']} category."
    )

    scheme_reasons = {
        s["name"]: (
            f"Your age, income, and category fit this scheme's eligibility rules "
            f"(match strength: {s['score']})."
        )
        for s in schemes
    }
    job_reasons = {
        j["name"]: (
            f"Your age, education, and location fit this job's eligibility rules "
            f"(match strength: {j['score']})."
        )
        for j in jobs
    }

    # Without Gemini, the AI relevance label simply mirrors the rule-based
    # eligibility score so the page still shows a sensible value.
    scheme_relevance = {s["name"]: s["score"] for s in schemes}
    job_relevance = {j["name"]: j["score"] for j in jobs}

    return {
        "summary": summary,
        "scheme_reasons": scheme_reasons,
        "job_reasons": job_reasons,
        "scheme_relevance": scheme_relevance,
        "job_relevance": job_relevance,
        "mode": "fallback",
    }


def build_gemini_prompt(user, schemes, jobs):
    scheme_lines = "\n".join(
        f"- {s['name']} (eligibility strength: {s['score']}): {s['description']}"
        for s in schemes
    ) or "None"
    job_lines = "\n".join(
        f"- {j['name']} (eligibility strength: {j['score']}): {j['description']}"
        for j in jobs
    ) or "None"

    income_display = f"{user['income']:,.0f}" if user["income"] is not None else "N/A"

    return f"""
You are GramaSahay AI, an intelligent assistant that helps rural citizens of India discover government schemes and jobs.

IMPORTANT RULES:

- Eligibility has ALREADY been decided by a Python rule engine.
- Never add, remove or reorder schemes/jobs.
- Never say a user is ineligible for an item already provided.
- Explain only the items given.

Your tasks:

1. Analyze the user's profile deeply.
2. Write a personalized summary of 180-250 words in 2-3 paragraphs.
3. Explain why each scheme suits this person.
4. Explain why each job suits this person.
5. Give encouraging guidance.

User Profile:

Name: {user['full_name']}
Age: {user['age']}
Gender: {user['gender']}
State: {user['state']}
Education: {user['education']}
Occupation: {user['occupation']}
Annual Income: Rs. {income_display}
Category: {user['category']}
Disability: {user['disability']}

Eligible Schemes:

{scheme_lines}

Eligible Jobs:

{job_lines}

Respond ONLY as JSON.

JSON format:

{{
  "summary":"180-250 word detailed summary",

  "scheme_reasons":{{
    "<exact scheme name>":"3-4 sentence explanation"
  }},

  "job_reasons":{{
    "<exact job name>":"3-4 sentence explanation"
  }},

  "scheme_relevance":{{
    "<exact scheme name>":"High"
  }},

  "job_relevance":{{
    "<exact job name>":"High"
  }}
}}
"""


def get_ai_content(user, schemes, jobs):
    """
    Calls Gemini once to generate the profile summary, per-item reasons,
    and a per-item AI relevance label, for results the rule engine has
    ALREADY approved (more efficient than one call per item).

    Robust exception handling ensures any failure - missing key, network
    error, safety-blocked response, malformed JSON, unexpected shape -
    gracefully falls back to template-based text instead of crashing or
    showing a broken page.
    """
    fallback = build_fallback_ai_content(user, schemes, jobs)

    if not GEMINI_ENABLED:
        print("❌ Using Fallback Mode")
        print("   Reason: Gemini is not connected (see startup log above)")
        return fallback

    try:
        prompt = build_gemini_prompt(user, schemes, jobs)
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        # response.text raises ValueError if Gemini blocked the prompt/output
        # (e.g. safety filters) or returned no candidates at all.
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Gemini returned an empty response")

        # Some Gemini responses wrap JSON in markdown code fences - strip them.
        text = re.sub(r"^```(json)?", "", text.strip())
        text = re.sub(r"```$", "", text.strip()).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as json_err:
            raise ValueError(f"Gemini response was not valid JSON ({json_err})") from json_err

        if not isinstance(data, dict) or "summary" not in data:
            raise ValueError("Gemini response JSON was missing the required 'summary' key")

        data.setdefault("scheme_reasons", {})
        data.setdefault("job_reasons", {})
        data.setdefault("scheme_relevance", {})
        data.setdefault("job_relevance", {})
        data["mode"] = "gemini"

        print("✅ Gemini Response Generated")
        return data

    except Exception as exc:  # noqa: BLE001 - any failure here must degrade gracefully, never crash the page
        print("❌ Using Fallback Mode")
        print(f"   Reason: Gemini request failed - {exc}")
        return fallback


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """The application opens directly on this eligibility form."""
    return render_template(
        "index.html",
        states=INDIAN_STATES,
        educations=EDUCATION_OPTIONS,
        occupations=OCCUPATION_OPTIONS,
        genders=GENDER_OPTIONS,
        categories=CATEGORY_OPTIONS,
        disabilities=DISABILITY_OPTIONS,
        errors=[],
        form_data={},
    )


@app.route("/recommend", methods=["POST"])
def recommend():
    """Validate input, run the rule engine, get AI explanations, show results."""
    user, errors = validate_and_parse(request.form)

    if errors:
        # Re-render the form with the error messages and previously typed values.
        return render_template(
            "index.html",
            states=INDIAN_STATES,
            educations=EDUCATION_OPTIONS,
            occupations=OCCUPATION_OPTIONS,
            genders=GENDER_OPTIONS,
            categories=CATEGORY_OPTIONS,
            disabilities=DISABILITY_OPTIONS,
            errors=errors,
            form_data=request.form,
        )

    eligible_schemes = find_eligible(user, SCHEMES)
    eligible_jobs = find_eligible(user, JOBS)

    # Order here is still fully decided by find_eligible()/evaluate_item()
    # (the rule engine). Gemini only adds explanatory text + a relevance
    # label on top of this already-final list - it cannot add, remove, or
    # reorder anything.
    ai_content = get_ai_content(user, eligible_schemes, eligible_jobs)

    for s in eligible_schemes:
        s["reason"] = ai_content.get("scheme_reasons", {}).get(
            s["name"], "Matches your profile based on the eligibility rules."
        )
        # AI relevance is purely explanatory; if Gemini didn't return a
        # valid High/Medium/Low value for this item, fall back to its own
        # rule-based eligibility score so the UI always has something sane.
        s["ai_relevance"] = _clean_relevance(
            ai_content.get("scheme_relevance", {}).get(s["name"]), s["score"]
        )
    for j in eligible_jobs:
        j["reason"] = ai_content.get("job_reasons", {}).get(
            j["name"], "Matches your profile based on the eligibility rules."
        )
        j["ai_relevance"] = _clean_relevance(
            ai_content.get("job_relevance", {}).get(j["name"]), j["score"]
        )

    return render_template(
        "result.html",
        user=user,
        summary=ai_content.get("summary", ""),
        schemes=eligible_schemes,
        jobs=eligible_jobs,
        ai_mode=ai_content.get("mode", "fallback"),
    )


if __name__ == "__main__":
    app.run(debug=True,
        use_reloader=False)