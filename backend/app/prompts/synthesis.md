Write a draft investment research brief using only the supplied upstream agent outputs.

This is not financial advice. Do not make buy, sell, hold, allocation, price-target, or timing recommendations.

Required sections:
- Company / ticker identified
- Market data summary
- Recent news sentiment
- Fundamentals summary
- Key risks
- Bull case
- Bear case
- Balanced view

Return JSON with this shape:

{
  "sections": [
    {
      "heading": "Company / ticker identified",
      "summary": "A concise section summary",
      "claims": [
        {
          "text": "A cautious, evidence-grounded claim",
          "evidence_ids": ["company_resolution_1"],
          "confidence": "low | medium | high"
        }
      ]
    }
  ]
}

Rules:
- Include exactly the required section headings.
- Every claim must cite at least one supplied evidence_id.
- Do not cite evidence IDs that are not supplied.
- Use cautious language and preserve uncertainty.
- Represent conflicting signals as tensions, not recommendations.
- If evidence is limited for a section, say so in the summary and include fewer claims.
- Do not introduce facts from memory.
