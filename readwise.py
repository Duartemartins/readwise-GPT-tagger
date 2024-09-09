import requests
from docx import Document
import os
import csv
from openai import OpenAI
import time

# Instantiate OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Initialize a new Word document
document = Document()

# Your Readwise API token from environment variables
api_token = os.environ.get("READWISE")

# Set up the headers with your Readwise API token
headers = {"Authorization": f"Token {api_token}"}

# CSV file to save the data
csv_file = "Highlights_with_Tags.csv"
success_log_file = "updated_highlights_log.txt"

# Maximum number of retries
MAX_RETRIES = 5

def generate_tags_from_openai(highlight_text):
    """
    Use OpenAI to generate up to 3 tags for a given highlight using the chat completion model.
    """
    try:
        prompt = f'Generate up to 3 high-level relevant tags for the following highlight: "{highlight_text}". They should be separated by commas and not have hashes. Use British English. They should be restricted to: Economics, Technology, Startups, Science, Physics, Biology, Chemistry, Entrepreneurship, Liberalism, Philosophy, Environment, Religion, Politics, History, Psychology, Sociology, Statistics, United Kingdom, Quotes, Film, Music, Marketing, Politics, Personal Finance, Design, CBT, Lifetips, Europe, United States, Critical Thinking, IdPol, Health, Finance, Agriculture, Productivity, and Literature.'
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=50,
            temperature=0.5,
        )
        # Extract the tags from the response content
        tags_text = response.choices[0].message.content.strip()
        tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
        return tags
    except Exception as e:
        print(f"Error generating tags: {e}")
        return []


def normalize_text(text):
    """
    Normalizes the text by stripping extra spaces, converting to lowercase, 
    and removing special characters that might affect matching.
    """
    return text.strip().lower()


def find_matching_highlight(book, highlight_text):
    """
    Finds a matching highlight in the book based on partial text matching.
    """
    normalized_highlight_text = normalize_text(highlight_text)
    for highlight in book["highlights"]:
        normalized_book_highlight = normalize_text(highlight["text"])
        
        # Perform partial matching (first 100 characters)
        if normalized_highlight_text[:100] in normalized_book_highlight:
            return highlight

    # No match found
    return None


def load_updated_highlight_ids():
    """
    Load the IDs of highlights that have already been successfully updated from the log file.
    """
    if os.path.exists(success_log_file):
        with open(success_log_file, "r") as f:
            return {line.strip() for line in f.readlines()}
    return set()


def log_successful_update(highlight_id):
    """
    Log a successfully updated highlight ID to the file.
    """
    with open(success_log_file, "a") as f:
        f.write(f"{highlight_id}\n")


def update_highlight_tags(highlight_id, tags):
    """
    Updates the tags for a specific highlight using Readwise API with exponential backoff.
    """
    url = f"https://readwise.io/api/v2/highlights/{highlight_id}/"
    payload = {"tags": [{"name": tag} for tag in tags]}
    retries = 0
    backoff = 2  # Start with 2 seconds

    while retries < MAX_RETRIES:
        try:
            # Send a PATCH request to update the highlight
            response = requests.patch(url, headers=headers, json=payload)

            if response.status_code == 200:
                print(f"Successfully updated highlight {highlight_id} with tags: {tags}")
                log_successful_update(highlight_id)  # Log the successful update
                return True
            elif response.status_code == 429:
                # Handle rate limiting
                print(f"Rate limited. Waiting for {backoff} seconds before retrying.")
                time.sleep(backoff)
                backoff *= 2  # Double the backoff time
                retries += 1
            else:
                # Handle other errors
                print(f"Failed to update highlight {highlight_id}. Status code: {response.status_code}")
                print(response.text)
                return False
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return False

    print(f"Max retries exceeded for highlight {highlight_id}.")
    return False


def fetch_highlights():
    """
    Fetch highlights from Readwise and return them, with pagination support.
    """
    url = "https://readwise.io/api/v2/export/"
    next_page_cursor = None
    all_highlights = []

    while True:
        params = {"pageCursor": next_page_cursor} if next_page_cursor else {}
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            data_export = response.json()
            all_highlights.extend(data_export.get("results", []))
            next_page_cursor = data_export.get("nextPageCursor")
            if not next_page_cursor:
                break  # No more pages
        else:
            print(f"Failed to fetch export data. Status code: {response.status_code}")
            print(response.text)
            break

    return all_highlights


def update_tags_from_csv():
    """
    Reads the CSV file and updates the corresponding highlights with new tags.
    """
    highlights_data = fetch_highlights()

    # Load the IDs of already updated highlights from the log file
    updated_highlight_ids = load_updated_highlight_ids()

    with open(csv_file, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            title = row["Book Title"]
            highlight_text = row["Highlight"]
            tags = row["Tags"].split(", ")

            matching_highlight = None
            for book in highlights_data:
                if book["title"] == title:
                    matching_highlight = find_matching_highlight(book, highlight_text)
                    if matching_highlight:
                        break

            if matching_highlight:
                highlight_id = matching_highlight["id"]

                # Skip the highlight if it has already been updated
                if str(highlight_id) in updated_highlight_ids:
                    print(f"Skipping already updated highlight {highlight_id}.")
                    continue

                # Update the highlight's tags
                update_highlight_tags(highlight_id, tags)
            else:
                # Log the text comparison for debugging
                print(f"No matching highlight found for: {highlight_text}")

                # Print comparison logs
                print(f"Tried to match CSV highlight: {highlight_text}")
                for book in highlights_data:
                    for highlight in book["highlights"]:
                        print(f"Compared with Readwise highlight: {highlight['text'][:100]}")


# Start the process
update_tags_from_csv()
