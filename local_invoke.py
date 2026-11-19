"""
local_invoke.py
---------------
Utility script to test Lambda handlers locally without deploying to AWS.
Loads seed data from data/resume.json into a mocked database layer and
simulates an API Gateway request.

Usage:
    python local_invoke.py [route]

Examples:
    python local_invoke.py /resume
    python local_invoke.py /resume/personal
    python local_invoke.py /resume/experience
    python local_invoke.py /resume/education
    python local_invoke.py /resume/skills
"""

import json
import os
import sys
from unittest.mock import MagicMock

# Add src/ to path
SRC_DIR = os.path.join(os.path.dirname(__file__), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import lambda_function  # noqa: E402

# Load local seed data from data/resume.json
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "resume.json")
with open(DATA_PATH, "r", encoding="utf-8") as f:
    resume_data = json.load(f)

# Mock database calls with local JSON data
mock_db = MagicMock()
mock_db.get_personal.return_value = resume_data.get("personal")
mock_db.get_experience.return_value = resume_data.get("experience")
mock_db.get_education.return_value = resume_data.get("education")
mock_db.get_skills.return_value = resume_data.get("skills")
mock_db.get_full_resume.return_value = resume_data

lambda_function.database = mock_db

# Determine route from command-line arguments (default: /resume/personal)
route = sys.argv[1] if len(sys.argv) > 1 else "/resume/personal"

# Simulate API Gateway proxy event
event = {
    "httpMethod": "GET",
    "path": route,
    "resource": route,
    "headers": {"x-api-key": "local-test-key"},
}

print(f"=== Invoking Lambda handler for route: {route} ===")
response = lambda_function.lambda_handler(event, None)

print(f"HTTP Status: {response['statusCode']}")
print("Response Body:")
print(json.dumps(json.loads(response["body"]), indent=2))
