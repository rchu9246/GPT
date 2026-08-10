-- GPT Quant V9.2 Paper Trading Dashboard v1.0
-- Read-only policies for dashboard access via publishable/anon key.
--
-- IMPORTANT:
-- These policies make the four PAPER-TRADING tables readable via the public
-- Supabase anon role. They do NOT permit INSERT/UPDATE/DELETE.
--
-- If your GitHub Pages site is public, the paper-trading data is therefore
-- publicly readable. Do not run this SQL if you want these records private.

drop policy if exists "paper_dashboard_read_runs" on public.gptq_paper_runs;
create policy "paper_dashboard_read_runs"
on public.gptq_paper_runs for select
to anon
using (true);

drop policy if exists "paper_dashboard_read_orders" on public.gptq_paper_orders;
create policy "paper_dashboard_read_orders"
on public.gptq_paper_orders for select
to anon
using (true);

drop policy if exists "paper_dashboard_read_positions" on public.gptq_paper_positions;
create policy "paper_dashboard_read_positions"
on public.gptq_paper_positions for select
to anon
using (true);

drop policy if exists "paper_dashboard_read_equity" on public.gptq_paper_equity_snapshots;
create policy "paper_dashboard_read_equity"
on public.gptq_paper_equity_snapshots for select
to anon
using (true);
