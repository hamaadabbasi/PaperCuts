# extraction.py
# Sends a paper's text to the LLM and gets back structured findings as JSON
# (task, datasets, methods, metrics, results). This is Path B in the architecture.

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

# Reads OPENAI_API_KEY from the .env file (must run before creating the client)
load_dotenv()

client = OpenAI()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# The extraction prompt. We will revise it based on testing.
EXTRACTION_PROMPT = """You are helping compare research papers, so the details need to be accurate. Read the paper text below and pull out the information listed here. Return only valid JSON.

The text has page markers like [Page 3]. Use them for the page numbers.

What to extract:
- title: the title of the paper.
- research_task: the problem the paper is trying to solve.
- datasets: every dataset the paper uses.
- methods: the models or approaches the paper tests or proposes.
- evaluation_metrics: the metrics used to measure performance.
- results: every score the paper reports, including numbers from tables. For each one, give the value, the metric, how that metric is defined (for example macro- or micro-averaged), the dataset, the method, and the evaluation settings (for example the train/test split).

For every item, also give the section it appears in, the page number, and the exact passage it came from. Copy the passage word for word from the text, do not reword it.

If the paper does not say something, write "not reported". Do not guess, and do not fill in anything from your own background knowledge.

Extra rules:
- Make one results entry per number. If one sentence reports three values, make three entries.
- The passage must contain the value it is attached to.
- Fill in the dataset, method, and evaluation settings only when the paper clearly states them for that result. Otherwise write "not reported". Do not assume.
- For the section, use the heading the passage actually appears under, such as Results or Methods.
- List each dataset and method once, and make sure its passage mentions it by name.

Return the JSON in this format:
{
  "title": "",
  "research_task": {"value": "", "section": "", "page": 0, "passage": ""},
  "datasets": [{"name": "", "section": "", "page": 0, "passage": ""}],
  "methods": [{"name": "", "section": "", "page": 0, "passage": ""}],
  "evaluation_metrics": [{"name": "", "section": "", "page": 0, "passage": ""}],
  "results": [
    {
      "value": "",
      "metric": "",
      "metric_definition": "",
      "dataset": "",
      "method": "",
      "evaluation_settings": "",
      "section": "",
      "page": 0,
      "passage": ""
    }
  ]
}"""


def extract_findings(pages):
    # Put a [Page N] marker before each page so the LLM can report page numbers
    paper_text = ""
    for p in pages:
        paper_text += f"\n[Page {p['page']}]\n{p['text']}\n"
    
    response = client.chat.completions.create(
        model = MODEL,
        
        # JSON mode: the model must return valid JSON
        response_format = {"type": "json_object"},
        
        messages = [
            {"role": "user", "content": EXTRACTION_PROMPT + "\n\nPAPER TEXT:\n" + paper_text}
        ],
    )
    raw = response.choices[0].message.content

    # Turn the text into a Python dictionary
    return json.loads(raw)