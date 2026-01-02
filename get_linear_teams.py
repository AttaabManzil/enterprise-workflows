import requests
import os

LINEAR_API_KEY = os.getenv("LINEAR_API_KEY")

query = """
{
  teams {
    nodes {
      id
      name
      key
    }
  }
}
"""

response = requests.post(
    'https://api.linear.app/graphql',
    json={'query': query},
    headers={
        'Authorization': LINEAR_API_KEY,
        'Content-Type': 'application/json'
    }
)

result = response.json()

if 'data' in result:
    print("\nYour Linear Teams:")
    print("-" * 50)
    for team in result['data']['teams']['nodes']:
        print(f"Team: {team['name']}")
        print(f"  ID:  {team['id']}")
        print(f"  Key: {team['key']}")
        print()
else:
    print("Error:", result)