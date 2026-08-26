"use server";

import { revalidatePath } from "next/cache";
import { getSupabaseClient, linksTableName } from "@/lib/supabase";

export async function addLink(formData: FormData) {
  const url = String(formData.get("url") || "").trim();
  const category = String(formData.get("category") || "").trim();
  const itemQuantity = Number(formData.get("item_quantity"));

  if (!url || !category) {
    throw new Error("URL e categoria são obrigatórios");
  }
  if (!Number.isInteger(itemQuantity) || itemQuantity <= 0) {
    throw new Error("Quantidade de itens deve ser um número inteiro maior que zero");
  }

  const supabase = getSupabaseClient();
  const { error } = await supabase
    .from(linksTableName())
    .insert({ url, category, item_quantity: itemQuantity });
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

export async function updateItemQuantity(id: string, formData: FormData) {
  const itemQuantity = Number(formData.get("item_quantity"));
  if (!Number.isInteger(itemQuantity) || itemQuantity <= 0) {
    throw new Error("Quantidade de itens deve ser um número inteiro maior que zero");
  }

  const supabase = getSupabaseClient();
  const { error } = await supabase
    .from(linksTableName())
    .update({ item_quantity: itemQuantity })
    .eq("id", id);
  if (error) {
    throw new Error(`Falha ao atualizar quantidade: ${error.message}`);
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
