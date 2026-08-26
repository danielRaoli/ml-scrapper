"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-md space-y-4 rounded-xl border border-red-200 bg-red-50 p-6 text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
        <h1 className="text-lg font-semibold">Algo deu errado</h1>
        <p className="text-sm">{error.message}</p>
        <button
          type="button"
          onClick={() => reset()}
          className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white"
        >
          Tentar novamente
        </button>
      </div>
    </main>
  );
}
