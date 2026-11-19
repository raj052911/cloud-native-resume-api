"""
database.py
-----------
Handles all DynamoDB interactions for the Serverless Resume API.

Responsibilities:
  - Provide a singleton DynamoDB resource / table reference.
  - Load resume data from the JSON file into DynamoDB (idempotent).
  - Retrieve individual resume sections and the full resume via Query.
"""

import json
import logging
import os
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "ResumeData")
RESUME_PK = "RESUME"

# Path to the seed data file — works both locally and inside the Lambda zip.
_DATA_DIR = Path(__file__).parent.parent / "data"
RESUME_JSON_PATH = _DATA_DIR / "resume.json"


# ---------------------------------------------------------------------------
# DynamoDB resource (lazy singleton)
# ---------------------------------------------------------------------------
_dynamodb = None
_table = None


def _get_table():
    """Return the DynamoDB Table resource, creating it once per Lambda cold start."""
    global _dynamodb, _table
    if _table is None:
        region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        _dynamodb = boto3.resource("dynamodb", region_name=region)
        _table = _dynamodb.Table(TABLE_NAME)
    return _table


# ---------------------------------------------------------------------------
# Idempotent data initialisation
# ---------------------------------------------------------------------------
def _is_data_loaded(table) -> bool:
    """
    Check if the PERSONAL record already exists.
    Uses a lightweight GetItem instead of a full Scan to avoid extra cost.
    """
    response = table.get_item(
        Key={"PK": RESUME_PK, "SK": "PERSONAL"}
    )
    return "Item" in response


def _load_resume_json() -> dict:
    """Read and parse the resume JSON seed file."""
    with open(RESUME_JSON_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def initialise_data() -> None:
    """
    Load resume JSON into DynamoDB if the data is not already present.
    This function is idempotent — repeated calls are safe and produce no
    duplicate writes after the first successful load.
    """
    table = _get_table()

    if _is_data_loaded(table):
        logger.info("Resume data already present in DynamoDB. Skipping initialisation.")
        return

    logger.info("Initialising DynamoDB with resume data from %s", RESUME_JSON_PATH)
    resume = _load_resume_json()

    items_to_write = _build_dynamodb_items(resume)

    # Batch write all items in a single API call (max 25 per batch).
    with table.batch_writer() as batch:
        for item in items_to_write:
            batch.put_item(Item=item)

    logger.info("Successfully wrote %d resume records to DynamoDB.", len(items_to_write))


def _build_dynamodb_items(resume: dict) -> list:
    """
    Convert the resume JSON structure into a flat list of DynamoDB items,
    each with a composite key (PK=RESUME, SK=<section>).
    """
    items = []

    # PERSONAL
    items.append({
        "PK": RESUME_PK,
        "SK": "PERSONAL",
        **resume["personal"]
    })

    # EXPERIENCE — one item per role, SK = EXPERIENCE_001, EXPERIENCE_002, ...
    for entry in resume.get("experience", []):
        entry_copy = {k: v for k, v in entry.items() if k != "sk"}
        sk = entry.get("sk", "EXPERIENCE_001")
        items.append({
            "PK": RESUME_PK,
            "SK": sk,
            **entry_copy
        })

    # EDUCATION — one item per qualification
    for entry in resume.get("education", []):
        entry_copy = {k: v for k, v in entry.items() if k != "sk"}
        sk = entry.get("sk", "EDUCATION_001")
        items.append({
            "PK": RESUME_PK,
            "SK": sk,
            **entry_copy
        })

    # SKILLS — single item
    items.append({
        "PK": RESUME_PK,
        "SK": "SKILLS",
        **resume["skills"]
    })

    return items


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------
def get_personal() -> dict | None:
    """Retrieve the PERSONAL record."""
    return _get_item("PERSONAL")


def get_skills() -> dict | None:
    """Retrieve the SKILLS record."""
    return _get_item("SKILLS")


def get_experience() -> list:
    """
    Retrieve all EXPERIENCE records, sorted by SK (chronological by SK suffix).
    Uses a Query with a begins_with condition to avoid a Scan.
    """
    return _query_by_sk_prefix("EXPERIENCE")


def get_education() -> list:
    """
    Retrieve all EDUCATION records.
    Uses a Query with a begins_with condition to avoid a Scan.
    """
    return _query_by_sk_prefix("EDUCATION")


def get_full_resume() -> dict:
    """
    Retrieve all resume records with a single Query on PK=RESUME.
    Returns a structured dictionary with all five sections.
    """
    table = _get_table()

    try:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(RESUME_PK)
        )
    except ClientError as exc:
        logger.error("DynamoDB Query failed: %s", exc.response["Error"]["Message"])
        raise

    items = response.get("Items", [])
    return _assemble_full_resume(items)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _get_item(sk: str) -> dict | None:
    """Fetch a single item by its sort key and strip the DynamoDB key fields."""
    table = _get_table()

    try:
        response = table.get_item(Key={"PK": RESUME_PK, "SK": sk})
    except ClientError as exc:
        logger.error(
            "DynamoDB GetItem failed for SK=%s: %s",
            sk,
            exc.response["Error"]["Message"],
        )
        raise

    item = response.get("Item")
    if item is None:
        return None

    return _strip_keys(item)


def _query_by_sk_prefix(prefix: str) -> list:
    """Return all items whose SK begins with *prefix*, with key fields removed."""
    table = _get_table()

    try:
        response = table.query(
            KeyConditionExpression=(
                Key("PK").eq(RESUME_PK) & Key("SK").begins_with(prefix)
            )
        )
    except ClientError as exc:
        logger.error(
            "DynamoDB Query failed for prefix=%s: %s",
            prefix,
            exc.response["Error"]["Message"],
        )
        raise

    return [_strip_keys(item) for item in response.get("Items", [])]


def _strip_keys(item: dict) -> dict:
    """Remove DynamoDB primary key attributes from a returned item."""
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def _assemble_full_resume(items: list) -> dict:
    """
    Given a flat list of all DynamoDB items for PK=RESUME,
    organise them back into the five-section resume structure.
    """
    resume = {
        "personal": None,
        "experience": [],
        "education": [],
        "skills": None,
    }

    for item in items:
        sk = item.get("SK", "")
        clean = _strip_keys(item)

        if sk == "PERSONAL":
            resume["personal"] = clean
        elif sk == "SKILLS":
            resume["skills"] = clean
        elif sk.startswith("EXPERIENCE"):
            resume["experience"].append(clean)
        elif sk.startswith("EDUCATION"):
            resume["education"].append(clean)

    # Sort collections by their original SK to preserve insertion order.
    resume["experience"].sort(key=lambda x: x.get("company", ""))
    resume["education"].sort(key=lambda x: x.get("start_year", ""))

    return resume
