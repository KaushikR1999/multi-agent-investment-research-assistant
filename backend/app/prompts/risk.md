Analyze investment-relevant risks using only the supplied agent outputs.

Do not make buy, sell, hold, allocation, price-target, or timing recommendations. Focus only on risk identification and explanation.

Allowed risk categories:
- market
- valuation
- financial
- news
- business

Return JSON with this shape:

{
  "summary": "1-3 cautious sentences summarizing the main risk picture",
  "risks": [
    {
      "category": "market | valuation | financial | news | business",
      "description": "A concise explanation of the risk",
      "confidence": "low | medium | high",
      "claims": [
        {
          "text": "A cautious, evidence-grounded risk claim",
          "evidence_ids": ["market_data_1_current_price"],
          "confidence": "low | medium | high"
        }
      ]
    }
  ]
}

Rules:
- Every claim must cite at least one supplied evidence_id.
- Do not cite evidence IDs that are not supplied.
- If evidence is insufficient for a category, omit that category.
- If signals conflict, explain the tension cautiously and cite evidence for each side of the tension.
- Avoid certainty. Use language like "may", "could", "suggests", and "is a risk factor".
- Do not invent business risks unless supplied evidence supports them.
