import json
import boto3
import ytscraper

print("Loading function")

s3 = boto3.client("s3")


# The handler expects these event keys to be set in the triggering
# event (api_keys, query, max_pages)
# Optional event keys: location, location_radius, max_results, disable_https
def lambda_handler(event, context):
    payload = event["body"]
    print(payload)
    if "api_keys" not in payload:
        raise ValueError("api_keys not in payload")
    if "query" not in payload:
        raise ValueError("query not in payload")
    if "max_pages" not in payload:
        raise ValueError("max_pages not in payload")

    if "max_results" not in payload:
        payload["max_results"] = 10
    if "location" not in payload:
        payload["location"] = ""
    if "location_radius" not in payload:
        payload["location_radius"] = ""
    if "disable_https" not in payload:
        payload["disable_https"] = False

    print("Scraping youtube with payload: " + json.dumps(payload, indent=2))
    ytscraper.scrape_yt(
        payload["api_keys"],
        payload["max_pages"],
        payload["max_results"],
        payload["location"],
        payload["location_radius"],
        payload["query"],
        payload["disable_https"],
    )


if __name__ == "__main__":
    lambda_handler(
        {
            "body": {
                "api_keys": "YOUR_API_KEY",
                "query": "official music video",
                "max_pages": 1,
                "location": "tokyo",
            }
        },
        None,
    )
