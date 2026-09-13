BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

-- Fail closed; never repair or rewrite existing rows.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.quant_events
        WHERE symbol IS NOT NULL
        GROUP BY account_name, event_date, symbol, event_type, title
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'quant_events duplicate conflict keys found; no rows modified';
    END IF;
END;
$$;

-- Preserve quant_events_uidx unchanged.
-- This must be a full index, not WHERE symbol IS NOT NULL.
CREATE UNIQUE INDEX IF NOT EXISTS quant_events_postgrest_uidx
ON public.quant_events USING btree
    (account_name, event_date, symbol, event_type, title);

-- IF NOT EXISTS alone does not validate an existing index.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_index AS i
        WHERE i.indexrelid =
              pg_catalog.to_regclass('public.quant_events_postgrest_uidx')
          AND i.indrelid = 'public.quant_events'::regclass
          AND i.indisunique
          AND i.indisvalid
          AND i.indisready
          AND i.indimmediate
          AND i.indnkeyatts = 5
          AND i.indnatts = 5
          AND i.indexprs IS NULL
          AND i.indpred IS NULL
          AND ARRAY(
              SELECT pg_catalog.pg_get_indexdef(i.indexrelid, n, true)
              FROM generate_series(1, 5) AS positions(n)
              ORDER BY n
          ) = ARRAY[
              'account_name', 'event_date', 'symbol', 'event_type', 'title'
          ]::text[]
    ) THEN
        RAISE EXCEPTION
            'quant_events_postgrest_uidx is not the expected valid unique index';
    END IF;
END;
$$;

COMMIT;
