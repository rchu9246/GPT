-- Additive, forward-only gptq shadow-paper accounting foundation.
-- Apply only after code and activation controls have been reviewed. No data
-- migration, historical UPDATE/DELETE, or paper_*_v92 changes are performed.
-- The gptq schema has no stable portfolio ID; strategy_version is its minimum
-- existing lineage identity. A second account per strategy is unsupported.

create table if not exists public.gptq_paper_accounting_lineages_v1 (
    strategy_version text primary key,
    initialized_on date not null,
    latest_business_date date not null,
    accounting_state_version bigint not null default 1 check (accounting_state_version > 0),
    closing_cash numeric(20,2) not null check (closing_cash >= 0),
    cumulative_realized_pnl numeric(20,2) not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.gptq_paper_accounting_states_v1 (
    strategy_version text not null references public.gptq_paper_accounting_lineages_v1(strategy_version),
    business_date date not null,
    accounting_state_version bigint not null check (accounting_state_version > 0),
    owner_run_id bigint,
    owner_run_attempt bigint,
    opening_cash numeric(20,2) not null,
    closing_cash numeric(20,2) not null check (closing_cash >= 0),
    market_value numeric(20,2) not null check (market_value >= 0),
    total_equity numeric(20,2) not null,
    daily_realized_pnl numeric(20,2) not null default 0,
    cumulative_realized_pnl numeric(20,2) not null default 0,
    unrealized_pnl numeric(20,2) not null default 0,
    state_hash text not null,
    finalized boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (strategy_version, business_date),
    unique (strategy_version, accounting_state_version),
    check (abs(total_equity - closing_cash - market_value) <= 0.01)
);

create table if not exists public.gptq_paper_accounting_events_v1 (
    id bigint generated always as identity primary key,
    strategy_version text not null references public.gptq_paper_accounting_lineages_v1(strategy_version),
    business_date date not null,
    accounting_state_version bigint not null,
    event_key text not null,
    event_type text not null check (event_type in
        ('INITIALIZATION','BUY','SELL','CASH_ADJUSTMENT','MARK_TO_MARKET')),
    event_hash text not null,
    owner_run_id bigint,
    owner_run_attempt bigint,
    order_id bigint,
    cash_delta numeric(20,2) not null default 0,
    trade_realized_pnl numeric(20,2) not null default 0,
    notional numeric(20,2) not null default 0,
    buy_commission numeric(20,2) not null default 0,
    sell_commission numeric(20,2) not null default 0,
    transaction_tax numeric(20,2) not null default 0,
    slippage numeric(20,2) not null default 0,
    cost_basis numeric(20,2) not null default 0,
    authorized_adjustment boolean not null default false,
    market_value numeric(20,2),
    unrealized_pnl numeric(20,2),
    created_at timestamptz not null default now(),
    unique (strategy_version, event_key),
    foreign key (strategy_version, business_date)
        references public.gptq_paper_accounting_states_v1(strategy_version, business_date)
);

create index if not exists idx_gptq_paper_accounting_events_v1_date
    on public.gptq_paper_accounting_events_v1(strategy_version, business_date, id);

alter table public.gptq_paper_accounting_lineages_v1 enable row level security;
alter table public.gptq_paper_accounting_states_v1 enable row level security;
alter table public.gptq_paper_accounting_events_v1 enable row level security;

-- No anon/authenticated policies. Service-role calls use the RPCs below.
-- pgcrypto is deliberately not required; hashes are SHA-256 computed by the
-- owner from canonical JSON and compared as opaque strings in SQL.

create or replace function public.gptq_paper_accounting_initialize_v1(
    p_strategy_version text, p_business_date date, p_opening_cash numeric,
    p_market_value numeric, p_unrealized_pnl numeric, p_event_key text,
    p_event_hash text, p_state_hash text, p_owner_run_id bigint default null,
    p_owner_run_attempt bigint default null
) returns public.gptq_paper_accounting_states_v1
language plpgsql security definer set search_path = public as $$
declare result public.gptq_paper_accounting_states_v1;
begin
    if nullif(p_strategy_version,'') is null or nullif(p_event_key,'') is null
       or nullif(p_event_hash,'') is null or nullif(p_state_hash,'') is null
       or p_business_date is null or p_opening_cash is null or p_market_value is null
       or p_unrealized_pnl is null or p_opening_cash < 0 or p_market_value < 0 then
        raise exception 'INVALID_ACCOUNTING_INITIALIZATION';
    end if;
    -- An existing lineage is never reinitialized, including a same-key replay.
    if exists (select 1 from public.gptq_paper_accounting_lineages_v1
               where strategy_version = p_strategy_version) then
        raise exception 'ACCOUNTING_LINEAGE_ALREADY_INITIALIZED';
    end if;
    insert into public.gptq_paper_accounting_lineages_v1
        (strategy_version, initialized_on, latest_business_date, closing_cash)
    values (p_strategy_version, p_business_date, p_business_date, round(p_opening_cash,2));
    insert into public.gptq_paper_accounting_states_v1
        (strategy_version,business_date,accounting_state_version,owner_run_id,
         owner_run_attempt,opening_cash,closing_cash,market_value,total_equity,
         unrealized_pnl,state_hash)
    values (p_strategy_version,p_business_date,1,p_owner_run_id,p_owner_run_attempt,
            round(p_opening_cash,2),round(p_opening_cash,2),round(p_market_value,2),
            round(p_opening_cash+p_market_value,2),round(p_unrealized_pnl,2),p_state_hash)
    returning * into result;
    insert into public.gptq_paper_accounting_events_v1
        (strategy_version,business_date,accounting_state_version,event_key,event_type,
         event_hash,owner_run_id,owner_run_attempt,market_value,unrealized_pnl)
    values (p_strategy_version,p_business_date,1,p_event_key,'INITIALIZATION',
            p_event_hash,p_owner_run_id,p_owner_run_attempt,
            round(p_market_value,2),round(p_unrealized_pnl,2));
    return result;
end $$;

create or replace function public.gptq_paper_accounting_apply_event_v1(
    p_strategy_version text, p_business_date date, p_event_key text,
    p_event_type text, p_event_hash text, p_state_hash text,
    p_cash_delta numeric default 0, p_trade_realized_pnl numeric default 0,
    p_notional numeric default 0, p_buy_commission numeric default 0,
    p_sell_commission numeric default 0, p_transaction_tax numeric default 0,
    p_slippage numeric default 0, p_cost_basis numeric default 0,
    p_authorized_adjustment boolean default false, p_market_value numeric default null,
    p_unrealized_pnl numeric default null, p_owner_run_id bigint default null,
    p_owner_run_attempt bigint default null, p_order_id bigint default null
) returns public.gptq_paper_accounting_states_v1
language plpgsql security definer set search_path = public as $$
declare lineage public.gptq_paper_accounting_lineages_v1;
        state public.gptq_paper_accounting_states_v1;
        existing public.gptq_paper_accounting_events_v1;
begin
    if nullif(p_event_key,'') is null or nullif(p_event_hash,'') is null
       or nullif(p_state_hash,'') is null or p_business_date is null
       or p_event_type is null
       or p_event_type not in ('BUY','SELL','CASH_ADJUSTMENT','MARK_TO_MARKET') then
        raise exception 'INVALID_ACCOUNTING_EVENT';
    end if;
    select * into lineage from public.gptq_paper_accounting_lineages_v1
      where strategy_version=p_strategy_version for update;
    if not found then raise exception 'MISSING_PRIOR_ACCOUNTING_STATE'; end if;
    select * into existing from public.gptq_paper_accounting_events_v1
      where strategy_version=p_strategy_version and event_key=p_event_key;
    if found then
        if existing.event_hash <> p_event_hash then
            raise exception 'ACCOUNTING_EVENT_IDENTITY_COLLISION';
        end if;
        select * into state from public.gptq_paper_accounting_states_v1
          where strategy_version=p_strategy_version and business_date=existing.business_date;
        return state;
    end if;
    if p_business_date < lineage.latest_business_date then
        raise exception 'HISTORICAL_ACCOUNTING_REWRITE_FORBIDDEN';
    end if;
    if p_business_date > lineage.latest_business_date then
        select * into state from public.gptq_paper_accounting_states_v1
          where strategy_version=p_strategy_version
            and business_date=lineage.latest_business_date for update;
        if not found or not state.finalized then
            raise exception 'PRIOR_ACCOUNTING_DATE_NOT_FINALIZED';
        end if;
        update public.gptq_paper_accounting_lineages_v1
          set latest_business_date=p_business_date,
              accounting_state_version=accounting_state_version+1,
              updated_at=now()
          where strategy_version=p_strategy_version
          returning * into lineage;
        insert into public.gptq_paper_accounting_states_v1
          (strategy_version,business_date,accounting_state_version,owner_run_id,
           owner_run_attempt,opening_cash,closing_cash,market_value,total_equity,
           daily_realized_pnl,cumulative_realized_pnl,unrealized_pnl,state_hash)
        values (p_strategy_version,p_business_date,lineage.accounting_state_version,
                p_owner_run_id,p_owner_run_attempt,state.closing_cash,state.closing_cash,
                state.market_value,state.total_equity,0,state.cumulative_realized_pnl,
                state.unrealized_pnl,p_state_hash);
    end if;
    select * into state from public.gptq_paper_accounting_states_v1
      where strategy_version=p_strategy_version and business_date=p_business_date for update;
    if not found then raise exception 'MISSING_ACCOUNTING_DATE_STATE'; end if;
    if state.finalized then raise exception 'FINALIZED_ACCOUNTING_STATE_IMMUTABLE'; end if;
    if p_event_type='BUY' and
       (abs(round(p_cash_delta,2)+round(p_notional+p_buy_commission,2)) > 0.01
        or p_trade_realized_pnl <> 0 or p_order_id is null) then
        raise exception 'BUY_ACCOUNTING_INVARIANT_FAILED';
    elsif p_event_type='SELL' and
       (abs(round(p_cash_delta,2)-round(p_notional-p_sell_commission-p_transaction_tax,2)) > 0.01
        or abs(round(p_trade_realized_pnl,2)-round(p_cash_delta-p_cost_basis,2)) > 0.01
        or p_order_id is null) then
        raise exception 'SELL_ACCOUNTING_INVARIANT_FAILED';
    elsif p_event_type='CASH_ADJUSTMENT' and not p_authorized_adjustment then
        raise exception 'CASH_ADJUSTMENT_NOT_AUTHORIZED';
    elsif p_event_type='MARK_TO_MARKET' and
       (p_cash_delta <> 0 or p_market_value is null or p_unrealized_pnl is null) then
        raise exception 'MARK_TO_MARKET_INVARIANT_FAILED';
    end if;
    if state.closing_cash + round(p_cash_delta,2) < 0 then
        raise exception 'NEGATIVE_ACCOUNTING_CASH';
    end if;
    update public.gptq_paper_accounting_states_v1
      set closing_cash=round(closing_cash+p_cash_delta,2),
          market_value=coalesce(round(p_market_value,2),market_value),
          total_equity=round(closing_cash+p_cash_delta+coalesce(p_market_value,market_value),2),
          daily_realized_pnl=round(daily_realized_pnl+p_trade_realized_pnl,2),
          cumulative_realized_pnl=round(cumulative_realized_pnl+p_trade_realized_pnl,2),
          unrealized_pnl=coalesce(round(p_unrealized_pnl,2),unrealized_pnl),
          owner_run_id=p_owner_run_id,owner_run_attempt=p_owner_run_attempt,
          state_hash=p_state_hash,updated_at=now()
      where strategy_version=p_strategy_version and business_date=p_business_date
      returning * into state;
    update public.gptq_paper_accounting_lineages_v1
      set closing_cash=state.closing_cash,
          cumulative_realized_pnl=state.cumulative_realized_pnl,updated_at=now()
      where strategy_version=p_strategy_version;
    insert into public.gptq_paper_accounting_events_v1
      (strategy_version,business_date,accounting_state_version,event_key,event_type,
       event_hash,owner_run_id,owner_run_attempt,order_id,cash_delta,trade_realized_pnl,
       notional,buy_commission,sell_commission,transaction_tax,slippage,cost_basis,
       authorized_adjustment,market_value,unrealized_pnl)
    values (p_strategy_version,p_business_date,state.accounting_state_version,
            p_event_key,p_event_type,p_event_hash,p_owner_run_id,p_owner_run_attempt,
            p_order_id,round(p_cash_delta,2),round(p_trade_realized_pnl,2),
            round(p_notional,2),round(p_buy_commission,2),round(p_sell_commission,2),
            round(p_transaction_tax,2),round(p_slippage,2),round(p_cost_basis,2),
            p_authorized_adjustment,p_market_value,p_unrealized_pnl);
    return state;
end $$;

create or replace function public.gptq_paper_accounting_finalize_v1(
    p_strategy_version text, p_business_date date, p_expected_cash numeric,
    p_expected_market_value numeric, p_expected_equity numeric,
    p_expected_daily_realized_pnl numeric, p_expected_unrealized_pnl numeric
) returns public.gptq_paper_accounting_states_v1
language plpgsql security definer set search_path = public as $$
declare state public.gptq_paper_accounting_states_v1;
begin
    select * into state from public.gptq_paper_accounting_states_v1
      where strategy_version=p_strategy_version and business_date=p_business_date for update;
    if not found then raise exception 'MISSING_ACCOUNTING_STATE'; end if;
    if abs(state.closing_cash-p_expected_cash)>0.01
       or abs(state.market_value-p_expected_market_value)>0.01
       or abs(state.total_equity-p_expected_equity)>0.01
       or abs(state.daily_realized_pnl-p_expected_daily_realized_pnl)>0.01
       or abs(state.unrealized_pnl-p_expected_unrealized_pnl)>0.01
       or abs(state.total_equity-state.closing_cash-state.market_value)>0.01 then
        raise exception 'ACCOUNTING_PUBLICATION_INVARIANT_FAILED';
    end if;
    if not state.finalized then
        update public.gptq_paper_accounting_states_v1 set finalized=true,updated_at=now()
          where strategy_version=p_strategy_version and business_date=p_business_date
          returning * into state;
    end if;
    perform set_config('gptq.accounting_publisher','on',true);
    insert into public.gptq_paper_equity_snapshots
      (run_date,strategy_version,cash,market_value,total_equity,realized_pnl,
       unrealized_pnl,open_positions)
    values (p_business_date,p_strategy_version,state.closing_cash,state.market_value,
            state.total_equity,state.daily_realized_pnl,state.unrealized_pnl,
            (select count(*) from public.gptq_paper_positions
             where strategy_version=p_strategy_version))
    on conflict (run_date,strategy_version) do update
      set cash=excluded.cash,market_value=excluded.market_value,
          total_equity=excluded.total_equity,realized_pnl=excluded.realized_pnl,
          unrealized_pnl=excluded.unrealized_pnl,
          open_positions=excluded.open_positions;
    update public.gptq_paper_runs
       set ending_cash=state.closing_cash,ending_equity=state.total_equity,
           realized_pnl=state.daily_realized_pnl,
           unrealized_pnl=state.unrealized_pnl
     where run_date=p_business_date and strategy_version=p_strategy_version;
    return state;
end $$;

-- Order insertion and accounting application are one Postgres transaction.
-- A crash after this RPC commits cannot leave a cash debit without its order,
-- and a replay returns the existing event/order without a second debit.
create or replace function public.gptq_paper_accounting_post_order_v1(
    p_order jsonb, p_event_key text, p_event_hash text, p_state_hash text,
    p_cash_delta numeric, p_trade_realized_pnl numeric,
    p_buy_commission numeric, p_sell_commission numeric,
    p_transaction_tax numeric, p_slippage numeric, p_cost_basis numeric,
    p_owner_run_attempt bigint default null
) returns jsonb language plpgsql security definer set search_path = public as $$
declare existing public.gptq_paper_accounting_events_v1;
        order_row public.gptq_paper_orders;
        state public.gptq_paper_accounting_states_v1;
        v_strategy text := p_order->>'strategy_version';
        v_date date := (p_order->>'run_date')::date;
        v_side text := p_order->>'side';
begin
    if v_side not in ('BUY','SELL') or nullif(v_strategy,'') is null
       or v_date is null or nullif(p_event_key,'') is null then
        raise exception 'INVALID_ACCOUNTING_ORDER';
    end if;
    -- Lock lineage before the duplicate test, in the same order as apply_event.
    perform 1 from public.gptq_paper_accounting_lineages_v1
      where strategy_version=v_strategy for update;
    if not found then raise exception 'MISSING_PRIOR_ACCOUNTING_STATE'; end if;
    select * into existing from public.gptq_paper_accounting_events_v1
      where strategy_version=v_strategy and event_key=p_event_key;
    if found then
        if existing.event_hash <> p_event_hash then
            raise exception 'ACCOUNTING_EVENT_IDENTITY_COLLISION';
        end if;
        select * into order_row from public.gptq_paper_orders where id=existing.order_id;
        select * into state from public.gptq_paper_accounting_states_v1
          where strategy_version=v_strategy and business_date=existing.business_date;
        return jsonb_build_object('order',to_jsonb(order_row),'state',to_jsonb(state));
    end if;
    insert into public.gptq_paper_orders
      (run_id,run_date,strategy_version,stock_id,symbol,side,signal_score,
       signal_label,reference_price,simulated_fill_price,shares,notional,status,
       reason,realized_pnl,holding_days,exit_reason,execution_mode,
       source_signal_id,risk_approved,risk_reason,commission,slippage)
    values ((p_order->>'run_id')::bigint,v_date,v_strategy,
            (p_order->>'stock_id')::bigint,p_order->>'symbol',v_side,
            (p_order->>'signal_score')::numeric,p_order->>'signal_label',
            (p_order->>'reference_price')::numeric,
            (p_order->>'simulated_fill_price')::numeric,
            (p_order->>'shares')::integer,(p_order->>'notional')::numeric,
            coalesce(p_order->>'status','FILLED'),p_order->>'reason',
            (p_order->>'realized_pnl')::numeric,(p_order->>'holding_days')::integer,
            p_order->>'exit_reason',p_order->>'execution_mode',
            (p_order->>'source_signal_id')::bigint,
            (p_order->>'risk_approved')::boolean,p_order->>'risk_reason',
            coalesce((p_order->>'commission')::numeric,0),
            coalesce((p_order->>'slippage')::numeric,0))
    returning * into order_row;
    state := public.gptq_paper_accounting_apply_event_v1(
      v_strategy,v_date,p_event_key,v_side,p_event_hash,p_state_hash,
      p_cash_delta,p_trade_realized_pnl,(p_order->>'notional')::numeric,
      p_buy_commission,p_sell_commission,p_transaction_tax,p_slippage,
      p_cost_basis,false,null,null,(p_order->>'run_id')::bigint,
      p_owner_run_attempt,order_row.id);
    return jsonb_build_object('order',to_jsonb(order_row),'state',to_jsonb(state));
end $$;

-- The migration itself changes no historical row. The publisher must set
-- gptq.accounting_publisher=on in its transaction before writing compatibility
-- snapshots. This guard only applies on/after an initialized lineage date.
create or replace function public.gptq_paper_accounting_guard_snapshot_v1()
returns trigger language plpgsql as $$
begin
    if exists (select 1 from public.gptq_paper_accounting_lineages_v1 l
               where l.strategy_version=new.strategy_version
                 and new.run_date>=l.initialized_on)
       and current_setting('gptq.accounting_publisher',true) is distinct from 'on' then
        raise exception 'NON_OWNER_FINANCIAL_SNAPSHOT_WRITE';
    end if;
    return new;
end $$;

drop trigger if exists gptq_paper_accounting_guard_snapshot_v1
    on public.gptq_paper_equity_snapshots;
create trigger gptq_paper_accounting_guard_snapshot_v1
before insert or update on public.gptq_paper_equity_snapshots
for each row execute function public.gptq_paper_accounting_guard_snapshot_v1();

create or replace function public.gptq_paper_accounting_guard_daily_v1()
returns trigger language plpgsql as $$
declare state public.gptq_paper_accounting_states_v1;
begin
    if exists (select 1 from public.gptq_paper_accounting_lineages_v1 l
               where l.strategy_version=new.strategy_version
                 and new.run_date>=l.initialized_on) then
        select * into state from public.gptq_paper_accounting_states_v1
          where strategy_version=new.strategy_version and business_date=new.run_date;
        if not found or not state.finalized
           or abs(new.cash-state.closing_cash)>0.01
           or abs(new.market_value-state.market_value)>0.01
           or abs(new.equity-state.total_equity)>0.01
           or abs(new.realized_pnl-state.daily_realized_pnl)>0.01
           or abs(new.unrealized_pnl-state.unrealized_pnl)>0.01 then
            raise exception 'NON_AUTHORITATIVE_DAILY_SNAPSHOT';
        end if;
    end if;
    return new;
end $$;

drop trigger if exists gptq_paper_accounting_guard_daily_v1
    on public.gptq_paper_daily_snapshots;
create trigger gptq_paper_accounting_guard_daily_v1
before insert or update on public.gptq_paper_daily_snapshots
for each row execute function public.gptq_paper_accounting_guard_daily_v1();

create or replace function public.gptq_paper_accounting_guard_run_v1()
returns trigger language plpgsql as $$
begin
    if exists (select 1 from public.gptq_paper_accounting_states_v1 s
               where s.strategy_version=new.strategy_version
                 and s.business_date=new.run_date and s.finalized)
       and current_setting('gptq.accounting_publisher',true) is distinct from 'on'
       and (new.ending_cash is distinct from old.ending_cash
            or new.ending_equity is distinct from old.ending_equity
            or new.realized_pnl is distinct from old.realized_pnl
            or new.unrealized_pnl is distinct from old.unrealized_pnl) then
        raise exception 'FINALIZED_ACCOUNTING_RUN_FINANCIALS_IMMUTABLE';
    end if;
    return new;
end $$;

drop trigger if exists gptq_paper_accounting_guard_run_v1
    on public.gptq_paper_runs;
create trigger gptq_paper_accounting_guard_run_v1
before update on public.gptq_paper_runs
for each row execute function public.gptq_paper_accounting_guard_run_v1();

create or replace function public.gptq_paper_accounting_guard_state_v1()
returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' or old.finalized then
        raise exception 'FINALIZED_ACCOUNTING_STATE_IMMUTABLE';
    end if;
    return new;
end $$;

drop trigger if exists gptq_paper_accounting_guard_state_v1
    on public.gptq_paper_accounting_states_v1;
create trigger gptq_paper_accounting_guard_state_v1
before update or delete on public.gptq_paper_accounting_states_v1
for each row execute function public.gptq_paper_accounting_guard_state_v1();

create or replace function public.gptq_paper_accounting_guard_event_v1()
returns trigger language plpgsql as $$
begin
    raise exception 'IMMUTABLE_ACCOUNTING_EVENT';
end $$;

drop trigger if exists gptq_paper_accounting_guard_event_v1
    on public.gptq_paper_accounting_events_v1;
create trigger gptq_paper_accounting_guard_event_v1
before update or delete on public.gptq_paper_accounting_events_v1
for each row execute function public.gptq_paper_accounting_guard_event_v1();

revoke all on function public.gptq_paper_accounting_initialize_v1(
    text,date,numeric,numeric,numeric,text,text,text,bigint,bigint) from public;
revoke all on function public.gptq_paper_accounting_apply_event_v1(
    text,date,text,text,text,text,numeric,numeric,numeric,numeric,numeric,
    numeric,numeric,numeric,boolean,numeric,numeric,bigint,bigint,bigint) from public;
revoke all on function public.gptq_paper_accounting_finalize_v1(
    text,date,numeric,numeric,numeric,numeric,numeric) from public;
grant execute on function public.gptq_paper_accounting_initialize_v1(
    text,date,numeric,numeric,numeric,text,text,text,bigint,bigint) to service_role;
grant execute on function public.gptq_paper_accounting_apply_event_v1(
    text,date,text,text,text,text,numeric,numeric,numeric,numeric,numeric,
    numeric,numeric,numeric,boolean,numeric,numeric,bigint,bigint,bigint) to service_role;
grant execute on function public.gptq_paper_accounting_finalize_v1(
    text,date,numeric,numeric,numeric,numeric,numeric) to service_role;
revoke all on function public.gptq_paper_accounting_post_order_v1(
    jsonb,text,text,text,numeric,numeric,numeric,numeric,numeric,numeric,numeric,bigint)
    from public;
grant execute on function public.gptq_paper_accounting_post_order_v1(
    jsonb,text,text,text,numeric,numeric,numeric,numeric,numeric,numeric,numeric,bigint)
    to service_role;
