# GPT Quant V14 Enterprise AI Trading Platform

A maintainable Taiwan-equity quantitative research and operational paper
trading platform.

V14 adds:
- a server-side paper trading operations dashboard,
- a single copy-paste Supabase setup script,
- read-only frontend policies for paper-account monitoring,
- scheduled and manually triggered paper execution,
- account, position, order, fill, equity and engine-run observability.

The public frontend cannot write trades. All engine writes require the
Supabase service-role secret stored in GitHub Actions or a secure server.
