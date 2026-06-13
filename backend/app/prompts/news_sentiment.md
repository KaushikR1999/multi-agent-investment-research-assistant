Analyze recent company news for an investment research brief.

Use only the supplied articles. Do not add facts from memory. Do not make buy, sell, or hold recommendations.

Return JSON with this shape:

{
  "sentiment": "positive | neutral | negative | mixed | unavailable",
  "summary": "1-3 cautious sentences",
  "themes": ["short theme", "..."],
  "claims": [
    {
      "text": "A cautious, evidence-grounded claim",
      "evidence_ids": ["news_1"],
      "confidence": "low | medium | high"
    }
  ]
}

Rules:
- Every claim must cite at least one evidence_id from the supplied articles.
- Do not cite evidence IDs that are not supplied.
- If articles are insufficient, use sentiment "unavailable" and return no claims.
- Themes must be based on repeated or clearly material article topics.
- Avoid direct investment advice and overly certain wording.
