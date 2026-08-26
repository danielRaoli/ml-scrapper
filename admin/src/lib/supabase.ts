import { createClient } from "@supabase/supabase-js";

export type ScrapeLink = {
  id: string;
  url: string;
  category: string;
  active: boolean;
  created_at: string;
};

export const CATEGORIES = [
  "geral",
  "roupas",
  "academia",
  "eletronicos",
  "beleza",
  "eletrodomesticos",
] as const;

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Variável de ambiente ${name} não configurada`);
  }
  return value;
}

export function getSupabaseClient() {
  const url = requiredEnv("SUPABASE_URL");
  const key = requiredEnv("SUPABASE_ANON_KEY");
  return createClient(url, key, {
    auth: { persistSession: false },
  });
}

export function linksTableName(): string {
  return process.env.SUPABASE_TABLE_LINKS || "scrape_links";
}
