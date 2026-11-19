# tests/test_lambda.py
"""
Unit tests for src/lambda_function.py

Tests cover:
  1.  GET /resume/personal        → 200
  2.  GET /resume/experience      → 200
  3.  GET /resume/education       → 200
  4.  GET /resume/skills          → 200
  5.  GET /resume                 → 200
  6.  Missing resume records      → 404
  7.  Invalid / unknown routes    → 400
  8.  Database ClientError        → 500 (no internal detail exposed)
  9.  JSON response structure     → status / message / data keys present

All AWS service calls are mocked. No active AWS account is required.

IMPORT ORDER NOTE:
  lambda_function.py calls database.initialise_data() at module level
  (outside the handler) on the first cold start. We inject a mock database
  into sys.modules BEFORE importing lambda_function so this call is safe
  and no boto3 connection is attempted during test collection.

Run with:  pytest tests/test_lambda.py -v
"""

import sys
import os
import json
from unittest.mock import MagicMock
import pytest

# conftest.py adds src/ to sys.path, but be explicit in case this file is run alone.
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ── Mock database object for lambda_function ──────────────────────────────────
import lambda_function

_mock_db = MagicMock()
_mock_db.initialise_data.return_value = None


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

PERSONAL = {
    "full_name": "Test User",
    "title": "Cloud Engineer",
    "email": "test@example.com",
    "phone": "+91-99999-00000",
    "location": "Mumbai, India",
    "summary": "Motivated cloud engineer.",
    "linkedin": "https://linkedin.com/in/testuser",
    "github": "https://github.com/testuser",
}

EXPERIENCE = [
    {
        "company": "Test Corp",
        "title": "Cloud Intern",
        "location": "Remote",
        "start_date": "June 2025",
        "end_date": "August 2025",
        "duration": "3 months",
        "responsibilities": ["Built serverless APIs on AWS"],
        "achievements": ["Reduced latency by 20%"],
    }
]

EDUCATION = [
    {
        "institution": "Test University",
        "degree": "B.E.",
        "field_of_study": "CSE",
        "location": "Mumbai",
        "start_year": "2022",
        "graduation_year": "2026",
        "cgpa": "8.5/10",
        "relevant_coursework": ["Cloud Computing"],
        "academic_achievements": ["Dean's List"],
    }
]

SKILLS = {
    "programming_languages": ["Python"],
    "cloud_technologies": ["AWS Lambda", "DynamoDB"],
    "databases": ["DynamoDB", "MySQL"],
    "development_tools": ["Git", "Postman"],
    "other_skills": ["REST APIs", "IaC"],
}

FULL_RESUME = {
    "personal": PERSONAL,
    "experience": EXPERIENCE,
    "education": EDUCATION,
    "skills": SKILLS,
}


@pytest.fixture(autouse=True)
def reset_mock_db(monkeypatch):
    """
    Reset all mock_db side_effects and return_values before every test to
    prevent state leakage between tests.
    """
    monkeypatch.setattr(lambda_function, "database", _mock_db)
    _mock_db.reset_mock()
    _mock_db.initialise_data.return_value = None
    # Set sensible defaults for every handler
    _mock_db.get_personal.return_value = PERSONAL
    _mock_db.get_experience.return_value = EXPERIENCE
    _mock_db.get_education.return_value = EDUCATION
    _mock_db.get_skills.return_value = SKILLS
    _mock_db.get_full_resume.return_value = FULL_RESUME
    yield


def api_event(method: str, path: str) -> dict:
    """Build a minimal API Gateway Lambda proxy integration event."""
    return {
        "httpMethod": method,
        "path": path,
        "resource": path,
        "pathParameters": None,
        "queryStringParameters": None,
        "headers": {"x-api-key": "test-api-key-value"},
        "body": None,
        "isBase64Encoded": False,
        "requestContext": {"stage": "test", "httpMethod": method},
    }


def body(response: dict) -> dict:
    """Deserialise the JSON response body."""
    return json.loads(response["body"])


def _client_error(code: str = "InternalServerError"):
    from botocore.exceptions import ClientError
    return ClientError({"Error": {"Code": code, "Message": "Simulated error"}}, "Op")


# ---------------------------------------------------------------------------
# 1.  Personal information endpoint
# ---------------------------------------------------------------------------

