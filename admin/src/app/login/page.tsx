import { login } from "./actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <form
        action={login}
        className="w-full max-w-sm space-y-4 rounded-xl border border-black/10 p-6 dark:border-white/15"
      >
        <div>
          <h1 className="text-lg font-semibold">Painel do Scraper</h1>
          <p className="text-sm text-black/60 dark:text-white/60">
            Entre com a senha de administrador.
          </p>
        </div>
        <div className="space-y-1">
          <label htmlFor="password" className="text-sm font-medium">
            Senha
          </label>
          <input
            id="password"
            name="password"
            type="password"
            required
            autoFocus
            className="w-full rounded-md border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40 dark:border-white/20 dark:focus:border-white/40"
          />
        </div>
        {params.error && (
          <p className="text-sm text-red-600" role="alert">
            Senha incorreta.
          </p>
        )}
        <button
          type="submit"
          className="w-full rounded-md bg-black px-3 py-2 text-sm font-medium text-white dark:bg-white dark:text-black"
        >
          Entrar
        </button>
      </form>
    </main>
  );
}
