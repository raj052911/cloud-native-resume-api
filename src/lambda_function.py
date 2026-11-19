"""
lambda_function.py
------------------
Entry point for the Serverless Resume API AWS Lambda function.

Routing table:
  GET /resume            → handle_full_resume()
  GET /resume/personal   → handle_personal()
  GET /resume/experience → handle_experience()
  GET /resume/education  → handle_education()
  GET /resume/skills     → handle_skills()

Design notes:
  - A single Lambda function handles all five routes; API Gateway passes
    the resource path and HTTP method so the handler can dispatch correctly.
  - `database.initialise_data()` is called once per cold start (outside the
    handler) so subsequent warm invocations skip the DynamoDB check.
  - All database exceptions bubble up to the top-level try/except which
    returns HTTP 500 without exposing internal details.
  - Only GET is accepted; any other method returns HTTP 405.
"""

import logging

from botocore.exceptions import ClientError

import database
import response as res

# ---------------------------------------------------------------------------
# Lazy data initialisation (runs once per Lambda execution environment)
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_data_initialized = False


def _ensure_data_initialized() -> None:
    """Ensure DynamoDB contains initial resume data on first invocation."""
    global _data_initialized
    if not _data_initialized:
        database.initialise_data()
        _data_initialized = True


# ---------------------------------------------------------------------------
# Route definitions
# ---------------------------------------------------------------------------
_ROUTES = {
    "/resume": "full",
    "/resume/personal": "personal",
    "/resume/experience": "experience",
    "/resume/education": "education",
    "/resume/skills": "skills",
}


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------
def lambda_handler(event: dict, context) -> dict:
    """
    Main Lambda entry point called by API Gateway for every HTTP request.

    Args:
        event:   API Gateway proxy integration event dict.
        context: Lambda context object (unused but required by the signature).

    Returns:
        API Gateway-compatible HTTP response dict.
    """
    http_method = event.get("httpMethod", "")
    resource_path = event.get("resource", event.get("path", ""))

    logger.info("Received %s %s", http_method, resource_path)

    # Only GET requests are supported.
    if http_method != "GET":
        return res.method_not_allowed(http_method)

    # Dispatch to the appropriate handler based on the resource path.
    route_key = _ROUTES.get(resource_path)

    if route_key is None:
        return res.bad_request(f"Route '{resource_path}' does not exist.")

    try:
        _ensure_data_initialized()
        return _dispatch(route_key)
    except ClientError as exc:
        logger.error("DynamoDB ClientError on route '%s': %s", route_key, exc)
        return res.server_error("A database error occurred. Please try again later.")
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error on route '%s': %s", route_key, exc)
        return res.server_error("An unexpected error occurred.")


def _dispatch(route_key: str) -> dict:
    """
    Call the correct handler function for the resolved route key.

    Args:
        route_key: One of 'full', 'personal', 'experience', 'education', 'skills'.

    Returns:
        API Gateway-compatible HTTP response dict.
    """
    handlers = {
        "full": handle_full_resume,
        "personal": handle_personal,
        "experience": handle_experience,
        "education": handle_education,
        "skills": handle_skills,
    }
    return handlers[route_key]()


# ---------------------------------------------------------------------------
# Individual route handlers
# ---------------------------------------------------------------------------

def handle_personal() -> dict:
    """
    GET /resume/personal
    Returns the candidate's personal information and professional summary.
    """
    data = database.get_personal()

    if data is None:
        logger.warning("PERSONAL record not found in DynamoDB.")
        return res.not_found("Personal information")

    return res.success(data, "Personal information retrieved successfully.")


def handle_experience() -> dict:
    """
    GET /resume/experience
    Returns a list of work experience records ordered by sort key.
    """
    data = database.get_experience()

    if not data:
        logger.warning("No EXPERIENCE records found in DynamoDB.")
        return res.not_found("Work experience")

    return res.success(data, "Work experience retrieved successfully.")


def handle_education() -> dict:
    """
    GET /resume/education
    Returns a list of education records.
    """
    data = database.get_education()

    if not data:
        logger.warning("No EDUCATION records found in DynamoDB.")
        return res.not_found("Education information")

    return res.success(data, "Education information retrieved successfully.")


def handle_skills() -> dict:
    """
    GET /resume/skills
    Returns categorised technical skills.
    """
    data = database.get_skills()

    if data is None:
        logger.warning("SKILLS record not found in DynamoDB.")
        return res.not_found("Skills information")

    return res.success(data, "Skills retrieved successfully.")


def handle_full_resume() -> dict:
    """
    GET /resume
    Returns the complete resume with all five sections assembled.
    """
    data = database.get_full_resume()

    # Treat the resume as missing only if every section is empty / None.
    all_empty = (
        data.get("personal") is None
        and not data.get("experience")
        and not data.get("education")
        and data.get("skills") is None
    )

    if all_empty:
        logger.warning("Full resume query returned no data.")
        return res.not_found("Resume")

    return res.success(data, "Full resume retrieved successfully.")
