# Baseline clarification review

Edit the Decision and Your notes fields. Suggested decisions are provisional;
they are not counted as measured passes. Use pass / partial / fail.

## Q27 — Which sellers performed best?

Model behavior: generated SQL rather than asking which performance metric to use.
The generated SQL also referenced a nonexistent orders.seller_id column.

Suggested decision: fail.
Decision: fail
Your notes: The model failed to ask for clarification on the subjective term "best" (which could mean highest revenue, order volume, review rating, or fulfillment speed). Instead, it hallucinated an executable query that erroneously referenced a nonexistent `orders.seller_id` column (sellers are linked through `order_items`).

## Q28 — What is our customer churn rate this quarter?

Model response: "Could you please specify which quarter you are referring to?
Also, do you want the churn rate based on customer_unique_id or customer_id?"

Suggested decision: partial. It asks for the quarter, but misses the inactivity
definition needed for churn and questions a customer-key rule already supplied.
A complete clarification should ask for the inactivity threshold and historical
reference quarter.

Decision: partial
Your notes: Correctly recognized that "this quarter" requires an explicit historical anchor since the dataset is historical. However, it failed to ask for the inactivity threshold definition (e.g. 90/180/365 days of dormancy) necessary to define e-commerce churn, and unnecessarily re-questioned the customer identity rule already defined in the business policy.

## Q29 — Show me all the bad orders from last month.

Model response: "What is the definition of a 'bad' order?"

Suggested decision: partial. It clarifies "bad", but not the historical reference
month. No database action should occur until both are defined.

Decision: partial
Your notes: Correctly identified that "bad" order is undefined (could refer to cancellations, reviews <= 2, severe delivery delays, or payment disputes), but failed to clarify the historical reference month and year relative to the dataset timeframe.

## Q30 — How profitable was our electronics category recently?

Model behavior: assumed zero cost and generated a revenue query instead of
explaining that cost data is unavailable and clarifying category/time scope.

Suggested decision: fail. Revenue is not profit; inventing zero cost is unsupported.
Decision: fail
Your notes: Hallucinated that profit equals revenue by assuming zero costs, rather than alerting the user that COGS and cost data are absent from the database. It also failed to clarify the unanchored "recently" timeline or specify which electronics subcategory was intended.

## Business-definition confirmation

The benchmark uses these explicit definitions. Mark accepted or describe changes:

- Late means calendar delivery date after calendar estimated date, not time after midnight.
- Commercial sales use delivered orders, unless the question explicitly states another scope.
- Payment-type review scores weight each order/type once after averaging that order's reviews.
- Category review scores weight each order/category once after averaging that order's reviews.
- Q24 measures positive review rows / all review rows by buyer cohort; the question
  will be reworded explicitly before the next benchmark version.

Definitions accepted / requested changes:
Accepted as stated. The benchmark definitions (calendar-day delivery comparisons, default delivered-order scope, order-level review score averaging prior to category/payment aggregation to prevent line-item skew, and row-level positive review ratio for customer cohorts) provide sound, mathematically consistent reference baselines across all queries.

## Fresh final-test questions

Optional but valuable: add 10 new business questions in a separate file
`final_holdout_questions.md` in the repository root. Do not copy or simply
paraphrase the existing questions. Include joins, aggregation and ambiguity.
No SQL is required. These will be reserved from training and prompt tuning;
reference answers will be built before evaluating the final candidate.

