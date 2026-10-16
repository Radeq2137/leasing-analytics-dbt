-- Staging model for raw contracts: rename, trim, normalize and cast. Nothing is filtered
-- here; splitting rows into valid / rejected comes in a later step (docs/02-data-contract.md).
-- Every raw column is text (all_varchar), so a bad value becomes NULL instead of an error.

with source as (

    -- 1:1 with the raw extract, names exactly as in the CSV header
    -- (docs/02-data-contract.md). Listed explicitly on purpose: if the generator
    -- changes the header, this model fails loudly instead of silently
    -- passing a new column through or dropping one.
    select
        transaction_id,
        contract_id,
        customer_id,
        customer_type,
        customer_email,
        vendor_id,
        vendor_type,
        asset_type,
        asset_price,
        net_value,
        down_payment_pct,
        term_months,
        signed_date,
        delivery_street,
        delivery_city,
        delivery_postal_code,
        delivery_region,
        status,
        INCLUDE_IN_STATS,
        dt

    from {{ source('raw', 'contracts') }}

)

select
    -- identifiers
    try_cast(transaction_id as uuid)                      as transaction_id,
    trim(contract_id)                                     as contract_id,
    trim(customer_id)                                     as customer_id,
    trim(vendor_id)                                       as vendor_id,

    -- mandatory categories: "<unknown>" is valid ("known unknown") -> 'unknown'
    case when trim(customer_type) = '<unknown>' then 'unknown'
         else lower(trim(customer_type)) end              as customer_type,
    case when trim(vendor_type) = '<unknown>' then 'unknown'
         else lower(trim(vendor_type)) end                as vendor_type,
    case when trim(asset_type) = '<unknown>' then 'unknown'
         else lower(trim(asset_type)) end                 as asset_type,
    case when trim(status) = '<unknown>' then 'unknown'
         else lower(trim(status)) end                     as status,

    -- optional text: blank or "<unknown>" -> NULL (blank CSV cells are already NULL)
    nullif(nullif(trim(customer_email), ''), '<unknown>')         as customer_email,
    nullif(nullif(trim(delivery_street), ''), '<unknown>')        as delivery_street,
    nullif(nullif(trim(delivery_city), ''), '<unknown>')          as delivery_city,
    nullif(nullif(trim(delivery_postal_code), ''), '<unknown>')   as delivery_postal_code,
    nullif(nullif(trim(delivery_region), ''), '<unknown>')        as delivery_region,

    -- numbers and dates: try_cast gives NULL when the text is not parsable
    try_cast(asset_price as decimal(18, 2))               as asset_price,
    try_cast(net_value as decimal(18, 2))                 as net_value,
    try_cast(down_payment_pct as decimal(5, 2))           as down_payment_pct,
    try_cast(term_months as integer)                      as term_months,
    try_cast(signed_date as date)                         as signed_date,

    -- flag: Y -> true, N -> false, anything else ("<unknown>", "yes", blank) -> NULL
    case upper(trim(INCLUDE_IN_STATS))
        when 'Y' then true
        when 'N' then false
    end                                                   as include_in_stats,

    -- partition date from the S3 path (dt=YYYY-MM-DD); cast explicitly so the
    -- staging contract holds even if the hive partition column arrives as text
    try_cast(dt as date)                                  as dt

from source
