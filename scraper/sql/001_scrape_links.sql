-- Run this once in the Supabase SQL editor to create the table the
-- admin panel manages and the scraper reads from.

create table if not exists public.scrape_links (
  id uuid primary key default gen_random_uuid(),
  url text not null,
  category text not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists scrape_links_active_idx on public.scrape_links (active);