class TestPersonalEndpoint:

    def test_returns_200(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert response["statusCode"] == 200

    def test_body_status_is_success(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert body(response)["status"] == "success"

    def test_body_data_contains_full_name(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert body(response)["data"]["full_name"] == "Test User"

    def test_body_data_contains_all_required_fields(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        data = body(response)["data"]
        for field in ("full_name", "title", "email", "phone", "location",
                      "summary", "linkedin", "github"):
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# 2.  Work experience endpoint
# ---------------------------------------------------------------------------

class TestExperienceEndpoint:

    def test_returns_200(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/experience"), None)
        assert response["statusCode"] == 200

    def test_body_data_is_a_list(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/experience"), None)
        assert isinstance(body(response)["data"], list)

    def test_body_data_contains_one_entry(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/experience"), None)
        assert len(body(response)["data"]) == 1

    def test_experience_entry_has_company_and_title(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/experience"), None)
        entry = body(response)["data"][0]
        assert entry["company"] == "Test Corp"
        assert entry["title"] == "Cloud Intern"


# ---------------------------------------------------------------------------
# 3.  Education endpoint
# ---------------------------------------------------------------------------

class TestEducationEndpoint:

    def test_returns_200(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/education"), None)
        assert response["statusCode"] == 200

    def test_body_data_is_a_list(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/education"), None)
        assert isinstance(body(response)["data"], list)

    def test_education_entry_has_institution_and_degree(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/education"), None)
        entry = body(response)["data"][0]
        assert entry["institution"] == "Test University"
        assert entry["degree"] == "B.E."


# ---------------------------------------------------------------------------
# 4.  Skills endpoint
# ---------------------------------------------------------------------------

class TestSkillsEndpoint:

    def test_returns_200(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/skills"), None)
        assert response["statusCode"] == 200

    def test_body_data_contains_all_five_skill_categories(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/skills"), None)
        data = body(response)["data"]
        for category in ("programming_languages", "cloud_technologies", "databases",
                         "development_tools", "other_skills"):
            assert category in data, f"Missing skill category: {category}"

    def test_programming_languages_includes_python(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/skills"), None)
        assert "Python" in body(response)["data"]["programming_languages"]


# ---------------------------------------------------------------------------
# 5.  Full resume endpoint
# ---------------------------------------------------------------------------

class TestFullResumeEndpoint:

    def test_returns_200(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume"), None)
        assert response["statusCode"] == 200

    def test_body_data_contains_four_sections(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume"), None)
        data = body(response)["data"]
        for section in ("personal", "experience", "education", "skills"):
            assert section in data, f"Missing section: {section}"

    def test_personal_section_has_full_name(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume"), None)
        assert body(response)["data"]["personal"]["full_name"] == "Test User"

    def test_experience_section_is_a_list(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume"), None)
        assert isinstance(body(response)["data"]["experience"], list)


# ---------------------------------------------------------------------------
# 6.  Missing resume records → 404
# ---------------------------------------------------------------------------

class TestMissingRecords:

    def test_personal_not_found_returns_404(self):
        _mock_db.get_personal.return_value = None
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert response["statusCode"] == 404

    def test_skills_not_found_returns_404(self):
        _mock_db.get_skills.return_value = None
        response = lambda_function.lambda_handler(api_event("GET", "/resume/skills"), None)
        assert response["statusCode"] == 404

    def test_experience_empty_list_returns_404(self):
        _mock_db.get_experience.return_value = []
        response = lambda_function.lambda_handler(api_event("GET", "/resume/experience"), None)
        assert response["statusCode"] == 404

    def test_education_empty_list_returns_404(self):
        _mock_db.get_education.return_value = []
        response = lambda_function.lambda_handler(api_event("GET", "/resume/education"), None)
        assert response["statusCode"] == 404

    def test_full_resume_all_empty_returns_404(self):
        _mock_db.get_full_resume.return_value = {
            "personal": None, "experience": [], "education": [], "skills": None
        }
        response = lambda_function.lambda_handler(api_event("GET", "/resume"), None)
        assert response["statusCode"] == 404

    def test_404_body_status_is_error(self):
        _mock_db.get_personal.return_value = None
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert body(response)["status"] == "error"

    def test_404_body_data_is_null(self):
        _mock_db.get_personal.return_value = None
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert body(response)["data"] is None


# ---------------------------------------------------------------------------
# 7.  Invalid / unknown API routes → 400
# ---------------------------------------------------------------------------

class TestInvalidRoutes:

    def test_unknown_path_returns_400(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/unknown"), None)
        assert response["statusCode"] == 400

    def test_root_path_returns_400(self):
        response = lambda_function.lambda_handler(api_event("GET", "/"), None)
        assert response["statusCode"] == 400

    def test_empty_path_returns_400(self):
        response = lambda_function.lambda_handler(api_event("GET", ""), None)
        assert response["statusCode"] == 400

    def test_partial_resume_path_returns_400(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resum"), None)
        assert response["statusCode"] == 400

    def test_400_body_status_is_error(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/bogus"), None)
        assert body(response)["status"] == "error"

    def test_400_body_data_is_null(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/bogus"), None)
        assert body(response)["data"] is None


# ---------------------------------------------------------------------------
# 8.  Database exception handling → 500
# ---------------------------------------------------------------------------

class TestDatabaseExceptionHandling:

    def test_client_error_on_personal_returns_500(self):
        _mock_db.get_personal.side_effect = _client_error("ResourceNotFoundException")
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert response["statusCode"] == 500

    def test_client_error_on_experience_returns_500(self):
        _mock_db.get_experience.side_effect = _client_error("ProvisionedThroughputExceededException")
        response = lambda_function.lambda_handler(api_event("GET", "/resume/experience"), None)
        assert response["statusCode"] == 500

    def test_client_error_on_education_returns_500(self):
        _mock_db.get_education.side_effect = _client_error()
        response = lambda_function.lambda_handler(api_event("GET", "/resume/education"), None)
        assert response["statusCode"] == 500

    def test_client_error_on_skills_returns_500(self):
        _mock_db.get_skills.side_effect = _client_error()
        response = lambda_function.lambda_handler(api_event("GET", "/resume/skills"), None)
        assert response["statusCode"] == 500

    def test_client_error_on_full_resume_returns_500(self):
        _mock_db.get_full_resume.side_effect = _client_error()
        response = lambda_function.lambda_handler(api_event("GET", "/resume"), None)
        assert response["statusCode"] == 500

    def test_unexpected_exception_returns_500(self):
        _mock_db.get_personal.side_effect = RuntimeError("Unexpected crash")
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert response["statusCode"] == 500

    def test_500_does_not_expose_internal_error_message(self):
        """The response body must never contain internal exception details."""
        secret = "CONFIDENTIAL-TABLE-NAME-prod-9f3a"
        _mock_db.get_skills.side_effect = _client_error("InternalServerError")
        # Inject a secret into the error to verify it doesn't leak
        _mock_db.get_skills.side_effect.response["Error"]["Message"] = secret
        response = lambda_function.lambda_handler(api_event("GET", "/resume/skills"), None)
        assert secret not in response["body"]

    def test_500_body_status_is_error(self):
        _mock_db.get_personal.side_effect = _client_error()
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert body(response)["status"] == "error"


# ---------------------------------------------------------------------------
# 9.  JSON response structure
# ---------------------------------------------------------------------------

class TestResponseStructure:

    def test_success_response_has_status_message_data_keys(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        b = body(response)
        assert "status" in b
        assert "message" in b
        assert "data" in b

    def test_error_response_has_status_message_data_keys(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/invalid"), None)
        b = body(response)
        assert "status" in b
        assert "message" in b
        assert "data" in b

    def test_content_type_header_is_application_json(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        assert response["headers"]["Content-Type"] == "application/json"

    def test_cors_header_is_present(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume"), None)
        assert "Access-Control-Allow-Origin" in response["headers"]

    def test_body_is_valid_json_string(self):
        response = lambda_function.lambda_handler(api_event("GET", "/resume/personal"), None)
        parsed = json.loads(response["body"])   # Must not raise
        assert isinstance(parsed, dict)

    def test_post_method_returns_405(self):
        response = lambda_function.lambda_handler(api_event("POST", "/resume"), None)
        assert response["statusCode"] == 405

    def test_put_method_returns_405(self):
        response = lambda_function.lambda_handler(api_event("PUT", "/resume/personal"), None)
        assert response["statusCode"] == 405

    def test_delete_method_returns_405(self):
        response = lambda_function.lambda_handler(api_event("DELETE", "/resume/skills"), None)
        assert response["statusCode"] == 405

    def test_405_body_status_is_error(self):
        response = lambda_function.lambda_handler(api_event("POST", "/resume"), None)
        assert body(response)["status"] == "error"

    def test_message_field_is_a_non_empty_string(self):
        for path in ("/resume", "/resume/personal", "/resume/experience",
                     "/resume/education", "/resume/skills"):
            response = lambda_function.lambda_handler(api_event("GET", path), None)
            msg = body(response).get("message", "")
            assert isinstance(msg, str) and len(msg) > 0, f"Empty message for {path}"
