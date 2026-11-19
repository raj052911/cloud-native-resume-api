# tests/test_database.py
"""
Unit tests for src/database.py

Tests cover:
  1.  initialise_data() when data is already present  → skips batch write
  2.  initialise_data() when data is absent           → writes seed items
  3.  get_personal()   - item found
  4.  get_personal()   - item missing   → returns None
  5.  get_skills()     - item found / missing
  6.  get_experience() - records found / empty
  7.  get_education()  - records found / stripped keys
  8.  get_full_resume()- assembles all four sections
  9.  DynamoDB ClientError propagation across all public functions

No active AWS account is required. All boto3 calls are mocked.
Run with:  pytest tests/test_database.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch
import pytest

# conftest.py adds src/ to sys.path, but be explicit in case this file is run alone.
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import database
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_error(code: str = "InternalServerError", msg: str = "Simulated error") -> ClientError:
    """Build a botocore ClientError with a realistic structure."""
    return ClientError({"Error": {"Code": code, "Message": msg}}, "Operation")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_table_singleton():
    """
    Reset the lazy DynamoDB singleton before and after every test.
    Forces _get_table() to call boto3.resource() on the next invocation,
    ensuring each test receives a fresh mock table.
    """
    database._table = None
    database._dynamodb = None
    yield
    database._table = None
    database._dynamodb = None


@pytest.fixture
def mock_table():
    """
    Patch database.boto3 so that boto3.resource("dynamodb").Table(...)
    returns a controllable MagicMock table object.
    """
    table = MagicMock()
    with patch("database.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = table
        database._table = table
        database._dynamodb = mock_boto3.resource.return_value
        yield table


# ---------------------------------------------------------------------------
# 1 & 2.  initialise_data()
# ---------------------------------------------------------------------------

class TestInitialiseDataAlreadyLoaded:
    """Data already in DynamoDB → initialise_data must be a no-op."""

    def test_skips_batch_write_when_personal_record_exists(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {"PK": "RESUME", "SK": "PERSONAL", "full_name": "Jane"}
        }
        database.initialise_data()
        mock_table.batch_writer.assert_not_called()

    def test_checks_personal_key_as_sentinel(self, mock_table):
        """The function uses a GetItem on PERSONAL as the existence check."""
        mock_table.get_item.return_value = {
            "Item": {"PK": "RESUME", "SK": "PERSONAL"}
        }
        database.initialise_data()
        mock_table.get_item.assert_called_once_with(
            Key={"PK": "RESUME", "SK": "PERSONAL"}
        )


class TestInitialiseDataNotLoaded:
    """No data in DynamoDB → initialise_data must write all seed records."""

    def _setup_batch_writer(self, mock_table):
        """Wire up the batch_writer context manager and collect put_item calls."""
        put_items = []
        ctx = MagicMock()
        ctx.put_item.side_effect = lambda Item: put_items.append(Item)
        mock_table.batch_writer.return_value.__enter__.return_value = ctx
        mock_table.batch_writer.return_value.__exit__.return_value = False
        return put_items

    def test_calls_batch_writer_when_data_absent(self, mock_table):
        mock_table.get_item.return_value = {}
        self._setup_batch_writer(mock_table)
        database.initialise_data()
        mock_table.batch_writer.assert_called_once()

    def test_writes_exactly_five_items(self, mock_table):
        """1 PERSONAL + 2 EXPERIENCE + 1 EDUCATION + 1 SKILLS = 5."""
        mock_table.get_item.return_value = {}
        put_items = self._setup_batch_writer(mock_table)
        database.initialise_data()
        assert len(put_items) == 5

    def test_all_items_have_pk_resume(self, mock_table):
        mock_table.get_item.return_value = {}
        put_items = self._setup_batch_writer(mock_table)
        database.initialise_data()
        for item in put_items:
            assert item["PK"] == "RESUME", f"Item has unexpected PK: {item['PK']}"

    def test_expected_sort_keys_are_present(self, mock_table):
        """Verify the DynamoDB design spec sort keys are written."""
        mock_table.get_item.return_value = {}
        put_items = self._setup_batch_writer(mock_table)
        database.initialise_data()
        sort_keys = {item["SK"] for item in put_items}
        assert "PERSONAL" in sort_keys
        assert "SKILLS" in sort_keys
        assert any(sk.startswith("EXPERIENCE") for sk in sort_keys)
        assert any(sk.startswith("EDUCATION") for sk in sort_keys)

    def test_is_idempotent_second_call_skips_write(self, mock_table):
        """
        After the first successful write, a second call must detect data
        is present and skip the batch write entirely.
        """
        # First call: data absent → write
        mock_table.get_item.return_value = {}
        self._setup_batch_writer(mock_table)
        database.initialise_data()

        # Second call: data now present → skip
        reset_table_singleton  # re-runs autouse fixture implicitly via scope
        database._table = None
        database._dynamodb = None
        mock_table.get_item.return_value = {
            "Item": {"PK": "RESUME", "SK": "PERSONAL"}
        }
        mock_table.batch_writer.reset_mock()
        database.initialise_data()
        mock_table.batch_writer.assert_not_called()


# ---------------------------------------------------------------------------
# 3 & 4.  get_personal()
# ---------------------------------------------------------------------------

class TestGetPersonal:

    def test_returns_dict_when_item_found(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {
                "PK": "RESUME", "SK": "PERSONAL",
                "full_name": "Jane Doe", "email": "jane@test.com",
            }
        }
        result = database.get_personal()
        assert result is not None
        assert isinstance(result, dict)

    def test_strips_pk_and_sk_from_returned_item(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {"PK": "RESUME", "SK": "PERSONAL", "full_name": "Jane Doe"}
        }
        result = database.get_personal()
        assert "PK" not in result
        assert "SK" not in result

    def test_returns_correct_attribute_values(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {"PK": "RESUME", "SK": "PERSONAL", "full_name": "Jane Doe",
                     "email": "jane@test.com", "github": "https://github.com/jane"}
        }
        result = database.get_personal()
        assert result["full_name"] == "Jane Doe"
        assert result["email"] == "jane@test.com"
        assert result["github"] == "https://github.com/jane"

    def test_returns_none_when_item_missing(self, mock_table):
        mock_table.get_item.return_value = {}  # No "Item" key
        result = database.get_personal()
        assert result is None

    def test_raises_client_error_on_dynamodb_failure(self, mock_table):
        mock_table.get_item.side_effect = _client_error("ResourceNotFoundException")
        with pytest.raises(ClientError):
            database.get_personal()


# ---------------------------------------------------------------------------
# 5.  get_skills()
# ---------------------------------------------------------------------------

class TestGetSkills:

    def test_returns_skills_dict_when_found(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {
                "PK": "RESUME", "SK": "SKILLS",
                "programming_languages": ["Python"],
                "cloud_technologies": ["AWS Lambda"],
                "databases": ["DynamoDB"],
                "development_tools": ["Git"],
                "other_skills": ["REST APIs"],
            }
        }
        result = database.get_skills()
        assert result is not None
        assert "programming_languages" in result
        assert "cloud_technologies" in result

    def test_strips_pk_and_sk_from_skills(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {"PK": "RESUME", "SK": "SKILLS", "programming_languages": ["Python"]}
        }
        result = database.get_skills()
        assert "PK" not in result
        assert "SK" not in result

    def test_returns_none_when_skills_missing(self, mock_table):
        mock_table.get_item.return_value = {}
        result = database.get_skills()
        assert result is None

    def test_raises_client_error_on_failure(self, mock_table):
        mock_table.get_item.side_effect = _client_error()
        with pytest.raises(ClientError):
            database.get_skills()


# ---------------------------------------------------------------------------
# 6.  get_experience()
# ---------------------------------------------------------------------------

class TestGetExperience:

    def test_returns_list_of_experience_records(self, mock_table):
        mock_table.query.return_value = {
            "Items": [
                {"PK": "RESUME", "SK": "EXPERIENCE_001", "company": "Corp A", "title": "Intern"},
                {"PK": "RESUME", "SK": "EXPERIENCE_002", "company": "Corp B", "title": "Engineer"},
            ]
        }
        result = database.get_experience()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_strips_pk_and_sk_from_each_item(self, mock_table):
        mock_table.query.return_value = {
            "Items": [{"PK": "RESUME", "SK": "EXPERIENCE_001", "company": "Corp A"}]
        }
        result = database.get_experience()
        assert "PK" not in result[0]
        assert "SK" not in result[0]
        assert result[0]["company"] == "Corp A"

    def test_returns_empty_list_when_no_records(self, mock_table):
        mock_table.query.return_value = {"Items": []}
        result = database.get_experience()
        assert result == []

    def test_raises_client_error_on_query_failure(self, mock_table):
        mock_table.query.side_effect = _client_error("ProvisionedThroughputExceededException")
        with pytest.raises(ClientError):
            database.get_experience()


# ---------------------------------------------------------------------------
# 7.  get_education()
# ---------------------------------------------------------------------------

class TestGetEducation:

    def test_returns_list_of_education_records(self, mock_table):
        mock_table.query.return_value = {
            "Items": [
                {
                    "PK": "RESUME", "SK": "EDUCATION_001",
                    "institution": "Uni X", "degree": "B.E.",
                    "field_of_study": "CSE", "start_year": "2022",
                    "graduation_year": "2026",
                }
            ]
        }
        result = database.get_education()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["institution"] == "Uni X"

    def test_strips_pk_and_sk_from_education_items(self, mock_table):
        mock_table.query.return_value = {
            "Items": [{"PK": "RESUME", "SK": "EDUCATION_001", "institution": "Uni X"}]
        }
        result = database.get_education()
        assert "PK" not in result[0]
        assert "SK" not in result[0]

    def test_returns_empty_list_when_no_records(self, mock_table):
        mock_table.query.return_value = {"Items": []}
        result = database.get_education()
        assert result == []

    def test_raises_client_error_on_query_failure(self, mock_table):
        mock_table.query.side_effect = _client_error()
        with pytest.raises(ClientError):
            database.get_education()


# ---------------------------------------------------------------------------
# 8.  get_full_resume()
# ---------------------------------------------------------------------------

class TestGetFullResume:

    _ALL_ITEMS = [
        {"PK": "RESUME", "SK": "PERSONAL",       "full_name": "Jane Doe"},
        {"PK": "RESUME", "SK": "EXPERIENCE_001",  "company": "Corp A"},
        {"PK": "RESUME", "SK": "EXPERIENCE_002",  "company": "Corp B"},
        {"PK": "RESUME", "SK": "EDUCATION_001",   "institution": "Uni X"},
        {"PK": "RESUME", "SK": "SKILLS",          "programming_languages": ["Python"]},
    ]

    def test_returns_dict_with_four_sections(self, mock_table):
        mock_table.query.return_value = {"Items": self._ALL_ITEMS}
        result = database.get_full_resume()
        assert "personal" in result
        assert "experience" in result
        assert "education" in result
        assert "skills" in result

    def test_personal_section_is_dict_with_correct_data(self, mock_table):
        mock_table.query.return_value = {"Items": self._ALL_ITEMS}
        result = database.get_full_resume()
        assert isinstance(result["personal"], dict)
        assert result["personal"]["full_name"] == "Jane Doe"

    def test_experience_section_is_list_with_two_entries(self, mock_table):
        mock_table.query.return_value = {"Items": self._ALL_ITEMS}
        result = database.get_full_resume()
        assert isinstance(result["experience"], list)
        assert len(result["experience"]) == 2

    def test_education_section_is_list_with_one_entry(self, mock_table):
        mock_table.query.return_value = {"Items": self._ALL_ITEMS}
        result = database.get_full_resume()
        assert isinstance(result["education"], list)
        assert len(result["education"]) == 1

    def test_skills_section_is_dict(self, mock_table):
        mock_table.query.return_value = {"Items": self._ALL_ITEMS}
        result = database.get_full_resume()
        assert isinstance(result["skills"], dict)

    def test_pk_and_sk_stripped_from_all_sections(self, mock_table):
        mock_table.query.return_value = {"Items": self._ALL_ITEMS}
        result = database.get_full_resume()
        assert "PK" not in result["personal"]
        assert "SK" not in result["personal"]
        for exp in result["experience"]:
            assert "PK" not in exp
            assert "SK" not in exp
        for edu in result["education"]:
            assert "PK" not in edu
            assert "SK" not in edu
        assert "PK" not in result["skills"]
        assert "SK" not in result["skills"]

    def test_returns_empty_sections_on_empty_query(self, mock_table):
        mock_table.query.return_value = {"Items": []}
        result = database.get_full_resume()
        assert result["personal"] is None
        assert result["experience"] == []
        assert result["education"] == []
        assert result["skills"] is None

    def test_raises_client_error_on_query_failure(self, mock_table):
        mock_table.query.side_effect = _client_error("InternalServerError")
        with pytest.raises(ClientError):
            database.get_full_resume()


# ---------------------------------------------------------------------------
# 9.  ClientError propagation across all public functions
# ---------------------------------------------------------------------------

class TestClientErrorPropagation:
    """Every public database function must let ClientError bubble up to the caller."""

    def test_get_personal_propagates(self, mock_table):
        mock_table.get_item.side_effect = _client_error()
        with pytest.raises(ClientError):
            database.get_personal()

    def test_get_skills_propagates(self, mock_table):
        mock_table.get_item.side_effect = _client_error()
        with pytest.raises(ClientError):
            database.get_skills()

    def test_get_experience_propagates(self, mock_table):
        mock_table.query.side_effect = _client_error()
        with pytest.raises(ClientError):
            database.get_experience()

    def test_get_education_propagates(self, mock_table):
        mock_table.query.side_effect = _client_error()
        with pytest.raises(ClientError):
            database.get_education()

    def test_get_full_resume_propagates(self, mock_table):
        mock_table.query.side_effect = _client_error()
        with pytest.raises(ClientError):
            database.get_full_resume()
