-- Valid contracts: rows that passed every row-level rule of docs/02-data-contract.md.
-- The rules live in stg_contracts_cleaned (column rejection_reason); NULL there = valid.
select * exclude (rejection_reason)
from {{ ref('stg_contracts_cleaned') }}
where rejection_reason is null
