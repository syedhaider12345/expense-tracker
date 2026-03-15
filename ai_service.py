from groq import Groq
from config import GROQ_API_KEY


def generate_spending_insights(
    user_name: str,
    month: str,
    category_breakdown: dict,
    monthly_total: float,
    budget_statuses: list
) -> dict:
    """
    Call the Groq API (free) to generate natural-language spending insights.
    Returns a dict with 'summary', 'tips', and 'biggest_category' keys.
    Falls back to rule-based insights if no API key is set.
    """
    if not GROQ_API_KEY:
        return _fallback_insights(category_breakdown, monthly_total, month)

    # Build a clear, data-rich prompt
    breakdown_text = "\n".join(
        f"  - {cat}: ₹{amt:,.0f}" for cat, amt in category_breakdown.items()
    )

    budget_text = ""
    if budget_statuses:
        budget_lines = "\n".join(
            f"  - {b['category']}: spent ₹{b['spent']:,.0f} of ₹{b['limit']:,.0f} limit ({b['percent_used']:.0f}% used) — {b['status']}"
            for b in budget_statuses
        )
        budget_text = f"\nBudget tracking this month:\n{budget_lines}"

    prompt = f"""You are a friendly personal finance assistant. Analyze the following expense data for {user_name} for {month} and give practical, specific advice.

Total spent this month: ₹{monthly_total:,.0f}

Category breakdown:
{breakdown_text}
{budget_text}

Respond ONLY with a valid JSON object in this exact format (no markdown, no extra text):
{{
  "summary": "A 2-3 sentence plain-English summary of their spending this month. Be specific with numbers. Mention if they are over or under budget.",
  "tips": [
    "Specific actionable tip 1 based on their actual data",
    "Specific actionable tip 2 based on their actual data",
    "Specific actionable tip 3 based on their actual data"
  ],
  "biggest_category": "the single category name with highest spending"
}}"""

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=600,
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": "You are a personal finance assistant. Always respond with valid JSON only. No markdown, no explanation, just the JSON object."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        import json
        raw = response.choices[0].message.content.strip()

        # Strip any accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())

    except Exception as e:
        print(f"[AI] Error calling Groq API: {e}")
        return _fallback_insights(category_breakdown, monthly_total, month)


def _fallback_insights(category_breakdown: dict, monthly_total: float, month: str) -> dict:
    """Simple rule-based insights when no API key is configured."""
    if not category_breakdown:
        return {
            "summary": "No expenses recorded yet this month. Start adding expenses to see insights.",
            "tips": [
                "Add your first expense to get started.",
                "Set monthly budgets to track your spending.",
                "Check back after recording a few expenses."
            ],
            "biggest_category": "N/A"
        }

    biggest = max(category_breakdown, key=category_breakdown.get)
    biggest_amt = category_breakdown[biggest]
    biggest_pct = (biggest_amt / monthly_total * 100) if monthly_total else 0

    return {
        "summary": f"You spent ₹{monthly_total:,.0f} in {month} across {len(category_breakdown)} categories. {biggest} accounts for the most at ₹{biggest_amt:,.0f} ({biggest_pct:.0f}% of total spending).",
        "tips": [
            f"Your biggest spend is {biggest} at ₹{biggest_amt:,.0f} ({biggest_pct:.0f}% of total). Review if this aligns with your priorities.",
            "Set a monthly budget for each category to get automatic alerts when you are overspending.",
            "Try the 50/30/20 rule: 50% needs, 30% wants, 20% savings."
        ],
        "biggest_category": biggest
    }