# Database Source Information

## Dataset Overview
- **Dataset Name**: Brazilian E-Commerce Public Dataset by Olist (with Olist Marketing Funnel Dataset)
- **Primary Source / Download-Page URL**: 
  - [Kaggle: Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
  - [Kaggle: Marketing Funnel by Olist](https://www.kaggle.com/datasets/olistbr/marketing-funnel-olist)
- **License**: CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International)
- **Download Date**: April 28, 2024
- **Local File**: `olist.sqlite` (112.7 MB)

## Transformations & Data Integrity
- **Status**: Downloaded unchanged.
- **Packaging**: The raw CSV files provided by Olist were compiled into a single relational SQLite database (`olist.sqlite`) preserving all original table schemas, column names, nullability, and raw records.
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
