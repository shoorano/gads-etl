-- Canonical reporting tables for gads-etl
CREATE TABLE IF NOT EXISTS fact_campaign_daily (
    customer_id VARCHAR(32) NOT NULL,
    campaign_id VARCHAR(32) NOT NULL,
    date DATE NOT NULL,
    impressions BIGINT,
    clicks BIGINT,
    conversions NUMERIC(18,4),
    cost_micros BIGINT,
    PRIMARY KEY (customer_id, campaign_id, date)
);

CREATE TABLE IF NOT EXISTS fact_ad_group_daily (
    customer_id VARCHAR(32) NOT NULL,
    ad_group_id VARCHAR(32) NOT NULL,
    campaign_id VARCHAR(32) NOT NULL,
    device VARCHAR(32),
    date DATE NOT NULL,
    conversions NUMERIC(18,4),
    cost_micros BIGINT,
    value_per_conversion NUMERIC(18,4),
    PRIMARY KEY (customer_id, ad_group_id, date)
);
