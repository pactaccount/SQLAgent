"""Frozen reference definitions. Do not use these evaluation cases for training."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = """Use SQLite. Revenue means item prices, excluding freight. Commercial sales
questions use delivered orders; explicit all-order/status, catalog, payment, review,
first-purchase and cohort questions use all records unless stated otherwise.
Unique buyers use customer_unique_id. Monthly reporting uses purchase month.
Late delivery compares calendar dates; delay is their calendar-day difference.
Use English category names, falling back to Portuguese, and 'unknown' for missing.
For payment-type reviews, average reviews per order first, then weight each distinct
order/payment-type pair once. Category reviews weight each distinct order/category
once after averaging that order's reviews. Q24's percentage means positive review
rows among review rows within each buyer cohort, not percentage of buyers.
Installment brackets exclude zero installments. Top-N ties use ascending identifier
unless dense ranks are explicitly requested. Return all qualifying categories when
no limit is specified. For 2017 growth, January has no prior-month value (NULL).
Do not invent costs, profitability, an inactivity definition, or reference dates.
"""

SQL = {
1: "SELECT order_status,COUNT(*) FROM orders GROUP BY order_status ORDER BY order_status",
2: "SELECT COUNT(DISTINCT c.customer_unique_id) FROM orders o JOIN customers c USING(customer_id)",
3: "SELECT payment_type,COUNT(*) n FROM order_payments GROUP BY payment_type ORDER BY n DESC,payment_type LIMIT 5",
4: "SELECT COUNT(DISTINCT product_category_name) FROM products",
5: "SELECT i.product_id,i.price FROM order_items i JOIN orders o USING(order_id) WHERE o.order_status='delivered' ORDER BY i.price DESC,i.order_id,i.order_item_id LIMIT 5",
6: "SELECT COUNT(*) FROM orders WHERE order_status='canceled'",
7: "SELECT review_score,COUNT(*) FROM order_reviews WHERE review_score BETWEEN 1 AND 5 GROUP BY review_score ORDER BY review_score",
8: "SELECT COUNT(DISTINCT seller_id) FROM sellers",
9: "SELECT c.customer_state,COUNT(*) n FROM orders o JOIN customers c USING(customer_id) WHERE o.order_status='delivered' GROUP BY c.customer_state ORDER BY n DESC,c.customer_state LIMIT 5",
10: "SELECT strftime('%Y-%m',o.order_purchase_timestamp) month,SUM(i.price) FROM orders o JOIN order_items i USING(order_id) WHERE o.order_status='delivered' AND o.order_purchase_timestamp>='2017-01-01' AND o.order_purchase_timestamp<'2018-01-01' GROUP BY month ORDER BY month",
11: "SELECT c.customer_state,AVG(i.freight_value) FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) WHERE o.order_status='delivered' GROUP BY c.customer_state ORDER BY c.customer_state",
12: "SELECT c.customer_state,AVG(julianday(o.order_delivered_customer_date)-julianday(o.order_purchase_timestamp)) FROM orders o JOIN customers c USING(customer_id) WHERE o.order_status='delivered' AND o.order_delivered_customer_date IS NOT NULL AND o.order_purchase_timestamp IS NOT NULL GROUP BY c.customer_state ORDER BY c.customer_state",
13: "SELECT COUNT(*) FROM orders WHERE order_status='delivered' AND date(order_delivered_customer_date)>date(order_estimated_delivery_date)",
14: "SELECT COALESCE(t.product_category_name_english,p.product_category_name,'unknown') category,SUM(i.price) revenue FROM order_items i JOIN orders o USING(order_id) JOIN products p USING(product_id) LEFT JOIN product_category_name_translation t USING(product_category_name) WHERE o.order_status='delivered' GROUP BY category ORDER BY revenue DESC,category LIMIT 10",
15: "WITH r AS (SELECT order_id,AVG(review_score) score FROM order_reviews GROUP BY order_id), p AS (SELECT DISTINCT order_id,payment_type FROM order_payments) SELECT p.payment_type,AVG(r.score) FROM p JOIN r USING(order_id) GROUP BY p.payment_type ORDER BY p.payment_type",
16: "SELECT COUNT(*) FROM (SELECT order_id FROM order_items GROUP BY order_id HAVING COUNT(DISTINCT seller_id)>1)",
17: "WITH f AS (SELECT c.customer_unique_id,MIN(o.order_purchase_timestamp) first_date FROM orders o JOIN customers c USING(customer_id) GROUP BY c.customer_unique_id) SELECT strftime('%Y-%m',first_date) month,COUNT(*) FROM f WHERE first_date>='2017-01-01' AND first_date<'2018-01-01' GROUP BY month ORDER BY month",
18: "SELECT AVG(n) FROM (SELECT o.order_id,COUNT(i.order_item_id) n FROM orders o LEFT JOIN order_items i USING(order_id) WHERE o.order_status='delivered' GROUP BY o.order_id)",
19: "SELECT s.seller_state,COUNT(*) n FROM order_items i JOIN sellers s USING(seller_id) JOIN orders o USING(order_id) WHERE o.order_status='delivered' GROUP BY s.seller_state ORDER BY n DESC,s.seller_state LIMIT 5",
20: "SELECT CASE WHEN payment_installments=1 THEN '1' WHEN payment_installments BETWEEN 2 AND 5 THEN '2-5' WHEN payment_installments BETWEEN 6 AND 10 THEN '6-10' ELSE '>10' END bracket,SUM(payment_value) FROM order_payments WHERE payment_installments>=1 GROUP BY bracket ORDER BY MIN(payment_installments)",
21: "WITH r AS (SELECT order_id,AVG(review_score) score FROM order_reviews GROUP BY order_id), oc AS (SELECT DISTINCT o.order_id,COALESCE(t.product_category_name_english,p.product_category_name,'unknown') category FROM orders o JOIN order_items i USING(order_id) JOIN products p USING(product_id) LEFT JOIN product_category_name_translation t USING(product_category_name) WHERE o.order_status='delivered') SELECT category,AVG(r.score) score FROM oc JOIN r USING(order_id) GROUP BY category HAVING COUNT(*)>=100 ORDER BY score DESC,category",
22: "WITH m AS (SELECT strftime('%Y-%m',o.order_purchase_timestamp) month,SUM(i.price) revenue FROM orders o JOIN order_items i USING(order_id) WHERE o.order_status='delivered' AND o.order_purchase_timestamp>='2017-01-01' AND o.order_purchase_timestamp<'2018-01-01' GROUP BY month), g AS (SELECT *,LAG(revenue) OVER (ORDER BY month) prev FROM m) SELECT month,(revenue-prev)*100.0/NULLIF(prev,0) FROM g ORDER BY month",
23: "WITH s AS (SELECT COALESCE(t.product_category_name_english,p.product_category_name,'unknown') category,i.seller_id,SUM(i.price) revenue FROM order_items i JOIN orders o USING(order_id) JOIN products p USING(product_id) LEFT JOIN product_category_name_translation t USING(product_category_name) WHERE o.order_status='delivered' GROUP BY category,i.seller_id), top AS (SELECT category FROM s GROUP BY category ORDER BY SUM(revenue) DESC,category LIMIT 5), ranked AS (SELECT s.*,DENSE_RANK() OVER (PARTITION BY category ORDER BY revenue DESC) rank FROM s JOIN top USING(category)) SELECT category,seller_id,revenue FROM ranked WHERE rank<=3 ORDER BY category,revenue DESC,seller_id",
24: "WITH cohort AS (SELECT c.customer_unique_id,CASE WHEN COUNT(*)>1 THEN 'repeat' ELSE 'one-time' END kind FROM orders o JOIN customers c USING(customer_id) GROUP BY c.customer_unique_id) SELECT h.kind,100.0*AVG(CASE WHEN r.review_score>=4 THEN 1.0 ELSE 0.0 END) FROM order_reviews r JOIN orders o USING(order_id) JOIN customers c USING(customer_id) JOIN cohort h USING(customer_unique_id) GROUP BY h.kind ORDER BY h.kind",
25: "SELECT c.customer_state,100.0*AVG(CASE WHEN date(o.order_delivered_customer_date)>date(o.order_estimated_delivery_date) THEN 1.0 ELSE 0.0 END),AVG(CASE WHEN date(o.order_delivered_customer_date)>date(o.order_estimated_delivery_date) THEN julianday(date(o.order_delivered_customer_date))-julianday(date(o.order_estimated_delivery_date)) END) FROM orders o JOIN customers c USING(customer_id) WHERE o.order_status='delivered' GROUP BY c.customer_state HAVING COUNT(*)>=500 ORDER BY c.customer_state",
26: "SELECT COALESCE(t.product_category_name_english,p.product_category_name,'unknown') category,AVG(p.product_weight_g)/1000.0,AVG(i.freight_value/NULLIF(i.price,0)) FROM order_items i JOIN products p USING(product_id) JOIN orders o USING(order_id) LEFT JOIN product_category_name_translation t USING(product_category_name) WHERE o.order_status='delivered' GROUP BY category HAVING COUNT(*)>=200 ORDER BY category",
}


def cases():
    text = (ROOT / 'business_questions.md').read_text()
    matches = re.findall(r'ID: (Q\d+)\nQuestion: (.*?)\n', text)
    assert len(matches) == 30 and len({i for i, _ in matches}) == 30
    return [dict(id=i, question=q, expected_action='sql' if int(i[1:])<=26 else 'clarify',
                 reference_sql=SQL.get(int(i[1:])),
                 difficulty='simple' if int(i[1:])<=8 else 'intermediate' if int(i[1:])<=20 else 'complex' if int(i[1:])<=26 else 'clarification')
            for i,q in matches]
