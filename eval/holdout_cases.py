"""Final, evaluation-only task contracts. Never import into application prompts."""

import re
from olist_cases import ROOT

REFERENCES = [
    """WITH flags AS (SELECT o.order_id,MAX(CASE WHEN s.seller_state<>c.customer_state THEN 1 ELSE 0 END) interstate FROM orders o JOIN customers c USING(customer_id) JOIN order_items i USING(order_id) JOIN sellers s USING(seller_id) WHERE o.order_status='delivered' GROUP BY o.order_id) SELECT 100.0*SUM(interstate)/(SELECT COUNT(*) FROM orders WHERE order_status='delivered') FROM flags""",
    """SELECT c.business_segment,AVG(julianday(c.won_date)-julianday(q.first_contact_date)) FROM leads_closed c JOIN leads_qualified q USING(mql_id) GROUP BY c.business_segment ORDER BY c.business_segment""",
    """SELECT review_score,AVG((julianday(review_answer_timestamp)-julianday(review_creation_date))*24.0) FROM order_reviews WHERE review_score BETWEEN 1 AND 5 GROUP BY review_score ORDER BY review_score""",
    """WITH per_product AS (SELECT p.product_id,p.product_length_cm*p.product_width_cm*p.product_height_cm/1000.0 volume,AVG(i.freight_value/NULLIF(p.product_length_cm*p.product_width_cm*p.product_height_cm/1000.0,0)) freight_per_liter FROM products p JOIN order_items i USING(product_id) JOIN orders o USING(order_id) WHERE o.order_status='delivered' GROUP BY p.product_id HAVING COUNT(*)>=50) SELECT AVG(volume),AVG(freight_per_liter) FROM per_product""",
    """WITH per_order AS (SELECT p.order_id,COUNT(DISTINCT p.payment_type) kinds,SUM(p.payment_value) total FROM order_payments p JOIN orders o USING(order_id) WHERE o.order_status='delivered' GROUP BY p.order_id) SELECT CASE WHEN kinds>1 THEN 'multi' ELSE 'single' END cohort,COUNT(*),AVG(total) FROM per_order GROUP BY cohort ORDER BY cohort""",
    """WITH close_dates AS (SELECT seller_id,MIN(won_date) closed FROM leads_closed GROUP BY seller_id), first_sales AS (SELECT i.seller_id,MIN(o.order_purchase_timestamp) first_sale FROM order_items i JOIN orders o USING(order_id) WHERE o.order_status='delivered' GROUP BY i.seller_id) SELECT AVG(julianday(f.first_sale)-julianday(c.closed)) FROM close_dates c JOIN first_sales f USING(seller_id)""",
    """WITH baskets AS (SELECT o.order_id,o.order_purchase_timestamp,SUM(i.price) spend FROM orders o JOIN order_items i USING(order_id) WHERE o.order_status='delivered' GROUP BY o.order_id) SELECT CAST(strftime('%w',order_purchase_timestamp) AS INTEGER) weekday,COUNT(*),AVG(spend) FROM baskets GROUP BY weekday ORDER BY weekday""",
    """SELECT c.customer_state,AVG(julianday(date(o.order_estimated_delivery_date))-julianday(date(o.order_delivered_customer_date))) FROM orders o JOIN customers c USING(customer_id) WHERE o.order_status='delivered' AND date(o.order_delivered_customer_date)<date(o.order_estimated_delivery_date) GROUP BY c.customer_state ORDER BY c.customer_state""",
]

# Make scoring contracts explicit to avoid penalizing defensible interpretations.
# These clarify the supplied questions; they are not answer examples or model rules.
CONTRACTS = {
    "H01": "Count each delivered order once; interstate means at least one seller is in a different state from the customer. Use all delivered orders as denominator. Return only the percentage.",
    "H02": "Return business_segment and average days. Retain missing segment as NULL.",
    "H03": "Return review_score and average hours. This is the recorded timestamp interval, not proof of a support-agent response.",
    "H04": "Return two overall averages, weighting each qualifying product equally: volume in liters, then its average freight cost per liter. Qualify products by at least 50 delivered item rows. Exclude missing values from each average and avoid division by zero.",
    "H05": "Return cohort ('single' or 'multi'), order_count and average_total_payment; one row per cohort, using summed payment value per delivered order.",
    "H06": "Use each seller once, their earliest recorded deal close and first delivered sale purchase timestamp. Exclude sellers without both events. Retain negative intervals. Return only average elapsed days.",
    "H07": "Return weekday as an integer (0 Sunday through 6 Saturday), order_count and average merchandise spend per order. Sum item prices per order before averaging.",
    "H08": "Compare calendar dates and measure calendar days. Return customer_state and average days early. Estimated delivery is the dataset estimate, not a verified carrier SLA.",
}


def cases():
    text = (ROOT / "eval/datasets/holdout.md").read_text()
    entries = re.findall(
        r"\* \*\*ID\*\*: (H\d+)\n.*?\* \*\*Question\*\*: (.*?)\n", text, re.S
    )
    if len(entries) != 10:
        raise ValueError("Expected ten final holdout questions.")
    result = []
    for index, (identifier, original) in enumerate(entries):
        result.append(
            {
                "id": identifier,
                "original_question": original,
                "question": original
                + (" " + CONTRACTS[identifier] if identifier in CONTRACTS else ""),
                "expected_action": "sql" if index < 8 else "clarify",
                "reference_sql": REFERENCES[index] if index < 8 else None,
                "difficulty": "final_holdout",
            }
        )
    return result
