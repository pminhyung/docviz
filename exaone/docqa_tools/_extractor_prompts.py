"""Goal-oriented extractor prompt (verbatim from doc_agent_v2).

Source: doc_agent_v2/config/training_prompts.py
    - EXTRACTOR_DOC_PROMPT  (internal documents — used by ReadFullDocument)

The web counterpart (EXTRACTOR_PROMPT) is intentionally not included
here: web pages are handled by the built-in web_extract tool which uses
Hermes' own (goal-agnostic) summarization policy.

Kept byte-for-byte so the LLM behavior on internal documents matches
the original SFT trace that doc_agent_v2 produced.
"""


EXTRACTOR_DOC_PROMPT = """Please process the following Internal Document contents and user goal to extract relevant information:

## **Internal Document Contents**
{webpage_content}

## **User Goal**
{goal}

## **Task Guidelines**
1. **Content Scanning for Rational**: Locate the **specific sections/data** directly related to the user's goal within the document content
2. **Key Extraction for Evidence**: Identify and extract the **most relevant information** from the content, you never miss any important information, output the **full original context** of the content as far as possible, it can be more than three paragraphs.
3. **Summary Output for Summary**: Organize into a concise paragraph with logical flow, prioritizing clarity and judge the contribution of the information to the goal.
4. please extract and cite the documents containing relevant information by referring in the form of [index] (e.g., King Sejong invented Hangul [1][2][4]).
   You should include citations generously -- attach references to all sentences or claims that are supported by or derived from the retrieved sources whenever possible, not just the final or main statements.
   The goal is to maximize citation density for transparency and traceability of the information used.

**Final Output Format using JSON format has "rational", "evidence", "summary" fields**
Strictly Follow this Output format:

{{
  "rational": "**specific sections/data** directly related to the user's goal within the provided content",
  "evidence": "*most relevant information** from the provided content",
  "summary": "summary for relevant information"
}}
"""
