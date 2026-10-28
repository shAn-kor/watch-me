import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider } from "react-router-dom";
import type { ApiClient } from "../api/client";
import { ApiProvider } from "../api/provider";
import { CreatorProviders } from "../components/creator/CreatorProviders";
import type { createAppRouter } from "./router";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
}

export interface AppProps {
  router: ReturnType<typeof createAppRouter>;
  queryClient?: QueryClient;
  /** main.tsx passes the http or mock client (VITE_API_MOCK); tests pass a mock client. */
  client: ApiClient;
}

/** Providers shared by main.tsx and tests. creator providers (auth, toasts) are mounted here. */
export function App({ router, queryClient, client }: AppProps) {
  const [fallback] = useState(createQueryClient);
  return (
    <ApiProvider client={client}>
      <QueryClientProvider client={queryClient ?? fallback}>
        <CreatorProviders>
          <RouterProvider router={router} />
        </CreatorProviders>
      </QueryClientProvider>
    </ApiProvider>
  );
}
