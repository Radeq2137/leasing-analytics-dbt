{{ config(materialized='table') }}

-- Staging model for raw contracts: rename, trim, normalize, cast, and classify every row.
-- Materialized as a table: the S3 files are read once per `dbt run`, and the filter models
-- and tests that depend on this one then run against the local copy (fast).
-- Nothing is dropped here. Each row gets a rejection_reason (NULL = valid); the two models
-- stg_contracts (valid) and stg_contracts__rejected (quarantine) just filter on it.
-- Rules: docs/02-data-contract.md. Every raw column is text (all_varchar), so a bad value
-- becomes NULL after try_cast instead of breaking the read.

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

),

cleaned as (

    -- Columns ending in _raw keep the trimmed original text. After try_cast a blank value and a
    -- non-parsable value are both NULL; the _raw copy tells them apart ("missing" vs "invalid").
    -- They are used only by the rules below and removed from the final output.
    select
        -- identifiers
        try_cast(nullif(trim(transaction_id), '') as uuid)    as transaction_id,
        nullif(trim(transaction_id), '')                      as transaction_id_raw,
        nullif(trim(contract_id), '')                         as contract_id,
        nullif(trim(customer_id), '')                         as customer_id,
        nullif(trim(vendor_id), '')                           as vendor_id,

        -- mandatory categories: "<unknown>" is valid ("known unknown") -> 'unknown'; blank -> NULL
        case when trim(customer_type) = '<unknown>' then 'unknown'
             else lower(nullif(trim(customer_type), '')) end  as customer_type,
        case when trim(vendor_type) = '<unknown>' then 'unknown'
             else lower(nullif(trim(vendor_type), '')) end    as vendor_type,
        case when trim(asset_type) = '<unknown>' then 'unknown'
             else lower(nullif(trim(asset_type), '')) end     as asset_type,
        case when trim(status) = '<unknown>' then 'unknown'
             else lower(nullif(trim(status), '')) end         as status,

        -- optional text: blank or "<unknown>" -> NULL
        nullif(nullif(trim(customer_email), ''), '<unknown>')         as customer_email,
        nullif(nullif(trim(delivery_street), ''), '<unknown>')        as delivery_street,
        nullif(nullif(trim(delivery_city), ''), '<unknown>')          as delivery_city,
        nullif(nullif(trim(delivery_postal_code), ''), '<unknown>')   as delivery_postal_code,
        nullif(nullif(trim(delivery_region), ''), '<unknown>')        as delivery_region,

        -- numbers and dates: try_cast gives NULL when the text is not parsable
        try_cast(nullif(trim(asset_price), '') as decimal(18, 2))       as asset_price,
        nullif(trim(asset_price), '')                                   as asset_price_raw,
        try_cast(nullif(trim(net_value), '') as decimal(18, 2))         as net_value,
        nullif(trim(net_value), '')                                     as net_value_raw,
        try_cast(nullif(trim(down_payment_pct), '') as decimal(5, 2))   as down_payment_pct,
        nullif(trim(down_payment_pct), '')                              as down_payment_pct_raw,
        try_cast(nullif(trim(term_months), '') as integer)              as term_months,
        nullif(trim(term_months), '')                                   as term_months_raw,
        try_cast(nullif(trim(signed_date), '') as date)                 as signed_date,
        nullif(trim(signed_date), '')                                   as signed_date_raw,

        -- flag: Y -> true, N -> false, anything else ("<unknown>", "yes", blank) -> NULL
        case upper(trim(INCLUDE_IN_STATS))
            when 'Y' then true
            when 'N' then false
        end                                                   as include_in_stats,
        nullif(trim(INCLUDE_IN_STATS), '')                    as include_in_stats_raw,

        -- partition date from the S3 path (dt=YYYY-MM-DD); cast explicitly so the
        -- staging contract holds even if the hive partition column arrives as text
        try_cast(dt as date)                                  as dt

    from source

),

classified as (

    -- The FIRST matching rule wins, so the order matters: first "mandatory field is blank",
    -- then "value is not parsable", then business rules. NULL = the row is valid.
    select
        *,
        case
            -- 1. mandatory field is blank
            when transaction_id_raw is null  then 'missing_mandatory_transaction_id'
            when contract_id is null         then 'missing_mandatory_contract_id'
            when customer_id is null         then 'missing_mandatory_customer_id'
            when customer_type is null       then 'missing_mandatory_customer_type'
            when vendor_id is null           then 'missing_mandatory_vendor_id'
            when vendor_type is null         then 'missing_mandatory_vendor_type'
            when asset_type is null          then 'missing_mandatory_asset_type'
            when asset_price_raw is null     then 'missing_mandatory_asset_price'
            when net_value_raw is null       then 'missing_mandatory_net_value'
            when term_months_raw is null     then 'missing_mandatory_term_months'
            when signed_date_raw is null     then 'missing_mandatory_signed_date'
            when status is null              then 'missing_mandatory_status'
            when include_in_stats_raw is null then 'missing_mandatory_include_in_stats'

            -- 2. value present but not parsable (includes "<unknown>" in numbers and dates)
            when transaction_id is null      then 'invalid_uuid_transaction_id'
            when asset_price is null         then 'invalid_number_asset_price'
            when net_value is null           then 'invalid_number_net_value'
            when term_months is null         then 'invalid_integer_term_months'
            when signed_date is null         then 'invalid_date_signed_date'
            when down_payment_pct_raw is not null and down_payment_pct is null
                                             then 'invalid_number_down_payment_pct'
            when upper(include_in_stats_raw) not in ('Y', 'N', '<UNKNOWN>')
                                             then 'invalid_value_include_in_stats'

            -- 3. business rules
            when asset_price <= 0 or net_value <= 0   then 'non_positive_amount'
            when net_value > asset_price              then 'net_value_above_price'
            when signed_date > dt                     then 'future_signed_date'
            when term_months not between 12 and 84    then 'term_months_out_of_range'
            when down_payment_pct not between 0 and 100 then 'down_payment_pct_out_of_range'
        end as rejection_reason

    from cleaned

),

deduplicated as (

    -- Row-level rules cannot see other rows, so duplicates are handled here. Per contract_id the
    -- first row survives: rows without any other problem come first, then the earliest dt, then
    -- transaction_id (to make the result deterministic). A later valid row with the same
    -- contract_id becomes 'duplicate_contract_id'; rows that already have a reason keep it.
    select
        * exclude (rejection_reason),
        coalesce(
            rejection_reason,
            case
                when row_number() over (
                    partition by contract_id
                    order by (rejection_reason is not null), dt, transaction_id
                ) > 1 then 'duplicate_contract_id'
            end
        ) as rejection_reason

    from classified

)

select * exclude (
    transaction_id_raw,
    asset_price_raw,
    net_value_raw,
    down_payment_pct_raw,
    term_months_raw,
    signed_date_raw,
    include_in_stats_raw
)
from deduplicated
