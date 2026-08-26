import { getSupabaseClient, linksTableName, CATEGORIES, type ScrapeLink } from "@/lib/supabase";
import { addLink, setLinkActive, deleteLink, updateItemQuantity } from "./actions";
import { logout } from "./login/actions";

export const dynamic = "force-dynamic";

async function getLinks(): Promise<ScrapeLink[]> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from(linksTableName())
    .select("*")
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(`Falha ao carregar links: ${error.message}`);
  }

  return data ?? [];
}

export default async function AdminPage() {
  const links = await getLinks();

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Links do Scraper</h1>
          <p className="text-sm text-black/60 dark:text-white/60">
            Cadastre os links de ofertas que o scraper deve buscar.
          </p>
        </div>
        <form action={logout}>
          <button
            type="submit"
            className="text-sm text-black/60 underline hover:text-black dark:text-white/60 dark:hover:text-white"
          >
            Sair
          </button>
        </form>
      </header>

      <form
        action={addLink}
        className="flex flex-col gap-3 rounded-xl border border-black/10 p-4 dark:border-white/15 sm:flex-row sm:items-end"
      >
        <div className="flex-1 space-y-1">
          <label htmlFor="url" className="text-sm font-medium">
            URL da oferta
          </label>
          <input
            id="url"
            name="url"
            type="url"
            required
            placeholder="https://www.mercadolivre.com.br/ofertas?category=..."
            className="w-full rounded-md border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40 dark:border-white/20 dark:focus:border-white/40"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="category" className="text-sm font-medium">
            Categoria
          </label>
          <select
            id="category"
            name="category"
            defaultValue={CATEGORIES[0]}
            className="w-full rounded-md border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40 dark:border-white/20 dark:focus:border-white/40 sm:w-auto"
          >
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="item_quantity" className="text-sm font-medium">
            Qtd. de itens
          </label>
          <input
            id="item_quantity"
            name="item_quantity"
            type="number"
            min={1}
            step={1}
            required
            defaultValue={6}
            className="w-full rounded-md border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40 dark:border-white/20 dark:focus:border-white/40 sm:w-24"
          />
        </div>
        <button
          type="submit"
          className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white dark:bg-white dark:text-black"
        >
          Adicionar
        </button>
      </form>

      <div className="overflow-x-auto rounded-xl border border-black/10 dark:border-white/15">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-black/10 text-black/60 dark:border-white/15 dark:text-white/60">
            <tr>
              <th className="px-4 py-2 font-medium">URL</th>
              <th className="px-4 py-2 font-medium">Categoria</th>
              <th className="px-4 py-2 font-medium">Qtd. itens</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {links.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-black/50 dark:text-white/50">
                  Nenhum link cadastrado ainda.
                </td>
              </tr>
            )}
            {links.map((link) => (
              <tr key={link.id} className="border-b border-black/5 last:border-0 dark:border-white/10">
                <td className="max-w-xs truncate px-4 py-2">
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-black/30 hover:decoration-black dark:decoration-white/30 dark:hover:decoration-white"
                    title={link.url}
                  >
                    {link.url}
                  </a>
                </td>
                <td className="px-4 py-2">{link.category}</td>
                <td className="px-4 py-2">
                  <form
                    action={updateItemQuantity.bind(null, link.id)}
                    className="flex items-center gap-1"
                  >
                    <input
                      name="item_quantity"
                      type="number"
                      min={1}
                      step={1}
                      defaultValue={link.item_quantity}
                      className="w-16 rounded-md border border-black/15 px-2 py-1 text-sm outline-none focus:border-black/40 dark:border-white/20 dark:focus:border-white/40"
                    />
                    <button type="submit" className="text-xs underline">
                      Salvar
                    </button>
                  </form>
                </td>
                <td className="px-4 py-2">
                  <span
                    className={
                      link.active
                        ? "rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/40 dark:text-green-400"
                        : "rounded-full bg-black/10 px-2 py-0.5 text-xs font-medium text-black/60 dark:bg-white/10 dark:text-white/60"
                    }
                  >
                    {link.active ? "Ativo" : "Inativo"}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <div className="flex justify-end gap-3">
                    <form action={setLinkActive.bind(null, link.id, !link.active)}>
                      <button type="submit" className="text-xs underline">
                        {link.active ? "Desativar" : "Ativar"}
                      </button>
                    </form>
                    <form action={deleteLink.bind(null, link.id)}>
                      <button type="submit" className="text-xs text-red-600 underline">
                        Remover
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
