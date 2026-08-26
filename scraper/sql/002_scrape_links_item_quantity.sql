-- Run this if you already created scrape_links from 001 before
-- item_quantity existed. Safe to re-run.

alter table public.scrape_links
  add column if not exists item_quantity integer not null default 6;
