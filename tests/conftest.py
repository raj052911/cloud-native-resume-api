# tests/conftest.py
"""
Shared pytest configuration for the Serverless Resume API test suite.

Sets dummy AWS environment variables and adds src/ to sys.path so tests
can run completely offline without an active AWS account or credentials.
"""

import os
import sys

# Standard dummy AWS credentials for offline testing (prevents NoRegionError/NoCredentialsError)
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["DYNAMODB_TABLE_NAME"] = "ResumeData"

# Insert src/ at the front of the module search path once for the whole session.
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(SRC_DIR))
