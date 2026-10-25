# Final Holdout Business Questions (Evaluation Only)

This dataset comprises 10 novel, held-out business questions reserved strictly from model training, prompt tuning, and few-shot selection. These questions evaluate cross-domain analytical tasks, marketing funnel relationships, customer feedback mechanics, dimensional shipping metrics, and ambiguous enterprise inquiries.

No SQL queries are included. Reference queries and expected result sets will be authored independently prior to testing final candidate checkpoints.

---

### Question 01 — Cross-State Fulfillment Ratio
* **ID**: H01
* **Task Type**: Geographic logistics join & ratio calculation
* **Question**: What percentage of delivered orders were fulfilled by sellers located in a different state from the customer?
* **Analytical Scope**: Joins `orders`, `order_items`, `customers`, and `sellers`. Compares `customers.customer_state` with `sellers.seller_state` for delivered orders, calculating the proportion of interstate vs. intrastate fulfillments.
* **Expected Behavior**: Answer

---

### Question 02 — Lead Conversion Duration by Business Segment
* **ID**: H02
* **Task Type**: Funnel date arithmetic & grouping
* **Question**: For closed deals in the marketing funnel, what was the average duration in days from initial lead qualification to deal close, broken down by business segment?
* **Analytical Scope**: Joins `leads_closed` with `leads_qualified` on `mql_id`. Computes `julianday(leads_closed.won_date) - julianday(leads_qualified.first_contact_date)` and averages by `leads_closed.business_segment`.
* **Expected Behavior**: Answer

---

### Question 03 — Customer Support Review Response Latency
* **ID**: H03
* **Task Type**: Timestamp difference & score partitioning
* **Question**: What is the average time in hours between the creation of a customer review and the logged review answer timestamp, broken down by review score (1 to 5)?
* **Analytical Scope**: Uses `order_reviews`. Calculates the timestamp delta between `review_answer_timestamp` and `review_creation_date` in hours, grouped by `review_score` to inspect whether negative reviews receive faster or slower responses.
* **Expected Behavior**: Answer

---

### Question 04 — Volumetric Shipping Efficiency
* **ID**: H04
* **Task Type**: Multi-attribute physical computation & filtering
* **Question**: Across products with at least 50 delivered items sold, what is the average product volume in liters (length × width × height / 1000) and the average freight cost per liter of volume?
* **Analytical Scope**: Joins `order_items`, `products`, and `orders`. Filters for `orders.order_status = 'delivered'` and products with count `>= 50`. Computes volumetric dimensions and freight-to-volume efficiency.
* **Expected Behavior**: Answer

---

### Question 05 — Multi-Method Payment Order Composition
* **ID**: H05
* **Task Type**: Conditional aggregation & payment basket comparison
* **Question**: How many delivered orders were paid using more than one distinct payment type (e.g., combining a voucher with a credit card), and what was their average total payment value compared to single-payment-type orders?
* **Analytical Scope**: Aggregates `order_payments` by `order_id` to partition orders into single-type vs. multi-type payment baskets (`COUNT(DISTINCT payment_type) > 1`), joined with `orders` (`order_status = 'delivered'`) to compare frequency and average basket size.
* **Expected Behavior**: Answer

---

### Question 06 — Seller Onboarding-to-First-Sale Velocity
* **ID**: H06
* **Task Type**: Cross-funnel chronological join & minimum date extraction
* **Question**: For sellers acquired through the marketing funnel, what was the average number of days between their deal close date and the timestamp of their very first customer sale?
* **Analytical Scope**: Joins `leads_closed` on `seller_id` with `order_items` and `orders`. For each seller, extracts the earliest `MIN(orders.order_purchase_timestamp)` and calculates the elapsed days from `leads_closed.won_date`.
* **Expected Behavior**: Answer

---

### Question 07 — Day-of-Week Purchase Distribution
* **ID**: H07
* **Task Type**: Temporal date-part extraction & order volume analysis
* **Question**: How does delivered order volume and average item spend distribute across days of the week (Sunday through Saturday)?
* **Analytical Scope**: Uses `strftime('%w', order_purchase_timestamp)` across `orders` joined with `order_items` for delivered orders, returning the day of week, total order count, and average merchandise spend per order.
* **Expected Behavior**: Answer

---

### Question 08 — Early Delivery Buffer by Customer State
* **ID**: H08
* **Task Type**: SLA differential aggregation & state grouping
* **Question**: For orders delivered strictly before the carrier estimated date, how many days in advance did customers receive their package on average, grouped by customer state?
* **Analytical Scope**: Joins `orders` and `customers`. Filters for `order_status = 'delivered'` and `order_delivered_customer_date < order_estimated_delivery_date`. Computes `AVG(julianday(order_estimated_delivery_date) - julianday(order_delivered_customer_date))` per `customer_state`.
* **Expected Behavior**: Answer

---

### Question 09 — Clarification Case: "Top-Tier" Acquisition Channels
* **ID**: H09
* **Task Type**: Subjective multi-attribute query requiring dialogue
* **Question**: Which marketing acquisition channel brought in our highest-tier sellers?
* **Analytical Scope**: The concept of "highest-tier seller" is undefined—it could mean highest total gross merchandise value (GMV), highest unit order count, lowest return/cancellation rate, or fastest dispatch time. Additionally, attribution requires specifying whether channel credit comes from `leads_qualified.origin` or declared lead type.
* **Expected Behavior**: Ask for clarification

---

### Question 10 — Clarification Case: Dormant VIP Customer Identification
* **ID**: H10
* **Task Type**: Unanchored recency & undefined segment threshold
* **Question**: List all dormant VIP customers from 2017 who should receive a reactivation discount.
* **Analytical Scope**: "VIP customer" is undefined (could require a minimum lifetime spend, order frequency, or average order value threshold), and "dormant" lacks an inactivity window (e.g., 90, 180, or 365 days without purchase). Furthermore, determining reactivation status requires an explicit reference date anchor.
* **Expected Behavior**: Ask for clarification
