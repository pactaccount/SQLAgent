# Dataset provenance and licenses

## Dataset Overview
- **Dataset Name**: Brazilian E-Commerce Public Dataset by Olist (with Olist Marketing Funnel Dataset)
- **Primary Source / Download-Page URL**: 
  - [Kaggle: Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
  - [Kaggle: Marketing Funnel by Olist](https://www.kaggle.com/datasets/olistbr/marketing-funnel-olist)
- **License**: CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International)
- **Reported date in the original local source note**: April 28, 2024. This is not independently verified as the actual download date.
- **Local File**: `olist.sqlite` (112.7 MB)

## Transformations & Data Integrity
- **Status**: Downloaded unchanged.
- **Packaging**: The local SQLite file combines the Olist e-commerce and marketing-funnel tables. The original note described CSV-to-SQLite compilation, but the exact conversion procedure and row-for-row equivalence were not independently verified. Treat the supplied SQLite file as the fixed evaluation input.
- **Tables Included**:
  - `orders`: Order status, purchase, approval, carrier delivery, and customer delivery timestamps.
  - `order_items`: Order line items, item prices, freight values, product IDs, and seller IDs.
  - `order_payments`: Payment sequential steps, payment types, installments, and payment values.
  - `order_reviews`: Review IDs, review scores, titles, comment messages, and timestamps.
  - `customers`: Customer IDs, unique customer identifiers (`customer_unique_id`), zip codes, cities, and states.
  - `sellers`: Seller IDs, zip codes, cities, and states.
  - `products`: Product dimensions, weights, photo counts, and category names.
  - `product_category_name_translation`: Portuguese to English category name translations.
  - `geolocation`: Brazilian zip codes with latitude, longitude, city, and state coordinates.
  - `leads_qualified`: Qualified marketing leads (MQLs) from the marketing funnel.
  - `leads_closed`: Closed deals linking MQLs with seller IDs, lead types, and deal attributes.
- **Integrity Notice**: The master database `olist.sqlite` is kept strictly untouched and unmodified. All evaluations, schema inspections, relationship audits, and test queries execute against working copies or read-only connections.

## Bundled sample

`data/chinook.db` is the small music-store demonstration database retained from
the existing project. Its MIT notice is preserved in
[CHINOOK_LICENSE.md](../data/CHINOOK_LICENSE.md). The sample is distributed with the
application; the larger Olist database and user uploads are not.

## Repository and evaluation handling

Keep the original Olist file at the project root for the existing evaluation runner.
Do not clean, deduplicate or remove records merely to improve a score. Missing
values, multiple reviews and split payments are handled through explicit reference
semantics. Raw data files and uploaded conversions are ignored by Git, with the
licensed Chinook sample as the sole exception. Dataset license statements above
come from the supplied provenance note; application MIT licensing does not replace
dataset terms.
