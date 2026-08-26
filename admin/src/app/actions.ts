"use server";

import { revalidatePath } from "next/cache";
import { getSupabaseClient, linksTableName } from "@/lib/supabase";

export async function addLink(formData: FormData) {
  const url = String(formData.get("url") || "").trim();
  const category = String(formData.get("category") || "").trim();

  if (!url || !category) {
    throw new Error("URL e categoria são obrigatórios");
  }

  const supabase = getSupabaseClient();
  const { error } = await supabase.from(linksTableName()).insert({ url, category });
  if (error) {
    throw new Error(`Falha ao salvar link: ${error.message}`);
  }

  revalidatePath("/");
}

export async function setLinkActive(id: string, active: boolean) {
  const supabase = getSupabaseClient();
  const { error } = await supabase.from(linksTableName()).update({ active }).eq("id", id);
  if (error) {
    throw new Error(`Falha ao atualizar link: ${error.message}`);
  }
  revalidatePath("/");
}

export async function deleteLink(id: string) {
  const supabase = getSupabaseClient();
  const { error } = await supabase.from(linksTableName()).delete().eq("id", id);
  if (error) {
    throw new Error(`Falha ao remover link: ${error.message}`);
  }
  revalidatePath("/");
}
