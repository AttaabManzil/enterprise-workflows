import os
import requests
from dotenv import load_dotenv

LINEAR_API_URL = os.getenv("LINEAR_API_KEY")


class LinearAPIError(Exception):
    """Raised when Linear API returns an error."""


def create_issue(title: str, description: str):
    """
    Creates a Linear issue and returns issue metadata.
    """

    load_dotenv()

    api_key = os.getenv("LINEAR_API_KEY")
    team_id = os.getenv("LINEAR_TEAM_ID")

    if not api_key:
        raise RuntimeError("LINEAR_API_KEY is not set")

    if not team_id:
        raise RuntimeError("LINEAR_TEAM_ID is not set")

    query = """
    mutation CreateIssue($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        issue {
          id
          identifier
          url
        }
      }
    }
    """

    variables = {
        "input": {
            "teamId": team_id,
            "title": title,
            "description": description,
        }
    }

    headers = {
        "Authorization": api_key,  # ✅ NO "Bearer"
        "Content-Type": "application/json",
    }

    response = requests.post(
        LINEAR_API_URL,
        headers=headers,
        json={
            "query": query,
            "variables": variables,
        },
        timeout=10,
    )

    if response.status_code != 200:
        raise LinearAPIError(
            f"Linear API HTTP {response.status_code}\n{response.text}"
        )

    data = response.json()

    if "errors" in data:
        raise LinearAPIError(f"Linear API error: {data['errors']}")

    return data["data"]["issueCreate"]["issue"]
