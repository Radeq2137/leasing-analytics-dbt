{{ config(materialized='table') }}

with source as (
    SELECT
        customer_id,
        customer_type,
        customer_name,
        industry,
        region,
        city,
        customer_email,
        registration_date,
        dt
    FROM {{source('raw', 'customers')}}
),

seed_city_region as (
    SELECT *
    FROM {{ ref('ref_city_region') }}
),

cleaned as (
    SELECT
        NULLIF(TRIM(source.customer_id),'') as customer_id,
        CASE WHEN TRIM(LOWER(customer_type)) = '<unknown>' THEN 'unknown'
        ELSE TRIM(LOWER(customer_type))
        END AS customer_type,
        NULLIF(TRIM(customer_name),'') as customer_name,
        CASE WHEN TRIM(LOWER(industry)) = '<unknown>' THEN 'unknown'
        ELSE TRIM(LOWER(industry))
        END AS industry,
        LOWER(NULLIF(TRIM(source.region),'')) as region,
        NULLIF(NULLIF(TRIM(source.city),''),'<unknown>') as city,
        NULLIF(NULLIF(TRIM(source.customer_email),''),'<unknown>') as customer_email,
        CASE
            -- a blank city or region is not a mismatch (data contract)
            WHEN NULLIF(NULLIF(TRIM(source.city),''),'<unknown>') IS NULL
              OR NULLIF(TRIM(source.region),'') IS NULL THEN 'city_region_match'
            -- both are filled but the (city, region) pair is not in the seed: the LEFT JOIN found nothing
            WHEN seed_city_region.city IS NULL THEN 'city_region_mismatch'
            ELSE 'city_region_match'
        END AS city_region_mismatch_flag,
        try_cast(source.dt as date) as dt,
        try_cast(NULLIF(TRIM(source.registration_date),'') as date) as registration_date,
        NULLIF(TRIM(source.registration_date),'') as registration_date_raw,
        CASE WHEN try_cast(NULLIF(TRIM(source.registration_date),'') as date) > try_cast(source.dt as date) then 'Customer_from_future'
        ELSE 'OK'
        END AS registration_date_from_future_flag
        
    FROM source
    LEFT JOIN seed_city_region
    ON source.city = seed_city_region.city
    AND LOWER(TRIM(source.region)) = seed_city_region.region
),

flagged as (
    SELECT
        *,
        (customer_email IS NOT NULL) AND
         count(distinct customer_id) over (partition by lower(customer_email)) > 1 AS has_duplicate_email
    FROM cleaned
)

SELECT * FROM flagged

--SELECT * FROM cleaned