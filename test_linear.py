from dotenv import load_dotenv
load_dotenv()

from linear_client import create_issue

issue = create_issue(
    title="🔥 Linear API Smoke Test",
    description="If you see this issue, Linear is working."
)

print("Created issue:", issue["identifier"], issue["url"])
