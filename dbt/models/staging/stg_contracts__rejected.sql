-- Quarantine: rows that broke a row-level rule, kept together with the reason.
-- Nothing is dropped: stg_contracts + stg_contracts__rejected = every raw row.
select *
from {{ ref('stg_contracts_cleaned') }}
where rejection_reason is not null
